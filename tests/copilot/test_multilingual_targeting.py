# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot multilingual targeting safety tests."""

class TestMultilingualTargeting:
    def test_display_text_not_used_for_targeting(self, db, novel, entities):
        """Target resolution uses ID, not display text."""
        from app.core.copilot.scope import ScopeSnapshot
        from app.core.copilot.suggestions import compile_suggestions
        snapshot = ScopeSnapshot(
            novel=novel, novel_language="zh", entities=entities, entities_by_id={e.id: e for e in entities},
            relationships=[], systems=[], attributes_by_entity={},
            draft_entities=[], draft_relationships=[], draft_systems=[],
        )
        raw = [{"kind": "update_entity", "title": "x", "summary": "x", "target_resource": "entity", "target_id": None, "delta": {"description": "x"}}]
        compiled = compile_suggestions(raw, [], snapshot, "research", "current_entity")
        # target_id is None for update → can't resolve → advisory
        assert compiled[0].preview["actionable"] is False
