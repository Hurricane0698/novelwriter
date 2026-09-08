# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared copilot scope types, limits, and text helpers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields
from typing import Any, Literal

from app.core.copilot.messages import CopilotTextKey, get_copilot_text
from app.core.indexing import WindowIndexLifecycleSnapshot
from app.language_policy import get_language_policy

CopilotRuntimeProfile = Literal[
    "focused_research", "draft_governance", "broad_exploration"
]
CopilotFocusVariant = Literal["entity", "relationship", "draft", "whole_book"]

MAX_EVIDENCE_ITEMS = 15
MAX_SCOPE_ENTITIES = 80
MAX_SCOPE_RELATIONSHIPS = 60
MAX_SCOPE_SYSTEMS = 30
MAX_CHAPTER_EXCERPT_CHARS = 2000


@dataclass(frozen=True)
class EntityLookupRef:
    entity_id: int
    name: str
    status: str


@dataclass(frozen=True)
class SystemLookupRef:
    system_id: int
    name: str
    status: str


@dataclass(frozen=True)
class NovelScopeValue:
    id: int
    title: str
    author: str | None
    language: str | None
    window_index: bytes | None


@dataclass(frozen=True)
class EntityScopeValue:
    id: int
    name: str
    entity_type: str
    description: str | None
    aliases: list[str] | None
    status: str | None


@dataclass(frozen=True)
class AttributeScopeValue:
    id: int
    key: str
    surface: str
    visibility: str


@dataclass(frozen=True)
class RelationshipScopeValue:
    id: int
    source_id: int
    target_id: int
    label: str
    description: str | None
    visibility: str
    status: str | None


@dataclass(frozen=True)
class SystemScopeValue:
    id: int
    name: str
    display_type: str
    description: str | None
    constraints: list[Any] | None
    status: str | None


def _row_value(value_type, row):
    # Explicit DTO fields are the complete read contract. No ORM state or lazy
    # relationships leave the session; JSON values belong to this snapshot.
    if isinstance(row, value_type):
        return row
    return value_type(
        **{item.name: deepcopy(getattr(row, item.name)) for item in fields(value_type)}
    )


@dataclass(frozen=True)
class ScopeSnapshot:
    """Read-only world values, independent of the session used to load them.

    Collection shapes stay compatible with prompt and suggestion consumers.
    They are snapshot-owned; readers must not mutate them.
    """

    novel: NovelScopeValue
    novel_language: str
    entities: list[EntityScopeValue]
    entities_by_id: dict[int, EntityScopeValue]
    relationships: list[RelationshipScopeValue]
    systems: list[SystemScopeValue]
    attributes_by_entity: dict[int, list[AttributeScopeValue]]
    draft_entities: list[EntityScopeValue]
    draft_relationships: list[RelationshipScopeValue]
    draft_systems: list[SystemScopeValue]
    profile: str = "broad_exploration"
    focus_variant: str = "whole_book"
    focus_entity_id: int | None = None
    window_index_state: WindowIndexLifecycleSnapshot | None = None
    novel_entity_refs_by_name_key: dict[str, tuple[EntityLookupRef, ...]] = field(
        default_factory=dict
    )
    novel_system_refs_by_name_key: dict[str, tuple[SystemLookupRef, ...]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        # Keep direct ScopeSnapshot construction compatible while enforcing the
        # same value boundary as load_scope_snapshot, including in tests.
        values = {}

        def as_value(value_type, row):
            key = (value_type, id(row))
            if key not in values:
                values[key] = _row_value(value_type, row)
            return values[key]

        object.__setattr__(self, "novel", as_value(NovelScopeValue, self.novel))
        for name, value_type in (
            ("entities", EntityScopeValue),
            ("draft_entities", EntityScopeValue),
            ("relationships", RelationshipScopeValue),
            ("draft_relationships", RelationshipScopeValue),
            ("systems", SystemScopeValue),
            ("draft_systems", SystemScopeValue),
        ):
            object.__setattr__(
                self, name, [as_value(value_type, row) for row in getattr(self, name)]
            )
        object.__setattr__(
            self,
            "entities_by_id",
            {
                key: as_value(EntityScopeValue, value)
                for key, value in self.entities_by_id.items()
            },
        )
        object.__setattr__(
            self,
            "attributes_by_entity",
            {
                key: [as_value(AttributeScopeValue, value) for value in rows]
                for key, rows in self.attributes_by_entity.items()
            },
        )
        object.__setattr__(
            self,
            "novel_entity_refs_by_name_key",
            dict(self.novel_entity_refs_by_name_key),
        )
        object.__setattr__(
            self,
            "novel_system_refs_by_name_key",
            dict(self.novel_system_refs_by_name_key),
        )
        object.__setattr__(
            self, "window_index_state", deepcopy(self.window_index_state)
        )


@dataclass
class EvidenceItem:
    """A backend-sourced, verifiable evidence item."""

    evidence_id: str
    source_type: str
    source_ref: dict[str, Any]
    title: str
    excerpt: str
    why_relevant: str
    pack_id: str | None = None
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    anchor_terms: list[str] = field(default_factory=list)
    support_count: int | None = None
    preview_excerpt: str | None = None
    expanded: bool = False


def scope_text(
    interaction_locale: str,
    text_key: CopilotTextKey,
    **params: object,
) -> str:
    return get_copilot_text(text_key, locale=interaction_locale, **params)


def append_scope_labeled_line(
    text: str,
    *,
    interaction_locale: str,
    label_key: CopilotTextKey,
    value: str,
) -> str:
    label = scope_text(interaction_locale, label_key)
    return f"{text}\n{label}: {value}"


def normalize_lookup_key(value: str | None, *, language: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return get_language_policy(language, sample_text=text).normalize_for_matching(text)
