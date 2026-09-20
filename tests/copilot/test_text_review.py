"""Bounded review, explicit adoption and stale-result protection contracts."""
import json
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from openai import AsyncOpenAI

from app.core.ai_client import AIClient
from app.core.copilot.apply import apply_suggestions
from app.core.copilot.service import create_run, open_or_reuse_session
from app.core.copilot.suggestions import serialize_compiled_suggestions
from app.core.copilot.text_review import (
    SYSTEM_PROMPT, ReviewResult, build_review_prompt, compile_review_result, execute_review,
)
from app.core.copilot.text_review_apply import apply_text_suggestions, review_response
from app.core.copilot.text_review_evidence import (
    estimate_tokens, prepare_text_review, persist_review_context,
)
from app.core.text_targets import content_hash, stage_text_write
from app.models import Chapter, Continuation, CopilotRun, CopilotSession, WorldEntityAttribute
from tests.copilot.runtime_support import TEST_LLM_CONFIG, TestingSessionLocal


def review_work(db, novel, target, action="review_text"):
    session = CopilotSession(session_id=str(uuid.uuid4()), novel_id=novel.id, user_id=1,
        mode="research", scope="whole_book", interaction_locale="zh", signature=str(uuid.uuid4()),
        display_title="核对", context_json={"text_target": target})
    db.add(session)
    db.flush()
    run = CopilotRun(run_id=str(uuid.uuid4()), copilot_session_id=session.id, novel_id=novel.id,
        user_id=1, status="completed", prompt="核对", quick_action_id=action, context_json=session.context_json)
    db.add(run)
    db.commit()
    work = prepare_text_review(db, run, novel)
    build_review_prompt(work, run.prompt)
    persist_review_context(db, run, work)
    return run, work


def compile_cards(db, run, work, drafts, latest=3):
    cards = compile_review_result(work, ReviewResult.model_validate({"answer": "核对完成", "suggestions": drafts}), latest_chapter=latest)
    run.suggestions_json = serialize_compiled_suggestions(cards)
    db.commit()
    return cards


def patch(work, before, after):
    source = next(item for item in work.evidence if item.source_type == "chapter")
    return {"kind": "replace_text", "title": "局部核对", "summary": "与前文对照", "before": before, "after": after,
            "references": [{"id": source.evidence_id, "quote": source.excerpt[:20]}]}


def test_historical_evidence_and_budget(db, novel, chapters, entities, attributes, systems):
    chapters[0].content = "张三留在宗门，境界是金丹期。"
    chapters[1].content = "张三" + "面前传来风声。" * 2200
    chapters[2].content = "绝不可混入的未来正文，张三成为宗主。"
    attributes[0].truth = "作者保留的隐藏解释"
    db.commit()
    _, work = review_work(db, novel, {"kind": "chapter", "id": chapters[1].id})
    assert "绝不可混入的未来正文" not in work.prompt
    assert all(item.source_ref["chapter_number"] < 2 for item in work.evidence if item.source_type == "chapter")
    assert "作者保留的隐藏解释" in work.prompt
    assert work.estimated_input_tokens == estimate_tokens(SYSTEM_PROMPT + work.prompt) <= 8000
    assert "实际核对" in work.coverage
    assert len(work.excerpt) < len(chapters[1].content)


def test_native_state_cutoff_happens_before_ranking_trace_and_open():
    from app.core.indexing.builder import ChapterText
    from app.core.indexing.state_proto import StateProtoIndex, TargetSpec, execute_state_proto_build
    chapters = [
        ChapterText(chapter_id=1, text="林秋在云港旧街盘货。"),
        ChapterText(chapter_id=2, text="夜里林秋来到北栈码头等船。"),
        ChapterText(chapter_id=3, text="后来林秋仍在河湾书院。"),
    ]
    built = execute_state_proto_build(chapters=chapters, novel_language="zh", target_specs=[TargetSpec(id="lin", canonical_name="林秋")])
    full = StateProtoIndex.from_msgpack(built.index_payload, chapter_texts={chapter.chapter_id: chapter.text for chapter in chapters})
    bounded = full.through_chapter(1)
    packs = bounded.find_state("lin")
    assert packs
    assert all("北栈码头" not in pack.preview_excerpt and "河湾书院" not in pack.preview_excerpt for pack in packs)
    assert all(row.chapter_to <= 1 for pack in packs for row in bounded.trace_slot("lin", pack.slot).regimes)
    assert all(bounded.open(pack.source_handle).chapter_number == 1 for pack in packs)
    future_segment = next(segment for segment in full.segments if segment.chapter_number == 3)
    with pytest.raises(KeyError):
        bounded.open(f"segment::{future_segment.segment_id}")
    assert all(segment.chapter_number <= 1 for segment in bounded.segments)
    assert len(full.segments) > len(bounded.segments)


