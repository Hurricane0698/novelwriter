# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Lightweight locale snippet system for inline format strings.

The prompt catalog (PromptKey) handles full LLM prompt templates.
This module handles the many small format strings (chapter headings,
section headers, length guidance, error messages) that appear inline
in generator / context assembly code.
"""

from __future__ import annotations

from enum import Enum

from app.language import DEFAULT_LANGUAGE, get_language_fallback_chain


class SnippetKey(str, Enum):
    # Chapter/outline formatting
    CHAPTER_HEADING_FMT = "chapter_heading_fmt"
    OUTLINE_HEADING_FMT = "outline_heading_fmt"
    NO_OUTLINE = "no_outline"

    # Length discipline
    LENGTH_GUIDANCE_TARGET = "length_guidance_target"
    LENGTH_GUIDANCE_DEFAULT = "length_guidance_default"
    SYSTEM_LENGTH_HEADER = "system_length_header"
    SYSTEM_LENGTH_RULES = "system_length_rules"

    # Style anchor
    STYLE_ANCHOR = "style_anchor"

    # Continuation instruction
    CONTINUE_INSTRUCTION = "continue_instruction"

    # World context section headers
    SECTION_SYSTEMS = "section_systems"
    SECTION_ENTITIES = "section_entities"
    SECTION_RELATIONSHIPS = "section_relationships"

    # Unnamed placeholders
    UNNAMED_SYSTEM = "unnamed_system"
    UNNAMED_ENTITY = "unnamed_entity"

    # Labels
    ALIASES_LABEL = "aliases_label"
    USER_INSTRUCTION_HEADER = "user_instruction_header"

    # Inline punctuation for world context rendering
    DESC_SEPARATOR = "desc_separator"
    ALIAS_SEPARATOR = "alias_separator"

    # World generation chunk directives
    WORLDGEN_CHUNK_DIRECTIVE_MULTI = "worldgen_chunk_directive_multi"
    WORLDGEN_CHUNK_DIRECTIVE_SINGLE = "worldgen_chunk_directive_single"


# ---------------------------------------------------------------------------
# Registry: locale -> key -> template
# ---------------------------------------------------------------------------

_SNIPPETS: dict[str, dict[SnippetKey, str]] = {}


def register_snippets(locale: str, snippets: dict[SnippetKey, str]) -> None:
    if locale not in _SNIPPETS:
        _SNIPPETS[locale] = {}
    _SNIPPETS[locale].update(snippets)


def get_snippet(key: SnippetKey, locale: str | None = None) -> str:
    for candidate in get_language_fallback_chain(locale, default=DEFAULT_LANGUAGE):
        bucket = _SNIPPETS.get(candidate)
        if bucket and key in bucket:
            return bucket[key]
    raise KeyError(f"No snippet for {key!r} (locale={locale or DEFAULT_LANGUAGE!r})")


# ---------------------------------------------------------------------------
# Chinese snippets (default)
# ---------------------------------------------------------------------------

_ZH: dict[SnippetKey, str] = {
    SnippetKey.CHAPTER_HEADING_FMT: "【第{n}章：{title}】",
    SnippetKey.OUTLINE_HEADING_FMT: "【第{start}–{end}章大纲】",
    SnippetKey.NO_OUTLINE: "暂无大纲。",
    SnippetKey.LENGTH_GUIDANCE_TARGET: (
        "以约{target}字为目标完整展开正文，不要过早收束，"
        "明显短于约{min_chars}字会显得篇幅不足，可自然上浮到约{ceiling}字，"
        "最后在完整句子处结束"
    ),
    SnippetKey.LENGTH_GUIDANCE_DEFAULT: "请把正文写成自然完整的一章，在完整句子处结束。",
    SnippetKey.SYSTEM_LENGTH_HEADER: "【长度纪律】",
    SnippetKey.SYSTEM_LENGTH_RULES: (
        "- 直接开始写正文，不要先做分析、提纲或铺垫性说明\n"
        "- 若篇幅尚未充分展开，不要过早结束"
    ),
    SnippetKey.STYLE_ANCHOR: (
        "你的续写必须在语体、口吻、句式和用词上与下方 <recent_chapters> 完全一致，"
        "开篇就要无缝衔接原文风格。"
    ),
    SnippetKey.CONTINUE_INSTRUCTION: "请续写{reference}：",
    SnippetKey.SECTION_SYSTEMS: "〈世界体系〉",
    SnippetKey.SECTION_ENTITIES: "〈角色与事物〉",
    SnippetKey.SECTION_RELATIONSHIPS: "〈人物关系〉",
    SnippetKey.UNNAMED_SYSTEM: "（未命名体系）",
    SnippetKey.UNNAMED_ENTITY: "（未命名实体）",
    SnippetKey.ALIASES_LABEL: "别名：",
    SnippetKey.DESC_SEPARATOR: "：",
    SnippetKey.ALIAS_SEPARATOR: "、",
    SnippetKey.USER_INSTRUCTION_HEADER: "【用户续写指令】",
    SnippetKey.WORLDGEN_CHUNK_DIRECTIVE_MULTI: (
        "你当前只处理第{chunk_index}/{chunk_count}段设定文本。请尽量覆盖这一段中明确、稳定、可复用的设定。"
        "即使与其他段重复也没关系，系统稍后会自动去重整合；不要因为担心重复而把内容压缩得过少。"
    ),
    SnippetKey.WORLDGEN_CHUNK_DIRECTIVE_SINGLE: (
        "请尽量完整覆盖文本中明确、稳定、可复用的设定，不要过度压缩条目数量。"
    ),
}

register_snippets("zh", _ZH)

# ---------------------------------------------------------------------------
# English snippets
# ---------------------------------------------------------------------------

_EN: dict[SnippetKey, str] = {
    SnippetKey.CHAPTER_HEADING_FMT: "【Chapter {n}: {title}】",
    SnippetKey.OUTLINE_HEADING_FMT: "【Outline: Chapters {start}–{end}】",
    SnippetKey.NO_OUTLINE: "No outline available.",
    SnippetKey.LENGTH_GUIDANCE_TARGET: (
        "Aim for approximately {target} characters of fully developed prose. "
        "Do not wrap up prematurely — anything clearly shorter than ~{min_chars} characters feels truncated. "
        "You may naturally extend to ~{ceiling} characters. End on a complete sentence."
    ),
    SnippetKey.LENGTH_GUIDANCE_DEFAULT: (
        "Write a naturally complete chapter, ending on a complete sentence."
    ),
    SnippetKey.SYSTEM_LENGTH_HEADER: "【Length Discipline】",
    SnippetKey.SYSTEM_LENGTH_RULES: (
        "- Begin the prose directly — no analysis, outline, or preamble\n"
        "- If the text has not been fully developed, do not end prematurely"
    ),
    SnippetKey.STYLE_ANCHOR: (
        "Your continuation must exactly match the register, tone, sentence rhythm, "
        "and diction of the <recent_chapters> below. "
        "Start seamlessly from where the original left off."
    ),
    SnippetKey.CONTINUE_INSTRUCTION: "Continue writing {reference}:",
    SnippetKey.SECTION_SYSTEMS: "〈World Systems〉",
    SnippetKey.SECTION_ENTITIES: "〈Characters & Entities〉",
    SnippetKey.SECTION_RELATIONSHIPS: "〈Relationships〉",
    SnippetKey.UNNAMED_SYSTEM: "(Unnamed System)",
    SnippetKey.UNNAMED_ENTITY: "(Unnamed Entity)",
    SnippetKey.ALIASES_LABEL: "Aliases: ",
    SnippetKey.DESC_SEPARATOR: ": ",
    SnippetKey.ALIAS_SEPARATOR: ", ",
    SnippetKey.USER_INSTRUCTION_HEADER: "【User Instruction】",
    SnippetKey.WORLDGEN_CHUNK_DIRECTIVE_MULTI: (
        "You are processing chunk {chunk_index}/{chunk_count} of the world-building text. "
        "Extract as many clear, stable, reusable details as possible from this chunk. "
        "Overlap with other chunks is fine — the system will de-duplicate later. "
        "Do not compress content to avoid repetition."
    ),
    SnippetKey.WORLDGEN_CHUNK_DIRECTIVE_SINGLE: (
        "Extract as many clear, stable, reusable details as possible. "
        "Do not over-compress the number of entries."
    ),
}

register_snippets("en", _EN)

# ---------------------------------------------------------------------------
# Japanese snippets — inherits CJK bracket conventions from zh
# ---------------------------------------------------------------------------

_JA: dict[SnippetKey, str] = {
    SnippetKey.CHAPTER_HEADING_FMT: "【第{n}章：{title}】",
    SnippetKey.OUTLINE_HEADING_FMT: "【第{start}–{end}章 あらすじ】",
    SnippetKey.NO_OUTLINE: "あらすじはありません。",
    SnippetKey.LENGTH_GUIDANCE_TARGET: (
        "約{target}文字を目標に本文を十分に展開してください。"
        "約{min_chars}文字を明らかに下回ると不十分です。"
        "自然であれば約{ceiling}文字まで伸ばしても構いません。"
        "完全な文で終わらせてください。"
    ),
    SnippetKey.LENGTH_GUIDANCE_DEFAULT: "自然で完結した一章を書き、完全な文で終わらせてください。",
    SnippetKey.SYSTEM_LENGTH_HEADER: "【文字数規律】",
    SnippetKey.SYSTEM_LENGTH_RULES: (
        "- 分析・概要・前置きなしで本文を直接書き始めてください\n"
        "- 十分に展開されていない場合、早期に終わらせないでください"
    ),
    SnippetKey.STYLE_ANCHOR: (
        "続きの文体・語調・文のリズム・語彙レベルは、"
        "下記 <recent_chapters> と完全に一致させてください。"
        "冒頭から原文のスタイルにシームレスに接続してください。"
    ),
    SnippetKey.CONTINUE_INSTRUCTION: "{reference}の続きを書いてください：",
    SnippetKey.SECTION_SYSTEMS: "〈世界体系〉",
    SnippetKey.SECTION_ENTITIES: "〈登場人物・事物〉",
    SnippetKey.SECTION_RELATIONSHIPS: "〈人物関係〉",
    SnippetKey.UNNAMED_SYSTEM: "（名称未設定の体系）",
    SnippetKey.UNNAMED_ENTITY: "（名称未設定のエンティティ）",
    SnippetKey.ALIASES_LABEL: "別名：",
    SnippetKey.DESC_SEPARATOR: "：",
    SnippetKey.ALIAS_SEPARATOR: "、",
    SnippetKey.USER_INSTRUCTION_HEADER: "【ユーザー指示】",
    SnippetKey.WORLDGEN_CHUNK_DIRECTIVE_MULTI: (
        "現在、世界観設定テキストの第{chunk_index}/{chunk_count}段を処理しています。"
        "この段にある明確で安定した再利用可能な設定をできるだけ網羅してください。"
        "他の段と重複しても問題ありません。システムが後で自動的に統合します。"
    ),
    SnippetKey.WORLDGEN_CHUNK_DIRECTIVE_SINGLE: (
        "テキスト中の明確で安定した再利用可能な設定をできるだけ網羅してください。"
        "エントリ数を過度に圧縮しないでください。"
    ),
}

register_snippets("ja", _JA)

# ---------------------------------------------------------------------------
# Korean snippets
# ---------------------------------------------------------------------------

_KO: dict[SnippetKey, str] = {
    SnippetKey.CHAPTER_HEADING_FMT: "【제{n}장: {title}】",
    SnippetKey.OUTLINE_HEADING_FMT: "【제{start}–{end}장 개요】",
    SnippetKey.NO_OUTLINE: "개요가 없습니다.",
    SnippetKey.LENGTH_GUIDANCE_TARGET: (
        "약 {target}자를 목표로 본문을 충분히 전개해 주세요. "
        "약 {min_chars}자보다 확연히 짧으면 분량이 부족합니다. "
        "자연스럽다면 약 {ceiling}자까지 늘려도 괜찮습니다. "
        "완전한 문장으로 끝내 주세요."
    ),
    SnippetKey.LENGTH_GUIDANCE_DEFAULT: "자연스럽고 완결된 한 장을 써 주세요. 완전한 문장으로 마무리하세요.",
    SnippetKey.SYSTEM_LENGTH_HEADER: "【길이 규율】",
    SnippetKey.SYSTEM_LENGTH_RULES: (
        "- 분석, 개요, 서론 없이 바로 본문을 시작하세요\n"
        "- 충분히 전개되지 않았다면 너무 일찍 끝내지 마세요"
    ),
    SnippetKey.STYLE_ANCHOR: (
        "이어쓰기의 문체, 어조, 문장 리듬, 어휘 수준은 "
        "아래 <recent_chapters>와 완전히 일치해야 합니다. "
        "첫 문장부터 원문의 스타일에 자연스럽게 이어 주세요."
    ),
    SnippetKey.CONTINUE_INSTRUCTION: "{reference} 이어쓰기:",
    SnippetKey.SECTION_SYSTEMS: "〈세계 체계〉",
    SnippetKey.SECTION_ENTITIES: "〈등장인물 및 사물〉",
    SnippetKey.SECTION_RELATIONSHIPS: "〈인물 관계〉",
    SnippetKey.UNNAMED_SYSTEM: "(이름 없는 체계)",
    SnippetKey.UNNAMED_ENTITY: "(이름 없는 개체)",
    SnippetKey.ALIASES_LABEL: "별명: ",
    SnippetKey.DESC_SEPARATOR: "：",
    SnippetKey.ALIAS_SEPARATOR: ", ",
    SnippetKey.USER_INSTRUCTION_HEADER: "【사용자 지시】",
    SnippetKey.WORLDGEN_CHUNK_DIRECTIVE_MULTI: (
        "현재 세계관 설정 텍스트의 {chunk_index}/{chunk_count}번째 단락을 처리하고 있습니다. "
        "이 단락에서 명확하고 안정적이며 재사용 가능한 설정을 최대한 추출해 주세요. "
        "다른 단락과 중복되어도 괜찮습니다. 시스템이 나중에 자동으로 통합합니다."
    ),
    SnippetKey.WORLDGEN_CHUNK_DIRECTIVE_SINGLE: (
        "텍스트에서 명확하고 안정적이며 재사용 가능한 설정을 최대한 추출해 주세요. "
        "항목 수를 과도하게 압축하지 마세요."
    ),
}

register_snippets("ko", _KO)
