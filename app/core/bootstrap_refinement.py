from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
import logging
import math
from typing import Sequence

from pydantic import BaseModel, Field

from app.core import bootstrap_text_fallback
from app.core.ai_client import AIClient, StructuredOutputParseError, get_client
from app.core.indexing.builder import ChapterText
from app.core.llm_config import ResolvedLlmConfig
from app.core.indexing.state_proto_runtime import StateProtoIndex
from app.core.indexing.zh_name_rules import (
    get_zh_name_trailing_noise_chars,
    is_zh_name_suffix_title,
    looks_like_zh_person_name,
    looks_like_zh_translit_fragment,
)
from app.core.text import PromptKey, get_prompt
from app.language import resolve_prompt_locale
from app.language_policy import get_language_policy

DEFAULT_MAX_CANDIDATES = 500
DEFAULT_LLM_TEMPERATURE = 0.3
DEFAULT_LLM_MAX_TOKENS = 10000
DEFAULT_LLM_PROMPT_CANDIDATES = 64
DEFAULT_LLM_PROMPT_PAIRS = 96
DEFAULT_LLM_MAX_ENTITIES = 80
DEFAULT_LLM_MAX_RELATIONSHIPS = 120
MIN_LLM_PROMPT_CANDIDATES = 30
MIN_LLM_PROMPT_PAIRS = 40
MIN_LLM_MAX_ENTITIES = 16
MIN_LLM_MAX_RELATIONSHIPS = 24
_ZH_NONREFERENTIAL_PREFIX_CHARS = frozenset({"一", "都", "这", "那", "没"})
_ZH_NONREFERENTIAL_SUFFIX_CHARS = frozenset({"吗", "呢", "吧", "啊", "呀", "么"})
_ZH_NONREFERENTIAL_INTERIOR_CHARS = frozenset({"不", "没"})
_PROMPT_IMPORTANCE_LOG_WEIGHT = 18.0
_PROMPT_ASSOCIATION_BONUS_WEIGHT = 14.0
_PROMPT_PERSON_LIKE_BONUS = 12.0
_PROMPT_TRANSLIT_BONUS = 10.0
_PROMPT_LONG_SURFACE_BONUS = 2.0
_PROMPT_ENTITY_SUFFIX_BONUS = 7.0
_PROMPT_TWO_CHAR_ENTITY_SUFFIX_BONUS = 4.0
_PROMPT_GENERIC_BACKDROP_EXACT_PENALTY = 12.0
_PROMPT_PAIR_ENDPOINT_WEIGHT = 0.35
_PROMPT_ZH_PREFIX_SHADOW_PENALTY = 16.0
_ZH_PREFIX_SHADOW_MIN_COUNT_RATIO = 0.92
_ZH_PREFIX_SHADOW_MAX_SECONDARY_RATIO = 0.5
_ZH_ENTITY_LIKE_SUFFIXES = (
    "教会",
    "学派",
    "组织",
    "基地",
    "边界",
    "星系",
    "王国",
    "共和国",
    "帝国",
    "之地",
    "权杖",
    "胸针",
    "铜哨",
    "神灯",
    "黄铜书",
    "面具",
    "笔记",
    "蜡烛",
    "手套",
    "皇族",
    "家族",
    "仙宫",
    "山庄",
    "神宗",
    "大陆",
    "禁地",
    "会",
    "者",
    "界",
    "城",
    "港",
    "谷",
    "湖",
    "河",
    "山",
    "殿",
    "宫",
    "阁",
    "楼",
    "坊",
    "铺",
)
_ZH_TWO_CHAR_ENTITY_SUFFIX_CHARS = frozenset({"会", "者", "界", "城", "司", "派", "盟", "帮"})
_ZH_ALIAS_TITLE_TOKENS = frozenset(
    {
        "先生",
        "小姐",
        "夫人",
        "太太",
        "大人",
        "公子",
        "姑娘",
        "少主",
        "门主",
        "掌门",
        "教主",
        "宫主",
        "宗主",
        "阁主",
        "谷主",
        "城主",
        "家主",
        "长老",
        "大长老",
        "师父",
        "老师",
        "师尊",
        "师兄",
        "师姐",
        "师弟",
        "师妹",
        "国师",
        "老祖",
        "殿下",
        "陛下",
    }
)
_ZH_ALIAS_TITLE_SUFFIXES = (
    "之王",
    "王爷",
    "大帝",
    "天君",
    "真君",
    "魔君",
    "仙尊",
    "神尊",
    "圣子",
    "圣女",
    "公主",
    "少爷",
    "先生",
    "小姐",
    "夫人",
    "太太",
    "大人",
    "公子",
    "姑娘",
    "少主",
    "门主",
    "掌门",
    "教主",
    "宫主",
    "宗主",
    "阁主",
    "谷主",
    "城主",
    "家主",
    "长老",
    "大长老",
    "师父",
    "老师",
    "师尊",
    "师兄",
    "师姐",
    "师弟",
    "师妹",
    "国师",
    "老祖",
    "殿下",
    "陛下",
)
_ZH_ALIAS_TITLE_LAST_CHARS = frozenset(
    {"王", "帝", "君", "尊", "皇", "后", "主", "爷", "侯", "公", "帅", "相", "师", "使", "将"}
)
_ZH_GENERIC_BACKDROP_SURFACES = frozenset(
    {
        "世界",
        "文明",
        "人类",
        "地球",
        "宇宙",
        "科学",
        "技术",
        "信息",
        "系统",
        "工作",
        "研究",
        "运行",
        "计算",
        "计算机",
        "材料",
        "目标",
        "现实",
        "怀疑",
        "虚幻",
        "无比",
        "可怕",
        "面对",
        "快速",
        "先生",
        "小姐",
        "物品",
        "基地",
        "边界",
    }
)

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True, slots=True)
class BootstrapRefinementInputs:
    importance: dict[str, int]
    cooccurrence_pairs: list[tuple[str, str, int]]
    allowed_alias_candidates: frozenset[str] = frozenset()
    supported_alias_candidates: frozenset[str] = frozenset()
    supplemental_candidate_count: int = 0
    supplemental_pair_count: int = 0


