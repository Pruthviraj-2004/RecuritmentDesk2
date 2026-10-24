"""Request context: session authentication, CSRF protection, organization scoping and role checks."""
from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import hash_token
from app.db.session import get_db
from app.db.types import utcnow
from app.models.auth import Organization, OrganizationMembership, User, UserSession
from app.models.enums import ROLE_RANK, Role

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class Ctx:
    db: Session
    user: User
    org: Organization
    role: Role
    session: UserSession

    @property
    def org_id(self) -> uuid.UUID:
        return self.org.id

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id


def get_ctx(request: Request, db: Session = Depends(get_db)) -> Ctx:
    s = get_settings()
    token = request.cookies.get(s.session_cookie_name)
    if not token:
        raise AuthenticationError("Not authenticated")
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    now = utcnow()
    if not sess or sess.revoked_at is not None or sess.expires_at < now:
        raise AuthenticationError("Session expired")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not hmac.compare_digest(sent, sess.csrf_token):
            raise PermissionDeniedError("Missing or invalid CSRF token", code="csrf_failed")
    user = db.get(User, sess.user_id)
    if not user or not user.is_active:
        raise AuthenticationError("Account disabled")
    m = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == user.id).order_by(OrganizationMembership.created_at))
    if not m:
        raise PermissionDeniedError("User has no organization")
    org = db.get(Organization, m.organization_id)
    if sess.last_seen_at is None or (now - sess.last_seen_at).total_seconds() > 300:
        sess.last_seen_at = now
        db.commit()
    return Ctx(db=db, user=user, org=org, role=Role(m.role), session=sess)


def require_role(minimum: Role):
    def dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        if ROLE_RANK[ctx.role] < ROLE_RANK[minimum]:
            raise PermissionDeniedError(f"This action requires the '{minimum.value}' role or higher")
        return ctx

    return dep


viewer = Depends(require_role(Role.VIEWER))
member = Depends(require_role(Role.MEMBER))
admin = Depends(require_role(Role.ADMIN))
