# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import WorldGenerationRun


WORLD_GENERATION_RUN_STATUS_RUNNING = "running"
WORLD_GENERATION_RUN_STATUS_COMPLETED = "completed"
WORLD_GENERATION_RUN_STATUS_FAILED = "failed"


def claim_world_generation_run(
    db: Session, *, user_id: int, novel_id: int, claim_token: str,
) -> int | None:
    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
    statement = (
        insert(WorldGenerationRun)
        .values(user_id=user_id, novel_id=novel_id, claim_token=claim_token, status="running")
        .on_conflict_do_nothing(
            index_elements=["user_id", "novel_id"], index_where=sa.text("status = 'running'")
        )
        .returning(WorldGenerationRun.id)
    )
    run_id = db.scalar(statement)
    db.commit()
    return run_id


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
