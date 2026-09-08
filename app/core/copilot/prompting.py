# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Prompt construction helpers for copilot."""

from __future__ import annotations

from typing import Any

from app.core.copilot.prompt_intent import (
    apply_quick_action_prompt,
    classify_turn_intent,
    should_preload_world_context,
)
from app.core.copilot.prompt_contract import (
    PromptBuild,
    PromptSection,
    assemble_prompt_build,
)
from app.core.copilot.prompt_registry import (
    _SURFACE_LABELS,
    prompt_block as _prompt_block,
    prompt_map as _prompt_map,
    prompt_text as _prompt_text,
)
from app.core.copilot.scope import EvidenceItem, ScopeSnapshot
from app.models import WorldEntity, WorldRelationship, WorldSystem

__all__ = [
    "apply_quick_action_prompt",
    "build_auto_preload",
    "build_copilot_system_prompt_build",
    "build_copilot_system_prompt",
    "build_tool_loop_system_prompt_build",
    "build_tool_loop_system_prompt",
    "classify_turn_intent",
    "should_preload_world_context",
]


def _resolve_focus_label(
    snapshot: ScopeSnapshot, session_data: dict[str, Any]
) -> str | None:
    display_title = str(session_data.get("display_title", "") or "").strip()
    if display_title:
        return display_title

    context = session_data.get("context_json") or {}
    entity_id = context.get("entity_id")
    if entity_id is not None:
        entity = snapshot.entities_by_id.get(entity_id)
        if entity:
            return entity.name
    return None


def _build_workbench_context_text(
    snapshot: ScopeSnapshot,
    scenario: str,
    session_data: dict[str, Any],
    interaction_locale: str = "zh",
) -> str:
    context = session_data.get("context_json") or {}
    surface_label = _SURFACE_LABELS.get(
        str(context.get("surface") or "").lower(), "Novel Copilot"
    )
    if str(context.get("surface") or "").lower() == "atlas":
        stage_key = str(context.get("tab") or "").lower()
    else:
        stage_key = str(context.get("stage") or context.get("tab") or "").lower()
    try:
        stage_label = _prompt_map(interaction_locale, "stage_labels", stage_key)
    except KeyError:
        stage_label = _prompt_text(interaction_locale, "current_workspace")
    focus_label = _resolve_focus_label(snapshot, session_data)

    lines = [
        _prompt_text(
            interaction_locale, "surface_line", surface=surface_label, stage=stage_label
        ),
        _prompt_text(
            interaction_locale,
            "profile_line",
            profile=_prompt_map(
                interaction_locale,
                "profile_labels",
                snapshot.profile,
                fallback_key=snapshot.profile,
            ),
        ),
        _prompt_text(
            interaction_locale,
            "scenario_line",
            scenario=_prompt_map(
                interaction_locale,
                "focus_labels",
                snapshot.focus_variant or scenario,
                fallback_key=scenario,
            ),
        ),
    ]
    if focus_label:
        lines.append(_prompt_text(interaction_locale, "focus_line", focus=focus_label))
    focus_entity_id = (
        snapshot.focus_entity_id
        if isinstance(snapshot.focus_entity_id, int)
        else context.get("entity_id")
    )
    if isinstance(focus_entity_id, int):
        lines.append(
            _prompt_text(
                interaction_locale, "focus_entity_id_line", entity_id=focus_entity_id
            )
        )

    capabilities = _prompt_map(
        interaction_locale,
        "focus_capabilities",
        snapshot.focus_variant or "whole_book",
        fallback_key="whole_book",
    )
    lines.append(_prompt_text(interaction_locale, "capabilities_header"))
    lines.extend(f"  {idx}. {item}" for idx, item in enumerate(capabilities, start=1))
    return "\n".join(lines)


def _build_intent_behavior_text(
    turn_intent: str, interaction_locale: str = "zh"
) -> str:
    if turn_intent == "smalltalk":
        return _prompt_text(interaction_locale, "intent_smalltalk")
    if turn_intent == "capability_query":
        return _prompt_text(interaction_locale, "intent_capability_query")
    return _prompt_text(interaction_locale, "intent_task_query")


