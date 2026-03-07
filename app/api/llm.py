"""LLM test endpoint — validate user-supplied API config."""

import time

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import AsyncOpenAI

from app.api.novels import get_llm_config
from app.core.auth import get_current_user_or_default
from app.core.ai_client import _record_usage, _resolve_billing_source
from app.core.safety_fuses import check_ai_available

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.post("/test")
async def test_llm_connection(
    request: Request,
    _user=Depends(get_current_user_or_default),
    _ai_gate: None = Depends(check_ai_available),
):
    """Send a minimal completion request to validate LLM config from headers."""
    config = get_llm_config(request)
    if not config or not config.get("base_url") or not config.get("api_key") or not config.get("model"):
        raise HTTPException(status_code=400, detail="Missing LLM config headers (X-LLM-Base-Url, X-LLM-Api-Key, X-LLM-Model)")

    base_url = config["base_url"]
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    base_url = base_url.rstrip("/")

    client = AsyncOpenAI(
        base_url=base_url,
        api_key=config["api_key"],
        timeout=10.0,
    )

    start = time.perf_counter()
    try:
        response = await client.chat.completions.create(
            model=config["model"],
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            try:
                prompt_tokens = int(usage.prompt_tokens)
                completion_tokens = int(usage.completion_tokens)
            except (TypeError, ValueError):
                pass
            else:
                _record_usage(
                    config["model"],
                    prompt_tokens,
                    completion_tokens,
                    endpoint="/api/llm/test",
                    node_name="llm_test",
                    user_id=getattr(_user, "id", None),
                    billing_source=_resolve_billing_source(
                        config.get("billing_source_hint"),
                        using_request_override=bool(
                            request.headers.get("x-llm-base-url")
                            and request.headers.get("x-llm-api-key")
                            and request.headers.get("x-llm-model")
                        ),
                    ),
                )
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {"ok": True, "model": config["model"], "latency_ms": latency_ms}
    except Exception as e:
        return {"ok": False, "error": str(e)}
