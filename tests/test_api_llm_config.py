from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.config as config_mod
from app.api import llm as llm_api
from app.config import Settings
from app.core.auth import get_current_user_or_default
from app.core.desktop_llm_config import DesktopLlmConfigStore
from app.database import get_db


_DESKTOP_ORIGIN = "http://127.0.0.1:8000"


class _TestProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return b"protected:" + plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        prefix = b"protected:"
        if not ciphertext.startswith(prefix):
            raise ValueError("invalid ciphertext")
        return ciphertext[len(prefix) :][::-1]


@pytest.fixture
def desktop_api(monkeypatch, tmp_path):
    settings = Settings(
        environment="desktop",
        deploy_mode="selfhost",
        novwr_desktop_llm_config_path=str(tmp_path / "llm-config.json"),
        _env_file=None,
    )
    monkeypatch.setattr(config_mod, "_settings_instance", settings)

    def make_store() -> DesktopLlmConfigStore:
        return DesktopLlmConfigStore(
            tmp_path / "llm-config.json",
            protector=_TestProtector(),
        )

    monkeypatch.setattr(
        llm_api, "get_desktop_llm_config_store", lambda _settings: make_store()
    )
    import app.core.llm_config as llm_config_mod

    monkeypatch.setattr(
        llm_config_mod,
        "get_desktop_llm_config_store",
        lambda _settings: make_store(),
    )

    app = FastAPI()
    app.include_router(llm_api.router)
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_current_user_or_default] = lambda: SimpleNamespace(
        id=1
    )
    with TestClient(app) as client:
        yield client, make_store


def _put(client: TestClient, payload: dict, *, origin: str | None = _DESKTOP_ORIGIN):
    headers = {} if origin is None else {"origin": origin}
    return client.put("/api/llm/config", json=payload, headers=headers)


def test_desktop_config_persists_across_store_recreation_without_returning_key(
    desktop_api,
):
    client, make_store = desktop_api

    empty = client.get("/api/llm/config")
    assert empty.status_code == 200
    assert empty.json() == {
        "configured": False,
        "base_url": "",
        "model": "",
        "api_key_configured": False,
    }

    saved = _put(
        client,
        {
            "base_url": "https://gateway.example/v1/chat/completions/",
            "api_key": "desktop-secret",
            "model": "model-a",
        },
    )
    assert saved.status_code == 200
    assert saved.json() == {
        "configured": True,
        "base_url": "https://gateway.example/v1",
        "model": "model-a",
        "api_key_configured": True,
    }
    assert "desktop-secret" not in saved.text

    restarted = make_store().load()
    assert restarted is not None
    assert restarted.api_key == "desktop-secret"

    loaded = client.get("/api/llm/config")
    assert loaded.json() == saved.json()
    assert "desktop-secret" not in loaded.text


def test_desktop_config_update_without_key_preserves_existing_secret(desktop_api):
    client, make_store = desktop_api
    assert (
        _put(
            client,
            {
                "base_url": "https://one.example/v1",
                "api_key": "keep-this-key",
                "model": "model-one",
            },
        ).status_code
        == 200
    )

    updated = _put(
        client,
        {
            "base_url": "https://two.example/v1",
            "model": "model-two",
        },
    )

    assert updated.status_code == 200
    stored = make_store().load()
    assert stored is not None
    assert stored.base_url == "https://two.example/v1"
    assert stored.model == "model-two"
    assert stored.api_key == "keep-this-key"


def test_desktop_config_full_update_overwrites_unreadable_saved_config(desktop_api):
    client, make_store = desktop_api
    store = make_store()
    store.path.write_bytes(b"not-json")

    response = _put(
        client,
        {
            "base_url": "https://replacement.example/v1",
            "api_key": "replacement-key",
            "model": "replacement-model",
        },
    )

    assert response.status_code == 200
    stored = make_store().load()
    assert stored is not None
    assert stored.base_url == "https://replacement.example/v1"
    assert stored.api_key == "replacement-key"
    assert stored.model == "replacement-model"


