# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot end-to-end workflow tests."""

class TestE2EWorkflows:
    """E2E tests that exercise the full HTTP endpoint flow.

    These verify user workflows, not code paths:
    - session open → run create → poll → answer + evidence
    - apply contract through HTTP
    - stale run detection via poll
    """

    def test_whole_book_inquiry_returns_answer_and_evidence(self, client, db, novel, entities, chapters):
        """Whole-book inquiry can return answer + evidence without suggestions.
        This is a normal success result, not an error."""
        # Open session
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "research", "scope": "whole_book",
        })
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # Create a completed run directly in DB (simulates background execution)
        from app.models import CopilotRun, CopilotSession as CS
        cs = db.query(CS).filter(CS.session_id == session_id).first()
        run = CopilotRun(
            run_id="e2e-run-wb", copilot_session_id=cs.id, novel_id=novel.id, user_id=1,
            status="completed", prompt="全书盘点",
            answer="全书存在3个未收束设定缺口",
            evidence_json=[{
                "evidence_id": "ev_0", "source_type": "chapter_excerpt",
                "source_ref": {"chapter_id": chapters[0].id, "chapter_number": 1, "start_pos": 0, "end_pos": 50},
                "title": "第1章", "excerpt": "宗门修行", "why_relevant": "高频线索",
            }],
            suggestions_json=[],  # inquiry-only — no suggestions
        )
        db.add(run)
        db.commit()

        # Poll
        resp = client.get(f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/{run.run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["answer"] == "全书存在3个未收束设定缺口"
        assert len(data["evidence"]) == 1
        assert len(data["suggestions"]) == 0  # inquiry-only is normal

    def test_current_entity_enrichment_full_flow(self, client, db, novel, entities, attributes, chapters):
        """Entity enrichment workflow: open session → create run → poll → apply suggestion."""
        # Open session scoped to entity
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "current_entity", "scope": "current_entity",
            "context": {"entity_id": entities[0].id},
            "display_title": entities[0].name,
        })
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # Simulate completed run with suggestion
        from app.models import CopilotRun, CopilotSession as CS
        cs = db.query(CS).filter(CS.session_id == session_id).first()
        run = CopilotRun(
            run_id="e2e-run-ent", copilot_session_id=cs.id, novel_id=novel.id, user_id=1,
            status="completed", prompt="补完张三",
            answer="张三是宗门弟子，建议补充描述和属性",
            evidence_json=[{
                "evidence_id": "ev_0", "source_type": "chapter_excerpt",
                "source_ref": {"chapter_id": chapters[0].id},
                "title": "第1章", "excerpt": "张三在宗门修行", "why_relevant": "直接提及",
            }],
            suggestions_json=[{
                "suggestion_id": "sg_enrich_0", "kind": "update_entity",
                "title": "补充描述", "summary": "基于章节证据补充",
                "evidence_ids": ["ev_0"],
                "target": {"resource": "entity", "resource_id": entities[0].id, "label": "张三", "tab": "entities", "entity_id": entities[0].id},
                "preview": {"target_label": "张三", "summary": "补充描述", "field_deltas": [{"field": "description", "label": "描述", "before": "主角", "after": "宗门弟子，修行天赋卓越"}], "evidence_quotes": ["张三在宗门修行"], "actionable": True},
                "apply": {"type": "update_entity", "entity_id": entities[0].id, "data": {"description": "宗门弟子，修行天赋卓越"}},
                "status": "pending",
            }],
        )
        db.add(run)
        db.commit()

        # Poll — should see suggestion
        resp = client.get(f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/{run.run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["preview"]["actionable"] is True

        # Apply — this is the approval boundary
        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/{run.run_id}/apply",
            json={"suggestion_ids": ["sg_enrich_0"]},
        )
        assert resp.status_code == 200
        assert resp.json()["results"][0]["success"] is True

        # Verify world model was actually mutated
        db.refresh(entities[0])
        assert entities[0].description == "宗门弟子，修行天赋卓越"

    def test_draft_cleanup_rejects_non_draft_through_api(self, client, db, novel, entities, chapters):
        """Draft cleanup applied through API respects the draft-only constraint."""
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "draft_cleanup", "scope": "whole_book",
        })
        session_id = resp.json()["session_id"]

        from app.models import CopilotRun, CopilotSession as CS
        cs = db.query(CS).filter(CS.session_id == session_id).first()
        # Suggestion targets a confirmed entity — should be advisory only
        run = CopilotRun(
            run_id="e2e-run-dc", copilot_session_id=cs.id, novel_id=novel.id, user_id=1,
            status="completed", prompt="整理草稿",
            answer="已审查", evidence_json=[],
            suggestions_json=[{
                "suggestion_id": "sg_dc_0", "kind": "update_entity",
                "title": "x", "summary": "x", "evidence_ids": [],
                "target": {"resource": "entity", "resource_id": entities[0].id, "label": "张三", "tab": "review"},
                "preview": {"target_label": "张三", "summary": "x", "field_deltas": [], "evidence_quotes": [], "actionable": False},
                "apply": None, "status": "pending",
            }],
        )
        db.add(run)
        db.commit()

        # Apply advisory suggestion → should fail gracefully
        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/{run.run_id}/apply",
            json={"suggestion_ids": ["sg_dc_0"]},
        )
        assert resp.status_code == 200
        assert resp.json()["results"][0]["success"] is False
        assert resp.json()["results"][0]["error_code"] == "not_actionable"

    def test_stale_run_detected_on_poll(self, client, db, novel):
        """Stale running run is marked interrupted when polled."""
        from datetime import datetime, timedelta, timezone
        from app.models import CopilotRun, CopilotSession as CS

        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "research", "scope": "whole_book",
        })
        session_id = resp.json()["session_id"]
        cs = db.query(CS).filter(CS.session_id == session_id).first()

        # Create a run with old updated_at
        run = CopilotRun(
            run_id="e2e-run-stale", copilot_session_id=cs.id, novel_id=novel.id, user_id=1,
            status="running", prompt="test",
        )
        db.add(run)
        db.commit()

        # Manually set updated_at to 10 minutes ago
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.execute(
            db.query(CopilotRun).filter(CopilotRun.run_id == "e2e-run-stale").statement,
        )
        # Use raw SQL for precise control
        from sqlalchemy import text
        db.execute(text("UPDATE copilot_runs SET updated_at = :ts WHERE run_id = :rid"), {"ts": old_time, "rid": "e2e-run-stale"})
        db.commit()
        db.expire_all()

        resp = client.get(f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/e2e-run-stale")
        assert resp.status_code == 200
        assert resp.json()["status"] == "interrupted"

    def test_stale_queued_run_detected_on_poll(self, client, db, novel):
        """Stale queued run is marked interrupted when polled."""
        from datetime import datetime, timedelta, timezone
        from app.models import CopilotRun, CopilotSession as CS

        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "research", "scope": "whole_book",
        })
        session_id = resp.json()["session_id"]
        cs = db.query(CS).filter(CS.session_id == session_id).first()

        run = CopilotRun(
            run_id="e2e-run-queued-stale",
            copilot_session_id=cs.id,
            novel_id=novel.id,
            user_id=1,
            status="queued",
            prompt="test",
            lease_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=60),
        )
        db.add(run)
        db.commit()

        resp = client.get(f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/e2e-run-queued-stale")
        assert resp.status_code == 200
        assert resp.json()["status"] == "interrupted"

    def test_parallel_sessions_coexist(self, client, db, novel, entities):
        """Multiple sessions can coexist with bounded active runs."""
        # Open two sessions with different scopes
        r1 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "research", "scope": "whole_book",
        })
        r2 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "current_entity", "scope": "current_entity",
            "context": {"entity_id": entities[0].id},
        })
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["session_id"] != r2.json()["session_id"]
