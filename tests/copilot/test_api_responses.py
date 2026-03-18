# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from app.models import CopilotRun, CopilotSession

pytest_plugins = ("tests.copilot.test_runtime",)


def test_run_poll_includes_non_actionable_reason(client, db, novel, entities):
    session = CopilotSession(
        session_id="sess-preview-reason",
        novel_id=novel.id,
        user_id=1,
        mode="current_entity",
        scope="current_entity",
        context_json={"entity_id": entities[0].id},
        interaction_locale="zh",
        signature="sig-preview-reason",
        display_title=entities[0].name,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    run = CopilotRun(
        run_id="run-preview-reason",
        copilot_session_id=session.id,
        novel_id=novel.id,
        user_id=1,
        status="completed",
        prompt="补全关系",
        answer="分析完成",
        evidence_json=[],
        suggestions_json=[
            {
                "suggestion_id": "sg_rel_blocked",
                "kind": "create_relationship",
                "title": "补上关系",
                "summary": "建议补上一条关键关系。",
                "evidence_ids": [],
                "target": {
                    "resource": "relationship",
                    "resource_id": None,
                    "label": "新关系",
                    "tab": "relationships",
                    "entity_id": entities[0].id,
                },
                "preview": {
                    "target_label": "新关系",
                    "summary": "建议补上一条关键关系。",
                    "field_deltas": [],
                    "evidence_quotes": [],
                    "actionable": False,
                    "non_actionable_reason": "这条关系还依赖未确认的人物或设定。请先确认相关实体，再来确认这条关系。",
                },
                "apply": None,
                "status": "pending",
            },
        ],
    )
    db.add(run)
    db.commit()

    response = client.get(
        f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}",
    )

    assert response.status_code == 200
    preview = response.json()["suggestions"][0]["preview"]
    assert preview["actionable"] is False
    assert preview["non_actionable_reason"] == "这条关系还依赖未确认的人物或设定。请先确认相关实体，再来确认这条关系。"


def test_run_list_returns_session_history_oldest_first(client, db, novel):
    session = CopilotSession(
        session_id="sess-history",
        novel_id=novel.id,
        user_id=1,
        mode="research",
        scope="whole_book",
        context_json=None,
        interaction_locale="zh",
        signature="sig-history",
        display_title="全书探索",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    run1 = CopilotRun(
        run_id="run-history-1",
        copilot_session_id=session.id,
        novel_id=novel.id,
        user_id=1,
        status="completed",
        prompt="先总结主角",
        answer="第一轮回答",
        evidence_json=[],
        suggestions_json=[],
    )
    run2 = CopilotRun(
        run_id="run-history-2",
        copilot_session_id=session.id,
        novel_id=novel.id,
        user_id=1,
        status="completed",
        prompt="再总结宗门",
        answer="第二轮回答",
        evidence_json=[],
        suggestions_json=[],
    )
    db.add_all([run1, run2])
    db.commit()

    response = client.get(
        f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs",
    )

    assert response.status_code == 200
    data = response.json()
    assert [item["run_id"] for item in data] == ["run-history-1", "run-history-2"]
    assert [item["prompt"] for item in data] == ["先总结主角", "再总结宗门"]
