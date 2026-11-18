# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot research tool dispatch tests."""

from app.models import Chapter

class TestToolDispatch:
    def _make_snapshot(self, db, novel, entities=None, relationships=None, systems=None):
        from app.core.copilot.scope import load_scope_snapshot
        return load_scope_snapshot(db, novel, "research", "whole_book", None)

    def test_tool_find_by_entity_name(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find
        from app.core.copilot.workspace import Workspace
        workspace = Workspace()
        result = _tool_find("张三", "all", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)
        assert data["total_found"] > 0
        # Should have found world rows matching 张三
        pack_ids = [p["pack_id"] for p in data["packs"]]
        assert any("ent_" in pid for pid in pack_ids)

    def test_tool_find_by_alias(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find
        from app.core.copilot.workspace import Workspace
        workspace = Workspace()
        result = _tool_find("三哥", "all", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)
        assert data["total_found"] > 0

    def test_tool_find_drafts_returns_quality_signals(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find
        from app.core.copilot.workspace import Workspace
        workspace = Workspace()
        result = _tool_find("草稿", "drafts", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)
        # entities[2] (王五) is draft with empty description
        has_draft = any("draft" in p.get("pack_id", "") for p in data["packs"])
        assert has_draft

    def test_tool_find_drafts_localizes_quality_signals_to_english(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find
        from app.core.copilot.workspace import Workspace

        workspace = Workspace()
        result = _tool_find("draft", "drafts", db, novel.id, novel, self._make_snapshot(db, novel), workspace, interaction_locale="en")
        import json
        data = json.loads(result)

        assert data["total_found"] > 0
        pack = workspace.evidence_packs[data["packs"][0]["pack_id"]]
        assert "[Draft" in pack.preview_excerpt
        assert any(issue in pack.preview_excerpt for issue in ("Missing description", "No aliases", "No attributes"))

    def test_tool_find_whole_book_prioritizes_world_rows(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find
        from app.core.copilot.workspace import Workspace
        workspace = Workspace()
        result = _tool_find("张三", "world_rows", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)
        assert data["total_found"] > 0
        # World row packs should have entity-based pack IDs
        assert any("ent_" in p["pack_id"] for p in data["packs"])

    def test_tool_find_unknown_query_falls_back_to_story_text(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find
        from app.core.copilot.workspace import Workspace
        workspace = Workspace()
        # Search for something in chapter content but not in entity names
        result = _tool_find("宗门修行", "story_text", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)
        assert data["total_found"] > 0

    def test_tool_find_all_scope_can_return_chapter_only_results(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find
        from app.core.copilot.workspace import Workspace

        chapters[0].content = "第一章写到远古星门重新开启。"
        db.commit()

        workspace = Workspace()
        result = _tool_find("远古星门", "all", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)

        assert data["total_found"] > 0
        pack_id = data["packs"][0]["pack_id"]
        pack = workspace.evidence_packs[pack_id]
        assert pack.source_refs[0]["type"] == "chapter"
        assert pack.source_refs[0]["chapter_number"] == 1

    def test_tool_find_story_text_keyword_bag_scans_whole_book_not_just_latest_chapters(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find
        from app.core.copilot.workspace import Workspace

        db.add_all([
            Chapter(novel_id=novel.id, chapter_number=4, title="第4章", content="这是后续章节，没有目标词。"),
            Chapter(novel_id=novel.id, chapter_number=5, title="第5章", content="这是后续章节，仍然没有目标词。"),
            Chapter(novel_id=novel.id, chapter_number=6, title="第6章", content="这是最新章节，也没有目标词。"),
        ])
        chapters[0].content = "第一章写到远古星门重新开启，帝国军团开始调动。"
        db.commit()

        workspace = Workspace()
        result = _tool_find("帝国 远古星门", "story_text", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)

        assert data["total_found"] > 0
        pack_id = data["packs"][0]["pack_id"]
        pack = workspace.evidence_packs[pack_id]
        assert pack.source_refs[0]["chapter_number"] == 1
        assert set(pack.anchor_terms) >= {"帝国", "远古星门"}

    def test_tool_find_world_rows_supports_multi_term_queries(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find
        from app.core.copilot.workspace import Workspace

        entities[1].description = "帝国军团中的统帅人物"
        db.commit()

        workspace = Workspace()
        result = _tool_find("帝国 军团", "world_rows", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)

        assert data["total_found"] > 0
        assert any("ent_" in p["pack_id"] for p in data["packs"])

    def test_tool_open_expands_known_pack(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find, _tool_open
        from app.core.copilot.workspace import Workspace
        workspace = Workspace()
        # First find to populate packs
        _tool_find("张三", "all", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        assert len(workspace.evidence_packs) > 0
        pack_id = next(iter(workspace.evidence_packs))
        result = _tool_open(pack_id, 2000, db, novel, workspace)
        import json
        data = json.loads(result)
        assert data["pack_id"] == pack_id
        assert "error" not in data

    def test_tool_open_rejects_unknown_pack(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_open
        from app.core.copilot.workspace import Workspace
        workspace = Workspace()
        result = _tool_open("nonexistent_pack", 2000, db, novel, workspace)
        import json
        data = json.loads(result)
        assert "error" in data

    def test_tool_open_rejects_unknown_pack_in_english(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_open
        from app.core.copilot.workspace import Workspace

        workspace = Workspace()
        result = _tool_open("nonexistent_pack", 2000, db, novel, workspace, interaction_locale="en")
        import json
        data = json.loads(result)

        assert data["error"] == "Unknown pack_id: nonexistent_pack. Use find() first."

    def test_tool_open_many_expands_multiple_packs_in_input_order(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find, _tool_open_many
        from app.core.copilot.workspace import Workspace

        db.add(
            Chapter(
                novel_id=novel.id,
                chapter_number=4,
                title="第4章",
                content="第四章再次提到远古星门的异动。",
            )
        )
        chapters[0].content = "第一章写到远古星门重新开启。"
        db.commit()

        workspace = Workspace()
        result = _tool_find(
            "远古星门",
            "story_text",
            db,
            novel.id,
            novel,
            self._make_snapshot(db, novel),
            workspace,
        )
        import json

        find_data = json.loads(result)
        pack_ids = [pack["pack_id"] for pack in find_data["packs"][:2]]
        assert len(pack_ids) == 2

        requested_order = [pack_ids[1], pack_ids[0]]
        open_result = _tool_open_many(requested_order, 800, db, novel, workspace)
        data = json.loads(open_result)

        assert data["opened_count"] == 2
        assert [item["pack_id"] for item in data["results"]] == requested_order
        assert all("expanded_text" in item for item in data["results"])
        assert workspace.opened_pack_ids == requested_order

    def test_tool_open_many_rejects_more_than_max_unique_packs(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_open_many
        from app.core.copilot.workspace import Workspace

        workspace = Workspace()
        open_result = _tool_open_many(
            ["pk_a", "pk_b", "pk_c", "pk_d"],
            800,
            db,
            novel,
            workspace,
        )
        import json

        data = json.loads(open_result)

        assert data["opened_count"] == 0
        assert data["requested_count"] == 4
        assert data["max_pack_ids"] == 3
        assert data["results"] == []
        assert "error" in data
        assert workspace.opened_pack_ids == []

    def test_tool_open_many_reports_partial_unknown_pack_errors(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find, _tool_open_many
        from app.core.copilot.workspace import Workspace

        chapters[0].content = "第一章写到远古星门重新开启。"
        db.commit()

        workspace = Workspace()
        result = _tool_find(
            "远古星门",
            "story_text",
            db,
            novel.id,
            novel,
            self._make_snapshot(db, novel),
            workspace,
        )
        import json

        find_data = json.loads(result)
        valid_pack_id = find_data["packs"][0]["pack_id"]

        open_result = _tool_open_many(
            ["nonexistent_pack", valid_pack_id],
            800,
            db,
            novel,
            workspace,
        )
        data = json.loads(open_result)

        assert data["opened_count"] == 1
        assert data["failed_count"] == 1
        assert data["failed_pack_ids"] == ["nonexistent_pack"]
        assert "error" in data
        assert data["results"][0]["pack_id"] == "nonexistent_pack"
        assert "error" in data["results"][0]
        assert data["results"][1]["pack_id"] == valid_pack_id
        assert "expanded_text" in data["results"][1]

    def test_tool_open_many_does_not_shrink_existing_expanded_text(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_open, _tool_open_many
        from app.core.copilot.workspace import EvidencePack, Workspace

        chapters[0].content = "甲" * 180 + "远古星门" + "乙" * 2600
        db.commit()

        workspace = Workspace(
            evidence_packs={
                "pk_a": EvidencePack(
                    pack_id="pk_a",
                    source_refs=[{
                        "type": "chapter",
                        "chapter_id": chapters[0].id,
                        "chapter_number": chapters[0].chapter_number,
                        "start_pos": 180,
                        "end_pos": 184,
                    }],
                    preview_excerpt="远古星门",
                    anchor_terms=["远古星门"],
                    support_count=1,
                    related_targets=[{"type": "chapter", "chapter_id": chapters[0].id}],
                ),
            }
        )

        import json

        first_result = json.loads(_tool_open("pk_a", 2000, db, novel, workspace))
        first_length = len(first_result["expanded_text"])

        second_result = json.loads(_tool_open_many(["pk_a"], 200, db, novel, workspace))
        second_length = len(second_result["results"][0]["expanded_text"])

        assert first_length > 400
        assert second_length == first_length
        assert len(workspace.evidence_packs["pk_a"].expanded_text or "") == first_length

    def test_tool_open_many_partial_failures_mark_trace_incomplete(self, db, novel, entities, chapters):
        from app.core.copilot.research_tools import _tool_find, _tool_open_many
        from app.core.copilot.tracing import build_tool_journal_entry
        from app.core.copilot.workspace import Workspace

        chapters[0].content = "第一章写到远古星门重新开启。"
        db.commit()

        workspace = Workspace()
        find_result = _tool_find(
            "远古星门",
            "story_text",
            db,
            novel.id,
            novel,
            self._make_snapshot(db, novel),
            workspace,
        )
        import json

        valid_pack_id = json.loads(find_result)["packs"][0]["pack_id"]
        open_result = _tool_open_many(
            ["nonexistent_pack", valid_pack_id],
            800,
            db,
            novel,
            workspace,
        )

        entry = build_tool_journal_entry(
            tool_name="open_many",
            tool_args={"pack_ids": ["nonexistent_pack", valid_pack_id], "expand_chars": 800},
            tool_result=open_result,
            round_number=1,
            call_index=1,
            interaction_locale="zh",
        )

        assert entry["status"] == "incomplete"
        assert "检索步骤未完成" in entry["summary"]

    def test_tool_read_returns_live_entity_state(self, db, novel, entities, attributes):
        from app.core.copilot.research_tools import _tool_read
        snapshot = self._make_snapshot(db, novel)
        result = _tool_read([{"type": "entity", "id": entities[0].id}], db, novel.id, snapshot)
        import json
        data = json.loads(result)
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "张三"
        assert data["results"][0]["type"] == "entity"

    def test_tool_read_returns_live_relationship_state(self, db, novel, entities, relationships):
        from app.core.copilot.research_tools import _tool_read
        snapshot = self._make_snapshot(db, novel)
        result = _tool_read([{"type": "relationship", "id": relationships[0].id}], db, novel.id, snapshot)
        import json
        data = json.loads(result)
        assert len(data["results"]) == 1
        assert data["results"][0]["label"] == "对手"
