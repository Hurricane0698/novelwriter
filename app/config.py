from typing import Literal

import os
from pydantic import ConfigDict, model_validator
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

    deploy_mode: Literal["selfhost"] = "selfhost"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # Desktop-only process contract. The Tauri launcher owns this path and the
    # Python runtime never derives it from the install or data directory.
    novwr_desktop_llm_config_path: str = ""

    db_auto_create: bool = False

    max_context_chapters: int = DEFAULT_CONTEXT_CHAPTERS
    default_continuation_tokens: int = 4000
    max_continuation_tokens: int = 16000
    continuation_min_target_ratio: float = 0.9
    continuation_chars_to_tokens_ratio: float = 2.5
    continuation_token_buffer_ratio: float = 0.1
    continuation_prompt_target_overrun_ratio: float = 1.12
    # When trimming continuation output, allow the cut to extend up to this
    # multiple of target_chars forward to the next sentence boundary, so the
    # sentence straddling the target is kept whole instead of dropped (prefer a
    # little over target to severing mid-plot). 1.0 disables forward overshoot.
    continuation_trim_overrun_ratio: float = 1.15

    # User-reviewed, ranged context-summary generation and injection budgets.
    context_summary_max_range_chapters: int = 100
    context_summary_source_max_chars: int = 120_000
    context_summary_injection_max_chars: int = 40_000
    context_summary_generation_max_tokens: int = 4_000

    # World generation from free-text settings
    world_generation_chunk_chars: int = 7000
    world_generation_chunk_overlap_chars: int = 500
    world_generation_max_chunks: int = 8
    world_generation_chunk_max_tokens: int = 15000

    # Bootstrap
    bootstrap_llm_temperature: float = 0.3
    bootstrap_llm_timeout_seconds: int = 120
    bootstrap_max_candidates: int = 500
    bootstrap_common_words_dir: str = "data/common_words"
    bootstrap_stale_job_timeout_seconds: int = 900

    # Derived-asset background jobs
    derived_asset_job_lease_seconds: int = 300
    derived_asset_job_stale_timeout_seconds: int = 900

    # Ingest/import jobs and long-file policy
    ingest_job_lease_seconds: int = 300
    ingest_job_stale_timeout_seconds: int = 900
    ingest_large_source_bytes: int = 2 * 1024 * 1024
    ingest_large_source_chars: int = 400_000
    ingest_large_chapter_count: int = 120
    hosted_job_worker_poll_seconds: float = 2.0

    # CORS
    cors_allowed_origins: list[str] = ["http://localhost:5173"]

    # JWT Authentication
    jwt_secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Upload/import
    upload_max_megabytes: int = 30
    upload_chunk_size_bytes: int = 1024 * 1024

    llm_default_input_cost_per_million_usd: float = 0.0
    llm_default_output_cost_per_million_usd: float = 0.0

    # Per Python process (shared across its threads/event loops), not per app,
    # provider account or deployment. Server and worker have independent pools.
    # Background calls also take the narrower blocking lane in their process.
    max_concurrent_llm_calls: int = 50
    max_background_concurrent_llm_calls: int = 1
    generation_run_stale_timeout_seconds: int = 900

    # Copilot admission control
    copilot_max_runs_per_session: int = 1
    copilot_max_runs_per_user: int = 2
    copilot_max_runs_global: int = 10
    copilot_max_tool_rounds: int = 8
    copilot_run_queue_timeout_seconds: int = 30
    copilot_run_lease_seconds: int = 300
    copilot_run_stale_timeout_seconds: int = 300

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
    def runtime_mode(self) -> Literal["selfhost", "desktop"]:
        if self.normalized_environment == "desktop":
            return "desktop"
        return self.deploy_mode

    @property
    def is_production(self) -> bool:
        return self.normalized_environment in {"production", "prod"}

    @model_validator(mode="after")
    def _validate_llm_concurrency(self) -> "Settings":
        if int(self.max_concurrent_llm_calls) < 1:
            raise ValueError("max_concurrent_llm_calls must be >= 1")
        if int(self.max_background_concurrent_llm_calls) < 1:
            raise ValueError("max_background_concurrent_llm_calls must be >= 1")
        if int(self.max_background_concurrent_llm_calls) > int(self.max_concurrent_llm_calls):
            raise ValueError(
                "max_background_concurrent_llm_calls cannot exceed max_concurrent_llm_calls"
            )
        return self

    @model_validator(mode="after")
    def _validate_context_summary_limits(self) -> "Settings":
        for field_name in (
            "context_summary_max_range_chapters",
            "context_summary_source_max_chars",
            "context_summary_injection_max_chars",
            "context_summary_generation_max_tokens",
        ):
            if int(getattr(self, field_name)) < 1:
                raise ValueError(f"{field_name} must be >= 1")
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Prefer `.env` for local/selfhost workflows so project-level config
        # can override user-wide shell exports (e.g., OPENAI_API_KEY in ~/.bashrc).
        #
        # Desktop never reads `.env`; its launcher supplies the complete process contract.
        # In production deployments, OS env must override `.env` so a stray checked-in
        # or copied file cannot silently downgrade security settings.
        normalized_env = (os.getenv("ENVIRONMENT") or "").strip().lower()
        if normalized_env == "desktop":
            return (init_settings, env_settings, file_secret_settings)
        if normalized_env in {"production", "prod"} or os.getenv("DEPLOY_MODE", "selfhost") != "selfhost":
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
