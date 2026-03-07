"""
Tests for World Model API endpoints.

Validates CRUD operations, bootstrap confirm flow, and error handling
per world-model-schema.md API spec.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import BootstrapJob, Novel



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
    from app.models import User
    test_app.dependency_overrides[get_current_user] = lambda: User(
        id=1, username="t", hashed_password="x", role="admin", is_active=True
    )

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


# ===========================================================================
# Entity CRUD
# ===========================================================================

class TestEntityAPI:

    def test_create_entity(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "云澈",
            "entity_type": "Character",
            "description": "主角",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "云澈"
        assert data["entity_type"] == "Character"
        assert data["status"] == "draft"
        assert data["origin"] == "manual"
        assert data["worldpack_pack_id"] is None
        assert data["worldpack_key"] is None

    def test_create_entity_custom_type(self, client, novel):
        """Free-form entity_type: any string is valid."""
        resp = client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "暴风号",
            "entity_type": "Starship",
        })
        assert resp.status_code == 201
        assert resp.json()["entity_type"] == "Starship"

    def test_create_entity_with_aliases(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "云澈",
            "entity_type": "Character",
            "aliases": ["小澈", "Yun Che"],
        })
        assert resp.status_code == 201
        assert resp.json()["aliases"] == ["小澈", "Yun Che"]

    def test_create_entity_duplicate_name_409(self, client, novel):
        client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "云澈", "entity_type": "Character",
        })
        resp = client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "云澈", "entity_type": "Character",
        })
        assert resp.status_code == 409

    def test_list_entities(self, client, novel):
        client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "云澈", "entity_type": "Character"})
        client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "苍风帝国", "entity_type": "Faction"})

        resp = client.get(f"/api/novels/{novel.id}/world/entities")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_entities_filter_by_type(self, client, novel):
        client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "云澈", "entity_type": "Character"})
        client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "苍风帝国", "entity_type": "Faction"})

        resp = client.get(f"/api/novels/{novel.id}/world/entities", params={"entity_type": "Character"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["entity_type"] == "Character"

    def test_list_entities_filter_by_status(self, client, novel):
        client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "draft角色", "entity_type": "Character"})
        # Confirm one via batch confirm
        resp = client.get(f"/api/novels/{novel.id}/world/entities")
        eid = resp.json()[0]["id"]
        client.post(f"/api/novels/{novel.id}/world/entities/confirm", json={"ids": [eid]})

        client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "另一个draft", "entity_type": "Character"})

        resp = client.get(f"/api/novels/{novel.id}/world/entities", params={"status": "confirmed"})
        assert len(resp.json()) == 1

    def test_list_entities_filter_by_q(self, client, novel):
        client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "云澈", "entity_type": "Character"})
        client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "楚月仙", "entity_type": "Character"})

        resp = client.get(f"/api/novels/{novel.id}/world/entities", params={"q": "月"})
        assert resp.status_code == 200
        data = resp.json()
        assert [e["name"] for e in data] == ["楚月仙"]

    def test_get_entity_with_attributes(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "云澈", "entity_type": "Character"})
        eid = resp.json()["id"]

        client.post(f"/api/novels/{novel.id}/world/entities/{eid}/attributes", json={
            "key": "修为", "surface": "真玄境",
        })

        resp = client.get(f"/api/novels/{novel.id}/world/entities/{eid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "云澈"
        assert len(data["attributes"]) == 1
        assert data["attributes"][0]["key"] == "修为"

    def test_update_entity(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "云澈", "entity_type": "Character"})
        eid = resp.json()["id"]

        resp = client.put(f"/api/novels/{novel.id}/world/entities/{eid}", json={
            "description": "更新后的描述",
        })
        assert resp.status_code == 200
        assert resp.json()["description"] == "更新后的描述"

    def test_delete_entity(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "临时", "entity_type": "Character"})
        eid = resp.json()["id"]

        resp = client.delete(f"/api/novels/{novel.id}/world/entities/{eid}")
        assert resp.status_code == 200

        resp = client.get(f"/api/novels/{novel.id}/world/entities/{eid}")
        assert resp.status_code == 404

    def test_batch_confirm_entities(self, client, novel):
        """Bootstrap review: batch confirm multiple draft entities."""
        ids = []
        for name in ["角色A", "角色B", "角色C"]:
            resp = client.post(f"/api/novels/{novel.id}/world/entities", json={"name": name, "entity_type": "Character"})
            ids.append(resp.json()["id"])

        resp = client.post(f"/api/novels/{novel.id}/world/entities/confirm", json={"ids": ids})
        assert resp.status_code == 200
        assert resp.json()["confirmed"] == 3

        # Verify all confirmed
        resp = client.get(f"/api/novels/{novel.id}/world/entities", params={"status": "confirmed"})
        assert len(resp.json()) == 3

    def test_batch_reject_entities_deletes_only_drafts(self, client, novel):
        draft = client.post(
            f"/api/novels/{novel.id}/world/entities",
            json={"name": "draft角色", "entity_type": "Character"},
        ).json()
        confirmed = client.post(
            f"/api/novels/{novel.id}/world/entities",
            json={"name": "confirmed角色", "entity_type": "Character"},
        ).json()
        client.post(f"/api/novels/{novel.id}/world/entities/confirm", json={"ids": [confirmed["id"]]})

        resp = client.post(
            f"/api/novels/{novel.id}/world/entities/reject",
            json={"ids": [draft["id"], confirmed["id"]]},
        )
        assert resp.status_code == 200
        assert resp.json()["rejected"] == 1

        remaining = client.get(f"/api/novels/{novel.id}/world/entities").json()
        assert [e["name"] for e in remaining] == ["confirmed角色"]

    def test_cross_novel_isolation(self, client, db):
        """Entities from novel A must not appear in novel B's list."""
        novel_a = Novel(title="小说A", author="A", file_path="/tmp/a.txt")
        novel_b = Novel(title="小说B", author="B", file_path="/tmp/b.txt")
        db.add_all([novel_a, novel_b])
        db.commit()
        db.refresh(novel_a)
        db.refresh(novel_b)

        client.post(f"/api/novels/{novel_a.id}/world/entities", json={"name": "角色A", "entity_type": "Character"})
        client.post(f"/api/novels/{novel_b.id}/world/entities", json={"name": "角色B", "entity_type": "Character"})

        resp_a = client.get(f"/api/novels/{novel_a.id}/world/entities")
        resp_b = client.get(f"/api/novels/{novel_b.id}/world/entities")

        names_a = [e["name"] for e in resp_a.json()]
        names_b = [e["name"] for e in resp_b.json()]

        assert names_a == ["角色A"]
        assert names_b == ["角色B"]


