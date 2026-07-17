# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""HTTP adapter for the canonical runtime LLM configuration resolver."""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.config import get_settings
from app.core.llm_config import (
    LlmConfigError,
    LlmConfigValues,
    ResolvedLlmConfig,
    resolve_llm_config,
)

LLM_BASE_URL_HEADER = "x-llm-base-url"
LLM_API_KEY_HEADER = "x-llm-api-key"
LLM_MODEL_HEADER = "x-llm-model"


def read_llm_override(request: Request) -> LlmConfigValues:
    header_names = {
        LLM_BASE_URL_HEADER,
        LLM_API_KEY_HEADER,
        LLM_MODEL_HEADER,
    }
    return LlmConfigValues(
        base_url=request.headers.get(LLM_BASE_URL_HEADER),
        api_key=request.headers.get(LLM_API_KEY_HEADER),
        model=request.headers.get(LLM_MODEL_HEADER),
        provided=any(name in request.headers for name in header_names),
    )


def get_llm_config(request: Request) -> ResolvedLlmConfig:
    try:
        return resolve_llm_config(
            settings=get_settings(),
            request_override=read_llm_override(request),
        )
    except LlmConfigError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
