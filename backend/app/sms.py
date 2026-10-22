"""Sending verification codes.

The sender is chosen by POETRY_SMS__PROVIDER. With no credentials the mock
logs the code, so the whole flow works in development at no cost; set the
Vonage keys and real messages go out with no other change.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from .configuration import settings

log = logging.getLogger(__name__)

VONAGE_URL = "https://rest.nexmo.com/sms/json"


class SmsSender(Protocol):
    async def send_code(self, phone: str, code: str) -> None: ...


def message_for(code: str) -> str:
    return f"קוד האימות שלך לחומוס המשורר: {code}"


class MockSender:
    """Logs the code instead of sending it. Development only."""

    async def send_code(self, phone: str, code: str) -> None:
        log.warning("SMS not configured — code for %s is %s", phone, code)


class VonageSender:
    """Vonage (formerly Nexmo) SMS API."""

    async def send_code(self, phone: str, code: str) -> None:
        payload = {
            "api_key": settings.sms.vonage_api_key,
            "api_secret": settings.sms.vonage_api_secret.get_secret_value(),
            # E.164 without the plus, as Vonage expects.
            "to": phone.lstrip("+"),
            "from": settings.sms.sender_id,
            "text": message_for(code),
            # Hebrew needs UCS-2; Vonage splits longer messages itself.
            "type": "unicode",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(VONAGE_URL, data=payload)

        if response.status_code != 200:
            log.error("Vonage HTTP %s: %s", response.status_code, response.text[:200])
            raise SmsDeliveryError("לא הצלחנו לשלוח את ההודעה, נסו שוב")

        # Vonage reports per-message failures inside a 200 response.
        body = response.json()
        for message in body.get("messages", []):
            if message.get("status") != "0":
                log.error(
                    "Vonage refused message: status=%s error=%s",
                    message.get("status"),
                    message.get("error-text"),
                )
                raise SmsDeliveryError("לא הצלחנו לשלוח את ההודעה, נסו שוב")


class SmsDeliveryError(RuntimeError):
    """The provider refused or failed to deliver the message."""


def get_sms_sender() -> SmsSender:
    if settings.sms.provider == "vonage" and settings.sms.configured:
        return VonageSender()
    if settings.sms.provider == "vonage":
        log.error("Vonage selected but credentials are missing; using the mock")
    return MockSender()


def code_is_returned_to_client() -> bool:
    """Whether the API may echo the code back.

    Only outside production and only with the mock, so a misconfigured
    production deploy can never hand out codes over HTTP.
    """
    return settings.sms.provider == "mock" and not settings.is_production