# ===========================================================================
# Attribute CRUD
# ===========================================================================

class TestAttributeAPI:

    @pytest.fixture
    def entity_id(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "云澈", "entity_type": "Character",
        })
        return resp.json()["id"]

    def test_add_attribute(self, client, novel, entity_id):
        resp = client.post(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes", json={
            "key": "修为",
            "surface": "真玄境",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["key"] == "修为"
        assert data["visibility"] == "active"  # default
        assert data["truth"] is None
        assert data["origin"] == "manual"
        assert data["worldpack_pack_id"] is None

    def test_add_attribute_with_visibility(self, client, novel, entity_id):
        resp = client.post(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes", json={
            "key": "神秘力量",
            "surface": "偶尔爆发",
            "truth": "邪神遗脉",
            "visibility": "active",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["visibility"] == "active"
        assert data["truth"] == "邪神遗脉"

    def test_add_attribute_duplicate_key_409(self, client, novel, entity_id):
        client.post(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes", json={
            "key": "修为", "surface": "真玄境",
        })
        resp = client.post(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes", json={
            "key": "修为", "surface": "天玄境",
        })
        assert resp.status_code == 409

    def test_update_attribute_surface(self, client, novel, entity_id):
        resp = client.post(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes", json={
            "key": "修为", "surface": "真玄境",
        })
        aid = resp.json()["id"]

        resp = client.put(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes/{aid}", json={
            "surface": "天玄境",
        })
        assert resp.status_code == 200
        assert resp.json()["surface"] == "天玄境"

    def test_update_attribute_visibility(self, client, novel, entity_id):
        """Change visibility: e.g. hidden → active when foreshadowing is revealed."""
        resp = client.post(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes", json={
            "key": "血脉", "surface": "神秘", "visibility": "hidden",
        })
        aid = resp.json()["id"]

        resp = client.put(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes/{aid}", json={
            "surface": "邪神之血",
            "visibility": "active",
        })
        assert resp.status_code == 200
        assert resp.json()["visibility"] == "active"
        assert resp.json()["surface"] == "邪神之血"

    def test_update_attribute_truth(self, client, novel, entity_id):
        """User fills in truth for an attribute with foreshadowing."""
        resp = client.post(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes", json={
            "key": "神秘力量", "surface": "偶尔爆发",
        })
        aid = resp.json()["id"]

        resp = client.put(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes/{aid}", json={
            "truth": "邪神遗脉",
        })
        assert resp.status_code == 200
        assert resp.json()["truth"] == "邪神遗脉"
        assert resp.json()["surface"] == "偶尔爆发"  # surface unchanged

    def test_delete_attribute(self, client, novel, entity_id):
        resp = client.post(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes", json={
            "key": "临时属性", "surface": "临时值",
        })
        aid = resp.json()["id"]

        resp = client.delete(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes/{aid}")
        assert resp.status_code == 200

    def test_reorder_attributes(self, client, novel, entity_id):
        aids = []
        for key in ["修为", "阵营", "武器"]:
            resp = client.post(f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes", json={
                "key": key, "surface": f"{key}值",
            })
            aids.append(resp.json()["id"])

        # Reverse order
        resp = client.patch(
            f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes/reorder",
            json={"order": list(reversed(aids))},
        )
        assert resp.status_code == 200


