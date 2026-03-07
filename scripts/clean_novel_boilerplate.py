#!/usr/bin/env python3
"""
Remove common website navigation/boilerplate lines accidentally captured when scraping.

This is a conservative, line-based cleaner intended for already-downloaded .txt novels.
It is scoped by chapter number in the *title line* (e.g. 第2175章 ...).
"""

from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path


def detect_text_encoding(path: Path) -> str:
    sample = path.read_bytes()[:200_000]
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "gb2312", "utf-16"):
        try:
            sample.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "gb18030"


def _should_drop_line(s: str) -> bool:
    s = s.strip()
    if not s:
        return False

    # URLs / domains
    if "http://" in s or "https://" in s or "www." in s:
        return True

    # Common navigation / site chrome strings seen on hjwzw-like pages
    drop_substrings = [
        "快捷鍵",
        "上一章",
        "下一章",
        "目錄",
        "目录",
        "返回書頁",
        "返回书页",
        "手機網頁版",
        "手机网页版",
        "加入書簽",
        "加入书签",
        "收藏",
        "投票",
        "推薦票",
        "推荐票",
        "章節錯誤",
        "章节错误",
        "請記住本站域名",
        "请记住本站域名",
        "hjwzw",
    ]
    if any(x in s for x in drop_substrings):
        return True

    # Pure separators
    if re.fullmatch(r"[\|\-_=·•\s\xa0]+", s):
        return True

    return False


def clean_block(block: str) -> str:
    """
    Clean a chapter block that starts with a title line.
    Keep indentation in content lines; only decide drop/keep using stripped text.
    """
    lines = block.splitlines()
    if not lines:
        return block

    title = lines[0].rstrip()
    kept: list[str] = [title]

    blank_streak = 0
    for line in lines[1:]:
        check = line.strip()
        if _should_drop_line(check):
            continue

        if not check:
            blank_streak += 1
            if blank_streak >= 3:
                continue
            kept.append("")
            continue

        blank_streak = 0
        kept.append(line.rstrip())

    # Trim excessive leading/trailing blanks after title
    while len(kept) >= 2 and kept[1] == "":
        kept.pop(1)
    while kept and kept[-1] == "":
        kept.pop()

    return "\n".join(kept) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="Novel txt file path")
    ap.add_argument("--start", type=int, required=True, help="Start chapter number (in title), e.g. 2167")
    ap.add_argument("--end", type=int, required=True, help="End chapter number (in title), e.g. 2175")
    ap.add_argument("--marker", default="『还在连载中...』", help="Stop before this marker if present")
    ap.add_argument("--no-backup", action="store_true", help="Do not create a .bak copy")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")

    enc = detect_text_encoding(path)
    text = path.read_text(encoding=enc, errors="replace")

    marker_idx = text.find(args.marker)
    scan_text = text if marker_idx == -1 else text[:marker_idx]

    # Title line matcher for the requested range.
    title_re = re.compile(rf"^第({args.start}|{args.end}|\d+)章.*$", re.M)
    starts: list[tuple[int, str]] = []
    for m in title_re.finditer(scan_text):
        try:
            num = int(re.match(r"^第(\d+)章", m.group(0)).group(1))  # type: ignore[union-attr]
        except Exception:
            continue
        if args.start <= num <= args.end:
            starts.append((m.start(), m.group(0)))

    if not starts:
        print("No matching chapter titles found in the specified range.")
        return 1

    # Build exact chapter blocks by finding the next in-range title OR next any title
    # (to avoid running into footer/marker).
    any_title_re = re.compile(r"^第\d+章.*$", re.M)

    # Work from end -> start to keep indices stable when replacing.
    starts.sort(key=lambda t: t[0], reverse=True)
    new_text = text
    cleaned = 0

    for pos, title in starts:
        # Find the end boundary: next title after this one, or marker, or end of file.
        m_next = any_title_re.search(scan_text, pos + 1)
        end = m_next.start() if m_next else (marker_idx if marker_idx != -1 else len(text))

        block = new_text[pos:end]
        cleaned_block = clean_block(block)
        if cleaned_block != block:
            new_text = new_text[:pos] + cleaned_block + new_text[end:]
            cleaned += 1

    if cleaned == 0:
        print("No changes made (already clean?).")
        return 0

    if not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = path.with_suffix(path.suffix + f".bak_{ts}")
        shutil.copy2(path, bak)
        print(f"Backup written: {bak}")

    path.write_text(new_text, encoding=enc)
    print(f"Cleaned chapters: {cleaned} (encoding={enc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
