"""Phone normalisation and verification."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.configuration import settings
from app.models import MenuItem, PhoneVerification, User, UserRole
from app.phone import InvalidPhoneNumber, display_phone, normalise_phone
from app.phone_auth import (
    generate_code,
    phone_taken_by_other,
    request_code,
    verify_code,
)


# --- normalisation ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "052-8498629",
        "0528498629",
        "052 849 8629",
        "+972528498629",
        "+972 52 849 8629",
        "972528498629",
        "528498629",
        "00972528498629",
    ],
)
def test_every_way_of_typing_one_number_normalises_the_same(raw):
    """Otherwise one person ends up with several accounts."""
    assert normalise_phone(raw) == "+972528498629"


def test_an_israeli_landline_is_accepted():
    assert normalise_phone("03-6878635") == "+97236878635"


@pytest.mark.parametrize(
    "raw", ["", "   ", "abc", "123", "05", "052-84", "+1", "0000"]
)
def test_junk_is_rejected(raw):
    with pytest.raises(InvalidPhoneNumber):
        normalise_phone(raw)


def test_an_international_number_is_kept():
    assert normalise_phone("+447911123456") == "+447911123456"


def test_display_uses_the_local_form():
    assert display_phone("+972528498629") == "052-849-8629"
    # Anything else is shown as stored.
    assert display_phone("+447911123456") == "+447911123456"


# --- codes -----------------------------------------------------------------


def test_a_code_is_digits_of_the_configured_length():
    code = generate_code()
    assert code.isdigit()
    assert len(code) == settings.sms.code_length


async def test_requesting_a_code_stores_only_its_hash(db):
    """A leaked database must not hand over live codes."""
    code = await request_code(db, "+972528498629")
    await db.commit()

    from sqlalchemy import select

    record = (await db.execute(select(PhoneVerification))).scalars().one()
    assert record.code_hash != code
    assert len(record.code_hash) == 64


async def test_the_right_code_verifies_once(db):
    code = await request_code(db, "+972528498629")
    await db.commit()

    record = await verify_code(db, "+972528498629", code)
    assert record.consumed_at is not None

    # A consumed code cannot be replayed.
    with pytest.raises(HTTPException) as exc:
        await verify_code(db, "+972528498629", code)
    assert exc.value.status_code == 400


async def test_a_wrong_code_is_refused_and_counted(db):
    await request_code(db, "+972528498629")
    await db.commit()

    with pytest.raises(HTTPException):
        await verify_code(db, "+972528498629", "000000")

    from sqlalchemy import select

    record = (await db.execute(select(PhoneVerification))).scalars().one()
    assert record.attempts == 1
    assert record.consumed_at is None


async def test_too_many_wrong_guesses_burns_the_code(db):
    code = await request_code(db, "+972528498629")
    await db.commit()

    for _ in range(settings.sms.max_attempts):
        with pytest.raises(HTTPException):
            await verify_code(db, "+972528498629", "000000")

    # Even the correct code no longer works.
    with pytest.raises(HTTPException) as exc:
        await verify_code(db, "+972528498629", code)
    assert "ניסיונות" in exc.value.detail


async def test_an_expired_code_is_refused(db):
    code = await request_code(db, "+972528498629")
    await db.commit()

    from sqlalchemy import select

    record = (await db.execute(select(PhoneVerification))).scalars().one()
    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await verify_code(db, "+972528498629", code)
    assert "פג" in exc.value.detail


async def test_a_code_cannot_be_used_for_a_different_number(db):
    """The hash is bound to the number it was sent to."""
    code = await request_code(db, "+972528498629")
    await db.commit()

    with pytest.raises(HTTPException):
        await verify_code(db, "+972500000000", code)


async def test_verifying_with_no_outstanding_code_fails(db):
    with pytest.raises(HTTPException) as exc:
        await verify_code(db, "+972528498629", "123456")
    assert exc.value.status_code == 400


# --- rate limiting ---------------------------------------------------------


async def test_a_second_request_is_rate_limited(db):
    await request_code(db, "+972528498629")
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await request_code(db, "+972528498629")
    assert exc.value.status_code == 429


async def test_the_hourly_cap_stops_a_flood(db):
    """Caps SMS spend and stops someone's phone being used as a weapon."""
    phone = "+972528498629"
    now = datetime.now(timezone.utc)
    for i in range(settings.sms.max_per_hour):
        db.add(
            PhoneVerification(
                phone=phone,
                code_hash="x" * 64,
                expires_at=now + timedelta(minutes=5),
                # Spread them out so the cooldown is not what trips.
                created_at=now - timedelta(minutes=50 - i),
            )
        )
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await request_code(db, phone)
    assert exc.value.status_code == 429
    assert "שעה" in exc.value.detail


