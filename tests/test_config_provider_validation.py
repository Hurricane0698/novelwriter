from app.config import Settings


def test_deploy_mode_defaults_to_selfhost():
    assert Settings.model_fields["deploy_mode"].default == "selfhost"


def test_openai_model_default_starts_with_gpt():
    assert Settings.model_fields["openai_model"].default.startswith("gpt-")
