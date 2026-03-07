"""
Tests for Context Assembly — visibility injection rules.

Validates that writer and consistency checker receive the correct
subset of world model data per world-model-schema.md spec.

These tests target the context_assembly module's output, not the LLM.
"""

import pytest
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Novel




# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def novel(db):
    n = Novel(title="逆天邪神", author="火星引力", file_path="/tmp/test.txt", total_chapters=200)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture
def populated_world(db, novel):
    """Create a world model with various visibility levels for testing."""
    from app.models import (
        WorldEntity, WorldEntityAttribute, WorldRelationship, WorldSystem,
    )

    # Entities
    yunche = WorldEntity(novel_id=novel.id, name="云澈", entity_type="Character",
                         description="主角", status="confirmed", aliases=["小澈"])
    chuyuexian = WorldEntity(novel_id=novel.id, name="楚月仙", entity_type="Character",
                              description="师父", status="confirmed")
    draft_char = WorldEntity(novel_id=novel.id, name="神秘人", entity_type="Character",
                              description="未确认角色", status="draft")
    cangfeng = WorldEntity(novel_id=novel.id, name="苍风帝国", entity_type="Faction",
                            description="二流帝国", status="confirmed")
    db.add_all([yunche, chuyuexian, draft_char, cangfeng])
    db.commit()

    # Attributes with different visibility
    attrs = [
        WorldEntityAttribute(entity_id=yunche.id, key="修为", surface="真玄境", visibility="active"),
        WorldEntityAttribute(entity_id=yunche.id, key="性格", surface="坚韧不拔", visibility="reference"),
        WorldEntityAttribute(entity_id=yunche.id, key="神秘力量", surface="偶尔爆发银色光芒",
                             truth="邪神遗脉", visibility="active"),
        WorldEntityAttribute(entity_id=yunche.id, key="真实血脉", surface="表面普通人",
                             truth="邪神传人", visibility="hidden"),
        WorldEntityAttribute(entity_id=chuyuexian.id, key="修为", surface="御座境", visibility="active"),
    ]
    db.add_all(attrs)

    # Relationships with different visibility
    rels = [
        WorldRelationship(novel_id=novel.id, source_id=yunche.id, target_id=chuyuexian.id,
                          label="师徒", visibility="active", status="confirmed"),
        WorldRelationship(novel_id=novel.id, source_id=yunche.id, target_id=cangfeng.id,
                          label="暗中对抗", visibility="hidden", status="confirmed"),
        WorldRelationship(novel_id=novel.id, source_id=yunche.id, target_id=chuyuexian.id,
                          label="暗恋", visibility="reference",
                          description="云澈对楚月仙有好感", status="confirmed"),
        WorldRelationship(novel_id=novel.id, source_id=yunche.id, target_id=cangfeng.id,
                          label="draft关系", status="draft"),
    ]
    db.add_all(rels)

    # Systems
    sys_confirmed = WorldSystem(
        novel_id=novel.id, name="修炼体系", display_type="hierarchy",
        description="玄气修炼等级", status="confirmed", visibility="active",
        data={"nodes": [{"id": "xuandi", "label": "玄帝境", "entity_id": None, "children": []}]},
        constraints=["突破需要天材地宝"],
    )
    sys_hidden = WorldSystem(
        novel_id=novel.id, name="隐藏体系", display_type="list",
        description="不应被writer看到", status="confirmed", visibility="hidden",
    )
    sys_draft = WorldSystem(
        novel_id=novel.id, name="draft体系", display_type="list",
        description="未确认", status="draft", visibility="active",
    )
    db.add_all([sys_confirmed, sys_hidden, sys_draft])
    db.commit()

    return {
        "novel": novel,
        "yunche": yunche,
        "chuyuexian": chuyuexian,
        "draft_char": draft_char,
        "cangfeng": cangfeng,
    }


# ===========================================================================
# Writer Context
# ===========================================================================

