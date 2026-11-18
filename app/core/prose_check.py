# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""
Post-generation prose-quality checks (non-blocking).

Goal:
- Catch obvious prose-quality problems in generated continuations.
- Surface advisory warnings to the client in a separate panel from drift warnings.

This module is intentionally deterministic, stateless, and lightweight.
No LLM calls, no DB reads/writes, no heavyweight NLP dependencies.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from typing import Any, Sequence

from app.language_policy import get_language_policy
from app.schemas import ProseWarning

# ---------------------------------------------------------------------------
# Language family detection (mirrors continuation_postcheck)
# ---------------------------------------------------------------------------


def _get_language_family(novel_language: str | None) -> str:
    if novel_language is None:
        return "both"
    policy = get_language_policy(novel_language)
    return policy.family


# ---------------------------------------------------------------------------
# Helper: evidence snippet
# ---------------------------------------------------------------------------


def _evidence_snippet(text: str, start: int, end: int, *, window: int = 30) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    snippet = text[left:right].replace("\n", " ").strip()
    if left > 0:
        snippet = "…" + snippet
    if right < len(text):
        snippet = snippet + "…"
    return snippet


# ---------------------------------------------------------------------------
# Rule: repeated_ngram
# ---------------------------------------------------------------------------

# CJK-family script ranges for tokenization/counting. `get_language_policy()`
# routes zh/ja/ko into the same "cjk" family, so prose checks must treat Han,
# kana, and hangul as countable script characters.
_CJK_SCRIPT_RANGES = "\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af"
_RE_CJK_CHAR = re.compile(f"[{_CJK_SCRIPT_RANGES}]")
_RE_CJK_RUN = re.compile(f"[{_CJK_SCRIPT_RANGES}]+")
_RE_WS_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)

NgramOccurrence = tuple[str, int, int]


def _cjk_ngrams(text: str, n: int) -> list[NgramOccurrence]:
    """Extract character-level n-grams without crossing punctuation or paragraph boundaries."""
    occurrences: list[NgramOccurrence] = []
    for match in _RE_CJK_RUN.finditer(text):
        segment = match.group()
        if len(segment) < n:
            continue
        base = match.start()
        occurrences.extend(
            (segment[i : i + n], base + i, base + i + n)
            for i in range(len(segment) - n + 1)
        )
    return occurrences


def _whitespace_tokens(text: str) -> list[tuple[str, int, int]]:
    return [
        (match.group().lower(), match.start(), match.end())
        for match in _RE_WS_WORD.finditer(text)
    ]


def _whitespace_ngrams(text: str, n: int) -> list[NgramOccurrence]:
    """Extract normalized word n-grams, ignoring surrounding punctuation and quotes."""
    tokens = _whitespace_tokens(text)
    if len(tokens) < n:
        return []
    return [
        (
            " ".join(token for token, _, _ in tokens[i : i + n]),
            tokens[i][1],
            tokens[i + n - 1][2],
        )
        for i in range(len(tokens) - n + 1)
    ]


_REPEATED_NGRAM_THRESHOLD = 3  # flag if an n-gram appears >= this many times
_NGRAM_SIZES_CJK = (3, 4, 5, 6)
_NGRAM_SIZES_WS = (3, 4, 5)


def _top_repeated_ngram_candidate(
    text: str,
    *,
    ngram_sizes: Sequence[int],
    gram_getter: Callable[[str, int], list[NgramOccurrence]],
) -> tuple[str, int, int, int] | None:
    """
    Return the strongest repeated n-gram candidate for the given token family.

    v0 intentionally emits at most one repeated-ngram warning per language family
    and continuation. This keeps the panel readable and avoids surfacing every
    sliding-window rotation of the same repeated phrase.
    """
    candidates: list[tuple[str, int, int, int]] = []

    for n in ngram_sizes:
        occurrences = gram_getter(text, n)
        counts = Counter(gram for gram, _, _ in occurrences)
        first_spans: dict[str, tuple[int, int]] = {}
        for gram, start, end in occurrences:
            first_spans.setdefault(gram, (start, end))
        for gram, count in counts.items():
            if count < _REPEATED_NGRAM_THRESHOLD:
                continue
            start, end = first_spans[gram]
            candidates.append((gram, count, start, end))

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            -item[1],          # more repetitions first
            -len(item[0]),     # then prefer the more specific phrase
            item[2],
            item[0],
        )
    )
    return candidates[0]


