"""
Validate episode metadata against object diversity profile.

Usage:
  python scripts/check_object_diversity.py --episode-dir C:\\RoboLab_Data\\episodes\\<id>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Validate object diversity in episode metadata.")
    parser.add_argument(
        "--episode-dir",
        type=str,
        required=True,
        help="Episode directory containing metadata.json",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="config/object_diversity_profile.json",
        help="Path to diversity profile JSON",
    )
    return parser.parse_args()


def fail(msg: str) -> int:
    print(f"[FAIL] {msg}")
    return 1


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    episode_dir = Path(args.episode_dir)
    profile_path = Path(args.profile)
    if not profile_path.is_absolute():
        profile_path = repo_root / profile_path

    metadata_path = episode_dir / "metadata.json"
    if not metadata_path.exists():
        return fail(f"metadata.json not found: {metadata_path}")
    if not profile_path.exists():
        return fail(f"profile not found: {profile_path}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    category_counts = metadata.get("spawned_object_category_counts") or {}
    total = int(metadata.get("spawned_object_count") or 0)
    required = list(profile.get("required_categories") or [])
    min_total = int(profile.get("min_total_objects", 0))
    min_each = int(profile.get("min_objects_per_category", 0))

    errors = []
    if total < min_total:
        errors.append(f"spawned_object_count={total} < min_total_objects={min_total}")

    for category in required:
        count = int(category_counts.get(category, 0))
        if count < min_each:
            errors.append(
                f"category '{category}' count={count} < min_objects_per_category={min_each}"
            )

    if errors:
        print("[FAIL] Object diversity check failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("[OK] Object diversity profile satisfied.")
    print(f"  total: {total}")
    for category in required:
        print(f"  {category}: {int(category_counts.get(category, 0))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
