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
from ..schemas import AdminLogin, UserOut
from ..security import (
    clear_session_cookie,
    create_session_token,
    get_current_user,
    set_session_cookie,
    verify_password,
)
from ..services import log_activity, record_coins

router = APIRouter(prefix="/api/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

OAUTH_STATE_COOKIE = "poet_oauth_state"


@router.get("/config")
async def auth_config() -> dict:
    """Lets the frontend hide the Google button when OAuth isn't configured."""
    return {"google_enabled": settings.google.configured}


@router.get("/google/login")
async def google_login() -> RedirectResponse:
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
    return user


@router.post("/logout")
async def logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
