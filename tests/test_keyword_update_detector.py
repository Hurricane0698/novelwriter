"""
Tests for KeywordUpdateDetector.

Validates that the detector scans chapter text for entity mentions
and flags suspected world model changes, per world-model-schema.md spec.

This is the free tier detector — no LLM calls, pure keyword matching.
"""

import pytest
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Novel

pytestmark = pytest.mark.contract


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
def world_with_entities(db, novel):
    """World model with confirmed entities and attributes."""
    from app.models import (
        WorldEntity, WorldEntityAttribute, WorldRelationship,
    )

    yunche = WorldEntity(
        novel_id=novel.id, name="云澈", entity_type="Character",
        status="confirmed", aliases=["小澈"],
    )
    chuyuexian = WorldEntity(
        novel_id=novel.id, name="楚月仙", entity_type="Character",
        status="confirmed",
    )
    cangfeng = WorldEntity(
        novel_id=novel.id, name="苍风帝国", entity_type="Faction",
        status="confirmed",
    )
    db.add_all([yunche, chuyuexian, cangfeng])
    db.commit()

    db.add(WorldEntityAttribute(entity_id=yunche.id, key="修为", surface="真玄境", visibility="active"))
    db.add(WorldEntityAttribute(entity_id=yunche.id, key="阵营", surface="苍风帝国", visibility="active"))
    db.add(WorldRelationship(
        novel_id=novel.id, source_id=yunche.id, target_id=chuyuexian.id,
        label="师徒", status="confirmed", visibility="active",
    ))
    db.commit()

    return {"novel": novel, "yunche": yunche, "chuyuexian": chuyuexian, "cangfeng": cangfeng}


# ===========================================================================
# Detection
# ===========================================================================

class TestKeywordUpdateDetector:

    def test_detect_attribute_change(self, db, world_with_entities):
        """Chapter mentions entity + change signal → propose attribute update."""
        from app.core.update_detector import KeywordUpdateDetector

        detector = KeywordUpdateDetector(db, world_with_entities["novel"].id)
        proposal = detector.detect("云澈终于突破到了天玄境，体内玄力暴涨。")

        assert len(proposal.entity_attribute_updates) > 0
        update = proposal.entity_attribute_updates[0]
        assert update["entity_name"] == "云澈"

    def test_no_detection_when_no_entity_mentioned(self, db, world_with_entities):
        """Chapter without any entity names → empty proposal."""
        from app.core.update_detector import KeywordUpdateDetector

        detector = KeywordUpdateDetector(db, world_with_entities["novel"].id)
        proposal = detector.detect("天空中飘着白云，微风拂过草地。")

        assert len(proposal.entity_attribute_updates) == 0
        assert len(proposal.relationship_updates) == 0

    def test_detect_via_alias(self, db, world_with_entities):
        """Entity mentioned by alias should also be detected."""
        from app.core.update_detector import KeywordUpdateDetector

        detector = KeywordUpdateDetector(db, world_with_entities["novel"].id)
        proposal = detector.detect("小澈突破到了天玄境。")

        assert len(proposal.entity_attribute_updates) > 0
        assert proposal.entity_attribute_updates[0]["entity_name"] == "云澈"

    def test_no_change_signal_no_proposal(self, db, world_with_entities):
        """Entity mentioned but no change signal → no proposal."""
        from app.core.update_detector import KeywordUpdateDetector

        detector = KeywordUpdateDetector(db, world_with_entities["novel"].id)
        proposal = detector.detect("云澈走在街上，看着来来往往的行人。")

        assert len(proposal.entity_attribute_updates) == 0

    def test_various_change_signals(self, db, world_with_entities):
        """Different Chinese change signal patterns should all be detected."""
        from app.core.update_detector import KeywordUpdateDetector

        detector = KeywordUpdateDetector(db, world_with_entities["novel"].id)

        change_sentences = [
            "云澈成为了天玄境强者。",
            "云澈变成了一个冷酷的人。",
            "云澈加入了焚天宗。",
            "云澈不再是苍风帝国的人了。",
            "云澈晋升为长老。",
        ]
        for sentence in change_sentences:
            proposal = detector.detect(sentence)
            assert len(proposal.entity_attribute_updates) > 0, \
                f"Failed to detect change in: {sentence}"

    def test_multiple_entities_detected(self, db, world_with_entities):
        """Multiple entities with changes in same chapter."""
        from app.core.update_detector import KeywordUpdateDetector

        detector = KeywordUpdateDetector(db, world_with_entities["novel"].id)
        proposal = detector.detect(
            "云澈突破到了天玄境。楚月仙也晋升为半步御座。"
        )

        entity_names = [u["entity_name"] for u in proposal.entity_attribute_updates]
        assert "云澈" in entity_names
        assert "楚月仙" in entity_names

    def test_detector_never_writes_to_db(self, db, world_with_entities):
        """Detector is read-only — never modifies world model."""
        from app.core.update_detector import KeywordUpdateDetector
        from app.models import WorldEntityAttribute

        before = db.query(WorldEntityAttribute).filter_by(
            entity_id=world_with_entities["yunche"].id, key="修为"
        ).first().surface

        detector = KeywordUpdateDetector(db, world_with_entities["novel"].id)
        detector.detect("云澈突破到了天玄境。")

        after = db.query(WorldEntityAttribute).filter_by(
            entity_id=world_with_entities["yunche"].id, key="修为"
        ).first().surface

        assert before == after == "真玄境"  # unchanged


# ===========================================================================
# WorldUpdateProposal structure
# ===========================================================================

class TestWorldUpdateProposal:

    def test_proposal_structure(self):
        """WorldUpdateProposal has the expected fields per spec."""
        from app.core.update_detector import WorldUpdateProposal

        proposal = WorldUpdateProposal(
            entity_attribute_updates=[{"entity_name": "云澈", "key": "修为", "old_value": "真玄境", "new_value": "天玄境"}],
            relationship_updates=[{"source_name": "云澈", "target_name": "萧战", "old_label": "仇敌", "new_label": "盟友"}],
            new_entities=[{"name": "焚天宗", "type": "Faction", "attributes": []}],
            new_relationships=[{"source_name": "云澈", "target_name": "焚天宗", "label": "加入"}],
        )

        assert len(proposal.entity_attribute_updates) == 1
        assert proposal.entity_attribute_updates[0]["new_value"] == "天玄境"
        assert proposal.relationship_updates[0]["new_label"] == "盟友"
        assert proposal.new_relationships[0]["label"] == "加入"

    def test_empty_proposal(self):
        """Empty proposal when no changes detected."""
        from app.core.update_detector import WorldUpdateProposal

        proposal = WorldUpdateProposal()

        assert len(proposal.entity_attribute_updates) == 0
        assert len(proposal.relationship_updates) == 0
        assert len(proposal.new_entities) == 0
        assert len(proposal.new_relationships) == 0


# ===========================================================================
# Protocol compliance
# ===========================================================================

class TestUpdateDetectorProtocol:

    def test_keyword_detector_implements_protocol(self):
        """KeywordUpdateDetector conforms to UpdateDetector protocol."""
        from app.core.update_detector import KeywordUpdateDetector, UpdateDetector  # noqa: F401

        assert hasattr(KeywordUpdateDetector, "detect")
        # If Protocol is runtime-checkable, verify isinstance
        # Otherwise just check method signature exists
