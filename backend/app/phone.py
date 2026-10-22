"""Phone number normalisation to E.164.

Members type numbers many ways — 052-849-8629, 0528498629, +972 52 849 8629 —
and all of them must resolve to one stored value, or the same person ends up
with several accounts and a uniqueness constraint that never fires.

Deliberately small rather than pulling in `phonenumbers`: the restaurant is
Israeli, and a local prefix plus a length check covers its customers. The
`+<digits>` branch accepts other countries without validating them deeply.
"""

from __future__ import annotations

import re

from fastapi import HTTPException, status

from .configuration import settings

# Israeli mobile prefixes after the leading zero: 050-059.
_IL_MOBILE = re.compile(r"^5\d{8}$")


class InvalidPhoneNumber(ValueError):
    """The input could not be read as a phone number."""


def normalise_phone(raw: str) -> str:
    """Return the number in E.164 form, e.g. +972528498629.

    Raises InvalidPhoneNumber when the input cannot be a real number.
    """
    if not raw or not raw.strip():
        raise InvalidPhoneNumber("מספר טלפון חסר")

    # Keep digits, and a leading + if present.
    text = raw.strip().replace("‏", "").replace("‎", "")
    plus = text.startswith("+") or text.startswith("00")
    digits = re.sub(r"\D", "", text)
    if text.startswith("00"):
        digits = digits[2:]

    if not digits:
        raise InvalidPhoneNumber("מספר טלפון לא תקין")

    region = settings.sms.default_region_prefix.lstrip("+")

    if plus:
        # Already international.
        if len(digits) < 8 or len(digits) > 15:
            raise InvalidPhoneNumber("מספר טלפון בינלאומי לא תקין")
        return f"+{digits}"

    if digits.startswith("0"):
        # Local form: drop the trunk zero and prepend the region.
        national = digits[1:]
        if not national:
            raise InvalidPhoneNumber("מספר טלפון לא תקין")
        if region == "972" and not _IL_MOBILE.match(national):
            # Landlines are 8 digits after the zero (e.g. 03-6878635).
            if not re.match(r"^[2-49]\d{7}$", national):
                raise InvalidPhoneNumber("מספר טלפון ישראלי לא תקין")
        return f"+{region}{national}"

    if digits.startswith(region):
        return f"+{digits}"

    # Bare national number without the trunk zero, e.g. 528498629.
    if region == "972" and _IL_MOBILE.match(digits):
        return f"+{region}{digits}"

    raise InvalidPhoneNumber("מספר טלפון לא תקין")


def normalise_phone_or_400(raw: str) -> str:
    """As normalise_phone, but raises an HTTP 400 for use in routes."""
    try:
        return normalise_phone(raw)
    except InvalidPhoneNumber as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


def display_phone(e164: str) -> str:
    """Render an Israeli number in the local form people recognise."""
    if e164.startswith("+972") and len(e164) == 13:
        rest = e164[4:]
        return f"0{rest[:2]}-{rest[2:5]}-{rest[5:]}"
    return e164
