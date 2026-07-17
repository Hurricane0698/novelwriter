from __future__ import annotations

import pytest

from app.config import Settings
from app.core.desktop_llm_config import DesktopLlmConfigStore, StoredDesktopLlmConfig
from app.core.llm_config import (
    LLM_API_KEY_MAX_LENGTH,
    LLM_CONFIG_API_KEY_INVALID_CODE,
    LLM_CONFIG_BASE_URL_INVALID_CODE,
    LLM_CONFIG_DESKTOP_OVERRIDE_DISABLED_CODE,
    LLM_CONFIG_HOSTED_BYOK_DISABLED_CODE,
    LLM_CONFIG_INCOMPLETE_CODE,
    LLM_CONFIG_MISSING_CODE,
    LlmConfigError,
    LlmConfigValues,
    ResolvedLlmConfig,
    resolve_llm_config,
)


class _TestProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        return ciphertext[::-1]


def _desktop_store(tmp_path) -> DesktopLlmConfigStore:
    store = DesktopLlmConfigStore(
        tmp_path / "llm-config.json",
        protector=_TestProtector(),
    )
    store.save(
        StoredDesktopLlmConfig(
            base_url="https://desktop.example/v1/chat/completions",
            api_key="desktop-key",
            model="desktop-model",
        )
    )
    return store


def test_hosted_uses_only_hosted_settings_without_generic_fallback():
    settings = Settings(
        deploy_mode="hosted",
        hosted_llm_base_url="",
        hosted_llm_api_key="",
        hosted_llm_model="",
        openai_base_url="https://generic.example/v1",
        openai_api_key="generic-key",
        openai_model="generic-model",
        _env_file=None,
    )

    with pytest.raises(LlmConfigError) as exc_info:
        resolve_llm_config(settings=settings)

    assert exc_info.value.code == LLM_CONFIG_MISSING_CODE


def test_hosted_rejects_even_explicit_empty_override_headers():
    settings = Settings(
        deploy_mode="hosted",
        hosted_llm_base_url="https://hosted.example/v1",
        hosted_llm_api_key="hosted-key",
        hosted_llm_model="hosted-model",
        _env_file=None,
    )

    with pytest.raises(LlmConfigError) as exc_info:
        resolve_llm_config(
            settings=settings,
            request_override=LlmConfigValues(provided=True),
        )

    assert exc_info.value.code == LLM_CONFIG_HOSTED_BYOK_DISABLED_CODE


def test_selfhost_requires_complete_explicit_override_including_empty_headers():
    settings = Settings(
        deploy_mode="selfhost",
        openai_base_url="https://settings.example/v1",
        openai_api_key="settings-key",
        openai_model="settings-model",
        _env_file=None,
    )

    with pytest.raises(LlmConfigError) as exc_info:
        resolve_llm_config(
            settings=settings,
            request_override=LlmConfigValues(
                base_url="",
                api_key="",
                model="",
                provided=True,
            ),
        )

    assert exc_info.value.code == LLM_CONFIG_INCOMPLETE_CODE


def test_selfhost_complete_request_override_is_normalized():
    config = resolve_llm_config(
        settings=Settings(deploy_mode="selfhost", _env_file=None),
        request_override=LlmConfigValues(
            base_url="https://request.example/v1/chat/completions/",
            api_key="request-key",
            model=" request-model ",
            provided=True,
        ),
    )

    assert config == ResolvedLlmConfig(
        base_url="https://request.example/v1",
        api_key="request-key",
        model="request-model",
        billing_source_hint="selfhost",
        source="selfhost_request",
    )


@pytest.mark.parametrize(
    "api_key",
    (
        " leading",
        "trailing ",
        "line\nbreak",
        "carriage\rreturn",
        "tab\tkey",
        "zero\u200bwidth",
    ),
)
def test_resolver_rejects_api_key_whitespace_and_control_characters(api_key):
    with pytest.raises(LlmConfigError) as exc_info:
        resolve_llm_config(
            settings=Settings(deploy_mode="selfhost", _env_file=None),
            request_override=LlmConfigValues(
                base_url="https://request.example/v1",
                api_key=api_key,
                model="request-model",
                provided=True,
            ),
        )

    assert exc_info.value.code == LLM_CONFIG_API_KEY_INVALID_CODE


