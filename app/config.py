import json
from typing import Literal

import os
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


MIN_CONTEXT_CHAPTERS = 1
MAX_CONTEXT_CHAPTERS = 10000
DEFAULT_CONTEXT_CHAPTERS = 5


def clamp_context_chapters(value: int) -> int:
    return max(MIN_CONTEXT_CHAPTERS, min(MAX_CONTEXT_CHAPTERS, int(value)))


def resolve_context_chapters(
    value: int | None,
    *,
    default: int | None = None,
    max_value: int | None = None,
) -> int:
    upper_bound = MAX_CONTEXT_CHAPTERS if max_value is None else max(MIN_CONTEXT_CHAPTERS, int(max_value))
    if value is None:
        baseline = DEFAULT_CONTEXT_CHAPTERS if default is None else int(default)
        return max(MIN_CONTEXT_CHAPTERS, min(upper_bound, baseline))
    return max(MIN_CONTEXT_CHAPTERS, min(upper_bound, int(value)))


def normalize_hosted_invite_code(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("invite code cannot be empty")
    return normalized


def _normalize_optional_hosted_invite_meta(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


class HostedInviteCode(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    label: str | None = Field(default=None, max_length=100)
    channel: str | None = Field(default=None, max_length=100)
    invite_batch: str | None = Field(default=None, max_length=100)

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return normalize_hosted_invite_code(value)

    @field_validator("label", "channel", "invite_batch", mode="before")
    @classmethod
    def _normalize_optional_fields(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            return _normalize_optional_hosted_invite_meta(value)
        return value


class Settings(BaseSettings):
    # Runtime environment (used for production security/logging gates).
    # Canonicalized via `normalized_environment`.
    environment: str = "dev"

    deploy_mode: Literal["hosted", "selfhost"] = "selfhost"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # Desktop-only process contract. The Tauri launcher owns this path and the
    # Python runtime never derives it from the install or data directory.
    novwr_desktop_llm_config_path: str = ""

    db_auto_create: bool = False

    max_context_chapters: int = DEFAULT_CONTEXT_CHAPTERS
    default_continuation_tokens: int = 4000
    max_continuation_tokens: int = 32000
    continuation_min_target_ratio: float = 0.9
    continuation_chars_to_tokens_ratio: float = 2.5
    continuation_token_buffer_ratio: float = 0.1
    continuation_prompt_target_overrun_ratio: float = 1.12
    # When trimming continuation output, allow the cut to extend up to this
    # multiple of target_chars forward to the next sentence boundary, so the
    # sentence straddling the target is kept whole instead of dropped (prefer a
    # little over target to severing mid-plot). 1.0 disables forward overshoot.
    continuation_trim_overrun_ratio: float = 1.15

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

    # Hosted mode: auth & quota
    hosted_invite_codes: list[HostedInviteCode] = Field(default_factory=list)
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    github_oauth_redirect_uri: str = ""
    hosted_github_login_enabled: bool = False
    initial_quota: int = 5
    feedback_bonus_quota: int = 20
    feedback_suggestion_bonus_quota: int = 10
    hosted_max_users: int = 0

    # Upload/import
    upload_max_megabytes: int = 30
    upload_chunk_size_bytes: int = 1024 * 1024

    # Hosted/server-side AI safety fuses
    ai_manual_disable: bool = False
    ai_hard_stop_usd: float = 0.0
    llm_default_input_cost_per_million_usd: float = 0.0
    llm_default_output_cost_per_million_usd: float = 0.0

    # Hosted mode: server-side LLM config (used when user doesn't supply headers)
    hosted_llm_base_url: str = ""
    hosted_llm_api_key: str = ""
    hosted_llm_model: str = ""

    # Concurrency: interactive LLM calls share a global fail-fast gate.
    # Background jobs additionally flow through a narrower blocking lane so
    # bootstrap/refinement traffic cannot crowd out foreground continuation.
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
    def runtime_mode(self) -> Literal["hosted", "selfhost", "desktop"]:
        if self.normalized_environment == "desktop":
            return "desktop"
        return self.deploy_mode

    @field_validator("hosted_invite_codes", mode="before")
    @classmethod
    def _parse_hosted_invite_codes(cls, value: object) -> object:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            parsed = json.loads(value)
            return parsed if parsed is not None else []
        return value

    @property
    def is_production(self) -> bool:
        return self.normalized_environment in {"production", "prod"}

    @property
    def hosted_invite_code_entries(self) -> tuple[HostedInviteCode, ...]:
        entries = tuple(self.hosted_invite_codes)
        seen_codes: set[str] = set()
        for entry in entries:
            if entry.code in seen_codes:
                raise RuntimeError("hosted_invite_codes contains duplicate invite codes")
            seen_codes.add(entry.code)
        return entries

    @property
    def hosted_invite_code_lookup(self) -> dict[str, HostedInviteCode]:
        return {entry.code: entry for entry in self.hosted_invite_code_entries}

    @property
    def hosted_invite_login_enabled(self) -> bool:
        return bool(self.hosted_invite_code_entries)

    @model_validator(mode="after")
    def _validate_runtime_mode(self) -> "Settings":
        if self.normalized_environment == "desktop" and self.deploy_mode != "selfhost":
            raise ValueError("desktop environment requires deploy_mode=selfhost")
        return self

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
        # Desktop never reads `.env`; its launcher supplies the complete process contract.
        # In production/hosted deployments, OS env must override `.env` so a stray checked-in
        # or copied file cannot silently downgrade security settings.
        normalized_env = (os.getenv("ENVIRONMENT") or "").strip().lower()
        normalized_deploy = (os.getenv("DEPLOY_MODE") or "").strip().lower()
        if normalized_env == "desktop":
            return (init_settings, env_settings, file_secret_settings)
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
