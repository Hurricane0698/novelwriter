from unittest.mock import AsyncMock, MagicMock

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


def _make_app(db, router) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return app


class TestLocalProfile:
    def test_selfhost_me_returns_default_user_without_token(self, db):
        from app.api import auth as auth_api

        app = _make_app(db, auth_api.router)
        with TestClient(app) as c:
            resp = c.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["username"] == "default"

    def test_preferences_persist_across_updates(self, db):
        from app.api import auth

        with TestClient(_make_app(db, auth.router)) as client:
            assert client.patch("/api/auth/preferences", json={
                "preferences": {"context_chapters": 99, "num_versions": 2}
            }).status_code == 200
            assert client.patch("/api/auth/preferences", json={
                "preferences": {"num_versions": 3}
            }).status_code == 200
            db.expire_all()
            assert client.get("/api/auth/me").json()["preferences"] == {
                "context_chapters": 5, "num_versions": 3
            }


class TestSelfhostOwnerBehavior:
    def test_selfhost_list_and_get_ignore_owner_id(self, db):
        from datetime import datetime, timezone

        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=111, username="default", hashed_password="x", role="admin", is_active=True)
        other = User(id=1, username="u1", hashed_password="x", role="user", is_active=True)
        db.add_all([user, other])
        db.commit()

        # Owned by a different user id; selfhost must still surface it.
        n1 = Novel(
            title="N1",
            author="",
            file_path="/tmp/n1.txt",
            total_chapters=0,
            owner_id=1,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        n2 = Novel(
            title="N2",
            author="",
            file_path="/tmp/n2.txt",
            total_chapters=0,
            owner_id=111,
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        db.add_all([n1, n2])
        db.commit()
        db.refresh(n1)
        db.refresh(n2)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.get("/api/novels")
            assert resp.status_code == 200
            ids = [row["id"] for row in resp.json()]
            assert ids == [n2.id, n1.id]

            resp2 = c.get(f"/api/novels/{n1.id}")
            assert resp2.status_code == 200


class TestLocalModelConnection:

    def test_selfhost_allows_http_base_url(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.core.auth import get_current_user_or_default
        import app.core.llm_request as llm_request

        monkeypatch.setattr(
            llm_request,
            "get_settings",
            lambda: MagicMock(deploy_mode="selfhost", runtime_mode="selfhost"),
        )

        response = MagicMock(usage=None)
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        stream_chunk = MagicMock()
        stream_chunk.choices = [MagicMock(delta=MagicMock(content="ok"))]
        stream_chunk.usage = None

        stream = MagicMock()
        stream.__aiter__.return_value = [stream_chunk]
        stream.close = AsyncMock()

        json_response = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"ok": true}'))]
        )
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[response, stream, json_response]
        )
        monkeypatch.setattr(llm_api, "AsyncOpenAI", lambda **kwargs: mock_client)

        app = _make_app(db, llm_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: User(
            id=1, username="default", hashed_password="x", role="admin", is_active=True
        )

        headers = {
            "x-llm-base-url": "http://localhost:8000/v1",
            "x-llm-api-key": "k",
            "x-llm-model": "m",
        }

        with TestClient(app) as c:
            resp = c.post("/api/llm/test", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == "llm_probe_compatible"
        assert resp.json()["capabilities"] == {"basic": True, "stream": True, "json_mode": True}

    def test_llm_test_reports_json_mode_incompatibility(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.core.auth import get_current_user_or_default

        basic_response = MagicMock(usage=None)
        stream_chunk = MagicMock()
        stream_chunk.choices = [MagicMock(delta=MagicMock(content="ok"))]
        stream_chunk.usage = None

        stream = MagicMock()
        stream.__aiter__.return_value = [stream_chunk]
        stream.close = AsyncMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                basic_response,
                stream,
                Exception("response_format json_object is not supported"),
            ]
        )
        monkeypatch.setattr(llm_api, "AsyncOpenAI", lambda **kwargs: mock_client)

        app = _make_app(db, llm_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: User(
            id=1, username="default", hashed_password="x", role="admin", is_active=True
        )

        headers = {
            "x-llm-base-url": "http://localhost:8000/v1",
            "x-llm-api-key": "k",
            "x-llm-model": "m",
        }

        with TestClient(app) as c:
            resp = c.post("/api/llm/test", headers=headers)

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == "llm_probe_capability_mismatch"
        assert payload["capabilities"] == {"basic": True, "stream": True, "json_mode": False}
        assert "message" not in payload
        assert "error" not in payload

    def test_llm_test_reports_stream_incompatibility(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.core.auth import get_current_user_or_default

        basic_response = MagicMock(usage=None)
        json_response = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"ok": true}'))]
        )

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                basic_response,
                Exception("streaming is not supported"),
                json_response,
            ]
        )
        monkeypatch.setattr(llm_api, "AsyncOpenAI", lambda **kwargs: mock_client)

        app = _make_app(db, llm_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: User(
            id=1, username="default", hashed_password="x", role="admin", is_active=True
        )

        headers = {
            "x-llm-base-url": "http://localhost:8000/v1",
            "x-llm-api-key": "k",
            "x-llm-model": "m",
        }

        with TestClient(app) as c:
            resp = c.post("/api/llm/test", headers=headers)

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == "llm_probe_capability_mismatch"
        assert payload["capabilities"] == {"basic": True, "stream": False, "json_mode": True}
        assert "message" not in payload
        assert "error" not in payload

    def test_llm_test_retries_stream_probe_without_stream_options(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.core.auth import get_current_user_or_default

        basic_response = MagicMock(usage=None)
        stream_chunk = MagicMock()
        stream_chunk.choices = [MagicMock(delta=MagicMock(content="ok"))]
        stream_chunk.usage = None

        stream = MagicMock()
        stream.__aiter__.return_value = [stream_chunk]
        stream.close = AsyncMock()

        json_response = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"ok": true}'))]
        )

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                basic_response,
                Exception("Unknown field: stream_options"),
                stream,
                json_response,
            ]
        )
        monkeypatch.setattr(llm_api, "AsyncOpenAI", lambda **kwargs: mock_client)

        app = _make_app(db, llm_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: User(
            id=1, username="default", hashed_password="x", role="admin", is_active=True
        )

        headers = {
            "x-llm-base-url": "http://localhost:8000/v1",
            "x-llm-api-key": "k",
            "x-llm-model": "m",
        }

        with TestClient(app) as c:
            resp = c.post("/api/llm/test", headers=headers)

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["code"] == "llm_probe_compatible"
        assert payload["capabilities"] == {"basic": True, "stream": True, "json_mode": True}

    def test_llm_test_rejects_partial_byok_headers(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.core.auth import get_current_user_or_default
        import app.core.llm_request as llm_request

        monkeypatch.setattr(
            llm_request,
            "get_settings",
            lambda: MagicMock(deploy_mode="selfhost", runtime_mode="selfhost"),
        )
        monkeypatch.setattr(llm_api, "AsyncOpenAI", lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not call provider")))

        app = _make_app(db, llm_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: User(
            id=1, username="default", hashed_password="x", role="admin", is_active=True
        )

        headers = {
            "x-llm-base-url": "http://localhost:8000/v1",
            "x-llm-api-key": "k",
        }

        with TestClient(app) as c:
            resp = c.post("/api/llm/test", headers=headers)

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "llm_config_incomplete"
