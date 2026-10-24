"""Task implementations (plain functions) + dispatcher.

`enqueue` sends to Celery when a broker is configured; otherwise (tests, no-Redis development) it runs inline.
Each implementation opens its own DB session and is idempotent, so retries and duplicate deliveries are safe.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger, job_id_var
from app.db.session import session_factory
from app.db.types import utcnow
from app.models.email import EmailAccount, EmailMessage
from app.models.enums import ConnectionStatus, DeliveryStatus, JobStatus, MessageStatus
from app.models.ops import EmailDelivery, ProcessingJob
from app.services import jobs
from app.services.exports.runner import cleanup_expired_exports, run_export
from app.services.extraction.pipeline import TransientProcessingError, process_message
from app.services.gmail.sync import RetryableSyncError, run_sync_job

log = get_logger(__name__)


def sync_account_impl(job_id: str) -> None:
    job_id_var.set(job_id)
    db = session_factory()()
    try:
        new_ids = run_sync_job(db, uuid.UUID(job_id))
    finally:
        db.close()
    for mid in new_ids:
        enqueue("process_email", str(mid))


def process_email_impl(message_id: str, force: bool = False, user_id: str | None = None) -> str:
    db = session_factory()()
    try:
        try:
            status = process_message(db, uuid.UUID(message_id), force=force, user_id=uuid.UUID(user_id) if user_id else None)
        except TransientProcessingError:
            db.commit()  # persist failed status + attempts before the retry
            raise
        db.commit()
        return status
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_export_impl(export_id: str) -> None:
    db = session_factory()()
    try:
        run_export(db, uuid.UUID(export_id))
    finally:
        db.close()


def send_delivery_impl(delivery_id: str) -> None:
    from app.services.delivery.service import send_delivery

    db = session_factory()()
    try:
        send_delivery(db, uuid.UUID(delivery_id))
    finally:
        db.close()


def send_digests_impl() -> int:
    from app.services.delivery.digest import run_due_digests

    db = session_factory()()
    try:
        return run_due_digests(db)
    finally:
        db.close()


def schedule_periodic_syncs_impl() -> int:
    """Create sync jobs for every enabled, connected account that is due (no active job)."""
    from app.services.jobs import active_job_for_account, create_job

    n = 0
    db = session_factory()()
    try:
        s = get_settings()
        due_before = utcnow() - timedelta(minutes=max(1, s.sync_interval_minutes) - 1)
        accts = db.scalars(select(EmailAccount).where(EmailAccount.sync_enabled.is_(True), EmailAccount.connection_status.in_(
            [ConnectionStatus.CONNECTED, ConnectionStatus.ERROR])))
        created: list[str] = []
        for a in accts:
            if active_job_for_account(db, a.id):
                continue
            if a.last_synced_at and a.last_synced_at > due_before:
                continue
            job = create_job(db, org_id=a.organization_id, job_type="sync", account_id=a.id, payload={"mode": "auto", "trigger": "schedule"})
            created.append(str(job.id))
        db.commit()
        n = len(created)
    finally:
        db.close()
    for jid in created:
        enqueue("sync_account", jid)
    return n


def process_pending_messages_impl(limit: int = 200) -> int:
    """Pick up messages left pending (e.g. after a restart) or waiting for AI once it becomes available."""
    from app.services.extraction.providers import get_provider

    db = session_factory()()
    try:
        statuses = [MessageStatus.PENDING, MessageStatus.PROCESSING]
        try:
            if get_provider() is not None:
                statuses.append(MessageStatus.AWAITING_AI)
        except Exception:  # noqa: BLE001
            pass
        stale = utcnow() - timedelta(minutes=15)
        rows = db.scalars(select(EmailMessage).where(EmailMessage.processing_status.in_(statuses), EmailMessage.updated_at < stale)
                          .order_by(EmailMessage.received_at.desc().nullslast()).limit(limit))
        ids = [str(m.id) for m in rows]
    finally:
        db.close()
    for i in ids:
        enqueue("process_email", i)
    return len(ids)


def resume_stuck_jobs_impl() -> int:
    """Re-dispatch jobs that were running when a worker died (no heartbeat for 10 minutes)."""
    db = session_factory()()
    try:
        cutoff = utcnow() - timedelta(minutes=10)
        stuck = list(db.scalars(select(ProcessingJob).where(ProcessingJob.status.in_([JobStatus.RUNNING, JobStatus.QUEUED]),
                                                            ProcessingJob.updated_at < cutoff)))
        out = []
        for j in stuck:
            if j.attempts >= j.max_attempts:
                jobs.finish(j, JobStatus.FAILED, "Abandoned after repeated worker interruptions")
                continue
            j.status = JobStatus.QUEUED
            out.append((j.job_type, str(j.id), str(j.email_account_id) if j.email_account_id else None))
        db.commit()
    finally:
        db.close()
    for jtype, jid, _ in out:
        if jtype == "sync":
            enqueue("sync_account", jid)
    return len(out)


def cleanup_impl() -> dict:
    from app.models.email import EmailMessage as M

    db = session_factory()()
    try:
        removed = cleanup_expired_exports(db)
        cutoff = utcnow() - timedelta(days=get_settings().email_body_retention_days)
        purged = 0
        for m in db.scalars(select(M).where(M.received_at < cutoff, M.body_text.is_not(None))):
            m.body_text, m.body_purged = None, True
            purged += 1
        db.commit()
        return {"exports_expired": removed, "bodies_purged": purged}
    finally:
        db.close()


def reconcile_accounts_impl() -> int:
    """Daily safety net: recent-window full sync per account to recover anything push/history missed."""
    from app.services.jobs import active_job_for_account, create_job

    db = session_factory()()
    ids: list[str] = []
    try:
        for a in db.scalars(select(EmailAccount).where(EmailAccount.sync_enabled.is_(True), EmailAccount.connection_status == ConnectionStatus.CONNECTED)):
            if active_job_for_account(db, a.id):
                continue
            j = create_job(db, org_id=a.organization_id, job_type="sync", account_id=a.id, payload={"mode": "full", "import_days": 3, "trigger": "reconcile"})
            ids.append(str(j.id))
        db.commit()
    finally:
        db.close()
    for i in ids:
        enqueue("sync_account", i)
    return len(ids)


_INLINE = {
    "sync_account": sync_account_impl,
    "process_email": process_email_impl,
    "run_export": run_export_impl,
    "send_delivery": send_delivery_impl,
}


def use_inline() -> bool:
    s = get_settings()
    return s.celery_eager or not s.redis_url


def enqueue(name: str, *args, **kwargs) -> None:
    """Dispatch a task. Inline mode swallows+logs exceptions the way a worker would (state is already persisted)."""
    if use_inline():
        try:
            _INLINE[name](*args, **kwargs)
        except (RetryableSyncError, TransientProcessingError) as e:
            log.warning("task_retry_needed_inline", extra={"task": name, "error": str(e)[:200]})
        except Exception:  # noqa: BLE001
            log.exception("inline_task_failed", extra={"task": name})
        return
    from app.tasks.celery_app import celery_app

    celery_app.send_task(f"rd.{name}", args=list(args), kwargs=kwargs)
