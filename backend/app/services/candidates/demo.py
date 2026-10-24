"""DEMO DATA ONLY. Generates clearly marked dummy candidate profiles (3-5 per requirement) with a spread of match quality, so the
matching, pipeline and filters can be demonstrated. Every demo profile has source "demo", the tag "demo", the e-mail domain
demo-candidates.example.org and 90000xxxxx phone numbers, and can be removed with `python -m app.cli purge-demo-candidates --yes`.
"""
from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.candidates import Candidate, CandidateNote, CandidateSubmission
from app.models.enums import LifecycleStatus
from app.models.requirements import JobRequirement
from app.services.candidates import service as svc

DEMO_SOURCE, DEMO_TAG, DEMO_DOMAIN = "demo", "demo", "demo-candidates.example.org"

VOCAB = [
    "Python", "Django", "Flask", "FastAPI", "Java", "Spring Boot", "Microservices", "Kafka", "JavaScript", "TypeScript", "React", "Redux", "Node.js", "HTML5", "CSS3", "SQL", "PostgreSQL", "MySQL",
    "MongoDB", "Redis", "Elasticsearch", "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "Jenkins", "CI/CD", "Git", "Linux", "Ansible", "Prometheus", "Grafana", "Spark", "Airflow",
    "Hadoop", "Snowflake", "ETL", "Pandas", "NumPy", "Power BI", "Tableau", "Excel", "Machine Learning", "Deep Learning", "NLP", "LLMs", "PyTorch", "TensorFlow", "MLOps", "REST", "GraphQL",
    "Agile", "Scrum", "JIRA", "BRD", "FRD", "UAT", "SIT", "Stakeholder management", "Data modelling", "Data migration", "Data structures", "Algorithms", "OOP", "JUnit", "Selenium", "Code review",
    "SAP", "SAP MM", "SAP SD", "SAP PP", "SAP EWM", "SAP FI/CO", "S/4HANA", "Hypercare", "Cutover", "Procurement", "Inventory management", "Team leadership", "Mentoring", "Hiring", "Roadmapping",
]
UNRELATED_POOL = ["Photoshop", "Tally", "Customer support", "Digital marketing", "Content writing", "Manual testing", "Recruitment", "Payroll", "Sales", "AutoCAD"]
FIRST = ["Aarav", "Aditi", "Akash", "Ananya", "Arjun", "Bhavna", "Chirag", "Deepa", "Dev", "Divya", "Farhan", "Gauri", "Harish", "Ishita", "Jayant", "Kavya", "Kunal", "Lakshmi", "Manish", "Meera",
         "Naveen", "Neha", "Nikhil", "Pooja", "Pranav", "Priyanka", "Rahul", "Rashmi", "Rohit", "Sanjay", "Shreya", "Siddharth", "Sneha", "Suresh", "Tanvi", "Uday", "Varun", "Vidya", "Vikram", "Zoya"]
LAST = ["Agarwal", "Bhat", "Chopra", "Desai", "Fernandes", "Gupta", "Iyer", "Joshi", "Kapoor", "Khan", "Kulkarni", "Mehta", "Menon", "Mishra", "Nair", "Pandey", "Patel", "Rao", "Reddy", "Saxena",
        "Shah", "Sharma", "Singh", "Sinha", "Srinivasan", "Thakur", "Trivedi", "Varma", "Verma", "Yadav"]
COMPANIES = ["Infoweave", "Brightlogic", "Northwind Tech", "Bluefin Systems", "Quanta Labs", "Zenith Software", "Orbitrail", "Crestline IT", "Pixelforge", "Datacrest", "Nimbus Works", "Apex Digital",
             "Lumen Analytics", "Stackwise", "Kiteline", "Vertexa", "Clearpath Solutions", "Ironbridge Tech", "Sunrise Infotech", "Cobaltix"]
