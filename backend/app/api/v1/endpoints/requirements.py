from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import Ctx, admin, member, viewer
from app.services.gmail.links import gmail_url
from app.core.exceptions import AppError, ConflictError
from app.models.email import EmailAccount, EmailMessage
from app.models.enums import DuplicateStatus, LifecycleStatus, ReviewStatus
from app.models.requirements import DuplicateCandidate, JobRequirement, RequirementSource, RequirementVersion
from app.schemas.api import (
    BulkIn,
    BulkOut,
    Page,
    RequirementCreate,
    RequirementDetail,
    RequirementOut,
    RequirementPatch,
    SourceOut,
    VersionOut,
)
from app.services.audit import service as audit
from app.services.deduplication.matcher import compare, profile_from_requirement
from app.services.requirements import service as svc
from app.services.requirements.query import RequirementFilters, apply_filters, apply_sort

router = APIRouter(prefix="/requirements", tags=["requirements"])


def build_outputs(db: Session, rows: list[JobRequirement], model=RequirementOut) -> list:
    """Batch-load source accounts and duplicate flags (no N+1)."""
    ids = [r.id for r in rows]
    accounts: dict[uuid.UUID, set[str]] = {}
    counts: dict[uuid.UUID, int] = {}
    pending: set[uuid.UUID] = set()
    if ids:
        for rid, email in db.execute(select(RequirementSource.job_requirement_id, EmailAccount.email_address)
                                      .join(EmailMessage, EmailMessage.id == RequirementSource.email_message_id)
                                      .join(EmailAccount, EmailAccount.id == EmailMessage.email_account_id)
                                      .where(RequirementSource.job_requirement_id.in_(ids))):
            accounts.setdefault(rid, set()).add(email)
        counts = dict(db.execute(select(RequirementSource.job_requirement_id, func.count()).where(RequirementSource.job_requirement_id.in_(ids))
                                 .group_by(RequirementSource.job_requirement_id)).all())
        for a, b in db.execute(select(DuplicateCandidate.requirement_id_a, DuplicateCandidate.requirement_id_b)
                               .where(DuplicateCandidate.review_status == DuplicateStatus.PENDING,
                                      or_(DuplicateCandidate.requirement_id_a.in_(ids), DuplicateCandidate.requirement_id_b.in_(ids)))):
            pending.update((a, b))
    out = []
    for r in rows:
        o = model.model_validate(r)
        o.source_accounts = sorted(accounts.get(r.id, set()))
        o.source_count = counts.get(r.id, 0)
        o.has_pending_duplicate = r.id in pending
        out.append(o)
    return out


def filters_dep(q: str | None = Query(None, max_length=200), date_from: datetime | None = None, date_to: datetime | None = None, account_id: uuid.UUID | None = None,
                client: str | None = None, job_title: str | None = None, skill: str | None = None, exp_min: float | None = None, exp_max: float | None = None,
                location: str | None = None, work_mode: str | None = None, salary_min: float | None = None, salary_max: float | None = None,
                recruiter: str | None = None, review_status: str | None = None, lifecycle_status: str | None = None, source_type: str | None = None,
                duplicate_status: str | None = None, include_merged: bool = False) -> RequirementFilters:
    return RequirementFilters(q=q, date_from=date_from, date_to=date_to, account_id=account_id, client=client, job_title=job_title, skill=skill,
                              exp_min=exp_min, exp_max=exp_max, location=location, work_mode=work_mode, salary_min=salary_min, salary_max=salary_max,
                              recruiter=recruiter, review_status=review_status, lifecycle_status=lifecycle_status, source_type=source_type,
                              duplicate_status=duplicate_status, include_merged=include_merged)


@router.get("", response_model=Page[RequirementOut])
def list_requirements(ctx: Ctx = viewer, f: RequirementFilters = Depends(filters_dep), page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                      sort: str = "received_at", direction: str = Query("desc", pattern="^(asc|desc)$")):
    base = apply_filters(select(JobRequirement), ctx.org_id, f)
    total = ctx.db.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = apply_sort(base.options(selectinload(JobRequirement.skills)), sort, direction).limit(page_size).offset((page - 1) * page_size)
    rows = list(ctx.db.scalars(stmt))
    return Page(items=build_outputs(ctx.db, rows), total=total, page=page, page_size=page_size)


