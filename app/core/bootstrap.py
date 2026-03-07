# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import logging
import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path
from typing import Callable, Protocol, Sequence

from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.ai_client import AIClient, StructuredOutputParseError, get_client
from app.core.llm_semaphore import acquire_llm_slot_blocking, release_llm_slot
from app.core.window_index import NovelIndex, WindowRef
from app.database import SessionLocal
from app.models import BootstrapJob, Chapter, Novel, WorldEntity, WorldRelationship
from app.world_relationships import canonicalize_relationship_label

try:
    import ahocorasick
except ImportError:  # pragma: no cover - local fallback when dependency is missing
    ahocorasick = None

try:
    import jieba
except ImportError:  # pragma: no cover - local fallback when dependency is missing
    jieba = None

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SIZE = 500
DEFAULT_WINDOW_STEP = 250
DEFAULT_MIN_WINDOW_COUNT = 3
DEFAULT_MIN_WINDOW_RATIO = 0.005
DEFAULT_MAX_CANDIDATES = 500
DEFAULT_LLM_TEMPERATURE = 0.3
DEFAULT_COMMON_WORDS_DIR = "data/common_words"
DEFAULT_CJK_SPACE_RATIO_THRESHOLD = 0.05
DEFAULT_STALE_JOB_TIMEOUT_SECONDS = 900
BOOTSTRAP_PARSE_ERROR_MESSAGE = "AI 输出解析失败，请重试"
BOOTSTRAP_GENERIC_ERROR_MESSAGE = "引导扫描失败，请稍后重试"
BOOTSTRAP_MODE_INITIAL = "initial"
BOOTSTRAP_MODE_INDEX_REFRESH = "index_refresh"
BOOTSTRAP_MODE_REEXTRACT = "reextract"
BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS = "replace_bootstrap_drafts"
BOOTSTRAP_DRAFT_POLICY_MERGE = "merge"
LEGACY_ORIGIN_TRACKING_CUTOFF = datetime(2026, 2, 18, tzinfo=timezone.utc)

BOOTSTRAP_STATUS_SEQUENCE = (
    "pending",
    "tokenizing",
    "extracting",
    "windowing",
    "refining",
    "completed",
)
RUNNING_BOOTSTRAP_STATUSES = frozenset(BOOTSTRAP_STATUS_SEQUENCE[:-1])

_ALLOWED_TRANSITIONS = {
    "pending": {"tokenizing", "failed"},
    "tokenizing": {"extracting", "failed"},
    "extracting": {"windowing", "failed"},
    "windowing": {"refining", "failed"},
    "refining": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}

_COMMON_WORD_FILE_BY_LANGUAGE = {
    "zh": "zh.txt",
    "en": "en.txt",
}
_COMMON_WORDS_CACHE: dict[tuple[str, str], frozenset[str]] = {}
_COMMON_WORDS_COMBINED_CACHE: dict[tuple[str, str], frozenset[str]] = {}

_TRIM_CHARS = " \t\r\n.,!?;:\"'()[]{}<>，。！？；：、“”‘’（）【】《》、…·-—"
_KNOWN_BOOTSTRAP_MODES = frozenset(
    {
        BOOTSTRAP_MODE_INITIAL,
        BOOTSTRAP_MODE_INDEX_REFRESH,
        BOOTSTRAP_MODE_REEXTRACT,
    }
)
_KNOWN_REEXTRACT_DRAFT_POLICIES = frozenset(
    {
        BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS,
        BOOTSTRAP_DRAFT_POLICY_MERGE,
    }
)


@dataclass(slots=True)
class ChapterText:
    chapter_id: int
    text: str


@dataclass(slots=True)
class LegacyDraftAmbiguity:
    entity_ids: list[int]
    relationship_ids: list[int]

    def has_any(self) -> bool:
        return bool(self.entity_ids or self.relationship_ids)


class Tokenizer(Protocol):
    def tokenize(self, text: str) -> list[str]:
        ...


