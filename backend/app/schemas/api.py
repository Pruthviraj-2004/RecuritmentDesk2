"""Typed request/response schemas for /api/v1."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------- auth
class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


class UserOut(ORM):
    id: uuid.UUID
    email: str
    display_name: str


class MeOut(BaseModel):
    user: UserOut
    organization: dict
    role: str
    csrf_token: str


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(max_length=200)


class SessionOut(ORM):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime | None
    user_agent: str | None
    ip_address: str | None
    current: bool = False


# ---------------------------------------------------------------- accounts
class AccountOut(ORM):
    id: uuid.UUID
    email_address: str
    display_name: str | None
    provider: str
    connection_status: str
    sync_enabled: bool
    import_days: int
    extra_query: str | None
    is_default_sender: bool
    scopes: list[str]
    can_send: bool
    can_read: bool
    last_synced_at: datetime | None
    last_error: str | None
    created_at: datetime
    stats: dict[str, Any] = {}
    masked_email: str = ""


class ConnectIn(BaseModel):
    enable_send: bool = True
    login_hint: str | None = Field(default=None, max_length=320)


class ConnectOut(BaseModel):
    authorization_url: str


class AccountPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    sync_enabled: bool | None = None
    import_days: int | None = Field(default=None, ge=1, le=365)
    extra_query: str | None = Field(default=None, max_length=500)
    is_default_sender: bool | None = None


class SyncRequest(BaseModel):
    mode: Literal["auto", "full"] = "auto"
    import_days: int | None = Field(default=None, ge=1, le=365)


# ---------------------------------------------------------------- emails
class AttachmentOut(ORM):
    id: uuid.UUID
    filename: str
    content_type: str | None
    size_bytes: int
    extraction_status: str
    error_summary: str | None


class EmailListItem(ORM):
    id: uuid.UUID
    email_account_id: uuid.UUID
    account_email: str | None = None
    sender: str | None
    subject: str | None
    received_at: datetime | None
    classification: str | None
    classification_confidence: float | None
    processing_status: str
    error_summary: str | None
    attachment_count: int = 0
    requirement_ids: list[uuid.UUID] = []
    is_duplicate: bool = False


class EmailDetail(EmailListItem):
    body_text: str | None
    snippet: str | None
    attachments: list[AttachmentOut] = []
    gmail_url: str | None = None
    extraction_runs: list[dict] = []
    processing_attempts: int = 0


class ReclassifyIn(BaseModel):
    classification: str


class LinkRequirementIn(BaseModel):
    requirement_id: uuid.UUID


# ---------------------------------------------------------------- requirements
class RequirementBase(BaseModel):
    client_name: str | None = Field(default=None, max_length=300)
    job_title: str | None = Field(default=None, max_length=300)
    job_reference_id: str | None = Field(default=None, max_length=100)
    job_description: str | None = Field(default=None, max_length=60000)
    department: str | None = Field(default=None, max_length=200)
    seniority: str | None = Field(default=None, max_length=50)
    minimum_experience: float | None = Field(default=None, ge=0, le=60)
    maximum_experience: float | None = Field(default=None, ge=0, le=60)
    education: str | None = Field(default=None, max_length=500)
    domain_experience: str | None = Field(default=None, max_length=500)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=8)
    salary_period: Literal["hour", "day", "month", "year"] | None = None
    employment_type: str | None = Field(default=None, max_length=50)
    notice_period: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    work_mode: Literal["remote", "hybrid", "onsite", "unknown"] | None = None
    relocation: str | None = Field(default=None, max_length=200)
    travel: str | None = Field(default=None, max_length=200)
    recruiter_name: str | None = Field(default=None, max_length=200)
    recruiter_email: EmailStr | None = None
    recruiter_phone: str | None = Field(default=None, max_length=50)
    client_contact: str | None = Field(default=None, max_length=500)
    submission_email: EmailStr | None = None
    submission_instructions: str | None = Field(default=None, max_length=5000)
    number_of_openings: int | None = Field(default=None, ge=1, le=10000)
    certifications: list[str] | None = None
    required_documents: list[str] | None = None
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _blank(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


class RequirementCreate(RequirementBase):
    received_at: datetime | None = None
    from_email_id: uuid.UUID | None = None


class RequirementPatch(RequirementBase):
    pass


class RequirementOut(ORM):
    id: uuid.UUID
    client_name: str | None
    job_title: str | None
    job_reference_id: str | None
    job_description: str | None = None
    required_skills: list[str]
    preferred_skills: list[str]
    minimum_experience: float | None
    maximum_experience: float | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_period: str | None
    employment_type: str | None
    location: str | None
    work_mode: str
    recruiter_name: str | None
    recruiter_email: str | None
    number_of_openings: int | None
    received_at: datetime | None
    last_updated_at: datetime | None
    lifecycle_status: str
    review_status: str
    extraction_confidence: float | None
    validation_warnings: list[str]
    version_number: int
    merged_into_id: uuid.UUID | None
    source_accounts: list[str] = []
    source_count: int = 0
    has_pending_duplicate: bool = False

    @field_validator("salary_min", "salary_max", mode="before")
    @classmethod
    def _dec(cls, v):
        return float(v) if v is not None else None


class RequirementDetail(RequirementOut):
    department: str | None
    seniority: str | None
    education: str | None
    domain_experience: str | None
    notice_period: str | None
    city: str | None
    state: str | None
    country: str | None
    relocation: str | None
    travel: str | None
    recruiter_phone: str | None
    client_contact: str | None
    submission_email: str | None
    submission_instructions: str | None
    certifications: list[str]
    required_documents: list[str]
    extraction_model: str | None
    created_at: datetime
    updated_at: datetime


class SourceOut(BaseModel):
    id: uuid.UUID
    source_type: str
    linked_at: datetime
    email_message_id: uuid.UUID | None
    account_email: str | None
    sender: str | None
    subject: str | None
    received_at: datetime | None
    gmail_url: str | None
    evidence: dict = {}


class VersionOut(ORM):
    id: uuid.UUID
    version_number: int
    previous_values: dict
    new_values: dict
    change_source: str
    changed_by: uuid.UUID | None
    created_at: datetime


class BulkIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    action: Literal["approve", "reject", "archive", "restore"]


class BulkOut(BaseModel):
    succeeded: list[uuid.UUID]
    failed: list[dict]


# ---------------------------------------------------------------- duplicates
class DuplicateOut(BaseModel):
    id: uuid.UUID
    matching_score: float
    matching_reasons: list[str]
    conflicting_fields: list[str]
    review_status: str
    created_at: datetime
    resolved_at: datetime | None
    requirement_a: RequirementOut
    requirement_b: RequirementOut


class DuplicateDetail(DuplicateOut):
    sources_a: list[SourceOut] = []
    sources_b: list[SourceOut] = []


class MergeIn(BaseModel):
    survivor_id: uuid.UUID


# ---------------------------------------------------------------- jobs / exports
class JobOut(ORM):
    id: uuid.UUID
    job_type: str
    status: str
    progress: float | None
    attempts: int
    max_attempts: int
    email_account_id: uuid.UUID | None
    account_email: str | None = None
    stats: dict
    checkpoint: dict = {}
    error_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    duration_seconds: float | None = None


class ExportOptions(BaseModel):
    columns: list[str] | None = None
    sheet_name: str | None = Field(default=None, max_length=31)
    sort: str | None = None
    direction: Literal["asc", "desc"] = "desc"
    include_source: bool = False
    include_audit: bool = False
    include_summary: bool = True
    include_metadata: bool = False


class ExportCreate(BaseModel):
    filename: str | None = Field(default=None, max_length=120)
    selected_ids: list[uuid.UUID] | None = Field(default=None, max_length=5000)
    filters: dict[str, Any] | None = None
    scope: Literal["selected", "filtered", "approved"] = "filtered"
    options: ExportOptions = ExportOptions()


class ExportOut(ORM):
    id: uuid.UUID
    filename: str
    status: str
    record_count: int | None
    file_size_bytes: int | None
    error_summary: str | None
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None
    options: dict
    filters: dict
    requested_by: uuid.UUID | None


class SendIn(BaseModel):
    sender_account_id: uuid.UUID
    to: list[str] = Field(min_length=1, max_length=20)
    cc: list[str] = Field(default_factory=list, max_length=20)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(default="", max_length=20000)
    confirm: bool = False


class DeliveryOut(ORM):
    id: uuid.UUID
    export_job_id: uuid.UUID
    sender_account_id: uuid.UUID | None
    sender_email: str | None = None
    recipient_addresses: list[str]
    cc_addresses: list[str]
    subject: str
    status: str
    status_label: str = ""
    provider_message_id: str | None
    error_summary: str | None
    attempts: int
    created_at: datetime
    sent_at: datetime | None


class RetryDeliveryIn(BaseModel):
    acknowledge_possible_duplicate: bool = False


class AuditOut(ORM):
    id: uuid.UUID
    user_id: uuid.UUID | None
    user_email: str | None = None
    action: str
    entity_type: str | None
    entity_id: str | None
    event_metadata: dict = Field(serialization_alias="metadata")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class NotificationOut(ORM):
    id: uuid.UUID
    kind: str
    severity: str
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime
