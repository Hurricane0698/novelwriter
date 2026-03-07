# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""
Generator utilities for continuation and outline generation.

This module provides:
1. Lorebook context injection
2. Multi-model routing support
"""

from typing import AsyncGenerator, List
import asyncio
import math
import re
from sqlalchemy.orm import Session
import logging

from app.models import Novel, Chapter, Outline, Continuation
from app.core.ai_client import ai_client
from app.core.lore_manager import LoreManager
from app.core.cache import cache_manager
from app.utils.prompts import CONTINUATION_PROMPT, OUTLINE_PROMPT, SYSTEM_PROMPT
from app.config import get_settings, resolve_context_chapters
from app.core.chapter_numbering import get_next_missing_chapter_number

logger = logging.getLogger(__name__)


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def _sanitize_continuation_content(text: str) -> str:
    """Strip provider thinking/analysis blocks from creative-writing output.

    Some reasoning models emit chain-of-thought in <think>...</think> blocks.
    We never want to persist or display those in NovWr.
    """
    if not text:
        return ""

    cleaned = _THINK_BLOCK_RE.sub("", text)
    # A few gateways prefix with "Final:" when using reasoning models.
    cleaned = re.sub(r"^\s*(final|answer)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _build_length_guidance(target_chars: int | None) -> str:
    if target_chars:
        return f"按照约{target_chars}字的篇幅，在完整句子处收束"
    return "以合适的章节篇幅，在完整句子处收束"


def _compute_max_tokens(
    target_chars: int | None,
    max_tokens: int | None,
    default_tokens: int,
    cap: int = 16000,
) -> int:
    if target_chars:
        estimated = math.ceil(target_chars * 2.2)
        estimated = math.ceil(estimated * 1.1)
        return min(cap, max(100, estimated))
    if max_tokens is not None:
        return max_tokens
    return default_tokens


def _trim_to_target_chars(text: str, target_chars: int) -> str:
    if target_chars <= 0:
        return text

    punctuation = "。！？!?…"
    slice_end = min(len(text), target_chars)
    window_start = max(0, slice_end - 200)

    trimmed = text[:slice_end].rstrip()
    if trimmed and trimmed[-1] in punctuation:
        return trimmed

    candidate = None
    for idx in range(slice_end, window_start, -1):
        if text[idx - 1] in punctuation:
            candidate = idx
            break

    if candidate is None:
        for idx in range(slice_end, 0, -1):
            if text[idx - 1] in punctuation:
                candidate = idx
                break

    if candidate is None:
        return trimmed
    return text[:candidate].rstrip()


async def generate_outline(
    db: Session,
    novel_id: int,
    chapter_start: int,
    chapter_end: int,
) -> Outline:
    """Generate outline for specified chapter range."""
    chapters = (
        db.query(Chapter)
        .filter(
            Chapter.novel_id == novel_id,
            Chapter.chapter_number >= chapter_start,
            Chapter.chapter_number <= chapter_end,
        )
        .order_by(Chapter.chapter_number)
        .all()
    )

    if not chapters:
        raise ValueError(
            f"No chapters found for novel {novel_id} in range {chapter_start}-{chapter_end}. "
            f"Ensure the novel has been uploaded and chapters exist in this range."
        )

    content = "\n\n".join(
        f"【第{ch.chapter_number}章：{ch.title}】\n{ch.content[:1000]}..."
        for ch in chapters
    )

    prompt = OUTLINE_PROMPT.format(
        start=chapter_start,
        end=chapter_end,
        content=content,
    )

    outline_text = await ai_client.generate(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        max_tokens=1000,
    )

    outline = Outline(
        novel_id=novel_id,
        chapter_start=chapter_start,
        chapter_end=chapter_end,
        outline_text=outline_text,
    )
    db.add(outline)
    db.commit()
    db.refresh(outline)

    return outline


async def _build_continuation_prompt(
    db: Session,
    novel_id: int,
    use_core_memory: bool = True,
    use_lorebook: bool = True,
    prompt: str | None = None,
    max_tokens: int | None = None,
    target_chars: int | None = None,
    context_chapters: int | None = None,
    world_context: str | None = None,
    narrative_constraints: str | None = None,
    world_debug_summary: dict | None = None,
) -> tuple[str, int, dict]:
    """Build the continuation prompt and return (prompt, effective_max_tokens, build_info)."""
    settings = get_settings()

    effective_max_tokens = _compute_max_tokens(
        target_chars=target_chars,
        max_tokens=max_tokens,
        default_tokens=settings.default_continuation_tokens,
        cap=settings.max_continuation_tokens,
    )
    length_guidance = _build_length_guidance(target_chars)

    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise ValueError(
            f"Novel {novel_id} not found. Please upload a novel first using POST /api/novels/upload."
        )

    effective_context_chapters = resolve_context_chapters(
        context_chapters,
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
        raise ValueError(
            f"Novel {novel_id} has no chapters. Cannot generate continuation without existing content."
        )

    outlines = (
        db.query(Outline)
        .filter(Outline.novel_id == novel_id)
        .order_by(Outline.chapter_end.desc())
        .limit(2)
        .all()
    )

    recent_content = "\n\n".join(
        f"【第{ch.chapter_number}章：{ch.title}】\n{ch.content}"
        for ch in recent_chapters
    )

    outline_content = "\n\n".join(
        f"【第{o.chapter_start}–{o.chapter_end}章大纲】\n{o.outline_text}"
        for o in outlines
    ) if outlines else "暂无大纲。"

    next_chapter = get_next_missing_chapter_number(db, novel_id)

    world_context_section = ""
    if use_core_memory and world_context and world_context.strip():
        world_context_section = f"\n<world_knowledge>\n{world_context.strip()}\n</world_knowledge>\n"
        try:
            systems = (world_debug_summary or {}).get("injected_systems") or []
            entities = (world_debug_summary or {}).get("injected_entities") or []
            rels = (world_debug_summary or {}).get("injected_relationships") or []
            logger.info(
                "Injecting WorldModel context for novel %s: %s systems, %s entities, %s relationships",
                novel_id,
                len(systems),
                len(entities),
                len(rels),
            )
        except Exception:
            logger.info("Injecting WorldModel context for novel %s", novel_id)

    lorebook_context = ""
    if use_lorebook:
        try:
            lore_manager = cache_manager.get_lore(novel_id)
            if not lore_manager:
                lore_manager = LoreManager(novel_id)
                lore_manager.build_automaton(db)
                cache_manager.set_lore(novel_id, lore_manager)
            context, matched_entries, total_tokens = lore_manager.get_injection_context(
                recent_content,
                max_tokens=settings.lore_max_total_tokens,
            )
            if context:
                lorebook_context = f"\n<supplementary_lore>\n{context}\n</supplementary_lore>"
                logger.info(
                    f"Injecting Lorebook context for novel {novel_id}: "
                    f"{len(matched_entries)} entries, {total_tokens} tokens"
                )
        except Exception as e:
            logger.warning(f"Failed to get Lorebook context for novel {novel_id}: {e}")

    combined_context = ""
    if world_context_section:
        combined_context += world_context_section
    if lorebook_context:
        combined_context += lorebook_context

    user_instruction = ""
    if prompt and prompt.strip():
        user_instruction = f"\n<user_instruction>\n{prompt.strip()}\n</user_instruction>\n"
        logger.info(f"User instruction provided for novel {novel_id}: {prompt[:50]}...")

    constraints_section = (narrative_constraints or "").strip()

    generation_prompt = CONTINUATION_PROMPT.format(
        title=novel.title,
        next_chapter=next_chapter,
        outline=outline_content,
        world_context=combined_context,
        recent_chapters=recent_content,
        narrative_constraints=f"\n{constraints_section}\n" if constraints_section else "",
    )

    if user_instruction:
        generation_prompt += user_instruction

    generation_prompt += f"\n请{length_guidance}，开始续写第{next_chapter}章："

    return generation_prompt, effective_max_tokens, {
        "next_chapter": next_chapter,
    }


async def continue_novel(
    db: Session,
    novel_id: int,
    num_versions: int = 1,
    use_core_memory: bool = True,
    use_lorebook: bool = True,
    prompt: str | None = None,
    max_tokens: int | None = None,
    target_chars: int | None = None,
    context_chapters: int | None = None,
    world_context: str | None = None,
    narrative_constraints: str | None = None,
    world_debug_summary: dict | None = None,
    llm_config: dict | None = None,
    temperature: float | None = None,
    user_id: int | None = None,
) -> List[Continuation]:
    """
    Generate continuation for a novel.

    Args:
        db: Database session
        novel_id: ID of the novel to continue
        num_versions: Number of continuation versions to generate
        use_lorebook: Whether to inject Lorebook context
        prompt: Optional user instruction for guiding the continuation
        max_tokens: Optional max tokens for generation (defaults to settings.default_continuation_tokens)
        target_chars: Optional target length in characters for the continuation
        context_chapters: Override for settings.max_context_chapters
        world_context: Injected WorldModel context (already visibility-filtered)
        narrative_constraints: Extracted narrative constraints from WorldSystem (injected as dedicated prompt section)
        world_debug_summary: Optional debug summary (used for logging/traceability)

    Returns:
        List of generated Continuation objects
    """
    generation_prompt, effective_max_tokens, build_info = await _build_continuation_prompt(
        db=db,
        novel_id=novel_id,
        use_core_memory=use_core_memory,
        use_lorebook=use_lorebook,
        prompt=prompt,
        max_tokens=max_tokens,
        target_chars=target_chars,
        context_chapters=context_chapters,
        world_context=world_context,
        narrative_constraints=narrative_constraints,
        world_debug_summary=world_debug_summary,
    )
    next_chapter = build_info["next_chapter"]

    # Generate continuations
    continuations = []
    llm_kwargs = llm_config or {}
    if temperature is not None:
        llm_kwargs["temperature"] = temperature
    for i in range(num_versions):
        logger.info(f"Generating continuation {i+1}/{num_versions} for novel {novel_id}")

        content = await ai_client.generate(
            prompt=generation_prompt,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=effective_max_tokens,
            user_id=user_id,
            **llm_kwargs,
        )

        content = _sanitize_continuation_content(content)

        if target_chars:
            content = _trim_to_target_chars(content, target_chars)

        continuation = Continuation(
            novel_id=novel_id,
            chapter_number=next_chapter,
            content=content,
            prompt_used=generation_prompt,
        )
        db.add(continuation)
        db.commit()
        db.refresh(continuation)
        continuations.append(continuation)

    return continuations


async def continue_novel_stream(
    db: Session,
    novel_id: int,
    num_versions: int = 1,
    use_core_memory: bool = True,
    use_lorebook: bool = True,
    prompt: str | None = None,
    max_tokens: int | None = None,
    target_chars: int | None = None,
    context_chapters: int | None = None,
    world_context: str | None = None,
    narrative_constraints: str | None = None,
    world_debug_summary: dict | None = None,
    llm_config: dict | None = None,
    request_id: str | None = None,
    temperature: float | None = None,
    user_id: int | None = None,
) -> AsyncGenerator[dict, None]:
    """Yield NDJSON events for streaming continuation generation."""
    generation_prompt, effective_max_tokens, build_info = await _build_continuation_prompt(
        db=db,
        novel_id=novel_id,
        use_core_memory=use_core_memory,
        use_lorebook=use_lorebook,
        prompt=prompt,
        max_tokens=max_tokens,
        target_chars=target_chars,
        context_chapters=context_chapters,
        world_context=world_context,
        narrative_constraints=narrative_constraints,
        world_debug_summary=world_debug_summary,
    )
    next_chapter = build_info["next_chapter"]
    llm_kwargs = llm_config or {}
    if temperature is not None:
        llm_kwargs["temperature"] = temperature

    def _error_event(*, code: str, message: str, variant: int | None = None) -> dict:
        event: dict = {"type": "error", "code": code, "message": message}
        if variant is not None:
            event["variant"] = int(variant)
        if request_id:
            event["request_id"] = request_id
        return event

    yield {
        "type": "start",
        "variant": 0,
        "total_variants": num_versions,
        "debug": world_debug_summary or None,
    }

    # Stream variant 0
    full_content = ""
    continuation_ids: list[int] = []
    try:
        async for chunk in ai_client.generate_stream(
            prompt=generation_prompt,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=effective_max_tokens,
            user_id=user_id,
            **llm_kwargs,
        ):
            full_content += chunk
            yield {"type": "token", "variant": 0, "content": chunk}
    except Exception:
        logger.exception(
            "continue_novel_stream: variant 0 streaming failed (request_id=%s, novel_id=%s)",
            request_id,
            novel_id,
        )
        yield _error_event(code="llm_stream_failed", message="续写生成失败，请重试", variant=0)
    else:
        full_content = _sanitize_continuation_content(full_content)
        if target_chars:
            full_content = _trim_to_target_chars(full_content, target_chars)

        continuation = Continuation(
            novel_id=novel_id,
            chapter_number=next_chapter,
            content=full_content,
            prompt_used=generation_prompt,
        )
        db.add(continuation)
        try:
            db.commit()
            db.refresh(continuation)
        except Exception:
            db.rollback()
            try:
                db.expunge(continuation)
            except Exception:
                pass
            logger.exception(
                "continue_novel_stream: variant 0 DB persist failed (request_id=%s, novel_id=%s)",
                request_id,
                novel_id,
            )
            yield _error_event(code="db_persist_failed", message="保存续写结果失败，请重试", variant=0)
        else:
            continuation_ids.append(int(continuation.id))
            # Include final content so the client can reconcile any trimming/normalization.
            yield {
                "type": "variant_done",
                "variant": 0,
                "continuation_id": continuation.id,
                "content": continuation.content,
            }

    # Generate remaining variants in parallel (non-streaming generation, sequential DB writes)
    if num_versions > 1:
        async def _generate_variant_content(variant_idx: int) -> dict:
            try:
                content = await ai_client.generate(
                    prompt=generation_prompt,
                    system_prompt=SYSTEM_PROMPT,
                    max_tokens=effective_max_tokens,
                    user_id=user_id,
                    **llm_kwargs,
                )

                content = _sanitize_continuation_content(content)
                if target_chars:
                    content = _trim_to_target_chars(content, target_chars)
                return {"variant": variant_idx, "ok": True, "content": content}
            except Exception:
                logger.exception(
                    "continue_novel_stream: variant %s generate failed (request_id=%s, novel_id=%s)",
                    variant_idx,
                    request_id,
                    novel_id,
                )
                return {"variant": variant_idx, "ok": False}

        results = await asyncio.gather(
            *[_generate_variant_content(i) for i in range(1, num_versions)]
        )

        for result in results:
            variant_idx = int(result["variant"])
            if not result.get("ok"):
                yield _error_event(code="llm_generate_failed", message="续写生成失败，请重试", variant=variant_idx)
                continue

            content = str(result["content"])
            c = Continuation(
                novel_id=novel_id,
                chapter_number=next_chapter,
                content=content,
                prompt_used=generation_prompt,
            )
            db.add(c)
            try:
                db.commit()
                db.refresh(c)
            except Exception:
                db.rollback()
                try:
                    db.expunge(c)
                except Exception:
                    pass
                logger.exception(
                    "continue_novel_stream: variant %s DB persist failed (request_id=%s, novel_id=%s)",
                    variant_idx,
                    request_id,
                    novel_id,
                )
                yield _error_event(code="db_persist_failed", message="保存续写结果失败，请重试", variant=variant_idx)
            else:
                continuation_ids.append(int(c.id))
                yield {
                    "type": "variant_done",
                    "variant": variant_idx,
                    "continuation_id": c.id,
                    "content": c.content,
                }

    yield {"type": "done", "continuation_ids": continuation_ids}


async def generate_all_outlines(db: Session, novel_id: int) -> List[Outline]:
    """Generate outlines for entire novel (one per 100 chapters)."""
    settings = get_settings()

    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise ValueError(
            f"Novel {novel_id} not found. Please upload a novel first."
        )

    outlines = []
    chunk_size = settings.outline_chunk_size

    chapter_numbers = [
        n
        for (n,) in (
            db.query(Chapter.chapter_number)
            .filter(Chapter.novel_id == novel_id)
            .order_by(Chapter.chapter_number)
            .all()
        )
        if n is not None
    ]
    if not chapter_numbers:
        return outlines

    for idx in range(0, len(chapter_numbers), chunk_size):
        chunk = chapter_numbers[idx : idx + chunk_size]
        start = chunk[0]
        end = chunk[-1]

        # Check if outline already exists
        existing = (
            db.query(Outline)
            .filter(
                Outline.novel_id == novel_id,
                Outline.chapter_start == start,
                Outline.chapter_end == end,
            )
            .first()
        )

        if existing:
            outlines.append(existing)
        else:
            outline = await generate_outline(db, novel_id, start, end)
            outlines.append(outline)

    return outlines
