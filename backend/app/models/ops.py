from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin
from app.db.types import JSONType, UTCDateTime, utcnow


class ExtractionRun(Base, IdMixin):
    __tablename__ = "extraction_runs"
    __table_args__ = (Index("ix_extraction_message", "email_message_id"),)

    email_message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # succeeded|failed|skipped
    extracted_data: Mapped[dict | None] = mapped_column(JSONType)
    confidence_metadata: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ProcessingJob(Base, IdMixin):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index("ix_jobs_org_status", "organization_id", "status"),
        Index("ix_jobs_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("email_accounts.id", ondelete="CASCADE"))
    job_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    progress: Mapped[float | None] = mapped_column(Float)  # 0..1 when measurable
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    checkpoint: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    stats: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(String(500))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)


class ExportJob(Base, IdMixin):
    __tablename__ = "export_jobs"
    __table_args__ = (Index("ix_export_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    options: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    filters: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    selected_record_ids: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    file_reference: Mapped[str | None] = mapped_column(String(500))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    error_summary: Mapped[str | None] = mapped_column(String(500))
    record_count: Mapped[int | None] = mapped_column(Integer)
    processing_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class EmailDelivery(Base, IdMixin):
    __tablename__ = "email_deliveries"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_delivery_idempotency"),
        Index("ix_delivery_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    export_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("export_jobs.id", ondelete="CASCADE"), nullable=False)
    sender_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("email_accounts.id", ondelete="SET NULL"))
    recipient_addresses: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    cc_addresses: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    rfc_message_id: Mapped[str | None] = mapped_column(String(300))
    provider_message_id: Mapped[str | None] = mapped_column(String(100))
    error_summary: Mapped[str | None] = mapped_column(String(500))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AuditLog(Base, IdMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_org_created", "organization_id", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    event_metadata: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Notification(Base, IdMixin):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notif_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="info", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(String(500))
    link: Mapped[str | None] = mapped_column(String(200))
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AppSetting(Base, IdMixin):
    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("organization_id", "section", name="uq_setting_org_section"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    section: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)
