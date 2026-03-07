"""
Tests for World Model database models.

Validates table structure, constraints, cascade behavior, and visibility semantics
per world-model-schema.md spec.
"""

import pytest
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

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


# ---------------------------------------------------------------------------
# WorldEntity
# ---------------------------------------------------------------------------

class TestWorldEntity:
    """WorldEntity table structure and constraints."""

    def test_create_entity(self, db, novel):
        from app.models import WorldEntity

        entity = WorldEntity(
            novel_id=novel.id,
            name="云澈",
            entity_type="Character",
            description="主角，性格坚韧",
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)

        assert entity.id is not None
        assert entity.name == "云澈"
        assert entity.entity_type == "Character"
        assert entity.status == "draft"  # default
        assert entity.aliases == []  # default empty list

    def test_entity_type_is_free_text(self, db, novel):
        """entity_type is a free label, not a fixed enum."""
        from app.models import WorldEntity

        for etype in ["Character", "Location", "机甲", "Starship", "修炼功法"]:
            entity = WorldEntity(
                novel_id=novel.id,
                name=f"test_{etype}",
                entity_type=etype,
            )
            db.add(entity)
        db.commit()

        entities = db.query(WorldEntity).filter_by(novel_id=novel.id).all()
        assert len(entities) == 5

    def test_unique_name_per_novel(self, db, novel):
        """novel_id + name must be unique."""
        from app.models import WorldEntity

        db.add(WorldEntity(novel_id=novel.id, name="云澈", entity_type="Character"))
        db.commit()

        db.add(WorldEntity(novel_id=novel.id, name="云澈", entity_type="Character"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_same_name_different_novel(self, db, novel):
        """Same name allowed in different novels."""
        from app.models import WorldEntity

        novel2 = Novel(title="斗破苍穹", author="天蚕土豆", file_path="/tmp/test2.txt")
        db.add(novel2)
        db.commit()

        db.add(WorldEntity(novel_id=novel.id, name="萧炎", entity_type="Character"))
        db.add(WorldEntity(novel_id=novel2.id, name="萧炎", entity_type="Character"))
        db.commit()  # should not raise

    def test_aliases_json_field(self, db, novel):
        """aliases stores a JSON array of alternative names."""
        from app.models import WorldEntity

        entity = WorldEntity(
            novel_id=novel.id,
            name="云澈",
            entity_type="Character",
            aliases=["小澈", "Yun Che"],
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)

        assert entity.aliases == ["小澈", "Yun Che"]

    def test_status_draft_and_confirmed(self, db, novel):
        """Entity can be draft or confirmed."""
        from app.models import WorldEntity

        draft = WorldEntity(novel_id=novel.id, name="draft_entity", entity_type="Character")
        confirmed = WorldEntity(novel_id=novel.id, name="confirmed_entity", entity_type="Character", status="confirmed")
        db.add_all([draft, confirmed])
        db.commit()

        assert draft.status == "draft"
        assert confirmed.status == "confirmed"


# ---------------------------------------------------------------------------
# WorldEntityAttribute
# ---------------------------------------------------------------------------

class TestWorldEntityAttribute:
    """WorldEntityAttribute table structure, visibility, and foreshadowing."""

    @pytest.fixture
    def entity(self, db, novel):
        from app.models import WorldEntity

        e = WorldEntity(novel_id=novel.id, name="云澈", entity_type="Character", status="confirmed")
        db.add(e)
        db.commit()
        db.refresh(e)
        return e

    def test_create_attribute(self, db, entity):
        from app.models import WorldEntityAttribute

        attr = WorldEntityAttribute(
            entity_id=entity.id,
            key="修为",
            surface="真玄境",
        )
        db.add(attr)
        db.commit()
        db.refresh(attr)

        assert attr.visibility == "active"  # default
        assert attr.truth is None  # default
        assert attr.sort_order == 0  # default

    def test_unique_key_per_entity(self, db, entity):
        """entity_id + key must be unique."""
        from app.models import WorldEntityAttribute

        db.add(WorldEntityAttribute(entity_id=entity.id, key="修为", surface="真玄境"))
        db.commit()

        db.add(WorldEntityAttribute(entity_id=entity.id, key="修为", surface="天玄境"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_three_visibility_levels(self, db, entity):
        """All three visibility levels are valid."""
        from app.models import WorldEntityAttribute

        for i, vis in enumerate(["active", "reference", "hidden"]):
            db.add(WorldEntityAttribute(
                entity_id=entity.id,
                key=f"attr_{vis}",
                surface=f"surface_{vis}",
                visibility=vis,
            ))
        db.commit()

        attrs = db.query(WorldEntityAttribute).filter_by(entity_id=entity.id).all()
        assert len(attrs) == 3

    def test_dual_field_foreshadowing(self, db, entity):
        """Attribute with truth (foreshadowing): surface is the writer's script, truth is the real answer."""
        from app.models import WorldEntityAttribute

        attr = WorldEntityAttribute(
            entity_id=entity.id,
            key="神秘力量",
            surface="偶尔在危机时爆发，伴随银色光芒",
            truth="邪神遗脉",
            visibility="active",
        )
        db.add(attr)
        db.commit()
        db.refresh(attr)

        assert attr.surface == "偶尔在危机时爆发，伴随银色光芒"
        assert attr.truth == "邪神遗脉"
        assert attr.visibility == "active"

    def test_hidden_attribute_with_truth(self, db, entity):
        """Hidden attribute: author knows the answer, writer must not see."""
        from app.models import WorldEntityAttribute

        attr = WorldEntityAttribute(
            entity_id=entity.id,
            key="真实身份",
            surface="管家",
            truth="凶手",
            visibility="hidden",
        )
        db.add(attr)
        db.commit()

        assert attr.visibility == "hidden"
        assert attr.truth == "凶手"

    def test_cascade_delete_with_entity(self, db, novel):
        """Deleting entity cascades to its attributes."""
        from app.models import WorldEntity, WorldEntityAttribute

        entity = WorldEntity(novel_id=novel.id, name="临时角色", entity_type="Character", status="confirmed")
        db.add(entity)
        db.commit()

        db.add(WorldEntityAttribute(entity_id=entity.id, key="武器", surface="剑"))
        db.add(WorldEntityAttribute(entity_id=entity.id, key="阵营", surface="正派"))
        db.commit()

        assert db.query(WorldEntityAttribute).filter_by(entity_id=entity.id).count() == 2

        db.delete(entity)
        db.commit()

        assert db.query(WorldEntityAttribute).filter_by(entity_id=entity.id).count() == 0

    def test_filter_by_visibility(self, db, entity):
        """Can filter attributes by visibility at SQL level."""
        from app.models import WorldEntityAttribute

        db.add(WorldEntityAttribute(entity_id=entity.id, key="修为", surface="真玄境", visibility="active"))
        db.add(WorldEntityAttribute(entity_id=entity.id, key="血脉", surface="神秘", visibility="reference"))
        db.add(WorldEntityAttribute(entity_id=entity.id, key="真实身份", surface="表面", truth="真相", visibility="hidden"))
        db.commit()

        # Writer should see active + reference, not hidden
        writer_attrs = db.query(WorldEntityAttribute).filter(
            WorldEntityAttribute.entity_id == entity.id,
            WorldEntityAttribute.visibility.in_(["active", "reference"]),
        ).all()
        assert len(writer_attrs) == 2
        assert all(a.key != "真实身份" for a in writer_attrs)

        # Consistency checker sees all
        all_attrs = db.query(WorldEntityAttribute).filter_by(entity_id=entity.id).all()
        assert len(all_attrs) == 3


# ---------------------------------------------------------------------------
# WorldRelationship
# ---------------------------------------------------------------------------

class TestWorldRelationship:
    """WorldRelationship table structure and constraints."""

    @pytest.fixture
    def entities(self, db, novel):
        from app.models import WorldEntity

        e1 = WorldEntity(novel_id=novel.id, name="云澈", entity_type="Character", status="confirmed")
        e2 = WorldEntity(novel_id=novel.id, name="楚月仙", entity_type="Character", status="confirmed")
        e3 = WorldEntity(novel_id=novel.id, name="苍风帝国", entity_type="Faction", status="confirmed")
        db.add_all([e1, e2, e3])
        db.commit()
        db.refresh(e1)
        db.refresh(e2)
        db.refresh(e3)
        return e1, e2, e3

    def test_create_relationship(self, db, novel, entities):
        from app.models import WorldRelationship

        e1, e2, _ = entities
        rel = WorldRelationship(
            novel_id=novel.id,
            source_id=e1.id,
            target_id=e2.id,
            label="师徒",
            description="楚月仙是云澈的师父",
        )
        db.add(rel)
        db.commit()
        db.refresh(rel)

        assert rel.label == "师徒"
        assert rel.status == "draft"  # default
        assert rel.visibility == "active"  # default

    def test_relationship_has_visibility(self, db, novel, entities):
        """Relationships support the same 3-level visibility."""
        from app.models import WorldRelationship

        e1, e2, _ = entities
        rel = WorldRelationship(
            novel_id=novel.id,
            source_id=e1.id,
            target_id=e2.id,
            label="暗恋",
            visibility="hidden",
        )
        db.add(rel)
        db.commit()

        assert rel.visibility == "hidden"

    def test_cascade_delete_entity_removes_relationships(self, db, novel, entities):
        """Deleting an entity removes relationships where it is source or target."""
        from app.models import WorldRelationship

        e1, e2, e3 = entities
        db.add(WorldRelationship(novel_id=novel.id, source_id=e1.id, target_id=e2.id, label="师徒"))
        db.add(WorldRelationship(novel_id=novel.id, source_id=e3.id, target_id=e1.id, label="所属"))
        db.commit()

        assert db.query(WorldRelationship).filter_by(novel_id=novel.id).count() == 2

        db.delete(e1)
        db.commit()

        assert db.query(WorldRelationship).filter_by(novel_id=novel.id).count() == 0


# ---------------------------------------------------------------------------
# WorldSystem
# ---------------------------------------------------------------------------

class TestWorldSystem:
    """WorldSystem table structure and JSON data."""

    def test_create_hierarchy_system(self, db, novel):
        from app.models import WorldSystem

        system = WorldSystem(
            novel_id=novel.id,
            name="修炼体系",
            display_type="hierarchy",
            description="玄气修炼等级体系",
            data={"nodes": [{"id": "xuandi", "label": "玄帝境", "entity_id": None, "children": []}]},
            constraints=["突破需要天材地宝", "每个境界分十层"],
        )
        db.add(system)
        db.commit()
        db.refresh(system)

        assert system.display_type == "hierarchy"
        assert system.data["nodes"][0]["label"] == "玄帝境"
        assert len(system.constraints) == 2
        assert system.status == "draft"  # default

    def test_create_graph_system(self, db, novel):
        from app.models import WorldSystem

        system = WorldSystem(
            novel_id=novel.id,
            name="势力格局",
            display_type="graph",
            data={
                "nodes": [{"id": "cf", "label": "苍风帝国", "entity_id": None, "position": {"x": 100, "y": 200}}],
                "edges": [{"from": "cf", "to": "lf", "label": "附属"}],
            },
        )
        db.add(system)
        db.commit()

        assert system.display_type == "graph"

    def test_create_timeline_system(self, db, novel):
        from app.models import WorldSystem

        system = WorldSystem(
            novel_id=novel.id,
            name="历史大事件",
            display_type="timeline",
            data={"events": [{"time": "千年前", "label": "魔法消失"}]},
        )
        db.add(system)
        db.commit()

        assert system.display_type == "timeline"

    def test_create_list_system(self, db, novel):
        from app.models import WorldSystem

        system = WorldSystem(
            novel_id=novel.id,
            name="世界法则",
            display_type="list",
            data={"items": [{"label": "玄力不能在极寒之地使用"}]},
        )
        db.add(system)
        db.commit()

        assert system.display_type == "list"

    def test_unique_name_per_novel(self, db, novel):
        from app.models import WorldSystem

        db.add(WorldSystem(novel_id=novel.id, name="修炼体系", display_type="hierarchy"))
        db.commit()

        db.add(WorldSystem(novel_id=novel.id, name="修炼体系", display_type="list"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_system_has_visibility(self, db, novel):
        from app.models import WorldSystem

        system = WorldSystem(
            novel_id=novel.id,
            name="隐藏体系",
            display_type="list",
            visibility="hidden",
        )
        db.add(system)
        db.commit()

        assert system.visibility == "hidden"


# ---------------------------------------------------------------------------
# Exploration & ExplorationChapter
# ---------------------------------------------------------------------------

class TestExploration:
    """Exploration save/restore chapter sequences."""

    def test_create_exploration(self, db, novel):
        from app.models import Exploration

        exp = Exploration(
            novel_id=novel.id,
            name="尝试线路A",
            description="云澈走暗黑路线",
            from_chapter=201,
            to_chapter=210,
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)

        assert exp.from_chapter == 201
        assert exp.to_chapter == 210

    def test_unique_name_per_novel(self, db, novel):
        from app.models import Exploration

        db.add(Exploration(novel_id=novel.id, name="线路A", from_chapter=1, to_chapter=5))
        db.commit()

        db.add(Exploration(novel_id=novel.id, name="线路A", from_chapter=6, to_chapter=10))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_exploration_chapters(self, db, novel):
        from app.models import Exploration, ExplorationChapter

        exp = Exploration(novel_id=novel.id, name="线路B", from_chapter=201, to_chapter=203)
        db.add(exp)
        db.commit()

        for i, ch_num in enumerate([201, 202, 203]):
            db.add(ExplorationChapter(
                exploration_id=exp.id,
                chapter_number=ch_num,
                title=f"第{ch_num}章",
                content=f"章节{ch_num}的内容",
                sort_order=i,
            ))
        db.commit()

        chapters = db.query(ExplorationChapter).filter_by(exploration_id=exp.id).order_by(ExplorationChapter.sort_order).all()
        assert len(chapters) == 3
        assert chapters[0].chapter_number == 201
        assert chapters[2].chapter_number == 203

    def test_cascade_delete_exploration(self, db, novel):
        """Deleting exploration cascades to its chapters."""
        from app.models import Exploration, ExplorationChapter

        exp = Exploration(novel_id=novel.id, name="临时线路", from_chapter=1, to_chapter=2)
        db.add(exp)
        db.commit()

        db.add(ExplorationChapter(exploration_id=exp.id, chapter_number=1, content="内容", sort_order=0))
        db.commit()

        db.delete(exp)
        db.commit()

        assert db.query(ExplorationChapter).count() == 0


# ---------------------------------------------------------------------------
# Bootstrap: draft → confirmed flow
# ---------------------------------------------------------------------------

class TestBootstrapFlow:
    """Bootstrap one-time draft → confirmed workflow."""

    def test_draft_entities_not_in_confirmed_query(self, db, novel):
        """Only confirmed entities should appear in generation context queries."""
        from app.models import WorldEntity

        db.add(WorldEntity(novel_id=novel.id, name="draft角色", entity_type="Character", status="draft"))
        db.add(WorldEntity(novel_id=novel.id, name="confirmed角色", entity_type="Character", status="confirmed"))
        db.commit()

        confirmed = db.query(WorldEntity).filter_by(novel_id=novel.id, status="confirmed").all()
        assert len(confirmed) == 1
        assert confirmed[0].name == "confirmed角色"

    def test_batch_confirm_entities(self, db, novel):
        """Batch confirm: update multiple draft entities to confirmed."""
        from app.models import WorldEntity

        for i in range(5):
            db.add(WorldEntity(novel_id=novel.id, name=f"entity_{i}", entity_type="Character", status="draft"))
        db.commit()

        # Batch confirm
        db.query(WorldEntity).filter_by(novel_id=novel.id, status="draft").update({"status": "confirmed"})
        db.commit()

        drafts = db.query(WorldEntity).filter_by(novel_id=novel.id, status="draft").count()
        confirmed = db.query(WorldEntity).filter_by(novel_id=novel.id, status="confirmed").count()
        assert drafts == 0
        assert confirmed == 5

    def test_draft_relationships_not_in_confirmed_query(self, db, novel):
        from app.models import WorldEntity, WorldRelationship

        e1 = WorldEntity(novel_id=novel.id, name="A", entity_type="Character", status="confirmed")
        e2 = WorldEntity(novel_id=novel.id, name="B", entity_type="Character", status="confirmed")
        db.add_all([e1, e2])
        db.commit()

        db.add(WorldRelationship(novel_id=novel.id, source_id=e1.id, target_id=e2.id, label="师徒", status="draft"))
        db.add(WorldRelationship(novel_id=novel.id, source_id=e2.id, target_id=e1.id, label="仇敌", status="confirmed"))
        db.commit()

        confirmed_rels = db.query(WorldRelationship).filter_by(novel_id=novel.id, status="confirmed").all()
        assert len(confirmed_rels) == 1
        assert confirmed_rels[0].label == "仇敌"

    def test_draft_systems_not_in_confirmed_query(self, db, novel):
        from app.models import WorldSystem

        db.add(WorldSystem(novel_id=novel.id, name="draft体系", display_type="list", status="draft"))
        db.add(WorldSystem(novel_id=novel.id, name="confirmed体系", display_type="list", status="confirmed"))
        db.commit()

        confirmed = db.query(WorldSystem).filter_by(novel_id=novel.id, status="confirmed").all()
        assert len(confirmed) == 1
        assert confirmed[0].name == "confirmed体系"
