"""Gmail account connection (OAuth + PKCE), token lifecycle and gateway factory."""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, ConflictError, ValidationFailure
from app.core.security import get_cipher, hash_token, new_token, pkce_pair
from app.db.types import utcnow
from app.integrations.gmail_client import (
    IDENTITY_SCOPES,
    SCOPE_READ,
    SCOPE_SEND,
    GmailAuthError,
    GmailGateway,
    GoogleGmailGateway,
    OAuthClient,
)
from app.models.auth import OAuthState
from app.models.email import EmailAccount, EmailSyncState
from app.models.enums import ConnectionStatus

# Overridable in tests
_oauth_factory: Callable[[Settings], OAuthClient] = lambda s: OAuthClient(s)
_gateway_factory: Callable[[str], GmailGateway] = lambda token: GoogleGmailGateway(token)


def set_factories(oauth=None, gateway=None) -> None:
    global _oauth_factory, _gateway_factory
    if oauth is not None:
        _oauth_factory = oauth
    if gateway is not None:
        _gateway_factory = gateway


def reset_factories() -> None:
    global _oauth_factory, _gateway_factory
    _oauth_factory = lambda s: OAuthClient(s)
    _gateway_factory = lambda token: GoogleGmailGateway(token)


def get_oauth_client() -> OAuthClient:
    return _oauth_factory(get_settings())


def begin_connect(db: Session, *, user_id: uuid.UUID, org_id: uuid.UUID, enable_send: bool, reauthorize_account_id: uuid.UUID | None = None,
                  login_hint: str | None = None) -> str:
    s = get_settings()
    if not s.google_configured:
        raise AppError("Google OAuth is not configured on the server (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)", code="google_not_configured", status_code=503)
    state = new_token(32)
    verifier, challenge = pkce_pair()
    db.add(OAuthState(state_hash=hash_token(state), user_id=user_id, organization_id=org_id, code_verifier=verifier,
                      purpose="reauthorize" if reauthorize_account_id else "connect", enable_send=enable_send,
                      reauthorize_account_id=reauthorize_account_id, expires_at=utcnow() + timedelta(minutes=10)))
    db.flush()
    scopes = IDENTITY_SCOPES + [SCOPE_READ] + ([SCOPE_SEND] if enable_send else [])
    return get_oauth_client().authorization_url(state, challenge, scopes, login_hint)


def complete_connect(db: Session, *, state: str, code: str, session_user_id: uuid.UUID) -> EmailAccount:
    st = db.scalar(select(OAuthState).where(OAuthState.state_hash == hash_token(state)))
    if st is None or st.used_at is not None or st.expires_at < utcnow():
        raise ValidationFailure("Invalid or expired OAuth state", code="invalid_oauth_state")
    if st.user_id != session_user_id:
        raise ValidationFailure("OAuth state does not belong to this session", code="invalid_oauth_state")
    st.used_at = utcnow()  # single use, even if the exchange below fails
    db.commit()

    oauth = get_oauth_client()
    tokens = oauth.exchange_code(code, st.code_verifier)
    profile = oauth.fetch_profile(tokens.access_token)
    profile.email = profile.email.strip().lower()
    if SCOPE_READ not in tokens.scopes:
        raise ValidationFailure("Gmail read permission was not granted; it is required to synchronise recruitment emails", code="missing_scope")

    cipher = get_cipher()
    acct = db.scalar(select(EmailAccount).where(EmailAccount.organization_id == st.organization_id, EmailAccount.provider == "gmail",
                                                EmailAccount.email_address == profile.email))
    if st.purpose == "reauthorize" and st.reauthorize_account_id:
        if acct is None or acct.id != st.reauthorize_account_id:
            raise ConflictError("Reauthorization must use the same Google account", code="account_mismatch")
    if not tokens.refresh_token and not (acct and acct.encrypted_refresh_token):
        raise ValidationFailure("Google did not return a refresh token; remove the app from your Google account permissions and retry",
                                code="no_refresh_token")
    if acct is None:
        acct = EmailAccount(organization_id=st.organization_id, connected_by_user_id=st.user_id, provider="gmail",
                            email_address=profile.email, display_name=profile.name, import_days=get_settings().initial_import_days,
                            scopes=[], is_default_sender=False)
        db.add(acct)
    acct.provider_account_id = profile.sub
    acct.encrypted_access_token = cipher.encrypt(tokens.access_token)
    if tokens.refresh_token:
        acct.encrypted_refresh_token = cipher.encrypt(tokens.refresh_token)
    acct.token_expiry = utcnow() + timedelta(seconds=tokens.expires_in)
    acct.scopes = sorted(set(tokens.scopes))
    acct.connection_status = ConnectionStatus.CONNECTED
    acct.last_error = None
    db.flush()
    if acct.sync_state is None:
        db.add(EmailSyncState(email_account_id=acct.id, cursor_metadata={}))
    if acct.can_send and not db.scalar(select(EmailAccount.id).where(EmailAccount.organization_id == acct.organization_id,
                                                                     EmailAccount.is_default_sender.is_(True))):
        acct.is_default_sender = True
    db.flush()
    return acct


def get_access_token(db: Session, acct: EmailAccount) -> str:
    """Return a valid access token, refreshing (and persisting) if needed. Marks the account expired on invalid_grant."""
    cipher = get_cipher()
    now = utcnow()
    if acct.encrypted_access_token and acct.token_expiry and acct.token_expiry > now + timedelta(seconds=90):
        return cipher.decrypt(acct.encrypted_access_token)
    if not acct.encrypted_refresh_token:
        _mark_expired(db, acct, "No refresh token stored")
        raise GmailAuthError("No refresh token; reauthorization required")
    try:
        tokens = get_oauth_client().refresh(cipher.decrypt(acct.encrypted_refresh_token))
    except GmailAuthError:
        _mark_expired(db, acct, "Google authorization was revoked or expired")
        raise
    acct.encrypted_access_token = cipher.encrypt(tokens.access_token)
    acct.token_expiry = now + timedelta(seconds=tokens.expires_in)
    if tokens.refresh_token:
        acct.encrypted_refresh_token = cipher.encrypt(tokens.refresh_token)
    db.flush()
    return tokens.access_token


def _mark_expired(db: Session, acct: EmailAccount, reason: str) -> None:
    acct.connection_status = ConnectionStatus.EXPIRED
    acct.last_error = reason
    db.flush()


def gateway_for(db: Session, acct: EmailAccount) -> GmailGateway:
    return _gateway_factory(get_access_token(db, acct))


def disconnect_account(db: Session, acct: EmailAccount, revoke: bool = True) -> bool:
    """Revoke at Google where possible and remove stored credentials. Synced data is retained."""
    revoked = False
    if revoke and acct.encrypted_refresh_token:
        try:
            revoked = get_oauth_client().revoke(get_cipher().decrypt(acct.encrypted_refresh_token))
        except Exception:  # noqa: BLE001 - revocation is best effort; credentials are deleted regardless
            revoked = False
    acct.encrypted_access_token = None
    acct.encrypted_refresh_token = None
    acct.token_expiry = None
    acct.connection_status = ConnectionStatus.DISCONNECTED
    acct.sync_enabled = False
    acct.is_default_sender = False
    db.flush()
    return revoked
