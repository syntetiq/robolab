#!/usr/bin/env python3
"""
Generate 20 diverse graspable object USD assets for Tiago manipulation tasks.

Each object is a realistic-scale composition of UsdGeom primitives with
physics (RigidBody, Collision, Mass) and distinct preview materials.

Output: C:/RoboLab_Data/data/object_sets/<object_name>.usda

Categories:
  - Mugs (4 variants)
  - Bottles (4 variants)
  - Fruits (4 types)
  - Containers (4 types)
  - Kitchen items (4 types)

All geometry is in meters, Z-up. Objects are centered at origin so the
data_collector_tiago.py spawner can place them with a translate op.
"""

import os
import sys
from pathlib import Path

try:
    from pxr import Usd, UsdGeom, UsdShade, UsdPhysics, Gf, Sdf, Vt
except ImportError:
    print("ERROR: pxr (usd-core) not found. Install with: pip install usd-core")
    sys.exit(1)


OUT_DIR = Path(r"C:\RoboLab_Data\data\object_sets")


def _create_material(stage, mat_path, color, metallic=0.0, roughness=0.6):
    """Create a UsdPreviewSurface material with the given diffuse color."""
    mat = UsdShade.Material.Define(stage, mat_path)
    shader = UsdShade.Shader.Define(stage, f"{mat_path}/PBR")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def _apply_physics(prim, mass_kg):
    UsdPhysics.RigidBodyAPI.Apply(prim)
    UsdPhysics.CollisionAPI.Apply(prim)
    UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(mass_kg)


def _bind_material(prim, mat):
    UsdShade.MaterialBindingAPI.Apply(prim)
    UsdShade.MaterialBindingAPI(prim).Bind(mat)


def _xform(prim, translate=(0, 0, 0), scale=None, rotate_z=0):
    xf = UsdGeom.Xformable(prim)
    if translate != (0, 0, 0):
        xf.AddTranslateOp().Set(Gf.Vec3d(*translate))
    if rotate_z:
        xf.AddRotateZOp().Set(float(rotate_z))
    if scale:
        xf.AddScaleOp().Set(Gf.Vec3f(*scale))


def create_mug(stage, root, variant, mat):
    """Mug = cylinder body + torus-approximated handle (thin cylinder arc)."""
    body = UsdGeom.Cylinder.Define(stage, f"{root}/Body")
    body.CreateRadiusAttr(variant["radius"])
    body.CreateHeightAttr(variant["height"])
    body.CreateAxisAttr("Z")
    _xform(body.GetPrim(), translate=(0, 0, variant["height"] / 2))
    _bind_material(body.GetPrim(), mat)

    handle = UsdGeom.Cylinder.Define(stage, f"{root}/Handle")
    handle.CreateRadiusAttr(0.005)
    handle.CreateHeightAttr(variant["height"] * 0.6)
    handle.CreateAxisAttr("Z")
    _xform(handle.GetPrim(), translate=(variant["radius"] + 0.012, 0, variant["height"] * 0.5))
    _bind_material(handle.GetPrim(), mat)

    return stage.GetPrimAtPath(root)


def create_bottle(stage, root, variant, mat, cap_mat):
    """Bottle = cylinder body + narrower cylinder neck + sphere cap."""
    body = UsdGeom.Cylinder.Define(stage, f"{root}/Body")
    body.CreateRadiusAttr(variant["body_r"])
    body.CreateHeightAttr(variant["body_h"])
    body.CreateAxisAttr("Z")
    _xform(body.GetPrim(), translate=(0, 0, variant["body_h"] / 2))
    _bind_material(body.GetPrim(), mat)

    neck = UsdGeom.Cylinder.Define(stage, f"{root}/Neck")
    neck.CreateRadiusAttr(variant["neck_r"])
    neck.CreateHeightAttr(variant["neck_h"])
    neck.CreateAxisAttr("Z")
    _xform(neck.GetPrim(), translate=(0, 0, variant["body_h"] + variant["neck_h"] / 2))
    _bind_material(neck.GetPrim(), mat)

    cap = UsdGeom.Sphere.Define(stage, f"{root}/Cap")
    cap.CreateRadiusAttr(variant["neck_r"] + 0.002)
    top_z = variant["body_h"] + variant["neck_h"] + variant["neck_r"]
    _xform(cap.GetPrim(), translate=(0, 0, top_z))
    _bind_material(cap.GetPrim(), cap_mat)

    return stage.GetPrimAtPath(root)


