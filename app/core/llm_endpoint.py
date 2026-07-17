from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


class OpenAIBaseUrlError(ValueError):
    """Raised when an OpenAI-compatible base URL violates the endpoint contract."""


def normalize_openai_base_url(value: str) -> str:
    raw = str(value or "")
    if not raw or any(
        character.isspace() or ord(character) <= 0x1F or ord(character) == 0x7F
        for character in raw
    ):
        raise OpenAIBaseUrlError(
            "OpenAI base URL must not be empty or contain whitespace or control characters."
        )
    if "?" in raw or "#" in raw:
        raise OpenAIBaseUrlError(
            "OpenAI base URL must not contain a query or fragment."
        )

    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise OpenAIBaseUrlError("OpenAI base URL is malformed.") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise OpenAIBaseUrlError("OpenAI base URL must use HTTP or HTTPS.")
    if not hostname:
        raise OpenAIBaseUrlError("OpenAI base URL must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise OpenAIBaseUrlError("OpenAI base URL must not contain credentials.")
    if parsed.netloc.endswith(":"):
        raise OpenAIBaseUrlError("OpenAI base URL contains an invalid port.")

    path = parsed.path.rstrip("/")
    suffix = "/chat/completions"
    if path.endswith(suffix):
        path = path[: -len(suffix)].rstrip("/")

    return urlunsplit((parsed.scheme.lower(), parsed.netloc, path, "", ""))