INDIA_CITIES = ["Bengaluru", "Pune", "Hyderabad", "Chennai", "Mumbai", "Delhi NCR", "Noida", "Gurugram", "Kolkata", "Ahmedabad", "Kochi", "Jaipur"]
US_CITIES = ["Detroit, MI", "Chicago, IL", "Dallas, TX", "Austin, TX", "Columbus, OH", "Atlanta, GA"]
NOTICE = ["Immediate", "15 days", "30 days", "30 days", "60 days", "90 days"]
STATUSES = ["new", "new", "new", "screening", "screening", "shortlisted", "shortlisted", "interviewing", "on_hold"]
TIERS = ["strong", "good", "medium", "weak", "near_miss"]


@dataclass
class DemoPlan:
    requirement: JobRequirement
    profiles: list[dict] = field(default_factory=list)


def _keywords(req: JobRequirement) -> list[str]:
    text = " ".join([*req.required_skills, *req.preferred_skills, req.job_title or ""])
    found: list[str] = []
    for term in VOCAB:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.I) and term not in found:
            found.append(term)
    if len(found) < 4:  # phrase-only skills: fall back to short leading words so the demo still works
        for s in req.required_skills:
            w = re.sub(r"[^A-Za-z0-9+#/. ]", "", s).strip().split()
            cand = " ".join(w[:2]).title() if w else ""
            if cand and cand not in found:
                found.append(cand)
    return found[:12]


def _city(req: JobRequirement) -> tuple[str | None, list[str]]:
    loc = (req.location or "").strip()
    is_us = bool(re.search(r"\b(US|USA|United States|MI|TX|CA|NY)\b", loc))
    pool = US_CITIES if is_us else INDIA_CITIES
    city = re.split(r"[,(]", loc)[0].strip() or None
    return city, pool


def plan_for(req: JobRequirement, rng: random.Random, used_names: set[str], used_phones: set[str], counter: list[int]) -> list[dict]:
    kws = _keywords(req)
    city, pool = _city(req)
    is_us = pool is US_CITIES
    lo = req.minimum_experience if req.minimum_experience is not None else 5.0
    hi = req.maximum_experience if req.maximum_experience is not None else lo + 4
    n = rng.choice([3, 4, 4, 5, 5])
    tiers = TIERS[:n] if n < 5 else TIERS
    out: list[dict] = []
    for tier in tiers:
        while True:
            first, last = rng.choice(FIRST), rng.choice(LAST)
            if f"{first} {last}" not in used_names:
                used_names.add(f"{first} {last}")
                break
        counter[0] += 1
        phone = f"90000{rng.randint(10000, 99999)}"
        while phone in used_phones:
            phone = f"90000{rng.randint(10000, 99999)}"
        used_phones.add(phone)
        if tier == "strong":
            skills, exp, here, relocate = list(kws), rng.uniform(lo + 0.3, max(lo + 0.5, (lo + hi) / 2)), True, None
        elif tier == "good":
            k = max(2, round(len(kws) * 0.75))
            skills, exp, here, relocate = rng.sample(kws, min(k, len(kws))) + rng.sample(VOCAB, 2), rng.uniform(lo, hi), rng.random() < 0.6, True
        elif tier == "medium":
            k = max(2, round(len(kws) * 0.5))
            skills, exp, here, relocate = rng.sample(kws, min(k, len(kws))) + rng.sample(VOCAB, 3), rng.uniform(max(0, lo - 1.5), hi + 1.5), False, True
        elif tier == "near_miss":  # right skills, wrong seniority: shows how experience fit changes the score
            skills, exp, here, relocate = list(kws), (hi + rng.uniform(4, 6)) if lo >= 3 else (lo + rng.uniform(5, 7)), rng.random() < 0.5, False
        else:  # weak
            k = max(1, round(len(kws) * 0.2))
            skills, exp, here, relocate = rng.sample(kws, min(k, len(kws))) + rng.sample(UNRELATED_POOL, 3), rng.uniform(0.5, lo + 4), False, False
        exp = round(max(0.0, min(exp, 40.0)), 1)
        where = city if (here and city) else rng.choice([c for c in pool if c != city])
        title = req.job_title if tier in ("strong", "good", "near_miss") else (req.job_title if tier == "medium" else rng.choice(["Software Tester", "Support Engineer", "Business Executive", "Associate Consultant"]))
        if tier == "good" and rng.random() < 0.5 and req.job_title:
            title = f"Senior {req.job_title}" if exp > 5 and not req.job_title.lower().startswith("senior") else req.job_title
        base = (110000 if is_us else 350000) + exp * (14000 if is_us else 190000)
        cur = round(base * rng.uniform(0.85, 1.15), -3)
        out.append({
            "first_name": first, "last_name": last, "email": f"{first}.{last}{counter[0]}@{DEMO_DOMAIN}".lower(), "phone": phone, "current_title": title, "current_company": rng.choice(COMPANIES),
            "total_experience": exp, "relevant_experience": round(max(0.0, exp - rng.uniform(0, 1.5)), 1), "skills": list(dict.fromkeys(skills)), "current_location": where,
            "preferred_locations": [c for c in rng.sample(pool, 2) if c != where][:2] + ([city] if relocate and city else []), "willing_to_relocate": relocate, "notice_period": rng.choice(NOTICE),
            "current_ctc": cur, "expected_ctc": round(cur * rng.uniform(1.15, 1.4), -3), "currency": "USD" if is_us else "INR", "education": rng.choice(["B.Tech", "B.E.", "MCA", "M.Tech", "B.Sc", "MBA"]),
            "work_authorization": "US work authorization" if is_us else None, "summary": f"Demo profile (dummy data) created to demonstrate matching for {req.job_title}.",
            "source": DEMO_SOURCE, "status": rng.choice(STATUSES), "rating": rng.choice([None, 3, 3, 4, 4, 5]), "tags": [DEMO_TAG] + (["referral"] if rng.random() < 0.2 else []), "_tier": tier,
        })
    return out


