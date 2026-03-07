"""Tests for invite code auth + quota system."""

import os
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.config import reload_settings
from app.main import app
from app.database import get_db


@pytest.fixture()
def hosted_client(tmp_path):
    """Test client configured for hosted mode with invite code."""
    db_path = tmp_path / "test.db"

    # Save original env
    orig_env = {}
    env_overrides = {
        "DEPLOY_MODE": "hosted",
        "INVITE_CODE": "TEST-CODE-123",
        "JWT_SECRET_KEY": "test-secret-key-for-hosted-mode",
        "INITIAL_QUOTA": "5",
        "FEEDBACK_BONUS_QUOTA": "20",
    }
    for key, val in env_overrides.items():
        orig_env[key] = os.environ.get(key)
        os.environ[key] = val
    reload_settings()

    # Save and temporarily remove conftest auth overrides so real auth runs
    saved_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.clear()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)
    yield client

    # Restore env vars
    for key, orig_val in orig_env.items():
        if orig_val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = orig_val

    # Restore all overrides and reload settings
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved_overrides)
    reload_settings()


class TestInviteRegistration:
    def test_register_disabled_in_hosted(self, hosted_client):
        resp = hosted_client.post(
            "/api/auth/register",
            json={"username": "hosted_user", "password": "password123!"},
        )
        assert resp.status_code == 405

    def test_invite_success(self, hosted_client):
        resp = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "小明",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_invite_sets_http_only_session_cookie(self, hosted_client):
        from app.core.auth import SESSION_COOKIE_NAME

        resp = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "Cookie测试",
        })

        assert resp.status_code == 201
        assert SESSION_COOKIE_NAME in resp.cookies

    def test_me_accepts_session_cookie_without_authorization_header(self, hosted_client):
        hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "Cookie用户",
        })

        me_resp = hosted_client.get("/api/auth/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["nickname"] == "Cookie用户"

    def test_logout_clears_session_cookie(self, hosted_client):
        hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "退出测试",
        })

        logout_resp = hosted_client.post("/api/auth/logout")
        assert logout_resp.status_code == 204

        me_resp = hosted_client.get("/api/auth/me")
        assert me_resp.status_code == 401

    def test_invite_wrong_code(self, hosted_client):
        resp = hosted_client.post("/api/auth/invite", json={
            "invite_code": "WRONG-CODE",
            "nickname": "小明",
        })
        assert resp.status_code == 403

    def test_invite_returns_user_with_quota(self, hosted_client):
        resp = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "测试用户",
        })
        token = resp.json()["access_token"]

        me_resp = hosted_client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert me_resp.status_code == 200
        user = me_resp.json()
        assert user["nickname"] == "测试用户"
        assert user["generation_quota"] == 5
        assert user["feedback_submitted"] is False

    def test_invite_relogin_returns_same_user_and_preserves_quota(self, hosted_client):
        """Re-inviting with the same nickname should log into the same account."""
        resp1 = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "重登测试",
        })
        assert resp1.status_code == 201
        token1 = resp1.json()["access_token"]

        me1 = hosted_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
        assert me1.status_code == 200
        user1 = me1.json()
        user_id = user1["id"]

        # Simulate usage by decrementing quota on the backend.
        from app.core.auth import decrement_quota
        from app.models import User

        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        u = db.query(User).filter(User.id == user_id).first()
        assert u is not None
        decrement_quota(db, u, count=2)

        # Re-login via invite: should NOT create a new user or reset quota.
        resp2 = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "重登测试",
        })
        assert resp2.status_code == 201
        token2 = resp2.json()["access_token"]

        me2 = hosted_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"})
        assert me2.status_code == 200
        user2 = me2.json()
        assert user2["id"] == user_id
        assert user2["generation_quota"] == 3

    def test_invite_blocks_new_signup_once_hosted_user_cap_is_reached(self, hosted_client, monkeypatch):
        monkeypatch.setenv("HOSTED_MAX_USERS", "1")
        reload_settings()

        resp1 = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "容量1号",
        })
        assert resp1.status_code == 201

        resp2 = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "容量2号",
        })
        assert resp2.status_code == 503
        assert resp2.json()["detail"]["code"] == "hosted_user_cap_reached"

    def test_invite_allows_existing_user_relogin_even_when_user_cap_is_reached(self, hosted_client, monkeypatch):
        monkeypatch.setenv("HOSTED_MAX_USERS", "1")
        reload_settings()

        resp1 = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "容量重登",
        })
        assert resp1.status_code == 201

        resp2 = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "容量重登",
        })
        assert resp2.status_code == 201

    def test_invite_cap_stays_atomic_under_concurrent_signups(self, hosted_client, monkeypatch):
        import app.api.auth as auth_api

        monkeypatch.setenv("HOSTED_MAX_USERS", "1")
        reload_settings()

        original_hash_password = auth_api.hash_password
        first_signup_entered = threading.Event()
        release_first_signup = threading.Event()
        hash_call_count = 0
        hash_call_lock = threading.Lock()

        def slow_hash_password(raw_password: str) -> str:
            nonlocal hash_call_count
            with hash_call_lock:
                hash_call_count += 1
                current_call = hash_call_count

            if current_call == 1:
                first_signup_entered.set()
                assert release_first_signup.wait(timeout=5)

            return original_hash_password(raw_password)

        monkeypatch.setattr(auth_api, "hash_password", slow_hash_password)

        results: dict[str, object] = {}

        def submit_invite(nickname: str) -> None:
            with TestClient(app) as client:
                results[nickname] = client.post(
                    "/api/auth/invite",
                    json={"invite_code": "TEST-CODE-123", "nickname": nickname},
                )

        first_thread = threading.Thread(target=submit_invite, args=("并发容量1号",))
        second_thread = threading.Thread(target=submit_invite, args=("并发容量2号",))

        first_thread.start()
        assert first_signup_entered.wait(timeout=5)

        second_thread.start()
        time.sleep(0.2)
        release_first_signup.set()

        first_thread.join(timeout=5)
        second_thread.join(timeout=5)

        assert not first_thread.is_alive()
        assert not second_thread.is_alive()

        responses = [results["并发容量1号"], results["并发容量2号"]]
        status_codes = sorted(resp.status_code for resp in responses)
        assert status_codes == [201, 503]
        assert hash_call_count == 1

        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            from app.models import User

            active_users = db.query(User).filter(User.is_active.is_(True)).count()
            assert active_users == 1
        finally:
            db.close()

    def test_preferences_context_chapters_above_cap_is_clamped_to_five(self, hosted_client):
        resp = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "偏好上限测试",
        })
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        patch_resp = hosted_client.patch(
            "/api/auth/preferences",
            json={"preferences": {"context_chapters": 99}},
            headers=headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["preferences"]["context_chapters"] == 5


class TestQuota:
    def test_quota_endpoint(self, hosted_client):
        resp = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "配额测试",
        })
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        quota_resp = hosted_client.get("/api/auth/quota", headers=headers)
        assert quota_resp.status_code == 200
        assert quota_resp.json()["generation_quota"] == 5
        assert quota_resp.json()["feedback_submitted"] is False