# --- one number, one account ----------------------------------------------


async def test_a_number_held_by_another_account_is_detected(db, member):
    member.phone = "+972528498629"
    await db.flush()

    other = User(email="other@example.com", role=UserRole.member)
    db.add(other)
    await db.flush()

    assert await phone_taken_by_other(db, "+972528498629", other.id) is True
    assert await phone_taken_by_other(db, "+972528498629", member.id) is False
    assert await phone_taken_by_other(db, "+972500000000", other.id) is False


# --- ordering requires verification ---------------------------------------


async def test_an_unverified_member_cannot_order(db, member):
    from app.security import get_verified_member

    assert member.phone_verified_at is None
    with pytest.raises(HTTPException) as exc:
        await get_verified_member(member)
    assert exc.value.status_code == 403


async def test_a_verified_member_can_order(db, member):
    from app.security import get_verified_member

    member.phone = "+972528498629"
    member.phone_verified_at = datetime.now(timezone.utc)
    await db.flush()

    assert await get_verified_member(member) is member


async def test_the_cooldown_message_never_says_zero_seconds(db):
    """int() truncation rendered a sub-second wait as "try again in 0 seconds"."""
    phone = "+972528498629"
    await request_code(db, phone)
    await db.commit()

    from sqlalchemy import select

    record = (await db.execute(select(PhoneVerification))).scalars().one()
    # Leave a fraction of a second on the clock.
    record.created_at = datetime.now(timezone.utc) - timedelta(
        seconds=settings.sms.resend_cooldown_seconds - 0.4
    )
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await request_code(db, phone)
    assert "0 שניות" not in exc.value.detail
    assert "1 שניות" in exc.value.detail


# --- the admin escape hatch ------------------------------------------------


async def test_an_admin_can_verify_a_members_phone(db, member):
    """Needed for support cases and before a provider is configured."""
    from app.routers.admin import verify_user_phone

    admin = User(email="admin@example.com", role=UserRole.admin)
    db.add(admin)
    await db.flush()

    result = await verify_user_phone(
        member.id, {"phone": "054-2718281"}, admin=admin, db=db
    )
    assert result.phone_verified is True
    assert member.phone == "+972542718281"
    assert member.phone_verified_at is not None


async def test_an_admin_cannot_assign_a_number_twice(db, member):
    from app.routers.admin import verify_user_phone

    admin = User(email="admin@example.com", role=UserRole.admin)
    other = User(email="other@example.com", role=UserRole.member)
    db.add_all([admin, other])
    await db.flush()
    member.phone = "+972542718281"
    await db.flush()

    with pytest.raises(HTTPException) as exc:
        await verify_user_phone(
            other.id, {"phone": "0542718281"}, admin=admin, db=db
        )
    assert exc.value.status_code == 409


async def test_verifying_without_a_number_needs_one_on_file(db, member):
    from app.routers.admin import verify_user_phone

    admin = User(email="admin@example.com", role=UserRole.admin)
    db.add(admin)
    await db.flush()

    assert member.phone is None
    with pytest.raises(HTTPException) as exc:
        await verify_user_phone(member.id, {}, admin=admin, db=db)
    assert exc.value.status_code == 400

    # With a number already on file, no argument is required.
    member.phone = "+972542718281"
    await db.flush()
    result = await verify_user_phone(member.id, {}, admin=admin, db=db)
    assert result.phone_verified is True
