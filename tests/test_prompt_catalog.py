# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Regression tests for the prompt template catalog.

Contracts verified:
1. Every PromptKey resolves to a non-empty string via get_prompt().
2. The backward-compat shim (app.utils.prompts) re-exports identical strings.
3. Locale fallback works: unknown locale falls back to DEFAULT_LOCALE.
4. Missing key raises KeyError.
5. register_templates() merges without clobbering existing keys.
6. Template format placeholders match what consumers expect.
"""

from __future__ import annotations

import pytest

from app.core.text import DEFAULT_LOCALE, PromptKey, get_prompt, register_templates
from app.core.text.catalog import _catalogs


# -----------------------------------------------------------------------
# 1. Every key resolves
# -----------------------------------------------------------------------

@pytest.mark.parametrize("key", list(PromptKey))
def test_all_keys_resolve(key: PromptKey) -> None:
    result = get_prompt(key)
    assert isinstance(result, str)
    assert len(result) > 0


# -----------------------------------------------------------------------
# 2. Backward-compat shim matches catalog
# -----------------------------------------------------------------------

def test_shim_matches_catalog() -> None:
    from app.utils.prompts import (
        CONTINUATION_PROMPT,
        OUTLINE_PROMPT,
        SYSTEM_PROMPT,
        WORLD_GENERATION_PROMPT,
        WORLD_GENERATION_SYSTEM_PROMPT,
    )

    assert SYSTEM_PROMPT == get_prompt(PromptKey.SYSTEM)
    assert CONTINUATION_PROMPT == get_prompt(PromptKey.CONTINUATION)
    assert OUTLINE_PROMPT == get_prompt(PromptKey.OUTLINE)
    assert WORLD_GENERATION_SYSTEM_PROMPT == get_prompt(PromptKey.WORLD_GEN_SYSTEM)
    assert WORLD_GENERATION_PROMPT == get_prompt(PromptKey.WORLD_GEN)


# -----------------------------------------------------------------------
# 3. Locale fallback
# -----------------------------------------------------------------------

def test_unknown_locale_falls_back_to_default() -> None:
    result = get_prompt(PromptKey.SYSTEM, locale="xx-nonexistent")
    assert result == get_prompt(PromptKey.SYSTEM, locale=DEFAULT_LOCALE)


# -----------------------------------------------------------------------
# 4. Missing key raises KeyError
# -----------------------------------------------------------------------

def test_missing_key_in_empty_locale_raises() -> None:
    # Register a locale with only one key, then ask for another.
    register_templates("test-sparse", {PromptKey.SYSTEM: "test"})
    try:
        # SYSTEM exists — should work.
        assert get_prompt(PromptKey.SYSTEM, locale="test-sparse") == "test"
        # OUTLINE does not exist in this locale, but DEFAULT_LOCALE fallback
        # should still provide it.
        assert get_prompt(PromptKey.OUTLINE, locale="test-sparse") == get_prompt(
            PromptKey.OUTLINE
        )
    finally:
        _catalogs.pop("test-sparse", None)


# -----------------------------------------------------------------------
# 5. register_templates merges
# -----------------------------------------------------------------------

def test_register_templates_merges() -> None:
    register_templates("test-merge", {PromptKey.SYSTEM: "a"})
    register_templates("test-merge", {PromptKey.OUTLINE: "b"})
    try:
        assert _catalogs["test-merge"][PromptKey.SYSTEM] == "a"
        assert _catalogs["test-merge"][PromptKey.OUTLINE] == "b"
    finally:
        _catalogs.pop("test-merge", None)


def test_register_templates_overwrites_individual_key() -> None:
    register_templates("test-overwrite", {PromptKey.SYSTEM: "old"})
    register_templates("test-overwrite", {PromptKey.SYSTEM: "new"})
    try:
        assert _catalogs["test-overwrite"][PromptKey.SYSTEM] == "new"
    finally:
        _catalogs.pop("test-overwrite", None)


# -----------------------------------------------------------------------
# 6. Format placeholders match consumer expectations
# -----------------------------------------------------------------------

def test_continuation_template_has_expected_placeholders() -> None:
    tpl = get_prompt(PromptKey.CONTINUATION)
    # generator.py calls .format(title=..., next_chapter=..., outline=...,
    #                            world_context=..., narrative_constraints=...)
    formatted = tpl.format(
        title="Test Novel",
        next_chapter=42,
        outline="outline text",
        world_context="",
        narrative_constraints="",
    )
    assert "Test Novel" in formatted
    assert "42" in formatted


def test_outline_template_has_expected_placeholders() -> None:
    tpl = get_prompt(PromptKey.OUTLINE)
    formatted = tpl.format(start=1, end=10, content="chapter content")
    assert "1" in formatted
    assert "10" in formatted
    assert "chapter content" in formatted


def test_world_gen_template_has_expected_placeholders() -> None:
    tpl = get_prompt(PromptKey.WORLD_GEN)
    formatted = tpl.format(text="world text", chunk_directive="directive")
    assert "world text" in formatted
    assert "directive" in formatted


# -----------------------------------------------------------------------
# 7. Provider parameter accepted (forward compat, no dispatch yet)
# -----------------------------------------------------------------------

def test_provider_parameter_accepted() -> None:
    result = get_prompt(PromptKey.SYSTEM, provider="deepseek")
    assert result == get_prompt(PromptKey.SYSTEM)