class TestWriterContext:
    """Writer context: what the writing LLM should see."""

    def test_only_confirmed_entities(self, db, populated_world):
        """Draft entities must not appear in writer context."""
        from app.core.context_assembly import assemble_writer_context

        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="云澈走进了大殿")

        entity_names = [e["name"] for e in ctx["entities"]]
        assert "云澈" in entity_names
        assert "神秘人" not in entity_names  # draft

    def test_entity_aliases_injected(self, db, populated_world):
        """Writer context should include entity aliases for stable naming."""
        from app.core.context_assembly import assemble_writer_context

        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="云澈走进了大殿")
        yunche = next(e for e in ctx["entities"] if e["name"] == "云澈")
        assert yunche.get("aliases") == ["小澈"]

    def test_active_attribute_value_injected(self, db, populated_world):
        """Active attributes: inject value."""
        from app.core.context_assembly import assemble_writer_context

        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="云澈运转玄力")

        yunche_attrs = _find_entity_attrs(ctx, "云澈")
        xiuwei = _find_attr(yunche_attrs, "修为")
        assert xiuwei is not None
        assert xiuwei["surface"] == "真玄境"

    def test_hidden_attribute_never_injected(self, db, populated_world):
        """Hidden attributes must NEVER appear in writer context."""
        from app.core.context_assembly import assemble_writer_context

        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="云澈走进了大殿")

        yunche_attrs = _find_entity_attrs(ctx, "云澈")
        assert _find_attr(yunche_attrs, "真实血脉") is None

    def test_active_attribute_with_truth_surface_only(self, db, populated_world):
        """Active attributes with truth: inject surface but NOT truth."""
        from app.core.context_assembly import assemble_writer_context

        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="云澈感到体内力量涌动")

        yunche_attrs = _find_entity_attrs(ctx, "云澈")
        mystery = _find_attr(yunche_attrs, "神秘力量")
        assert mystery is not None
        assert mystery["surface"] == "偶尔爆发银色光芒"
        assert "truth" not in mystery or mystery.get("truth") is None

    def test_reference_attribute_injected_when_entity_directly_involved(self, db, populated_world):
        """Reference attributes injected when entity is directly mentioned in chapter."""
        from app.core.context_assembly import assemble_writer_context

        # Chapter directly about 云澈 → reference attribute "性格" should be included
        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="云澈独自面对强敌，咬牙坚持")

        yunche_attrs = _find_entity_attrs(ctx, "云澈")
        xingge = _find_attr(yunche_attrs, "性格")
        assert xingge is not None
        assert xingge["surface"] == "坚韧不拔"

    def test_reference_attribute_not_injected_when_entity_not_involved(self, db, populated_world):
        """Reference attributes NOT injected when entity is not directly mentioned."""
        from app.core.context_assembly import assemble_writer_context

        # Chapter only mentions 楚月仙, not 云澈 → 云澈's reference attrs should not appear
        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="楚月仙在冰云仙宫独自修炼")

        # 云澈 not mentioned → not in context at all, so no reference attrs
        yunche_attrs = _find_entity_attrs(ctx, "云澈")
        assert _find_attr(yunche_attrs, "性格") is None

    def test_hidden_relationship_not_injected(self, db, populated_world):
        """Hidden relationships must not appear in writer context."""
        from app.core.context_assembly import assemble_writer_context

        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="云澈来到苍风帝国")

        rel_types = [r["label"] for r in ctx.get("relationships", [])]
        assert "暗中对抗" not in rel_types

    def test_active_relationship_injected(self, db, populated_world):
        """Active confirmed relationships should be injected."""
        from app.core.context_assembly import assemble_writer_context

        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="云澈和楚月仙一起修炼")

        rel_types = [r["label"] for r in ctx.get("relationships", [])]
        assert "师徒" in rel_types

    def test_draft_relationship_not_injected(self, db, populated_world):
        """Draft relationships must not appear in writer context."""
        from app.core.context_assembly import assemble_writer_context

        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="云澈来到苍风帝国")

        rel_types = [r["label"] for r in ctx.get("relationships", [])]
        assert "draft关系" not in rel_types

    def test_active_system_injected(self, db, populated_world):
        """Confirmed active systems should be injected with data + constraints."""
        from app.core.context_assembly import assemble_writer_context

        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="云澈尝试突破修为")

        system_names = [s["name"] for s in ctx.get("systems", [])]
        assert "修炼体系" in system_names

        xiulian = next(s for s in ctx["systems"] if s["name"] == "修炼体系")
        assert "data" in xiulian
        assert "constraints" in xiulian

    def test_hidden_system_not_injected(self, db, populated_world):
        """Hidden systems must not appear in writer context."""
        from app.core.context_assembly import assemble_writer_context

        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="云澈探索世界")

        system_names = [s["name"] for s in ctx.get("systems", [])]
        assert "隐藏体系" not in system_names

    def test_draft_system_not_injected(self, db, populated_world):
        """Draft systems must not appear in writer context."""
        from app.core.context_assembly import assemble_writer_context

        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="云澈探索世界")

        system_names = [s["name"] for s in ctx.get("systems", [])]
        assert "draft体系" not in system_names

    def test_end_to_end_chapter_context(self, db, populated_world):
        """Real scenario: chapter mentions multiple entities, verify combined context."""
        from app.core.context_assembly import assemble_writer_context

        ctx = assemble_writer_context(
            db, populated_world["novel"].id,
            chapter_text="云澈和楚月仙来到苍风帝国的皇宫，准备突破修为",
        )

        # Both mentioned entities present
        entity_names = [e["name"] for e in ctx["entities"]]
        assert "云澈" in entity_names
        assert "楚月仙" in entity_names
        assert "苍风帝国" in entity_names
        assert "神秘人" not in entity_names  # draft

        # 云澈: active visible, hidden not
        yunche_attrs = _find_entity_attrs(ctx, "云澈")
        assert _find_attr(yunche_attrs, "修为") is not None       # active
        assert _find_attr(yunche_attrs, "神秘力量") is not None    # active (with truth)
        assert _find_attr(yunche_attrs, "真实血脉") is None        # hidden

        # truth not leaked for active attribute with truth
        mystery = _find_attr(yunche_attrs, "神秘力量")
        assert "truth" not in mystery or mystery.get("truth") is None

        # Relationships: active visible, hidden not, draft not
        rel_types = [r["label"] for r in ctx.get("relationships", [])]
        assert "师徒" in rel_types
        assert "暗中对抗" not in rel_types
        assert "draft关系" not in rel_types

        # System: confirmed active visible
        system_names = [s["name"] for s in ctx.get("systems", [])]
        assert "修炼体系" in system_names
        assert "隐藏体系" not in system_names
        assert "draft体系" not in system_names

    def test_entity_not_mentioned_not_injected(self, db, populated_world):
        """Entities not mentioned in chapter text should not appear in writer context."""
        from app.core.context_assembly import assemble_writer_context

        # Only 楚月仙 mentioned — 云澈 and 苍风帝国 should not be injected
        ctx = assemble_writer_context(db, populated_world["novel"].id, chapter_text="楚月仙在冰云仙宫独自修炼")

        entity_names = [e["name"] for e in ctx["entities"]]
        assert "楚月仙" in entity_names
        assert "云澈" not in entity_names
        assert "苍风帝国" not in entity_names

    def test_longest_match_priority_avoids_nested_short_alias(self, db, novel):
        """When a long name matches, contained short aliases should not double-count."""
        from app.core.context_assembly import assemble_writer_context
        from app.models import WorldEntity

        e = WorldEntity(
            novel_id=novel.id,
            name="云澈",
            entity_type="Character",
            description="主角",
            status="confirmed",
            aliases=["云"],
        )
        db.add(e)
        db.commit()
        db.refresh(e)

        ctx = assemble_writer_context(db, novel.id, chapter_text="云澈走进了大殿")
        assert ctx["debug"]["relevant_entity_ids"] == [e.id]

        out = next(x for x in ctx["entities"] if x["id"] == e.id)
        assert out["match_count"] == 1
        assert out["matched_terms"] == ["云澈"]

    def test_multiple_terms_for_same_entity_dedupe_relevant_ids(self, db, novel):
        """Multiple mentions/aliases of the same entity must not duplicate entity IDs."""
        from app.core.context_assembly import assemble_writer_context
        from app.models import WorldEntity

        e = WorldEntity(
            novel_id=novel.id,
            name="云澈",
            entity_type="Character",
            status="confirmed",
            aliases=["小澈"],
        )
        db.add(e)
        db.commit()
        db.refresh(e)

        ctx = assemble_writer_context(db, novel.id, chapter_text="云澈对小澈说道：小澈，走。")
        assert ctx["debug"]["relevant_entity_ids"] == [e.id]

        out = next(x for x in ctx["entities"] if x["id"] == e.id)
        assert out["match_count"] == 3
        assert sorted(out["matched_terms"]) == ["云澈", "小澈"]

    def test_ambiguous_alias_does_not_trigger_relevance(self, db, novel):
        """An alias mapping to multiple entities should be disabled and not trigger relevance."""
        from app.core.context_assembly import assemble_writer_context
        from app.models import WorldEntity

        e1 = WorldEntity(
            novel_id=novel.id,
            name="苍风帝国",
            entity_type="Faction",
            status="confirmed",
            aliases=["帝国"],
        )
        e2 = WorldEntity(
            novel_id=novel.id,
            name="火焰帝国",
            entity_type="Faction",
            status="confirmed",
            aliases=["帝国"],
        )
        db.add_all([e1, e2])
        db.commit()

        ctx = assemble_writer_context(db, novel.id, chapter_text="帝国陷入危机")
        assert ctx["debug"]["relevant_entity_ids"] == []
        assert ctx["entities"] == []
        assert "帝国" in ctx["debug"]["ambiguous_keywords_disabled"]

    def test_budget_truncation_order_relationships_then_attributes_then_entities(self, db, novel):
        """Budget truncation drops reference relationships first, then reference attributes, then tail entities."""
        from copy import deepcopy

        from app.core.context_assembly import (
            _estimate_writer_context_tokens,
            apply_writer_context_budget,
            assemble_writer_context,
        )
        from app.models import WorldEntity, WorldEntityAttribute, WorldRelationship, WorldSystem

        a = WorldEntity(novel_id=novel.id, name="甲", entity_type="Character", status="confirmed")
        b = WorldEntity(novel_id=novel.id, name="乙", entity_type="Character", status="confirmed")
        c = WorldEntity(novel_id=novel.id, name="丙", entity_type="Character", status="confirmed")
        db.add_all([a, b, c])
        db.commit()
        db.refresh(a)
        db.refresh(b)
        db.refresh(c)

        long_text = "很长的参考信息" * 100
        db.add_all(
            [
                WorldEntityAttribute(entity_id=a.id, key="active", surface="ok", visibility="active"),
                WorldEntityAttribute(entity_id=a.id, key="ref", surface=long_text, visibility="reference"),
                WorldEntityAttribute(entity_id=b.id, key="active", surface="ok", visibility="active"),
                WorldEntityAttribute(entity_id=b.id, key="ref", surface=long_text, visibility="reference"),
                WorldEntityAttribute(entity_id=c.id, key="active", surface="ok", visibility="active"),
                WorldEntityAttribute(entity_id=c.id, key="ref", surface=long_text, visibility="reference"),
            ]
        )

        db.add_all(
            [
                WorldRelationship(
                    novel_id=novel.id,
                    source_id=a.id,
                    target_id=b.id,
                    label="盟友",
                    description="ok",
                    visibility="active",
                    status="confirmed",
                ),
                WorldRelationship(
                    novel_id=novel.id,
                    source_id=a.id,
                    target_id=b.id,
                    label="传闻",
                    description=long_text,
                    visibility="reference",
                    status="confirmed",
                ),
                WorldRelationship(
                    novel_id=novel.id,
                    source_id=b.id,
                    target_id=c.id,
                    label="传闻",
                    description=long_text,
                    visibility="reference",
                    status="confirmed",
                ),
            ]
        )

        sys_active = WorldSystem(
            novel_id=novel.id,
            name="体系",
            display_type="list",
            description="small",
            status="confirmed",
            visibility="active",
            data={"items": [{"label": "ok"}]},
        )
        db.add(sys_active)
        db.commit()

        # Mention counts: 甲(3), 乙(2), 丙(1) so entity order is deterministic.
        full_ctx = assemble_writer_context(db, novel.id, chapter_text="甲甲甲 乙乙 丙")
        full_est = _estimate_writer_context_tokens(full_ctx)
        assert full_est > 0

        # Budget that requires dropping reference relationships, but keeps reference attributes.
        drop_rels = deepcopy(full_ctx)
        drop_rels["relationships"] = [r for r in drop_rels["relationships"] if r["visibility"] != "reference"]
        est_drop_rels = _estimate_writer_context_tokens(drop_rels)
        assert est_drop_rels < full_est

        ctx_rel_only = apply_writer_context_budget(full_ctx, max_estimated_tokens=est_drop_rels)
        assert all(r["visibility"] != "reference" for r in ctx_rel_only["relationships"])
        assert any(
            a_["visibility"] == "reference"
            for e_ in ctx_rel_only["entities"]
            for a_ in e_["attributes"]
        )

        # Budget that requires dropping reference attributes too, but keeps all entities.
        drop_attrs = deepcopy(drop_rels)
        for e_ in drop_attrs["entities"]:
            e_["attributes"] = [a_ for a_ in e_["attributes"] if a_["visibility"] != "reference"]
        est_drop_attrs = _estimate_writer_context_tokens(drop_attrs)

        ctx_no_ref_attrs = apply_writer_context_budget(full_ctx, max_estimated_tokens=est_drop_attrs)
        assert len(ctx_no_ref_attrs["entities"]) == len(full_ctx["entities"])
        assert all(r["visibility"] != "reference" for r in ctx_no_ref_attrs["relationships"])
        assert all(
            a_["visibility"] != "reference"
            for e_ in ctx_no_ref_attrs["entities"]
            for a_ in e_["attributes"]
        )

        # Budget that requires dropping tail entities (after dropping ref rels + attrs).
        drop_one = deepcopy(drop_attrs)
        dropped = drop_one["entities"].pop()
        dropped_id = dropped["id"]
        drop_one["relationships"] = [
            r
            for r in drop_one["relationships"]
            if r["source_id"] != dropped_id and r["target_id"] != dropped_id
        ]
        est_drop_one = _estimate_writer_context_tokens(drop_one)

        ctx_drop_one = apply_writer_context_budget(full_ctx, max_estimated_tokens=est_drop_one)
        assert len(ctx_drop_one["entities"]) == len(full_ctx["entities"]) - 1
        injected_names = [e_["name"] for e_ in ctx_drop_one["entities"]]
        assert "丙" not in injected_names