def test_resolver_rejects_api_key_over_maximum_length():
    with pytest.raises(LlmConfigError) as exc_info:
        resolve_llm_config(
            settings=Settings(deploy_mode="selfhost", _env_file=None),
            request_override=LlmConfigValues(
                base_url="https://request.example/v1",
                api_key="k" * (LLM_API_KEY_MAX_LENGTH + 1),
                model="request-model",
                provided=True,
            ),
        )

    assert exc_info.value.code == LLM_CONFIG_API_KEY_INVALID_CODE


def test_resolver_rejects_non_string_api_key_without_coercion():
    with pytest.raises(LlmConfigError) as exc_info:
        resolve_llm_config(
            settings=Settings(deploy_mode="selfhost", _env_file=None),
            request_override=LlmConfigValues(
                base_url="https://request.example/v1",
                api_key=["secret-fragment"],  # type: ignore[arg-type]
                model="request-model",
                provided=True,
            ),
        )

    assert exc_info.value.code == LLM_CONFIG_API_KEY_INVALID_CODE


def test_resolver_accepts_api_key_at_maximum_length_without_mutation():
    api_key = "k" * LLM_API_KEY_MAX_LENGTH

    config = resolve_llm_config(
        settings=Settings(deploy_mode="selfhost", _env_file=None),
        request_override=LlmConfigValues(
            base_url="https://request.example/v1",
            api_key=api_key,
            model="request-model",
            provided=True,
        ),
    )

    assert config.api_key == api_key


def test_resolver_wraps_invalid_base_url_as_structured_config_error():
    with pytest.raises(LlmConfigError) as exc_info:
        resolve_llm_config(
            settings=Settings(deploy_mode="selfhost", _env_file=None),
            request_override=LlmConfigValues(
                base_url="file:///tmp/provider",
                api_key="request-key",
                model="request-model",
                provided=True,
            ),
        )

    assert exc_info.value.code == LLM_CONFIG_BASE_URL_INVALID_CODE


def test_desktop_uses_only_encrypted_store_and_rejects_any_header(tmp_path):
    settings = Settings(
        environment="desktop",
        deploy_mode="selfhost",
        openai_base_url="https://generic.example/v1",
        openai_api_key="generic-key",
        openai_model="generic-model",
        novwr_desktop_llm_config_path=str(tmp_path / "llm-config.json"),
        _env_file=None,
    )
    store = _desktop_store(tmp_path)

    config = resolve_llm_config(settings=settings, desktop_store=store)
    assert config.base_url == "https://desktop.example/v1"
    assert config.model == "desktop-model"
    assert config.source == "desktop_store"

    with pytest.raises(LlmConfigError) as exc_info:
        resolve_llm_config(
            settings=settings,
            desktop_store=store,
            request_override=LlmConfigValues(provided=True),
        )

    assert exc_info.value.code == LLM_CONFIG_DESKTOP_OVERRIDE_DISABLED_CODE


def test_resolved_config_repr_never_contains_secret():
    config = ResolvedLlmConfig(
        base_url="https://example/v1",
        api_key="never-print-this",
        model="model",
        billing_source_hint="selfhost",
        source="selfhost_settings",
    )

    assert "never-print-this" not in repr(config)


def test_auto_bootstrap_readiness_propagates_corrupt_desktop_store(monkeypatch):
    from app.core.world import bootstrap_queue

    monkeypatch.setattr(
        bootstrap_queue,
        "resolve_llm_config",
        lambda **_kwargs: (_ for _ in ()).throw(
            LlmConfigError(
                code="desktop_llm_config_unreadable",
                message="unreadable",
                status_code=500,
            )
        ),
    )

    with pytest.raises(LlmConfigError) as exc_info:
        bootstrap_queue._auto_bootstrap_llm_ready(
            Settings(environment="desktop", deploy_mode="selfhost", _env_file=None)
        )

    assert exc_info.value.code == "desktop_llm_config_unreadable"
