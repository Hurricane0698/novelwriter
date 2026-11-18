# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

def test_smalltalk_prompt_build_stays_on_light_sections(db, novel, entities):
    from app.core.copilot.prompting import build_copilot_system_prompt_build
    from app.core.copilot.scope import load_scope_snapshot

    snapshot = load_scope_snapshot(
        db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id}
    )
    build = build_copilot_system_prompt_build(
        snapshot,
        [],
        "current_entity",
        "zh",
        {
            "context_json": {
                "surface": "studio",
                "stage": "entity",
                "entity_id": entities[0].id,
            },
            "display_title": entities[0].name,
        },
        "smalltalk",
    )

    assert build.prompt_id == "workbench_assistant"
    assert "world_model" not in build.section_ids
    assert build.to_debug_dict()["preload_world_context"] is False
