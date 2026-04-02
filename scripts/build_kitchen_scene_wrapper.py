#!/usr/bin/env python3
"""
Create a task-ready USDA wrapper for a converted kitchen USD asset.

This script does not convert OBJ/DAE directly. It expects a source USD/USDA/USDZ
that has already been converted by Isaac Sim importer or another DCC pipeline.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scene_prep_contract import resolve_scene_prep_contract


def to_usd_ref(path: Path) -> str:
    normalized = str(path.resolve()).replace("\\", "/")
    return f"@{normalized}@"


def build_wrapper(
    source_usd: Path,
    output_usda: Path,
    spawn_x: float,
    spawn_y: float,
    spawn_z: float,
    manifest_path: Path | None = None,
) -> None:
    contract = resolve_scene_prep_contract(source_usd.name, manifest_path=manifest_path)
    # CLI values remain an override for one-off alignment tasks.
    use_spawn_x = spawn_x if spawn_x is not None else contract.spawn_x
    use_spawn_y = spawn_y if spawn_y is not None else contract.spawn_y
    use_spawn_z = spawn_z if spawn_z is not None else contract.spawn_z
    floor_scale = f"{contract.floor_size_xy:.4f}, {contract.floor_size_xy:.4f}, {contract.floor_half_height * 2.0:.4f}"
    floor_z = contract.floor_top_z - contract.floor_half_height
    spawn_pad_scale = f"{contract.spawn_pad_size_x:.4f}, {contract.spawn_pad_size_y:.4f}, {contract.spawn_pad_height:.4f}"
    spawn_pad_z = use_spawn_z - (contract.spawn_pad_height / 2.0)
    text = f"""#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)

def Xform "World"
{{
    def Xform "Environment" (
        prepend references = [{to_usd_ref(source_usd)}]
        prepend apiSchemas = ["PhysicsRigidBodyAPI"]
    )
    {{
        bool physics:rigidBodyEnabled = false
        bool physics:kinematicEnabled = true
    }}

    def PhysicsScene "PhysicsScene"
    {{
        float3 physics:gravityDirection = (0, 0, -1)
        float physics:gravityMagnitude = 9.81
    }}

    def Xform "RoboLabSupport"
    {{
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

        def Cube "RobotSpawnPad" (
            prepend apiSchemas = ["PhysicsCollisionAPI"]
        )
        {{
            bool physics:collisionEnabled = 1
            token visibility = "invisible"
            double size = 1
            float3 xformOp:scale = ({spawn_pad_scale})
            double3 xformOp:translate = ({use_spawn_x:.4f}, {use_spawn_y:.4f}, {spawn_pad_z:.4f})
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
        }}
    }}
}}
"""
    output_usda.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build kitchen USDA wrapper from converted USD.")
    parser.add_argument("--source-usd", required=True, help="Path to converted kitchen USD/USDZ asset.")
    parser.add_argument(
        "--output-usda",
        default=r"C:\RoboLab_Data\scenes\Kitchen_Modern_TiagoCompatible.usda",
        help="Output wrapper path.",
    )
    parser.add_argument("--spawn-x", type=float, default=0.8)
    parser.add_argument("--spawn-y", type=float, default=0.0)
    parser.add_argument("--spawn-z", type=float, default=0.0)
    parser.add_argument("--manifest", default="", help="Scene prep manifest path.")
    args = parser.parse_args()

    source = Path(args.source_usd)
    if not source.exists():
        raise FileNotFoundError(f"Converted source USD not found: {source}")

    output = Path(args.output_usda)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest).resolve() if args.manifest else None
    build_wrapper(source, output, args.spawn_x, args.spawn_y, args.spawn_z, manifest_path=manifest_path)
    print(f"[KitchenWrapper] Created: {output}")


if __name__ == "__main__":
    main()
