# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Turn-intent and quick-action prompt policy helpers for copilot."""

from __future__ import annotations

from app.core.copilot.prompt_registry import (
    _CAPABILITY_HINTS,
    _GREETING_NORMALIZED,
    _PUNCTUATION_RE,
    _TASK_INTENT_HINTS,
    prompt_map,
    prompt_text,
)


def _strip_quick_action_prefix(prompt: str) -> str:
    for prefix in ("[研究重点:", "[Research focus:"):
        if prompt.startswith(prefix):
            closing = prompt.find("]")
            if closing != -1:
                return prompt[closing + 1 :].strip()
    return prompt.strip()


def apply_quick_action_prompt(
    prompt: str,
    quick_action_id: str | None,
    interaction_locale: str = "zh",
) -> str:
    """Prefix the user prompt with an internal quick-action research focus."""
    if not quick_action_id:
        return prompt
    try:
        focus = prompt_map(interaction_locale, "quick_action_focus", quick_action_id)
    except KeyError:
        return prompt
    prefix = prompt_text(interaction_locale, "quick_action_prefix", focus=focus)
    return f"{prefix}\n\n{prompt}"


def classify_turn_intent(prompt: str) -> str:
    """Classify the current user turn."""
    raw = _strip_quick_action_prefix(prompt)
    if not raw:
        return "smalltalk"

    lowered = raw.casefold()
    normalized = _PUNCTUATION_RE.sub("", lowered)

    if any(hint in lowered for hint in _CAPABILITY_HINTS):
        return "capability_query"

    if normalized in _GREETING_NORMALIZED:
        return "smalltalk"

    if any(hint in lowered for hint in _TASK_INTENT_HINTS):
        return "task_query"

    if len(normalized) <= 6 and any(
        token in normalized
        for token in ("你好", "您好", "在吗", "谢谢", "hi", "hello", "hey")
    ):
        return "smalltalk"

    return "task_query"


def should_preload_world_context(turn_intent: str) -> bool:
    return turn_intent == "task_query"