@dataclass(frozen=True, slots=True)
class _PromptCandidateStat:
    name: str
    importance: int
    pair_degree: int
    strongest_association: float
    shortlist_score: float


def _looks_like_zh_title_or_honorific(alias: str) -> bool:
    if not alias:
        return False
    if alias in _ZH_ALIAS_TITLE_TOKENS or is_zh_name_suffix_title(alias):
        return True
    if any(alias.endswith(suffix) for suffix in _ZH_ALIAS_TITLE_SUFFIXES):
        return True
    return 2 <= len(alias) <= 4 and alias[-1:] in _ZH_ALIAS_TITLE_LAST_CHARS


def _sanitize_entity_aliases(
    *,
    name: str,
    aliases: Sequence[str],
    allowed_candidate_keys: set[str],
    allowed_raw_candidates: set[str],
    supported_alias_candidate_keys: set[str],
    canonical_name_keys: set[str],
    canonical_raw_names: set[str],
    novel_language: str | None,
) -> list[str]:
    policy = get_language_policy(novel_language, sample_text=name or None)
    trailing_noise_chars = (
        get_zh_name_trailing_noise_chars() if policy.base_language == "zh" else frozenset()
    )
    name_key = policy.normalize_for_matching(name)
    cleaned_aliases: list[str] = []
    seen_keys = {name_key}
    seen_raw = {name}

    for raw_alias in aliases:
        alias = str(raw_alias or "").strip()
        if not alias or alias in seen_raw:
            continue

        alias_key = policy.normalize_for_matching(alias)
        is_zh_surface_variant = (
            policy.base_language == "zh"
            and alias != name
            and alias in allowed_raw_candidates
            and alias_key == name_key
        )
        if alias in canonical_raw_names:
            continue
        if alias_key in canonical_name_keys and not is_zh_surface_variant:
            continue
        if (
            allowed_candidate_keys
            and alias_key not in allowed_candidate_keys
            and alias not in allowed_raw_candidates
        ):
            continue
        if policy.base_language == "zh":
            if len(alias) == len(name) + 1 and alias[-1] in trailing_noise_chars:
                continue
            if (
                alias_key != name_key
                and not (set(alias) & set(name))
                and alias_key not in supported_alias_candidate_keys
                and not _looks_like_zh_title_or_honorific(alias)
            ):
                continue

        if alias_key in seen_keys and not is_zh_surface_variant:
            continue

        seen_raw.add(alias)
        if not is_zh_surface_variant:
            seen_keys.add(alias_key)
        cleaned_aliases.append(alias)

    return cleaned_aliases


