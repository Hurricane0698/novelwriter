# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from dataclasses import dataclass

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request, Response, Query
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Any, List
import json
import logging
import re
from uuid import uuid4

from app.database import get_db
from app.database import DATA_DIR
from app.models import (
    Novel,
    Chapter,
    Continuation,
)
from app.schemas import (
    NovelResponse,
    ChapterResponse,
    ChapterMetaResponse,
    ChapterCreateRequest,
    ChapterUpdateRequest,
    ContinuationResponse,
    ContinueDebugSummary,
    ContinueRequest,
    ContinueResponse,
    UploadResponse,
)
from app.core.parser import parse_novel_file
from app.core.llm_request import get_llm_config
from app.core.context_assembly import apply_writer_context_budget, assemble_writer_context
from app.core.continuation_postcheck import postcheck_continuation
from app.core.continuation_text import (
    append_user_instruction_for_relevance,
    extract_narrative_constraints,
    format_recent_chapters_for_prompt,
    format_world_context_for_prompt,
)
from app.core.generator import continue_novel, continue_novel_stream
from app.core.chapter_numbering import get_next_missing_chapter_number
from app.config import get_settings, resolve_context_chapters
from app.core.auth import (
    get_current_user_or_default,
    check_generation_quota,
    QuotaScope,
)
from app.core.llm_semaphore import acquire_llm_slot, release_llm_slot
from app.core.events import record_event
from app.models import User

router = APIRouter(prefix="/api/novels", tags=["novels"])

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)
UPLOAD_CONSENT_VERSION = "2026-03-06"

_SAFE_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_delete_where(
    db: Session,
    *,
    table: str,
    where_sql: str,
    params: dict[str, Any],
    allow_missing_column: bool = False,
) -> None:
    """Best-effort delete helper for optional/legacy tables.

    We keep this defensive because:
    - Local/selfhost DBs may drift (older schemas, partial migrations).
    - Some legacy tables exist in production DBs but are no longer represented in ORM models.
    """
    if not _SAFE_SQL_IDENTIFIER_RE.match(table):
        raise ValueError(f"Unsafe table name: {table!r}")

    try:
        # Use a SAVEPOINT so "missing table/column" errors in optional/legacy paths
        # don't poison the surrounding transaction (e.g., PostgreSQL aborts tx on error).
        with db.begin_nested():
            db.execute(sa.text(f"DELETE FROM {table} WHERE {where_sql}"), params)
    except DBAPIError as exc:
        msg = str(getattr(exc, "orig", exc)).lower()

        # SQLite: "no such table: X", "no such column: Y"
        if "no such table" in msg:
            logger.debug("Skipping delete from missing table %s", table)
            return
        if allow_missing_column and "no such column" in msg:
            logger.debug("Skipping delete from %s due to missing column", table)
            return

        # PostgreSQL: "relation X does not exist", "column Y does not exist"
        if "does not exist" in msg and ("relation" in msg or "table" in msg):
            logger.debug("Skipping delete from missing table %s", table)
            return
        if allow_missing_column and "does not exist" in msg and "column" in msg:
            logger.debug("Skipping delete from %s due to missing column", table)
            return

        # MySQL-style (best-effort): "Table ... doesn't exist", "Unknown column ..."
        if "doesn't exist" in msg and "table" in msg:
            logger.debug("Skipping delete from missing table %s", table)
            return
        if allow_missing_column and "unknown column" in msg:
            logger.debug("Skipping delete from %s due to missing column", table)
            return

        raise


def _user_novels(db: Session, user: User):
    """Return query filtered to novels visible to this user.

    - hosted: strict owner_id isolation
    - selfhost: single-user local mode; ignore owner_id so local DBs remain usable
    """
    q = db.query(Novel)
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return q
    return q.filter(Novel.owner_id == user.id)


def _verify_novel_access(novel: Novel | None, user: User) -> Novel:
    """Verify novel exists and user has access."""
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    settings = get_settings()
    if settings.deploy_mode == "hosted" and novel.owner_id != user.id:
        # Hosted mode must not leak existence across users.
        raise HTTPException(status_code=404, detail="Novel not found")
    return novel


