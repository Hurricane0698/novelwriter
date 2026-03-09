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
from app.core.context_assembly import apply_writer_context_budget, assemble_writer_context
from app.core.continuation_postcheck import postcheck_continuation
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


def get_llm_config(request: Request) -> dict | None:
    """Extract per-request LLM config from headers.

    In hosted mode, falls back to server-side config if no headers supplied.
    """
    base_url = request.headers.get("x-llm-base-url")
    api_key = request.headers.get("x-llm-api-key")
    model = request.headers.get("x-llm-model")
    if not base_url and not api_key and not model:
        # Hosted mode: fall back to server-side LLM config
        settings = get_settings()
        if settings.deploy_mode == "hosted" and settings.hosted_llm_base_url:
            return {
                "base_url": settings.hosted_llm_base_url,
                "api_key": settings.hosted_llm_api_key,
                "model": settings.hosted_llm_model,
                "billing_source_hint": "hosted",
            }
        return None

    if not base_url or not api_key or not model:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "llm_config_incomplete",
                "message": "BYOK requires X-LLM-Base-Url, X-LLM-Api-Key, and X-LLM-Model together.",
            },
        )

    settings = get_settings()
    if settings.deploy_mode == "hosted" and base_url:
        from app.core.url_validator import UnsafeURLError, validate_llm_url
        try:
            validate_llm_url(base_url)
        except UnsafeURLError as e:
            # Reject user-controlled endpoints that can be used for SSRF in hosted mode.
            raise HTTPException(status_code=400, detail=str(e))

    billing_source_hint = "byok" if settings.deploy_mode == "hosted" else "selfhost"
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "billing_source_hint": billing_source_hint,
    }


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


def _extract_narrative_constraints(writer_ctx: dict[str, Any]) -> str:
    """Extract constraints from active systems into a standalone prompt section.

    Returns an empty string when no constraints exist, so the prompt template
    collapses cleanly.
    """
    systems = writer_ctx.get("systems") or []
    rules: list[str] = []
    for s in systems:
        if not isinstance(s, dict):
            continue
        constraints = s.get("constraints") or []
        if not isinstance(constraints, list):
            continue
        for c in constraints:
            c = str(c or "").strip()
            if c:
                rules.append(c)
    if not rules:
        return ""
    numbered = "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
    return f"\n<narrative_constraints>\n{numbered}\n</narrative_constraints>\n"


# ---------------------------------------------------------------------------
# System data renderers (display_type → natural language)
# ---------------------------------------------------------------------------

def _render_hierarchy_data(data: Any) -> str:
    """Render hierarchy system data as an indented list."""
    nodes = data.get("nodes") if isinstance(data, dict) else None
    if not isinstance(nodes, list) or not nodes:
        return ""
    lines: list[str] = []

    def _walk(node: Any, depth: int = 0) -> None:
        if not isinstance(node, dict):
            return
        label = str(node.get("label") or node.get("name") or "").strip()
        if not label:
            return
        desc = str(node.get("description") or "").strip()
        indent = "  " * depth
        line = f"{indent}· {label}"
        if desc:
            line += f"：{desc}"
        lines.append(line)
        for child in node.get("children") or []:
            _walk(child, depth + 1)

    for n in nodes:
        _walk(n)
    return "\n".join(lines)


def _render_graph_data(data: Any) -> str:
    """Render graph system data as nodes + edges."""
    if not isinstance(data, dict):
        return ""
    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    if not isinstance(nodes, list) and not isinstance(edges, list):
        return ""
    lines: list[str] = []
    node_map: dict[str, str] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "")
        label = str(n.get("label") or n.get("name") or nid).strip()
        node_map[nid] = label
        desc = str(n.get("description") or "").strip()
        line = f"· {label}"
        if desc:
            line += f"：{desc}"
        lines.append(line)
    for e in edges:
        if not isinstance(e, dict):
            continue
        src = node_map.get(str(e.get("source") or e.get("from") or ""), str(e.get("source") or e.get("from") or "?"))
        tgt = node_map.get(str(e.get("target") or e.get("to") or ""), str(e.get("target") or e.get("to") or "?"))
        elabel = str(e.get("label") or "").strip()
        if elabel:
            lines.append(f"  {src} —{elabel}→ {tgt}")
        else:
            lines.append(f"  {src} → {tgt}")
    return "\n".join(lines)


def _render_timeline_data(data: Any) -> str:
    """Render timeline system data as a chronological list."""
    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list) or not events:
        return ""
    lines: list[str] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        label = str(ev.get("label") or "").strip()
        date = str(ev.get("date") or "").strip()
        desc = str(ev.get("description") or "").strip()
        if not label:
            continue
        line = "· "
        if date:
            line += f"{date}，{label}"
        else:
            line += label
        if desc:
            line += f"：{desc}"
        lines.append(line)
    return "\n".join(lines)


