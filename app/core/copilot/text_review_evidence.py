"""Deterministic, chapter-bounded evidence for explicit author-view checks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.copilot.scope_shared import EvidenceItem, ScopeSnapshot
from app.core.indexing.lifecycle import inspect_window_index_lifecycle
from app.core.indexing.state_proto_runtime import StateProtoIndex
from app.core.text_targets import (
    content_hash,
    current_content,
    load_text_target,
    stale_text,
)
from app.models import (
    Chapter,
    CopilotRun,
    Novel,
    WorldEntity,
    WorldEntityAttribute,
    WorldRelationship,
    WorldSystem,
)

TEXT_REVIEW_ACTIONS = {"review_text", "propose_world_updates"}
INPUT_TOKEN_BUDGET = 8000
MAX_TARGET_CHARS = 5000
WORLD_FIELDS = {
    "entity": ("name", "entity_type", "description", "aliases"),
    "attribute": ("entity_id", "key", "surface", "truth", "visibility"),
    "relationship": ("source_id", "target_id", "label", "description", "visibility"),
    "system": ("name", "description", "constraints", "visibility"),
}
WORLD_MODELS = {
    "entity": WorldEntity,
    "attribute": WorldEntityAttribute,
    "relationship": WorldRelationship,
    "system": WorldSystem,
}


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def estimate_tokens(value: str) -> int:
    # A deliberately conservative estimate, not provider billing or a tokenizer.
    return sum(2 if ord(char) > 127 else 0.34 for char in value).__ceil__()


def world_values(row, resource: str) -> dict:
    return {key: getattr(row, key) for key in WORLD_FIELDS[resource]}


def bind_text_target(db: Session, novel_id: int, target: dict) -> dict:
    row = load_text_target(db, novel_id, target)
    body = current_content(row)
    expected = target.get("content_hash")
    if expected and content_hash(body) != expected:
        raise stale_text()
    return {
        **target,
        "chapter_number": row.chapter_number,
        "content_hash": content_hash(body),
        "label": target.get("label")
        or f"第 {row.chapter_number} 章 · {'正文' if target['kind'] == 'chapter' else '候选'}",
    }


@dataclass
class TextReviewWork:
    action: str
    target: dict
    body: str
    excerpt: str
    start: int
    evidence: list[EvidenceItem]
    snapshot: ScopeSnapshot
    coverage: str
    locale: str
    prompt: str = ""
    estimated_input_tokens: int = 0


def prepare_text_review(db: Session, run: CopilotRun, novel: Novel) -> TextReviewWork:
    target = bind_text_target(
        db, novel.id, (run.context_json or {}).get("text_target") or {}
    )
    if run.quick_action_id == "propose_world_updates" and target["kind"] != "chapter":
        raise ValueError("World updates require adopted chapter text")
    row = load_text_target(db, novel.id, target)
    body = current_content(row)
    start = min(target.get("start", 0), len(body))
    end = min(target.get("end") or len(body), len(body), start + MAX_TARGET_CHARS)
    excerpt = body[start:end]
    if not excerpt.strip():
        raise ValueError("No text to review")
    evidence: list[EvidenceItem] = []

    def add(source_type: str, ref: dict, title: str, text: str, why: str) -> None:
        if text.strip():
            evidence.append(
                EvidenceItem(f"e{len(evidence)}", source_type, ref, title, text, why)
            )

    target_ref = {
        "kind": target["kind"],
        "id": row.id,
        "chapter_number": row.chapter_number,
        "content_hash": target["content_hash"],
        "start_pos": start,
        "end_pos": end,
    }
    if target["kind"] == "chapter":
        target_ref["chapter_id"] = row.id
    add(
        "target_text",
        target_ref,
        target["label"],
        excerpt,
        "待核对文本，不能作为自身先前状态的证明",
    )

    refs = (
        db.query(WorldEntity.id, WorldEntity.name, WorldEntity.aliases)
        .filter(WorldEntity.novel_id == novel.id)
        .all()
    )
    matched_ids = [
        item.id
        for item in refs
        if any(
            name and name.casefold() in excerpt.casefold()
            for name in [item.name, *(item.aliases or [])]
        )
    ][:12]
    entities = (
        db.query(WorldEntity)
        .filter(WorldEntity.id.in_(matched_ids))
        .order_by(WorldEntity.id)
        .all()
        if matched_ids
        else []
    )
    attrs = (
        db.query(WorldEntityAttribute)
        .filter(WorldEntityAttribute.entity_id.in_(matched_ids))
        .order_by(WorldEntityAttribute.id)
        .all()
        if matched_ids
        else []
    )
    relationships = (
        db.query(WorldRelationship)
        .filter(
            WorldRelationship.novel_id == novel.id,
            or_(
                WorldRelationship.source_id.in_(matched_ids),
                WorldRelationship.target_id.in_(matched_ids),
            ),
        )
        .order_by(WorldRelationship.id)
        .limit(12)
        .all()
        if matched_ids
        else []
    )
    systems = (
        db.query(WorldSystem)
        .filter(WorldSystem.novel_id == novel.id, WorldSystem.status == "confirmed")
        .order_by(WorldSystem.id)
        .all()
    )
    systems.sort(
        key=lambda item: (
            item.name not in excerpt
            and not any(
                entity.name in dump([item.description, item.constraints])
                for entity in entities
            ),
            item.id,
        )
    )
    systems = systems[:8]
    for resource, rows in [
        ("system", systems),
        ("entity", entities),
        ("attribute", attrs[:32]),
        ("relationship", relationships),
    ]:
        for item in rows:
            values = world_values(item, resource)
            source_notes = [
                {
                    "chapter_number": source.get("chapter_number"),
                    "status": source.get("status"),
                }
                for source in item.source_refs
            ]
            text = dump(
                {
                    "resource": resource,
                    "id": item.id,
                    **values,
                    "status": getattr(item, "status", None),
                    "sources": source_notes,
                }
            )
            if len(text) > 1800:
                continue  # Never silently turn half a rule into a complete rule.
            name = getattr(
                item, "name", getattr(item, "key", getattr(item, "label", ""))
            )
            add(
                "world_setting",
                {
                    "resource": resource,
                    "id": item.id,
                    "values": values,
                    "historical_unavailable": any(
                        (source.get("chapter_number") or 0) >= row.chapter_number
                        for source in source_notes
                    ),
                },
                f"当前设定 · {name}",
                text,
                "当前作者材料；surface 可含传闻与提示，truth 不代表应在此章揭晓",
            )

    def chapter_excerpt(chapter: Chapter, begin: int, finish: int, why: str) -> None:
        add(
            "chapter",
            {
                "chapter_id": chapter.id,
                "chapter_number": chapter.chapter_number,
                "content_hash": content_hash(chapter.content),
                "start_pos": begin,
                "end_pos": finish,
            },
            f"第 {chapter.chapter_number} 章",
            chapter.content[begin:finish],
            why,
        )

    state_available = False
    lifecycle = inspect_window_index_lifecycle(novel)
    if lifecycle.status == "fresh" and novel.window_index:
        try:

            def resolve(chapter_id: int) -> str:
                chapter = db.get(Chapter, chapter_id)
                return (
                    chapter.content
                    if chapter
                    and chapter.novel_id == novel.id
                    and chapter.chapter_number < row.chapter_number
                    else ""
                )

            index = StateProtoIndex.from_msgpack(
                novel.window_index, chapter_text_resolver=resolve
            ).through_chapter(row.chapter_number - 1)
            state_available = True
            seen: set[tuple[int, int]] = set()
            for item in index.targets.values():
                if not any(
                    name and name in excerpt
                    for name in [item.canonical_name, *item.aliases]
                ):
                    continue
                for pack in index.find_state(item.id):
                    source = index.open(pack.source_handle)
                    key = (source.chapter_id, source.start_pos)
                    if key in seen or len(seen) >= 6:
                        continue
                    chapter = db.get(Chapter, source.chapter_id)
                    if (
                        chapter is None
                        or chapter.novel_id != novel.id
                        or chapter.chapter_number >= row.chapter_number
                    ):
                        continue
                    seen.add(key)
                    chapter_excerpt(
                        chapter,
                        source.start_pos,
                        source.end_pos,
                        f"候选状态线索 {pack.slot}={pack.candidate_value_signature}；不确定性：{pack.uncertainty_hint or '仍需语境判断'}",
                    )
        except (ValueError, KeyError, TypeError):
            state_available = False
    # Bounded current-text fallback; never read future chapters or other candidates.
    previous = (
        db.query(Chapter)
        .filter(
            Chapter.novel_id == novel.id, Chapter.chapter_number < row.chapter_number
        )
        .order_by(Chapter.chapter_number.desc())
        .limit(12)
        .all()
    )
    included = {item.source_ref.get("chapter_id") for item in evidence}
    for chapter in previous:
        if chapter.id in included:
            continue
        positions = [chapter.content.find(entity.name) for entity in entities]
        positions = [position for position in positions if position >= 0]
        if not positions and len(evidence) > 1:
            continue
        begin = (
            max(0, min(positions) - 180)
            if positions
            else max(0, len(chapter.content) - 700)
        )
        chapter_excerpt(
            chapter,
            begin,
            min(len(chapter.content), begin + 700),
            "目标章之前的正文片段；按叙述语境判断",
        )
        if sum(item.source_type == "chapter" for item in evidence) >= 6:
            break
    coverage = f"参考截至第 {row.chapter_number} 章的正文与当前设定 · 作者视角"
    if not state_available:
        coverage += "；状态索引不可用，使用有限正文片段"
    snapshot = ScopeSnapshot(
        novel=novel,
        novel_language=novel.language,
        entities=entities,
        entities_by_id={entity.id: entity for entity in entities},
        relationships=relationships,
        systems=systems,
        attributes_by_entity={
            entity.id: [attr for attr in attrs if attr.entity_id == entity.id]
            for entity in entities
        },
        draft_entities=[],
        draft_relationships=[],
        draft_systems=[],
    )
    return TextReviewWork(
        run.quick_action_id,
        target,
        body,
        excerpt,
        start,
        evidence,
        snapshot,
        coverage,
        run.session.interaction_locale,
    )


def persist_review_context(db: Session, run: CopilotRun, work: TextReviewWork) -> None:
    run.context_json = {
        **(run.context_json or {}),
        "text_target": work.target,
        "text_review": {
            "action": work.action,
            "target": work.target,
            "coverage": work.coverage,
            "estimated_input_tokens": work.estimated_input_tokens,
            "closed": False,
        },
    }
    run.evidence_json = [asdict(item) for item in work.evidence]
    db.commit()
