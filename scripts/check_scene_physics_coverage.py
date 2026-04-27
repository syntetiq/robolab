#!/usr/bin/env python3
"""
Static physics coverage checks for Tiago-compatible scene wrappers.

This does not run Isaac Sim. It verifies that wrapper contracts needed for
stable robot interaction exist and match the scene prep manifest.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scene_prep_contract import resolve_scene_prep_contract


REQUIRED_SNIPPETS = [
    'def PhysicsScene "PhysicsScene"',
    'def Cube "FloorCollider"',
    'def Cube "RobotSpawnPad"',
    'prepend apiSchemas = ["PhysicsCollisionAPI"]',
    "physics:contactOffset",
    "physics:restOffset",
]


def expected_spawn_snippet(contract, wrapper_text: str) -> bool:
    z_center = contract.spawn_z - (contract.spawn_pad_height / 2.0)
    expected = f"double3 xformOp:translate = ({contract.spawn_x:.4f}, {contract.spawn_y:.4f}, {z_center:.4f})"
    return expected in wrapper_text


def check_wrapper(wrapper_path: Path, manifest_path: Path, errors: list[str], warnings: list[str], strict_spawn: bool) -> None:
    text = wrapper_path.read_text(encoding="utf-8")
    for snippet in REQUIRED_SNIPPETS:
        if snippet not in text:
            errors.append(f"{wrapper_path.name}: missing required snippet '{snippet}'")

    contract = resolve_scene_prep_contract(wrapper_path.name, manifest_path=manifest_path)
    if not expected_spawn_snippet(contract, text):
        message = f"{wrapper_path.name}: RobotSpawnPad translate does not match manifest profile '{contract.profile_id}'"
        if strict_spawn:
            errors.append(message)
        else:
            warnings.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check physics coverage in scene wrappers.")
    parser.add_argument(
        "--runtime-scenes-dir",
        default=r"C:\RoboLab_Data\scenes",
        help="Directory with *_TiagoCompatible.usda wrappers.",
    )
    parser.add_argument(
        "--manifest",
        default=str(Path(__file__).resolve().parents[1] / "config" / "scene_prep_manifest.json"),
        help="Scene prep manifest path.",
    )
    parser.add_argument(
        "--include",
        default="*Office*_TiagoCompatible.usda,*Meeting*_TiagoCompatible.usda,*Canonical*_TiagoCompatible.usda,*Kitchen*_TiagoCompatible.usda",
        help="Comma-separated glob patterns for wrappers to validate.",
    )
    parser.add_argument(
        "--strict-spawn",
        action="store_true",
        help="Fail if RobotSpawnPad does not match manifest spawn pose.",
    )
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_scenes_dir)
    manifest_path = Path(args.manifest)
    if not runtime_dir.exists():
        print(f"[FAIL] runtime scenes dir not found: {runtime_dir}")
        return 2
    if not manifest_path.exists():
        print(f"[FAIL] manifest not found: {manifest_path}")
        return 2

    patterns = [p.strip() for p in str(args.include).split(",") if p.strip()]
    wrappers: list[Path] = []
    for pat in patterns:
        wrappers.extend(runtime_dir.glob(pat))
    wrappers = sorted(set(wrappers))
    if not wrappers:
        print(f"[FAIL] no wrappers matched include patterns in {runtime_dir}")
        return 2

    errors: list[str] = []
    warnings: list[str] = []
    for wrapper in wrappers:
        check_wrapper(wrapper, manifest_path, errors, warnings, strict_spawn=bool(args.strict_spawn))

    if errors:
        print("[FAIL] Scene physics coverage checks failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    if warnings:
        print("[WARN] Scene physics coverage warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    print(f"[OK] Scene physics coverage checks passed ({len(wrappers)} wrappers).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
