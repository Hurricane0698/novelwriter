# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ContinuationRun


CONTINUATION_RUN_STATUS_RUNNING = "running"
CONTINUATION_RUN_STATUS_COMPLETED = "completed"
CONTINUATION_RUN_STATUS_FAILED = "failed"
CONTINUATION_RUN_REUSE_CLIENT_REQUEST = "client_request"
CONTINUATION_RUN_REUSE_SEMANTIC_ACTIVE = "semantic_active"
_CLIENT_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


class ContinuationRunConflictError(ValueError):
    """Raised when one client request id is reused for a different payload."""


@dataclass(frozen=True)
class ContinuationRunClaim:
    run_id: int
    owner: bool
    status: str
    reuse_kind: str | None
    delivered_count: int
    continuation_ids: tuple[int, ...]
    debug_summary: dict[str, Any] | None
    error_code: str | None
    error_message: str | None


def normalize_continuation_client_request_id(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if not _CLIENT_REQUEST_ID_RE.fullmatch(normalized):
        raise ValueError(
            "continuation request id must be 1-64 chars of letters, digits, dot, colon, underscore, or dash"
        )
    return normalized


def build_continuation_request_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _serialize_continuation_ids(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    ids: list[int] = []
    for item in value:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return ids


def _to_claim(
    run: ContinuationRun,
    *,
    owner: bool,
    reuse_kind: str | None = None,
) -> ContinuationRunClaim:
    return ContinuationRunClaim(
        run_id=int(run.id),
        owner=owner,
        status=str(run.status),
        reuse_kind=reuse_kind,
        delivered_count=int(run.delivered_count or 0),
        continuation_ids=tuple(_serialize_continuation_ids(run.continuation_ids)),
        debug_summary=dict(run.debug_summary) if isinstance(run.debug_summary, dict) else None,
        error_code=run.error_code,
        error_message=run.error_message,
    )


def _load_active_semantic_continuation_run(
    db: Session,
    *,
    user_id: int,
    novel_id: int,
    semantic_key: str | None,
    exclude_run_id: int | None = None,
) -> ContinuationRun | None:
    if semantic_key is None:
        return None

    query = db.query(ContinuationRun).filter(
        ContinuationRun.user_id == user_id,
        ContinuationRun.novel_id == novel_id,
        ContinuationRun.semantic_key == semantic_key,
        ContinuationRun.status == CONTINUATION_RUN_STATUS_RUNNING,
    )
    if exclude_run_id is not None:
        query = query.filter(ContinuationRun.id != exclude_run_id)
    return query.first()


def claim_continuation_run(
    db: Session,
    *,
    user_id: int,
    novel_id: int,
    client_request_id: str,
    request_hash: str,
    semantic_key: str | None,
    claim_token: str,
) -> ContinuationRunClaim:
    created = ContinuationRun(
        user_id=user_id,
        novel_id=novel_id,
        client_request_id=client_request_id,
        request_hash=request_hash,
        semantic_key=semantic_key,
        claim_token=claim_token,
        status=CONTINUATION_RUN_STATUS_RUNNING,
        delivered_count=0,
        continuation_ids=[],
    )

    while True:
        existing_by_request = (
            db.query(ContinuationRun)
            .filter(
                ContinuationRun.user_id == user_id,
                ContinuationRun.novel_id == novel_id,
                ContinuationRun.client_request_id == client_request_id,
            )
            .first()
        )
        if existing_by_request is not None:
            if existing_by_request.request_hash != request_hash:
                raise ContinuationRunConflictError(
                    "continuation request id was reused with a different request payload"
                )

            if (
                existing_by_request.status == CONTINUATION_RUN_STATUS_FAILED
                and int(existing_by_request.delivered_count or 0) == 0
            ):
                existing_active_semantic = _load_active_semantic_continuation_run(
                    db,
                    user_id=user_id,
                    novel_id=novel_id,
                    semantic_key=semantic_key,
                    exclude_run_id=int(existing_by_request.id),
                )
                if existing_active_semantic is not None:
                    return _to_claim(
                        existing_active_semantic,
                        owner=False,
                        reuse_kind=CONTINUATION_RUN_REUSE_SEMANTIC_ACTIVE,
                    )

                try:
                    result = db.execute(
                        sa.update(ContinuationRun)
                        .where(
                            ContinuationRun.id == existing_by_request.id,
                            ContinuationRun.status == CONTINUATION_RUN_STATUS_FAILED,
                            ContinuationRun.delivered_count == 0,
                        )
                        .values(
                            status=CONTINUATION_RUN_STATUS_RUNNING,
                            semantic_key=semantic_key,
                            claim_token=claim_token,
                            error_code=None,
                            error_message=None,
                            completed_at=None,
                            updated_at=sa.func.now(),
                        )
                    )
                    if result.rowcount > 0:
                        db.commit()
                        refreshed = (
                            db.query(ContinuationRun)
                            .filter(ContinuationRun.id == existing_by_request.id)
                            .first()
                        )
                        if refreshed is None:
                            raise RuntimeError("Continuation run disappeared after takeover")
                        return _to_claim(refreshed, owner=True)
                    db.rollback()
                    continue
                except IntegrityError:
                    db.rollback()
                    existing_active_semantic = _load_active_semantic_continuation_run(
                        db,
                        user_id=user_id,
                        novel_id=novel_id,
                        semantic_key=semantic_key,
                        exclude_run_id=int(existing_by_request.id),
                    )
                    if existing_active_semantic is not None:
                        return _to_claim(
                            existing_active_semantic,
                            owner=False,
                            reuse_kind=CONTINUATION_RUN_REUSE_SEMANTIC_ACTIVE,
                        )
                    continue

            return _to_claim(
                existing_by_request,
                owner=False,
                reuse_kind=CONTINUATION_RUN_REUSE_CLIENT_REQUEST,
            )

        existing_active_semantic = _load_active_semantic_continuation_run(
            db,
            user_id=user_id,
            novel_id=novel_id,
            semantic_key=semantic_key,
        )
        if existing_active_semantic is not None:
            return _to_claim(
                existing_active_semantic,
                owner=False,
                reuse_kind=CONTINUATION_RUN_REUSE_SEMANTIC_ACTIVE,
            )

        db.add(created)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(created)
        return _to_claim(created, owner=True)


def record_continuation_run_result(
    db: Session,
    *,
    run_id: int,
    claim_token: str,
    continuation_id: int,
) -> bool:
    run = db.query(ContinuationRun).filter(ContinuationRun.id == run_id).first()
    if run is None or run.claim_token != claim_token or run.status != CONTINUATION_RUN_STATUS_RUNNING:
        return False

    continuation_ids = _serialize_continuation_ids(run.continuation_ids)
    if continuation_id not in continuation_ids:
        continuation_ids.append(int(continuation_id))
    run.continuation_ids = continuation_ids
    run.delivered_count = len(continuation_ids)
    run.updated_at = datetime.now(timezone.utc)
    db.commit()
    return True


def complete_continuation_run(
    db: Session,
    *,
    run_id: int,
    claim_token: str,
    continuation_ids: list[int],
    debug_summary: dict[str, Any],
) -> bool:
    result = db.execute(
        sa.update(ContinuationRun)
        .where(
            ContinuationRun.id == run_id,
            ContinuationRun.claim_token == claim_token,
            ContinuationRun.status == CONTINUATION_RUN_STATUS_RUNNING,
        )
        .values(
            status=CONTINUATION_RUN_STATUS_COMPLETED,
            continuation_ids=[int(item) for item in continuation_ids],
            delivered_count=len(continuation_ids),
            debug_summary=debug_summary,
            completed_at=datetime.now(timezone.utc),
            updated_at=sa.func.now(),
        )
    )
    if result.rowcount <= 0:
        db.rollback()
        return False
    db.commit()
    return True


def fail_continuation_run(
    db: Session,
    *,
    run_id: int,
    claim_token: str,
    error_code: str,
    error_message: str,
) -> bool:
    result = db.execute(
        sa.update(ContinuationRun)
        .where(
            ContinuationRun.id == run_id,
            ContinuationRun.claim_token == claim_token,
            ContinuationRun.status == CONTINUATION_RUN_STATUS_RUNNING,
        )
        .values(
            status=CONTINUATION_RUN_STATUS_FAILED,
            error_code=error_code[:64],
            error_message=error_message,
            completed_at=datetime.now(timezone.utc),
            updated_at=sa.func.now(),
        )
    )
    if result.rowcount <= 0:
        db.rollback()
        return False
    db.commit()
    return True