def create_fruit(stage, root, shape, dims, mat):
    """Fruit = sphere (apple/orange) or scaled sphere (pear) or capsule (banana)."""
    if shape == "sphere":
        geo = UsdGeom.Sphere.Define(stage, f"{root}/Shape")
        geo.CreateRadiusAttr(dims["radius"])
        _xform(geo.GetPrim(), translate=(0, 0, dims["radius"]))
    elif shape == "ellipsoid":
        geo = UsdGeom.Sphere.Define(stage, f"{root}/Shape")
        geo.CreateRadiusAttr(1.0)
        _xform(geo.GetPrim(), translate=(0, 0, dims["sz"]),
               scale=(dims["sx"], dims["sy"], dims["sz"]))
    elif shape == "banana":
        seg1 = UsdGeom.Capsule.Define(stage, f"{root}/Seg1")
        seg1.CreateRadiusAttr(dims["radius"])
        seg1.CreateHeightAttr(dims["length"] * 0.5)
        seg1.CreateAxisAttr("Y")
        _xform(seg1.GetPrim(), translate=(0, 0, dims["radius"]))
        _bind_material(seg1.GetPrim(), mat)
        seg2 = UsdGeom.Capsule.Define(stage, f"{root}/Seg2")
        seg2.CreateRadiusAttr(dims["radius"] * 0.9)
        seg2.CreateHeightAttr(dims["length"] * 0.5)
        seg2.CreateAxisAttr("Y")
        _xform(seg2.GetPrim(), translate=(0.02, 0, dims["radius"] + 0.01), rotate_z=15)
        _bind_material(seg2.GetPrim(), mat)
        return stage.GetPrimAtPath(root)

    _bind_material(stage.GetPrimAtPath(f"{root}/Shape"), mat)
    return stage.GetPrimAtPath(root)


def create_container(stage, root, variant, mat, lid_mat=None):
    """Container = box or cylinder body, optionally with a lid."""
    if variant.get("shape") == "cylinder":
        body = UsdGeom.Cylinder.Define(stage, f"{root}/Body")
        body.CreateRadiusAttr(variant["radius"])
        body.CreateHeightAttr(variant["height"])
        body.CreateAxisAttr("Z")
        _xform(body.GetPrim(), translate=(0, 0, variant["height"] / 2))
    else:
        body = UsdGeom.Cube.Define(stage, f"{root}/Body")
        body.CreateSizeAttr(1.0)
        _xform(body.GetPrim(), translate=(0, 0, variant["height"] / 2),
               scale=(variant["width"], variant["depth"], variant["height"]))
    _bind_material(body.GetPrim(), mat)

    if lid_mat and variant.get("has_lid"):
        if variant.get("shape") == "cylinder":
            lid = UsdGeom.Cylinder.Define(stage, f"{root}/Lid")
            lid.CreateRadiusAttr(variant["radius"] + 0.002)
            lid.CreateHeightAttr(0.008)
            lid.CreateAxisAttr("Z")
        else:
            lid = UsdGeom.Cube.Define(stage, f"{root}/Lid")
            lid.CreateSizeAttr(1.0)
            _xform(lid.GetPrim(), translate=(0, 0, variant["height"] + 0.005),
                   scale=(variant["width"] + 0.004, variant["depth"] + 0.004, 0.008))
            _bind_material(lid.GetPrim(), lid_mat)
            return stage.GetPrimAtPath(root)
        _xform(lid.GetPrim(), translate=(0, 0, variant["height"] + 0.005))
        _bind_material(lid.GetPrim(), lid_mat)

    return stage.GetPrimAtPath(root)


def create_kitchen_item(stage, root, kind, mat):
    """Various kitchen items: plate, bowl, can, glass."""
    if kind == "plate":
        geo = UsdGeom.Cylinder.Define(stage, f"{root}/Plate")
        geo.CreateRadiusAttr(0.10)
        geo.CreateHeightAttr(0.015)
        geo.CreateAxisAttr("Z")
        _xform(geo.GetPrim(), translate=(0, 0, 0.0075))
        _bind_material(geo.GetPrim(), mat)
    elif kind == "bowl":
        geo = UsdGeom.Sphere.Define(stage, f"{root}/Bowl")
        geo.CreateRadiusAttr(0.07)
        _xform(geo.GetPrim(), translate=(0, 0, 0.035),
               scale=(1.0, 1.0, 0.5))
        _bind_material(geo.GetPrim(), mat)
    elif kind == "can":
        geo = UsdGeom.Cylinder.Define(stage, f"{root}/Can")
        geo.CreateRadiusAttr(0.033)
        geo.CreateHeightAttr(0.12)
        geo.CreateAxisAttr("Z")
        _xform(geo.GetPrim(), translate=(0, 0, 0.06))
        _bind_material(geo.GetPrim(), mat)
    elif kind == "glass":
        geo = UsdGeom.Cylinder.Define(stage, f"{root}/Glass")
        geo.CreateRadiusAttr(0.035)
        geo.CreateHeightAttr(0.14)
        geo.CreateAxisAttr("Z")
        _xform(geo.GetPrim(), translate=(0, 0, 0.07))
        _bind_material(geo.GetPrim(), mat)

    return stage.GetPrimAtPath(root)


