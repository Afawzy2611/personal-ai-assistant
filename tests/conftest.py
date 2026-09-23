"""Shared pytest fixtures."""

from __future__ import annotations

import os
from typing import Any, Dict, Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

# Ensure deterministic env before importing the app
os.environ["API_KEY"] = "test-api-key-please-change"
os.environ["REQUIRE_AUTH"] = "1"
os.environ["ENV"] = "development"
os.environ["ALLOW_INSECURE_SMS_HTTP"] = "0"
os.environ["WAY2SMS_BASE_URL"] = "https://www.way2sms.com"
os.environ["WAY2SMS_USERNAME"] = "server-user"
os.environ["WAY2SMS_PASSWORD"] = "server-pass"
os.environ.pop("CORS_ORIGINS", None)
os.environ.pop("TRUSTED_HOSTS", None)

from config.settings import get_settings  # noqa: E402
from auth.rate_limit import reset_rate_limiter_for_tests  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    reset_rate_limiter_for_tests()
    yield
    get_settings.cache_clear()
    reset_rate_limiter_for_tests()


@pytest.fixture
def mock_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.name = "mock"
    provider.send = AsyncMock(return_value={"status": "success", "message": "ok"})
    provider.schedule = AsyncMock(return_value={"status": "success", "message": "ok"})
    provider.get_mobile_details = AsyncMock(
        return_value={
            "mobile_number": "9876543210",
            "status": "found",
            "operator": "JIO",
            "country": "India",
        }
    )
    return provider


@pytest.fixture
def client(mock_provider: AsyncMock) -> Iterator[TestClient]:
    from main import create_app
    from routers import sms as sms_router

    app = create_app()
    # Inject mock provider so tests never hit the network
    sms_router._service._provider = mock_provider
    with TestClient(app) as test_client:
        yield test_client
    sms_router._service._provider = None


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    return {"Authorization": "Bearer test-api-key-please-change"}
