"""Tests for app/core/ai_client.py — AIClient generate() and model routing."""

import json
import logging
import traceback

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel
from app.core.ai_client import (
    AIClient,
    LLMUnavailableError,
    ToolCallUnsupportedError,
    _estimate_cost,
    get_client,
)
from app.core.llm_config import ResolvedLlmConfig


@pytest.fixture
def client():
    return AIClient()


_SELFHOST_CONFIG = ResolvedLlmConfig(
    base_url="https://api.openai.com/v1",
    api_key="sk-test",
    model="gpt-4o",
    billing_source_hint="selfhost",
    source="selfhost_settings",
)
_HOSTED_CONFIG = ResolvedLlmConfig(
    base_url="https://hosted.example/v1",
    api_key="hosted-key",
    model="hosted-model",
    billing_source_hint="hosted",
    source="hosted_settings",
)
_PROVIDER_SECRET = "sk-ai-client-redaction-7f6b9d2c"
_SECRET_CONFIG = ResolvedLlmConfig(
    base_url="https://provider.example/v1",
    api_key=_PROVIDER_SECRET,
    model="provider-model",
    billing_source_hint="selfhost",
    source="selfhost_settings",
)


def _provider_error(message: str, *, status_code: int | None = None) -> RuntimeError:
    error = RuntimeError(
        f"{message}\r\nAuthorization: Bearer {_PROVIDER_SECRET}"
        f"\\r\\napi_key={_PROVIDER_SECRET}"
    )
    if status_code is not None:
        error.status_code = status_code
    return error


def _assert_provider_error_sanitized(
    error: Exception,
    caplog: pytest.LogCaptureFixture,
    *,
    expected_message: str,
) -> None:
    assert str(error) == expected_message
    assert error.__cause__ is None
    assert error.__context__ is None
    assert _PROVIDER_SECRET not in "".join(traceback.format_exception(error))
    assert _PROVIDER_SECRET not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


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


# --- generate() with mocked providers ---


@pytest.mark.asyncio
@patch("app.core.ai_client.ensure_ai_available_fresh_session")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_uses_resolved_billing_source_for_ai_gate(
    MockOpenAI, mock_ai_gate
):
    mock_response = MagicMock()
    mock_response.usage = None
    mock_response.choices = [MagicMock(message=MagicMock(content="Generated text"))]
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_response)
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    result = await c.generate(
        "Write something",
        llm_config=_HOSTED_CONFIG,
    )

    assert result == "Generated text"
    mock_ai_gate.assert_called_once_with(billing_source="hosted")


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
    result = await c.generate("Write something", llm_config=_SELFHOST_CONFIG)
    assert result == "Generated text"
    mock_client_instance.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.core.ai_client.ensure_ai_available_fresh_session")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_stream_uses_resolved_billing_source_for_ai_gate(
    MockOpenAI, mock_ai_gate
):
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
        llm_config=_HOSTED_CONFIG,
    ):
        out.append(token)

    assert "".join(out) == "A"
    mock_ai_gate.assert_called_once_with(billing_source="hosted")


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
    async for token in c.generate_stream(
        "Write something",
        llm_config=_SELFHOST_CONFIG,
    ):
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
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_stream_retries_without_stream_options_on_unsupported_gateway(
    MockOpenAI, mock_record_usage, caplog
):
    caplog.set_level(logging.WARNING, logger="app.core.ai_client")

    chunk1 = MagicMock()
    chunk1.usage = None
    chunk1.choices = [MagicMock(delta=MagicMock(content="A"))]

    chunk2 = MagicMock()
    chunk2.usage = None
    chunk2.choices = [MagicMock(delta=MagicMock(content="B"))]

    async def fake_stream():
        yield chunk1
        yield chunk2

    bad_exc = _provider_error("Unknown field: stream_options", status_code=400)

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(side_effect=[bad_exc, fake_stream()])
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    out = []
    async for token in c.generate_stream(
        "Write something",
        llm_config=_SECRET_CONFIG,
    ):
        out.append(token)

    assert "".join(out) == "AB"

    calls = mock_client_instance.chat.completions.create.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["stream_options"] == {"include_usage": True}
    assert "stream_options" not in calls[1].kwargs
    mock_record_usage.assert_not_called()
    assert "Streaming include_usage unsupported" in caplog.text
    assert _PROVIDER_SECRET not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.asyncio
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_stream_sanitizes_noncompat_provider_error(MockOpenAI, caplog):
    caplog.set_level(logging.WARNING, logger="app.core.ai_client")
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(
        side_effect=_provider_error("provider unavailable")
    )
    MockOpenAI.return_value = mock_client_instance

    with pytest.raises(LLMUnavailableError) as exc_info:
        async for _ in AIClient().generate_stream(
            "Write something",
            llm_config=_SECRET_CONFIG,
        ):
            pass

    _assert_provider_error_sanitized(
        exc_info.value,
        caplog,
        expected_message="LLM provider request failed",
    )


@pytest.mark.asyncio
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_stream_sanitizes_fallback_provider_error(MockOpenAI, caplog):
    caplog.set_level(logging.WARNING, logger="app.core.ai_client")
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(
        side_effect=[
            _provider_error("Unknown field: stream_options", status_code=400),
            _provider_error("fallback request failed"),
        ]
    )
    MockOpenAI.return_value = mock_client_instance

    with pytest.raises(LLMUnavailableError) as exc_info:
        async for _ in AIClient().generate_stream(
            "Write something",
            llm_config=_SECRET_CONFIG,
        ):
            pass

    _assert_provider_error_sanitized(
        exc_info.value,
        caplog,
        expected_message="LLM provider request failed",
    )


