# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot session open/reuse tests."""

import pytest

from app.models import CopilotRun, CopilotSession

class TestSessionOpenReuse:
    def test_create_new_session(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={"mode": "research", "scope": "whole_book"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is True
        assert data["session_id"]

    def test_reuse_same_signature(self, client, novel):
        body = {"mode": "research", "scope": "whole_book", "interaction_locale": "zh"}
        r1 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json=body).json()
        r2 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json=body).json()
        assert r1["session_id"] == r2["session_id"]
        assert r1["created"] is True
        assert r2["created"] is False

    def test_different_scope_different_session(self, client, novel, entities):
        r1 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={"mode": "research", "scope": "whole_book"}).json()
        r2 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={"mode": "current_entity", "scope": "current_entity", "context": {"entity_id": entities[0].id}}).json()
        assert r1["session_id"] != r2["session_id"]

    def test_different_locale_different_session(self, client, novel):
        r1 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={"mode": "research", "scope": "whole_book", "interaction_locale": "zh"}).json()
        r2 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={"mode": "research", "scope": "whole_book", "interaction_locale": "en"}).json()
        assert r1["session_id"] != r2["session_id"]

    def test_locale_aliases_reuse_same_session_and_return_normalized_locale(self, client, novel):
        r1 = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={"mode": "research", "scope": "whole_book", "interaction_locale": "en-US"},
        ).json()
        r2 = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={"mode": "research", "scope": "whole_book", "interaction_locale": "en"},
        ).json()
        assert r1["session_id"] == r2["session_id"]
        assert r1["interaction_locale"] == "en"
        assert r2["interaction_locale"] == "en"

    def test_non_string_interaction_locale_returns_422(self, client, novel):
        from pydantic import ValidationError

        from app.schemas import CopilotSessionOpenRequest

        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={"mode": "research", "scope": "whole_book", "interaction_locale": 5},
        )

        assert resp.status_code == 422
        with pytest.raises(ValidationError):
            CopilotSessionOpenRequest(mode="research", scope="whole_book", interaction_locale=5)

    def test_service_boundary_normalizes_interaction_locale_aliases(self, db, novel):
        from app.core.copilot.service import open_or_reuse_session

        session, created = open_or_reuse_session(
            db,
            novel.id,
            1,
            "research",
            "whole_book",
            None,
            "en-US",
            "English workspace",
        )

        assert created is True
        assert session.interaction_locale == "en"

        reused, created = open_or_reuse_session(
            db,
            novel.id,
            1,
            "research",
            "whole_book",
            None,
            "en",
            "English workspace 2",
        )

        assert created is False
        assert reused.session_id == session.session_id
        assert reused.interaction_locale == "en"

    def test_ui_surface_context_reuses_same_session_identity(self, client, novel, entities):
        r1 = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={
                "mode": "current_entity",
                "scope": "current_entity",
                "context": {"entity_id": entities[0].id, "surface": "studio", "stage": "entity"},
            },
        ).json()
        r2 = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={
                "mode": "current_entity",
                "scope": "current_entity",
                "context": {"entity_id": entities[0].id, "surface": "atlas", "stage": "entities", "tab": "entities"},
            },
        ).json()
        assert r1["session_id"] == r2["session_id"]
        assert r2["context"]["surface"] == "atlas"
        assert r2["context"]["tab"] == "entities"
        assert r2["context"]["stage"] is None

    def test_whole_book_ui_context_does_not_split_session(self, client, novel):
        r1 = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={
                "mode": "research",
                "scope": "whole_book",
                "context": {"surface": "studio", "stage": "write"},
            },
        ).json()
        r2 = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={
                "mode": "research",
                "scope": "whole_book",
                "context": {"surface": "atlas", "stage": "systems", "tab": "systems"},
            },
        ).json()
        assert r1["session_id"] == r2["session_id"]
        assert r2["context"]["surface"] == "atlas"
        assert r2["context"]["tab"] == "systems"
        assert r2["context"]["stage"] is None

    def test_current_entity_scope_requires_entity_id(self, client, novel):
        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={
                "mode": "current_entity",
                "scope": "current_entity",
                "context": {"surface": "studio", "stage": "entity"},
            },
        )
        assert resp.status_code == 422

    def test_research_current_tab_requires_relationship_tab(self, client, novel):
        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={
                "mode": "research",
                "scope": "current_tab",
                "context": {"tab": "review"},
            },
        )
        assert resp.status_code == 422

    def test_duplicate_signature_conflict_reuses_existing_session(self, db, novel, monkeypatch):
        from app.core.copilot.runtime_lookup import load_session_by_signature as _load_session_by_signature
        from app.core.copilot.service import open_or_reuse_session

        existing, created = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "初始标题")
        assert created is True

        calls = {"count": 0}

        def fake_load(db_session, *, novel_id, user_id, signature):
            calls["count"] += 1
            if calls["count"] == 1:
                return None
            return _load_session_by_signature(
                db_session,
                novel_id=novel_id,
                user_id=user_id,
                signature=signature,
            )

        monkeypatch.setattr("app.core.copilot.runtime_lookup.load_session_by_signature", fake_load)

        reused, created = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "更新标题")
        assert created is False
        assert reused.session_id == existing.session_id
        assert reused.display_title == "更新标题"

    def test_model_declares_unique_session_signature_index(self):
        indexes = {index.name: index for index in CopilotSession.__table__.indexes}
        lookup_index = indexes["uq_copilot_sessions_lookup"]
        assert lookup_index.unique is True

    def test_model_declares_partial_unique_active_run_index_for_sqlite_and_postgres(self):
        indexes = {index.name: index for index in CopilotRun.__table__.indexes}
        active_index = indexes["uq_copilot_runs_active_session"]
        assert active_index.unique is True
        assert active_index.dialect_options["sqlite"].get("where") is not None
        assert active_index.dialect_options["postgresql"].get("where") is not None
