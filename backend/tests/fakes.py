"""Test doubles for Google and AI services plus Gmail payload builders. Used only by tests."""
from __future__ import annotations

import base64
from datetime import datetime, timezone

from app.integrations.gmail_client import (
    GmailAmbiguousSend,
    GmailAuthError,
    GmailHistoryExpired,
    GmailNotFound,
    GmailRateLimited,
    GmailTransient,
    Profile,
    TokenSet,
)


def b64(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def gmail_message(mid: str, subject: str, body: str, sender: str = "Jane Recruiter <jane@staffing.com>", *, html: str | None = None,
                  attachments: list[tuple[str, str, bytes]] | None = None, ts: datetime | None = None, thread: str | None = None,
                  labels: list[str] | None = None, extra_headers: dict[str, str] | None = None, message_id: str | None = None) -> dict:
    ts = ts or datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    parts = [{"mimeType": "text/plain", "filename": "", "body": {"size": len(body), "data": b64(body)}}]
    if html:
        parts.append({"mimeType": "text/html", "filename": "", "body": {"size": len(html), "data": b64(html)}})
    atts = {}
    for i, (name, mime, data) in enumerate(attachments or []):
        aid = f"att-{mid}-{i}"
        atts[aid] = data
        parts.append({"mimeType": mime, "filename": name, "body": {"attachmentId": aid, "size": len(data)}})
    return {
        "id": mid, "threadId": thread or f"t-{mid}", "snippet": body[:80], "labelIds": labels or ["INBOX"], "internalDate": str(int(ts.timestamp() * 1000)),
        "historyId": "100", "_attachments": atts,
        "payload": {"mimeType": "multipart/mixed", "headers": [
            {"name": "From", "value": sender}, {"name": "To", "value": "me@gmail.com"}, {"name": "Subject", "value": subject},
            {"name": "Message-ID", "value": message_id or f"<{mid}@mail.example>"}] + [{"name": k, "value": v} for k, v in (extra_headers or {}).items()], "body": {"size": 0}, "parts": parts},
    }


JD_BODY = """Hi,

We have an urgent requirement.

Client: Globex Corporation
Job Title: Senior Python Developer
Job ID: GX-1042
Location: Bangalore, India (Hybrid)
Experience: 5-8 years
Required Skills: Python, Django, PostgreSQL, AWS
Good to have: Kubernetes, Terraform
Salary: 25 - 35 LPA
Send your updated resume to jane@staffing.com

Regards,
Jane Recruiter
"""


class FakeMailbox:
    """In-memory Gmail API double. Records sent messages and supports failure injection."""

    def __init__(self):
        self.messages: dict[str, dict] = {}
        self.history_id = 1000
        self.history: list[tuple[int, str]] = []
        self.sent: list[bytes] = []
        self.page_size = 100
        self.fail_list: Exception | None = None
        self.fail_get: dict[str, Exception] = {}
        self.send_error: Exception | None = None
        self.send_accepted_despite_error = False
        self.history_expired = False
        self.calls: list[str] = []

    def add(self, msg: dict) -> dict:
        self.messages[msg["id"]] = msg
        self.history_id += 1
        self.history.append((self.history_id, msg["id"]))
        return msg

    # ---- GmailGateway
    def get_profile(self):
        return {"emailAddress": "me@gmail.com", "historyId": str(self.history_id)}

    def list_message_ids(self, query, page_token, max_results=100):
        self.calls.append("list")
        if self.fail_list:
            raise self.fail_list
        ids = list(self.messages)
        start = int(page_token or 0)
        end = start + self.page_size
        return ids[start:end], (str(end) if end < len(ids) else None)

    def get_message(self, message_id):
        self.calls.append(f"get:{message_id}")
        if message_id in self.fail_get:
            raise self.fail_get[message_id]
        if message_id not in self.messages:
            raise GmailNotFound("missing")
        m = self.messages[message_id]
        return {k: v for k, v in m.items() if k != "_attachments"}

    def get_attachment(self, message_id, attachment_id):
        return self.messages[message_id]["_attachments"][attachment_id]

    def list_history(self, start_history_id, page_token):
        if self.history_expired:
            raise GmailHistoryExpired("expired")
        ids = [mid for hid, mid in self.history if hid > int(start_history_id)]
        return ids, None, str(self.history_id)

    def send_raw(self, raw):
        if self.send_error:
            if self.send_accepted_despite_error:
                self.sent.append(raw)
            raise self.send_error
        self.sent.append(raw)
        return {"id": f"sent-{len(self.sent)}", "threadId": "tt"}

    def find_sent_by_rfc_id(self, rfc_message_id):
        for i, raw in enumerate(self.sent):
            if rfc_message_id.encode() in raw:
                return f"sent-{i + 1}"
        return None


class FakeOAuth:
    def __init__(self, email="new@gmail.com", sub="sub-new", scopes=None, refresh=True, fail_exchange=False):
        self.email, self.sub, self.refresh_token = email, sub, refresh
        self.scopes = scopes or ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send", "openid", "email"]
        self.fail_exchange = fail_exchange
        self.revoked: list[str] = []
        self.last_verifier = None
        self.refresh_error: Exception | None = None

    def authorization_url(self, state, code_challenge, scopes, login_hint=None):
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}&cc={code_challenge}&scope={'+'.join(scopes)}"

    def exchange_code(self, code, code_verifier):
        self.last_verifier = code_verifier
        if self.fail_exchange or code != "good-code":
            raise GmailAuthError("bad code")
        return TokenSet("ya29.fake-access", "1//fake-refresh-token-value-0123456789" if self.refresh_token else None, 3600, self.scopes)

    def fetch_profile(self, access_token):
        return Profile(sub=self.sub, email=self.email, name="New Account")

    def refresh(self, refresh_token):
        if self.refresh_error:
            raise self.refresh_error
        return TokenSet("ya29.refreshed", None, 3600, self.scopes)

    def revoke(self, token):
        self.revoked.append(token)
        return True
