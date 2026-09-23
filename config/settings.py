"""Application settings loaded from environment variables only."""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-side configuration. Never accept secrets from request bodies."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime mode
    env: str = Field(default="development", description="development | production")
    require_auth: bool = Field(
        default=True,
        description="Fail closed: require API_KEY. Set REQUIRE_AUTH=0 only for local experiments.",
    )

    # API authentication (server-side only)
    api_key: Optional[str] = Field(default=None, description="Bearer / X-API-Key secret")

    # Way2sms credentials (server-side only — never from clients)
    way2sms_username: Optional[str] = Field(default=None)
    way2sms_password: Optional[str] = Field(default=None)

    # SMS transport
    sms_provider: str = Field(
        default="way2sms",
        description="Active provider key. way2sms is a legacy scraper; prefer twilio when available.",
    )
    way2sms_base_url: str = Field(
        default="https://www.way2sms.com",
        description="Prefer https://. HTTP only allowed when ALLOW_INSECURE_SMS_HTTP=1.",
    )
    allow_insecure_sms_http: bool = Field(
        default=False,
        description="Explicit opt-in for cleartext Way2sms HTTP. Do not enable in production.",
    )
    sms_http_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)

    # Host hardening
    trusted_hosts: Optional[str] = Field(
        default=None,
        description="Comma-separated hostnames for TrustedHostMiddleware. Empty disables.",
    )
    cors_origins: str = Field(
        default="",
        description="Comma-separated origins. Empty = no CORS middleware (safest default).",
    )

    # Rate limiting (in-memory; use Redis for multi-instance)
    rate_limit_per_minute: int = Field(default=30, ge=1, le=1000)

    @field_validator("require_auth", "allow_insecure_sms_http", mode="before")
    @classmethod
    def _parse_boolish(cls, value):  # noqa: ANN001
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return value

    @property
    def is_production(self) -> bool:
        return self.env.strip().lower() == "production"

    @property
    def auth_required(self) -> bool:
        # Fail closed in production even if REQUIRE_AUTH was flipped off by mistake
        if self.is_production:
            return True
        return bool(self.require_auth)

    @property
    def trusted_host_list(self) -> List[str]:
        if not self.trusted_hosts:
            return []
        return [h.strip() for h in self.trusted_hosts.split(",") if h.strip()]

    @property
    def cors_origin_list(self) -> List[str]:
        if not self.cors_origins:
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
