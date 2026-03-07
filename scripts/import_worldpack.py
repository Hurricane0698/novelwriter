#!/usr/bin/env python3
"""One-off script to import a worldpack JSON file into a novel's world model.

Usage:
  scripts/uv_run.sh python scripts/import_worldpack.py \
      --novel-id 6 \
      --worldpack worldpack.baike.nitianxieshen.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.schemas import WorldpackV1Payload  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Import worldpack into novel DB")
    parser.add_argument("--novel-id", type=int, required=True)
    parser.add_argument("--worldpack", type=str, required=True, help="Path to worldpack JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, don't commit")
    args = parser.parse_args()

    wp_path = Path(args.worldpack)
    if not wp_path.exists():
        print(f"File not found: {wp_path}")
        return 1

    # Validate JSON + Pydantic schema
    raw = json.loads(wp_path.read_text(encoding="utf-8"))
    try:
        payload = WorldpackV1Payload(**raw)
    except Exception as e:
        print(f"Schema validation failed: {e}")
        return 1

    print(f"Validated: pack_id={payload.pack_id}, "
          f"{len(payload.entities)} entities, "
          f"{len(payload.relationships)} relationships, "
          f"{len(payload.systems)} systems")

    if args.dry_run:
        print("Dry run — skipping DB import.")
        return 0

    # Import via the same endpoint logic (inline, no HTTP)
    from app.api.world import import_worldpack_v1
    from app.models import Novel, User

    db = SessionLocal()
    try:
        novel = db.query(Novel).filter(Novel.id == args.novel_id).first()
        if not novel:
            print(f"Novel {args.novel_id} not found in DB")
            return 1

        # Create a minimal fake user (the endpoint requires it but doesn't use it for import logic)
        fake_user = db.query(User).first()
        if not fake_user:
            print("No users in DB")
            return 1

        result = import_worldpack_v1(
            novel_id=args.novel_id,
            body=payload,
            db=db,
            current_user=fake_user,
        )

        print(f"\nImport result for pack_id={result.pack_id}:")
        c = result.counts
        print(f"  Entities:      created={c.entities_created} updated={c.entities_updated} deleted={c.entities_deleted}")
        print(f"  Attributes:    created={c.attributes_created} updated={c.attributes_updated} deleted={c.attributes_deleted}")
        print(f"  Relationships: created={c.relationships_created} updated={c.relationships_updated} deleted={c.relationships_deleted}")
        print(f"  Systems:       created={c.systems_created} updated={c.systems_updated} deleted={c.systems_deleted}")

        if result.warnings:
            print(f"\nWarnings ({len(result.warnings)}):")
            for w in result.warnings:
                print(f"  [{w.code}] {w.message}")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
