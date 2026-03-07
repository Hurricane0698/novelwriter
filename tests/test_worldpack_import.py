"""Tests for worldpack.v1 import endpoint semantics."""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Novel, User, WorldEntity, WorldEntityAttribute, WorldRelationship, WorldSystem


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
    n = Novel(title="Worldpack Import", author="Tester", file_path="/tmp/test.txt", total_chapters=0)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture
def client(db):
    from app.api import world

    test_app = FastAPI()
    test_app.include_router(world.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db

    from app.core.auth import get_current_user

    test_app.dependency_overrides[get_current_user] = lambda: User(
        id=1, username="t", hashed_password="x", role="admin", is_active=True
    )

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


def _base_payload(*, pack_id: str, entities=None, relationships=None, systems=None):
    return {
        "schema_version": "worldpack.v1",
        "pack_id": pack_id,
        "pack_name": "Test Pack",
        "language": "zh",
        "license": "CC-BY",
        "source": {"wiki_base_url": "https://example.com/wiki"},
        "generated_at": datetime(2026, 2, 22, tzinfo=timezone.utc).isoformat(),
        "entities": entities or [],
        "relationships": relationships or [],
        "systems": systems or [],
    }


def test_schema_version_validation_400(client, novel):
    payload = _base_payload(pack_id="pack-1")
    payload["schema_version"] = "worldpack.v0"
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload)
    assert resp.status_code == 400


def test_relationship_missing_refs_warning(client, novel):
    payload = _base_payload(
        pack_id="pack-1",
        entities=[
            {"key": "a", "name": "甲", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
        ],
        relationships=[
            {"source_key": "a", "target_key": "missing", "label": "认识", "description": ""},
        ],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    codes = {w["code"] for w in data["warnings"]}
    assert "missing_relationship_refs" in codes
    assert data["counts"]["relationships_created"] == 0


def test_defaults_status_visibility(client, novel, db):
    payload = _base_payload(
        pack_id="pack-1",
        entities=[
            {
                "key": "e1",
                "name": "云澈",
                "entity_type": "Character",
                "description": "主角",
                "aliases": ["小澈"],
                "attributes": [{"key": "修为", "surface": "真玄境"}],
            },
            {"key": "e2", "name": "苍风帝国", "entity_type": "Faction", "description": "", "aliases": [], "attributes": []},
        ],
        relationships=[{"source_key": "e1", "target_key": "e2", "label": "来自", "description": ""}],
        systems=[
            {"name": "修炼体系", "display_type": "list", "description": "等级划分", "data": {"items": []}, "constraints": []}
        ],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload)
    assert resp.status_code == 200

    entity = (
        db.query(WorldEntity)
        .filter(WorldEntity.novel_id == novel.id, WorldEntity.worldpack_pack_id == "pack-1", WorldEntity.worldpack_key == "e1")
        .first()
    )
    assert entity is not None
    assert entity.origin == "worldpack"
    assert entity.status == "confirmed"

    attr = db.query(WorldEntityAttribute).filter(WorldEntityAttribute.entity_id == entity.id, WorldEntityAttribute.key == "修为").first()
    assert attr is not None
    assert attr.origin == "worldpack"
    assert attr.visibility == "reference"

    rel = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id, WorldRelationship.worldpack_pack_id == "pack-1").first()
    assert rel is not None
    assert rel.origin == "worldpack"
    assert rel.status == "confirmed"
    assert rel.visibility == "reference"

    system = db.query(WorldSystem).filter(WorldSystem.novel_id == novel.id, WorldSystem.name == "修炼体系").first()
    assert system is not None
    assert system.origin == "worldpack"
    assert system.status == "confirmed"
    assert system.visibility == "reference"


def test_idempotency_second_import_no_changes(client, novel):
    payload = _base_payload(
        pack_id="pack-1",
        entities=[
            {"key": "e1", "name": "云澈", "entity_type": "Character", "description": "主角", "aliases": [], "attributes": []},
            {"key": "e2", "name": "千叶影儿", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
        ],
        relationships=[{"source_key": "e1", "target_key": "e2", "label": "同伴", "description": ""}],
        systems=[{"name": "规则", "display_type": "list", "description": "", "data": {}, "constraints": []}],
    )
    first = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload)
    assert first.status_code == 200
    second = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload)
    assert second.status_code == 200
    counts = second.json()["counts"]
    assert all(v == 0 for v in counts.values())


