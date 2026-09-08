"""Exercise the public probe endpoint through the real SDK and a local transport."""

import json
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
import pytest

from app.api import llm
from app.core.auth import get_current_user_or_default
from app.database import get_db


@pytest.fixture
def probe(monkeypatch):
    requests = []
    usage = []
    responses = []

    def provider(request):
        body = json.loads(request.content)
        requests.append(body)
        if body.get("stream"):
            chunk = {"id": "stream", "object": "chat.completion.chunk", "created": 0,
                     "model": "reasoner", "choices": [{"index": 0, "delta": {"content": "ok"},
                                                       "finish_reason": None}]}
            return httpx.Response(200, text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n",
                                  headers={"content-type": "text/event-stream"})
        if "response_format" in body:
            result = responses.pop(0)
            if isinstance(result, int):
                return httpx.Response(result, json={"error": {"message": "response_format json_object is not supported" if result == 400 else "Temporary outage with secret-token", "type": "invalid_request_error"}})
            content, reason, tokens = result
        else:
            content, reason, tokens = "", "length", 1
        return httpx.Response(200, json={
            "id": "probe", "object": "chat.completion", "created": 0, "model": "reasoner",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": reason}],
            "usage": {"prompt_tokens": 5, "completion_tokens": tokens,
                      "total_tokens": 5 + tokens},
        })

    monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kwargs: AsyncOpenAI(
        **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(provider)),
    ))
    monkeypatch.setattr(llm, "get_llm_config", lambda request: SimpleNamespace(
        base_url="https://provider.test/v1", api_key="test-key", model="reasoner",
        billing_source_hint="hosted",
    ))
    monkeypatch.setattr(llm, "ensure_ai_available", lambda *args, **kwargs: None)
    monkeypatch.setattr(llm, "_record_usage", lambda *args, **kwargs: usage.append((args, kwargs)))
    app = FastAPI()
    app.include_router(llm.router)
    app.dependency_overrides[get_current_user_or_default] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_db] = lambda: None

    def run(results):
        responses.extend(results)
        with TestClient(app) as client:
            result = client.post("/api/llm/test")
        assert result.status_code == 200
        return result.json(), requests, usage

    return run


def test_reasoning_truncation_retries_then_confirms_json_mode(probe):
    payload, requests, usage = probe([(None, "length", 256), ('{"ok":true}', "stop", 300)])
    assert payload["code"] == "llm_probe_compatible"
    assert payload["capabilities"]["json_mode"] is True
    budgets = [r["max_tokens"] for r in requests if "response_format" in r]
    assert len(budgets) == 2 and 32 < budgets[0] < budgets[1] <= 2048
    assert sum(args[2] for args, _ in usage) == 557
    assert all(kwargs["billing_source"] == "hosted" for _, kwargs in usage)


def test_persistent_truncation_is_inconclusive_and_bounded(probe):
    payload, requests, _ = probe([(None, "length", 256), ('{"ok":', "length", 1024)])
    assert payload["code"] == "llm_probe_inconclusive"
    assert payload["capabilities"]["json_mode"] is False
    assert len([r for r in requests if "response_format" in r]) == 2


@pytest.mark.parametrize("content", [None, "", "not json", "[]"])
def test_unusable_output_does_not_claim_unsupported(probe, content):
    payload, requests, _ = probe([(content, "stop", 20)])
    assert payload["code"] == "llm_probe_inconclusive"
    assert len(requests) == 3


def test_explicit_json_mode_rejection_is_not_retried(probe):
    payload, requests, _ = probe([400])
    assert payload["code"] == "llm_probe_capability_mismatch"
    assert len(requests) == 3


def test_provider_outage_is_inconclusive_without_sdk_retries_or_error_leaks(probe):
    payload, requests, _ = probe([503])
    assert payload["code"] == "llm_probe_inconclusive"
    assert len(requests) == 3
    assert "secret-token" not in json.dumps(payload)
