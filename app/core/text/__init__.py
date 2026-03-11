# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Prompt template selection layer.

Provides locale/provider-aware prompt template lookup.
Currently only ``zh`` locale is populated.

Adding a new locale or provider variant:
1. Create a module in ``app/core/text/`` (e.g. ``en.py``).
2. Call ``register_templates("en", {PromptKey.SYSTEM: "...", ...})``.
3. Pass ``locale="en"`` to ``get_prompt()`` at the call site.
"""

from app.core.text.catalog import (  # noqa: F401  — public API
    DEFAULT_LOCALE,
    PromptKey,
    get_prompt,
    register_templates,
)

# Auto-register the default Chinese locale on first import.
import app.core.text.zh  # noqa: F401

__all__ = [
    "DEFAULT_LOCALE",
    "PromptKey",
    "get_prompt",
    "register_templates",
]
