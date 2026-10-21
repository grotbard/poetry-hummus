from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from .configuration import settings
from .db import get_db
from .models import User, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def create_session_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.security.session_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.security.secret_key.get_secret_value(), algorithm=ALGORITHM)


def decode_session_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.security.secret_key.get_secret_value(), algorithms=[ALGORITHM])


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key=settings.security.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.security.session_ttl_hours * 3600,
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(settings.security.session_cookie_name, path="/")


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    token = request.cookies.get(settings.security.session_cookie_name)
    if not token:
        # Allow Bearer tokens too, which keeps the API usable from scripts/tests.
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    try:
        payload = decode_session_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")

    user = await db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or disabled")
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role is not UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user
