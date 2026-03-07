"""
Tests for POST /novels/{novel_id}/continue.

Focus:
- WorldModel context injection is assembled and injected into the prompt
- context_chapters overrides settings.max_context_chapters

Network calls are avoided by mocking ai_client.generate.
"""

import pytest
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import (
    Chapter,
    Continuation,
    Novel,
    WorldEntity,
    WorldRelationship,
    WorldSystem,
)


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def novel(db):
    n = Novel(title="逆天邪神", author="火星引力", file_path="/tmp/test.txt", total_chapters=2)
    db.add(n)
    db.commit()
    db.refresh(n)

    db.add_all(
        [
            Chapter(novel_id=n.id, chapter_number=1, title="第一章", content="云澈踏入宗门，心如止水。"),
            Chapter(novel_id=n.id, chapter_number=2, title="第二章", content="楚月仙在大殿中静坐，气息如渊。"),
        ]
    )
    db.commit()
    return n


@pytest.fixture
def world(db, novel):
    yunche = WorldEntity(
        novel_id=novel.id,
        name="云澈",
        entity_type="Character",
        description="主角",
        status="confirmed",
    )
    chuyuexian = WorldEntity(
        novel_id=novel.id,
        name="楚月仙",
        entity_type="Character",
        description="师父",
        status="confirmed",
    )
    db.add_all([yunche, chuyuexian])
    db.commit()
    db.refresh(yunche)
    db.refresh(chuyuexian)

    rel = WorldRelationship(
        novel_id=novel.id,
        source_id=yunche.id,
        target_id=chuyuexian.id,
        label="师徒",
        description="共同修炼",
        visibility="active",
        status="confirmed",
    )
    system = WorldSystem(
        novel_id=novel.id,
        name="修炼体系",
        display_type="list",
        description="玄气修炼等级",
        data={"items": [{"label": "真玄境", "visibility": "active"}]},
        constraints=["突破需要契机"],
        visibility="active",
        status="confirmed",
    )
    db.add_all([rel, system])
    db.commit()
    return {"yunche": yunche, "chuyuexian": chuyuexian}