def test_relationship_label_canonical_dedup(client, novel, db):
    payload_v1 = _base_payload(
        pack_id="pack-1",
        entities=[
            {"key": "e1", "name": "云澈", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
            {"key": "e2", "name": "千叶影儿", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
        ],
        relationships=[{"source_key": "e1", "target_key": "e2", "label": "伴侣", "description": ""}],
    )
    payload_v2 = _base_payload(
        pack_id="pack-1",
        entities=payload_v1["entities"],
        relationships=[{"source_key": "e1", "target_key": "e2", "label": "伴侣关系", "description": "detail"}],
    )

    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v1)
    assert resp.status_code == 200
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v2)
    assert resp.status_code == 200
    counts = resp.json()["counts"]
    assert counts["relationships_created"] == 0
    assert counts["relationships_updated"] == 1

    rels = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id).all()
    assert len(rels) == 1
    assert rels[0].label == "伴侣关系"
    assert rels[0].description == "detail"


def test_manual_preserved_overwrite_boundary(client, novel, db):
    manual = WorldEntity(
        novel_id=novel.id,
        name="云澈",
        entity_type="Character",
        description="manual desc",
        aliases=[],
        origin="manual",
        status="confirmed",
        worldpack_pack_id="pack-1",
        worldpack_key="e1",
    )
    db.add(manual)
    db.commit()

    payload = _base_payload(
        pack_id="pack-1",
        entities=[
            {"key": "e1", "name": "云澈", "entity_type": "Character", "description": "pack desc", "aliases": [], "attributes": []},
        ],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload)
    assert resp.status_code == 200
    db.refresh(manual)
    assert manual.description == "manual desc"


def test_promotion_entity_prevents_overwrite(client, novel, db):
    payload_v1 = _base_payload(
        pack_id="pack-1",
        entities=[
            {"key": "e1", "name": "云澈", "entity_type": "Character", "description": "pack v1", "aliases": [], "attributes": []},
        ],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v1)
    assert resp.status_code == 200

    entity = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id, WorldEntity.worldpack_pack_id == "pack-1", WorldEntity.worldpack_key == "e1").first()
    assert entity is not None
    assert entity.origin == "worldpack"

    # Editing an origin=worldpack row promotes it to manual.
    edit = client.put(
        f"/api/novels/{novel.id}/world/entities/{entity.id}",
        json={"description": "user edit"},
    )
    assert edit.status_code == 200
    db.refresh(entity)
    assert entity.origin == "manual"

    payload_v2 = _base_payload(
        pack_id="pack-1",
        entities=[
            {"key": "e1", "name": "云澈", "entity_type": "Character", "description": "pack v2", "aliases": [], "attributes": []},
        ],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v2)
    assert resp.status_code == 200
    db.refresh(entity)
    assert entity.description == "user edit"


def test_promotion_attribute_prevents_overwrite(client, novel, db):
    payload_v1 = _base_payload(
        pack_id="pack-1",
        entities=[
            {
                "key": "e1",
                "name": "云澈",
                "entity_type": "Character",
                "description": "",
                "aliases": [],
                "attributes": [{"key": "修为", "surface": "真玄境"}],
            },
        ],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v1)
    assert resp.status_code == 200

    entity = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id, WorldEntity.worldpack_key == "e1").first()
    attr = db.query(WorldEntityAttribute).filter(WorldEntityAttribute.entity_id == entity.id, WorldEntityAttribute.key == "修为").first()
    assert attr.origin == "worldpack"

    edit = client.put(
        f"/api/novels/{novel.id}/world/entities/{entity.id}/attributes/{attr.id}",
        json={"surface": "用户修改"},
    )
    assert edit.status_code == 200
    db.refresh(attr)
    assert attr.origin == "manual"

    payload_v2 = _base_payload(
        pack_id="pack-1",
        entities=[
            {
                "key": "e1",
                "name": "云澈",
                "entity_type": "Character",
                "description": "",
                "aliases": [],
                "attributes": [{"key": "修为", "surface": "神元境"}],
            },
        ],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v2)
    assert resp.status_code == 200
    db.refresh(attr)
    assert attr.surface == "用户修改"


