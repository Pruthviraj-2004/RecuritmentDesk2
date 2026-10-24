"""Scheduled digest: every N hours email an Excel file of requirements that are new or changed since the previous digest.

Opt-in per organization (Settings > Scheduled email). Nothing is sent when nothing changed. The previous digest is found through
its idempotency key, so no extra state is stored and a restart can never double send.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.types import utcnow
from app.models.email import EmailAccount
from app.models.enums import ConnectionStatus, DeliveryStatus, ExportStatus, JobStatus, LifecycleStatus, ReviewStatus
from app.models.ops import AppSetting, EmailDelivery, ExportJob, ProcessingJob
from app.models.requirements import JobRequirement
from app.services import jobs
from app.services.app_settings import DigestSettings
from app.services.delivery.service import create_delivery, send_delivery, validate_recipients
from app.services.exports.runner import run_export

log = get_logger(__name__)
RETRY_AFTER = timedelta(minutes=30)  # a failed attempt is not repeated on every scheduler tick
_SENT = [DeliveryStatus.ACCEPTED, DeliveryStatus.UNCERTAIN, DeliveryStatus.SENDING]


def _sender(db: Session, org_id: uuid.UUID, email: str) -> EmailAccount | None:
    accts = [a for a in db.scalars(select(EmailAccount).where(
        EmailAccount.organization_id == org_id, EmailAccount.connection_status.in_([ConnectionStatus.CONNECTED, ConnectionStatus.ERROR]))) if a.can_send]
    if email.strip():
        return next((a for a in accts if a.email_address.lower() == email.strip().lower()), None)
    return next((a for a in accts if a.is_default_sender), accts[0] if accts else None)


def digest_org(db: Session, org_id: uuid.UUID, cfg: DigestSettings) -> str:
    """Send one digest if due. Returns a short status string (delivery status when sent)."""
    if not cfg.enabled or not cfg.recipients:
        return "disabled"
    now = utcnow()
    base = select(EmailDelivery).where(EmailDelivery.organization_id == org_id, EmailDelivery.idempotency_key.like("digest:%"))
    latest = db.scalar(base.order_by(EmailDelivery.created_at.desc()))
    last_ok = db.scalar(base.where(EmailDelivery.status.in_(_SENT)).order_by(EmailDelivery.created_at.desc()))
    if last_ok and now - last_ok.created_at < timedelta(hours=cfg.interval_hours):
        return "not_due"
    if latest and latest.status == DeliveryStatus.FAILED and now - latest.created_at < RETRY_AFTER:
        return "backoff"
    if db.scalar(select(ProcessingJob.id).where(ProcessingJob.organization_id == org_id, ProcessingJob.job_type == "sync",
                                                ProcessingJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])).limit(1)):
        return "sync_running"  # wait so the file reflects the newest mail
    acct = _sender(db, org_id, cfg.sender_email)
    if acct is None:
        return "no_sender"
    stmt = select(JobRequirement.id).where(JobRequirement.organization_id == org_id, JobRequirement.lifecycle_status == LifecycleStatus.ACTIVE,
                                           JobRequirement.review_status != ReviewStatus.REJECTED)
    if last_ok:
        stmt = stmt.where(JobRequirement.updated_at > last_ok.created_at)
    ids = [str(i) for i in db.scalars(stmt)]
    if not ids:
        return "nothing_new"
    user_id, acct_id = acct.connected_by_user_id, acct.id
    recipients = validate_recipients(cfg.recipients)
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
    which = "new or updated since the last email" if last_ok else "currently active"
    body = f"Hello,\n\nAttached are the {len(ids)} requirements {which} (automatic update every {cfg.interval_hours} hours).\n\nRegards"
    d, _ = create_delivery(db, org_id=org_id, user_id=user_id, export_id=export_id, sender_account_id=acct_id, to=recipients, cc=[],
                           subject=f"Recruitment requirements update ({len(ids)})", body=body, confirmed=True,
                           idempotency_key=f"digest:{org_id}:after:{last_ok.id if last_ok else 'start'}")
    db.commit()
    return send_delivery(db, d.id).status


def run_due_digests(db: Session) -> int:
    n = 0
    for row in list(db.scalars(select(AppSetting).where(AppSetting.section == "digest"))):
        try:
            if digest_org(db, row.organization_id, DigestSettings.model_validate(row.value)) in (DeliveryStatus.ACCEPTED, DeliveryStatus.UNCERTAIN):
                n += 1
        except Exception:  # noqa: BLE001 - one organization must not stop the others
            db.rollback()
            log.exception("digest_failed", extra={"organization_id": str(row.organization_id)})
    return n
