"""Explicit, single-request author review within the existing Copilot run."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, OnErrorOmit
from sqlalchemy.orm import Session

from app.core.ai_client import AIClient, structured_system_prompt
from app.core.copilot.run_store import persist_completed_run, renew_run_lease
from app.core.copilot.runtime_errors import RunLeaseLostError
from app.core.copilot.suggestions import CompiledSuggestion, compile_suggestions
from app.core.copilot.sync_runtime import run_sync
from app.core.copilot.text_review_evidence import (
    INPUT_TOKEN_BUDGET,
    TextReviewWork,
    estimate_tokens,
    persist_review_context,
    prepare_text_review,
)
from app.core.llm_semaphore import acquire_llm_slot, release_llm_slot
from app.models import Chapter, CopilotRun

REVIEW_FORMAT = """You are a fiction editor. Answer in the requested language. Read the supplied passages as fiction.
Return one JSON object {"answer":"brief conclusion","suggestions":[]}. For each suggestion give a kind, title and references with the evidence id and an exact quote. Offer at most three suggestions.
"""
REVIEW_PROMPTS = {
    "review_text": REVIEW_FORMAT + """Check continuity against earlier passages and cited rules. Distinguish narrator, belief and rumor. Current settings describe the present. Leave hidden explanations out of replacement prose.
Use kind "replace_text" for a local edit: before is a unique, exact substring of the target and after is the replacement (up to 300 characters). Cite an earlier passage or a rule that supports it. Use "note" for a concern that needs the author's judgment.""",
    "propose_world_updates": REVIEW_FORMAT + """Record only changes that matter to a later scene: possession, commitments, who knows something, or a lasting rule. Attribute beliefs and rumors to their speakers. An empty suggestions list is valid.
Example response for a sailor giving his map to Ada: {"answer":"Ada now holds the map.","suggestions":[{"kind":"create_entity","title":"Map","delta":{"name":"Map","entity_type":"Item","description":"Held by Ada."},"references":[{"id":"e0","quote":"he handed his map to Ada"}]}]}.
Quote the target chapter. Use create_entity, create_relationship or create_system for new records. Use update_entity, update_relationship or update_system with an existing target_id and only the changed fields in delta. For relationships set target_resource to relationship and give existing source_id, target_id and label. For rules set target_resource to system and give name, description and constraints. For historical chapters record dated experience as attributes (key and surface).""",
}


class Reference(BaseModel):
    id: str = Field(max_length=80)
    quote: str = Field(min_length=1, max_length=600)


class ReviewDraft(BaseModel):
    kind: str = Field(max_length=40)
    title: str = Field(max_length=160)
    summary: str = Field(default="", max_length=800)
    references: list[Reference] = Field(default_factory=list, max_length=3)
    before: str = Field(default="", max_length=1200)
    after: str = Field(default="", max_length=300)
    target_resource: str = "entity"
    target_id: int | None = None
    delta: dict = Field(default_factory=dict)


class ReviewResult(BaseModel):
    answer: str = Field(max_length=4000)
    suggestions: list[OnErrorOmit[ReviewDraft]] = Field(default_factory=list)


