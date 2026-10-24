from __future__ import annotations

from datetime import datetime, timezone

from app.services.extraction.providers import MockProvider, set_provider_override
from app.services.extraction.schema import ExtractedRequirement, ExtractionResult
from tests.fakes import JD_BODY, gmail_message


def globex_requirement(**kw) -> ExtractedRequirement:
    base = dict(client_name="Globex Corporation", job_title="Senior Python Developer", job_reference_id="GX-1042", required_skills=["Python", "Django", "PostgreSQL", "AWS"],
                preferred_skills=["Kubernetes", "Terraform"], minimum_experience=5, maximum_experience=8, city="Bangalore", country="India", work_mode="hybrid",
                recruiter_email="jane@staffing.com", recruiter_name="Jane Recruiter", salary_min=25, salary_max=35, salary_currency="INR", salary_period="year",
                evidence={"client_name": "Client: Globex Corporation"})
    base.update(kw)
    return ExtractedRequirement(**base)


def use_ai(*reqs: ExtractedRequirement, classification="new_requirement", error=None) -> MockProvider:
    p = MockProvider(canned=ExtractionResult(classification=classification, classification_confidence=0.9, requirements=list(reqs)), error=error)
    set_provider_override(p)
    return p


def jd_message(mid="m0000001", subject="Urgent requirement: Senior Python Developer", body=JD_BODY, **kw):
    kw.setdefault("ts", datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc))
    return gmail_message(mid, subject, body, **kw)


def sync(api, account_id, **body):
    r = api.post(f"/api/v1/email-accounts/{account_id}/sync", json=body or None)
    assert r.status_code == 200, r.text
    return r.json()
