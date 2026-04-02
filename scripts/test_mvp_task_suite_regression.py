"""
Regression checks for MVP task suite coverage.

Validates that required fixed task configs exist and include required task types
for the 5 main scenarios:
  1) pick/place to sink
  2) pick/place to fridge
  3) pick/place to dishwasher
  4) open/close fridge
  5) open/close dishwasher
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = REPO_ROOT / "config" / "tasks"

REQUIRED_CONFIGS = {
    "fixed_banana_to_sink.json": {"pick_object", "place_object"},
    "fixed_mug_to_fridge.json": {"pick_object", "place_object"},
    "fixed_mug_to_dishwasher.json": {"pick_object", "place_object"},
    "fixed_fridge_open_close.json": {"open_door", "close_door"},
    "fixed_dishwasher_open_close.json": {"open_door", "close_door"},
}


def main() -> int:
    errors = []
    for filename, required_types in REQUIRED_CONFIGS.items():
        path = TASK_DIR / filename
        if not path.exists():
            errors.append(f"missing config: {path}")
            continue
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid JSON in {path}: {exc}")
            continue

        if cfg.get("kitchen_scene") != "fixed":
            errors.append(f"{filename}: kitchen_scene must be 'fixed'")

        tasks = cfg.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            errors.append(f"{filename}: tasks must be a non-empty list")
            continue

        task_types = {str(t.get("type", "")) for t in tasks if isinstance(t, dict)}
        missing_types = sorted(required_types - task_types)
        if missing_types:
            errors.append(f"{filename}: missing required task types: {', '.join(missing_types)}")

    if errors:
        print("[FAIL] MVP task suite regression failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("[OK] MVP task suite coverage checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
