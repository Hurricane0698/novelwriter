# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""
Post-generation continuation checks (non-blocking).

Goal:
- Catch obvious lore drift signals (new proper nouns / invented honorifics) early.
- Surface warnings to the client for quick iteration.

This module is intentionally deterministic and does not read/write the DB.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from app.language_policy import get_language_policy
from app.schemas import PostcheckWarning

_CJK_RANGE = "\u4e00-\u9fff"

# ---------------------------------------------------------------------------
# CJK patterns (existing)
# ---------------------------------------------------------------------------
_RE_SINGLE_QUOTES = re.compile(
    r'\u2018([' + _CJK_RANGE + r']{2,20})\u2019'
)
_RE_BOOK_QUOTES = re.compile(rf"《([{_CJK_RANGE}]{{2,20}})》")
_RE_BRACKETS = re.compile(rf"【([{_CJK_RANGE}]{{2,20}})】")

_RE_NAMING_CUE = re.compile(
    r'(?:名为|称为|其名|名曰|号称|被称为|唤作|唤为)[\u201c\u0022\u300a\u3010\u2018\u2019]?'
    r'([' + _CJK_RANGE + r']{2,20})'
    r'[\u201d\u0022\u300b\u3011\u2018\u2019]?'
)

_RE_DIALOGUE_ADDRESS = re.compile(
    r'\u201c([' + _CJK_RANGE + r']{2,6})[！!，,：:]'
)

_ADDRESS_STOPWORDS = {
    "太好了",
    "好了",
    "快点",
    "等等",
    "别怕",
    "不必",
    "住手",
}

# ---------------------------------------------------------------------------
# English patterns
# ---------------------------------------------------------------------------
# Quoted terms: capitalized words in smart/straight double quotes
_RE_EN_QUOTED_TERMS = re.compile(
    r'[\u201c"]((?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*))[\u201d"]'
)

# Naming cues: "named X", "called X", etc.
_RE_EN_NAMING_CUE = re.compile(
    r'(?:named|called|known as|dubbed|titled|christened)\s+'
    r'["\u201c\']?([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)["\u201d\']?'
)

# Dialogue address: "John!" or "John," at start of dialogue
_RE_EN_DIALOGUE_ADDRESS = re.compile(
    r'[\u201c"]([A-Z][a-z]+)[!,:]'
)

_EN_ADDRESS_STOPWORDS = {
    "Well", "Look", "Listen", "Wait", "Stop", "Come", "Help",
    "Please", "Thanks", "Hello", "Hey", "Yes", "Yeah", "Okay",
    "Sure", "Right", "Fine", "Good", "Great", "God", "Dear",
    "Damn", "Wow", "Hmm", "Huh", "Shh", "Hush", "Alas",
    "Oh", "No", "Ah",
}

# ---------------------------------------------------------------------------
# Japanese patterns (supplement CJK patterns with JA-specific cues)
# ---------------------------------------------------------------------------
_JA_CHAR_RANGE = "ぁ-ヿ\u4e00-\u9fff"  # hiragana + katakana + kanji

# Name BEFORE cue: 魔王と呼ばれる, 魔王という名の, 魔王と名乗る
_RE_JA_NAMING_CUE_PRE = re.compile(
    rf'([{_JA_CHAR_RANGE}]{{2,20}})(?:と呼ばれる|という名の|と名乗る)'
)
# Name AFTER cue: 名は魔王, 名前は魔王
_RE_JA_NAMING_CUE_POST = re.compile(
    rf'(?:名は|名前は)([{_JA_CHAR_RANGE}]{{2,20}})'
)
# 「-quoted dialogue with hiragana+kanji names
_RE_JA_DIALOGUE_ADDRESS = re.compile(
    rf'\u300c([{_JA_CHAR_RANGE}]{{2,6}})[！!、,：:]'
)

_JA_ADDRESS_STOPWORDS = {
    "すみません", "ありがとう", "おはよう", "ちょっと",
    "やめて", "お願い", "よろしく", "なるほど",
}

# ---------------------------------------------------------------------------
# Korean patterns (supplement CJK patterns with KO-specific cues)
# ---------------------------------------------------------------------------
_HANGUL_RANGE = "가-힣"

