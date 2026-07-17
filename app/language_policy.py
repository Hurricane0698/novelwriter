from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
import unicodedata
from dataclasses import dataclass

from app.language import DEFAULT_LANGUAGE, normalize_language_code

DEFAULT_CJK_SPACE_RATIO_THRESHOLD = 0.05
DEFAULT_SENTENCE_BACKTRACK_WINDOW = 200

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_HANGUL_RE = re.compile(r"[\uac00-\ud7af]")
_LATIN_ASCII_RE = re.compile(r"[A-Za-z]")
_WHITESPACE_RE = re.compile(r"\s+")
_TRIM_CHARS = " \t\r\n.,!?;:\"'()[]{}<>，。！？；：、“”‘’（）【】《》、…·-—"
_SENTENCE_CLOSERS = frozenset("\"'”’）】》」』〉〕〗]")
_RELATIONSHIP_SUFFIXES_BY_LANGUAGE = {
    "zh": ("关系", "關係"),
    "ja": ("関係",),
    "ko": ("관계",),
}
_ALL_CJK_RELATIONSHIP_SUFFIXES = tuple(
    dict.fromkeys(
        suffix
        for suffixes in _RELATIONSHIP_SUFFIXES_BY_LANGUAGE.values()
        for suffix in suffixes
    )
)
_ZH_VARIANT_CHARS_PATH = (
    Path(__file__).resolve().parent
    / "core"
    / "indexing"
    / "data"
    / "zh_variant_chars.tsv"
)


@lru_cache(maxsize=1)
def _zh_variant_char_translation_table() -> dict[int, str]:
    if not _ZH_VARIANT_CHARS_PATH.exists():
        return {}

    translation_table: dict[int, str] = {}
    for raw_line in _ZH_VARIANT_CHARS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        src, dst = (part.strip() for part in parts)
        if len(src) != 1 or len(dst) != 1:
            continue
        translation_table[ord(src)] = dst
    return translation_table


def _normalize_text(
    value: str | None,
    *,
    apply_zh_variant_chars: bool = False,
) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    if apply_zh_variant_chars:
        translation_table = _zh_variant_char_translation_table()
    else:
        translation_table = {}
    if translation_table:
        normalized = normalized.translate(translation_table)
    return normalized


def _collect_script_counts(text: str) -> tuple[int, int, int, int]:
    return (
        sum(1 for _ in _CJK_RE.finditer(text)),
        sum(1 for _ in _LATIN_ASCII_RE.finditer(text)),
        sum(1 for _ in _KANA_RE.finditer(text)),
        sum(1 for _ in _HANGUL_RE.finditer(text)),
    )


def _script_is_dominant(script_count: int, other_count: int) -> bool:
    return script_count >= 2 and (other_count == 0 or script_count * 3 >= other_count)


def detect_language_from_text(
    text: str,
    *,
    cjk_space_ratio_threshold: float = DEFAULT_CJK_SPACE_RATIO_THRESHOLD,
) -> str:
    normalized = _normalize_text(text)
    if not normalized.strip():
        return "en"

    cjk_count, latin_count, kana_count, hangul_count = _collect_script_counts(normalized)

    if _script_is_dominant(hangul_count, cjk_count + latin_count + kana_count):
        return "ko"
    if _script_is_dominant(kana_count, cjk_count + latin_count + hangul_count):
        return "ja"

    if cjk_count:
        space_ratio = normalized.count(" ") / max(len(normalized), 1)
        if cjk_count >= latin_count or space_ratio < cjk_space_ratio_threshold:
            return "zh"

    return "en"


def resolve_text_processing_language(
    language: str | None,
    *,
    sample_text: str | None = None,
    default: str = DEFAULT_LANGUAGE,
) -> str:
    normalized = normalize_language_code(language, default=None)
    if normalized:
        return normalized

    if sample_text:
        detected = normalize_language_code(detect_language_from_text(sample_text), default=None)
        if detected:
            return detected

    normalized_default = normalize_language_code(default, default=None)
    if normalized_default:
        return normalized_default
    return DEFAULT_LANGUAGE


