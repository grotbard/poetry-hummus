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


# --- the TextMe OTP provider ----------------------------------------------


def _textme_settings(monkeypatch):
    from app.configuration import SmsSettings

    return SmsSettings(
        provider="textme",
        textme_token="tok",
        textme_username="user",
        _env_file=None,
    )


def test_textme_needs_both_a_token_and_a_username():
    from app.configuration import SmsSettings

    base = dict(provider="textme", _env_file=None)
    assert SmsSettings(**base).configured is False
    assert SmsSettings(textme_token="t", **base).configured is False
    assert SmsSettings(textme_username="u", **base).configured is False
    assert SmsSettings(textme_token="t", textme_username="u", **base).configured is True


def test_an_israeli_number_is_sent_in_local_form():
    """TextMe documents 05XXXXXXXX, not E.164."""
    from app.sms import _local_phone

    assert _local_phone("+972542718281") == "0542718281"
    # Anything else loses only the plus.
    assert _local_phone("+447911123456") == "447911123456"


def test_textme_does_not_keep_the_code_locally():
    """The provider owns it, so nothing to hash or store here."""
    from app.sms import MockProvider, TextMeProvider

    assert TextMeProvider.stores_code_locally is False
    assert MockProvider.stores_code_locally is True


async def test_a_rejected_code_is_the_members_fault_not_an_outage(monkeypatch):
    """Status 12 means a wrong code; anything else is a real failure."""
    from app.sms import CodeRejected, SmsDeliveryError, TextMeProvider

    provider = TextMeProvider()

    async def wrong_code(body):
        return {"status": 12, "message": "not validated"}

    monkeypatch.setattr(provider, "_call", wrong_code)
    with pytest.raises(CodeRejected):
        await provider.validate_code("+972542718281", "000000")

    async def provider_broken(body):
        return {"status": 99, "message": "account suspended"}

    monkeypatch.setattr(provider, "_call", provider_broken)
    with pytest.raises(SmsDeliveryError):
        await provider.validate_code("+972542718281", "000000")


async def test_a_good_code_passes(monkeypatch):
    from app.sms import TextMeProvider

    provider = TextMeProvider()

    async def ok(body):
        return {"status": 0, "message": "The code successfully validated"}

    monkeypatch.setattr(provider, "_call", ok)
    await provider.validate_code("+972542718281", "123456")


async def test_a_refused_send_raises(monkeypatch):
    from app.sms import SmsDeliveryError, TextMeProvider

    provider = TextMeProvider()

    async def refused(body):
        return {"status": 7, "message": "sender not verified"}

    monkeypatch.setattr(provider, "_call", refused)
    with pytest.raises(SmsDeliveryError):
        await provider.send_code("+972542718281", None)


async def test_the_send_body_matches_the_documented_shape(monkeypatch):
    """Field names come from TextMe's OpenAPI spec; a typo fails silently."""
    from app.sms import TextMeProvider

    captured: dict = {}
    provider = TextMeProvider()

    async def capture(body):
        captured.update(body)
        return {"status": 0, "code": "448431", "message": "ok"}

    monkeypatch.setattr(provider, "_call", capture)
    await provider.send_code("+972542718281", None)

    sent = captured["send_otp"]
    assert set(sent) >= {"user", "phone", "source"}, "required fields missing"
    assert sent["user"]["username"] == settings.sms.textme_username
    assert sent["phone"] == "0542718281"
    assert "[code]" in sent["text"], "TextMe substitutes [code]"


@pytest.mark.parametrize("code", [None, "", "   "])
async def test_a_missing_code_is_rejected_not_a_crash(db, code):
    """request_code returns None when a real provider is in use, and that
    value reached verify_code as a None .strip() crash."""
    await request_code(db, "+972528498629")
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await verify_code(db, "+972528498629", code)
    assert exc.value.status_code == 400


# --- the admin approval queue ---------------------------------------------


async def test_the_pending_filter_finds_only_members_who_are_stuck(db):
    """The queue must not surface admins, verified members, or blocked ones."""
    from datetime import datetime, timezone

    from app.routers.admin import list_users

    stuck = User(email="stuck@example.com", role=UserRole.member)
    done = User(
        email="done@example.com",
        role=UserRole.member,
        phone="+972500000001",
        phone_verified_at=datetime.now(timezone.utc),
    )
    blocked = User(
        email="blocked@example.com", role=UserRole.member, is_active=False
    )
    boss = User(email="boss@example.com", role=UserRole.admin)
    db.add_all([stuck, done, blocked, boss])
    await db.flush()

    page = await list_users(pending_phone=True, page=1, page_size=25, db=db)
    emails = {row.email for row in page.items}
    assert "stuck@example.com" in emails
    assert "done@example.com" not in emails, "already verified"
    assert "blocked@example.com" not in emails, "disabled accounts are not waiting"
    assert "boss@example.com" not in emails, "admins are exempt"