def _build_runtime_instruction_text(
    snapshot: ScopeSnapshot,
    scenario: str,
    interaction_locale: str = "zh",
) -> str:
    profile_instr = _prompt_map(
        interaction_locale,
        "profile_instructions",
        snapshot.profile,
        fallback_key=snapshot.profile,
    )
    focus_key = snapshot.focus_variant or scenario
    focus_instr = _prompt_map(
        interaction_locale,
        "focus_instructions",
        focus_key,
        fallback_key="entity",
    )
    return f"{profile_instr}\n{focus_instr}".strip()


def _make_prompt_section(
    *,
    section_id: str,
    interaction_locale: str,
    heading_key: str | None,
    body: str,
    content_kind: str,
    depends_on: tuple[str, ...],
) -> PromptSection:
    return PromptSection(
        section_id=section_id,
        heading=(
            _prompt_block(interaction_locale, heading_key) if heading_key else None
        ),
        body=body,
        content_kind=content_kind,  # type: ignore[arg-type]
        depends_on=depends_on,
    )


def _build_prompt_metadata(
    *,
    snapshot: ScopeSnapshot,
    scenario: str,
    turn_intent: str,
    prompt_variant: str,
    preload_world_context: bool,
) -> dict[str, Any]:
    return {
        "prompt_variant": prompt_variant,
        "snapshot_profile": snapshot.profile,
        "focus_variant": snapshot.focus_variant or scenario,
        "scenario": scenario,
        "turn_intent": turn_intent,
        "preload_world_context": preload_world_context,
    }


def _build_language_rules_text(
    snapshot: ScopeSnapshot,
    interaction_locale: str,
) -> str:
    novel_lang = snapshot.novel_language
    if interaction_locale and interaction_locale != novel_lang:
        locale_instr = _prompt_text(
            interaction_locale,
            "language_interaction_rule",
            interaction_locale=interaction_locale,
            novel_lang=novel_lang,
        )
    else:
        locale_instr = _prompt_text(
            interaction_locale, "language_novel_rule", novel_lang=novel_lang
        )
    return "\n".join(
        [
            locale_instr,
            _prompt_block(interaction_locale, "canonical_names_rule"),
        ]
    )


def _build_common_prompt_sections(
    *,
    snapshot: ScopeSnapshot,
    scenario: str,
    interaction_locale: str,
    session_data: dict[str, Any],
    turn_intent: str,
) -> list[PromptSection]:
    return [
        _make_prompt_section(
            section_id="current_task",
            interaction_locale=interaction_locale,
            heading_key="heading_current_task",
            body=_build_runtime_instruction_text(
                snapshot,
                scenario,
                interaction_locale,
            ),
            content_kind="dynamic",
            depends_on=("snapshot.profile", "snapshot.focus_variant", "scenario"),
        ),
        _make_prompt_section(
            section_id="workbench_context",
            interaction_locale=interaction_locale,
            heading_key="heading_workbench_context",
            body=_build_workbench_context_text(
                snapshot,
                scenario,
                session_data,
                interaction_locale,
            ),
            content_kind="dynamic",
            depends_on=(
                "session.context_json",
                "session.display_title",
                "snapshot.focus_entity_id",
            ),
        ),
        _make_prompt_section(
            section_id="turn_behavior",
            interaction_locale=interaction_locale,
            heading_key="heading_turn_behavior",
            body=_build_intent_behavior_text(turn_intent, interaction_locale),
            content_kind="dynamic",
            depends_on=("turn_intent",),
        ),
        _make_prompt_section(
            section_id="language_rules",
            interaction_locale=interaction_locale,
            heading_key="heading_language_rules",
            body=_build_language_rules_text(snapshot, interaction_locale),
            content_kind="dynamic",
            depends_on=("snapshot.novel_language", "interaction_locale"),
        ),
    ]