def sanitize_bootstrap_refinement_result(
    refinement: BootstrapRefinementResult,
    *,
    allowed_candidates: Sequence[str],
    supported_alias_candidates: Sequence[str] = (),
    novel_language: str | None,
) -> BootstrapRefinementResult:
    policy = get_language_policy(novel_language)
    allowed_raw_candidates = {
        str(candidate or "").strip()
        for candidate in allowed_candidates
        if str(candidate or "").strip()
    }
    allowed_candidate_keys = {
        policy.normalize_for_matching(candidate)
        for candidate in allowed_raw_candidates
    }
    supported_alias_candidate_keys = {
        policy.normalize_for_matching(candidate)
        for candidate in supported_alias_candidates
        if str(candidate or "").strip()
    }
    canonical_name_keys = {
        policy.normalize_for_matching(entity.name)
        for entity in refinement.entities
        if entity.name.strip()
    }
    canonical_raw_names = {
        entity.name.strip() for entity in refinement.entities if entity.name.strip()
    }

    sanitized_entities = [
        RefinedEntity(
            name=entity.name.strip(),
            entity_type=entity.entity_type,
            aliases=_sanitize_entity_aliases(
                name=entity.name.strip(),
                aliases=entity.aliases,
                allowed_candidate_keys=allowed_candidate_keys,
                allowed_raw_candidates=allowed_raw_candidates,
                supported_alias_candidate_keys=supported_alias_candidate_keys,
                canonical_name_keys=canonical_name_keys,
                canonical_raw_names=canonical_raw_names,
                novel_language=novel_language,
            ),
        )
        for entity in refinement.entities
        if entity.name.strip()
    ]

    return BootstrapRefinementResult(
        entities=sanitized_entities,
        relationships=refinement.relationships,
    )


def _zh_nonreferential_phrase_penalty(name: str) -> float:
    if len(name) < 3:
        return 0.0

    penalty = 0.0
    if name[:1] in _ZH_NONREFERENTIAL_PREFIX_CHARS:
        penalty += 6.0
    if name[-1:] in _ZH_NONREFERENTIAL_SUFFIX_CHARS:
        penalty += 6.0
    if any(char in _ZH_NONREFERENTIAL_INTERIOR_CHARS for char in name):
        penalty += 4.0
    return penalty


def _zh_entity_like_surface_bonus(name: str) -> float:
    bonus = 0.0
    if looks_like_zh_person_name(name):
        bonus += _PROMPT_PERSON_LIKE_BONUS
    if looks_like_zh_translit_fragment(name):
        bonus += _PROMPT_TRANSLIT_BONUS
    if len(name) >= 3:
        bonus += _PROMPT_LONG_SURFACE_BONUS
        if any(name.endswith(suffix) for suffix in _ZH_ENTITY_LIKE_SUFFIXES):
            bonus += _PROMPT_ENTITY_SUFFIX_BONUS
    elif len(name) == 2 and name[-1:] in _ZH_TWO_CHAR_ENTITY_SUFFIX_CHARS:
        bonus += _PROMPT_TWO_CHAR_ENTITY_SUFFIX_BONUS
    return bonus


