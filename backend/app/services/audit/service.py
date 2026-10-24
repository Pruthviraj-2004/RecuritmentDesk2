from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import redact
from app.models.ops import AuditLog, Notification

_SENSITIVE = {"password", "access_token", "refresh_token", "token", "secret", "api_key", "code"}


def _clean(meta: dict[str, Any] | None) -> dict:
    out: dict = {}
    for k, v in (meta or {}).items():
        if k.lower() in _SENSITIVE:
            continue
        if isinstance(v, str):
            v = redact(v)[:500]
        out[k] = v
    return out


def record(db: Session, *, org_id: uuid.UUID | None, user_id: uuid.UUID | None, action: str, entity_type: str | None = None,
           entity_id: Any = None, metadata: dict | None = None) -> AuditLog:
    log = AuditLog(organization_id=org_id, user_id=user_id, action=action, entity_type=entity_type,
                   entity_id=str(entity_id) if entity_id is not None else None, event_metadata=_clean(metadata))
    db.add(log)
    return log


def notify(db: Session, *, org_id: uuid.UUID, kind: str, title: str, body: str | None = None, severity: str = "info",
           link: str | None = None) -> Notification | None:
    from app.services.app_settings import get_section

    prefs = get_section(db, org_id, "notifications")
    pref_key = {"sync_failed": "sync_failure", "extraction_failed": "extraction_failure", "duplicate_review": "duplicate_review",
                "export_completed": "export_completed", "send_failed": "send_failure"}.get(kind)
    if pref_key and not getattr(prefs, pref_key):
        return None
    n = Notification(organization_id=org_id, kind=kind, title=title[:200], body=(redact(body)[:500] if body else None), severity=severity, link=link)
    db.add(n)
    return n
