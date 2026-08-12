from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from markdown_it import MarkdownIt
from markdown_it.token import Token

from app.core.parser import ParsedChapter, build_parsed_chapter
from app.core.source_errors import (
    MarkdownStructureInvalidError,
    SourceEncodingUnsupportedError,
)


# Fixed parser-safety invariants, intentionally separate from ingest size tiers.
_MAX_MARKDOWN_BLOCK_LINES = 100_000
_MAX_MARKDOWN_BLOCK_TOKENS = 100_000
_MAX_MARKDOWN_HEADING_SOURCE_CHARS = 4_096
_MAX_MARKDOWN_HEADING_CHARS = 255

_SERIALIZED_CHAPTER_BOUNDARY = "## nov-wr-serialized-chapter-boundary\n"
_INLINE_MARKDOWN = MarkdownIt("commonmark")


class _BlockTokenState(Protocol):
    tokens: list[Token]


@dataclass(frozen=True, slots=True)
class ParsedMarkdownNovel:
    source_chars: int
    chapters: list[ParsedChapter]


@dataclass(frozen=True, slots=True)
class _StructuralHeading:
    level: int
    title: str
    start_line: int
    end_line: int


def _read_utf8_markdown(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Novel file not found: {file_path}")
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceEncodingUnsupportedError(
            "Markdown sources must use UTF-8 or UTF-8 BOM"
        ) from exc


def _logical_line_break_count(source: str) -> int:
    return source.count("\n") + source.count("\r") - source.count("\r\n")


def _markdown_line_count(source: str) -> int:
    if not source:
        return 0
    return _logical_line_break_count(source) + 1


def _enforce_block_token_budget(
    state: _BlockTokenState,
    _start_line: int,
    _end_line: int,
    silent: bool,
) -> bool:
    if not silent and len(state.tokens) >= _MAX_MARKDOWN_BLOCK_TOKENS:
        raise MarkdownStructureInvalidError(
            "Markdown structure exceeds the supported block token limit"
        )
    return False


def _parse_block_structure(source: str) -> list[Token]:
    if _markdown_line_count(source) > _MAX_MARKDOWN_BLOCK_LINES:
        raise MarkdownStructureInvalidError(
            "Markdown structure exceeds the supported line limit"
        )

    parser = MarkdownIt("commonmark").disable("inline")
    parser.block.ruler.before(
        "code",
        "nov_wr_block_token_budget",
        _enforce_block_token_budget,
    )
    tokens = parser.parse(source)
    if len(tokens) > _MAX_MARKDOWN_BLOCK_TOKENS:
        raise MarkdownStructureInvalidError(
            "Markdown structure exceeds the supported block token limit"
        )
    return tokens


def _plain_heading_title(inline: Token) -> str:
    if len(inline.content) > _MAX_MARKDOWN_HEADING_SOURCE_CHARS:
        raise MarkdownStructureInvalidError(
            "Markdown structure heading exceeds the supported source length"
        )

    parsed_inline = _INLINE_MARKDOWN.parseInline(inline.content)
    children = parsed_inline[0].children or []
    if len(children) != 1 or children[0].type != "text":
        raise MarkdownStructureInvalidError(
            "H1 and H2 headings must use plain text without inline Markdown"
        )
    title = children[0].content.strip()
    if not title:
        raise MarkdownStructureInvalidError("H1 and H2 headings cannot be empty")
    if len(title) > _MAX_MARKDOWN_HEADING_CHARS:
        raise MarkdownStructureInvalidError(
            "H1 and H2 headings cannot exceed 255 characters"
        )
    return title


def validate_markdown_chapter_body(content: str) -> None:
    """Reject reserved headings and bodies that can swallow the next chapter."""
    serialized_body = content if content.endswith("\n") else f"{content}\n"
    boundary_start_line = _logical_line_break_count(serialized_body)
    tokens = _parse_block_structure(
        f"{serialized_body}{_SERIALIZED_CHAPTER_BOUNDARY}"
    )

    boundary_is_preserved = False
    for token in tokens:
        if token.type != "heading_open" or token.tag not in {"h1", "h2"}:
            continue
        if token.map is not None and int(token.map[0]) < boundary_start_line:
            raise MarkdownStructureInvalidError(
                "Markdown chapter bodies cannot contain H1 or H2 headings"
            )
        if (
            token.tag == "h2"
            and token.level == 0
            and token.markup == "##"
            and token.map is not None
            and int(token.map[0]) == boundary_start_line
        ):
            boundary_is_preserved = True

    if not boundary_is_preserved:
        raise MarkdownStructureInvalidError(
            "Markdown chapter body must preserve the next serialized chapter boundary"
        )


def _structural_headings(tokens: list[Token]) -> list[_StructuralHeading]:
    headings: list[_StructuralHeading] = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.tag not in {"h1", "h2"}:
            continue
        if token.level != 0:
            raise MarkdownStructureInvalidError(
                "Novel structure headings must appear at the top level"
            )
        if token.markup not in {"#", "##"}:
            raise MarkdownStructureInvalidError(
                "Novel structure headings must use ATX # or ## syntax"
            )
        if token.map is None or index + 1 >= len(tokens):
            raise MarkdownStructureInvalidError("Markdown heading position is unavailable")
        inline = tokens[index + 1]
        if inline.type != "inline":
            raise MarkdownStructureInvalidError("Markdown heading content is invalid")
        headings.append(
            _StructuralHeading(
                level=int(token.tag[1]),
                title=_plain_heading_title(inline),
                start_line=int(token.map[0]),
                end_line=int(token.map[1]),
            )
        )
    return headings


def parse_markdown_novel(file_path: str) -> ParsedMarkdownNovel:
    source = _read_utf8_markdown(file_path)
    tokens = _parse_block_structure(source)
    headings = _structural_headings(tokens)
    del tokens
    if not any(heading.level == 2 for heading in headings):
        raise MarkdownStructureInvalidError(
            "Markdown novels require at least one H2 chapter heading"
        )

    lines = source.splitlines(keepends=True)
    current_volume: str | None = None
    volume_has_chapter = True
    chapters: list[ParsedChapter] = []
    previous_structure_end = 0

    for index, heading in enumerate(headings):
        between = "".join(lines[previous_structure_end:heading.start_line])
        if not chapters and between.strip():
            raise MarkdownStructureInvalidError(
                "Markdown body content cannot appear before the first chapter"
            )
        if current_volume is not None and not volume_has_chapter and between.strip():
            raise MarkdownStructureInvalidError(
                "Markdown body content cannot appear before a volume's first chapter"
            )

        if heading.level == 1:
            if current_volume is not None and not volume_has_chapter:
                raise MarkdownStructureInvalidError(
                    "Every Markdown volume must contain at least one chapter"
                )
            current_volume = heading.title
            volume_has_chapter = False
            previous_structure_end = heading.end_line
            continue

        if current_volume is not None:
            volume_has_chapter = True

        next_structure_start = (
            headings[index + 1].start_line if index + 1 < len(headings) else len(lines)
        )
        chapter_content = "".join(lines[heading.end_line:next_structure_start])
        validate_markdown_chapter_body(chapter_content)
        chapters.append(
            build_parsed_chapter(
                raw_label=heading.title,
                chapter_content=chapter_content,
                source_volume_title=current_volume,
            )
        )
        previous_structure_end = next_structure_start

    if current_volume is not None and not volume_has_chapter:
        raise MarkdownStructureInvalidError(
            "Every Markdown volume must contain at least one chapter"
        )

    return ParsedMarkdownNovel(source_chars=len(source), chapters=chapters)
