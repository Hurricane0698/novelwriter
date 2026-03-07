"""
Contract tests: hosted mode must enforce owner isolation for novel-scoped routers.

Why: in hosted (multi-tenant) deployments, users must not be able to read/write
other users' novel-scoped data by guessing `novel_id`.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Novel, User


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


def _make_app(db, router, *, current_user: User) -> FastAPI:
    from app.core.auth import get_current_user_or_default

    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_or_default] = lambda: current_user
    return app


@pytest.fixture
def users(db) -> tuple[User, User]:
    u1 = User(id=1, username="u1", hashed_password="x", role="user", is_active=True)
    u2 = User(id=2, username="u2", hashed_password="x", role="user", is_active=True)
    db.add_all([u1, u2])
    db.commit()
    return u1, u2


class TestHostedIsolationNovelScopedRouters:
    def test_hosted_world_denies_cross_tenant_access(self, db, users, monkeypatch):
        import app.api.deps as api_deps
        from app.api import world as world_api

        monkeypatch.setattr(api_deps, "get_settings", lambda: MagicMock(deploy_mode="hosted"))

        u1, u2 = users
        other_novel = Novel(title="N", author="", file_path="/tmp/n.txt", total_chapters=0, owner_id=u2.id)
        db.add(other_novel)
        db.commit()
        db.refresh(other_novel)

        app = _make_app(db, world_api.router, current_user=u1)
        with TestClient(app) as c:
            resp = c.get(f"/api/novels/{other_novel.id}/world/entities")
        assert resp.status_code == 404

    def test_hosted_lorebook_denies_cross_tenant_access(self, db, users, monkeypatch):
        import app.api.deps as api_deps
        from app.api import lorebook as lorebook_api

        monkeypatch.setattr(api_deps, "get_settings", lambda: MagicMock(deploy_mode="hosted"))

        u1, u2 = users
        other_novel = Novel(title="N", author="", file_path="/tmp/n.txt", total_chapters=0, owner_id=u2.id)
        db.add(other_novel)
        db.commit()
        db.refresh(other_novel)

        app = _make_app(db, lorebook_api.router, current_user=u1)
        with TestClient(app) as c:
            resp = c.get(f"/api/novels/{other_novel.id}/lorebook/entries")
        assert resp.status_code == 404

    def test_hosted_dashboard_denies_cross_tenant_access(self, db, users, monkeypatch):
        import app.api.deps as api_deps
        from app.api import dashboard as dashboard_api

        monkeypatch.setattr(api_deps, "get_settings", lambda: MagicMock(deploy_mode="hosted"))

        u1, u2 = users
        other_novel = Novel(title="N", author="", file_path="/tmp/n.txt", total_chapters=0, owner_id=u2.id)
        db.add(other_novel)
        db.commit()
        db.refresh(other_novel)

        app = _make_app(db, dashboard_api.router, current_user=u1)
        with TestClient(app) as c:
            resp = c.get(f"/api/novels/{other_novel.id}/dashboard")
        assert resp.status_code == 404


class TestSelfhostNovelScopedRouters:
    def test_selfhost_world_ignores_owner_id(self, db, users, monkeypatch):
        import app.api.deps as api_deps
        from app.api import world as world_api

        monkeypatch.setattr(api_deps, "get_settings", lambda: MagicMock(deploy_mode="selfhost"))

        u1, u2 = users
        other_novel = Novel(title="N", author="", file_path="/tmp/n.txt", total_chapters=0, owner_id=u2.id)
        db.add(other_novel)
        db.commit()
        db.refresh(other_novel)

        app = _make_app(db, world_api.router, current_user=u1)
        with TestClient(app) as c:
            resp = c.get(f"/api/novels/{other_novel.id}/world/entities")
        assert resp.status_code == 200
