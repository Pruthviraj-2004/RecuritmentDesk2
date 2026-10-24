from __future__ import annotations

import re
from urllib.parse import quote


def gmail_url(account_email: str | None, gmail_id: str) -> str | None:
    """Safe deep link built only from the validated account email + Gmail message id (never from email content)."""
    if not account_email or not re.fullmatch(r"[0-9a-fA-F]{8,32}", gmail_id or ""):
        return None
    return f"https://mail.google.com/mail/u/{quote(account_email, safe='')}/#all/{gmail_id}"
