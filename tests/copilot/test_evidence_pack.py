# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot evidence-pack utility tests."""

class TestEvidencePack:
    def test_pack_id_includes_content_hash(self):
        from app.core.copilot.workspace import make_pack_id as _make_pack_id
        id1 = _make_pack_id("pk_ent_1", "content A")
        id2 = _make_pack_id("pk_ent_1", "content B")
        assert id1 != id2
        # Same content → same ID
        id3 = _make_pack_id("pk_ent_1", "content A")
        assert id1 == id3

    def test_overlapping_windows_deduplicate(self):
        from app.core.copilot.research_tools import _deduplicate_packs
        from app.core.copilot.workspace import EvidencePack
        p1 = EvidencePack(pack_id="pk_1", source_refs=[], preview_excerpt="a", anchor_terms=[], support_count=2, related_targets=[])
        p2 = EvidencePack(pack_id="pk_1", source_refs=[], preview_excerpt="a", anchor_terms=[], support_count=1, related_targets=[])
        p3 = EvidencePack(pack_id="pk_2", source_refs=[], preview_excerpt="b", anchor_terms=[], support_count=1, related_targets=[])
        result = _deduplicate_packs([p1, p2, p3])
        assert len(result) == 2
        # Should keep the one with higher support_count
        by_id = {p.pack_id: p for p in result}
        assert by_id["pk_1"].support_count == 2
