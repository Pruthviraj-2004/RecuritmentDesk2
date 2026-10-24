from __future__ import annotations

import re
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, ValidationFailure
from app.core.security import hash_password, hash_token, new_token, validate_password_strength, verify_password
from app.db.types import utcnow
from app.models.auth import Organization, OrganizationMembership, User, UserSession
from app.models.enums import Role


def create_user_with_org(db: Session, *, email: str, password: str, display_name: str | None, org_name: str) -> tuple[User, Organization]:
    problems = validate_password_strength(password)
    if problems:
        raise ValidationFailure("; ".join(problems))
    email = email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise ValidationFailure("A user with this email already exists")
    user = User(email=email, display_name=display_name or email.split("@")[0], password_hash=hash_password(password), role="user", is_active=True)
    db.add(user)
    slug_base = re.sub(r"[^a-z0-9]+", "-", org_name.lower()).strip("-") or "org"
    slug = slug_base
    while db.scalar(select(Organization.id).where(Organization.slug == slug)):
        slug = f"{slug_base}-{uuid.uuid4().hex[:6]}"
    org = Organization(name=org_name, slug=slug)
    db.add(org)
    db.flush()
    db.add(OrganizationMembership(organization_id=org.id, user_id=user.id, role=Role.OWNER))
    db.flush()
    return user, org


def bootstrap_admin(db: Session) -> bool:
    """Create the first administrator from INITIAL_ADMIN_* when no user exists. Returns True if created."""
    s = get_settings()
    if db.scalar(select(User.id).limit(1)):
        return False
    if not (s.initial_admin_email and s.initial_admin_password):
        return False
    create_user_with_org(db, email=s.initial_admin_email, password=s.initial_admin_password, display_name="Administrator", org_name=s.initial_org_name)
    return True


def login(db: Session, email: str, password: str, user_agent: str | None, ip: str | None) -> tuple[User, str, UserSession]:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    ok = verify_password(password, user.password_hash if user else None)
    if not user or not ok or not user.is_active:
        raise AuthenticationError("Invalid email or password", code="invalid_credentials")
    s = get_settings()
    token = new_token(32)
    sess = UserSession(user_id=user.id, token_hash=hash_token(token), csrf_token=new_token(24),
                       expires_at=utcnow() + timedelta(hours=s.session_ttl_hours), last_seen_at=utcnow(),
                       user_agent=(user_agent or "")[:300] or None, ip_address=ip)
    db.add(sess)
    user.last_login_at = utcnow()
    db.flush()
    return user, token, sess


def revoke_session(db: Session, session: UserSession) -> None:
    session.revoked_at = utcnow()


def revoke_other_sessions(db: Session, user_id: uuid.UUID, keep_id: uuid.UUID) -> int:
    res = db.execute(update(UserSession).where(UserSession.user_id == user_id, UserSession.id != keep_id, UserSession.revoked_at.is_(None))
                     .values(revoked_at=utcnow()))
    return res.rowcount or 0


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise AuthenticationError("Current password is incorrect", code="invalid_credentials")
    problems = validate_password_strength(new)
    if problems:
        raise ValidationFailure("; ".join(problems))
    user.password_hash = hash_password(new)
