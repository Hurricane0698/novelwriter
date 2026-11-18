# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot basic apply-contract tests."""

from app.models import CopilotRun, CopilotSession, WorldEntity
from tests.copilot.apply_support import create_completed_apply_run


class TestApplyBasicContract:
    def test_apply_update_modifies_entity(self, client, db, novel, entities):
        session, run = create_completed_apply_run(db, novel, entities)
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply", json={"suggestion_ids": ["sg_update"]})
        assert resp.status_code == 200
        assert resp.json()["results"][0]["success"] is True
        db.refresh(entities[0])
        assert entities[0].description == "宗门弟子"

    def test_apply_create_produces_confirmed_manual_row(self, client, db, novel, entities):
        """Apply IS the approval boundary — created rows are confirmed, not draft."""
        session, run = create_completed_apply_run(db, novel, entities)
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply", json={"suggestion_ids": ["sg_create"]})
        assert resp.status_code == 200
        assert resp.json()["results"][0]["success"] is True
        new_entity = db.query(WorldEntity).filter(WorldEntity.name == "太玄禁律").first()
        assert new_entity is not None
        assert new_entity.origin == "manual"
        assert new_entity.status == "confirmed"

    def test_apply_create_rolls_back_when_deferred_attribute_write_fails(self, client, db, novel, entities):
        session = CopilotSession(
            session_id="test-sess-apply-rollback",
            novel_id=novel.id,
            user_id=1,
            mode="current_entity",
            scope="current_entity",
            context_json={"entity_id": entities[0].id},
            interaction_locale="zh",
            signature="sig-apply-rollback",
            display_title="张三",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        run = CopilotRun(
            run_id="test-run-apply-rollback",
            copilot_session_id=session.id,
            novel_id=novel.id,
            user_id=1,
            status="completed",
            prompt="补完",
            answer="完成",
            evidence_json=[],
            suggestions_json=[
                {
                    "suggestion_id": "sg_create_attr_conflict",
                    "kind": "create_entity",
                    "title": "新建失败回滚",
                    "summary": "x",
                    "evidence_ids": [],
                    "target": {"resource": "entity", "resource_id": None, "label": "玄天戒律", "tab": "entities"},
                    "preview": {"target_label": "玄天戒律", "summary": "x", "field_deltas": [], "evidence_quotes": [], "actionable": True},
                    "apply": {
                        "type": "create_entity",
                        "data": {"name": "玄天戒律", "entity_type": "Concept", "description": "会触发属性冲突"},
                        "deferred_attribute_actions": [
                            {"type": "create_attribute", "data": {"key": "约束", "surface": "不可违逆"}},
                            {"type": "create_attribute", "data": {"key": "约束", "surface": "重复键导致失败"}},
                        ],
                    },
                    "status": "pending",
                },
            ],
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply",
            json={"suggestion_ids": ["sg_create_attr_conflict"]},
        )

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["success"] is False

        assert db.query(WorldEntity).filter(
            WorldEntity.novel_id == novel.id,
            WorldEntity.name == "玄天戒律",
        ).first() is None

        db.refresh(run)
        assert run.suggestions_json[0]["status"] == "pending"

    def test_advisory_suggestion_not_applicable(self, client, db, novel, entities):
        session, run = create_completed_apply_run(db, novel, entities)
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply", json={"suggestion_ids": ["sg_advisory"]})
        assert resp.json()["results"][0]["success"] is False
        assert resp.json()["results"][0]["error_code"] == "not_actionable"

    def test_apply_endpoint_localizes_not_actionable_error_to_english(self, client, db, novel, entities):
        session, run = create_completed_apply_run(db, novel, entities, interaction_locale="en")
        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply",
            json={"suggestion_ids": ["sg_advisory"]},
        )

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["success"] is False
        assert result["error_code"] == "not_actionable"
        assert "cannot be applied directly" in result["error_message"]

    def test_stale_target_doesnt_block_others(self, client, db, novel, entities):
        session, run = create_completed_apply_run(db, novel, entities)
        db.delete(entities[0])
        db.commit()
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply", json={"suggestion_ids": ["sg_update"]})
        results = resp.json()["results"]
        assert results[0]["success"] is False
        assert results[0]["error_code"] == "copilot_target_stale"

    def test_apply_endpoint_localizes_stale_error_to_english(self, client, db, novel, entities):
        session, run = create_completed_apply_run(db, novel, entities, interaction_locale="en")
        db.delete(entities[0])
        db.commit()

        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply",
            json={"suggestion_ids": ["sg_update"]},
        )

        result = resp.json()["results"][0]
        assert result["success"] is False
        assert result["error_code"] == "copilot_target_stale"
        assert result["error_message"] == "The underlying content just changed. Refresh and try again."

    def test_apply_on_running_run_rejected(self, client, db, novel, entities):
        session = CopilotSession(session_id="sess-running", novel_id=novel.id, user_id=1, mode="research", scope="whole_book", interaction_locale="zh", signature="sig-r", display_title="")
        db.add(session)
        db.commit()
        db.refresh(session)
        run = CopilotRun(run_id="run-running", copilot_session_id=session.id, novel_id=novel.id, user_id=1, status="running", prompt="x")
        db.add(run)
        db.commit()
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply", json={"suggestion_ids": ["x"]})
        assert resp.status_code == 409
