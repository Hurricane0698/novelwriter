# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Text rendering helpers for continuation prompts and world context surfaces."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from app.core.text.snippets import SnippetKey, get_snippet


_TRAILING_CHAPTER_SEPARATOR_RE = re.compile(r"[:：]\s*】$")
def format_chapter_heading_for_prompt(
    chapter_number: int | str,
    title: str | None,
    *,
    locale: str | None = None,
    source_chapter_label: str | None = None,
) -> str:
    del source_chapter_label

    effective_title = str(title or "").strip()
    heading = get_snippet(SnippetKey.CHAPTER_HEADING_FMT, locale).format(
        n=chapter_number,
        title=effective_title,
    )
    if effective_title:
        return heading
    return _TRAILING_CHAPTER_SEPARATOR_RE.sub("】", heading)

def _format_generic_chapter_reference(number: int, *, locale: str | None = None) -> str:
    normalized_locale = (locale or "").lower()
    if normalized_locale.startswith("en"):
        return f"Chapter {number}"
    if normalized_locale.startswith("ko"):
        return f"제{number}장"
    return f"第{number}章"


def format_next_chapter_reference(
    internal_next_chapter: int,
    *,
    latest_source_chapter_label: str | None = None,
    latest_source_chapter_number: int | None = None,
    locale: str | None = None,
) -> str:
    del latest_source_chapter_label, latest_source_chapter_number
    return _format_generic_chapter_reference(internal_next_chapter, locale=locale)


def format_recent_chapters_for_prompt(
    recent_chapters: Sequence[Any],
    *,
    locale: str | None = None,
) -> str:
    return "\n\n".join(
        format_chapter_heading_for_prompt(
            getattr(ch, 'chapter_number', ''),
            getattr(ch, 'title', ''),
            locale=locale,
            source_chapter_label=getattr(ch, 'source_chapter_label', None),
        )
        + f"\n{getattr(ch, 'content', '')}"
        for ch in recent_chapters
    )


def append_user_instruction_for_relevance(
    text: str,
    user_prompt: str | None,
    *,
    locale: str | None = None,
) -> str:
    if user_prompt and user_prompt.strip():
        header = get_snippet(SnippetKey.USER_INSTRUCTION_HEADER, locale)
        return text + f"\n\n{header}\n" + user_prompt.strip()
    return text


def extract_narrative_constraints(writer_ctx: Mapping[str, Any]) -> str:
    """Extract constraints from the selected systems into a standalone prompt section."""

    systems = writer_ctx.get("systems") or []
    rules: list[str] = []
    for system in systems:
        if not isinstance(system, dict):
            continue
        constraints = system.get("constraints") or []
        if not isinstance(constraints, list):
            continue
        for rule in constraints:
            rule = str(rule or "").strip()
            if rule:
                rules.append(rule)

    if not rules:
        return ""

    numbered = "\n".join(f"{idx}. {rule}" for idx, rule in enumerate(rules, 1))
    return f"\n<narrative_constraints>\n{numbered}\n</narrative_constraints>\n"


def _render_hierarchy_data(data: Any, *, desc_sep: str = ": ") -> str:
    nodes = data.get("nodes") if isinstance(data, dict) else None
    if not isinstance(nodes, list) or not nodes:
        return ""

    lines: list[str] = []

    def _walk(node: Any, depth: int = 0) -> None:
        if not isinstance(node, dict):
            return
        label = str(node.get("label") or node.get("name") or "").strip()
        if not label:
            return
        desc = str(node.get("description") or "").strip()
        indent = "  " * depth
        line = f"{indent}\u00b7 {label}"
        if desc:
            line += f"{desc_sep}{desc}"
        lines.append(line)
        for child in node.get("children") or []:
            _walk(child, depth + 1)

    for node in nodes:
        _walk(node)
    return "\n".join(lines)


def _render_timeline_data(data: Any, *, desc_sep: str = ": ") -> str:
    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list) or not events:
        return ""

    lines: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        label = str(event.get("label") or "").strip()
        date = str(event.get("time") or event.get("date") or "").strip()
        desc = str(event.get("description") or "").strip()
        if not label:
            continue
        line = "\u00b7 "
        line += f"{date}\uff0c{label}" if date else label
        if desc:
            line += f"{desc_sep}{desc}"
        lines.append(line)
    return "\n".join(lines)


