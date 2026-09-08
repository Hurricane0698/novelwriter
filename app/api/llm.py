"""Desktop LLM configuration and provider capability probes."""

from collections.abc import Awaitable, Callable
import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.ai_client import (
    _record_usage,
    _stream_options_unsupported,
)
from app.core.auth import get_current_user_or_default
from app.core.llm_config import (
    LLM_CONFIG_API_KEY_INVALID_CODE,
    LLM_CONFIG_API_KEY_INVALID_MESSAGE,
    LLM_CONFIG_DESKTOP_ONLY_CODE,
    LlmConfigError,
    delete_desktop_llm_config,
    get_desktop_llm_config_store,
    load_desktop_llm_config,
    save_desktop_llm_config,
)
from app.core.llm_request import get_llm_config
from app.core.safety_fuses import ensure_ai_available
from app.database import get_db
from app.schemas import (
    DesktopLlmConfigPutRequest,
    DesktopLlmConfigResponse,
    LlmProbeCapabilitiesResponse,
    LlmProbeCapabilityStatuses,
    LlmProbeResponse,
)

_DESKTOP_APP_ORIGIN = "http://127.0.0.1:8000"
_DESKTOP_ORIGIN_FORBIDDEN_CODE = "desktop_origin_forbidden"
_DESKTOP_API_KEY_REQUIRED_CODE = "desktop_llm_api_key_required"
_LLM_REQUEST_INVALID_CODE = "llm_request_invalid"
_LLM_REQUEST_INVALID_MESSAGE = "LLM request validation failed."
_PROBE_COMPATIBLE_CODE = "llm_probe_compatible"
_PROBE_CONNECTION_FAILED_CODE = "llm_probe_connection_failed"
_PROBE_CAPABILITY_MISMATCH_CODE = "llm_probe_capability_mismatch"
_PROBE_INCONCLUSIVE_CODE = "llm_probe_inconclusive"
_JSON_PROBE_TOKEN_BUDGETS = (256, 1024)
_PROBE_TOTAL_TIMEOUT_SECONDS = 25.0


class _ProbeInconclusiveError(ValueError):
    """The response did not establish whether the requested capability works."""


def _capability_unsupported(exc: Exception, names: tuple[str, ...]) -> bool:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and status_code not in (400, 404, 422):
        return False
    message = str(exc).casefold()
    return any(name in message for name in names) and any(
        marker in message for marker in (
            "not supported", "unsupported", "does not support", "unknown parameter",
            "unknown field", "unrecognized request argument",
        )
    )


def _validation_error_targets_api_key(exc: RequestValidationError) -> bool:
    for error in exc.errors():
        location = error.get("loc", ())
        if any(
            isinstance(part, str) and part.replace("_", "").casefold() == "apikey"
            for part in location
        ):
            return True
    return False


class _SanitizedLlmValidationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_handler = super().get_route_handler()

        async def sanitized_handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except RequestValidationError as exc:
                api_key_error = _validation_error_targets_api_key(exc)
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content={
                        "detail": {
                            "code": (
                                LLM_CONFIG_API_KEY_INVALID_CODE
                                if api_key_error
                                else _LLM_REQUEST_INVALID_CODE
                            ),
                            "message": (
                                LLM_CONFIG_API_KEY_INVALID_MESSAGE
                                if api_key_error
                                else _LLM_REQUEST_INVALID_MESSAGE
                            ),
                        }
                    },
                )

        return sanitized_handler


router = APIRouter(
    prefix="/api/llm",
    tags=["llm"],
    route_class=_SanitizedLlmValidationRoute,
)


def _raise_llm_config_error(exc: LlmConfigError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _require_desktop_runtime(settings: Settings) -> None:
    if settings.runtime_mode != "desktop":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": LLM_CONFIG_DESKTOP_ONLY_CODE,
                "message": "Desktop LLM configuration is available only in desktop mode.",
            },
        )


def _require_desktop_origin(request: Request) -> None:
    if request.headers.get("origin") != _DESKTOP_APP_ORIGIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": _DESKTOP_ORIGIN_FORBIDDEN_CODE,
                "message": "Desktop credential changes require the desktop app origin.",
            },
        )


def _desktop_config_response(stored) -> DesktopLlmConfigResponse:
    if stored is None:
        return DesktopLlmConfigResponse(
            configured=False,
            base_url="",
            model="",
            api_key_configured=False,
        )
    return DesktopLlmConfigResponse(
        configured=True,
        base_url=stored.base_url,
        model=stored.model,
        api_key_configured=True,
    )


@router.get("/config", response_model=DesktopLlmConfigResponse)
def get_desktop_llm_config() -> DesktopLlmConfigResponse:
    settings = get_settings()
    _require_desktop_runtime(settings)
    try:
        stored = load_desktop_llm_config(get_desktop_llm_config_store(settings))
    except LlmConfigError as exc:
        _raise_llm_config_error(exc)
    return _desktop_config_response(stored)