def _build_continue_debug_summary(writer_ctx: dict[str, Any], context_chapters: int) -> ContinueDebugSummary:
    systems = writer_ctx.get("systems") or []
    entities = writer_ctx.get("entities") or []
    relationships = writer_ctx.get("relationships") or []
    debug = writer_ctx.get("debug") or {}

    def _safe_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    entity_names = [str(e.get("name") or "").strip() for e in entities if str(e.get("name") or "").strip()]
    system_names = [str(s.get("name") or "").strip() for s in systems if str(s.get("name") or "").strip()]

    id_to_name: dict[int, str] = {}
    for e in entities:
        entity_id = _safe_int(e.get("id"))
        name = str(e.get("name") or "").strip()
        if entity_id is None or not name:
            continue
        id_to_name[entity_id] = name

    rel_names: list[str] = []
    for r in relationships:
        label = str(r.get("label") or "").strip()
        src_raw = r.get("source_id")
        tgt_raw = r.get("target_id")
        src_id = _safe_int(src_raw)
        tgt_id = _safe_int(tgt_raw)
        src = id_to_name.get(src_id, str(src_raw)) if src_id is not None else "?"
        tgt = id_to_name.get(tgt_id, str(tgt_raw)) if tgt_id is not None else "?"
        if label:
            rel_names.append(f"{src} --{label}--> {tgt}")
        else:
            rel_names.append(f"{src} --> {tgt}")

    relevant_entity_ids: list[int] = []
    for raw in list(debug.get("relevant_entity_ids") or []):
        i = _safe_int(raw)
        if i is not None:
            relevant_entity_ids.append(i)

    return ContinueDebugSummary(
        context_chapters=int(context_chapters),
        injected_systems=system_names,
        injected_entities=entity_names,
        injected_relationships=rel_names,
        relevant_entity_ids=relevant_entity_ids,
        ambiguous_keywords_disabled=list(debug.get("ambiguous_keywords_disabled") or []),
    )


@dataclass
class _ContinuationContext:
    recent_text: str
    world_context: str
    narrative_constraints: str
    debug_summary: ContinueDebugSummary
    writer_ctx: dict[str, Any]
    effective_context_chapters: int


def _prepare_continuation_context(
    db: Session,
    novel_id: int,
    req: ContinueRequest,
    current_user: User,
) -> _ContinuationContext:
    """Sync helper: DB queries + context assembly. Designed to run in threadpool."""
    settings = get_settings()

    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    _verify_novel_access(novel, current_user)

    effective_context_chapters = resolve_context_chapters(
        req.context_chapters,
        default=settings.max_context_chapters,
    )

    recent_chapters = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_number.desc())
        .limit(effective_context_chapters)
        .all()
    )
    recent_chapters = list(reversed(recent_chapters))
    if not recent_chapters:
        raise HTTPException(status_code=400, detail="Novel has no chapters")

    recent_text = format_recent_chapters_for_prompt(recent_chapters)
    relevance_text = append_user_instruction_for_relevance(recent_text, req.prompt)

    try:
        writer_ctx = assemble_writer_context(db, novel_id, chapter_text=relevance_text)
        writer_ctx = apply_writer_context_budget(writer_ctx)
    except Exception:
        logger.exception("assemble_writer_context failed for novel %s", novel_id)
        raise HTTPException(status_code=500, detail="Context assembly failed")

    world_context = format_world_context_for_prompt(writer_ctx)
    narrative_constraints = extract_narrative_constraints(writer_ctx)
    debug_summary = _build_continue_debug_summary(writer_ctx, context_chapters=effective_context_chapters)

    return _ContinuationContext(
        recent_text=recent_text,
        world_context=world_context,
        narrative_constraints=narrative_constraints,
        debug_summary=debug_summary,
        writer_ctx=writer_ctx,
        effective_context_chapters=effective_context_chapters,
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_novel(
    file: UploadFile = File(...),
    title: str = Form(...),
    author: str = Form(""),
    consent_acknowledged: bool = Form(False),
    consent_version: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    """Upload and parse a novel file."""
    if not consent_acknowledged:
        raise HTTPException(
            status_code=400,
            detail={"code": "upload_consent_required", "message": "Upload consent is required"},
        )
    if consent_version != UPLOAD_CONSENT_VERSION:
        raise HTTPException(
            status_code=400,
            detail={"code": "upload_consent_version_mismatch", "message": "Upload consent version is outdated"},
        )

    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    allowed_extensions = {".txt"}
    original_name = file.filename.replace("\\", "/").split("/")[-1]
    ext = Path(original_name).suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {allowed_extensions}",
        )

    # Enforce 30 MB upload limit.
    stem = Path(original_name).stem
    safe_stem = "".join(c for c in stem if c.isalnum() or c in "._-").strip("._-")
    safe_stem = safe_stem[:80]
    token = uuid4().hex
    safe_filename = f"{safe_stem}_{token}{ext}" if safe_stem else f"{token}{ext}"
    file_path = UPLOAD_DIR / safe_filename
    max_size = 30 * 1024 * 1024
    chunk_size = 1024 * 1024  # 1 MiB
    bytes_written = 0
    try:
        with file_path.open("wb") as handle:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_size:
                    raise HTTPException(status_code=413, detail="File too large. Maximum size is 30 MB.")
                # Disk IO is blocking; offload writes so this async route doesn't
                # stall the event loop under load.
                await run_in_threadpool(handle.write, chunk)
    except HTTPException:
        file_path.unlink(missing_ok=True)
        raise
    except Exception:
        file_path.unlink(missing_ok=True)
        raise
    finally:
        try:
            await file.close()
        except Exception:
            pass

    try:
        chapters = parse_novel_file(str(file_path))
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse novel: {str(e)}")

    # Create novel record
    novel = Novel(
        title=title,
        author=author,
        file_path=str(file_path),
        total_chapters=len(chapters),
        owner_id=current_user.id,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)

    # Save chapters
    for chapter_num, chapter_title, chapter_content in chapters:
        chapter = Chapter(
            novel_id=novel.id,
            chapter_number=chapter_num,
            title=chapter_title,
            content=chapter_content,
        )
        db.add(chapter)

    db.commit()

    record_event(
        db,
        current_user.id,
        "novel_upload",
        novel_id=novel.id,
        meta={"chapters": len(chapters), "consent_acknowledged": True, "consent_version": consent_version},
    )

    return UploadResponse(
        novel_id=novel.id,
        total_chapters=len(chapters),
        message="Upload successful",
    )


@router.get("", response_model=List[NovelResponse])
def list_novels(db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_default)):
    """List all novels for the current user."""
    novels = _user_novels(db, current_user).order_by(Novel.created_at.desc()).all()
    return novels


