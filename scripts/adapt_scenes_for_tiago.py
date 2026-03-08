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


def as_usd_ref(path: Path) -> str:
    normalized = str(path.resolve()).replace("\\", "/")
    return f"@{normalized}@"


def build_wrapper(source_path: Path, output_path: Path) -> None:
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
        # Ground plane: 100x100 m, 0.2 m thick, top surface exactly at z=0.
        # Centre = (0, 0, -0.1); half-extent in Z = 0.1 => top at z=0.
        def Cube "FloorCollider" (
            prepend apiSchemas = ["PhysicsCollisionAPI"]
        )
        {{
            bool physics:collisionEnabled = 1
            float physics:contactOffset = 0.02
            float physics:restOffset = 0.0
            token visibility = "invisible"
            double size = 1
            float3 xformOp:scale = (100, 100, 0.2)
            double3 xformOp:translate = (0, 0, -0.1)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
        }}

        # Reinforced collision pad at robot spawn (1.0, -1.0).
        # Same level as FloorCollider so there is no step under the wheels.
        # Top surface at z=0; robot spawns at z=0.03 which is above this pad.
        def Cube "RobotSpawnPad" (
            prepend apiSchemas = ["PhysicsCollisionAPI"]
        )
        {{
            bool physics:collisionEnabled = 1
            token visibility = "invisible"
            double size = 1
            float3 xformOp:scale = (2.0, 2.0, 0.2)
            double3 xformOp:translate = (1.0, -1.0, -0.1)
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
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {input_dir}")

    sources = []
    for ext in ("*.usd", "*.usdz"):
        sources.extend(input_dir.glob(ext))

    created = []
    for source in sorted(sources):
        if "_TiagoCompatible" in source.name:
            continue
        output = source.with_name(f"{source.stem}_TiagoCompatible.usda")
        build_wrapper(source.resolve(), output.resolve())
        created.append(output)
        print(f"[SceneAdapt] Created/updated: {output.name}")

    print(f"[SceneAdapt] Done. Wrappers created/updated: {len(created)}")


if __name__ == "__main__":
    main()
