from typing import Any, Literal, Type, TypeVar
from dataclasses import dataclass, field
import json
import logging
from openai import AsyncOpenAI
from pydantic import BaseModel
from app.config import get_settings
from app.core.safety_fuses import (
    ensure_ai_available_fresh_session,
    token_usage_recording_disabled,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

AgentRole = Literal["director", "writer", "editor", "summary", "default"]


class LLMUnavailableError(RuntimeError):
    """Raised when an LLM request cannot be completed (network/auth/provider errors)."""


class StructuredOutputParseError(ValueError):
    """Raised when an LLM returns output that cannot be parsed into the response model."""

    def __init__(self, *, max_retries: int, last_error: Exception | None = None):
        # Keep prefix stable for callers that key off the message.
        message = f"Failed to parse structured output after {max_retries} retries"
        if last_error is not None:
            message = f"{message}: {type(last_error).__name__}"
        super().__init__(message)
        self.max_retries = max_retries
        self.last_error = last_error


class ToolCallUnsupportedError(RuntimeError):
    """Raised when the LLM provider does not support tool/function calling."""


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string


@dataclass(slots=True)
class ToolLLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0

# Estimated cost per 1M tokens (input, output) in USD.
#
# Hosted operators can override these via env when using Vertex/OpenAI-compatible
# gateways so the budget hard-stop tracks their actual provider pricing.
_COST_TABLE = {
    "gemini-3.0-flash": (0.5, 3),
}
_DEFAULT_COST = (0.5, 3)
_BILLING_SOURCE_HOSTED = "hosted"
_BILLING_SOURCE_BYOK = "byok"
_BILLING_SOURCE_SELFHOST = "selfhost"


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    settings = get_settings()
    configured_input = float(settings.llm_default_input_cost_per_million_usd or 0.0)
    configured_output = float(settings.llm_default_output_cost_per_million_usd or 0.0)
    default_input_rate, default_output_rate = _COST_TABLE.get(model, _DEFAULT_COST)
    input_rate = configured_input if configured_input > 0 else default_input_rate
    output_rate = configured_output if configured_output > 0 else default_output_rate
    return (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000


def _resolve_billing_source(
    billing_source_hint: str | None,
    *,
    using_request_override: bool,
) -> str:
    normalized_hint = (billing_source_hint or "").strip().lower()

    if normalized_hint == _BILLING_SOURCE_HOSTED:
        return _BILLING_SOURCE_HOSTED

    settings = get_settings()
    if normalized_hint == _BILLING_SOURCE_BYOK:
        if using_request_override:
            return _BILLING_SOURCE_BYOK
        return _BILLING_SOURCE_HOSTED if settings.deploy_mode == "hosted" else _BILLING_SOURCE_SELFHOST

    if normalized_hint == _BILLING_SOURCE_SELFHOST:
        return _BILLING_SOURCE_SELFHOST

    if settings.deploy_mode == "hosted":
        return _BILLING_SOURCE_BYOK if using_request_override else _BILLING_SOURCE_HOSTED
    return _BILLING_SOURCE_SELFHOST


def _record_usage(model: str, prompt_tokens: int, completion_tokens: int,
                  endpoint: str = "", node_name: str | None = None, user_id: int | None = None,
                  billing_source: str = _BILLING_SOURCE_SELFHOST) -> None:
    """Persist token usage to DB. Non-blocking — failures are logged, never raised."""
    if token_usage_recording_disabled():
        return

    try:
        from app.database import SessionLocal
        from app.models import TokenUsage
        total = prompt_tokens + completion_tokens
        record = TokenUsage(
            user_id=user_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_estimate=_estimate_cost(model, prompt_tokens, completion_tokens),
            billing_source=billing_source,
            endpoint=endpoint,
            node_name=node_name,
        )
        db = SessionLocal()
        try:
            db.add(record)
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.warning("Failed to record token usage", exc_info=True)


def _stream_options_unsupported(exc: Exception) -> bool:
    """Return True if a provider/gateway rejects the `stream_options` parameter."""
    if isinstance(exc, TypeError) and "stream_options" in str(exc):
        return True

    status_code = getattr(exc, "status_code", None)
    if status_code not in {None, 400, 422}:
        return False

    message = str(exc).lower()
    if "stream_options" not in message and "include_usage" not in message:
        return False

    # Conservative: only retry when it's very likely an unknown-argument style failure.
    return any(
        hint in message
        for hint in (
            "unknown",
            "unrecognized",
            "unexpected",
            "extra",
            "not permitted",
            "invalid",
            "unsupported",
            "not supported",
        )
    )


def _tool_call_unsupported(exc: Exception) -> bool:
    """Return True if a provider/gateway rejects the `tools` parameter."""
    status_code = getattr(exc, "status_code", None)
    if status_code not in {None, 400, 422}:
        return False

    message = str(exc).lower()
    if "tool" not in message and "function" not in message:
        return False

    return any(
        hint in message
        for hint in (
            "unknown",
            "unrecognized",
            "unexpected",
            "not permitted",
            "invalid",
            "unsupported",
            "not supported",
            "does not support",
        )
    )


class AIClient:
    """
    Multi-model AI client supporting role-based model routing.

    All providers are accessed via the OpenAI-compatible SDK.
    Per-request overrides (base_url, api_key, model) take precedence over env config.
    """

    @property
    def settings(self):
        """Fetch settings lazily to support hot-reload of .env values."""
        return get_settings()

    def _get_config(self, role: AgentRole = "default") -> dict:
        """Get API configuration from runtime settings."""
        _ = role
        settings = self.settings
        if settings.deploy_mode == "hosted":
            base_url = settings.hosted_llm_base_url or settings.openai_base_url
            api_key = settings.hosted_llm_api_key or settings.openai_api_key
            model = settings.hosted_llm_model or settings.openai_model
        else:
            base_url = settings.openai_base_url
            api_key = settings.openai_api_key
            model = settings.openai_model
        if base_url.endswith("/chat/completions"):
            base_url = base_url[: -len("/chat/completions")]
        base_url = base_url.rstrip("/")
        return {
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
        }

    def _resolve_config(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> dict:
        """Resolve LLM config: use per-request values if all 3 provided, else env fallback."""
        if base_url and api_key and model:
            if base_url.endswith("/chat/completions"):
                base_url = base_url[: -len("/chat/completions")]
            base_url = base_url.rstrip("/")
            return {"base_url": base_url, "api_key": api_key, "model": model}
        return self._get_config()

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "You are a professional web novel writer.",
        max_tokens: int = 2000,
        temperature: float = 0.8,
        role: AgentRole = "default",
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        billing_source_hint: str | None = None,
        user_id: int | None = None,
    ) -> str:
        usage_billing_source = _resolve_billing_source(
            billing_source_hint,
            using_request_override=bool(base_url and api_key and model),
        )
        ensure_ai_available_fresh_session(billing_source=usage_billing_source)
        config = self._resolve_config(base_url, api_key, model)
        client = AsyncOpenAI(
            base_url=config["base_url"],
            api_key=config["api_key"],
        )
        response = await client.chat.completions.create(
            model=config["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if response.usage:
            _record_usage(config["model"], response.usage.prompt_tokens,
                          response.usage.completion_tokens, node_name=role, user_id=user_id,
                          billing_source=usage_billing_source)
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        if finish_reason == "length":
            logger.warning(
                "generate truncated (max_tokens=%s, finish_reason=%s)",
                max_tokens,
                finish_reason,
                extra={"base_url": config["base_url"], "model": config["model"]},
            )
        return response.choices[0].message.content or ""

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "You are a professional web novel writer.",
        max_tokens: int = 2000,
        temperature: float = 0.8,
        role: AgentRole = "default",
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        billing_source_hint: str | None = None,
        user_id: int | None = None,
    ):
        """Yield content chunks from streaming LLM response."""
        usage_billing_source = _resolve_billing_source(
            billing_source_hint,
            using_request_override=bool(base_url and api_key and model),
        )
        ensure_ai_available_fresh_session(billing_source=usage_billing_source)
        config = self._resolve_config(base_url, api_key, model)
        client = AsyncOpenAI(
            base_url=config["base_url"],
            api_key=config["api_key"],
        )
        request_kwargs = {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        try:
            # Provider-dependent; some OpenAI-compatible gateways 400 on unknown params.
            stream = await client.chat.completions.create(
                **request_kwargs,
                stream_options={"include_usage": True},
            )
        except Exception as exc:
            if not _stream_options_unsupported(exc):
                raise
            logger.warning(
                "Streaming include_usage unsupported; retrying without stream_options",
                exc_info=True,
                extra={"base_url": config["base_url"], "model": config["model"]},
            )
            stream = await client.chat.completions.create(**request_kwargs)
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        finish_reason: str | None = None
        async for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage:
                try:
                    prompt_tokens = int(usage.prompt_tokens)
                    completion_tokens = int(usage.completion_tokens)
                except Exception:
                    pass
            if chunk.choices:
                finish_reason = getattr(chunk.choices[0], "finish_reason", None) or finish_reason
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        if prompt_tokens is not None and completion_tokens is not None:
            _record_usage(
                config["model"],
                prompt_tokens,
                completion_tokens,
                node_name=role,
                user_id=user_id,
                billing_source=usage_billing_source,
            )
        if finish_reason == "length":
            logger.warning(
                "generate_stream truncated (max_tokens=%s, finish_reason=%s)",
                max_tokens,
                finish_reason,
                extra={"base_url": config["base_url"], "model": config["model"]},
            )

    async def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4000,
        temperature: float = 0.4,
        role: AgentRole = "default",
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        billing_source_hint: str | None = None,
        user_id: int | None = None,
        tool_choice: str | None = None,
    ) -> ToolLLMResponse:
        """Single-turn LLM call with tool definitions. Returns ToolLLMResponse.

        Raises ToolCallUnsupportedError if the provider rejects the tools parameter.
        """
        usage_billing_source = _resolve_billing_source(
            billing_source_hint,
            using_request_override=bool(base_url and api_key and model),
        )
        ensure_ai_available_fresh_session(billing_source=usage_billing_source)
        config = self._resolve_config(base_url, api_key, model)
        client = AsyncOpenAI(
            base_url=config["base_url"],
            api_key=config["api_key"],
        )

        request_kwargs: dict[str, Any] = {
            "model": config["model"],
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            request_kwargs["tools"] = tools
        if tool_choice is not None:
            request_kwargs["tool_choice"] = tool_choice

        try:
            response = await client.chat.completions.create(**request_kwargs)
        except Exception as exc:
            if _tool_call_unsupported(exc):
                raise ToolCallUnsupportedError(str(exc)) from exc
            raise

        if response.usage:
            _record_usage(
                config["model"],
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                node_name=role,
                user_id=user_id,
                billing_source=usage_billing_source,
            )

        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice else None
        finish_reason = choice.finish_reason if choice else None

        tool_calls: list[ToolCall] = []
        if choice and choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                ))

        return ToolLLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
        )

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str = "You are a professional web novel writer.",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        role: AgentRole = "default",
        max_retries: int = 3,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        billing_source_hint: str | None = None,
        user_id: int | None = None,
    ) -> T:
        """
        Generate structured output via OpenAI-compatible JSON mode + Pydantic parsing.

        Raises:
            StructuredOutputParseError: If structured output cannot be parsed after retries
            LLMUnavailableError: If the LLM request fails after retries
        """
        usage_billing_source = _resolve_billing_source(
            billing_source_hint,
            using_request_override=bool(base_url and api_key and model),
        )
        ensure_ai_available_fresh_session(billing_source=usage_billing_source)
        config = self._resolve_config(base_url, api_key, model)
        client = AsyncOpenAI(
            base_url=config["base_url"],
            api_key=config["api_key"],
        )

        schema_json = json.dumps(response_model.model_json_schema(), ensure_ascii=False)
        structured_system = (
            f"{system_prompt}\n\n"
            f"You MUST respond with valid JSON matching this schema:\n{schema_json}"
        )

        last_request_error: Exception | None = None
        last_parse_error: Exception | None = None
        saw_response = False

        for attempt in range(max_retries):
            try:
                response = await client.chat.completions.create(
                    model=config["model"],
                    messages=[
                        {"role": "system", "content": structured_system},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )
            except Exception as e:
                last_request_error = e
                logger.warning(
                    "generate_structured request failed (attempt %s/%s)",
                    attempt + 1,
                    max_retries,
                    exc_info=True,
                    extra={"base_url": config["base_url"], "model": config["model"]},
                )
                continue

            saw_response = True
            if response.usage:
                _record_usage(
                    config["model"],
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                    node_name=role,
                    user_id=user_id,
                    billing_source=usage_billing_source,
                )
            raw = response.choices[0].message.content or ""
            finish_reason = response.choices[0].finish_reason
            response_id = getattr(response, "id", None)

            # If truncated (length limit hit), retrying won't help.
            if finish_reason == "length":
                logger.warning(
                    "generate_structured truncated (max_tokens=%s, finish_reason=%s, content_len=%s, response_id=%s)",
                    max_tokens,
                    finish_reason,
                    len(raw),
                    response_id,
                    extra={"base_url": config["base_url"], "model": config["model"]},
                )
                raise StructuredOutputParseError(
                    max_retries=1,
                    last_error=ValueError(
                        f"LLM response truncated (finish_reason=length, max_tokens={max_tokens}). "
                        "Increase max_tokens or reduce input."
                    ),
                )

            try:
                return response_model.model_validate_json(raw)
            except Exception as e:
                last_parse_error = e
                logger.warning(
                    "generate_structured parse failed (attempt %s/%s, finish_reason=%s, content_len=%s, response_id=%s)",
                    attempt + 1,
                    max_retries,
                    finish_reason,
                    len(raw),
                    response_id,
                    exc_info=True,
                    extra={"base_url": config["base_url"], "model": config["model"]},
                )
                continue

        if saw_response and last_parse_error is not None:
            raise StructuredOutputParseError(max_retries=max_retries, last_error=last_parse_error) from last_parse_error

        err = last_request_error or last_parse_error
        raise LLMUnavailableError(f"LLM request failed after {max_retries} retries") from err


ai_client = AIClient()


def get_client(role: AgentRole = "default") -> AIClient:
    """
    Get the AI client instance.

    Note: The role parameter is stored for reference but must still be passed
    to generate() and generate_structured() methods for model routing.
    """
    return ai_client
