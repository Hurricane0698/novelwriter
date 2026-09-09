"""Exercise Copilot with independently owned sessions and one real pool slot."""

import json
import threading

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.ai_client import ToolCall, ToolLLMResponse
from app.database import Base
from app.models import Chapter, CopilotRun, Novel, WorldEntity
from tests.copilot.runtime_support import TEST_LLM_CONFIG, noop_coro


@pytest.fixture
def runtime_database(monkeypatch):
    decoded_workspaces = []

    def deserialize_json(value):
        payload = json.loads(value)
        if isinstance(payload, dict) and "archive_marker" in payload:
            decoded_workspaces.append(payload["archive_marker"])
        return payload

    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.05,
        json_deserializer=deserialize_json,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    sessions = []

    def new_session():
        session = factory()
        sessions.append(session)
        owner_thread = threading.get_ident()

        def check_owner(*args):
            assert threading.get_ident() == owner_thread

        event.listen(session, "after_begin", check_owner)
        event.listen(session, "after_transaction_end", check_owner)
        return session

    monkeypatch.setattr("app.database.SessionLocal", new_session)
    monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", noop_coro)
    monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)
    try:
        yield engine, new_session, decoded_workspaces
    finally:
        for session in sessions:
            session.close()
        engine.dispose()


def _seed_runtime(factory):
    from app.core.copilot.scope import gather_evidence, load_scope_snapshot
    from app.core.copilot.service import create_run, open_or_reuse_session

    with factory() as db:
        novel = Novel(
            title="Synthetic book", author="test", file_path="unused.txt", language="zh"
        )
        db.add(novel)
        db.flush()
        entity = WorldEntity(
            novel_id=novel.id,
            name="张三",
            entity_type="Character",
            description="主角",
            status="confirmed",
            origin="manual",
        )
        db.add_all(
            [
                entity,
                Chapter(
                    novel_id=novel.id,
                    chapter_number=1,
                    title="第一章",
                    content="张三在宗门修行。",
                ),
            ]
        )
        db.flush()
        context = {"entity_id": entity.id}
        session, _ = open_or_reuse_session(
            db, novel.id, 1, "current_entity", "current_entity", context, "zh", "张三"
        )
        run = create_run(db, session, 1, "补完张三")
        snapshot = load_scope_snapshot(db, novel, session.mode, session.scope, context)
        evidence = gather_evidence(db, novel, snapshot, context)
        data = {
            "mode": session.mode,
            "scope": session.scope,
            "context_json": context,
            "interaction_locale": "zh",
            "display_title": "张三",
        }
        return novel.id, run.run_id, data, snapshot, evidence


@pytest.mark.asyncio
async def test_auto_open_releases_tool_connection_before_next_model_call(
    runtime_database, monkeypatch
):
    from app.core.copilot.runtime_adapters import run_tool_loop

    engine, factory, _ = runtime_database
    novel_id, _, data, snapshot, evidence = _seed_runtime(factory)
    connection_counts = []

    async def model_response(self, **kwargs):
        connection_counts.append(engine.pool.checkedout())
        if len(connection_counts) == 1:
            return ToolLLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(id="find", name="find", arguments='{"query":"张三"}')
                ],
            )
        return ToolLLMResponse(content='{"answer":"完成","suggestions":[]}')

    monkeypatch.setattr(
        "app.core.ai_client.AIClient.generate_with_tools", model_response
    )
    parsed, _, workspace = await run_tool_loop(
        factory,
        novel_id,
        data,
        "补完张三",
        TEST_LLM_CONFIG,
        1,
        snapshot,
        "entity_completion",
        evidence,
        "task_query",
    )
    assert parsed["answer"] == "完成"
    assert [entry["tool"] for entry in workspace.tool_journal] == ["find", "open"]
    assert connection_counts == [0, 0]
    assert engine.pool.checkedout() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("prepare_failure", [False, True])
async def test_execute_run_releases_preparation_connection(
    runtime_database, monkeypatch, prepare_failure
):
    from app.core.copilot.service import execute_copilot_run

    engine, factory, _ = runtime_database
    novel_id, run_id, _, _, _ = _seed_runtime(factory)
    connection_counts = []

    async def model_response(self, **kwargs):
        connection_counts.append(engine.pool.checkedout())
        return ToolLLMResponse(content='{"answer":"完成","suggestions":[]}')

    monkeypatch.setattr(
        "app.core.ai_client.AIClient.generate_with_tools", model_response
    )
    if prepare_failure:

        def fail_preparation(db, *args, **kwargs):
            assert db.query(Chapter).count() == 1
            raise ValueError("Synthetic scope loading failure")

        monkeypatch.setattr(
            "app.core.copilot.scope.load_scope_snapshot", fail_preparation
        )
    await execute_copilot_run(run_id, novel_id, 1, TEST_LLM_CONFIG)
    with factory() as db:
        run = db.query(CopilotRun).filter_by(run_id=run_id).one()
        assert run.status == ("error" if prepare_failure else "completed")
        if not prepare_failure:
            assert run.answer == "完成"
    assert connection_counts == ([] if prepare_failure else [0])
    assert engine.pool.checkedout() == 0


def test_follow_up_loads_only_latest_workspace_without_dropping_messages(
    runtime_database,
):
    from app.core.copilot.execution_runtime import _build_follow_up_inputs
    from app.core.copilot.session_runtime import build_follow_up_conversation_messages

    _, factory, decoded_workspaces = runtime_database
    novel_id, run_id, _, _, _ = _seed_runtime(factory)
    with factory() as db:
        run = db.query(CopilotRun).filter_by(run_id=run_id).one()
        db.add_all(
            [
                CopilotRun(
                    run_id=f"prior-{index}",
                    copilot_session_id=run.copilot_session_id,
                    novel_id=novel_id,
                    user_id=1,
                    status="completed",
                    prompt=f"prompt-{index}",
                    answer=f"answer-{index}",
                    workspace_json={
                        "archive_marker": index,
                        "messages": [{"content": "x" * 100_000}],
                    },
                )
                for index in range(3)
            ]
        )
        db.commit()
    with factory() as db:
        run = db.query(CopilotRun).filter_by(run_id=run_id).one()
        decoded_workspaces.clear()
        messages, _ = _build_follow_up_inputs(
            db,
            run=run,
            inherited_workspace=None,
            build_follow_up_conversation_messages=build_follow_up_conversation_messages,
        )
        assert messages == [
            message
            for index in range(3)
            for message in (
                {"role": "user", "content": f"prompt-{index}"},
                {"role": "assistant", "content": f"answer-{index}"},
            )
        ]
        assert decoded_workspaces == [2]
