"""Phone verification: issuing codes and checking them."""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .configuration import settings
from .models import PhoneVerification, User
from .sms import (
    CodeRejected,
    SmsDeliveryError,
    code_is_returned_to_client,
    get_otp_provider,
)


def _hash_code(phone: str, code: str) -> str:
    """Bind the hash to the number so a code cannot be replayed elsewhere."""
    secret = settings.security.secret_key.get_secret_value().encode()
    return hmac.new(secret, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def generate_code() -> str:
    length = settings.sms.code_length
    return "".join(secrets.choice("0123456789") for _ in range(length))


async def request_code(
    db: AsyncSession, phone: str, user_id: int | None = None
) -> str | None:
    """Issue and send a code. Returns it only when the mock is in use.

    Rate limited two ways: a cooldown between requests, and an hourly cap, so
    a hostile caller cannot run up an SMS bill or flood someone's phone.
    """
    now = datetime.now(timezone.utc)
    sms = settings.sms

    recent = (
        await db.execute(
            select(PhoneVerification)
            .where(PhoneVerification.phone == phone)
            .order_by(desc(PhoneVerification.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if recent is not None:
        elapsed = (now - _aware(recent.created_at)).total_seconds()
        if elapsed < sms.resend_cooldown_seconds:
            wait = math.ceil(sms.resend_cooldown_seconds - elapsed)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"נסו שוב בעוד {wait} שניות",
            )

    hour_ago = now - timedelta(hours=1)
    sent_this_hour = (
        await db.execute(
            select(func.count(PhoneVerification.id)).where(
                PhoneVerification.phone == phone,
                PhoneVerification.created_at >= hour_ago,
            )
        )
    ).scalar() or 0
    if sent_this_hour >= sms.max_per_hour:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "נשלחו יותר מדי קודים למספר הזה. נסו שוב בעוד שעה",
        )

    provider = get_otp_provider()
    # TextMe mints and keeps the code itself, so there is nothing to hash
    # here; the row exists only to drive the cooldown and hourly cap.
    code = generate_code() if provider.stores_code_locally else None

    db.add(
        PhoneVerification(
            phone=phone,
            code_hash=_hash_code(phone, code) if code else "",
            expires_at=now + timedelta(minutes=sms.code_valid_minutes),
            user_id=user_id,
        )
    )
    await db.flush()

    try:
        await provider.send_code(phone, code)
    except SmsDeliveryError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return code if code_is_returned_to_client() else None


async def verify_code(db: AsyncSession, phone: str, code: str) -> PhoneVerification:
    """Check a code, consuming it on success.

    Raises HTTP 400 for a wrong, expired, missing, or already-used code.
    """
    if not code or not code.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "קוד אימות חסר")

    provider = get_otp_provider()
    now = datetime.now(timezone.utc)
    record = (
        await db.execute(
            select(PhoneVerification)
            .where(
                PhoneVerification.phone == phone,
                PhoneVerification.consumed_at.is_(None),
            )
            .order_by(desc(PhoneVerification.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    if record is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "לא נמצא קוד פעיל, בקשו קוד חדש"
        )
    if _aware(record.expires_at) <= now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "הקוד פג, בקשו קוד חדש")
    if record.attempts >= settings.sms.max_attempts:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "יותר מדי ניסיונות, בקשו קוד חדש"
        )

    record.attempts += 1

    if provider.stores_code_locally:
        # Constant-time, so a wrong code leaks nothing by timing.
        matched = hmac.compare_digest(
            record.code_hash, _hash_code(phone, code.strip())
        )
    else:
        # The provider is the authority on its own code.
        try:
            await provider.validate_code(phone, code.strip())
            matched = True
        except CodeRejected:
            matched = False
        except SmsDeliveryError as exc:
            await db.flush()
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    if not matched:
        await db.flush()
        remaining = settings.sms.max_attempts - record.attempts
        detail = (
            "קוד שגוי, בקשו קוד חדש"
            if remaining <= 0
            else f"קוד שגוי, נותרו {remaining} ניסיונות"
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail)

    record.consumed_at = now
    await db.flush()
    return record


async def phone_taken_by_other(
    db: AsyncSession, phone: str, user_id: int | None
) -> bool:
    """Whether a verified account other than this one already holds the number."""
    owner = (
        await db.execute(select(User).where(User.phone == phone))
    ).scalar_one_or_none()
    return owner is not None and owner.id != user_id
