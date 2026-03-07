"""
World Model contract tests — edge cases and 404 paths not covered by test_api_world.py.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Novel, User, WorldEntityAttribute


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
    n = Novel(title="测试小说", author="测试", file_path="/tmp/t.txt", total_chapters=1)
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
        id=1, username="t", hashed_password="x", role="admin", is_active=True,
    )

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


@pytest.fixture
def entity_id(client, novel):
    resp = client.post(f"/api/novels/{novel.id}/world/entities", json={
        "name": "测试实体", "entity_type": "Character",
    })
    return resp.json()["id"]


@pytest.fixture
def attr_id(client, novel, entity_id):
    resp = client.post(
        f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes",
        json={"key": "修为", "surface": "真玄境"},
    )
    return resp.json()["id"]


# ===========================================================================
# 404 — nonexistent novel
# ===========================================================================


class TestNovel404:

    def test_list_entities_novel_404(self, client):
        assert client.get("/api/novels/9999/world/entities").status_code == 404

    def test_create_entity_novel_404(self, client):
        resp = client.post("/api/novels/9999/world/entities", json={
            "name": "x", "entity_type": "Character",
        })
        assert resp.status_code == 404

    def test_list_relationships_novel_404(self, client):
        assert client.get("/api/novels/9999/world/relationships").status_code == 404

    def test_create_relationship_novel_404(self, client):
        resp = client.post("/api/novels/9999/world/relationships", json={
            "source_id": 1, "target_id": 2, "label": "x",
        })
        assert resp.status_code == 404

    def test_list_systems_novel_404(self, client):
        assert client.get("/api/novels/9999/world/systems").status_code == 404

    def test_create_system_novel_404(self, client):
        resp = client.post("/api/novels/9999/world/systems", json={
            "name": "x", "display_type": "list",
        })
        assert resp.status_code == 404


# ===========================================================================
# 404 — nonexistent entity / attribute / relationship / system
# ===========================================================================


class TestResource404:

    def test_get_entity_404(self, client, novel):
        assert client.get(f"/api/novels/{novel.id}/world/entities/9999").status_code == 404

    def test_update_entity_404(self, client, novel):
        resp = client.put(f"/api/novels/{novel.id}/world/entities/9999", json={"description": "x"})
        assert resp.status_code == 404

    def test_delete_entity_404(self, client, novel):
        assert client.delete(f"/api/novels/{novel.id}/world/entities/9999").status_code == 404

    def test_add_attribute_entity_404(self, client, novel):
        resp = client.post(
            f"/api/novels/{novel.id}/world/entities/9999/attributes",
            json={"key": "k", "surface": "v"},
        )
        assert resp.status_code == 404

    def test_update_attribute_404(self, client, novel, entity_id):
        resp = client.put(
            f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes/9999",
            json={"surface": "x"},
        )
        assert resp.status_code == 404

    def test_delete_attribute_404(self, client, novel, entity_id):
        resp = client.delete(
            f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes/9999",
        )
        assert resp.status_code == 404

    def test_update_relationship_404(self, client, novel):
        resp = client.put(
            f"/api/novels/{novel.id}/world/relationships/9999", json={"label": "x"},
        )
        assert resp.status_code == 404

    def test_delete_relationship_404(self, client, novel):
        assert client.delete(f"/api/novels/{novel.id}/world/relationships/9999").status_code == 404

    def test_get_system_404(self, client, novel):
        assert client.get(f"/api/novels/{novel.id}/world/systems/9999").status_code == 404

    def test_update_system_404(self, client, novel):
        resp = client.put(
            f"/api/novels/{novel.id}/world/systems/9999", json={"description": "x"},
        )
        assert resp.status_code == 404

    def test_delete_system_404(self, client, novel):
        assert client.delete(f"/api/novels/{novel.id}/world/systems/9999").status_code == 404


# ===========================================================================
# Batch confirm edge cases
# ===========================================================================


class TestBatchConfirmEdgeCases:

    def test_confirm_already_confirmed_entity(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "已确认", "entity_type": "Character",
        })
        eid = resp.json()["id"]
        client.post(f"/api/novels/{novel.id}/world/entities/confirm", json={"ids": [eid]})
        resp = client.post(f"/api/novels/{novel.id}/world/entities/confirm", json={"ids": [eid]})
        assert resp.json()["confirmed"] == 0

    def test_confirm_empty_ids(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/entities/confirm", json={"ids": []})
        assert resp.status_code == 200
        assert resp.json()["confirmed"] == 0

    def test_confirm_nonexistent_ids(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/entities/confirm", json={"ids": [9999]})
        assert resp.json()["confirmed"] == 0

    def test_confirm_already_confirmed_relationship(self, client, novel):
        r1 = client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "A", "entity_type": "Character",
        })
        r2 = client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "B", "entity_type": "Character",
        })
        resp = client.post(f"/api/novels/{novel.id}/world/relationships", json={
            "source_id": r1.json()["id"], "target_id": r2.json()["id"], "label": "友",
        })
        rid = resp.json()["id"]
        client.post(f"/api/novels/{novel.id}/world/relationships/confirm", json={"ids": [rid]})
        resp = client.post(f"/api/novels/{novel.id}/world/relationships/confirm", json={"ids": [rid]})
        assert resp.json()["confirmed"] == 0

    def test_confirm_already_confirmed_system(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/systems", json={
            "name": "体系", "display_type": "list",
        })
        sid = resp.json()["id"]
        client.post(f"/api/novels/{novel.id}/world/systems/confirm", json={"ids": [sid]})
        resp = client.post(f"/api/novels/{novel.id}/world/systems/confirm", json={"ids": [sid]})
        assert resp.json()["confirmed"] == 0


# ===========================================================================
# Cascade & conflict edge cases
# ===========================================================================


class TestCascadeAndConflict:

    def test_delete_entity_cascades_attributes(self, client, novel, entity_id, attr_id, db):
        client.delete(f"/api/novels/{novel.id}/world/entities/{entity_id}")
        assert db.query(WorldEntityAttribute).filter_by(id=attr_id).first() is None

    def test_reorder_updates_sort_order(self, client, novel, entity_id):
        aids = []
        for key in ["A", "B", "C"]:
            resp = client.post(
                f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes",
                json={"key": key, "surface": key},
            )
            aids.append(resp.json()["id"])

        client.patch(
            f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes/reorder",
            json={"order": list(reversed(aids))},
        )

        resp = client.get(f"/api/novels/{novel.id}/world/entities/{entity_id}")
        attrs = sorted(resp.json()["attributes"], key=lambda a: a["sort_order"])
        assert [a["key"] for a in attrs] == ["C", "B", "A"]

    def test_update_entity_name_conflict_409(self, client, novel):
        client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "A", "entity_type": "Character",
        })
        resp = client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "B", "entity_type": "Character",
        })
        eid_b = resp.json()["id"]
        resp = client.put(f"/api/novels/{novel.id}/world/entities/{eid_b}", json={"name": "A"})
        assert resp.status_code == 409

    def test_update_system_name_conflict_409(self, client, novel):
        client.post(f"/api/novels/{novel.id}/world/systems", json={
            "name": "S1", "display_type": "list",
        })
        resp = client.post(f"/api/novels/{novel.id}/world/systems", json={
            "name": "S2", "display_type": "list",
        })
        sid = resp.json()["id"]
        resp = client.put(f"/api/novels/{novel.id}/world/systems/{sid}", json={"name": "S1"})
        assert resp.status_code == 409

    def test_update_attribute_key_conflict_409(self, client, novel, entity_id):
        client.post(
            f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes",
            json={"key": "K1", "surface": "v"},
        )
        resp = client.post(
            f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes",
            json={"key": "K2", "surface": "v"},
        )
        aid = resp.json()["id"]
        resp = client.put(
            f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes/{aid}",
            json={"key": "K1"},
        )
        assert resp.status_code == 409


# ===========================================================================
# Happy path CRUD
# ===========================================================================


class TestEntityCRUD:

    def test_create_get_update_delete(self, client, novel):
        base = f"/api/novels/{novel.id}/world/entities"
        resp = client.post(base, json={"name": "李逍遥", "entity_type": "Character", "description": "主角"})
        assert resp.status_code == 201
        eid = resp.json()["id"]
        assert resp.json()["status"] == "draft"

        assert client.get(f"{base}/{eid}").json()["attributes"] == []

        resp = client.put(f"{base}/{eid}", json={"description": "蜀山弟子"})
        assert resp.json()["description"] == "蜀山弟子"

        assert client.delete(f"{base}/{eid}").status_code == 200
        assert client.get(f"{base}/{eid}").status_code == 404

    def test_list_filter_by_type(self, client, novel):
        base = f"/api/novels/{novel.id}/world/entities"
        client.post(base, json={"name": "A", "entity_type": "Character"})
        client.post(base, json={"name": "B", "entity_type": "Location"})
        assert len(client.get(base, params={"entity_type": "Character"}).json()) == 1

    def test_entity_with_aliases(self, client, novel):
        base = f"/api/novels/{novel.id}/world/entities"
        aliases = ["逍遥哥哥", "李大侠"]
        resp = client.post(base, json={"name": "李逍遥", "entity_type": "Character", "aliases": aliases})
        assert resp.json()["aliases"] == aliases
        assert client.get(f"{base}/{resp.json()['id']}").json()["aliases"] == aliases


class TestAttributeCRUD:

    def test_create_with_all_fields(self, client, novel, entity_id):
        url = f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes"
        resp = client.post(url, json={
            "key": "身份", "surface": "表面是书生", "truth": "实为暗卫", "visibility": "active",
        })
        assert resp.status_code == 201
        assert resp.json()["truth"] == "实为暗卫"
        assert resp.json()["visibility"] == "active"

    def test_update_visibility(self, client, novel, entity_id):
        url = f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes"
        aid = client.post(url, json={"key": "K", "surface": "V"}).json()["id"]
        assert client.put(f"{url}/{aid}", json={"visibility": "hidden"}).json()["visibility"] == "hidden"

    def test_all_visibility_levels(self, client, novel, entity_id):
        url = f"/api/novels/{novel.id}/world/entities/{entity_id}/attributes"
        for vis in ("active", "reference", "hidden"):
            resp = client.post(url, json={"key": f"key_{vis}", "surface": "v", "visibility": vis})
            assert resp.json()["visibility"] == vis


class TestRelationshipCRUD:

    def _two_entities(self, client, novel):
        base = f"/api/novels/{novel.id}/world/entities"
        a = client.post(base, json={"name": "甲", "entity_type": "Character"}).json()["id"]
        b = client.post(base, json={"name": "乙", "entity_type": "Character"}).json()["id"]
        return a, b

    def test_create_update_delete(self, client, novel):
        a, b = self._two_entities(client, novel)
        base = f"/api/novels/{novel.id}/world/relationships"
        resp = client.post(base, json={"source_id": a, "target_id": b, "label": "师徒"})
        assert resp.status_code == 201
        rid = resp.json()["id"]
        assert client.put(f"{base}/{rid}", json={"label": "仇敌"}).json()["label"] == "仇敌"
        assert client.delete(f"{base}/{rid}").status_code == 200

    def test_with_description_and_visibility(self, client, novel):
        a, b = self._two_entities(client, novel)
        resp = client.post(f"/api/novels/{novel.id}/world/relationships", json={
            "source_id": a, "target_id": b, "label": "盟友",
            "description": "共同对抗魔族", "visibility": "reference",
        })
        assert resp.json()["description"] == "共同对抗魔族"
        assert resp.json()["visibility"] == "reference"


# ===========================================================================
# Novel isolation — cross-novel attribute & relationship operations
# ===========================================================================


class TestNovelIsolation:

    @pytest.fixture
    def novel_b(self, db):
        n = Novel(title="另一本小说", author="测试B", file_path="/tmp/b.txt", total_chapters=1)
        db.add(n)
        db.commit()
        db.refresh(n)
        return n

    @pytest.fixture
    def entity_in_a(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "实体A", "entity_type": "Character",
        })
        return resp.json()["id"]

    @pytest.fixture
    def attr_in_a(self, client, novel, entity_in_a):
        resp = client.post(
            f"/api/novels/{novel.id}/world/entities/{entity_in_a}/attributes",
            json={"key": "修为", "surface": "真玄境"},
        )
        return resp.json()["id"]

    def test_update_attribute_cross_novel_404(self, client, novel_b, entity_in_a, attr_in_a):
        resp = client.put(
            f"/api/novels/{novel_b.id}/world/entities/{entity_in_a}/attributes/{attr_in_a}",
            json={"surface": "偷改"},
        )
        assert resp.status_code == 404

    def test_delete_attribute_cross_novel_404(self, client, novel_b, entity_in_a, attr_in_a):
        resp = client.delete(
            f"/api/novels/{novel_b.id}/world/entities/{entity_in_a}/attributes/{attr_in_a}",
        )
        assert resp.status_code == 404

    def test_reorder_attributes_cross_novel_404(self, client, novel_b, entity_in_a, attr_in_a):
        resp = client.patch(
            f"/api/novels/{novel_b.id}/world/entities/{entity_in_a}/attributes/reorder",
            json={"order": [attr_in_a]},
        )
        assert resp.status_code == 404

    def test_add_attribute_cross_novel_404(self, client, novel_b, entity_in_a):
        resp = client.post(
            f"/api/novels/{novel_b.id}/world/entities/{entity_in_a}/attributes",
            json={"key": "偷加", "surface": "v"},
        )
        assert resp.status_code == 404

    def test_create_relationship_cross_novel_entities_404(self, client, novel, novel_b):
        ea = client.post(f"/api/novels/{novel.id}/world/entities", json={
            "name": "甲A", "entity_type": "Character",
        }).json()["id"]
        eb = client.post(f"/api/novels/{novel_b.id}/world/entities", json={
            "name": "乙B", "entity_type": "Character",
        }).json()["id"]
        # source belongs to novel, target belongs to novel_b → 404
        resp = client.post(f"/api/novels/{novel.id}/world/relationships", json={
            "source_id": ea, "target_id": eb, "label": "跨小说",
        })
        assert resp.status_code == 404

    def test_create_relationship_both_foreign_404(self, client, novel, novel_b):
        ea = client.post(f"/api/novels/{novel_b.id}/world/entities", json={
            "name": "外A", "entity_type": "Character",
        }).json()["id"]
        eb = client.post(f"/api/novels/{novel_b.id}/world/entities", json={
            "name": "外B", "entity_type": "Character",
        }).json()["id"]
        # both entities belong to novel_b, but creating under novel → 404
        resp = client.post(f"/api/novels/{novel.id}/world/relationships", json={
            "source_id": ea, "target_id": eb, "label": "偷建",
        })
        assert resp.status_code == 404


class TestSystemCRUD:

    def test_create_get_update_delete(self, client, novel):
        base = f"/api/novels/{novel.id}/world/systems"
        data = {"nodes": [{"id": "root", "label": "玄帝境", "entity_id": None, "children": []}]}
        resp = client.post(base, json={
            "name": "修炼体系", "display_type": "hierarchy",
            "data": data, "constraints": ["突破需要天材地宝"],
        })
        assert resp.status_code == 201
        sid = resp.json()["id"]
        got = client.get(f"{base}/{sid}").json()
        assert got["data"] == data
        assert got["constraints"] == ["突破需要天材地宝"]
        client.put(f"{base}/{sid}", json={"data": {"nodes": []}})
        assert client.get(f"{base}/{sid}").json()["data"] == {"nodes": []}
        assert client.delete(f"{base}/{sid}").status_code == 200

    def test_all_display_types_roundtrip(self, client, novel):
        base = f"/api/novels/{novel.id}/world/systems"
        cases = {
            "graph": {"nodes": [{"id": "a", "label": "X", "position": {"x": 0, "y": 0}}], "edges": []},
            "timeline": {"events": [{"time": "千年前", "label": "魔法消失"}]},
            "list": {"items": [{"label": "规则一"}]},
        }
        for dt, data in cases.items():
            resp = client.post(base, json={"name": f"S_{dt}", "display_type": dt, "data": data})
            assert resp.json()["data"] == data
