"""DEVELOPMENT / E2E ONLY. Starts the real FastAPI app on an isolated SQLite database with fake Gmail, fake Google OAuth and a rule-based
extraction provider, and seeds it by running the real sync -> extract -> dedup pipeline. Never used by the normal application.

    python -m tests.e2e_server            # http://localhost:8001, login owner@example.com / Str0ngPassword!23
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

PORT = int(os.environ.get("E2E_PORT", "8001"))
TMP = tempfile.mkdtemp(prefix="rd-e2e-")
from cryptography.fernet import Fernet  # noqa: E402

os.environ.update({
    "APP_ENV": "test", "DATABASE_URL": f"sqlite:///{TMP}/e2e.db", "DATABASE_SCHEMA": "", "REDIS_URL": "", "CELERY_EAGER": "true", "MANUAL_SYNC_COOLDOWN_SECONDS": "0",
    "SECRET_KEY": "e2e-secret-key-e2e-secret-key-e2e-secret-key", "ENCRYPTION_KEY": Fernet.generate_key().decode(), "GOOGLE_CLIENT_ID": "e2e", "GOOGLE_CLIENT_SECRET": "e2e",
    "AI_PROVIDER": "mock", "STORAGE_PATH": f"{TMP}/storage", "FRONTEND_URL": f"http://localhost:{os.environ.get('E2E_FRONTEND_PORT', '5173')}",
    "GOOGLE_REDIRECT_URI": f"http://localhost:{PORT}/api/v1/email-accounts/oauth/callback", "CORS_ORIGINS": "http://localhost:5173,http://localhost:4173",
})

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.db.session import session_scope  # noqa: E402
from app.models.email import EmailAccount, EmailSyncState  # noqa: E402
from app.services.extraction.providers import AIProvider, set_provider_override  # noqa: E402
from app.services.extraction.schema import ExtractedRequirement, ExtractionResult  # noqa: E402
from app.services.gmail import accounts as acct_svc  # noqa: E402
from tests.fakes import FakeMailbox, FakeOAuth, gmail_message  # noqa: E402

PASSWORD = "Str0ngPassword!23"


class RuleBasedProvider(AIProvider):
    """Deterministic stand-in for an LLM: reads 'Label: value' lines. DEVELOPMENT ONLY."""

    name, model = "dev-rules", "dev-rules-1"

    def extract(self, *, subject, sender, body, attachments, received_at):
        from app.services.classification.heuristics import classify_email, extract_hints

        text = body + "\n" + "\n".join(t for _, t in attachments)
        cls = classify_email(subject, text, sender)
        if cls.category.value not in ("new_requirement", "updated_requirement"):
            return ExtractionResult(classification=cls.category.value, classification_confidence=cls.confidence)
        g = lambda label: (m.group(1).strip() if (m := re.search(rf"^{label}:\s*(.+)$", text, re.M | re.I)) else None)  # noqa: E731
        skills = [s.strip() for s in (g("Required Skills") or "").split(",") if s.strip()]
        pref = [s.strip() for s in (g("Good to have") or "").split(",") if s.strip()]
        hints = extract_hints(text)
        loc = g("Location") or ""
        city = re.split(r"[,(]", loc)[0].strip() or None
        sal = re.search(r"(\d+)\s*-\s*(\d+)\s*LPA", g("Salary") or "")
        r = ExtractedRequirement(client_name=g("Client"), job_title=g("Job Title"), job_reference_id=hints.get("job_reference_id"), required_skills=skills, preferred_skills=pref,
                                 minimum_experience=hints.get("minimum_experience"), maximum_experience=hints.get("maximum_experience"), city=city,
                                 country="India" if "india" in loc.lower() else None, work_mode=hints.get("work_mode", "unknown"), recruiter_email=(hints.get("emails") or [None])[0],
                                 salary_min=float(sal.group(1)) if sal else None, salary_max=float(sal.group(2)) if sal else None, salary_currency="INR" if sal else None,
                                 salary_period="year" if sal else None, job_description=body[:1500])
        return ExtractionResult(classification=cls.category.value, classification_confidence=cls.confidence, requirements=[r])

    def json_completion(self, system, user):
        """Rule-based profile 'extraction' for the e2e/demo server: reads lines like 'Title at Company (Jan 2022 - Present). Description'."""
        body = user.split("<profile>", 1)[-1].split("</profile>", 1)[0]
        positions = []
        for m in re.finditer(r"^(?P<title>.+?) at (?P<company>[^(\n]+?) \((?P<s>[A-Za-z]{3} \d{4}) - (?P<e>[A-Za-z]{3} \d{4}|Present)\)\.?[ \t]*(?P<d>.*)$", body, re.M):
            positions.append({"company": m["company"].strip(), "title": m["title"].strip(), "start": m["s"], "end": m["e"], "description": m["d"].strip() or None, "skills_used": []})
        line = lambda label: (m.group(1).strip() if (m := re.search(rf"^{label}:\s*(.+)$", body, re.M | re.I)) else "")
        skills = [s.strip() for s in line("Skills").split(",") if s.strip()]
        edu = line("Education").split(",")
        cur = positions[0] if positions else {}
        return {"headline": f"{cur.get('title', '')} at {cur.get('company', '')}".strip(), "ai_summary": "Demo summary generated by the rule-based stand-in model.", "current_title": cur.get("title"),
                "current_company": cur.get("company"), "seniority": "senior", "industries": [], "skills": skills, "top_skills": skills[:8], "positions": positions,
                "education": [{"school": edu[-1].strip(), "degree": edu[0].strip()}] if len(edu) > 1 else [], "certifications": [c.strip() for c in line("Certifications").split(",") if c.strip()],
                "projects": [], "languages": [], "honors": [], "links": [], "career_highlights": [], "screening_questions": ["Walk me through your most recent project."]}

    def health_check(self):
        return {"status": "ok", "detail": "dev provider"}


def jd(client, title, ref, skills, loc="Bangalore, India (Hybrid)", exp="5-8", extra=""):
    ref_line = f"Job ID: {ref}\n" if ref else ""
    return (f"Hi,\n\nWe have an urgent requirement.\n\nClient: {client}\nJob Title: {title}\n{ref_line}Location: {loc}\nExperience: {exp} years\n"
            f"Required Skills: {skills}\nGood to have: Docker\nSalary: 20 - 30 LPA\nSend your updated resume to jane@staffing.com\n{extra}\nRegards,\nJane")


def seed() -> None:
    from app.services.auth.service import create_user_with_org
    from app.core.security import get_cipher
    from app.db.types import utcnow
    from app.tasks.runner import sync_account_impl
    from app.services import jobs

    now = datetime.now(timezone.utc)
    boxes: dict[str, FakeMailbox] = {}

    class Router:
        def __call__(self, token):
            return boxes.setdefault(token, FakeMailbox())

    acct_svc.set_factories(gateway=Router(), oauth=lambda s: DevOAuth())
    set_provider_override(RuleBasedProvider())
    cipher = get_cipher()
    with session_scope() as db:
        user, org = create_user_with_org(db, email="owner@example.com", password=PASSWORD, display_name="Demo Owner", org_name="Demo Recruiting")
        from sqlalchemy import select
        from app.models.auth import OrganizationMembership

        viewer, vorg = create_user_with_org(db, email="viewer@example.com", password=PASSWORD, display_name="Read Only", org_name="Viewer Tmp")
        m = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == viewer.id))
        m.organization_id, m.role = org.id, "viewer"
        ids = []
        for email in ("work@gmail.com", "personal@gmail.com"):
            a = EmailAccount(organization_id=org.id, connected_by_user_id=user.id, provider="gmail", provider_account_id=f"sub-{email}", email_address=email,
                             encrypted_access_token=cipher.encrypt(f"access-{email}"), encrypted_refresh_token=cipher.encrypt("refresh"), token_expiry=utcnow() + timedelta(hours=1),
                             scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send", "openid", "email"], is_default_sender=email.startswith("work"))
            db.add(a)
            db.flush()
            db.add(EmailSyncState(email_account_id=a.id, cursor_metadata={}))
            ids.append((email, a.id))
    work, personal = boxes.setdefault("access-work@gmail.com", FakeMailbox()), boxes.setdefault("access-personal@gmail.com", FakeMailbox())
    t = lambda d: now - timedelta(days=d)  # noqa: E731
    python_jd = jd("Globex Corporation", "Senior Python Developer", "GX-1042", "Python, Django, PostgreSQL, AWS")
    work.add(gmail_message("a0000001", "Urgent requirement: Senior Python Developer", python_jd, ts=t(2)))
    personal.add(gmail_message("b0000001", "Urgent requirement: Senior Python Developer", python_jd, ts=t(2), sender="Jane Recruiter <jane@staffing.com>"))  # cross-account copy
    work.add(gmail_message("a0000002", "Requirement - Java Architect", jd("Initech", "Java Architect", "IN-77", "Java, Spring Boot, Kafka, Microservices", "Pune, India (Onsite)", "9-12"), ts=t(3), sender="Bob <bob@initech-hr.com>"))
    work.add(gmail_message("a0000003", "Hot requirement: Data Engineer", jd("Hooli", "Data Engineer", None, "Python, Spark, SQL, Airflow", "Remote, India", "4-7"), ts=t(5)))
    personal.add(gmail_message("b0000002", "Fwd: Data Engineer opening", jd("Hooli", "Data Engineer", None, "Python, Spark, SQL, Airflow", "Remote, India", "4-7", "Forwarded from partner"), ts=t(4), sender="Priya <priya@partner.com>"))
    personal.add(gmail_message("b0000003", "Opening: DevOps Engineer", jd("Globex Corporation", "DevOps Engineer", "GX-2001", "AWS, Terraform, Kubernetes, Jenkins", "Hyderabad, India (Hybrid)", "6-9"), ts=t(7), sender="Sam <sam@talent.io>"))
    personal.add(gmail_message("b0000004", "Weekly newsletter", "Unsubscribe from our newsletter. 50% off sale this week!", sender="Shop <no-reply@shop.com>", ts=t(1)))
    personal.add(gmail_message("b0000005", "Java Architect - Mumbai", jd("Initech", "Java Architect", None, "Java, Spring Boot, Kafka, Microservices", "Mumbai, India (Onsite)", "9-12"), ts=t(1), sender="Dan <dan@other-agency.com>"))
    work.add(gmail_message("a0000004", "Lunch tomorrow?", "Hey, are we still on for lunch tomorrow? Let me know.", sender="Friend <friend@example.com>", ts=t(1)))
    with session_scope() as db:
        for _, aid in ids:
            j = jobs.create_job(db, org_id=org.id, job_type="sync", account_id=aid, payload={"mode": "full"}, user_id=user.id)
            jid = str(j.id)
            db.commit()
            sync_account_impl(jid)


class DevOAuth(FakeOAuth):
    """Fake consent screen: 'Google' immediately redirects back to our callback with a valid code."""

    def __init__(self):
        super().__init__(email="newhire@gmail.com", sub="sub-newhire")

    def authorization_url(self, state, code_challenge, scopes, login_hint=None):
        return f"http://localhost:{PORT}/api/v1/email-accounts/oauth/callback?state={state}&code=good-code"


def main() -> None:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")
    seed()
    import uvicorn

    print(f"E2E server ready on http://localhost:{PORT}  (login owner@example.com / {PASSWORD})", flush=True)
    try:
        uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, log_level="warning")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
