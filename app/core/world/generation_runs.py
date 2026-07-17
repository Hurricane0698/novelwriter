# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import WorldGenerationRun


WORLD_GENERATION_RUN_STATUS_RUNNING = "running"
WORLD_GENERATION_RUN_STATUS_COMPLETED = "completed"
WORLD_GENERATION_RUN_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class WorldGenerationRunClaim:
    run_id: int
    owner: bool
    status: str


def _to_claim(run: WorldGenerationRun, *, owner: bool) -> WorldGenerationRunClaim:
    return WorldGenerationRunClaim(
        run_id=int(run.id),
        owner=owner,
        status=str(run.status),
    )


def claim_world_generation_run(
    db: Session,
    *,
    user_id: int,
    novel_id: int,
    claim_token: str,
) -> WorldGenerationRunClaim:
    created = WorldGenerationRun(
        user_id=user_id,
        novel_id=novel_id,
        claim_token=claim_token,
        status=WORLD_GENERATION_RUN_STATUS_RUNNING,
    )

    while True:
        existing = (
            db.query(WorldGenerationRun)
            .filter(
                WorldGenerationRun.user_id == user_id,
                WorldGenerationRun.novel_id == novel_id,
                WorldGenerationRun.status == WORLD_GENERATION_RUN_STATUS_RUNNING,
            )
            .first()
        )
        if existing is not None:
            return _to_claim(existing, owner=False)

        db.add(created)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(created)
        return _to_claim(created, owner=True)


def complete_world_generation_run(
    db: Session,
    *,
    run_id: int,
    claim_token: str,
) -> bool:
    result = db.execute(
        sa.update(WorldGenerationRun)
        .where(
            WorldGenerationRun.id == run_id,
            WorldGenerationRun.claim_token == claim_token,
            WorldGenerationRun.status == WORLD_GENERATION_RUN_STATUS_RUNNING,
        )
        .values(
            status=WORLD_GENERATION_RUN_STATUS_COMPLETED,
            completed_at=datetime.now(timezone.utc),
            updated_at=sa.func.now(),
        )
    )
    if result.rowcount <= 0:
        db.rollback()
        return False
    db.commit()
    return True


def fail_world_generation_run(
    db: Session,
    *,
    run_id: int,
    claim_token: str,
    error_code: str,
    error_message: str,
) -> bool:
    result = db.execute(
        sa.update(WorldGenerationRun)
        .where(
            WorldGenerationRun.id == run_id,
            WorldGenerationRun.claim_token == claim_token,
            WorldGenerationRun.status == WORLD_GENERATION_RUN_STATUS_RUNNING,
        )
        .values(
            status=WORLD_GENERATION_RUN_STATUS_FAILED,
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
