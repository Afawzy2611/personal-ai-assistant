"""Way2sms scraper implementation.

SECURITY NOTES (live risk):
- Way2sms historically used cleartext HTTP and HTML form scraping.
- Prefer HTTPS. If the base URL is http://, this provider refuses unless
  ALLOW_INSECURE_SMS_HTTP=1.
- For production SMS, migrate to Twilio (or another official API) via SmsProvider.
- Credentials MUST come from server env, never from client request bodies.
- Each operation uses an isolated requests.Session (no process-wide shared auth).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from auth.logging_utils import redact
from config.settings import Settings, get_settings
from providers.base import SmsProvider, SmsProviderError

logger = logging.getLogger("providers.way2sms")


class Way2smsProvider(SmsProvider):
    name = "way2sms"

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._assert_transport_policy()

    def _assert_transport_policy(self) -> None:
        base = (self.settings.way2sms_base_url or "").strip()
        parsed = urlparse(base)
        if parsed.scheme == "https":
            return
        if parsed.scheme == "http":
            if self.settings.allow_insecure_sms_http:
                logger.warning(
                    "ALLOW_INSECURE_SMS_HTTP=1: using cleartext HTTP for Way2sms. "
                    "Do not use this in production; prefer Twilio or another HTTPS API."
                )
                return
            raise SmsProviderError(
                "Way2sms base URL is HTTP. Refusing cleartext transport. "
                "Set WAY2SMS_BASE_URL to https://… or explicitly set "
                "ALLOW_INSECURE_SMS_HTTP=1 for local experiments only. "
                "For live SMS, use Twilio (or another official provider) instead of scraping.",
                code="insecure_transport",
            )
        raise SmsProviderError(
            "Invalid WAY2SMS_BASE_URL scheme; expected https (or http with ALLOW_INSECURE_SMS_HTTP=1).",
            code="insecure_transport",
        )

    def _credentials(self) -> tuple[str, str]:
        user = self.settings.way2sms_username
        password = self.settings.way2sms_password
        if not user or not password:
            raise SmsProviderError(
                "Way2sms credentials are not configured on the server",
                code="misconfigured",
            )
        return user, password

    def _new_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; PersonalSmsAssistant/1.0; +https://localhost)"
                )
            }
        )
        return session

    def _timeout(self) -> float:
        return float(self.settings.sms_http_timeout_seconds)

    def _login(self, session: requests.Session, username: str, password: str) -> None:
        login_url = f"{self.settings.way2sms_base_url.rstrip('/')}/auth-login"
        try:
            response = session.post(
                login_url,
                data={"username": username, "password": password, "button": "Login"},
                timeout=self._timeout(),
            )
        except requests.RequestException as exc:
            logger.error("Way2sms login transport error: %s", redact(str(exc)))
            raise SmsProviderError("Upstream login failed", code="upstream") from exc

        if response.status_code != 200 or "logout" not in response.text.lower():
            logger.warning("Way2sms login rejected by upstream")
            raise SmsProviderError(
                "SMS provider authentication failed",
                code="auth_failed",
            )

    async def send(self, recipient: str, message: str) -> Dict[str, Any]:
        username, password = self._credentials()
        session = self._new_session()
        try:
            self._login(session, username, password)
            sms_url = f"{self.settings.way2sms_base_url.rstrip('/')}/quicksms"
            try:
                response = session.post(
                    sms_url,
                    data={
                        "custid": "",
                        "message": message,
                        "mobileno": recipient,
                        "Forward": "Send SMS",
                    },
                    timeout=self._timeout(),
                )
            except requests.RequestException as exc:
                logger.error("Way2sms send transport error: %s", redact(str(exc)))
                raise SmsProviderError("Upstream send failed", code="upstream") from exc

            if response.status_code != 200:
                raise SmsProviderError("Upstream send failed", code="upstream")

            logger.info("SMS send completed via Way2sms")
            return {"status": "success", "message": "SMS sent successfully"}
        finally:
            session.close()

    async def schedule(
        self,
        recipient: str,
        message: str,
        date: str,
        time: str,
    ) -> Dict[str, Any]:
        username, password = self._credentials()
        session = self._new_session()
        try:
            self._login(session, username, password)
            schedule_url = f"{self.settings.way2sms_base_url.rstrip('/')}/sms/send"
            try:
                response = session.post(
                    schedule_url,
                    data={
                        "message": message,
                        "mobileno": recipient,
                        "sendDate": date,
                        "sendTime": time,
                        "SendSMS": "Schedule SMS",
                    },
                    timeout=self._timeout(),
                )
            except requests.RequestException as exc:
                logger.error("Way2sms schedule transport error: %s", redact(str(exc)))
                raise SmsProviderError("Upstream schedule failed", code="upstream") from exc

            if response.status_code != 200:
                raise SmsProviderError("Upstream schedule failed", code="upstream")

            logger.info("SMS schedule completed via Way2sms")
            return {
                "status": "success",
                "message": "SMS scheduled successfully",
                "scheduled_date": date,
                "scheduled_time": time,
            }
        finally:
            session.close()

    async def get_mobile_details(self, mobile_number: str) -> Dict[str, Any]:
        session = self._new_session()
        try:
            details_url = f"{self.settings.way2sms_base_url.rstrip('/')}/smstodebug"
            try:
                response = session.get(
                    details_url,
                    params={"mobile": mobile_number},
                    timeout=self._timeout(),
                )
            except requests.RequestException as exc:
                logger.error("Way2sms details transport error: %s", redact(str(exc)))
                raise SmsProviderError("Upstream lookup failed", code="upstream") from exc

            if response.status_code != 200:
                return {
                    "mobile_number": mobile_number,
                    "status": "not_found",
                    "operator": None,
                    "country": None,
                }

            soup = BeautifulSoup(response.content, "html.parser")
            text = soup.get_text()
            return {
                "mobile_number": mobile_number,
                "status": "found",
                "operator": self._extract_operator(text),
                "country": "India" if "india" in text.lower() else None,
            }
        finally:
            session.close()

    @staticmethod
    def _extract_operator(text: str) -> Optional[str]:
        operators = (
            "airtel",
            "vodafone",
            "jio",
            "bsnl",
            "idea",
            "mts",
            "uninor",
            "reliance",
            "docomo",
            "tata",
            "loop",
            "virgin",
        )
        lower = text.lower()
        for op in operators:
            if op in lower:
                return op.upper()
        return None
