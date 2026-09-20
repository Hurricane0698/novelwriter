"""Validate only the content and values a review actually used."""

from __future__ import annotations

from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.core.copilot.text_review_evidence import WORLD_MODELS, TextReviewWork
from app.core.text_targets import (
    content_hash,
    current_content,
    load_text_target,
    stage_text_write,
    stale_text,
)
from app.models import Chapter, CopilotRun, Novel, WorldEntity, WorldEntityAttribute


def capture_action_guards(action: dict, work: TextReviewWork) -> None:
    guards = action.setdefault("review_guards", [])
    resource = action["type"].split("_", 1)[1]
    rows = {
        "entity": work.snapshot.entities,
        "relationship": work.snapshot.relationships,
        "system": work.snapshot.systems,
    }[resource]
    if action["type"].startswith("update_"):
        row = next(
            (row for row in rows if row.id == action.get(f"{resource}_id")), None
        )
        if row is None:
            raise ValueError("Update target outside the review snapshot")
        guards.append(
            {
                "resource": resource,
                "id": row.id,
                "values": {key: getattr(row, key) for key in action.get("data", {})},
            }
        )
    for item in action.get("attribute_actions", []):
        attrs = work.snapshot.attributes_by_entity.get(item["entity_id"], [])
        if item["type"] == "update_attribute":
            attr = next((row for row in attrs if row.id == item["attribute_id"]), None)
            if attr is None:
                raise ValueError("Attribute outside the review snapshot")
            guards.append(
                {
                    "resource": "attribute",
                    "id": attr.id,
                    "values": {key: getattr(attr, key) for key in item["data"]},
                }
            )
        else:
            guards.append(
                {
                    "resource": "attribute_absent",
                    "entity_id": item["entity_id"],
                    "key": item["data"]["key"],
                }
            )


def validate_guards(
    db: Session, novel_id: int, guards: list[dict], *, lock: bool = True
) -> None:
    def read(query):
        query = query.populate_existing()
        return (query.with_for_update() if lock else query).first()

    for guard in guards:
        resource = guard.get("resource")
        if resource == "attribute_absent":
            entity = read(
                db.query(WorldEntity).filter_by(
                    id=guard["entity_id"], novel_id=novel_id
                )
            )
            if (
                entity is None
                or db.query(WorldEntityAttribute)
                .filter_by(entity_id=entity.id, key=guard["key"])
                .first()
            ):
                raise stale_text()
        elif resource in WORLD_MODELS:
            model = WORLD_MODELS[resource]
            row = read(db.query(model).filter(model.id == guard["id"]))
            owner = (
                db.get(WorldEntity, row.entity_id)
                if resource == "attribute" and row
                else row
            )
            if (
                row is None
                or owner is None
                or owner.novel_id != novel_id
                or any(
                    getattr(row, key, None) != value
                    for key, value in guard.get("values", {}).items()
                )
            ):
                raise stale_text()
        elif guard.get("chapter_id"):
            chapter = read(
                db.query(Chapter).filter_by(id=guard["chapter_id"], novel_id=novel_id)
            )
            if chapter is None or content_hash(chapter.content) != guard.get(
                "content_hash"
            ):
                raise stale_text()


def attach_action_sources(db: Session, action: dict, result: dict | None) -> None:
    refs = action.get("source_refs")
    if not refs:
        return
    resource = action["type"].split("_", 1)[1]
    model = WORLD_MODELS[resource]
    row_id = (result or {}).get(f"{resource}_id") or action.get(f"{resource}_id")
    row = db.get(model, row_id) if row_id else None
    if row and action.get("data"):
        row.source_metadata = {
            "refs": deepcopy(refs[:3]),
            "values": {key: deepcopy(getattr(row, key)) for key in action["data"]},
        }
    for item in [
        *action.get("attribute_actions", []),
        *action.get("deferred_attribute_actions", []),
    ]:
        entity_id = item.get("entity_id") or row_id
        if item.get("attribute_id"):
            attr = db.get(WorldEntityAttribute, item["attribute_id"])
        else:
            attr = (
                db.query(WorldEntityAttribute)
                .filter_by(entity_id=entity_id, key=item["data"]["key"])
                .first()
            )
        if attr:
            attr.source_metadata = {
                "refs": deepcopy(refs[:3]),
                "values": {key: deepcopy(getattr(attr, key)) for key in item["data"]},
            }


