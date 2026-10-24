"""Application configuration. Every setting here is actually used by the code."""
from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULTS = {"", "change-me", "changeme", "dev-secret-key-change-me"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"  # development | test | production
    app_name: str = "RecruitmentDesk"
    app_version: str = "1.0.0"
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"
    cors_origins: str = ""  # comma separated; defaults to frontend_url

    database_url: str = "postgresql+psycopg://recruitment:recruitment@localhost:5432/recruitmentdesk"
    database_schema: str = ""  # PostgreSQL schema to isolate app tables (e.g. on a shared Neon database)
    redis_url: str = ""
    celery_eager: bool = False  # run tasks inline (tests / no-redis dev mode)

    secret_key: str = "dev-secret-key-change-me"
    encryption_key: str = ""  # urlsafe base64 Fernet key
    session_cookie_name: str = "rd_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"
    session_ttl_hours: int = 12

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/email-accounts/oauth/callback"
    google_pubsub_topic: str = ""  # optional; push notifications are not required for sync

    ai_provider: str = "none"  # none | openai_compatible | mock
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: int = 60
    ai_max_retries: int = 3

    storage_backend: str = "local"
    storage_path: str = "./data/storage"

    initial_admin_email: str = ""
    initial_admin_password: str = ""
    initial_org_name: str = "My Recruitment Desk"

    sync_interval_minutes: int = 15
    initial_import_days: int = 30
    max_import_days: int = 365
    max_attachment_size_mb: int = 15
    max_attachments_per_message: int = 10
    max_email_body_chars: int = 60000
    email_body_retention_days: int = 90
    export_retention_days: int = 14
    max_delivery_attachment_mb: int = 20

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins or self.frontend_url
        return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]

    @property
    def max_attachment_bytes(self) -> int:
        return self.max_attachment_size_mb * 1024 * 1024

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if self.is_production:
            problems = self.configuration_problems()
            if problems:
                raise ValueError("Invalid production configuration: " + "; ".join(problems))
        if "*" in self.cors_origin_list:
            raise ValueError("Wildcard CORS origins are not allowed with credentialed requests")
        return self

    def configuration_problems(self) -> list[str]:
        """Human-readable problems that never include secret values."""
        problems: list[str] = []
        if self.secret_key in INSECURE_DEFAULTS or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be set to a random value of at least 32 characters")
        if not self.encryption_key:
            problems.append("ENCRYPTION_KEY must be set (generate with scripts/generate-keys.ps1)")
        if self.is_production and not self.session_cookie_secure:
            problems.append("SESSION_COOKIE_SECURE must be true in production")
        if self.is_production and self.session_cookie_samesite.lower() == "none":
            problems.append("SESSION_COOKIE_SAMESITE=none is not allowed")
        return problems

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def ai_configured(self) -> bool:
        if self.ai_provider == "mock":
            return True
        return self.ai_provider == "openai_compatible" and bool(self.ai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