def build_copilot_system_prompt_build(
    snapshot: ScopeSnapshot,
    evidence: list[EvidenceItem],
    scenario: str,
    interaction_locale: str,
    session_data: dict[str, Any],
    turn_intent: str,
) -> PromptBuild:
    sections = [
        _make_prompt_section(
            section_id="assistant_identity",
            interaction_locale=interaction_locale,
            heading_key=None,
            body=_prompt_block(interaction_locale, "assistant_intro_workbench"),
            content_kind="static",
            depends_on=(),
        ),
        *_build_common_prompt_sections(
            snapshot=snapshot,
            scenario=scenario,
            interaction_locale=interaction_locale,
            session_data=session_data,
            turn_intent=turn_intent,
        ),
    ]

    if not should_preload_world_context(turn_intent):
        sections.extend(
            [
                _make_prompt_section(
                    section_id="output_contract",
                    interaction_locale=interaction_locale,
                    heading_key="heading_output_format",
                    body=_prompt_block(interaction_locale, "workbench_output_contract"),
                    content_kind="static",
                    depends_on=(),
                ),
                _make_prompt_section(
                    section_id="response_rules",
                    interaction_locale=interaction_locale,
                    heading_key="heading_rules",
                    body=_prompt_block(interaction_locale, "workbench_rules"),
                    content_kind="static",
                    depends_on=(),
                ),
            ]
        )
        return assemble_prompt_build(
            prompt_id="workbench_assistant",
            locale=interaction_locale,
            sections=sections,
            metadata=_build_prompt_metadata(
                snapshot=snapshot,
                scenario=scenario,
                turn_intent=turn_intent,
                prompt_variant="workbench_assistant",
                preload_world_context=False,
            ),
        )

    sections[0] = _make_prompt_section(
        section_id="assistant_identity",
        interaction_locale=interaction_locale,
        heading_key=None,
        body=_prompt_block(interaction_locale, "assistant_intro_research"),
        content_kind="static",
        depends_on=(),
    )
    world_model_text = _build_world_model_prompt_block(snapshot, interaction_locale)
    evidence_text = _format_evidence_for_prompt(evidence) or _prompt_text(
        interaction_locale, "no_evidence"
    )
    sections.extend(
        [
            _make_prompt_section(
                section_id="world_model",
                interaction_locale=interaction_locale,
                heading_key="heading_world_model",
                body=world_model_text,
                content_kind="dynamic",
                depends_on=(
                    "snapshot.profile",
                    "snapshot.entities",
                    "snapshot.relationships",
                    "snapshot.systems",
                ),
            ),
            _make_prompt_section(
                section_id="backend_evidence",
                interaction_locale=interaction_locale,
                heading_key="heading_backend_evidence",
                body="\n".join(
                    [
                        _prompt_block(interaction_locale, "backend_evidence_intro"),
                        evidence_text,
                    ]
                ),
                content_kind="dynamic",
                depends_on=("evidence",),
            ),
            _make_prompt_section(
                section_id="output_contract",
                interaction_locale=interaction_locale,
                heading_key="heading_output_format",
                body=_prompt_block(interaction_locale, "research_output_contract"),
                content_kind="static",
                depends_on=(),
            ),
            _make_prompt_section(
                section_id="response_rules",
                interaction_locale=interaction_locale,
                heading_key="heading_rules",
                body=_prompt_block(interaction_locale, "research_rules"),
                content_kind="static",
                depends_on=(),
            ),
        ]
    )
    return assemble_prompt_build(
        prompt_id="research_assistant",
        locale=interaction_locale,
        sections=sections,
        metadata=_build_prompt_metadata(
            snapshot=snapshot,
            scenario=scenario,
            turn_intent=turn_intent,
            prompt_variant="research_assistant",
            preload_world_context=True,
        ),
    )


def _format_entity_rows_for_prompt(
    entities: list[WorldEntity],
    snapshot: ScopeSnapshot,
    interaction_locale: str = "zh",
) -> str:
    lines: list[str] = []
    for entity in entities:
        draft_tag = (
            _prompt_text(interaction_locale, "entity_draft_tag")
            if entity.status == "draft"
            else ""
        )
        parts = [
            f"[Entity#{entity.id}]{draft_tag} {entity.name} ({entity.entity_type})"
        ]
        if entity.description:
            parts.append(
                _prompt_text(
                    interaction_locale,
                    "entity_description_line",
                    text=entity.description[:300],
                )
            )
        if entity.aliases:
            parts.append(
                _prompt_text(
                    interaction_locale,
                    "entity_aliases_line",
                    aliases=", ".join(entity.aliases[:5]),
                )
            )
        attrs = snapshot.attributes_by_entity.get(entity.id, [])
        for attr in attrs[:8]:
            vis = f" [{attr.visibility}]" if attr.visibility != "active" else ""
            parts.append(
                _prompt_text(
                    interaction_locale,
                    "entity_attribute_line",
                    attribute_key=attr.key,
                    surface=attr.surface[:200],
                    visibility=vis,
                )
            )
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _format_entities_for_prompt(
    snapshot: ScopeSnapshot, interaction_locale: str = "zh"
) -> str:
    return _format_entity_rows_for_prompt(
        snapshot.entities, snapshot, interaction_locale
    )


