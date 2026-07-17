import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

import app.core.bootstrap as bootstrap_module
from app.config import Settings
from app.core.bootstrap import (
    BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS,
    BOOTSTRAP_MODE_INDEX_REFRESH,
    BOOTSTRAP_MODE_INITIAL,
    BOOTSTRAP_MODE_REEXTRACT,
    BootstrapRefinementResult,
    is_stale_running_job,
    refine_candidates_with_llm,
    run_bootstrap_job,
)
from app.core.indexing.window_index import NovelIndex
from app.database import Base
from app.models import BootstrapJob, Chapter, Novel, WorldEntity, WorldRelationship


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


def test_is_stale_running_job_only_for_running_status():
    stale_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    running_job = BootstrapJob(
        novel_id=1,
        status="windowing",
        progress={"step": 3, "detail": "windowing"},
        result={},
        created_at=stale_at,
        updated_at=stale_at,
    )
    assert is_stale_running_job(running_job, stale_after_seconds=60)

    running_job.status = "completed"
    assert not is_stale_running_job(running_job, stale_after_seconds=60)


class _FakeAIClient:
    def __init__(
        self,
        payload: dict | None = None,
        *,
        error: Exception | None = None,
        delay_seconds: float = 0.0,
        responses: list[dict | Exception] | None = None,
    ):
        self._payload = payload or {"entities": [], "relationships": []}
        self._error = error
        self._delay_seconds = delay_seconds
        self._responses = list(responses) if responses is not None else None
        self.calls = 0
        self.last_kwargs: dict | None = None
        self.call_kwargs: list[dict] = []

    async def generate_structured(self, **kwargs):
        self.calls += 1
        self.last_kwargs = dict(kwargs)
        self.call_kwargs.append(dict(kwargs))
        if self._delay_seconds > 0:
            await asyncio.sleep(self._delay_seconds)
        if self._responses is not None and self._responses:
            response = self._responses.pop(0)
            if isinstance(response, Exception):
                raise response
            response_model = kwargs["response_model"]
            return response_model.model_validate(response)
        if self._error:
            raise self._error
        response_model = kwargs["response_model"]
        return response_model.model_validate(self._payload)


@pytest.mark.asyncio
async def test_refine_candidates_with_llm_calls_client_once():
    fake_client = _FakeAIClient(
        payload={
            "entities": [{"name": "Alice", "entity_type": "Character", "aliases": ["Al"]}],
            "relationships": [{"source_name": "Alice", "target_name": "Bob", "label": "ally"}],
        }
    )
    result = await refine_candidates_with_llm(
        {"Alice": 5, "Bob": 3},
        [("Alice", "Bob", 2)],
        client=fake_client,
        llm_config={"base_url": "https://example.com/v1", "api_key": "k", "model": "m"},
        max_candidates=10,
        temperature=0.3,
        user_id=123,
    )

    assert isinstance(result, BootstrapRefinementResult)
    assert fake_client.calls == 1
    assert (fake_client.last_kwargs or {}).get("user_id") == 123
    assert (fake_client.last_kwargs or {}).get("base_url") == "https://example.com/v1"
    assert (fake_client.last_kwargs or {}).get("api_key") == "k"
    assert (fake_client.last_kwargs or {}).get("model") == "m"
    assert result.entities[0].name == "Alice"


@pytest.mark.asyncio
async def test_refine_candidates_with_llm_filters_pairs_to_shortlisted_candidates():
    fake_client = _FakeAIClient()

    await refine_candidates_with_llm(
        {"Alice": 5, "Bob": 4},
        [
            ("Alice", "Bob", 3),
            ("Alice", "Carol", 10),
        ],
        client=fake_client,
        max_candidates=2,
    )

    prompt = (fake_client.last_kwargs or {}).get("prompt") or ""
    assert "Alice -- Bob" in prompt
    assert "Alice -- Carol" not in prompt


@pytest.mark.asyncio
async def test_refine_candidates_with_llm_uses_tighter_default_prompt_candidate_cap():
    fake_client = _FakeAIClient()

    importance = {f"Entity{i:03d}": 500 - i for i in range(100)}

    await refine_candidates_with_llm(
        importance,
        [],
        client=fake_client,
        max_candidates=200,
    )

    prompt = (fake_client.last_kwargs or {}).get("prompt") or ""
    assert "Entity063" in prompt
    assert "Entity064" not in prompt