class WhitespaceTokenizer:
    def tokenize(self, text: str) -> list[str]:
        return text.split()


class JiebaTokenizer:
    def tokenize(self, text: str) -> list[str]:
        if jieba is None:
            cleaned = "".join(ch if ch not in _TRIM_CHARS else " " for ch in text)
            chunks = [chunk for chunk in cleaned.split() if chunk]
            tokens: list[str] = []
            for chunk in chunks:
                if len(chunk) < 2:
                    continue
                if len(chunk) <= 4:
                    tokens.append(chunk)
                    continue
                tokens.extend(chunk[i : i + 2] for i in range(0, len(chunk) - 1))
            return tokens
        return [token for token in jieba.lcut(text) if token]


class RefinedEntity(BaseModel):
    name: str = Field(min_length=1)
    entity_type: str = "other"
    aliases: list[str] = Field(default_factory=list)


class RefinedRelationship(BaseModel):
    source_name: str = Field(min_length=1)
    target_name: str = Field(min_length=1)
    label: str = Field(min_length=1)


class BootstrapRefinementResult(BaseModel):
    entities: list[RefinedEntity] = Field(default_factory=list)
    relationships: list[RefinedRelationship] = Field(default_factory=list)


def is_running_status(status: str | None) -> bool:
    return status in RUNNING_BOOTSTRAP_STATUSES


def resolve_bootstrap_mode(raw_mode: str | None) -> str:
    mode = (raw_mode or BOOTSTRAP_MODE_INDEX_REFRESH).strip()
    if mode in _KNOWN_BOOTSTRAP_MODES:
        return mode
    return BOOTSTRAP_MODE_INDEX_REFRESH


def resolve_reextract_draft_policy(raw_policy: str | None) -> str:
    policy = (raw_policy or BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS).strip()
    if policy in _KNOWN_REEXTRACT_DRAFT_POLICIES:
        return policy
    return BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS


def is_stale_running_job(
    job: BootstrapJob,
    *,
    stale_after_seconds: int = DEFAULT_STALE_JOB_TIMEOUT_SECONDS,
    now: datetime | None = None,
) -> bool:
    if stale_after_seconds <= 0:
        return False
    if not is_running_status(job.status):
        return False

    updated_at = job.updated_at or job.created_at
    if updated_at is None:
        return False

    if updated_at.tzinfo is not None:
        updated_at = updated_at.astimezone(timezone.utc).replace(tzinfo=None)

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is not None:
        current_time = current_time.astimezone(timezone.utc).replace(tzinfo=None)

    return updated_at <= (current_time - timedelta(seconds=stale_after_seconds))