def _render_list_data(data: Any) -> str:
    """Render list system data as bullet points."""
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        return ""
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("name") or "").strip()
        desc = str(item.get("description") or "").strip()
        if not label:
            continue
        line = f"· {label}"
        if desc:
            line += f"：{desc}"
        lines.append(line)
    return "\n".join(lines)


_SYSTEM_DATA_RENDERERS = {
    "hierarchy": _render_hierarchy_data,
    "graph": _render_graph_data,
    "timeline": _render_timeline_data,
    "list": _render_list_data,
}


def _render_system_data(display_type: str, data: Any) -> str:
    """Render system data as natural language based on display_type."""
    renderer = _SYSTEM_DATA_RENDERERS.get(display_type)
    if renderer and data:
        return renderer(data)
    if data:
        try:
            return json.dumps(data, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(data)
    return ""


def _format_world_context_for_prompt(writer_ctx: dict[str, Any]) -> str:
    """Render assemble_writer_context() output into an LLM-friendly text block."""
    systems = writer_ctx.get("systems") or []
    entities = writer_ctx.get("entities") or []
    relationships = writer_ctx.get("relationships") or []

    id_to_name: dict[int, str] = {}
    for e in entities:
        try:
            id_to_name[int(e.get("id"))] = str(e.get("name") or "").strip()
        except Exception:
            continue

    lines: list[str] = []

    if systems:
        lines.append("〈世界体系〉")
        for s in systems:
            name = str(s.get("name") or "").strip()
            desc = str(s.get("description") or "").strip()
            display_type = str(s.get("display_type") or "").strip()
            header = f"- {name}" if name else "- （未命名体系）"
            if desc:
                header += f"：{desc}"
            lines.append(header)

            # Constraints are extracted separately via _extract_narrative_constraints
            # and injected as a dedicated prompt section; skip them here.

            data = s.get("data")
            rendered = _render_system_data(display_type, data)
            if rendered:
                for dl in rendered.split("\n"):
                    lines.append(f"  {dl}")

    if entities:
        lines.append("〈角色与事物〉")
        for e in entities:
            name = str(e.get("name") or "").strip()
            entity_type = str(e.get("entity_type") or "").strip()
            desc = str(e.get("description") or "").strip()
            header = f"- {name}" if name else "- （未命名实体）"
            if entity_type:
                header += f"（{entity_type}）"
            if desc:
                header += f"：{desc}"
            lines.append(header)

            aliases = e.get("aliases") or []
            if isinstance(aliases, list):
                normalized = []
                for a in aliases:
                    a = str(a or "").strip()
                    if not a or (name and a == name):
                        continue
                    normalized.append(a)
                if normalized:
                    lines.append(f"  别名：{'、'.join(normalized)}")

            attrs = e.get("attributes") or []
            if isinstance(attrs, list) and attrs:
                for a in attrs:
                    key = str(a.get("key") or "").strip()
                    surface = str(a.get("surface") or "").strip()
                    if key and surface:
                        lines.append(f"  - {key}：{surface}")
                    elif key:
                        lines.append(f"  - {key}")

    if relationships:
        lines.append("〈人物关系〉")
        for r in relationships:
            label = str(r.get("label") or "").strip()
            desc = str(r.get("description") or "").strip()
            src_id = r.get("source_id")
            tgt_id = r.get("target_id")
            src = id_to_name.get(int(src_id), str(src_id)) if src_id is not None else "？"
            tgt = id_to_name.get(int(tgt_id), str(tgt_id)) if tgt_id is not None else "？"
            if label:
                rel = f"- {src} —{label}→ {tgt}"
            else:
                rel = f"- {src} → {tgt}"
            if desc:
                rel += f"：{desc}"
            lines.append(rel)

    return "\n".join(lines).strip()


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

    recent_text = "\n\n".join(
        f"【Chapter {ch.chapter_number}: {ch.title}】\n{ch.content}"
        for ch in recent_chapters
    )

    relevance_text = recent_text
    if req.prompt and req.prompt.strip():
        relevance_text = relevance_text + "\n\n【用户续写指令】\n" + req.prompt.strip()

    try:
        writer_ctx = assemble_writer_context(db, novel_id, chapter_text=relevance_text)
        writer_ctx = apply_writer_context_budget(writer_ctx)
    except Exception:
        logger.exception("assemble_writer_context failed for novel %s", novel_id)
        raise HTTPException(status_code=500, detail="Context assembly failed")

    world_context = _format_world_context_for_prompt(writer_ctx)
    narrative_constraints = _extract_narrative_constraints(writer_ctx)
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