@router.get("/{novel_id}", response_model=NovelResponse)
def get_novel(novel_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_default)):
    """Get novel information."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    _verify_novel_access(novel, current_user)
    return novel


@router.get("/{novel_id}/chapters", response_model=List[ChapterResponse])
def get_chapters(
    novel_id: int,
    skip: int = 0,
    limit: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
) -> List[ChapterResponse]:
    """Get full chapters for a novel (includes content)."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    _verify_novel_access(novel, current_user)

    query = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_number)
        .offset(skip)
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


@router.get("/{novel_id}/chapters/meta", response_model=List[ChapterMetaResponse])
def get_chapters_meta(
    novel_id: int,
    skip: int = 0,
    limit: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
) -> List[ChapterMetaResponse]:
    """Get lightweight chapter metadata for a novel (excludes content)."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    _verify_novel_access(novel, current_user)

    query = (
        db.query(
            Chapter.id,
            Chapter.novel_id,
            Chapter.chapter_number,
            Chapter.title,
            Chapter.created_at,
        )
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_number)
        .offset(skip)
    )
    if limit is not None:
        query = query.limit(limit)
    rows = query.all()
    return [
        ChapterMetaResponse(
            id=r.id,
            novel_id=r.novel_id,
            chapter_number=r.chapter_number,
            title=r.title,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/{novel_id}/chapters/{chapter_number}", response_model=ChapterResponse)
def get_chapter(
    novel_id: int,
    chapter_number: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    """Get a specific chapter by number."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    _verify_novel_access(novel, current_user)

    chapter = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id, Chapter.chapter_number == chapter_number)
        .first()
    )
    if not chapter:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter {chapter_number} not found in novel {novel_id}"
        )
    return chapter


