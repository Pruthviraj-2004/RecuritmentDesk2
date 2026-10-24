"""Candidate profiles: normalization, create/update, duplicate detection, notes and pipeline helpers."""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailure
from app.db.types import utcnow
from app.models.candidates import CANDIDATE_STATUSES, Candidate, CandidateNote, CandidateSkill
from app.services.normalization.text import normalize_email_address, normalize_skill_list

SCALAR_FIELDS = [
    "first_name", "last_name", "email", "phone", "current_title", "current_company", "total_experience", "relevant_experience", "current_location",
    "willing_to_relocate", "notice_period", "current_ctc", "expected_ctc", "currency", "education", "work_authorization", "linkedin_url", "resume_url",
    "summary", "source", "status", "rating",
]
LIST_FIELDS = ["preferred_locations", "certifications", "tags"]
EDITABLE_FIELDS = SCALAR_FIELDS + LIST_FIELDS + ["skills"]
MAX_LEN = {"first_name": 120, "last_name": 120, "email": 320, "phone": 50, "current_title": 200, "current_company": 200, "current_location": 200, "notice_period": 100,
           "currency": 8, "education": 500, "work_authorization": 100, "linkedin_url": 500, "resume_url": 500, "source": 60}


def normalize_phone(phone: str | None) -> str | None:
    """Digits only; for numbers longer than 10 digits the last 10 are kept so '+91 98765 43210' matches '9876543210'."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 7:
        return None
    return digits[-10:] if len(digits) > 10 else digits


def clean_email(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as e:
        raise ValidationFailure(f"Invalid email address: {value[:60]!r}") from e


def clean_list(values: list[str] | None, limit: int = 50, item_len: int = 80) -> list[str]:
    out: list[str] = []
    for v in values or []:
        v = re.sub(r"\s+", " ", str(v)).strip()
        if v and v.lower() not in {x.lower() for x in out}:
            out.append(v[:item_len])
    return out[:limit]


def _num(v):
    return float(v) if isinstance(v, (Decimal, int, float)) and not isinstance(v, bool) else v


def snapshot(c: Candidate) -> dict:
    d = {f: _num(getattr(c, f)) for f in SCALAR_FIELDS + LIST_FIELDS}
    d["skills"] = c.skill_names
    return d


def _set_skills(c: Candidate, skills: list[str] | None, *, merge: bool = False) -> None:
    if skills is None:
        return
    wanted = {norm: display for display, norm in normalize_skill_list(skills)}
    if merge:
        for s in c.skills:
            wanted.setdefault(s.normalized, s.name)
    for s in list(c.skills):
        if s.normalized not in wanted:
            c.skills.remove(s)
        else:
            s.name = wanted.pop(s.normalized)
    for norm, display in wanted.items():
        c.skills.append(CandidateSkill(name=display[:120], normalized=norm[:120]))


def apply_fields(c: Candidate, values: dict, *, merge: bool = False) -> None:
    """Write validated values onto a candidate. With merge=True only non-empty incoming values overwrite, lists/skills are unioned."""
    for f in SCALAR_FIELDS:
        if f not in values:
            continue
        v = values[f]
        if isinstance(v, str):
            v = v.strip() or None
        if merge and v is None:
            continue
        if f in MAX_LEN and isinstance(v, str):
            v = v[: MAX_LEN[f]]
        setattr(c, f, v)
    for f in LIST_FIELDS:
        if f in values and values[f] is not None:
            incoming = clean_list(values[f])
            setattr(c, f, clean_list((getattr(c, f) or []) + incoming) if merge else incoming)
    if "skills" in values:
        _set_skills(c, values["skills"], merge=merge)
    c.first_name = (c.first_name or "").strip()
    c.full_name = " ".join(p for p in (c.first_name, (c.last_name or "").strip()) if p)[:250]
    c.email_normalized = normalize_email_address(c.email) or None
    c.phone_normalized = normalize_phone(c.phone)
    if c.status not in CANDIDATE_STATUSES:
        c.status = "new"


def validate_values(values: dict) -> dict:
    """Server-side validation for API writes (the importer has its own row-level reporting)."""
    out = dict(values)
    if "email" in out:
        out["email"] = clean_email(out["email"])
    if out.get("phone") is not None and out["phone"].strip() and not normalize_phone(out["phone"]):
        raise ValidationFailure("Phone number must have at least 7 digits")
    for f in ("total_experience", "relevant_experience"):
        if out.get(f) is not None and not (0 <= out[f] <= 60):
            raise ValidationFailure(f"{f} must be between 0 and 60 years")
    for f in ("current_ctc", "expected_ctc"):
        if out.get(f) is not None and out[f] < 0:
            raise ValidationFailure(f"{f} cannot be negative")
    if out.get("rating") is not None and not (1 <= out["rating"] <= 5):
        raise ValidationFailure("rating must be between 1 and 5")
    if out.get("status") is not None and out["status"] not in CANDIDATE_STATUSES:
        raise ValidationFailure(f"status must be one of {CANDIDATE_STATUSES}")
    for f in ("linkedin_url", "resume_url"):
        if out.get(f) and not re.match(r"^https?://", out[f].strip(), re.I):
            raise ValidationFailure(f"{f} must start with http:// or https://")
    return out


def find_duplicates(db: Session, org_id: uuid.UUID, *, email: str | None, phone: str | None, exclude_id: uuid.UUID | None = None) -> list[Candidate]:
    conds = []
    if email:
        conds.append(Candidate.email_normalized == normalize_email_address(email))
    if phone and normalize_phone(phone):
        conds.append(Candidate.phone_normalized == normalize_phone(phone))
    if not conds:
        return []
    q = select(Candidate).where(Candidate.organization_id == org_id, or_(*conds))
    if exclude_id:
        q = q.where(Candidate.id != exclude_id)
    return list(db.scalars(q))


def get_candidate(db: Session, org_id: uuid.UUID, cid: uuid.UUID) -> Candidate:
    c = db.scalar(select(Candidate).options(selectinload(Candidate.skills)).where(Candidate.id == cid, Candidate.organization_id == org_id))
    if not c:
        raise NotFoundError("Candidate not found")
    return c


def create_candidate(db: Session, org_id: uuid.UUID, values: dict, *, user_id: uuid.UUID | None, check_duplicates: bool = True, import_id: uuid.UUID | None = None) -> Candidate:
    values = validate_values(values)
    if not (values.get("first_name") or "").strip():
        raise ValidationFailure("First name is required")
    if not values.get("email"):
        raise ValidationFailure("Email address is required")
    if not normalize_phone(values.get("phone")):
        raise ValidationFailure("Phone number is required (at least 7 digits)")
    if check_duplicates:
        dups = find_duplicates(db, org_id, email=values.get("email"), phone=values.get("phone"))
        if dups:
            d = dups[0]
            raise ConflictError(f"{d.full_name} already exists with the same {'email' if d.email_normalized and d.email_normalized == normalize_email_address(values.get('email')) else 'phone number'}",
                                code="duplicate_candidate", details={"existing_id": str(d.id), "existing_name": d.full_name})
    c = Candidate(organization_id=org_id, created_by=user_id, updated_by=user_id, import_id=import_id, status="new", source="manual", preferred_locations=[], certifications=[], tags=[])
    c.id = uuid.uuid4()
    apply_fields(c, values)
    db.add(c)
    db.flush()
    return c


def update_candidate(db: Session, c: Candidate, patch: dict, *, user_id: uuid.UUID | None) -> Candidate:
    unknown = set(patch) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValidationFailure(f"Unknown or read-only fields: {sorted(unknown)}")
    for required in ("first_name", "email", "phone"):  # mandatory fields can be changed but never cleared
        if required in patch and not (patch[required] or "").strip():
            raise ValidationFailure(f"{required.replace('_', ' ').capitalize()} is required and cannot be removed")
    patch = validate_values(patch)
    old_status = c.status
    new_email = patch.get("email", c.email)
    new_phone = patch.get("phone", c.phone)
    if ("email" in patch or "phone" in patch):
        dups = find_duplicates(db, c.organization_id, email=new_email, phone=new_phone, exclude_id=c.id)
        if dups:
            raise ConflictError(f"{dups[0].full_name} already has this email or phone number", code="duplicate_candidate", details={"existing_id": str(dups[0].id)})
    apply_fields(c, patch)
    if not c.first_name:
        raise ValidationFailure("First name is required")
    c.updated_by = user_id
    c.updated_at = utcnow()
    db.flush()
    if c.status != old_status:
        add_note(db, c, f"Status changed from {old_status.replace('_', ' ')} to {c.status.replace('_', ' ')}", user_id=user_id, kind="status")
    return c


def add_note(db: Session, c: Candidate, body: str, *, user_id: uuid.UUID | None, kind: str = "note") -> CandidateNote:
    n = CandidateNote(candidate_id=c.id, author_user_id=user_id, kind=kind, body=body.strip()[:5000])
    db.add(n)
    db.flush()
    return n


def touch_contacted(c: Candidate, when: datetime | None = None) -> None:
    c.last_contacted_at = when or utcnow()