VALID_FEEDBACK = {
    "overall_rating": "great",
    "issues": ["speed"],
}

VALID_FEEDBACK_WITH_SUGGESTION = {
    "overall_rating": "great",
    "issues": ["speed"],
    "suggestion": "希望能支持更多模型的选择，比如本地部署的大模型也可以接入",
}


class TestFeedback:
    def test_feedback_grants_bonus(self, hosted_client):
        resp = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "反馈测试",
        })
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        feedback_resp = hosted_client.post(
            "/api/auth/feedback",
            json={"answers": VALID_FEEDBACK},
            headers=headers,
        )
        assert feedback_resp.status_code == 200
        data = feedback_resp.json()
        assert data["generation_quota"] == 25  # 5 + 20
        assert data["feedback_submitted"] is True

    def test_feedback_with_suggestion_grants_extra_bonus(self, hosted_client):
        resp = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "建议测试",
        })
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        feedback_resp = hosted_client.post(
            "/api/auth/feedback",
            json={"answers": VALID_FEEDBACK_WITH_SUGGESTION},
            headers=headers,
        )
        assert feedback_resp.status_code == 200
        data = feedback_resp.json()
        assert data["generation_quota"] == 35  # 5 + 20 + 10
        assert data["feedback_submitted"] is True

    def test_feedback_bug_requires_description(self, hosted_client):
        resp = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "Bug描述测试",
        })
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # bugs selected but no bug_description
        feedback_resp = hosted_client.post(
            "/api/auth/feedback",
            json={"answers": {"overall_rating": "okay", "issues": ["bugs"]}},
            headers=headers,
        )
        assert feedback_resp.status_code == 422

        # With description — should pass
        feedback_resp = hosted_client.post(
            "/api/auth/feedback",
            json={"answers": {"overall_rating": "okay", "issues": ["bugs"], "bug_description": "页面白屏"}},
            headers=headers,
        )
        assert feedback_resp.status_code == 200

    def test_feedback_rejects_missing_fields(self, hosted_client):
        resp = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "缺字段测试",
        })
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Missing 'issues' key
        feedback_resp = hosted_client.post(
            "/api/auth/feedback",
            json={"answers": {"overall_rating": "great"}},
            headers=headers,
        )
        assert feedback_resp.status_code == 422

        # Empty issues list
        feedback_resp = hosted_client.post(
            "/api/auth/feedback",
            json={"answers": {"overall_rating": "great", "issues": []}},
            headers=headers,
        )
        assert feedback_resp.status_code == 422

    def test_feedback_idempotent(self, hosted_client):
        resp = hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "重复反馈",
        })
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # First feedback
        hosted_client.post("/api/auth/feedback", json={"answers": VALID_FEEDBACK}, headers=headers)

        # Second feedback — no additional quota
        feedback_resp = hosted_client.post(
            "/api/auth/feedback",
            json={"answers": VALID_FEEDBACK},
            headers=headers,
        )
        assert feedback_resp.json()["generation_quota"] == 25  # still 5 + 20


