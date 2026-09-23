"""SMS domain helpers (validation + provider orchestration).

Rewritten as a real Python module (prior revision was a single-line escaped blob).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from providers.base import SmsProvider, SmsProviderError
from providers.factory import get_sms_provider

logger = logging.getLogger("services.sms")

_PHONE_RE = re.compile(r"^\d{10,13}$")


class NumSpyService:
    """Facade kept for compatibility with the historical module name.

    Uses a pluggable SmsProvider. Does not accept client-posted passwords.
    Does not share authenticated HTTP sessions across requests.
    """

    def __init__(self, provider: Optional[SmsProvider] = None) -> None:
        self._provider = provider

    @property
    def provider(self) -> SmsProvider:
        if self._provider is None:
            self._provider = get_sms_provider()
        return self._provider

    async def validate_phone_number(self, phone_number: str) -> Dict[str, Any]:
        phone = str(phone_number or "").strip()
        if not phone:
            return {"valid": False, "reason": "empty"}
        if not _PHONE_RE.fullmatch(phone):
            if not phone.isdigit():
                return {"valid": False, "reason": "non_numeric"}
            if len(phone) < 10:
                return {"valid": False, "reason": "too_short"}
            if len(phone) > 13:
                return {"valid": False, "reason": "too_long"}
            return {"valid": False, "reason": "invalid_format"}
        return {"valid": True, "length": len(phone)}

    async def send_sms(self, mobile_number: str, message: str) -> Dict[str, Any]:
        return await self.provider.send(mobile_number, message)

    async def schedule_sms(
        self,
        mobile_number: str,
        message: str,
        date: str,
        time: str,
    ) -> Dict[str, Any]:
        return await self.provider.schedule(mobile_number, message, date, time)

    async def get_mobile_details(self, mobile_number: str) -> Dict[str, Any]:
        return await self.provider.get_mobile_details(mobile_number)


# Re-export for tests / callers
__all__ = ["NumSpyService", "SmsProviderError"]
