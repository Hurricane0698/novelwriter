# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""JWT authentication utilities."""

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.llm_request import resolve_generation_billing_source
from app.core.safety_fuses import ensure_ai_available
from app.database import get_db
from app.models import QuotaReservation, User


logger = logging.getLogger(__name__)
_QUOTA_RESERVATION_OWNER_TOKEN = uuid4().hex

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


def _resolve_generation_billing_source(request: Request) -> str:
    return resolve_generation_billing_source(request)


def check_generation_quota(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
) -> User:
    """Dependency stub — validates quota > 0 but does NOT decrement.

    Actual decrement happens via decrement_quota() in the endpoint body,
    where num_versions is known.
    """
    ensure_ai_available(db, billing_source=_resolve_generation_billing_source(request))

    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return current_user

    if reconcile_abandoned_quota_reservations(db, user_id=current_user.id) > 0:
        try:
            db.refresh(current_user)
        except Exception:
            pass

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


def reconcile_abandoned_quota_reservations(db: Session, *, user_id: int | None = None) -> int:
    """Refund open reservations left behind by a dead process.

    Reservations are leased to the current process via `_QUOTA_RESERVATION_OWNER_TOKEN`.
    In the current single-process hosted architecture, any open row from another
    lease token is abandoned and safe to reconcile immediately.
    """
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return 0

    stmt = sa.select(QuotaReservation).where(
        QuotaReservation.released_at.is_(None),
        QuotaReservation.lease_token != _QUOTA_RESERVATION_OWNER_TOKEN,
    )
    if user_id is not None:
        stmt = stmt.where(QuotaReservation.user_id == user_id)

    reservations = list(db.execute(stmt).scalars())
    if not reservations:
        return 0

    refunded_by_user: dict[int, int] = {}
    released_at = datetime.now(timezone.utc)

    for reservation in reservations:
        unused = max(0, int(reservation.reserved_count) - int(reservation.charged_count))
        if unused > 0:
            refunded_by_user[reservation.user_id] = refunded_by_user.get(reservation.user_id, 0) + unused
        reservation.released_at = released_at
        reservation.updated_at = released_at

    for orphan_user_id, refunded in refunded_by_user.items():
        db.execute(
            sa.update(User)
            .where(User.id == orphan_user_id)
            .values(generation_quota=User.generation_quota + refunded)
        )

    db.commit()

    refunded_total = sum(refunded_by_user.values())
    if refunded_total > 0:
        logger.warning(
            "Recovered %s quota from abandoned reservations",
            refunded_total,
        )
    return refunded_total


def open_quota_reservation(db: Session, user_id: int, count: int = 1) -> int | None:
    """Reserve quota and create a durable reservation row in one transaction."""
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return None
    if count <= 0:
        return None

    reconcile_abandoned_quota_reservations(db, user_id=user_id)

    result = db.execute(
        sa.update(User)
        .where(User.id == user_id, User.generation_quota >= count)
        .values(generation_quota=User.generation_quota - count)
    )
    if result.rowcount <= 0:
        db.rollback()
        user = db.query(User).filter(User.id == user_id).first()
        have = getattr(user, "generation_quota", 0)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Generation quota exhausted. Submit feedback to unlock more."
                if count == 1
                else f"Not enough quota for this request (need {count}, have {have}). Submit feedback to unlock more."
            ),
        )

    reservation = QuotaReservation(
        user_id=user_id,
        reserved_count=count,
        charged_count=0,
        lease_token=_QUOTA_RESERVATION_OWNER_TOKEN,
    )
    db.add(reservation)
    db.flush()
    reservation_id = int(reservation.id)
    db.commit()
    return reservation_id


def finalize_quota_reservation(db: Session, reservation_id: int) -> tuple[int, int]:
    """Close a durable reservation and refund any unused quota."""
    reservation = (
        db.query(QuotaReservation)
        .filter(QuotaReservation.id == reservation_id)
        .first()
    )
    if not reservation or reservation.released_at is not None:
        return 0, 0

    charged = int(reservation.charged_count)
    unused = max(0, int(reservation.reserved_count) - charged)
    if unused > 0:
        db.execute(
            sa.update(User)
            .where(User.id == reservation.user_id)
            .values(generation_quota=User.generation_quota + unused)
        )

    released_at = datetime.now(timezone.utc)
    reservation.released_at = released_at
    reservation.updated_at = released_at
    db.commit()
    return charged, unused


class QuotaScope:
    """Tracks how many variants were actually delivered during a generation.

    Usage::

        scope = QuotaScope(db, user_id, count=num_versions)
        scope.reserve()          # pre-deduct quota (raises 429 if insufficient)
        ...
        scope.charge(1)          # mark one variant as successfully delivered
        ...
        scope.finalize()         # refund (reserved - charged); call in finally

    Both streaming and non-streaming endpoints use the same lifecycle, ensuring
    the invariant: users only pay for variants they actually received.
    """

    def __init__(self, db: Session, user_id: int, count: int = 1):
        self.db = db
        self.user_id = user_id
        self.reserved = count
        self.charged = 0
        self._active = False
        self.reservation_id: int | None = None

    def reserve(self) -> None:
        """Pre-deduct quota and persist a reservation row."""
        self.reservation_id = open_quota_reservation(self.db, self.user_id, count=self.reserved)
        self._active = True

    def charge(self, n: int = 1) -> None:
        """Mark *n* variants as successfully delivered and persist the charge."""
        if not self._active or n <= 0:
            return

        next_total = self.charged + n
        if next_total > self.reserved:
            raise ValueError(f"Quota charge exceeds reservation: {next_total} > {self.reserved}")

        if self.reservation_id is None:
            self.charged = next_total
            return

        result = self.db.execute(
            sa.update(QuotaReservation)
            .where(
                QuotaReservation.id == self.reservation_id,
                QuotaReservation.released_at.is_(None),
                QuotaReservation.charged_count + n <= QuotaReservation.reserved_count,
            )
            .values(
                charged_count=QuotaReservation.charged_count + n,
                updated_at=sa.func.now(),
            )
        )
        if result.rowcount <= 0:
            self.db.rollback()
            raise RuntimeError("Failed to persist quota charge")

        self.db.commit()
        self.charged = next_total

    def finalize(self) -> None:
        """Refund unreceived variants. Safe to call multiple times."""
        if not self._active:
            return

        if self.reservation_id is not None:
            charged, _unused = finalize_quota_reservation(self.db, self.reservation_id)
            self.charged = charged

        self.reservation_id = None
        self._active = False


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

    reconcile_abandoned_quota_reservations(db, user_id=user_id)

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