class TestDecrementQuota:
    def test_decrement_reduces_quota(self, hosted_client):
        """decrement_quota subtracts the correct count."""
        from app.core.auth import decrement_quota

        hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "扣减测试",
        })

        # Get the db session and user from the override
        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        from app.models import User
        user = db.query(User).filter(User.nickname == "扣减测试").first()
        assert user.generation_quota == 5

        decrement_quota(db, user, count=3)
        assert user.generation_quota == 2

        decrement_quota(db, user, count=1)
        assert user.generation_quota == 1

    def test_decrement_rejects_insufficient_quota(self, hosted_client):
        """decrement_quota raises 429 when count exceeds remaining quota."""
        from fastapi import HTTPException
        from app.core.auth import decrement_quota

        hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "不足测试",
        })

        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        from app.models import User
        user = db.query(User).filter(User.nickname == "不足测试").first()
        assert user.generation_quota == 5

        with pytest.raises(HTTPException) as exc_info:
            decrement_quota(db, user, count=10)
        assert exc_info.value.status_code == 429

    def test_try_decrement_atomic(self, hosted_client):
        """try_decrement_quota atomically decrements and returns bool."""
        from app.core.auth import try_decrement_quota

        hosted_client.post("/api/auth/invite", json={
            "invite_code": "TEST-CODE-123",
            "nickname": "原子扣减",
        })

        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        from app.models import User
        user = db.query(User).filter(User.nickname == "原子扣减").first()
        assert user.generation_quota == 5

        assert try_decrement_quota(db, user.id, count=2) is True
        db.refresh(user)
        assert user.generation_quota == 3

        assert try_decrement_quota(db, user.id, count=10) is False
        db.refresh(user)
        assert user.generation_quota == 3  # unchanged
