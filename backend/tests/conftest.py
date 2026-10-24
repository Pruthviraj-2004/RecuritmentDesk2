"""Test harness: isolated SQLite DB built by the real Alembic migration, fake Gmail/OAuth/AI. No network, no credentials."""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid

_TMP = tempfile.mkdtemp(prefix="rd-tests-")
os.environ.update({
    "APP_ENV": "test", "DATABASE_URL": f"sqlite:///{_TMP}/test.db", "DATABASE_SCHEMA": "", "REDIS_URL": "", "CELERY_EAGER": "true",
    "SECRET_KEY": "test-secret-key-test-secret-key-test-secret",
    "GOOGLE_CLIENT_ID": "test-client-id", "GOOGLE_CLIENT_SECRET": "test-client-secret", "AI_PROVIDER": "none", "AI_API_KEY": "",
    "STORAGE_PATH": f"{_TMP}/storage", "INITIAL_ADMIN_EMAIL": "", "INITIAL_ADMIN_PASSWORD": "", "FRONTEND_URL": "http://localhost:5173",
})

from cryptography.fernet import Fernet as _F  # noqa: E402

os.environ["ENCRYPTION_KEY"] = _F.generate_key().decode()

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import rate_limiter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_engine, reset_engine, session_factory  # noqa: E402
from tests.fakes import FakeMailbox, FakeOAuth  # noqa: E402

get_settings.cache_clear()

PASSWORD = "Str0ngPassword!23"


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    reset_engine()
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")
    yield
    reset_engine()
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean(_migrate):
    rate_limiter.reset()
    eng = get_engine()
    with eng.begin() as c:
        c.execute(text("PRAGMA foreign_keys=OFF"))
        for t in reversed(Base.metadata.sorted_tables):
            c.execute(text(f"DELETE FROM {t.name}"))
        c.execute(text("PRAGMA foreign_keys=ON"))
    from app.services.extraction.providers import set_provider_override
    from app.services.gmail import accounts as acct_svc

    set_provider_override(None)
    acct_svc.reset_factories()
    yield
    set_provider_override(None)
    acct_svc.reset_factories()


class FreshSession(Session):
    """Test session that ends its (read) transaction before each query so it always sees committed API/worker writes."""

    def _fresh(self):
        if not (self.new or self.dirty or self.deleted):
            self.commit()

    def execute(self, *a, **k):
        self._fresh()
        return super().execute(*a, **k)

    def get(self, *a, **k):
        self._fresh()
        return super().get(*a, **k)

    def scalar(self, *a, **k):
        self._fresh()
        return super().scalar(*a, **k)

    def scalars(self, *a, **k):
        self._fresh()
        return super().scalars(*a, **k)


@pytest.fixture
def db():
    get_engine()
    s = FreshSession(bind=get_engine(), expire_on_commit=True, autoflush=False)
    yield s
    s.close()


class MailboxRouter:
    """Maps each account (by its fake access token) to its own in-memory mailbox."""

    def __init__(self):
        self.boxes: dict[str, FakeMailbox] = {}

    def __call__(self, token: str):
        return self.boxes.setdefault(token, FakeMailbox())

    def for_email(self, email: str) -> FakeMailbox:
        return self.boxes.setdefault(f"access-{email}", FakeMailbox())


@pytest.fixture
def mailbox():
    from app.services.gmail import accounts as acct_svc

    router = MailboxRouter()
    acct_svc.set_factories(gateway=router)
    return router


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def make_user(db, email="owner@example.com", password=PASSWORD, org="Acme Recruiting"):
    from app.services.auth.service import create_user_with_org

    user, org_ = create_user_with_org(db, email=email, password=password, display_name="Owner", org_name=org)
    db.commit()
    return user, org_


@pytest.fixture
def owner(db):
    return make_user(db)


class Api:
    """Thin authenticated client that sends the CSRF header automatically."""

    def __init__(self, client: TestClient, csrf: str | None):
        self.c, self.csrf = client, csrf

    def _h(self, extra=None):
        h = {"X-CSRF-Token": self.csrf} if self.csrf else {}
        h.update(extra or {})
        return h

    def get(self, url, **kw):
        return self.c.get(url, headers=self._h(kw.pop("headers", None)), **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def patch(self, url, json=None, **kw):
        return self.c.patch(url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def put(self, url, json=None, **kw):
        return self.c.put(url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self._h(kw.pop("headers", None)), **kw)


def login(client: TestClient, email="owner@example.com", password=PASSWORD) -> Api:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return Api(client, r.json()["csrf_token"])


@pytest.fixture
def api(client, owner) -> Api:
    return login(client)


@pytest.fixture
def connected_account(db, owner):
    """Factory: creates a connected Gmail account (encrypted tokens, read+send scopes) and returns the EmailAccount."""
    return lambda email="acct1@gmail.com", scopes=None, default=False: _make_account(db, owner[1].id, owner[0].id, email, scopes, default)


def _make_account(db, org_id, user_id, email, scopes, default):
    from datetime import timedelta

    from app.core.security import get_cipher
    from app.db.types import utcnow
    from app.models.email import EmailAccount, EmailSyncState

    cipher = get_cipher()
    token = f"access-{email}"
    a = EmailAccount(organization_id=org_id, connected_by_user_id=user_id, provider="gmail", provider_account_id=f"sub-{email}", email_address=email,
                     encrypted_access_token=cipher.encrypt(token), encrypted_refresh_token=cipher.encrypt(f"refresh-{email}"),
                     token_expiry=utcnow() + timedelta(hours=1), connection_status="connected", import_days=30, is_default_sender=default,
                     scopes=scopes or ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send", "openid", "email"])
    db.add(a)
    db.flush()
    db.add(EmailSyncState(email_account_id=a.id, cursor_metadata={}))
    db.commit()
    return a
