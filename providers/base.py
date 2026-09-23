"""SMS provider interface — swap Way2sms for Twilio without rewriting routes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class SmsProviderError(Exception):
    """Provider-level failure (credentials, transport, upstream)."""

    def __init__(self, message: str = "SMS provider error", *, code: str = "provider_error"):
        super().__init__(message)
        self.code = code


class SmsProvider(ABC):
    """Thin interface for outbound SMS operations."""

    name: str = "abstract"

    @abstractmethod
    async def send(self, recipient: str, message: str) -> Dict[str, Any]:
        """Send an SMS immediately. Raises SmsProviderError on failure."""

    @abstractmethod
    async def schedule(
        self,
        recipient: str,
        message: str,
        date: str,
        time: str,
    ) -> Dict[str, Any]:
        """Schedule an SMS. Raises SmsProviderError on failure."""

    async def get_mobile_details(self, mobile_number: str) -> Dict[str, Any]:
        """Optional lookup. Default: not supported."""
        return {
            "mobile_number": mobile_number,
            "status": "unsupported",
            "operator": None,
            "country": None,
        }

    async def aclose(self) -> None:
        """Release any resources. Default no-op."""
        return None
