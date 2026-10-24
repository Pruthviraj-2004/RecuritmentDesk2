from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text

from app.api.deps import Ctx, admin, member, viewer
from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailure
from app.models.auth import User
from app.models.email import EmailAccount, EmailMessage
from app.models.enums import ACTIVE_JOB_STATUSES, ConnectionStatus, JobStatus
from app.models.ops import AuditLog, Notification, ProcessingJob
from app.schemas.api import AuditOut, JobOut, NotificationOut, Page
from app.services import analytics, jobs
from app.services.app_settings import SECTIONS, get_section, save_section
from app.services.audit import service as audit
from app.services.extraction.providers import AIError, get_provider
from app.tasks.runner import enqueue, use_inline

router = APIRouter(tags=["operations"])


# ---------------------------------------------------------------- jobs
def _job_out(j: ProcessingJob, emails: dict) -> JobOut:
    o = JobOut.model_validate(j)
    o.account_email = emails.get(j.email_account_id)
    from app.db.types import utcnow

    end = j.completed_at or (utcnow() if j.status == JobStatus.RUNNING else None)
    o.duration_seconds = round((end - j.started_at).total_seconds(), 1) if end and j.started_at else None
    return o


@router.get("/jobs", response_model=Page[JobOut])
def list_jobs(ctx: Ctx = viewer, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), status: str | None = None, job_type: str | None = None,
              account_id: uuid.UUID | None = None):
    stmt = select(ProcessingJob).where(ProcessingJob.organization_id == ctx.org_id)
    if status == "active":
        stmt = stmt.where(ProcessingJob.status.in_([s.value for s in ACTIVE_JOB_STATUSES]))
    elif status:
        stmt = stmt.where(ProcessingJob.status == status)
    if job_type:
        stmt = stmt.where(ProcessingJob.job_type == job_type)
    if account_id:
        stmt = stmt.where(ProcessingJob.email_account_id == account_id)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(ctx.db.scalars(stmt.order_by(ProcessingJob.created_at.desc()).limit(page_size).offset((page - 1) * page_size)))
    emails = dict(ctx.db.execute(select(EmailAccount.id, EmailAccount.email_address).where(EmailAccount.organization_id == ctx.org_id)).all())
    return Page(items=[_job_out(j, emails) for j in rows], total=total, page=page, page_size=page_size)


@router.get("/jobs/summary")
def jobs_summary(ctx: Ctx = viewer):
    M = EmailMessage
    counts = dict(ctx.db.execute(select(M.processing_status, func.count()).where(M.organization_id == ctx.org_id).group_by(M.processing_status)).all())
    accts = ctx.db.scalars(select(EmailAccount).where(EmailAccount.organization_id == ctx.org_id)).all()
    return {
        "messages": counts,
        "extraction_pending": counts.get("pending", 0) + counts.get("processing", 0) + counts.get("awaiting_ai", 0),
        "extraction_failed": counts.get("failed", 0),
        "accounts": [{"id": str(a.id), "email": a.email_address, "status": a.connection_status, "last_synced_at": a.last_synced_at, "last_error": a.last_error} for a in accts],
    }