# ===========================================================================
# Consistency Checker Context
# ===========================================================================

class TestConsistencyCheckerContext:
    """Consistency checker: sees everything including hidden + truth."""

    def test_hidden_attribute_visible(self, db, populated_world):
        """Consistency checker sees hidden attributes with value + truth."""
        from app.core.context_assembly import assemble_checker_context

        ctx = assemble_checker_context(db, populated_world["novel"].id, chapter_text="云澈走进了大殿")

        yunche_attrs = _find_entity_attrs(ctx, "云澈")
        hidden = _find_attr(yunche_attrs, "真实血脉")
        assert hidden is not None
        assert hidden["surface"] == "表面普通人"
        assert hidden["truth"] == "邪神传人"

    def test_active_attribute_with_truth_checker_sees_both(self, db, populated_world):
        """Consistency checker sees active attributes with truth."""
        from app.core.context_assembly import assemble_checker_context

        ctx = assemble_checker_context(db, populated_world["novel"].id, chapter_text="云澈感到力量涌动")

        yunche_attrs = _find_entity_attrs(ctx, "云澈")
        mystery = _find_attr(yunche_attrs, "神秘力量")
        assert mystery is not None
        assert mystery["truth"] == "邪神遗脉"

    def test_hidden_relationship_visible(self, db, populated_world):
        """Consistency checker sees hidden relationships."""
        from app.core.context_assembly import assemble_checker_context

        ctx = assemble_checker_context(db, populated_world["novel"].id, chapter_text="云澈来到苍风帝国")

        rel_types = [r["label"] for r in ctx.get("relationships", [])]
        assert "暗中对抗" in rel_types

    def test_checker_is_read_only(self, db, populated_world):
        """Consistency checker context is read-only — no writes to world model."""
        from app.core.context_assembly import assemble_checker_context
        from app.models import WorldEntity

        before_count = db.query(WorldEntity).filter_by(novel_id=populated_world["novel"].id).count()

        assemble_checker_context(db, populated_world["novel"].id, chapter_text="任意文本")

        after_count = db.query(WorldEntity).filter_by(novel_id=populated_world["novel"].id).count()
        assert before_count == after_count


# ===========================================================================
# Helpers
# ===========================================================================

def _find_entity_attrs(ctx, entity_name):
    """Find attributes for a named entity in context output."""
    for e in ctx.get("entities", []):
        if e["name"] == entity_name:
            return e.get("attributes", [])
    return []


def _find_attr(attrs, key):
    """Find a specific attribute by key."""
    for a in attrs:
        if a["key"] == key:
            return a
    return None