def _format_relationship_rows_for_prompt(
    relationships: list[WorldRelationship],
    snapshot: ScopeSnapshot,
    interaction_locale: str = "zh",
) -> str:
    lines: list[str] = []
    for relationship in relationships:
        src = snapshot.entities_by_id.get(relationship.source_id)
        tgt = snapshot.entities_by_id.get(relationship.target_id)
        src_name = src.name if src else f"Entity#{relationship.source_id}"
        tgt_name = tgt.name if tgt else f"Entity#{relationship.target_id}"
        draft_tag = (
            _prompt_text(interaction_locale, "relationship_draft_tag")
            if relationship.status == "draft"
            else ""
        )
        desc = (
            f" — {relationship.description[:200]}" if relationship.description else ""
        )
        lines.append(
            f"[Rel#{relationship.id}]{draft_tag} {src_name} --[{relationship.label}]--> {tgt_name}{desc}"
        )
    return "\n".join(lines)


def _format_relationships_for_prompt(
    snapshot: ScopeSnapshot, interaction_locale: str = "zh"
) -> str:
    return _format_relationship_rows_for_prompt(
        snapshot.relationships, snapshot, interaction_locale
    )


def _format_system_rows_for_prompt(
    systems: list[WorldSystem],
    interaction_locale: str = "zh",
) -> str:
    lines: list[str] = []
    for system in systems:
        draft_tag = (
            _prompt_text(interaction_locale, "system_draft_tag")
            if system.status == "draft"
            else ""
        )
        parts = [
            f"[System#{system.id}]{draft_tag} {system.name} ({system.display_type})"
        ]
        if system.description:
            parts.append(
                _prompt_text(
                    interaction_locale,
                    "system_description_line",
                    text=system.description[:300],
                )
            )
        if system.constraints:
            parts.append(
                _prompt_text(
                    interaction_locale,
                    "system_constraints_line",
                    constraints="; ".join(
                        str(constraint)[:100] for constraint in system.constraints[:5]
                    ),
                )
            )
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _format_systems_for_prompt(
    snapshot: ScopeSnapshot, interaction_locale: str = "zh"
) -> str:
    return _format_system_rows_for_prompt(snapshot.systems, interaction_locale)


def _format_evidence_for_prompt(evidence: list[EvidenceItem]) -> str:
    parts: list[str] = []
    for index, item in enumerate(evidence):
        parts.append(
            f"[Evidence#{index}] ({item.source_type}) {item.title}\n{item.excerpt}"
        )
    return "\n\n---\n\n".join(parts)


def _build_broad_exploration_world_overview(
    snapshot: ScopeSnapshot,
    interaction_locale: str = "zh",
) -> str:
    name_separator = _prompt_text(interaction_locale, "name_separator")
    entity_samples = name_separator.join(
        entity.name for entity in snapshot.entities[:6]
    ) or _prompt_text(interaction_locale, "none_entities")
    relationship_samples = []
    for relationship in snapshot.relationships[:4]:
        src = snapshot.entities_by_id.get(relationship.source_id)
        tgt = snapshot.entities_by_id.get(relationship.target_id)
        relationship_samples.append(
            f"{src.name if src else '?'} --[{relationship.label}]--> {tgt.name if tgt else '?'}"
        )
    system_samples = (
        name_separator.join(system.name for system in snapshot.systems[:4])
        if snapshot.systems
        else _prompt_text(interaction_locale, "none_systems")
    )
    draft_count = (
        len(snapshot.draft_entities)
        + len(snapshot.draft_relationships)
        + len(snapshot.draft_systems)
    )

    parts = [
        _prompt_text(
            interaction_locale,
            "broad_loaded",
            entity_count=len(snapshot.entities),
            relationship_count=len(snapshot.relationships),
            system_count=len(snapshot.systems),
        ),
        _prompt_text(
            interaction_locale, "broad_entity_samples", samples=entity_samples
        ),
    ]
    if relationship_samples:
        parts.append(
            _prompt_text(
                interaction_locale,
                "broad_relationship_samples",
                samples="; ".join(relationship_samples),
            )
        )
    if snapshot.systems:
        parts.append(
            _prompt_text(
                interaction_locale, "broad_system_samples", samples=system_samples
            )
        )
    if draft_count:
        parts.append(
            _prompt_text(
                interaction_locale,
                "broad_draft_counts",
                entity_count=len(snapshot.draft_entities),
                relationship_count=len(snapshot.draft_relationships),
                system_count=len(snapshot.draft_systems),
            )
        )
    parts.append(_prompt_text(interaction_locale, "broad_on_demand_hint"))
    return "\n".join(parts)