@router.get("/jobs/issues")
def processing_issues(ctx: Ctx = viewer, limit: int = Query(50, ge=1, le=200)):
    """Messages that need attention (failed extraction or waiting for AI). Only metadata is returned, never email content."""
    rows = ctx.db.execute(select(EmailMessage.id, EmailMessage.subject, EmailMessage.sender, EmailMessage.received_at, EmailMessage.processing_status,
                                 EmailMessage.error_summary, EmailAccount.email_address)
                          .join(EmailAccount, EmailAccount.id == EmailMessage.email_account_id)
                          .where(EmailMessage.organization_id == ctx.org_id, EmailMessage.processing_status.in_(["failed", "awaiting_ai"]))
                          .order_by(EmailMessage.received_at.desc().nullslast()).limit(limit)).all()
    return [{"id": str(r[0]), "subject": r[1], "sender": r[2], "received_at": r[3], "status": r[4], "error": r[5], "account": r[6]} for r in rows]


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, ctx: Ctx = viewer):
    j = ctx.db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id, ProcessingJob.organization_id == ctx.org_id))
    if not j:
        raise NotFoundError("Job not found")
    return _job_out(j, dict(ctx.db.execute(select(EmailAccount.id, EmailAccount.email_address).where(EmailAccount.organization_id == ctx.org_id)).all()))


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: uuid.UUID, ctx: Ctx = member):
    j = ctx.db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id, ProcessingJob.organization_id == ctx.org_id))
    if not j:
        raise NotFoundError("Job not found")
    if j.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise ConflictError(f"A job with status '{j.status}' cannot be cancelled")
    if j.status == JobStatus.QUEUED:
        jobs.finish(j, JobStatus.CANCELLED)
    else:
        j.status = JobStatus.CANCEL_REQUESTED  # worker stops at the next checkpoint
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="job.cancel_requested", entity_type="job", entity_id=j.id)
    ctx.db.commit()
    return _job_out(j, {})


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: uuid.UUID, ctx: Ctx = member):
    j = ctx.db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id, ProcessingJob.organization_id == ctx.org_id))
    if not j:
        raise NotFoundError("Job not found")
    if j.status not in (JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.COMPLETED_WITH_ERRORS):
        raise ConflictError(f"A job with status '{j.status}' cannot be retried")
    if j.job_type != "sync" or not j.email_account_id:
        raise ConflictError("Only synchronization jobs can be retried here; re-run exports from the Exports page")
    acct = ctx.db.get(EmailAccount, j.email_account_id)
    if acct.connection_status in (ConnectionStatus.EXPIRED, ConnectionStatus.DISCONNECTED):
        raise ConflictError("Reauthorize the account before retrying", code="account_needs_reauth")
    if jobs.active_job_for_account(ctx.db, acct.id):
        raise ConflictError("A sync is already running for this account")
    new = jobs.create_job(ctx.db, org_id=ctx.org_id, job_type="sync", account_id=acct.id, payload={**(j.payload or {}), "trigger": "retry", "retry_of": str(j.id)}, user_id=ctx.user_id)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="job.retried", entity_type="job", entity_id=new.id, metadata={"retry_of": str(j.id)})
    ctx.db.commit()
    enqueue("sync_account", str(new.id))
    ctx.db.refresh(new)
    return _job_out(new, {acct.id: acct.email_address})


@router.post("/emails/retry-failed")
def retry_failed_emails(ctx: Ctx = member, limit: int = Query(100, ge=1, le=500)):
    ids = [str(i) for i in ctx.db.scalars(select(EmailMessage.id).where(EmailMessage.organization_id == ctx.org_id, EmailMessage.processing_status.in_(["failed", "awaiting_ai"])).limit(limit))]
    for i in ids:
        m = ctx.db.get(EmailMessage, uuid.UUID(i))
        m.processing_status = "pending"
    ctx.db.commit()
    for i in ids:
        enqueue("process_email", i, False, str(ctx.user_id))
    return {"queued": len(ids)}


# ---------------------------------------------------------------- audit / notifications
@router.get("/audit-logs", response_model=Page[AuditOut])
def audit_logs(ctx: Ctx = viewer, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=200), action: str | None = None, entity_type: str | None = None,
               entity_id: str | None = None, date_from: datetime | None = None, date_to: datetime | None = None):
    stmt = select(AuditLog).where(AuditLog.organization_id == ctx.org_id)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action.replace('%', '')}%"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(ctx.db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(page_size).offset((page - 1) * page_size)))
    emails = dict(ctx.db.execute(select(User.id, User.email).where(User.id.in_({r.user_id for r in rows if r.user_id}))).all()) if rows else {}
    items = [AuditOut(id=r.id, user_id=r.user_id, user_email=emails.get(r.user_id), action=r.action, entity_type=r.entity_type, entity_id=r.entity_id,
                      event_metadata=r.event_metadata, created_at=r.created_at) for r in rows]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/notifications")
def notifications(ctx: Ctx = viewer, limit: int = Query(20, ge=1, le=100)):
    rows = list(ctx.db.scalars(select(Notification).where(Notification.organization_id == ctx.org_id).order_by(Notification.created_at.desc()).limit(limit)))
    unread = ctx.db.scalar(select(func.count()).select_from(Notification).where(Notification.organization_id == ctx.org_id, Notification.read_at.is_(None))) or 0
    return {"unread": unread, "items": [NotificationOut.model_validate(r) for r in rows]}


@router.post("/notifications/read-all", status_code=204)
def read_all(ctx: Ctx = viewer):
    from app.db.types import utcnow

    for n in ctx.db.scalars(select(Notification).where(Notification.organization_id == ctx.org_id, Notification.read_at.is_(None))):
        n.read_at = utcnow()
    ctx.db.commit()