OBJECTS = [
    # -- Mugs --
    {"name": "mug_ceramic_white", "cat": "mug",
     "variant": {"radius": 0.04, "height": 0.095},
     "color": (0.92, 0.90, 0.87), "mass": 0.35},
    {"name": "mug_ceramic_blue", "cat": "mug",
     "variant": {"radius": 0.038, "height": 0.09},
     "color": (0.20, 0.35, 0.65), "mass": 0.30},
    {"name": "mug_tall_red", "cat": "mug",
     "variant": {"radius": 0.035, "height": 0.12},
     "color": (0.75, 0.15, 0.10), "mass": 0.32},
    {"name": "mug_espresso_brown", "cat": "mug",
     "variant": {"radius": 0.028, "height": 0.06},
     "color": (0.45, 0.28, 0.15), "mass": 0.20},

    # -- Bottles --
    {"name": "bottle_water_clear", "cat": "bottle",
     "variant": {"body_r": 0.033, "body_h": 0.18, "neck_r": 0.013, "neck_h": 0.05},
     "color": (0.85, 0.92, 0.95), "cap_color": (0.2, 0.45, 0.8), "mass": 0.50},
    {"name": "bottle_juice_orange", "cat": "bottle",
     "variant": {"body_r": 0.038, "body_h": 0.20, "neck_r": 0.015, "neck_h": 0.04},
     "color": (0.95, 0.60, 0.15), "cap_color": (0.15, 0.55, 0.15), "mass": 0.60},
    {"name": "bottle_soda_green", "cat": "bottle",
     "variant": {"body_r": 0.030, "body_h": 0.22, "neck_r": 0.012, "neck_h": 0.06},
     "color": (0.15, 0.55, 0.20), "cap_color": (0.8, 0.8, 0.8), "mass": 0.45},
    {"name": "bottle_milk_white", "cat": "bottle",
     "variant": {"body_r": 0.042, "body_h": 0.16, "neck_r": 0.018, "neck_h": 0.04},
     "color": (0.95, 0.95, 0.93), "cap_color": (0.9, 0.1, 0.1), "mass": 0.55},

    # -- Fruits --
    {"name": "fruit_apple_red", "cat": "fruit", "shape": "sphere",
     "dims": {"radius": 0.04}, "color": (0.75, 0.12, 0.10), "mass": 0.18},
    {"name": "fruit_orange", "cat": "fruit", "shape": "sphere",
     "dims": {"radius": 0.042}, "color": (0.95, 0.55, 0.08), "mass": 0.20},
    {"name": "fruit_pear_green", "cat": "fruit", "shape": "ellipsoid",
     "dims": {"sx": 0.035, "sy": 0.035, "sz": 0.05}, "color": (0.55, 0.72, 0.20), "mass": 0.17},
    {"name": "fruit_banana", "cat": "fruit", "shape": "banana",
     "dims": {"radius": 0.018, "length": 0.18}, "color": (0.95, 0.88, 0.25), "mass": 0.12},

    # -- Containers --
    {"name": "container_tupperware_blue", "cat": "container",
     "variant": {"width": 0.12, "depth": 0.08, "height": 0.06, "has_lid": True},
     "color": (0.15, 0.35, 0.70), "lid_color": (0.20, 0.40, 0.75), "mass": 0.15},
    {"name": "container_round_red", "cat": "container",
     "variant": {"shape": "cylinder", "radius": 0.05, "height": 0.07, "has_lid": True},
     "color": (0.72, 0.12, 0.12), "lid_color": (0.80, 0.15, 0.15), "mass": 0.12},
    {"name": "container_lunch_box", "cat": "container",
     "variant": {"width": 0.16, "depth": 0.10, "height": 0.05, "has_lid": True},
     "color": (0.20, 0.60, 0.30), "lid_color": (0.25, 0.65, 0.35), "mass": 0.18},
    {"name": "container_jar_glass", "cat": "container",
     "variant": {"shape": "cylinder", "radius": 0.04, "height": 0.10, "has_lid": True},
     "color": (0.88, 0.90, 0.88), "lid_color": (0.7, 0.55, 0.25), "mass": 0.25},

    # -- Kitchen items --
    {"name": "plate_dinner_white", "cat": "kitchen", "kind": "plate",
     "color": (0.95, 0.95, 0.93), "mass": 0.45},
    {"name": "bowl_cereal_blue", "cat": "kitchen", "kind": "bowl",
     "color": (0.25, 0.42, 0.72), "mass": 0.30},
    {"name": "can_soda", "cat": "kitchen", "kind": "can",
     "color": (0.85, 0.10, 0.10), "mass": 0.35},
    {"name": "glass_drinking", "cat": "kitchen", "kind": "glass",
     "color": (0.82, 0.88, 0.92), "mass": 0.25},

    # -- Additional diversity (10 more) --
    {"name": "mug_travel_black", "cat": "mug",
     "variant": {"radius": 0.042, "height": 0.16},
     "color": (0.10, 0.10, 0.12), "mass": 0.40},
    {"name": "bottle_wine_dark", "cat": "bottle",
     "variant": {"body_r": 0.036, "body_h": 0.25, "neck_r": 0.012, "neck_h": 0.08},
     "color": (0.12, 0.08, 0.15), "cap_color": (0.70, 0.55, 0.20), "mass": 0.70},
    {"name": "fruit_lemon_yellow", "cat": "fruit", "shape": "ellipsoid",
     "dims": {"sx": 0.03, "sy": 0.025, "sz": 0.025}, "color": (0.95, 0.90, 0.20), "mass": 0.10},
    {"name": "fruit_avocado", "cat": "fruit", "shape": "ellipsoid",
     "dims": {"sx": 0.035, "sy": 0.03, "sz": 0.05}, "color": (0.20, 0.35, 0.12), "mass": 0.22},
    {"name": "container_spice_small", "cat": "container",
     "variant": {"shape": "cylinder", "radius": 0.025, "height": 0.08, "has_lid": True},
     "color": (0.60, 0.40, 0.15), "lid_color": (0.55, 0.55, 0.55), "mass": 0.08},
    {"name": "bowl_soup_cream", "cat": "kitchen", "kind": "bowl",
     "color": (0.92, 0.88, 0.78), "mass": 0.35},
    {"name": "can_beans", "cat": "kitchen", "kind": "can",
     "color": (0.20, 0.35, 0.65), "mass": 0.40},
    {"name": "glass_wine", "cat": "kitchen", "kind": "glass",
     "color": (0.90, 0.92, 0.94), "mass": 0.20},
    {"name": "container_butter_yellow", "cat": "container",
     "variant": {"width": 0.10, "depth": 0.06, "height": 0.04, "has_lid": True},
     "color": (0.95, 0.90, 0.40), "lid_color": (0.95, 0.92, 0.50), "mass": 0.10},
    {"name": "plate_small_green", "cat": "kitchen", "kind": "plate",
     "color": (0.30, 0.60, 0.25), "mass": 0.30},
]