def _zh_generic_backdrop_penalty(name: str) -> float:
    penalty = 0.0
    if name in _ZH_GENERIC_BACKDROP_SURFACES:
        penalty += _PROMPT_GENERIC_BACKDROP_EXACT_PENALTY
    return penalty


def _candidate_surface_bonus(name: str, *, novel_language: str | None) -> float:
    policy = get_language_policy(novel_language, sample_text=name or None)
    if policy.base_language == "zh":
        return _zh_entity_like_surface_bonus(name)
    return 0.0


def _candidate_surface_penalty(name: str, *, novel_language: str | None) -> float:
    policy = get_language_policy(novel_language, sample_text=name or None)
    if policy.base_language == "zh":
        return _zh_nonreferential_phrase_penalty(name) + _zh_generic_backdrop_penalty(name)
    return 0.0


def _build_zh_prefix_shadow_map(importance: dict[str, int]) -> dict[str, str]:
    shadow_map: dict[str, str] = {}
    person_like_names = [
        (name, int(count))
        for name, count in importance.items()
        if int(count) > 0 and looks_like_zh_person_name(name)
    ]
    if not person_like_names:
        return shadow_map

    for short_name, short_count in person_like_names:
        extensions = sorted(
            (
                (long_name, long_count)
                for long_name, long_count in person_like_names
                if long_name != short_name
                and len(long_name) == len(short_name) + 1
                and long_name.startswith(short_name)
            ),
            key=lambda item: (-item[1], item[0]),
        )
        if not extensions:
            continue

        best_name, best_count = extensions[0]
        if float(best_count) / max(short_count, 1) < _ZH_PREFIX_SHADOW_MIN_COUNT_RATIO:
            continue

        second_count = extensions[1][1] if len(extensions) > 1 else 0
        if second_count and float(second_count) / max(best_count, 1) >= _ZH_PREFIX_SHADOW_MAX_SECONDARY_RATIO:
            continue

        shadow_map[short_name] = best_name

    return shadow_map


def _build_prompt_candidate_stats(
    importance: dict[str, int],
    cooccurrence_pairs: Sequence[tuple[str, str, int]],
    *,
    novel_language: str | None,
) -> list[_PromptCandidateStat]:
    zh_prefix_shadow_map = (
        _build_zh_prefix_shadow_map(importance)
        if get_language_policy(novel_language).base_language == "zh"
        else {}
    )
    pair_degree: Counter[str] = Counter()
    strongest_association: dict[str, float] = defaultdict(float)

    for left, right, count in cooccurrence_pairs:
        left_importance = int(importance.get(left, 0))
        right_importance = int(importance.get(right, 0))
        if left_importance <= 0 or right_importance <= 0 or count <= 0:
            continue
        association = float(count) / math.sqrt(left_importance * right_importance)
        pair_degree[left] += 1
        pair_degree[right] += 1
        if association > strongest_association[left]:
            strongest_association[left] = association
        if association > strongest_association[right]:
            strongest_association[right] = association

    stats: list[_PromptCandidateStat] = []
    for name, raw_importance in importance.items():
        score = int(raw_importance)
        if score <= 0:
            continue
        shortlist_score = (
            math.log1p(float(score)) * _PROMPT_IMPORTANCE_LOG_WEIGHT
            + strongest_association.get(name, 0.0) * _PROMPT_ASSOCIATION_BONUS_WEIGHT
            + _candidate_surface_bonus(name, novel_language=novel_language)
            - _candidate_surface_penalty(name, novel_language=novel_language)
            - (
                _PROMPT_ZH_PREFIX_SHADOW_PENALTY
                if name in zh_prefix_shadow_map
                else 0.0
            )
        )
        stats.append(
            _PromptCandidateStat(
                name=name,
                importance=score,
                pair_degree=int(pair_degree.get(name, 0)),
                strongest_association=float(strongest_association.get(name, 0.0)),
                shortlist_score=shortlist_score,
            )
        )

    stats.sort(
        key=lambda item: (
            -item.shortlist_score,
            -item.importance,
            -len(item.name),
            item.name,
        )
    )
    return stats


