#!/usr/bin/env python3
"""
Remove a contiguous numeric chapter range from a novel .txt file.

This is useful to roll back mistakenly appended chapters.

The range is matched by *title line* pattern: ^第{num}章
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--marker", default="『还在连载中...』", help="Stop boundary marker (if present)")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    if args.end < args.start:
        raise SystemExit("--end must be >= --start")

    path = Path(args.file)
    enc = detect_text_encoding(path)
    text = path.read_text(encoding=enc, errors="replace")

    # Find the first chapter title in range and the last chapter title in range.
    any_title_re = re.compile(r"^第(\d+)章.*$", re.M)
    first_pos: int | None = None
    last_pos: int | None = None
    last_num: int | None = None

    for m in any_title_re.finditer(text):
        try:
            num = int(m.group(1))
        except Exception:
            continue
        if args.start <= num <= args.end:
            if first_pos is None:
                first_pos = m.start()
            last_pos = m.start()
            last_num = num

    if first_pos is None or last_pos is None:
        print("No matching chapter titles found in the requested range; no changes made.")
        return 1

    # Determine end boundary: next chapter after the last matched one, or marker, or EOF.
    m_next = any_title_re.search(text, last_pos + 1)
    end_pos = m_next.start() if m_next else len(text)

    marker_idx = text.find(args.marker, last_pos + 1)
    if marker_idx != -1 and marker_idx < end_pos:
        end_pos = marker_idx

    # Include a preceding separator line if present (match our writer's style).
    # We only reach back within a small window to avoid deleting content accidentally.
    sep = "————"
    window_start = max(0, first_pos - 64)
    window = text[window_start:first_pos]
    sep_idx = window.rfind(sep)
    if sep_idx != -1:
        # ensure it's at line start (or after newline)
        abs_sep = window_start + sep_idx
        if abs_sep == 0 or text[abs_sep - 1] == "\n":
            first_pos = abs_sep

    removed_block = text[first_pos:end_pos]
    removed_titles = re.findall(r"^第\d+章.*$", removed_block, re.M)

    if not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = path.with_suffix(path.suffix + f".bak_{ts}")
        shutil.copy2(path, bak)
        print(f"Backup written: {bak}")

    new_text = text[:first_pos].rstrip("\n") + "\n\n" + text[end_pos:].lstrip("\n")
    path.write_text(new_text, encoding=enc)

    print(
        f"Removed chapters by title: {len(removed_titles)} "
        f"(range requested {args.start}-{args.end}, last_seen={last_num}). encoding={enc}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
