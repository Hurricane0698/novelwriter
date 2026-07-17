# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Copilot hosted quota billing tests."""

import pytest

from app.core.llm_config import ResolvedLlmConfig
from app.models import CopilotRun, QuotaReservation
from tests.copilot.runtime_support import TestingSessionLocal

_SELFHOST_BILLING_CONFIG = ResolvedLlmConfig(
    base_url="https://example.com/v1",
    api_key="key",
    model="model",
    billing_source_hint="selfhost",
    source="selfhost_settings",
)

class TestHostedQuotaBilling:
    def test_run_create_reserves_quota_and_links_reservation(self, hosted_client, db, novel, hosted_user, monkeypatch):
        from app.api import copilot as copilot_api

        novel.owner_id = hosted_user.id
        db.commit()
        db.refresh(novel)

        session_resp = hosted_client.post(
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

        resp = hosted_client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs",
            json={"prompt": "分析张三"},
        )
        assert resp.status_code == 202

        data = resp.json()
        run = db.query(CopilotRun).filter(CopilotRun.run_id == data["run_id"]).one()
        reservation = db.query(QuotaReservation).filter(QuotaReservation.id == run.quota_reservation_id).one()

        db.refresh(hosted_user)
        assert hosted_user.generation_quota == 1
        assert run.quota_reservation_id is not None
        assert reservation.reserved_count == 1
        assert reservation.charged_count == 0
        assert reservation.released_at is None
        assert len(scheduled) == 1

    def test_run_create_returns_structured_quota_code_when_quota_is_exhausted(self, hosted_client, db, novel, hosted_user):
        novel.owner_id = hosted_user.id
        hosted_user.generation_quota = 0
        db.commit()
        db.refresh(novel)
        db.refresh(hosted_user)

        session_resp = hosted_client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={"mode": "research", "scope": "whole_book"},
        )
        assert session_resp.status_code == 200
        session_id = session_resp.json()["session_id"]

        resp = hosted_client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs",
            json={"prompt": "分析张三"},
        )

        assert resp.status_code == 429
        data = resp.json()
        assert data["detail"]["code"] == "generation_quota_exhausted"
        assert "quota exhausted" in data["detail"]["message"].lower()

    def test_reclaim_stale_run_refunds_reserved_quota(self, db, novel, hosted_user):
        from datetime import datetime, timedelta, timezone

        from app.core.auth import open_quota_reservation
        from app.core.copilot.run_state import reclaim_stale_runs
        from app.core.copilot.service import create_run, open_or_reuse_session

        novel.owner_id = hosted_user.id
        db.commit()

        session, _ = open_or_reuse_session(db, novel.id, hosted_user.id, "research", "whole_book", None, "zh", "")
        reservation_id = open_quota_reservation(db, hosted_user.id, count=1)
        run = create_run(db, session, hosted_user.id, "排队中的请求", quota_reservation_id=reservation_id)
        run.lease_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=60)
        db.commit()

        reclaimed = reclaim_stale_runs(db, run_ids=[run.run_id])

        db.refresh(run)
        db.refresh(hosted_user)
        reservation = db.query(QuotaReservation).filter(QuotaReservation.id == reservation_id).one()
        assert reclaimed == [run.run_id]
        assert run.status == "interrupted"
        assert hosted_user.generation_quota == 2
        assert reservation.charged_count == 0
        assert reservation.released_at is not None

    @pytest.mark.asyncio
    async def test_execute_copilot_run_charges_completed_hosted_run(self, db, novel, hosted_user, monkeypatch):
        import app.database as db_mod
        from app.core.auth import open_quota_reservation
        from app.core.copilot.service import create_run, execute_copilot_run, open_or_reuse_session

        novel.owner_id = hosted_user.id
        db.commit()

        session, _ = open_or_reuse_session(db, novel.id, hosted_user.id, "research", "whole_book", None, "zh", "")
        reservation_id = open_quota_reservation(db, hosted_user.id, count=1)
        run = create_run(db, session, hosted_user.id, "分析张三", quota_reservation_id=reservation_id)

        async def fake_run_tool_loop(*_args, **_kwargs):
            return {"answer": "已完成分析", "suggestions": []}, [], None

        monkeypatch.setattr(db_mod, "SessionLocal", TestingSessionLocal)
        monkeypatch.setattr("app.core.copilot.scope.gather_evidence", lambda *_args, **_kwargs: [])
        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_tool_loop", fake_run_tool_loop)
        monkeypatch.setattr("app.core.copilot.suggestions.compile_suggestions", lambda *_args, **_kwargs: [])

        await execute_copilot_run(
            run.run_id,
            novel.id,
            hosted_user.id,
            llm_config=_SELFHOST_BILLING_CONFIG,
        )

        db.expire_all()
        run = db.query(CopilotRun).filter(CopilotRun.run_id == run.run_id).one()
        reservation = db.query(QuotaReservation).filter(QuotaReservation.id == reservation_id).one()
        db.refresh(hosted_user)
        assert run.status == "completed"
        assert hosted_user.generation_quota == 1
        assert reservation.charged_count == 1
        assert reservation.released_at is not None

    @pytest.mark.asyncio
    async def test_execute_copilot_run_refunds_failed_hosted_run(self, db, novel, hosted_user, monkeypatch):
        import app.database as db_mod
        from app.core.auth import open_quota_reservation
        from app.core.copilot.service import create_run, execute_copilot_run, open_or_reuse_session

        novel.owner_id = hosted_user.id
        db.commit()

        session, _ = open_or_reuse_session(db, novel.id, hosted_user.id, "research", "whole_book", None, "zh", "")
        reservation_id = open_quota_reservation(db, hosted_user.id, count=1)
        run = create_run(db, session, hosted_user.id, "这次会失败", quota_reservation_id=reservation_id)

        async def broken_tool_loop(*_args, **_kwargs):
            raise RuntimeError("tool loop failed")

        async def broken_one_shot(*_args, **_kwargs):
            raise RuntimeError("one-shot failed")

        monkeypatch.setattr(db_mod, "SessionLocal", TestingSessionLocal)
        monkeypatch.setattr("app.core.copilot.scope.gather_evidence", lambda *_args, **_kwargs: [])
        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_tool_loop", broken_tool_loop)
        monkeypatch.setattr("app.core.copilot.runtime_adapters.run_one_shot", broken_one_shot)

        await execute_copilot_run(
            run.run_id,
            novel.id,
            hosted_user.id,
            llm_config=_SELFHOST_BILLING_CONFIG,
        )

        db.expire_all()
        run = db.query(CopilotRun).filter(CopilotRun.run_id == run.run_id).one()
        reservation = db.query(QuotaReservation).filter(QuotaReservation.id == reservation_id).one()
        db.refresh(hosted_user)
        assert run.status == "error"
        assert hosted_user.generation_quota == 2
        assert reservation.charged_count == 0
        assert reservation.released_at is not None
