from __future__ import annotations


LLM_API_KEY_MAX_LENGTH = 4096
LLM_API_KEY_INVALID_CODE = "llm_api_key_invalid"
LLM_API_KEY_INVALID_MESSAGE = (
    f"LLM API key must be at most {LLM_API_KEY_MAX_LENGTH} characters and contain "
    "no whitespace or control characters."
)


class LlmApiKeyError(ValueError):
    """Raised when an API key violates the canonical credential contract."""


def validate_llm_api_key(value: object) -> str:
    if not isinstance(value, str):
        raise LlmApiKeyError(LLM_API_KEY_INVALID_MESSAGE)
    api_key = value
    if len(api_key) > LLM_API_KEY_MAX_LENGTH or any(
        character.isspace() or not character.isprintable() for character in api_key
    ):
        raise LlmApiKeyError(LLM_API_KEY_INVALID_MESSAGE)
    return api_key
