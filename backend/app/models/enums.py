"""String enums. Stored as plain strings in the database (validated in code) so values can evolve via migrations."""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


ROLE_RANK = {Role.VIEWER: 0, Role.MEMBER: 1, Role.ADMIN: 2, Role.OWNER: 3}


class ConnectionStatus(StrEnum):
    CONNECTED = "connected"
    SYNCING = "syncing"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"  # authorization revoked / refresh token invalid: needs reauthorization
    ERROR = "error"


class MessageClassification(StrEnum):
    NEW_REQUIREMENT = "new_requirement"
    UPDATED_REQUIREMENT = "updated_requirement"
    RECRUITER_FOLLOWUP = "recruiter_followup"
    CANDIDATE_SUBMISSION = "candidate_submission"
    INTERVIEW_SCHEDULING = "interview_scheduling"
    JOB_CLOSURE = "job_closure"
    UNRELATED = "unrelated"
    NEEDS_REVIEW = "needs_review"


REQUIREMENT_CLASSES = {MessageClassification.NEW_REQUIREMENT, MessageClassification.UPDATED_REQUIREMENT}


class MessageStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_AI = "awaiting_ai"  # AI provider not configured/unavailable; will extract when available
    PROCESSED = "processed"  # at least one requirement extracted/linked
    NO_REQUIREMENT = "no_requirement"
    NEEDS_REVIEW = "needs_review"
    DUPLICATE = "duplicate"  # cross-account copy linked to an already processed message
    IGNORED = "ignored"
    FAILED = "failed"


class AttachmentStatus(StrEnum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    UNSUPPORTED = "unsupported"
    QUARANTINED = "quarantined"
    TOO_LARGE = "too_large"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReviewStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class LifecycleStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"
    MERGED = "merged"


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class SkillKind(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"


class DuplicateStatus(StrEnum):
    PENDING = "pending"
    MERGED = "merged"
    KEPT_BOTH = "kept_both"
    RELATED = "related"
    DISMISSED = "dismissed"


class JobType(StrEnum):
    SYNC = "sync"
    EXTRACTION = "extraction"
    EXPORT = "export"
    DELIVERY = "delivery"
    MAINTENANCE = "maintenance"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


ACTIVE_JOB_STATUSES = {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}


class ExportStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class DeliveryStatus(StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    ACCEPTED = "accepted_by_gmail"  # Gmail accepted the message; this is NOT proof of inbox delivery
    FAILED = "failed"
    UNCERTAIN = "uncertain"  # network failure after submit; outcome unknown, no automatic resend