def lock_review_run(db: Session, run: CopilotRun) -> None:
    # SQLite obtains its write lock here; PostgreSQL locks the run row. Refresh
    # after waiting so duplicate clicks cannot reuse a pre-lock suggestion list.
    result = db.execute(
        update(CopilotRun)
        .where(CopilotRun.id == run.id, CopilotRun.status == "completed")
        .values(updated_at=func.now()),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        raise HTTPException(409, detail="Review is not completed")
    db.refresh(run)


def apply_text_suggestions(
    db: Session, run: CopilotRun, suggestion_ids: list[str], expected_hash: str
) -> dict:
    from app.api.novel_chapters import _validate_chapter_content
    from app.core.indexing.lifecycle import (
        mark_window_index_inputs_changed,
        enqueue_window_index_rebuild_job,
    )

    lock_review_run(db, run)
    metadata = (run.context_json or {}).get("text_review") or {}
    if metadata.get("action") != "review_text" or metadata.get("closed"):
        raise stale_text()
    target = metadata["target"]
    row = load_text_target(db, run.novel_id, target)
    before = current_content(row)
    if expected_hash != target["content_hash"] or content_hash(before) != expected_hash:
        raise stale_text()
    ids = set(suggestion_ids)
    if not ids or len(ids) != len(suggestion_ids) or len(ids) > 3:
        raise HTTPException(422, detail="Select up to three different edits")
    suggestions = deepcopy(run.suggestions_json or [])
    selected = [item for item in suggestions if item["suggestion_id"] in ids]
    if len(selected) != len(ids) or any(
        item.get("status") != "pending"
        or (item.get("apply") or {}).get("type") != "replace_text"
        for item in selected
    ):
        raise stale_text()
    changes = sorted(
        (item["apply"]["data"] for item in selected), key=lambda change: change["start"]
    )
    for index, change in enumerate(changes):
        if before[change["start"] : change["end"]] != change["before"] or (
            index and changes[index - 1]["end"] > change["start"]
        ):
            raise stale_text()
    for item in selected:
        validate_guards(db, run.novel_id, item["apply"].get("review_guards", []))
    after = before
    for change in reversed(changes):
        after = after[: change["start"]] + change["after"] + after[change["end"] :]
    novel = db.get(Novel, run.novel_id)
    _validate_chapter_content(novel, after)
    stage_text_write(db, row, after, expected_hash)
    if isinstance(row, Chapter):
        revision = mark_window_index_inputs_changed(novel)
        enqueue_window_index_rebuild_job(
            db, novel_id=novel.id, target_revision=revision
        )
    for item in selected:
        item["status"] = "applied"
    run.suggestions_json = suggestions
    run.context_json = {**run.context_json, "text_review": {**metadata, "closed": True}}
    db.commit()
    return {
        "target": target,
        "content": after,
        "content_hash": content_hash(after),
        "before_content": before,
        "updated_at": row.updated_at if isinstance(row, Chapter) else None,
    }


def review_response(run: CopilotRun, db: Session) -> dict | None:
    metadata = deepcopy((run.context_json or {}).get("text_review"))
    if not metadata:
        return None
    try:
        row = load_text_target(db, run.novel_id, metadata["target"])
        metadata["stale"] = (
            content_hash(current_content(row)) != metadata["target"]["content_hash"]
        )
        for item in run.suggestions_json or []:
            if item.get("status") == "pending":
                validate_guards(
                    db,
                    run.novel_id,
                    (item.get("apply") or {}).get("review_guards", []),
                    lock=False,
                )
    except HTTPException:
        metadata["stale"] = True
    return metadata
