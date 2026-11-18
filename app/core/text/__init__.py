# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

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
from app.core.text.snippets import (  # noqa: F401  — public API
    SnippetKey,
    get_snippet,
    register_snippets,
)

# Auto-register locales on first import.
import app.core.text.zh  # noqa: F401
import app.core.text.en  # noqa: F401
import app.core.text.ja  # noqa: F401
import app.core.text.ko  # noqa: F401

__all__ = [
    "DEFAULT_LOCALE",
    "PromptKey",
    "SnippetKey",
    "get_prompt",
    "get_snippet",
    "register_snippets",
    "register_templates",
]
