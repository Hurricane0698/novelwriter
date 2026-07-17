from __future__ import annotations

import base64
import json

import pytest

from app.core.desktop_llm_config import (
    DESKTOP_LLM_CONFIG_SCHEMA_VERSION,
    DesktopLlmConfigStore,
    DesktopLlmConfigStoreError,
    StoredDesktopLlmConfig,
)
from app.core.llm_api_key import LLM_API_KEY_MAX_LENGTH


class _TestProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return b"protected:" + plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        prefix = b"protected:"
        if not ciphertext.startswith(prefix):
            raise ValueError("invalid ciphertext")
        return ciphertext[len(prefix) :][::-1]


def _store(tmp_path) -> DesktopLlmConfigStore:
    return DesktopLlmConfigStore(
        tmp_path / "llm-config.json",
        protector=_TestProtector(),
    )


def _write_encrypted_payload(store: DesktopLlmConfigStore, payload: dict) -> None:
    plaintext = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    ciphertext = _TestProtector().protect(plaintext)
    store.path.write_text(
        json.dumps(
            {
                "version": DESKTOP_LLM_CONFIG_SCHEMA_VERSION,
                "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def test_store_round_trip_is_encrypted_normalized_and_restart_safe(tmp_path):
    store = _store(tmp_path)
    store.save(
        StoredDesktopLlmConfig(
            base_url="https://gateway.example/v1/chat/completions/",
            api_key="desktop-secret",
            model="  model-x  ",
        )
    )

    raw = store.path.read_bytes()
    envelope = json.loads(raw)
    assert envelope["version"] == DESKTOP_LLM_CONFIG_SCHEMA_VERSION
    assert set(envelope) == {"version", "ciphertext"}
    assert b"desktop-secret" not in raw
    assert b"gateway.example" not in raw
    assert b"model-x" not in raw

    restarted_store = _store(tmp_path)
    assert restarted_store.load() == StoredDesktopLlmConfig(
        base_url="https://gateway.example/v1",
        api_key="desktop-secret",
        model="model-x",
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
        "k" * (LLM_API_KEY_MAX_LENGTH + 1),
    ),
)
def test_store_rejects_invalid_api_key_without_silent_normalization(
    tmp_path,
    api_key,
):
    store = _store(tmp_path)

    with pytest.raises(DesktopLlmConfigStoreError) as exc_info:
        store.save(
            StoredDesktopLlmConfig(
                base_url="https://example/v1",
                api_key=api_key,
                model="model",
            )
        )

    assert exc_info.value.code == "llm_api_key_invalid"
    assert not store.path.exists()


def test_store_rejects_invalid_api_key_when_loading_encrypted_payload(tmp_path):
    store = _store(tmp_path)
    _write_encrypted_payload(
        store,
        {
            "version": DESKTOP_LLM_CONFIG_SCHEMA_VERSION,
            "base_url": "https://example/v1",
            "api_key": " persisted-secret ",
            "model": "model",
        },
    )

    with pytest.raises(DesktopLlmConfigStoreError) as exc_info:
        store.load()

    assert exc_info.value.code == "llm_api_key_invalid"


def test_store_rejects_non_string_api_key_in_encrypted_payload(tmp_path):
    store = _store(tmp_path)
    _write_encrypted_payload(
        store,
        {
            "version": DESKTOP_LLM_CONFIG_SCHEMA_VERSION,
            "base_url": "https://example/v1",
            "api_key": ["secret-fragment"],
            "model": "model",
        },
    )

    with pytest.raises(DesktopLlmConfigStoreError) as exc_info:
        store.load()

    assert exc_info.value.code == "llm_api_key_invalid"


@pytest.mark.parametrize(
    "config",
    (
        StoredDesktopLlmConfig(base_url="", api_key="key", model="model"),
        StoredDesktopLlmConfig(
            base_url="https://example/v1", api_key="", model="model"
        ),
        StoredDesktopLlmConfig(base_url="https://example/v1", api_key="key", model=" "),
    ),
)
def test_store_rejects_incomplete_internal_writes(tmp_path, config):
    store = _store(tmp_path)

    with pytest.raises(DesktopLlmConfigStoreError) as exc_info:
        store.save(config)

    assert exc_info.value.code == "desktop_llm_config_invalid"
    assert not store.path.exists()


def test_store_wraps_invalid_base_url_as_desktop_config_error(tmp_path):
    store = _store(tmp_path)

    with pytest.raises(DesktopLlmConfigStoreError) as exc_info:
        store.save(
            StoredDesktopLlmConfig(
                base_url="https://token@example.com/v1",
                api_key="key",
                model="model",
            )
        )

    assert exc_info.value.code == "desktop_llm_config_invalid"
    assert not store.path.exists()


def test_store_rejects_corrupt_or_unversioned_payload(tmp_path):
    store = _store(tmp_path)
    store.path.write_text('{"version":1,"ciphertext":"not-base64"}\n', encoding="utf-8")

    with pytest.raises(DesktopLlmConfigStoreError) as exc_info:
        store.load()

    assert exc_info.value.code == "desktop_llm_config_unreadable"


def test_secret_fields_are_excluded_from_repr():
    config = StoredDesktopLlmConfig(
        base_url="https://example/v1",
        api_key="never-print-this",
        model="model",
    )

    assert "never-print-this" not in repr(config)


def test_atomic_replace_failure_preserves_existing_config(monkeypatch, tmp_path):
    import app.core.desktop_llm_config as desktop_llm_config

    store = _store(tmp_path)
    original = StoredDesktopLlmConfig(
        base_url="https://one.example/v1",
        api_key="original-key",
        model="model-one",
    )
    store.save(original)

    monkeypatch.setattr(
        desktop_llm_config.os,
        "replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(DesktopLlmConfigStoreError) as exc_info:
        store.save(
            StoredDesktopLlmConfig(
                base_url="https://two.example/v1",
                api_key="replacement-key",
                model="model-two",
            )
        )

    assert exc_info.value.code == "desktop_llm_config_write_failed"
    assert store.load() == original
    assert list(tmp_path.glob(".llm-config.json.*.tmp")) == []


def test_delete_is_idempotent(tmp_path):
    store = _store(tmp_path)

    store.delete()
    store.save(
        StoredDesktopLlmConfig(
            base_url="https://example.com/v1",
            api_key="key",
            model="model",
        )
    )
    store.delete()
    store.delete()

    assert store.load() is None