def generate_object(obj_spec):
    name = obj_spec["name"]
    out_path = OUT_DIR / f"{name}.usda"

    stage = Usd.Stage.CreateNew(str(out_path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    root_path = f"/{name}"
    root_xf = UsdGeom.Xform.Define(stage, root_path)
    root_prim = root_xf.GetPrim()
    stage.SetDefaultPrim(root_prim)

    mat = _create_material(stage, f"{root_path}/Materials/Main", obj_spec["color"])

    cat = obj_spec["cat"]
    if cat == "mug":
        create_mug(stage, root_path, obj_spec["variant"], mat)
    elif cat == "bottle":
        cap_mat = _create_material(stage, f"{root_path}/Materials/Cap",
                                   obj_spec.get("cap_color", (0.5, 0.5, 0.5)), metallic=0.3)
        create_bottle(stage, root_path, obj_spec["variant"], mat, cap_mat)
    elif cat == "fruit":
        create_fruit(stage, root_path, obj_spec["shape"], obj_spec["dims"], mat)
    elif cat == "container":
        lid_mat = None
        if obj_spec.get("lid_color"):
            lid_mat = _create_material(stage, f"{root_path}/Materials/Lid",
                                       obj_spec["lid_color"])
        create_container(stage, root_path, obj_spec["variant"], mat, lid_mat)
    elif cat == "kitchen":
        create_kitchen_item(stage, root_path, obj_spec["kind"], mat)

    _apply_physics(root_prim, obj_spec["mass"])

    stage.GetRootLayer().Save()
    print(f"  Created: {out_path}  ({cat})")
    return out_path


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating {len(OBJECTS)} object assets in {OUT_DIR}...")
    paths = []
    for spec in OBJECTS:
        p = generate_object(spec)
        paths.append(p)
    print(f"\nDone. {len(paths)} USD assets created.")

    manifest = OUT_DIR / "manifest.txt"
    manifest.write_text("\n".join(p.name for p in paths) + "\n")
    print(f"Manifest written to {manifest}")


if __name__ == "__main__":
    main()