def test_invalid_quote_or_ambiguous_anchor_is_reference_only(db, novel, chapters):
    chapters[2].content = "张三回来了。张三回来了。"
    db.commit()
    run, work = review_work(db, novel, {"kind": "chapter", "id": chapters[2].id})
    ambiguous = patch(work, "张三回来了。", "张三留下了。")
    fabricated = patch(work, work.body, "张三留下了。")
    fabricated["references"][0]["quote"] = "这句根本不存在"
    cards = compile_cards(db, run, work, [ambiguous, fabricated])
    assert len(cards) == 2
    assert all(card.apply_action is None and not card.preview["actionable"] for card in cards)


def test_future_sourced_setting_cannot_justify_historical_rewrite(db, novel, chapters, entities):
    entity = entities[0]
    chapters[1].content = "张三留在南城。"
    entity.source_metadata = {"values": {"description": entity.description}, "refs": [{
        "chapter_id": chapters[2].id, "chapter_number": 3,
        "content_hash": content_hash(chapters[2].content), "quote": chapters[2].content,
    }]}
    db.commit()
    run, work = review_work(db, novel, {"kind": "chapter", "id": chapters[1].id})
    source = next(item for item in work.evidence if item.source_ref.get("resource") == "entity"
                  and item.source_ref.get("id") == entity.id)
    cards = compile_cards(db, run, work, [{"kind": "replace_text", "title": "未来状态",
        "before": "南城", "after": "北城", "references": [{"id": source.evidence_id, "quote": source.excerpt}]}])
    assert cards[0].apply_action is None


def test_world_update_source_locates_exact_quote_in_selected_excerpt(db, novel, chapters, entities):
    chapters[2].content = "😀前文。张三成为守门人。末尾。"
    db.commit()
    _, work = review_work(db, novel, {"kind": "chapter", "id": chapters[2].id, "start": 4}, "propose_world_updates")
    quote = "张三成为守门人。"
    cards = compile_review_result(work, ReviewResult.model_validate({"answer": "更新", "suggestions": [{
        "kind": "update_entity", "target_id": entities[0].id, "title": "身份", "delta": {"description": "守门人"},
        "references": [{"id": "e0", "quote": quote}],
    }]}), latest_chapter=3)
    source = cards[0].apply_action["source_refs"][0]
    assert work.body[source["start_pos"]:source["end_pos"]] == quote


def test_batch_apply_preserves_candidate_original_and_rejects_replay(db, novel, chapters):
    candidate = Continuation(novel_id=novel.id, chapter_number=4, content="😀张三去了南城。李四留在北城。")
    other = Continuation(novel_id=novel.id, chapter_number=4, content="其他候选原样保留。")
    db.add_all([candidate, other])
    db.commit()
    original = candidate.content
    run, work = review_work(db, novel, {"kind": "continuation", "id": candidate.id})
    cards = compile_cards(db, run, work, [patch(work, "南城", "西城"), patch(work, "北城", "东城")])
    result = apply_text_suggestions(db, run, [card.suggestion_id for card in cards], content_hash(original))
    db.refresh(candidate)
    assert result["before_content"] == candidate.content == original
    assert candidate.edited_content == "😀张三去了西城。李四留在东城。"
    assert other.edited_content is None
    assert db.query(Chapter).count() == 3  # Applying is not adoption.
    with pytest.raises(HTTPException) as error:
        apply_text_suggestions(db, run, [cards[0].suggestion_id], result["content_hash"])
    assert error.value.status_code == 409
    db.rollback()
    # Undo can restore only the exact result, never a subsequent manual edit.
    stage_text_write(db, candidate, "作者后续修改", result["content_hash"])
    db.commit()
    with pytest.raises(HTTPException):
        stage_text_write(db, candidate, original, result["content_hash"])
    db.rollback()
    assert candidate.edited_content == "作者后续修改"


@pytest.mark.parametrize("change", ["target", "source", "overlap", "duplicate"])
def test_stale_or_overlapping_batch_writes_nothing(db, novel, chapters, change):
    chapters[2].content = "张三在南城。李四在北城。"
    db.commit()
    run, work = review_work(db, novel, {"kind": "chapter", "id": chapters[2].id})
    drafts = [patch(work, "南城", "西城"), patch(work, "张三在南城", "张三在东城")]
    cards = compile_cards(db, run, work, drafts)
    selected = [cards[0].suggestion_id]
    if change == "target":
        chapters[2].content += "新的手改。"
    elif change == "source":
        source_id = next(item.source_ref["chapter_id"] for item in work.evidence if item.source_type == "chapter")
        db.get(Chapter, source_id).content += "前文已变。"
    elif change == "overlap":
        selected.append(cards[1].suggestion_id)
    else:
        selected *= 2
    db.commit()
    expected = chapters[2].content
    with pytest.raises(HTTPException):
        apply_text_suggestions(db, run, selected, work.target["content_hash"])
    db.rollback()
    assert chapters[2].content == expected
    assert all(item["status"] == "pending" for item in run.suggestions_json)


