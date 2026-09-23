"""API key authentication for SMS routes."""

from __future__ import annotations

import hmac
import logging
from typing import Optional

from fastapi import Header, HTTPException, Request, status

from config.settings import get_settings

logger = logging.getLogger("auth")


def _extract_api_key(
    authorization: Optional[str],
    x_api_key: Optional[str],
) -> Optional[str]:
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    if authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
    return None


def _constant_time_equal(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


async def require_api_key(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> str:
    """
    Require a valid API key via Authorization: Bearer <key> or X-API-Key.

    Fail closed when auth is required and API_KEY is unset.
    """
    cfg = get_settings()

    if not cfg.auth_required:
        # Explicit local opt-out only (REQUIRE_AUTH=0 and non-production)
        provided = _extract_api_key(authorization, x_api_key)
        return provided or "anonymous-dev"

    expected = cfg.api_key
    if not expected:
        logger.error("API_KEY unset while auth is required; refusing request")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is misconfigured",
        )

    provided = _extract_api_key(authorization, x_api_key)
    if not provided or not _constant_time_equal(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Stash for rate limiter without logging the key
    request.state.api_key_id = "primary"
    return "primary"
