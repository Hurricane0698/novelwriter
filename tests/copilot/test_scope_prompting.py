# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Copilot scope snapshot and prompting tests."""

import pytest

from app.models import WorldEntity, WorldRelationship, WorldSystem

class TestScopeAndPrompt:
    @pytest.mark.parametrize("locale", ["zh", "en"])
    def test_entity_fallback_prompt_includes_attributes(self, db, novel, entities, attributes, locale):
        from app.core.copilot.prompting import build_copilot_system_prompt
        from app.core.copilot.scope import load_scope_snapshot

        context = {"entity_id": entities[0].id}
        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", context)
        prompt = build_copilot_system_prompt(
            snapshot, [], "current_entity", locale,
            {"context_json": context, "display_title": entities[0].name}, "task_query",
        )

        assert f"{attributes[0].key}: {attributes[0].surface}" in prompt

    def test_whole_book_loads_all(self, db, novel, entities, relationships, systems, chapters):
        from app.core.copilot.scope import load_scope_snapshot
        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        assert len(snapshot.entities) >= 3
        assert len(snapshot.relationships) >= 1
        assert len(snapshot.systems) >= 1

    def test_current_entity_scopes_to_neighbors(self, db, novel, entities, relationships, chapters):
        from app.core.copilot.scope import load_scope_snapshot
        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        ids = {e.id for e in snapshot.entities}
        assert entities[0].id in ids
        assert entities[1].id in ids  # relationship partner

    def test_relationship_current_tab_uses_focused_research_profile(self, db, novel, entities, relationships, systems):
        from app.core.copilot.scope import load_scope_snapshot

        extra = WorldEntity(
            novel_id=novel.id,
            name="赵六",
            entity_type="Character",
            description="路人",
            aliases=[],
            status="confirmed",
            origin="manual",
        )
        db.add(extra)
        db.commit()
        db.refresh(extra)

        noise_rel = WorldRelationship(
            novel_id=novel.id,
            source_id=entities[1].id,
            target_id=extra.id,
            label="同伙",
            label_canonical="同伙",
            description="和张三无关",
            status="confirmed",
            origin="manual",
        )
        db.add(noise_rel)
        db.commit()

        snapshot = load_scope_snapshot(
            db,
            novel,
            "research",
            "current_tab",
            {"entity_id": entities[0].id, "tab": "relationships"},
        )

        ids = {entity.id for entity in snapshot.entities}
        assert snapshot.profile == "focused_research"
        assert snapshot.focus_variant == "relationship"
        assert entities[0].id in ids
        assert entities[1].id in ids
        assert entities[2].id not in ids
        assert extra.id not in ids
        assert snapshot.systems == []
        assert {relationship.id for relationship in snapshot.relationships} == {relationships[0].id}

    def test_draft_cleanup_exposes_drafts(self, db, novel, entities, chapters):
        from app.core.copilot.scope import load_scope_snapshot
        snapshot = load_scope_snapshot(db, novel, "draft_cleanup", "whole_book", None)
        assert len(snapshot.draft_entities) > 0

    def test_draft_cleanup_current_tab_isolates_to_draft_workset(self, db, novel, entities, relationships, systems):
        from app.core.copilot.scope import load_scope_snapshot

        draft_relationship = WorldRelationship(
            novel_id=novel.id,
            source_id=entities[2].id,
            target_id=entities[0].id,
            label="待确认同门",
            label_canonical="待确认同门",
            description="仅草稿工作需要",
            status="draft",
            origin="bootstrap",
        )
        draft_system = WorldSystem(
            novel_id=novel.id,
            name="未定法则",
            display_type="list",
            description="待补完",
            constraints=[],
            status="draft",
            origin="bootstrap",
        )
        db.add_all([draft_relationship, draft_system])
        db.commit()
        db.refresh(draft_relationship)
        db.refresh(draft_system)

        snapshot = load_scope_snapshot(
            db,
            novel,
            "draft_cleanup",
            "current_tab",
            {"tab": "review"},
        )

        ids = {entity.id for entity in snapshot.entities}
        assert snapshot.profile == "draft_governance"
        assert snapshot.focus_variant == "draft"
        assert entities[2].id in ids
        assert entities[0].id in ids  # supporting endpoint for the draft relationship
        assert entities[1].id not in ids
        assert {relationship.id for relationship in snapshot.relationships} == {draft_relationship.id}
        assert {system.id for system in snapshot.systems} == {draft_system.id}
        assert relationships[0].id not in {relationship.id for relationship in snapshot.relationships}
        assert systems[0].id not in {system.id for system in snapshot.systems}

    def test_prompt_contains_evidence_refs(self, db, novel, entities, chapters):
        from app.core.copilot.prompting import build_copilot_system_prompt
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        prompt = build_copilot_system_prompt(
            snapshot, evidence, "whole_book", "zh",
            {"context_json": {"surface": "atlas", "tab": "systems"}, "display_title": "全书探索"},
            "task_query",
        )
        assert "[Evidence#" in prompt
        assert "cited_evidence_indices" in prompt

    def test_whole_book_prompt_stays_thin(self, db, novel, entities, relationships, systems, chapters):
        from app.core.copilot.prompting import build_copilot_system_prompt
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        prompt = build_copilot_system_prompt(
            snapshot,
            evidence,
            "whole_book",
            "zh",
            {"context_json": {"surface": "atlas", "tab": "systems"}, "display_title": "全书探索"},
            "task_query",
        )

        assert "已加载全书概览" in prompt
        assert f"[Entity#{entities[0].id}]" not in prompt
        assert f"[Rel#{relationships[0].id}]" not in prompt
        assert "按需检索或展开证据" in prompt

    def test_entity_prompt_explicitly_mentions_non_character_entity_types(self, db, novel, entities):
        from app.core.copilot.prompting import build_tool_loop_system_prompt as _build_tool_loop_system_prompt
        from app.core.copilot.runtime_scenario import derive_scenario
        from app.core.copilot.scope import load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        prompt = _build_tool_loop_system_prompt(
            snapshot,
            derive_scenario("current_entity", "current_entity", {"entity_id": entities[0].id}),
            "zh",
            {"context_json": {"entity_id": entities[0].id}, "display_title": entities[0].name},
            "task_query",
        )

        assert "不只包括人物" in prompt
        assert "势力、地点、组织、物件、概念" in prompt

    def test_multilingual_prompt_preserves_canonical(self, db, novel, entities, chapters):
        from app.core.copilot.prompting import build_copilot_system_prompt
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        prompt = build_copilot_system_prompt(
            snapshot, evidence, "whole_book", "en",
            {"context_json": {"surface": "atlas", "tab": "systems"}, "display_title": "全书探索"},
            "task_query",
        )
        assert "canonical" in prompt.lower() or "原语言" in prompt
        assert "张三" in prompt  # Chinese entity name preserved

    def test_english_prompt_localizes_instruction_scaffold(self, db, novel, entities, chapters):
        from app.core.copilot.prompting import build_copilot_system_prompt
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None, interaction_locale="en")
        prompt = build_copilot_system_prompt(
            snapshot,
            evidence,
            "whole_book",
            "en",
            {"context_json": {"surface": "atlas", "tab": "systems"}, "display_title": "World sweep"},
            "task_query",
        )

        assert "You are a novel world-model research assistant" in prompt
        assert "## Current task" in prompt
        assert "## Current workbench context" in prompt
        assert "Canonical names and labels must remain" in prompt
        assert "张三" in prompt

    def test_prompt_explicitly_allows_non_character_entities(self, db, novel, entities, chapters):
        from app.core.copilot.prompting import build_copilot_system_prompt
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        prompt = build_copilot_system_prompt(
            snapshot, evidence, "whole_book", "zh",
            {"context_json": {"surface": "atlas", "tab": "systems"}, "display_title": "全书探索"},
            "task_query",
        )

        assert "实体不只包括人物" in prompt
        assert "势力、组织、地点、物件、概念、规则" in prompt

    def test_intent_classifier_distinguishes_smalltalk_capability_and_task(self):
        from app.core.copilot.prompting import classify_turn_intent

        assert classify_turn_intent("你好") == "smalltalk"
        assert classify_turn_intent("你现在能做什么？") == "capability_query"
        assert classify_turn_intent("梳理一下张三和李四的关系") == "task_query"

    def test_smalltalk_prompt_uses_light_workbench_context(self, db, novel, entities, chapters):
        from app.core.copilot.prompting import build_copilot_system_prompt
        from app.core.copilot.scope import load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        prompt = build_copilot_system_prompt(
            snapshot,
            [],
            "current_entity",
            "zh",
            {"context_json": {"surface": "studio", "stage": "entity", "entity_id": entities[0].id}, "display_title": "张三"},
            "smalltalk",
        )
        assert "当前界面：Studio / 实体检查" in prompt
        assert "不要主动生成 suggestions" in prompt
        assert "## 世界模型" not in prompt

    def test_draft_governance_evidence_stays_local_to_drafts(self, db, novel, entities, chapters):
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "draft_cleanup", "current_tab", {"tab": "review"})
        evidence = gather_evidence(db, novel, snapshot, {"tab": "review"})

        assert any(item.evidence_id.startswith("draft_ent_") for item in evidence)
        assert all(item.source_type != "chapter_excerpt" for item in evidence)

    def test_gather_evidence_localizes_to_english(self, db, novel, entities, chapters):
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        evidence = gather_evidence(
            db,
            novel,
            snapshot,
            {"entity_id": entities[0].id},
            interaction_locale="en",
        )

        assert any(item.title.startswith("Chapter ") for item in evidence if item.source_type == "chapter_excerpt")
        assert any(item.title == f"Entity · {entities[0].name}" for item in evidence)
        assert any(item.why_relevant == "Current research target entity" for item in evidence)