def build_review_prompt(work: TextReviewWork, user_prompt: str) -> str:
    target = work.evidence[0]
    system_prompt = structured_system_prompt(REVIEW_PROMPTS[work.action], ReviewResult)
    request = f"Language: {work.locale}\nRequest: {user_prompt[:1000]}"

    def encode(items) -> str:
        target, *references = items
        passages = [f"Reference [{item.evidence_id}] {item.title}\n{item.excerpt}" for item in references]
        return "\n\n".join([request, *passages, f"Target passage [{target.evidence_id}] {target.title}\n{target.excerpt}"])

    # Reserve room for evidence; shortening is explicit in the returned coverage.
    while (
        estimate_tokens(system_prompt + encode([target])) > 6000
        and len(target.excerpt) > 300
    ):
        target.excerpt = target.excerpt[: int(len(target.excerpt) * 0.85)]
    work.excerpt = target.excerpt
    target.source_ref["end_pos"] = work.start + len(work.excerpt)
    selected = [target]
    settings = [
        item for item in work.evidence[1:] if item.source_type == "world_setting"
    ]
    passages = [item for item in work.evidence[1:] if item.source_type == "chapter"]
    ordered = []
    for index in range(max(len(settings), len(passages))):
        if index < len(settings):
            ordered.append(settings[index])
        if index < len(passages):
            ordered.append(passages[index])
    for item in ordered:
        if (
            len(selected) < 12
            and estimate_tokens(system_prompt + encode([*selected, item]))
            <= INPUT_TOKEN_BUDGET
        ):
            selected.append(item)
    if len(selected) < len(work.evidence):
        work.coverage += "；证据按本次预算选取"
    if work.start or len(work.excerpt) < len(work.body):
        work.coverage += (
            f"；实际核对第 {work.start + 1}–{work.start + len(work.excerpt)} 字"
        )
    work.evidence = selected
    work.prompt = encode(selected)
    work.estimated_input_tokens = estimate_tokens(system_prompt + work.prompt)
    return work.prompt


def prepare_run(db: Session, run: CopilotRun, novel) -> TextReviewWork:
    work = prepare_text_review(db, run, novel)
    build_review_prompt(work, run.prompt)
    persist_review_context(db, run, work)
    return work


def _references(draft: ReviewDraft, work: TextReviewWork):
    lookup = {item.evidence_id: item for item in work.evidence}
    references = []
    for ref in draft.references:
        item = lookup.get(ref.id)
        if item is None or ref.quote not in item.excerpt:
            return []
        references.append((item, ref.quote))
    return references


