"""macOS configuration uses one scoped Keychain record and no plaintext file."""

from __future__ import annotations

import json

import pytest

from app.core.desktop_llm_config import DesktopLlmConfigStoreError, StoredDesktopLlmConfig


class MemoryKeychain:
    def __init__(self):
        self.items = {}
        self.failure = None

    def read(self, account):
        if self.failure == "read":
            raise DesktopLlmConfigStoreError(code="desktop_llm_config_crypto_failed", message="Keychain unavailable")
        return self.items.get(account)

    def write(self, account, payload):
        if self.failure == "write":
            raise DesktopLlmConfigStoreError(code="desktop_llm_config_crypto_failed", message="Keychain unavailable")
        self.items[account] = payload

    def delete(self, account):
        if self.failure == "delete":
            raise DesktopLlmConfigStoreError(code="desktop_llm_config_crypto_failed", message="Keychain unavailable")
        self.items.pop(account, None)


def make_store(tmp_path, keychain):
    from app.core.desktop_llm_config import MacKeychainLlmConfigStore

    return MacKeychainLlmConfigStore(tmp_path / "llm-config.json", keychain=keychain)


def test_keychain_round_trip_update_restart_and_delete_are_profile_scoped(tmp_path):
    keychain = MemoryKeychain()
    store = make_store(tmp_path, keychain)
    original = StoredDesktopLlmConfig(base_url="https://example.com/v1/chat/completions/", api_key="secret-one", model=" model-one ")
    assert store.load() is None
    store.save(original)
    assert not store.path.exists()
    assert not list(tmp_path.rglob("*"))
    restarted = make_store(tmp_path, keychain)
    assert restarted.load() == StoredDesktopLlmConfig(base_url="https://example.com/v1", api_key="secret-one", model="model-one")
    changed = StoredDesktopLlmConfig(base_url="https://two.example/v1", api_key="secret-two", model="model-two")
    restarted.save(changed)
    assert len(keychain.items) == 1 and restarted.load() == changed
    other = make_store(tmp_path / "other-profile", keychain)
    assert other.account != store.account
    other.save(original)
    restarted.delete()
    restarted.delete()
    assert restarted.load() is None and other.load() is not None


@pytest.mark.parametrize("operation", ["read", "write", "delete"])
def test_keychain_errors_preserve_old_configuration_without_secret_in_error(tmp_path, operation):
    keychain = MemoryKeychain()
    store = make_store(tmp_path, keychain)
    original = StoredDesktopLlmConfig(base_url="https://example.com/v1", api_key="never-log-original", model="model")
    store.save(original)
    keychain.failure = operation
    with pytest.raises(DesktopLlmConfigStoreError) as caught:
        if operation == "write":
            store.save(StoredDesktopLlmConfig(base_url=original.base_url, api_key="never-log-new", model="new"))
        elif operation == "delete":
            store.delete()
        else:
            store.load()
    assert "never-log" not in str(caught.value)
    keychain.failure = None
    assert store.load() == original
    assert not store.path.exists()


def test_keychain_invalid_config_and_corrupt_payload_use_existing_error_contract(tmp_path):
    keychain = MemoryKeychain()
    store = make_store(tmp_path, keychain)
    with pytest.raises(DesktopLlmConfigStoreError, match="API key"):
        store.save(StoredDesktopLlmConfig(base_url="https://example.com/v1", api_key="invalid\nkey", model="model"))
    assert not keychain.items
    keychain.items[store.account] = json.dumps({"version": 999, "api_key": "private"}).encode()
    with pytest.raises(DesktopLlmConfigStoreError) as caught:
        store.load()
    assert caught.value.code == "desktop_llm_config_unreadable"
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_llm_store_factory_dispatches_platform_without_changing_injected_protectors(tmp_path, monkeypatch, platform):
    import app.core.desktop_llm_config as desktop
    from app.config import Settings
    from app.core.llm_config import get_desktop_llm_config_store

    marker = object()
    protector = object()
    monkeypatch.setattr(desktop.sys, "platform", platform)
    monkeypatch.setattr(desktop, "MacKeychainLlmConfigStore", lambda path: marker)
    monkeypatch.setattr(desktop, "WindowsDataProtector", lambda: protector)
    settings = Settings(novwr_desktop_llm_config_path=str(tmp_path / "llm-config.json"), _env_file=None)
    store = get_desktop_llm_config_store(settings)
    if platform == "darwin":
        assert store is marker
    else:
        assert isinstance(store, desktop.DesktopLlmConfigStore) and store._protector is protector
    injected = get_desktop_llm_config_store(settings, protector=protector)
    assert isinstance(injected, desktop.DesktopLlmConfigStore) and injected._protector is protector
