# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Copilot execution degradation tests."""

import pytest

from tests.copilot.runtime_support import TEST_LLM_CONFIG, noop_coro as _noop_coro

class TestDegradation:
    @pytest.fixture
    def mock_session_and_run(self, db, novel, entities, chapters):
        from app.core.copilot.service import create_run, open_or_reuse_session
        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        run = create_run(db, session, 1, "测试降级")
        return session, run

    @pytest.mark.asyncio
    async def test_tool_unsupported_degrades_to_one_shot(self, db, novel, entities, chapters, mock_session_and_run, monkeypatch):
        from app.core.ai_client import ToolCallUnsupportedError

        session, run = mock_session_and_run

        one_shot_called = False

        async def mock_tool_loop(*args, **kwargs):
            raise ToolCallUnsupportedError("tools not supported")

        async def mock_one_shot(snapshot, evidence, scenario, session_data, turn_intent, prompt, llm_config, user_id, **kwargs):
            nonlocal one_shot_called
            one_shot_called = True
            return {"answer": "one-shot fallback", "suggestions": []}, evidence

        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_one_shot", mock_one_shot)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        from app.core.copilot.service import execute_copilot_run
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run.run_id, novel.id, 1, TEST_LLM_CONFIG)
        assert one_shot_called
        db.refresh(run)
        assert run.status == "completed"
        assert any(
            step["summary"] == "当前模型不支持分步检索，已切换为直接分析"
            for step in (run.trace_json or [])
        )

        db.close = original_close

    @pytest.mark.asyncio
    async def test_tool_unsupported_degrades_to_one_shot_with_english_trace(self, db, novel, entities, chapters, monkeypatch):
        from app.core.ai_client import ToolCallUnsupportedError
        from app.core.copilot.service import create_run, execute_copilot_run, open_or_reuse_session

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "en", "")
        run = create_run(db, session, 1, "Summarize the world")

        async def mock_tool_loop(*args, **kwargs):
            raise ToolCallUnsupportedError("tools not supported")

        async def mock_one_shot(snapshot, evidence, scenario, session_data, turn_intent, prompt, llm_config, user_id, **kwargs):
            return {"answer": "one-shot fallback", "suggestions": []}, evidence

        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_one_shot", mock_one_shot)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run.run_id, novel.id, 1, TEST_LLM_CONFIG)

        db.refresh(run)
        assert run.status == "completed"
        assert any(
            step["summary"] == "The current model does not support multi-step retrieval, so the run switched to direct analysis"
            for step in (run.trace_json or [])
        )

        db.close = original_close

    @pytest.mark.asyncio
    async def test_both_paths_fail_marks_run_error(self, db, novel, entities, chapters, mock_session_and_run, monkeypatch):
        """When both tool-loop and one-shot fail, run is marked as error."""
        from app.core.ai_client import ToolCallUnsupportedError

        session, run = mock_session_and_run

        async def mock_tool_loop(*args, **kwargs):
            raise ToolCallUnsupportedError("tools not supported")

        async def mock_one_shot(*args, **kwargs):
            raise RuntimeError("one-shot also failed")

        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_one_shot", mock_one_shot)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        from app.core.copilot.service import execute_copilot_run
        await execute_copilot_run(run.run_id, novel.id, 1, TEST_LLM_CONFIG)

        db.refresh(run)
        assert run.status == "error"
        assert run.error is not None

        db.close = original_close

    @pytest.mark.asyncio
    async def test_tool_loop_llm_error_degrades_to_one_shot(self, db, novel, entities, chapters, mock_session_and_run, monkeypatch):
        """When tool loop fails with a non-tool error (e.g. rate limit),
        execution falls back to one-shot instead of dying."""
        session, run = mock_session_and_run

        one_shot_called = False

        async def mock_tool_loop(*args, **kwargs):
            raise RuntimeError("429 rate limit exceeded")

        async def mock_one_shot(snapshot, evidence, scenario, session_data, turn_intent, prompt, llm_config, user_id, **kwargs):
            nonlocal one_shot_called
            one_shot_called = True
            return {"answer": "one-shot after rate limit", "suggestions": []}, evidence

        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_one_shot", mock_one_shot)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        from app.core.copilot.service import execute_copilot_run
        await execute_copilot_run(run.run_id, novel.id, 1, TEST_LLM_CONFIG)
        assert one_shot_called

        db.refresh(run)
        assert run.status == "completed"
        assert run.answer == "one-shot after rate limit"
        assert any(
            "已切换为直接分析" in step["summary"]
            for step in (run.trace_json or [])
        )

        db.close = original_close

    @pytest.mark.asyncio
    async def test_completed_run_records_tool_trace_steps(self, db, novel, entities, chapters, mock_session_and_run, monkeypatch):
        from app.core.copilot.service import execute_copilot_run
        from app.core.copilot.workspace import Workspace

        session, run = mock_session_and_run

        async def mock_tool_loop(
            db_factory, novel_id, session_data, prompt, llm_config, user_id, snapshot, scenario, evidence,
            turn_intent, run_id="", worker_id="", inherited_workspace=None, **kwargs,
        ):
            workspace = Workspace()
            workspace.tool_call_count = 2
            workspace.tool_journal = [
                {
                    "step_id": "tool_1",
                    "kind": "tool_find",
                    "status": "completed",
                    "summary": "搜索「张三」",
                    "tool": "find",
                    "args": {"query": "张三"},
                    "result_summary": '{"total_found": 2}',
                    "round": 1,
                },
                {
                    "step_id": "tool_2",
                    "kind": "tool_read",
                    "status": "completed",
                    "summary": "读取 1 个设定目标，返回 1 条结果",
                    "tool": "read",
                    "args": {"target_refs": [{"type": "entity", "id": entities[0].id}]},
                    "result_summary": '{"results": [{"type": "entity", "id": 1}]}',
                    "round": 1,
                },
            ]
            return {"answer": "done", "suggestions": []}, evidence, workspace

        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run.run_id, novel.id, 1, TEST_LLM_CONFIG)

        db.refresh(run)
        summaries = [step["summary"] for step in (run.trace_json or [])]
        assert run.status == "completed"
        assert "本轮通过分步检索整理信息，共执行 2 步" in summaries
        assert "搜索「张三」" in summaries
        assert "读取 1 个设定目标，返回 1 条结果" in summaries

        db.close = original_close

    @pytest.mark.asyncio
    async def test_capability_query_suppresses_model_suggestions(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot.service import create_run, execute_copilot_run, open_or_reuse_session
        from app.core.copilot.workspace import Workspace

        session, _ = open_or_reuse_session(
            db,
            novel.id,
            1,
            "current_entity",
            "current_entity",
            {"entity_id": entities[0].id, "surface": "studio", "stage": "entity"},
            "zh",
            "张三",
        )
        run = create_run(db, session, 1, "你现在能做什么？")

        async def mock_tool_loop(
            db_factory, novel_id, session_data, prompt, llm_config, user_id, snapshot, scenario, evidence,
            turn_intent, run_id="", worker_id="", inherited_workspace=None, **kwargs,
        ):
            workspace = Workspace()
            return {
                "answer": "我现在在实体检查界面，可以解释当前实体、补充设定、在你明确要求时生成建议卡。",
                "suggestions": [{
                    "kind": "update_entity",
                    "title": "不该出现的建议",
                    "summary": "这条建议应该被抑制",
                    "target_resource": "entity",
                    "target_id": entities[0].id,
                    "delta": {"description": "x"},
                }],
            }, evidence, workspace

        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run.run_id, novel.id, 1, TEST_LLM_CONFIG)

        db.refresh(run)
        assert run.status == "completed"
        assert run.answer.startswith("我现在在实体检查界面")
        assert run.suggestions_json == []
        assert run.evidence_json == []

        db.close = original_close
