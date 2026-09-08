from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.core.auth import get_current_user_or_default
from app.core.context_summaries import (
    context_summary_source_fingerprint,
    load_context_summary_source,
)
from app.core.llm_config import ResolvedLlmConfig
from app.core.llm_request import get_llm_config
from app.database import Base, get_db
from app.models import Chapter, Novel, NovelContextSummary, User


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def user(db):
    row = User(
        username="context-summary-user",
        hashed_password="x",
        role="admin",
        is_active=True,
        generation_quota=8,
        feedback_submitted=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def novel(db, user):
    row = Novel(
        title="Markdown 长篇",
        author="作者",
        language="zh",
        file_path="/tmp/context-summary.md",
        content_format="markdown",
        total_chapters=2,
        owner_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add_all(
        [
            Chapter(
                novel_id=row.id,
                chapter_number=1,
                title="起点",
                content="### 场景\n\n主角找到 **旧钥匙**。",
            ),
            Chapter(
                novel_id=row.id,
                chapter_number=2,
                title="门后",
                content="门后传来回声，线索尚未解决。",
            ),
        ]
    )
    db.commit()
    return row


@pytest.fixture
def client(db, user, monkeypatch):
    from app.api import novel_context_summaries as summaries_api

    test_app = FastAPI()
    test_app.include_router(summaries_api.router)

    def override_get_db():
        yield db

    llm_config = ResolvedLlmConfig(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="test-model",
        billing_source_hint="selfhost",
        source="selfhost_settings",
    )
    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user_or_default] = lambda: user
    test_app.dependency_overrides[get_llm_config] = lambda: llm_config

    async def acquire() -> None:
        return None

    monkeypatch.setattr(summaries_api, "acquire_llm_slot", acquire)
    monkeypatch.setattr(summaries_api, "release_llm_slot", lambda: None)

    with TestClient(test_app) as test_client:
        yield test_client
    test_app.dependency_overrides.clear()


def _fresh_summary(
    db,
    novel,
    *,
    start_chapter: int = 1,
    end_chapter: int = 2,
    content: str = "事件回顾",
    review_status: str = "confirmed",
) -> NovelContextSummary:
    source = load_context_summary_source(
        db,
        novel_id=novel.id,
        start_chapter=start_chapter,
        end_chapter=end_chapter,
        locale=novel.language,
    )
    row = NovelContextSummary(
        novel_id=novel.id,
        start_chapter=start_chapter,
        end_chapter=end_chapter,
        title=f"第{start_chapter}—{end_chapter}章远期剧情回顾",
        content=content,
        source_fingerprint=context_summary_source_fingerprint(source),
        review_status=review_status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_create_context_summary_preserves_markdown_and_requires_review(
    client,
    db,
    novel,
    monkeypatch,
):
    from app.api import novel_context_summaries as summaries_api

    captured: dict[str, object] = {}

    async def generate(_self, prompt: str, **kwargs) -> str:
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return "主角取得旧钥匙，并听见门后的回声。"

    monkeypatch.setattr(summaries_api.AIClient, "generate", generate)

    response = client.post(
        f"/api/novels/{novel.id}/context-summaries",
        json={"start_chapter": 1, "end_chapter": 2},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "第1—2章远期剧情回顾"
    assert payload["review_status"] == "draft"
    assert payload["is_stale"] is False
    assert "### 场景" in str(captured["prompt"])
    assert "**旧钥匙**" in str(captured["prompt"])
    assert captured["kwargs"]["max_tokens"] == 4000
    row = db.query(NovelContextSummary).filter_by(novel_id=novel.id).one()
    assert len(row.source_fingerprint) == 64


def test_list_marks_summary_stale_after_source_chapter_changes(client, db, novel):
    row = _fresh_summary(db, novel)
    initial = client.get(f"/api/novels/{novel.id}/context-summaries")
    assert initial.status_code == 200
    assert initial.json()[0]["is_stale"] is False

    chapter = db.query(Chapter).filter_by(novel_id=novel.id, chapter_number=1).one()
    chapter.content += "\n\n新增事实。"
    db.commit()

    changed = client.get(f"/api/novels/{novel.id}/context-summaries")
    assert changed.status_code == 200
    assert changed.json()[0]["id"] == row.id
    assert changed.json()[0]["is_stale"] is True


@pytest.mark.parametrize("surface", ["list", "continuation"])
def test_summary_freshness_reads_overlapping_chapters_once(db, novel, user, surface, monkeypatch):
    from app.api.novel_context_summaries import list_context_summaries
    from app.api.novel_continuation_context import _format_selected_context_summaries
    from app.core import context_summaries

    rows = [
        _fresh_summary(db, novel, start_chapter=start, end_chapter=end)
        for start, end in [(1, 2), (1, 1), (2, 2), (1, 2)]
    ]
    novel_id = novel.id
    summary_ids = [row.id for row in rows]
    chapter_queries = []
    formatted_chapters = []
    original_format = context_summaries.format_recent_chapters_for_prompt

    def format_once(chapters, **kwargs):
        formatted_chapters.extend(chapter.chapter_number for chapter in chapters)
        return original_format(chapters, **kwargs)

    monkeypatch.setattr(context_summaries, "format_recent_chapters_for_prompt", format_once)

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "from chapters" in statement.lower():
            chapter_queries.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        if surface == "list":
            result = list_context_summaries(novel_id, db, user)
            assert all(not item["is_stale"] for item in result)
        else:
            _format_selected_context_summaries(
                db,
                novel_id=novel_id,
                context_summary_ids=summary_ids,
                locale=novel.language,
            )
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert len(chapter_queries) == 1
    assert formatted_chapters == [1, 2]


@pytest.mark.parametrize("locale", ["zh", "en", "ja", "ko"])
def test_batched_summary_freshness_preserves_ranges_gaps_and_markdown(db, novel, user, locale):
    from app.api.novel_context_summaries import list_context_summaries

    novel.language = locale
    db.add(Chapter(
        novel_id=novel.id,
        chapter_number=4,
        title="",
        source_chapter_label="第四回：原始标签",
        content="",
    ))
    db.commit()
    whole = _fresh_summary(db, novel, end_chapter=4)
    first = _fresh_summary(db, novel, start_chapter=1, end_chapter=1)
    second = _fresh_summary(db, novel, start_chapter=2, end_chapter=2)
    blank = _fresh_summary(db, novel, start_chapter=4, end_chapter=4)
    empty = _fresh_summary(db, novel, start_chapter=8, end_chapter=9)
    expected = {whole.id: False, first.id: False, second.id: False, blank.id: False, empty.id: True}
    result = list_context_summaries(novel.id, db, user)
    assert {item["id"]: item["is_stale"] for item in result} == expected

    blank_chapter = db.query(Chapter).filter_by(novel_id=novel.id, chapter_number=4).one()
    blank_chapter.source_chapter_label = "Updated source label"
    db.commit()
    result = list_context_summaries(novel.id, db, user)
    assert {item["id"]: item["is_stale"] for item in result} == expected

    chapter = db.query(Chapter).filter_by(novel_id=novel.id, chapter_number=2).one()
    db.delete(chapter)
    db.commit()
    expected[whole.id] = True
    expected[second.id] = True
    result = list_context_summaries(novel.id, db, user)
    assert {item["id"]: item["is_stale"] for item in result} == expected

    blank_chapter.title = "Changed heading"
    db.commit()
    expected[blank.id] = True
    result = list_context_summaries(novel.id, db, user)
    assert {item["id"]: item["is_stale"] for item in result} == expected


def test_summary_batch_does_not_read_chapters_between_distant_ranges(db, novel, user):
    from app.api.novel_context_summaries import list_context_summaries

    db.add_all([
        Chapter(novel_id=novel.id, chapter_number=500, title="Unselected", content="unrelated"),
        Chapter(novel_id=novel.id, chapter_number=1000, title="Selected", content="related"),
    ])
    db.commit()
    _fresh_summary(db, novel)
    _fresh_summary(db, novel, start_chapter=1000, end_chapter=1000)
    novel_id = novel.id
    db.expunge_all()
    loaded = []

    def capture(chapter, _context):
        loaded.append(chapter.chapter_number)

    event.listen(Chapter, "load", capture)
    try:
        result = list_context_summaries(novel_id, db, user)
    finally:
        event.remove(Chapter, "load", capture)
    assert all(not row["is_stale"] for row in result)
    assert loaded == [1, 2, 1000]


def test_update_allows_edit_and_confirm_only_when_source_is_fresh(client, db, novel):
    row = _fresh_summary(db, novel, review_status="draft")
    confirmed = client.put(
        f"/api/novels/{novel.id}/context-summaries/{row.id}",
        json={"content": "作者审核后的回顾", "review_status": "confirmed"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["content"] == "作者审核后的回顾"
    assert confirmed.json()["review_status"] == "confirmed"

    chapter = db.query(Chapter).filter_by(novel_id=novel.id, chapter_number=2).one()
    chapter.content = "正文已经改写。"
    db.commit()
    rejected = client.put(
        f"/api/novels/{novel.id}/context-summaries/{row.id}",
        json={"content": "试图继续确认", "review_status": "confirmed"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "context_summary_stale"


def test_regenerate_refreshes_fingerprint_and_resets_review(client, db, novel, monkeypatch):
    from app.api import novel_context_summaries as summaries_api

    row = _fresh_summary(db, novel)
    previous_fingerprint = row.source_fingerprint
    chapter = db.query(Chapter).filter_by(novel_id=novel.id, chapter_number=2).one()
    chapter.content = "改写后的门后场景。"
    db.commit()

    async def generate(*_args, **_kwargs) -> str:
        return "根据改写正文生成的新回顾。"

    monkeypatch.setattr(summaries_api.AIClient, "generate", generate)
    response = client.post(
        f"/api/novels/{novel.id}/context-summaries/{row.id}/regenerate"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["content"] == "根据改写正文生成的新回顾。"
    assert payload["review_status"] == "draft"
    assert payload["is_stale"] is False
    db.refresh(row)
    assert row.source_fingerprint != previous_fingerprint


def test_generation_rejects_oversized_source_before_llm(client, novel, monkeypatch):
    from app.api import novel_context_summaries as summaries_api

    settings = Settings(
        deploy_mode="selfhost",
        openai_base_url="https://example.com/v1",
        openai_api_key="test-key",
        openai_model="test-model",
        context_summary_source_max_chars=10,
        _env_file=None,
    )
    monkeypatch.setattr(summaries_api, "get_settings", lambda: settings)
    generate = AsyncMock(side_effect=AssertionError("oversized source must not reach the LLM"))
    monkeypatch.setattr(summaries_api.AIClient, "generate", generate)

    response = client.post(
        f"/api/novels/{novel.id}/context-summaries",
        json={"start_chapter": 1, "end_chapter": 2},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "context_summary_source_too_large"
    generate.assert_not_awaited()


def test_generation_preserves_busy_retry_header_without_reserving_quota(
    client,
    novel,
    monkeypatch,
):
    from app.api import novel_context_summaries as summaries_api

    async def busy() -> None:
        raise HTTPException(
            status_code=503,
            detail={"code": "llm_busy", "message": "busy"},
            headers={"Retry-After": "5"},
        )

    generate = AsyncMock()
    monkeypatch.setattr(summaries_api, "acquire_llm_slot", busy)
    monkeypatch.setattr(summaries_api.AIClient, "generate", generate)
    response = client.post(
        f"/api/novels/{novel.id}/context-summaries",
        json={"start_chapter": 1, "end_chapter": 2},
    )
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    generate.assert_not_awaited()


def test_delete_context_summary_is_novel_scoped(client, db, novel):
    row = _fresh_summary(db, novel)
    response = client.delete(f"/api/novels/{novel.id}/context-summaries/{row.id}")
    assert response.status_code == 200
    assert db.get(NovelContextSummary, row.id) is None


def test_selected_context_summaries_must_be_confirmed_fresh_ordered_and_bounded(
    db,
    novel,
    monkeypatch,
):
    from app.api import novel_continuation_context as context_api

    first = _fresh_summary(
        db,
        novel,
        start_chapter=1,
        end_chapter=1,
        content="第一段",
    )
    second = _fresh_summary(
        db,
        novel,
        start_chapter=2,
        end_chapter=2,
        content="第二段",
    )
    context, labels = context_api._format_selected_context_summaries(
        db,
        novel_id=novel.id,
        context_summary_ids=[second.id, first.id],
        locale="zh",
    )
    assert context.index("第二段") < context.index("第一段")
    assert labels == ["第2—2章远期剧情回顾", "第1—1章远期剧情回顾"]

    first.review_status = "draft"
    db.commit()
    with pytest.raises(HTTPException) as unconfirmed:
        context_api._format_selected_context_summaries(
            db,
            novel_id=novel.id,
            context_summary_ids=[first.id],
            locale="zh",
        )
    assert unconfirmed.value.detail["code"] == "context_summary_unconfirmed"

    first.review_status = "confirmed"
    db.commit()
    settings = Settings(
        deploy_mode="selfhost",
        openai_base_url="https://example.com/v1",
        openai_api_key="test-key",
        openai_model="test-model",
        context_summary_injection_max_chars=20,
        _env_file=None,
    )
    monkeypatch.setattr(context_api, "get_settings", lambda: settings)
    with pytest.raises(HTTPException) as oversized:
        context_api._format_selected_context_summaries(
            db,
            novel_id=novel.id,
            context_summary_ids=[first.id, second.id],
            locale="zh",
        )
    assert oversized.value.detail["code"] == "context_summary_context_too_large"


def test_prepare_context_keeps_recaps_separate_and_reports_debug(db, novel, user, monkeypatch):
    from app.api import novel_continuation_context as context_api
    from app.schemas import ContinueRequest

    summary = _fresh_summary(db, novel, content="这段回顾由作者确认。")
    monkeypatch.setattr(
        context_api,
        "assemble_writer_context",
        lambda *_args, **_kwargs: {"systems": [], "entities": [], "relationships": []},
    )
    prepared = context_api._prepare_continuation_context(
        db,
        novel.id,
        ContinueRequest(context_summary_ids=[summary.id]),
        user,
    )
    assert "这段回顾由作者确认" in prepared.chapter_recaps
    assert "这段回顾由作者确认" not in prepared.world_context
    assert prepared.debug_summary.injected_context_summaries == ["第1—2章远期剧情回顾"]

    chapter = db.query(Chapter).filter_by(novel_id=novel.id, chapter_number=1).one()
    chapter.content = "修改后正文"
    db.commit()
    with pytest.raises(HTTPException) as stale:
        context_api._prepare_continuation_context(
            db,
            novel.id,
            ContinueRequest(context_summary_ids=[summary.id]),
            user,
        )
    assert stale.value.detail["code"] == "context_summary_stale"
