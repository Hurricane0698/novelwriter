"""Observe real event-loop, session and cancellation boundaries without a model."""

import asyncio
import threading
import time

import pytest
from sqlalchemy import event

from app.core.ai_client import ToolCall, ToolLLMResponse
from tests.copilot.runtime_support import TEST_LLM_CONFIG
from tests.copilot.test_resource_lifecycle import (
    _seed_runtime,
    runtime_database as runtime_database,
)
from tests.copilot.test_sync_runtime import wait_started


@pytest.mark.asyncio
async def test_run_database_work_stays_off_event_loop(runtime_database, monkeypatch):
    from app.core.copilot.service import execute_copilot_run

    engine, factory, _ = runtime_database
    novel_id, run_id, _, _, _ = _seed_runtime(factory)
    loop_thread = threading.get_ident()
    sql_threads = []

    def observe_sql(*args):
        sql_threads.append(threading.get_ident())

    event.listen(engine, "before_cursor_execute", observe_sql)

    async def model_response(self, **kwargs):
        assert engine.pool.checkedout() == 0
        return ToolLLMResponse(content='{"answer":"完成","suggestions":[]}')

    monkeypatch.setattr(
        "app.core.ai_client.AIClient.generate_with_tools", model_response
    )
    try:
        await execute_copilot_run(run_id, novel_id, 1, TEST_LLM_CONFIG)
    finally:
        event.remove(engine, "before_cursor_execute", observe_sql)
    assert sql_threads
    assert loop_thread not in sql_threads
    assert engine.pool.checkedout() == 0


@pytest.mark.asyncio
async def test_tool_batch_allows_other_requests_to_progress(
    runtime_database, monkeypatch
):
    from app.core.copilot import runtime_adapters

    _, factory, _ = runtime_database
    novel_id, _, data, snapshot, evidence = _seed_runtime(factory)
    entered = threading.Event()
    finished = threading.Event()
    request_seen_during_tool = False
    calls = 0
    dispatch = runtime_adapters._dispatch_tool

    def slow_dispatch(*args, **kwargs):
        entered.set()
        time.sleep(0.12)
        result = dispatch(*args, **kwargs)
        finished.set()
        return result

    async def model_response(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ToolLLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(id="find", name="find", arguments='{"query":"张三"}')
                ],
            )
        return ToolLLMResponse(content='{"answer":"完成","suggestions":[]}')

    async def concurrent_request():
        nonlocal request_seen_during_tool
        while not entered.is_set():
            await asyncio.sleep(0.001)
        request_seen_during_tool = not finished.is_set()

    monkeypatch.setattr(runtime_adapters, "_dispatch_tool", slow_dispatch)
    monkeypatch.setattr(
        "app.core.ai_client.AIClient.generate_with_tools", model_response
    )
    await asyncio.gather(
        runtime_adapters.run_tool_loop(
            factory,
            novel_id,
            data,
            "张三",
            TEST_LLM_CONFIG,
            1,
            snapshot,
            "entity_completion",
            evidence,
            "task_query",
        ),
        concurrent_request(),
    )
    assert request_seen_during_tool


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_failure", [False, True])
async def test_cancelled_tool_closes_session_without_writing_or_fallback(
    runtime_database, monkeypatch, tool_failure
):
    from app.core.copilot import runtime_adapters
    from app.core.copilot.service import execute_copilot_run
    from app.models import Chapter, CopilotRun

    engine, factory, _ = runtime_database
    novel_id, run_id, _, _, _ = _seed_runtime(factory)
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    model_calls = 0
    fallback_calls = []
    dispatch = runtime_adapters._dispatch_tool

    def blocking_dispatch(name, args, db, *rest):
        try:
            assert db.query(Chapter).count() == 1
            started.set()
            assert release.wait(2)
            if tool_failure:
                raise ValueError("failure racing with cancellation")
            return dispatch(name, args, db, *rest)
        finally:
            finished.set()

    async def model_response(self, **kwargs):
        nonlocal model_calls
        model_calls += 1
        return ToolLLMResponse(
            content=None,
            tool_calls=[ToolCall(id="find", name="find", arguments='{"query":"张三"}')],
        )

    async def unexpected_fallback(*args, **kwargs):
        fallback_calls.append(True)
        raise AssertionError("cancelled runs must not start fallback")

    monkeypatch.setattr(runtime_adapters, "_dispatch_tool", blocking_dispatch)
    monkeypatch.setattr(runtime_adapters, "run_one_shot", unexpected_fallback)
    monkeypatch.setattr(
        "app.core.ai_client.AIClient.generate_with_tools", model_response
    )
    task = asyncio.create_task(
        execute_copilot_run(run_id, novel_id, 1, TEST_LLM_CONFIG)
    )
    try:
        await wait_started(started)
        assert engine.pool.checkedout() == 1
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
        assert engine.pool.checkedout() == 0
        with factory() as db:
            run = db.query(CopilotRun).filter_by(run_id=run_id).one()
            assert run.status == "running"  # existing lease-based resume contract
            assert len(run.workspace_json["pending_tool_calls"]) == 1
            assert run.workspace_json["tool_journal"] == []
        assert model_calls == 1
        assert fallback_calls == []
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_compilation_reloads_values_changed_while_awaiting_model(
    runtime_database, monkeypatch
):
    from app.core.copilot import suggestions
    from app.core.copilot.service import execute_copilot_run
    from app.core.copilot.sync_runtime import run_sync
    from app.models import WorldEntity

    _, factory, _ = runtime_database
    novel_id, run_id, _, _, _ = _seed_runtime(factory)
    seen_descriptions = []
    compile_suggestions = suggestions.compile_suggestions

    def change_world():
        with factory() as db:
            db.query(WorldEntity).filter_by(
                novel_id=novel_id
            ).one().description = "模型等待期间的新状态"
            db.commit()

    async def model_response(self, **kwargs):
        await run_sync(change_world)
        return ToolLLMResponse(content='{"answer":"完成","suggestions":[]}')

    def observe_compile(raw, evidence, snapshot, *args, **kwargs):
        seen_descriptions.extend(row.description for row in snapshot.entities)
        return compile_suggestions(raw, evidence, snapshot, *args, **kwargs)

    monkeypatch.setattr(suggestions, "compile_suggestions", observe_compile)
    monkeypatch.setattr(
        "app.core.ai_client.AIClient.generate_with_tools", model_response
    )
    await execute_copilot_run(run_id, novel_id, 1, TEST_LLM_CONFIG)
    assert seen_descriptions == ["模型等待期间的新状态"]