def _build_draft_governance_world_context(
    snapshot: ScopeSnapshot,
    interaction_locale: str = "zh",
) -> str:
    supporting_entities = [
        entity for entity in snapshot.entities if entity.status != "draft"
    ]
    parts = [
        _prompt_text(interaction_locale, "draft_workset_intro"),
        _prompt_text(
            interaction_locale,
            "draft_counts",
            entity_count=len(snapshot.draft_entities),
            relationship_count=len(snapshot.draft_relationships),
            system_count=len(snapshot.draft_systems),
        ),
    ]
    if snapshot.draft_entities:
        parts.append(
            _prompt_text(interaction_locale, "section_draft_entities")
            + (
                _format_entity_rows_for_prompt(
                    snapshot.draft_entities, snapshot, interaction_locale
                )
                or _prompt_text(interaction_locale, "none_generic")
            )
        )
    if snapshot.draft_relationships:
        parts.append(
            _prompt_text(interaction_locale, "section_draft_relationships")
            + (
                _format_relationship_rows_for_prompt(
                    snapshot.draft_relationships, snapshot, interaction_locale
                )
                or _prompt_text(interaction_locale, "none_generic")
            )
        )
    if snapshot.draft_systems:
        parts.append(
            _prompt_text(interaction_locale, "section_draft_systems")
            + (
                _format_system_rows_for_prompt(
                    snapshot.draft_systems, interaction_locale
                )
                or _prompt_text(interaction_locale, "none_generic")
            )
        )
    if supporting_entities:
        lines = [
            f"- {entity.name} ({entity.entity_type})"
            for entity in supporting_entities[:8]
        ]
        parts.append(
            _prompt_text(interaction_locale, "section_related_confirmed_entities")
            + "\n".join(lines)
        )
    return "\n\n".join(parts)


def _build_world_model_prompt_block(
    snapshot: ScopeSnapshot, interaction_locale: str = "zh"
) -> str:
    if snapshot.profile == "broad_exploration":
        return _build_broad_exploration_world_overview(snapshot, interaction_locale)
    if snapshot.profile == "draft_governance":
        return _build_draft_governance_world_context(snapshot, interaction_locale)

    entities_text = _format_entities_for_prompt(
        snapshot, interaction_locale
    ) or _prompt_text(interaction_locale, "none_entities")
    relationships_text = _format_relationships_for_prompt(
        snapshot, interaction_locale
    ) or _prompt_text(interaction_locale, "none_relationships")
    parts = [
        _prompt_text(interaction_locale, "section_entities"),
        entities_text,
        "",
        _prompt_text(interaction_locale, "section_relationships"),
        relationships_text,
    ]
    if snapshot.systems:
        parts.extend(
            [
                "",
                _prompt_text(interaction_locale, "section_systems"),
                _format_systems_for_prompt(snapshot, interaction_locale)
                or _prompt_text(interaction_locale, "none_systems"),
            ]
        )
    return "\n".join(parts)


def build_copilot_system_prompt(
    snapshot: ScopeSnapshot,
    evidence: list[EvidenceItem],
    scenario: str,
    interaction_locale: str,
    session_data: dict[str, Any],
    turn_intent: str,
) -> str:
    return build_copilot_system_prompt_build(
        snapshot,
        evidence,
        scenario,
        interaction_locale,
        session_data,
        turn_intent,
    ).prompt_text


