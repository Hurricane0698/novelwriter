# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Copilot lease recovery and resumed loop tests."""

import pytest

from app.models import CopilotRun
from tests.copilot.runtime_support import TEST_LLM_CONFIG, noop_coro as _noop_coro

class TestLeaseRecovery:
    @pytest.mark.asyncio
    async def test_lease_loss_during_execution_preserves_interrupted_state(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot.messages import CopilotTextKey, get_copilot_text
        from app.core.copilot.runtime_errors import RunLeaseLostError
        from app.core.copilot.run_state import (
            interrupt_run as _interrupt_run,
            utcnow_naive as _utcnow_naive,
        )
        from app.core.copilot.service import (
            create_run,
            execute_copilot_run,
            open_or_reuse_session,
        )

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        run = create_run(db, session, 1, "分析全书")
        interrupted_message = get_copilot_text(CopilotTextKey.RUN_INTERRUPTED, locale="zh")

        async def mock_tool_loop(
            db_factory, novel_id, session_data, prompt, llm_config, user_id, snapshot, scenario, evidence,
            turn_intent, run_id="", worker_id="", inherited_workspace=None, **kwargs,
        ):
            interrupted_run = db.query(CopilotRun).filter(CopilotRun.run_id == run_id).first()
            _interrupt_run(interrupted_run, message=interrupted_message, now=_utcnow_naive())
            db.commit()
            raise RunLeaseLostError(run_id)

        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run.run_id, novel.id, 1, TEST_LLM_CONFIG)

        db.refresh(run)
        assert run.status == "interrupted"
        assert run.error == interrupted_message
        assert run.finished_at is not None

        db.close = original_close

    @pytest.mark.asyncio
    async def test_resumed_loop_uses_inherited_messages_and_reduced_budget(self, db, novel, entities, chapters, monkeypatch):
        """When _run_tool_loop receives inherited_workspace, it:
        1. Starts from the inherited messages (not fresh system prompt)
        2. Has reduced round budget (max_rounds - rounds_used)
        3. Preserves inherited evidence packs in workspace
        """
        from app.core.copilot.runtime_adapters import run_tool_loop as _run_tool_loop
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.copilot.runtime_scenario import derive_scenario
        from app.core.copilot.workspace import EvidencePack, Workspace
        from app.core.ai_client import ToolLLMResponse

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        scenario = derive_scenario("research", "whole_book", None)
        session_data = {"mode": "research", "scope": "whole_book", "context_json": None, "interaction_locale": "zh"}

        # Build an inherited workspace that used 6 of 8 rounds
        prev_ws = Workspace()
        prev_ws.round_count = 6
        prev_ws.tool_call_count = 6
        prev_ws.evidence_packs["pk_prev"] = EvidencePack(
            pack_id="pk_prev", source_refs=[{"type": "entity", "id": 1}],
            preview_excerpt="已有证据", anchor_terms=["张三"],
            support_count=1, related_targets=[],
        )
        prev_ws.messages = [
            {"role": "system", "content": "previous system prompt"},
            {"role": "user", "content": "original question"},
        ]

        received_messages = []

        async def mock_generate(self_client, **kwargs):
            received_messages.append(kwargs.get("messages", []))
            # Return final answer immediately
            return ToolLLMResponse(
                content='{"answer": "resumed answer", "suggestions": []}',
                tool_calls=[], finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        parsed, final_ev, workspace = await _run_tool_loop(
            lambda: db, novel.id, session_data, "继续", TEST_LLM_CONFIG, 1,
            snapshot, scenario, evidence, "task_query",
            inherited_workspace=prev_ws.to_dict(),
        )

        # 1. Answer came through
        assert parsed["answer"] == "resumed answer"

        # 2. LLM received the inherited messages (not fresh system prompt)
        assert len(received_messages) == 1
        msgs = received_messages[0]
        assert msgs[0]["content"] == "previous system prompt"  # inherited, not rebuilt
        assert msgs[1]["content"] == "original question"

        # 3. Inherited evidence packs preserved
        assert "pk_prev" in workspace.evidence_packs

        # 4. Round count continues from inherited
        assert workspace.round_count >= 7  # was 6, now at least 7

    @pytest.mark.asyncio
    async def test_resumed_loop_finishes_pending_tool_batch_before_next_llm_call(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot.runtime_adapters import run_tool_loop as _run_tool_loop
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.copilot.runtime_scenario import derive_scenario
        from app.core.copilot.workspace import Workspace
        from app.core.ai_client import ToolLLMResponse

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        scenario = derive_scenario("research", "whole_book", None)
        session_data = {"mode": "research", "scope": "whole_book", "context_json": None, "interaction_locale": "zh"}

        prev_ws = Workspace()
        prev_ws.round_count = 2
        prev_ws.tool_call_count = 1
        prev_ws.messages = [
            {"role": "system", "content": "previous system prompt"},
            {"role": "user", "content": "original question"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "load_scope_snapshot", "arguments": "{}"}},
                    {"id": "c2", "type": "function", "function": {"name": "find", "arguments": '{"query": "张三"}'}},
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": '{"profile": "broad_exploration"}'},
        ]
        prev_ws.pending_tool_calls = [{"id": "c2", "name": "find", "arguments": '{"query": "张三"}'}]

        received_messages = []

        async def mock_generate(self_client, **kwargs):
            received_messages.append(kwargs.get("messages", []))
            return ToolLLMResponse(
                content='{"answer": "resumed answer", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        parsed, _, workspace = await _run_tool_loop(
            lambda: db,
            novel.id,
            session_data,
            "继续",
            TEST_LLM_CONFIG,
            1,
            snapshot,
            scenario,
            evidence,
            "task_query",
            inherited_workspace=prev_ws.to_dict(),
        )

        assert parsed["answer"] == "resumed answer"
        assert workspace.tool_call_count == 2
        assert workspace.pending_tool_calls == []
        assert len(received_messages) == 1
        resumed_messages = received_messages[0]
        assert len([m for m in resumed_messages if m["role"] == "tool"]) == 2
        assistant_with_tools = next(m for m in resumed_messages if m["role"] == "assistant" and "tool_calls" in m)
        assert len(assistant_with_tools["tool_calls"]) == 2

    @pytest.mark.asyncio
    async def test_follow_up_loop_uses_prior_conversation_but_fresh_budget(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot.runtime_adapters import run_tool_loop as _run_tool_loop
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.copilot.runtime_scenario import derive_scenario
        from app.core.copilot.workspace import EvidencePack, Workspace
        from app.core.ai_client import ToolLLMResponse

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        scenario = derive_scenario("research", "whole_book", None)
        session_data = {"mode": "research", "scope": "whole_book", "context_json": None, "interaction_locale": "zh"}

        prior_workspace = Workspace()
        prior_workspace.round_count = 6
        prior_workspace.tool_call_count = 6
        prior_workspace.pending_tool_calls = [{"id": "stale", "name": "find", "arguments": "{}"}]
        prior_workspace.evidence_packs["pk_prev"] = EvidencePack(
            pack_id="pk_prev",
            source_refs=[{"type": "entity", "id": 1}],
            preview_excerpt="已有证据",
            anchor_terms=["张三"],
            support_count=1,
            related_targets=[],
        )
        prior_workspace.opened_pack_ids = ["pk_prev"]

        received_messages = []

        async def mock_generate(self_client, **kwargs):
            received_messages.append(kwargs.get("messages", []))
            return ToolLLMResponse(
                content='{"answer": "follow-up answer", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        parsed, _, workspace = await _run_tool_loop(
            lambda: db,
            novel.id,
            session_data,
            "继续分析张三和宗门的联系",
            TEST_LLM_CONFIG,
            1,
            snapshot,
            scenario,
            evidence,
            "task_query",
            prior_messages=[
                {"role": "user", "content": "先总结一下张三"},
                {"role": "assistant", "content": "张三目前是主角。"},
            ],
            workspace_seed=prior_workspace.to_dict(),
        )

        assert parsed["answer"] == "follow-up answer"
        assert len(received_messages) == 1
        msgs = received_messages[0]
        assert msgs[0]["role"] == "system"
        assert msgs[1] == {"role": "user", "content": "先总结一下张三"}
        assert msgs[2] == {"role": "assistant", "content": "张三目前是主角。"}
        assert "继续分析张三和宗门的联系" in msgs[3]["content"]
        assert "pk_prev" in workspace.evidence_packs
        assert workspace.opened_pack_ids == ["pk_prev"]
        assert workspace.round_count >= 1
        assert workspace.tool_call_count == 0
        assert workspace.pending_tool_calls == []

    @pytest.mark.asyncio
    async def test_resumed_loop_budget_exhaustion_still_forces_wrapup(self, db, novel, entities, chapters, monkeypatch):
        """If inherited workspace already used all rounds, the loop immediately
        forces a wrap-up call (tool_choice=none)."""
        from app.core.copilot.runtime_adapters import run_tool_loop as _run_tool_loop
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.copilot.runtime_scenario import derive_scenario
        from app.core.copilot.workspace import Workspace
        from app.core.ai_client import ToolLLMResponse

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        scenario = derive_scenario("research", "whole_book", None)
        session_data = {"mode": "research", "scope": "whole_book", "context_json": None, "interaction_locale": "zh"}

        # Workspace used all 8 rounds
        prev_ws = Workspace()
        prev_ws.round_count = 8
        prev_ws.messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
        ]

        tool_choice_seen = []

        async def mock_generate(self_client, **kwargs):
            tool_choice_seen.append(kwargs.get("tool_choice"))
            return ToolLLMResponse(
                content='{"answer": "budget done", "suggestions": []}',
                tool_calls=[], finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate)
        monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)

        parsed, _, _ = await _run_tool_loop(
            lambda: db, novel.id, session_data, "继续", TEST_LLM_CONFIG, 1,
            snapshot, scenario, evidence, "task_query",
            inherited_workspace=prev_ws.to_dict(),
        )

        assert parsed["answer"] == "budget done"
        # The loop had 0 remaining rounds, so it went straight to wrap-up
        assert "none" in tool_choice_seen
