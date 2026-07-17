# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.language_policy import (
    get_language_policy,
    resolve_text_processing_language,
)

try:
    import _novwr_state_proto
except ImportError:  # pragma: no cover - local fallback when Rust build is missing
    _novwr_state_proto = None


DEFAULT_COMMON_WORDS_DIR = "data/common_words"

_COMMON_WORD_FILE_BY_LANGUAGE = {
    "zh": "zh.txt",
    "en": "en.txt",
}
_COMMON_WORDS_CACHE: dict[tuple[str, str], frozenset[str]] = {}
_COMMON_WORDS_COMBINED_CACHE: dict[tuple[str, str], frozenset[str]] = {}
_TRIM_CHARS = " \t\r\n.,!?;:\"'()[]{}<>，。！？；：、“”‘’（）【】《》、…·-—"


@dataclass(slots=True)
class ChapterText:
    chapter_id: int
    text: str


class Tokenizer(Protocol):
    def tokenize(self, text: str) -> list[str]: ...


class WhitespaceTokenizer:
    def tokenize(self, text: str) -> list[str]:
        return text.split()


class CharacterNgramTokenizer:
    def __init__(self, *, n: int = 2):
        self.n = max(2, int(n))

    def tokenize(self, text: str) -> list[str]:
        cleaned = "".join(ch if ch not in _TRIM_CHARS else " " for ch in text)
        chunks = [chunk for chunk in cleaned.split() if chunk]
        tokens: list[str] = []
        for chunk in chunks:
            if len(chunk) < 2:
                continue
            if len(chunk) <= self.n:
                tokens.append(chunk)
                continue
            tokens.extend(
                chunk[i : i + self.n] for i in range(0, len(chunk) - self.n + 1)
            )
        return tokens


class JiebaTokenizer:
    def tokenize(self, text: str) -> list[str]:
        rust_tokenize = (
            getattr(_novwr_state_proto, "tokenize_zh_text", None)
            if _novwr_state_proto is not None
            else None
        )
        if rust_tokenize is not None:
            return [token for token in rust_tokenize(text) if token]
        return CharacterNgramTokenizer(n=2).tokenize(text)


def get_tokenizer(
    language: str,
    *,
    cjk_tokenizer: Tokenizer | None = None,
    cjk_ngram_tokenizer: Tokenizer | None = None,
    whitespace_tokenizer: Tokenizer | None = None,
) -> Tokenizer:
    policy = get_language_policy(language)
    if policy.tokenizer_kind == "jieba":
        return cjk_tokenizer or JiebaTokenizer()
    if policy.tokenizer_kind == "cjk_bigram":
        return cjk_ngram_tokenizer or CharacterNgramTokenizer(n=2)
    return whitespace_tokenizer or WhitespaceTokenizer()


def tokenize_text(
    text: str,
    *,
    language: str | None = None,
    tokenizer: Tokenizer | None = None,
) -> tuple[str, list[str]]:
    resolved_language = resolve_text_processing_language(language, sample_text=text)
    resolved_tokenizer = tokenizer or get_tokenizer(resolved_language)
    return resolved_language, resolved_tokenizer.tokenize(text)


def _resolve_common_words_base_dir(common_words_dir: str) -> Path:
    base_dir = Path(common_words_dir)
    if not base_dir.is_absolute():
        base_dir = Path(__file__).resolve().parents[3] / base_dir
    return base_dir.resolve()


def _load_common_words_file(file_path: Path, language_code: str) -> frozenset[str]:
    cache_key = (str(file_path), language_code)
    cached = _COMMON_WORDS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if not file_path.exists():
        raise FileNotFoundError(f"Common words file does not exist: {file_path}")

    words: set[str] = set()
    with file_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            word = raw_line.strip()
            if not word or word.startswith("#"):
                continue
            normalized_word = get_language_policy(language_code).normalize_for_matching(
                word
            )
            words.add(word)
            words.add(normalized_word)

    frozen_words = frozenset(words)
    _COMMON_WORDS_CACHE[cache_key] = frozen_words
    return frozen_words


def load_common_words(
    language: str,
    *,
    common_words_dir: str = DEFAULT_COMMON_WORDS_DIR,
) -> set[str]:
    policy = get_language_policy(language)
    normalized_language = policy.common_words_bucket
    base_dir = _resolve_common_words_base_dir(common_words_dir)
    combined_cache_key = (str(base_dir), normalized_language)
    cached = _COMMON_WORDS_COMBINED_CACHE.get(combined_cache_key)
    if cached is not None:
        return set(cached)

    fallback_language = "en" if normalized_language == "zh" else "zh"
    primary_words = _load_common_words_file(
        base_dir / _COMMON_WORD_FILE_BY_LANGUAGE[normalized_language],
        normalized_language,
    )
    fallback_words = _load_common_words_file(
        base_dir / _COMMON_WORD_FILE_BY_LANGUAGE[fallback_language],
        fallback_language,
    )
    merged = frozenset(set(primary_words) | set(fallback_words))
    _COMMON_WORDS_COMBINED_CACHE[combined_cache_key] = merged
    return set(merged)


__all__ = [
    "ChapterText",
    "Tokenizer",
    "WhitespaceTokenizer",
    "CharacterNgramTokenizer",
    "JiebaTokenizer",
    "get_tokenizer",
    "tokenize_text",
    "load_common_words",
]
