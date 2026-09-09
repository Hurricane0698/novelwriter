"""Opt-in native macOS checks, scoped to freshly generated task-only items."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from app.core.desktop_llm_config import (
    DesktopLlmConfigStoreError,
    MacKeychainLlmConfigStore,
    StoredDesktopLlmConfig,
)


pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("NOVWR_TEST_MACOS_KEYCHAIN") != "1",
    reason="requires explicit native Keychain smoke-test opt-in on macOS",
)


@pytest.fixture
def native_store(tmp_path):
    from app.core.macos_keychain import MacKeychain

    service = "com.novwr.test.macos-20260908." + uuid.uuid4().hex
    keychain = MacKeychain(service=service)
    store = MacKeychainLlmConfigStore(tmp_path / "isolated-profile" / "llm-config.json", keychain=keychain)
    try:
        yield store, keychain, service
    finally:
        # Exact service/account deletion only; never query a user's item list.
        store.delete()
        assert store.load() is None


def test_native_keychain_round_trip_update_and_fresh_process(native_store):
    store, _keychain, service = native_store
    assert store.load() is None
    secret = "novwr-test-" + uuid.uuid4().hex
    initial = StoredDesktopLlmConfig(base_url="https://test.example/v1", api_key=secret, model="test-model")
    store.save(initial)
    assert store.load() == initial
    assert not store.path.exists() and not store.path.parent.exists()
    updated = StoredDesktopLlmConfig(base_url=initial.base_url, api_key=secret + "-updated", model="changed-model")
    store.save(updated)
    assert store.load() == updated
    script = """
import hashlib
from pathlib import Path
import sys
from app.core.desktop_llm_config import MacKeychainLlmConfigStore
from app.core.macos_keychain import MacKeychain
store = MacKeychainLlmConfigStore(Path(sys.argv[1]), keychain=MacKeychain(service=sys.argv[2]))
config = store.load()
assert config is not None and config.model == 'changed-model'
assert hashlib.sha256(config.api_key.encode()).hexdigest() == sys.argv[3]
print('restart-ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(store.path), service, hashlib.sha256(updated.api_key.encode()).hexdigest()],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30, check=True,
    )
    assert result.stdout.strip() == "restart-ok"
    assert updated.api_key not in result.stdout + result.stderr
    store.delete()
    store.delete()
    assert store.load() is None


@pytest.mark.parametrize("operation", ["save", "delete"])
def test_native_keychain_failure_preserves_prior_item(native_store, monkeypatch, operation):
    store, keychain, _service = native_store
    original = StoredDesktopLlmConfig(base_url="https://test.example/v1", api_key="novwr-test-" + uuid.uuid4().hex, model="original")
    store.save(original)
    with monkeypatch.context() as patch:
        # Inject a native OSStatus denial without changing the real item.
        patch.setattr(keychain._security, "SecItemUpdate" if operation == "save" else "SecItemDelete", lambda *_args: -25293)
        with pytest.raises(DesktopLlmConfigStoreError) as caught:
            if operation == "save":
                store.save(StoredDesktopLlmConfig(base_url=original.base_url, api_key="novwr-test-new", model="new"))
            else:
                store.delete()
        assert caught.value.code == "desktop_llm_config_crypto_failed"
        assert original.api_key not in str(caught.value)
    assert store.load() == original


def test_desktop_api_uses_native_keychain_without_returning_secret(native_store, monkeypatch, caplog):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.config as config_module
    from app.api import llm as llm_api
    from app.config import Settings

    store, keychain, _service = native_store
    monkeypatch.setattr(config_module, "_settings_instance", Settings(
        environment="desktop", deploy_mode="selfhost",
        novwr_desktop_llm_config_path=str(store.path), _env_file=None,
    ))
    monkeypatch.setattr(llm_api, "get_desktop_llm_config_store", lambda _settings: MacKeychainLlmConfigStore(store.path, keychain=keychain))
    app = FastAPI()
    app.include_router(llm_api.router)
    secret = "novwr-test-" + uuid.uuid4().hex
    headers = {"origin": "http://127.0.0.1:8000"}
    with TestClient(app) as client:
        response = client.put("/api/llm/config", headers=headers, json={"base_url": "https://test.example/v1", "api_key": secret, "model": "first"})
        assert response.status_code == 200 and secret not in response.text
        response = client.get("/api/llm/config")
        assert response.json()["api_key_configured"] is True and secret not in response.text
        response = client.put("/api/llm/config", headers=headers, json={"base_url": "https://test.example/v1", "model": "second"})
        assert response.status_code == 200 and store.load().api_key == secret
        assert store.load().model == "second" and not store.path.exists()
        assert client.delete("/api/llm/config", headers=headers).status_code == 204
        assert client.get("/api/llm/config").json()["configured"] is False
    assert secret not in caplog.text
