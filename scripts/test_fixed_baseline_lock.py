#!/usr/bin/env python3
"""
Fail-fast lock for fixed baseline contracts.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def must_exist(path: Path, errors: list[str], label: str) -> None:
    if not path.exists():
        errors.append(f"{label} missing: {path}")


def main() -> int:
    errors: list[str] = []
    must_exist(REPO_ROOT / "scenes/kitchen_fixed/kitchen_fixed_builder.py", errors, "fixed builder")
    must_exist(REPO_ROOT / "scenes/kitchen_fixed/kitchen_fixed_config.yaml", errors, "fixed config")

    required_fixed_configs = [
        "fixed_banana_to_sink.json",
        "fixed_mug_to_fridge.json",
        "fixed_mug_to_dishwasher.json",
        "fixed_fridge_open_close.json",
        "fixed_dishwasher_open_close.json",
    ]
    for name in required_fixed_configs:
        cfg = REPO_ROOT / "config/tasks" / name
        must_exist(cfg, errors, "fixed task config")
        if cfg.exists():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                if data.get("kitchen_scene") != "fixed":
                    errors.append(f"{name}: kitchen_scene must stay 'fixed'")
            except Exception as exc:
                errors.append(f"{name}: invalid json ({exc})")

    bench = REPO_ROOT / "scripts/test_robot_bench.py"
    must_exist(bench, errors, "test_robot_bench")
    if bench.exists():
        text = bench.read_text(encoding="utf-8")
        for snippet in (
            "if use_fixed_kitchen:",
            "[Bench] Lights: using fixed kitchen light rig only",
            "UsdLux.DomeLight.Define",
            "UsdLux.DistantLight.Define",
        ):
            if snippet not in text:
                errors.append(f"test_robot_bench.py missing baseline snippet: {snippet}")

        if not re.search(r"navigate_to", text):
            errors.append("test_robot_bench.py missing navigate_to task handling")
        if not re.search(r"open_door", text):
            errors.append("test_robot_bench.py missing open_door task handling")

    if errors:
        print("[FAIL] Fixed baseline lock failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("[OK] Fixed baseline lock passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
