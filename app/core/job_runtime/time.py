from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def resolve_lease_expiry(now: datetime, lease_seconds: int) -> datetime | None:
    if lease_seconds <= 0:
        return None
    return now + timedelta(seconds=lease_seconds)
