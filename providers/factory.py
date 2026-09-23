"""Provider factory — extend here when adding Twilio etc."""

from __future__ import annotations

from config.settings import Settings, get_settings
from providers.base import SmsProvider, SmsProviderError
from providers.way2sms import Way2smsProvider


def get_sms_provider(settings: Settings | None = None) -> SmsProvider:
    cfg = settings or get_settings()
    key = (cfg.sms_provider or "way2sms").strip().lower()
    if key == "way2sms":
        return Way2smsProvider(cfg)
    if key == "twilio":
        # Intentionally not implemented: do not fabricate Twilio credentials or stubs
        # that pretend to work. Add a real TwilioProvider when Account SID + Auth Token
        # are available via env (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN).
        raise SmsProviderError(
            "Twilio provider is not configured yet. Set SMS_PROVIDER=way2sms "
            "or implement providers/twilio.py with server-side TWILIO_* env vars.",
            code="provider_unavailable",
        )
    raise SmsProviderError(f"Unknown SMS provider: {key}", code="provider_unavailable")