def _pair_shortlist_score(
    left: str,
    right: str,
    count: int,
    *,
    importance: dict[str, int],
    candidate_scores: dict[str, float],
) -> float:
    left_importance = int(importance.get(left, 0))
    right_importance = int(importance.get(right, 0))
    if left_importance <= 0 or right_importance <= 0 or count <= 0:
        return float("-inf")

    association = float(count) / math.sqrt(left_importance * right_importance)
    endpoint_floor = min(
        float(candidate_scores.get(left, 0.0)),
        float(candidate_scores.get(right, 0.0)),
    )
    return float(count) * (1.0 + association) + endpoint_floor * _PROMPT_PAIR_ENDPOINT_WEIGHT


def _select_refinement_prompt_shortlist(
    importance: dict[str, int],
    cooccurrence_pairs: Sequence[tuple[str, str, int]],
    *,
    max_candidates: int,
    max_pairs: int,
    novel_language: str | None,
) -> tuple[list[tuple[str, int]], list[tuple[str, str, int]]]:
    candidate_stats = _build_prompt_candidate_stats(
        importance,
        cooccurrence_pairs,
        novel_language=novel_language,
    )
    if not candidate_stats:
        return [], []

    shadowed_names = (
        set(_build_zh_prefix_shadow_map(importance))
        if get_language_policy(novel_language).base_language == "zh"
        else set()
    )
    candidate_stats_by_name = {item.name: item for item in candidate_stats}
    raw_candidate_names = [
        name
        for name, _ in sorted(
            importance.items(),
            key=lambda item: (-item[1], -len(item[0]), item[0]),
        )
        if name not in shadowed_names
    ]
    raw_reserve = min(max_candidates, max(max_candidates // 4, 1))
    rerank_primary = max(max_candidates - raw_reserve, 1)

    selected_names_in_order: list[str] = []
    seen_names: set[str] = set()

    def _append_names(names: Sequence[str]) -> None:
        for name in names:
            if name in seen_names or name not in candidate_stats_by_name:
                continue
            seen_names.add(name)
            selected_names_in_order.append(name)
            if len(selected_names_in_order) >= max_candidates:
                return

    reranked_names = [
        item.name for item in candidate_stats if item.name not in shadowed_names
    ]
    _append_names(reranked_names[:rerank_primary])
    if len(selected_names_in_order) < max_candidates:
        _append_names(raw_candidate_names[:raw_reserve])
    if len(selected_names_in_order) < max_candidates:
        _append_names(reranked_names[rerank_primary:])
    if len(selected_names_in_order) < max_candidates and shadowed_names:
        _append_names(
            [
                name
                for name, _ in sorted(
                    importance.items(),
                    key=lambda item: (-item[1], -len(item[0]), item[0]),
                )
                if name in shadowed_names
            ]
        )

    selected_candidate_stats = [
        candidate_stats_by_name[name] for name in selected_names_in_order
    ]
    selected_names = {item.name for item in selected_candidate_stats}
    candidate_scores = {
        item.name: item.shortlist_score for item in selected_candidate_stats
    }

    shortlisted_pairs = sorted(
        (
            (left, right, count)
            for left, right, count in cooccurrence_pairs
            if left in selected_names and right in selected_names
        ),
        key=lambda item: (
            -_pair_shortlist_score(
                item[0],
                item[1],
                item[2],
                importance=importance,
                candidate_scores=candidate_scores,
            ),
            -item[2],
            item[0],
            item[1],
        ),
    )[:max_pairs]

    return (
        [(item.name, item.importance) for item in selected_candidate_stats],
        shortlisted_pairs,
    )


def _build_refinement_prompt(
    importance: dict[str, int],
    cooccurrence_pairs: Sequence[tuple[str, str, int]],
    *,
    max_candidates: int,
    max_pairs: int,
    max_entities: int,
    max_relationships: int,
    prompt_locale: str | None = None,
    novel_language: str | None = None,
) -> str:
    sorted_candidates, sorted_pairs = _select_refinement_prompt_shortlist(
        importance,
        cooccurrence_pairs,
        max_candidates=max_candidates,
        max_pairs=max_pairs,
        novel_language=novel_language,
    )

    candidate_lines = (
        "\n".join([f"- {name}: {count}" for name, count in sorted_candidates])
        or "- (none)"
    )
    pair_lines = (
        "\n".join(
            [f"- {left} -- {right}: {count}" for left, right, count in sorted_pairs]
        )
        or "- (none)"
    )

    locale = prompt_locale or "zh"
    prompt = get_prompt(PromptKey.BOOTSTRAP_REFINEMENT, locale=locale).format(
        candidate_lines=candidate_lines,
        pair_lines=pair_lines,
    )
    return f"{prompt}\n\n{_build_output_limit_instruction(locale, max_entities=max_entities, max_relationships=max_relationships)}"


def _build_output_limit_instruction(
    locale: str,
    *,
    max_entities: int,
    max_relationships: int,
) -> str:
    normalized = (locale or "zh").strip().lower()
    if normalized.startswith("zh"):
        return (
            f"7) 最多输出 {max_entities} 个实体、{max_relationships} 条关系。"
            "如果候选很多，只保留最重要、最具体、最确定的项。"
        )
    if normalized.startswith("ja"):
        return (
            f"7) 出力は最大で {max_entities} 個のエンティティ、"
            f"{max_relationships} 個の関係まで。候補が多い場合は、最も重要で具体的かつ確信度の高いものだけを残してください。"
        )
    if normalized.startswith("ko"):
        return (
            f"7) 최대 {max_entities}개의 엔티티와 {max_relationships}개의 관계만 출력하세요. "
            "후보가 많다면 가장 중요하고 구체적이며 확신이 높은 항목만 남기세요."
        )
    return (
        f"7) Output at most {max_entities} entities and {max_relationships} relationships. "
        "If there are many candidates, keep only the most important, specific, and high-confidence items."
    )


def _is_truncation_parse_error(exc: Exception) -> bool:
    if not isinstance(exc, StructuredOutputParseError):
        return False
    last_error = getattr(exc, "last_error", None)
    return isinstance(last_error, ValueError) and "truncated" in str(last_error).lower()


async def refine_candidates_with_llm(
    importance: dict[str, int],
    cooccurrence_pairs: Sequence[tuple[str, str, int]],
    *,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    temperature: float = DEFAULT_LLM_TEMPERATURE,
    client: AIClient | None = None,
    llm_config: ResolvedLlmConfig,
    user_id: int | None = None,
    novel_language: str | None = None,
) -> BootstrapRefinementResult:
    if not importance:
        return BootstrapRefinementResult()

    prompt_locale = resolve_prompt_locale(novel_language=novel_language)
    ai = client or get_client()
    prompt_candidate_limit = max(
        1,
        min(int(max_candidates or 0), DEFAULT_LLM_PROMPT_CANDIDATES),
    )
    prompt_pair_limit = max(
        prompt_candidate_limit,
        min(prompt_candidate_limit * 2, DEFAULT_LLM_PROMPT_PAIRS),
    )
    max_entities = DEFAULT_LLM_MAX_ENTITIES
    max_relationships = DEFAULT_LLM_MAX_RELATIONSHIPS

    while True:
        prompt = _build_refinement_prompt(
            importance,
            cooccurrence_pairs,
            max_candidates=prompt_candidate_limit,
            max_pairs=prompt_pair_limit,
            max_entities=max_entities,
            max_relationships=max_relationships,
            prompt_locale=prompt_locale,
            novel_language=novel_language,
        )
        try:
            return await ai.generate_structured(
                prompt=prompt,
                response_model=BootstrapRefinementResult,
                system_prompt="You are a precise information extraction assistant.",
                temperature=temperature,
                max_tokens=DEFAULT_LLM_MAX_TOKENS,
                role="editor",
                llm_config=llm_config,
                user_id=user_id,
            )
        except StructuredOutputParseError as exc:
            if not _is_truncation_parse_error(exc):
                raise

            next_prompt_candidate_limit = max(
                MIN_LLM_PROMPT_CANDIDATES,
                prompt_candidate_limit // 2,
            )
            next_prompt_pair_limit = max(
                max(next_prompt_candidate_limit, MIN_LLM_PROMPT_PAIRS),
                prompt_pair_limit // 2,
            )
            next_max_entities = max(MIN_LLM_MAX_ENTITIES, max_entities // 2)
            next_max_relationships = max(
                max(next_max_entities, MIN_LLM_MAX_RELATIONSHIPS),
                max_relationships // 2,
            )

            if (
                next_prompt_candidate_limit == prompt_candidate_limit
                and next_prompt_pair_limit == prompt_pair_limit
                and next_max_entities == max_entities
                and next_max_relationships == max_relationships
            ):
                raise

            logger.warning(
                "bootstrap refinement truncated; retrying with narrower prompt "
                "(candidates=%s->%s, pairs=%s->%s, entities=%s->%s, relationships=%s->%s)",
                prompt_candidate_limit,
                next_prompt_candidate_limit,
                prompt_pair_limit,
                next_prompt_pair_limit,
                max_entities,
                next_max_entities,
                max_relationships,
                next_max_relationships,
            )
            prompt_candidate_limit = next_prompt_candidate_limit
            prompt_pair_limit = next_prompt_pair_limit
            max_entities = next_max_entities
            max_relationships = next_max_relationships


def build_bootstrap_refinement_inputs(
    *,
    index_payload: bytes | None,
    chapters: Sequence[ChapterText],
    novel_language: str | None,
    common_words_dir: str,
    limit: int,
    include_text_fallback: bool,
) -> BootstrapRefinementInputs:
    (
        importance,
        cooccurrence_pairs,
        allowed_alias_candidates,
        supported_alias_candidates,
    ) = _build_refinement_inputs_from_state_proto_payload(index_payload)
    supplemental_candidate_count = 0
    supplemental_pair_count = 0

    if include_text_fallback:
        text_inputs = bootstrap_text_fallback._build_text_refinement_inputs_from_candidates(
            chapters,
            novel_language=novel_language,
            common_words_dir=common_words_dir,
            limit=limit,
        )
        text_importance = text_inputs.importance
        text_pairs = text_inputs.cooccurrence_pairs
        if not importance and not cooccurrence_pairs:
            importance = text_importance
            cooccurrence_pairs = text_pairs
            allowed_alias_candidates = frozenset(text_inputs.allowed_alias_candidates)
            supported_alias_candidates = frozenset(text_inputs.supported_alias_candidates)
            supplemental_candidate_count = len(text_importance)
            supplemental_pair_count = len(text_pairs)
        elif text_importance or text_pairs:
            primary_candidates = set(importance)
            primary_pairs = {(left, right) for left, right, _ in cooccurrence_pairs}
            importance, cooccurrence_pairs = _merge_refinement_inputs(
                primary_importance=importance,
                primary_pairs=cooccurrence_pairs,
                supplemental_importance=text_importance,
                supplemental_pairs=text_pairs,
            )
            supplemental_candidate_count = len(set(importance) - primary_candidates)
            supplemental_pair_count = len(
                {(left, right) for left, right, _ in cooccurrence_pairs} - primary_pairs
            )
            allowed_alias_candidates = frozenset(
                {*allowed_alias_candidates, *text_inputs.allowed_alias_candidates}
            )
            supported_alias_candidates = frozenset(
                {*supported_alias_candidates, *text_inputs.supported_alias_candidates}
            )

    return BootstrapRefinementInputs(
        importance=importance,
        cooccurrence_pairs=cooccurrence_pairs,
        allowed_alias_candidates=allowed_alias_candidates,
        supported_alias_candidates=supported_alias_candidates,
        supplemental_candidate_count=supplemental_candidate_count,
        supplemental_pair_count=supplemental_pair_count,
    )


def _build_refinement_inputs_from_state_proto_payload(
    index_payload: bytes | None,
) -> tuple[dict[str, int], list[tuple[str, str, int]], frozenset[str], frozenset[str]]:
    if not index_payload:
        return {}, [], frozenset(), frozenset()

    index = StateProtoIndex.from_msgpack(index_payload)
    target_names = {
        target_id: target.canonical_name.strip()
        for target_id, target in index.targets.items()
        if target.canonical_name.strip()
    }
    if not target_names:
        return {}, [], frozenset(), frozenset()

    allowed_alias_candidates = frozenset(
        alias
        for target in index.targets.values()
        for alias in target.all_aliases()
        if alias.strip()
    )

    mention_counts = Counter(
        posting.target_id
        for posting in index.mention_postings
        if posting.target_id in target_names
    )
    claim_counts = Counter(
        claim.key.target_id
        for claim in index.claim_atoms
        if claim.key.target_id in target_names
    )
    coverage_counts = Counter(
        rep.target_id for rep in index.coverage_reps if rep.target_id in target_names
    )

    importance: dict[str, int] = {}
    for target_id, name in target_names.items():
        score = (
            int(mention_counts.get(target_id, 0)) * 2
            + int(claim_counts.get(target_id, 0)) * 3
            + int(coverage_counts.get(target_id, 0))
        )
        if score > 0:
            importance[name] = score

    segment_targets: dict[int, set[str]] = defaultdict(set)
    for posting in index.mention_postings:
        name = target_names.get(posting.target_id)
        if name:
            segment_targets[int(posting.segment_id)].add(name)
    for claim in index.claim_atoms:
        name = target_names.get(claim.key.target_id)
        if name:
            segment_targets[int(claim.segment_id)].add(name)

    pair_counts: Counter[tuple[str, str]] = Counter()
    for names in segment_targets.values():
        if len(names) < 2:
            continue
        for left, right in combinations(sorted(names), 2):
            pair_counts[(left, right)] += 1

    cooccurrence_pairs = sorted(
        (
            (left, right, count)
            for (left, right), count in pair_counts.items()
            if count > 0
        ),
        key=lambda item: (-item[2], item[0], item[1]),
    )
    return (
        importance,
        cooccurrence_pairs,
        allowed_alias_candidates,
        allowed_alias_candidates,
    )

def _merge_refinement_inputs(
    *,
    primary_importance: dict[str, int],
    primary_pairs: Sequence[tuple[str, str, int]],
    supplemental_importance: dict[str, int],
    supplemental_pairs: Sequence[tuple[str, str, int]],
) -> tuple[dict[str, int], list[tuple[str, str, int]]]:
    merged_importance = dict(primary_importance)
    supplemental_names = {
        name for name in supplemental_importance if name not in merged_importance
    }
    for name in supplemental_names:
        merged_importance[name] = supplemental_importance[name]

    merged_pair_counts = {(left, right): count for left, right, count in primary_pairs}
    for left, right, count in supplemental_pairs:
        if left not in merged_importance or right not in merged_importance:
            continue
        if left not in supplemental_names and right not in supplemental_names:
            continue
        merged_pair_counts[(left, right)] = max(
            int(count),
            int(merged_pair_counts.get((left, right), 0)),
        )

    return merged_importance, sorted(
        (
            (left, right, count)
            for (left, right), count in merged_pair_counts.items()
            if count > 0
        ),
        key=lambda item: (-item[2], item[0], item[1]),
    )