def test_world_update_requires_separate_confirmation_and_keeps_sources(db, novel, chapters, entities):
    chapters[2].content = "张三在第3章成为守门人。"
    db.commit()
    run, work = review_work(db, novel, {"kind": "chapter", "id": chapters[2].id}, "propose_world_updates")
    draft = {"kind": "update_entity", "target_resource": "entity", "target_id": entities[0].id,
        "title": "记录身份", "references": [{"id": "e0", "quote": work.body}],
        "delta": {"attributes": [{"key": "守门经历", "surface": "第3章成为守门人", "truth": "禁止写入", "visibility": "hidden"}]}}
    cards = compile_cards(db, run, work, [draft])
    assert cards[0].apply_action is not None
    assert db.query(WorldEntityAttribute).count() == 0
    result = apply_suggestions(db, run, [cards[0].suggestion_id])
    assert result[0].success
    attr = db.query(WorldEntityAttribute).one()
    assert attr.truth is None and attr.visibility != "hidden"
    assert attr.source_refs[0]["quote"] == work.body
    assert attr.source_refs[0]["status"] == "current"
    chapters[2].content += "修改来源。"
    db.commit()
    assert attr.source_refs[0]["status"] == "needs_review"
    assert entities[0].status == "confirmed"
    db.delete(chapters[2])
    db.commit()
    assert attr.source_refs[0]["status"] == "missing"


def test_world_value_changed_while_model_running_is_not_overwritten(db, novel, chapters, entities):
    run, work = review_work(db, novel, {"kind": "chapter", "id": chapters[2].id}, "propose_world_updates")
    entities[0].description = "作者刚刚改过的设定"
    db.commit()
    cards = compile_cards(db, run, work, [{"kind": "update_entity", "target_id": entities[0].id,
        "title": "更新", "delta": {"description": "模型提出的新描述"},
        "references": [{"id": "e0", "quote": work.body}]}])
    assert review_response(run, db)["stale"]
    result = apply_suggestions(db, run, [cards[0].suggestion_id])
    assert not result[0].success
    assert entities[0].description == "作者刚刚改过的设定"


def test_historical_world_overwrite_is_reference_only(db, novel, chapters, entities):
    run, work = review_work(db, novel, {"kind": "chapter", "id": chapters[0].id}, "propose_world_updates")
    cards = compile_cards(db, run, work, [{"kind": "update_entity", "target_id": entities[0].id,
        "title": "过时状态", "delta": {"description": "过去的位置"},
        "references": [{"id": "e0", "quote": work.body}]}])
    assert cards[0].apply_action is None
    assert not cards[0].preview["actionable"]


def test_new_review_reuses_session_but_captures_current_text(db, novel, chapters):
    context = {"text_target": {"kind": "chapter", "id": chapters[0].id}}
    session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", context, "zh", "核对")
    first = create_run(db, session, 1, "核对", quick_action_id="review_text")
    first.status = "completed"
    chapters[0].content += "新正文"
    db.commit()
    session_again, created = open_or_reuse_session(db, novel.id, 1, "research", "whole_book",
        {"text_target": {**context["text_target"], "content_hash": content_hash(chapters[0].content)}}, "zh", "核对")
    assert not created and session.id == session_again.id
    second = create_run(db, session_again, 1, "再核对", quick_action_id="review_text")
    assert first.context_json["text_target"]["content_hash"] != second.context_json["text_target"]["content_hash"]


@pytest.mark.asyncio
async def test_malformed_review_calls_model_once_without_fallback(db, novel, chapters, monkeypatch):
    run, work = review_work(db, novel, {"kind": "chapter", "id": chapters[2].id})
    run.status = "running"
    run.lease_owner = "review-worker"
    db.commit()
    generate = AsyncMock(return_value="truncated JSON {")
    monkeypatch.setattr(AIClient, "generate", generate)
    monkeypatch.setattr("app.core.copilot.text_review.acquire_llm_slot", AsyncMock())
    monkeypatch.setattr("app.core.copilot.text_review.release_llm_slot", lambda: None)
    with pytest.raises(json.JSONDecodeError):
        await execute_review(work, db_factory=TestingSessionLocal, run_id=run.run_id,
            worker_id="review-worker", llm_config=TEST_LLM_CONFIG, user_id=1)
    generate.assert_awaited_once()
    assert generate.call_args.kwargs["provider_retries"] == 0
    assert generate.call_args.kwargs["max_tokens"] == 2000


@pytest.mark.asyncio
async def test_provider_failure_really_sends_only_one_http_request(monkeypatch):
    from contextlib import asynccontextmanager
    import app.core.ai_client as module
    requests = []
    def provider(request):
        requests.append(request)
        return httpx.Response(500, json={"error": {"message": "temporary failure"}})
    @asynccontextmanager
    async def client(_config):
        async with AsyncOpenAI(api_key="synthetic-key", base_url="https://test.invalid/v1",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(provider))) as sdk:
            yield sdk
    monkeypatch.setattr(module, "_openai_client", client)
    monkeypatch.setattr(module, "ensure_ai_available_fresh_session", lambda **kwargs: None)
    with pytest.raises(Exception):
        await AIClient().generate("核对", llm_config=TEST_LLM_CONFIG, provider_retries=0)
    assert len(requests) == 1