@router.post("/{novel_id}/chapters", response_model=ChapterResponse, status_code=201)
def create_chapter(
    novel_id: int,
    req: ChapterCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    """Create a new chapter for a novel."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    _verify_novel_access(novel, current_user)

    if req.chapter_number is not None and req.chapter_number < 1:
        raise HTTPException(status_code=400, detail="chapter_number must be >= 1")

    # Auto-numbering fills the smallest missing positive chapter number.
    if req.chapter_number is None:
        # Defensive retry: concurrent auto-creates may race on the same number.
        for attempt in range(3):
            chapter_number = get_next_missing_chapter_number(db, novel_id)
            chapter = Chapter(
                novel_id=novel_id,
                chapter_number=chapter_number,
                title=req.title,
                content=req.content,
            )
            db.add(chapter)
            try:
                db.flush()  # surface unique constraint failures before commit
                db.query(Novel).filter(Novel.id == novel_id).update(
                    {Novel.total_chapters: Novel.total_chapters + 1}
                )
                db.commit()
            except IntegrityError:
                db.rollback()
                # Ensure the failed pending object doesn't get re-flushed on retry.
                try:
                    db.expunge(chapter)
                except Exception:
                    pass
                if attempt < 2:
                    continue
                raise HTTPException(
                    status_code=409,
                    detail="Chapter number conflict; please retry",
                )

            db.refresh(chapter)
            return chapter

        # Unreachable; loop always returns or raises.
        raise HTTPException(status_code=409, detail="Chapter number conflict; please retry")

    chapter_number = req.chapter_number

    existing = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id, Chapter.chapter_number == chapter_number)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Chapter {chapter_number} already exists")

    chapter = Chapter(
        novel_id=novel_id,
        chapter_number=chapter_number,
        title=req.title,
        content=req.content,
    )
    db.add(chapter)
    try:
        db.flush()
        db.query(Novel).filter(Novel.id == novel_id).update(
            {Novel.total_chapters: Novel.total_chapters + 1}
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Chapter {chapter_number} already exists")

    db.refresh(chapter)
    return chapter


@router.put("/{novel_id}/chapters/{chapter_number}", response_model=ChapterResponse)
def update_chapter(
    novel_id: int,
    chapter_number: int,
    req: ChapterUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    """Update a chapter's title and/or content."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    _verify_novel_access(novel, current_user)

    chapter = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id, Chapter.chapter_number == chapter_number)
        .first()
    )
    if not chapter:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter {chapter_number} not found in novel {novel_id}",
        )

    if req.title is None and req.content is None:
        raise HTTPException(status_code=400, detail="Must provide title and/or content")

    if req.title is not None:
        chapter.title = req.title
    if req.content is not None:
        chapter.content = req.content
    db.commit()
    db.refresh(chapter)
    record_event(db, current_user.id, "chapter_save", novel_id=novel_id, meta={"chapter": chapter_number})
    return chapter


