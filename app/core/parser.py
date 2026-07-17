# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Iterable

from app.core.chapter_headings import (
    ParsedChapterHeading,
    chinese_to_arabic,
    compile_chapter_heading_regexes,
    line_may_be_chapter_heading,
    parse_chapter_heading,
    strip_leading_chapter_heading,
)
from app.language import DEFAULT_LANGUAGE, normalize_language_code
from app.language_policy import LanguageDetectionAccumulator

__all__ = [
    "ParsedChapter",
    "ParsedChapterHeading",
    "chinese_to_arabic",
    "parse_chapter_heading",
    "parse_novel_file",
    "parse_novel_file_streaming",
    "parse_novel_text",
    "probe_novel_file",
    "read_novel_file_text",
    "strip_leading_chapter_heading",
]

_SUPPORTED_TEXT_ENCODINGS = ("utf-8", "gb18030", "gbk", "gb2312", "utf-16")


@dataclass(frozen=True)
class ParsedChapter:
    title: str
    content: str
    source_chapter_label: str | None = None
    source_chapter_number: int | None = None


def read_novel_file_text(file_path: str) -> str:
    return _read_novel_file_text_with_encoding(file_path)[0]


def _read_novel_file_text_with_encoding(file_path: str) -> tuple[str, str]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Novel file not found: {file_path}")

    for encoding in _SUPPORTED_TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=encoding), encoding
        except (UnicodeDecodeError, UnicodeError):
            continue

    raise ValueError(f"Unable to decode file with supported encodings: {file_path}")


def parse_novel_text(
    content: str, *, language: str | None = None
) -> list[ParsedChapter]:
    """Parse novel text into structured chapter records."""
    chapter_regexes = compile_chapter_heading_regexes(
        language=language,
        sample_text=content,
    )

    chapter_positions: list[tuple[int, str]] = []
    for chapter_regex in chapter_regexes:
        for match in chapter_regex.finditer(content):
            chapter_positions.append((match.start(), match.group()))
        if chapter_positions:
            break

    if not chapter_positions:
        return [ParsedChapter(title="", content=content.strip())]

    chapter_positions.sort(key=lambda item: item[0])

    parsed_chapters: list[ParsedChapter] = []
    for index, (position, raw_label) in enumerate(chapter_positions):
        content_start = position + len(raw_label)
        if index + 1 < len(chapter_positions):
            content_end = chapter_positions[index + 1][0]
        else:
            content_end = len(content)

        chapter_content = content[content_start:content_end].strip()
        parsed_chapters.append(
            _build_parsed_chapter(
                raw_label=raw_label,
                chapter_content=chapter_content,
            )
        )

    return parsed_chapters


def parse_novel_file(
    file_path: str, *, language: str | None = None
) -> list[ParsedChapter]:
    return parse_novel_text(read_novel_file_text(file_path), language=language)


def probe_novel_file(
    file_path: str,
    *,
    requested_language: str | None,
) -> tuple[str, int, str]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Novel file not found: {file_path}")

    normalized_requested = normalize_language_code(requested_language, default=None)

    for encoding in _SUPPORTED_TEXT_ENCODINGS:
        source_chars = 0
        try:
            detection = (
                None
                if normalized_requested is not None
                else LanguageDetectionAccumulator()
            )
            with path.open("r", encoding=encoding) as handle:
                for raw_line in handle:
                    source_chars += len(raw_line)
                    if detection is not None:
                        detection.add_text(raw_line)

            resolved_language = normalized_requested
            if resolved_language is None:
                resolved_language = normalize_language_code(
                    detection.detect_language()
                    if detection is not None
                    else DEFAULT_LANGUAGE,
                    default=DEFAULT_LANGUAGE,
                )
            return encoding, source_chars, resolved_language or DEFAULT_LANGUAGE
        except (UnicodeDecodeError, UnicodeError):
            continue

    raise ValueError(f"Unable to decode file with supported encodings: {file_path}")


def parse_novel_file_streaming(
    file_path: str,
    *,
    encoding: str,
    language: str,
    chapter_regex: re.Pattern[str] | None = None,
) -> list[ParsedChapter]:
    if chapter_regex is None:
        chapter_regex = _find_chapter_heading_regex_in_file(
            file_path,
            encoding=encoding,
            language=language,
        )
    if chapter_regex is None:
        return [
            ParsedChapter(
                title="",
                content="".join(
                    _iter_novel_file_lines(file_path, encoding=encoding)
                ).strip(),
            )
        ]

    parsed_chapters: list[ParsedChapter] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for raw_line in _iter_novel_file_lines(file_path, encoding=encoding):
        line = raw_line.rstrip("\r\n")
        if chapter_regex.match(line):
            if current_heading is not None:
                parsed_chapters.append(
                    _build_parsed_chapter(
                        raw_label=current_heading,
                        chapter_content="".join(current_lines).strip(),
                    )
                )
            current_heading = line
            current_lines = []
            continue
        if current_heading is not None:
            current_lines.append(raw_line)

    if current_heading is not None:
        parsed_chapters.append(
            _build_parsed_chapter(
                raw_label=current_heading,
                chapter_content="".join(current_lines).strip(),
            )
        )

    return parsed_chapters


def _iter_novel_file_lines(file_path: str, *, encoding: str) -> Iterable[str]:
    path = Path(file_path)
    with path.open("r", encoding=encoding) as handle:
        yield from handle


def _find_chapter_heading_regex_in_file(
    file_path: str,
    *,
    encoding: str,
    language: str,
) -> re.Pattern[str] | None:
    compiled_patterns = compile_chapter_heading_regexes(
        language=language,
        sample_text="",
    )
    best_index: int | None = None

    for raw_line in _iter_novel_file_lines(file_path, encoding=encoding):
        line = raw_line.rstrip("\r\n")
        if not line_may_be_chapter_heading(line):
            continue
        max_index = len(compiled_patterns) if best_index is None else best_index
        for index in range(max_index):
            if not compiled_patterns[index].match(line):
                continue
            best_index = index
            if index == 0:
                return compiled_patterns[0]
            break

    if best_index is None:
        return None
    return compiled_patterns[best_index]


def _build_parsed_chapter(
    *,
    raw_label: str,
    chapter_content: str,
) -> ParsedChapter:
    trimmed_label = raw_label.strip()
    parsed_heading = parse_chapter_heading(trimmed_label)
    if parsed_heading is None:
        return ParsedChapter(
            title=trimmed_label,
            content=chapter_content,
        )

    return ParsedChapter(
        title=parsed_heading.title,
        content=chapter_content,
        source_chapter_label=parsed_heading.source_label,
        source_chapter_number=parsed_heading.source_number,
    )