def build_auto_preload(snapshot: ScopeSnapshot, interaction_locale: str = "zh") -> str:
    """Build a minimal snapshot summary for the first message."""
    if snapshot.profile == "focused_research":
        focus_entity = snapshot.entities_by_id.get(snapshot.focus_entity_id or -1)
        entity_names = [
            f"{entity.name}({entity.entity_type})"
            + (
                _prompt_text(interaction_locale, "entity_draft_tag")
                if entity.status == "draft"
                else ""
            )
            for entity in snapshot.entities[:12]
        ]
        relationship_lines: list[str] = []
        for relationship in snapshot.relationships[:12]:
            src = snapshot.entities_by_id.get(relationship.source_id)
            tgt = snapshot.entities_by_id.get(relationship.target_id)
            relationship_lines.append(
                f"  [Rel#{relationship.id}] {src.name if src else '?'} --[{relationship.label}]--> {tgt.name if tgt else '?'}"
            )

        parts = [
            _prompt_text(
                interaction_locale,
                "focused_context_loaded",
                entity_count=len(snapshot.entities),
                relationship_count=len(snapshot.relationships),
                system_count=len(snapshot.systems),
            ),
        ]
        if focus_entity:
            parts.append(
                _prompt_text(
                    interaction_locale,
                    "focused_current_entity",
                    entity_id=focus_entity.id,
                    entity_name=focus_entity.name,
                    entity_type=focus_entity.entity_type,
                )
            )
            attrs = snapshot.attributes_by_entity.get(focus_entity.id, [])
            if attrs:
                parts.append(
                    _prompt_text(interaction_locale, "focus_attributes_label")
                    + "; ".join(f"{attr.key}={attr.surface[:80]}" for attr in attrs[:6])
                )
        if entity_names:
            parts.append(
                _prompt_text(
                    interaction_locale,
                    "loaded_entities",
                    entities=", ".join(entity_names),
                )
            )
        if relationship_lines:
            parts.append(
                _prompt_text(interaction_locale, "direct_relationships_label")
                + "\n".join(relationship_lines)
            )
        parts.append(_prompt_text(interaction_locale, "focused_expand_hint"))
        return "\n".join(parts)

    if snapshot.profile == "draft_governance":
        parts = [
            _prompt_text(
                interaction_locale,
                "draft_governance_loaded",
                entity_count=len(snapshot.draft_entities),
                relationship_count=len(snapshot.draft_relationships),
                system_count=len(snapshot.draft_systems),
            ),
        ]
        if snapshot.draft_entities:
            draft_lines = []
            for entity in snapshot.draft_entities[:12]:
                desc = (entity.description or "").strip()
                desc_note = (
                    f" — {desc[:80]}"
                    if desc
                    else _prompt_text(interaction_locale, "draft_no_description_suffix")
                )
                draft_lines.append(
                    f"  [Entity#{entity.id}] {entity.name} ({entity.entity_type}){desc_note}"
                )
            parts.append(
                _prompt_text(interaction_locale, "section_draft_entities")
                + "\n".join(draft_lines)
            )
        if snapshot.draft_relationships:
            draft_relationships = []
            for relationship in snapshot.draft_relationships[:10]:
                src = snapshot.entities_by_id.get(relationship.source_id)
                tgt = snapshot.entities_by_id.get(relationship.target_id)
                draft_relationships.append(
                    f"  [Rel#{relationship.id}] {src.name if src else '?'} --[{relationship.label}]--> {tgt.name if tgt else '?'}"
                )
            parts.append(
                _prompt_text(interaction_locale, "section_draft_relationships")
                + "\n".join(draft_relationships)
            )
        if snapshot.draft_systems:
            draft_systems = [
                f"  [System#{system.id}] {system.name}"
                for system in snapshot.draft_systems[:10]
            ]
            parts.append(
                _prompt_text(interaction_locale, "section_draft_systems")
                + "\n".join(draft_systems)
            )
        parts.append(_prompt_text(interaction_locale, "draft_confirmed_rows_hint"))
        return "\n".join(parts)

    entity_names = [
        f"{entity.name}({entity.entity_type})"
        + (
            _prompt_text(interaction_locale, "entity_draft_tag")
            if entity.status == "draft"
            else ""
        )
        for entity in snapshot.entities[:30]
    ]
    relationship_summaries = []
    for relationship in snapshot.relationships[:15]:
        src = snapshot.entities_by_id.get(relationship.source_id)
        tgt = snapshot.entities_by_id.get(relationship.target_id)
        relationship_summaries.append(
            f"{src.name if src else '?'} --[{relationship.label}]--> {tgt.name if tgt else '?'}"
        )
    system_names = [system.name for system in snapshot.systems]
    draft_count = (
        len(snapshot.draft_entities)
        + len(snapshot.draft_relationships)
        + len(snapshot.draft_systems)
    )
    parts = [
        _prompt_text(
            interaction_locale,
            "whole_book_overview_loaded",
            entity_count=len(snapshot.entities),
            relationship_count=len(snapshot.relationships),
            system_count=len(snapshot.systems),
            draft_count=draft_count,
        ),
    ]
    if entity_names:
        parts.append(
            _prompt_text(
                interaction_locale,
                "whole_book_entity_examples",
                samples=", ".join(entity_names[:12]),
            )
        )
    if relationship_summaries:
        parts.append(
            _prompt_text(
                interaction_locale,
                "whole_book_relationship_examples",
                samples="; ".join(relationship_summaries[:8]),
            )
        )
    if system_names:
        parts.append(
            _prompt_text(
                interaction_locale,
                "whole_book_system_examples",
                samples=", ".join(system_names[:8]),
            )
        )
    if draft_count:
        parts.append(_prompt_text(interaction_locale, "whole_book_draft_detail_hint"))
    parts.append(_prompt_text(interaction_locale, "whole_book_thin_hint"))
    return "\n".join(parts)


