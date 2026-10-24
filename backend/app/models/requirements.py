from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.types import JSONType, UTCDateTime, utcnow


class JobRequirement(Base, IdMixin, TimestampMixin):
    __tablename__ = "job_requirements"
    __table_args__ = (
        Index("ix_req_org_review", "organization_id", "review_status"),
        Index("ix_req_org_lifecycle", "organization_id", "lifecycle_status"),
        Index("ix_req_org_received", "organization_id", "received_at"),
        Index("ix_req_org_fingerprint", "organization_id", "canonical_fingerprint"),
        Index("ix_req_org_client_norm", "organization_id", "client_normalized"),
        Index("ix_req_org_title_norm", "organization_id", "title_normalized"),
        Index("ix_req_org_refid", "organization_id", "job_reference_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    client_name: Mapped[str | None] = mapped_column(String(300))
    client_normalized: Mapped[str | None] = mapped_column(String(300))
    job_title: Mapped[str | None] = mapped_column(String(300))
    title_normalized: Mapped[str | None] = mapped_column(String(300))
    job_reference_id: Mapped[str | None] = mapped_column(String(100))
    job_description: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(String(200))
    seniority: Mapped[str | None] = mapped_column(String(50))
    minimum_experience: Mapped[float | None] = mapped_column(Float)
    maximum_experience: Mapped[float | None] = mapped_column(Float)
    education: Mapped[str | None] = mapped_column(String(500))
    certifications: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    domain_experience: Mapped[str | None] = mapped_column(String(500))
    salary_min: Mapped[float | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[float | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    salary_period: Mapped[str | None] = mapped_column(String(20))
    employment_type: Mapped[str | None] = mapped_column(String(50))
    notice_period: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    location_normalized: Mapped[str | None] = mapped_column(String(300))
    work_mode: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    relocation: Mapped[str | None] = mapped_column(String(200))
    travel: Mapped[str | None] = mapped_column(String(200))
    recruiter_name: Mapped[str | None] = mapped_column(String(200))
    recruiter_email: Mapped[str | None] = mapped_column(String(320))
    recruiter_phone: Mapped[str | None] = mapped_column(String(50))
    client_contact: Mapped[str | None] = mapped_column(String(500))
    submission_email: Mapped[str | None] = mapped_column(String(320))
    submission_instructions: Mapped[str | None] = mapped_column(Text)
    required_documents: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    number_of_openings: Mapped[int | None] = mapped_column(Integer)
    received_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    lifecycle_status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), default="needs_review", nullable=False)
    canonical_fingerprint: Mapped[str | None] = mapped_column(String(64))
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_requirements.id", ondelete="SET NULL"))
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    extraction_model: Mapped[str | None] = mapped_column(String(100))
    validation_warnings: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    skills: Mapped[list["RequirementSkill"]] = relationship(back_populates="requirement", cascade="all, delete-orphan")
    sources: Mapped[list["RequirementSource"]] = relationship(back_populates="requirement", cascade="all, delete-orphan")

    @property
    def required_skills(self) -> list[str]:
        return sorted((s.name for s in self.skills if s.kind == "required"), key=str.lower)

    @property
    def preferred_skills(self) -> list[str]:
        return sorted((s.name for s in self.skills if s.kind == "preferred"), key=str.lower)


class RequirementSkill(Base, IdMixin):
    __tablename__ = "requirement_skills"
    __table_args__ = (
        UniqueConstraint("job_requirement_id", "normalized", "kind", name="uq_skill_per_requirement"),
        Index("ix_skill_normalized", "normalized"),
    )

    job_requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_requirements.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="required", nullable=False)
    category: Mapped[str | None] = mapped_column(String(40))

    requirement: Mapped[JobRequirement] = relationship(back_populates="skills")


class RequirementSource(Base, IdMixin):
    __tablename__ = "requirement_sources"
    __table_args__ = (
        UniqueConstraint("job_requirement_id", "email_message_id", "source_type", name="uq_source_req_msg_type"),
        Index("ix_source_message", "email_message_id"),
    )

    job_requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_requirements.id", ondelete="CASCADE"), nullable=False)
    email_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("email_messages.id", ondelete="SET NULL"))
    source_type: Mapped[str] = mapped_column(String(32), default="email_body", nullable=False)  # email_body|attachment|manual|duplicate_copy|closure_notice
    evidence_metadata: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    linked_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    requirement: Mapped[JobRequirement] = relationship(back_populates="sources")


class RequirementVersion(Base, IdMixin):
    __tablename__ = "requirement_versions"
    __table_args__ = (UniqueConstraint("job_requirement_id", "version_number", name="uq_version_number"),)

    job_requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_requirements.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_values: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    new_values: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    change_source: Mapped[str] = mapped_column(String(40), nullable=False)  # extraction|manual_edit|merge|dedup_enrichment|status
    changed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class DuplicateCandidate(Base, IdMixin):
    __tablename__ = "duplicate_candidates"
    __table_args__ = (
        UniqueConstraint("requirement_id_a", "requirement_id_b", name="uq_duplicate_pair"),
        Index("ix_dup_org_status", "organization_id", "review_status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    requirement_id_a: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_requirements.id", ondelete="CASCADE"), nullable=False)
    requirement_id_b: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_requirements.id", ondelete="CASCADE"), nullable=False)
    matching_score: Mapped[float] = mapped_column(Float, nullable=False)
    matching_reasons: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    conflicting_fields: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    requirement_a: Mapped[JobRequirement] = relationship(foreign_keys=[requirement_id_a])
    requirement_b: Mapped[JobRequirement] = relationship(foreign_keys=[requirement_id_b])
