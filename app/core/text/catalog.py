# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Prompt template catalog with locale/provider-aware lookup.

The catalog is a two-level registry: locale -> PromptKey -> template string.
Lookup falls back to DEFAULT_LOCALE when the requested locale has no entry.

Provider is accepted by get_prompt() but not yet dispatched — reserved for
provider-specific template variants (e.g. different formatting for different
LLM backends).
"""

from __future__ import annotations

from enum import Enum

DEFAULT_LOCALE = "zh"

# ---------------------------------------------------------------------------
# Prompt keys — one per template slot
# ---------------------------------------------------------------------------


class PromptKey(str, Enum):
    SYSTEM = "system"
    CONTINUATION = "continuation"
    OUTLINE = "outline"
    WORLD_GEN_SYSTEM = "world_gen_system"
    WORLD_GEN = "world_gen"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_catalogs: dict[str, dict[PromptKey, str]] = {}


def register_templates(locale: str, templates: dict[PromptKey, str]) -> None:
    """Merge *templates* into the catalog for *locale*.

    Safe to call multiple times for the same locale (e.g. when a new domain
    adds its own prompts).  Later calls overwrite individual keys, not the
    entire locale.
    """
    if locale not in _catalogs:
        _catalogs[locale] = {}
    _catalogs[locale].update(templates)


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def get_prompt(
    key: PromptKey,
    *,
    locale: str | None = None,
    provider: str | None = None,
) -> str:
    """Return the template string for *key*.

    Lookup order:
    1. Exact *locale* match.
    2. DEFAULT_LOCALE fallback.

    *provider* is accepted for forward compatibility but does not yet
    influence selection.

    Raises ``KeyError`` if no template is found.
    """
    effective = locale or DEFAULT_LOCALE

    catalog = _catalogs.get(effective)
    if catalog and key in catalog:
        return catalog[key]

    # Fallback to default locale when the requested one is incomplete.
    if effective != DEFAULT_LOCALE:
        catalog = _catalogs.get(DEFAULT_LOCALE)
        if catalog and key in catalog:
            return catalog[key]

    raise KeyError(
        f"No template for {key!r} (locale={effective!r})"
    )
