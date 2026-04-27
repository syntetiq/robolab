#!/usr/bin/env python3
"""
Create Tiago-compatible USDA wrappers for USD/USDZ scenes.

Improvements over v1:
- Environment ref overridden with physics:rigidBodyEnabled=false so that
  any dynamic rigid bodies in the source USDZ cannot fall under gravity.
- Floor collider raised slightly and dedicated contact offset for stable
  robot-floor contact.
- RobotSpawnPad placed AT the floor level (z=-0.1) instead of ABOVE it,
  so the robot does not spawn inside the collision geometry.
- Larger ground plane (100x100 m).
- ASCII-only comments to avoid USD parser encoding issues on Windows.
"""

import argparse
from pathlib import Path

from scene_prep_contract import resolve_scene_prep_contract


def as_usd_ref(path: Path) -> str:
    normalized = str(path.resolve()).replace("\\", "/")
    return f"@{normalized}@"


def build_wrapper(source_path: Path, output_path: Path, manifest_path: Path | None = None) -> None:
    contract = resolve_scene_prep_contract(source_path.name, manifest_path=manifest_path)
    floor_scale = f"{contract.floor_size_xy:.4f}, {contract.floor_size_xy:.4f}, {contract.floor_half_height * 2.0:.4f}"
    floor_z = contract.floor_top_z - contract.floor_half_height
    spawn_pad_scale = f"{contract.spawn_pad_size_x:.4f}, {contract.spawn_pad_size_y:.4f}, {contract.spawn_pad_height:.4f}"
    spawn_pad_z = contract.spawn_z - (contract.spawn_pad_height / 2.0)
    text = f"""#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)

def Xform "World"
{{
    # --- Environment reference -------------------------------------------
    # Declare the environment with a reference and apply PhysicsRigidBodyAPI
    # to prevent any rigid-body children in the USDZ from becoming dynamic
    # (falling under gravity) when the PhysicsScene activates.
    def Xform "Environment" (
        prepend references = [{as_usd_ref(source_path)}]
        prepend apiSchemas = ["PhysicsRigidBodyAPI"]
    )
    {{
        bool physics:rigidBodyEnabled = false
        bool physics:kinematicEnabled = true
    }}

    # --- Physics scene ---------------------------------------------------
    def PhysicsScene "PhysicsScene"
    {{
        float3 physics:gravityDirection = (0, 0, -1)
        float physics:gravityMagnitude = 9.81
    }}

    # --- Static support geometry ----------------------------------------
    def Xform "RoboLabSupport" (
        kind = "component"
    )
    {{
        # Ground plane from scene prep contract.
        def Cube "FloorCollider" (
            prepend apiSchemas = ["PhysicsCollisionAPI"]
        )
        {{
            bool physics:collisionEnabled = 1
            float physics:contactOffset = {contract.contact_offset}
            float physics:restOffset = {contract.rest_offset}
            token visibility = "invisible"
            double size = 1
            float3 xformOp:scale = ({floor_scale})
            double3 xformOp:translate = (0, 0, {floor_z:.4f})
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
        }}

        # Reinforced collision pad at robot spawn pose from contract.
        def Cube "RobotSpawnPad" (
            prepend apiSchemas = ["PhysicsCollisionAPI"]
        )
        {{
            bool physics:collisionEnabled = 1
            token visibility = "invisible"
            double size = 1
            float3 xformOp:scale = ({spawn_pad_scale})
            double3 xformOp:translate = ({contract.spawn_x:.4f}, {contract.spawn_y:.4f}, {spawn_pad_z:.4f})
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
        }}

        # Small task-space proxy volume around spawn; used by fit validators.
        def Cube "TaskSpaceVolume" (
            prepend apiSchemas = ["PhysicsCollisionAPI"]
        )
        {{
            bool physics:collisionEnabled = 0
            token visibility = "invisible"
            double size = 1
            float3 xformOp:scale = (2.5, 2.5, 2.0)
            double3 xformOp:translate = ({contract.spawn_x:.4f}, {contract.spawn_y:.4f}, {contract.spawn_z + 1.0:.4f})
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
        }}
    }}
}}
"""
    output_path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Tiago-compatible scene wrappers.")
    parser.add_argument(
        "--input-dir",
        default=r"C:\RoboLab_Data\scenes",
        help="Folder with source USD/USDZ scenes.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Folder for generated wrappers. Defaults to --input-dir.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively search for USD/USDZ sources under --input-dir.",
    )
    parser.add_argument(
        "--include",
        default="*",
        help="Filename wildcard filter (e.g. '*Office*').",
    )
    parser.add_argument(
        "--manifest",
        default="",
        help="Scene prep manifest path. Defaults to config/scene_prep_manifest.json.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {input_dir}")
    output_dir = Path(args.output_dir) if args.output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    sources = []
    globber = input_dir.rglob if args.recursive else input_dir.glob
    include_pat = args.include or "*"
    for ext in ("*.usd", "*.usdz"):
        for candidate in globber(ext):
            if candidate.match(include_pat):
                sources.append(candidate)

    manifest_path = Path(args.manifest).resolve() if args.manifest else None

    created = []
    for source in sorted(sources):
        if "_TiagoCompatible" in source.name:
            continue
        output = output_dir / f"{source.stem}_TiagoCompatible.usda"
        build_wrapper(source.resolve(), output.resolve(), manifest_path=manifest_path)
        created.append(output)
        print(f"[SceneAdapt] Created/updated: {output.name}")

    print(f"[SceneAdapt] Done. Wrappers created/updated: {len(created)}")


if __name__ == "__main__":
    main()
