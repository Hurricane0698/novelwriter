# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot run admission-control tests."""

import pytest

class TestAdmissionControl:
    def test_create_run_snapshots_canonical_context_before_session_reuse(self, db, novel, entities):
        from app.core.copilot.service import create_run, open_or_reuse_session

        studio_context = {"entity_id": entities[0].id, "surface": "studio", "stage": "entity"}
        atlas_context = {"entity_id": entities[0].id, "surface": "atlas", "stage": "entities", "tab": "entities"}

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
        run = create_run(db, session, 1, "先看 studio 上下文")

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

        db.refresh(run)
        db.refresh(reused)
        assert created is False
        assert reused.session_id == session.session_id
        assert run.context_json == studio_context
        assert reused.context_json == {"entity_id": entities[0].id, "surface": "atlas", "tab": "entities"}

    def test_one_active_run_per_session(self, db, novel):
        from app.core.copilot.runtime_errors import CopilotError
        from app.core.copilot.service import create_run, open_or_reuse_session
        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        create_run(db, session, 1, "first")
        with pytest.raises(CopilotError) as exc_info:
            create_run(db, session, 1, "second")
        assert exc_info.value.code == "session_run_active"

    def test_max_active_runs_per_user(self, db, novel):
        from app.config import get_settings
        from app.core.copilot.runtime_errors import CopilotError
        from app.core.copilot.service import create_run, open_or_reuse_session
        limit = get_settings().copilot_max_runs_per_user
        for i in range(limit):
            session, _ = open_or_reuse_session(
                db,
                novel.id,
                1,
                "current_entity",
                "current_entity",
                {"entity_id": i + 100},
                "zh",
                f"s{i}",
            )
            create_run(db, session, 1, f"run {i}")
        extra, _ = open_or_reuse_session(
            db,
            novel.id,
            1,
            "current_entity",
            "current_entity",
            {"entity_id": 999},
            "zh",
            "extra",
        )
        with pytest.raises(CopilotError) as exc_info:
            create_run(db, extra, 1, "too many")
        assert exc_info.value.code == "too_many_active_runs"

    def test_stale_queued_run_reclaimed_before_new_run(self, db, novel):
        from datetime import datetime, timedelta, timezone
        from app.core.copilot.service import create_run, open_or_reuse_session

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        stale_run = create_run(db, session, 1, "first")
        stale_run.lease_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=60)
        db.commit()

        replacement = create_run(db, session, 1, "second")

        db.refresh(stale_run)
        assert stale_run.status == "interrupted"
        assert replacement.run_id != stale_run.run_id
        assert replacement.status == "queued"

    def test_db_constraint_translates_duplicate_active_run_conflict(self, db, novel, monkeypatch):
        from app.core.copilot.runtime_errors import CopilotError
        from app.core.copilot.service import create_run, open_or_reuse_session

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        create_run(db, session, 1, "first")

        monkeypatch.setattr("app.core.copilot.runtime_lookup.count_active_runs_in_session", lambda *_args, **_kwargs: 0)

        with pytest.raises(CopilotError) as exc_info:
            create_run(db, session, 1, "second")
        assert exc_info.value.code == "session_run_active"
