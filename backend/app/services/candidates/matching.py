"""Candidate <-> requirement matching: transparent weighted score with reasons (no AI call at match time, fully deterministic).

The candidate is evaluated as the UNION of the saved profile and the latest AI profile (if one exists): skills from both (including
skills tied to roles and project technologies), the larger of the two experience figures, locations from both, and role titles from the
current role and the AI-extracted work history. Nothing has to be "applied" first. Results say which matches came only from the AI profile.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.candidate_ai import CandidateAIProfile
from app.models.candidates import Candidate, CandidateSubmission
from app.models.enums import LifecycleStatus, ReviewStatus
from app.models.requirements import JobRequirement
from app.services.normalization.text import normalize_location, normalize_skill, normalize_title

W_SKILLS, W_EXP, W_LOC, W_TITLE = 0.60, 0.25, 0.15, 0.10
_GENERIC_TITLE_WORDS = {"senior", "junior", "lead", "sr", "jr", "the", "and", "for", "with", "staff", "principal", "associate", "intern"}


@dataclass
class Match:
    score: int
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    ai_profile_used: bool = False
    ai_only_matches: list[str] = field(default_factory=list)  # requirement skills matched only thanks to the AI profile


@dataclass
class AiView:
    """The parts of a candidate's latest AI profile that matching uses."""

    skills: dict[str, str]
    experience_years: float | None
    location: str | None
    titles: list[str]


def ai_view(result: dict | None) -> AiView | None:
    if not result:
        return None
    p = (result or {}).get("profile") or {}
    a = (result or {}).get("analytics") or {}
    raw: list[str] = [*(p.get("skills") or []), *(p.get("top_skills") or [])]
    for pos in p.get("positions") or []:
        raw += pos.get("skills_used") or []
    for pr in p.get("projects") or []:
        raw += pr.get("technologies") or []
    skills: dict[str, str] = {}
    for s in raw:
        n = normalize_skill(s)
        if n:
            skills.setdefault(n, s)
    titles = [t for t in [p.get("current_title"), *[x.get("title") for x in p.get("positions") or []]] if t]
    return AiView(skills, a.get("total_experience_years"), p.get("location"), titles)


def latest_ai_views(db: Session, org_id: uuid.UUID, candidate_ids: list[uuid.UUID] | None = None) -> dict[uuid.UUID, AiView]:
    """Latest successful AI profile per candidate (older runs are ignored)."""
    q = select(CandidateAIProfile.candidate_id, CandidateAIProfile.result).where(CandidateAIProfile.organization_id == org_id, CandidateAIProfile.status == "succeeded")
    if candidate_ids is not None:
        if not candidate_ids:
            return {}
        q = q.where(CandidateAIProfile.candidate_id.in_(candidate_ids))
    out: dict[uuid.UUID, AiView] = {}
    for cid, result in db.execute(q.order_by(CandidateAIProfile.created_at.desc())):
        if cid not in out and (v := ai_view(result)):
            out[cid] = v
    return out


def _tokens(s: str | None) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", normalize_location(s)) if len(t) > 2}


