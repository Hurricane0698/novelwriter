"""Tests for app/core/parser.py — structured novel chapter parsing."""

import pytest
import tempfile
import os
from app.core.parser import parse_novel_file, chinese_to_arabic
from app.core.ingest.parser_service import parse_source_file


# --- chinese_to_arabic ---


def test_arabic_passthrough():
    assert chinese_to_arabic("42") == 42


def test_single_digit():
    assert chinese_to_arabic("三") == 3


def test_tens():
    assert chinese_to_arabic("十") == 10
    assert chinese_to_arabic("十五") == 15
    assert chinese_to_arabic("二十") == 20
    assert chinese_to_arabic("二十三") == 23


def test_hundreds():
    assert chinese_to_arabic("一百") == 100
    assert chinese_to_arabic("三百二十一") == 321


def test_thousands():
    assert chinese_to_arabic("一千") == 1000


def test_empty_returns_none():
    assert chinese_to_arabic("") is None


# --- parse_novel_file ---


def _write_tmp(content: str, encoding: str = "utf-8") -> str:
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding=encoding) as f:
        f.write(content)
    return path


def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        parse_novel_file("/nonexistent/path.txt")


def test_no_chapter_markers():
    path = _write_tmp("Just some text without any chapter markers.")
    try:
        result = parse_novel_file(path)
        assert len(result) == 1
        assert result[0].title == ""
        assert result[0].source_chapter_label is None
        assert result[0].source_chapter_number is None
        assert "Just some text" in result[0].content
    finally:
        os.unlink(path)


def test_no_chapter_markers_uses_language_localized_fallback_title():
    path = _write_tmp("これは章見出しのない本文です。")
    try:
        result = parse_novel_file(path, language="ja")
        assert len(result) == 1
        assert result[0].title == ""
        assert result[0].source_chapter_label is None
    finally:
        os.unlink(path)


def test_chinese_chapter_format():
    content = "第一章 开端\n这是第一章的内容。\n第二章 发展\n这是第二章的内容。\n"
    path = _write_tmp(content)
    try:
        result = parse_novel_file(path)
        assert len(result) == 2
        assert result[0].source_chapter_label == "第一章 开端"
        assert result[0].source_chapter_number == 1
        assert result[0].title == "开端"
        assert "第一章的内容" in result[0].content
        assert result[1].source_chapter_label == "第二章 发展"
        assert result[1].source_chapter_number == 2
        assert result[1].title == "发展"
        assert "第二章的内容" in result[1].content
    finally:
        os.unlink(path)


def test_english_chapter_format():
    content = "Chapter 1 Beginning\nFirst chapter content.\nChapter 2 Middle\nSecond chapter content.\n"
    path = _write_tmp(content)
    try:
        result = parse_novel_file(path)
        assert len(result) == 2
        assert result[0].source_chapter_label == "Chapter 1 Beginning"
        assert result[0].source_chapter_number == 1
        assert result[0].title == "Beginning"
        assert "First chapter content" in result[0].content
    finally:
        os.unlink(path)


def test_english_prologue_and_chapter_format():
    content = "Prologue\nOpening scene.\nChapter II Middle\nSecond chapter content.\n"
    path = _write_tmp(content)
    try:
        result = parse_novel_file(path, language="en")
        assert len(result) == 2
        assert result[0].source_chapter_label == "Prologue"
        assert result[0].source_chapter_number is None
        assert result[0].title == "Prologue"
        assert "Opening scene" in result[0].content
        assert result[1].source_chapter_label == "Chapter II Middle"
        assert result[1].source_chapter_number == 2
        assert result[1].title == "Middle"
    finally:
        os.unlink(path)


def test_japanese_chapter_format():
    content = "プロローグ\n始まり。\n第1話 出会い\n本文。\n"
    path = _write_tmp(content)
    try:
        result = parse_novel_file(path, language="ja")
        assert len(result) == 2
        assert result[0].source_chapter_label == "プロローグ"
        assert result[0].title == "プロローグ"
        assert "始まり" in result[0].content
        assert result[1].source_chapter_label == "第1話 出会い"
        assert result[1].source_chapter_number == 1
        assert result[1].title == "出会い"
    finally:
        os.unlink(path)


def test_korean_chapter_format():
    content = "프롤로그\n시작이다.\n제1장 만남\n본문이다.\n"
    path = _write_tmp(content)
    try:
        result = parse_novel_file(path, language="ko")
        assert len(result) == 2
        assert result[0].source_chapter_label == "프롤로그"
        assert result[0].title == "프롤로그"
        assert "시작이다" in result[0].content
        assert result[1].source_chapter_label == "제1장 만남"
        assert result[1].source_chapter_number == 1
        assert result[1].title == "만남"
    finally:
        os.unlink(path)


def test_special_chapter_types():
    content = "序章\n这是序章的内容。\n第一章 正文\n正文内容\n"
    path = _write_tmp(content)
    try:
        result = parse_novel_file(path)
        assert len(result) == 2
        assert result[0].source_chapter_label == "序章"
        assert result[0].title == "序章"
        assert "序章的内容" in result[0].content
        assert result[1].source_chapter_number == 1
        assert result[1].title == "正文"
    finally:
        os.unlink(path)


def test_single_chapter():
    content = "第一章 唯一\n唯一的内容。\n"
    path = _write_tmp(content)
    try:
        result = parse_novel_file(path)
        assert len(result) == 1
        assert result[0].title == "唯一"
        assert "唯一的内容" in result[0].content
    finally:
        os.unlink(path)


def test_empty_content():
    path = _write_tmp("")
    try:
        result = parse_novel_file(path)
        assert len(result) == 1
        assert result[0].title == ""
        assert result[0].content == ""
    finally:
        os.unlink(path)


def test_gbk_encoding():
    content = "第一章 测试\n内容\n"
    path = _write_tmp(content, encoding="gbk")
    try:
        result = parse_novel_file(path)
        assert len(result) == 1
        assert result[0].source_chapter_label == "第一章 测试"
        assert result[0].title == "测试"
    finally:
        os.unlink(path)


def test_parse_source_file_matches_parser_output_for_chaptered_text():
    content = "第一章 开端\n这是第一章的内容。\n第二章 发展\n这是第二章的内容。\n"
    path = _write_tmp(content)
    try:
        parsed = parse_source_file(
            path,
            content_format="plain_text",
            requested_language=None,
        )
        direct = parse_novel_file(path)
        assert parsed.resolved_language == "zh"
        assert parsed.source_chars == len(content)
        assert parsed.chapters == direct
    finally:
        os.unlink(path)


def test_parse_source_file_matches_parser_output_without_markers():
    content = "Just some text without any chapter markers."
    path = _write_tmp(content)
    try:
        parsed = parse_source_file(
            path,
            content_format="plain_text",
            requested_language="en",
        )
        direct = parse_novel_file(path, language="en")
        assert parsed.resolved_language == "en"
        assert parsed.source_chars == len(content)
        assert parsed.chapters == direct
    finally:
        os.unlink(path)
