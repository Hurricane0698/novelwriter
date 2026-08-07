# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""
Continuation generation: prompt assembly with WorldModel context injection,
plus sync and streaming generation drivers sharing one finalize/persist path.
"""

from typing import AsyncGenerator, List
import asyncio
import math
import re
from sqlalchemy.orm import Session
import logging

from app.models import Novel, Continuation
from app.core.ai_client import ai_client
from app.core.continuation_text import format_chapter_heading_for_prompt, format_next_chapter_reference
from app.core.text import PromptKey, get_prompt
from app.core.text.snippets import SnippetKey, get_snippet
from app.config import get_settings, resolve_context_chapters
from app.core.chapter_numbering import get_next_missing_chapter_number, load_recent_chapters
from app.core.llm_config import ResolvedLlmConfig
from app.language import resolve_prompt_locale
from app.language_policy import get_language_policy

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


def _compute_generation_target_chars(target_chars: int | None, overrun_ratio: float) -> int | None:
    if not target_chars:
        return None
    return max(target_chars, math.ceil(target_chars * max(1.0, overrun_ratio)))


def _build_length_guidance(
    target_chars: int | None,
    generation_target_chars: int | None,
    min_ratio: float,
    *,
    prompt_locale: str | None = None,
) -> str:
    if target_chars:
        min_chars = max(1, math.floor(target_chars * min_ratio))
        prompt_target = generation_target_chars or target_chars
        natural_ceiling = max(prompt_target, math.ceil(target_chars * 1.1))
        return get_snippet(SnippetKey.LENGTH_GUIDANCE_TARGET, prompt_locale).format(
            target=prompt_target, min_chars=min_chars, ceiling=natural_ceiling,
        )
    return get_snippet(SnippetKey.LENGTH_GUIDANCE_DEFAULT, prompt_locale)


def _build_system_prompt(length_guidance: str, *, prompt_locale: str) -> str:
    length_header = get_snippet(SnippetKey.SYSTEM_LENGTH_HEADER, prompt_locale)
    length_rules = get_snippet(SnippetKey.SYSTEM_LENGTH_RULES, prompt_locale)
    return (
        f"{get_prompt(PromptKey.SYSTEM, locale=prompt_locale)}\n\n"
        f"{length_header}\n"
        f"- {length_guidance}\n"
        f"{length_rules}"
    )


def _compute_max_tokens(
    target_chars: int | None,
    max_tokens: int | None,
    default_tokens: int,
    chars_to_tokens_ratio: float,
    token_buffer_ratio: float,
    cap: int = 32000,
) -> int:
    if target_chars:
        estimated = math.ceil(target_chars * chars_to_tokens_ratio)
        estimated = math.ceil(estimated * (1 + token_buffer_ratio))
        return min(cap, max(100, estimated))
    if max_tokens is not None:
        return max_tokens
    return default_tokens


def _finalize_generated_content(
    content: str,
    *,
    target_chars: int | None,
    language: str | None,
) -> str:
    """Shared post-generation pipeline: strip think blocks, trim to target."""
    content = _sanitize_continuation_content(content)
    if target_chars:
        content = _trim_to_target_chars(content, target_chars, language=language)
    return content


def _persist_continuation(
    db: Session,
    *,
    novel_id: int,
    chapter_number: int,
    content: str,
    prompt_used: str,
) -> Continuation:
    """Persist one continuation variant; rolls back and re-raises on failure."""
    continuation = Continuation(
        novel_id=novel_id,
        chapter_number=chapter_number,
        content=content,
        prompt_used=prompt_used,
    )
    db.add(continuation)
    try:
        db.commit()
    except Exception:
        db.rollback()
        try:
            db.expunge(continuation)
        except Exception:
            pass
        raise
    db.refresh(continuation)
    return continuation


def _trim_to_target_chars(text: str, target_chars: int, *, language: str | None = None) -> str:
    settings = get_settings()
    overrun_ratio = max(1.0, settings.continuation_trim_overrun_ratio)
    max_overrun_chars = math.ceil(target_chars * (overrun_ratio - 1.0))
    policy = get_language_policy(language, sample_text=text)
    return policy.trim_to_sentence_boundary(
        text, target_chars, max_overrun_chars=max_overrun_chars
    )


async def _build_continuation_prompt(
    db: Session,
    novel_id: int,
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
    generation_target_chars = _compute_generation_target_chars(
        target_chars,
        settings.continuation_prompt_target_overrun_ratio,
    )

    effective_max_tokens = _compute_max_tokens(
        target_chars=target_chars,
        max_tokens=max_tokens,
        default_tokens=settings.default_continuation_tokens,
        chars_to_tokens_ratio=settings.continuation_chars_to_tokens_ratio,
        token_buffer_ratio=settings.continuation_token_buffer_ratio,
        cap=settings.max_continuation_tokens,
    )

    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise ValueError(
            f"Novel {novel_id} not found. Please upload a novel first using POST /api/novels/upload."
        )
    prompt_locale = resolve_prompt_locale(novel_language=getattr(novel, "language", None))

    length_guidance = _build_length_guidance(
        target_chars,
        generation_target_chars,
        settings.continuation_min_target_ratio,
        prompt_locale=prompt_locale,
    )

    effective_context_chapters = resolve_context_chapters(
        context_chapters,
        default=settings.max_context_chapters,
        max_value=max(1, int(getattr(novel, "total_chapters", 0) or 1)),
    )
    recent_chapters = load_recent_chapters(db, novel_id, effective_context_chapters)

    if not recent_chapters:
        raise ValueError(
            f"Novel {novel_id} has no chapters. Cannot generate continuation without existing content."
        )

    recent_content = "\n\n".join(
        format_chapter_heading_for_prompt(
            ch.chapter_number,
            ch.title,
            locale=prompt_locale,
            source_chapter_label=getattr(ch, "source_chapter_label", None),
        ) + f"\n{ch.content}"
        for ch in recent_chapters
    )

    next_chapter = get_next_missing_chapter_number(db, novel_id)
    latest_recent_chapter = recent_chapters[-1]
    next_chapter_reference = format_next_chapter_reference(
        next_chapter,
        latest_source_chapter_label=getattr(latest_recent_chapter, "source_chapter_label", None),
        latest_source_chapter_number=getattr(latest_recent_chapter, "source_chapter_number", None),
        locale=prompt_locale,
    )

    world_context_section = ""
    if world_context and world_context.strip():
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

    combined_context = ""
    if world_context_section:
        combined_context += world_context_section

    user_instruction = ""
    if prompt and prompt.strip():
        user_instruction = f"\n<user_instruction>\n{prompt.strip()}\n</user_instruction>\n"
        logger.info(f"User instruction provided for novel {novel_id}: {prompt[:50]}...")

    constraints_section = (narrative_constraints or "").strip()

    generation_prompt = get_prompt(PromptKey.CONTINUATION, locale=prompt_locale).format(
        title=novel.title,
        next_chapter=next_chapter,
        next_chapter_reference=next_chapter_reference,
        world_context=combined_context,
        narrative_constraints=f"\n{constraints_section}\n" if constraints_section else "",
    )

    if user_instruction:
        generation_prompt += user_instruction

    # Style anchor + recent chapters LAST: autoregressive generation continues
    # the style of the most recently seen text.  Placing the novel prose at the
    # tail of the prompt exploits this inertia so the model's first tokens
    # naturally match the original register.
    style_anchor = get_snippet(SnippetKey.STYLE_ANCHOR, prompt_locale)
    continue_instruction = get_snippet(SnippetKey.CONTINUE_INSTRUCTION, prompt_locale).format(
        n=next_chapter,
        reference=next_chapter_reference,
    )
    generation_prompt += (
        f"\n{style_anchor}\n\n"
        f"<recent_chapters>\n{recent_content}\n</recent_chapters>\n"
        f"{continue_instruction}"
    )

    return generation_prompt, effective_max_tokens, {
        "next_chapter": next_chapter,
        "next_chapter_reference": next_chapter_reference,
        "novel_language": getattr(novel, "language", None),
        "system_prompt": _build_system_prompt(length_guidance, prompt_locale=prompt_locale),
    }


async def continue_novel(
    db: Session,
    novel_id: int,
    num_versions: int = 1,
    prompt: str | None = None,
    max_tokens: int | None = None,
    target_chars: int | None = None,
    context_chapters: int | None = None,
    world_context: str | None = None,
    narrative_constraints: str | None = None,
    world_debug_summary: dict | None = None,
    *,
    llm_config: ResolvedLlmConfig,
    temperature: float | None = None,
    user_id: int | None = None,
) -> List[Continuation]:
    """
    Generate continuation for a novel.

    Args:
        db: Database session
        novel_id: ID of the novel to continue
        num_versions: Number of continuation versions to generate
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
        prompt=prompt,
        max_tokens=max_tokens,
        target_chars=target_chars,
        context_chapters=context_chapters,
        world_context=world_context,
        narrative_constraints=narrative_constraints,
        world_debug_summary=world_debug_summary,
    )
    next_chapter = build_info["next_chapter"]
    novel_language = build_info.get("novel_language")
    system_prompt = build_info["system_prompt"]

    # Generate continuations
    continuations = []
    generation_temperature = 0.8 if temperature is None else temperature
    for i in range(num_versions):
        logger.info(f"Generating continuation {i+1}/{num_versions} for novel {novel_id}")

        content = await ai_client.generate(
            prompt=generation_prompt,
            system_prompt=system_prompt,
            max_tokens=effective_max_tokens,
            temperature=generation_temperature,
            llm_config=llm_config,
            user_id=user_id,
        )

        content = _finalize_generated_content(
            content, target_chars=target_chars, language=novel_language,
        )
        continuation = _persist_continuation(
            db,
            novel_id=novel_id,
            chapter_number=next_chapter,
            content=content,
            prompt_used=generation_prompt,
        )
        continuations.append(continuation)

    return continuations