@pytest.mark.asyncio
async def test_refine_candidates_with_llm_retries_with_narrower_prompt_after_truncation():
    from app.core.ai_client import StructuredOutputParseError

    truncation_error = StructuredOutputParseError(
        max_retries=1,
        last_error=ValueError(
            "LLM response truncated (finish_reason=length, max_tokens=8000). Increase max_tokens or reduce input."
        ),
    )
    fake_client = _FakeAIClient(
        responses=[
            truncation_error,
            {
                "entities": [{"name": "Alice", "entity_type": "Character", "aliases": []}],
                "relationships": [],
            },
        ]
    )

    importance = {f"Entity{i}": 500 - i for i in range(200)}
    importance["Alice"] = 999
    pairs = [(f"Entity{i}", f"Entity{i+1}", 10) for i in range(120)]

    result = await refine_candidates_with_llm(
        importance,
        pairs,
        client=fake_client,
        max_candidates=200,
    )

    assert result.entities[0].name == "Alice"
    assert fake_client.calls == 2
    first_prompt = fake_client.call_kwargs[0]["prompt"]
    second_prompt = fake_client.call_kwargs[1]["prompt"]
    assert len(second_prompt) < len(first_prompt)


@pytest.mark.asyncio
async def test_run_bootstrap_job_persists_index_entities_and_relationships_english(db):
    novel = Novel(title="Test Novel", author="Tester", language="en", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    english_text = ("Alice met Bob in the city. Alice trusted Bob. " * 60).strip()
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content=english_text))
    job = BootstrapJob(
        novel_id=novel.id,
        mode=BOOTSTRAP_MODE_INITIAL,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={"entities_found": 0, "relationships_found": 0},
    )
    db.add(job)
    db.commit()

    fake_client = _FakeAIClient(
        payload={
            "entities": [
                {"name": "Alice", "entity_type": "Character", "aliases": ["Al"]},
                {"name": "Bob", "entity_type": "Character", "aliases": []},
            ],
            "relationships": [{"source_name": "Alice", "target_name": "Bob", "label": "ally"}],
        }
    )

    await run_bootstrap_job(
        job.id,
        session_factory=TestingSessionLocal,
        client=fake_client,
        user_id=777,
        llm_config={"base_url": "https://example.com/v1", "api_key": "k", "model": "m"},
    )

    db.expire_all()
    refreshed_job = db.query(BootstrapJob).filter(BootstrapJob.id == job.id).first()
    refreshed_novel = db.query(Novel).filter(Novel.id == novel.id).first()

    assert refreshed_job.status == "completed"
    assert refreshed_job.result is not None
    assert refreshed_job.result["entities_found"] == 2
    assert refreshed_job.result["relationships_found"] == 1
    assert refreshed_job.result["index_refresh_only"] is False
    assert refreshed_job.result["llm_blocking_wait_count"] == 1
    assert float(refreshed_job.result["llm_blocking_wait_seconds"]) >= 0.0
    assert refreshed_novel.window_index is not None
    assert (fake_client.last_kwargs or {}).get("user_id") == 777
    assert (fake_client.last_kwargs or {}).get("base_url") == "https://example.com/v1"
    assert (fake_client.last_kwargs or {}).get("api_key") == "k"
    assert (fake_client.last_kwargs or {}).get("model") == "m"

    restored_index = NovelIndex.from_msgpack(refreshed_novel.window_index)
    assert "Alice" in restored_index.entity_windows

    entities = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).all()
    relationships = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id).all()
    assert len(entities) == 2
    assert len(relationships) == 1
    assert all(entity.origin == "bootstrap" for entity in entities)
    assert all(relationship.origin == "bootstrap" for relationship in relationships)
    assert relationships[0].status == "draft"


@pytest.mark.asyncio
async def test_run_bootstrap_job_keeps_mention_only_entities_in_refinement_prompt(db):
    novel = Novel(title="Prompt Coverage", author="Tester", language="en", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    english_text = ("Alice is in Paris. Bob meets Alice. " * 60).strip()
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content=english_text))
    job = BootstrapJob(
        novel_id=novel.id,
        mode=BOOTSTRAP_MODE_INITIAL,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={"entities_found": 0, "relationships_found": 0},
    )
    db.add(job)
    db.commit()

    fake_client = _FakeAIClient(
        payload={
            "entities": [
                {"name": "Alice", "entity_type": "Character", "aliases": []},
                {"name": "Bob", "entity_type": "Character", "aliases": []},
            ],
            "relationships": [{"source_name": "Alice", "target_name": "Bob", "label": "ally"}],
        }
    )

    await run_bootstrap_job(job.id, session_factory=TestingSessionLocal, client=fake_client)

    prompt = (fake_client.last_kwargs or {}).get("prompt") or ""
    assert "- Alice:" in prompt
    assert "- Bob:" in prompt


