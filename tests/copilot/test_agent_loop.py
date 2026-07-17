# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Copilot agent loop tests."""

import pytest

from tests.copilot.runtime_support import TEST_LLM_CONFIG, noop_coro as _noop_coro

class TestAgentLoop:
    @pytest.fixture
    def mock_setup(self, db, novel, entities, chapters):
        """Set up session and run for agent loop tests."""
        from app.core.copilot.service import create_run, open_or_reuse_session
        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        run = create_run(db, session, 1, "分析张三")
        session_data = {
            "mode": session.mode, "scope": session.scope,
            "context_json": run.context_json, "interaction_locale": session.interaction_locale,
        }
        return session_data, run.prompt, session, run

    @pytest.mark.asyncio
    async def test_happy_path_auto_preload_then_find_then_answer(self, db, novel, entities, chapters, mock_setup, monkeypatch):
        from app.core.copilot.runtime_adapters import run_tool_loop as _run_tool_loop
        from app.core.ai_client import ToolLLMResponse, ToolCall

        session_data, prompt, session, run = mock_setup
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.copilot.runtime_scenario import derive_scenario
        snapshot = load_scope_snapshot(db, novel, session.mode, session.scope, session.context_json)
        evidence = gather_evidence(db, novel, snapshot, session.context_json)
        scenario = derive_scenario(session.mode, session.scope, session.context_json)

        call_count = 0

        async def mock_generate_with_tools(self_client, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: agent uses find tool
                return ToolLLMResponse(
                    content=None,
                    tool_calls=[ToolCall(id="call_1", name="find", arguments='{"query": "张三"}')],
                    finish_reason="tool_calls",
                )
            else:
                # Second call: final answer
                return ToolLLMResponse(
                    content='{"answer": "张三是主角", "suggestions": []}',
                    tool_calls=[],
                    finish_reason="stop",
                )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        def test_db_factory():
            return db

        parsed, tool_evidence, workspace = await _run_tool_loop(
            test_db_factory, novel.id, session_data, prompt, TEST_LLM_CONFIG, 1, snapshot, scenario, evidence, "task_query",
        )
        assert parsed["answer"] == "张三是主角"
        assert workspace.tool_call_count >= 1
        assert workspace.prompt_debug is not None
        assert workspace.prompt_debug["system_prompt"]["prompt_id"] == "tool_loop"
        assert "tools" in workspace.prompt_debug["system_prompt"]["section_ids"]
        assert workspace.prompt_debug["auto_preload"]["included"] is True
        assert workspace.tool_journal[0]["tool_metadata"]["read_only"] is True

    @pytest.mark.asyncio
    async def test_recovers_text_form_tool_call_leaked_as_content(self, db, novel, entities, chapters, mock_setup, monkeypatch):
        """A gateway that returns the tool call as plain text is salvaged so
        retrieval still runs and a real answer (not raw markup) is produced."""
        from app.core.copilot.runtime_adapters import run_tool_loop as _run_tool_loop
        from app.core.ai_client import ToolLLMResponse

        session_data, prompt, session, run = mock_setup
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.copilot.runtime_scenario import derive_scenario
        snapshot = load_scope_snapshot(db, novel, session.mode, session.scope, session.context_json)
        evidence = gather_evidence(db, novel, snapshot, session.context_json)
        scenario = derive_scenario(session.mode, session.scope, session.context_json)

        call_count = 0

        async def mock_generate_with_tools(self_client, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Tool call leaked as text content; structured tool_calls empty.
                return ToolLLMResponse(
                    content='<tool_call>{"name": "find", "arguments": {"query": "张三"}}</tool_call>',
                    tool_calls=[],
                    finish_reason="stop",
                )
            return ToolLLMResponse(
                content='{"answer": "张三是主角", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        def test_db_factory():
            return db

        parsed, tool_evidence, workspace = await _run_tool_loop(
            test_db_factory, novel.id, session_data, prompt, TEST_LLM_CONFIG, 1, snapshot, scenario, evidence, "task_query",
        )

        # The find tool actually executed despite the leaked text-form call,
        # and the final answer is clean prose rather than raw markup.
        assert workspace.tool_call_count >= 1
        assert any(entry.get("tool") == "find" for entry in workspace.tool_journal)
        assert parsed["answer"] == "张三是主角"
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_executes_all_tool_calls_from_single_model_turn(self, db, novel, entities, chapters, mock_setup, monkeypatch):
        from app.core.copilot.runtime_adapters import run_tool_loop as _run_tool_loop
        from app.core.ai_client import ToolLLMResponse, ToolCall

        session_data, prompt, session, run = mock_setup
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.copilot.runtime_scenario import derive_scenario
        snapshot = load_scope_snapshot(db, novel, session.mode, session.scope, session.context_json)
        evidence = gather_evidence(db, novel, snapshot, session.context_json)
        scenario = derive_scenario(session.mode, session.scope, session.context_json)

        call_count = 0
        captured_messages = []

        async def mock_generate_with_tools(self_client, **kwargs):
            nonlocal call_count
            call_count += 1
            captured_messages.append(kwargs.get("messages", []))
            if call_count == 1:
                return ToolLLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCall(id="call_1", name="load_scope_snapshot", arguments="{}"),
                        ToolCall(id="call_2", name="find", arguments='{"query": "张三"}'),
                    ],
                    finish_reason="tool_calls",
                )
            return ToolLLMResponse(
                content='{"answer": "done", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        parsed, _, workspace = await _run_tool_loop(
            lambda: db, novel.id, session_data, prompt, TEST_LLM_CONFIG, 1, snapshot, scenario, evidence, "task_query",
        )

        assert parsed["answer"] == "done"
        assert workspace.tool_call_count == 2
        assert [entry["tool"] for entry in workspace.tool_journal] == ["load_scope_snapshot", "find"]
        assert len(captured_messages) == 2
        second_turn_messages = captured_messages[1]
        assert len([m for m in second_turn_messages if m["role"] == "tool"]) == 2
        assistant_with_tools = next(m for m in second_turn_messages if m["role"] == "assistant" and "tool_calls" in m)
        assert len(assistant_with_tools["tool_calls"]) == 2
        assert workspace.tool_journal[0]["tool_metadata"]["execution_path"] == "runtime"
        assert workspace.tool_journal[1]["tool_metadata"]["auto_follow_up_hint"] == "open_first_chapter_pack"

    @pytest.mark.asyncio
    async def test_current_entity_find_auto_opens_chapter_pack_for_progressive_disclosure(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot.runtime_adapters import run_tool_loop as _run_tool_loop
        from app.core.copilot.runtime_scenario import derive_scenario
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.ai_client import ToolLLMResponse, ToolCall

        session_data = {
            "mode": "current_entity",
            "scope": "current_entity",
            "context_json": {"entity_id": entities[0].id},
            "interaction_locale": "zh",
            "display_title": entities[0].name,
        }
        snapshot = load_scope_snapshot(
            db,
            novel,
            session_data["mode"],
            session_data["scope"],
            session_data["context_json"],
        )
        evidence = gather_evidence(db, novel, snapshot, session_data["context_json"])
        scenario = derive_scenario(
            session_data["mode"],
            session_data["scope"],
            session_data["context_json"],
        )

        captured_messages = []
        call_count = 0

        async def mock_generate_with_tools(self_client, **kwargs):
            nonlocal call_count
            call_count += 1
            captured_messages.append(kwargs.get("messages", []))
            if call_count == 1:
                return ToolLLMResponse(
                    content=None,
                    tool_calls=[ToolCall(id="call_1", name="find", arguments='{"query": "张三"}')],
                    finish_reason="tool_calls",
                )
            return ToolLLMResponse(
                content='{"answer": "done", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        parsed, _, workspace = await _run_tool_loop(
            lambda: db,
            novel.id,
            session_data,
            "补完张三",
            TEST_LLM_CONFIG,
            1,
            snapshot,
            scenario,
            evidence,
            "task_query",
        )

        assert parsed["answer"] == "done"
        assert workspace.tool_call_count == 2
        assert len(workspace.opened_pack_ids) == 1
        assert len(captured_messages) == 2
        second_turn_messages = captured_messages[1]
        assert len([m for m in second_turn_messages if m["role"] == "tool"]) == 2
        assert any(
            any(call["function"]["name"] == "open" for call in message.get("tool_calls", []))
            for message in second_turn_messages
            if message["role"] == "assistant" and "tool_calls" in message
        )

    @pytest.mark.asyncio
    async def test_tool_loop_executes_open_many_from_workspace_seed(self, db, novel, entities, chapters, mock_setup, monkeypatch):
        from app.core.copilot.runtime_adapters import run_tool_loop as _run_tool_loop
        from app.core.copilot.runtime_scenario import derive_scenario
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.ai_client import ToolLLMResponse, ToolCall
        from app.core.copilot.workspace import EvidencePack, Workspace

        session_data, prompt, session, run = mock_setup
        chapters[0].content = "第一章写到远古星门重新开启。"
        chapters[1].content = "第二章再次提到远古星门的波动。"
        db.commit()

        snapshot = load_scope_snapshot(db, novel, session.mode, session.scope, session.context_json)
        evidence = gather_evidence(db, novel, snapshot, session.context_json)
        scenario = derive_scenario(session.mode, session.scope, session.context_json)

        workspace_seed = Workspace(
            evidence_packs={
                "pk_a": EvidencePack(
                    pack_id="pk_a",
                    source_refs=[{
                        "type": "chapter",
                        "chapter_id": chapters[0].id,
                        "chapter_number": chapters[0].chapter_number,
                        "start_pos": 0,
                        "end_pos": 12,
                    }],
                    preview_excerpt="第一章写到远古星门",
                    anchor_terms=["远古星门"],
                    support_count=1,
                    related_targets=[{"type": "chapter", "chapter_id": chapters[0].id}],
                ),
                "pk_b": EvidencePack(
                    pack_id="pk_b",
                    source_refs=[{
                        "type": "chapter",
                        "chapter_id": chapters[1].id,
                        "chapter_number": chapters[1].chapter_number,
                        "start_pos": 0,
                        "end_pos": 13,
                    }],
                    preview_excerpt="第二章再次提到远古星门",
                    anchor_terms=["远古星门"],
                    support_count=1,
                    related_targets=[{"type": "chapter", "chapter_id": chapters[1].id}],
                ),
            }
        ).to_dict()

        captured_messages = []
        call_count = 0

        async def mock_generate_with_tools(self_client, **kwargs):
            nonlocal call_count
            call_count += 1
            captured_messages.append(kwargs.get("messages", []))
            if call_count == 1:
                return ToolLLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id="call_1",
                            name="open_many",
                            arguments='{"pack_ids": ["pk_a", "pk_b"], "expand_chars": 600}',
                        )
                    ],
                    finish_reason="tool_calls",
                )
            return ToolLLMResponse(
                content='{"answer": "done", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        parsed, _, workspace = await _run_tool_loop(
            lambda: db,
            novel.id,
            session_data,
            prompt,
            TEST_LLM_CONFIG,
            1,
            snapshot,
            scenario,
            evidence,
            "task_query",
            workspace_seed=workspace_seed,
        )

        assert parsed["answer"] == "done"
        assert workspace.tool_call_count == 1
        assert workspace.opened_pack_ids == ["pk_a", "pk_b"]
        second_turn_messages = captured_messages[1]
        tool_message = next(message for message in second_turn_messages if message["role"] == "tool")
        assert '"opened_count": 2' in tool_message["content"]

    @pytest.mark.asyncio
    async def test_budget_exhaustion_forces_wrap_up(self, db, novel, entities, chapters, mock_setup, monkeypatch):
        from app.core.copilot.runtime_adapters import run_tool_loop as _run_tool_loop
        from app.core.ai_client import ToolLLMResponse, ToolCall

        session_data, prompt, session, run = mock_setup
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.copilot.runtime_scenario import derive_scenario
        snapshot = load_scope_snapshot(db, novel, session.mode, session.scope, session.context_json)
        evidence = gather_evidence(db, novel, snapshot, session.context_json)
        scenario = derive_scenario(session.mode, session.scope, session.context_json)

        call_count = 0

        async def mock_generate_with_tools(self_client, **kwargs):
            nonlocal call_count
            call_count += 1
            tool_choice = kwargs.get("tool_choice")
            if tool_choice == "none":
                # Forced wrap-up
                return ToolLLMResponse(
                    content='{"answer": "预算用尽", "suggestions": []}',
                    tool_calls=[],
                    finish_reason="stop",
                )
            # Always request a tool call to exhaust budget
            return ToolLLMResponse(
                content=None,
                tool_calls=[ToolCall(id=f"call_{call_count}", name="find", arguments='{"query": "test"}')],
                finish_reason="tool_calls",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        # Override max rounds to 2 for faster test
        monkeypatch.setattr("app.config.Settings.copilot_max_tool_rounds", 2, raising=False)

        def test_db_factory():
            return db

        parsed, _, workspace = await _run_tool_loop(
            test_db_factory, novel.id, session_data, prompt, TEST_LLM_CONFIG, 1, snapshot, scenario, evidence, "task_query",
        )
        assert parsed["answer"] == "预算用尽"

    @pytest.mark.asyncio
    async def test_workspace_persisted_after_each_step(self, db, novel, entities, chapters, mock_setup, monkeypatch):
        from app.core.copilot.runtime_adapters import run_tool_loop as _run_tool_loop
        from app.core.ai_client import ToolLLMResponse, ToolCall

        session_data, prompt, session, run = mock_setup

        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.copilot.runtime_scenario import derive_scenario
        snapshot = load_scope_snapshot(db, novel, session.mode, session.scope, session.context_json)
        evidence = gather_evidence(db, novel, snapshot, session.context_json)
        scenario = derive_scenario(session.mode, session.scope, session.context_json)

        persist_calls = []

        def mock_persist(db_factory, run_id, workspace, **kwargs):
            persist_calls.append(run_id)
            return True

        monkeypatch.setattr("app.core.copilot.run_store.persist_running_workspace", mock_persist)

        call_count = 0

        async def mock_generate_with_tools(self_client, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ToolLLMResponse(
                    content=None,
                    tool_calls=[ToolCall(id="c1", name="find", arguments='{"query": "test"}')],
                    finish_reason="tool_calls",
                )
            return ToolLLMResponse(
                content='{"answer": "done", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        def test_db_factory():
            return db

        await _run_tool_loop(
            test_db_factory, novel.id, session_data, prompt, TEST_LLM_CONFIG, 1, snapshot, scenario, evidence, "task_query",
            run_id="test-persist-run",
        )
        assert len(persist_calls) >= 1

    @pytest.mark.asyncio
    async def test_smalltalk_turn_skips_auto_preload_dump(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot.runtime_adapters import run_tool_loop as _run_tool_loop
        from app.core.copilot.scope import load_scope_snapshot
        from app.core.copilot.runtime_scenario import derive_scenario
        from app.core.ai_client import ToolLLMResponse

        snapshot = load_scope_snapshot(
            db, novel, "current_entity", "current_entity",
            {"entity_id": entities[0].id, "surface": "studio", "stage": "entity"},
        )
        scenario = derive_scenario("current_entity", "current_entity", {"entity_id": entities[0].id})
        captured_messages = []

        async def mock_generate_with_tools(self_client, **kwargs):
            captured_messages.append(kwargs.get("messages", []))
            return ToolLLMResponse(
                content='{"answer": "你好，我现在在实体检查界面", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        parsed, _, _ = await _run_tool_loop(
            lambda: db,
            novel.id,
            {
                "mode": "current_entity",
                "scope": "current_entity",
                "context_json": {"entity_id": entities[0].id, "surface": "studio", "stage": "entity"},
                "interaction_locale": "zh",
                "display_title": "张三",
            },
            "你好",
            TEST_LLM_CONFIG,
            1,
            snapshot,
            scenario,
            [],
            "smalltalk",
        )

        assert parsed["answer"].startswith("你好")
        assert len(captured_messages) == 1
        assert "[Auto-preloaded world model summary]" not in captured_messages[0][1]["content"]
