# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Text rendering helpers for continuation prompts and world context surfaces."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence


def format_recent_chapters_for_prompt(recent_chapters: Sequence[Any]) -> str:
    return "\n\n".join(
        f"【Chapter {getattr(ch, 'chapter_number', '')}: {getattr(ch, 'title', '')}】\n"
        f"{getattr(ch, 'content', '')}"
        for ch in recent_chapters
    )


def append_user_instruction_for_relevance(text: str, user_prompt: str | None) -> str:
    if user_prompt and user_prompt.strip():
        return text + "\n\n【用户续写指令】\n" + user_prompt.strip()
    return text


def extract_narrative_constraints(writer_ctx: Mapping[str, Any]) -> str:
    """Extract constraints from active systems into a standalone prompt section."""

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


def _render_hierarchy_data(data: Any) -> str:
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
        line = f"{indent}· {label}"
        if desc:
            line += f"：{desc}"
        lines.append(line)
        for child in node.get("children") or []:
            _walk(child, depth + 1)

    for node in nodes:
        _walk(node)
    return "\n".join(lines)


def _render_graph_data(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    if not isinstance(nodes, list) and not isinstance(edges, list):
        return ""

    lines: list[str] = []
    node_map: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        label = str(node.get("label") or node.get("name") or node_id).strip()
        node_map[node_id] = label
        desc = str(node.get("description") or "").strip()
        line = f"· {label}"
        if desc:
            line += f"：{desc}"
        lines.append(line)

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        src = node_map.get(
            str(edge.get("source") or edge.get("from") or ""),
            str(edge.get("source") or edge.get("from") or "?"),
        )
        tgt = node_map.get(
            str(edge.get("target") or edge.get("to") or ""),
            str(edge.get("target") or edge.get("to") or "?"),
        )
        label = str(edge.get("label") or "").strip()
        if label:
            lines.append(f"  {src} —{label}→ {tgt}")
        else:
            lines.append(f"  {src} → {tgt}")
    return "\n".join(lines)


def _render_timeline_data(data: Any) -> str:
    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list) or not events:
        return ""

    lines: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        label = str(event.get("label") or "").strip()
        date = str(event.get("date") or "").strip()
        desc = str(event.get("description") or "").strip()
        if not label:
            continue
        line = "· "
        line += f"{date}，{label}" if date else label
        if desc:
            line += f"：{desc}"
        lines.append(line)
    return "\n".join(lines)


def _render_list_data(data: Any) -> str:
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
        line = f"· {label}"
        if desc:
            line += f"：{desc}"
        lines.append(line)
    return "\n".join(lines)


_SYSTEM_DATA_RENDERERS = {
    "hierarchy": _render_hierarchy_data,
    "graph": _render_graph_data,
    "timeline": _render_timeline_data,
    "list": _render_list_data,
}


def _render_system_data(display_type: str, data: Any) -> str:
    renderer = _SYSTEM_DATA_RENDERERS.get(display_type)
    if renderer and data:
        return renderer(data)
    if data:
        try:
            return json.dumps(data, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(data)
    return ""


def format_world_context_for_prompt(writer_ctx: Mapping[str, Any]) -> str:
    """Render assemble_writer_context() output into an LLM-friendly text block."""

    systems = writer_ctx.get("systems") or []
    entities = writer_ctx.get("entities") or []
    relationships = writer_ctx.get("relationships") or []

    id_to_name: dict[int, str] = {}
    for entity in entities:
        try:
            id_to_name[int(entity.get("id"))] = str(entity.get("name") or "").strip()
        except Exception:
            continue

    lines: list[str] = []

    if systems:
        lines.append("〈世界体系〉")
        for system in systems:
            name = str(system.get("name") or "").strip()
            desc = str(system.get("description") or "").strip()
            display_type = str(system.get("display_type") or "").strip()
            header = f"- {name}" if name else "- （未命名体系）"
            if desc:
                header += f"：{desc}"
            lines.append(header)

            rendered = _render_system_data(display_type, system.get("data"))
            if rendered:
                for line in rendered.split("\n"):
                    lines.append(f"  {line}")

    if entities:
        lines.append("〈角色与事物〉")
        for entity in entities:
            name = str(entity.get("name") or "").strip()
            entity_type = str(entity.get("entity_type") or "").strip()
            desc = str(entity.get("description") or "").strip()
            header = f"- {name}" if name else "- （未命名实体）"
            if entity_type:
                header += f"（{entity_type}）"
            if desc:
                header += f"：{desc}"
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
                    lines.append(f"  别名：{'、'.join(normalized)}")

            attrs = entity.get("attributes") or []
            if isinstance(attrs, list) and attrs:
                for attr in attrs:
                    key = str(attr.get("key") or "").strip()
                    surface = str(attr.get("surface") or "").strip()
                    if key and surface:
                        lines.append(f"  - {key}：{surface}")
                    elif key:
                        lines.append(f"  - {key}")

    if relationships:
        lines.append("〈人物关系〉")
        for relationship in relationships:
            label = str(relationship.get("label") or "").strip()
            desc = str(relationship.get("description") or "").strip()
            src_id = relationship.get("source_id")
            tgt_id = relationship.get("target_id")
            src = id_to_name.get(int(src_id), str(src_id)) if src_id is not None else "？"
            tgt = id_to_name.get(int(tgt_id), str(tgt_id)) if tgt_id is not None else "？"
            line = f"- {src}"
            line += f" —{label}→ {tgt}" if label else f" → {tgt}"
            if desc:
                line += f"：{desc}"
            lines.append(line)

    return "\n".join(lines).strip()