@pytest.mark.asyncio
async def test_run_bootstrap_job_persists_entities_and_relationships_chinese(db):
    novel = Novel(title="中文测试", author="作者", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    db.add(
        Chapter(
            novel_id=novel.id,
            chapter_number=1,
            title="第一章",
            content=("云澈与楚月仙来到苍风帝国。云澈拔剑迎战。" * 80),
        )
    )
    job = BootstrapJob(
        novel_id=novel.id,
        mode=BOOTSTRAP_MODE_INITIAL,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={"entities_found": 0, "relationships_found": 0},
    )
    db.add(job)
    db.commit()

    fake_client = _FakeAIClient(
        payload={
            "entities": [
                {"name": "云澈", "entity_type": "Character", "aliases": ["小澈"]},
                {"name": "楚月仙", "entity_type": "Character", "aliases": []},
            ],
            "relationships": [{"source_name": "云澈", "target_name": "楚月仙", "label": "同伴"}],
        }
    )

    await run_bootstrap_job(job.id, session_factory=TestingSessionLocal, client=fake_client)

    db.expire_all()
    refreshed_job = db.query(BootstrapJob).filter(BootstrapJob.id == job.id).first()
    entities = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).all()
    relationships = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id).all()

    assert refreshed_job.status == "completed"
    assert len(entities) == 2
    assert len(relationships) == 1
    assert refreshed_job.initialized is True


@pytest.mark.asyncio
async def test_run_bootstrap_job_defers_state_proto_build_until_world_entities_exist(
    db, monkeypatch
):
    novel = Novel(title="Bootstrap Targets", author="Tester", language="en", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    english_text = ("Alice met Bob in the city. Alice trusted Bob. " * 60).strip()
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content=english_text))
    job = BootstrapJob(
        novel_id=novel.id,
        mode=BOOTSTRAP_MODE_INITIAL,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={"entities_found": 0, "relationships_found": 0},
    )
    db.add(job)
    db.commit()

    fake_client = _FakeAIClient(
        payload={
            "entities": [
                {"name": "Alice", "entity_type": "Character", "aliases": []},
                {"name": "Bob", "entity_type": "Character", "aliases": []},
            ],
            "relationships": [],
        }
    )

    original_build = bootstrap_module.execute_state_proto_build
    seen_target_specs: list[tuple[tuple[str, str], ...]] = []

    def _build(**kwargs):
        target_specs = tuple(kwargs.get("target_specs") or ())
        seen_target_specs.append(
            tuple((spec.id, spec.canonical_name) for spec in target_specs)
        )
        return original_build(**kwargs)

    monkeypatch.setattr(bootstrap_module, "execute_state_proto_build", _build)

    await run_bootstrap_job(job.id, session_factory=TestingSessionLocal, client=fake_client)

    assert len(seen_target_specs) == 2
    assert seen_target_specs[0] == ()
    assert any(spec_id.startswith("entity:") for spec_id, _ in seen_target_specs[1])