# Name BEFORE cue: 마왕라고 불리는, 마왕이라 불리는
_RE_KO_NAMING_CUE_PRE = re.compile(
    rf'([{_HANGUL_RANGE}]{{2,20}})(?:라고\s*불리는|라는|이라\s*불리는|이라는)'
)
# Name AFTER cue: 이름은 마왕
_RE_KO_NAMING_CUE_POST = re.compile(
    rf'(?:이름은)\s*([{_HANGUL_RANGE}]{{2,20}})'
)
# Korean dialogue uses straight quotes or CJK quotes
_RE_KO_DIALOGUE_ADDRESS = re.compile(
    rf'["\u201c\u300c]([{_HANGUL_RANGE}]{{2,6}})[！!、,：:]'
)

_KO_ADDRESS_STOPWORDS = {
    "그래서", "하지만", "그런데", "잠깐만", "여보세", "이봐요",
}


def _iter_system_labels(data: Any) -> Iterable[str]:
    if isinstance(data, dict):
        for k, v in data.items():
            if k in {"label", "name"} and isinstance(v, str):
                yield v
            else:
                yield from _iter_system_labels(v)
        return
    if isinstance(data, list):
        for item in data:
            yield from _iter_system_labels(item)


def _build_known_terms(writer_ctx: Mapping[str, Any]) -> set[str]:
    terms: set[str] = set()

    for ent in writer_ctx.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        name = str(ent.get("name") or "").strip()
        if name:
            terms.add(name)
        aliases = ent.get("aliases") or []
        if isinstance(aliases, list):
            for a in aliases:
                a = str(a or "").strip()
                if a:
                    terms.add(a)

    for sys in writer_ctx.get("systems") or []:
        if not isinstance(sys, dict):
            continue
        name = str(sys.get("name") or "").strip()
        if name:
            terms.add(name)
        data = sys.get("data")
        for label in _iter_system_labels(data):
            label = str(label or "").strip()
            if label:
                terms.add(label)

    return terms


def _evidence_snippet(text: str, start: int, end: int, *, window: int = 18) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    return text[left:right].replace("\n", " ")


def _get_language_family(novel_language: str | None) -> str:
    """Return 'cjk', 'whitespace', or 'both' for pattern selection."""
    if novel_language is None:
        return "both"
    policy = get_language_policy(novel_language)
    return policy.family


def _extract_cjk_matches(text: str) -> list[tuple[str, str, int, int]]:
    """CJK-specific pattern extraction."""
    out: list[tuple[str, str, int, int]] = []

    for m in _RE_SINGLE_QUOTES.finditer(text):
        out.append(("unknown_term_quoted", m.group(1), m.start(1), m.end(1)))
    for m in _RE_BOOK_QUOTES.finditer(text):
        out.append(("unknown_term_quoted", m.group(1), m.start(1), m.end(1)))
    for m in _RE_BRACKETS.finditer(text):
        out.append(("unknown_term_bracketed", m.group(1), m.start(1), m.end(1)))
    for m in _RE_NAMING_CUE.finditer(text):
        out.append(("unknown_term_named", m.group(1), m.start(1), m.end(1)))
    for m in _RE_DIALOGUE_ADDRESS.finditer(text):
        term = m.group(1)
        if term in _ADDRESS_STOPWORDS:
            continue
        out.append(("unknown_address_token", term, m.start(1), m.end(1)))

    return out


def _extract_en_matches(text: str) -> list[tuple[str, str, int, int]]:
    """English-specific pattern extraction."""
    out: list[tuple[str, str, int, int]] = []

    for m in _RE_EN_QUOTED_TERMS.finditer(text):
        out.append(("unknown_term_quoted", m.group(1), m.start(1), m.end(1)))
    for m in _RE_EN_NAMING_CUE.finditer(text):
        out.append(("unknown_term_named", m.group(1), m.start(1), m.end(1)))
    for m in _RE_EN_DIALOGUE_ADDRESS.finditer(text):
        term = m.group(1)
        if term in _EN_ADDRESS_STOPWORDS:
            continue
        out.append(("unknown_address_token", term, m.start(1), m.end(1)))

    return out


