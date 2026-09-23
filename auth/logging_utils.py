"""Safe logging helpers — never emit phones, passwords, or API keys."""

from __future__ import annotations

import re

_PHONE_RE = re.compile(r"\b\d{8,15}\b")
_PASSWORD_KEYS = re.compile(
    r"(password|passwd|pwd|api[_-]?key|authorization|bearer|secret|token)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def redact(text: str) -> str:
    if not text:
        return text
    redacted = _PASSWORD_KEYS.sub(r"\1=[REDACTED]", text)
    redacted = _PHONE_RE.sub("[PHONE]", redacted)
    return redacted
