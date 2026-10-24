"""Validated structured output of an extraction run."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Classification = Literal[
    "new_requirement", "updated_requirement", "recruiter_followup", "candidate_submission",
    "interview_scheduling", "job_closure", "unrelated", "needs_review",
]


class ExtractedRequirement(BaseModel):
    client_name: str | None = None
    job_title: str | None = None
    job_reference_id: str | None = None
    number_of_openings: int | None = Field(default=None, ge=1, le=10000)
    job_description: str | None = None
    department: str | None = None

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    domain_experience: str | None = None

    minimum_experience: float | None = Field(default=None, ge=0, le=60)
    maximum_experience: float | None = Field(default=None, ge=0, le=60)
    seniority: str | None = None
    education: str | None = None

    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = None
    salary_period: Literal["hour", "day", "month", "year"] | None = None
    employment_type: str | None = None
    notice_period: str | None = None

    city: str | None = None
    state: str | None = None
    country: str | None = None
    work_mode: Literal["remote", "hybrid", "onsite", "unknown"] = "unknown"
    relocation: str | None = None
    travel: str | None = None

    recruiter_name: str | None = None
    recruiter_email: str | None = None
    recruiter_phone: str | None = None
    client_contact: str | None = None
    submission_email: str | None = None
    submission_instructions: str | None = None
    required_documents: list[str] = Field(default_factory=list)

    evidence: dict[str, str] = Field(default_factory=dict, description="field -> short verbatim snippet from the source")
    field_confidence: dict[str, float] = Field(default_factory=dict)

    @field_validator("salary_currency")
    @classmethod
    def _currency(cls, v: str | None):
        if v is None:
            return None
        v = v.strip().upper()
        return v if re.fullmatch(r"[A-Z]{3}|[$€£₹]", v) else None

    @field_validator("work_mode", mode="before")
    @classmethod
    def _wm(cls, v):
        if isinstance(v, str):
            v = v.strip().lower().replace("-", "").replace("_", "")
            return {"onsite": "onsite", "onsite ": "onsite", "remote": "remote", "hybrid": "hybrid"}.get(v, "unknown")
        return "unknown"

    @field_validator("required_skills", "preferred_skills", "certifications", "required_documents", mode="before")
    @classmethod
    def _list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [s.strip() for s in re.split(r"[,;\n]", v) if s.strip()]
        return [str(x) for x in v if x]

    @field_validator("*", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("evidence", mode="before")
    @classmethod
    def _evidence(cls, v):
        """Models often emit null/non-string snippets for fields they could not find; unknown means 'no evidence'."""
        if not isinstance(v, dict):
            return {}
        return {str(k): s.strip() for k, s in v.items() if isinstance(s, str) and s.strip()}

    @field_validator("field_confidence", mode="before")
    @classmethod
    def _field_conf(cls, v):
        if not isinstance(v, dict):
            return {}
        out = {}
        for k, x in v.items():
            try:
                f = float(x)
            except (TypeError, ValueError):
                continue
            out[str(k)] = min(1.0, max(0.0, f))
        return out

    @field_validator("minimum_experience", "maximum_experience", "salary_min", "salary_max", mode="before")
    @classmethod
    def _number(cls, v):
        """Accept '5', '5+ years', '1,20,000' as numbers; anything unparseable becomes null instead of failing the whole email."""
        if v is None or isinstance(v, (int, float)) and not isinstance(v, bool):
            return v
        if isinstance(v, str):
            m = re.search(r"\d[\d,]*(?:\.\d+)?", v)
            return float(m.group(0).replace(",", "")) if m else None
        return None

    @field_validator("number_of_openings", mode="before")
    @classmethod
    def _openings(cls, v):
        if isinstance(v, str):
            m = re.search(r"\d+", v)
            return int(m.group(0)) if m else None
        if isinstance(v, float):
            return int(v)
        return v

    @field_validator("salary_period", mode="before")
    @classmethod
    def _period(cls, v):
        if isinstance(v, str):
            v = v.strip().lower().replace("per ", "").replace("annum", "year").replace("annual", "year")
            return {"hour": "hour", "hourly": "hour", "day": "day", "daily": "day", "month": "month", "year": "year", "yr": "year", "pa": "year"}.get(v, None)
        return None

    def has_core_identity(self) -> bool:
        return bool(self.job_title or self.job_reference_id)


class ExtractionResult(BaseModel):
    classification: Classification = "needs_review"
    classification_confidence: float = Field(default=0.5, ge=0, le=1)
    requirements: list[ExtractedRequirement] = Field(default_factory=list, max_length=25)
    notes: str | None = None