def _word_in(short: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9+#.]){re.escape(short)}(?![a-z0-9+#])", phrase) is not None


def skill_matches(req_skill: str, cand_skills: dict[str, str]) -> bool:
    """Exact match, or a short skill appearing as whole words inside a longer one in either direction.

    Requirement skills are often phrases ("Docker, Kubernetes and cloud platforms") while candidates list keywords ("Docker"),
    so 'docker' matches that phrase. Skills of 1-2 characters (R, Go) must match exactly to avoid accidental hits.
    """
    if req_skill in cand_skills:
        return True
    for cs in cand_skills:
        short, long_ = (cs, req_skill) if len(cs) <= len(req_skill) else (req_skill, cs)
        if len(short) >= 3 and short != long_ and _word_in(short, long_):
            return True
    return False


def _title_tokens(t: str | None) -> set[str]:
    return {w for w in normalize_title(t).split() if len(w) > 2 and w not in _GENERIC_TITLE_WORDS}


def score(cand: Candidate, req: JobRequirement, ai: AiView | None = None) -> Match:
    reasons: list[str] = []
    parts: list[tuple[float, float]] = []  # (weight, 0..1)
    profile_skills = {s.normalized: s.name for s in cand.skills}
    cskills = dict(profile_skills)
    if ai:
        for k, v in ai.skills.items():
            cskills.setdefault(k, v)
    required = {s.normalized: s.name for s in req.skills if s.kind == "required"}
    preferred = {s.normalized: s.name for s in req.skills if s.kind == "preferred"}
    matched = [required[k] for k in required if skill_matches(k, cskills)]
    missing = [required[k] for k in required if not skill_matches(k, cskills)]
    ai_only = [required[k] for k in required if skill_matches(k, cskills) and not skill_matches(k, profile_skills)] if ai else []
    if required:
        cov = len(matched) / len(required)
        pref_cov = (sum(1 for k in preferred if skill_matches(k, cskills)) / len(preferred)) if preferred else 0.0
        parts.append((W_SKILLS, min(1.0, cov * 0.88 + pref_cov * 0.12) if preferred else cov))  # preferred skills only matter when the job lists some
        reasons.append(f"Has {len(matched)} of {len(required)} required skills" + (f" ({len(ai_only)} only found in the AI profile)" if ai_only else ""))

    exp_candidates = [x for x in (cand.total_experience, ai.experience_years if ai else None) if x is not None]
    exp = max(exp_candidates) if exp_candidates else None
    lo, hi = req.minimum_experience, req.maximum_experience
    if exp is not None and lo is not None:
        top = hi if hi is not None else lo + 3
        src = " (from the AI profile's dated work history)" if ai and ai.experience_years is not None and exp == ai.experience_years and exp != cand.total_experience else ""
        if lo - 0.5 <= exp <= top + 1:
            parts.append((W_EXP, 1.0))
            reasons.append(f"Experience fits ({exp:g} yrs vs {lo:g}-{top:g}){src}")
        elif lo - 2 <= exp <= top + 3:
            parts.append((W_EXP, 0.5))
            reasons.append(f"Experience is close ({exp:g} yrs vs {lo:g}-{top:g}){src}")
        else:
            parts.append((W_EXP, 0.0))
            reasons.append(f"Experience differs ({exp:g} yrs vs {lo:g}-{top:g}){src}")

    if req.work_mode == "remote":
        parts.append((W_LOC, 1.0))
        reasons.append("Role is remote")
    elif req.location_normalized:
        rt = _tokens(req.location)
        here = _tokens(cand.current_location) | (_tokens(ai.location) if ai else set())
        pref = set().union(*[_tokens(x) for x in (cand.preferred_locations or [])]) if cand.preferred_locations else set()
        if rt & here:
            parts.append((W_LOC, 1.0))
            reasons.append("Located in the job's city")
        elif rt & pref:
            parts.append((W_LOC, 0.8))
            reasons.append("Prefers the job's location")
        elif cand.willing_to_relocate:
            parts.append((W_LOC, 0.6))
            reasons.append("Willing to relocate")
        elif here or pref:
            parts.append((W_LOC, 0.0))
            reasons.append("Different location")

    rtitle = _title_tokens(req.job_title)
    titles = [t for t in [cand.current_title, *(ai.titles if ai else [])] if t]
    if rtitle and titles:
        best = max(len(rtitle & _title_tokens(t)) / len(rtitle) for t in titles)
        if best >= 0.99:
            parts.append((W_TITLE, 1.0))
            reasons.append("Has held a matching role title")
        elif best >= 0.5:
            parts.append((W_TITLE, 0.6))
            reasons.append("Has held a similar role title")
        elif best > 0:
            parts.append((W_TITLE, 0.3))
            reasons.append("Some overlap with the role title")
        else:
            parts.append((W_TITLE, 0.0))

    total_w = sum(w for w, _ in parts)
    pct = round(100 * sum(w * v for w, v in parts) / total_w) if total_w else 0
    if not required and not parts:
        reasons.append("Not enough data on the requirement to compare")
    return Match(pct, matched, missing, reasons, ai_profile_used=ai is not None, ai_only_matches=ai_only)


def matching_candidates(db: Session, org_id: uuid.UUID, req: JobRequirement, limit: int = 20, min_score: int = 35) -> list[tuple[Candidate, Match, str | None]]:
    """Top candidates for a requirement. The third item is the candidate's existing pipeline stage for this requirement, if any."""
    stages = {cid: st for cid, st in db.execute(select(CandidateSubmission.candidate_id, CandidateSubmission.stage).where(CandidateSubmission.requirement_id == req.id))}
    cands = list(db.scalars(select(Candidate).options(selectinload(Candidate.skills)).where(
        Candidate.organization_id == org_id, Candidate.is_archived.is_(False), Candidate.status.not_in(["rejected", "hired", "not_interested"])).limit(3000)))
    views = latest_ai_views(db, org_id, [c.id for c in cands])
    has_required = bool([s for s in req.skills if s.kind == "required"])
    out = []
    for c in cands:
        m = score(c, req, views.get(c.id))
        if m.score >= min_score and (m.matched_skills or not has_required):
            out.append((c, m, stages.get(c.id)))
    out.sort(key=lambda t: (-t[1].score, t[0].full_name.lower()))
    return out[:limit]


def matching_requirements(db: Session, org_id: uuid.UUID, cand: Candidate, limit: int = 15, min_score: int = 35) -> list[tuple[JobRequirement, Match, str | None]]:
    stages = {rid: st for rid, st in db.execute(select(CandidateSubmission.requirement_id, CandidateSubmission.stage).where(CandidateSubmission.candidate_id == cand.id))}
    ai = latest_ai_views(db, org_id, [cand.id]).get(cand.id)
    reqs = db.scalars(select(JobRequirement).options(selectinload(JobRequirement.skills)).where(
        JobRequirement.organization_id == org_id, JobRequirement.lifecycle_status == LifecycleStatus.ACTIVE,
        JobRequirement.review_status != ReviewStatus.REJECTED).limit(3000))
    out = []
    for r in reqs:
        m = score(cand, r, ai)
        if m.score >= min_score and (m.matched_skills or not [s for s in r.skills if s.kind == "required"]):
            out.append((r, m, stages.get(r.id)))
    out.sort(key=lambda t: -t[1].score)
    return out[:limit]
