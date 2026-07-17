"""
Tests for world generation endpoint:

POST /api/novels/{novel_id}/world/generate
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base, get_db
from app.core.text import PromptKey
from app.core.llm_config import ResolvedLlmConfig
from app.models import Novel, WorldEntity, WorldRelationship, WorldSystem, User


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _selfhost_settings(**overrides) -> Settings:
    return Settings(
        deploy_mode="selfhost",
        openai_base_url="https://example.com/v1",
        openai_api_key="test-key",
        openai_model="test-model",
        _env_file=None,
        **overrides,
    )


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
    n = Novel(title="测试小说", author="测试作者", file_path="/tmp/test.txt", total_chapters=1)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture
def client(db):
    from app.api import world
    from app.core.auth import get_current_user_or_default, check_generation_quota

    test_app = FastAPI()
    test_app.include_router(world.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    fake_user = User(
        id=1,
        username="testuser",
        hashed_password="x",
        role="admin",
        is_active=True,
        generation_quota=999,
        feedback_submitted=False,
    )

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user_or_default] = lambda: fake_user
    test_app.dependency_overrides[check_generation_quota] = lambda: fake_user

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


def test_generate_world_creates_drafts_and_summary(client, db, novel, monkeypatch):
    from app.core.ai_client import ai_client
    from app.core.world.gen import (
        WorldGenEntity,
        WorldGenLLMOutput,
        WorldGenRelationship,
        WorldGenSystem,
        WorldGenSystemItem,
    )

    llm_output = WorldGenLLMOutput(
        entities=[
            WorldGenEntity(name="云澈", entity_type="Character", description="主角", aliases=["小澈"]),
            WorldGenEntity(name="苍风帝国", entity_type="Faction", description="势力", aliases=[]),
        ],
        relationships=[
            WorldGenRelationship(source="云澈", target="苍风帝国", label="来自", description="出身于此"),
        ],
        systems=[
            WorldGenSystem(
                name="修炼体系",
                description="境界划分",
                items=[WorldGenSystemItem(label="真玄境", description="基础境界")],
                constraints=["不要随意改变修炼等级设定"],
            ),
        ],
    )

    mock = AsyncMock(return_value=llm_output)
    monkeypatch.setattr(ai_client, "generate_structured", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["entities_created"] == 2
    assert data["relationships_created"] == 1
    assert data["systems_created"] == 1
    assert isinstance(data.get("warnings"), list)

    entities = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).order_by(WorldEntity.id.asc()).all()
    assert len(entities) == 2
    assert {e.name for e in entities} == {"云澈", "苍风帝国"}
    assert all(e.status == "draft" for e in entities)
    assert all(e.origin == "worldgen" for e in entities)

    rels = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id).all()
    assert len(rels) == 1
    assert rels[0].visibility == "reference"
    assert rels[0].origin == "worldgen"
    assert rels[0].status == "draft"

    # Relationship resolution: src/tgt IDs should point to the created entities.
    id_to_name = {e.id: e.name for e in entities}
    assert id_to_name[rels[0].source_id] == "云澈"
    assert id_to_name[rels[0].target_id] == "苍风帝国"

    systems = db.query(WorldSystem).filter(WorldSystem.novel_id == novel.id).all()
    assert len(systems) == 1
    assert systems[0].display_type == "list"
    assert systems[0].visibility == "reference"
    assert systems[0].origin == "worldgen"
    assert systems[0].status == "draft"


@pytest.mark.asyncio
async def test_generate_world_drafts_uses_novel_language_for_prompt_locale(db, novel, monkeypatch):
    from app.core.world import gen as world_gen_mod

    novel.language = "en-US"
    db.commit()

    seen_locales: list[tuple[PromptKey, str | None]] = []

    def fake_get_prompt(key: PromptKey, *, locale: str | None = None, provider: str | None = None) -> str:
        del provider
        seen_locales.append((key, locale))
        if key == PromptKey.WORLD_GEN_SYSTEM:
            return "system prompt"
        if key == PromptKey.WORLD_GEN:
            return "{chunk_directive}\n{text}"
        raise AssertionError(f"unexpected key: {key}")

    monkeypatch.setattr(world_gen_mod, "get_prompt", fake_get_prompt)
    monkeypatch.setattr(
        world_gen_mod.ai_client,
        "generate_structured",
        AsyncMock(return_value=world_gen_mod.WorldGenLLMOutput()),
    )

    result = await world_gen_mod.generate_world_drafts(
        db=db,
        novel_id=novel.id,
        text="This world setting text is intentionally long enough to trigger the generation path.",
        llm_config=ResolvedLlmConfig(
            base_url="https://example.com/v1",
            api_key="key",
            model="model",
            billing_source_hint="selfhost",
            source="selfhost_settings",
        ),
    )

    assert result.entities_created == 0
    assert (PromptKey.WORLD_GEN, "en-us") in seen_locales
    assert (PromptKey.WORLD_GEN_SYSTEM, "en-us") in seen_locales


def test_generate_world_orphan_relationships_are_dropped_with_warning(client, db, novel, monkeypatch):
    from app.core.ai_client import ai_client
    from app.core.world.gen import WorldGenEntity, WorldGenLLMOutput, WorldGenRelationship

    llm_output = WorldGenLLMOutput(
        entities=[
            WorldGenEntity(name="云澈", entity_type="Character"),
        ],
        relationships=[
            WorldGenRelationship(source="云澈", target="不存在", label="敌对", description="并不存在的对象"),
        ],
        systems=[],
    )

    mock = AsyncMock(return_value=llm_output)
    monkeypatch.setattr(ai_client, "generate_structured", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["entities_created"] == 1
    assert data["relationships_created"] == 0
    assert any(w.get("code") == "orphan_relationship_dropped" for w in data.get("warnings", []))

    rels = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id).all()
    assert rels == []


def test_generate_world_systems_default_to_list_type(client, db, novel, monkeypatch):
    from app.core.ai_client import ai_client
    from app.core.world.gen import WorldGenLLMOutput, WorldGenSystem

    llm_output = WorldGenLLMOutput(
        entities=[],
        relationships=[],
        systems=[WorldGenSystem(name="世界规则", description="一些规则")],
    )

    mock = AsyncMock(return_value=llm_output)
    monkeypatch.setattr(ai_client, "generate_structured", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 200

    systems = db.query(WorldSystem).filter(WorldSystem.novel_id == novel.id).all()
    assert len(systems) == 1
    assert systems[0].display_type == "list"


def test_worldgen_output_normalizes_unknown_system_display_type_to_list():
    from app.core.world.gen import WorldGenLLMOutput

    parsed = WorldGenLLMOutput.model_validate(
        {
            "systems": [
                {
                    "name": "世界规则",
                    "display_type": "graph",
                    "items": [{"label": "法则"}],
                }
            ]
        }
    )

    assert parsed.systems[0].display_type == "list"


def test_generate_world_persists_timeline_systems_and_skips_missing_time(client, db, novel, monkeypatch):
    from app.core.ai_client import ai_client
    from app.core.world.gen import WorldGenLLMOutput, WorldGenSystem, WorldGenSystemItem

    llm_output = WorldGenLLMOutput(
        entities=[],
        relationships=[],
        systems=[
            WorldGenSystem(
                name="历史年表",
                display_type="timeline",
                description="王朝关键节点",
                items=[
                    WorldGenSystemItem(time="上古纪元", label="灵气初开", description="天地初分"),
                    WorldGenSystemItem(label="无时间事件", description="应被跳过"),
                ],
            )
        ],
    )

    mock = AsyncMock(return_value=llm_output)
    monkeypatch.setattr(ai_client, "generate_structured", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 200
    payload = resp.json()
    warning = next(w for w in payload.get("warnings", []) if w.get("code") == "system_item_skipped")
    assert warning["message_key"] == "world.generate.warning.system_item_missing_time"
    assert warning["message_params"] == {"display_type": "timeline"}

    systems = db.query(WorldSystem).filter(WorldSystem.novel_id == novel.id).all()
    assert len(systems) == 1
    assert systems[0].display_type == "timeline"
    assert systems[0].data == {
        "events": [
            {
                "time": "上古纪元",
                "label": "灵气初开",
                "description": "天地初分",
                "visibility": "reference",
            }
        ]
    }


def test_generate_world_persists_hierarchy_systems_with_generated_ids(client, db, novel, monkeypatch):
    from app.core.ai_client import ai_client
    from app.core.world.gen import WorldGenLLMOutput, WorldGenSystem, WorldGenSystemItem

    llm_output = WorldGenLLMOutput(
        entities=[],
        relationships=[],
        systems=[
            WorldGenSystem(
                name="宗门架构",
                display_type="hierarchy",
                items=[
                    WorldGenSystemItem(
                        label="外门",
                        children=[
                            WorldGenSystemItem(label="弟子"),
                            WorldGenSystemItem(label="执事"),
                        ],
                    ),
                    WorldGenSystemItem(label="内门"),
                ],
            )
        ],
    )

    mock = AsyncMock(return_value=llm_output)
    monkeypatch.setattr(ai_client, "generate_structured", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 200

    systems = db.query(WorldSystem).filter(WorldSystem.novel_id == novel.id).all()
    assert len(systems) == 1
    assert systems[0].display_type == "hierarchy"
    assert [node["label"] for node in systems[0].data["nodes"]] == ["外门", "内门"]

    outer = systems[0].data["nodes"][0]
    assert outer["visibility"] == "reference"
    assert outer["id"].startswith("wg_")
    assert [child["label"] for child in outer["children"]] == ["弟子", "执事"]
    assert all(child["visibility"] == "reference" for child in outer["children"])
    assert all(child["id"].startswith("wg_") for child in outer["children"])


def test_generate_world_dedupes_relationships_and_systems(client, db, novel, monkeypatch):
    from app.core.ai_client import ai_client
    from app.core.world.gen import (
        WorldGenEntity,
        WorldGenLLMOutput,
        WorldGenRelationship,
        WorldGenSystem,
        WorldGenSystemItem,
    )

    llm_output = WorldGenLLMOutput(
        entities=[
            WorldGenEntity(name="云澈", entity_type="Character"),
            WorldGenEntity(name="苍风帝国", entity_type="Faction"),
        ],
        relationships=[
            WorldGenRelationship(source="云澈", target="苍风帝国", label="来自", description="出身于此"),
            # Same triple after normalization (whitespace) and canonicalization ("关系" suffix).
            WorldGenRelationship(source="云澈", target="苍风帝国", label=" 来自 ", description="重复"),
            WorldGenRelationship(source="云澈", target="苍风帝国", label="来自关系", description="重复"),
        ],
        systems=[
            WorldGenSystem(
                name="修炼体系",
                items=[
                    WorldGenSystemItem(label="真玄境", description="基础境界"),
                    WorldGenSystemItem(label="真玄境", description="重复"),
                ],
                constraints=[
                    "不要随意改变修炼等级设定",
                    "不要随意改变修炼等级设定",
                ],
            ),
            WorldGenSystem(name="修炼体系", description="重复系统"),
        ],
    )

    mock = AsyncMock(return_value=llm_output)
    monkeypatch.setattr(ai_client, "generate_structured", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["relationships_created"] == 1
    assert data["systems_created"] == 1
    assert any(w.get("code") == "relationship_duplicate_dropped" for w in data.get("warnings", []))
    assert any(w.get("code") == "system_duplicate_dropped" for w in data.get("warnings", []))

    rels = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id).all()
    assert len(rels) == 1

    systems = db.query(WorldSystem).filter(WorldSystem.novel_id == novel.id).all()
    assert len(systems) == 1
    assert systems[0].data.get("items") == [
        {"label": "真玄境", "description": "基础境界", "visibility": "reference"},
    ]
    assert systems[0].constraints == ["不要随意改变修炼等级设定"]


def test_generate_world_forwards_byok_headers(client, novel, monkeypatch):
    from app.core.ai_client import ai_client
    from app.core.world.gen import WorldGenLLMOutput

    mock = AsyncMock(return_value=WorldGenLLMOutput())
    monkeypatch.setattr(ai_client, "generate_structured", mock)

    headers = {
        "x-llm-base-url": "https://example.com/v1",
        "x-llm-api-key": "test-key",
        "x-llm-model": "test-model",
    }
    resp = client.post(
        f"/api/novels/{novel.id}/world/generate",
        json={"text": "这是一段足够长的世界观设定文本。"},
        headers=headers,
    )
    assert resp.status_code == 200
    kwargs = mock.call_args.kwargs
    assert kwargs["llm_config"] == ResolvedLlmConfig(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="test-model",
        billing_source_hint="selfhost",
        source="selfhost_request",
    )


def test_generate_world_rejects_partial_byok_headers(client, novel, monkeypatch):
    from app.core.ai_client import ai_client
    from app.core.world.gen import WorldGenLLMOutput

    mock = AsyncMock(return_value=WorldGenLLMOutput())
    monkeypatch.setattr(ai_client, "generate_structured", mock)

    headers = {
        "x-llm-base-url": "https://example.com/v1",
        "x-llm-api-key": "test-key",
    }
    resp = client.post(
        f"/api/novels/{novel.id}/world/generate",
        json={"text": "这是一段足够长的世界观设定文本。"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "llm_config_incomplete"
    mock.assert_not_called()


def test_generate_world_text_too_short_422(client, novel):
    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "太短"})
    assert resp.status_code == 422


def test_generate_world_text_non_whitespace_too_short_422(client, novel):
    # Length >= 10 but still too few non-whitespace characters.
    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "a a a a a a"})
    assert resp.status_code == 422
    payload = resp.json()
    assert any(
        isinstance(item, dict) and item.get("type") == "world_generate_text_too_short_non_whitespace"
        for item in payload.get("detail", [])
    )


def test_generate_world_llm_unavailable_maps_to_503(client, novel, monkeypatch):
    from app.core.world import generation_application as generation_app
    from app.core.ai_client import LLMUnavailableError

    mock = AsyncMock(side_effect=LLMUnavailableError("boom"))
    monkeypatch.setattr(generation_app, "generate_world_drafts", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 503
    payload = resp.json()
    assert payload["detail"]["code"] == "world_generate_llm_unavailable"


def test_generate_world_llm_schema_invalid_maps_to_502(client, novel, monkeypatch):
    from app.core.world import generation_application as generation_app
    from app.core.ai_client import StructuredOutputParseError

    mock = AsyncMock(side_effect=StructuredOutputParseError(max_retries=3))
    monkeypatch.setattr(generation_app, "generate_world_drafts", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 502
    payload = resp.json()
    assert payload["detail"]["code"] == "world_generate_llm_schema_invalid"


def test_generate_world_unexpected_error_maps_to_500(client, novel, monkeypatch):
    from app.core.world import generation_application as generation_app

    mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(generation_app, "generate_world_drafts", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 500
    payload = resp.json()
    assert payload["detail"]["code"] == "world_generate_failed"


def test_generate_world_does_not_delete_bootstrap_drafts(client, db, novel, monkeypatch):
    from app.core.ai_client import ai_client
    from app.core.world.gen import WorldGenEntity, WorldGenLLMOutput

    # Simulate an unrelated bootstrap draft (e.g. created by chapter bootstrap extraction).
    db.add(
        WorldEntity(
            novel_id=novel.id,
            name="不会被删",
            entity_type="Concept",
            description="bootstrap 草稿",
            aliases=[],
            origin="bootstrap",
            status="draft",
        )
    )
    db.commit()

    llm_output = WorldGenLLMOutput(
        entities=[WorldGenEntity(name="新条目", entity_type="Concept")],
        relationships=[],
        systems=[],
    )
    mock = AsyncMock(return_value=llm_output)
    monkeypatch.setattr(ai_client, "generate_structured", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 200

    names = {e.name for e in db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).all()}
    assert "不会被删" in names
    assert "新条目" in names


def test_generate_world_chunks_long_text_and_merges_results(client, db, novel, monkeypatch):
    import app.config as config_mod
    from app.core.ai_client import ai_client
    from app.core.world.gen import (
        WorldGenEntity,
        WorldGenLLMOutput,
        WorldGenRelationship,
        WorldGenSystem,
        WorldGenSystemItem,
    )

    prev = config_mod._settings_instance
    config_mod._settings_instance = _selfhost_settings(
        world_generation_chunk_chars=15,
        world_generation_chunk_overlap_chars=0,
        world_generation_max_chunks=3,
        world_generation_chunk_max_tokens=1234,
    )
    try:
        mock = AsyncMock(
            side_effect=[
                WorldGenLLMOutput(
                    entities=[WorldGenEntity(name="云澈", entity_type="Concept", description="主角")],
                    systems=[
                        WorldGenSystem(
                            name="修炼体系",
                            description="境界划分",
                            items=[WorldGenSystemItem(label="真玄境", description="基础")],
                            constraints=["不要随意改变修炼等级设定"],
                        )
                    ],
                ),
                WorldGenLLMOutput(
                    entities=[WorldGenEntity(name="苍风帝国", entity_type="Faction", description="势力")],
                    relationships=[
                        WorldGenRelationship(source="云澈", target="苍风帝国", label="来自", description="出身于此")
                    ],
                    systems=[
                        WorldGenSystem(
                            name="修炼体系",
                            description="更完整的境界规则",
                            items=[WorldGenSystemItem(label="地玄境", description="进阶")],
                            constraints=["不要随意改变修炼等级设定"],
                        )
                    ],
                ),
                WorldGenLLMOutput(
                    entities=[WorldGenEntity(name="云澈", entity_type="Character", description="天赋极高", aliases=["小澈"])],
                ),
            ]
        )
        monkeypatch.setattr(ai_client, "generate_structured", mock)

        resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "甲" * 31})
        assert resp.status_code == 200
        data = resp.json()
        assert data["entities_created"] == 2
        assert data["relationships_created"] == 1
        assert data["systems_created"] == 1
        assert mock.await_count == 3
        assert all(call.kwargs["max_tokens"] == 1234 for call in mock.await_args_list)

        entities = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).order_by(WorldEntity.id.asc()).all()
        assert {e.name for e in entities} == {"云澈", "苍风帝国"}
        yunche = next(e for e in entities if e.name == "云澈")
        assert yunche.entity_type == "Character"
        assert yunche.aliases == ["小澈"]
        assert yunche.description == "天赋极高"

        systems = db.query(WorldSystem).filter(WorldSystem.novel_id == novel.id).all()
        assert len(systems) == 1
        items = systems[0].data.get("items") or []
        assert {item["label"] for item in items} == {"真玄境", "地玄境"}
        assert systems[0].constraints == ["不要随意改变修炼等级设定"]
    finally:
        config_mod._settings_instance = prev


def test_generate_world_chunks_merge_hierarchy_systems(client, db, novel, monkeypatch):
    import app.config as config_mod
    from app.core.ai_client import ai_client
    from app.core.world.gen import WorldGenLLMOutput, WorldGenSystem, WorldGenSystemItem

    prev = config_mod._settings_instance
    config_mod._settings_instance = _selfhost_settings(
        world_generation_chunk_chars=12,
        world_generation_chunk_overlap_chars=0,
        world_generation_max_chunks=2,
        world_generation_chunk_max_tokens=777,
    )
    try:
        mock = AsyncMock(
            side_effect=[
                WorldGenLLMOutput(
                    systems=[
                        WorldGenSystem(
                            name="宗门架构",
                            display_type="hierarchy",
                            items=[
                                WorldGenSystemItem(
                                    label="外门",
                                    children=[WorldGenSystemItem(label="弟子")],
                                )
                            ],
                        )
                    ]
                ),
                WorldGenLLMOutput(
                    systems=[
                        WorldGenSystem(
                            name="宗门架构",
                            display_type="hierarchy",
                            items=[
                                WorldGenSystemItem(
                                    label="外门",
                                    children=[WorldGenSystemItem(label="执事")],
                                ),
                                WorldGenSystemItem(label="内门"),
                            ],
                        )
                    ]
                ),
            ]
        )
        monkeypatch.setattr(ai_client, "generate_structured", mock)

        resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "甲" * 25})
        assert resp.status_code == 200

        systems = db.query(WorldSystem).filter(WorldSystem.novel_id == novel.id).all()
        assert len(systems) == 1
        assert systems[0].display_type == "hierarchy"
        assert [node["label"] for node in systems[0].data["nodes"]] == ["外门", "内门"]
        assert [child["label"] for child in systems[0].data["nodes"][0]["children"]] == ["弟子", "执事"]
    finally:
        config_mod._settings_instance = prev


def test_generate_world_chunks_downgrade_conflicting_system_shapes_to_list(client, db, novel, monkeypatch):
    import app.config as config_mod
    from app.core.ai_client import ai_client
    from app.core.world.gen import WorldGenLLMOutput, WorldGenSystem, WorldGenSystemItem

    prev = config_mod._settings_instance
    config_mod._settings_instance = _selfhost_settings(
        world_generation_chunk_chars=12,
        world_generation_chunk_overlap_chars=0,
        world_generation_max_chunks=2,
        world_generation_chunk_max_tokens=777,
    )
    try:
        mock = AsyncMock(
            side_effect=[
                WorldGenLLMOutput(
                    systems=[
                        WorldGenSystem(
                            name="宗门沿革",
                            display_type="hierarchy",
                            items=[
                                WorldGenSystemItem(
                                    label="外门",
                                    children=[WorldGenSystemItem(label="弟子")],
                                )
                            ],
                        )
                    ]
                ),
                WorldGenLLMOutput(
                    systems=[
                        WorldGenSystem(
                            name="宗门沿革",
                            display_type="timeline",
                            items=[
                                WorldGenSystemItem(
                                    time="上古纪元",
                                    label="内门建立",
                                    description="宗门扩张",
                                )
                            ],
                        )
                    ]
                ),
            ]
        )
        monkeypatch.setattr(ai_client, "generate_structured", mock)

        resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "甲" * 25})
        assert resp.status_code == 200
        payload = resp.json()
        warning = next(w for w in payload.get("warnings", []) if w.get("code") == "system_display_type_conflict")
        assert warning["message_key"] == "world.generate.warning.system_display_type_conflict"
        assert warning["message_params"]["downgraded_display_type"] == "list"

        systems = db.query(WorldSystem).filter(WorldSystem.novel_id == novel.id).all()
        assert len(systems) == 1
        assert systems[0].display_type == "list"
        assert systems[0].data == {
            "items": [
                {"label": "外门", "visibility": "reference"},
                {"label": "外门 / 弟子", "visibility": "reference"},
                {"label": "[上古纪元] 内门建立", "description": "宗门扩张", "visibility": "reference"},
            ]
        }
    finally:
        config_mod._settings_instance = prev


def test_generate_world_replaces_previous_worldgen_drafts(client, db, novel, monkeypatch):
    from app.core.ai_client import ai_client
    from app.core.world.gen import WorldGenEntity, WorldGenLLMOutput

    first = WorldGenLLMOutput(entities=[WorldGenEntity(name="A", entity_type="Concept")])
    second = WorldGenLLMOutput(entities=[WorldGenEntity(name="B", entity_type="Concept")])
    mock = AsyncMock(side_effect=[first, second])
    monkeypatch.setattr(ai_client, "generate_structured", mock)

    resp1 = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp1.status_code == 200

    resp2 = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp2.status_code == 200

    entities = (
        db.query(WorldEntity)
        .filter(WorldEntity.novel_id == novel.id, WorldEntity.origin == "worldgen", WorldEntity.status == "draft")
        .all()
    )
    assert {e.name for e in entities} == {"B"}


def test_generate_world_db_conflict_maps_to_409(client, novel, monkeypatch):
    from app.core.world import generation_application as generation_app
    from sqlalchemy.exc import IntegrityError

    mock = AsyncMock(side_effect=IntegrityError("stmt", "params", Exception("orig")))
    monkeypatch.setattr(generation_app, "generate_world_drafts", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 409
    payload = resp.json()
    assert payload["detail"]["code"] == "world_generate_conflict"
