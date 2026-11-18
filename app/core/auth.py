# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""JWT authentication utilities."""

import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User


logger = logging.getLogger(__name__)
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
SESSION_COOKIE_NAME = "novwr_session"


def create_access_token(data: dict) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {**data, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def request_is_secure(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    return forwarded_proto == "https" or request.url.scheme == "https"


def set_auth_cookie(response: Response, request: Request, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        secure=request_is_secure(request),
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def issue_user_session(*, response: Response, request: Request, user: User) -> str:
    token = create_access_token({"sub": user.username})
    set_auth_cookie(response, request, token)
    return token


def _resolve_token(token: str | None, request: Request) -> str | None:
    if token:
        return token
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    return cookie_token or None


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    resolved_token = _resolve_token(token, request)
    if not resolved_token:
        raise credentials_exc

    try:
        payload = jwt.decode(resolved_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exc
    except jwt.PyJWTError:
        raise credentials_exc

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exc
    return user


def _get_or_create_default_user(db: Session) -> User:
    """Get or create the default selfhost user."""
    user = db.query(User).filter(User.username == "default").first()
    if user is None:
        user = User(
            username="default",
            hashed_password="!",
            role="admin",
            is_active=True,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.query(User).filter(User.username == "default").first()
            if user is None:
                raise
            return user
        db.refresh(user)

        # Seed demo novel on first selfhost login (best-effort).
        try:
            from app.core.seed_demo import seed_demo_novel
            seed_demo_novel(db, user)
        except Exception:
            logger.exception("Failed to seed demo novel for default user")
    return user


def get_current_user_or_default(db: Session = Depends(get_db)) -> User:
    return _get_or_create_default_user(db)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