def _extract_ja_matches(text: str) -> list[tuple[str, str, int, int]]:
    """Japanese-specific pattern extraction (supplements CJK patterns)."""
    out: list[tuple[str, str, int, int]] = []

    for m in _RE_JA_NAMING_CUE_PRE.finditer(text):
        out.append(("unknown_term_named", m.group(1), m.start(1), m.end(1)))
    for m in _RE_JA_NAMING_CUE_POST.finditer(text):
        out.append(("unknown_term_named", m.group(1), m.start(1), m.end(1)))
    for m in _RE_JA_DIALOGUE_ADDRESS.finditer(text):
        term = m.group(1)
        if term in _JA_ADDRESS_STOPWORDS:
            continue
        out.append(("unknown_address_token", term, m.start(1), m.end(1)))

    return out


def _extract_ko_matches(text: str) -> list[tuple[str, str, int, int]]:
    """Korean-specific pattern extraction (supplements CJK patterns)."""
    out: list[tuple[str, str, int, int]] = []

    for m in _RE_KO_NAMING_CUE_PRE.finditer(text):
        out.append(("unknown_term_named", m.group(1), m.start(1), m.end(1)))
    for m in _RE_KO_NAMING_CUE_POST.finditer(text):
        out.append(("unknown_term_named", m.group(1), m.start(1), m.end(1)))
    for m in _RE_KO_DIALOGUE_ADDRESS.finditer(text):
        term = m.group(1)
        if term in _KO_ADDRESS_STOPWORDS:
            continue
        out.append(("unknown_address_token", term, m.start(1), m.end(1)))

    return out


def _extract_term_matches(
    text: str,
    *,
    novel_language: str | None = None,
) -> list[tuple[str, str, int, int]]:
    """Return list of (code, term, start, end) candidates."""
    family = _get_language_family(novel_language)

    if family == "cjk":
        matches = _extract_cjk_matches(text)
        if novel_language:
            base = get_language_policy(novel_language).base_language
            if base == "ja":
                matches += _extract_ja_matches(text)
            elif base == "ko":
                matches += _extract_ko_matches(text)
        return matches
    if family == "whitespace":
        return _extract_en_matches(text)
    # Both / unknown — run all patterns
    return _extract_cjk_matches(text) + _extract_en_matches(text)


def postcheck_continuation(
    *,
    writer_ctx: Mapping[str, Any],
    recent_text: str,
    user_prompt: str | None,
    continuations: Sequence[Any],
    novel_language: str | None = None,
) -> list[PostcheckWarning]:
    """
    Run postchecks over generated continuations.

    Args:
      writer_ctx: assembled writer context (already budget-trimmed).
      recent_text: the actual recent chapters text (without user instruction appended).
      user_prompt: optional user instruction text.
      continuations: list of Continuation ORM rows (must have .content).
      novel_language: language code of the novel (used to select pattern set).
    """
    known_terms = _build_known_terms(writer_ctx)
    prompt = (user_prompt or "").strip()
    recent = recent_text or ""

    warnings: list[PostcheckWarning] = []
    seen: set[tuple[int, str, str]] = set()

    for idx, cont in enumerate(continuations, start=1):
        text = str(getattr(cont, "content", "") or "")
        for code, term, start, end in _extract_term_matches(
            text, novel_language=novel_language,
        ):
            term = str(term or "").strip()
            if not term:
                continue

            # Consider a term "known" if it appears in injected world context, the recent
            # chapters, or the user instruction.
            if term in known_terms:
                continue
            if term in recent:
                continue
            if prompt and term in prompt:
                continue

            sig = (idx, code, term)
            if sig in seen:
                continue
            seen.add(sig)

            evidence = _evidence_snippet(text, start, end)
            warnings.append(
                PostcheckWarning(
                    code=code,
                    term=term,
                    message_key=f"continuation.postcheck.warning.{code}",
                    message_params={"term": term},
                    message=(
                        "Potential lore drift / invented naming: "
                        f"term '{term}' not found in World Context, recent chapters, or user instruction."
                    ),
                    version=idx,
                    evidence=evidence,
                )
            )

    warnings.sort(key=lambda w: (int(w.version or 0), w.code, w.term))
    return warnings
