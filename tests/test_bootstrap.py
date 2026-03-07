from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.bootstrap import (
    BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS,
    BOOTSTRAP_MODE_INDEX_REFRESH,
    BOOTSTRAP_MODE_INITIAL,
    BOOTSTRAP_MODE_REEXTRACT,
    BootstrapRefinementResult,
    ChapterText,
    build_window_index,
    compute_cooccurrence,
    detect_language,
    extract_candidates,
    is_stale_running_job,
    load_common_words,
    refine_candidates_with_llm,
    run_bootstrap_job,
)
from app.core.window_index import NovelIndex
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


def test_detect_language_by_space_ratio():
    assert detect_language("Alice and Bob walked home.") == "en"
    assert detect_language("云澈看向远方，楚月仙站在雪中。") == "zh"


def test_extract_candidates_filters_short_tokens_and_stop_words():
    tokens = ["a", "the", "Alice", "Alice", "Bob", "and", "Bob", "city"]
    common_words = {"the", "and"}

    candidates = extract_candidates(tokens, common_words)
    assert candidates == {"Alice": 2, "Bob": 2, "city": 1}


def test_load_common_words_merges_primary_and_fallback_language_files(tmp_path):
    common_words_dir = tmp_path / "common_words"
    common_words_dir.mkdir(parents=True)
    (common_words_dir / "en.txt").write_text("the\nand\n", encoding="utf-8")
    (common_words_dir / "zh.txt").write_text("没有\n什么\n", encoding="utf-8")

    words_for_en = load_common_words("en", common_words_dir=str(common_words_dir))
    words_for_zh = load_common_words("zh", common_words_dir=str(common_words_dir))

    assert "the" in words_for_en
    assert "没有" in words_for_en
    assert "the" in words_for_zh
    assert "没有" in words_for_zh


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


def test_build_window_index_filters_low_window_count_candidates():
    chapters = [
        ChapterText(chapter_id=1, text="alice bob"),
        ChapterText(chapter_id=2, text="alice city"),
        ChapterText(chapter_id=3, text="alice"),
    ]
    candidates = {"alice": 3, "bob": 1, "city": 1}

    index, importance = build_window_index(
        chapters,
        candidates,
        window_size=500,
        window_step=250,
        min_window_count=2,
        min_window_ratio=0.0,
    )

    assert importance == {"alice": 3}
    assert set(index.entity_windows.keys()) == {"alice"}
    assert len(index.find_entity_passages("alice", limit=10)) == 3


def test_compute_cooccurrence_from_window_entities():
    index = NovelIndex(
        entity_windows={},
        window_entities={
            1: {"alice", "bob", "carol"},
            2: {"alice", "bob"},
            3: {"alice", "carol"},
        },
    )

    pairs = compute_cooccurrence(index)
    assert pairs[0] == ("alice", "bob", 2)
    assert pairs[1] == ("alice", "carol", 2)
    assert ("bob", "carol", 1) in pairs


class _FakeAIClient:
    def __init__(self, payload: dict | None = None, *, error: Exception | None = None):
        self._payload = payload or {"entities": [], "relationships": []}
        self._error = error
        self.calls = 0
        self.last_kwargs: dict | None = None

    async def generate_structured(self, **kwargs):
        self.calls += 1
        self.last_kwargs = dict(kwargs)
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
async def test_run_bootstrap_job_persists_index_entities_and_relationships_english(db):
    novel = Novel(title="Test Novel", author="Tester", file_path="/tmp/test.txt", total_chapters=1)
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
    assert refreshed_job.result == {"entities_found": 2, "relationships_found": 1, "index_refresh_only": False}
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
async def test_bootstrap_dedupes_canonical_relationship_labels(db):
    novel = Novel(title="Canonical Test", author="Tester", file_path="/tmp/test.txt", total_chapters=1)
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
    novel = Novel(title="Failure Case", author="Tester", file_path="/tmp/test.txt", total_chapters=1)
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
    assert refreshed_job.status == "failed"
    assert "引导扫描失败，请稍后重试" in (refreshed_job.error or "")


@pytest.mark.asyncio
async def test_run_bootstrap_job_captures_parse_failure(db):
    novel = Novel(title="Parse Failure Case", author="Tester", file_path="/tmp/test.txt", total_chapters=1)
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
    assert refreshed_job.status == "failed"
    assert "AI 输出解析失败，请重试" in (refreshed_job.error or "")


@pytest.mark.asyncio
async def test_run_bootstrap_job_index_refresh_only_updates_window_index(db):
    novel = Novel(title="Index Refresh", author="Tester", file_path="/tmp/test.txt", total_chapters=1)
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
    novel = Novel(title="Reextract Replace", author="Tester", file_path="/tmp/test.txt", total_chapters=1)
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
