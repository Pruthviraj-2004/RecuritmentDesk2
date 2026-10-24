"""One 'tick' of everything the Celery beat scheduler normally triggers, runnable from a single HTTP call.

For hosting without a worker (for example Render's free plan, where the service sleeps and has no Redis): an external free scheduler
calls POST /api/v1/internal/tick every 10-15 minutes. The call wakes the service, then the work runs in a background thread so the HTTP
response is immediate. Everything here is idempotent, and a lock stops overlapping ticks.
"""
from __future__ import annotations

import threading
import time

from app.core.logging import get_logger
from app.tasks import runner

log = get_logger(__name__)
_lock = threading.Lock()
_last: dict[str, float] = {}
_state: dict = {"last_started": None, "last_finished": None, "last_result": None}

CLEANUP_EVERY = 6 * 3600
RECONCILE_EVERY = 24 * 3600


def status() -> dict:
    return {"running": _lock.locked(), **_state}


def _due(name: str, every: float) -> bool:
    now = time.monotonic()
    if name not in _last or now - _last[name] >= every:
        _last[name] = now
        return True
    return False


def run_tick() -> dict:
    """Run one pass: sync due accounts, extract anything waiting, resume stuck jobs, send due scheduled emails, housekeeping."""
    result: dict = {}
    steps = [
        ("sync_jobs_created", runner.schedule_periodic_syncs_impl),  # inline mode runs the created syncs right here, in order
        ("pending_processed", runner.process_pending_messages_impl),
        ("stuck_resumed", runner.resume_stuck_jobs_impl),
        ("scheduled_emails_sent", runner.send_digests_impl),  # after syncing so the file reflects the newest mail
    ]
    if _due("cleanup", CLEANUP_EVERY):
        steps.append(("cleanup", runner.cleanup_impl))
    if _due("reconcile", RECONCILE_EVERY):
        steps.append(("reconciled", runner.reconcile_accounts_impl))
    for name, fn in steps:
        try:
            result[name] = fn()
        except Exception as e:  # noqa: BLE001 - one failing step must not stop the others
            log.exception("tick_step_failed", extra={"step": name})
            result[name] = f"error: {type(e).__name__}"
    return result


def start_in_background() -> bool:
    """Start a tick in a background thread. Returns False if one is already running."""
    if not _lock.acquire(blocking=False):
        return False

    def work():
        _state["last_started"] = time.time()
        try:
            _state["last_result"] = run_tick()
        finally:
            _state["last_finished"] = time.time()
            _lock.release()

    threading.Thread(target=work, name="tick", daemon=True).start()
    return True
