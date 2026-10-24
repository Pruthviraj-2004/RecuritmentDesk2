"""Requirement lifecycle: create, edit (versioned), ingest from extraction with deduplication, merge."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailure
from app.db.types import utcnow
from app.models.email import EmailMessage
from app.models.enums import DuplicateStatus, LifecycleStatus, ReviewStatus
from app.models.requirements import (
    DuplicateCandidate,
    JobRequirement,
    RequirementSkill,
    RequirementSource,
    RequirementVersion,
)
from app.services.app_settings import DedupSettings
from app.services.deduplication.matcher import (
    decide,
    ordered_pair,
    profile_from_extracted,
    profile_from_requirement,
)
from app.services.extraction.schema import ExtractedRequirement
from app.services.normalization.text import (
    normalize_company,
    normalize_location,
    normalize_skill_list,
    normalize_title,
    requirement_fingerprint,
    skill_category,
)

SCALAR_FIELDS = [
    "client_name", "job_title", "job_reference_id", "job_description", "department", "seniority", "minimum_experience",
    "maximum_experience", "education", "domain_experience", "salary_min", "salary_max", "salary_currency", "salary_period",
    "employment_type", "notice_period", "location", "city", "state", "country", "work_mode", "relocation", "travel",
    "recruiter_name", "recruiter_email", "recruiter_phone", "client_contact", "submission_email", "submission_instructions",
    "number_of_openings",
]
LIST_FIELDS = ["certifications", "required_documents"]
EDITABLE_FIELDS = SCALAR_FIELDS + LIST_FIELDS + ["required_skills", "preferred_skills"]
_NUMERIC = {"salary_min", "salary_max", "minimum_experience", "maximum_experience"}


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def snapshot(req: JobRequirement) -> dict:
    snap = {f: _jsonable(getattr(req, f)) for f in SCALAR_FIELDS + LIST_FIELDS}
    snap["required_skills"] = sorted(req.required_skills)
    snap["preferred_skills"] = sorted(req.preferred_skills)
    snap["review_status"] = req.review_status
    snap["lifecycle_status"] = req.lifecycle_status
    return snap


def location_display(city: str | None, state: str | None, country: str | None, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    parts = [p for p in (city, state, country) if p]
    return ", ".join(parts) or None


def refresh_derived(req: JobRequirement) -> None:
    req.client_normalized = normalize_company(req.client_name) or None
    req.title_normalized = normalize_title(req.job_title) or None
    req.location = location_display(req.city, req.state, req.country, req.location)
    req.location_normalized = normalize_location(req.location) or None
    req.canonical_fingerprint = requirement_fingerprint(req.client_name, req.job_title, req.job_reference_id, req.location)
    req.last_updated_at = utcnow()


def _set_skills(req: JobRequirement, required: list[str] | None, preferred: list[str] | None) -> None:
    if required is None and preferred is None:
        return
    cur_req = [(s.name, s.normalized) for s in req.skills if s.kind == "required"]
    cur_pref = [(s.name, s.normalized) for s in req.skills if s.kind == "preferred"]
    new_req = normalize_skill_list(required) if required is not None else cur_req
    req_norms = {n for _, n in new_req}
    new_pref = [(d, n) for d, n in (normalize_skill_list(preferred) if preferred is not None else cur_pref) if n not in req_norms]
    wanted = {(norm, kind): display for kind, items in (("required", new_req), ("preferred", new_pref)) for display, norm in items}
    # differential update: avoids insert-before-delete unique violations within one flush
    for s in list(req.skills):
        if (s.normalized, s.kind) not in wanted:
            req.skills.remove(s)
        else:
            s.name = wanted.pop((s.normalized, s.kind))
    for (norm, kind), display in wanted.items():
        req.skills.append(RequirementSkill(name=display, normalized=norm, kind=kind, category=skill_category(norm)))


def _add_version(db: Session, req: JobRequirement, prev: dict, new: dict, source: str, user_id: uuid.UUID | None) -> None:
    changed_prev = {k: v for k, v in prev.items() if new.get(k) != v}
    if not changed_prev:
        return
    changed_new = {k: new.get(k) for k in changed_prev}
    req.version_number = (req.version_number or 0) + 1
    db.add(RequirementVersion(job_requirement_id=req.id, version_number=req.version_number, previous_values=changed_prev,
                              new_values=changed_new, change_source=source, changed_by=user_id))


def create_requirement(db: Session, org_id: uuid.UUID, values: dict, *, user_id: uuid.UUID | None, source: str = "manual",
                       review_status: str = ReviewStatus.NEEDS_REVIEW, received_at: datetime | None = None,
                       confidence: float | None = None, model: str | None = None, warnings: list[str] | None = None) -> JobRequirement:
    req = JobRequirement(organization_id=org_id, review_status=str(review_status), received_at=received_at,
                         extraction_confidence=confidence, extraction_model=model, validation_warnings=warnings or [],
                         created_by=user_id, updated_by=user_id, version_number=1, certifications=[], required_documents=[])
    for f in SCALAR_FIELDS + LIST_FIELDS:
        if f in values and values[f] is not None:
            setattr(req, f, values[f])
    if not req.work_mode:
        req.work_mode = "unknown"
    req.id = uuid.uuid4()
    refresh_derived(req)
    db.add(req)
    _set_skills(req, values.get("required_skills") or [], values.get("preferred_skills") or [])
    db.flush()
    db.add(RequirementVersion(job_requirement_id=req.id, version_number=1, previous_values={}, new_values=snapshot(req),
                              change_source=source, changed_by=user_id))
    return req


def update_requirement(db: Session, req: JobRequirement, patch: dict, *, user_id: uuid.UUID | None, source: str = "manual_edit") -> JobRequirement:
    unknown = set(patch) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValidationFailure(f"Unknown or read-only fields: {sorted(unknown)}")
    if req.lifecycle_status == LifecycleStatus.MERGED:
        raise ConflictError("A merged requirement cannot be edited; edit the surviving record instead")
    prev = snapshot(req)
    for f in SCALAR_FIELDS + LIST_FIELDS:
        if f in patch:
            v = patch[f]
            if f in _NUMERIC and v is not None:
                v = float(v)
            setattr(req, f, v if v != "" else None)
    if "city" in patch or "state" in patch or "country" in patch:
        if "location" not in patch:
            req.location = None
    _set_skills(req, patch.get("required_skills"), patch.get("preferred_skills"))
    db.flush()
    db.refresh(req, attribute_names=["skills"])
    refresh_derived(req)
    req.updated_by = user_id
    if source == "manual_edit":
        req.validation_warnings = [w for w in (req.validation_warnings or []) if not w.startswith("conflict:")]
    _add_version(db, req, prev, snapshot(req), source, user_id)
    return req


def set_review_status(db: Session, req: JobRequirement, status: str, user_id: uuid.UUID | None) -> JobRequirement:
    prev = snapshot(req)
    req.review_status = status
    req.updated_by = user_id
    if status == ReviewStatus.APPROVED:
        req.validation_warnings = []  # approving means a person reviewed the record, so the automatic warnings are resolved
    _add_version(db, req, prev, snapshot(req), "status", user_id)
    return req


def set_lifecycle_status(db: Session, req: JobRequirement, status: str, user_id: uuid.UUID | None) -> JobRequirement:
    if req.lifecycle_status == LifecycleStatus.MERGED:
        raise ConflictError("A merged requirement cannot change status")
    prev = snapshot(req)
    req.lifecycle_status = status
    req.updated_by = user_id
    _add_version(db, req, prev, snapshot(req), "status", user_id)
    return req


def get_requirement(db: Session, org_id: uuid.UUID, req_id: uuid.UUID) -> JobRequirement:
    req = db.scalar(select(JobRequirement).options(selectinload(JobRequirement.skills), selectinload(JobRequirement.sources))
                    .where(JobRequirement.id == req_id, JobRequirement.organization_id == org_id))
    if not req:
        raise NotFoundError("Requirement not found")
    return req


def link_source(db: Session, req: JobRequirement, message_id: uuid.UUID | None, source_type: str, evidence: dict | None = None) -> bool:
    """Idempotent: returns False if this (requirement, message, type) link already exists."""
    exists = db.scalar(select(RequirementSource.id).where(
        RequirementSource.job_requirement_id == req.id, RequirementSource.email_message_id == message_id,
        RequirementSource.source_type == source_type))
    if exists:
        return False
    db.add(RequirementSource(job_requirement_id=req.id, email_message_id=message_id, source_type=source_type, evidence_metadata=evidence or {}))
    db.flush()
    return True


# ----------------------------------------------------------------------------------------------------------------
# Ingestion from extraction
# ----------------------------------------------------------------------------------------------------------------
@dataclass
class IngestOutcome:
    action: str  # created | attached_exact | created_probable | created_related | created_insufficient | no_match_closure | unchanged
    requirement: JobRequirement | None
    candidate: DuplicateCandidate | None = None
    conflicts: list[str] | None = None


def extracted_to_values(e: ExtractedRequirement) -> dict:
    d = e.model_dump(exclude={"evidence", "field_confidence"})
    d["location"] = location_display(e.city, e.state, e.country)
    return d


def _candidate_pool(db: Session, org_id: uuid.UUID, e: ExtractedRequirement, fp: str | None, exclude_id: uuid.UUID | None) -> list[JobRequirement]:
    conds = []
    if fp:
        conds.append(JobRequirement.canonical_fingerprint == fp)
    c, t = normalize_company(e.client_name), normalize_title(e.job_title)
    if c:
        conds.append(JobRequirement.client_normalized == c)
    if e.job_reference_id:
        conds.append(JobRequirement.job_reference_id == e.job_reference_id)
    if t:
        conds.append(JobRequirement.title_normalized == t)
    if not conds:
        return []
    q = (select(JobRequirement).options(selectinload(JobRequirement.skills))
         .where(JobRequirement.organization_id == org_id, JobRequirement.lifecycle_status != LifecycleStatus.MERGED, or_(*conds))
         .order_by(JobRequirement.received_at.desc().nullslast()).limit(200))
    if exclude_id:
        q = q.where(JobRequirement.id != exclude_id)
    return list(db.scalars(q))


def _store_candidate(db: Session, org_id: uuid.UUID, a: JobRequirement, b: JobRequirement, score: float, reasons: list[str],
                     conflicts: list[str], status: str) -> DuplicateCandidate:
    id_a, id_b = ordered_pair(a.id, b.id)
    cand = db.scalar(select(DuplicateCandidate).where(DuplicateCandidate.requirement_id_a == id_a, DuplicateCandidate.requirement_id_b == id_b))
    if cand:
        return cand
    cand = DuplicateCandidate(organization_id=org_id, requirement_id_a=id_a, requirement_id_b=id_b, matching_score=score,
                              matching_reasons=reasons, conflicting_fields=conflicts, review_status=status)
    if status != DuplicateStatus.PENDING:
        cand.resolved_at = utcnow()
    db.add(cand)
    db.flush()
    return cand


def _enrich_from_new(db: Session, existing: JobRequirement, e: ExtractedRequirement, new_vals: dict, user_id) -> list[str]:
    """Fill empty fields from a duplicate source; report fields that conflict (never silently overwritten)."""
    prev = snapshot(existing)
    conflicts: list[str] = []
    for f in SCALAR_FIELDS:
        nv = new_vals.get(f)
        if nv in (None, "", "unknown"):
            continue
        cv = getattr(existing, f)
        if cv in (None, "", "unknown"):
            setattr(existing, f, nv)
        elif f not in ("job_description", "location") and _jsonable(cv) != nv and str(cv).strip().lower() != str(nv).strip().lower():
            conflicts.append(f)
    for kind_field in ("required_skills", "preferred_skills"):
        have = set(getattr(existing, kind_field))
        new_items = [s for s in new_vals.get(kind_field, []) if s and s.lower() not in {h.lower() for h in have}]
        if new_items and not have:
            _set_skills(existing, new_vals.get("required_skills") if kind_field == "required_skills" else None,
                        new_vals.get("preferred_skills") if kind_field == "preferred_skills" else None)
        elif new_items and kind_field == "required_skills":
            conflicts.append("required_skills")
    db.flush()
    db.refresh(existing, attribute_names=["skills"])
    refresh_derived(existing)
    _add_version(db, existing, prev, snapshot(existing), "dedup_enrichment", user_id)
    if conflicts:
        existing.validation_warnings = sorted(set((existing.validation_warnings or []) + [f"conflict:{c}" for c in conflicts]))
        if existing.review_status == ReviewStatus.APPROVED:
            existing.review_status = ReviewStatus.NEEDS_REVIEW
    return conflicts


def ingest_extracted(db: Session, org_id: uuid.UUID, message: EmailMessage, e: ExtractedRequirement, *, warnings: list[str], confidence: float,
                     model: str | None, classification: str, source_type: str, dedup: DedupSettings, needs_review_threshold: float,
                     user_id: uuid.UUID | None = None) -> IngestOutcome:
    vals = extracted_to_values(e)
    loc = vals["location"]
    received = message.received_at
    new_profile = profile_from_extracted(e, loc, received)

    # Reprocessing the same message must not create duplicates: prefer requirements already sourced from this message.
    prior = list(db.scalars(select(JobRequirement).options(selectinload(JobRequirement.skills))
                            .join(RequirementSource, RequirementSource.job_requirement_id == JobRequirement.id)
                            .where(RequirementSource.email_message_id == message.id, JobRequirement.organization_id == org_id,
                                   JobRequirement.lifecycle_status != LifecycleStatus.MERGED)))
    pool = {r.id: r for r in prior}
    for r in _candidate_pool(db, org_id, e, new_profile.fingerprint, None):
        pool.setdefault(r.id, r)

    best = None
    for r in pool.values():
        d = decide(new_profile, profile_from_requirement(r), dedup.probable_threshold, dedup.related_threshold, dedup.time_window_days,
                   dedup.require_client_for_auto_attach)
        rank = {"exact": 4, "probable": 3, "related": 2, "insufficient": 1, "distinct": 0}[d.kind]
        if r in prior and d.kind in ("exact", "probable"):
            rank += 0.5
        if best is None or (rank, d.score) > (best[0], best[1].score):
            best = (rank, d, r)

    kind = best[1].kind if best else "distinct"
    existing = best[2] if best else None

    if classification == "job_closure":
        if kind == "exact" and existing is not None:
            link_source(db, existing, message.id, "closure_notice", {"classification": classification})
            existing.validation_warnings = sorted(set((existing.validation_warnings or []) + ["closure_notice_received"]))
            return IngestOutcome("attached_exact", existing)
        return IngestOutcome("no_match_closure", None)

    if kind == "exact" and existing is not None and dedup.auto_attach_exact:
        added = link_source(db, existing, message.id, source_type, {"match": "exact", "score": best[1].score, "reasons": best[1].reasons})
        conflicts: list[str] = []
        if added or classification == "updated_requirement":
            conflicts = _enrich_from_new(db, existing, e, vals, user_id)
            if received and (existing.received_at is None or received > existing.received_at):
                existing.last_updated_at = utcnow()
        return IngestOutcome("attached_exact" if added else "unchanged", existing, conflicts=conflicts)

    status = ReviewStatus.NEEDS_REVIEW
    all_warnings = list(warnings)
    if kind == "insufficient" or not (e.job_title or e.job_reference_id):
        all_warnings.append("insufficient_information")
    req = create_requirement(db, org_id, vals, user_id=user_id, source="extraction", review_status=status, received_at=received,
                             confidence=confidence, model=model, warnings=all_warnings)
    link_source(db, req, message.id, source_type, {"classification": classification, "evidence": e.evidence})
    if existing is not None and kind == "probable":
        cand = _store_candidate(db, org_id, req, existing, best[1].score, best[1].reasons, best[1].conflicts, DuplicateStatus.PENDING)
        return IngestOutcome("created_probable", req, cand, best[1].conflicts)
    if existing is not None and kind == "related" and dedup.create_related_links:
        cand = _store_candidate(db, org_id, req, existing, best[1].score, best[1].reasons, best[1].conflicts, DuplicateStatus.RELATED)
        return IngestOutcome("created_related", req, cand)
    if existing is not None and kind == "exact":  # auto attach disabled by policy -> human review
        cand = _store_candidate(db, org_id, req, existing, best[1].score, best[1].reasons, best[1].conflicts, DuplicateStatus.PENDING)
        return IngestOutcome("created_probable", req, cand)
    return IngestOutcome("created_insufficient" if kind == "insufficient" else "created", req)


# ----------------------------------------------------------------------------------------------------------------
# Duplicate review actions
# ----------------------------------------------------------------------------------------------------------------
def get_candidate(db: Session, org_id: uuid.UUID, cid: uuid.UUID) -> DuplicateCandidate:
    c = db.scalar(select(DuplicateCandidate).where(DuplicateCandidate.id == cid, DuplicateCandidate.organization_id == org_id))
    if not c:
        raise NotFoundError("Duplicate candidate not found")
    return c


def merge_requirements(db: Session, org_id: uuid.UUID, cand: DuplicateCandidate, survivor_id: uuid.UUID, user_id: uuid.UUID) -> JobRequirement:
    """Merge the other record into `survivor_id`. Sources, skills and history are preserved; nothing is deleted."""
    if cand.review_status == DuplicateStatus.MERGED:
        raise ConflictError("This duplicate has already been merged")
    if survivor_id not in (cand.requirement_id_a, cand.requirement_id_b):
        raise ValidationFailure("survivor_id must be one of the two requirements in this duplicate candidate")
    loser_id = cand.requirement_id_b if survivor_id == cand.requirement_id_a else cand.requirement_id_a
    survivor = get_requirement(db, org_id, survivor_id)
    loser = get_requirement(db, org_id, loser_id)
    if loser.lifecycle_status == LifecycleStatus.MERGED or survivor.lifecycle_status == LifecycleStatus.MERGED:
        raise ConflictError("One of the requirements has already been merged elsewhere")

    prev = snapshot(survivor)
    prev_version = survivor.version_number
    for f in SCALAR_FIELDS:
        if getattr(survivor, f) in (None, "", "unknown") and getattr(loser, f) not in (None, "", "unknown"):
            setattr(survivor, f, getattr(loser, f))
    for f in LIST_FIELDS:
        merged = list(dict.fromkeys((getattr(survivor, f) or []) + (getattr(loser, f) or [])))
        setattr(survivor, f, merged)
    have = {(s.normalized, s.kind) for s in survivor.skills}
    req_norms = {s.normalized for s in survivor.skills if s.kind == "required"}
    for s in loser.skills:
        if (s.normalized, s.kind) not in have and not (s.kind == "preferred" and s.normalized in req_norms):
            survivor.skills.append(RequirementSkill(name=s.name, normalized=s.normalized, kind=s.kind, category=s.category))
    existing_keys = {(s.email_message_id, s.source_type) for s in survivor.sources}
    for src in list(loser.sources):
        if (src.email_message_id, src.source_type) in existing_keys:
            continue
        db.add(RequirementSource(job_requirement_id=survivor.id, email_message_id=src.email_message_id, source_type=src.source_type,
                                 evidence_metadata={**(src.evidence_metadata or {}), "merged_from": str(loser.id)}, linked_at=src.linked_at))
    db.flush()
    db.refresh(survivor, attribute_names=["skills", "sources"])
    if loser.received_at and (survivor.received_at is None or loser.received_at < survivor.received_at):
        survivor.received_at = loser.received_at  # first-seen date
    refresh_derived(survivor)
    survivor.updated_by = user_id
    _add_version(db, survivor, prev, snapshot(survivor), "merge", user_id)
    if survivor.version_number == prev_version:  # nothing but sources changed: still record the merge in history
        survivor.version_number += 1
        db.add(RequirementVersion(job_requirement_id=survivor.id, version_number=survivor.version_number, previous_values={},
                                  new_values={"merged_from": str(loser.id)}, change_source="merge", changed_by=user_id))

    loser_prev = snapshot(loser)
    loser.lifecycle_status = LifecycleStatus.MERGED
    loser.merged_into_id = survivor.id
    loser.updated_by = user_id
    _add_version(db, loser, loser_prev, snapshot(loser), "merge", user_id)

    cand.review_status = DuplicateStatus.MERGED
    cand.resolved_by, cand.resolved_at = user_id, utcnow()
    # other pending candidates that referenced the loser now refer to the survivor's lineage: dismiss them for re-evaluation
    others = db.scalars(select(DuplicateCandidate).where(
        DuplicateCandidate.organization_id == org_id, DuplicateCandidate.id != cand.id, DuplicateCandidate.review_status == DuplicateStatus.PENDING,
        or_(DuplicateCandidate.requirement_id_a == loser.id, DuplicateCandidate.requirement_id_b == loser.id)))
    for o in others:
        o.review_status = DuplicateStatus.DISMISSED
        o.resolved_by, o.resolved_at = user_id, utcnow()
    return survivor


def resolve_candidate(db: Session, cand: DuplicateCandidate, status: str, user_id: uuid.UUID) -> DuplicateCandidate:
    if cand.review_status == DuplicateStatus.MERGED:
        raise ConflictError("A merged duplicate cannot be changed; merges are permanent")
    cand.review_status = status
    cand.resolved_by, cand.resolved_at = user_id, utcnow()
    return cand


def reopen_candidate(db: Session, cand: DuplicateCandidate) -> DuplicateCandidate:
    if cand.review_status == DuplicateStatus.MERGED:
        raise ConflictError("A merged duplicate cannot be reopened")
    cand.review_status = DuplicateStatus.PENDING
    cand.resolved_by, cand.resolved_at = None, None
    return cand
