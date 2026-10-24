"""Password sign-in for members who signed up by phone."""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.models import User, UserRole
from app.routers.auth import member_login, set_my_password
from app.schemas import MemberLogin, SetPasswordIn
from app.security import hash_password


class FakeRequest:
    cookies: dict = {}
    client = None


class FakeResponse:
    def set_cookie(self, *a, **k): ...
    def delete_cookie(self, *a, **k): ...


async def _member(db, *, verified: bool = True, password: str | None = "hunter2222"):
    user = User(
        email="member@example.com",
        full_name="חבר",
        phone="+972542718281",
        role=UserRole.member,
        password_hash=hash_password(password) if password else None,
        phone_verified_at=datetime.now(timezone.utc) if verified else None,
    )
    db.add(user)
    await db.flush()
    return user


async def _login(db, identifier: str, password: str):
    return await member_login(
        MemberLogin(identifier=identifier, password=password),
        request=FakeRequest(),
        response=FakeResponse(),
        db=db,
    )


# --- signing in ------------------------------------------------------------


@pytest.mark.parametrize(
    "identifier",
    ["+972542718281", "0542718281", "054-271-8281", "member@example.com"],
)
async def test_either_the_phone_or_the_email_works(db, identifier):
    await _member(db)
    result = await _login(db, identifier, "hunter2222")
    assert result.email == "member@example.com"


async def test_the_wrong_password_is_refused(db):
    await _member(db)
    with pytest.raises(HTTPException) as exc:
        await _login(db, "0542718281", "not-the-password")
    assert exc.value.status_code == 401


async def test_an_unknown_identifier_fails_the_same_way(db):
    """The message must not reveal whether an account exists."""
    await _member(db)
    with pytest.raises(HTTPException) as unknown:
        await _login(db, "054-000-0000", "hunter2222")
    with pytest.raises(HTTPException) as wrong:
        await _login(db, "0542718281", "wrong-password")
    assert unknown.value.status_code == wrong.value.status_code == 401
    assert unknown.value.detail == wrong.value.detail


async def test_an_account_without_a_password_cannot_sign_in(db):
    """A Google-only member has no password, so no password should open it."""
    await _member(db, password=None)
    with pytest.raises(HTTPException) as exc:
        await _login(db, "0542718281", "any-guess-at-all")
    assert exc.value.status_code == 401


async def test_an_unverified_member_is_turned_away(db):
    """A password alone must not stand in for proving the number."""
    await _member(db, verified=False)
    with pytest.raises(HTTPException) as exc:
        await _login(db, "0542718281", "hunter2222")
    assert exc.value.status_code == 403
    assert "אומת" in exc.value.detail


async def test_a_disabled_account_is_turned_away(db):
    user = await _member(db)
    user.is_active = False
    await db.flush()
    with pytest.raises(HTTPException) as exc:
        await _login(db, "0542718281", "hunter2222")
    assert exc.value.status_code == 403


async def test_a_mistyped_email_is_not_read_as_a_phone(db):
    await _member(db)
    with pytest.raises(HTTPException) as exc:
        await _login(db, "member@exampl.com", "hunter2222")
    assert exc.value.status_code == 401


# --- setting a password ----------------------------------------------------


async def test_a_member_can_set_a_password_and_then_use_it(db):
    user = await _member(db, password=None)
    assert user.password_hash is None

    result = await set_my_password(SetPasswordIn(password="brand-new-pw"), user=user, db=db)
    assert result.has_password is True

    signed_in = await _login(db, "0542718281", "brand-new-pw")
    assert signed_in.email == "member@example.com"


async def test_the_password_is_hashed_not_stored(db):
    user = await _member(db, password=None)
    await set_my_password(SetPasswordIn(password="plaintext-never"), user=user, db=db)
    assert user.password_hash != "plaintext-never"
    assert user.password_hash.startswith("$2")


async def test_a_short_password_is_rejected(db):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SetPasswordIn(password="short")
