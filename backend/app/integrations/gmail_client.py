"""Gmail API gateway (Google's official client library) and Google OAuth 2.0 client.

All network access goes through these two classes so tests can replace them with fakes.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from app.core.config import Settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

SCOPE_READ = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_SEND = "https://www.googleapis.com/auth/gmail.send"
IDENTITY_SCOPES = ["openid", "email", "profile"]


class GmailError(Exception):
    pass


class GmailAuthError(GmailError):
    """Credentials invalid/revoked: the account must be reauthorized."""


class GmailRateLimited(GmailError):
    pass


class GmailTransient(GmailError):
    pass


class GmailHistoryExpired(GmailError):
    pass


class GmailNotFound(GmailError):
    pass


class GmailAmbiguousSend(GmailError):
    """Network failure while sending: the message may or may not have been accepted."""


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_in: int
    scopes: list[str]
    id_token: str | None = None


@dataclass
class Profile:
    sub: str
    email: str
    name: str | None


class OAuthClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.s = settings
        self._transport = transport

    def authorization_url(self, state: str, code_challenge: str, scopes: list[str], login_hint: str | None = None) -> str:
        params = {
            "client_id": self.s.google_client_id, "redirect_uri": self.s.google_redirect_uri, "response_type": "code",
            "scope": " ".join(scopes), "state": state, "access_type": "offline", "prompt": "consent",
            "include_granted_scopes": "true", "code_challenge": code_challenge, "code_challenge_method": "S256",
        }
        if login_hint:
            params["login_hint"] = login_hint
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def _post(self, url: str, data: dict) -> httpx.Response:
        try:
            with httpx.Client(timeout=20, transport=self._transport) as c:
                return c.post(url, data=data)
        except httpx.HTTPError as e:
            raise GmailTransient(f"OAuth request failed: {type(e).__name__}") from e

    def exchange_code(self, code: str, code_verifier: str) -> TokenSet:
        r = self._post(GOOGLE_TOKEN_URL, {
            "code": code, "client_id": self.s.google_client_id, "client_secret": self.s.google_client_secret,
            "redirect_uri": self.s.google_redirect_uri, "grant_type": "authorization_code", "code_verifier": code_verifier})
        if r.status_code != 200:
            raise GmailAuthError("Google rejected the authorization code")
        d = r.json()
        return TokenSet(d["access_token"], d.get("refresh_token"), int(d.get("expires_in", 3600)), d.get("scope", "").split(), d.get("id_token"))

    def refresh(self, refresh_token: str) -> TokenSet:
        r = self._post(GOOGLE_TOKEN_URL, {
            "refresh_token": refresh_token, "client_id": self.s.google_client_id, "client_secret": self.s.google_client_secret,
            "grant_type": "refresh_token"})
        if r.status_code in (400, 401):
            raise GmailAuthError("Authorization expired or revoked (invalid_grant)")
        if r.status_code >= 500 or r.status_code == 429:
            raise GmailTransient(f"Google token endpoint returned {r.status_code}")
        if r.status_code != 200:
            raise GmailError(f"Token refresh failed ({r.status_code})")
        d = r.json()
        return TokenSet(d["access_token"], d.get("refresh_token"), int(d.get("expires_in", 3600)), d.get("scope", "").split())

    def fetch_profile(self, access_token: str) -> Profile:
        try:
            with httpx.Client(timeout=20, transport=self._transport) as c:
                r = c.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        except httpx.HTTPError as e:
            raise GmailTransient("Could not reach Google userinfo") from e
        if r.status_code != 200:
            raise GmailAuthError("Could not read the authorized Google account identity")
        d = r.json()
        if not d.get("email") or not d.get("sub") or d.get("email_verified") is False:
            raise GmailAuthError("Google account email is missing or unverified")
        return Profile(sub=d["sub"], email=d["email"].lower(), name=d.get("name"))

    def revoke(self, token: str) -> bool:
        try:
            return self._post(GOOGLE_REVOKE_URL, {"token": token}).status_code == 200
        except GmailError:
            return False


class GmailGateway(Protocol):
    def get_profile(self) -> dict: ...
    def list_message_ids(self, query: str, page_token: str | None, max_results: int = 100) -> tuple[list[str], str | None]: ...
    def get_message(self, message_id: str) -> dict: ...
    def get_attachment(self, message_id: str, attachment_id: str) -> bytes: ...
    def list_history(self, start_history_id: str, page_token: str | None) -> tuple[list[str], str | None, str | None]: ...
    def send_raw(self, raw_rfc822: bytes) -> dict: ...
    def find_sent_by_rfc_id(self, rfc_message_id: str) -> str | None: ...


def _map_http_error(e: Any) -> Exception:
    status = getattr(getattr(e, "resp", None), "status", None)
    reason = str(getattr(e, "reason", "") or e)
    if status == 401:
        return GmailAuthError("Gmail rejected the credentials")
    if status == 403 and ("rateLimit" in reason or "quota" in reason.lower() or "userRateLimit" in reason):
        return GmailRateLimited("Gmail rate limit reached")
    if status == 403:
        return GmailAuthError("Gmail permission denied (missing scope or access revoked)")
    if status == 429:
        return GmailRateLimited("Gmail rate limit reached")
    if status == 404:
        return GmailNotFound("Not found")
    if status and status >= 500:
        return GmailTransient(f"Gmail server error {status}")
    return GmailError(f"Gmail API error {status}")


class GoogleGmailGateway:
    """Real Gmail API client built on googleapiclient. Created per task with a fresh access token."""

    def __init__(self, access_token: str):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        self._svc = build("gmail", "v1", credentials=Credentials(token=access_token), cache_discovery=False)

    def _exec(self, req):
        from googleapiclient.errors import HttpError

        try:
            return req.execute(num_retries=2)
        except HttpError as e:
            raise _map_http_error(e) from e
        except (TimeoutError, ConnectionError, OSError) as e:
            raise GmailTransient(type(e).__name__) from e

    def get_profile(self) -> dict:
        return self._exec(self._svc.users().getProfile(userId="me"))

    def list_message_ids(self, query, page_token, max_results=100):
        r = self._exec(self._svc.users().messages().list(userId="me", q=query, pageToken=page_token, maxResults=max_results))
        return [m["id"] for m in r.get("messages", [])], r.get("nextPageToken")

    def get_message(self, message_id):
        return self._exec(self._svc.users().messages().get(userId="me", id=message_id, format="full"))

    def get_attachment(self, message_id, attachment_id):
        r = self._exec(self._svc.users().messages().attachments().get(userId="me", messageId=message_id, id=attachment_id))
        return base64.urlsafe_b64decode(r["data"] + "=" * (-len(r["data"]) % 4))

    def list_history(self, start_history_id, page_token):
        try:
            r = self._exec(self._svc.users().history().list(userId="me", startHistoryId=start_history_id, historyTypes=["messageAdded"],
                                                           pageToken=page_token))
        except GmailNotFound as e:
            raise GmailHistoryExpired("History cursor is no longer valid") from e
        ids: list[str] = []
        for h in r.get("history", []):
            ids += [m["message"]["id"] for m in h.get("messagesAdded", [])]
        return list(dict.fromkeys(ids)), r.get("nextPageToken"), r.get("historyId")

    def send_raw(self, raw_rfc822: bytes) -> dict:
        from googleapiclient.errors import HttpError

        body = {"raw": base64.urlsafe_b64encode(raw_rfc822).decode()}
        try:
            # num_retries=0 on purpose: never auto-resend, the first attempt might already have been accepted.
            return self._svc.users().messages().send(userId="me", body=body).execute(num_retries=0)
        except HttpError as e:
            raise _map_http_error(e) from e
        except (TimeoutError, ConnectionError, OSError) as e:
            raise GmailAmbiguousSend(type(e).__name__) from e

    def find_sent_by_rfc_id(self, rfc_message_id: str) -> str | None:
        clean = rfc_message_id.strip("<>")
        r = self._exec(self._svc.users().messages().list(userId="me", q=f"rfc822msgid:{clean} in:sent", maxResults=1))
        msgs = r.get("messages", [])
        return msgs[0]["id"] if msgs else None
