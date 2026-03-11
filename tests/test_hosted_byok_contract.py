"""
Contract tests for deploy_mode (selfhost/hosted) + BYOK (LLM headers) security.

These are intentionally small, high-signal tests covering:
- /api/auth/me behavior by deploy_mode
- hosted owner_id isolation for novels
- hosted SSRF rejection for user-supplied LLM base_url headers
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Novel, TokenUsage, User


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


class TestAuthMeDeployMode:
    def test_selfhost_me_returns_default_user_without_token(self, db):
        from app.api import auth as auth_api

        app = _make_app(db, auth_api.router)
        with TestClient(app) as c:
            resp = c.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["username"] == "default"

    def test_hosted_me_requires_token(self, db, monkeypatch):
        from app.api import auth as auth_api
        import app.core.auth as auth_core

        monkeypatch.setattr(auth_core, "get_settings", lambda: MagicMock(deploy_mode="hosted"))

        app = _make_app(db, auth_api.router)
        with TestClient(app) as c:
            resp = c.get("/api/auth/me")
        assert resp.status_code == 401


class TestHostedOwnerIsolation:
    def test_list_and_get_are_filtered_by_owner_id_in_hosted_mode(self, db, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        # hosted mode: strict owner_id isolation
        monkeypatch.setattr(novels_api, "get_settings", lambda: MagicMock(deploy_mode="hosted"))

        user1 = User(id=1, username="u1", hashed_password="x", role="admin", is_active=True)
        user2 = User(id=2, username="u2", hashed_password="x", role="user", is_active=True)
        db.add_all([user1, user2])
        db.commit()

        n1 = Novel(title="N1", author="", file_path="/tmp/n1.txt", total_chapters=0, owner_id=1)
        n2 = Novel(title="N2", author="", file_path="/tmp/n2.txt", total_chapters=0, owner_id=2)
        db.add_all([n1, n2])
        db.commit()
        db.refresh(n1)
        db.refresh(n2)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user1

        with TestClient(app) as c:
            resp = c.get("/api/novels")
            assert resp.status_code == 200
            data = resp.json()
            assert [row["id"] for row in data] == [n1.id]

            resp2 = c.get(f"/api/novels/{n2.id}")
            assert resp2.status_code == 404


class TestSelfhostOwnerBehavior:
    def test_selfhost_list_and_get_ignore_owner_id(self, db, monkeypatch):
        from datetime import datetime, timezone

        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        monkeypatch.setattr(novels_api, "get_settings", lambda: MagicMock(deploy_mode="selfhost"))

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


class TestHostedSSRFRejection:
    def test_hosted_rejects_http_and_link_local_base_url(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.core.auth import get_current_user_or_default
        import app.core.llm_request as llm_request
        import app.core.url_validator as url_validator

        monkeypatch.setattr(llm_request, "get_settings", lambda: MagicMock(deploy_mode="hosted"))
        monkeypatch.setattr(url_validator, "get_settings", lambda: MagicMock(deploy_mode="hosted"))

        app = _make_app(db, llm_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: User(
            id=1, username="u", hashed_password="x", role="admin", is_active=True
        )

        headers = {
            "x-llm-api-key": "k",
            "x-llm-model": "m",
        }

        with TestClient(app) as c:
            resp = c.post("/api/llm/test", headers={**headers, "x-llm-base-url": "http://localhost:8000"})
            assert resp.status_code == 400

            resp2 = c.post("/api/llm/test", headers={**headers, "x-llm-base-url": "https://169.254.169.254/v1"})
            assert resp2.status_code == 400

    def test_selfhost_allows_http_base_url(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.core.auth import get_current_user_or_default
        import app.core.llm_request as llm_request
        import app.core.url_validator as url_validator

        monkeypatch.setattr(llm_request, "get_settings", lambda: MagicMock(deploy_mode="selfhost"))
        monkeypatch.setattr(url_validator, "get_settings", lambda: MagicMock(deploy_mode="selfhost"))

        response = MagicMock(usage=None)
        mock_client = MagicMock()
        stream_chunk = MagicMock()
        stream_chunk.choices = [MagicMock(delta=MagicMock(content="ok"))]
        stream_chunk.usage = None

        async def fake_stream():
            yield stream_chunk

        json_response = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"ok": true}'))]
        )
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[response, fake_stream(), json_response]
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
        assert resp.json()["ok"] is True
        assert resp.json()["capabilities"] == {"basic": True, "stream": True, "json_mode": True}

    def test_hosted_llm_test_records_server_owned_usage(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.config import Settings
        from app.core.auth import get_current_user_or_default
        from app.database import SessionLocal
        import app.config as config_mod

        prev = config_mod._settings_instance
        prev_session_local = SessionLocal
        config_mod._settings_instance = Settings(
            deploy_mode="hosted",
            hosted_llm_base_url="https://example.com/v1",
            hosted_llm_api_key="hosted-key",
            hosted_llm_model="gemini-3.0-flash",
            _env_file=None,
        )
        try:
            monkeypatch.setattr("app.database.SessionLocal", TestingSessionLocal)
            user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
            app = _make_app(db, llm_api.router)
            app.dependency_overrides[get_current_user_or_default] = lambda: user

            usage = MagicMock(prompt_tokens=1_000, completion_tokens=2_000)
            response = MagicMock(usage=usage)
            stream_chunk = MagicMock()
            stream_chunk.choices = [MagicMock(delta=MagicMock(content="ok"))]
            stream_chunk.usage = None

            async def fake_stream():
                yield stream_chunk

            json_response = MagicMock(
                choices=[MagicMock(message=MagicMock(content='{"ok": true}'))]
            )
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[response, fake_stream(), json_response]
            )
            monkeypatch.setattr(llm_api, "AsyncOpenAI", lambda **kwargs: mock_client)

            with TestClient(app) as c:
                resp = c.post("/api/llm/test")

            assert resp.status_code == 200
            assert resp.json()["ok"] is True

            row = db.query(TokenUsage).order_by(TokenUsage.id.desc()).first()
            assert row is not None
            assert row.model == "gemini-3.0-flash"
            assert row.endpoint == "/api/llm/test"
            assert row.node_name == "llm_test"
            assert row.user_id == 1
            assert row.billing_source == "hosted"
            assert row.cost_estimate == pytest.approx(0.0065)
        finally:
            monkeypatch.setattr("app.database.SessionLocal", prev_session_local)
            config_mod._settings_instance = prev

    def test_llm_test_reports_json_mode_incompatibility(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.core.auth import get_current_user_or_default

        basic_response = MagicMock(usage=None)
        stream_chunk = MagicMock()
        stream_chunk.choices = [MagicMock(delta=MagicMock(content="ok"))]
        stream_chunk.usage = None

        async def fake_stream():
            yield stream_chunk

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                basic_response,
                fake_stream(),
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
        assert payload["ok"] is False
        assert payload["capabilities"] == {"basic": True, "stream": True, "json_mode": False}
        assert "JSON 模式" in payload["error"]

    def test_llm_test_reports_stream_incompatibility(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.core.auth import get_current_user_or_default

        basic_response = MagicMock(usage=None)
        json_response = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"ok": true}'))]
        )

        mock_client = MagicMock()
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
        assert payload["ok"] is False
        assert payload["capabilities"] == {"basic": True, "stream": False, "json_mode": True}
        assert "流式输出" in payload["error"]

    def test_llm_test_retries_stream_probe_without_stream_options(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.core.auth import get_current_user_or_default

        basic_response = MagicMock(usage=None)
        stream_chunk = MagicMock()
        stream_chunk.choices = [MagicMock(delta=MagicMock(content="ok"))]
        stream_chunk.usage = None

        async def fake_stream():
            yield stream_chunk

        json_response = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"ok": true}'))]
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                basic_response,
                Exception("Unknown field: stream_options"),
                fake_stream(),
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
        assert payload["ok"] is True
        assert payload["capabilities"] == {"basic": True, "stream": True, "json_mode": True}

    def test_hosted_llm_test_allows_byok_when_hosted_budget_hard_stop_is_reached(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.config import Settings
        from app.core.auth import get_current_user_or_default
        import app.config as config_mod

        prev = config_mod._settings_instance
        config_mod._settings_instance = Settings(deploy_mode="hosted", ai_hard_stop_usd=1.0, _env_file=None)
        try:
            db.add(
                TokenUsage(
                    user_id=1,
                    model="gemini-3.0-flash",
                    prompt_tokens=10,
                    completion_tokens=10,
                    total_tokens=20,
                    cost_estimate=1.0,
                    billing_source="hosted",
                    node_name="writer",
                )
            )
            db.commit()

            basic_response = MagicMock(usage=None)
            stream_chunk = MagicMock()
            stream_chunk.choices = [MagicMock(delta=MagicMock(content="ok"))]
            stream_chunk.usage = None

            async def fake_stream():
                yield stream_chunk

            json_response = MagicMock(
                choices=[MagicMock(message=MagicMock(content='{"ok": true}'))]
            )
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[basic_response, fake_stream(), json_response]
            )
            monkeypatch.setattr(llm_api, "AsyncOpenAI", lambda **kwargs: mock_client)

            app = _make_app(db, llm_api.router)
            app.dependency_overrides[get_current_user_or_default] = lambda: User(
                id=1, username="u", hashed_password="x", role="admin", is_active=True
            )

            headers = {
                "x-llm-base-url": "https://example.com/v1",
                "x-llm-api-key": "k",
                "x-llm-model": "m",
            }

            with TestClient(app) as c:
                resp = c.post("/api/llm/test", headers=headers)

            assert resp.status_code == 200
            assert resp.json()["ok"] is True
        finally:
            config_mod._settings_instance = prev

    def test_llm_test_rejects_partial_byok_headers(self, db, monkeypatch):
        from app.api import llm as llm_api
        from app.core.auth import get_current_user_or_default
        import app.core.llm_request as llm_request
        import app.core.url_validator as url_validator

        monkeypatch.setattr(llm_request, "get_settings", lambda: MagicMock(deploy_mode="selfhost"))
        monkeypatch.setattr(url_validator, "get_settings", lambda: MagicMock(deploy_mode="selfhost"))
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


    def test_llm_test_rejects_when_ai_is_manually_disabled(self, db):
        from app.api import llm as llm_api
        from app.config import Settings
        from app.core.auth import get_current_user_or_default
        import app.config as config_mod

        prev = config_mod._settings_instance
        config_mod._settings_instance = Settings(deploy_mode="hosted", ai_manual_disable=True, _env_file=None)
        try:
            app = _make_app(db, llm_api.router)
            app.dependency_overrides[get_current_user_or_default] = lambda: User(
                id=1, username="u", hashed_password="x", role="admin", is_active=True
            )
            llm_api.AsyncOpenAI = lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not call provider"))

            headers = {
                "x-llm-base-url": "https://example.com/v1",
                "x-llm-api-key": "k",
                "x-llm-model": "m",
            }

            with TestClient(app) as c:
                resp = c.post("/api/llm/test", headers=headers)

            assert resp.status_code == 503
            assert resp.json()["detail"]["code"] == "ai_manually_disabled"
        finally:
            config_mod._settings_instance = prev
