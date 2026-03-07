# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""JWT authentication utilities."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.safety_fuses import ensure_ai_available
from app.database import get_db
from app.models import User

#
# Password hashing
# ----------------
# We intentionally do NOT rely on passlib's bcrypt backend because the
# passlib<->bcrypt compatibility matrix is brittle on newer Python versions.
# Use a stable, stdlib-backed scheme for new hashes, and keep a bcrypt fallback
# verifier for legacy rows.
#
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
SESSION_COOKIE_NAME = "novwr_session"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        # Legacy support: previously stored bcrypt hashes typically start with "$2".
        # Verify them via the bcrypt library directly to avoid passlib backend issues.
        if hashed.startswith("$2"):
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        return pwd_context.verify(plain, hashed)
    except Exception:
        # Auth must never 500 due to a hash backend issue; treat as invalid credentials.
        return False


def create_access_token(data: dict) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {**data, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _request_is_secure(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    return forwarded_proto == "https" or request.url.scheme == "https"


def set_auth_cookie(response: Response, request: Request, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        secure=_request_is_secure(request),
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


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
            hashed_password=hash_password("default"),
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Seed demo novel on first selfhost login (best-effort).
        try:
            from app.core.seed_demo import seed_demo_novel
            seed_demo_novel(db, user)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Failed to seed demo novel for default user")
    return user


def get_current_user_or_default(
    request: Request,
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> User:
    """Unified auth: selfhost auto-creates default user, hosted requires JWT."""
    settings = get_settings()

    if settings.deploy_mode == "selfhost":
        return _get_or_create_default_user(db)

    # hosted mode — token required
    resolved_token = _resolve_token(token, request)
    if not resolved_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_current_user(request=request, token=resolved_token, db=db)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def check_generation_quota(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
) -> User:
    """Dependency stub — validates quota > 0 but does NOT decrement.

    Actual decrement happens via decrement_quota() in the endpoint body,
    where num_versions is known.
    """
    ensure_ai_available(db)

    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return current_user

    if current_user.generation_quota <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Generation quota exhausted. Submit feedback to unlock more.",
        )

    return current_user


def decrement_quota(db: Session, user: User, count: int = 1) -> None:
    """Decrement generation quota by count. Hosted mode only.

    Call this in the endpoint body after validating num_versions.
    """
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return
    if count <= 0:
        return

    result = db.execute(
        sa.update(User)
        .where(User.id == user.id, User.generation_quota >= count)
        .values(generation_quota=User.generation_quota - count)
    )
    if result.rowcount <= 0:
        db.rollback()
        # Refresh for an accurate "have N" message when the caller passes a stale User object.
        try:
            db.refresh(user)
        except Exception:
            pass
        have = getattr(user, "generation_quota", None)
        have_str = str(have) if isinstance(have, int) else "0"
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Not enough quota. Need {count}, have {have_str}. Submit feedback to unlock more.",
        )
    db.commit()
    try:
        db.refresh(user)
    except Exception:
        pass


def reserve_quota(db: Session, user_id: int, count: int = 1) -> None:
    """Reserve quota by atomically decrementing `generation_quota`.

    This is intended for non-stream generation endpoints to avoid a race where:
    - generation succeeds (and writes results) and
    - quota decrement fails under concurrency (lost update / insufficient quota).

    Callers should `refund_quota()` on failure paths so users only pay for
    successful generations.
    """
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return
    if count <= 0:
        return

    ok = try_decrement_quota(db, user_id=user_id, count=count)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Generation quota exhausted. Submit feedback to unlock more."
                if count == 1
                else f"Not enough quota for this request (need {count}). Submit feedback to unlock more."
            ),
        )


def refund_quota(db: Session, user_id: int, count: int = 1) -> None:
    """Refund previously reserved quota (best-effort). Hosted mode only."""
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return
    if count <= 0:
        return

    db.execute(
        sa.update(User)
        .where(User.id == user_id)
        .values(generation_quota=User.generation_quota + count)
    )
    db.commit()


def try_decrement_quota(db: Session, user_id: int, count: int = 1) -> bool:
    """Atomically decrement quota at the SQL level. Returns True on success.

    Unlike decrement_quota(), this never raises — safe to call inside
    async generators where HTTPException can't propagate cleanly.
    """
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return True

    result = db.execute(
        sa.update(User)
        .where(User.id == user_id, User.generation_quota >= count)
        .values(generation_quota=User.generation_quota - count)
    )
    db.commit()
    return result.rowcount > 0
