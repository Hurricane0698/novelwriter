from __future__ import annotations

from pathlib import Path

import pytest

from app.core import markdown_parser as markdown_parser_module
from app.core.ingest.parser_service import parse_source_file
from app.core.markdown_parser import (
    parse_markdown_novel,
    validate_markdown_chapter_body,
)
from app.core.source_errors import (
    MarkdownStructureInvalidError,
    SourceEncodingUnsupportedError,
)


def _write_markdown(tmp_path: Path, content: str, *, bom: bool = False) -> Path:
    path = tmp_path / "novel.md"
    payload = content.encode("utf-8")
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)
    return path


def test_markdown_parser_preserves_body_and_volume_structure(tmp_path: Path):
    source = (
        "# 第一卷 风起\n"
        "## 第一章 开端\n"
        "\n"
        "这里有 **粗体**、*斜体*。\n"
        "\n"
        "### 章内小节\n"
        "\n"
        "- 列表一\n"
        "- 列表二\n"
        "\n"
        "> 引用\n"
        "\n"
        "---\n"
        "\n"
        "## 第二章 继续\n"
        "Unicode：雪山🏔️\n"
        "# 第二卷 归途\n"
        "## Chapter 3 Return\n"
        "```python\nprint('ok')\n```\n"
    )
    parsed = parse_markdown_novel(str(_write_markdown(tmp_path, source)))

    assert parsed.source_chars == len(source)
    assert [chapter.title for chapter in parsed.chapters] == ["开端", "继续", "Return"]
    assert [chapter.source_chapter_number for chapter in parsed.chapters] == [1, 2, 3]
    assert [chapter.source_volume_title for chapter in parsed.chapters] == [
        "第一卷 风起",
        "第一卷 风起",
        "第二卷 归途",
    ]
    assert parsed.chapters[0].content == (
        "\n这里有 **粗体**、*斜体*。\n\n### 章内小节\n\n"
        "- 列表一\n- 列表二\n\n> 引用\n\n---\n\n"
    )
    assert parsed.chapters[2].content == "```python\nprint('ok')\n```\n"


def test_markdown_parser_accepts_unscoped_chapters_and_utf8_bom(tmp_path: Path):
    source = "## 序章\n你好，世界。\n## 第二章\n再见。"
    parsed = parse_source_file(
        str(_write_markdown(tmp_path, source, bom=True)),
        content_format="markdown",
        requested_language=None,
    )

    assert parsed.resolved_language == "zh"
    assert [chapter.source_volume_title for chapter in parsed.chapters] == [None, None]
    assert parsed.chapters[0].title == "序章"
    assert parsed.chapters[1].source_chapter_number == 2


def test_markdown_language_detection_uses_empty_body_structure(tmp_path: Path):
    parsed = parse_source_file(
        str(_write_markdown(tmp_path, "# 第一卷\n## 序章\n")),
        content_format="markdown",
        requested_language=None,
    )

    assert parsed.resolved_language == "zh"


def test_markdown_parser_restores_escaped_plain_heading_metadata(tmp_path: Path):
    source = "# First \\*Volume\\*\n## First \\*Star\\* \\[Draft\\] \\\\ path\n正文"

    parsed = parse_markdown_novel(str(_write_markdown(tmp_path, source)))

    assert parsed.chapters[0].source_volume_title == "First *Volume*"
    assert parsed.chapters[0].title == "First *Star* [Draft] \\ path"


def test_markdown_parser_accepts_decoded_heading_at_storage_limit(tmp_path: Path):
    title = "章" * 255

    parsed = parse_markdown_novel(
        str(_write_markdown(tmp_path, f"## {title}\n正文"))
    )

    assert parsed.chapters[0].title == title


def test_markdown_parser_rejects_decoded_heading_above_storage_limit(
    tmp_path: Path,
):
    title = "章" * 256

    with pytest.raises(
        MarkdownStructureInvalidError,
        match="cannot exceed 255 characters",
    ):
        parse_markdown_novel(str(_write_markdown(tmp_path, f"## {title}\n正文")))


@pytest.mark.parametrize("heading", ["序章", "Prologue"])
def test_markdown_parser_preserves_standalone_special_heading_as_title(
    tmp_path: Path,
    heading: str,
):
    parsed = parse_markdown_novel(
        str(_write_markdown(tmp_path, f"## {heading}\n正文"))
    )

    assert parsed.chapters[0].title == heading
    assert parsed.chapters[0].source_chapter_label == heading
    assert parsed.chapters[0].source_chapter_number is None


