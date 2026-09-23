"""FastAPI application entrypoint for the SMS API stub."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config.settings import get_settings
from routers import sms as sms_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.auth_required and not settings.api_key:
        logger.error(
            "API_KEY is unset while auth is required "
            "(ENV=%s REQUIRE_AUTH=%s). SMS routes will return 503 until configured.",
            settings.env,
            settings.require_auth,
        )
    if settings.allow_insecure_sms_http:
        logger.warning(
            "ALLOW_INSECURE_SMS_HTTP is enabled — cleartext SMS transport allowed. "
            "Do not use this for live production."
        )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Personal SMS API Stub",
        description=(
            "Authenticated SMS send/schedule stub. Not a multi-model AI assistant. "
            "Credentials are server-side only. Prefer Twilio over Way2sms for live SMS."
        ),
        version="0.2.0-security",
        lifespan=lifespan,
    )

    # Secure CORS defaults: do not combine allow_origins=["*"] with credentials.
    origins = settings.cors_origin_list
    if origins:
        if "*" in origins:
            logger.warning(
                "CORS_ORIGINS contains '*'; enabling CORS without credentials "
                "(wildcard + credentials is unsafe)."
            )
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=False,
                allow_methods=["GET", "POST"],
                allow_headers=["Authorization", "X-API-Key", "Content-Type"],
            )
        else:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=origins,
                allow_credentials=True,
                allow_methods=["GET", "POST"],
                allow_headers=["Authorization", "X-API-Key", "Content-Type"],
            )

    hosts = settings.trusted_host_list
    if hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @app.get("/health")
    async def health() -> dict:
        """Public liveness probe — no API key required."""
        return {"status": "ok"}

    app.include_router(sms_router.router)
    return app


app = create_app()