async def test_the_queue_puts_the_longest_wait_first(db):
    """Triage order: whoever has been stuck longest is served first."""
    from datetime import datetime, timedelta, timezone

    from app.routers.admin import list_users

    now = datetime.now(timezone.utc)
    old = User(
        email="old@example.com", role=UserRole.member, created_at=now - timedelta(days=3)
    )
    new = User(
        email="new@example.com", role=UserRole.member, created_at=now - timedelta(hours=1)
    )
    db.add_all([new, old])
    await db.flush()

    page = await list_users(pending_phone=True, page=1, page_size=25, db=db)
    assert [r.email for r in page.items][:2] == ["old@example.com", "new@example.com"]


async def test_approving_removes_a_member_from_the_queue(db):
    from app.routers.admin import list_users, verify_user_phone

    admin = User(email="boss@example.com", role=UserRole.admin)
    stuck = User(email="stuck@example.com", role=UserRole.member)
    db.add_all([admin, stuck])
    await db.flush()

    assert any(r.email == "stuck@example.com" for r in (await list_users(pending_phone=True, page=1, page_size=25, db=db)).items)

    await verify_user_phone(stuck.id, {"phone": "054-2718281"}, admin=admin, db=db)

    remaining = await list_users(pending_phone=True, page=1, page_size=25, db=db)
    assert not any(r.email == "stuck@example.com" for r in remaining.items)


async def test_the_stats_count_matches_the_queue(db):
    """The tab badge and the list must not disagree."""
    from app.routers.admin import list_users, stats

    db.add_all(
        [
            User(email="a@example.com", role=UserRole.member),
            User(email="b@example.com", role=UserRole.member),
        ]
    )
    await db.flush()

    counted = (await stats(db=db)).pending_phone_approvals
    listed = (await list_users(pending_phone=True, page=1, page_size=25, db=db)).total
    assert counted == listed == 2


# --- asking an admin instead of waiting for an SMS ------------------------


async def test_requesting_approval_creates_an_unverified_account(db):
    """The member gets in but cannot order until a human confirms."""
    from app.routers.admin import list_users
    from app.routers.auth import request_admin_approval
    from app.schemas import AdminApprovalRequest

    class FakeRequest:
        cookies: dict = {}
        client = None

    class FakeResponse:
        def set_cookie(self, *a, **k): ...
        def delete_cookie(self, *a, **k): ...

    result = await request_admin_approval(
        AdminApprovalRequest(
            phone="054-9998887", email="noSMS@example.com", full_name="לא קיבל"
        ),
        request=FakeRequest(),
        response=FakeResponse(),
        db=db,
    )

    assert result.phone_verified is False, "must not shortcut verification"
    queue = await list_users(pending_phone=True, page=1, page_size=25, db=db)
    assert any(r.email == "nosms@example.com" for r in queue.items)


async def test_an_explicit_request_sorts_above_a_passive_signup(db):
    """Someone who asked for help is triaged before someone who stalled."""
    from datetime import datetime, timedelta, timezone

    from app.routers.admin import list_users

    now = datetime.now(timezone.utc)
    # The passive one registered earlier, so date alone would rank it first.
    passive = User(
        email="passive@example.com",
        role=UserRole.member,
        created_at=now - timedelta(days=5),
    )
    asked = User(
        email="asked@example.com",
        role=UserRole.member,
        created_at=now - timedelta(hours=1),
        approval_requested_at=now,
    )
    db.add_all([passive, asked])
    await db.flush()

    queue = await list_users(pending_phone=True, page=1, page_size=25, db=db)
    emails = [r.email for r in queue.items]
    assert emails.index("asked@example.com") < emails.index("passive@example.com")


async def test_approval_cannot_be_requested_for_a_verified_number(db, member):
    from datetime import datetime, timezone

    from app.routers.auth import request_admin_approval_for_me
    from app.schemas import SelfApprovalRequest

    class FakeRequest:
        cookies: dict = {}
        client = None

    member.phone = "+972542718281"
    member.phone_verified_at = datetime.now(timezone.utc)
    await db.flush()

    with pytest.raises(HTTPException) as exc:
        await request_admin_approval_for_me(
            SelfApprovalRequest(phone="054-2718281"),
            request=FakeRequest(),
            user=member,
            db=db,
        )
    assert exc.value.status_code == 400


async def test_a_requested_number_already_held_elsewhere_is_refused(db, member):
    from app.routers.auth import request_admin_approval_for_me
    from app.schemas import SelfApprovalRequest

    class FakeRequest:
        cookies: dict = {}
        client = None

    other = User(email="other@example.com", role=UserRole.member, phone="+972542718281")
    db.add(other)
    await db.flush()

    with pytest.raises(HTTPException) as exc:
        await request_admin_approval_for_me(
            SelfApprovalRequest(phone="054-2718281"),
            request=FakeRequest(),
            user=member,
            db=db,
        )
    assert exc.value.status_code == 409


async def test_the_requested_number_is_recorded_for_the_admin(db, member):
    """The admin needs to see which number to confirm."""
    from app.routers.auth import request_admin_approval_for_me
    from app.schemas import SelfApprovalRequest

    class FakeRequest:
        cookies: dict = {}
        client = None

    await request_admin_approval_for_me(
        SelfApprovalRequest(phone="054-2718281"),
        request=FakeRequest(),
        user=member,
        db=db,
    )
    assert member.phone == "+972542718281"
    assert member.approval_requested_at is not None
    assert member.phone_verified_at is None, "still not verified"