@pytest.mark.asyncio
async def test_run_bootstrap_job_builds_state_proto_before_refinement_in_hosted_mode(
    db, monkeypatch
):
    novel = Novel(title="Hosted Bootstrap Targets", author="Tester", language="en", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    english_text = ("Alice met Bob in the city. Alice trusted Bob. " * 60).strip()
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content=english_text))
    job = BootstrapJob(
        novel_id=novel.id,
        mode=BOOTSTRAP_MODE_INITIAL,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={"entities_found": 0, "relationships_found": 0},
    )
    db.add(job)
    db.commit()

    fake_client = _FakeAIClient(
        payload={
            "entities": [
                {"name": "Alice", "entity_type": "Character", "aliases": []},
                {"name": "Bob", "entity_type": "Character", "aliases": []},
            ],
            "relationships": [],
        }
    )

    monkeypatch.setattr(
        bootstrap_module,
        "get_settings",
        lambda: Settings.model_validate({"deploy_mode": "hosted", "environment": "production"}),
    )

    original_build = bootstrap_module.execute_state_proto_build
    seen_target_specs: list[tuple[tuple[str, str], ...]] = []

    def _build(**kwargs):
        target_specs = tuple(kwargs.get("target_specs") or ())
        seen_target_specs.append(
            tuple((spec.id, spec.canonical_name) for spec in target_specs)
        )
        return original_build(**kwargs)

    monkeypatch.setattr(bootstrap_module, "execute_state_proto_build", _build)

    await run_bootstrap_job(job.id, session_factory=TestingSessionLocal, client=fake_client)

    assert len(seen_target_specs) == 2
    assert seen_target_specs[0] == ()
    assert any(spec_id.startswith("entity:") for spec_id, _ in seen_target_specs[1])


@pytest.mark.asyncio
async def test_run_bootstrap_job_fails_fast_without_rust_state_proto(db, monkeypatch):
    """Rust-canonical contract: no hidden Python compat payload when Rust is unavailable."""
    from app.core.indexing.state_proto_executor import STATE_PROTO_RUST_REQUIRED_ERROR

    novel = Novel(title="Rust Required", author="Tester", language="en", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content="Alice met Bob. " * 40))
    job = BootstrapJob(
        novel_id=novel.id,
        mode=BOOTSTRAP_MODE_INITIAL,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={"entities_found": 0, "relationships_found": 0},
    )
    db.add(job)
    db.commit()

    def _build(**kwargs):
        raise RuntimeError(STATE_PROTO_RUST_REQUIRED_ERROR)

    monkeypatch.setattr(bootstrap_module, "execute_state_proto_build", _build)

    summary = await run_bootstrap_job(job.id, session_factory=TestingSessionLocal, client=_FakeAIClient())

    assert summary is None
    db.expire_all()
    refreshed_job = db.query(BootstrapJob).filter(BootstrapJob.id == job.id).first()
    refreshed_novel = db.query(Novel).filter(Novel.id == novel.id).first()
    assert refreshed_job.status == "failed"
    assert refreshed_novel.window_index is None
    assert refreshed_novel.window_index_status == "failed"


@pytest.mark.asyncio
async def test_bootstrap_dedupes_canonical_relationship_labels(db):
    novel = Novel(title="Canonical Test", author="Tester", language="en", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content="Alice met Bob. " * 20))
    alice = WorldEntity(novel_id=novel.id, name="Alice", entity_type="Character", aliases=[], origin="manual", status="confirmed")
    bob = WorldEntity(novel_id=novel.id, name="Bob", entity_type="Character", aliases=[], origin="manual", status="confirmed")
    db.add_all([alice, bob])
    db.commit()

    db.add(
        WorldRelationship(
            novel_id=novel.id,
            source_id=alice.id,
            target_id=bob.id,
            label="伴侣",
            origin="manual",
            status="confirmed",
        )
    )
    job = BootstrapJob(
        novel_id=novel.id,
        mode=BOOTSTRAP_MODE_INITIAL,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={"entities_found": 0, "relationships_found": 0},
    )
    db.add(job)
    db.commit()

    fake_client = _FakeAIClient(
        payload={
            "entities": [
                {"name": "Alice", "entity_type": "Character", "aliases": []},
                {"name": "Bob", "entity_type": "Character", "aliases": []},
            ],
            "relationships": [{"source_name": "Alice", "target_name": "Bob", "label": "伴侣关系"}],
        }
    )

    await run_bootstrap_job(job.id, session_factory=TestingSessionLocal, client=fake_client)

    relationships = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id).all()
    assert len(relationships) == 1


@pytest.mark.asyncio
async def test_run_bootstrap_job_captures_non_parse_failure(db):
    novel = Novel(title="Failure Case", author="Tester", language="en", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content=("Alice met Bob. " * 80)))
    job = BootstrapJob(
        novel_id=novel.id,
        mode=BOOTSTRAP_MODE_INITIAL,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={"entities_found": 0, "relationships_found": 0},
    )
    db.add(job)
    db.commit()

    failing_client = _FakeAIClient(error=RuntimeError("LLM unavailable"))
    await run_bootstrap_job(job.id, session_factory=TestingSessionLocal, client=failing_client)

    db.expire_all()
    refreshed_job = db.query(BootstrapJob).filter(BootstrapJob.id == job.id).first()
    refreshed_novel = db.query(Novel).filter(Novel.id == novel.id).first()
    assert refreshed_job.status == "failed"
    assert "引导扫描失败，请稍后重试" in (refreshed_job.error or "")
    assert refreshed_novel.window_index_status == "fresh"
    assert refreshed_novel.window_index_revision == 1
    assert refreshed_novel.window_index_built_revision == 1
    assert refreshed_novel.window_index is not None


