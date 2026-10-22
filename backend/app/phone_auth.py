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
from .sms import SmsDeliveryError, code_is_returned_to_client, get_sms_sender


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

    code = generate_code()
    db.add(
        PhoneVerification(
            phone=phone,
            code_hash=_hash_code(phone, code),
            expires_at=now + timedelta(seconds=sms.code_ttl_seconds),
            user_id=user_id,
        )
    )
    await db.flush()

    try:
        await get_sms_sender().send_code(phone, code)
    except SmsDeliveryError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return code if code_is_returned_to_client() else None


async def verify_code(db: AsyncSession, phone: str, code: str) -> PhoneVerification:
    """Check a code, consuming it on success.

    Raises HTTP 400 for a wrong, expired, or already-used code.
    """
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
    # Constant-time, so a wrong code leaks nothing by timing.
    if not hmac.compare_digest(record.code_hash, _hash_code(phone, code.strip())):
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
