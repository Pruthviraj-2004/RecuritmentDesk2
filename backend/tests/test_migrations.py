"""Migrations are exercised against a fresh database in a subprocess (upgrade, drift check, downgrade, re-upgrade)."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": db_url, "DATABASE_SCHEMA": ""}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)


def test_migrations_upgrade_check_downgrade_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        url = f"sqlite:///{d}/m.db"
        up = _alembic(url, "upgrade", "head")
        assert up.returncode == 0, up.stderr
        check = _alembic(url, "check")  # models and migrations must not drift apart
        assert check.returncode == 0, check.stderr + check.stdout
        assert _alembic(url, "downgrade", "base").returncode == 0
        assert _alembic(url, "upgrade", "head").returncode == 0


def test_all_expected_tables_exist():
    from sqlalchemy import inspect

    from app.db.session import get_engine

    names = set(inspect(get_engine()).get_table_names())
    expected = {"users", "organizations", "organization_memberships", "email_accounts", "email_sync_states", "email_messages", "email_attachments",
                "job_requirements", "requirement_skills", "requirement_sources", "requirement_versions", "duplicate_candidates", "extraction_runs",
                "processing_jobs", "export_jobs", "email_deliveries", "audit_logs", "user_sessions", "oauth_states", "notifications", "app_settings"}
    assert expected <= names


def test_database_enforces_critical_uniqueness(db, connected_account):
    import pytest
    from sqlalchemy.exc import IntegrityError

    from app.models.email import EmailMessage

    a = connected_account("u@gmail.com")
    for _ in range(2):
        db.add(EmailMessage(organization_id=a.organization_id, email_account_id=a.id, gmail_message_id="same-id", recipients=[], labels=[], source_metadata={}))
        if _ == 0:
            db.commit()
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # a duplicate pair can only be stored once regardless of order
    from app.models.requirements import DuplicateCandidate
    from app.services.requirements.service import create_requirement

    r1 = create_requirement(db, a.organization_id, {"job_title": "A", "client_name": "X"}, user_id=None)
    r2 = create_requirement(db, a.organization_id, {"job_title": "A2", "client_name": "X"}, user_id=None)
    db.commit()
    db.add(DuplicateCandidate(organization_id=a.organization_id, requirement_id_a=r1.id, requirement_id_b=r2.id, matching_score=0.8))
    db.commit()
    db.add(DuplicateCandidate(organization_id=a.organization_id, requirement_id_a=r1.id, requirement_id_b=r2.id, matching_score=0.8))
    with pytest.raises(IntegrityError):
        db.commit()