def transition_bootstrap_job(
    job: BootstrapJob,
    new_status: str,
    *,
    detail: str | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    current = str(job.status)
    allowed = _ALLOWED_TRANSITIONS.get(current)
    if allowed is None:
        raise ValueError(f"Unknown bootstrap status: {current}")
    if new_status not in allowed:
        raise ValueError(f"Invalid bootstrap transition: {current} -> {new_status}")

    current_progress = job.progress or {}
    if new_status in BOOTSTRAP_STATUS_SEQUENCE:
        step = BOOTSTRAP_STATUS_SEQUENCE.index(new_status)
    else:
        step = int(current_progress.get("step", 0))

    job.status = new_status
    job.progress = {"step": step, "detail": detail or new_status}

    if new_status == "completed":
        job.result = result or {
            "entities_found": 0,
            "relationships_found": 0,
            "index_refresh_only": False,
        }
        job.error = None
    elif new_status == "failed":
        job.error = error or "Bootstrap failed"


def detect_language(text: str, *, cjk_space_ratio_threshold: float = DEFAULT_CJK_SPACE_RATIO_THRESHOLD) -> str:
    if not text:
        return "en"
    space_ratio = text.count(" ") / max(len(text), 1)
    if space_ratio < cjk_space_ratio_threshold:
        return "zh"
    return "en"


def get_tokenizer(
    language: str,
    *,
    cjk_tokenizer: Tokenizer | None = None,
    whitespace_tokenizer: Tokenizer | None = None,
) -> Tokenizer:
    if language == "zh":
        return cjk_tokenizer or JiebaTokenizer()
    return whitespace_tokenizer or WhitespaceTokenizer()


def tokenize_text(
    text: str,
    *,
    language: str | None = None,
    tokenizer: Tokenizer | None = None,
) -> tuple[str, list[str]]:
    resolved_language = language or detect_language(text)
    resolved_tokenizer = tokenizer or get_tokenizer(resolved_language)
    return resolved_language, resolved_tokenizer.tokenize(text)


def normalize_token(token: str) -> str:
    return token.strip(_TRIM_CHARS)


def _resolve_common_words_base_dir(common_words_dir: str) -> Path:
    base_dir = Path(common_words_dir)
    if not base_dir.is_absolute():
        base_dir = Path(__file__).resolve().parents[2] / base_dir
    return base_dir.resolve()


def _load_common_words_file(file_path: Path, language_code: str) -> frozenset[str]:
    cache_key = (str(file_path), language_code)
    cached = _COMMON_WORDS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if not file_path.exists():
        raise FileNotFoundError(f"Common words file does not exist: {file_path}")

    words: set[str] = set()
    with file_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            word = raw_line.strip()
            if not word or word.startswith("#"):
                continue
            words.add(word)
            words.add(word.lower())

    frozen_words = frozenset(words)
    _COMMON_WORDS_CACHE[cache_key] = frozen_words
    return frozen_words


def load_common_words(language: str, *, common_words_dir: str = DEFAULT_COMMON_WORDS_DIR) -> set[str]:
    normalized_language = "zh" if language == "zh" else "en"
    base_dir = _resolve_common_words_base_dir(common_words_dir)
    combined_cache_key = (str(base_dir), normalized_language)
    cached = _COMMON_WORDS_COMBINED_CACHE.get(combined_cache_key)
    if cached is not None:
        return set(cached)

    fallback_language = "en" if normalized_language == "zh" else "zh"
    primary_words = _load_common_words_file(
        base_dir / _COMMON_WORD_FILE_BY_LANGUAGE[normalized_language],
        normalized_language,
    )
    fallback_words = _load_common_words_file(
        base_dir / _COMMON_WORD_FILE_BY_LANGUAGE[fallback_language],
        fallback_language,
    )
    merged = frozenset(set(primary_words) | set(fallback_words))
    _COMMON_WORDS_COMBINED_CACHE[combined_cache_key] = merged
    return set(merged)


def extract_candidates(tokens: Sequence[str], common_words: set[str]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for token in tokens:
        normalized = normalize_token(token)
        if len(normalized) < 2:
            continue
        lowered = normalized.lower()
        if normalized in common_words or lowered in common_words:
            continue
        counts[normalized] += 1
    return dict(counts)


def _window_offsets(text_length: int, window_size: int, window_step: int) -> list[int]:
    if text_length <= 0:
        return []
    if text_length <= window_size:
        return [0]

    offsets = list(range(0, max(text_length - window_size + 1, 1), window_step))
    last_start = text_length - window_size
    if offsets and offsets[-1] != last_start:
        offsets.append(last_start)
    return offsets


def _build_automaton(candidate_names: Sequence[str]):
    if ahocorasick is None:
        return None

    automaton = ahocorasick.Automaton()
    for name in candidate_names:
        if name:
            automaton.add_word(name, name)
    automaton.make_automaton()
    return automaton


def _match_candidates_in_window(window_text: str, candidate_names: Sequence[str], automaton) -> set[str]:
    if not window_text:
        return set()

    if automaton is not None:
        matches: set[str] = set()
        for _, candidate in automaton.iter(window_text):
            matches.add(candidate)
        return matches

    return {candidate for candidate in candidate_names if candidate in window_text}


def build_window_index(
    chapters: Sequence[ChapterText],
    candidates: dict[str, int],
    *,
    window_size: int = DEFAULT_WINDOW_SIZE,
    window_step: int = DEFAULT_WINDOW_STEP,
    min_window_count: int = DEFAULT_MIN_WINDOW_COUNT,
    min_window_ratio: float = DEFAULT_MIN_WINDOW_RATIO,
) -> tuple[NovelIndex, dict[str, int]]:
    if window_size <= 0 or window_step <= 0:
        raise ValueError("Window size and step must be positive")
    if min_window_count < 1:
        raise ValueError("min_window_count must be >= 1")
    if min_window_ratio < 0:
        raise ValueError("min_window_ratio must be >= 0")

    candidate_names = [name for name in candidates if name]
    if not candidate_names or not chapters:
        return NovelIndex(), {}

    automaton = _build_automaton(candidate_names)

    entity_windows_raw: dict[str, list[WindowRef]] = defaultdict(list)
    window_entities_raw: dict[int, set[str]] = defaultdict(set)
    importance_counter: Counter[str] = Counter()

    total_windows = 0
    window_id = 1

    for chapter in chapters:
        chapter_text = chapter.text or ""
        if not chapter_text.strip():
            continue
        for start_pos in _window_offsets(len(chapter_text), window_size, window_step):
            end_pos = min(start_pos + window_size, len(chapter_text))
            window_text = chapter_text[start_pos:end_pos]
            total_windows += 1

            present_candidates = _match_candidates_in_window(window_text, candidate_names, automaton)
            if not present_candidates:
                window_id += 1
                continue

            entity_count = len(present_candidates)
            for candidate in present_candidates:
                ref = WindowRef(
                    window_id=window_id,
                    chapter_id=chapter.chapter_id,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    entity_count=entity_count,
                )
                entity_windows_raw[candidate].append(ref)
                window_entities_raw[window_id].add(candidate)
                importance_counter[candidate] += 1
            window_id += 1

    if total_windows == 0:
        return NovelIndex(), {}

    threshold = max(min_window_count, math.ceil(total_windows * min_window_ratio))

    filtered_entity_windows: dict[str, list[WindowRef]] = {}
    filtered_window_entities: dict[int, set[str]] = defaultdict(set)
    filtered_importance: dict[str, int] = {}

    for candidate, count in importance_counter.items():
        if count < threshold:
            continue
        windows = sorted(entity_windows_raw[candidate], key=lambda ref: (-ref.entity_count, ref.window_id))
        filtered_entity_windows[candidate] = windows
        filtered_importance[candidate] = count
        for window_ref in windows:
            filtered_window_entities[window_ref.window_id].add(candidate)

    return (
        NovelIndex(
            entity_windows=filtered_entity_windows,
            window_entities=dict(filtered_window_entities),
        ),
        filtered_importance,
    )


def compute_cooccurrence(index: NovelIndex) -> list[tuple[str, str, int]]:
    pair_counts: Counter[tuple[str, str]] = Counter()
    for entities in index.window_entities.values():
        if len(entities) < 2:
            continue
        for left, right in combinations(sorted(entities), 2):
            pair_counts[(left, right)] += 1

    return sorted(
        [(left, right, count) for (left, right), count in pair_counts.items()],
        key=lambda item: (-item[2], item[0], item[1]),
    )


def _build_refinement_prompt(
    importance: dict[str, int],
    cooccurrence_pairs: Sequence[tuple[str, str, int]],
    *,
    max_candidates: int,
) -> str:
    sorted_candidates = sorted(importance.items(), key=lambda item: (-item[1], item[0]))[:max_candidates]
    sorted_pairs = list(cooccurrence_pairs[: max_candidates * 2])

    candidate_lines = "\n".join([f"- {name}: {count}" for name, count in sorted_candidates]) or "- (none)"
    pair_lines = "\n".join([f"- {left} -- {right}: {count}" for left, right, count in sorted_pairs]) or "- (none)"

    return (
        "你正在从一部小说的候选词中提炼出世界观实体和关系。\n\n"
        "## 输入\n\n"
        "候选词（名称: 出现窗口数）:\n"
        f"{candidate_lines}\n\n"
        "共现对（名称A -- 名称B: 共现次数）:\n"
        f"{pair_lines}\n\n"
        "## 任务\n\n"
        "1) **过滤噪声**: 去除动词、形容词、普通名词等非实体词（如「一声」「那个」「知道」）。\n"
        "2) **合并别名**: 同一角色/地点的不同称呼合并为一个实体，全名为 name，其余放 aliases。"
        "例如：「顾慎为」和「顾兄」→ name=顾慎为, aliases=[顾兄]；「荷女」和「小荷」→ name=荷女, aliases=[小荷]。\n"
        "3) **分类**: entity_type 从以下选择: Character, Location, Item, Faction, Concept, other。\n"
        "4) **关系标签**: label 必须是具体且有信息量的描述（3-6字），能让读者一眼理解两者的关系。"
        "禁止使用「关联」「相关」「部属」等笼统词。"
        "好的例子: 父女、师徒、宿敌、青梅竹马、同门师兄弟、主仆、持有、坐落于、效忠于。"
        "坏的例子: 关联、相关、部属、关系。\n"
        "5) 只输出确信度高的实体和关系，宁缺毋滥。\n\n"
        "## 示例输出片段\n\n"
        "```json\n"
        "{\n"
        '  "entities": [\n'
        '    {"name": "顾慎为", "entity_type": "Character", "aliases": ["顾兄", "小顾"]},\n'
        '    {"name": "太玄宗", "entity_type": "Faction", "aliases": []}\n'
        "  ],\n"
        '  "relationships": [\n'
        '    {"source_name": "顾慎为", "target_name": "太玄宗", "label": "弟子出身"},\n'
        '    {"source_name": "独步王", "target_name": "雨公子", "label": "父女"}\n'
        "  ]\n"
        "}\n"
        "```\n\n"
        "请直接返回完整 JSON。\n"
    )


async def refine_candidates_with_llm(
    importance: dict[str, int],
    cooccurrence_pairs: Sequence[tuple[str, str, int]],
    *,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    temperature: float = DEFAULT_LLM_TEMPERATURE,
    client: AIClient | None = None,
    llm_config: dict | None = None,
    user_id: int | None = None,
) -> BootstrapRefinementResult:
    if not importance:
        return BootstrapRefinementResult()

    prompt = _build_refinement_prompt(importance, cooccurrence_pairs, max_candidates=max_candidates)
    llm_kwargs = llm_config or {}
    ai = client or get_client()
    return await ai.generate_structured(
        prompt=prompt,
        response_model=BootstrapRefinementResult,
        system_prompt="You are a precise information extraction assistant.",
        temperature=temperature,
        max_tokens=8000,
        role="editor",
        user_id=user_id,
        **llm_kwargs,
    )


def _normalize_aliases(raw_aliases: Sequence[str], canonical_name: str) -> list[str]:
    canonical_key = canonical_name.strip().lower()
    seen = {canonical_key}
    aliases: list[str] = []
    for raw_alias in raw_aliases:
        alias = raw_alias.strip()
        if not alias:
            continue
        key = alias.lower()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(alias)
    return aliases


def _is_refinement_parse_error(exc: Exception) -> bool:
    return isinstance(exc, StructuredOutputParseError)


def _sanitize_bootstrap_error(exc: Exception) -> str:
    if _is_refinement_parse_error(exc):
        return BOOTSTRAP_PARSE_ERROR_MESSAGE
    return BOOTSTRAP_GENERIC_ERROR_MESSAGE


def _normalize_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _is_legacy_manual_draft_row(
    *,
    created_at: datetime | None,
    updated_at: datetime | None,
    cutoff: datetime,
) -> bool:
    created = _normalize_timestamp(created_at)
    if created is None:
        return False

    normalized_cutoff = _normalize_timestamp(cutoff)
    if normalized_cutoff is None:
        return False

    if created >= normalized_cutoff:
        return False

    updated = _normalize_timestamp(updated_at)
    if updated is None:
        return True
    return updated <= normalized_cutoff


def find_legacy_manual_draft_ambiguity(
    db: Session,
    *,
    novel_id: int,
    cutoff: datetime = LEGACY_ORIGIN_TRACKING_CUTOFF,
) -> LegacyDraftAmbiguity:
    entity_ids = [
        row.id
        for row in db.query(
            WorldEntity.id,
            WorldEntity.created_at,
            WorldEntity.updated_at,
        ).filter(
            WorldEntity.novel_id == novel_id,
            WorldEntity.status == "draft",
            WorldEntity.origin == "manual",
        ).all()
        if _is_legacy_manual_draft_row(
            created_at=row.created_at,
            updated_at=row.updated_at,
            cutoff=cutoff,
        )
    ]

    relationship_ids = [
        row.id
        for row in db.query(
            WorldRelationship.id,
            WorldRelationship.created_at,
            WorldRelationship.updated_at,
        ).filter(
            WorldRelationship.novel_id == novel_id,
            WorldRelationship.status == "draft",
            WorldRelationship.origin == "manual",
        ).all()
        if _is_legacy_manual_draft_row(
            created_at=row.created_at,
            updated_at=row.updated_at,
            cutoff=cutoff,
        )
    ]

    return LegacyDraftAmbiguity(
        entity_ids=entity_ids,
        relationship_ids=relationship_ids,
    )


def _delete_bootstrap_origin_drafts(db: Session, *, novel_id: int) -> None:
    bootstrap_draft_entity_ids = [
        entity_id
        for (entity_id,) in db.query(WorldEntity.id).filter(
            WorldEntity.novel_id == novel_id,
            WorldEntity.status == "draft",
            WorldEntity.origin == "bootstrap",
        ).all()
    ]

    db.query(WorldRelationship).filter(
        WorldRelationship.novel_id == novel_id,
        WorldRelationship.status == "draft",
        WorldRelationship.origin == "bootstrap",
    ).delete(synchronize_session=False)

    if not bootstrap_draft_entity_ids:
        return

    referenced_rows = db.query(
        WorldRelationship.source_id,
        WorldRelationship.target_id,
    ).filter(
        WorldRelationship.novel_id == novel_id,
        or_(
            WorldRelationship.source_id.in_(bootstrap_draft_entity_ids),
            WorldRelationship.target_id.in_(bootstrap_draft_entity_ids),
        ),
    ).all()
    referenced_entity_ids = {
        entity_id
        for row in referenced_rows
        for entity_id in row
        if entity_id in bootstrap_draft_entity_ids
    }
    deletable_entity_ids = [
        entity_id
        for entity_id in bootstrap_draft_entity_ids
        if entity_id not in referenced_entity_ids
    ]
    if deletable_entity_ids:
        db.query(WorldEntity).filter(
            WorldEntity.id.in_(deletable_entity_ids),
        ).delete(synchronize_session=False)


def persist_bootstrap_output(
    db: Session,
    *,
    novel_id: int,
    index: NovelIndex,
    refinement: BootstrapRefinementResult,
    mode: str,
    draft_policy: str | None,
) -> tuple[int, int]:
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel is None:
        raise ValueError(f"Novel not found: {novel_id}")

    novel.window_index = index.to_msgpack()
    if mode == BOOTSTRAP_MODE_INDEX_REFRESH:
        db.flush()
        return 0, 0

    if (
        mode == BOOTSTRAP_MODE_REEXTRACT
        and draft_policy == BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS
    ):
        _delete_bootstrap_origin_drafts(db, novel_id=novel_id)

    existing_entities = {
        entity.name: entity
        for entity in db.query(WorldEntity).filter(WorldEntity.novel_id == novel_id).all()
    }
    entity_ids_by_name: dict[str, int] = {}
    entities_written = 0

    for refined_entity in refinement.entities:
        name = refined_entity.name.strip()
        if not name:
            continue

        aliases = _normalize_aliases(refined_entity.aliases, name)
        entity_type = refined_entity.entity_type.strip() if refined_entity.entity_type else "other"
        if not entity_type:
            entity_type = "other"

        entity = existing_entities.get(name)
        if entity is None:
            entity = WorldEntity(
                novel_id=novel_id,
                name=name,
                entity_type=entity_type,
                aliases=aliases,
                origin="bootstrap",
                status="draft",
            )
            db.add(entity)
            db.flush()
            existing_entities[name] = entity
            entities_written += 1
        elif entity.status == "draft" and entity.origin == "bootstrap":
            entity.entity_type = entity_type
            merged_aliases = _normalize_aliases([*(entity.aliases or []), *aliases], name)
            entity.aliases = merged_aliases
            entities_written += 1

        entity_ids_by_name[name] = entity.id

    # Relationships are bidirectional in the product semantics, so avoid duplicates
    # when the same (source, target, label_canonical) pair already exists in either direction.
    existing_relationship_keys = {
        (
            rel.source_id,
            rel.target_id,
            rel.label_canonical or canonicalize_relationship_label(rel.label),
        )
        for rel in db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel_id).all()
    }
    relationships_written = 0

    for refined_relationship in refinement.relationships:
        source_name = refined_relationship.source_name.strip()
        target_name = refined_relationship.target_name.strip()
        label = refined_relationship.label.strip()
        if not source_name or not target_name or not label or source_name == target_name:
            continue
        label_canonical = canonicalize_relationship_label(label)

        source_id = entity_ids_by_name.get(source_name)
        target_id = entity_ids_by_name.get(target_name)
        if source_id is None:
            source = existing_entities.get(source_name)
            source_id = source.id if source else None
        if target_id is None:
            target = existing_entities.get(target_name)
            target_id = target.id if target else None
        if source_id is None or target_id is None:
            continue

        direct_key = (source_id, target_id, label_canonical)
        reverse_key = (target_id, source_id, label_canonical)
        if direct_key in existing_relationship_keys or reverse_key in existing_relationship_keys:
            continue

        new_rel = WorldRelationship(
            novel_id=novel_id,
            source_id=source_id,
            target_id=target_id,
            label=label,
            origin="bootstrap",
            status="draft",
        )
        db.add(new_rel)
        existing_relationship_keys.add(direct_key)
        relationships_written += 1

    db.flush()
    return entities_written, relationships_written


def _load_chapters(db: Session, novel_id: int) -> list[ChapterText]:
    rows = (
        db.query(Chapter.id, Chapter.content)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_number.asc())
        .all()
    )
    return [
        ChapterText(chapter_id=chapter_id, text=content or "")
        for chapter_id, content in rows
        if (content or "").strip()
    ]


