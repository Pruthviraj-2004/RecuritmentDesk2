from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Ctx, admin, get_ctx, member, viewer
from app.core.config import get_settings
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.db.session import get_db
from app.db.types import utcnow
from app.integrations.gmail_client import GmailError
from app.models.email import EmailAccount, EmailMessage
from app.models.enums import ConnectionStatus
from app.models.ops import ProcessingJob
from app.models.requirements import RequirementSource
from app.schemas.api import AccountOut, AccountPatch, ConnectIn, ConnectOut, SyncRequest
from app.services import jobs
from app.services.audit import service as audit
from app.services.gmail import accounts as acct_svc
from app.tasks.runner import enqueue

router = APIRouter(prefix="/email-accounts", tags=["email accounts"])


def mask_email(e: str) -> str:
    local, _, domain = e.partition("@")
    return f"{local[:2]}{'*' * max(1, len(local) - 2)}@{domain}"


def sync_available_at(db: Session, account_id: uuid.UUID) -> datetime | None:
    """When a manual sync may next be started for this account, or None if it may be started now."""
    cooldown = timedelta(seconds=get_settings().manual_sync_cooldown_seconds)
    if cooldown.total_seconds() <= 0:
        return None
    recent = db.scalars(select(ProcessingJob).where(ProcessingJob.email_account_id == account_id, ProcessingJob.job_type == "sync",
                                                    ProcessingJob.created_at > utcnow() - cooldown).order_by(ProcessingJob.created_at.desc()))
    for j in recent:
        if (j.payload or {}).get("trigger") == "manual":
            return j.created_at + cooldown
    return None


def _out(db: Session, a: EmailAccount, ctx_role_full: bool = True) -> AccountOut:
    total = db.scalar(select(func.count()).select_from(EmailMessage).where(EmailMessage.email_account_id == a.id)) or 0
    by_status = dict(db.execute(select(EmailMessage.processing_status, func.count()).where(EmailMessage.email_account_id == a.id)
                                .group_by(EmailMessage.processing_status)).all())
    reqs = db.scalar(select(func.count(func.distinct(RequirementSource.job_requirement_id))).join(
        EmailMessage, EmailMessage.id == RequirementSource.email_message_id).where(EmailMessage.email_account_id == a.id)) or 0
    out = AccountOut.model_validate(a)
    out.stats = {"messages": total, "processed": by_status.get("processed", 0) + by_status.get("duplicate", 0), "failed": by_status.get("failed", 0),
                 "pending": by_status.get("pending", 0) + by_status.get("awaiting_ai", 0), "requirements": reqs}
    out.masked_email = mask_email(a.email_address)
    out.sync_available_at = sync_available_at(db, a.id)
    return out


def _get(db: Session, org_id: uuid.UUID, account_id: uuid.UUID) -> EmailAccount:
    a = db.scalar(select(EmailAccount).where(EmailAccount.id == account_id, EmailAccount.organization_id == org_id))
    if not a:
        raise NotFoundError("Account not found")
    return a


@router.get("", response_model=list[AccountOut])
def list_accounts(ctx: Ctx = viewer):
    rows = ctx.db.scalars(select(EmailAccount).where(EmailAccount.organization_id == ctx.org_id).order_by(EmailAccount.created_at))
    return [_out(ctx.db, a) for a in rows]


@router.post("/connect", response_model=ConnectOut)
def connect(body: ConnectIn, ctx: Ctx = admin):
    url = acct_svc.begin_connect(ctx.db, user_id=ctx.user_id, org_id=ctx.org_id, enable_send=body.enable_send, login_hint=body.login_hint)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="account.connect_started", metadata={"send_scope": body.enable_send})
    ctx.db.commit()
    return ConnectOut(authorization_url=url)


@router.post("/{account_id}/reauthorize", response_model=ConnectOut)
def reauthorize(account_id: uuid.UUID, body: ConnectIn, ctx: Ctx = admin):
    a = _get(ctx.db, ctx.org_id, account_id)
    url = acct_svc.begin_connect(ctx.db, user_id=ctx.user_id, org_id=ctx.org_id, enable_send=body.enable_send, reauthorize_account_id=a.id,
                                 login_hint=a.email_address)
    ctx.db.commit()
    return ConnectOut(authorization_url=url)


