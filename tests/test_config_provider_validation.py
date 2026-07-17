import pytest
from pydantic import ValidationError

from app.config import Settings


def test_deploy_mode_defaults_to_selfhost():
    assert Settings.model_fields["deploy_mode"].default == "selfhost"


def test_openai_model_default_starts_with_gpt():
    assert Settings.model_fields["openai_model"].default.startswith("gpt-")


def test_settings_do_not_keep_unwired_provider_fields():
    model_fields = Settings.model_fields

    assert "deepseek_api_key" not in model_fields
    assert "deepseek_base_url" not in model_fields
    assert "deepseek_model" not in model_fields


def test_settings_do_not_keep_removed_lorebook_fields():
    model_fields = Settings.model_fields

    assert "lore_max_total_tokens" not in model_fields
    assert "lore_default_priority" not in model_fields
    assert "lore_default_token_budget" not in model_fields


def test_settings_do_not_keep_dead_outline_generation_knobs():
    assert "outline_chunk_size" not in Settings.model_fields


def test_settings_validate_background_llm_lane_does_not_exceed_global_capacity():
    with pytest.raises(ValidationError, match="max_background_concurrent_llm_calls cannot exceed"):
        Settings(
            max_concurrent_llm_calls=1,
            max_background_concurrent_llm_calls=2,
            _env_file=None,
        )