@pytest.fixture
def client(db, monkeypatch):
    from app.api import novels

    test_app = FastAPI()
    test_app.include_router(novels.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db

    from app.core.auth import get_current_user_or_default, check_generation_quota
    from app.models import User

    fake_user = User(
        id=1, username="t", hashed_password="x", role="admin", is_active=True,
        generation_quota=999, feedback_submitted=False,
    )
    test_app.dependency_overrides[get_current_user_or_default] = lambda: fake_user
    test_app.dependency_overrides[check_generation_quota] = lambda: fake_user

    captured: dict[str, object] = {}

    async def fake_generate(prompt: str, system_prompt: str = "", max_tokens: int = 0, **kwargs) -> str:
        captured["prompt"] = prompt
        captured["system_prompt"] = system_prompt
        captured["max_tokens"] = max_tokens
        captured["kwargs"] = kwargs
        return "续写内容"

    async def fake_generate_stream(prompt: str, system_prompt: str = "", max_tokens: int = 0, **kwargs):
        captured["stream_prompt"] = prompt
        captured["stream_system_prompt"] = system_prompt
        captured["stream_max_tokens"] = max_tokens
        captured["stream_kwargs"] = kwargs
        # Two chunks to simulate incremental streaming.
        yield "续"
        yield "写"

    import app.core.generator as generator_mod

    monkeypatch.setattr(generator_mod.ai_client, "generate", fake_generate)
    monkeypatch.setattr(generator_mod.ai_client, "generate_stream", fake_generate_stream)

    with TestClient(test_app) as c:
        yield c, captured
    test_app.dependency_overrides.clear()


class TestContinueEndpoint:
    def test_injects_world_context_and_returns_debug(self, client, db, novel, world):
        c, captured = client

        resp = c.post(
            f"/api/novels/{novel.id}/continue",
            json={"num_versions": 1, "context_chapters": 2},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["continuations"]) == 1
        assert data["continuations"][0]["chapter_number"] == 3

        debug = data["debug"]
        assert debug["context_chapters"] == 2
        assert "修炼体系" in debug["injected_systems"]
        assert "云澈" in debug["injected_entities"]
        assert "楚月仙" in debug["injected_entities"]
        assert any("师徒" in r for r in debug["injected_relationships"])

        prompt_used = str(captured.get("prompt") or "")
        assert "<world_knowledge>" in prompt_used
        assert "修炼体系" in prompt_used
        assert "云澈" in prompt_used
        assert "楚月仙" in prompt_used

        # Also persisted to DB for traceability.
        cont = db.query(Continuation).filter(Continuation.novel_id == novel.id).one()
        assert "<world_knowledge>" in cont.prompt_used

    def test_context_chapters_override_affects_relevance(self, client, novel, world):
        c, captured = client

        # Only use the last chapter. It mentions 楚月仙 but not 云澈.
        resp = c.post(
            f"/api/novels/{novel.id}/continue",
            json={"context_chapters": 1},
        )
        assert resp.status_code == 200
        data = resp.json()

        debug = data["debug"]
        assert debug["context_chapters"] == 1
        assert debug["injected_entities"] == ["楚月仙"]
        assert debug["injected_relationships"] == []

        prompt_used = str(captured.get("prompt") or "")
        assert "楚月仙" in prompt_used
        assert "云澈" not in debug["injected_entities"]

    def test_user_prompt_is_part_of_relevance_signal(self, client, novel, world):
        c, captured = client

        # context_chapters=1 would normally exclude 云澈, but the user instruction mentions him.
        resp = c.post(
            f"/api/novels/{novel.id}/continue",
            json={"context_chapters": 1, "prompt": "请继续写云澈的内心戏"},
        )
        assert resp.status_code == 200
        data = resp.json()

        debug = data["debug"]
        assert "楚月仙" in debug["injected_entities"]
        assert "云澈" in debug["injected_entities"]

        prompt_used = str(captured.get("prompt") or "")
        assert "<world_knowledge>" in prompt_used
        assert "云澈" in prompt_used

    def test_context_chapters_above_cap_falls_back_to_five(self, client, db, novel):
        c, _captured = client

        for idx in range(3, 8):
            db.add(
                Chapter(
                    novel_id=novel.id,
                    chapter_number=idx,
                    title=f"第{idx}章",
                    content=f"这是第 {idx} 章内容。",
                )
            )
        db.commit()

        resp = c.post(
            f"/api/novels/{novel.id}/continue",
            json={"context_chapters": 99},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["debug"]["context_chapters"] == 5


class TestContinueStreamEndpoint:
    def test_stream_yields_ndjson_events_and_includes_variant_content(self, client, novel):
        c, captured = client

        headers = {
            "x-llm-base-url": "https://user.example.com/v1",
            "x-llm-api-key": "user-key",
            "x-llm-model": "user-model",
        }
        resp = c.post(
            f"/api/novels/{novel.id}/continue/stream",
            json={"num_versions": 2, "context_chapters": 2},
            headers=headers,
        )
        assert resp.status_code == 200

        lines = [ln for ln in resp.text.splitlines() if ln.strip()]
        events = [json.loads(ln) for ln in lines]

        assert events[0]["type"] == "start"
        assert events[0]["total_variants"] == 2

        token_text = "".join(e["content"] for e in events if e["type"] == "token" and e["variant"] == 0)
        assert token_text == "续写"

        done0 = next(e for e in events if e["type"] == "variant_done" and e["variant"] == 0)
        done1 = next(e for e in events if e["type"] == "variant_done" and e["variant"] == 1)
        assert done0["content"] == "续写"
        assert done1["content"] == "续写内容"

        done = next(e for e in events if e["type"] == "done")
        assert done["continuation_ids"] == [done0["continuation_id"], done1["continuation_id"]]

        # BYOK headers are passed through to both streaming and non-streaming generation calls.
        assert captured.get("stream_kwargs", {}).get("base_url") == "https://user.example.com/v1"
        assert captured.get("stream_kwargs", {}).get("api_key") == "user-key"
        assert captured.get("stream_kwargs", {}).get("model") == "user-model"

        assert captured.get("kwargs", {}).get("base_url") == "https://user.example.com/v1"
        assert captured.get("kwargs", {}).get("api_key") == "user-key"
        assert captured.get("kwargs", {}).get("model") == "user-model"

    def test_get_continuations_preserves_requested_order(self, client, novel):
        c, _ = client

        resp = c.post(
            f"/api/novels/{novel.id}/continue/stream",
            json={"num_versions": 2, "context_chapters": 2},
        )
        assert resp.status_code == 200
        events = [json.loads(ln) for ln in resp.text.splitlines() if ln.strip()]
        done0 = next(e for e in events if e["type"] == "variant_done" and e["variant"] == 0)
        done1 = next(e for e in events if e["type"] == "variant_done" and e["variant"] == 1)

        resp2 = c.get(f"/api/novels/{novel.id}/continuations?ids={done1['continuation_id']},{done0['continuation_id']}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert [row["id"] for row in data] == [done1["continuation_id"], done0["continuation_id"]]

    def test_stream_strips_thinking_blocks_from_non_stream_variants(self, client, novel, monkeypatch):
        c, _ = client

        import app.core.generator as generator_mod

        async def fake_generate(prompt: str, system_prompt: str = "", max_tokens: int = 0, **kwargs) -> str:
            return "<think>Step-by-step reasoning...</think>\n续写内容"

        monkeypatch.setattr(generator_mod.ai_client, "generate", fake_generate)

        resp = c.post(
            f"/api/novels/{novel.id}/continue/stream",
            json={"num_versions": 2, "context_chapters": 2},
        )
        assert resp.status_code == 200

        events = [json.loads(ln) for ln in resp.text.splitlines() if ln.strip()]
        done1 = next(e for e in events if e["type"] == "variant_done" and e["variant"] == 1)
        assert done1["content"] == "续写内容"


class TestTemperaturePassthrough:
    def test_temperature_passed_to_generate(self, client, novel):
        c, captured = client

        resp = c.post(
            f"/api/novels/{novel.id}/continue",
            json={"num_versions": 1, "context_chapters": 2, "temperature": 1.5},
        )
        assert resp.status_code == 200
        assert captured["kwargs"]["temperature"] == 1.5

    def test_temperature_passed_to_stream(self, client, novel):
        c, captured = client

        resp = c.post(
            f"/api/novels/{novel.id}/continue/stream",
            json={"num_versions": 1, "context_chapters": 2, "temperature": 0.3},
        )
        assert resp.status_code == 200
        assert captured["stream_kwargs"]["temperature"] == 0.3

    def test_temperature_omitted_uses_default(self, client, novel):
        c, captured = client

        resp = c.post(
            f"/api/novels/{novel.id}/continue",
            json={"num_versions": 1, "context_chapters": 2},
        )
        assert resp.status_code == 200
        # temperature should NOT appear in kwargs when not provided
        assert "temperature" not in captured["kwargs"]

    def test_temperature_validation_rejects_out_of_range(self, client, novel):
        c, _ = client

        resp = c.post(
            f"/api/novels/{novel.id}/continue",
            json={"num_versions": 1, "temperature": -0.1},
        )
        assert resp.status_code == 422

        resp = c.post(
            f"/api/novels/{novel.id}/continue",
            json={"num_versions": 1, "temperature": 2.1},
        )
        assert resp.status_code == 422
