"""Current-text identity and conditional writes; no content history."""

from __future__ import annotations

import hashlib

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.models import Chapter, Continuation


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def current_content(row: Chapter | Continuation) -> str:
    if isinstance(row, Continuation) and row.edited_content is not None:
        return row.edited_content
    return row.content


def stale_text() -> HTTPException:
    return HTTPException(
        409,
        detail={
            "code": "text_target_stale",
            "message": "文本已改变，请重新核对；未覆盖当前内容。",
        },
    )


def load_text_target(
    db: Session, novel_id: int, target: dict
) -> Chapter | Continuation:
    model = Chapter if target.get("kind") == "chapter" else Continuation
    if target.get("kind") not in {"chapter", "continuation"}:
        raise HTTPException(422, detail="Invalid text target")
    row = (
        db.query(model)
        .filter(model.id == target.get("id"), model.novel_id == novel_id)
        .first()
    )
    if row is None:
        raise HTTPException(404, detail="Text target not found")
    return row


def stage_text_write(
    db: Session, row: Chapter | Continuation, content: str, expected_hash: str
) -> None:
    """Compare and write atomically, including a candidate's nullable edited draft."""
    before = current_content(row)
    if content_hash(before) != expected_hash:
        raise stale_text()
    model = type(row)
    if isinstance(row, Continuation):
        condition = (
            func.coalesce(Continuation.edited_content, Continuation.content) == before
        )
        values = {"edited_content": content}
    else:
        condition = Chapter.content == before
        values = {"content": content, "updated_at": func.now()}
    result = db.execute(
        update(model).where(model.id == row.id, condition).values(**values),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        raise stale_text()
    db.expire(row)