@router.get("/oauth/callback", include_in_schema=True)
def oauth_callback(request: Request, state: str = Query(default=""), code: str = Query(default=""), error: str | None = Query(default=None),
                   ctx: Ctx = Depends(get_ctx)):
    """Browser redirect target. Always redirects to a fixed frontend path (never to a caller-supplied URL)."""
    base = get_settings().frontend_url.rstrip("/") + "/accounts"

    def back(**params):
        return RedirectResponse(f"{base}?{urlencode(params)}", status_code=303)

    if error:
        audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="account.connect_denied", metadata={"error": error[:50]})
        ctx.db.commit()
        return back(connect="denied")
    if not state or not code:
        return back(connect="invalid")
    try:
        acct = acct_svc.complete_connect(ctx.db, state=state, code=code, session_user_id=ctx.user_id)
        audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="account.connected", entity_type="email_account", entity_id=acct.id,
                     metadata={"account": acct.email_address})
        ctx.db.commit()
        return back(connect="success", account=str(acct.id))
    except (AppError, GmailError) as e:
        ctx.db.rollback()  # discards any partial account changes (the consumed OAuth state was committed earlier)
        code_ = getattr(e, "code", "failed")
        return back(connect="error", reason=code_ if code_ in ("invalid_oauth_state", "missing_scope", "no_refresh_token", "account_mismatch") else "failed")


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: uuid.UUID, ctx: Ctx = viewer):
    return _out(ctx.db, _get(ctx.db, ctx.org_id, account_id))


@router.patch("/{account_id}", response_model=AccountOut)
def patch_account(account_id: uuid.UUID, body: AccountPatch, ctx: Ctx = admin):
    a = _get(ctx.db, ctx.org_id, account_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("is_default_sender"):
        if not a.can_send or a.connection_status in (ConnectionStatus.DISCONNECTED, ConnectionStatus.EXPIRED):
            raise ConflictError("Only a connected account with send permission can be the default sender")
        for other in ctx.db.scalars(select(EmailAccount).where(EmailAccount.organization_id == ctx.org_id, EmailAccount.id != a.id)):
            other.is_default_sender = False
    for k, v in data.items():
        setattr(a, k, v)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="account.updated", entity_type="email_account", entity_id=a.id, metadata={"fields": list(data)})
    ctx.db.commit()
    return _out(ctx.db, a)


@router.delete("/{account_id}")
def disconnect(account_id: uuid.UUID, ctx: Ctx = admin):
    a = _get(ctx.db, ctx.org_id, account_id)
    revoked = acct_svc.disconnect_account(ctx.db, a)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="account.disconnected", entity_type="email_account", entity_id=a.id,
                 metadata={"account": a.email_address, "revoked_at_google": revoked})
    ctx.db.commit()
    return {"disconnected": True, "revoked_at_google": revoked}


def _start_sync(ctx: Ctx, a: EmailAccount, body: SyncRequest | None) -> dict:
    if a.connection_status in (ConnectionStatus.DISCONNECTED, ConnectionStatus.EXPIRED):
        raise ConflictError("Account must be (re)authorized before syncing", code="account_needs_reauth")
    if not a.can_read:
        raise ConflictError("Account lacks Gmail read permission", code="missing_read_scope")
    existing = jobs.active_job_for_account(ctx.db, a.id)
    if existing:
        return {"job_id": str(existing.id), "status": existing.status, "already_running": True}
    wait_until = sync_available_at(ctx.db, a.id)
    if wait_until:
        secs = max(1, int((wait_until - utcnow()).total_seconds()))
        raise AppError(f"A sync was started a moment ago. Try again after {max(1, -(-secs // 60))} minute(s).", code="sync_cooldown", status_code=429,
                       details={"available_at": wait_until.isoformat(), "retry_after_seconds": secs})
    payload = {"mode": (body.mode if body else "auto"), "trigger": "manual"}
    if body and body.import_days:
        payload["import_days"] = body.import_days
    job = jobs.create_job(ctx.db, org_id=ctx.org_id, job_type="sync", account_id=a.id, payload=payload, user_id=ctx.user_id)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="sync.started", entity_type="email_account", entity_id=a.id, metadata=payload)
    ctx.db.commit()
    enqueue("sync_account", str(job.id))
    return {"job_id": str(job.id), "status": "queued", "already_running": False}


@router.post("/sync-all")
def sync_all(ctx: Ctx = member):
    accts = ctx.db.scalars(select(EmailAccount).where(EmailAccount.organization_id == ctx.org_id, EmailAccount.sync_enabled.is_(True),
                                                      EmailAccount.connection_status.in_([ConnectionStatus.CONNECTED, ConnectionStatus.ERROR]))).all()
    results, skipped = [], []
    for a in accts:
        try:
            results.append({"account": a.email_address, **_start_sync(ctx, a, None)})
        except (ConflictError, AppError) as e:
            skipped.append({"account": a.email_address, "reason": e.message})
    return {"started": results, "skipped": skipped}


@router.post("/{account_id}/sync")
def sync_one(account_id: uuid.UUID, body: SyncRequest | None = None, ctx: Ctx = member):
    return _start_sync(ctx, _get(ctx.db, ctx.org_id, account_id), body)
