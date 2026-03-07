"""
Contract tests: hosted mode usage endpoints must not leak cross-tenant data.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import TokenUsage, User


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


class TestHostedUsageIsolation:
    def test_hosted_usage_summary_is_scoped_to_current_user(self, db, monkeypatch):
        from app.api import usage as usage_api

        monkeypatch.setattr(usage_api, "get_settings", lambda: MagicMock(deploy_mode="hosted"))

        user1 = User(id=1, username="u1", hashed_password="x", role="user", is_active=True)

        db.add_all(
            [
                TokenUsage(
                    user_id=1,
                    model="m1",
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                    cost_estimate=0.01,
                    endpoint="/api/novels/1/continue",
                    node_name="writer",
                ),
                TokenUsage(
                    user_id=2,
                    model="m2",
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                    cost_estimate=0.1,
                    endpoint="/api/novels/2/continue",
                    node_name="writer",
                ),
            ]
        )
        db.commit()

        app = _make_app(db, usage_api.router, current_user=user1)
        with TestClient(app) as c:
            resp = c.get("/api/usage/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_tokens"] == 15
            assert data["by_model"] == [{"model": "m1", "total_tokens": 15, "cost_usd": 0.01}]

            recent = c.get("/api/usage/recent")
            assert recent.status_code == 200
            assert len(recent.json()) == 1
            assert recent.json()[0]["model"] == "m1"


class TestSelfhostUsageBehavior:
    def test_selfhost_usage_summary_includes_all_rows(self, db, monkeypatch):
        from app.api import usage as usage_api

        monkeypatch.setattr(usage_api, "get_settings", lambda: MagicMock(deploy_mode="selfhost"))

        user1 = User(id=1, username="default", hashed_password="x", role="admin", is_active=True)

        db.add_all(
            [
                TokenUsage(
                    user_id=1,
                    model="m1",
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                    cost_estimate=0.01,
                ),
                TokenUsage(
                    user_id=2,
                    model="m2",
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                    cost_estimate=0.1,
                ),
            ]
        )
        db.commit()

        app = _make_app(db, usage_api.router, current_user=user1)
        with TestClient(app) as c:
            resp = c.get("/api/usage/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_tokens"] == 165
