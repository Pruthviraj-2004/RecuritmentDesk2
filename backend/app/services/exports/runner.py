"""Export job execution and retention cleanup."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationFailure
from app.core.logging import get_logger
from app.db.types import utcnow
from app.integrations.storage import StorageError, get_storage
from app.models.email import EmailAccount, EmailMessage
from app.models.enums import ExportStatus, JobStatus, LifecycleStatus
from app.models.ops import ExportJob, ProcessingJob
from app.models.requirements import JobRequirement, RequirementSource
from app.services import jobs
from app.services.audit import service as audit
from app.services.exports.excel import SORTABLE, build_workbook, resolve_columns, safe_filename
from app.services.requirements.query import RequirementFilters, apply_filters, apply_sort

log = get_logger(__name__)
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
BATCH = 500


def run_export(db: Session, export_id: uuid.UUID) -> ExportJob:
    exp = db.get(ExportJob, export_id)
    if exp is None:
        raise NotFoundError("Export not found")
    if exp.status in (ExportStatus.COMPLETED, ExportStatus.EXPIRED):
        return exp
    job = db.get(ProcessingJob, exp.processing_job_id) if exp.processing_job_id else None
    if job:
        jobs.start(job)
    exp.status = ExportStatus.RUNNING
    db.commit()
    try:
        opts = exp.options or {}
        columns = resolve_columns(opts.get("columns"), bool(opts.get("include_source")), bool(opts.get("include_audit")))
        base = select(JobRequirement).options(selectinload(JobRequirement.skills), selectinload(JobRequirement.sources))
        if exp.selected_record_ids:
            ids = [uuid.UUID(i) for i in exp.selected_record_ids]
            stmt = base.where(JobRequirement.organization_id == exp.organization_id, JobRequirement.id.in_(ids),
                              JobRequirement.lifecycle_status != LifecycleStatus.MERGED)
        else:
            stmt = apply_filters(base, exp.organization_id, RequirementFilters.model_validate(exp.filters or {}))
        stmt = apply_sort(stmt, opts.get("sort") if opts.get("sort") in SORTABLE else "received_at", opts.get("direction", "desc"))

        account_names: dict[uuid.UUID, str] = {}

        def rows():
            offset = 0
            while True:
                batch = list(db.scalars(stmt.limit(BATCH).offset(offset)))
                if not batch:
                    return
                if opts.get("include_source"):
                    msg_ids = [s.email_message_id for r in batch for s in r.sources if s.email_message_id]
                    if msg_ids:
                        for mid, aid, email in db.execute(select(EmailMessage.id, EmailAccount.id, EmailAccount.email_address)
                                                           .join(EmailAccount, EmailAccount.id == EmailMessage.email_account_id)
                                                           .where(EmailMessage.id.in_(msg_ids))):
                            account_names[mid] = email
                    for r in batch:
                        r._source_accounts = sorted({account_names[s.email_message_id] for s in r.sources if s.email_message_id in account_names})
                yield from batch
                offset += BATCH

        meta = None
        if opts.get("include_metadata"):
            meta = {"Generated at (UTC)": utcnow().strftime("%Y-%m-%d %H:%M"), "Filters": exp.filters or {}, "Selected records": len(exp.selected_record_ids or []) or "all matching"}
        data, count = build_workbook(rows(), columns, sheet_name=opts.get("sheet_name") or "Requirements",
                                     summary={"Generated (UTC)": utcnow().strftime("%Y-%m-%d %H:%M")} if opts.get("include_summary", True) else None,
                                     metadata=meta)
        if count == 0:
            raise ValidationFailure("No requirements matched this export selection")
        ref = get_storage().save(f"exports/{exp.organization_id}", data, ".xlsx")
        exp.file_reference, exp.file_size_bytes, exp.record_count = ref, len(data), count
        exp.status, exp.completed_at = ExportStatus.COMPLETED, utcnow()
        exp.expires_at = exp.completed_at + timedelta(days=get_settings().export_retention_days)
        exp.error_summary = None
        if job:
            jobs.finish(job, JobStatus.COMPLETED)
        audit.record(db, org_id=exp.organization_id, user_id=exp.requested_by, action="export.generated", entity_type="export", entity_id=exp.id,
                     metadata={"records": count, "filename": exp.filename})
        audit.notify(db, org_id=exp.organization_id, kind="export_completed", title="Excel export ready", body=f"{exp.filename} ({count} requirements)", link="/exports")
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        exp = db.get(ExportJob, export_id)
        exp.status = ExportStatus.FAILED
        exp.error_summary = (str(e) if isinstance(e, (ValidationFailure, StorageError)) else f"Export failed ({type(e).__name__})")[:500]
        if job := (db.get(ProcessingJob, exp.processing_job_id) if exp.processing_job_id else None):
            jobs.finish(job, JobStatus.FAILED, exp.error_summary)
        if not isinstance(e, ValidationFailure):
            log.exception("export_failed", extra={"export_id": str(export_id)})
        db.commit()
    return exp


def read_export_file(db: Session, org_id: uuid.UUID, export_id: uuid.UUID) -> tuple[ExportJob, bytes]:
    exp = db.scalar(select(ExportJob).where(ExportJob.id == export_id, ExportJob.organization_id == org_id))
    if not exp:
        raise NotFoundError("Export not found")
    if exp.status != ExportStatus.COMPLETED or not exp.file_reference:
        raise ValidationFailure("Export is not ready", code="export_not_ready")
    if exp.expires_at and exp.expires_at < utcnow():
        raise PermissionDeniedError("Export has expired", code="export_expired")
    try:
        return exp, get_storage().read(exp.file_reference)
    except StorageError as e:
        raise NotFoundError("Export file is no longer available") from e


def cleanup_expired_exports(db: Session) -> int:
    n = 0
    for exp in db.scalars(select(ExportJob).where(ExportJob.status == ExportStatus.COMPLETED, ExportJob.expires_at < utcnow())):
        if exp.file_reference:
            get_storage().delete(exp.file_reference)
        exp.file_reference, exp.status = None, ExportStatus.EXPIRED
        n += 1
    db.commit()
    return n


def default_filename(fmt: str | None, name: str | None) -> str:
    base = safe_filename(name or (fmt or "recruitment-requirements-{date}").replace("{date}", utcnow().strftime("%Y-%m-%d")))
    return base if base.lower().endswith(".xlsx") else base + ".xlsx"