def test_promotion_relationship_prevents_overwrite(client, novel, db):
    payload_v1 = _base_payload(
        pack_id="pack-1",
        entities=[
            {"key": "e1", "name": "云澈", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
            {"key": "e2", "name": "千叶影儿", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
        ],
        relationships=[{"source_key": "e1", "target_key": "e2", "label": "同伴", "description": "pack v1"}],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v1)
    assert resp.status_code == 200

    rel = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id, WorldRelationship.worldpack_pack_id == "pack-1").first()
    assert rel is not None
    assert rel.origin == "worldpack"

    edit = client.put(
        f"/api/novels/{novel.id}/world/relationships/{rel.id}",
        json={"description": "user edit"},
    )
    assert edit.status_code == 200
    db.refresh(rel)
    assert rel.origin == "manual"

    payload_v2 = _base_payload(
        pack_id="pack-1",
        entities=payload_v1["entities"],
        relationships=[{"source_key": "e1", "target_key": "e2", "label": "同伴", "description": "pack v2"}],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v2)
    assert resp.status_code == 200
    db.refresh(rel)
    assert rel.description == "user edit"


def test_promotion_system_prevents_overwrite(client, novel, db):
    payload_v1 = _base_payload(
        pack_id="pack-1",
        systems=[{"name": "修炼体系", "display_type": "list", "description": "pack v1", "data": {}, "constraints": []}],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v1)
    assert resp.status_code == 200

    system = db.query(WorldSystem).filter(WorldSystem.novel_id == novel.id, WorldSystem.name == "修炼体系").first()
    assert system is not None
    assert system.origin == "worldpack"

    edit = client.put(
        f"/api/novels/{novel.id}/world/systems/{system.id}",
        json={"description": "user edit"},
    )
    assert edit.status_code == 200
    db.refresh(system)
    assert system.origin == "manual"

    payload_v2 = _base_payload(
        pack_id="pack-1",
        systems=[{"name": "修炼体系", "display_type": "list", "description": "pack v2", "data": {}, "constraints": []}],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v2)
    assert resp.status_code == 200
    db.refresh(system)
    assert system.description == "user edit"


def test_deletions_only_for_origin_worldpack(client, novel, db):
    payload_v1 = _base_payload(
        pack_id="pack-1",
        entities=[
            {"key": "e1", "name": "云澈", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
            {"key": "e2", "name": "千叶影儿", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
        ],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v1)
    assert resp.status_code == 200

    e1 = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id, WorldEntity.worldpack_key == "e1").first()
    e2 = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id, WorldEntity.worldpack_key == "e2").first()
    assert e1 is not None and e2 is not None

    # Promote e2 to manual.
    edit = client.put(
        f"/api/novels/{novel.id}/world/entities/{e2.id}",
        json={"description": "user edit"},
    )
    assert edit.status_code == 200
    db.refresh(e2)
    assert e2.origin == "manual"

    # Import an empty pack payload: should delete only remaining origin=worldpack rows.
    empty = _base_payload(pack_id="pack-1", entities=[])
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=empty)
    assert resp.status_code == 200
    assert resp.json()["counts"]["entities_deleted"] == 1

    assert db.query(WorldEntity).filter(WorldEntity.id == e1.id).first() is None
    assert db.query(WorldEntity).filter(WorldEntity.id == e2.id).first() is not None


