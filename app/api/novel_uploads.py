# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from starlette.concurrency import run_in_threadpool
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth import get_current_user_or_default
from app.core.ingest import (
    accept_novel_upload,
    inspect_novel_ingest_job,
    reset_novel_ingest_job_for_retry,
    upload_limit_bytes,
)
from app.database import get_db
from app.models import (
    ContinuationRun, CopilotRun, CopilotSession, Exploration, ExplorationChapter,
    User, WorldEntity, WorldEntityAttribute, WorldGenerationRun, WorldRelationship, WorldSystem,
)
from app.content_formats import (
    MARKDOWN_CONTENT_FORMAT,
    PLAIN_TEXT_CONTENT_FORMAT,
    NovelContentFormat,
)
from app.schemas import (
    NovelResponse,
    UploadResponse,
)

from . import novel_support

router = APIRouter(prefix="/api/novels", tags=["novels"])

NOVEL_SOURCE_FORMAT_BY_EXTENSION: dict[str, NovelContentFormat] = {
    ".txt": PLAIN_TEXT_CONTENT_FORMAT,
    ".md": MARKDOWN_CONTENT_FORMAT,
}


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_novel(
    file: UploadFile = File(...),
    title: str = Form(...),
    author: str = Form(""),
    language: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    """Accept a novel upload and enqueue background ingest."""
    settings = get_settings()
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"code": "upload_filename_missing", "message": "No filename provided"},
        )

    original_name = file.filename.replace("\\", "/").split("/")[-1]
    ext = Path(original_name).suffix.lower()
    if ext not in NOVEL_SOURCE_FORMAT_BY_EXTENSION:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "upload_type_not_supported",
                "message": "File type not supported. Allowed: .txt, .md",
            },
        )

    stem = Path(original_name).stem
    safe_stem = "".join(c for c in stem if c.isalnum() or c in "._-").strip("._-")
    safe_stem = safe_stem[:80]
    token = uuid4().hex
    safe_filename = f"{safe_stem}_{token}{ext}" if safe_stem else f"{token}{ext}"
    file_path = novel_support.UPLOAD_DIR / safe_filename
    max_size = upload_limit_bytes(settings)
    chunk_size = max(1024, int(settings.upload_chunk_size_bytes))
    bytes_written = 0
    try:
        with file_path.open("wb") as handle:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_size:
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "code": "upload_file_too_large",
                            "message": f"File too large. Maximum size is {settings.upload_max_megabytes} MB.",
                            "max_megabytes": int(settings.upload_max_megabytes),
                        },
                    )
                await run_in_threadpool(handle.write, chunk)
    except Exception:
        file_path.unlink(missing_ok=True)
        raise
    finally:
        try:
            await file.close()
        except Exception:
            pass

    try:
        novel = accept_novel_upload(
            db,
            title=title,
            author=author,
            file_path=str(file_path),
            owner_id=current_user.id,
            source_bytes=bytes_written,
            requested_language=language,
            content_format=NOVEL_SOURCE_FORMAT_BY_EXTENSION[ext],
        )
        db.commit()
        db.refresh(novel)
    except Exception:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise

    return UploadResponse(
        novel_id=novel.id,
        total_chapters=None,
        message="Upload accepted",
    )


@router.post("/{novel_id}/ingest/retry", response_model=NovelResponse, status_code=202)
def retry_novel_ingest(
    novel_id: int,
    db: Session = Depends(get_db),
):
    novel = novel_support.get_novel(db, novel_id)

    if inspect_novel_ingest_job(db, novel_id=novel_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "ingest_job_not_found", "message": "Novel ingest job not found"},
        )

    if not reset_novel_ingest_job_for_retry(db, novel_id=novel_id):
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "ingest_retry_not_allowed", "message": "Novel ingest retry is not allowed"},
        )

    db.commit()
    db.refresh(novel)

    return novel_support.serialize_novel_with_states(
        novel,
        db=db,
        has_window_index_payload=novel.window_index_payload_size is not None,
    )


@router.delete("/{novel_id}", status_code=204)
def delete_novel(
    novel_id: int,
    db: Session = Depends(get_db),
):
    novel = novel_support.get_novel(db, novel_id)

    entity_ids = sa.select(WorldEntity.id).where(WorldEntity.novel_id == novel_id)
    exploration_ids = sa.select(Exploration.id).where(Exploration.novel_id == novel_id)
    db.execute(sa.delete(WorldEntityAttribute).where(WorldEntityAttribute.entity_id.in_(entity_ids)))
    db.execute(sa.delete(ExplorationChapter).where(ExplorationChapter.exploration_id.in_(exploration_ids)))
    for model in (WorldRelationship, WorldEntity, WorldSystem, Exploration, CopilotRun,
                  CopilotSession, ContinuationRun, WorldGenerationRun):
        db.execute(sa.delete(model).where(model.novel_id == novel_id))
    novel_support.delete_legacy_novel_rows(db, novel_id)

    file_path = Path(novel.file_path) if novel.file_path else None
    db.delete(novel)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    if file_path is not None:
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            novel_support.logger.warning(
                "Failed to delete novel file after DB delete (novel_id=%s, file_path=%s)",
                novel_id,
                str(file_path),
                exc_info=True,
            )

    return Response(status_code=204)
