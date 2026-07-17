# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Copilot prompt contract tests."""

import pytest

from app.core.llm_config import ResolvedLlmConfig
from app.models import CopilotRun, CopilotSession
from tests.copilot.runtime_support import TestingSessionLocal

_LLM_CONFIG = ResolvedLlmConfig(
    base_url="https://example.com/v1",
    api_key="key",
    model="model",
    billing_source_hint="selfhost",
    source="selfhost_settings",
)

class TestPromptContracts:
    def test_run_create_keeps_quick_action_prefix_out_of_response_prompt(self, client, db, novel, monkeypatch):
        from app.api import copilot as copilot_api

        session_resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={"mode": "research", "scope": "whole_book"},
        )
        assert session_resp.status_code == 200
        session_id = session_resp.json()["session_id"]

        scheduled: list[object] = []

        def fake_create_task(coro):
            scheduled.append(coro)
            coro.close()
            return object()

        monkeypatch.setattr(copilot_api.asyncio, "create_task", fake_create_task)

        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs",
            json={
                "prompt": "请盘点当前世界模型的缺口。",
                "quick_action_id": "scan_world_gaps",
            },
        )
        assert resp.status_code == 202

        payload = resp.json()
        run = db.query(CopilotRun).filter(CopilotRun.run_id == payload["run_id"]).one()
        assert payload["prompt"] == "请盘点当前世界模型的缺口。"
        assert run.prompt == "请盘点当前世界模型的缺口。"
        assert run.quick_action_id == "scan_world_gaps"
        assert len(scheduled) == 1

    @pytest.mark.asyncio
    async def test_execute_copilot_run_uses_internal_quick_action_prompt(self, db, novel, monkeypatch):
        import app.database as db_mod

        from app.core.copilot.service import create_run, execute_copilot_run, open_or_reuse_session

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        run = create_run(
            db,
            session,
            1,
            "请盘点当前世界模型的缺口。",
            quick_action_id="scan_world_gaps",
        )

        captured_prompts: list[str] = []

        async def fake_run_tool_loop(_db_factory, _novel_id, _session_data, prompt, *_args, **_kwargs):
            captured_prompts.append(prompt)
            return {"answer": "完成", "suggestions": []}, [], None

        monkeypatch.setattr(db_mod, "SessionLocal", TestingSessionLocal)
        monkeypatch.setattr("app.core.copilot.scope.gather_evidence", lambda *_args, **_kwargs: [])
        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_tool_loop", fake_run_tool_loop)
        monkeypatch.setattr("app.core.copilot.suggestions.compile_suggestions", lambda *_args, **_kwargs: [])

        await execute_copilot_run(run.run_id, novel.id, 1, llm_config=_LLM_CONFIG)

        db.expire_all()
        run = db.query(CopilotRun).filter(CopilotRun.run_id == run.run_id).one()
        assert run.status == "completed"
        assert run.prompt == "请盘点当前世界模型的缺口。"
        assert captured_prompts == [
            "[研究重点: 重点找出世界模型中尚未覆盖但章节反复提到的设定、组织或概念。]\n\n请盘点当前世界模型的缺口。",
        ]

    @pytest.mark.asyncio
    async def test_execute_copilot_run_uses_run_context_snapshot_after_session_retarget(self, db, novel, entities, monkeypatch):
        import app.database as db_mod

        from app.core.copilot.service import create_run, execute_copilot_run, open_or_reuse_session

        studio_context = {"entity_id": entities[0].id, "surface": "studio", "stage": "entity"}
        atlas_context = {"entity_id": entities[0].id, "surface": "atlas", "tab": "entities"}

        session, _ = open_or_reuse_session(
            db,
            novel.id,
            1,
            "current_entity",
            "current_entity",
            studio_context,
            "zh",
            "张三",
        )
        run = create_run(db, session, 1, "分析张三")

        reused, created = open_or_reuse_session(
            db,
            novel.id,
            1,
            "current_entity",
            "current_entity",
            atlas_context,
            "zh",
            "张三 Atlas",
        )
        assert created is False
        assert reused.session_id == session.session_id

        captured_contexts: list[dict | None] = []

        def fail_after_capturing_context(_db, _novel, _mode, _scope, context):
            captured_contexts.append(context)
            raise RuntimeError("stop after context capture")

        monkeypatch.setattr(db_mod, "SessionLocal", TestingSessionLocal)
        monkeypatch.setattr("app.core.copilot.scope.load_scope_snapshot", fail_after_capturing_context)

        await execute_copilot_run(run.run_id, novel.id, 1, llm_config=_LLM_CONFIG)

        db.expire_all()
        run = db.query(CopilotRun).filter(CopilotRun.run_id == run.run_id).one()
        session = db.query(CopilotSession).filter(CopilotSession.session_id == session.session_id).one()

        assert captured_contexts == [studio_context]
        assert run.context_json == studio_context
        assert session.context_json == atlas_context
        assert run.status == "error"
