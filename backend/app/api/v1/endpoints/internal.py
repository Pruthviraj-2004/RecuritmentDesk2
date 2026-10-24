"""Machine-to-machine endpoints. Not used by the browser."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, NotFoundError
from app.services import tick

router = APIRouter(prefix="/internal", tags=["internal"])


def _authorize(authorization: str | None) -> None:
    secret = get_settings().tick_secret
    if not secret:
        raise NotFoundError("Not found")  # disabled unless TICK_SECRET is configured
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not supplied or not hmac.compare_digest(supplied.encode(), secret.encode()):
        raise AuthenticationError("Invalid token", code="invalid_tick_token")


@router.api_route("/tick", methods=["GET", "POST"])
def run_tick(authorization: str | None = Header(default=None)):
    """Run one scheduler pass in the background (sync due accounts, extract waiting mail, send due scheduled emails).

    Call it every 10-15 minutes from a free external scheduler with the header  Authorization: Bearer <TICK_SECRET>.
    Returns immediately; overlapping calls are ignored while a pass is still running.
    """
    _authorize(authorization)
    started = tick.start_in_background()
    return JSONResponse(status_code=202 if started else 200, content={"started": started, "already_running": not started, **tick.status()})
