"""Parse Gmail API `format=full` payloads into plain data. Email content is untrusted: HTML is converted to text only."""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import getaddresses, parseaddr, parsedate_to_datetime

from app.services.normalization.text import html_to_text, normalize_email_address, normalize_whitespace


@dataclass
class AttachmentRef:
    filename: str
    content_type: str | None
    size: int
    attachment_id: str | None
    inline_data: bytes | None = None


@dataclass
class ParsedMessage:
    gmail_id: str
    thread_id: str | None
    rfc_message_id: str | None
    sender: str | None
    sender_email: str | None
    recipients: list[str]
    subject: str | None
    snippet: str | None
    labels: list[str]
    received_at: datetime | None
    body_text: str
    attachments: list[AttachmentRef] = field(default_factory=list)
    history_id: str | None = None
    exported_by_app: bool = False


def _b64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _walk(part: dict, text_parts: list[str], html_parts: list[str], atts: list[AttachmentRef], depth: int = 0) -> None:
    if depth > 12:  # guard against pathological nesting
        return
    mime = (part.get("mimeType") or "").lower()
    body = part.get("body") or {}
    filename = part.get("filename") or ""
    if filename or body.get("attachmentId"):
        if filename:
            data = _b64(body["data"]) if body.get("data") and not body.get("attachmentId") else None
            atts.append(AttachmentRef(filename[:500], mime or None, int(body.get("size", 0)), body.get("attachmentId"), data))
    elif mime == "text/plain" and body.get("data"):
        text_parts.append(_b64(body["data"]).decode("utf-8", "replace"))
    elif mime == "text/html" and body.get("data"):
        html_parts.append(_b64(body["data"]).decode("utf-8", "replace"))
    for child in part.get("parts") or []:
        _walk(child, text_parts, html_parts, atts, depth + 1)


def parse_gmail_message(raw: dict, max_chars: int) -> ParsedMessage:
    payload = raw.get("payload") or {}
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    text_parts: list[str] = []
    html_parts: list[str] = []
    atts: list[AttachmentRef] = []
    _walk(payload, text_parts, html_parts, atts)

    if text_parts:
        body = normalize_whitespace("\n".join(text_parts))
    elif html_parts:
        body = html_to_text("\n".join(html_parts))
    else:
        body = ""

    received: datetime | None = None
    if raw.get("internalDate"):
        try:
            received = datetime.fromtimestamp(int(raw["internalDate"]) / 1000, tz=timezone.utc)
        except (ValueError, OverflowError):
            received = None
    if received is None and headers.get("date"):
        try:
            received = parsedate_to_datetime(headers["date"]).astimezone(timezone.utc)
        except (TypeError, ValueError):
            received = None

    sender = headers.get("from")
    recips = [a for _, a in getaddresses([headers.get("to", ""), headers.get("cc", "")]) if a]
    return ParsedMessage(
        gmail_id=raw["id"], thread_id=raw.get("threadId"), rfc_message_id=headers.get("message-id"),
        sender=sender[:500] if sender else None, sender_email=normalize_email_address(parseaddr(sender or "")[1]) or None,
        recipients=[r.lower() for r in recips][:50], subject=(headers.get("subject") or "")[:1000] or None,
        snippet=(raw.get("snippet") or "")[:500] or None, labels=raw.get("labelIds", []), received_at=received,
        body_text=body[:max_chars], attachments=atts, history_id=raw.get("historyId"), exported_by_app="x-recruitmentdesk-export" in headers,
    )
