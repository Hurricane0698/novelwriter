"""
Pytest configuration and shared fixtures.
"""

import sys
from pathlib import Path
import socket

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(autouse=True)
def _force_selfhost_settings():
    """Make test runs deterministic (ignore developer-local repo `.env`).

    Many tests assume selfhost mode (no auth tokens, no owner_id isolation).
    A developer-local `.env` may set DEPLOY_MODE=hosted, which would otherwise
    flip API behavior and break the suite.

    Tests that need hosted mode should set OS env `DEPLOY_MODE=hosted` and call
    `reload_settings()` explicitly (see tests/test_invite_quota.py).
    """
    import os

    # If a test explicitly opts into hosted mode via OS env, respect it.
    if os.getenv("DEPLOY_MODE", "").strip().lower() == "hosted":
        yield
        return

    import app.config as config_mod
    from app.config import Settings

    config_mod._settings_instance = Settings(deploy_mode="selfhost", _env_file=None)
    yield


@pytest.fixture(autouse=True)
def _bypass_auth():
    """Override JWT auth dependency globally so existing tests pass without tokens."""
    from app.main import app
    from app.core.auth import (
        check_generation_quota,
        get_current_user,
        get_current_user_or_default,
        require_admin,
    )
    from app.models import User

    fake_user = User(
        id=1, username="testuser", hashed_password="x", role="admin", is_active=True,
        generation_quota=999, feedback_submitted=False,
    )

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_current_user_or_default] = lambda: fake_user
    app.dependency_overrides[require_admin] = lambda: fake_user
    app.dependency_overrides[check_generation_quota] = lambda: fake_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_or_default, None)
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(check_generation_quota, None)


@pytest.fixture
def allow_public_llm_url_resolution(monkeypatch):
    """Resolve BYOK test hosts to a stable public IP without skipping validation."""
    import app.core.url_validator as url_validator

    original_getaddrinfo = url_validator.socket.getaddrinfo

    def _install(*, hostname: str = "example.com", ip: str = "93.184.216.34") -> None:
        def fake_getaddrinfo(requested_hostname, port, family=0, type=0, proto=0, flags=0):
            if requested_hostname == hostname:
                return [(socket.AF_INET, socket.SOCK_STREAM, proto or 6, "", (ip, port or 0))]
            return original_getaddrinfo(requested_hostname, port, family, type, proto, flags)

        monkeypatch.setattr(url_validator.socket, "getaddrinfo", fake_getaddrinfo)

    return _install
