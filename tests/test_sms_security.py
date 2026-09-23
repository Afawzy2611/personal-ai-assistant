"""Security-focused tests for the SMS API path."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from auth.rate_limit import reset_rate_limiter_for_tests
from config.settings import get_settings
from providers.base import SmsProviderError
from providers.way2sms import Way2smsProvider


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_send_requires_api_key(client: TestClient) -> None:
    response = client.post(
        "/sms/send",
        json={"recipient": "9876543210", "message": "hello"},
    )
    assert response.status_code == 401


def test_send_rejects_wrong_api_key(client: TestClient) -> None:
    response = client.post(
        "/sms/send",
        headers={"X-API-Key": "wrong"},
        json={"recipient": "9876543210", "message": "hello"},
    )
    assert response.status_code == 401


def test_send_accepts_bearer_and_x_api_key(client: TestClient, auth_headers) -> None:
    ok = client.post(
        "/sms/send",
        headers=auth_headers,
        json={"recipient": "9876543210", "message": "hello"},
    )
    assert ok.status_code == 200

    ok2 = client.post(
        "/sms/send",
        headers={"X-API-Key": "test-api-key-please-change"},
        json={"recipient": "9876543210", "message": "hello again"},
    )
    assert ok2.status_code == 200


def test_password_fields_rejected(client: TestClient, auth_headers) -> None:
    """Client-posted Way2sms passwords must be rejected (extra=forbid)."""
    response = client.post(
        "/sms/send",
        headers=auth_headers,
        json={
            "recipient": "9876543210",
            "message": "hello",
            "username": "attacker",
            "password": "secret",
        },
    )
    assert response.status_code == 422


def test_schedule_password_fields_rejected(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/sms/schedule",
        headers=auth_headers,
        json={
            "recipient": "9876543210",
            "message": "hello",
            "date": "01/01/2030",
            "time": "14:30",
            "password": "secret",
        },
    )
    assert response.status_code == 422


def test_message_max_length_160(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/sms/send",
        headers=auth_headers,
        json={"recipient": "9876543210", "message": "x" * 161},
    )
    assert response.status_code == 422


def test_message_length_160_ok(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/sms/send",
        headers=auth_headers,
        json={"recipient": "9876543210", "message": "x" * 160},
    )
    assert response.status_code == 200


def test_login_required_before_send() -> None:
    """
    Severity check: provider must authenticate successfully before attempting send.
    If login fails, send must not POST to the SMS endpoint.
    """
    get_settings.cache_clear()
    settings = get_settings()
    provider = Way2smsProvider(settings)

    posted = []

    class FakeResponse:
        def __init__(self, status_code: int, text: str = "") -> None:
            self.status_code = status_code
            self.text = text
            self.content = text.encode()

    class FakeSession:
        def post(self, url, data=None, timeout=None):  # noqa: ANN001
            posted.append({"url": url, "data": dict(data or {})})
            # Always fail login (no 'logout' marker)
            return FakeResponse(200, "invalid credentials")

        def close(self) -> None:
            return None

    with patch.object(provider, "_new_session", return_value=FakeSession()):
        with pytest.raises(SmsProviderError) as exc_info:
            import asyncio

            asyncio.run(provider.send("9876543210", "should-not-send"))

    assert exc_info.value.code == "auth_failed"
    # Only the login POST should have happened — never quicksms
    assert len(posted) == 1
    assert "auth-login" in posted[0]["url"]
    assert all("quicksms" not in p["url"] for p in posted)
    # Password must not appear in exception message
    assert "server-pass" not in str(exc_info.value)


def test_insecure_http_refused_without_opt_in() -> None:
    get_settings.cache_clear()
    os.environ["WAY2SMS_BASE_URL"] = "http://www.way2sms.com"
    os.environ["ALLOW_INSECURE_SMS_HTTP"] = "0"
    get_settings.cache_clear()
    try:
        with pytest.raises(SmsProviderError) as exc_info:
            Way2smsProvider(get_settings())
        assert exc_info.value.code == "insecure_transport"
    finally:
        os.environ["WAY2SMS_BASE_URL"] = "https://www.way2sms.com"
        get_settings.cache_clear()


def test_missing_api_key_fails_closed_in_production(mock_provider: AsyncMock) -> None:
    get_settings.cache_clear()
    os.environ["ENV"] = "production"
    os.environ["API_KEY"] = ""
    get_settings.cache_clear()
    reset_rate_limiter_for_tests()
    try:
        from main import create_app
        from routers import sms as sms_router

        app = create_app()
        sms_router._service._provider = mock_provider
        with TestClient(app) as c:
            response = c.post(
                "/sms/send",
                headers={"Authorization": "Bearer anything"},
                json={"recipient": "9876543210", "message": "hello"},
            )
            # Fail closed: misconfigured auth → 503
            assert response.status_code == 503
    finally:
        os.environ["ENV"] = "development"
        os.environ["API_KEY"] = "test-api-key-please-change"
        get_settings.cache_clear()
        sms_router._service._provider = None


def test_errors_are_generic(client: TestClient, auth_headers, mock_provider) -> None:
    mock_provider.send = AsyncMock(
        side_effect=SmsProviderError("secret upstream stacktrace with 9876543210", code="upstream")
    )
    response = client.post(
        "/sms/send",
        headers=auth_headers,
        json={"recipient": "9876543210", "message": "hello"},
    )
    assert response.status_code == 502
    body = response.json()
    assert body["detail"] == "SMS operation failed"
    assert "9876543210" not in response.text
    assert "stacktrace" not in response.text.lower()
