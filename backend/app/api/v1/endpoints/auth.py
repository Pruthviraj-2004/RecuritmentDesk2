from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Ctx, get_ctx
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.security import rate_limiter
from app.db.session import get_db
from app.models.auth import UserSession
from app.schemas.api import LoginIn, MeOut, PasswordChangeIn, SessionOut, UserOut
from app.services.audit import service as audit
from app.services.auth import service as auth

router = APIRouter(prefix="/auth", tags=["auth"])


def _me(ctx_user, org, role, csrf) -> MeOut:
    return MeOut(user=UserOut.model_validate(ctx_user), organization={"id": str(org.id), "name": org.name, "slug": org.slug}, role=str(role), csrf_token=csrf)


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    ip_key, acct_key = f"login:ip:{ip}", f"login:acct:{body.email.strip().lower()}"
    rate_limiter.check(ip_key, 30, 600, record=False)  # only FAILED attempts count toward the lockout
    rate_limiter.check(acct_key, 8, 600, record=False)
    try:
        user, token, sess = auth.login(db, body.email, body.password, request.headers.get("user-agent"), ip)
    except Exception:
        db.rollback()
        rate_limiter.hit(ip_key)
        rate_limiter.hit(acct_key)
        audit.record(db, org_id=None, user_id=None, action="auth.login_failed", metadata={"email": body.email[:100], "ip": ip})
        db.commit()
        raise
    from app.models.auth import OrganizationMembership, Organization

    m = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == user.id))
    org = db.get(Organization, m.organization_id)
    audit.record(db, org_id=org.id, user_id=user.id, action="auth.login", entity_type="user", entity_id=user.id)
    db.commit()
    s = get_settings()
    response.set_cookie(s.session_cookie_name, token, httponly=True, secure=s.session_cookie_secure, samesite=s.session_cookie_samesite.lower(),
                        max_age=s.session_ttl_hours * 3600, path="/")
    return _me(user, org, m.role, sess.csrf_token)


@router.post("/logout", status_code=204)
def logout(response: Response, ctx: Ctx = Depends(get_ctx)):
    auth.revoke_session(ctx.db, ctx.session)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="auth.logout", entity_type="user", entity_id=ctx.user_id)
    ctx.db.commit()
    s = get_settings()
    response.delete_cookie(s.session_cookie_name, path="/")


@router.get("/me", response_model=MeOut)
def me(ctx: Ctx = Depends(get_ctx)):
    return _me(ctx.user, ctx.org, ctx.role, ctx.session.csrf_token)


@router.post("/change-password", status_code=204)
def change_password(body: PasswordChangeIn, ctx: Ctx = Depends(get_ctx)):
    auth.change_password(ctx.db, ctx.user, body.current_password, body.new_password)
    revoked = auth.revoke_other_sessions(ctx.db, ctx.user_id, ctx.session.id)
    audit.record(ctx.db, org_id=ctx.org_id, user_id=ctx.user_id, action="auth.password_changed", entity_type="user", entity_id=ctx.user_id,
                 metadata={"other_sessions_revoked": revoked})
    ctx.db.commit()


@router.get("/sessions", response_model=list[SessionOut])
def sessions(ctx: Ctx = Depends(get_ctx)):
    rows = ctx.db.scalars(select(UserSession).where(UserSession.user_id == ctx.user_id, UserSession.revoked_at.is_(None)).order_by(UserSession.created_at.desc()))
    return [SessionOut(id=r.id, created_at=r.created_at, last_seen_at=r.last_seen_at, user_agent=r.user_agent, ip_address=r.ip_address,
                       current=r.id == ctx.session.id) for r in rows]


@router.post("/sessions/{session_id}/revoke", status_code=204)
def revoke(session_id: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    sess = ctx.db.scalar(select(UserSession).where(UserSession.id == session_id, UserSession.user_id == ctx.user_id))
    if not sess:
        raise NotFoundError("Session not found")
    auth.revoke_session(ctx.db, sess)
    ctx.db.commit()