async def continue_novel_stream(
    db: Session,
    novel_id: int,
    num_versions: int = 1,
    prompt: str | None = None,
    max_tokens: int | None = None,
    target_chars: int | None = None,
    context_chapters: int | None = None,
    world_context: str | None = None,
    narrative_constraints: str | None = None,
    world_debug_summary: dict | None = None,
    *,
    llm_config: ResolvedLlmConfig,
    request_id: str | None = None,
    temperature: float | None = None,
    user_id: int | None = None,
) -> AsyncGenerator[dict, None]:
    """Yield NDJSON events for streaming continuation generation."""
    generation_prompt, effective_max_tokens, build_info = await _build_continuation_prompt(
        db=db,
        novel_id=novel_id,
        prompt=prompt,
        max_tokens=max_tokens,
        target_chars=target_chars,
        context_chapters=context_chapters,
        world_context=world_context,
        narrative_constraints=narrative_constraints,
        world_debug_summary=world_debug_summary,
    )
    next_chapter = build_info["next_chapter"]
    novel_language = build_info.get("novel_language")
    system_prompt = build_info["system_prompt"]
    generation_temperature = 0.8 if temperature is None else temperature

    def _error_event(*, code: str, message: str, message_key: str | None = None, variant: int | None = None) -> dict:
        event: dict = {"type": "error", "code": code, "message": message}
        if message_key is not None:
            event["message_key"] = message_key
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
            system_prompt=system_prompt,
            max_tokens=effective_max_tokens,
            temperature=generation_temperature,
            llm_config=llm_config,
            user_id=user_id,
        ):
            full_content += chunk
            yield {"type": "token", "variant": 0, "content": chunk}
    except Exception:
        logger.exception(
            "continue_novel_stream: variant 0 streaming failed (request_id=%s, novel_id=%s)",
            request_id,
            novel_id,
        )
        yield _error_event(code="llm_stream_failed", message="续写生成失败，请重试", message_key="continuation.error.llm_stream_failed", variant=0)
    else:
        full_content = _finalize_generated_content(
            full_content, target_chars=target_chars, language=novel_language,
        )
        try:
            continuation = _persist_continuation(
                db,
                novel_id=novel_id,
                chapter_number=next_chapter,
                content=full_content,
                prompt_used=generation_prompt,
            )
        except Exception:
            logger.exception(
                "continue_novel_stream: variant 0 DB persist failed (request_id=%s, novel_id=%s)",
                request_id,
                novel_id,
            )
            yield _error_event(code="db_persist_failed", message="保存续写结果失败，请重试", message_key="continuation.error.db_persist_failed", variant=0)
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
                    system_prompt=system_prompt,
                    max_tokens=effective_max_tokens,
                    temperature=generation_temperature,
                    llm_config=llm_config,
                    user_id=user_id,
                )

                content = _finalize_generated_content(
                    content, target_chars=target_chars, language=novel_language,
                )
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
                yield _error_event(code="llm_generate_failed", message="续写生成失败，请重试", message_key="continuation.error.llm_generate_failed", variant=variant_idx)
                continue

            content = str(result["content"])
            try:
                c = _persist_continuation(
                    db,
                    novel_id=novel_id,
                    chapter_number=next_chapter,
                    content=content,
                    prompt_used=generation_prompt,
                )
            except Exception:
                logger.exception(
                    "continue_novel_stream: variant %s DB persist failed (request_id=%s, novel_id=%s)",
                    variant_idx,
                    request_id,
                    novel_id,
                )
                yield _error_event(code="db_persist_failed", message="保存续写结果失败，请重试", message_key="continuation.error.db_persist_failed", variant=variant_idx)
            else:
                continuation_ids.append(int(c.id))
                yield {
                    "type": "variant_done",
                    "variant": variant_idx,
                    "continuation_id": c.id,
                    "content": c.content,
                }

    yield {"type": "done", "continuation_ids": continuation_ids}
