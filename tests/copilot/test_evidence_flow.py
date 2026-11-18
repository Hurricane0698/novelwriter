# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot workspace evidence flow tests."""

class TestEvidenceFlow:
    def test_workspace_evidence_merges_to_evidence_items(self, db, novel, entities, chapters):
        """Evidence packs discovered by tools flow into the serializable evidence list."""
        from app.core.copilot.scope import EvidenceItem
        from app.core.copilot.workspace import EvidencePack, Workspace, evidence_from_workspace as _evidence_from_workspace

        base = [EvidenceItem(
            evidence_id="ev_base", source_type="chapter_excerpt",
            source_ref={"chapter_id": 1}, title="base", excerpt="text", why_relevant="test",
        )]
        workspace = Workspace()
        workspace.evidence_packs["pk_ent_1_abc12345"] = EvidencePack(
            pack_id="pk_ent_1_abc12345",
            source_refs=[{"type": "entity", "id": entities[0].id}],
            preview_excerpt="张三是主角",
            anchor_terms=["张三"],
            support_count=2,
            related_targets=[],
        )
        merged = _evidence_from_workspace(workspace, base)
        assert len(merged) == 2
        pack_ev = [e for e in merged if e.evidence_id.startswith("pack_")]
        assert len(pack_ev) == 1
        assert pack_ev[0].source_type == "world_entity"
        assert pack_ev[0].pack_id == "pk_ent_1_abc12345"
        assert pack_ev[0].anchor_terms == ["张三"]
        assert pack_ev[0].support_count == 2
        assert pack_ev[0].preview_excerpt == "张三是主角"
        assert pack_ev[0].expanded is False

    def test_workspace_evidence_localizes_reason_to_english(self, db, novel, entities, chapters):
        from app.core.copilot.scope import EvidenceItem
        from app.core.copilot.workspace import EvidencePack, Workspace, evidence_from_workspace as _evidence_from_workspace

        base = [EvidenceItem(
            evidence_id="ev_base", source_type="chapter_excerpt",
            source_ref={"chapter_id": 1}, title="base", excerpt="text", why_relevant="test",
        )]
        workspace = Workspace()
        workspace.evidence_packs["pk_ent_1_abc12345"] = EvidencePack(
            pack_id="pk_ent_1_abc12345",
            source_refs=[{"type": "entity", "id": entities[0].id}],
            preview_excerpt="Zhang San is the protagonist",
            anchor_terms=["Zhang San"],
            support_count=2,
            related_targets=[],
        )

        merged = _evidence_from_workspace(workspace, base, interaction_locale="en")

        pack_ev = [e for e in merged if e.evidence_id.startswith("pack_")]
        assert len(pack_ev) == 1
        assert pack_ev[0].why_relevant == "Compiled from 2 related clues"
