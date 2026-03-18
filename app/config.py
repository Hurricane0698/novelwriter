from typing import Literal

import os
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


MIN_CONTEXT_CHAPTERS = 1
MAX_CONTEXT_CHAPTERS = 5
DEFAULT_CONTEXT_CHAPTERS = 5


def clamp_context_chapters(value: int) -> int:
    return max(MIN_CONTEXT_CHAPTERS, min(MAX_CONTEXT_CHAPTERS, int(value)))


def resolve_context_chapters(value: int | None, *, default: int | None = None) -> int:
    if value is None:
        baseline = DEFAULT_CONTEXT_CHAPTERS if default is None else int(default)
        return clamp_context_chapters(baseline)
    return clamp_context_chapters(value)


class Settings(BaseSettings):
    # Runtime environment (used for production security/logging gates).
    # Canonicalized via `normalized_environment`.
    environment: str = "dev"

    deploy_mode: Literal["hosted", "selfhost"] = "selfhost"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    db_auto_create: bool = False

    max_context_chapters: int = DEFAULT_CONTEXT_CHAPTERS
    outline_chunk_size: int = 100
    default_continuation_tokens: int = 4000
    max_continuation_tokens: int = 16000
    continuation_min_target_ratio: float = 0.9
    continuation_chars_to_tokens_ratio: float = 2.5
    continuation_token_buffer_ratio: float = 0.1
    continuation_prompt_target_overrun_ratio: float = 1.12

    # World generation from free-text settings
    world_generation_chunk_chars: int = 7000
    world_generation_chunk_overlap_chars: int = 500
    world_generation_max_chunks: int = 8
    world_generation_chunk_max_tokens: int = 15000

    # Bootstrap
    bootstrap_window_size: int = 500
    bootstrap_window_step: int = 250
    bootstrap_min_window_count: int = 3
    bootstrap_min_window_ratio: float = 0.005
    bootstrap_llm_temperature: float = 0.3
    bootstrap_max_candidates: int = 500
    bootstrap_common_words_dir: str = "data/common_words"
    bootstrap_stale_job_timeout_seconds: int = 900

    # Derived-asset background jobs
    derived_asset_job_lease_seconds: int = 300
    derived_asset_job_stale_timeout_seconds: int = 900

    # Lorebook Configuration
    lore_max_total_tokens: int = 2000
    lore_default_priority: int = 100
    lore_protagonist_priority: int = 1
    lore_item_priority: int = 50
    lore_location_priority: int = 75
    lore_faction_priority: int = 80
    lore_default_token_budget: int = 500

    # CORS
    cors_allowed_origins: list[str] = ["http://localhost:5173"]

    # JWT Authentication
    jwt_secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Hosted mode: invite code & quota
    invite_code: str = ""
    initial_quota: int = 5
    feedback_bonus_quota: int = 20
    feedback_suggestion_bonus_quota: int = 10
    hosted_max_users: int = 0

    # Hosted/server-side AI safety fuses
    ai_manual_disable: bool = False
    ai_hard_stop_usd: float = 0.0
    llm_default_input_cost_per_million_usd: float = 0.0
    llm_default_output_cost_per_million_usd: float = 0.0

    # Hosted mode: server-side LLM config (used when user doesn't supply headers)
    hosted_llm_base_url: str = ""
    hosted_llm_api_key: str = ""
    hosted_llm_model: str = ""

    # Concurrency: max simultaneous LLM API calls (semaphore-based)
    max_concurrent_llm_calls: int = 50

    # Copilot admission control
    copilot_max_runs_per_session: int = 1
    copilot_max_runs_per_user: int = 2
    copilot_max_runs_global: int = 10
    copilot_max_tool_rounds: int = 8
    copilot_run_queue_timeout_seconds: int = 30
    copilot_run_lease_seconds: int = 300
    copilot_run_stale_timeout_seconds: int = 300

    # Event tracking (product analytics). Selfhost: off by default. Hosted: enable via env.
    enable_event_tracking: bool = False

    # Debug/diagnostics
    enable_debug_endpoints: bool = False

    model_config = ConfigDict(
        env_file=".env",
        extra="ignore"
    )

    @property
    def normalized_environment(self) -> str:
        return (self.environment or "dev").strip().lower()

    @property
    def is_production(self) -> bool:
        return self.normalized_environment in {"production", "prod"}

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Default: prefer `.env` for local/selfhost workflows so project-level config
        # can override user-wide shell exports (e.g., OPENAI_API_KEY in ~/.bashrc).
        #
        # Safety: in production/hosted deployments, OS env must override `.env` so a stray
        # checked-in or copied `.env` can't silently downgrade security settings.
        normalized_env = (os.getenv("ENVIRONMENT") or "").strip().lower()
        normalized_deploy = (os.getenv("DEPLOY_MODE") or "").strip().lower()
        if normalized_env in {"production", "prod"} or normalized_deploy == "hosted":
            return (init_settings, env_settings, dotenv_settings, file_secret_settings)
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)


_settings_instance = None


def get_settings() -> Settings:
    """Get settings instance. Reloads from .env on first call after server restart."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


def reload_settings() -> Settings:
    """Force reload settings from .env file."""
    global _settings_instance
    _settings_instance = Settings()
    return _settings_instance
