"""Hold the provider pending while observing real pool events and concurrent edits."""

import asyncio

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Novel, User, WorldEntity, WorldGenerationRun
from app.core.llm_config import ResolvedLlmConfig
from app.core.world import gen, generation_application, generation_persistence
from app.core.world.use_case_errors import WorldUseCaseError


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [None, "novel", "draft", "delete", "llm_failure", "write_failure", "cancel"])
async def test_generation_releases_connections_during_model_wait_and_checks_snapshot(tmp_path, monkeypatch, change):
    engine = create_engine(f"sqlite:///{tmp_path / 'world.db'}", pool_size=2, max_overflow=0)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as db:
        user = User(username="test", hashed_password="unused")
        db.add(user)
        db.flush()
        novel = Novel(title="Original", file_path="unused", owner_id=user.id, language="en")
        db.add(novel)
        db.flush()
        novel_id, user_id = novel.id, user.id
        db.add(WorldEntity(novel_id=novel_id, name="Old draft", entity_type="Concept", origin="worldgen", status="draft"))
        db.commit()

    active = 0
    checkouts = 0

    def checkout(*args):
        nonlocal active, checkouts
        active += 1
        checkouts += 1

    def checkin(*args):
        nonlocal active
        active -= 1

    event.listen(engine, "checkout", checkout)
    event.listen(engine, "checkin", checkin)
    entered, resume = asyncio.Event(), asyncio.Event()

    async def generate(**kwargs):
        entered.set()
        await resume.wait()
        if change == "llm_failure":
            raise RuntimeError("provider failed")
        return gen.WorldGenLLMOutput(entities=[gen.WorldGenEntity(name="New draft", entity_type="Concept")])

    monkeypatch.setattr(gen.ai_client, "generate_structured", generate)
    if change == "write_failure":
        def fail(**kwargs):
            raise RuntimeError("write failed after entity flush")
        monkeypatch.setattr(generation_persistence, "_stage_systems", fail)

    task = asyncio.create_task(generation_application.generate_world_from_text(
        novel_id, text="A sufficiently detailed world setting.", session_factory=factory, user_id=user_id,
        llm_config=ResolvedLlmConfig(base_url="https://example.invalid/v1", api_key="unused", model="test", billing_source_hint="selfhost", source="selfhost_settings"),
    ))
    try:
        await asyncio.wait_for(entered.wait(), timeout=3)
        assert checkouts > 0
        assert active == 0, "generation must not retain auth/quota/read connections while waiting"
        with factory() as db:
            if change == "novel":
                db.get(Novel, novel_id).title = "Edited during generation"
            elif change == "draft":
                db.query(WorldEntity).one().description = "Edited during generation"
            elif change == "delete":
                # Match the API's explicit world/run cascade before deleting the novel.
                db.query(WorldEntity).filter_by(novel_id=novel_id).delete()
                db.query(WorldGenerationRun).filter_by(novel_id=novel_id).delete()
                db.delete(db.get(Novel, novel_id))
            db.commit()
        assert active == 0
        if change == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            resume.set()
            if change is None:
                assert (await task).entities_created == 1
            else:
                with pytest.raises(WorldUseCaseError) as error:
                    await task
                assert error.value.status_code == (404 if change == "delete" else 409 if change in {"novel", "draft"} else 500)
        assert active == 0
        with factory() as db:
            names = [row.name for row in db.query(WorldEntity)]
            assert names == (["New draft"] if change is None else [] if change == "delete" else ["Old draft"])
            if change == "draft":
                assert db.query(WorldEntity).one().description == "Edited during generation"
            assert not db.query(WorldGenerationRun).filter_by(status="running").count()
    finally:
        resume.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        engine.dispose()
