# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot run polling tests."""

from app.models import CopilotRun, CopilotSession

class TestRunPoll:
    def test_poll_returns_backend_evidence(self, client, db, novel):
        session = CopilotSession(session_id="sess-poll", novel_id=novel.id, user_id=1, mode="research", scope="whole_book", interaction_locale="zh", signature="sig-p", display_title="")
        db.add(session)
        db.commit()
        db.refresh(session)
        run = CopilotRun(
            run_id="run-poll", copilot_session_id=session.id, novel_id=novel.id, user_id=1,
            status="completed", prompt="test", answer="分析完成",
            evidence_json=[{
                "evidence_id": "ev_0", "source_type": "chapter_excerpt",
                "source_ref": {"chapter_id": 1, "chapter_number": 1, "start_pos": 0, "end_pos": 100},
                "title": "第1章", "excerpt": "关键文本", "why_relevant": "相关",
                "pack_id": "pk_ch_1",
                "source_refs": [{"type": "chapter", "chapter_id": 1, "chapter_number": 1, "start_pos": 0, "end_pos": 100}],
                "anchor_terms": ["帝国", "军团"],
                "support_count": 2,
                "preview_excerpt": "关键文本",
                "expanded": True,
            }],
            suggestions_json=[],
        )
        db.add(run)
        db.commit()
        resp = client.get(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["answer"] == "分析完成"
        assert len(data["evidence"]) == 1
        assert data["evidence"][0]["source_ref"]["chapter_id"] == 1
        assert data["evidence"][0]["pack_id"] == "pk_ch_1"
        assert data["evidence"][0]["anchor_terms"] == ["帝国", "军团"]
        assert data["evidence"][0]["expanded"] is True

    def test_poll_nonexistent_returns_404(self, client, db, novel):
        session = CopilotSession(session_id="sess-p404", novel_id=novel.id, user_id=1, mode="research", scope="whole_book", interaction_locale="zh", signature="sig-p404", display_title="")
        db.add(session)
        db.commit()
        resp = client.get(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/nonexistent")
        assert resp.status_code == 404
