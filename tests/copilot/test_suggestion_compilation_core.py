# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot suggestion compilation core tests."""

from tests.copilot.suggestion_support import make_scope_snapshot

class TestSuggestionCompilationCore:
    def test_valid_update_compiles_to_actionable(self, db, novel, entities):
        from app.core.copilot.scope import EvidenceItem
        from app.core.copilot.suggestions import compile_suggestions
        snapshot = make_scope_snapshot(db, entities, [], [])
        evidence = [EvidenceItem(evidence_id="ev_0", source_type="chapter_excerpt", source_ref={"chapter_id": 1}, title="第1章", excerpt="张三是宗门弟子", why_relevant="支撑")]
        raw = [{"kind": "update_entity", "title": "补完", "summary": "补充", "cited_evidence_indices": [0], "target_resource": "entity", "target_id": entities[0].id, "delta": {"description": "宗门弟子"}}]
        compiled = compile_suggestions(raw, evidence, snapshot, "research", "current_entity")
        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is True
        assert compiled[0].apply_action["type"] == "update_entity"

    def test_invalid_target_compiles_to_advisory(self, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions
        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [{"kind": "update_entity", "title": "x", "summary": "x", "target_resource": "entity", "target_id": 99999, "delta": {"description": "x"}}]
        compiled = compile_suggestions(raw, [], snapshot, "research", "current_entity")
        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is False

    def test_create_entity_not_blocked_without_collision(self, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions
        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [{"kind": "create_entity", "target_resource": "entity", "title": "新", "summary": "新", "delta": {"name": "太玄禁律", "entity_type": "Concept"}}]
        compiled = compile_suggestions(raw, [], snapshot, "research", "whole_book")
        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is True

    def test_create_blocked_by_name_collision(self, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions
        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [{"kind": "create_entity", "target_resource": "entity", "title": "重名", "summary": "x", "delta": {"name": "张三", "entity_type": "Character"}}]
        compiled = compile_suggestions(raw, [], snapshot, "research", "whole_book")
        assert compiled[0].preview["actionable"] is False

    def test_attribute_suggestion_compiled_to_action(self, db, novel, entities, attributes):
        """Entity enrichment with attributes — the #1 workflow."""
        from app.core.copilot.suggestions import compile_suggestions
        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [{
            "kind": "update_entity", "title": "补属性", "summary": "补充", "target_resource": "entity",
            "target_id": entities[0].id,
            "delta": {"attributes": [{"key": "门派", "surface": "太玄宗"}, {"key": "境界", "surface": "元婴期"}]},
        }]
        compiled = compile_suggestions(raw, [], snapshot, "research", "current_entity")
        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is True
        action = compiled[0].apply_action
        assert "attribute_actions" in action
        attr_actions = action["attribute_actions"]
        # "门派" is new -> create_attribute; "境界" exists -> update_attribute
        types = [a["type"] for a in attr_actions]
        assert "create_attribute" in types
        assert "update_attribute" in types

    def test_compile_suggestions_localizes_preview_to_english(self, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions

        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [{
            "kind": "update_entity",
            "title": "Fill entity",
            "summary": "Add clearer details",
            "target_resource": "entity",
            "target_id": entities[0].id,
            "delta": {
                "description": "A clearer English description",
                "attributes": [{"key": "Faction", "surface": "Tai Xuan Sect"}],
            },
        }]

        compiled = compile_suggestions(
            raw,
            [],
            snapshot,
            "research",
            "current_entity",
            interaction_locale="en",
        )

        labels = {item["label"] for item in compiled[0].preview["field_deltas"]}
        assert "Description" in labels
        assert "Attribute · Faction" in labels

    def test_create_relationship_non_actionable_reason_localizes_to_english(self, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions

        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [{
            "kind": "create_relationship",
            "title": "Add bond",
            "summary": "Link two unresolved targets",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": 9991,
                "target_id": 9992,
                "label": "Ally",
            },
        }]

        compiled = compile_suggestions(
            raw,
            [],
            snapshot,
            "research",
            "relationships",
            interaction_locale="en",
        )

        assert compiled[0].preview["actionable"] is False
        assert "Confirm those first" in (compiled[0].preview["non_actionable_reason"] or "")

    def test_compile_suggestions_localizes_fallback_title_and_new_resource_label_to_english(self, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions

        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [{
            "kind": "create_entity",
            "summary": "Need a better-formed entity card",
            "target_resource": "entity",
            "delta": {},
        }]

        compiled = compile_suggestions(
            raw,
            [],
            snapshot,
            "research",
            "whole_book",
            interaction_locale="en",
        )

        assert compiled[0].title == "Suggestion 1"
        assert compiled[0].preview["target_label"] == "New entity"
        assert "incomplete" in (compiled[0].preview["non_actionable_reason"] or "")
