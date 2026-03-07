# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

import re
from pathlib import Path
from typing import List, Tuple


def parse_novel_file(file_path: str) -> List[Tuple[int, str, str]]:
    """
    Parse novel file and split by chapters.

    Returns:
        List[(chapter_num, chapter_title, chapter_content)]

    Note:
        `chapter_title` preserves the full title line (e.g. "第一章 开端", "Chapter 1 Beginning").
        Downstream UI can choose how to display it.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Novel file not found: {file_path}")

    # Include gb18030 (superset of gbk) since many CN/TW novel dumps use it.
    encodings = ["utf-8", "gb18030", "gbk", "gb2312", "utf-16"]
    content = None

    for encoding in encodings:
        try:
            content = path.read_text(encoding=encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if content is None:
        raise ValueError(f"Unable to decode file with supported encodings: {file_path}")

    # Chapter title patterns (must be at line start)
    # Pattern matches: 第X章, 第X回, 第X节 (Chinese numerals or Arabic)
    # Also matches: 序章, 序言, 楔子, 尾声, 后记, 番外
    chapter_title_patterns = [
        r"^\s*(?:第[0-9零一二三四五六七八九十百千万]+[章回节]|序[章言]|楔子|尾声|后记|番外).*$",
        r"^\s*Chapter\s+\d+.*$",
    ]

    # Find all chapter titles and their positions
    chapter_positions = []
    for pattern in chapter_title_patterns:
        for match in re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE):
            chapter_positions.append((match.start(), match.group()))
        if chapter_positions:
            break

    if not chapter_positions:
        # Fallback: treat entire content as one chapter
        return [(1, "Chapter 1", content.strip())]

    # Sort by position (should already be sorted, but ensure)
    chapter_positions.sort(key=lambda x: x[0])

    # Extract chapters with content
    result = []
    for i, (pos, title) in enumerate(chapter_positions):
        # Content starts after the title line
        content_start = pos + len(title)
        # Content ends at next chapter or end of file
        if i + 1 < len(chapter_positions):
            content_end = chapter_positions[i + 1][0]
        else:
            content_end = len(content)

        chapter_content = content[content_start:content_end].strip()
        result.append((i + 1, title.strip(), chapter_content))

    return result


def chinese_to_arabic(chinese_num: str) -> int:
    """Convert Chinese numerals to Arabic numerals."""
    chinese_digits = {
        "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }
    chinese_units = {"十": 10, "百": 100, "千": 1000, "万": 10000}

    if chinese_num.isdigit():
        return int(chinese_num)

    result = 0
    temp = 0

    for char in chinese_num:
        if char in chinese_digits:
            temp = chinese_digits[char]
        elif char in chinese_units:
            if temp == 0:
                temp = 1
            result += temp * chinese_units[char]
            temp = 0

    result += temp
    return result if result > 0 else 1
