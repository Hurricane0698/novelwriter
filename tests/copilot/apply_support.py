# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Shared support for copilot apply-contract tests."""

from app.models import CopilotRun, CopilotSession


def create_completed_apply_run(db, novel, entities, interaction_locale: str = "zh"):
    session = CopilotSession(
        session_id="test-sess-apply",
        novel_id=novel.id,
        user_id=1,
        mode="current_entity",
        scope="current_entity",
        context_json={"entity_id": entities[0].id},
        interaction_locale=interaction_locale,
        signature=f"sig-apply-{interaction_locale}",
        display_title=entities[0].name,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    run = CopilotRun(
        run_id="test-run-apply",
        copilot_session_id=session.id,
        novel_id=novel.id,
        user_id=1,
        status="completed",
        prompt="补完",
        answer="完成",
        evidence_json=[],
        suggestions_json=[
            {
                "suggestion_id": "sg_update",
                "kind": "update_entity",
                "title": "补描述",
                "summary": "x",
                "evidence_ids": [],
                "target": {"resource": "entity", "resource_id": entities[0].id, "label": "张三", "tab": "entities", "entity_id": entities[0].id},
                "preview": {"target_label": "张三", "summary": "x", "field_deltas": [], "evidence_quotes": [], "actionable": True},
                "apply": {"type": "update_entity", "entity_id": entities[0].id, "data": {"description": "宗门弟子"}},
                "status": "pending",
            },
            {
                "suggestion_id": "sg_create",
                "kind": "create_entity",
                "title": "新建",
                "summary": "x",
                "evidence_ids": [],
                "target": {"resource": "entity", "resource_id": None, "label": "太玄禁律", "tab": "entities"},
                "preview": {"target_label": "太玄禁律", "summary": "x", "field_deltas": [], "evidence_quotes": [], "actionable": True},
                "apply": {"type": "create_entity", "data": {"name": "太玄禁律", "entity_type": "Concept", "description": "禁忌规约"}},
                "status": "pending",
            },
            {
                "suggestion_id": "sg_advisory",
                "kind": "update_entity",
                "title": "仅参考",
                "summary": "x",
                "evidence_ids": [],
                "target": {"resource": "entity", "resource_id": entities[0].id, "label": "张三", "tab": "entities"},
                "preview": {"target_label": "张三", "summary": "x", "field_deltas": [], "evidence_quotes": [], "actionable": False},
                "apply": None,
                "status": "pending",
            },
        ],
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return session, run
