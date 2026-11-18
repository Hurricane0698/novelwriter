# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot suggestion compilation scope-guard tests."""

from app.models import WorldEntity

class TestSuggestionCompilationScopeGuards:
    def test_create_entity_is_blocked_by_existing_novel_entity_outside_current_scope(self, db, novel, entities, relationships):
        from app.core.copilot.suggestions import compile_suggestions
        from app.core.copilot.scope import load_scope_snapshot

        outsider = WorldEntity(
            novel_id=novel.id,
            name="蒋艺昕",
            entity_type="Character",
            description="远端角色",
            aliases=["艺昕"],
            status="confirmed",
            origin="bootstrap",
        )
        db.add(outsider)
        db.commit()
        db.refresh(outsider)

        snapshot = load_scope_snapshot(
            db,
            novel,
            "current_entity",
            "current_entity",
            {"entity_id": entities[0].id},
        )

        assert outsider.id not in snapshot.entities_by_id

        raw = [{
            "kind": "create_entity",
            "title": "重复创建人物",
            "summary": "不该再创建已存在实体",
            "target_resource": "entity",
            "target_id": None,
            "delta": {"name": "蒋艺昕", "entity_type": "Character"},
        }]

        compiled = compile_suggestions(raw, [], snapshot, "current_entity", "current_entity")

        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is False
        assert compiled[0].apply_action is None

    def test_create_relationship_resolves_existing_alias_outside_current_scope_without_duplicate(self, db, novel, entities, relationships):
        from app.core.copilot.suggestions import compile_suggestions
        from app.core.copilot.scope import load_scope_snapshot

        outsider = WorldEntity(
            novel_id=novel.id,
            name="罗杰",
            entity_type="Character",
            description="远端角色",
            aliases=["杰哥"],
            status="confirmed",
            origin="bootstrap",
        )
        db.add(outsider)
        db.commit()
        db.refresh(outsider)

        snapshot = load_scope_snapshot(
            db,
            novel,
            "current_entity",
            "current_entity",
            {"entity_id": entities[0].id},
        )

        assert outsider.id not in snapshot.entities_by_id

        raw = [{
            "kind": "create_relationship",
            "title": "补关系",
            "summary": "让张三与杰哥建立联系",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": entities[0].id,
                "target_name": "杰哥",
                "label": "旧识",
            },
        }]

        compiled = compile_suggestions(raw, [], snapshot, "current_entity", "current_entity")

        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is True
        assert "endpoint_dependencies" not in compiled[0].apply_action
        assert compiled[0].apply_action["data"]["target_id"] == outsider.id
