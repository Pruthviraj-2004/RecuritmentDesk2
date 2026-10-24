"""Structured logging with request correlation and secret redaction."""
from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
job_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("job_id", default=None)

_REDACT_PATTERNS = [
    (re.compile(r"(ya29\.[A-Za-z0-9_\-\.]+)"), "[REDACTED_TOKEN]"),
    (re.compile(r"(1//[A-Za-z0-9_\-\.]{20,})"), "[REDACTED_TOKEN]"),
    (re.compile(r"(sk-[A-Za-z0-9_\-]{16,})"), "[REDACTED_KEY]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.=]+"), r"\1[REDACTED]"),
    (
        re.compile(
            r"(?i)((?:access_token|refresh_token|client_secret|password|api_key|authorization)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}&]+"
        ),
        r"\1[REDACTED]",
    ),
]


def redact(text: str) -> str:
    for pattern, repl in _REDACT_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.getMessage()))
        record.args = ()
        return True


_STD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "job_id": job_id_var.get(),
        }
        for k, v in record.__dict__.items():
            if k not in _STD and not k.startswith("_"):
                payload[k] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(production: bool, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RedactingFilter())
    handler.setFormatter(
        JsonFormatter() if production else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
