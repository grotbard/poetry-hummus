import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..configuration import settings
from ..db import get_db
from ..models import CoinTxKind, User, UserRole
from ..phone import InvalidPhoneNumber, normalise_phone, normalise_phone_or_400
from ..phone_auth import phone_taken_by_other, request_code, verify_code
from ..schemas import (
    AdminApprovalRequest,
    AdminLogin,
    MemberLogin,
    SelfApprovalRequest,
    SetPasswordIn,
    PhoneCodeRequest,
    PhoneCodeSent,
    PhoneSignupIn,
    PhoneVerifyIn,
    UserOut,
)
from ..security import (
    clear_session_cookie,
    hash_password,
    create_session_token,
    get_current_user,
    set_session_cookie,
    verify_password,
)
from ..services import attach_referral, expire_coins, log_activity, record_coins

router = APIRouter(prefix="/api/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

OAUTH_STATE_COOKIE = "poet_oauth_state"
REFERRAL_COOKIE = "poet_ref"


@router.get("/config")
async def auth_config() -> dict:
    """Lets the frontend hide the Google button when OAuth isn't configured."""
    return {"google_enabled": settings.google.configured}


@router.get("/google/login")
async def google_login(ref: str | None = None) -> RedirectResponse:
    if not settings.google.configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Google OAuth is not configured on this server",
        )
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.google.client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    response = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")
    # CSRF guard: the state we get back must match this cookie.
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=600,
        path="/",
    )
    # Remember the invite code across the round trip to Google.
    if ref:
        response.set_cookie(
            REFERRAL_COOKIE,
            ref[:16],
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=1800,
            path="/",
        )
    return response


