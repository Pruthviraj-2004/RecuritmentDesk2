"""Requirement deduplication: deterministic rules first, then weighted similarity.

Decisions:
  exact        -> safe to attach the new source to the existing requirement automatically
  probable     -> create a new record + a duplicate review item (a human decides)
  related      -> keep separate, record a relationship (e.g. same client/role family, different job IDs)
  distinct     -> unrelated record
  insufficient -> not enough comparable data; manual review
Title similarity alone NEVER produces a merge or a probable duplicate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher

from app.services.normalization.text import (
    normalize_company,
    normalize_location,
    normalize_skill,
    normalize_title,
    requirement_fingerprint,
)

WEIGHTS = {"client": 0.20, "title": 0.25, "ref": 0.20, "skills": 0.15, "location": 0.05, "experience": 0.05, "recruiter": 0.05, "description": 0.05}


@dataclass
class Profile:
    client: str = ""
    title: str = ""
    ref: str = ""
    required_skills: frozenset[str] = frozenset()
    exp_min: float | None = None
    exp_max: float | None = None
    location: str = ""
    work_mode: str = "unknown"
    salary_min: float | None = None
    salary_max: float | None = None
    recruiter_email: str = ""
    description: str = ""
    employment_type: str = ""
    openings: int | None = None
    received_at: datetime | None = None
    fingerprint: str | None = None


def _ref(v: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (v or "").lower())


def profile_from_requirement(r) -> Profile:
    return Profile(
        client=r.client_normalized or normalize_company(r.client_name),
        title=r.title_normalized or normalize_title(r.job_title),
        ref=_ref(r.job_reference_id),
        required_skills=frozenset(s.normalized for s in r.skills if s.kind == "required"),
        exp_min=r.minimum_experience, exp_max=r.maximum_experience,
        location=r.location_normalized or normalize_location(r.location),
        work_mode=r.work_mode or "unknown",
        salary_min=float(r.salary_min) if r.salary_min is not None else None,
        salary_max=float(r.salary_max) if r.salary_max is not None else None,
        recruiter_email=(r.recruiter_email or "").lower(),
        description=(r.job_description or "")[:1500],
        employment_type=(r.employment_type or "").lower(),
        openings=r.number_of_openings, received_at=r.received_at, fingerprint=r.canonical_fingerprint,
    )


def profile_from_extracted(e, location_display: str | None, received_at: datetime | None) -> Profile:
    return Profile(
        client=normalize_company(e.client_name), title=normalize_title(e.job_title), ref=_ref(e.job_reference_id),
        required_skills=frozenset(normalize_skill(s) for s in e.required_skills if normalize_skill(s)),
        exp_min=e.minimum_experience, exp_max=e.maximum_experience, location=normalize_location(location_display),
        work_mode=e.work_mode, salary_min=e.salary_min, salary_max=e.salary_max,
        recruiter_email=(e.recruiter_email or "").lower(), description=(e.job_description or "")[:1500],
        employment_type=(e.employment_type or "").lower(), openings=e.number_of_openings, received_at=received_at,
        fingerprint=requirement_fingerprint(e.client_name, e.job_title, e.job_reference_id, location_display),
    )


def _jaccard(a: frozenset | set, b: frozenset | set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"\W+", s.lower()) if len(t) > 3}


def _title_sim(a: str, b: str) -> float:
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    return max(SequenceMatcher(None, a, b).ratio(), _jaccard(ta, tb))


def _text_sim(a: str, b: str) -> float:
    return _jaccard(_tokens(a), _tokens(b))


def _range_overlap(a: Profile, b: Profile) -> float | None:
    if a.exp_min is None or b.exp_min is None:
        return None
    a_hi = a.exp_max if a.exp_max is not None else a.exp_min + 2
    b_hi = b.exp_max if b.exp_max is not None else b.exp_min + 2
    return 1.0 if max(a.exp_min, b.exp_min) <= min(a_hi, b_hi) else 0.0


@dataclass
class Comparison:
    score: float
    reasons: list[str]
    conflicts: list[str]
    comparable: int
    title_sim: float = 0.0
    client_eq: bool = False
    ref_state: str = "unknown"  # equal | different | unknown
    skills_sim: float | None = None
    days_apart: float | None = None


def compare(a: Profile, b: Profile) -> Comparison:
    comps: dict[str, float] = {}
    reasons: list[str] = []
    conflicts: list[str] = []

    client_eq = bool(a.client and b.client and (a.client == b.client or SequenceMatcher(None, a.client, b.client).ratio() >= 0.92))
    if a.client and b.client:
        comps["client"] = 1.0 if client_eq else 0.0
        (reasons if client_eq else conflicts).append("client")
    tsim = 0.0
    if a.title and b.title:
        tsim = _title_sim(a.title, b.title)
        comps["title"] = tsim
        if tsim >= 0.8:
            reasons.append(f"title similarity {tsim:.0%}")
        elif tsim < 0.5:
            conflicts.append("job_title")
    ref_state = "unknown"
    if a.ref and b.ref:
        ref_state = "equal" if a.ref == b.ref else "different"
        comps["ref"] = 1.0 if ref_state == "equal" else 0.0
        (reasons if ref_state == "equal" else conflicts).append("job_reference_id")
    skills_sim = None
    if a.required_skills and b.required_skills:
        skills_sim = _jaccard(a.required_skills, b.required_skills)
        comps["skills"] = skills_sim
        if skills_sim >= 0.6:
            reasons.append(f"required skills overlap {skills_sim:.0%}")
        elif skills_sim < 0.3:
            conflicts.append("required_skills")
    if a.location and b.location:
        same = a.location == b.location or a.location in b.location or b.location in a.location
        comps["location"] = 1.0 if same else 0.0
        (reasons if same else conflicts).append("location")
    ov = _range_overlap(a, b)
    if ov is not None:
        comps["experience"] = ov
        (reasons if ov else conflicts).append("experience")
    if a.recruiter_email and b.recruiter_email:
        same = a.recruiter_email == b.recruiter_email
        comps["recruiter"] = 1.0 if same else 0.0
        if same:
            reasons.append("recruiter")
    if len(a.description) > 80 and len(b.description) > 80:
        d = _text_sim(a.description, b.description)
        comps["description"] = d
        if d >= 0.6:
            reasons.append(f"description similarity {d:.0%}")

    if a.work_mode != "unknown" and b.work_mode != "unknown" and a.work_mode != b.work_mode:
        conflicts.append("work_mode")
    if None not in (a.salary_min, b.salary_min) and a.salary_min != b.salary_min:
        conflicts.append("salary_min")
    if None not in (a.salary_max, b.salary_max) and a.salary_max != b.salary_max:
        conflicts.append("salary_max")
    if a.employment_type and b.employment_type and a.employment_type != b.employment_type:
        conflicts.append("employment_type")

    total_w = sum(WEIGHTS[k] for k in comps)
    score = sum(WEIGHTS[k] * v for k, v in comps.items()) / total_w if total_w else 0.0

    # Title alone is never evidence of a duplicate.
    strong_other = client_eq or ref_state == "equal" or (skills_sim or 0) >= 0.5
    if not strong_other:
        score = min(score, 0.5)
    if ref_state == "different":
        score = min(score, 0.5)

    days = abs((a.received_at - b.received_at).total_seconds()) / 86400 if a.received_at and b.received_at else None
    return Comparison(round(score, 3), reasons, sorted(set(conflicts)), len(comps), tsim, client_eq, ref_state, skills_sim, days)


@dataclass
class Decision:
    kind: str  # exact | probable | related | distinct | insufficient
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def decide(new: Profile, existing: Profile, probable_threshold: float = 0.72, related_threshold: float = 0.55,
           window_days: int = 120, require_client_for_auto: bool = True) -> Decision:
    c = compare(new, existing)
    base = dict(score=c.score, reasons=c.reasons, conflicts=c.conflicts)

    if c.comparable < 2 or not (new.title or new.ref or new.client):
        return Decision("insufficient", **base)

    # 1. same client + same job reference id: same job (later emails are updates)
    if c.ref_state == "equal" and (c.client_eq or not (new.client and existing.client)):
        if c.client_eq or not require_client_for_auto:
            return Decision("exact", **{**base, "score": max(c.score, 0.95)})
        return Decision("probable", **base)

    # 2. identical canonical fingerprint with no contradictions
    if new.fingerprint and new.fingerprint == existing.fingerprint and c.ref_state != "different":
        within = c.days_apart is None or c.days_apart <= window_days
        skills_ok = c.skills_sim is None or c.skills_sim >= 0.5
        if within and skills_ok and c.client_eq:
            return Decision("exact", **{**base, "score": max(c.score, 0.9)})
        return Decision("probable", **{**base, "score": max(c.score, probable_threshold)})

    # 2b. a re-formatted copy of the same requirement (digest, forward, re-post): same client, near-identical title,
    #     compatible location and skills, no contradicting job ID
    loc_ok = not new.location or not existing.location or new.location == existing.location or new.location in existing.location or existing.location in new.location
    if (c.ref_state != "different" and c.client_eq and c.title_sim >= 0.9 and loc_ok and (c.skills_sim is None or c.skills_sim >= 0.5)
            and (c.days_apart is None or c.days_apart <= window_days)):
        return Decision("exact", **{**base, "score": max(c.score, 0.9)})

    # 3. different job reference ids: never merge; same client + very similar title => related
    if c.ref_state == "different":
        if c.client_eq and c.title_sim >= 0.8:
            return Decision("related", **base)
        return Decision("distinct", **base)

    if c.days_apart is not None and c.days_apart > window_days:
        return Decision("distinct", **base) if c.score < 0.9 else Decision("probable", **base)

    if c.score >= probable_threshold and c.comparable >= 3:
        return Decision("probable", **base)
    if c.score >= related_threshold and c.client_eq and c.title_sim >= 0.6:
        return Decision("related", **base)
    return Decision("distinct", **base)


def ordered_pair(a, b):
    """Normalise pair ordering so (A,B) and (B,A) map to the same unique row."""
    return (a, b) if str(a) < str(b) else (b, a)
