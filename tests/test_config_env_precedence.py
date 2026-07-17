from __future__ import annotations

from app.config import Settings


def test_dotenv_overrides_os_env_in_local_mode(monkeypatch, tmp_path) -> None:
    # Local/selfhost behavior: project `.env` should override user-wide shell exports
    # (e.g., OPENAI_API_KEY in ~/.bashrc) so users can set per-project keys.
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "OPENAI_API_KEY=from_dotenv\n"
        "JWT_SECRET_KEY=from_dotenv\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DEPLOY_MODE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "from_env")
    monkeypatch.setenv("JWT_SECRET_KEY", "from_env")

    s = Settings(_env_file=env_path)
    assert s.openai_api_key == "from_dotenv"
    assert s.jwt_secret_key == "from_dotenv"


def test_dotenv_is_used_as_fallback(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / "test.env"
    env_path.write_text("OPENAI_API_KEY=from_dotenv\n", encoding="utf-8")

    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DEPLOY_MODE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    s = Settings(_env_file=env_path)
    assert s.openai_api_key == "from_dotenv"


def test_desktop_mode_ignores_dotenv(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "ENVIRONMENT=dev\n"
        "DEPLOY_MODE=hosted\n"
        "JWT_SECRET_KEY=from-dotenv\n"
        "OPENAI_API_KEY=from-dotenv\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("ENVIRONMENT", "desktop")
    monkeypatch.setenv("DEPLOY_MODE", "selfhost")
    monkeypatch.setenv("JWT_SECRET_KEY", "from-desktop-launcher")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = Settings(_env_file=env_path)
    assert settings.environment == "desktop"
    assert settings.deploy_mode == "selfhost"
    assert settings.jwt_secret_key == "from-desktop-launcher"
    assert settings.openai_api_key == ""