@pytest.mark.asyncio
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_stream_sanitizes_iteration_provider_error(MockOpenAI, caplog):
    caplog.set_level(logging.WARNING, logger="app.core.ai_client")
    chunk = MagicMock()
    chunk.usage = None
    chunk.choices = [MagicMock(delta=MagicMock(content="A"), finish_reason=None)]

    async def failing_stream():
        yield chunk
        raise _provider_error("stream disconnected")

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=failing_stream())
    MockOpenAI.return_value = mock_client_instance

    output = []
    with pytest.raises(LLMUnavailableError) as exc_info:
        async for token in AIClient().generate_stream(
            "Write something",
            llm_config=_SECRET_CONFIG,
        ):
            output.append(token)

    assert output == ["A"]
    _assert_provider_error_sanitized(
        exc_info.value,
        caplog,
        expected_message="LLM provider request failed",
    )


# --- Error handling ---


@pytest.mark.asyncio
@patch("app.core.ai_client.ensure_ai_available_fresh_session")
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_structured_uses_resolved_billing_source_for_ai_gate(
    MockOpenAI, mock_ai_gate
):
    class ExampleModel(BaseModel):
        ok: bool

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
        llm_config=_HOSTED_CONFIG,
    )

    assert result.ok is True
    mock_ai_gate.assert_called_once_with(billing_source="hosted")


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
    async for token in c.generate_stream(
        "Write something",
        llm_config=_SELFHOST_CONFIG,
        max_tokens=1234,
    ):
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
    result = await c.generate(
        "Write something",
        llm_config=_SELFHOST_CONFIG,
        max_tokens=1234,
    )

    assert result == "Partial text"
    mock_log_warning.assert_called_once()
    logged = " ".join(str(x) for x in mock_log_warning.call_args.args)
    assert "generate truncated" in logged


@pytest.mark.asyncio
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_sanitizes_provider_error(MockOpenAI, caplog):
    caplog.set_level(logging.WARNING, logger="app.core.ai_client")
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(
        side_effect=_provider_error("API error")
    )
    MockOpenAI.return_value = mock_client_instance

    c = AIClient()
    with pytest.raises(LLMUnavailableError) as exc_info:
        await c.generate("Write something", llm_config=_SECRET_CONFIG)

    _assert_provider_error_sanitized(
        exc_info.value,
        caplog,
        expected_message="LLM provider request failed",
    )


@pytest.mark.asyncio
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_with_tools_sanitizes_unsupported_error(MockOpenAI, caplog):
    caplog.set_level(logging.WARNING, logger="app.core.ai_client")
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(
        side_effect=_provider_error("tools are unsupported", status_code=400)
    )
    MockOpenAI.return_value = mock_client_instance

    with pytest.raises(ToolCallUnsupportedError) as exc_info:
        await AIClient().generate_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "test"}}],
            llm_config=_SECRET_CONFIG,
        )

    _assert_provider_error_sanitized(
        exc_info.value,
        caplog,
        expected_message="LLM provider does not support tool calling",
    )


@pytest.mark.asyncio
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_with_tools_sanitizes_provider_error(MockOpenAI, caplog):
    caplog.set_level(logging.WARNING, logger="app.core.ai_client")
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(
        side_effect=_provider_error("provider unavailable", status_code=503)
    )
    MockOpenAI.return_value = mock_client_instance

    with pytest.raises(LLMUnavailableError) as exc_info:
        await AIClient().generate_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "test"}}],
            llm_config=_SECRET_CONFIG,
        )

    _assert_provider_error_sanitized(
        exc_info.value,
        caplog,
        expected_message="LLM provider request failed",
    )


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
        llm_config=_SELFHOST_CONFIG,
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
        llm_config=_SELFHOST_CONFIG,
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
            llm_config=_SELFHOST_CONFIG,
            role="default",
            max_retries=2,
        )

    assert mock_client_instance.chat.completions.create.await_count == 2


@pytest.mark.asyncio
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_structured_does_not_log_raw_llm_output(MockOpenAI, caplog):
    """
    Regression: never log raw LLM output (can contain PII/novel content) on parse failure.
    """
    caplog.set_level(logging.WARNING, logger="app.core.ai_client")

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
    with pytest.raises(ValueError, match="Failed to parse structured output") as exc_info:
        await c.generate_structured(
            prompt="Return JSON",
            response_model=DummyStructuredModel,
            llm_config=_SELFHOST_CONFIG,
            role="default",
            max_retries=1,
        )

    assert caplog.records
    assert secret not in caplog.text
    assert secret not in "".join(traceback.format_exception(exc_info.value))
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.asyncio
@patch("app.core.ai_client.AsyncOpenAI")
async def test_generate_structured_sanitizes_provider_errors(MockOpenAI, caplog):
    caplog.set_level(logging.WARNING, logger="app.core.ai_client")
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(
        side_effect=[
            _provider_error("structured request failed"),
            _provider_error("structured request failed again"),
        ]
    )
    MockOpenAI.return_value = mock_client_instance

    with pytest.raises(LLMUnavailableError) as exc_info:
        await AIClient().generate_structured(
            prompt="Return JSON",
            response_model=DummyStructuredModel,
            llm_config=_SECRET_CONFIG,
            max_retries=2,
        )

    assert mock_client_instance.chat.completions.create.await_count == 2
    assert [record.llm_attempt for record in caplog.records] == [1, 2]
    _assert_provider_error_sanitized(
        exc_info.value,
        caplog,
        expected_message="LLM provider request failed",
    )


# --- get_client() singleton ---


def test_get_client_returns_singleton():
    c1 = get_client()
    c2 = get_client("director")
    assert c1 is c2
