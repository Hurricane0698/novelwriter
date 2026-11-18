# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Scenario derivation helpers for the copilot runtime facade."""

from __future__ import annotations

from app.core.copilot.scope import derive_focus_variant


def derive_scenario(mode: str, scope: str, context: dict | None) -> str:
    """Derive the detailed research scenario from mode/scope/context."""
    focus_variant = derive_focus_variant(mode, scope, context)
    if focus_variant == "draft":
        return "draft_cleanup"
    if focus_variant == "whole_book":
        return "whole_book"
    if focus_variant == "relationship":
        return "relationships"
    return "current_entity"