# ===========================================================================
# Relationship CRUD
# ===========================================================================

class TestRelationshipAPI:

    @pytest.fixture
    def two_entities(self, client, novel):
        r1 = client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "云澈", "entity_type": "Character"})
        r2 = client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "楚月仙", "entity_type": "Character"})
        return r1.json()["id"], r2.json()["id"]

    def test_create_relationship(self, client, novel, two_entities):
        e1, e2 = two_entities
        resp = client.post(f"/api/novels/{novel.id}/world/relationships", json={
            "source_id": e1,
            "target_id": e2,
            "label": "师徒",
            "description": "楚月仙是云澈的师父",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["label"] == "师徒"
        assert data["visibility"] == "active"
        assert data["status"] == "draft"
        assert data["origin"] == "manual"
        assert data["worldpack_pack_id"] is None

    def test_create_relationship_with_visibility(self, client, novel, two_entities):
        e1, e2 = two_entities
        resp = client.post(f"/api/novels/{novel.id}/world/relationships", json={
            "source_id": e1,
            "target_id": e2,
            "label": "暗恋",
            "visibility": "hidden",
        })
        assert resp.status_code == 201
        assert resp.json()["visibility"] == "hidden"

    def test_create_relationship_rejects_canonical_duplicate(self, client, novel, two_entities):
        e1, e2 = two_entities
        resp = client.post(f"/api/novels/{novel.id}/world/relationships", json={
            "source_id": e1,
            "target_id": e2,
            "label": "伴侣",
        })
        assert resp.status_code == 201

        resp = client.post(f"/api/novels/{novel.id}/world/relationships", json={
            "source_id": e1,
            "target_id": e2,
            "label": "伴侣关系",
        })
        assert resp.status_code == 409

    def test_list_relationships(self, client, novel, two_entities):
        e1, e2 = two_entities
        client.post(f"/api/novels/{novel.id}/world/relationships", json={
            "source_id": e1, "target_id": e2, "label": "师徒",
        })

        resp = client.get(f"/api/novels/{novel.id}/world/relationships")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_relationships_filter_by_entity_id(self, client, novel):
        e1 = client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "A", "entity_type": "Character"}).json()["id"]
        e2 = client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "B", "entity_type": "Character"}).json()["id"]
        e3 = client.post(f"/api/novels/{novel.id}/world/entities", json={"name": "C", "entity_type": "Character"}).json()["id"]

        r1 = client.post(f"/api/novels/{novel.id}/world/relationships", json={"source_id": e1, "target_id": e2, "label": "r1"}).json()
        r2 = client.post(f"/api/novels/{novel.id}/world/relationships", json={"source_id": e1, "target_id": e3, "label": "r2"}).json()
        client.post(f"/api/novels/{novel.id}/world/relationships", json={"source_id": e2, "target_id": e3, "label": "unrelated"}).json()

        resp = client.get(f"/api/novels/{novel.id}/world/relationships", params={"entity_id": e1})
        assert resp.status_code == 200
        ids = sorted([r["id"] for r in resp.json()])
        assert ids == sorted([r1["id"], r2["id"]])

    def test_list_relationships_filter_by_status(self, client, novel, two_entities):
        e1, e2 = two_entities
        client.post(
            f"/api/novels/{novel.id}/world/relationships",
            json={"source_id": e1, "target_id": e2, "label": "draft"},
        ).json()
        confirmed = client.post(
            f"/api/novels/{novel.id}/world/relationships",
            json={"source_id": e2, "target_id": e1, "label": "confirmed"},
        ).json()
        client.post(f"/api/novels/{novel.id}/world/relationships/confirm", json={"ids": [confirmed["id"]]})

        resp = client.get(f"/api/novels/{novel.id}/world/relationships", params={"status": "confirmed"})
        assert resp.status_code == 200
        data = resp.json()
        assert [r["id"] for r in data] == [confirmed["id"]]

    def test_update_relationship(self, client, novel, two_entities):
        e1, e2 = two_entities
        resp = client.post(f"/api/novels/{novel.id}/world/relationships", json={
            "source_id": e1, "target_id": e2, "label": "仇敌",
        })
        rid = resp.json()["id"]

        resp = client.put(f"/api/novels/{novel.id}/world/relationships/{rid}", json={
            "label": "盟友",
        })
        assert resp.status_code == 200
        assert resp.json()["label"] == "盟友"

    def test_delete_relationship(self, client, novel, two_entities):
        e1, e2 = two_entities
        resp = client.post(f"/api/novels/{novel.id}/world/relationships", json={
            "source_id": e1, "target_id": e2, "label": "师徒",
        })
        rid = resp.json()["id"]

        resp = client.delete(f"/api/novels/{novel.id}/world/relationships/{rid}")
        assert resp.status_code == 200

    def test_batch_confirm_relationships(self, client, novel, two_entities):
        e1, e2 = two_entities
        resp = client.post(f"/api/novels/{novel.id}/world/relationships", json={
            "source_id": e1, "target_id": e2, "label": "师徒",
        })
        rid = resp.json()["id"]

        resp = client.post(f"/api/novels/{novel.id}/world/relationships/confirm", json={"ids": [rid]})
        assert resp.status_code == 200
        assert resp.json()["confirmed"] == 1

    def test_batch_reject_relationships_deletes_only_drafts(self, client, novel, two_entities):
        e1, e2 = two_entities
        draft = client.post(
            f"/api/novels/{novel.id}/world/relationships",
            json={"source_id": e1, "target_id": e2, "label": "draft"},
        ).json()
        confirmed = client.post(
            f"/api/novels/{novel.id}/world/relationships",
            json={"source_id": e2, "target_id": e1, "label": "confirmed"},
        ).json()
        client.post(f"/api/novels/{novel.id}/world/relationships/confirm", json={"ids": [confirmed["id"]]})

        resp = client.post(
            f"/api/novels/{novel.id}/world/relationships/reject",
            json={"ids": [draft["id"], confirmed["id"]]},
        )
        assert resp.status_code == 200
        assert resp.json()["rejected"] == 1

        remaining = client.get(f"/api/novels/{novel.id}/world/relationships").json()
        assert [r["id"] for r in remaining] == [confirmed["id"]]