@pytest.mark.parametrize(
    "source",
    [
        "## 第一章\n正文\n> ## Quoted heading\n> 引用正文\n",
        "## 第一章\n正文\n- # Listed volume\n  列表正文\n",
    ],
)
def test_markdown_parser_rejects_nested_structural_headings(
    tmp_path: Path,
    source: str,
):
    with pytest.raises(
        MarkdownStructureInvalidError,
        match="must appear at the top level",
    ):
        parse_markdown_novel(str(_write_markdown(tmp_path, source)))


@pytest.mark.parametrize(
    "body",
    [
        "# Heading one\n正文",
        "## Heading two\n正文",
        "Heading one\n===========\n正文",
        "Heading two\n-----------\n正文",
        "> ## Nested heading\n> 正文",
    ],
)
def test_markdown_chapter_body_rejects_structural_headings(body: str):
    with pytest.raises(
        MarkdownStructureInvalidError,
        match="cannot contain H1 or H2",
    ):
        validate_markdown_chapter_body(body)


def test_markdown_chapter_body_accepts_subheadings():
    validate_markdown_chapter_body("### Scene\n正文\n###### Detail\n更多正文")


@pytest.mark.parametrize(
    "body",
    [
        "```python\nprint('unterminated')",
        "<table>\n<tr><td>unterminated HTML block</td></tr>",
    ],
)
def test_markdown_chapter_body_rejects_blocks_that_swallow_next_boundary(body: str):
    with pytest.raises(
        MarkdownStructureInvalidError,
        match="preserve the next serialized chapter boundary",
    ):
        validate_markdown_chapter_body(body)


def test_markdown_parser_rejects_source_with_swallowed_chapter_boundary(
    tmp_path: Path,
):
    source = "## 第一章\n```text\n正文\n## 第二章\n后文\n"

    with pytest.raises(
        MarkdownStructureInvalidError,
        match="preserve the next serialized chapter boundary",
    ):
        parse_markdown_novel(str(_write_markdown(tmp_path, source)))


def test_markdown_parser_rejects_line_complexity_before_block_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def fail_if_parsed(*_args: object, **_kwargs: object) -> None:
        pytest.fail("MarkdownIt.parse must not run above the line limit")

    monkeypatch.setattr(markdown_parser_module.MarkdownIt, "parse", fail_if_parsed)
    source = "## 第一章\n" + (
        "\n" * markdown_parser_module._MAX_MARKDOWN_BLOCK_LINES
    )

    with pytest.raises(
        MarkdownStructureInvalidError,
        match="supported line limit",
    ):
        parse_markdown_novel(str(_write_markdown(tmp_path, source)))


def test_markdown_parser_bounds_heading_source_before_inline_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        markdown_parser_module,
        "_MAX_MARKDOWN_HEADING_SOURCE_CHARS",
        8,
    )

    with pytest.raises(
        MarkdownStructureInvalidError,
        match="supported source length",
    ):
        parse_markdown_novel(
            str(_write_markdown(tmp_path, "## heading-too-long\n正文"))
        )


def test_markdown_parser_enforces_block_token_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(markdown_parser_module, "_MAX_MARKDOWN_BLOCK_TOKENS", 5)
    source = "## 第一章\n正文\n## 第二章\n后文\n"

    with pytest.raises(
        MarkdownStructureInvalidError,
        match="supported block token limit",
    ):
        parse_markdown_novel(str(_write_markdown(tmp_path, source)))


@pytest.mark.parametrize(
    "source",
    [
        "# 只有卷\n正文",
        "前置正文\n## 第一章\n正文",
        "# 空卷\n# 下一卷\n## 第一章\n正文",
        "## **第一章**\n正文",
        "# 卷一\n卷前正文\n## 第一章\n正文",
        "## 第一章\n正文\n# 空尾卷\n",
        "第一章\n------\n正文",
    ],
)
def test_markdown_parser_rejects_invalid_novel_structure(tmp_path: Path, source: str):
    with pytest.raises(MarkdownStructureInvalidError):
        parse_markdown_novel(str(_write_markdown(tmp_path, source)))


def test_markdown_parser_rejects_non_utf8(tmp_path: Path):
    path = tmp_path / "novel.md"
    path.write_bytes("## 第一章\n正文".encode("gbk"))

    with pytest.raises(SourceEncodingUnsupportedError):
        parse_markdown_novel(str(path))
