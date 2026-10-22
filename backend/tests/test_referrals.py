"""Invite a friend: codes, payout timing, and the cap."""

import pytest

from app.configuration import settings
from app.models import MenuItem, OrderStatus, Referral, User, UserRole
from app.services import (
    advance_order_status,
    attach_referral,
    complete_referral_if_due,
    create_order,
    get_or_create_referral_code,
    paid_referral_count,
)

INVITER_COINS = settings.loyalty.referral_inviter_coins
INVITEE_COINS = settings.loyalty.referral_invitee_coins
MAX_FRIENDS = settings.loyalty.referral_max_friends


async def _member(db, email: str) -> User:
    user = User(email=email, full_name=email.split("@")[0], role=UserRole.member)
    db.add(user)
    await db.flush()
    return user


async def _collected_order(db, user, price: int = 10000):
    item = MenuItem(name_he="חומוס", category="hummus", price_agorot=price)
    db.add(item)
    await db.flush()
    order = await create_order(db, user, [(item.id, 1)], "", 0)
    for state in (OrderStatus.preparing, OrderStatus.ready, OrderStatus.collected):
        await advance_order_status(db, order, state)
    return order


def test_the_configured_terms():
    assert INVITER_COINS == 3
    assert INVITEE_COINS == 3
    assert MAX_FRIENDS == 10


# --- codes -----------------------------------------------------------------


async def test_a_code_is_minted_once_and_reused(db, member):
    first = await get_or_create_referral_code(db, member)
    assert len(first) == 8
    assert await get_or_create_referral_code(db, member) == first


async def test_codes_avoid_ambiguous_characters(db):
    """Codes get read aloud, so 0/O and 1/I/L must not appear."""
    for i in range(25):
        user = await _member(db, f"c{i}@example.com")
        code = await get_or_create_referral_code(db, user)
        assert not set(code) & set("01OIL")


async def test_codes_are_distinct(db):
    codes = set()
    for i in range(30):
        user = await _member(db, f"d{i}@example.com")
        codes.add(await get_or_create_referral_code(db, user))
    assert len(codes) == 30


# --- joining ---------------------------------------------------------------


async def test_friend_gets_bonus_coins_on_joining(db, member):
    code = await get_or_create_referral_code(db, member)
    friend = await _member(db, "friend@example.com")

    referral = await attach_referral(db, friend, code)
    await db.commit()

    assert referral is not None
    assert friend.coin_balance == INVITEE_COINS
    assert referral.invitee_coins == INVITEE_COINS


async def test_the_inviter_is_not_paid_at_signup(db, member):
    """Only a completed order pays the inviter."""
    code = await get_or_create_referral_code(db, member)
    friend = await _member(db, "friend@example.com")
    await attach_referral(db, friend, code)
    await db.commit()

    assert member.coin_balance == 0
    assert await paid_referral_count(db, member.id) == 0


async def test_a_lowercase_code_still_works(db, member):
    code = await get_or_create_referral_code(db, member)
    friend = await _member(db, "friend@example.com")
    assert await attach_referral(db, friend, code.lower()) is not None


@pytest.mark.parametrize("code", ["", "NOPE1234", "   ", "XXXXXXXX"])
async def test_an_unknown_code_is_ignored_rather_than_failing(db, code):
    """A bad link must never block someone's signup."""
    friend = await _member(db, "friend@example.com")
    assert await attach_referral(db, friend, code) is None
    assert friend.coin_balance == 0


async def test_self_referral_is_refused(db, member):
    code = await get_or_create_referral_code(db, member)
    assert await attach_referral(db, member, code) is None
    assert member.coin_balance == 0


async def test_a_member_can_only_be_invited_once(db, member):
    first_code = await get_or_create_referral_code(db, member)
    other = await _member(db, "other@example.com")
    second_code = await get_or_create_referral_code(db, other)
    friend = await _member(db, "friend@example.com")

    assert await attach_referral(db, friend, first_code) is not None
    await db.commit()
    assert await attach_referral(db, friend, second_code) is None
    assert friend.coin_balance == INVITEE_COINS, "no second joining bonus"


async def test_a_disabled_inviter_cannot_recruit(db, member):
    code = await get_or_create_referral_code(db, member)
    member.is_active = False
    await db.flush()

    friend = await _member(db, "friend@example.com")
    assert await attach_referral(db, friend, code) is None


# --- payout ----------------------------------------------------------------


async def test_the_inviter_is_paid_on_the_friends_first_order(db, member):
    code = await get_or_create_referral_code(db, member)
    friend = await _member(db, "friend@example.com")
    await attach_referral(db, friend, code)
    await db.commit()

    await _collected_order(db, friend)
    await db.commit()

    assert member.coin_balance == INVITER_COINS
    assert await paid_referral_count(db, member.id) == 1


async def test_a_second_order_pays_nothing_more(db, member):
    code = await get_or_create_referral_code(db, member)
    friend = await _member(db, "friend@example.com")
    await attach_referral(db, friend, code)
    await db.commit()

    await _collected_order(db, friend)
    await db.commit()
    assert member.coin_balance == INVITER_COINS

    await _collected_order(db, friend)
    await db.commit()
    assert member.coin_balance == INVITER_COINS, "one payout per friend"


async def test_an_order_from_an_uninvited_member_pays_no_one(db, member):
    order = await _collected_order(db, member)
    await db.commit()
    assert await complete_referral_if_due(db, order) == 0


async def test_the_cap_stops_payouts_after_ten_friends(db, member):
    code = await get_or_create_referral_code(db, member)

    for i in range(MAX_FRIENDS):
        friend = await _member(db, f"f{i}@example.com")
        await attach_referral(db, friend, code)
        await _collected_order(db, friend)
    await db.commit()

    assert member.coin_balance == MAX_FRIENDS * INVITER_COINS
    assert await paid_referral_count(db, member.id) == MAX_FRIENDS

    # The eleventh friend still gets their own bonus, but pays the inviter nothing.
    extra = await _member(db, "extra@example.com")
    await attach_referral(db, extra, code)
    await _collected_order(db, extra)
    await db.commit()

    assert extra.coin_balance >= INVITEE_COINS
    assert member.coin_balance == MAX_FRIENDS * INVITER_COINS, "cap holds"


async def test_a_capped_invitation_is_not_retried_forever(db, member):
    """Marking it complete stops every later order rescanning it."""
    code = await get_or_create_referral_code(db, member)
    for i in range(MAX_FRIENDS):
        friend = await _member(db, f"g{i}@example.com")
        await attach_referral(db, friend, code)
        await _collected_order(db, friend)
    await db.commit()

    extra = await _member(db, "extra@example.com")
    await attach_referral(db, extra, code)
    await _collected_order(db, extra)
    await db.commit()

    referral = (
        await db.execute(
            Referral.__table__.select().where(Referral.invitee_id == extra.id)
        )
    ).first()
    assert referral.completed_at is not None
    assert referral.inviter_coins == 0