# ===========================================================================
# Bootstrap Status
# ===========================================================================

class TestBootstrapStatusAPI:

    def test_bootstrap_status_marks_stale_job_failed(self, client, novel, db):
        stale_time = datetime.now(timezone.utc) - timedelta(hours=1)
        job = BootstrapJob(
            novel_id=novel.id,
            mode="reextract",
            status="refining",
            progress={"step": 4, "detail": "refining entities and relationships"},
            result={"entities_found": 0, "relationships_found": 0, "index_refresh_only": False},
            initialized=True,
            created_at=stale_time,
            updated_at=stale_time,
        )
        db.add(job)
        db.commit()

        resp = client.get(f"/api/novels/{novel.id}/world/bootstrap/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["error"]

        db.refresh(job)
        assert job.status == "failed"


# ===========================================================================
# System CRUD
# ===========================================================================

class TestSystemAPI:

    def test_create_system(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/systems", json={
            "name": "修炼体系",
            "display_type": "hierarchy",
            "description": "玄气修炼等级",
            "data": {"nodes": [{"id": "xuandi", "label": "玄帝境", "entity_id": None, "children": []}]},
            "constraints": ["突破需要天材地宝"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["display_type"] == "hierarchy"
        assert data["status"] == "draft"
        assert data["origin"] == "manual"
        assert data["worldpack_pack_id"] is None

    def test_list_systems(self, client, novel):
        client.post(f"/api/novels/{novel.id}/world/systems", json={
            "name": "修炼体系", "display_type": "hierarchy",
        })
        client.post(f"/api/novels/{novel.id}/world/systems", json={
            "name": "势力格局", "display_type": "graph",
        })

        resp = client.get(f"/api/novels/{novel.id}/world/systems")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_systems_filter_by_q_status_and_display_type(self, client, novel):
        draft = client.post(
            f"/api/novels/{novel.id}/world/systems",
            json={"name": "修炼体系", "display_type": "hierarchy"},
        ).json()
        confirmed = client.post(
            f"/api/novels/{novel.id}/world/systems",
            json={"name": "势力格局", "display_type": "graph"},
        ).json()
        client.post(f"/api/novels/{novel.id}/world/systems/confirm", json={"ids": [confirmed["id"]]})

        resp = client.get(f"/api/novels/{novel.id}/world/systems", params={"q": "势力"})
        assert [s["id"] for s in resp.json()] == [confirmed["id"]]

        resp = client.get(f"/api/novels/{novel.id}/world/systems", params={"status": "confirmed"})
        assert [s["id"] for s in resp.json()] == [confirmed["id"]]

        resp = client.get(f"/api/novels/{novel.id}/world/systems", params={"display_type": "hierarchy"})
        assert [s["id"] for s in resp.json()] == [draft["id"]]

    def test_batch_reject_systems_deletes_only_drafts(self, client, novel):
        draft = client.post(
            f"/api/novels/{novel.id}/world/systems",
            json={"name": "draft体系", "display_type": "list"},
        ).json()
        confirmed = client.post(
            f"/api/novels/{novel.id}/world/systems",
            json={"name": "confirmed体系", "display_type": "list"},
        ).json()
        client.post(f"/api/novels/{novel.id}/world/systems/confirm", json={"ids": [confirmed["id"]]})

        resp = client.post(
            f"/api/novels/{novel.id}/world/systems/reject",
            json={"ids": [draft["id"], confirmed["id"]]},
        )
        assert resp.status_code == 200
        assert resp.json()["rejected"] == 1

        remaining = client.get(f"/api/novels/{novel.id}/world/systems").json()
        assert [s["id"] for s in remaining] == [confirmed["id"]]

    def test_get_system_with_data(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/systems", json={
            "name": "修炼体系",
            "display_type": "hierarchy",
            "data": {"nodes": [{"id": "a", "label": "A", "entity_id": None, "children": []}]},
        })
        sid = resp.json()["id"]

        resp = client.get(f"/api/novels/{novel.id}/world/systems/{sid}")
        assert resp.status_code == 200
        assert resp.json()["data"]["nodes"][0]["label"] == "A"

    def test_create_system_rejects_invalid_nested_visibility(self, client, novel):
        resp = client.post(
            f"/api/novels/{novel.id}/world/systems",
            json={
                "name": "时间线",
                "display_type": "timeline",
                "data": {
                    "events": [
                        {"time": "第1章", "label": "开端", "visibility": "bogus"},
                    ]
                },
            },
        )
        assert resp.status_code == 422

    def test_update_system_rejects_invalid_data(self, client, novel):
        resp = client.post(
            f"/api/novels/{novel.id}/world/systems",
            json={"name": "规则", "display_type": "list"},
        )
        sid = resp.json()["id"]

        resp = client.put(
            f"/api/novels/{novel.id}/world/systems/{sid}",
            json={"data": {"items": [{"label": "A", "visibility": "bogus"}]}},
        )
        assert resp.status_code == 422

    def test_update_system_allows_list_item_id(self, client, novel):
        created = client.post(
            f"/api/novels/{novel.id}/world/systems",
            json={
                "name": "称谓",
                "display_type": "list",
                "data": {"items": [{"id": "title_mushen", "label": "母神", "description": "x"}]},
            },
        )
        assert created.status_code == 201
        sid = created.json()["id"]

        resp = client.put(
            f"/api/novels/{novel.id}/world/systems/{sid}",
            json={"data": {"items": [{"id": "title_mushen", "label": "母神", "description": "y"}]}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["items"][0]["id"] == "title_mushen"
        assert data["data"]["items"][0]["description"] == "y"

    def test_update_system(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/systems", json={
            "name": "修炼体系", "display_type": "hierarchy",
        })
        sid = resp.json()["id"]

        resp = client.put(f"/api/novels/{novel.id}/world/systems/{sid}", json={
            "constraints": ["突破需要天材地宝", "每个境界分十层"],
        })
        assert resp.status_code == 200
        assert len(resp.json()["constraints"]) == 2

    def test_update_system_validates_when_display_type_changes(self, client, novel):
        created = client.post(
            f"/api/novels/{novel.id}/world/systems",
            json={
                "name": "体系",
                "display_type": "hierarchy",
                "data": {"nodes": [{"id": "a", "label": "A", "children": []}]},
            },
        ).json()

        # Changing display_type without sending new data must validate existing
        # stored data. hierarchy.data is incompatible with list.display_type.
        resp = client.put(
            f"/api/novels/{novel.id}/world/systems/{created['id']}",
            json={"display_type": "list"},
        )
        assert resp.status_code == 422

    def test_update_system_display_type_change_allows_empty_data(self, client, novel):
        created = client.post(
            f"/api/novels/{novel.id}/world/systems",
            json={
                "name": "空体系",
                "display_type": "list",
                "data": {},
            },
        ).json()

        resp = client.put(
            f"/api/novels/{novel.id}/world/systems/{created['id']}",
            json={"display_type": "graph"},
        )
        assert resp.status_code == 200
        assert resp.json()["display_type"] == "graph"

    def test_update_system_unknown_display_type_returns_422(self, client, novel, db):
        from app.models import WorldSystem

        created = client.post(
            f"/api/novels/{novel.id}/world/systems",
            json={"name": "坏数据", "display_type": "list"},
        ).json()

        # Simulate a legacy/corrupt DB row.
        sys = db.query(WorldSystem).filter(WorldSystem.id == created["id"]).first()
        assert sys is not None
        sys.display_type = "bogus"
        db.commit()

        resp = client.put(
            f"/api/novels/{novel.id}/world/systems/{created['id']}",
            json={"data": {}},
        )
        assert resp.status_code == 422

    def test_list_systems_rejects_invalid_display_type_filter(self, client, novel):
        resp = client.get(
            f"/api/novels/{novel.id}/world/systems",
            params={"display_type": "bogus"},
        )
        assert resp.status_code == 422

    def test_delete_system(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/systems", json={
            "name": "临时体系", "display_type": "list",
        })
        sid = resp.json()["id"]

        resp = client.delete(f"/api/novels/{novel.id}/world/systems/{sid}")
        assert resp.status_code == 200

    def test_duplicate_name_409(self, client, novel):
        client.post(f"/api/novels/{novel.id}/world/systems", json={
            "name": "修炼体系", "display_type": "hierarchy",
        })
        resp = client.post(f"/api/novels/{novel.id}/world/systems", json={
            "name": "修炼体系", "display_type": "list",
        })
        assert resp.status_code == 409

    def test_batch_confirm_systems(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/systems", json={
            "name": "修炼体系", "display_type": "hierarchy",
        })
        sid = resp.json()["id"]

        resp = client.post(f"/api/novels/{novel.id}/world/systems/confirm", json={"ids": [sid]})
        assert resp.status_code == 200
        assert resp.json()["confirmed"] == 1
