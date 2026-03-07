#!/usr/bin/env python3
"""Sync Trellis workflow docs between Codex skills and Claude commands.

Examples:
  python3 scripts/sync_trellis_workflow.py pr
  python3 scripts/sync_trellis_workflow.py pr --canonical claude --description "Create and merge PR with cloud CI checks"
  python3 scripts/sync_trellis_workflow.py pr --check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
META_LINE_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    raw_meta, body = match.groups()
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        line = line.strip()
        if not line:
            continue

        meta_match = META_LINE_RE.match(line)
        if not meta_match:
            continue

        key, value = meta_match.groups()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        meta[key] = value

    return meta, body


def remove_usage_section(text: str) -> str:
    lines = text.splitlines()
    start = -1

    for idx, line in enumerate(lines):
        if line.strip() == "## Usage":
            start = idx
            break

    if start < 0:
        return text

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break

    kept_lines = lines[:start] + lines[end:]
    return "\n".join(kept_lines).strip() + "\n"


def ensure_usage_section(text: str, name: str) -> str:
    if re.search(r"(?m)^## Usage\s*$", text):
        return text.rstrip() + "\n"

    usage_block = f"## Usage\n\n```bash\n${name}\n```"
    match = re.search(r"(?m)^## ", text)

    if match:
        prefix = text[: match.start()].rstrip()
        suffix = text[match.start() :].lstrip("\n")
        return f"{prefix}\n\n{usage_block}\n\n{suffix.rstrip()}\n"

    return f"{text.rstrip()}\n\n{usage_block}\n"


def first_paragraph(text: str) -> str:
    lines = text.splitlines()
    paragraph_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if paragraph_lines:
                break
            continue

        if stripped.startswith("#"):
            continue

        if stripped.startswith("**") and stripped.endswith("**"):
            continue

        if stripped.startswith("```"):
            continue

        paragraph_lines.append(stripped)

    return " ".join(paragraph_lines).strip()


def escape_yaml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_claude_command(codex_skill_text: str) -> str:
    _, body = split_frontmatter(codex_skill_text)
    cleaned = remove_usage_section(body)
    return cleaned.rstrip() + "\n"


def build_codex_skill(
    claude_command_text: str,
    name: str,
    description: str,
) -> str:
    body = ensure_usage_section(claude_command_text, name)
    frontmatter = "\n".join(
        [
            "---",
            f"name: {name}",
            f"description: {escape_yaml_string(description)}",
            "---",
        ]
    )
    return frontmatter + "\n\n" + body.rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Trellis workflow docs between Codex skills and Claude commands."
    )
    parser.add_argument("name", help="Workflow name, e.g. pr")
    parser.add_argument(
        "--canonical",
        choices=("codex", "claude"),
        default="codex",
        help="Which side is source-of-truth (default: codex)",
    )
    parser.add_argument(
        "--description",
        help="Required when --canonical claude and no existing Codex description exists.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when files are out of sync; do not write files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files.",
    )
    return parser.parse_args()


def read_required(path: Path, label: str) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return path.read_text(encoding="utf-8")


def maybe_write(path: Path, content: str, dry_run: bool) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == content:
        print(f"[OK] Up to date: {path}")
        return False

    if dry_run:
        print(f"[DRY-RUN] Would update: {path}")
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"[OK] Updated: {path}")
    return True


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    codex_path = repo_root / ".agents" / "skills" / args.name / "SKILL.md"
    claude_path = repo_root / ".claude" / "commands" / "trellis" / f"{args.name}.md"

    if args.canonical == "codex":
        codex_text = read_required(codex_path, "Codex skill")
        target_claude = build_claude_command(codex_text)

        current_claude = claude_path.read_text(encoding="utf-8") if claude_path.exists() else None
        in_sync = current_claude == target_claude

        if args.check:
            if in_sync:
                print(f"[OK] In sync: {args.name}")
                return 0
            print(f"[ERR] Out of sync: {args.name}")
            return 1

        maybe_write(claude_path, target_claude, args.dry_run)
        return 0

    claude_text = read_required(claude_path, "Claude command")
    existing_codex = codex_path.read_text(encoding="utf-8") if codex_path.exists() else ""
    existing_meta, _ = split_frontmatter(existing_codex)

    description = args.description or existing_meta.get("description")
    if not description:
        inferred = first_paragraph(claude_text)
        description = inferred if inferred else "Workflow skill"

    target_codex = build_codex_skill(claude_text, args.name, description)
    current_codex = codex_path.read_text(encoding="utf-8") if codex_path.exists() else None
    in_sync = current_codex == target_codex

    if args.check:
        if in_sync:
            print(f"[OK] In sync: {args.name}")
            return 0
        print(f"[ERR] Out of sync: {args.name}")
        return 1

    maybe_write(codex_path, target_codex, args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        raise SystemExit(2)
