"""Provider resources must be released before a generation operation finishes."""

import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.ai_client import AIClient, LLMUnavailableError
from app.core.llm_config import ResolvedLlmConfig


class _Answer(BaseModel):
    answer: str


_CONFIG = ResolvedLlmConfig(
    base_url="https://provider.invalid/v1", api_key="synthetic-key", model="test-model",
    billing_source_hint="selfhost", source="selfhost_settings",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["generate", "generate_structured", "generate_with_tools", "generate_stream"])
@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
async def test_generation_closes_real_sdk_client(monkeypatch, method, outcome):
    entered = asyncio.Event()
    clients = []

    async def provider(request):
        entered.set()
        if outcome == "cancel":
            await asyncio.Future()
        if outcome == "failure":
            return httpx.Response(400, json={"error": {"message": "synthetic rejection"}})
        if method == "generate_stream":
            chunk = {"choices": [{"index": 0, "delta": {"content": "answer"}}]}
            return httpx.Response(200, content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 0, "model": "test-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"answer":"ok"}'}, "finish_reason": "stop"}],
        })

    def make_client(**kwargs):
        client = AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(provider)))
        clients.append(client)
        return client

    monkeypatch.setattr("app.core.ai_client.AsyncOpenAI", make_client)
    monkeypatch.setattr("app.core.ai_client.ensure_ai_available_fresh_session", lambda **kwargs: None)

    async def generate():
        client = AIClient()
        if method == "generate_stream":
            return [part async for part in client.generate_stream("prompt", llm_config=_CONFIG)]
        if method == "generate_with_tools":
            return await client.generate_with_tools([], [], llm_config=_CONFIG)
        if method == "generate_structured":
            return await client.generate_structured("prompt", _Answer, llm_config=_CONFIG)
        return await client.generate("prompt", llm_config=_CONFIG)

    task = asyncio.create_task(generate())
    try:
        if outcome == "cancel":
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif outcome == "failure":
            with pytest.raises(LLMUnavailableError):
                await task
        else:
            assert await task
        assert len(clients) == 1
        assert clients[0].is_closed()
    finally:
        for client in clients:
            await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["close", "failure", "cancel"])
async def test_stream_closes_response_body_after_partial_output(monkeypatch, outcome):
    waiting = asyncio.Event()

    class Body(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            chunk = {"choices": [{"index": 0, "delta": {"content": "first"}}]}
            yield f"data: {json.dumps(chunk)}\n\n".encode()
            if outcome == "failure":
                raise httpx.ReadError("synthetic disconnect")
            waiting.set()
            await asyncio.Future()

        async def aclose(self):
            self.closed = True

    body = Body()
    client = AsyncOpenAI(
        base_url=_CONFIG.base_url, api_key=_CONFIG.api_key,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body))),
    )
    monkeypatch.setattr("app.core.ai_client.AsyncOpenAI", lambda **kwargs: client)
    monkeypatch.setattr("app.core.ai_client.ensure_ai_available_fresh_session", lambda **kwargs: None)
    stream = AIClient().generate_stream("prompt", llm_config=_CONFIG)
    try:
        assert await anext(stream) == "first"
        if outcome == "close":
            await stream.aclose()
        elif outcome == "failure":
            with pytest.raises(LLMUnavailableError):
                await anext(stream)
        else:
            task = asyncio.create_task(anext(stream))
            await asyncio.wait_for(waiting.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert body.closed
        assert client.is_closed()
    finally:
        await stream.aclose()
        await client.close()
