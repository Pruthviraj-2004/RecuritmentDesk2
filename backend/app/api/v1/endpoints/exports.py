from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, Query, Response
from sqlalchemy import func, select

from app.api.deps import Ctx, member, viewer
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailure
from app.models.email import EmailAccount
from app.models.enums import DeliveryStatus, ExportStatus, ReviewStatus
from app.models.ops import EmailDelivery, ExportJob
from app.schemas.api import DeliveryOut, ExportCreate, ExportOut, Page, RetryDeliveryIn, SendIn
from app.services import jobs
from app.services.app_settings import get_section
from app.services.audit import service as audit
from app.services.delivery import service as delivery_svc
from app.services.exports.excel import COLUMNS, DEFAULT_COLUMNS
from app.services.exports.runner import XLSX_MIME, default_filename, read_export_file
from app.services.requirements.query import RequirementFilters
from app.tasks.runner import enqueue

router = APIRouter(tags=["exports"])

STATUS_LABELS = {
    DeliveryStatus.QUEUED: "Queued", DeliveryStatus.SENDING: "Sending",
    DeliveryStatus.ACCEPTED: "Accepted by Gmail (inbox delivery is not guaranteed)",
    DeliveryStatus.FAILED: "Failed - not sent", DeliveryStatus.UNCERTAIN: "Uncertain - check Gmail Sent folder",
}


def _delivery_out(ctx: Ctx, rows: list[EmailDelivery]) -> list[DeliveryOut]:
    senders = dict(ctx.db.execute(select(EmailAccount.id, EmailAccount.email_address).where(EmailAccount.organization_id == ctx.org_id)).all())
    out = []
    for d in rows:
        o = DeliveryOut.model_validate(d)
        o.sender_email, o.status_label = senders.get(d.sender_account_id), STATUS_LABELS.get(d.status, d.status)
        out.append(o)
    return out


@router.get("/exports/columns")
def columns(ctx: Ctx = viewer):
    return {"columns": [{"key": c.key, "header": c.header, "group": c.group, "default": c.key in DEFAULT_COLUMNS} for c in COLUMNS]}


@router.post("/exports", response_model=ExportOut, status_code=202)
def create_export(body: ExportCreate, ctx: Ctx = member):
    filters = dict(body.filters or {})
    selected: list[str] = []
    if body.scope == "selected":
        if not body.selected_ids:
            raise ValidationFailure("Select at least one requirement to export")
        selected = [str(i) for i in dict.fromkeys(body.selected_ids)]
    elif body.scope == "approved":
        filters = {**filters, "review_status": ReviewStatus.APPROVED.value}
    RequirementFilters.model_validate(filters)  # validates filter keys/values early
    if body.options.columns:
        bad = [c for c in body.options.columns if c not in {x.key for x in COLUMNS}]
        if bad:
            raise ValidationFailure(f"Unknown export columns: {bad}")
    general = get_section(ctx.db, ctx.org_id, "general")
    opts = body.options.model_dump()
    if not opts.get("columns") and general.default_export_columns:
        opts["columns"] = general.default_export_columns
    job = jobs.create_job(ctx.db, org_id=ctx.org_id, job_type="export", payload={}, user_id=ctx.user_id)
    exp = ExportJob(organization_id=ctx.org_id, requested_by=ctx.user_id, filename=default_filename(general.export_filename_format, body.filename),
                    options=opts, filters={k: (v.isoformat() if hasattr(v, "isoformat") else (str(v) if isinstance(v, uuid.UUID) else v)) for k, v in filters.items()},
                    selected_record_ids=selected, status=ExportStatus.QUEUED, processing_job_id=job.id)
    ctx.db.add(exp)
    ctx.db.flush()
    job.payload = {"export_id": str(exp.id)}
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="export.requested", entity_type="export", entity_id=exp.id, metadata={"scope": body.scope})
    ctx.db.commit()
    enqueue("run_export", str(exp.id))
    ctx.db.refresh(exp)
    return exp


