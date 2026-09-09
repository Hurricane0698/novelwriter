"""Value snapshots and optimistic conflict checks for text-to-world generation."""

from dataclasses import dataclass
from hashlib import sha256
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.world.use_case_errors import WorldUseCaseError
from app.models import Novel, WorldEntity, WorldEntityAttribute, WorldRelationship, WorldSystem


@dataclass(frozen=True)
class GenerationSnapshot:
    language: str
    fingerprint: str


def generation_snapshot(db: Session, novel_id: int, user_id: int | None, *, lock: bool = False) -> GenerationSnapshot:
    if lock and db.get_bind().dialect.name == "sqlite":
        # Own this short write transaction before validating its read snapshot.
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    query = select(Novel.title, Novel.language, Novel.owner_id, Novel.updated_at, Novel.window_index_revision).where(Novel.id == novel_id)
    novel = db.execute(query.with_for_update() if lock else query).first()
    if novel is None or (get_settings().deploy_mode == "hosted" and novel.owner_id != user_id):
        raise WorldUseCaseError(code="novel_not_found", message="Novel no longer available", status_code=404)
    digest = sha256()

    def include(value):
        digest.update(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode())
        digest.update(b"\n")

    include(tuple(novel))
    # A timestamp alone has insufficient precision on SQLite. Fingerprint field
    # values too, so editing a draft during generation cannot silently replace it.
    for model in (WorldEntity, WorldRelationship, WorldSystem, WorldEntityAttribute):
        table = model.__table__
        statement = select(table).order_by(table.c.id)
        if model is WorldEntityAttribute:
            statement = statement.where(table.c.entity_id.in_(select(WorldEntity.id).where(WorldEntity.novel_id == novel_id)))
        else:
            statement = statement.where(table.c.novel_id == novel_id)
        if lock:
            statement = statement.with_for_update()
        include(table.name)
        for row in db.execute(statement).yield_per(128):
            include(tuple(row))
    return GenerationSnapshot(language=novel.language, fingerprint=digest.hexdigest())


def check_generation_snapshot(db: Session, novel_id: int, user_id: int | None, expected: GenerationSnapshot) -> None:
    if generation_snapshot(db, novel_id, user_id, lock=True) != expected:
        raise WorldUseCaseError(
            code="world_generate_conflict", message="The novel or world changed during generation. Please retry.", status_code=409,
        )
