# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot backend evidence loading tests."""

import pytest

class TestBackendEvidence:
    def test_entity_scope_uses_window_index_only_when_fresh(self, db, novel, entities, chapters):
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.indexing import mark_window_index_build_succeeded
        from app.core.indexing.window_index import NovelIndex, WindowRef

        mark_window_index_build_succeeded(
            novel,
            index_payload=NovelIndex(
                entity_windows={
                    entities[0].name: [
                        WindowRef(
                            window_id=1,
                            chapter_id=chapters[0].id,
                            start_pos=0,
                            end_pos=len(chapters[0].content),
                            entity_count=1,
                        )
                    ]
                },
                window_entities={1: {entities[0].name}},
            ).to_msgpack(),
            revision=1,
        )
        db.commit()

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        evidence = gather_evidence(db, novel, snapshot, {"entity_id": entities[0].id})

        chapter_evidence = [item for item in evidence if item.source_type == "chapter_excerpt"]
        assert chapter_evidence
        assert any("包含对" in item.why_relevant for item in chapter_evidence)

    def test_evidence_has_verifiable_source_ref(self, db, novel, entities, chapters):
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        evidence = gather_evidence(db, novel, snapshot, {"entity_id": entities[0].id})

        assert len(evidence) > 0
        for ev in evidence:
            assert ev.source_ref is not None
            assert ev.evidence_id  # unique ID for citation linking
            if ev.source_type == "chapter_excerpt":
                assert "chapter_id" in ev.source_ref
            elif ev.source_type == "world_entity":
                assert "entity_id" in ev.source_ref
            elif ev.source_type == "world_relationship":
                assert "relationship_id" in ev.source_ref

    def test_evidence_includes_entity_context_for_entity_scope(self, db, novel, entities, attributes, chapters):
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        evidence = gather_evidence(db, novel, snapshot, {"entity_id": entities[0].id})

        entity_evidence = [e for e in evidence if e.source_type == "world_entity"]
        assert len(entity_evidence) >= 1
        assert "张三" in entity_evidence[0].excerpt

    def test_whole_book_preload_does_not_default_to_latest_three_chapters(self, db, novel, entities, relationships, systems, chapters):
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)

        assert all(item.source_type != "chapter_excerpt" for item in evidence)

    @pytest.mark.parametrize(
        ("prepare_state", "expected_reason"),
        [
            ("missing", "全书内容还在准备中，先回退到最近章节上下文"),
            ("stale", "章节有更新，先回退到最近章节上下文"),
            ("failed", "全书内容整理失败，先回退到最近章节上下文"),
        ],
    )
    def test_entity_scope_falls_back_with_explicit_reason(
        self,
        db,
        novel,
        entities,
        chapters,
        prepare_state,
        expected_reason,
    ):
        from app.core.copilot.scope import gather_evidence, load_scope_snapshot
        from app.core.indexing import (
            mark_window_index_build_failed,
            mark_window_index_build_succeeded,
            mark_window_index_inputs_changed,
        )

        if prepare_state == "stale":
            mark_window_index_build_succeeded(
                novel,
                index_payload=b"index-bytes",
                revision=1,
            )
            db.commit()
            mark_window_index_inputs_changed(novel)
            db.commit()
        elif prepare_state == "failed":
            mark_window_index_build_failed(
                novel,
                error="窗口索引重建失败，请稍后重试",
                revision=1,
            )
            db.commit()

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        evidence = gather_evidence(db, novel, snapshot, {"entity_id": entities[0].id})

        chapter_evidence = [item for item in evidence if item.source_type == "chapter_excerpt"]
        assert chapter_evidence
        assert all(item.why_relevant == expected_reason for item in chapter_evidence)

    @pytest.mark.parametrize("state", ["fresh", "missing", "stale", "failed"])
    def test_window_index_find_requires_fresh_state(self, db, novel, entities, chapters, state):
        from app.core.copilot.research_tools import _find_from_window_index
        from app.core.copilot.scope import load_scope_snapshot
        from app.core.indexing import (
            mark_window_index_build_failed,
            mark_window_index_build_succeeded,
            mark_window_index_inputs_changed,
        )
        from app.core.indexing.window_index import NovelIndex, WindowRef

        if state == "fresh":
            mark_window_index_build_succeeded(
                novel,
                index_payload=NovelIndex(
                    entity_windows={
                        entities[0].name: [
                            WindowRef(
                                window_id=1,
                                chapter_id=chapters[0].id,
                                start_pos=0,
                                end_pos=len(chapters[0].content),
                                entity_count=1,
                            )
                        ]
                    },
                    window_entities={1: {entities[0].name}},
                ).to_msgpack(),
                revision=1,
            )
            db.commit()
        elif state == "stale":
            mark_window_index_build_succeeded(
                novel,
                index_payload=b"index-bytes",
                revision=1,
            )
            db.commit()
            mark_window_index_inputs_changed(novel)
            db.commit()
        elif state == "failed":
            mark_window_index_build_failed(
                novel,
                error="窗口索引重建失败，请稍后重试",
                revision=1,
            )
            db.commit()

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        packs = _find_from_window_index("张三", db, novel.id, novel, snapshot)

        if state == "fresh":
            assert packs
        else:
            assert packs == []
