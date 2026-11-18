# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot dismiss tests."""

from app.models import CopilotRun, CopilotSession

class TestDismiss:
    def test_dismiss_doesnt_mutate_world_model(self, client, db, novel, entities):
        session = CopilotSession(session_id="sess-dismiss", novel_id=novel.id, user_id=1, mode="research", scope="whole_book", interaction_locale="zh", signature="sig-d", display_title="")
        db.add(session)
        db.commit()
        db.refresh(session)
        run = CopilotRun(
            run_id="run-dismiss", copilot_session_id=session.id, novel_id=novel.id, user_id=1, status="completed", prompt="x",
            suggestions_json=[{
                "suggestion_id": "sg_d", "kind": "update_entity", "title": "x", "summary": "x", "evidence_ids": [],
                "target": {"resource": "entity", "resource_id": entities[0].id, "label": "张三", "tab": "entities"},
                "preview": {"target_label": "张三", "summary": "x", "field_deltas": [], "evidence_quotes": [], "actionable": True},
                "apply": {"type": "update_entity", "entity_id": entities[0].id, "data": {"description": "不应写入"}},
                "status": "pending",
            }],
        )
        db.add(run)
        db.commit()
        original_desc = entities[0].description
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/dismiss", json={"suggestion_ids": ["sg_d"]})
        assert resp.status_code == 200
        db.refresh(entities[0])
        assert entities[0].description == original_desc
        db.refresh(run)
        assert run.suggestions_json[0]["status"] == "dismissed"
