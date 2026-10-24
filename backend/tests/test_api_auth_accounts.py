from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from app.models.auth import OAuthState
from app.models.email import EmailAccount
from app.models.enums import Role
from app.services.gmail import accounts as acct_svc
from tests.conftest import PASSWORD, Api, login, make_user
from tests.fakes import FakeOAuth

API = "/api/v1"


def test_login_logout_and_session_cookie_flags(client, owner):
    r = client.post(f"{API}/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "access_token" not in r.text and r.json()["role"] == "owner"
    csrf = r.json()["csrf_token"]
    assert client.get(f"{API}/auth/me").status_code == 200
    assert client.post(f"{API}/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get(f"{API}/auth/me").status_code == 401


def test_bad_credentials_are_generic_and_rate_limited(client, owner):
    r = client.post(f"{API}/auth/login", json={"email": "owner@example.com", "password": "nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    r2 = client.post(f"{API}/auth/login", json={"email": "ghost@example.com", "password": "nope"})
    assert r2.json()["error"]["message"] == r.json()["error"]["message"]  # no user enumeration
    codes = [client.post(f"{API}/auth/login", json={"email": "owner@example.com", "password": "bad"}).status_code for _ in range(10)]
    assert 429 in codes


def test_protected_endpoints_require_auth_and_csrf(client, api):
    anon = client.__class__(client.app)
    assert anon.get(f"{API}/requirements").status_code == 401
    assert anon.get(f"{API}/exports").status_code == 401
    # authenticated cookie but no CSRF header on a state-changing request
    r = client.post(f"{API}/requirements", json={"job_title": "X"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    assert api.post(f"{API}/requirements", json={"job_title": "X"}).status_code == 201


def test_viewer_cannot_write_or_manage_accounts(client, db, owner):
    from app.models.auth import OrganizationMembership

    viewer_user, _ = make_user(db, "viewer@example.com", org="Other")
    m = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == viewer_user.id))
    m.organization_id, m.role = owner[1].id, Role.VIEWER
    db.commit()
    v = login(client, "viewer@example.com")
    assert v.get(f"{API}/requirements").status_code == 200
    assert v.post(f"{API}/requirements", json={"job_title": "X"}).status_code == 403
    assert v.post(f"{API}/email-accounts/connect", json={}).status_code == 403
    assert v.put(f"{API}/settings/general", json={"values": {"theme": "dark"}}).status_code == 403


def test_connect_flow_uses_state_and_pkce_and_encrypts_tokens(client, api, db, owner):
    acct_svc.set_factories(oauth=lambda s: FakeOAuth(email="Work@Gmail.com"))
    url = api.post(f"{API}/email-accounts/connect", json={"enable_send": True}).json()["authorization_url"]
    q = parse_qs(urlparse(url).query)
    state = q["state"][0]
    assert q["cc"][0] and "gmail.send" in url and "gmail.readonly" in url
    assert db.scalar(select(OAuthState).where(OAuthState.state_hash != state)) is not None  # only a hash is stored

    r = client.get(f"{API}/email-accounts/oauth/callback", params={"state": state, "code": "good-code"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("http://localhost:5173/accounts?connect=success")
    db.expire_all()
    a = db.scalar(select(EmailAccount))
    assert a.email_address == "work@gmail.com" and a.connection_status == "connected" and a.is_default_sender
    assert "ya29" not in a.encrypted_access_token and "1//fake" not in a.encrypted_refresh_token  # encrypted at rest
    listing = api.get(f"{API}/email-accounts").json()
    assert "encrypted" not in str(listing) and "ya29" not in str(listing) and listing[0]["masked_email"].startswith("wo")
    # state is single use
    again = client.get(f"{API}/email-accounts/oauth/callback", params={"state": state, "code": "good-code"}, follow_redirects=False)
    assert "connect=error" in again.headers["location"]


def test_callback_rejects_bad_state_foreign_state_and_open_redirects(client, api, db, owner):
    acct_svc.set_factories(oauth=lambda s: FakeOAuth())
    for params in ({"state": "forged", "code": "good-code"}, {"code": "x"}, {"state": "s", "code": "x", "redirect": "https://evil.com"}):
        r = client.get(f"{API}/email-accounts/oauth/callback", params=params, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("http://localhost:5173/")
        assert "evil.com" not in r.headers["location"]
    # a state created by another user cannot be completed by this session
    other, org2 = make_user(db, "other@example.com", org="Org2")
    state = "foreign-state"
    from app.core.security import hash_token
    from app.db.types import utcnow
    from datetime import timedelta

    db.add(OAuthState(state_hash=hash_token(state), user_id=other.id, organization_id=org2.id, code_verifier="v", expires_at=utcnow() + timedelta(minutes=5)))
    db.commit()
    r = client.get(f"{API}/email-accounts/oauth/callback", params={"state": state, "code": "good-code"}, follow_redirects=False)
    assert "connect=error" in r.headers["location"] and db.scalar(select(EmailAccount)) is None


def test_denied_consent_and_missing_scope_or_refresh_token(client, api, db):
    r = client.get(f"{API}/email-accounts/oauth/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert "connect=denied" in r.headers["location"]
    for oauth, reason in ((FakeOAuth(scopes=["openid", "email"]), "missing_scope"), (FakeOAuth(refresh=False), "no_refresh_token")):
        acct_svc.set_factories(oauth=lambda s, o=oauth: o)
        state = parse_qs(urlparse(api.post(f"{API}/email-accounts/connect", json={}).json()["authorization_url"]).query)["state"][0]
        loc = client.get(f"{API}/email-accounts/oauth/callback", params={"state": state, "code": "good-code"}, follow_redirects=False).headers["location"]
        assert f"reason={reason}" in loc
    assert db.scalar(select(EmailAccount)) is None


def test_account_settings_default_sender_and_disconnect_revokes(client, api, db, connected_account):
    fake = FakeOAuth()
    acct_svc.set_factories(oauth=lambda s: fake)
    a1, a2 = connected_account("one@gmail.com", default=True), connected_account("two@gmail.com")
    r = api.patch(f"{API}/email-accounts/{a2.id}", json={"is_default_sender": True, "display_name": "Second", "import_days": 90})
    assert r.status_code == 200 and r.json()["is_default_sender"] and r.json()["import_days"] == 90
    db.expire_all()
    assert not db.get(EmailAccount, a1.id).is_default_sender
    d = api.delete(f"{API}/email-accounts/{a1.id}").json()
    assert d["revoked_at_google"] and fake.revoked
    db.expire_all()
    a1 = db.get(EmailAccount, a1.id)
    assert a1.encrypted_refresh_token is None and a1.encrypted_access_token is None and a1.connection_status == "disconnected"
    assert api.patch(f"{API}/email-accounts/{a1.id}", json={"is_default_sender": True}).status_code == 409


def test_account_scoped_to_organization(client, api, db, connected_account):
    a = connected_account("one@gmail.com")
    other, _ = make_user(db, "other@example.com", org="Org2")
    o = login(client, "other@example.com")
    assert o.get(f"{API}/email-accounts/{a.id}").status_code == 404
    assert o.get(f"{API}/email-accounts").json() == []
    assert o.post(f"{API}/email-accounts/{a.id}/sync").status_code == 404


def test_expired_token_is_refreshed_and_revoked_grant_marks_account_expired(db, connected_account):
    from datetime import timedelta

    from app.core.security import get_cipher
    from app.db.types import utcnow
    from app.integrations.gmail_client import GmailAuthError

    a = connected_account("one@gmail.com")
    fake = FakeOAuth()
    acct_svc.set_factories(oauth=lambda s: fake)
    a.token_expiry = utcnow() - timedelta(minutes=5)
    assert acct_svc.get_access_token(db, a) == "ya29.refreshed" and get_cipher().decrypt(a.encrypted_access_token) == "ya29.refreshed"
    a.token_expiry = utcnow() - timedelta(minutes=5)
    fake.refresh_error = GmailAuthError("invalid_grant")
    try:
        acct_svc.get_access_token(db, a)
        raise AssertionError("expected GmailAuthError")
    except GmailAuthError:
        pass
    assert a.connection_status == "expired" and a.last_error
