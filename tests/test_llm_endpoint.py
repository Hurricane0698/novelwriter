from __future__ import annotations

import pytest

from app.core.llm_endpoint import OpenAIBaseUrlError, normalize_openai_base_url


def test_normalize_openai_base_url_removes_endpoint_and_trailing_slash():
    assert (
        normalize_openai_base_url("https://gateway.example/v1/chat/completions/")
        == "https://gateway.example/v1"
    )
    assert (
        normalize_openai_base_url("https://gateway.example/v1//chat/completions/")
        == "https://gateway.example/v1"
    )


def test_normalize_openai_base_url_preserves_local_http_endpoint():
    assert (
        normalize_openai_base_url("http://127.0.0.1:11434/v1/")
        == "http://127.0.0.1:11434/v1"
    )


@pytest.mark.parametrize(
    "base_url",
    (
        "localhost:11434/v1",
        "file:///tmp/provider",
        "https://token@example.com/v1",
        "https://example.com/v1?api_key=secret",
        "https://example.com/v1#provider",
        " https://example.com/v1",
        "https://example.com/v1 ",
        "https://example .com/v1",
        "https://example.com/\x00v1",
    ),
)
def test_normalize_openai_base_url_rejects_invalid_or_secret_bearing_urls(base_url):
    with pytest.raises(OpenAIBaseUrlError):
        normalize_openai_base_url(base_url)
