from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.config import Settings, get_settings
from app.core.desktop_llm_config import (
    DesktopLlmConfigStore,
    DesktopLlmConfigStoreError,
    StoredDesktopLlmConfig,
    WindowsDataProtector,
)
from app.core.llm_api_key import (
    LLM_API_KEY_INVALID_CODE as LLM_CONFIG_API_KEY_INVALID_CODE,
    LLM_API_KEY_INVALID_MESSAGE as LLM_CONFIG_API_KEY_INVALID_MESSAGE,
    LLM_API_KEY_MAX_LENGTH as LLM_API_KEY_MAX_LENGTH,
    LlmApiKeyError,
    validate_llm_api_key as _validate_llm_api_key,
)
from app.core.llm_endpoint import OpenAIBaseUrlError, normalize_openai_base_url


BillingSource = Literal["hosted", "selfhost"]
LlmConfigSource = Literal[
    "hosted_settings",
    "selfhost_settings",
    "selfhost_request",
    "desktop_store",
]

LLM_CONFIG_MISSING_CODE = "llm_config_missing"
LLM_CONFIG_INCOMPLETE_CODE = "llm_config_incomplete"
LLM_CONFIG_BASE_URL_INVALID_CODE = "llm_base_url_invalid"
LLM_CONFIG_HOSTED_BYOK_DISABLED_CODE = "hosted_byok_disabled"
LLM_CONFIG_DESKTOP_OVERRIDE_DISABLED_CODE = "desktop_llm_override_disabled"
LLM_CONFIG_DESKTOP_ONLY_CODE = "desktop_llm_config_desktop_only"


class LlmConfigError(RuntimeError):
    def __init__(self, *, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code

    @property
    def detail(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


@dataclass(frozen=True, slots=True)
class LlmConfigValues:
    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False)
    model: str | None = None
    provided: bool = False

    def has_any_value(self) -> bool:
        return (
            self.provided
            or bool(str(self.base_url or "").strip())
            or self.api_key is not None
            or bool(str(self.model or "").strip())
        )

    def is_complete(self) -> bool:
        return bool(
            str(self.base_url or "").strip()
            and self.api_key is not None
            and self.api_key != ""
            and str(self.model or "").strip()
        )


@dataclass(frozen=True, slots=True)
class ResolvedLlmConfig:
    base_url: str
    api_key: str = field(repr=False)
    model: str
    billing_source_hint: BillingSource
    source: LlmConfigSource


def validate_llm_api_key(value: object) -> str:
    try:
        return _validate_llm_api_key(value)
    except LlmApiKeyError as exc:
        raise LlmConfigError(
            code=LLM_CONFIG_API_KEY_INVALID_CODE,
            message=LLM_CONFIG_API_KEY_INVALID_MESSAGE,
        ) from exc


def normalize_llm_config_values(
    values: LlmConfigValues,
    *,
    billing_source_hint: BillingSource,
    source: LlmConfigSource,
) -> ResolvedLlmConfig:
    raw_base_url = str(values.base_url or "")
    raw_api_key = values.api_key if values.api_key is not None else ""
    api_key = validate_llm_api_key(raw_api_key)
    model = str(values.model or "").strip()
    present = [bool(raw_base_url.strip()), bool(api_key), bool(model)]
    if not any(present):
        raise LlmConfigError(
            code=LLM_CONFIG_MISSING_CODE,
            message="LLM configuration is required before using AI features.",
        )
    if not all(present):
        raise LlmConfigError(
            code=LLM_CONFIG_INCOMPLETE_CODE,
            message="LLM configuration requires base URL, API key, and model together.",
        )
    try:
        base_url = normalize_openai_base_url(raw_base_url)
    except OpenAIBaseUrlError as exc:
        raise LlmConfigError(
            code=LLM_CONFIG_BASE_URL_INVALID_CODE,
            message=(
                "LLM base URL must be an absolute HTTP(S) URL without credentials, "
                "query, fragment, whitespace, or control characters."
            ),
        ) from exc
    return ResolvedLlmConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        billing_source_hint=billing_source_hint,
        source=source,
    )