@router.post("", response_model=RequirementDetail, status_code=201)
def create(body: RequirementCreate, ctx: Ctx = member):
    values = body.model_dump(exclude_unset=True, exclude={"received_at", "from_email_id"})
    req = svc.create_requirement(ctx.db, ctx.org_id, values, user_id=ctx.user_id, source="manual", received_at=body.received_at)
    if body.from_email_id:
        msg = ctx.db.scalar(select(EmailMessage).where(EmailMessage.id == body.from_email_id, EmailMessage.organization_id == ctx.org_id))
        if msg:
            svc.link_source(ctx.db, req, msg.id, "manual")
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="requirement.created", entity_type="requirement", entity_id=req.id)
    ctx.db.commit()
    return build_outputs(ctx.db, [req], RequirementDetail)[0]


@router.get("/{requirement_id}", response_model=RequirementDetail)
def get_one(requirement_id: uuid.UUID, ctx: Ctx = viewer):
    req = svc.get_requirement(ctx.db, ctx.org_id, requirement_id)
    return build_outputs(ctx.db, [req], RequirementDetail)[0]


@router.patch("/{requirement_id}", response_model=RequirementDetail)
def patch(requirement_id: uuid.UUID, body: RequirementPatch, ctx: Ctx = member):
    req = svc.get_requirement(ctx.db, ctx.org_id, requirement_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("minimum_experience") is not None and data.get("maximum_experience") is not None and data["maximum_experience"] < data["minimum_experience"]:
        raise AppError("maximum_experience must be >= minimum_experience", status_code=422, code="validation_error")
    if data.get("salary_min") is not None and data.get("salary_max") is not None and data["salary_max"] < data["salary_min"]:
        raise AppError("salary_max must be >= salary_min", status_code=422, code="validation_error")
    svc.update_requirement(ctx.db, req, data, user_id=ctx.user_id, source="manual_edit")
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="requirement.edited", entity_type="requirement", entity_id=req.id, metadata={"fields": sorted(data)})
    ctx.db.commit()
    ctx.db.refresh(req)
    return build_outputs(ctx.db, [req], RequirementDetail)[0]


@router.delete("/{requirement_id}")
def delete(requirement_id: uuid.UUID, ctx: Ctx = admin):
    """Safe deletion policy: requirements are archived (soft delete). Evidence and history are never destroyed here."""
    req = svc.get_requirement(ctx.db, ctx.org_id, requirement_id)
    svc.set_lifecycle_status(ctx.db, req, LifecycleStatus.ARCHIVED, ctx.user_id)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="requirement.archived", entity_type="requirement", entity_id=req.id, metadata={"via": "delete"})
    ctx.db.commit()
    return {"archived": True}


def _act(ctx: Ctx, rid: uuid.UUID, action: str) -> JobRequirement:
    req = svc.get_requirement(ctx.db, ctx.org_id, rid)
    if req.lifecycle_status == LifecycleStatus.MERGED:
        raise ConflictError("Merged requirements cannot be changed")
    if action == "approve":
        svc.set_review_status(ctx.db, req, ReviewStatus.APPROVED, ctx.user_id)
    elif action == "reject":
        svc.set_review_status(ctx.db, req, ReviewStatus.REJECTED, ctx.user_id)
    elif action == "archive":
        svc.set_lifecycle_status(ctx.db, req, LifecycleStatus.ARCHIVED, ctx.user_id)
    elif action == "restore":
        svc.set_lifecycle_status(ctx.db, req, LifecycleStatus.ACTIVE, ctx.user_id)
        if req.review_status == ReviewStatus.REJECTED:
            svc.set_review_status(ctx.db, req, ReviewStatus.NEEDS_REVIEW, ctx.user_id)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action=f"requirement.{action}d" if action != "reject" else "requirement.rejected",
                 entity_type="requirement", entity_id=req.id)
    return req


