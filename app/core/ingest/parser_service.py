from __future__ import annotations

from app.content_formats import (
    MARKDOWN_CONTENT_FORMAT,
    PLAIN_TEXT_CONTENT_FORMAT,
    NovelContentFormat,
)
from app.core.markdown_parser import parse_markdown_novel
from app.core.parser import ParsedChapter, parse_novel_file_streaming, probe_novel_file
from app.core.source_errors import SourceEncodingUnsupportedError
from app.language import normalize_language_code
from app.language_policy import LanguageDetectionAccumulator

from .contracts import ParsedNovelIngest


def resolve_requested_language(language: str | None) -> str | None:
    return normalize_language_code(language, default=None)


def _detect_markdown_language(chapters: list[ParsedChapter]) -> str:
    detection = LanguageDetectionAccumulator()
    active_volume: str | None = None

    for chapter in chapters:
        if (
            chapter.source_volume_title is not None
            and chapter.source_volume_title != active_volume
        ):
            detection.add_text(chapter.source_volume_title)
        active_volume = chapter.source_volume_title

        heading = chapter.source_chapter_label or chapter.title
        if heading:
            detection.add_text(heading)
        if chapter.content:
            detection.add_text(chapter.content)

    return detection.detect_language()


def parse_source_file(
    file_path: str,
    *,
    content_format: NovelContentFormat,
    requested_language: str | None,
) -> ParsedNovelIngest:
    if content_format == MARKDOWN_CONTENT_FORMAT:
        parsed_markdown = parse_markdown_novel(file_path)
        resolved_language = (
            resolve_requested_language(requested_language)
            or _detect_markdown_language(parsed_markdown.chapters)
        )
        return ParsedNovelIngest(
            source_chars=parsed_markdown.source_chars,
            resolved_language=resolved_language,
            chapters=parsed_markdown.chapters,
        )
    if content_format != PLAIN_TEXT_CONTENT_FORMAT:
        raise RuntimeError(f"Unknown novel content format: {content_format}")

    try:
        detected_encoding, source_chars, resolved_language = probe_novel_file(
            file_path,
            requested_language=requested_language,
        )
    except ValueError as exc:
        raise SourceEncodingUnsupportedError(
            "Plain-text source cannot be decoded with supported encodings"
        ) from exc
    chapters = parse_novel_file_streaming(
        file_path,
        encoding=detected_encoding,
        language=resolved_language,
    )
    return ParsedNovelIngest(
        source_chars=source_chars,
        resolved_language=resolved_language,
        chapters=chapters,
    )
