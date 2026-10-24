"""Password hashing, token encryption, session tokens, and rate limiting."""
from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.exceptions import RateLimitError

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        # comparable work to reduce user-enumeration timing differences
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except Exception:
            pass
        return False
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def validate_password_strength(password: str) -> list[str]:
    problems = []
    if len(password) < 8:
        problems.append("Password must be at least 8 characters")
    if password.lower() == password or password.upper() == password:
        problems.append("Password must mix upper and lower case letters")
    if not any(c.isdigit() for c in password):
        problems.append("Password must contain a digit")
    return problems


class TokenCipher:
    """Fernet-based encryption for OAuth tokens at rest."""

    def __init__(self, key: str):
        if not key:
            raise RuntimeError("ENCRYPTION_KEY is not configured")
        self._f = Fernet(key.encode())

    def encrypt(self, value: str) -> str:
        return self._f.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._f.decrypt(token.encode()).decode()
        except InvalidToken as e:
            raise RuntimeError("Stored token could not be decrypted (wrong ENCRYPTION_KEY?)") from e


def get_cipher() -> TokenCipher:
    return TokenCipher(get_settings().encryption_key)


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class RateLimiter:
    """In-process sliding-window limiter. Multi-replica deployments should also limit at the proxy."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int, record: bool = True) -> None:
        """Raise if `limit` events happened within the window. With record=False only inspects (use hit() to record)."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= limit:
                raise RateLimitError("Too many attempts, please try again later")
            if record:
                q.append(now)

    def hit(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter()