def compile_review_result(
    work: TextReviewWork, result: ReviewResult, *, latest_chapter: int
) -> list[CompiledSuggestion]:
    compiled = []
    for draft in result.suggestions:
        references = _references(draft, work)
        ids = [item.evidence_id for item, _ in references]
        quotes = [quote for _, quote in references]
        guards = [dict(item.source_ref) for item, _ in references]
        action = None
        reason = None
        if work.action == "review_text":
            valid_anchor = bool(
                draft.before
                and work.body.count(draft.before) == 1
                and draft.before in work.excerpt
            )
            grounded = any(
                item.source_type in {"chapter", "world_setting"}
                for item, _ in references
            )
            if (
                draft.kind == "replace_text"
                and valid_anchor
                and draft.after
                and grounded
                and not any(guard.get("historical_unavailable") for guard in guards)
            ):
                offset = work.body.index(draft.before)
                action = {
                    "type": "replace_text",
                    "data": {
                        "start": offset,
                        "end": offset + len(draft.before),
                        "before": draft.before,
                        "after": draft.after,
                    },
                    "review_guards": guards,
                }
            else:
                reason = "需作者判断：未获得可验证且唯一的原文位置或充分依据。"
            compiled.append(
                CompiledSuggestion(
                    suggestion_id=f"text_{uuid.uuid4().hex[:12]}",
                    kind="replace_text",
                    title=draft.title,
                    summary=draft.summary,
                    evidence_ids=ids,
                    target={
                        "resource": work.target["kind"],
                        "resource_id": work.target["id"],
                        "label": work.target["label"],
                        "tab": "chapter",
                    },
                    preview={
                        "target_label": work.target["label"],
                        "summary": draft.summary,
                        "field_deltas": [
                            {
                                "field": "content",
                                "label": "局部改写",
                                "before": draft.before or None,
                                "after": draft.after,
                            }
                        ]
                        if draft.after
                        else [],
                        "evidence_quotes": quotes,
                        "actionable": action is not None,
                        "non_actionable_reason": reason,
                    },
                    apply_action=action,
                )
            )
            continue
        if not any(item.source_type == "target_text" for item, _ in references):
            continue
        if draft.kind not in {
            "create_entity",
            "update_entity",
            "create_relationship",
            "update_relationship",
            "create_system",
            "update_system",
        }:
            continue
        if draft.target_resource not in {"entity", "relationship", "system"}:
            continue
        if draft.kind != f"{draft.kind.split('_')[0]}_{draft.target_resource}":
            continue
        # No silently synthesized dependencies or visibility/hidden-truth changes.
        delta = {
            key: value
            for key, value in draft.delta.items()
            if key not in {"visibility", "truth", "display_type"}
        }
        if isinstance(delta.get("attributes"), list):
            delta["attributes"] = [
                {key: value for key, value in item.items() if key in {"key", "surface"}}
                for item in delta["attributes"]
                if isinstance(item, dict)
            ]
        if draft.kind == "create_relationship" and not all(
            isinstance(delta.get(f"{side}_id"), int) for side in ("source", "target")
        ):
            continue
        raw = {
            "kind": draft.kind,
            "title": draft.title,
            "summary": draft.summary,
            "target_resource": draft.target_resource,
            "target_id": draft.target_id,
            "delta": delta,
            "cited_evidence_indices": [
                index
                for index, item in enumerate(work.evidence)
                if item.evidence_id in ids
            ],
        }
        cards = compile_suggestions(
            [raw], work.evidence, work.snapshot, "research", "whole_book", work.locale
        )
        for card in cards[:1]:
            card.preview["evidence_quotes"] = quotes
            action = card.apply_action
            if action:
                from app.core.copilot.text_review_apply import capture_action_guards

                action["review_guards"] = guards
                # Values captured in the original evidence snapshot, not fresh values after the model returns.
                capture_action_guards(action, work)
                if work.target["chapter_number"] < latest_chapter:
                    attrs = action.get("attribute_actions", [])
                    dated = all(
                        str(work.target["chapter_number"])
                        in item.get("data", {}).get("surface", "")
                        for item in attrs
                    )
                    if (
                        action["type"] != "update_entity"
                        or action.get("data")
                        or not attrs
                        or not dated
                        or any(item["type"] != "create_attribute" for item in attrs)
                    ):
                        card.apply_action = None
                        card.preview.update(
                            actionable=False,
                            non_actionable_reason="历史章不能直接覆盖当前状态；请记录带章节限定的新经历。",
                        )
                action["source_refs"] = [
                    {
                        **item.source_ref,
                        "quote": quote,
                        "start_pos": item.source_ref["start_pos"]
                        + item.excerpt.index(quote),
                        "end_pos": item.source_ref["start_pos"]
                        + item.excerpt.index(quote)
                        + len(quote),
                    }
                    for item, quote in references
                    if item.source_type == "target_text"
                ][:3]
            compiled.append(card)
    return compiled[:3]


async def execute_review(
    work: TextReviewWork,
    *,
    db_factory,
    run_id: str,
    worker_id: str,
    llm_config,
    user_id: int,
) -> None:
    if not await run_sync(
        renew_run_lease, db_factory, run_id=run_id, worker_id=worker_id
    ):
        raise RunLeaseLostError(run_id)
    await acquire_llm_slot()
    try:
        result = await AIClient().generate_structured(
            response_model=ReviewResult,
            prompt=work.prompt,
            system_prompt=REVIEW_PROMPTS[work.action],
            llm_config=llm_config,
            user_id=user_id,
            max_tokens=2000,
            temperature=0.2,
            max_retries=1,
        )
    finally:
        release_llm_slot()

    def finish():
        with db_factory() as db:
            latest = (
                db.query(Chapter.chapter_number)
                .filter(Chapter.novel_id == work.snapshot.novel.id)
                .order_by(Chapter.chapter_number.desc())
                .first()
            )
            return compile_review_result(
                work, result, latest_chapter=latest[0] if latest else 0
            )

    compiled = await run_sync(finish)
    await run_sync(
        persist_completed_run,
        db_factory,
        run_id=run_id,
        worker_id=worker_id,
        answer=result.answer,
        evidence=work.evidence,
        compiled_suggestions=compiled,
        workspace=None,
        execution_mode="text_review_one_shot",
        degraded_reason=None,
    )