@dataclass(frozen=True, slots=True)
class LanguagePolicy:
    language: str
    base_language: str
    family: str
    tokenizer_kind: str
    common_words_bucket: str
    sentence_terminators: tuple[str, ...]
    relationship_suffixes: tuple[str, ...]

    def normalize_for_matching(self, value: str | None) -> str:
        return _normalize_text(
            value,
            apply_zh_variant_chars=self.base_language == "zh",
        ).casefold()

    def normalize_token(self, token: str | None) -> str:
        return _normalize_text(
            token,
            apply_zh_variant_chars=self.base_language == "zh",
        ).strip(_TRIM_CHARS)

    def match_has_word_boundaries(self, text: str, start: int, end: int) -> bool:
        if self.family == "cjk":
            return True

        def is_word_char(ch: str) -> bool:
            return ch.isalnum() or ch in {"_", "-"}

        left_ok = start <= 0 or not is_word_char(text[start - 1])
        right_ok = end >= len(text) or not is_word_char(text[end])
        return left_ok and right_ok

    def canonicalize_relationship_label(self, label: str | None) -> str:
        normalized = _WHITESPACE_RE.sub(
            " ",
            _normalize_text(
                label,
                apply_zh_variant_chars=self.base_language == "zh",
            ).strip(),
        )
        canonical = normalized.casefold()

        suffixes = self.relationship_suffixes
        if self.family == "cjk":
            suffixes = _ALL_CJK_RELATIONSHIP_SUFFIXES

        for suffix in suffixes:
            suffix_key = suffix.casefold()
            if canonical.endswith(suffix_key) and len(canonical) > len(suffix_key):
                canonical = canonical[: -len(suffix_key)].rstrip()
                break

        return canonical or normalized.casefold()

    def trim_to_sentence_boundary(
        self,
        text: str,
        target_chars: int,
        *,
        backtrack_window: int = DEFAULT_SENTENCE_BACKTRACK_WINDOW,
        max_overrun_chars: int = 0,
    ) -> str:
        if target_chars <= 0:
            return text

        # Prefer keeping the sentence that straddles target_chars whole: when the
        # model produced more than target_chars, look forward to the next sentence
        # boundary within the overrun ceiling before falling back to a backward
        # (<= target) cut. This avoids systematically severing the final sentence
        # of a continuation just to stay under target. max_overrun_chars == 0
        # preserves the historical backward-only behavior for other callers.
        if max_overrun_chars > 0 and len(text) > target_chars:
            ceiling = min(len(text), target_chars + max_overrun_chars)
            for idx in range(target_chars, ceiling + 1):
                if self._is_sentence_boundary_at(text, idx):
                    return text[:idx].rstrip()

        slice_end = min(len(text), target_chars)
        trimmed = text[:slice_end].rstrip()
        if self._ends_with_sentence_boundary(trimmed):
            return trimmed

        window_start = max(0, slice_end - backtrack_window)
        for idx in range(slice_end, window_start, -1):
            if self._is_sentence_boundary_at(text, idx):
                return text[:idx].rstrip()

        for idx in range(slice_end, 0, -1):
            if self._is_sentence_boundary_at(text, idx):
                return text[:idx].rstrip()

        return trimmed

    def _ends_with_sentence_boundary(self, text: str) -> bool:
        return self._is_sentence_boundary_at(text, len(text))

    def _is_sentence_boundary_at(self, text: str, end_idx: int) -> bool:
        if end_idx <= 0:
            return False

        pos = end_idx - 1
        while pos >= 0 and text[pos] in _SENTENCE_CLOSERS:
            pos -= 1
        return pos >= 0 and text[pos] in self.sentence_terminators


@dataclass(slots=True)
class LanguageDetectionAccumulator:
    cjk_space_ratio_threshold: float = DEFAULT_CJK_SPACE_RATIO_THRESHOLD
    total_length: int = 0
    total_space_count: int = 0
    cjk_count: int = 0
    latin_count: int = 0
    kana_count: int = 0
    hangul_count: int = 0
    saw_text: bool = False
    _item_count: int = 0

    def add_text(self, text: str) -> None:
        normalized = _normalize_text(text)
        if normalized.strip():
            self.saw_text = True
        if self._item_count > 0:
            self.total_length += 1
        self.total_length += len(normalized)
        self.total_space_count += normalized.count(" ")
        (
            text_cjk_count,
            text_latin_count,
            text_kana_count,
            text_hangul_count,
        ) = _collect_script_counts(normalized)
        self.cjk_count += text_cjk_count
        self.latin_count += text_latin_count
        self.kana_count += text_kana_count
        self.hangul_count += text_hangul_count
        self._item_count += 1

    def detect_language(self) -> str:
        if not self.saw_text:
            return "en"
        if _script_is_dominant(
            self.hangul_count,
            self.cjk_count + self.latin_count + self.kana_count,
        ):
            return "ko"
        if _script_is_dominant(
            self.kana_count,
            self.cjk_count + self.latin_count + self.hangul_count,
        ):
            return "ja"
        if self.cjk_count:
            space_ratio = self.total_space_count / max(self.total_length, 1)
            if self.cjk_count >= self.latin_count or space_ratio < self.cjk_space_ratio_threshold:
                return "zh"
        return "en"


def get_language_policy(
    language: str | None = None,
    *,
    sample_text: str | None = None,
    default: str = DEFAULT_LANGUAGE,
) -> LanguagePolicy:
    resolved = resolve_text_processing_language(language, sample_text=sample_text, default=default)
    base = resolved.split("-", 1)[0]

    if base == "zh":
        return LanguagePolicy(
            language=resolved,
            base_language=base,
            family="cjk",
            tokenizer_kind="jieba",
            common_words_bucket="zh",
            sentence_terminators=("。", "！", "？", "!", "?", "…", "."),
            relationship_suffixes=_RELATIONSHIP_SUFFIXES_BY_LANGUAGE["zh"],
        )

    if base == "ja":
        return LanguagePolicy(
            language=resolved,
            base_language=base,
            family="cjk",
            tokenizer_kind="cjk_bigram",
            common_words_bucket="zh",
            sentence_terminators=("。", "！", "？", "!", "?", "…", "."),
            relationship_suffixes=_RELATIONSHIP_SUFFIXES_BY_LANGUAGE["ja"],
        )

    if base == "ko":
        return LanguagePolicy(
            language=resolved,
            base_language=base,
            family="cjk",
            tokenizer_kind="cjk_bigram",
            common_words_bucket="zh",
            sentence_terminators=(".", "!", "?", "…", "。", "！", "？"),
            relationship_suffixes=_RELATIONSHIP_SUFFIXES_BY_LANGUAGE["ko"],
        )

    return LanguagePolicy(
        language=resolved,
        base_language=base,
        family="whitespace",
        tokenizer_kind="whitespace",
        common_words_bucket="en",
        sentence_terminators=(".", "!", "?", "…", "。", "！", "？"),
        relationship_suffixes=(),
    )