def _check_repeated_ngrams(
    text: str, *, family: str, version: int,
) -> list[ProseWarning]:
    warnings: list[ProseWarning] = []

    if family in ("cjk", "both"):
        candidate = _top_repeated_ngram_candidate(
            text,
            ngram_sizes=sorted(_NGRAM_SIZES_CJK, reverse=True),
            gram_getter=_cjk_ngrams,
        )
        if candidate is not None:
            gram, count, start, end = candidate
            evidence = _evidence_snippet(text, start, end)
            warnings.append(
                ProseWarning(
                    code="repeated_ngram",
                    message_key="continuation.prosecheck.warning.repeated_ngram",
                    message_params={"phrase": gram, "count": count},
                    message=f"Repeated phrase '{gram}' appears {count} times in generated text.",
                    version=version,
                    evidence=evidence,
                )
            )

    if family in ("whitespace", "both"):
        candidate = _top_repeated_ngram_candidate(
            text,
            ngram_sizes=sorted(_NGRAM_SIZES_WS, reverse=True),
            gram_getter=_whitespace_ngrams,
        )
        if candidate is not None:
            gram, count, start, end = candidate
            evidence = _evidence_snippet(text, start, end)
            warnings.append(
                ProseWarning(
                    code="repeated_ngram",
                    message_key="continuation.prosecheck.warning.repeated_ngram",
                    message_params={"phrase": gram, "count": count},
                    message=f"Repeated phrase '{gram}' appears {count} times in generated text.",
                    version=version,
                    evidence=evidence,
                )
            )

    return warnings


# ---------------------------------------------------------------------------
# Rule: long_paragraph
# ---------------------------------------------------------------------------

_LONG_PARA_CHARS_CJK = 600
_LONG_PARA_WORDS_WS = 250


def _check_long_paragraphs(
    text: str, *, family: str, version: int,
) -> list[ProseWarning]:
    warnings: list[ProseWarning] = []
    paragraphs = re.split(r"\n\s*\n", text)

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        is_long = False
        metric_length: int | None = None
        metric_unit: str | None = None
        if family in ("cjk", "both"):
            cjk_chars = len(_RE_CJK_CHAR.findall(para))
            if cjk_chars > _LONG_PARA_CHARS_CJK:
                is_long = True
                metric_length = cjk_chars
                metric_unit = "cjk_chars"
        if not is_long and family in ("whitespace", "both"):
            word_count = len(para.split())
            if word_count > _LONG_PARA_WORDS_WS:
                is_long = True
                metric_length = word_count
                metric_unit = "words"

        if is_long:
            snippet = para[:80] + ("…" if len(para) > 80 else "")
            length_value = int(metric_length or len(para))
            unit_value = metric_unit or "chars"
            unit_label = "words" if unit_value == "words" else "characters"
            warnings.append(
                ProseWarning(
                    code="long_paragraph",
                    message_key="continuation.prosecheck.warning.long_paragraph",
                    message_params={"length": length_value, "unit": unit_value},
                    message=f"Paragraph is unusually long ({length_value} {unit_label}).",
                    version=version,
                    evidence=snippet,
                )
            )

    return warnings


# ---------------------------------------------------------------------------
# Rule: abnormal_sentence_length
# ---------------------------------------------------------------------------

# Sentence splitters: rudimentary but sufficient for advisory warnings
# CJK-family prose may end with either full-width or ASCII terminators
# (notably Korean prose often uses '.', '!', '?').
_RE_SENTENCE_CJK = re.compile(r"[^。！？.!?…\n]+[。！？.!?…]")
_RE_SENTENCE_WS = re.compile(r"[^.!?\n]+[.!?]")

_LONG_SENTENCE_CHARS_CJK = 200
_LONG_SENTENCE_WORDS_WS = 60


