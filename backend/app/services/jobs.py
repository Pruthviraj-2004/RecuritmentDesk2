"""ProcessingJob helpers shared by API and workers."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import redact
from app.db.types import utcnow
from app.models.enums import ACTIVE_JOB_STATUSES, JobStatus
from app.models.ops import ProcessingJob


def create_job(db: Session, *, org_id: uuid.UUID, job_type: str, account_id: uuid.UUID | None = None, payload: dict | None = None,
               user_id: uuid.UUID | None = None, max_attempts: int = 3) -> ProcessingJob:
    job = ProcessingJob(organization_id=org_id, email_account_id=account_id, job_type=job_type, status=JobStatus.QUEUED,
                        payload=payload or {}, checkpoint={}, stats={}, requested_by=user_id, max_attempts=max_attempts)
    db.add(job)
    db.flush()
    return job


def active_job_for_account(db: Session, account_id: uuid.UUID, job_type: str = "sync") -> ProcessingJob | None:
    return db.scalar(select(ProcessingJob).where(ProcessingJob.email_account_id == account_id, ProcessingJob.job_type == job_type,
                                                 ProcessingJob.status.in_([s.value for s in ACTIVE_JOB_STATUSES])))


def start(job: ProcessingJob) -> None:
    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.started_at = job.started_at or utcnow()
    job.error_summary = None


def finish(job: ProcessingJob, status: JobStatus, error: str | None = None) -> None:
    job.status = status
    job.completed_at = utcnow()
    if status in (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS):
        job.progress = 1.0
    job.error_summary = redact(error)[:500] if error else None


def bump(job: ProcessingJob, **counters: int) -> None:
    stats = dict(job.stats or {})
    for k, v in counters.items():
        stats[k] = stats.get(k, 0) + v
    job.stats = stats  # reassign so the JSON change is detected