def test_desktop_config_first_save_requires_api_key(desktop_api):
    client, _make_store = desktop_api

    response = _put(
        client,
        {"base_url": "https://example/v1", "model": "model"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "desktop_llm_api_key_required"


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
def test_desktop_config_rejects_api_key_whitespace_and_control_characters(
    desktop_api,
    api_key,
):
    client, _make_store = desktop_api

    response = _put(
        client,
        {
            "base_url": "https://example/v1",
            "api_key": api_key,
            "model": "model",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "llm_api_key_invalid"
    assert api_key not in response.text


@pytest.mark.parametrize(
    ("payload", "secret"),
    (
        (
            {
                "base_url": "https://example/v1",
                "api_key": {"secret": "malformed-secret"},
                "model": "model",
            },
            "malformed-secret",
        ),
        (
            {
                "base_url": "https://example/v1",
                "apiKey": "extra-field-secret",
                "model": "model",
            },
            "extra-field-secret",
        ),
    ),
)
def test_desktop_config_validation_errors_never_echo_api_key_input(
    desktop_api,
    payload,
    secret,
):
    client, _make_store = desktop_api

    response = _put(client, payload)

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "llm_api_key_invalid",
            "message": (
                "LLM API key must be at most 4096 characters and contain no "
                "whitespace or control characters."
            ),
        }
    }
    assert secret not in response.text


def test_llm_validation_route_preserves_openapi_request_schema(desktop_api):
    client, _make_store = desktop_api

    schema = client.get("/openapi.json").json()

    request_schema = schema["paths"]["/api/llm/config"]["put"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    assert request_schema == {"$ref": "#/components/schemas/DesktopLlmConfigPutRequest"}


@pytest.mark.parametrize(
    "base_url",
    (
        " https://example.com/v1",
        "https://example.com/v1 ",
    ),
)
def test_desktop_config_rejects_base_url_whitespace_without_silent_trimming(
    desktop_api,
    base_url,
):
    client, _make_store = desktop_api

    response = _put(
        client,
        {
            "base_url": base_url,
            "api_key": "key",
            "model": "model",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "llm_base_url_invalid"


@pytest.mark.parametrize(
    "origin", (None, "https://evil.example", "http://localhost:8000")
)
def test_desktop_config_mutations_require_exact_app_origin(desktop_api, origin):
    client, _make_store = desktop_api

    response = _put(
        client,
        {
            "base_url": "https://example/v1",
            "api_key": "key",
            "model": "model",
        },
        origin=origin,
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "desktop_origin_forbidden"


def test_desktop_config_delete_clears_saved_credentials(desktop_api):
    client, make_store = desktop_api
    assert (
        _put(
            client,
            {
                "base_url": "https://example/v1",
                "api_key": "key",
                "model": "model",
            },
        ).status_code
        == 200
    )

    response = client.delete(
        "/api/llm/config",
        headers={"origin": _DESKTOP_ORIGIN},
    )

    assert response.status_code == 204
    assert make_store().load() is None


def test_desktop_config_delete_rejects_wrong_origin(desktop_api):
    client, _make_store = desktop_api

    response = client.delete(
        "/api/llm/config",
        headers={"origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "desktop_origin_forbidden"


def test_desktop_config_endpoints_are_not_available_in_selfhost(monkeypatch):
    monkeypatch.setattr(
        config_mod,
        "_settings_instance",
        Settings(deploy_mode="selfhost", _env_file=None),
    )
    app = FastAPI()
    app.include_router(llm_api.router)

    with TestClient(app) as client:
        response = client.get("/api/llm/config")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "desktop_llm_config_desktop_only"


def test_desktop_probe_uses_saved_config_and_requires_origin(desktop_api, monkeypatch):
    client, _make_store = desktop_api
    assert (
        _put(
            client,
            {
                "base_url": "https://probe.example/v1",
                "api_key": "probe-secret",
                "model": "probe-model",
            },
        ).status_code
        == 200
    )

    basic_response = MagicMock(usage=None)
    stream_chunk = MagicMock()
    stream_chunk.choices = [MagicMock(delta=MagicMock(content="ok"))]
    stream_chunk.usage = None

    async def fake_stream():
        yield stream_chunk

    json_response = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"ok": true}'))]
    )
    provider = MagicMock()
    provider.chat.completions.create = AsyncMock(
        side_effect=[basic_response, fake_stream(), json_response]
    )
    constructor = MagicMock(return_value=provider)
    monkeypatch.setattr(llm_api, "AsyncOpenAI", constructor)

    missing_origin = client.post("/api/llm/test")
    assert missing_origin.status_code == 403
    assert constructor.call_count == 0

    wrong_origin = client.post(
        "/api/llm/test",
        headers={"origin": "https://evil.example"},
    )
    assert wrong_origin.status_code == 403
    assert constructor.call_count == 0

    response = client.post(
        "/api/llm/test",
        headers={"origin": _DESKTOP_ORIGIN},
    )

    assert response.status_code == 200
    assert response.json()["code"] == "llm_probe_compatible"
    assert "message" not in response.json()
    assert "error" not in response.json()
    constructor.assert_called_once_with(
        base_url="https://probe.example/v1",
        api_key="probe-secret",
        timeout=10.0,
    )


def test_desktop_probe_rejects_even_empty_llm_override_header(desktop_api, monkeypatch):
    client, _make_store = desktop_api
    monkeypatch.setattr(
        llm_api,
        "AsyncOpenAI",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("provider must not run")
        ),
    )

    response = client.post(
        "/api/llm/test",
        headers={
            "origin": _DESKTOP_ORIGIN,
            "x-llm-api-key": "",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "desktop_llm_override_disabled"


def test_probe_error_never_returns_provider_exception_text(desktop_api, monkeypatch):
    client, _make_store = desktop_api
    secret = 'probe-"quoted"-\\secret-must-not-leak'
    assert (
        _put(
            client,
            {
                "base_url": "https://probe.example/v1",
                "api_key": secret,
                "model": "probe-model",
            },
        ).status_code
        == 200
    )

    escaped_secret = json.dumps(secret)[1:-1]
    provider_error = f"provider rejected {escaped_secret}\r\nAuthorization: {secret}"
    provider = MagicMock()
    provider.chat.completions.create = AsyncMock(
        side_effect=RuntimeError(provider_error),
    )
    monkeypatch.setattr(llm_api, "AsyncOpenAI", lambda **_kwargs: provider)

    response = client.post(
        "/api/llm/test",
        headers={"origin": _DESKTOP_ORIGIN},
    )

    assert response.status_code == 200
    assert response.json()["code"] == "llm_probe_connection_failed"
    assert secret not in response.text
    assert escaped_secret not in response.text
    assert provider_error not in response.text
    assert "message" not in response.json()
    assert "error" not in response.json()


def test_probe_constructor_error_never_returns_exception_text(desktop_api, monkeypatch):
    client, _make_store = desktop_api
    secret = 'constructor-"quoted"-\\secret-must-not-leak'
    assert (
        _put(
            client,
            {
                "base_url": "https://probe.example/v1",
                "api_key": secret,
                "model": "probe-model",
            },
        ).status_code
        == 200
    )

    escaped_secret = json.dumps(secret)[1:-1]
    constructor_error = RuntimeError(
        f"invalid client config {escaped_secret}\r\nAuthorization: {secret}"
    )
    monkeypatch.setattr(
        llm_api,
        "AsyncOpenAI",
        MagicMock(side_effect=constructor_error),
    )

    response = client.post(
        "/api/llm/test",
        headers={"origin": _DESKTOP_ORIGIN},
    )

    assert response.status_code == 200
    assert response.json()["code"] == "llm_probe_connection_failed"
    assert secret not in response.text
    assert escaped_secret not in response.text
    assert str(constructor_error) not in response.text
    assert "message" not in response.json()
    assert "error" not in response.json()