for _a in ("approve", "reject", "archive", "restore"):
    def _make(action: str):
        def endpoint(requirement_id: uuid.UUID, ctx: Ctx = member):
            req = _act(ctx, requirement_id, action)
            ctx.db.commit()
            return build_outputs(ctx.db, [req], RequirementDetail)[0]
        endpoint.__name__ = f"{action}_requirement"
        return endpoint
    router.add_api_route(f"/{{requirement_id}}/{_a}", _make(_a), methods=["POST"], response_model=RequirementDetail)


@router.post("/bulk", response_model=BulkOut)
def bulk(body: BulkIn, ctx: Ctx = member):
    ok: list[uuid.UUID] = []
    failed: list[dict] = []
    for rid in dict.fromkeys(body.ids):
        try:
            with ctx.db.begin_nested():
                _act(ctx, rid, body.action)
            ok.append(rid)
        except AppError as e:
            failed.append({"id": str(rid), "error": e.message})
    ctx.db.commit()
    return BulkOut(succeeded=ok, failed=failed)


@router.get("/{requirement_id}/sources", response_model=list[SourceOut])
def sources(requirement_id: uuid.UUID, ctx: Ctx = viewer):
    svc.get_requirement(ctx.db, ctx.org_id, requirement_id)
    rows = ctx.db.execute(select(RequirementSource, EmailMessage, EmailAccount.email_address)
                          .join(EmailMessage, EmailMessage.id == RequirementSource.email_message_id, isouter=True)
                          .join(EmailAccount, EmailAccount.id == EmailMessage.email_account_id, isouter=True)
                          .where(RequirementSource.job_requirement_id == requirement_id).order_by(RequirementSource.linked_at.desc())).all()
    return [SourceOut(id=s.id, source_type=s.source_type, linked_at=s.linked_at, email_message_id=s.email_message_id, account_email=email,
                      sender=m.sender if m else None, subject=m.subject if m else None, received_at=m.received_at if m else None,
                      gmail_url=gmail_url(email, m.gmail_message_id) if m else None, evidence=s.evidence_metadata or {}) for s, m, email in rows]


@router.get("/{requirement_id}/versions", response_model=list[VersionOut])
def versions(requirement_id: uuid.UUID, ctx: Ctx = viewer):
    svc.get_requirement(ctx.db, ctx.org_id, requirement_id)
    return list(ctx.db.scalars(select(RequirementVersion).where(RequirementVersion.job_requirement_id == requirement_id).order_by(RequirementVersion.version_number.desc())))


@router.get("/{requirement_id}/similar")
def similar(requirement_id: uuid.UUID, ctx: Ctx = viewer, limit: int = Query(10, ge=1, le=50)):
    req = svc.get_requirement(ctx.db, ctx.org_id, requirement_id)
    prof = profile_from_requirement(req)
    conds = []
    if req.client_normalized:
        conds.append(JobRequirement.client_normalized == req.client_normalized)
    if req.title_normalized:
        conds.append(JobRequirement.title_normalized == req.title_normalized)
    if req.job_reference_id:
        conds.append(JobRequirement.job_reference_id == req.job_reference_id)
    first = (req.title_normalized or "").split(" ")[0]
    if first:
        conds.append(JobRequirement.title_normalized.ilike(f"%{first}%"))
    if not conds:
        return []
    pool = ctx.db.scalars(select(JobRequirement).options(selectinload(JobRequirement.skills)).where(
        JobRequirement.organization_id == ctx.org_id, JobRequirement.id != req.id, JobRequirement.lifecycle_status != LifecycleStatus.MERGED, or_(*conds)).limit(200)).all()
    scored = []
    for r in pool:
        c = compare(prof, profile_from_requirement(r))
        scored.append((c.score, r, c))
    scored.sort(key=lambda t: -t[0])
    top = scored[:limit]
    outs = build_outputs(ctx.db, [r for _, r, _ in top])
    return [{"score": s, "reasons": c.reasons, "conflicts": c.conflicts, "requirement": o} for (s, _, c), o in zip(top, outs)]
