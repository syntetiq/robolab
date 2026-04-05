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

    # Office assets and prep pipeline
    office_dir = REPO_ROOT / "scenes/Office"
    office_dir_alt = REPO_ROOT / "scenes/office"
    if not office_dir.exists() and office_dir_alt.exists():
        office_dir = office_dir_alt
    expect(office_dir, errors, "Office scenes dir")
    office_usdz = sorted(office_dir.glob("*.usdz"))
    if len(office_usdz) < 1:
        errors.append("No Office .usdz assets found under scenes/Office")
    expect(REPO_ROOT / "scripts/prepare_office_scene_assets.ps1", errors, "Office prep script")
    expect(REPO_ROOT / "scripts/adapt_scenes_for_tiago.py", errors, "Scene adapter script")
    expect(REPO_ROOT / "config/scene_prep_manifest.json", errors, "Scene prep manifest")
    expect(REPO_ROOT / "scripts/scene_prep_contract.py", errors, "Scene prep contract helper")
    expect(REPO_ROOT / "scripts/check_scene_physics_coverage.py", errors, "Scene physics coverage gate")
    expect(REPO_ROOT / "scripts/scene_fit_validator.py", errors, "Scene fit validator")

    # Kitchen raw mesh prep pipeline
    kitchen_raw_dir = REPO_ROOT / "scenes/kitchen/1"
    expect(kitchen_raw_dir, errors, "Kitchen raw mesh dir")
    if kitchen_raw_dir.exists():
        if len(list(kitchen_raw_dir.glob("*.obj"))) < 1:
            errors.append("Kitchen raw mesh dir has no .obj files")
        if len(list(kitchen_raw_dir.glob("*.dae"))) < 1:
            errors.append("Kitchen raw mesh dir has no .dae files")
    expect(REPO_ROOT / "scripts/build_kitchen_scene_wrapper.py", errors, "Kitchen wrapper script")
    expect(REPO_ROOT / "scenes/kitchen/README.md", errors, "Kitchen README")

    if errors:
        print("[FAIL] Scene assets regression failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("[OK] Scene assets regression checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
