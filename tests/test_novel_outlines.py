from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.core.auth import get_current_user_or_default
from app.core.llm_config import ResolvedLlmConfig
from app.core.llm_request import get_llm_config
from app.database import Base, get_db
from app.models import Chapter, Novel, NovelOutline, User


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
        username="outline-user",
        hashed_password="x",
        role="admin",
        is_active=True,
        generation_quota=5,
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
        file_path="/tmp/outline.md",
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
    from app.api import novel_outlines as outlines_api

    test_app = FastAPI()
    test_app.include_router(outlines_api.router)

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

    monkeypatch.setattr(outlines_api, "acquire_llm_slot", acquire)
    monkeypatch.setattr(outlines_api, "release_llm_slot", lambda: None)

    with TestClient(test_app) as test_client:
        yield test_client
    test_app.dependency_overrides.clear()


def test_create_outline_preserves_markdown_source_and_persists_result(
    client,
    db,
    novel,
    monkeypatch,
):
    from app.api import novel_outlines as outlines_api

    captured: dict[str, object] = {}

    async def generate(_self, prompt: str, **kwargs) -> str:
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return "主角取得旧钥匙，并听见门后的回声。"

    monkeypatch.setattr(outlines_api.AIClient, "generate", generate)

    response = client.post(
        f"/api/novels/{novel.id}/outlines",
        json={"start_chapter": 1, "end_chapter": 2},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "第1—2章剧情大纲"
    assert payload["content"] == "主角取得旧钥匙，并听见门后的回声。"
    assert "### 场景" in str(captured["prompt"])
    assert "**旧钥匙**" in str(captured["prompt"])
    assert captured["kwargs"]["max_tokens"] == 4000
    assert db.query(NovelOutline).filter_by(novel_id=novel.id).count() == 1


def test_create_outline_rejects_oversized_source_before_calling_llm(
    client,
    novel,
    monkeypatch,
):
    from app.api import novel_outlines as outlines_api

    settings = Settings(
        deploy_mode="selfhost",
        openai_base_url="https://example.com/v1",
        openai_api_key="test-key",
        openai_model="test-model",
        outline_source_max_chars=10,
        _env_file=None,
    )
    monkeypatch.setattr(outlines_api, "get_settings", lambda: settings)
    generate = AsyncMock(side_effect=AssertionError("oversized source must not reach the LLM"))
    monkeypatch.setattr(outlines_api.AIClient, "generate", generate)

    response = client.post(
        f"/api/novels/{novel.id}/outlines",
        json={"start_chapter": 1, "end_chapter": 2},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "outline_source_too_large"
    generate.assert_not_awaited()


def test_create_outline_refunds_failed_generation_and_releases_slot(
    client,
    novel,
    monkeypatch,
):
    from app.api import novel_outlines as outlines_api
    from app.core.ai_client import LLMUnavailableError

    lifecycle: list[str] = []

    class FakeQuotaScope:
        def __init__(self, *_args, **_kwargs):
            pass

        def reserve(self) -> None:
            lifecycle.append("reserve")

        def charge(self, _count: int) -> None:
            lifecycle.append("charge")

        def finalize(self) -> None:
            lifecycle.append("finalize")

    async def unavailable(*_args, **_kwargs) -> str:
        raise LLMUnavailableError("provider down")

    monkeypatch.setattr(outlines_api, "QuotaScope", FakeQuotaScope)
    monkeypatch.setattr(outlines_api.AIClient, "generate", unavailable)
    monkeypatch.setattr(
        outlines_api,
        "release_llm_slot",
        lambda: lifecycle.append("release"),
    )

    response = client.post(
        f"/api/novels/{novel.id}/outlines",
        json={"start_chapter": 1, "end_chapter": 2},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "outline_generation_llm_unavailable"
    assert lifecycle == ["reserve", "finalize", "release"]


def test_create_outline_preserves_busy_retry_header_without_reserving_quota(
    client,
    novel,
    monkeypatch,
):
    from app.api import novel_outlines as outlines_api

    async def busy() -> None:
        raise HTTPException(
            status_code=503,
            detail={"code": "llm_busy", "message": "busy"},
            headers={"Retry-After": "5"},
        )

    reserve = AsyncMock()
    monkeypatch.setattr(outlines_api, "acquire_llm_slot", busy)
    monkeypatch.setattr(outlines_api.AIClient, "generate", reserve)

    response = client.post(
        f"/api/novels/{novel.id}/outlines",
        json={"start_chapter": 1, "end_chapter": 2},
    )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    reserve.assert_not_awaited()


def test_delete_outline_is_novel_scoped(client, db, novel):
    row = NovelOutline(
        novel_id=novel.id,
        start_chapter=1,
        end_chapter=2,
        title="待删除",
        content="摘要",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    response = client.delete(f"/api/novels/{novel.id}/outlines/{row.id}")

    assert response.status_code == 200
    assert db.get(NovelOutline, row.id) is None


def test_selected_outline_context_is_ordered_and_bounded(db, novel, monkeypatch):
    from app.api import novel_continuation_context as context_api

    first = NovelOutline(
        novel_id=novel.id,
        start_chapter=1,
        end_chapter=1,
        title="一",
        content="第一段",
    )
    second = NovelOutline(
        novel_id=novel.id,
        start_chapter=2,
        end_chapter=2,
        title="二",
        content="第二段",
    )
    db.add_all([first, second])
    db.commit()
    db.refresh(first)
    db.refresh(second)

    context = context_api._format_selected_outlines(
        db,
        novel_id=novel.id,
        outline_ids=[second.id, first.id],
        locale="zh",
    )
    assert context.index("第二段") < context.index("第一段")

    settings = Settings(
        deploy_mode="selfhost",
        openai_base_url="https://example.com/v1",
        openai_api_key="test-key",
        openai_model="test-model",
        outline_context_max_chars=20,
        _env_file=None,
    )
    monkeypatch.setattr(context_api, "get_settings", lambda: settings)
    with pytest.raises(HTTPException) as exc_info:
        context_api._format_selected_outlines(
            db,
            novel_id=novel.id,
            outline_ids=[first.id, second.id],
            locale="zh",
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "outline_context_too_large"


def test_outline_injection_reduces_world_context_budget(
    db,
    novel,
    user,
    monkeypatch,
):
    from app.api import novel_continuation_context as context_api
    from app.core.context_assembly import DEFAULT_WORLD_CONTEXT_TOKEN_BUDGET
    from app.schemas import ContinueRequest

    outline = NovelOutline(
        novel_id=novel.id,
        start_chapter=1,
        end_chapter=2,
        title="范围大纲",
        content="这一段大纲会占用统一的上下文预算。",
    )
    db.add(outline)
    db.commit()
    db.refresh(outline)

    captured: dict[str, int] = {}
    monkeypatch.setattr(
        context_api,
        "assemble_writer_context",
        lambda *_args, **_kwargs: {"systems": [], "entities": [], "relationships": []},
    )

    def apply_budget(writer_ctx, *, max_estimated_tokens: int):
        captured["budget"] = max_estimated_tokens
        return writer_ctx

    monkeypatch.setattr(context_api, "apply_writer_context_budget", apply_budget)

    prepared = context_api._prepare_continuation_context(
        db,
        novel.id,
        ContinueRequest(outline_ids=[outline.id]),
        user,
    )

    assert "这一段大纲" in prepared.world_context
    assert captured["budget"] == (
        DEFAULT_WORLD_CONTEXT_TOKEN_BUDGET
        - len(
            context_api._format_selected_outlines(
                db,
                novel_id=novel.id,
                outline_ids=[outline.id],
                locale=novel.language,
            )
        )
    )
