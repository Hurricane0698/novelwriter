# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Backward-compatible prompt re-exports.

Canonical source is ``app.core.text``.  New code should import from there
directly.  This shim keeps existing ``from app.utils.prompts import X``
working until all call sites migrate.
"""

from app.core.text import PromptKey, get_prompt  # noqa: F401

SYSTEM_PROMPT: str = get_prompt(PromptKey.SYSTEM)
CONTINUATION_PROMPT: str = get_prompt(PromptKey.CONTINUATION)
OUTLINE_PROMPT: str = get_prompt(PromptKey.OUTLINE)
WORLD_GENERATION_SYSTEM_PROMPT: str = get_prompt(PromptKey.WORLD_GEN_SYSTEM)
WORLD_GENERATION_PROMPT: str = get_prompt(PromptKey.WORLD_GEN)
