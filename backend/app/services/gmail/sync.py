"""Gmail synchronization: windowed initial import, incremental history sync, checkpointing, idempotency."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.types import utcnow
from app.integrations.gmail_client import (
    GmailAuthError,
    GmailHistoryExpired,
    GmailNotFound,
    GmailRateLimited,
    GmailTransient,
)
from app.models.email import EmailAccount, EmailAttachment, EmailMessage, EmailSyncState
from app.models.enums import ConnectionStatus, JobStatus, MessageStatus
from app.models.ops import ProcessingJob
from app.services import jobs
from app.services.audit import service as audit
from app.services.gmail.accounts import gateway_for
from app.services.app_settings import get_section
from app.services.classification.heuristics import classify_email
from app.services.gmail.own_mail import own_addresses, own_mail_reason
from app.services.gmail.mime import ParsedMessage, parse_gmail_message
from app.models.enums import MessageClassification
from app.services.normalization.text import message_content_hash

log = get_logger(__name__)

PAGE_SIZE = 100


class RetryableSyncError(Exception):
    """Raised for transient failures; the task layer retries with exponential backoff."""


# Gmail only returns mail that mentions a hiring-related term, so everything else is never even fetched.
RECRUITMENT_TERMS = ('(requirement OR requirements OR hiring OR "job description" OR "job opening" OR "job requirement" OR vacancy OR opening OR '
                     '"open position" OR "looking for" OR JD OR "urgent need" OR "immediate joiner")')


def build_query(days: int, extra: str | None, recruitment_only: bool = True) -> str:
    q = f"newer_than:{int(days)}d -in:spam -in:trash -in:chats -category:promotions -category:social"
    if recruitment_only:
        q += " " + RECRUITMENT_TERMS
    if extra:
        q += " " + extra
    return q


def store_message(db: Session, acct: EmailAccount, p: ParsedMessage) -> tuple[EmailMessage, bool]:
    """Idempotently store a parsed message. Returns (message, created)."""
    existing = db.scalar(select(EmailMessage).where(EmailMessage.email_account_id == acct.id, EmailMessage.gmail_message_id == p.gmail_id))
    if existing:
        return existing, False
    sigs = [f"{a.filename.lower()}:{a.size}" for a in p.attachments]
    chash = message_content_hash(p.sender_email, p.subject, p.body_text, sigs)
    original = db.scalar(select(EmailMessage).where(
        EmailMessage.organization_id == acct.organization_id, EmailMessage.normalized_content_hash == chash,
        EmailMessage.email_account_id != acct.id).order_by(EmailMessage.created_at))
    msg = EmailMessage(
        organization_id=acct.organization_id, email_account_id=acct.id, gmail_message_id=p.gmail_id, gmail_thread_id=p.thread_id,
        rfc_message_id=(p.rfc_message_id or "")[:2000] or None, sender=p.sender, sender_email=p.sender_email, recipients=p.recipients, subject=p.subject,
        snippet=p.snippet, body_text=p.body_text, labels=p.labels, received_at=p.received_at, normalized_content_hash=chash,
        duplicate_of_message_id=original.id if original else None, processing_status=MessageStatus.PENDING, source_metadata={
            "history_id": p.history_id, "attachment_count": len(p.attachments),
            "attachments": [{"id": a.attachment_id, "name": a.filename} for a in p.attachments][:20]},
    )
    for a in p.attachments[: get_settings().max_attachments_per_message]:
        msg.attachments.append(EmailAttachment(gmail_attachment_id=a.attachment_id, filename=a.filename, content_type=(a.content_type or "")[:200] or None,
                                               size_bytes=a.size, extraction_status="pending"))
    try:
        with db.begin_nested():
            db.add(msg)
            db.flush()
    except IntegrityError:  # concurrent worker stored it first
        found = db.scalar(select(EmailMessage).where(EmailMessage.email_account_id == acct.id, EmailMessage.gmail_message_id == p.gmail_id))
        if found:
            return found, False
        raise
    return msg, True


def _commit_progress(db: Session, job: ProcessingJob) -> None:
    job.updated_at = utcnow()
    db.commit()


def run_sync_job(db: Session, job_id: uuid.UUID) -> list[uuid.UUID]:
    """Run (or resume) a sync job. Returns IDs of newly stored messages that need processing.

    Raises RetryableSyncError for transient problems; all progress is checkpointed so a retry/restart resumes.
    """
    job = db.get(ProcessingJob, job_id)
    if job is None or job.status in (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS, JobStatus.CANCELLED, JobStatus.FAILED):
        return []
    acct = db.get(EmailAccount, job.email_account_id) if job.email_account_id else None
    if acct is None or acct.connection_status in (ConnectionStatus.DISCONNECTED,):
        jobs.finish(job, JobStatus.FAILED, "Account is not connected")
        db.commit()
        return []
    if job.status == JobStatus.CANCEL_REQUESTED:
        jobs.finish(job, JobStatus.CANCELLED)
        db.commit()
        return []

    jobs.start(job)
    previous_status = acct.connection_status
    acct.connection_status = ConnectionStatus.SYNCING
    state = acct.sync_state or EmailSyncState(email_account_id=acct.id, cursor_metadata={})
    if acct.sync_state is None:
        db.add(state)
    state.status = "running"
    db.commit()

    new_ids: list[uuid.UUID] = []
    try:
        gw = gateway_for(db, acct)
        ck = dict(job.checkpoint or {})
        if "history_start" not in ck:
            ck["history_start"] = str(gw.get_profile().get("historyId") or "")
        mode = ck.get("mode")
        if not mode:
            full_requested = (job.payload or {}).get("mode") == "full"
            mode = "full" if (full_requested or not state.gmail_history_id) else "incremental"
            ck["mode"] = mode
        job.checkpoint = ck
        _commit_progress(db, job)

        if mode == "incremental":
            try:
                _run_incremental(db, job, acct, state, gw, new_ids)
            except GmailHistoryExpired:
                jobs.bump(job, history_expired=1)
                ck = {"history_start": ck["history_start"], "mode": "full", "reconciled": True}
                job.checkpoint = ck
                _commit_progress(db, job)
                _run_full(db, job, acct, gw, new_ids)
        else:
            _run_full(db, job, acct, gw, new_ids)

        db.refresh(job)
        if job.status == JobStatus.CANCEL_REQUESTED:
            jobs.finish(job, JobStatus.CANCELLED)
            acct.connection_status = ConnectionStatus.CONNECTED if previous_status != ConnectionStatus.EXPIRED else previous_status
            state.status = "idle"
            audit.record(db, org_id=job.organization_id, user_id=job.requested_by, action="sync.cancelled", entity_type="email_account", entity_id=acct.id)
            db.commit()
            return new_ids

        state.gmail_history_id = job.checkpoint.get("history_start") or state.gmail_history_id
        state.last_successful_sync_at = utcnow()
        state.status = "idle"
        state.error_summary = None
        state.updated_at = utcnow()
        acct.last_synced_at = state.last_successful_sync_at
        acct.connection_status = ConnectionStatus.CONNECTED
        acct.last_error = None
        errors = (job.stats or {}).get("message_errors", 0)
        jobs.finish(job, JobStatus.COMPLETED_WITH_ERRORS if errors else JobStatus.COMPLETED,
                    f"{errors} message(s) could not be stored (see error samples in the job details)" if errors else None)
        audit.record(db, org_id=job.organization_id, user_id=job.requested_by, action="sync.completed", entity_type="email_account",
                     entity_id=acct.id, metadata={"account": acct.email_address, **(job.stats or {})})
        db.commit()
        return new_ids

    except GmailAuthError as e:
        db.rollback()
        _fail(db, job_id, acct.id, str(e), expired=True)
        return new_ids
    except (GmailRateLimited, GmailTransient) as e:
        db.rollback()
        job = db.get(ProcessingJob, job_id)
        acct = db.get(EmailAccount, acct.id)
        if job.attempts >= job.max_attempts:
            _fail(db, job_id, acct.id, f"Gave up after {job.attempts} attempts: {e}", expired=False)
            return new_ids
        job.status = JobStatus.QUEUED
        job.error_summary = f"Temporary error, will retry: {e}"[:500]
        acct.connection_status = ConnectionStatus.CONNECTED if previous_status == ConnectionStatus.SYNCING else previous_status
        db.commit()
        raise RetryableSyncError(str(e)) from e
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log.exception("sync_job_failed", extra={"job_id": str(job_id)})
        _fail(db, job_id, acct.id, f"Unexpected error: {type(e).__name__}", expired=False)
        return new_ids


def _fail(db: Session, job_id: uuid.UUID, account_id: uuid.UUID, message: str, expired: bool) -> None:
    job = db.get(ProcessingJob, job_id)
    acct = db.get(EmailAccount, account_id)
    jobs.finish(job, JobStatus.FAILED, message)
    acct.connection_status = ConnectionStatus.EXPIRED if expired else ConnectionStatus.ERROR
    acct.last_error = message[:500]
    if acct.sync_state:
        acct.sync_state.status = "error"
        acct.sync_state.error_summary = message[:500]
    audit.record(db, org_id=job.organization_id, user_id=job.requested_by, action="sync.failed", entity_type="email_account", entity_id=acct.id,
                 metadata={"account": acct.email_address, "error": message[:300]})
    audit.notify(db, org_id=job.organization_id, kind="sync_failed", severity="error", title=f"Sync failed for {acct.email_address}",
                 body=message, link="/sync-jobs")
    db.commit()


def _ingest_ids(db: Session, job: ProcessingJob, acct: EmailAccount, gw, ids: list[str], new_ids: list[uuid.UUID], only_recruitment: bool) -> None:
    s = get_settings()
    own = own_addresses(db, acct.organization_id)
    for gid in ids:
        already = db.scalar(select(EmailMessage.id).where(EmailMessage.email_account_id == acct.id, EmailMessage.gmail_message_id == gid))
        if already:
            jobs.bump(job, fetched=1, skipped_existing=1)
            continue
        try:
            raw = gw.get_message(gid)
        except GmailNotFound:  # deleted/moved between listing and fetching (common with history sync): nothing to import, not an error
            jobs.bump(job, fetched=1, skipped_missing=1)
            continue
        try:
            parsed = parse_gmail_message(raw, s.max_email_body_chars)
            reason = own_mail_reason(db, acct.organization_id, sender_email=parsed.sender_email, own=own, filenames=[a.filename for a in parsed.attachments],
                                     mime_types=[a.content_type for a in parsed.attachments], labels=parsed.labels, export_header=parsed.exported_by_app,
                                     rfc_message_id=parsed.rfc_message_id)
            if reason:  # our own exports / digests / outgoing mail contain requirements that are already in the system
                jobs.bump(job, fetched=1, **{f"skipped_{reason}": 1})
                continue
            if only_recruitment:
                cls = classify_email(parsed.subject, parsed.body_text, parsed.sender, bool(parsed.attachments))
                if cls.category == MessageClassification.UNRELATED and cls.confidence >= 0.7:
                    jobs.bump(job, fetched=1, skipped_unrelated=1)  # clearly not recruitment: nothing is stored
                    continue
            msg, created = store_message(db, acct, parsed)
        except Exception as e:  # noqa: BLE001 - one malformed/oversized message must not fail the whole sync
            log.warning("message_store_failed", extra={"gmail_id": gid, "error_type": type(e).__name__})
            jobs.bump(job, fetched=1, message_errors=1)
            _note_error(job, gid, e)
            continue
        jobs.bump(job, fetched=1, **({"stored": 1} if created else {"skipped_existing": 1}))
        if created:
            new_ids.append(msg.id)


def _note_error(job: ProcessingJob, gid: str, exc: Exception) -> None:
    """Keep a few error samples (message id, exception type, first line; never email content) so failures are diagnosable from the UI."""
    ck = dict(job.checkpoint or {})
    samples = list(ck.get("error_samples", []))
    if len(samples) < 5:
        samples.append(f"{gid}: {type(exc).__name__}: {str(exc).splitlines()[0][:160] if str(exc) else ''}")
        ck["error_samples"] = samples
        job.checkpoint = ck


def _only_recruitment(db: Session, acct: EmailAccount) -> bool:
    value = get_section(db, acct.organization_id, "gmail").only_recruitment_emails
    db.commit()  # end the read transaction so a concurrent cancel/settings write never conflicts with this long-running job
    return value


def _cancel_requested(db: Session, job: ProcessingJob) -> bool:
    db.refresh(job)
    return job.status == JobStatus.CANCEL_REQUESTED


def _run_full(db: Session, job: ProcessingJob, acct: EmailAccount, gw, new_ids: list[uuid.UUID]) -> None:
    days = min(int((job.payload or {}).get("import_days") or acct.import_days or get_settings().initial_import_days), get_settings().max_import_days)
    only = _only_recruitment(db, acct)
    query = build_query(days, acct.extra_query, only)
    ck = dict(job.checkpoint)
    token = ck.get("page_token")
    while True:
        ids, token = gw.list_message_ids(query, token, PAGE_SIZE)
        _ingest_ids(db, job, acct, gw, ids, new_ids, only)
        ck["page_token"] = token
        ck["pages"] = ck.get("pages", 0) + 1
        if (job.checkpoint or {}).get("error_samples"):
            ck["error_samples"] = job.checkpoint["error_samples"]  # keep samples recorded while ingesting this page
        job.checkpoint = ck
        _commit_progress(db, job)  # durable checkpoint after every page
        if _cancel_requested(db, job) or not token:
            break


def _run_incremental(db: Session, job: ProcessingJob, acct: EmailAccount, state: EmailSyncState, gw, new_ids: list[uuid.UUID]) -> None:
    ck = dict(job.checkpoint)
    token = ck.get("page_token")
    only = _only_recruitment(db, acct)
    start = state.gmail_history_id
    while True:
        ids, token, _ = gw.list_history(start, token)
        _ingest_ids(db, job, acct, gw, ids, new_ids, only)
        ck["page_token"] = token
        if (job.checkpoint or {}).get("error_samples"):
            ck["error_samples"] = job.checkpoint["error_samples"]  # keep samples recorded while ingesting this page
        job.checkpoint = ck
        _commit_progress(db, job)
        if _cancel_requested(db, job) or not token:
            break