@router.delete("/{novel_id}/chapters/{chapter_number}", status_code=204)
def delete_chapter(
    novel_id: int,
    chapter_number: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    """Delete a chapter from a novel."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    _verify_novel_access(novel, current_user)

    chapter = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id, Chapter.chapter_number == chapter_number)
        .first()
    )
    if not chapter:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter {chapter_number} not found in novel {novel_id}",
        )

    db.delete(chapter)
    db.query(Novel).filter(Novel.id == novel_id).update(
        {Novel.total_chapters: Novel.total_chapters - 1}
    )
    db.commit()
    return Response(status_code=204)


@router.post("/{novel_id}/continue", response_model=ContinueResponse)
async def continue_novel_endpoint(
    novel_id: int,
    req: ContinueRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    llm_config: dict | None = Depends(get_llm_config),
    _quota_user: User = Depends(check_generation_quota),
):
    """Continue a novel using WorldModel visibility-driven context injection."""
    current_user = _quota_user
    ctx = await run_in_threadpool(
        _prepare_continuation_context, db, novel_id, req, current_user,
    )

    await acquire_llm_slot()
    quota = QuotaScope(db, current_user.id, count=int(req.num_versions or 1))
    try:
        quota.reserve()
        continuations = await continue_novel(
            db=db,
            novel_id=novel_id,
            num_versions=req.num_versions,
            prompt=req.prompt,
            max_tokens=req.max_tokens,
            target_chars=req.target_chars,
            context_chapters=ctx.effective_context_chapters,
            world_context=ctx.world_context,
            narrative_constraints=ctx.narrative_constraints,
            world_debug_summary=ctx.debug_summary.model_dump(),
            use_lorebook=False,
            llm_config=llm_config,
            temperature=req.temperature,
            user_id=current_user.id,
        )
        quota.charge(len(continuations or []))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logger.exception("continue_novel failed for novel %s", novel_id)
        raise HTTPException(status_code=500, detail="Continuation generation failed")
    finally:
        quota.finalize()
        release_llm_slot()

    record_event(db, current_user.id, "generation", novel_id=novel_id, meta={"variants": len(continuations)})

    postcheck_warnings = postcheck_continuation(
        writer_ctx=ctx.writer_ctx,
        recent_text=ctx.recent_text,
        user_prompt=req.prompt,
        continuations=continuations,
    )
    if postcheck_warnings:
        ctx.debug_summary = ctx.debug_summary.model_copy(
            update={"postcheck_warnings": postcheck_warnings}
        )

    return ContinueResponse(continuations=continuations, debug=ctx.debug_summary)


@router.post("/{novel_id}/continue/stream")
async def continue_novel_stream_endpoint(
    novel_id: int,
    req: ContinueRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    llm_config: dict | None = Depends(get_llm_config),
    _quota_user: User = Depends(check_generation_quota),
):
    """Stream continuation generation via NDJSON."""
    current_user = _quota_user
    settings = get_settings()
    if settings.deploy_mode != "selfhost" and current_user.generation_quota < req.num_versions:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Not enough quota. Need {req.num_versions}, have {current_user.generation_quota}. "
                "Submit feedback to unlock more."
            ),
        )

    ctx = await run_in_threadpool(
        _prepare_continuation_context, db, novel_id, req, current_user,
    )

    await acquire_llm_slot()

    quota = QuotaScope(db, current_user.id, count=int(req.num_versions or 1))
    try:
        quota.reserve()
    except Exception:
        release_llm_slot()
        raise

    request_id = getattr(request.state, "request_id", None)

    async def event_generator():
        try:
            from types import SimpleNamespace

            contents_by_variant: dict[int, str] = {}
            total_variants: int | None = None

            async for event in continue_novel_stream(
                db=db,
                novel_id=novel_id,
                num_versions=req.num_versions,
                prompt=req.prompt,
                max_tokens=req.max_tokens,
                target_chars=req.target_chars,
                context_chapters=ctx.effective_context_chapters,
                world_context=ctx.world_context,
                narrative_constraints=ctx.narrative_constraints,
                world_debug_summary=ctx.debug_summary.model_dump(),
                use_lorebook=False,
                llm_config=llm_config,
                request_id=request_id,
                temperature=req.temperature,
                user_id=current_user.id,
            ):
                if event.get("type") == "start":
                    try:
                        total_variants = int(event.get("total_variants") or req.num_versions)
                    except Exception:
                        total_variants = int(req.num_versions)

                if event.get("type") == "variant_done":
                    quota.charge(1)
                    try:
                        v = int(event.get("variant"))
                        contents_by_variant[v] = str(event.get("content") or "")
                    except Exception:
                        pass

                if event.get("type") == "done":
                    # Post-check is advisory only; never block or fail the stream.
                    try:
                        n = int(total_variants or req.num_versions)
                        conts = [
                            SimpleNamespace(content=contents_by_variant.get(i, ""))
                            for i in range(n)
                        ]
                        postcheck_warnings = postcheck_continuation(
                            writer_ctx=ctx.writer_ctx,
                            recent_text=ctx.recent_text,
                            user_prompt=req.prompt,
                            continuations=conts,
                        )
                        if postcheck_warnings:
                            debug_with_warnings = ctx.debug_summary.model_copy(
                                update={"postcheck_warnings": postcheck_warnings}
                            )
                            event["debug"] = debug_with_warnings.model_dump()
                    except Exception:
                        logger.exception(
                            "postcheck_continuation failed for stream (request_id=%s, novel_id=%s)",
                            request_id,
                            novel_id,
                        )
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            quota.finalize()
            if quota.charged > 0:
                record_event(db, current_user.id, "generation", novel_id=novel_id, meta={"variants": quota.charged, "stream": True})
            release_llm_slot()

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


@router.get("/{novel_id}/continuations", response_model=List[ContinuationResponse])
def get_continuations(
    novel_id: int,
    ids: str = Query(..., description="Comma-separated continuation IDs"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    """Fetch one or more Continuation rows by ID (used for results-page refresh)."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    _verify_novel_access(novel, current_user)

    parts = [p.strip() for p in (ids or "").split(",") if p.strip()]
    if not parts:
        raise HTTPException(status_code=400, detail="ids must not be empty")
    try:
        wanted = [int(p) for p in parts]
    except ValueError:
        raise HTTPException(status_code=400, detail="ids must be a comma-separated list of integers")
    if len(wanted) > 10:
        raise HTTPException(status_code=400, detail="Too many ids")

    rows = (
        db.query(Continuation)
        .filter(Continuation.novel_id == novel_id, Continuation.id.in_(wanted))
        .all()
    )
    by_id = {c.id: c for c in rows}
    missing = [i for i in wanted if i not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail="Continuation not found")
    # Preserve caller order so variant<->id mapping remains stable.
    return [by_id[i] for i in wanted]


@router.delete("/{novel_id}", status_code=204)
def delete_novel(novel_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_default)):
    """Delete a novel and all related data."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    _verify_novel_access(novel, current_user)

    # Delete rows from tables that are not ORM-cascaded off Novel, plus
    # best-effort cleanup for legacy tables that still exist in some DBs.
    #
    # Order matters when FK enforcement is enabled: delete dependents first.
    _safe_delete_where(db, table="world_relationships", where_sql="novel_id = :novel_id", params={"novel_id": novel_id})
    _safe_delete_where(db, table="world_entity_attributes", where_sql="entity_id IN (SELECT id FROM world_entities WHERE novel_id = :novel_id)", params={"novel_id": novel_id})
    _safe_delete_where(db, table="world_entities", where_sql="novel_id = :novel_id", params={"novel_id": novel_id})
    _safe_delete_where(db, table="world_systems", where_sql="novel_id = :novel_id", params={"novel_id": novel_id})
    _safe_delete_where(db, table="bootstrap_jobs", where_sql="novel_id = :novel_id", params={"novel_id": novel_id})

    # Exploration tables (not linked off Novel in ORM).
    _safe_delete_where(db, table="exploration_chapters", where_sql="exploration_id IN (SELECT id FROM explorations WHERE novel_id = :novel_id)", params={"novel_id": novel_id})
    _safe_delete_where(db, table="explorations", where_sql="novel_id = :novel_id", params={"novel_id": novel_id})

    # Legacy/removed components (best-effort cleanup; safe on DBs that still have them).
    #
    # These old tables are NOT part of the current ORM schema, and (critically)
    # not all of them contain a `novel_id` column. Delete in dependency order to
    # avoid leaving orphans even when SQLite FK enforcement is off.
    legacy_deletes: list[tuple[str, str]] = [
        # Character hierarchy: moments -> epochs -> arcs.
        (
            "character_moments",
            "epoch_id IN (SELECT id FROM character_epochs WHERE arc_id IN (SELECT id FROM character_arcs WHERE novel_id = :novel_id))",
        ),
        ("character_epochs", "arc_id IN (SELECT id FROM character_arcs WHERE novel_id = :novel_id)"),
        ("character_arcs", "novel_id = :novel_id"),

        # Plot hierarchy: beats -> threads -> arcs.
        (
            "plot_beats",
            "thread_id IN (SELECT id FROM plot_threads WHERE arc_id IN (SELECT id FROM plot_arcs WHERE novel_id = :novel_id))",
        ),
        ("plot_threads", "arc_id IN (SELECT id FROM plot_arcs WHERE novel_id = :novel_id)"),
        ("plot_arcs", "novel_id = :novel_id"),

        # Narrative tables.
        ("narrative_facts", "novel_id = :novel_id"),
        ("narrative_styles", "novel_id = :novel_id"),
        # Referenced by character_epochs.triggered_by_event_id, so delete last.
        ("narrative_events", "novel_id = :novel_id"),
    ]
    for table, where_sql in legacy_deletes:
        _safe_delete_where(
            db,
            table=table,
            where_sql=where_sql,
            params={"novel_id": novel_id},
            allow_missing_column=True,
        )

    # Delete DB state first; only delete the on-disk file after commit succeeds.
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
            logger.warning(
                "Failed to delete novel file after DB delete (novel_id=%s, file_path=%s)",
                novel_id,
                str(file_path),
                exc_info=True,
            )

    return Response(status_code=204)
