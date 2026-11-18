# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Public facade for copilot scope loading and evidence gathering."""

from __future__ import annotations

from .scope_evidence import gather_evidence, serialize_evidence
from .scope_shared import (
    CopilotFocusVariant,
    CopilotRuntimeProfile,
    EntityLookupRef,
    EvidenceItem,
    MAX_CHAPTER_EXCERPT_CHARS,
    MAX_EVIDENCE_ITEMS,
    MAX_SCOPE_ENTITIES,
    MAX_SCOPE_RELATIONSHIPS,
    MAX_SCOPE_SYSTEMS,
    ScopeSnapshot,
    SystemLookupRef,
)
from .scope_snapshot import (
    derive_focus_variant,
    derive_runtime_profile,
    load_scope_snapshot,
)

__all__ = [
    "CopilotFocusVariant",
    "CopilotRuntimeProfile",
    "EntityLookupRef",
    "EvidenceItem",
    "MAX_CHAPTER_EXCERPT_CHARS",
    "MAX_EVIDENCE_ITEMS",
    "MAX_SCOPE_ENTITIES",
    "MAX_SCOPE_RELATIONSHIPS",
    "MAX_SCOPE_SYSTEMS",
    "ScopeSnapshot",
    "SystemLookupRef",
    "derive_focus_variant",
    "derive_runtime_profile",
    "gather_evidence",
    "load_scope_snapshot",
    "serialize_evidence",
]