@pytest.mark.asyncio
async def test_run_bootstrap_job_captures_parse_failure(db):
    novel = Novel(title="Parse Failure Case", author="Tester", language="en", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content=("Alice met Bob. " * 80)))
    job = BootstrapJob(
        novel_id=novel.id,
        mode=BOOTSTRAP_MODE_INITIAL,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={"entities_found": 0, "relationships_found": 0},
    )
    db.add(job)
    db.commit()

    from app.core.ai_client import StructuredOutputParseError

    parse_error = StructuredOutputParseError(max_retries=3)
    failing_client = _FakeAIClient(error=parse_error)
    await run_bootstrap_job(job.id, session_factory=TestingSessionLocal, client=failing_client)

    db.expire_all()
    refreshed_job = db.query(BootstrapJob).filter(BootstrapJob.id == job.id).first()
    refreshed_novel = db.query(Novel).filter(Novel.id == novel.id).first()
    assert refreshed_job.status == "failed"
    assert "AI 输出解析失败，请重试" in (refreshed_job.error or "")
    assert refreshed_novel.window_index_status == "fresh"
    assert refreshed_novel.window_index_revision == 1
    assert refreshed_novel.window_index_built_revision == 1
    assert refreshed_novel.window_index is not None


@pytest.mark.asyncio
async def test_run_bootstrap_job_captures_timeout_failure(db, monkeypatch):
    novel = Novel(title="Timeout Failure Case", author="Tester", language="en", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content=("Alice met Bob. " * 80)))
    job = BootstrapJob(
        novel_id=novel.id,
        mode=BOOTSTRAP_MODE_INITIAL,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={"entities_found": 0, "relationships_found": 0},
    )
    db.add(job)
    db.commit()

    monkeypatch.setattr(
        bootstrap_module,
        "get_settings",
        lambda: Settings(bootstrap_llm_timeout_seconds=1, _env_file=None),
    )

    hanging_client = _FakeAIClient(delay_seconds=2.0)
    await run_bootstrap_job(job.id, session_factory=TestingSessionLocal, client=hanging_client)

    db.expire_all()
    refreshed_job = db.query(BootstrapJob).filter(BootstrapJob.id == job.id).first()
    refreshed_novel = db.query(Novel).filter(Novel.id == novel.id).first()
    assert refreshed_job.status == "failed"
    assert "引导扫描超时，请重试" in (refreshed_job.error or "")
    assert refreshed_novel.window_index_status == "fresh"
    assert refreshed_novel.window_index_revision == 1
    assert refreshed_novel.window_index_built_revision == 1
    assert refreshed_novel.window_index is not None


@pytest.mark.asyncio
async def test_run_bootstrap_job_index_refresh_only_updates_window_index(db):
    novel = Novel(title="Index Refresh", author="Tester", language="en", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content=("Alice met Bob in the city. " * 60)))

    confirmed_entity = WorldEntity(
        novel_id=novel.id,
        name="Alice",
        entity_type="Character",
        aliases=["Al"],
        status="confirmed",
        origin="manual",
    )
    draft_bootstrap_entity = WorldEntity(
        novel_id=novel.id,
        name="OldDraft",
        entity_type="Faction",
        aliases=[],
        status="draft",
        origin="bootstrap",
    )
    db.add_all([confirmed_entity, draft_bootstrap_entity])
    db.commit()
    db.refresh(confirmed_entity)
    db.refresh(draft_bootstrap_entity)

    db.add(
        WorldRelationship(
            novel_id=novel.id,
            source_id=confirmed_entity.id,
            target_id=draft_bootstrap_entity.id,
            label="knows",
            status="draft",
            origin="manual",
        )
    )
    job = BootstrapJob(
        novel_id=novel.id,
        mode=BOOTSTRAP_MODE_INDEX_REFRESH,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={"entities_found": 0, "relationships_found": 0, "index_refresh_only": True},
        initialized=True,
    )
    db.add(job)
    db.commit()

    fake_client = _FakeAIClient(
        payload={
            "entities": [{"name": "ShouldNotRun", "entity_type": "Character", "aliases": []}],
            "relationships": [],
        }
    )

    await run_bootstrap_job(job.id, session_factory=TestingSessionLocal, client=fake_client)

    db.expire_all()
    refreshed_job = db.query(BootstrapJob).filter(BootstrapJob.id == job.id).first()
    refreshed_novel = db.query(Novel).filter(Novel.id == novel.id).first()
    entities = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).all()
    relationships = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id).all()

    assert refreshed_job.status == "completed"
    assert refreshed_job.result["index_refresh_only"] is True
    assert refreshed_job.result["entities_found"] == 0
    assert refreshed_job.result["relationships_found"] == 0
    assert refreshed_novel.window_index is not None
    assert fake_client.calls == 0
    assert sorted(entity.name for entity in entities) == ["Alice", "OldDraft"]
    assert len(relationships) == 1


