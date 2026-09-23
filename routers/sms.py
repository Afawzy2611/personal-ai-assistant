"""SMS API routes — authenticated, no client-posted credentials.

Rewritten as a real Python module (prior revision was a single-line escaped blob).
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from auth.api_key import require_api_key
from auth.logging_utils import redact
from auth.rate_limit import enforce_rate_limit
from providers.base import SmsProviderError
from services.numspy_service import NumSpyService

logger = logging.getLogger("routers.sms")

router = APIRouter(
    prefix="/sms",
    tags=["sms"],
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)

_service = NumSpyService()


class SMSRequest(BaseModel):
    """Outbound SMS. Credentials are NEVER accepted from the client."""

    model_config = ConfigDict(extra="forbid")

    recipient: str = Field(..., min_length=10, max_length=13, description="Digits only")
    message: str = Field(..., min_length=1, max_length=160)

    @field_validator("recipient")
    @classmethod
    def recipient_digits(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.isdigit():
            raise ValueError("recipient must be digits only")
        return cleaned


class ScheduledSMSRequest(SMSRequest):
    date: str = Field(..., description="DD/MM/YYYY")
    time: str = Field(..., description="HH:MM 24-hour")


class MobileDetailsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mobile_number: str = Field(..., min_length=10, max_length=13)

    @field_validator("mobile_number")
    @classmethod
    def digits_only(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.isdigit():
            raise ValueError("mobile_number must be digits only")
        return cleaned


class SMSResponse(BaseModel):
    status: str
    message: str
    recipient: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class MobileDetailsResponse(BaseModel):
    mobile_number: str
    status: str
    operator: Optional[str] = None
    country: Optional[str] = None


def _map_provider_error(exc: SmsProviderError) -> HTTPException:
    if exc.code in {"auth_failed", "misconfigured"}:
        code = status.HTTP_502_BAD_GATEWAY if exc.code == "auth_failed" else status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code == "insecure_transport":
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code == "provider_unavailable":
        code = status.HTTP_501_NOT_IMPLEMENTED
    else:
        code = status.HTTP_502_BAD_GATEWAY
    # Generic client-facing detail; log redacted server-side separately
    return HTTPException(status_code=code, detail="SMS operation failed")


@router.post("/send", response_model=SMSResponse)
async def send_sms(payload: SMSRequest) -> SMSResponse:
    validation = await _service.validate_phone_number(payload.recipient)
    if not validation.get("valid"):
        raise HTTPException(status_code=400, detail="Invalid phone number")

    try:
        result = await _service.send_sms(payload.recipient, payload.message)
    except SmsProviderError as exc:
        logger.error("send failed: %s", redact(str(exc)))
        raise _map_provider_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("send unexpected error: %s", redact(str(exc)))
        raise HTTPException(status_code=500, detail="SMS operation failed") from exc

    return SMSResponse(
        status=result.get("status", "success"),
        message=result.get("message", "SMS sent successfully"),
        recipient=payload.recipient,
    )


@router.post("/schedule", response_model=SMSResponse)
async def schedule_sms(payload: ScheduledSMSRequest) -> SMSResponse:
    validation = await _service.validate_phone_number(payload.recipient)
    if not validation.get("valid"):
        raise HTTPException(status_code=400, detail="Invalid phone number")

    try:
        datetime.strptime(payload.date, "%d/%m/%Y")
        datetime.strptime(payload.time, "%H:%M")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date/time format (expected DD/MM/YYYY and HH:MM)",
        ) from None

    try:
        result = await _service.schedule_sms(
            payload.recipient,
            payload.message,
            payload.date,
            payload.time,
        )
    except SmsProviderError as exc:
        logger.error("schedule failed: %s", redact(str(exc)))
        raise _map_provider_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("schedule unexpected error: %s", redact(str(exc)))
        raise HTTPException(status_code=500, detail="SMS operation failed") from exc

    return SMSResponse(
        status=result.get("status", "success"),
        message=result.get("message", "SMS scheduled successfully"),
        recipient=payload.recipient,
    )


@router.post("/details", response_model=MobileDetailsResponse)
async def get_mobile_details(payload: MobileDetailsRequest) -> MobileDetailsResponse:
    validation = await _service.validate_phone_number(payload.mobile_number)
    if not validation.get("valid"):
        raise HTTPException(status_code=400, detail="Invalid phone number")

    try:
        details = await _service.get_mobile_details(payload.mobile_number)
    except SmsProviderError as exc:
        logger.error("details failed: %s", redact(str(exc)))
        raise _map_provider_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("details unexpected error: %s", redact(str(exc)))
        raise HTTPException(status_code=500, detail="SMS operation failed") from exc

    return MobileDetailsResponse(
        mobile_number=details.get("mobile_number", payload.mobile_number),
        status=details.get("status", "unknown"),
        operator=details.get("operator"),
        country=details.get("country"),
    )


@router.get("/validate/{phone_number}")
async def validate_phone_number(phone_number: str) -> dict:
    return await _service.validate_phone_number(phone_number)


@router.get("/status")
async def get_sms_status() -> dict:
    return {
        "service": "SMS API stub",
        "status": "active",
        "provider": "configurable (default: way2sms scraper — prefer Twilio for production)",
        "features": [
            "Send SMS",
            "Schedule SMS",
            "Get Mobile Details",
            "Phone Number Validation",
        ],
        "character_limit": 160,
        "auth": "API_KEY required (Bearer or X-API-Key)",
        "note": (
            "Way2sms is a legacy HTML scraper. Live production should use an "
            "official HTTPS provider (e.g. Twilio) via SmsProvider."
        ),
    }
