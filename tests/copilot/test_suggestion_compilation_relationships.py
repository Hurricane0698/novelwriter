# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot relationship suggestion compilation tests."""

from tests.copilot.suggestion_support import make_scope_snapshot

class TestSuggestionCompilationRelationships:
    def test_update_relationship_target_contains_graph_focus_and_highlight(self, db, novel, entities, relationships):
        from app.core.copilot.suggestions import compile_suggestions

        snapshot = make_scope_snapshot(db, entities, relationships, [])
        raw = [{
            "kind": "update_relationship",
            "title": "补关系描述",
            "summary": "补充宿敌关系",
            "target_resource": "relationship",
            "target_id": relationships[0].id,
            "delta": {"description": "更明确的宿敌关系"},
        }]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        assert len(compiled) == 1
        assert compiled[0].target["tab"] == "relationships"
        assert compiled[0].target["entity_id"] == relationships[0].source_id
        assert compiled[0].target["highlight_id"] == relationships[0].id

    def test_create_relationship_target_uses_source_entity_context(self, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions

        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [{
            "kind": "create_relationship",
            "title": "补关系",
            "summary": "建立张三和李四的联系",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": entities[0].id,
                "target_id": entities[1].id,
                "label": "同门",
            },
        }]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        assert len(compiled) == 1
        assert compiled[0].target["tab"] == "relationships"
        assert compiled[0].target["entity_id"] == entities[0].id

    def test_create_relationship_with_unresolved_entities_exposes_non_actionable_reason(self, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions

        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [{
            "kind": "create_relationship",
            "title": "补关系",
            "summary": "建立两名新人物之间的联系",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": 9991,
                "target_id": 9992,
                "label": "同盟",
            },
        }]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is False
        assert "请先确认相关实体" in (compiled[0].preview["non_actionable_reason"] or "")

    def test_create_relationship_with_same_run_entity_dependencies_compiles_actionable(self, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions

        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [
            {
                "kind": "create_entity",
                "title": "创建林七",
                "summary": "补一个新人物",
                "target_resource": "entity",
                "target_id": None,
                "delta": {"name": "林七", "entity_type": "Character"},
            },
            {
                "kind": "create_entity",
                "title": "创建赵八",
                "summary": "再补一个新人物",
                "target_resource": "entity",
                "target_id": None,
                "delta": {"name": "赵八", "entity_type": "Character"},
            },
            {
                "kind": "create_relationship",
                "title": "补关系",
                "summary": "建立两名新人物之间的联系",
                "target_resource": "relationship",
                "target_id": None,
                "delta": {
                    "source_name": "林七",
                    "target_name": "赵八",
                    "label": "同盟",
                },
            },
        ]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        assert len(compiled) == 3
        assert compiled[2].preview["actionable"] is True
        endpoint_dependencies = compiled[2].apply_action["endpoint_dependencies"]
        assert endpoint_dependencies["source"]["suggestion_id"] == compiled[0].suggestion_id
        assert endpoint_dependencies["target"]["suggestion_id"] == compiled[1].suggestion_id

    def test_create_relationship_synthesizes_missing_endpoint_entities(self, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions

        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [{
            "kind": "create_relationship",
            "title": "补关系",
            "summary": "让张三与太玄宗建立归属关系",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": entities[0].id,
                "target_name": "太玄宗",
                "target_entity_type": "Faction",
                "label": "隶属",
            },
        }]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")

        assert len(compiled) == 2
        synthetic_entity = compiled[0]
        relationship = compiled[1]
        assert synthetic_entity.kind == "create_entity"
        assert synthetic_entity.apply_action["data"]["name"] == "太玄宗"
        assert synthetic_entity.apply_action["data"]["entity_type"] == "Faction"
        assert relationship.preview["actionable"] is True
        endpoint_dependencies = relationship.apply_action["endpoint_dependencies"]
        assert endpoint_dependencies["target"]["suggestion_id"] == synthetic_entity.suggestion_id

    def test_create_relationship_resolves_existing_entity_alias_without_synthesizing_duplicate(self, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions

        entities[1].aliases = ["四哥"]
        db.commit()
        snapshot = make_scope_snapshot(db, entities, [], [])
        raw = [{
            "kind": "create_relationship",
            "title": "补关系",
            "summary": "让张三与四哥建立联系",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": entities[0].id,
                "target_name": "四哥",
                "label": "同盟",
            },
        }]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is True
        assert "endpoint_dependencies" not in compiled[0].apply_action
        assert compiled[0].apply_action["data"]["target_id"] == entities[1].id