def _render_list_data(data: Any, *, desc_sep: str = ": ") -> str:
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        return ""

    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("name") or "").strip()
        desc = str(item.get("description") or "").strip()
        if not label:
            continue
        line = f"\u00b7 {label}"
        if desc:
            line += f"{desc_sep}{desc}"
        lines.append(line)
    return "\n".join(lines)


_SYSTEM_DATA_RENDERERS = {
    "hierarchy": _render_hierarchy_data,
    "timeline": _render_timeline_data,
    "list": _render_list_data,
}


def _render_system_data(display_type: str, data: Any, *, desc_sep: str = ": ") -> str:
    renderer = _SYSTEM_DATA_RENDERERS.get(display_type)
    if renderer and data:
        return renderer(data, desc_sep=desc_sep)
    if data:
        try:
            return json.dumps(data, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(data)
    return ""


def format_world_context_for_prompt(
    writer_ctx: Mapping[str, Any],
    *,
    locale: str | None = None,
    entity_names: Mapping[int, str] | None = None,
) -> str:
    """Render assemble_writer_context() output into an LLM-friendly text block."""

    systems = writer_ctx.get("systems") or []
    entities = writer_ctx.get("entities") or []
    relationships = writer_ctx.get("relationships") or []

    desc_sep = get_snippet(SnippetKey.DESC_SEPARATOR, locale)
    alias_sep = get_snippet(SnippetKey.ALIAS_SEPARATOR, locale)

    id_to_name = {int(e["id"]): e["name"] for e in entities} if entity_names is None else entity_names
    lines: list[str] = []

    if systems:
        lines.append(get_snippet(SnippetKey.SECTION_SYSTEMS, locale))
        unnamed_system = get_snippet(SnippetKey.UNNAMED_SYSTEM, locale)
        for system in systems:
            name = str(system.get("name") or "").strip()
            desc = str(system.get("description") or "").strip()
            display_type = str(system.get("display_type") or "").strip()
            header = f"- {name}" if name else f"- {unnamed_system}"
            if desc:
                header += f"{desc_sep}{desc}"
            lines.append(header)

            rendered = _render_system_data(display_type, system.get("data"), desc_sep=desc_sep)
            if rendered:
                for line in rendered.split("\n"):
                    lines.append(f"  {line}")

    if entities:
        lines.append(get_snippet(SnippetKey.SECTION_ENTITIES, locale))
        unnamed_entity = get_snippet(SnippetKey.UNNAMED_ENTITY, locale)
        aliases_label = get_snippet(SnippetKey.ALIASES_LABEL, locale)
        for entity in entities:
            name = str(entity.get("name") or "").strip()
            entity_type = str(entity.get("entity_type") or "").strip()
            desc = str(entity.get("description") or "").strip()
            header = f"- {name}" if name else f"- {unnamed_entity}"
            if entity_type:
                header += f"({entity_type})"
            if desc:
                header += f"{desc_sep}{desc}"
            lines.append(header)

            aliases = entity.get("aliases") or []
            if isinstance(aliases, list):
                normalized = []
                for alias in aliases:
                    alias = str(alias or "").strip()
                    if not alias or (name and alias == name):
                        continue
                    normalized.append(alias)
                if normalized:
                    lines.append(f"  {aliases_label}{alias_sep.join(normalized)}")

            attrs = entity.get("attributes") or []
            if isinstance(attrs, list) and attrs:
                for attr in attrs:
                    key = str(attr.get("key") or "").strip()
                    surface = str(attr.get("surface") or "").strip()
                    if key and surface:
                        lines.append(f"  - {key}{desc_sep}{surface}")
                    elif key:
                        lines.append(f"  - {key}")

    if relationships:
        lines.append(get_snippet(SnippetKey.SECTION_RELATIONSHIPS, locale))
        for relationship in relationships:
            label = str(relationship.get("label") or "").strip()
            desc = str(relationship.get("description") or "").strip()
            src_id = relationship.get("source_id")
            tgt_id = relationship.get("target_id")
            src = id_to_name.get(int(src_id), str(src_id)) if src_id is not None else "?"
            tgt = id_to_name.get(int(tgt_id), str(tgt_id)) if tgt_id is not None else "?"
            line = f"- {src}"
            line += f" \u2014{label}\u2192 {tgt}" if label else f" \u2192 {tgt}"
            if desc:
                line += f"{desc_sep}{desc}"
            lines.append(line)

    return "\n".join(lines).strip()