def build_tool_loop_system_prompt_build(
    snapshot: ScopeSnapshot,
    scenario: str,
    interaction_locale: str,
    session_data: dict[str, Any],
    turn_intent: str,
) -> PromptBuild:
    """Build the explicit system-prompt assembly for the tool-loop agent."""
    if should_preload_world_context(turn_intent):
        workflow_hint = _prompt_map(
            interaction_locale,
            "focus_workflow_hints",
            snapshot.focus_variant or "entity",
            fallback_key="entity",
        )
    else:
        workflow_hint = _prompt_text(interaction_locale, "workflow_hint_light")
    sections = [
        _make_prompt_section(
            section_id="assistant_identity",
            interaction_locale=interaction_locale,
            heading_key=None,
            body=_prompt_block(interaction_locale, "assistant_intro_tool_loop"),
            content_kind="static",
            depends_on=(),
        ),
        *_build_common_prompt_sections(
            snapshot=snapshot,
            scenario=scenario,
            interaction_locale=interaction_locale,
            session_data=session_data,
            turn_intent=turn_intent,
        ),
        _make_prompt_section(
            section_id="tools",
            interaction_locale=interaction_locale,
            heading_key="heading_tools",
            body=_prompt_block(interaction_locale, "tools_body"),
            content_kind="static",
            depends_on=(),
        ),
        _make_prompt_section(
            section_id="suggested_workflow",
            interaction_locale=interaction_locale,
            heading_key="heading_suggested_workflow",
            body=workflow_hint,
            content_kind="dynamic",
            depends_on=("turn_intent", "snapshot.focus_variant"),
        ),
        _make_prompt_section(
            section_id="output_contract",
            interaction_locale=interaction_locale,
            heading_key="heading_final_answer_format",
            body=_prompt_block(interaction_locale, "tool_loop_output_contract"),
            content_kind="static",
            depends_on=(),
        ),
        _make_prompt_section(
            section_id="response_rules",
            interaction_locale=interaction_locale,
            heading_key="heading_rules",
            body=_prompt_block(interaction_locale, "tool_loop_rules"),
            content_kind="static",
            depends_on=(),
        ),
    ]
    return assemble_prompt_build(
        prompt_id="tool_loop",
        locale=interaction_locale,
        sections=sections,
        metadata=_build_prompt_metadata(
            snapshot=snapshot,
            scenario=scenario,
            turn_intent=turn_intent,
            prompt_variant="tool_loop",
            preload_world_context=should_preload_world_context(turn_intent),
        ),
    )


def build_tool_loop_system_prompt(
    snapshot: ScopeSnapshot,
    scenario: str,
    interaction_locale: str,
    session_data: dict[str, Any],
    turn_intent: str,
) -> str:
    return build_tool_loop_system_prompt_build(
        snapshot,
        scenario,
        interaction_locale,
        session_data,
        turn_intent,
    ).prompt_text
