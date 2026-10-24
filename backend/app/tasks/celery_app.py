"""Celery application, task wrappers (retry/backoff) and the beat schedule."""
from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.extraction.pipeline import TransientProcessingError
from app.services.gmail.sync import RetryableSyncError
from app.tasks import runner

s = get_settings()
celery_app = Celery("recruitmentdesk", broker=s.redis_url or "memory://", backend=None)
celery_app.conf.update(
    task_acks_late=True,  # a task interrupted by a crash is re-delivered (all tasks are idempotent)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=60 * 30,
    task_soft_time_limit=60 * 25,
    timezone="UTC",
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "periodic-sync": {"task": "rd.schedule_periodic_syncs", "schedule": max(1, s.sync_interval_minutes) * 60.0},
        "process-pending": {"task": "rd.process_pending", "schedule": 600.0},
        "resume-stuck": {"task": "rd.resume_stuck", "schedule": 300.0},
        "cleanup": {"task": "rd.cleanup", "schedule": 6 * 3600.0},
        "daily-reconcile": {"task": "rd.reconcile", "schedule": 24 * 3600.0},
    },
)


@worker_process_init.connect
def _init(**_):
    configure_logging(get_settings().is_production)


def _backoff(retries: int) -> int:
    return min(30 * (2**retries), 1800)


@celery_app.task(name="rd.sync_account", bind=True, max_retries=5)
def sync_account(self, job_id: str):
    try:
        runner.sync_account_impl(job_id)
    except RetryableSyncError as e:
        raise self.retry(exc=e, countdown=_backoff(self.request.retries))


@celery_app.task(name="rd.process_email", bind=True, max_retries=4)
def process_email(self, message_id: str, force: bool = False, user_id: str | None = None):
    try:
        return runner.process_email_impl(message_id, force, user_id)
    except TransientProcessingError as e:
        raise self.retry(exc=e, countdown=_backoff(self.request.retries))


@celery_app.task(name="rd.run_export")
def run_export(export_id: str):
    runner.run_export_impl(export_id)


@celery_app.task(name="rd.send_delivery", max_retries=0)  # never auto-retry sends
def send_delivery(delivery_id: str):
    runner.send_delivery_impl(delivery_id)


@celery_app.task(name="rd.schedule_periodic_syncs")
def schedule_periodic_syncs():
    return runner.schedule_periodic_syncs_impl()


@celery_app.task(name="rd.process_pending")
def process_pending():
    return runner.process_pending_messages_impl()


@celery_app.task(name="rd.resume_stuck")
def resume_stuck():
    return runner.resume_stuck_jobs_impl()


@celery_app.task(name="rd.cleanup")
def cleanup():
    return runner.cleanup_impl()


@celery_app.task(name="rd.reconcile")
def reconcile():
    return runner.reconcile_accounts_impl()
