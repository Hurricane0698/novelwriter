# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot dependency auto-apply contract tests."""

from app.models import CopilotRun, CopilotSession, WorldEntity, WorldRelationship
from tests.copilot.suggestion_support import make_scope_snapshot


class TestApplyDependencyContract:
    def test_apply_endpoint_returns_auto_applied_dependency_results(self, client, db, novel, entities):
        from app.core.copilot.suggestions import compile_suggestions
        from app.core.copilot.suggestions import serialize_compiled_suggestions

        session = CopilotSession(
            session_id="test-sess-chain-api",
            novel_id=novel.id,
            user_id=1,
            mode="research",
            scope="whole_book",
            interaction_locale="zh",
            signature="sig-chain-api",
            display_title="关系补全",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

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
        run = CopilotRun(
            run_id="test-run-chain-api",
            copilot_session_id=session.id,
            novel_id=novel.id,
            user_id=1,
            status="completed",
            prompt="补关系",
            answer="完成",
            evidence_json=[],
            suggestions_json=serialize_compiled_suggestions(compiled),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        relationship_suggestion = next(item for item in compiled if item.kind == "create_relationship")
        response = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply",
            json={"suggestion_ids": [relationship_suggestion.suggestion_id]},
        )

        assert response.status_code == 200
        result_ids = [item["suggestion_id"] for item in response.json()["results"]]
        assert result_ids == [item.suggestion_id for item in compiled]
        assert all(item["success"] is True for item in response.json()["results"])

    def test_apply_relationship_auto_applies_same_run_entity_dependencies(self, db, novel, entities):
        from app.core.copilot.apply import apply_suggestions
        from app.core.copilot.suggestions import compile_suggestions
        from app.core.copilot.suggestions import serialize_compiled_suggestions

        session = CopilotSession(
            session_id="test-sess-chain",
            novel_id=novel.id,
            user_id=1,
            mode="research",
            scope="whole_book",
            interaction_locale="zh",
            signature="sig-chain",
            display_title="关系补全",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

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
        run = CopilotRun(
            run_id="test-run-chain",
            copilot_session_id=session.id,
            novel_id=novel.id,
            user_id=1,
            status="completed",
            prompt="补关系",
            answer="完成",
            evidence_json=[],
            suggestions_json=serialize_compiled_suggestions(compiled),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        relationship_suggestion = next(item for item in compiled if item.kind == "create_relationship")
        results = apply_suggestions(db, run, [relationship_suggestion.suggestion_id])

        assert all(result.success for result in results)
        assert [result.suggestion_id for result in results] == [item.suggestion_id for item in compiled]
        names = {entity.name for entity in db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).all()}
        assert "林七" in names
        assert "赵八" in names

        relationship = db.query(WorldRelationship).filter(
            WorldRelationship.novel_id == novel.id,
            WorldRelationship.label == "同盟",
        ).first()
        assert relationship is not None
        assert relationship.status == "confirmed"

        db.refresh(run)
        statuses = {item["suggestion_id"]: item["status"] for item in (run.suggestions_json or [])}
        assert statuses[relationship_suggestion.suggestion_id] == "applied"
        assert sum(1 for status in statuses.values() if status == "applied") == 3

    def test_apply_relationship_with_synthesized_entity_dependency(self, db, novel, entities):
        from app.core.copilot.apply import apply_suggestions
        from app.core.copilot.suggestions import compile_suggestions
        from app.core.copilot.suggestions import serialize_compiled_suggestions

        session = CopilotSession(
            session_id="test-sess-synth-chain",
            novel_id=novel.id,
            user_id=1,
            mode="research",
            scope="current_entity",
            interaction_locale="zh",
            signature="sig-synth-chain",
            display_title="关系补全",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

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
        relationship_suggestion = next(item for item in compiled if item.kind == "create_relationship")
        run = CopilotRun(
            run_id="test-run-synth-chain",
            copilot_session_id=session.id,
            novel_id=novel.id,
            user_id=1,
            status="completed",
            prompt="补关系",
            answer="完成",
            evidence_json=[],
            suggestions_json=serialize_compiled_suggestions(compiled),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        results = apply_suggestions(db, run, [relationship_suggestion.suggestion_id])

        assert all(result.success for result in results)
        created_entity = db.query(WorldEntity).filter(
            WorldEntity.novel_id == novel.id,
            WorldEntity.name == "太玄宗",
        ).first()
        assert created_entity is not None
        assert created_entity.entity_type == "Faction"
        relationship = db.query(WorldRelationship).filter(
            WorldRelationship.novel_id == novel.id,
            WorldRelationship.label == "隶属",
        ).first()
        assert relationship is not None
        assert relationship.target_id == created_entity.id

    def test_apply_relationship_auto_applies_synthesized_endpoint_entity(self, db, novel, entities):
        from app.core.copilot.apply import apply_suggestions
        from app.core.copilot.suggestions import compile_suggestions
        from app.core.copilot.suggestions import serialize_compiled_suggestions

        session = CopilotSession(
            session_id="test-sess-synth",
            novel_id=novel.id,
            user_id=1,
            mode="research",
            scope="current_entity",
            interaction_locale="zh",
            signature="sig-synth",
            display_title="实体补全",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

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
        run = CopilotRun(
            run_id="test-run-synth",
            copilot_session_id=session.id,
            novel_id=novel.id,
            user_id=1,
            status="completed",
            prompt="补关系",
            answer="完成",
            evidence_json=[],
            suggestions_json=serialize_compiled_suggestions(compiled),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        relationship_suggestion = next(item for item in compiled if item.kind == "create_relationship")
        results = apply_suggestions(db, run, [relationship_suggestion.suggestion_id])

        assert all(result.success for result in results)
        created = db.query(WorldEntity).filter(
            WorldEntity.novel_id == novel.id,
            WorldEntity.name == "太玄宗",
        ).first()
        assert created is not None
        assert created.entity_type == "Faction"
        relationship = db.query(WorldRelationship).filter(
            WorldRelationship.novel_id == novel.id,
            WorldRelationship.label == "隶属",
        ).first()
        assert relationship is not None
        assert relationship.target_id == created.id
