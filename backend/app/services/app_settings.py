"""Per-organization settings sections with safe defaults. Secrets are never stored here."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import AppSetting


class GeneralSettings(BaseModel):
    # display_name / timezone / date_format are stored preferences; the UI currently renders dates in the browser locale
    display_name: str = "RecruitmentDesk"
    timezone: str = "UTC"
    date_format: str = "yyyy-MM-dd"
    theme: str = Field(default="system", pattern="^(light|dark|system)$")
    default_export_columns: list[str] = Field(default_factory=list)
    export_filename_format: str = "recruitment-requirements-{date}"


class GmailSettings(BaseModel):
    """Sync frequency is SYNC_INTERVAL_MINUTES (server) and the import window is per account, so only attachment handling lives here."""

    only_recruitment_emails: bool = True  # search Gmail for hiring-related mail only and never store clearly unrelated mail
    process_attachments: bool = True
    retain_attachment_files: bool = False


class AISettings(BaseModel):
    """Provider, model, key, timeout and retries come from server environment only; the review threshold is the one runtime knob."""

    review_confidence_threshold: float = Field(default=0.6, ge=0, le=1)


class DedupSettings(BaseModel):
    auto_attach_exact: bool = True
    probable_threshold: float = Field(default=0.72, ge=0.3, le=0.99)
    related_threshold: float = Field(default=0.55, ge=0.2, le=0.99)
    time_window_days: int = Field(default=120, ge=1, le=3650)
    require_client_for_auto_attach: bool = True
    create_related_links: bool = True


class NotificationSettings(BaseModel):
    sync_failure: bool = True
    extraction_failure: bool = True
    duplicate_review: bool = True
    export_completed: bool = True
    send_failure: bool = True


class DigestSettings(BaseModel):
    """Scheduled email: every N hours, after syncing, send an Excel file of requirements that are new or changed since the last one."""

    enabled: bool = False
    recipients: list[str] = Field(default_factory=list)
    sender_email: str = ""  # a connected Gmail account with send access; blank = the default sender account
    interval_hours: int = Field(default=3, ge=1, le=24)

    @field_validator("recipients", mode="before")
    @classmethod
    def _split(cls, v):
        if isinstance(v, str):
            parts = v.replace(";", ",").replace(" ", ",").replace(chr(10), ",").split(",")
            return [p.strip() for p in parts if p.strip()]
        return v


SECTIONS: dict[str, type[BaseModel]] = {
    "general": GeneralSettings,
    "gmail": GmailSettings,
    "ai": AISettings,
    "dedup": DedupSettings,
    "notifications": NotificationSettings,
    "digest": DigestSettings,
}


def get_section(db: Session, org_id: uuid.UUID, section: str) -> BaseModel:
    model = SECTIONS[section]
    row = db.scalar(select(AppSetting).where(AppSetting.organization_id == org_id, AppSetting.section == section))
    return model.model_validate(row.value) if row else model()


def save_section(db: Session, org_id: uuid.UUID, section: str, values: dict, user_id: uuid.UUID | None) -> BaseModel:
    model = SECTIONS[section].model_validate(values)
    row = db.scalar(select(AppSetting).where(AppSetting.organization_id == org_id, AppSetting.section == section))
    if row is None:
        row = AppSetting(organization_id=org_id, section=section, value=model.model_dump(), updated_by=user_id)
        db.add(row)
    else:
        row.value = model.model_dump()
        row.updated_by = user_id
    db.flush()
    return model
