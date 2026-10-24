"""Dashboard KPIs and chart data computed from live database records. Nothing is hardcoded or invented."""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.models.candidates import Candidate
from app.models.email import EmailAccount, EmailMessage
from app.models.enums import ConnectionStatus, DeliveryStatus, LifecycleStatus, MessageStatus, ReviewStatus
from app.models.ops import EmailDelivery, ExtractionRun, ProcessingJob
from app.models.requirements import DuplicateCandidate, JobRequirement, RequirementSkill, RequirementSource, RequirementVersion

R = JobRequirement


def _unique(org_id):
    return (R.organization_id == org_id, R.lifecycle_status != LifecycleStatus.MERGED)


def _range(date_from: datetime | None, date_to: datetime | None, default_days: int = 30) -> tuple[datetime, datetime]:
    end = date_to or utcnow()
    return (date_from or end - timedelta(days=default_days)), end


def kpis(db: Session, org_id: uuid.UUID) -> dict:
    now = utcnow()
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week0 = day0 - timedelta(days=day0.weekday())
    cnt = lambda *c: db.scalar(select(func.count()).select_from(R).where(*_unique(org_id), *c)) or 0  # noqa: E731
    msg_cnt = lambda *c: db.scalar(select(func.count()).select_from(EmailMessage).where(EmailMessage.organization_id == org_id, *c)) or 0  # noqa: E731
    S = MessageStatus
    return {
        "total_unique_requirements": cnt(R.lifecycle_status != LifecycleStatus.ARCHIVED),
        "awaiting_review": cnt(R.review_status == ReviewStatus.NEEDS_REVIEW, R.lifecycle_status == LifecycleStatus.ACTIVE),
        "approved": cnt(R.review_status == ReviewStatus.APPROVED, R.lifecycle_status != LifecycleStatus.ARCHIVED),
        "received_today": cnt(R.received_at >= day0),
        "received_this_week": cnt(R.received_at >= week0),
        "duplicates_pending": db.scalar(select(func.count()).select_from(DuplicateCandidate).where(
            DuplicateCandidate.organization_id == org_id, DuplicateCandidate.review_status == "pending")) or 0,
        "emails_processed": msg_cnt(EmailMessage.processing_status.in_([S.PROCESSED, S.DUPLICATE, S.NO_REQUIREMENT, S.NEEDS_REVIEW])),
        "extraction_failed_or_pending": msg_cnt(EmailMessage.processing_status.in_([S.FAILED, S.PENDING, S.PROCESSING, S.AWAITING_AI])),
        "connected_accounts": db.scalar(select(func.count()).select_from(EmailAccount).where(
            EmailAccount.organization_id == org_id, EmailAccount.connection_status.in_([ConnectionStatus.CONNECTED, ConnectionStatus.SYNCING]))) or 0,
        "accounts_needing_attention": db.scalar(select(func.count()).select_from(EmailAccount).where(
            EmailAccount.organization_id == org_id, EmailAccount.connection_status.in_([ConnectionStatus.EXPIRED, ConnectionStatus.ERROR]))) or 0,
        "last_successful_sync": db.scalar(select(func.max(EmailAccount.last_synced_at)).where(EmailAccount.organization_id == org_id)),
        "candidates": db.scalar(select(func.count()).select_from(Candidate).where(Candidate.organization_id == org_id, Candidate.is_archived.is_(False))) or 0,
        "pending_deliveries": db.scalar(select(func.count()).select_from(EmailDelivery).where(
            EmailDelivery.organization_id == org_id, EmailDelivery.status.in_([DeliveryStatus.QUEUED, DeliveryStatus.SENDING, DeliveryStatus.UNCERTAIN]))) or 0,
    }


def _group(db: Session, org_id, col, d_from, d_to, limit: int | None = None, extra=()):
    q = (select(col, func.count()).select_from(R).where(*_unique(org_id), R.received_at >= d_from, R.received_at <= d_to, col.is_not(None), *extra)
         .group_by(col).order_by(func.count().desc()))
    if limit:
        q = q.limit(limit)
    return [{"name": k, "count": v} for k, v in db.execute(q).all()]