def _check_abnormal_sentence_length(
    text: str, *, family: str, version: int,
) -> list[ProseWarning]:
    warnings: list[ProseWarning] = []

    if family in ("cjk", "both"):
        for m in _RE_SENTENCE_CJK.finditer(text):
            sentence = m.group().strip()
            cjk_chars = len(_RE_CJK_CHAR.findall(sentence))
            if cjk_chars > _LONG_SENTENCE_CHARS_CJK:
                snippet = sentence[:80] + ("…" if len(sentence) > 80 else "")
                warnings.append(
                    ProseWarning(
                        code="abnormal_sentence_length",
                        message_key="continuation.prosecheck.warning.abnormal_sentence_length",
                        message_params={"length": cjk_chars, "unit": "cjk_chars"},
                        message=f"Sentence is unusually long ({cjk_chars} CJK characters).",
                        version=version,
                        evidence=snippet,
                    )
                )

    if family in ("whitespace", "both"):
        for m in _RE_SENTENCE_WS.finditer(text):
            sentence = m.group().strip()
            word_count = len(sentence.split())
            if word_count > _LONG_SENTENCE_WORDS_WS:
                snippet = sentence[:100] + ("…" if len(sentence) > 100 else "")
                warnings.append(
                    ProseWarning(
                        code="abnormal_sentence_length",
                        message_key="continuation.prosecheck.warning.abnormal_sentence_length",
                        message_params={"length": word_count, "unit": "words"},
                        message=f"Sentence is unusually long ({word_count} words).",
                        version=version,
                        evidence=snippet,
                    )
                )

    return warnings


# ---------------------------------------------------------------------------
# Rule: summary_tone
# ---------------------------------------------------------------------------

_SUMMARY_TONE_PATTERNS_CJK = re.compile(
    r"(总之|综上所述|综上|总而言之|由此可见|不难看出|换言之|概括来说|一言以蔽之|通过以上分析|"
    r"要するに|まとめると|一言で言えば|結論として|"
    r"요컨대|정리하자면|결론적으로|한마디로(?: 말해)?|다시 말해)",
)
_SUMMARY_TONE_PATTERNS_WS = re.compile(
    r"\b(In summary|To summarize|In conclusion|Overall|To sum up|All in all|"
    r"In essence|Ultimately|As we can see|It is worth noting|"
    r"It should be noted|Needless to say)\b",
    re.IGNORECASE,
)


def _check_summary_tone(
    text: str, *, family: str, version: int,
) -> list[ProseWarning]:
    warnings: list[ProseWarning] = []
    seen_phrases: set[str] = set()

    if family in ("cjk", "both"):
        for m in _SUMMARY_TONE_PATTERNS_CJK.finditer(text):
            phrase = m.group()
            if phrase in seen_phrases:
                continue
            seen_phrases.add(phrase)
            evidence = _evidence_snippet(text, m.start(), m.end())
            warnings.append(
                ProseWarning(
                    code="summary_tone",
                    message_key="continuation.prosecheck.warning.summary_tone",
                    message_params={"phrase": phrase},
                    message=f"Summary/analytical tone detected: '{phrase}' may feel out-of-place in prose.",
                    version=version,
                    evidence=evidence,
                )
            )

    if family in ("whitespace", "both"):
        for m in _SUMMARY_TONE_PATTERNS_WS.finditer(text):
            phrase = m.group()
            key = phrase.lower()
            if key in seen_phrases:
                continue
            seen_phrases.add(key)
            evidence = _evidence_snippet(text, m.start(), m.end())
            warnings.append(
                ProseWarning(
                    code="summary_tone",
                    message_key="continuation.prosecheck.warning.summary_tone",
                    message_params={"phrase": phrase},
                    message=f"Summary/analytical tone detected: '{phrase}' may feel out-of-place in prose.",
                    version=version,
                    evidence=evidence,
                )
            )

    return warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prose_check_continuation(
    *,
    continuations: Sequence[Any],
    novel_language: str | None = None,
) -> list[ProseWarning]:
    """
    Run prose-quality postchecks over generated continuations.

    Args:
      continuations: list of objects with a .content attribute.
      novel_language: language code of the novel (used to select rule variants).

    Returns:
      list of ProseWarning objects, sorted by (version, code).
    """
    family = _get_language_family(novel_language)
    warnings: list[ProseWarning] = []

    for idx, cont in enumerate(continuations, start=1):
        text = str(getattr(cont, "content", "") or "")
        if not text.strip():
            continue

        warnings.extend(_check_repeated_ngrams(text, family=family, version=idx))
        warnings.extend(_check_long_paragraphs(text, family=family, version=idx))
        warnings.extend(
            _check_abnormal_sentence_length(text, family=family, version=idx)
        )
        warnings.extend(_check_summary_tone(text, family=family, version=idx))

    warnings.sort(key=lambda w: (int(w.version or 0), w.code))
    return warnings
