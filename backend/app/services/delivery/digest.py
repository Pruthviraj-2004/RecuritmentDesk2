"""Scheduled emails: any number of schedules per organization, each emailing an Excel file of requirements.

Each schedule decides WHAT to send (only what changed since its previous email, everything active, or whatever was new or updated in the
last N days) and WHEN (every N hours, or once a day at a set time in a timezone). Nothing is sent when there is nothing to send.
A schedule's previous email is found through the idempotency key of its deliveries, so no extra state is stored and a restart or two
overlapping scheduler ticks can never send the same email twice.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.types import utcnow
from app.models.email import EmailAccount
from app.models.enums import ConnectionStatus, DeliveryStatus, ExportStatus, JobStatus, LifecycleStatus, ReviewStatus
from app.models.ops import AppSetting, EmailDelivery, ExportJob, ProcessingJob
from app.models.requirements import JobRequirement
from app.services import jobs
from app.services.app_settings import DigestSchedule, DigestSettings
from app.services.delivery.service import create_delivery, send_delivery, validate_recipients
from app.services.exports.runner import run_export

log = get_logger(__name__)
RETRY_AFTER = timedelta(minutes=30)  # a failed attempt is not repeated on every scheduler tick
DAILY_GRACE = timedelta(hours=6)  # a daily email missed by more than this (server was down) waits for the next day
_SENT = [DeliveryStatus.ACCEPTED, DeliveryStatus.UNCERTAIN, DeliveryStatus.SENDING]


def _sender(db: Session, org_id: uuid.UUID, email: str) -> EmailAccount | None:
    accts = [a for a in db.scalars(select(EmailAccount).where(
        EmailAccount.organization_id == org_id, EmailAccount.connection_status.in_([ConnectionStatus.CONNECTED, ConnectionStatus.ERROR]))) if a.can_send]
    if email.strip():
        return next((a for a in accts if a.email_address.lower() == email.strip().lower()), None)
    return next((a for a in accts if a.is_default_sender), accts[0] if accts else None)


def latest_slot(sched: DigestSchedule, now: datetime) -> datetime:
    """The most recent moment a daily schedule was due (UTC)."""
    tz = ZoneInfo(sched.timezone)
    local = now.astimezone(tz)
    hh, mm = (int(x) for x in sched.time_of_day.split(":"))
    slot = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if slot > local:
        slot -= timedelta(days=1)
    return slot.astimezone(timezone.utc)


def _deliveries(org_id: uuid.UUID, sched: DigestSchedule):
    cond = EmailDelivery.idempotency_key.like(f"digest:{org_id}:{sched.id}:%")
    if sched.id == "default":  # the pre-multi-schedule keys
        cond = or_(cond, EmailDelivery.idempotency_key.like(f"digest:{org_id}:after:%"))
    return select(EmailDelivery).where(EmailDelivery.organization_id == org_id, cond)


def digest_schedule(db: Session, org_id: uuid.UUID, sched: DigestSchedule, now: datetime | None = None) -> str:
    """Send one schedule's email if it is due. Returns a short status (the delivery status when something was sent)."""
    if not sched.enabled or not sched.recipients:
        return "disabled"
    now = now or utcnow()
    base = _deliveries(org_id, sched)
    latest = db.scalar(base.order_by(EmailDelivery.created_at.desc()))
    last_ok = db.scalar(base.where(EmailDelivery.status.in_(_SENT)).order_by(EmailDelivery.created_at.desc()))
    if sched.frequency == "daily":
        slot = latest_slot(sched, now)
        if now - slot > DAILY_GRACE:
            return "missed_slot"
        if last_ok and last_ok.created_at >= slot:
            return "not_due"
        key = f"digest:{org_id}:{sched.id}:slot:{slot:%Y%m%d%H%M}"
    else:
        if last_ok and now - last_ok.created_at < timedelta(hours=sched.interval_hours):
            return "not_due"
        key = f"digest:{org_id}:{sched.id}:after:{last_ok.id if last_ok else 'start'}"
    if latest and latest.status == DeliveryStatus.FAILED and now - latest.created_at < RETRY_AFTER:
        return "backoff"
    if db.scalar(select(ProcessingJob.id).where(ProcessingJob.organization_id == org_id, ProcessingJob.job_type == "sync",
                                                ProcessingJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])).limit(1)):
        return "sync_running"  # wait so the file reflects the newest mail
    acct = _sender(db, org_id, sched.sender_email)
    if acct is None:
        return "no_sender"
    stmt = select(JobRequirement.id).where(JobRequirement.organization_id == org_id, JobRequirement.lifecycle_status == LifecycleStatus.ACTIVE,
                                           JobRequirement.review_status != ReviewStatus.REJECTED)
    if sched.mode == "delta":
        if last_ok:
            stmt = stmt.where(JobRequirement.updated_at > last_ok.created_at)
        scope = "new or updated since the last email" if last_ok else "currently active"
    elif sched.mode == "last_days":
        stmt = stmt.where(JobRequirement.updated_at >= now - timedelta(days=sched.days))
        scope = f"new or updated in the last {sched.days} days"
    else:
        scope = "currently active"
    ids = [str(i) for i in db.scalars(stmt)]
    if not ids:
        return "nothing_new"
    user_id, acct_id = acct.connected_by_user_id, acct.id
    recipients = validate_recipients(sched.recipients)
    job = jobs.create_job(db, org_id=org_id, job_type="export", payload={}, user_id=user_id)
    exp = ExportJob(organization_id=org_id, requested_by=user_id, filename=f"requirements-{now:%Y-%m-%d-%H%M}.xlsx", options={"include_summary": True},
                    filters={}, selected_record_ids=ids, status=ExportStatus.QUEUED, processing_job_id=job.id)
    db.add(exp)
    db.flush()
    export_id = exp.id
    job.payload = {"export_id": str(export_id)}
    db.commit()
    exp = run_export(db, export_id)
    if exp.status != ExportStatus.COMPLETED:
        return "export_failed"
    when = f"every {sched.interval_hours} hours" if sched.frequency == "hours" else f"daily at {sched.time_of_day} {sched.timezone}"
    body = f"Hello,\n\nAttached are the {len(ids)} requirements {scope} (scheduled email \"{sched.name}\", {when}).\n\nRegards"
    d, _ = create_delivery(db, org_id=org_id, user_id=user_id, export_id=export_id, sender_account_id=acct_id, to=recipients, cc=[],
                           subject=f"{sched.name} ({len(ids)})", body=body, confirmed=True, idempotency_key=key)
    db.commit()
    return send_delivery(db, d.id).status


def run_due_digests(db: Session) -> int:
    n = 0
    for row in list(db.scalars(select(AppSetting).where(AppSetting.section == "digest"))):
        try:
            cfg = DigestSettings.model_validate(row.value)
        except Exception:  # noqa: BLE001
            log.exception("digest_settings_invalid", extra={"organization_id": str(row.organization_id)})
            continue
        for sched in cfg.schedules:
            try:
                if digest_schedule(db, row.organization_id, sched) in (DeliveryStatus.ACCEPTED, DeliveryStatus.UNCERTAIN):
                    n += 1
            except Exception:  # noqa: BLE001 - one schedule must not stop the others
                db.rollback()
                log.exception("digest_failed", extra={"organization_id": str(row.organization_id), "schedule": sched.id})
    return n
