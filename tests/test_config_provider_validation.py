import pytest
from pydantic import ValidationError

from app.config import Settings


def test_deploy_mode_defaults_to_selfhost():
    assert Settings.model_fields["deploy_mode"].default == "selfhost"


def test_openai_model_default_starts_with_gpt():
    assert Settings.model_fields["openai_model"].default.startswith("gpt-")


def test_settings_validate_background_llm_lane_does_not_exceed_global_capacity():
    with pytest.raises(ValidationError, match="max_background_concurrent_llm_calls cannot exceed"):
        Settings(
            max_concurrent_llm_calls=1,
            max_background_concurrent_llm_calls=2,
            _env_file=None,
        )


def test_settings_reject_desktop_environment_with_hosted_deploy_mode():
    with pytest.raises(
        ValidationError,
        match="deploy_mode",
    ):
        Settings(
            environment="desktop",
            deploy_mode="hosted",
            _env_file=None,
        )