@router.get("/exports", response_model=Page[ExportOut])
def list_exports(ctx: Ctx = viewer, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    stmt = select(ExportJob).where(ExportJob.organization_id == ctx.org_id)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(ctx.db.scalars(stmt.order_by(ExportJob.created_at.desc()).limit(page_size).offset((page - 1) * page_size)))
    return Page(items=rows, total=total, page=page, page_size=page_size)


@router.get("/exports/{export_id}", response_model=ExportOut)
def get_export(export_id: uuid.UUID, ctx: Ctx = viewer):
    exp = ctx.db.scalar(select(ExportJob).where(ExportJob.id == export_id, ExportJob.organization_id == ctx.org_id))
    if not exp:
        raise NotFoundError("Export not found")
    return exp


@router.get("/exports/{export_id}/download")
def download(export_id: uuid.UUID, ctx: Ctx = viewer):
    exp, data = read_export_file(ctx.db, ctx.org_id, export_id)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="export.downloaded", entity_type="export", entity_id=exp.id)
    ctx.db.commit()
    return Response(content=data, media_type=XLSX_MIME, headers={
        "Content-Disposition": f'attachment; filename="{exp.filename}"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/exports/{export_id}/send", response_model=DeliveryOut, status_code=202)
def send_export(export_id: uuid.UUID, body: SendIn, ctx: Ctx = member, idempotency_key: str | None = Header(default=None, max_length=100)):
    d, created = delivery_svc.create_delivery(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, export_id=export_id, sender_account_id=body.sender_account_id,
                                              to=body.to, cc=body.cc, subject=body.subject, body=body.body, confirmed=body.confirm, idempotency_key=idempotency_key)
    ctx.db.commit()
    if created:
        enqueue("send_delivery", str(d.id))
        ctx.db.refresh(d)
    return _delivery_out(ctx, [d])[0]


@router.get("/deliveries", response_model=Page[DeliveryOut])
def list_deliveries(ctx: Ctx = viewer, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), export_id: uuid.UUID | None = None):
    stmt = select(EmailDelivery).where(EmailDelivery.organization_id == ctx.org_id)
    if export_id:
        stmt = stmt.where(EmailDelivery.export_job_id == export_id)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(ctx.db.scalars(stmt.order_by(EmailDelivery.created_at.desc()).limit(page_size).offset((page - 1) * page_size)))
    return Page(items=_delivery_out(ctx, rows), total=total, page=page, page_size=page_size)


@router.get("/deliveries/{delivery_id}", response_model=DeliveryOut)
def get_delivery(delivery_id: uuid.UUID, ctx: Ctx = viewer):
    d = ctx.db.scalar(select(EmailDelivery).where(EmailDelivery.id == delivery_id, EmailDelivery.organization_id == ctx.org_id))
    if not d:
        raise NotFoundError("Delivery not found")
    return _delivery_out(ctx, [d])[0]


@router.post("/deliveries/{delivery_id}/retry", response_model=DeliveryOut, status_code=202)
def retry_delivery(delivery_id: uuid.UUID, body: RetryDeliveryIn, ctx: Ctx = member):
    d = ctx.db.scalar(select(EmailDelivery).where(EmailDelivery.id == delivery_id, EmailDelivery.organization_id == ctx.org_id))
    if not d:
        raise NotFoundError("Delivery not found")
    if d.status == DeliveryStatus.UNCERTAIN and not body.acknowledge_possible_duplicate:
        raise ConflictError("The earlier attempt may have been delivered. Confirm that a duplicate is acceptable to retry.", code="uncertain_delivery_ack_required")
    if d.status not in (DeliveryStatus.FAILED, DeliveryStatus.UNCERTAIN):
        raise ConflictError(f"A delivery with status '{d.status}' cannot be retried")
    d.status = DeliveryStatus.QUEUED
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="delivery.retry_requested", entity_type="delivery", entity_id=d.id)
    ctx.db.commit()
    enqueue("send_delivery", str(d.id))
    ctx.db.refresh(d)
    return _delivery_out(ctx, [d])[0]


@router.get("/exports/templates/email")
def templates(ctx: Ctx = viewer):
    return {k: {"subject": v[0], "body": v[1]} for k, v in delivery_svc.TEMPLATES.items()}
