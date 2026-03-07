from __future__ import annotations


def test_os_environment_overrides_dotenv(monkeypatch, tmp_path):
    """Regression: a stray `.env` must not override OS env in production deploys."""
    from app.config import Settings

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "ENVIRONMENT=dev\n"
        "JWT_SECRET_KEY=from-dotenv\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "from-os")

    settings = Settings()
    assert settings.environment == "production"
    assert settings.jwt_secret_key == "from-os"


def test_dotenv_is_used_when_os_env_missing(monkeypatch, tmp_path):
    from app.config import Settings

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "JWT_SECRET_KEY=from-dotenv\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    settings = Settings()
    assert settings.jwt_secret_key == "from-dotenv"