async def run_bootstrap_job(
    job_id: int,
    *,
    session_factory: Callable[[], Session] | None = None,
    client: AIClient | None = None,
    user_id: int | None = None,
    llm_config: dict | None = None,
) -> None:
    make_session = session_factory or SessionLocal
    db = make_session()
    try:
        job = db.query(BootstrapJob).filter(BootstrapJob.id == job_id).first()
        if not job:
            return

        mode = resolve_bootstrap_mode(job.mode)
        draft_policy = (
            resolve_reextract_draft_policy(job.draft_policy)
            if mode == BOOTSTRAP_MODE_REEXTRACT
            else None
        )
        job.mode = mode
        job.draft_policy = draft_policy

        settings = get_settings()
        chapters = _load_chapters(db, job.novel_id)
        if not chapters:
            raise ValueError("Novel has no non-empty chapter text to bootstrap")

        combined_text = "\n".join(chapter.text for chapter in chapters)
        logger.info("bootstrap[%d]: loaded %d chapters, %d chars", job_id, len(chapters), len(combined_text))

        transition_bootstrap_job(job, "tokenizing", detail="tokenizing chapters")
        db.commit()

        t0 = time.monotonic()
        language, tokens = tokenize_text(combined_text)
        common_words = load_common_words(
            language,
            common_words_dir=settings.bootstrap_common_words_dir,
        )
        logger.info("bootstrap[%d]: tokenized in %.1fs → %d tokens (%s)", job_id, time.monotonic() - t0, len(tokens), language)

        transition_bootstrap_job(job, "extracting", detail=f"extracting candidates ({language})")
        db.commit()

        t0 = time.monotonic()
        candidates = extract_candidates(tokens, common_words)
        logger.info("bootstrap[%d]: extracted %d candidates in %.1fs", job_id, len(candidates), time.monotonic() - t0)

        transition_bootstrap_job(job, "windowing", detail="building window index")
        db.commit()

        t0 = time.monotonic()
        index, importance = build_window_index(
            chapters,
            candidates,
            window_size=settings.bootstrap_window_size,
            window_step=settings.bootstrap_window_step,
            min_window_count=settings.bootstrap_min_window_count,
            min_window_ratio=settings.bootstrap_min_window_ratio,
        )
        cooccurrence_pairs = (
            compute_cooccurrence(index)
            if mode != BOOTSTRAP_MODE_INDEX_REFRESH
            else []
        )
        logger.info(
            "bootstrap[%d]: windowed in %.1fs → %d important, %d cooccurrence pairs (%s)",
            job_id,
            time.monotonic() - t0,
            len(importance),
            len(cooccurrence_pairs),
            mode,
        )

        if mode == BOOTSTRAP_MODE_INDEX_REFRESH:
            transition_bootstrap_job(job, "refining", detail="refreshing window index only")
        else:
            transition_bootstrap_job(job, "refining", detail="refining entities and relationships")
        db.commit()

        if mode == BOOTSTRAP_MODE_INDEX_REFRESH:
            refinement = BootstrapRefinementResult()
        else:
            await acquire_llm_slot_blocking()
            try:
                refinement = await refine_candidates_with_llm(
                    importance,
                    cooccurrence_pairs,
                    max_candidates=settings.bootstrap_max_candidates,
                    temperature=settings.bootstrap_llm_temperature,
                    client=client,
                    llm_config=llm_config,
                    user_id=user_id,
                )
            finally:
                release_llm_slot()

        entities_found, relationships_found = persist_bootstrap_output(
            db,
            novel_id=job.novel_id,
            index=index,
            refinement=refinement,
            mode=mode,
            draft_policy=draft_policy,
        )
        if mode in {BOOTSTRAP_MODE_INITIAL, BOOTSTRAP_MODE_REEXTRACT}:
            job.initialized = True

        transition_bootstrap_job(
            job,
            "completed",
            detail="bootstrap completed",
            result={
                "entities_found": entities_found,
                "relationships_found": relationships_found,
                "index_refresh_only": mode == BOOTSTRAP_MODE_INDEX_REFRESH,
            },
        )
        db.commit()

        # Record analytics event after successful bootstrap
        from app.core.events import record_event
        if user_id is not None:
            record_event(db, user_id, "bootstrap_run", novel_id=job.novel_id, meta={
                "mode": mode,
                "entities_found": entities_found,
                "relationships_found": relationships_found,
            })
    except Exception as exc:  # pragma: no cover - defensive background task guard
        db.rollback()
        logger.exception("bootstrap background task failed")
        user_error = _sanitize_bootstrap_error(exc)
        try:
            failed_job = db.query(BootstrapJob).filter(BootstrapJob.id == job_id).first()
            if failed_job and failed_job.status != "failed":
                transition_bootstrap_job(failed_job, "failed", detail="bootstrap failed", error=user_error)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
