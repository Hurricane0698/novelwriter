# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot draft-cleanup suggestion compilation tests."""

from tests.copilot.suggestion_support import make_scope_snapshot

class TestSuggestionCompilationDraftCleanup:
    def test_draft_cleanup_rejects_confirmed_target(self, db, novel, entities):
        """draft_cleanup must only target draft rows."""
        from app.core.copilot.suggestions import compile_suggestions
        snapshot = make_scope_snapshot(db, entities, [], [])
        # entities[0] is confirmed, not draft
        raw = [{"kind": "update_entity", "title": "x", "summary": "x", "target_resource": "entity", "target_id": entities[0].id, "delta": {"description": "x"}}]
        compiled = compile_suggestions(raw, [], snapshot, "draft_cleanup", "draft_cleanup")
        assert compiled[0].preview["actionable"] is False

    def test_draft_cleanup_allows_draft_target(self, db, novel, entities):
        """draft_cleanup allows targeting actual draft rows."""
        from app.core.copilot.suggestions import compile_suggestions
        snapshot = make_scope_snapshot(db, entities, [], [])
        # entities[2] is draft
        raw = [{"kind": "update_entity", "title": "补完草稿", "summary": "x", "target_resource": "entity", "target_id": entities[2].id, "delta": {"description": "补充描述"}}]
        compiled = compile_suggestions(raw, [], snapshot, "draft_cleanup", "draft_cleanup")
        assert compiled[0].preview["actionable"] is True
        assert compiled[0].target["tab"] == "review"
        assert compiled[0].target["review_kind"] == "entities"

    def test_draft_cleanup_rejects_create(self, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions
        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [{"kind": "create_entity", "target_resource": "entity", "title": "新建", "summary": "x", "delta": {"name": "新实体", "entity_type": "Other"}}]
        compiled = compile_suggestions(raw, [], snapshot, "draft_cleanup", "draft_cleanup")
        assert compiled[0].preview["actionable"] is False
