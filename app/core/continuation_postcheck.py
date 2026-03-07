# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

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

from app.schemas import PostcheckWarning

_CJK_RANGE = "\u4e00-\u9fff"

_RE_SINGLE_QUOTES = re.compile(rf"‘([{_CJK_RANGE}]{{2,20}})’")
_RE_BOOK_QUOTES = re.compile(rf"《([{_CJK_RANGE}]{{2,20}})》")
_RE_BRACKETS = re.compile(rf"【([{_CJK_RANGE}]{{2,20}})】")

# Common narrative cues used when introducing a named thing.
_RE_NAMING_CUE = re.compile(
    rf"(?:名为|称为|其名|名曰|号称|被称为|唤作|唤为)[“\"《【‘']?"
    rf"([{_CJK_RANGE}]{{2,20}})"
    rf"[”\"》】’']?"
)

# Dialogue address token (very common place for invented nicknames/honorifics).
_RE_DIALOGUE_ADDRESS = re.compile(rf"“([{_CJK_RANGE}]{{2,6}})[！!，,：:]")

_ADDRESS_STOPWORDS = {
    "太好了",
    "好了",
    "快点",
    "等等",
    "别怕",
    "不必",
    "住手",
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


def _extract_term_matches(text: str) -> list[tuple[str, str, int, int]]:
    """Return list of (code, term, start, end) candidates."""
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


def postcheck_continuation(
    *,
    writer_ctx: Mapping[str, Any],
    recent_text: str,
    user_prompt: str | None,
    continuations: Sequence[Any],
) -> list[PostcheckWarning]:
    """
    Run postchecks over generated continuations.

    Args:
      writer_ctx: assembled writer context (already budget-trimmed).
      recent_text: the actual recent chapters text (without user instruction appended).
      user_prompt: optional user instruction text.
      continuations: list of Continuation ORM rows (must have .content).
    """
    known_terms = _build_known_terms(writer_ctx)
    prompt = (user_prompt or "").strip()
    recent = recent_text or ""

    warnings: list[PostcheckWarning] = []
    seen: set[tuple[int, str, str]] = set()

    for idx, cont in enumerate(continuations, start=1):
        text = str(getattr(cont, "content", "") or "")
        for code, term, start, end in _extract_term_matches(text):
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
