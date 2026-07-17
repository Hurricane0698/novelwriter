# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Copilot workspace inheritance and follow-up tests."""

import pytest

from tests.copilot.runtime_support import TEST_LLM_CONFIG

class TestWorkspaceResume:
    """Verify that an interrupted run's workspace is inherited and resumed,
    not restarted from scratch."""

    def test_interrupted_run_workspace_not_inherited_by_default_new_run(self, db, novel, entities, chapters):
        """Fresh runs must not silently inherit interrupted workspace."""
        from app.core.copilot.service import create_run, open_or_reuse_session
        from app.core.copilot.workspace import EvidencePack, Workspace

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")

        # Create first run, simulate it getting interrupted with workspace
        run1 = create_run(db, session, 1, "分析全书")
        ws = Workspace()
        ws.evidence_packs["pk_test"] = EvidencePack(
            pack_id="pk_test", source_refs=[{"type": "entity", "id": 1}],
            preview_excerpt="张三是主角", anchor_terms=["张三"],
            support_count=2, related_targets=[],
        )
        ws.round_count = 3
        ws.tool_call_count = 3
        ws.messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "分析全书"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "find", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "results"},
        ]
        run1.status = "interrupted"
        run1.workspace_json = ws.to_dict()
        db.commit()

        # Fresh follow-up should start clean unless caller explicitly resumes run1.
        run2 = create_run(db, session, 1, "继续分析")
        assert run2.workspace_json is None

    def test_explicit_resume_inherits_interrupted_workspace(self, db, novel, entities, chapters):
        """Explicit resume requests may inherit interrupted workspace."""
        from app.core.copilot.service import create_run, open_or_reuse_session
        from app.core.copilot.workspace import EvidencePack, Workspace

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")

        run1 = create_run(db, session, 1, "分析全书")
        ws = Workspace()
        ws.evidence_packs["pk_test"] = EvidencePack(
            pack_id="pk_test", source_refs=[{"type": "entity", "id": 1}],
            preview_excerpt="张三是主角", anchor_terms=["张三"],
            support_count=2, related_targets=[],
        )
        ws.round_count = 3
        ws.tool_call_count = 3
        ws.messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "分析全书"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "find", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "results"},
        ]
        run1.status = "interrupted"
        run1.workspace_json = ws.to_dict()
        db.commit()

        run2 = create_run(db, session, 1, "分析全书", resume_run_id=run1.run_id)
        assert run2.workspace_json is not None
        inherited = run2.workspace_json
        assert "pk_test" in inherited["evidence_packs"]
        assert inherited["round_count"] == 3
        assert len(inherited["messages"]) == 4

    def test_explicit_resume_requires_matching_prompt(self, db, novel, entities, chapters):
        from app.core.copilot.runtime_errors import CopilotError
        from app.core.copilot.service import create_run, open_or_reuse_session
        from app.core.copilot.workspace import Workspace

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")

        run1 = create_run(db, session, 1, "分析全书")
        run1.status = "interrupted"
        run1.workspace_json = Workspace(messages=[{"role": "user", "content": "分析全书"}]).to_dict()
        db.commit()

        with pytest.raises(CopilotError) as exc_info:
            create_run(db, session, 1, "继续分析", resume_run_id=run1.run_id)
        assert exc_info.value.code == "resume_prompt_mismatch"

    def test_completed_run_workspace_not_inherited(self, db, novel, entities, chapters):
        """Only interrupted runs donate their workspace, not completed ones."""
        from app.core.copilot.service import create_run, open_or_reuse_session
        from app.core.copilot.workspace import Workspace

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")

        run1 = create_run(db, session, 1, "分析全书")
        run1.status = "completed"
        run1.workspace_json = Workspace().to_dict()
        db.commit()

        run2 = create_run(db, session, 1, "新问题")
        assert run2.workspace_json is None

    @pytest.mark.asyncio
    async def test_completed_follow_up_run_uses_prior_conversation_and_workspace_seed(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot.service import create_run, execute_copilot_run, open_or_reuse_session
        from app.core.copilot.workspace import EvidencePack, Workspace

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")

        run1 = create_run(db, session, 1, "先总结张三")
        ws = Workspace()
        ws.evidence_packs["pk_prev"] = EvidencePack(
            pack_id="pk_prev",
            source_refs=[{"type": "entity", "id": entities[0].id}],
            preview_excerpt="张三是主角",
            anchor_terms=["张三"],
            support_count=2,
            related_targets=[],
        )
        ws.opened_pack_ids = ["pk_prev"]
        run1.status = "completed"
        run1.answer = "张三目前是主角，和宗门联系密切。"
        run1.workspace_json = ws.to_dict()
        db.commit()

        run2 = create_run(db, session, 1, "继续分析宗门线索")
        captured: dict[str, object] = {}

        async def mock_tool_loop(
            db_factory, novel_id, session_data, prompt, llm_config, user_id, snapshot, scenario, evidence,
            turn_intent, run_id="", worker_id="", inherited_workspace=None, prior_messages=None, workspace_seed=None,
        ):
            captured["inherited_workspace"] = inherited_workspace
            captured["prior_messages"] = prior_messages
            captured["workspace_seed"] = workspace_seed
            return {"answer": "follow-up", "suggestions": []}, evidence, Workspace()

        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.copilot.scope.gather_evidence", lambda *_args, **_kwargs: [])
        monkeypatch.setattr("app.core.copilot.suggestions.compile_suggestions", lambda *_args, **_kwargs: [])
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run2.run_id, novel.id, 1, TEST_LLM_CONFIG)

        assert captured["inherited_workspace"] is None
        assert captured["prior_messages"] == [
            {"role": "user", "content": "先总结张三"},
            {"role": "assistant", "content": "张三目前是主角，和宗门联系密切。"},
        ]
        workspace_seed = captured["workspace_seed"]
        assert isinstance(workspace_seed, dict)
        assert workspace_seed["evidence_packs"]["pk_prev"]["pack_id"] == "pk_prev"
        assert workspace_seed["opened_pack_ids"] == ["pk_prev"]
        assert workspace_seed["round_count"] == 0
        assert workspace_seed["tool_call_count"] == 0
        assert workspace_seed["pending_tool_calls"] == []
        assert workspace_seed["prompt_debug"] is None

        db.close = original_close

    @pytest.mark.asyncio
    async def test_interrupted_follow_up_run_uses_new_prompt_instead_of_resuming(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot.service import create_run, execute_copilot_run, open_or_reuse_session
        from app.core.copilot.workspace import EvidencePack, Workspace

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")

        run1 = create_run(db, session, 1, "旧问题")
        ws = Workspace()
        ws.evidence_packs["pk_prev"] = EvidencePack(
            pack_id="pk_prev",
            source_refs=[{"type": "entity", "id": entities[0].id}],
            preview_excerpt="张三是主角",
            anchor_terms=["张三"],
            support_count=2,
            related_targets=[],
        )
        ws.messages = [
            {"role": "system", "content": "previous system prompt"},
            {"role": "user", "content": "旧问题"},
        ]
        run1.status = "interrupted"
        run1.workspace_json = ws.to_dict()
        db.commit()

        run2 = create_run(db, session, 1, "新问题")
        captured: dict[str, object] = {}

        async def mock_tool_loop(
            db_factory, novel_id, session_data, prompt, llm_config, user_id, snapshot, scenario, evidence,
            turn_intent, run_id="", worker_id="", inherited_workspace=None, prior_messages=None, workspace_seed=None,
        ):
            captured["prompt"] = prompt
            captured["inherited_workspace"] = inherited_workspace
            captured["prior_messages"] = prior_messages
            captured["workspace_seed"] = workspace_seed
            return {"answer": "fresh follow-up", "suggestions": []}, evidence, Workspace()

        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.copilot.scope.gather_evidence", lambda *_args, **_kwargs: [])
        monkeypatch.setattr("app.core.copilot.suggestions.compile_suggestions", lambda *_args, **_kwargs: [])
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run2.run_id, novel.id, 1, TEST_LLM_CONFIG)

        assert captured["prompt"] == "新问题"
        assert captured["inherited_workspace"] is None
        assert captured["prior_messages"] == []
        assert captured["workspace_seed"] is None

        db.close = original_close
