"""Desktop provider clients preserve proxy bypasses without changing the environment."""

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socketserver
import threading
from types import SimpleNamespace

from fastapi import FastAPI
import httpx
import pytest

from app.api import llm
from app.core.auth import get_current_user_or_default
from app.core import ai_client
from app.core.desktop_http_client import DesktopAsyncHttpxClient, desktop_http_client_kwargs
from app.core.llm_config import ResolvedLlmConfig
from app.database import get_db


@pytest.fixture
def proxy_environment(monkeypatch):
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(key, "http://127.0.0.1:9")
    bypass = "localhost,127.0.0.0/8,::1,fc00::/7,fe80::/10,10.0.0.0/8,100.64.0.0/10"
    for key in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(key, bypass)
    return bypass


@pytest.mark.asyncio
async def test_application_factory_accepts_ipv6_bypass_networks(monkeypatch, proxy_environment):
    monkeypatch.setattr(ai_client, "get_settings", lambda: SimpleNamespace(runtime_mode="desktop"))
    config = ResolvedLlmConfig(
        base_url="http://127.0.0.1:9/v1", api_key="synthetic-key", model="test-model",
        billing_source_hint="selfhost", source="desktop_store",
    )
    client = ai_client._create_openai_client(config)
    await client.close()
    assert client.is_closed()
    assert os.environ["NO_PROXY"] == os.environ["no_proxy"] == proxy_environment


@pytest.fixture
def local_provider_and_proxy(monkeypatch, proxy_environment):
    requests = {"provider": [], "proxy": []}
    servers = []
    threads = []

    def handler_for(role):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def send_body(self, body, content_type="application/json"):
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                requests[role].append(self.path)
                if role == "proxy" and self.path.endswith("/redirect"):
                    self.send_response(302)
                    self.send_header("Location", provider_url + "/after-redirect")
                    self.end_headers()
                else:
                    self.send_body(json.dumps({"route": role}).encode())

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests[role].append(body)
                if body.get("stream"):
                    chunk = {"choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}]}
                    self.send_body(f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode(), "text/event-stream")
                else:
                    content = '{"ok":true}' if body.get("response_format") else "ok"
                    self.send_body(json.dumps({
                        "id": "local-test", "object": "chat.completion", "created": 0, "model": "test-model",
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                                     "finish_reason": "stop"}],
                    }).encode())

        return Handler

    try:
        for role in requests:
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(role))
            servers.append(server)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            thread.start()
            threads.append(thread)
        provider_url, proxy_url = [f"http://127.0.0.1:{server.server_port}" for server in servers]
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            monkeypatch.setenv(key, proxy_url)
        yield provider_url, requests
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)


@pytest.mark.asyncio
async def test_real_direct_proxy_domain_bypass_and_redirect_routes(local_provider_and_proxy, proxy_environment):
    provider_url, requests = local_provider_and_proxy
    async with DesktopAsyncHttpxClient(timeout=2) as client:
        assert (await client.get(provider_url)).json()["route"] == "provider"
        assert (await client.get(provider_url.replace("127.0.0.1", "localhost"))).json()["route"] == "provider"
        assert (await client.get("http://203.0.113.77/remote")).json()["route"] == "proxy"
        assert (await client.get("http://unresolved-provider.invalid/redirect")).json()["route"] == "provider"
    assert client.is_closed
    assert requests["proxy"] == ["http://203.0.113.77/remote", "http://unresolved-provider.invalid/redirect"]
    assert requests["provider"] == ["/", "/", "/after-redirect"]
    assert os.environ["NO_PROXY"] == os.environ["no_proxy"] == proxy_environment


@pytest.mark.asyncio
@pytest.mark.parametrize(("host", "direct"), [
    ("[fc00::1]", True), ("[fdff:ffff::1]", True), ("[fe00::1]", False),
    ("[fe80::1]", True), ("[febf::1]", True), ("[fec0::1]", False),
    ("[fe80::1%25en0]", True), ("[::1]", True),
    ("10.2.3.4", True), ("100.64.0.1", True), ("100.127.255.254", True), ("100.128.0.1", False),
])
async def test_literal_network_boundaries_keep_lan_and_tailscale_direct(proxy_environment, host, direct):
    async with DesktopAsyncHttpxClient() as client:
        assert (client._transport_for_url(httpx.URL(f"http://{host}")) is client._transport) == direct


