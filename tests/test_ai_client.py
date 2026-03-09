"""Tests for app/core/ai_client.py — AIClient generate() and model routing."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel
from app.core.ai_client import AIClient, _estimate_cost, get_client


@pytest.fixture
def client():
    return AIClient()


# --- Config building ---


@patch("app.core.ai_client.get_settings")
def test_get_config_returns_openai_settings(mock_settings):
    s = MagicMock(
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s
    c = AIClient()
    cfg = c._get_config("default")
    assert cfg["api_key"] == "sk-test"
    assert cfg["model"] == "gpt-4o"
    assert not cfg["base_url"].endswith("/chat/completions")


@patch("app.core.ai_client.get_settings")
def test_get_config_strips_chat_completions(mock_settings):
    s = MagicMock(
        openai_base_url="https://example.com/v1/chat/completions",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s
    c = AIClient()
    cfg = c._get_config()
    assert cfg["base_url"] == "https://example.com/v1"


@patch("app.core.ai_client.get_settings")
def test_estimate_cost_preserves_default_output_pricing_when_only_input_override_is_set(mock_settings):
    mock_settings.return_value = MagicMock(
        llm_default_input_cost_per_million_usd=1.25,
        llm_default_output_cost_per_million_usd=0.0,
    )

    cost = _estimate_cost("gemini-3.0-flash", 1_000_000, 1_000_000)

    assert cost == pytest.approx(4.25)


@patch("app.core.ai_client.get_settings")
def test_estimate_cost_preserves_default_input_pricing_when_only_output_override_is_set(mock_settings):
    mock_settings.return_value = MagicMock(
        llm_default_input_cost_per_million_usd=0.0,
        llm_default_output_cost_per_million_usd=4.5,
    )

    cost = _estimate_cost("gemini-3.0-flash", 1_000_000, 1_000_000)

    assert cost == pytest.approx(5.0)


# --- _resolve_config ---


@patch("app.core.ai_client.get_settings")
def test_resolve_config_uses_per_request_when_all_provided(mock_settings):
    s = MagicMock(
        openai_base_url="https://env.example.com/v1",
        openai_api_key="env-key",
        openai_model="env-model",
    )
    mock_settings.return_value = s
    c = AIClient()
    cfg = c._resolve_config(
        base_url="https://user.example.com/v1",
        api_key="user-key",
        model="user-model",
    )
    assert cfg["base_url"] == "https://user.example.com/v1"
    assert cfg["api_key"] == "user-key"
    assert cfg["model"] == "user-model"


@patch("app.core.ai_client.get_settings")
def test_resolve_config_falls_back_when_partial(mock_settings):
    s = MagicMock(
        openai_base_url="https://env.example.com/v1",
        openai_api_key="env-key",
        openai_model="env-model",
    )
    mock_settings.return_value = s
    c = AIClient()
    cfg = c._resolve_config(base_url="https://user.example.com/v1", api_key=None, model=None)
    assert cfg["api_key"] == "env-key"
    assert cfg["model"] == "env-model"


@patch("app.core.ai_client.get_settings")
def test_resolve_config_strips_chat_completions_from_per_request(mock_settings):
    s = MagicMock(
        openai_base_url="https://env.example.com/v1",
        openai_api_key="env-key",
        openai_model="env-model",
    )
    mock_settings.return_value = s
    c = AIClient()
    cfg = c._resolve_config(
        base_url="https://user.example.com/v1/chat/completions",
        api_key="k",
        model="m",
    )
    assert cfg["base_url"] == "https://user.example.com/v1"


# --- generate() with mocked providers ---


@pytest.mark.asyncio
@patch("app.core.ai_client.ensure_ai_available_fresh_session")
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_uses_byok_billing_source_for_ai_gate(
    MockOpenAI, mock_settings, mock_ai_gate
):
    s = MagicMock(
        deploy_mode="hosted",
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    mock_response = MagicMock()
    mock_response.usage = None
    mock_response.choices = [MagicMock(message=MagicMock(content="Generated text"))]
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_response)
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    result = await c.generate(
        "Write something",
        base_url="https://user.example.com/v1",
        api_key="user-key",
        model="user-model",
        billing_source_hint="byok",
    )

    assert result == "Generated text"
    mock_ai_gate.assert_called_once_with(billing_source="byok")


@pytest.mark.asyncio
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_openai(MockOpenAI, mock_settings):
    s = MagicMock(
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Generated text"))]
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_response)
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    result = await c.generate("Write something")
    assert result == "Generated text"
    mock_client_instance.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.core.ai_client.ensure_ai_available_fresh_session")
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_stream_uses_byok_billing_source_for_ai_gate(
    MockOpenAI, mock_settings, mock_ai_gate
):
    s = MagicMock(
        deploy_mode="hosted",
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    chunk = MagicMock()
    chunk.usage = None
    chunk.choices = [MagicMock(delta=MagicMock(content="A"))]

    async def fake_stream():
        yield chunk

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=fake_stream())
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    out = []
    async for token in c.generate_stream(
        "Write something",
        base_url="https://user.example.com/v1",
        api_key="user-key",
        model="user-model",
        billing_source_hint="byok",
    ):
        out.append(token)

    assert "".join(out) == "A"
    mock_ai_gate.assert_called_once_with(billing_source="byok")


@pytest.mark.asyncio
@patch("app.core.ai_client._record_usage")
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_stream_records_usage_when_available(MockOpenAI, mock_settings, mock_record_usage):
    s = MagicMock(
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    chunk1 = MagicMock()
    chunk1.usage = None
    chunk1.choices = [MagicMock(delta=MagicMock(content="A"))]

    chunk2 = MagicMock()
    chunk2.usage = None
    chunk2.choices = [MagicMock(delta=MagicMock(content="B"))]

    chunk3 = MagicMock()
    chunk3.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
    chunk3.choices = [MagicMock(delta=MagicMock(content=None))]

    async def fake_stream():
        yield chunk1
        yield chunk2
        yield chunk3

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=fake_stream())
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    out = []
    async for token in c.generate_stream("Write something"):
        out.append(token)

    assert "".join(out) == "AB"
    call_kwargs = mock_client_instance.chat.completions.create.call_args.kwargs
    assert call_kwargs["stream_options"] == {"include_usage": True}
    mock_record_usage.assert_called_once_with(
        "gpt-4o",
        10,
        20,
        node_name="default",
        user_id=None,
        billing_source="selfhost",
    )


@pytest.mark.asyncio
@patch("app.core.ai_client._record_usage")
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_stream_retries_without_stream_options_on_unsupported_gateway(
    MockOpenAI, mock_settings, mock_record_usage
):
    s = MagicMock(
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    chunk1 = MagicMock()
    chunk1.usage = None
    chunk1.choices = [MagicMock(delta=MagicMock(content="A"))]

    chunk2 = MagicMock()
    chunk2.usage = None
    chunk2.choices = [MagicMock(delta=MagicMock(content="B"))]

    async def fake_stream():
        yield chunk1
        yield chunk2

    bad_exc = Exception("Unknown field: stream_options")
    bad_exc.status_code = 400

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(side_effect=[bad_exc, fake_stream()])
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    out = []
    async for token in c.generate_stream("Write something"):
        out.append(token)

    assert "".join(out) == "AB"

    calls = mock_client_instance.chat.completions.create.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["stream_options"] == {"include_usage": True}
    assert "stream_options" not in calls[1].kwargs
    mock_record_usage.assert_not_called()


# --- Error handling ---


@pytest.mark.asyncio
@patch("app.core.ai_client.ensure_ai_available_fresh_session")
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_structured_uses_byok_billing_source_for_ai_gate(
    MockOpenAI, mock_settings, mock_ai_gate
):
    class ExampleModel(BaseModel):
        ok: bool

    s = MagicMock(
        deploy_mode="hosted",
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    mock_response = MagicMock()
    mock_response.usage = None
    mock_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps({"ok": True})), finish_reason="stop")
    ]
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_response)
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    result = await c.generate_structured(
        "Write something",
        ExampleModel,
        base_url="https://user.example.com/v1",
        api_key="user-key",
        model="user-model",
        billing_source_hint="byok",
    )

    assert result.ok is True
    mock_ai_gate.assert_called_once_with(billing_source="byok")


@pytest.mark.asyncio
@patch("app.core.ai_client.logger.warning")
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_stream_logs_when_response_is_truncated(MockOpenAI, mock_settings, mock_log_warning):
    s = MagicMock(
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    chunk1 = MagicMock()
    chunk1.usage = None
    chunk1.choices = [MagicMock(delta=MagicMock(content="A"), finish_reason=None)]

    chunk2 = MagicMock()
    chunk2.usage = None
    chunk2.choices = [MagicMock(delta=MagicMock(content=None), finish_reason="length")]

    async def fake_stream():
        yield chunk1
        yield chunk2

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=fake_stream())
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    out = []
    async for token in c.generate_stream("Write something", max_tokens=1234):
        out.append(token)

    assert "".join(out) == "A"
    mock_log_warning.assert_called_once()
    logged = " ".join(str(x) for x in mock_log_warning.call_args.args)
    assert "generate_stream truncated" in logged


@pytest.mark.asyncio
@patch("app.core.ai_client.logger.warning")
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_logs_when_response_is_truncated(MockOpenAI, mock_settings, mock_log_warning):
    s = MagicMock(
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    mock_response = MagicMock()
    mock_response.usage = None
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Partial text"), finish_reason="length")
    ]
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_response)
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    result = await c.generate("Write something", max_tokens=1234)

    assert result == "Partial text"
    mock_log_warning.assert_called_once()
    logged = " ".join(str(x) for x in mock_log_warning.call_args.args)
    assert "generate truncated" in logged


@pytest.mark.asyncio
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_api_error_propagates(MockOpenAI, mock_settings):
    s = MagicMock(
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(
        side_effect=Exception("API error")
    )
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    with pytest.raises(Exception, match="API error"):
        await c.generate("Write something")


# --- generate_structured() JSON-mode parsing/retry semantics ---


class DummyStructuredModel(BaseModel):
    title: str
    score: int


@pytest.mark.asyncio
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_structured_parses_json_mode(MockOpenAI, mock_settings):
    s = MagicMock(
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    mock_response = MagicMock()
    mock_response.usage = None
    mock_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps(dict(title="Scene", score=9))))
    ]
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_response)
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    result = await c.generate_structured(
        prompt="Return JSON",
        response_model=DummyStructuredModel,
        role="default",
    )

    assert result.title == "Scene"
    assert result.score == 9
    call_kwargs = mock_client_instance.chat.completions.create.call_args.kwargs
    assert call_kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_structured_retries_then_succeeds(MockOpenAI, mock_settings):
    s = MagicMock(
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    invalid_response = MagicMock()
    invalid_response.usage = None
    invalid_response.choices = [MagicMock(message=MagicMock(content="not-json"))]

    valid_response = MagicMock()
    valid_response.usage = None
    valid_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps(dict(title="Recovered", score=7))))
    ]

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(
        side_effect=[invalid_response, valid_response]
    )
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    result = await c.generate_structured(
        prompt="Return JSON",
        response_model=DummyStructuredModel,
        role="default",
        max_retries=2,
    )

    assert result.title == "Recovered"
    assert mock_client_instance.chat.completions.create.await_count == 2


@pytest.mark.asyncio
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_structured_raises_after_retry_exhaustion(MockOpenAI, mock_settings):
    s = MagicMock(
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    invalid_response = MagicMock()
    invalid_response.usage = None
    invalid_response.choices = [MagicMock(message=MagicMock(content="still-not-json"))]

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=invalid_response)
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    with pytest.raises(ValueError, match="Failed to parse structured output"):
        await c.generate_structured(
            prompt="Return JSON",
            response_model=DummyStructuredModel,
            role="default",
            max_retries=2,
        )

    assert mock_client_instance.chat.completions.create.await_count == 2


@pytest.mark.asyncio
@patch("app.core.ai_client.logger.warning")
@patch("app.core.ai_client.get_settings")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_structured_does_not_log_raw_llm_output(MockOpenAI, mock_settings, mock_log_warning):
    """
    Regression: never log raw LLM output (can contain PII/novel content) on parse failure.
    """
    s = MagicMock(
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="sk-test",
        openai_model="gpt-4o",
    )
    mock_settings.return_value = s

    secret = "SENSITIVE USER CONTENT"
    invalid_response = MagicMock()
    invalid_response.id = "chatcmpl-test"
    invalid_response.usage = None
    invalid_response.choices = [
        MagicMock(message=MagicMock(content=secret), finish_reason="stop")
    ]

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=invalid_response)
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    with pytest.raises(ValueError, match="Failed to parse structured output"):
        await c.generate_structured(
            prompt="Return JSON",
            response_model=DummyStructuredModel,
            role="default",
            max_retries=1,
        )

    assert mock_log_warning.called
    logged = " ".join([str(x) for x in mock_log_warning.call_args.args] + [str(mock_log_warning.call_args.kwargs)])
    assert secret not in logged


# --- get_client() singleton ---


def test_get_client_returns_singleton():
    c1 = get_client()
    c2 = get_client("director")
    assert c1 is c2
