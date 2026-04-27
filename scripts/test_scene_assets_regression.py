"""
Scene asset regression checks for additive Office/Kitchen integration.

This gate intentionally preserves the fixed kitchen baseline while validating
that new Office/Kitchen asset pipelines remain wired.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def expect(path: Path, errors: list[str], label: str) -> None:
    if not path.exists():
        errors.append(f"{label} missing: {path}")


def main() -> int:
    errors: list[str] = []

    # Fixed baseline contract
    expect(REPO_ROOT / "scenes/kitchen_fixed/kitchen_fixed_builder.py", errors, "fixed builder")
    expect(REPO_ROOT / "scenes/kitchen_fixed/kitchen_fixed_config.yaml", errors, "fixed config")
    for fixed_cfg in [
        "fixed_banana_to_sink.json",
        "fixed_mug_to_fridge.json",
        "fixed_fridge_open_close.json",
    ]:
        cfg_path = REPO_ROOT / "config/tasks" / fixed_cfg
        expect(cfg_path, errors, "fixed task config")
        if cfg_path.exists():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
                if data.get("kitchen_scene") != "fixed":
                    errors.append(f"{fixed_cfg}: kitchen_scene must remain 'fixed'")
            except Exception as exc:
                errors.append(f"{fixed_cfg}: invalid JSON ({exc})")

    # Procedural office scene (builder + config)
    expect(REPO_ROOT / "scenes/office_fixed/office_fixed_builder.py", errors, "office builder")
    expect(REPO_ROOT / "scenes/office_fixed/office_fixed_config.yaml", errors, "office config")

    # At least one office task config that targets the procedural office scene
    office_task_configs = sorted((REPO_ROOT / "config/tasks").glob("office_*.json"))
    if not office_task_configs:
        errors.append("No office task configs found under config/tasks/office_*.json")

    # Shared scene utilities used by both kitchen_fixed and office_fixed builders
    expect(REPO_ROOT / "scenes/scene_utils.py", errors, "shared scene utils")

    # Common scene preparation gates (still required)
    expect(REPO_ROOT / "config/scene_prep_manifest.json", errors, "scene prep manifest")
    expect(REPO_ROOT / "scripts/scene_prep_contract.py", errors, "scene prep contract helper")
    expect(REPO_ROOT / "scripts/check_scene_physics_coverage.py", errors, "scene physics coverage gate")
    expect(REPO_ROOT / "scripts/scene_fit_validator.py", errors, "scene fit validator")

    if errors:
        print("[FAIL] Scene assets regression failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("[OK] Scene assets regression checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
