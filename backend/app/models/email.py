from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.types import JSONType, UTCDateTime, utcnow


class EmailAccount(Base, IdMixin, TimestampMixin):
    __tablename__ = "email_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider", "email_address", name="uq_account_org_provider_email"),
        UniqueConstraint("provider", "provider_account_id", "organization_id", name="uq_account_provider_identity"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    connected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(32), default="gmail", nullable=False)
    provider_account_id: Mapped[str | None] = mapped_column(String(128))  # Google "sub"
    email_address: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expiry: Mapped[datetime | None] = mapped_column(UTCDateTime)
    scopes: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    connection_status: Mapped[str] = mapped_column(String(32), default="connected", nullable=False)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    import_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    extra_query: Mapped[str | None] = mapped_column(String(500))  # optional additional Gmail query terms
    is_default_sender: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(String(500))

    sync_state: Mapped["EmailSyncState | None"] = relationship(back_populates="account", uselist=False, cascade="all, delete-orphan")

    @property
    def can_send(self) -> bool:
        return any(s.endswith("/gmail.send") or s.endswith("/gmail.modify") or s == "https://mail.google.com/" for s in self.scopes or [])

    @property
    def can_read(self) -> bool:
        return any(s.endswith("/gmail.readonly") or s.endswith("/gmail.modify") or s == "https://mail.google.com/" for s in self.scopes or [])


class EmailSyncState(Base, IdMixin):
    __tablename__ = "email_sync_states"

    email_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_accounts.id", ondelete="CASCADE"), unique=True, nullable=False)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    gmail_history_id: Mapped[str | None] = mapped_column(String(32))
    cursor_metadata: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="idle", nullable=False)
    error_summary: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    account: Mapped[EmailAccount] = relationship(back_populates="sync_state")


class EmailMessage(Base, IdMixin, TimestampMixin):
    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("email_account_id", "gmail_message_id", name="uq_message_account_gmail_id"),
        Index("ix_messages_org_received", "organization_id", "received_at"),
        Index("ix_messages_org_hash", "organization_id", "normalized_content_hash"),
        Index("ix_messages_org_status", "organization_id", "processing_status"),
        Index("ix_messages_thread", "email_account_id", "gmail_thread_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_accounts.id", ondelete="CASCADE"), nullable=False)
    gmail_message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gmail_thread_id: Mapped[str | None] = mapped_column(String(64))
    rfc_message_id: Mapped[str | None] = mapped_column(Text)
    sender: Mapped[str | None] = mapped_column(String(500))
    sender_email: Mapped[str | None] = mapped_column(String(320))
    recipients: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(1000))
    snippet: Mapped[str | None] = mapped_column(String(500))
    body_text: Mapped[str | None] = mapped_column(Text)  # truncated; purged after retention window
    body_purged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    labels: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    normalized_content_hash: Mapped[str | None] = mapped_column(String(64))
    duplicate_of_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("email_messages.id", ondelete="SET NULL"))
    classification: Mapped[str | None] = mapped_column(String(40))
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    processing_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(String(500))
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    source_metadata: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    account: Mapped[EmailAccount] = relationship()
    attachments: Mapped[list["EmailAttachment"]] = relationship(back_populates="message", cascade="all, delete-orphan")


class EmailAttachment(Base, IdMixin):
    __tablename__ = "email_attachments"
    __table_args__ = (Index("ix_attachments_message", "email_message_id"),)

    email_message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=False)
    gmail_attachment_id: Mapped[str | None] = mapped_column(Text)  # Gmail attachment ids can exceed 700 characters
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    storage_reference: Mapped[str | None] = mapped_column(String(500))  # raw file; only if retention configured
    extraction_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    extracted_text_reference: Mapped[str | None] = mapped_column(String(500))
    error_summary: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    message: Mapped[EmailMessage] = relationship(back_populates="attachments")
