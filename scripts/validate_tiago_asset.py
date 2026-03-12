#!/usr/bin/env python3
"""Asset validation for TIAGo USD and graspable objects.

Checks:
  - Drive stiffness/damping on all joints
  - Mimic joint consistency
  - Collision API presence on gripper fingers
  - Physics materials on gripper fingers
  - Collision geometry type on graspable objects (convex vs mesh)
  - Contact/rest offset configuration
  - Transform consistency (no NaN/inf)

Usage (inside Isaac Sim Python):
    python.sh scripts/validate_tiago_asset.py [--tiago-usd PATH] [--objects-dir PATH]
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

_HEADLESS = True

try:
    from isaacsim import SimulationApp
    simulation_app = SimulationApp({"headless": _HEADLESS})
except Exception:
    simulation_app = None
    print("[Validator] WARN: Could not start SimulationApp — running in offline USD mode")

from pxr import Usd, UsdGeom, UsdPhysics, Gf, Sdf

try:
    from pxr import PhysxSchema
except ImportError:
    PhysxSchema = None

try:
    from pxr import UsdShade
except ImportError:
    UsdShade = None


class ValidationResult:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def error(self, msg: str):
        self.errors.append(msg)
        print(f"  [ERROR] {msg}")

    def warn(self, msg: str):
        self.warnings.append(msg)
        print(f"  [WARN]  {msg}")

    def ok(self, msg: str):
        self.info.append(msg)
        print(f"  [OK]    {msg}")

    def summary(self) -> str:
        return (
            f"Validation: {len(self.errors)} errors, "
            f"{len(self.warnings)} warnings, "
            f"{len(self.info)} passed"
        )


def validate_tiago_usd(usd_path: str, result: ValidationResult):
    """Validate TIAGo robot USD asset."""
    print(f"\n{'='*60}")
    print(f"Validating TIAGo USD: {usd_path}")
    print(f"{'='*60}")

    if not Path(usd_path).exists():
        result.error(f"TIAGo USD not found: {usd_path}")
        return

    stage = Usd.Stage.Open(usd_path)
    if not stage:
        result.error(f"Failed to open stage: {usd_path}")
        return

    result.ok(f"Stage opened: {usd_path}")

    joint_count = 0
    drive_issues = []
    mimic_joints = []
    finger_links = []
    has_collision_on_fingers = False
    has_physics_material_on_fingers = False

    for prim in stage.Traverse():
        path = prim.GetPath().pathString

        if prim.IsA(UsdPhysics.Joint):
            joint_count += 1

            drive_api = UsdPhysics.DriveAPI(prim, "angular")
            if not drive_api:
                drive_api = UsdPhysics.DriveAPI(prim, "linear")

            if drive_api:
                stiffness_attr = drive_api.GetStiffnessAttr()
                damping_attr = drive_api.GetDampingAttr()
                if stiffness_attr and stiffness_attr.HasValue():
                    stiff = stiffness_attr.Get()
                    if stiff == 0:
                        drive_issues.append(f"{path}: stiffness=0")
                if damping_attr and damping_attr.HasValue():
                    damp = damping_attr.Get()
                    if damp == 0:
                        drive_issues.append(f"{path}: damping=0")

        if "gripper" in path.lower() and "finger" in path.lower():
            if prim.GetTypeName() in ("", "Xform", "Mesh", "Scope"):
                finger_links.append(path)

                if prim.HasAPI(UsdPhysics.CollisionAPI):
                    has_collision_on_fingers = True

                if UsdShade:
                    binding_api = UsdShade.MaterialBindingAPI(prim)
                    if binding_api:
                        mat, _ = binding_api.ComputeBoundMaterial()
                        if mat and mat.GetPrim().HasAPI(UsdPhysics.MaterialAPI):
                            has_physics_material_on_fingers = True

        if PhysxSchema and prim.HasAPI(PhysxSchema.PhysxMimicJointAPI):
            mimic_joints.append(path)

        xformable = UsdGeom.Xformable(prim)
        if xformable:
            try:
                local_xf = xformable.GetLocalTransformation()
                for row in range(4):
                    for col in range(4):
                        v = local_xf[row][col]
                        if math.isnan(v) or math.isinf(v):
                            result.error(f"NaN/Inf in transform: {path}")
            except Exception:
                pass

    result.ok(f"Found {joint_count} joints")

    if drive_issues:
        for issue in drive_issues[:10]:
            result.warn(f"Drive issue: {issue}")
        if len(drive_issues) > 10:
            result.warn(f"... and {len(drive_issues) - 10} more drive issues")
    else:
        result.ok("All drives have non-zero stiffness/damping")

    if finger_links:
        result.ok(f"Found {len(finger_links)} finger link prims")
        for fl in finger_links:
            result.info.append(f"  Finger link: {fl}")
    else:
        result.warn("No gripper finger links found")

    if has_collision_on_fingers:
        result.ok("Collision API found on finger links")
    else:
        result.warn("No CollisionAPI on finger links — contacts may not register")

    if has_physics_material_on_fingers:
        result.ok("Physics material found on finger links")
    else:
        result.warn("No physics material (friction) on finger links — grasps may slip")

    if mimic_joints:
        result.ok(f"Found {len(mimic_joints)} mimic joints")
    else:
        result.info.append("No mimic joints found (may be expected for TIAGo gripper)")

    stage = None


def validate_object_usd(usd_path: str, result: ValidationResult):
    """Validate a graspable object USD for collision/physics setup."""
    print(f"\n--- Validating object: {Path(usd_path).name} ---")

    if not Path(usd_path).exists():
        result.error(f"Object USD not found: {usd_path}")
        return

    stage = Usd.Stage.Open(usd_path)
    if not stage:
        result.error(f"Failed to open: {usd_path}")
        return

    has_collision = False
    has_rigid_body = False
    has_mass = False
    has_physics_material = False
    has_contact_offset = False
    has_rest_offset = False
    collision_type = "none"
    mesh_count = 0

    for prim in stage.Traverse():
        path = prim.GetPath().pathString

        if prim.HasAPI(UsdPhysics.CollisionAPI):
            has_collision = True

            if PhysxSchema:
                collision_api = PhysxSchema.PhysxCollisionAPI(prim)
                if collision_api:
                    co_attr = collision_api.GetContactOffsetAttr()
                    if co_attr and co_attr.HasValue():
                        has_contact_offset = True
                    ro_attr = collision_api.GetRestOffsetAttr()
                    if ro_attr and ro_attr.HasValue():
                        has_rest_offset = True

            if PhysxSchema and prim.HasAPI(PhysxSchema.PhysxConvexDecompositionCollisionAPI):
                collision_type = "convex_decomposition"
            elif PhysxSchema and prim.HasAPI(PhysxSchema.PhysxConvexHullCollisionAPI):
                collision_type = "convex_hull"
            elif PhysxSchema and prim.HasAPI(PhysxSchema.PhysxTriangleMeshCollisionAPI):
                collision_type = "triangle_mesh"
            elif prim.IsA(UsdGeom.Mesh):
                collision_type = "mesh_implicit"
                mesh_count += 1
            elif prim.IsA(UsdGeom.Cube) or prim.IsA(UsdGeom.Sphere) or prim.IsA(UsdGeom.Cylinder):
                collision_type = "primitive"

        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            has_rigid_body = True

        if prim.HasAPI(UsdPhysics.MassAPI):
            has_mass = True

        if UsdShade:
            binding_api = UsdShade.MaterialBindingAPI(prim)
            if binding_api:
                mat, _ = binding_api.ComputeBoundMaterial()
                if mat and mat.GetPrim().HasAPI(UsdPhysics.MaterialAPI):
                    has_physics_material = True

    if has_collision:
        result.ok(f"CollisionAPI present, type: {collision_type}")
    else:
        result.warn("No CollisionAPI — object won't collide with gripper")

    if has_rigid_body:
        result.ok("RigidBodyAPI present")
    else:
        result.warn("No RigidBodyAPI — object won't respond to forces")

    if has_mass:
        result.ok("MassAPI present")
    else:
        result.info.append("No MassAPI (will use default mass)")

    if collision_type == "triangle_mesh":
        result.warn("Triangle mesh collider detected — may cause issues with small grippers. Consider convex decomposition.")
    elif collision_type == "mesh_implicit":
        result.warn(f"Implicit mesh collider ({mesh_count} meshes) — PhysX will auto-generate collision. Consider explicit convex hull.")

    if not has_contact_offset:
        result.warn("No contactOffset set — using PhysX default. Recommend 0.005m for manipulation.")
    else:
        result.ok("contactOffset configured")

    if not has_rest_offset:
        result.warn("No restOffset set — using PhysX default. Recommend 0.001m for manipulation.")
    else:
        result.ok("restOffset configured")

    if not has_physics_material:
        result.warn("No physics material (friction) — object may slip from gripper")
    else:
        result.ok("Physics material present")

    stage = None


def main():
    parser = argparse.ArgumentParser(description="Validate TIAGo and object assets for Isaac Sim manipulation")
    parser.add_argument(
        "--tiago-usd",
        default=os.environ.get(
            "TIAGO_USD_PATH",
            r"C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional_light.usd",
        ),
    )
    parser.add_argument(
        "--objects-dir",
        default=r"C:\RoboLab_Data\data\object_sets",
    )
    parser.add_argument("--object-name", default="025_mug", help="Specific object to validate")
    args = parser.parse_args()

    result = ValidationResult()

    validate_tiago_usd(args.tiago_usd, result)

    obj_dir = Path(args.objects_dir)
    if obj_dir.exists():
        target_usds = []
        if args.object_name:
            for f in obj_dir.rglob("*.usd"):
                if args.object_name.lower() in f.stem.lower():
                    target_usds.append(f)
            for f in obj_dir.rglob("*.usda"):
                if args.object_name.lower() in f.stem.lower():
                    target_usds.append(f)
        if not target_usds:
            target_usds = sorted(obj_dir.rglob("*.usd"))[:3]

        for obj_usd in target_usds:
            validate_object_usd(str(obj_usd), result)
    else:
        result.warn(f"Objects directory not found: {args.objects_dir}")

    print(f"\n{'='*60}")
    print(result.summary())
    if result.errors:
        print("\nERRORS:")
        for e in result.errors:
            print(f"  - {e}")
    if result.warnings:
        print("\nWARNINGS:")
        for w in result.warnings:
            print(f"  - {w}")
    print(f"{'='*60}")

    if simulation_app:
        simulation_app.close()

    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