@router.put("/config", response_model=DesktopLlmConfigResponse)
def put_desktop_llm_config(
    body: DesktopLlmConfigPutRequest,
    request: Request,
) -> DesktopLlmConfigResponse:
    settings = get_settings()
    _require_desktop_runtime(settings)
    _require_desktop_origin(request)
    try:
        store = get_desktop_llm_config_store(settings)
        if body.api_key is not None:
            api_key = body.api_key.get_secret_value()
        else:
            existing = load_desktop_llm_config(store)
            api_key = existing.api_key if existing is not None else ""
        if not api_key:
            raise LlmConfigError(
                code=_DESKTOP_API_KEY_REQUIRED_CODE,
                message="API key is required when configuring a desktop model for the first time.",
            )
        saved = save_desktop_llm_config(
            store,
            base_url=body.base_url,
            api_key=api_key,
            model=body.model,
        )
    except LlmConfigError as exc:
        _raise_llm_config_error(exc)
    return DesktopLlmConfigResponse(
        configured=True,
        base_url=saved.base_url,
        model=saved.model,
        api_key_configured=True,
    )


@router.delete("/config", status_code=status.HTTP_204_NO_CONTENT)
def remove_desktop_llm_config(request: Request) -> Response:
    settings = get_settings()
    _require_desktop_runtime(settings)
    _require_desktop_origin(request)
    try:
        delete_desktop_llm_config(get_desktop_llm_config_store(settings))
    except LlmConfigError as exc:
        _raise_llm_config_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _probe_stream_support(
    client: AsyncOpenAI, model: str, record_usage: Callable[[object], None],
) -> None:
    request_kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
        "max_tokens": 4,
        "stream": True,
    }
    try:
        stream = await client.chat.completions.create(
            **request_kwargs,
            stream_options={"include_usage": True},
        )
    except Exception as exc:
        if not _stream_options_unsupported(exc):
            raise
        stream = await client.chat.completions.create(**request_kwargs)

    try:
        async for chunk in stream:
            record_usage(chunk)
    finally:
        await stream.close()


async def _probe_json_mode_support(
    client: AsyncOpenAI, model: str, record_usage: Callable[[object], None],
) -> None:
    # Reasoning consumes the completion budget even when content is still empty.
    # Retry only an explicit truncation, with a bounded larger budget.
    for budget in _JSON_PROBE_TOKEN_BUDGETS:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": 'Return a JSON object: {"ok": true}'}],
            max_tokens=budget,
            response_format={"type": "json_object"},
        )
        record_usage(response)
        if not response.choices:
            raise _ProbeInconclusiveError("JSON probe returned no choices")
        choice = response.choices[0]
        if choice.finish_reason == "length":
            continue
        try:
            parsed = json.loads(choice.message.content or "")
        except (ValueError, TypeError):
            raise _ProbeInconclusiveError("JSON probe returned unusable content") from None
        if not isinstance(parsed, dict):
            raise _ProbeInconclusiveError("JSON probe did not return an object")
        return
    raise _ProbeInconclusiveError("JSON probe exhausted its completion budget")


@router.post("/test", response_model=LlmProbeResponse)
async def test_llm_connection(
    request: Request,
    _user=Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Probe the exact configuration that application AI calls will use."""
    settings = get_settings()
    if settings.runtime_mode == "desktop":
        _require_desktop_origin(request)
    config = get_llm_config(request)
    billing_source = config.billing_source_hint
    ensure_ai_available(db, billing_source=billing_source)

    start = time.perf_counter()
    capabilities = LlmProbeCapabilityStatuses()

    def record_usage(response: object) -> None:
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        if not isinstance(prompt_tokens, int) or not isinstance(completion_tokens, int):
            return
        _record_usage(
            config.model, prompt_tokens, completion_tokens,
            endpoint="/api/llm/test", node_name="llm_test",
            user_id=getattr(_user, "id", None), billing_source=billing_source,
        )

    try:
        async with asyncio.timeout(_PROBE_TOTAL_TIMEOUT_SECONDS):
            async with AsyncOpenAI(
                base_url=config.base_url,
                api_key=config.api_key,
                timeout=10.0,
                max_retries=0,
            ) as client:
                response = await client.chat.completions.create(
                    model=config.model,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=1,
                )
                capabilities.basic = "supported"
                record_usage(response)
                for name, probe, parameters in (
                    ("stream", _probe_stream_support, ("stream",)),
                    ("json_mode", _probe_json_mode_support, ("response_format", "json_object", "json mode")),
                ):
                    try:
                        await probe(client, config.model, record_usage)
                        setattr(capabilities, name, "supported")
                    except Exception as exc:
                        if _capability_unsupported(exc, parameters):
                            setattr(capabilities, name, "unsupported")
    except Exception:
        # A deadline or connection failure leaves unverified capabilities unknown.
        # Never replace an already established result with a later failure.
        pass

    statuses = capabilities.model_dump()
    if capabilities.basic != "supported":
        code = _PROBE_CONNECTION_FAILED_CODE
    elif "unsupported" in statuses.values():
        code = _PROBE_CAPABILITY_MISMATCH_CODE
    elif "unknown" in statuses.values():
        code = _PROBE_INCONCLUSIVE_CODE
    else:
        code = _PROBE_COMPATIBLE_CODE
    return LlmProbeResponse(
        code=code,
        model=config.model,
        latency_ms=round((time.perf_counter() - start) * 1000),
        # Retain the boolean projection for older desktop clients.
        capabilities=LlmProbeCapabilitiesResponse(**{
            name: value == "supported" for name, value in statuses.items()
        }),
        capability_statuses=capabilities,
    )