def get_desktop_llm_config_store(
    settings: Settings | None = None,
    *,
    protector=None,
) -> DesktopLlmConfigStore:
    resolved_settings = settings or get_settings()
    configured_path = str(resolved_settings.novwr_desktop_llm_config_path or "").strip()
    if not configured_path:
        raise LlmConfigError(
            code="desktop_llm_config_path_missing",
            message="Desktop LLM configuration path is missing from the runtime contract.",
            status_code=500,
        )
    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        raise LlmConfigError(
            code="desktop_llm_config_path_invalid",
            message="Desktop LLM configuration path must be absolute.",
            status_code=500,
        )
    return DesktopLlmConfigStore(path, protector=protector or WindowsDataProtector())


def _desktop_config(
    settings: Settings,
    *,
    desktop_store: DesktopLlmConfigStore | None,
) -> ResolvedLlmConfig:
    try:
        stored = (desktop_store or get_desktop_llm_config_store(settings)).load()
    except DesktopLlmConfigStoreError as exc:
        raise LlmConfigError(code=exc.code, message=str(exc), status_code=500) from exc
    if stored is None:
        raise LlmConfigError(
            code=LLM_CONFIG_MISSING_CODE,
            message="Configure an AI model in desktop settings before using AI features.",
        )
    return normalize_llm_config_values(
        LlmConfigValues(
            base_url=stored.base_url,
            api_key=stored.api_key,
            model=stored.model,
        ),
        billing_source_hint="selfhost",
        source="desktop_store",
    )


def resolve_llm_config(
    *,
    settings: Settings | None = None,
    request_override: LlmConfigValues | None = None,
    desktop_store: DesktopLlmConfigStore | None = None,
) -> ResolvedLlmConfig:
    resolved_settings = settings or get_settings()
    override = request_override or LlmConfigValues()
    runtime_mode = resolved_settings.runtime_mode

    if runtime_mode == "hosted":
        if override.has_any_value():
            raise LlmConfigError(
                code=LLM_CONFIG_HOSTED_BYOK_DISABLED_CODE,
                message="Hosted beta uses platform-managed AI credentials only.",
            )
        return normalize_llm_config_values(
            LlmConfigValues(
                base_url=resolved_settings.hosted_llm_base_url,
                api_key=resolved_settings.hosted_llm_api_key,
                model=resolved_settings.hosted_llm_model,
            ),
            billing_source_hint="hosted",
            source="hosted_settings",
        )

    if runtime_mode == "desktop":
        if override.has_any_value():
            raise LlmConfigError(
                code=LLM_CONFIG_DESKTOP_OVERRIDE_DISABLED_CODE,
                message="Desktop AI configuration must be managed through desktop settings.",
            )
        return _desktop_config(resolved_settings, desktop_store=desktop_store)

    if override.has_any_value():
        if not override.is_complete():
            raise LlmConfigError(
                code=LLM_CONFIG_INCOMPLETE_CODE,
                message="LLM configuration requires base URL, API key, and model together.",
            )
        return normalize_llm_config_values(
            override,
            billing_source_hint="selfhost",
            source="selfhost_request",
        )
    return normalize_llm_config_values(
        LlmConfigValues(
            base_url=resolved_settings.openai_base_url,
            api_key=resolved_settings.openai_api_key,
            model=resolved_settings.openai_model,
        ),
        billing_source_hint="selfhost",
        source="selfhost_settings",
    )


def save_desktop_llm_config(
    store: DesktopLlmConfigStore,
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> ResolvedLlmConfig:
    config = normalize_llm_config_values(
        LlmConfigValues(base_url=base_url, api_key=api_key, model=model),
        billing_source_hint="selfhost",
        source="desktop_store",
    )
    try:
        store.save(
            StoredDesktopLlmConfig(
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
            )
        )
    except DesktopLlmConfigStoreError as exc:
        raise LlmConfigError(code=exc.code, message=str(exc), status_code=500) from exc
    return config


def load_desktop_llm_config(
    store: DesktopLlmConfigStore,
) -> StoredDesktopLlmConfig | None:
    try:
        return store.load()
    except DesktopLlmConfigStoreError as exc:
        raise LlmConfigError(code=exc.code, message=str(exc), status_code=500) from exc


def delete_desktop_llm_config(store: DesktopLlmConfigStore) -> None:
    try:
        store.delete()
    except DesktopLlmConfigStoreError as exc:
        raise LlmConfigError(code=exc.code, message=str(exc), status_code=500) from exc
