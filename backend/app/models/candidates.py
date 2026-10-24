from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.types import JSONType, UTCDateTime, utcnow

CANDIDATE_STATUSES = ["new", "screening", "shortlisted", "interviewing", "offered", "hired", "rejected", "on_hold", "not_interested"]
SUBMISSION_STAGES = ["shortlisted", "submitted", "interview", "offered", "joined", "rejected", "withdrawn"]


class Candidate(Base, IdMixin, TimestampMixin):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("organization_id", "email_normalized", name="uq_candidate_org_email"),
        Index("ix_candidate_org_status", "organization_id", "status"),
        Index("ix_candidate_org_name", "organization_id", "full_name"),
        Index("ix_candidate_org_phone", "organization_id", "phone_normalized"),
        Index("ix_candidate_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(120))
    full_name: Mapped[str] = mapped_column(String(250), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)  # name, email and phone are mandatory; everything else is optional
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    phone_normalized: Mapped[str] = mapped_column(String(20), nullable=False)
    current_title: Mapped[str | None] = mapped_column(String(200))
    current_company: Mapped[str | None] = mapped_column(String(200))
    total_experience: Mapped[float | None] = mapped_column(Float)
    relevant_experience: Mapped[float | None] = mapped_column(Float)
    current_location: Mapped[str | None] = mapped_column(String(200))
    preferred_locations: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    willing_to_relocate: Mapped[bool | None] = mapped_column(Boolean)
    notice_period: Mapped[str | None] = mapped_column(String(100))
    current_ctc: Mapped[float | None] = mapped_column(Numeric(14, 2))
    expected_ctc: Mapped[float | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(8))
    education: Mapped[str | None] = mapped_column(String(500))
    certifications: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    work_authorization: Mapped[str | None] = mapped_column(String(100))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    resume_url: Mapped[str | None] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(60), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="new", nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer)
    tags: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_contacted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    import_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidate_imports.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    skills: Mapped[list["CandidateSkill"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")

    @property
    def skill_names(self) -> list[str]:
        return sorted((s.name for s in self.skills), key=str.lower)


class CandidateSkill(Base, IdMixin):
    __tablename__ = "candidate_skills"
    __table_args__ = (UniqueConstraint("candidate_id", "normalized", name="uq_candidate_skill"), Index("ix_candidate_skill_norm", "normalized"))

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized: Mapped[str] = mapped_column(String(120), nullable=False)

    candidate: Mapped[Candidate] = relationship(back_populates="skills")


class CandidateNote(Base, IdMixin):
    """Timeline entry: free-text notes plus system events (status changes, imports)."""

    __tablename__ = "candidate_notes"
    __table_args__ = (Index("ix_candidate_note_candidate", "candidate_id", "created_at"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), default="note", nullable=False)  # note | status | system
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class CandidateSubmission(Base, IdMixin):
    """Pipeline: a candidate put forward for a requirement and how far they got."""

    __tablename__ = "candidate_submissions"
    __table_args__ = (UniqueConstraint("candidate_id", "requirement_id", name="uq_submission_candidate_requirement"), Index("ix_submission_requirement", "requirement_id"))

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_requirements.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[str] = mapped_column(String(20), default="shortlisted", nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    candidate: Mapped[Candidate] = relationship()


class CandidateImport(Base, IdMixin):
    __tablename__ = "candidate_imports"
    __table_args__ = (Index("ix_candidate_import_org", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    on_duplicate: Mapped[str] = mapped_column(String(10), default="skip", nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_report: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)  # first 200 row problems; never raw file content
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