def test_missing_name_does_not_cause_partial_sync_deletions(client, novel, db):
    payload_v1 = _base_payload(
        pack_id="pack-1",
        entities=[
            {"key": "e1", "name": "云澈", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
            {"key": "e2", "name": "千叶影儿", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
        ],
        relationships=[{"source_key": "e1", "target_key": "e2", "label": "同伴", "description": ""}],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v1)
    assert resp.status_code == 200

    rel = (
        db.query(WorldRelationship)
        .filter(WorldRelationship.novel_id == novel.id, WorldRelationship.worldpack_pack_id == "pack-1")
        .first()
    )
    assert rel is not None

    payload_v2 = _base_payload(
        pack_id="pack-1",
        entities=[
            # Invalid entity in payload: missing name. Import should keep existing entity to
            # resolve relationships and avoid deleting existing worldpack rows.
            {"key": "e1", "name": "", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
            {"key": "e2", "name": "千叶影儿", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
        ],
        relationships=[{"source_key": "e1", "target_key": "e2", "label": "同伴", "description": ""}],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload_v2)
    assert resp.status_code == 200
    data = resp.json()

    # Relationship should remain (no partial-sync deletion).
    rel2 = (
        db.query(WorldRelationship)
        .filter(WorldRelationship.novel_id == novel.id, WorldRelationship.worldpack_pack_id == "pack-1")
        .first()
    )
    assert rel2 is not None
    assert data["counts"]["relationships_deleted"] == 0

    codes = {w["code"] for w in data["warnings"]}
    assert "missing_name_preserve_existing" in codes


def test_worldpack_identity_requires_pack_id_and_key_pair(db, novel):
    bad = WorldEntity(
        novel_id=novel.id,
        name="坏实体",
        entity_type="Character",
        description="",
        aliases=[],
        origin="worldpack",
        status="confirmed",
        worldpack_pack_id="pack-1",
        worldpack_key=None,
    )
    db.add(bad)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_visibility_active_from_payload(client, novel, db):
    """Import with visibility='active' on system and attribute; verify DB fields."""
    payload = _base_payload(
        pack_id="pack-vis-active",
        entities=[
            {
                "key": "e1",
                "name": "云澈",
                "entity_type": "Character",
                "description": "",
                "aliases": [],
                "attributes": [{"key": "修为", "surface": "真玄境", "visibility": "active"}],
            },
        ],
        systems=[
            {"name": "称谓", "display_type": "list", "description": "", "data": {}, "constraints": [], "visibility": "active"},
        ],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload)
    assert resp.status_code == 200

    entity = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id, WorldEntity.worldpack_key == "e1").first()
    attr = db.query(WorldEntityAttribute).filter(WorldEntityAttribute.entity_id == entity.id, WorldEntityAttribute.key == "修为").first()
    assert attr.visibility == "active"

    system = db.query(WorldSystem).filter(WorldSystem.novel_id == novel.id, WorldSystem.name == "称谓").first()
    assert system.visibility == "active"


def test_visibility_hidden_from_payload(client, novel, db):
    """Import with visibility='hidden' on relationship; verify DB field."""
    payload = _base_payload(
        pack_id="pack-vis-hidden",
        entities=[
            {"key": "e1", "name": "甲", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
            {"key": "e2", "name": "乙", "entity_type": "Character", "description": "", "aliases": [], "attributes": []},
        ],
        relationships=[
            {"source_key": "e1", "target_key": "e2", "label": "认识", "description": "", "visibility": "hidden"},
        ],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload)
    assert resp.status_code == 200

    rel = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id, WorldRelationship.worldpack_pack_id == "pack-vis-hidden").first()
    assert rel.visibility == "hidden"


def test_visibility_invalid_rejected_with_location_422(client, novel):
    """Import with invalid visibility; verify 422 error reports the field location(s)."""
    payload = _base_payload(
        pack_id="pack-vis-bogus",
        entities=[
            {
                "key": "e1",
                "name": "云澈",
                "entity_type": "Character",
                "description": "",
                "aliases": [],
                "attributes": [{"key": "修为", "surface": "真玄境", "visibility": "bogus"}],
            },
        ],
        systems=[
            {"name": "体系", "display_type": "list", "description": "", "data": {}, "constraints": [], "visibility": "bogus"},
        ],
    )
    resp = client.post(f"/api/novels/{novel.id}/world/worldpack/import", json=payload)
    assert resp.status_code == 422

    data = resp.json()
    locs = [err.get("loc") for err in data.get("detail", [])]
    assert ["body", "entities", 0, "attributes", 0, "visibility"] in locs
    assert ["body", "systems", 0, "visibility"] in locs