@pytest.mark.asyncio
async def test_run_bootstrap_job_reextract_replace_cleans_bootstrap_drafts_only(db):
    novel = Novel(title="Reextract Replace", author="Tester", language="en", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content=("Alice and Bob explored the city. " * 80)))

    confirmed_entity = WorldEntity(
        novel_id=novel.id,
        name="Alice",
        entity_type="Character",
        aliases=["The Hero"],
        status="confirmed",
        origin="manual",
    )
    old_bootstrap_draft = WorldEntity(
        novel_id=novel.id,
        name="OldBootstrapDraft",
        entity_type="Faction",
        aliases=["Old Alias"],
        status="draft",
        origin="bootstrap",
    )
    manual_draft = WorldEntity(
        novel_id=novel.id,
        name="ManualDraft",
        entity_type="Location",
        aliases=[],
        status="draft",
        origin="manual",
    )
    db.add_all([confirmed_entity, old_bootstrap_draft, manual_draft])
    db.commit()
    db.refresh(confirmed_entity)
    db.refresh(old_bootstrap_draft)
    db.refresh(manual_draft)

    db.add_all(
        [
            WorldRelationship(
                novel_id=novel.id,
                source_id=confirmed_entity.id,
                target_id=old_bootstrap_draft.id,
                label="old-bootstrap",
                status="draft",
                origin="bootstrap",
            ),
            WorldRelationship(
                novel_id=novel.id,
                source_id=confirmed_entity.id,
                target_id=manual_draft.id,
                label="manual-link",
                status="draft",
                origin="manual",
            ),
        ]
    )
    job = BootstrapJob(
        novel_id=novel.id,
        mode=BOOTSTRAP_MODE_REEXTRACT,
        draft_policy=BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={"entities_found": 0, "relationships_found": 0, "index_refresh_only": False},
        initialized=True,
    )
    db.add(job)
    db.commit()

    fake_client = _FakeAIClient(
        payload={
            "entities": [
                {"name": "Alice", "entity_type": "Item", "aliases": ["Changed Alias"]},
                {"name": "Bob", "entity_type": "Character", "aliases": ["B"]},
            ],
            "relationships": [{"source_name": "Alice", "target_name": "Bob", "label": "ally"}],
        }
    )

    await run_bootstrap_job(job.id, session_factory=TestingSessionLocal, client=fake_client)

    db.expire_all()
    refreshed_job = db.query(BootstrapJob).filter(BootstrapJob.id == job.id).first()
    entities = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).all()
    relationships = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id).all()

    entities_by_name = {entity.name: entity for entity in entities}
    labels = {relationship.label for relationship in relationships}

    assert refreshed_job.status == "completed"
    assert refreshed_job.result["index_refresh_only"] is False
    assert "OldBootstrapDraft" not in entities_by_name
    assert "ManualDraft" in entities_by_name
    assert entities_by_name["Alice"].entity_type == "Character"
    assert entities_by_name["Alice"].aliases == ["The Hero"]
    assert entities_by_name["Alice"].origin == "manual"
    assert entities_by_name["Bob"].origin == "bootstrap"
    assert "old-bootstrap" not in labels
    assert "manual-link" in labels
    assert "ally" in labels
