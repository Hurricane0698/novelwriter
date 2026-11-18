import pytest

from app.config import Settings
from app.main import StartupSecurityValidationError, _validate_startup_security_settings


def test_non_production_allows_default_jwt_secret():
    settings = Settings(environment="dev")

    _validate_startup_security_settings(
        jwt_secret_key="CHANGE-ME-IN-PRODUCTION",
        is_production=settings.is_production,
    )


def test_production_rejects_selfhost_deploy_mode():
    settings = Settings(environment="production")

    with pytest.raises(StartupSecurityValidationError):
        _validate_startup_security_settings(
            jwt_secret_key="replace-with-strong-secret-value",
            is_production=settings.is_production,
        )
