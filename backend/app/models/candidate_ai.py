from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin
from app.db.types import JSONType, UTCDateTime, utcnow


class CandidateAIProfile(Base, IdMixin):
    """One AI profile extraction run. Only the validated structured result is kept; the pasted/uploaded source text is NOT stored."""

    __tablename__ = "candidate_ai_profiles"
    __table_args__ = (Index("ix_candidate_ai_candidate", "candidate_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)  # linkedin_text | resume_text | file
    source_label: Mapped[str | None] = mapped_column(String(300))  # file name or short label, never content
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="succeeded", nullable=False)
    result: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)  # extraction + analytics + warnings
    applied_fields: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
