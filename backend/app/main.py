from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import install_exception_handlers
from app.core.logging import configure_logging, get_logger, request_id_var

log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(s.is_production)
    problems = s.configuration_problems()
    for p in problems:
        log.warning("configuration_warning: %s", p)
    if s.initial_admin_email and s.initial_admin_password and not problems:
        try:
            from app.db.session import session_scope
            from app.services.auth.service import bootstrap_admin

            with session_scope() as db:
                if bootstrap_admin(db):
                    log.info("bootstrap_admin_created")
        except Exception as e:  # noqa: BLE001 - e.g. migrations not applied yet
            log.warning("bootstrap_admin_skipped: %s", type(e).__name__)
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title=f"{s.app_name} API", version=s.app_version, lifespan=lifespan,
                  docs_url="/api/docs" if not s.is_production else None, redoc_url=None,
                  openapi_url="/api/openapi.json" if not s.is_production else None)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if s.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        log.info("request", extra={"method": request.method, "path": request.url.path, "status": response.status_code,
                                   "ms": round((time.perf_counter() - start) * 1000, 1), "request_id": rid})
        return response

    install_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
