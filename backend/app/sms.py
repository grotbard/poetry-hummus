"""One-time codes for phone verification.

Two providers, chosen by POETRY_SMS__PROVIDER:

* ``textme`` delegates the whole code lifecycle to TextMe's OTP service —
  they generate it, send it, and check it. This app never sees or stores a
  code, which is the main reason to prefer it.
* ``mock`` keeps the lifecycle local: it generates a code, logs it instead of
  sending, and verifies it against a hash. Used for development and tests,
  and as the fallback whenever TextMe is not configured.

Both satisfy the same protocol, so the routes do not care which is active.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from .configuration import settings

log = logging.getLogger(__name__)


class CodeRejected(Exception):
    """The submitted code was wrong, expired, or out of attempts."""

    def __init__(self, detail: str = "קוד שגוי או שפג תוקפו") -> None:
        super().__init__(detail)
        self.detail = detail


class SmsDeliveryError(RuntimeError):
    """The provider refused or failed to send the message."""


class OtpProvider(Protocol):
    """Issues and checks one-time codes."""

    #: True when this provider keeps the code itself, so the app must store
    #: a hash locally to verify against later.
    stores_code_locally: bool

    async def send_code(self, phone: str, code: str | None) -> None: ...

    async def validate_code(self, phone: str, code: str) -> None:
        """Raise CodeRejected when the code is not acceptable."""
        ...


def message_for(code: str) -> str:
    return f"קוד האימות שלך לחומוס המשורר: {code}"


class MockProvider:
    """Logs the code rather than sending it. Verification stays local."""

    stores_code_locally = True

    async def send_code(self, phone: str, code: str | None) -> None:
        log.warning("SMS not configured — code for %s is %s", phone, code)

    async def validate_code(self, phone: str, code: str) -> None:
        # The caller checks the stored hash; nothing to ask a provider.
        raise NotImplementedError("the mock verifies locally")


def _local_phone(e164: str) -> str:
    """TextMe wants an Israeli number as 05XXXXXXXX, not +9725XXXXXXXX."""
    if e164.startswith("+972"):
        return "0" + e164[4:]
    return e164.lstrip("+")


class TextMeProvider:
    """TextMe's OTP service — https://docs.textme.co.il/endpoints/otp

    One endpoint for everything; the root element of the body picks the
    operation. A ``status`` of 0 means success, anything else is an error,
    and 12 specifically means the code failed to validate.
    """

    stores_code_locally = False

    #: TextMe's documented code for "the submitted code did not validate".
    CODE_INVALID_STATUS = 12

    async def _call(self, body: dict) -> dict:
        sms = settings.sms
        try:
            async with httpx.AsyncClient(timeout=sms.timeout_seconds) as client:
                response = await client.post(
                    sms.textme_url,
                    json=body,
                    headers={
                        "Authorization": f"Bearer {sms.textme_token.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            log.error("TextMe unreachable: %s", exc)
            raise SmsDeliveryError("לא הצלחנו לשלוח את ההודעה, נסו שוב") from exc

        if response.status_code != 200:
            log.error("TextMe HTTP %s: %s", response.status_code, response.text[:200])
            raise SmsDeliveryError("לא הצלחנו לשלוח את ההודעה, נסו שוב")

        try:
            return response.json()
        except ValueError as exc:
            log.error("TextMe returned non-JSON: %s", response.text[:200])
            raise SmsDeliveryError("לא הצלחנו לשלוח את ההודעה, נסו שוב") from exc

    async def send_code(self, phone: str, code: str | None) -> None:
        """Ask TextMe to mint and send a code. `code` is ignored by design."""
        sms = settings.sms
        body = {
            "send_otp": {
                "user": {"username": sms.textme_username},
                "phone": _local_phone(phone),
                "source": sms.textme_sender,
                "app_id": sms.textme_app_id,
                "max_tries": str(sms.max_attempts),
                "valid_time": str(sms.code_valid_minutes),
                # [code] is substituted by TextMe.
                "text": "קוד האימות שלך לחומוס המשורר: [code]",
            }
        }
        payload = await self._call(body)
        status = payload.get("status")
        if str(status) != "0":
            log.error(
                "TextMe refused send_otp: status=%s message=%s",
                status,
                payload.get("message"),
            )
            raise SmsDeliveryError("לא הצלחנו לשלוח את ההודעה, נסו שוב")

    async def validate_code(self, phone: str, code: str) -> None:
        sms = settings.sms
        body = {
            "validate_otp": {
                "user": {"username": sms.textme_username},
                "phone": _local_phone(phone),
                "app_id": sms.textme_app_id,
                "code": code,
                "service_type": "sms",
            }
        }
        payload = await self._call(body)
        status = payload.get("status")
        if str(status) == "0":
            return

        if str(status) == str(self.CODE_INVALID_STATUS):
            raise CodeRejected("קוד שגוי או שפג תוקפו")

        # Anything else is a fault on our side or theirs, not the member's.
        log.error(
            "TextMe validate_otp failed: status=%s message=%s",
            status,
            payload.get("message"),
        )
        raise SmsDeliveryError("האימות נכשל, נסו שוב")


def get_otp_provider() -> OtpProvider:
    sms = settings.sms
    if sms.provider == "textme":
        if sms.configured:
            return TextMeProvider()
        log.error("TextMe selected but credentials are missing; using the mock")
    return MockProvider()


def code_is_returned_to_client() -> bool:
    """Whether the API may echo the code back.

    Only outside production and only with the mock, so a misconfigured
    production deploy can never hand out codes over HTTP.
    """
    return settings.sms.provider == "mock" and not settings.is_production
