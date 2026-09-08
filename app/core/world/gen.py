# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only


"""World generation orchestration: collect every model output, then persist drafts."""

from __future__ import annotations

from sqlalchemy.orm import Session
from app.config import get_settings
from app.core.ai_client import ai_client
from app.core.llm_config import ResolvedLlmConfig
from app.core.text import PromptKey, get_prompt
from app.core.text.snippets import SnippetKey, get_snippet
from app.language import resolve_prompt_locale
from app.models import Novel
from app.schemas import WorldGenerateResponse, WorldGenerateWarning
from .generation_normalization import _merge_worldgen_outputs
from .generation_persistence import persist_world_drafts

# Keep the existing extraction-schema import path available to callers.
from .generation_schema import (
    WorldGenEntity as WorldGenEntity,
    WorldGenRelationship as WorldGenRelationship,
    WorldGenSystemItem as WorldGenSystemItem,
    WorldGenSystem as WorldGenSystem,
    WorldGenLLMOutput as WorldGenLLMOutput,
)


def _chunk_world_generation_text(text: str) -> list[str]:
    settings = get_settings()
    normalized = (text or "").strip()
    if not normalized:
        return []

    chunk_chars = max(1, int(settings.world_generation_chunk_chars))
    max_chunks = max(1, int(settings.world_generation_max_chunks))
    overlap_chars = max(0, int(settings.world_generation_chunk_overlap_chars))
    overlap_chars = min(overlap_chars, chunk_chars - 1)

    if len(normalized) <= chunk_chars:
        return [normalized]

    step = max(1, chunk_chars - overlap_chars)
    chunks: list[str] = []
    start = 0
    while start < len(normalized) and len(chunks) < max_chunks:
        end = min(len(normalized), start + chunk_chars)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start += step
    return chunks


def _build_world_generation_prompt(
    *,
    text: str,
    chunk_index: int,
    chunk_count: int,
    prompt_locale: str,
) -> str:
    if chunk_count > 1:
        chunk_directive = get_snippet(
            SnippetKey.WORLDGEN_CHUNK_DIRECTIVE_MULTI,
            prompt_locale,
        ).format(chunk_index=chunk_index, chunk_count=chunk_count)
    else:
        chunk_directive = get_snippet(
            SnippetKey.WORLDGEN_CHUNK_DIRECTIVE_SINGLE,
            prompt_locale,
        )
    return get_prompt(PromptKey.WORLD_GEN, locale=prompt_locale).format(
        text=text.strip(),
        chunk_directive=chunk_directive,
    )


async def generate_world_drafts(
    *,
    db: Session,
    novel_id: int,
    text: str,
    llm_config: ResolvedLlmConfig,
    user_id: int | None = None,
) -> WorldGenerateResponse:
    """Generate and persist draft world items from free text.

    Notes:
    - Deletes previous world generation drafts (origin=worldgen,status=draft) before inserting new ones.
    - Confirmed/manual rows are preserved.
    """

    warnings: list[WorldGenerateWarning] = []

    settings = get_settings()
    novel = db.query(Novel.language).filter(Novel.id == novel_id).first()
    prompt_locale = resolve_prompt_locale(
        novel_language=getattr(novel, "language", None)
    )
    chunks = _chunk_world_generation_text(text)
    chunk_count = len(chunks)
    extracted_parts: list[WorldGenLLMOutput] = []

    for idx, chunk_text in enumerate(chunks, start=1):
        prompt = _build_world_generation_prompt(
            text=chunk_text,
            chunk_index=idx,
            chunk_count=chunk_count,
            prompt_locale=prompt_locale,
        )
        extracted_parts.append(
            await ai_client.generate_structured(
                prompt=prompt,
                response_model=WorldGenLLMOutput,
                system_prompt=get_prompt(
                    PromptKey.WORLD_GEN_SYSTEM, locale=prompt_locale
                ),
                # Structured extraction — low temperature for schema adherence.
                temperature=0.3,
                max_tokens=settings.world_generation_chunk_max_tokens,
                llm_config=llm_config,
                user_id=user_id,
            )
        )

    if len(extracted_parts) <= 1:
        extracted = extracted_parts[0] if extracted_parts else WorldGenLLMOutput()
    else:
        extracted = _merge_worldgen_outputs(extracted_parts, warnings=warnings)

    return persist_world_drafts(
        db=db, novel_id=novel_id, extracted=extracted, warnings=warnings
    )