@pytest.mark.asyncio
async def test_explicit_proxy_and_disabled_environment_keep_httpx_semantics(proxy_environment):
    async with DesktopAsyncHttpxClient(proxy="http://127.0.0.1:9") as client:
        assert client._transport_for_url(httpx.URL("http://10.2.3.4")) is not client._transport
    async with DesktopAsyncHttpxClient(trust_env=False) as client:
        assert client._transport_for_url(httpx.URL("http://203.0.113.77")) is client._transport
    assert desktop_http_client_kwargs("selfhost") == desktop_http_client_kwargs("hosted") == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_generation_uses_real_desktop_provider_transport(monkeypatch, local_provider_and_proxy, stream):
    provider_url, requests = local_provider_and_proxy
    monkeypatch.setattr(ai_client, "get_settings", lambda: SimpleNamespace(runtime_mode="desktop"))
    monkeypatch.setattr(ai_client, "ensure_ai_available_fresh_session", lambda **_kwargs: None)
    config = ResolvedLlmConfig(
        base_url=provider_url + "/v1", api_key="synthetic-key", model="test-model",
        billing_source_hint="selfhost", source="desktop_store",
    )
    if stream:
        assert [part async for part in ai_client.AIClient().generate_stream("hi", llm_config=config)] == ["ok"]
    else:
        assert await ai_client.AIClient().generate("hi", llm_config=config) == "ok"
    assert len(requests["provider"]) == 1
    assert not requests["proxy"]


@pytest.mark.asyncio
async def test_probe_uses_same_real_desktop_transport(monkeypatch, local_provider_and_proxy):
    provider_url, requests = local_provider_and_proxy
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(runtime_mode="desktop"))
    monkeypatch.setattr(llm, "get_llm_config", lambda _request: ResolvedLlmConfig(
        base_url=provider_url + "/v1", api_key="synthetic-key", model="test-model",
        billing_source_hint="selfhost", source="desktop_store",
    ))
    monkeypatch.setattr(llm, "ensure_ai_available", lambda *_args, **_kwargs: None)
    app = FastAPI()
    app.include_router(llm.router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user_or_default] = lambda: SimpleNamespace(id=1)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver", trust_env=False) as client:
        response = await client.post("/api/llm/test", headers={"origin": "http://127.0.0.1:8000"})
    assert response.json()["code"] == "llm_probe_compatible"
    assert len(requests["provider"]) == 3
    assert not requests["proxy"]


@pytest.mark.asyncio
async def test_real_socks_proxy_retains_remote_dns_and_network_bypasses(monkeypatch, local_provider_and_proxy):
    provider_url, requests = local_provider_and_proxy
    destinations = []

    class SocksHandler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            version, count = self.rfile.read(2)
            assert version == 5 and 0 in self.rfile.read(count)
            self.wfile.write(b"\x05\x00")
            version, command, _, address_type = self.rfile.read(4)
            assert (version, command, address_type) == (5, 1, 3)
            hostname = self.rfile.read(self.rfile.read(1)[0]).decode()
            port = int.from_bytes(self.rfile.read(2), "big")
            destinations.append((hostname, port))
            self.wfile.write(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
            while self.rfile.readline() not in (b"\r\n", b""):
                pass
            self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Length: 9\r\n\r\nvia-socks")

    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), SocksHandler) as server:
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                monkeypatch.delenv(key)
            for key in ("ALL_PROXY", "all_proxy"):
                monkeypatch.setenv(key, f"socks5h://127.0.0.1:{server.server_address[1]}")
            async with DesktopAsyncHttpxClient(timeout=2) as client:
                assert (await client.get(provider_url)).json()["route"] == "provider"
                assert (await client.get("http://unresolved-provider.invalid/socks")).text == "via-socks"
            assert destinations == [("unresolved-provider.invalid", 80)]
            assert not requests["proxy"]
        finally:
            server.shutdown()
            thread.join(timeout=2)