async def _verify_google_id_token(id_token: str) -> dict:
    """Validate the ID token signature and claims against Google's JWKS."""
    async with httpx.AsyncClient(timeout=10) as client:
        jwks = (await client.get(GOOGLE_JWKS_URL)).json()

    try:
        header = jwt.get_unverified_header(id_token)
        key = next(k for k in jwks["keys"] if k["kid"] == header["kid"])
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
        return jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            audience=settings.google.client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
        )
    except (StopIteration, KeyError, jwt.PyJWTError) as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, f"Invalid Google identity token: {exc}"
        ) from exc


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if error:
        return RedirectResponse(f"{settings.frontend_url}/login?error={error}")
    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing authorization code")

    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not expected_state or not state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth state mismatch")

    async with httpx.AsyncClient(timeout=10) as client:
        token_res = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google.client_id,
                "client_secret": settings.google.client_secret.get_secret_value(),
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if token_res.status_code != 200:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, f"Google token exchange failed: {token_res.text}"
        )

    id_token = token_res.json().get("id_token")
    if not id_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google response had no id_token")

    claims = await _verify_google_id_token(id_token)
    if not claims.get("email_verified", False):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google email is not verified")

    sub = claims["sub"]
    email = claims["email"].lower()

    user = (
        await db.execute(select(User).where(User.google_sub == sub))
    ).scalar_one_or_none()
    if user is None:
        # Link to a pre-existing account with the same email (e.g. seeded admin).
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

    is_new = user is None
    if is_new:
        user = User(
            email=email,
            google_sub=sub,
            full_name=claims.get("name", ""),
            picture_url=claims.get("picture"),
            role=UserRole.member,
        )
        db.add(user)
        await db.flush()
        if settings.loyalty.signup_bonus_coins:
            await record_coins(
                db,
                user,
                settings.loyalty.signup_bonus_coins,
                CoinTxKind.signup_bonus,
                reason="בונוס הרשמה למועדון",
            )
        await log_activity(db, "user.registered", user_id=user.id, details={"via": "google"})
        # A bad or missing code must never block the signup.
        invite_code = request.cookies.get(REFERRAL_COOKIE)
        if invite_code:
            await attach_referral(db, user, invite_code)
    else:
        user.google_sub = sub
        if claims.get("picture"):
            user.picture_url = claims["picture"]
        if claims.get("name") and not user.full_name:
            user.full_name = claims["name"]

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been disabled")

    user.last_login_at = datetime.now(timezone.utc)
    await log_activity(
        db,
        "user.login",
        user_id=user.id,
        details={"via": "google"},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    target = "/admin" if user.role is UserRole.admin else "/"
    response = RedirectResponse(f"{settings.frontend_url}{target}")
    set_session_cookie(response, create_session_token(user))
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    response.delete_cookie(REFERRAL_COOKIE, path="/")
    return response


@router.post("/admin/login", response_model=UserOut)
async def admin_login(
    payload: AdminLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Email + password sign-in, restricted to admin accounts."""
    user = (
        await db.execute(select(User).where(User.email == payload.email.lower()))
    ).scalar_one_or_none()

    if (
        user is None
        or not user.password_hash
        or not verify_password(payload.password, user.password_hash)
        or user.role is not UserRole.admin
    ):
        # Deliberately vague, so this can't be used to enumerate admins.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been disabled")

    user.last_login_at = datetime.now(timezone.utc)
    await log_activity(
        db,
        "admin.login",
        user_id=user.id,
        details={"via": "password"},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    set_session_cookie(response, create_session_token(user))
    return UserOut.from_user(user)


# ---------------------------------------------------------------------------
# Phone verification
#
# Two entry points: sign up with a phone number (plus an email), or attach a
# verified number to an account that signed in with Google. Either way every
# member ends up with a confirmed number, which the kitchen relies on.
# ---------------------------------------------------------------------------


@router.post("/phone/request", response_model=PhoneCodeSent)
async def request_phone_code(
    payload: PhoneCodeRequest,
    db: AsyncSession = Depends(get_db),
) -> PhoneCodeSent:
    """Send a verification code. Open, so signup can start here."""
    phone = normalise_phone_or_400(payload.phone)
    dev_code = await request_code(db, phone)
    await db.commit()
    return PhoneCodeSent(
        ok=True,
        phone=phone,
        resend_in_seconds=settings.sms.resend_cooldown_seconds,
        dev_code=dev_code,
    )


@router.post("/phone/signup", response_model=UserOut)
async def phone_signup(
    payload: PhoneSignupIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Create or sign in to an account identified by a verified phone number."""
    phone = normalise_phone_or_400(payload.phone)
    await verify_code(db, phone, payload.code)

    email = payload.email.lower()
    user = (
        await db.execute(select(User).where(User.phone == phone))
    ).scalar_one_or_none()

    if user is None:
        # The email may already belong to a Google account; link rather than
        # create a duplicate member.
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            if existing.phone and existing.phone != phone:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "לכתובת המייל הזו מחובר מספר טלפון אחר",
                )
            user = existing
            user.phone = phone
        else:
            user = User(
                email=email,
                full_name=payload.full_name.strip(),
                phone=phone,
                role=UserRole.member,
                password_hash=(
                    hash_password(payload.password) if payload.password else None
                ),
            )
            db.add(user)
            await db.flush()
            if settings.loyalty.signup_bonus_coins:
                await record_coins(
                    db,
                    user,
                    settings.loyalty.signup_bonus_coins,
                    CoinTxKind.signup_bonus,
                    reason="בונוס הרשמה למועדון",
                )
            await log_activity(
                db, "user.registered", user_id=user.id, details={"via": "phone"}
            )
            invite = payload.ref or request.cookies.get(REFERRAL_COOKIE)
            if invite:
                await attach_referral(db, user, invite)

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been disabled")

    if payload.password and not user.password_hash:
        user.password_hash = hash_password(payload.password)

    user.phone_verified_at = datetime.now(timezone.utc)
    user.last_login_at = datetime.now(timezone.utc)
    await log_activity(
        db,
        "phone.verified",
        user_id=user.id,
        details={"via": "signup"},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(user)

    set_session_cookie(response, create_session_token(user))
    response.delete_cookie(REFERRAL_COOKIE, path="/")
    return UserOut.from_user(user)


@router.post("/phone/request-approval", response_model=UserOut)
async def request_admin_approval(
    payload: AdminApprovalRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Create the account unverified and queue it for an admin.

    The fallback when the SMS never arrives. The member is signed in but
    cannot order until an admin confirms the number, so a bogus request buys
    nothing — it only puts a row in front of a human.
    """
    phone = normalise_phone_or_400(payload.phone)
    email = payload.email.lower()

    user = (
        await db.execute(select(User).where(User.phone == phone))
    ).scalar_one_or_none()
    if user is None:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            full_name=payload.full_name.strip(),
            phone=phone,
            role=UserRole.member,
            password_hash=(
                hash_password(payload.password) if payload.password else None
            ),
        )
        db.add(user)
        await db.flush()
        if settings.loyalty.signup_bonus_coins:
            await record_coins(
                db,
                user,
                settings.loyalty.signup_bonus_coins,
                CoinTxKind.signup_bonus,
                reason="בונוס הרשמה למועדון",
            )
        await log_activity(
            db, "user.registered", user_id=user.id, details={"via": "phone_approval"}
        )
        invite = payload.ref or request.cookies.get(REFERRAL_COOKIE)
        if invite:
            await attach_referral(db, user, invite)
    else:
        if user.phone and user.phone != phone:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "לכתובת המייל הזו מחובר מספר טלפון אחר",
            )
        if user.phone_verified_at is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "המספר כבר מאומת — אפשר להתחבר רגיל",
            )
        user.phone = phone

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been disabled")

    user.approval_requested_at = datetime.now(timezone.utc)
    user.last_login_at = datetime.now(timezone.utc)
    await log_activity(
        db,
        "phone.approval_requested",
        user_id=user.id,
        details={"phone": phone},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(user)

    # Signed in, but the verification gate still blocks ordering.
    set_session_cookie(response, create_session_token(user))
    response.delete_cookie(REFERRAL_COOKIE, path="/")
    return UserOut.from_user(user)


@router.post("/phone/request-approval-self", response_model=UserOut)
async def request_admin_approval_for_me(
    payload: SelfApprovalRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Same fallback, for a member already signed in through Google."""
    if user.phone_verified_at is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "מספר הטלפון שלכם כבר מאומת"
        )

    phone = normalise_phone_or_400(payload.phone)
    if await phone_taken_by_other(db, phone, user.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "מספר הטלפון הזה משויך לחשבון אחר"
        )
    # Record it unverified so the admin sees which number to confirm.
    user.phone = phone
    user.approval_requested_at = datetime.now(timezone.utc)
    await log_activity(
        db,
        "phone.approval_requested",
        user_id=user.id,
        details={"phone": phone, "via": "gate"},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(user)
    return UserOut.from_user(user)


@router.post("/phone/verify", response_model=UserOut)
async def verify_my_phone(
    payload: PhoneVerifyIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Attach a verified number to the signed-in account."""
    phone = normalise_phone_or_400(payload.phone)
    if await phone_taken_by_other(db, phone, user.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "מספר הטלפון הזה משויך לחשבון אחר"
        )

    await verify_code(db, phone, payload.code)
    user.phone = phone
    user.phone_verified_at = datetime.now(timezone.utc)
    await log_activity(
        db,
        "phone.verified",
        user_id=user.id,
        details={"via": "profile"},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(user)
    return UserOut.from_user(user)


@router.post("/login", response_model=UserOut)
async def member_login(
    payload: MemberLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Sign in with a password, by phone number or email.

    Only available once the number is verified: before that the member has
    not proved the phone is theirs, so a password alone must not let them in.
    """
    identifier = payload.identifier.strip()

    # An "@" means it can only be an email; otherwise try to read a phone and
    # fall back to treating it as an email, so a typo is not misread.
    user: User | None = None
    if "@" not in identifier:
        try:
            phone = normalise_phone(identifier)
        except InvalidPhoneNumber:
            phone = None
        if phone:
            user = (
                await db.execute(select(User).where(User.phone == phone))
            ).scalar_one_or_none()
    if user is None:
        user = (
            await db.execute(select(User).where(User.email == identifier.lower()))
        ).scalar_one_or_none()

    if (
        user is None
        or not user.password_hash
        or not verify_password(payload.password, user.password_hash)
    ):
        # Deliberately vague: this must not reveal which accounts exist.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "מספר/אימייל או סיסמה שגויים"
        )
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been disabled")
    if user.phone_verified_at is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "המספר עדיין לא אומת — השלימו את האימות או בקשו אישור מנהל",
        )

    user.last_login_at = datetime.now(timezone.utc)
    await log_activity(
        db,
        "user.login",
        user_id=user.id,
        details={"via": "password"},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(user)

    set_session_cookie(response, create_session_token(user))
    return UserOut.from_user(user)


@router.post("/password", response_model=UserOut)
async def set_my_password(
    payload: SetPasswordIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Set or replace the signed-in member's password."""
    user.password_hash = hash_password(payload.password)
    await log_activity(db, "user.password_set", user_id=user.id, details={})
    await db.commit()
    await db.refresh(user)
    return UserOut.from_user(user)


@router.post("/logout")
async def logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    # Expiry is applied lazily on read, so no scheduled job is required.
    if await expire_coins(db, user):
        await db.commit()
        await db.refresh(user)
    return UserOut.from_user(user)
