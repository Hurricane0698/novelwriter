# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

from __future__ import annotations

from app.core.ai_client import StructuredOutputParseError

BOOTSTRAP_PARSE_ERROR_MESSAGE = "AI 输出解析失败，请重试"
BOOTSTRAP_PARSE_ERROR_KEY = "bootstrap.error.parse_failed"
BOOTSTRAP_TIMEOUT_ERROR_MESSAGE = "引导扫描超时，请重试"
BOOTSTRAP_TIMEOUT_ERROR_KEY = "bootstrap.error.timeout"
BOOTSTRAP_GENERIC_ERROR_MESSAGE = "引导扫描失败，请稍后重试"
BOOTSTRAP_GENERIC_ERROR_KEY = "bootstrap.error.generic"


def is_refinement_parse_error(exc: Exception) -> bool:
    return isinstance(exc, StructuredOutputParseError)


def is_refinement_timeout_error(exc: Exception) -> bool:
    return isinstance(exc, TimeoutError)


def sanitize_bootstrap_error(exc: Exception) -> tuple[str, str]:
    """Return (user_message, message_key) for a bootstrap failure."""
    if is_refinement_parse_error(exc):
        return BOOTSTRAP_PARSE_ERROR_MESSAGE, BOOTSTRAP_PARSE_ERROR_KEY
    if is_refinement_timeout_error(exc):
        return BOOTSTRAP_TIMEOUT_ERROR_MESSAGE, BOOTSTRAP_TIMEOUT_ERROR_KEY
    return BOOTSTRAP_GENERIC_ERROR_MESSAGE, BOOTSTRAP_GENERIC_ERROR_KEY


__all__ = [
    "BOOTSTRAP_GENERIC_ERROR_KEY",
    "BOOTSTRAP_GENERIC_ERROR_MESSAGE",
    "BOOTSTRAP_PARSE_ERROR_KEY",
    "BOOTSTRAP_PARSE_ERROR_MESSAGE",
    "BOOTSTRAP_TIMEOUT_ERROR_KEY",
    "BOOTSTRAP_TIMEOUT_ERROR_MESSAGE",
    "is_refinement_parse_error",
    "is_refinement_timeout_error",
    "sanitize_bootstrap_error",
]