# ---------------------------------------------------------------- analytics
@router.get("/analytics/overview")
def analytics_overview(ctx: Ctx = viewer, date_from: datetime | None = None, date_to: datetime | None = None):
    return analytics.overview(ctx.db, ctx.org_id, date_from, date_to)


@router.get("/analytics/recruitment")
def analytics_recruitment(ctx: Ctx = viewer, date_from: datetime | None = None, date_to: datetime | None = None):
    return analytics.recruitment(ctx.db, ctx.org_id, date_from, date_to)


# ---------------------------------------------------------------- settings
class SettingsPatch(BaseModel):
    values: dict


@router.get("/settings/{section}")
def get_settings_section(section: str, ctx: Ctx = viewer):
    if section not in SECTIONS:
        raise NotFoundError("Unknown settings section")
    return get_section(ctx.db, ctx.org_id, section).model_dump()


@router.put("/settings/{section}")
def put_settings_section(section: str, body: SettingsPatch, ctx: Ctx = admin):
    if section not in SECTIONS:
        raise NotFoundError("Unknown settings section")
    current = get_section(ctx.db, ctx.org_id, section).model_dump()
    try:
        saved = save_section(ctx.db, ctx.org_id, section, {**current, **body.values}, ctx.user_id)
    except Exception as e:  # pydantic validation
        raise ValidationFailure(f"Invalid settings: {str(e)[:300]}") from e
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="settings.updated", entity_type="settings", entity_id=section, metadata={"keys": sorted(body.values)})
    ctx.db.commit()
    return saved.model_dump()


@router.get("/settings-meta/ai")
def ai_status(ctx: Ctx = viewer, check: bool = False):
    """Provider status. Secrets are never returned; `check=true` performs a live provider health check."""
    s = get_settings()
    info = {"provider": s.ai_provider, "model": s.ai_model if s.ai_provider != "none" else None, "configured": s.ai_configured,
            "base_url_host": s.ai_base_url.split("/")[2] if s.ai_provider == "openai_compatible" and "//" in s.ai_base_url else None,
            "message": None if s.ai_configured else "No AI provider configured. Records can be browsed, edited and exported; live extraction is paused."}
    if check and s.ai_configured:
        try:
            p = get_provider()
            info["health"] = p.health_check() if p else {"status": "error", "detail": "not configured"}
        except AIError as e:
            info["health"] = {"status": "error", "detail": str(e)}
    return info


# ---------------------------------------------------------------- health (public liveness + authenticated detail)
health_router = APIRouter(tags=["health"])


def _checks() -> dict:
    from app.db.session import get_engine

    s = get_settings()
    out: dict = {"version": s.app_version}
    try:
        with get_engine().connect() as c:
            c.execute(text("select 1"))
        out["database"] = {"status": "ok"}
    except Exception as e:  # noqa: BLE001
        out["database"] = {"status": "error", "detail": type(e).__name__}
    if not s.redis_url:
        out["redis"] = {"status": "not_configured", "detail": "Running tasks inline (no broker)"}
        out["worker"] = {"status": "not_configured", "detail": "Inline mode"}
    else:
        try:
            import redis

            redis.Redis.from_url(s.redis_url, socket_connect_timeout=2).ping()
            out["redis"] = {"status": "ok"}
            from app.tasks.celery_app import celery_app

            pong = celery_app.control.inspect(timeout=1.0).ping()
            out["worker"] = {"status": "ok" if pong else "error", "detail": f"{len(pong)} worker(s)" if pong else "no worker responded"}
        except Exception as e:  # noqa: BLE001
            out["redis"] = out.get("redis", {"status": "error", "detail": type(e).__name__})
            out["worker"] = {"status": "error", "detail": "unavailable"}
    out["ai"] = {"status": "ok" if s.ai_configured else "not_configured", "provider": s.ai_provider}
    out["gmail"] = {"status": "ok" if s.google_configured else "not_configured", "detail": None if s.google_configured else "Google OAuth credentials missing"}
    return out


@health_router.get("/health")
def health():
    """Unauthenticated liveness/readiness for load balancers: reveals no configuration details."""
    c = _checks()
    ok = c["database"]["status"] == "ok"
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=200 if ok else 503, content={"status": "ok" if ok else "degraded", "database": c["database"]["status"], "version": c["version"]})


@health_router.get("/health/details")
def health_details(ctx: Ctx = viewer):
    return _checks()