def build_plans(db: Session, org_id: uuid.UUID) -> list[DemoPlan]:
    used_names: set[str] = set()
    used_phones: set[str] = set()  # uniqueness within this run only: the generated set must not depend on database contents, so re-runs are idempotent
    reqs = list(db.scalars(select(JobRequirement).options(selectinload(JobRequirement.skills)).where(
        JobRequirement.organization_id == org_id, JobRequirement.lifecycle_status == LifecycleStatus.ACTIVE).order_by(JobRequirement.client_name, JobRequirement.job_title)))
    counter = [0]
    plans = []
    for req in reqs:
        rng = random.Random(str(req.id))  # deterministic: re-running yields the same people (and is then skipped as duplicates)
        plans.append(DemoPlan(req, plan_for(req, rng, used_names, used_phones, counter)))
    return plans


def seed(db: Session, org_id: uuid.UUID, user_id: uuid.UUID | None, *, apply: bool) -> dict:
    plans = build_plans(db, org_id)
    created = skipped = pipelines = 0
    for i, plan in enumerate(plans):
        for p in plan.profiles:
            tier = p.pop("_tier")
            if svc.find_duplicates(db, org_id, email=p["email"], phone=p["phone"]):
                skipped += 1
                continue
            if not apply:
                created += 1
                continue
            c = svc.create_candidate(db, org_id, p, user_id=user_id, check_duplicates=False)
            created += 1
            if tier == "strong" and i % 5 != 4:  # most jobs get one candidate already in the pipeline, at varied stages
                stage = ["shortlisted", "submitted", "interview", "offered", "shortlisted", "submitted"][i % 6]
                db.add(CandidateSubmission(organization_id=org_id, candidate_id=c.id, requirement_id=plan.requirement.id, stage=stage, notes="Demo pipeline entry", created_by=user_id))
                svc.add_note(db, c, f"Demo: added to pipeline for {plan.requirement.job_title} as {stage}", user_id=user_id, kind="system")
                pipelines += 1
    return {"requirements": len(plans), "created": created, "skipped_existing": skipped, "pipeline_entries": pipelines}


def purge(db: Session, org_id: uuid.UUID | None = None, *, apply: bool) -> int:
    q = select(Candidate.id).where(Candidate.source == DEMO_SOURCE, Candidate.email_normalized.like(f"%@{DEMO_DOMAIN}"))
    if org_id:
        q = q.where(Candidate.organization_id == org_id)
    ids = [i for (i,) in db.execute(q)]
    if apply and ids:
        db.execute(delete(Candidate).where(Candidate.id.in_(ids)))  # skills, notes and pipeline entries cascade
    return len(ids)
