from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

Status = Literal["new", "screening", "shortlisted", "interviewing", "offered", "hired", "rejected", "on_hold", "not_interested"]
Stage = Literal["shortlisted", "submitted", "interview", "offered", "joined", "rejected", "withdrawn"]


class CandidateBase(BaseModel):
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    current_title: str | None = Field(default=None, max_length=200)
    current_company: str | None = Field(default=None, max_length=200)
    total_experience: float | None = Field(default=None, ge=0, le=60)
    relevant_experience: float | None = Field(default=None, ge=0, le=60)
    current_location: str | None = Field(default=None, max_length=200)
    preferred_locations: list[str] | None = Field(default=None, max_length=30)
    willing_to_relocate: bool | None = None
    notice_period: str | None = Field(default=None, max_length=100)
    current_ctc: float | None = Field(default=None, ge=0)
    expected_ctc: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    education: str | None = Field(default=None, max_length=500)
    certifications: list[str] | None = Field(default=None, max_length=30)
    work_authorization: str | None = Field(default=None, max_length=100)
    linkedin_url: str | None = Field(default=None, max_length=500)
    resume_url: str | None = Field(default=None, max_length=500)
    summary: str | None = Field(default=None, max_length=5000)
    source: str | None = Field(default=None, max_length=60)
    status: Status | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] | None = Field(default=None, max_length=30)
    skills: list[str] | None = Field(default=None, max_length=80)

    @field_validator("*", mode="before")
    @classmethod
    def _blank(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


class CandidateCreate(CandidateBase):
    """Name, email and phone are mandatory; every other field is optional."""

    first_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=50)
    initial_note: str | None = Field(default=None, max_length=5000)


class CandidatePatch(CandidateBase):
    pass


class CandidateOut(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str | None
    full_name: str
    email: str | None
    phone: str | None
    current_title: str | None
    current_company: str | None
    total_experience: float | None
    relevant_experience: float | None
    current_location: str | None
    preferred_locations: list[str]
    willing_to_relocate: bool | None
    notice_period: str | None
    current_ctc: float | None
    expected_ctc: float | None
    currency: str | None
    education: str | None
    certifications: list[str]
    work_authorization: str | None
    linkedin_url: str | None
    resume_url: str | None
    summary: str | None
    source: str
    status: str
    rating: int | None
    tags: list[str]
    skills: list[str]
    is_archived: bool
    last_contacted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    pipeline_count: int = 0


class BulkIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    action: Literal["set_status", "add_tag", "remove_tag", "archive", "restore", "mark_contacted"]
    value: str | None = Field(default=None, max_length=60)


class ExportIn(BaseModel):
    ids: list[uuid.UUID] | None = Field(default=None, max_length=5000)
    filters: dict | None = None


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class NoteOut(BaseModel):
    id: uuid.UUID
    kind: str
    body: str
    author: str | None
    created_at: datetime


class SubmissionIn(BaseModel):
    requirement_id: uuid.UUID
    stage: Stage = "shortlisted"
    notes: str | None = Field(default=None, max_length=1000)


class SubmissionPatch(BaseModel):
    stage: Stage | None = None
    notes: str | None = Field(default=None, max_length=1000)


class SubmissionOut(BaseModel):
    id: uuid.UUID
    stage: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    candidate_id: uuid.UUID
    candidate_name: str
    candidate_title: str | None
    requirement_id: uuid.UUID
    requirement_title: str | None
    requirement_client: str | None


class MatchOut(BaseModel):
    score: int
    matched_skills: list[str]
    missing_skills: list[str]
    reasons: list[str]
    stage: str | None = None
    ai_profile_used: bool = False
    ai_only_matches: list[str] = []


class ApplyIn(BaseModel):
    fields: list[str] = Field(min_length=1, max_length=10)