def overview(db: Session, org_id: uuid.UUID, date_from: datetime | None, date_to: datetime | None) -> dict:
    d_from, d_to = _range(date_from, date_to)
    day = func.date(R.received_at) if db.get_bind().dialect.name == "sqlite" else cast(R.received_at, Date)  # SQLite's CAST(... AS DATE) yields a bare year
    daily = db.execute(select(day, func.count()).select_from(R).where(*_unique(org_id), R.received_at >= d_from, R.received_at <= d_to).group_by(day).order_by(day)).all()
    by_day: dict[date, int] = {}
    for k, v in daily:
        k = k if isinstance(k, date) else date.fromisoformat(str(k)[:10])
        by_day[k] = by_day.get(k, 0) + v
    series, cur = [], d_from.date()
    while cur <= d_to.date():
        series.append({"date": cur.isoformat(), "count": by_day.get(cur, 0)})
        cur += timedelta(days=1)
    weekly: dict[str, int] = defaultdict(int)
    monthly: dict[str, int] = defaultdict(int)
    for k, v in by_day.items():
        weekly[(k - timedelta(days=k.weekday())).isoformat()] += v
        monthly[k.strftime("%Y-%m")] += v

    skills = db.execute(select(RequirementSkill.normalized, func.min(RequirementSkill.name), func.count(func.distinct(RequirementSkill.job_requirement_id)))
                        .join(R, R.id == RequirementSkill.job_requirement_id).where(*_unique(org_id), RequirementSkill.kind == "required", R.received_at >= d_from, R.received_at <= d_to)
                        .group_by(RequirementSkill.normalized).order_by(func.count(func.distinct(RequirementSkill.job_requirement_id)).desc()).limit(12)).all()
    accounts = db.execute(select(EmailAccount.email_address, func.count(func.distinct(RequirementSource.job_requirement_id)))
                          .join(EmailMessage, EmailMessage.email_account_id == EmailAccount.id).join(RequirementSource, RequirementSource.email_message_id == EmailMessage.id)
                          .join(R, R.id == RequirementSource.job_requirement_id).where(EmailAccount.organization_id == org_id, R.lifecycle_status != LifecycleStatus.MERGED,
                                                                                         R.received_at >= d_from, R.received_at <= d_to).group_by(EmailAccount.email_address)).all()
    M = EmailMessage
    ok = (M.processing_status.in_(["processed", "duplicate", "no_requirement", "needs_review"]))
    msg = db.execute(select(func.sum(case((ok, 1), else_=0)), func.sum(case((M.processing_status == "failed", 1), else_=0)),
                            func.sum(case((M.processing_status.in_(["pending", "processing", "awaiting_ai"]), 1), else_=0)))
                     .where(M.organization_id == org_id, M.received_at >= d_from, M.received_at <= d_to)).one()
    return {
        "range": {"from": d_from.isoformat(), "to": d_to.isoformat()},
        "kpis": kpis(db, org_id),
        "received_over_time": series,
        "weekly_activity": [{"week": k, "count": v} for k, v in sorted(weekly.items())],
        "monthly_activity": [{"month": k, "count": v} for k, v in sorted(monthly.items())],
        "by_status": _group(db, org_id, R.review_status, d_from, d_to),
        "by_location": _group(db, org_id, R.location, d_from, d_to, 10),
        "by_client": _group(db, org_id, R.client_name, d_from, d_to, 10),
        "top_skills": [{"name": n, "count": c} for _, n, c in skills],
        "by_source_account": [{"name": n, "count": c} for n, c in accounts],
        "email_processing": {"succeeded": int(msg[0] or 0), "failed": int(msg[1] or 0), "pending": int(msg[2] or 0)},
    }


