"""Shared requirement filtering/sorting used by the list API, exports and analytics."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import Select, and_, exists, func, or_, select

from app.models.email import EmailMessage
from app.models.enums import DuplicateStatus, LifecycleStatus
from app.models.requirements import DuplicateCandidate, JobRequirement, RequirementSkill, RequirementSource
from app.services.normalization.text import normalize_skill


class RequirementFilters(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    date_from: datetime | None = None
    date_to: datetime | None = None
    account_id: uuid.UUID | None = None
    client: str | None = None
    job_title: str | None = None
    skill: str | None = None
    exp_min: float | None = None
    exp_max: float | None = None
    location: str | None = None
    work_mode: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    recruiter: str | None = None
    review_status: str | None = None
    lifecycle_status: str | None = None
    source_type: str | None = None
    duplicate_status: str | None = None  # pending | none
    include_merged: bool = False


def _like(col, value: str):
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return col.ilike(f"%{escaped}%", escape="\\")


def apply_filters(stmt: Select, org_id: uuid.UUID, f: RequirementFilters) -> Select:
    R = JobRequirement
    stmt = stmt.where(R.organization_id == org_id)
    if not f.include_merged:
        stmt = stmt.where(R.lifecycle_status != LifecycleStatus.MERGED)
    if f.lifecycle_status:
        stmt = stmt.where(R.lifecycle_status == f.lifecycle_status)
    elif not f.include_merged:
        stmt = stmt.where(R.lifecycle_status != LifecycleStatus.ARCHIVED)  # archived records are only shown when explicitly selected
    if f.review_status:
        stmt = stmt.where(R.review_status == f.review_status)
    if f.date_from:
        stmt = stmt.where(R.received_at >= f.date_from)
    if f.date_to:
        stmt = stmt.where(R.received_at <= f.date_to)
    if f.client:
        stmt = stmt.where(_like(R.client_name, f.client))
    if f.job_title:
        stmt = stmt.where(_like(R.job_title, f.job_title))
    if f.location:
        stmt = stmt.where(_like(R.location, f.location))
    if f.work_mode:
        stmt = stmt.where(R.work_mode == f.work_mode)
    if f.recruiter:
        stmt = stmt.where(or_(_like(R.recruiter_email, f.recruiter), _like(R.recruiter_name, f.recruiter)))
    if f.exp_min is not None:  # requirement's max (or min) experience must reach exp_min
        stmt = stmt.where(func.coalesce(R.maximum_experience, R.minimum_experience) >= f.exp_min)
    if f.exp_max is not None:
        stmt = stmt.where(R.minimum_experience <= f.exp_max)
    if f.salary_min is not None:
        stmt = stmt.where(func.coalesce(R.salary_max, R.salary_min) >= f.salary_min)
    if f.salary_max is not None:
        stmt = stmt.where(func.coalesce(R.salary_min, R.salary_max) <= f.salary_max)
    if f.skill:
        norm = normalize_skill(f.skill)
        stmt = stmt.where(exists().where(RequirementSkill.job_requirement_id == R.id, RequirementSkill.normalized == norm))
    if f.account_id or f.source_type:
        conds = [RequirementSource.job_requirement_id == R.id]
        if f.source_type:
            conds.append(RequirementSource.source_type == f.source_type)
        sub = select(RequirementSource.id).join(EmailMessage, EmailMessage.id == RequirementSource.email_message_id, isouter=True).where(and_(*conds))
        if f.account_id:
            sub = sub.where(EmailMessage.email_account_id == f.account_id)
        stmt = stmt.where(exists(sub))
    if f.duplicate_status:
        pending = exists().where(DuplicateCandidate.review_status == DuplicateStatus.PENDING,
                                 or_(DuplicateCandidate.requirement_id_a == R.id, DuplicateCandidate.requirement_id_b == R.id))
        stmt = stmt.where(pending if f.duplicate_status == "pending" else ~pending)
    if f.q:
        term = f.q.strip()
        like_conds = [_like(c, term) for c in (R.job_title, R.client_name, R.job_reference_id, R.recruiter_email, R.location, R.job_description)]
        like_conds.append(exists().where(RequirementSkill.job_requirement_id == R.id, RequirementSkill.normalized.ilike(f"%{normalize_skill(term).replace('%', '')}%")))
        stmt = stmt.where(or_(*like_conds))
    return stmt


SORT_COLUMNS = {
    "received_at": JobRequirement.received_at, "client_name": JobRequirement.client_name, "job_title": JobRequirement.job_title,
    "last_updated_at": JobRequirement.last_updated_at, "review_status": JobRequirement.review_status,
    "location": JobRequirement.location, "minimum_experience": JobRequirement.minimum_experience, "created_at": JobRequirement.created_at,
}


def apply_sort(stmt: Select, sort: str | None, direction: str = "desc") -> Select:
    col = SORT_COLUMNS.get(sort or "received_at", JobRequirement.received_at)
    order = col.asc() if direction == "asc" else col.desc()
    return stmt.order_by(order.nullslast(), JobRequirement.id)