def recruitment(db: Session, org_id: uuid.UUID, date_from: datetime | None, date_to: datetime | None) -> dict:
    d_from, d_to = _range(date_from, date_to, 90)
    exp_bucket = case((R.minimum_experience.is_(None), "Not specified"), (R.minimum_experience < 3, "0-2 yrs"), (R.minimum_experience < 6, "3-5 yrs"),
                      (R.minimum_experience < 9, "6-8 yrs"), (R.minimum_experience < 13, "9-12 yrs"), else_="13+ yrs")
    total_reqs = db.scalar(select(func.count()).select_from(R).where(*_unique(org_id), R.received_at >= d_from, R.received_at <= d_to)) or 0
    dup_total = db.scalar(select(func.count()).select_from(DuplicateCandidate).where(DuplicateCandidate.organization_id == org_id, DuplicateCandidate.created_at >= d_from,
                                                                                    DuplicateCandidate.created_at <= d_to, DuplicateCandidate.review_status.in_(["pending", "merged"]))) or 0
    attached = db.scalar(select(func.count()).select_from(RequirementSource).join(R, R.id == RequirementSource.job_requirement_id).where(
        R.organization_id == org_id, RequirementSource.source_type.in_(["duplicate_copy"]), RequirementSource.linked_at >= d_from, RequirementSource.linked_at <= d_to)) or 0
    runs = db.execute(select(func.count(), func.sum(case((ExtractionRun.status == "succeeded", 1), else_=0)))
                      .select_from(ExtractionRun).join(EmailMessage, EmailMessage.id == ExtractionRun.email_message_id)
                      .where(EmailMessage.organization_id == org_id, ExtractionRun.started_at >= d_from, ExtractionRun.started_at <= d_to, ExtractionRun.status != "skipped")).one()
    corrected = db.scalar(select(func.count(func.distinct(RequirementVersion.job_requirement_id))).join(R, R.id == RequirementVersion.job_requirement_id).where(
        *_unique(org_id), RequirementVersion.change_source == "manual_edit", R.received_at >= d_from, R.received_at <= d_to)) or 0
    extracted_reqs = db.scalar(select(func.count()).select_from(R).where(*_unique(org_id), R.extraction_model.is_not(None), R.received_at >= d_from, R.received_at <= d_to)) or 0
    dur = db.execute(select(ProcessingJob.started_at, ProcessingJob.completed_at).where(ProcessingJob.organization_id == org_id, ProcessingJob.status.in_(["completed", "completed_with_errors"]),
                                                                                         ProcessingJob.completed_at >= d_from, ProcessingJob.completed_at <= d_to, ProcessingJob.started_at.is_not(None))).all()
    secs = [(c - s).total_seconds() for s, c in dur if s and c]
    failed_jobs = db.execute(select(ProcessingJob.job_type, func.count()).where(ProcessingJob.organization_id == org_id, ProcessingJob.status == "failed",
                                                                                 ProcessingJob.created_at >= d_from, ProcessingJob.created_at <= d_to).group_by(ProcessingJob.job_type)).all()
    activity = db.execute(select(EmailAccount.email_address, func.count(EmailMessage.id)).join(EmailMessage, EmailMessage.email_account_id == EmailAccount.id)
                          .where(EmailAccount.organization_id == org_id, EmailMessage.received_at >= d_from, EmailMessage.received_at <= d_to).group_by(EmailAccount.email_address)).all()
    rate = lambda a, b: round(a / b, 4) if b else None  # noqa: E731
    return {
        "range": {"from": d_from.isoformat(), "to": d_to.isoformat()},
        "total_requirements": total_reqs,
        "by_client": _group(db, org_id, R.client_name, d_from, d_to, 15),
        "by_location": _group(db, org_id, R.location, d_from, d_to, 15),
        "by_work_mode": _group(db, org_id, R.work_mode, d_from, d_to, extra=(R.work_mode != "unknown",)),
        "by_experience": [{"name": k, "count": v} for k, v in db.execute(select(exp_bucket, func.count()).select_from(R).where(
            *_unique(org_id), R.received_at >= d_from, R.received_at <= d_to).group_by(exp_bucket)).all()],
        "by_skill": [{"name": n, "count": c} for n, c in db.execute(select(func.min(RequirementSkill.name), func.count(func.distinct(RequirementSkill.job_requirement_id)))
                                                                    .join(R, R.id == RequirementSkill.job_requirement_id).where(*_unique(org_id), RequirementSkill.kind == "required", R.received_at >= d_from, R.received_at <= d_to)
                                                                    .group_by(RequirementSkill.normalized).order_by(func.count(func.distinct(RequirementSkill.job_requirement_id)).desc()).limit(20)).all()],
        "duplicate_rate": {"value": rate(dup_total + attached, total_reqs + attached), "duplicate_candidates": dup_total, "cross_account_copies": attached},
        "extraction_success_rate": {"value": rate(int(runs[1] or 0), int(runs[0] or 0)), "runs": int(runs[0] or 0)},
        "manual_correction_rate": {"value": rate(corrected, extracted_reqs), "corrected": corrected, "extracted": extracted_reqs},
        "average_job_duration_seconds": round(sum(secs) / len(secs), 1) if secs else None,
        "failed_jobs_by_type": [{"name": k, "count": v} for k, v in failed_jobs],
        "account_activity": [{"name": n, "count": c} for n, c in activity],
    }
