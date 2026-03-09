"""Download YCB object assets from NVIDIA Nucleus to a local cache directory.

Must be run inside Isaac Sim (needs omni.client and Nucleus connectivity).

Usage (from Isaac Sim Python):
    python download_ycb_assets.py [--out-dir C:\\RoboLab_Data\\data\\object_sets_ycb]
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

try:
    from isaacsim import SimulationApp
    _headless = SimulationApp({"headless": True})
except Exception:
    _headless = None

try:
    import omni.client
    from omni.isaac.core.utils.nucleus import get_assets_root_path
except ImportError:
    try:
        from isaacsim.storage.native import get_assets_root_path
        import omni.client
    except ImportError:
        print("ERROR: Must run inside Isaac Sim environment.")
        sys.exit(1)


YCB_OBJECTS = [
    "002_master_chef_can",
    "003_cracker_box",
    "004_sugar_box",
    "005_tomato_soup_can",
    "006_mustard_bottle",
    "007_tuna_fish_can",
    "008_pudding_box",
    "009_gelatin_box",
    "010_potted_meat_can",
    "011_banana",
    "019_pitcher_base",
    "021_bleach_cleanser",
    "024_bowl",
    "025_mug",
    "035_power_drill",
    "036_wood_block",
    "040_large_marker",
    "052_extra_large_clamp",
    "061_foam_brick",
]


def download_file(nucleus_url: str, local_path: Path) -> bool:
    """Download a single file from Nucleus to local path."""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    result, _, content = omni.client.read_file(nucleus_url)
    if result != omni.client.Result.OK:
        return False
    local_path.write_bytes(memoryview(content))
    return True


def download_directory(nucleus_url: str, local_dir: Path) -> int:
    """Download a directory recursively from Nucleus."""
    count = 0
    result, entries = omni.client.list(nucleus_url)
    if result != omni.client.Result.OK:
        return 0
    for entry in entries:
        name = entry.relative_path
        full_url = f"{nucleus_url}/{name}"
        local_path = local_dir / name
        if entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
            count += download_directory(full_url, local_path)
        else:
            if download_file(full_url, local_path):
                count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Download YCB assets from Nucleus")
    parser.add_argument("--out-dir", type=str,
                        default=r"C:\RoboLab_Data\data\object_sets_ycb")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    assets_root = get_assets_root_path()
    if assets_root is None:
        print("ERROR: Cannot connect to Nucleus asset server.")
        print("Falling back to local USD generation...")
        _generate_local_ycb_replacements(out_dir)
        return

    print(f"Nucleus assets root: {assets_root}")
    ycb_base = f"{assets_root}/Isaac/Props/YCB/Axis_Aligned"

    downloaded = 0
    for obj_name in YCB_OBJECTS:
        usd_url = f"{ycb_base}/{obj_name}.usd"
        local_usd = out_dir / f"{obj_name}.usd"

        if local_usd.exists():
            print(f"  [skip] {obj_name} (already exists)")
            downloaded += 1
            continue

        if download_file(usd_url, local_usd):
            print(f"  [ok]   {obj_name}")
            downloaded += 1
            obj_dir_url = f"{ycb_base}/{obj_name}"
            obj_local_dir = out_dir / obj_name
            n_extra = download_directory(obj_dir_url, obj_local_dir)
            if n_extra:
                print(f"         + {n_extra} texture/material files")
        else:
            print(f"  [fail] {obj_name} — not found on Nucleus, generating local replacement")
            _generate_single_ycb_replacement(out_dir, obj_name)
            downloaded += 1

    manifest = out_dir / "manifest.txt"
    manifest.write_text("\n".join(f"{n}.usd" for n in YCB_OBJECTS) + "\n")
    print(f"\nDone: {downloaded}/{len(YCB_OBJECTS)} objects in {out_dir}")

    if _headless:
        _headless.close()


def _generate_local_ycb_replacements(out_dir: Path):
    """Generate local mesh-based replacements for YCB objects when Nucleus is unavailable."""
    from pxr import Usd, UsdGeom, UsdShade, UsdPhysics, Gf, Sdf

    _YCB_SPECS = {
        "002_master_chef_can": {"shape": "cylinder", "r": 0.05, "h": 0.14, "color": (0.15, 0.25, 0.55), "mass": 0.41},
        "003_cracker_box":     {"shape": "box", "dims": (0.16, 0.21, 0.07), "color": (0.85, 0.20, 0.15), "mass": 0.41},
        "004_sugar_box":       {"shape": "box", "dims": (0.09, 0.17, 0.04), "color": (0.95, 0.90, 0.30), "mass": 0.51},
        "005_tomato_soup_can": {"shape": "cylinder", "r": 0.033, "h": 0.10, "color": (0.80, 0.10, 0.10), "mass": 0.35},
        "006_mustard_bottle":  {"shape": "cylinder", "r": 0.03, "h": 0.18, "color": (0.90, 0.80, 0.10), "mass": 0.60},
        "007_tuna_fish_can":   {"shape": "cylinder", "r": 0.043, "h": 0.033, "color": (0.30, 0.50, 0.70), "mass": 0.17},
        "008_pudding_box":     {"shape": "box", "dims": (0.11, 0.09, 0.04), "color": (0.60, 0.30, 0.10), "mass": 0.19},
        "009_gelatin_box":     {"shape": "box", "dims": (0.09, 0.07, 0.03), "color": (0.90, 0.15, 0.25), "mass": 0.10},
        "010_potted_meat_can": {"shape": "cylinder", "r": 0.04, "h": 0.10, "color": (0.20, 0.35, 0.60), "mass": 0.37},
        "011_banana":          {"shape": "capsule", "r": 0.02, "h": 0.17, "color": (0.95, 0.88, 0.25), "mass": 0.07},
        "019_pitcher_base":    {"shape": "cylinder", "r": 0.08, "h": 0.20, "color": (0.85, 0.85, 0.80), "mass": 0.18},
        "021_bleach_cleanser": {"shape": "cylinder", "r": 0.04, "h": 0.25, "color": (0.95, 0.95, 0.90), "mass": 1.13},
        "024_bowl":            {"shape": "sphere", "r": 0.08, "color": (0.70, 0.35, 0.20), "mass": 0.15},
        "025_mug":             {"shape": "cylinder", "r": 0.04, "h": 0.12, "color": (0.80, 0.80, 0.75), "mass": 0.12},
        "035_power_drill":     {"shape": "box", "dims": (0.19, 0.18, 0.06), "color": (0.20, 0.20, 0.20), "mass": 0.90},
        "036_wood_block":      {"shape": "box", "dims": (0.09, 0.09, 0.09), "color": (0.70, 0.55, 0.30), "mass": 0.73},
        "040_large_marker":    {"shape": "cylinder", "r": 0.012, "h": 0.12, "color": (0.10, 0.10, 0.80), "mass": 0.02},
        "052_extra_large_clamp": {"shape": "box", "dims": (0.20, 0.09, 0.03), "color": (0.15, 0.15, 0.15), "mass": 0.20},
        "061_foam_brick":      {"shape": "box", "dims": (0.05, 0.05, 0.05), "color": (0.85, 0.40, 0.20), "mass": 0.03},
    }

    for name, spec in _YCB_SPECS.items():
        _generate_single_ycb_replacement(out_dir, name, spec=spec,
                                         Usd=Usd, UsdGeom=UsdGeom, UsdShade=UsdShade,
                                         UsdPhysics=UsdPhysics, Gf=Gf, Sdf=Sdf)

    manifest = out_dir / "manifest.txt"
    manifest.write_text("\n".join(f"{n}.usd" for n in YCB_OBJECTS) + "\n")
    print(f"Generated {len(_YCB_SPECS)} local YCB replacements in {out_dir}")


def _generate_single_ycb_replacement(out_dir: Path, name: str, spec=None,
                                      Usd=None, UsdGeom=None, UsdShade=None,
                                      UsdPhysics=None, Gf=None, Sdf=None):
    """Generate a single physics-enabled USD object as a YCB stand-in."""
    if Usd is None:
        from pxr import Usd, UsdGeom, UsdShade, UsdPhysics, Gf, Sdf

    _DEFAULT_SPECS = {
        "shape": "box", "dims": (0.08, 0.08, 0.08),
        "color": (0.5, 0.5, 0.5), "mass": 0.3,
    }
    if spec is None:
        spec = _DEFAULT_SPECS

    out_path = out_dir / f"{name}.usd"
    if out_path.exists():
        return

    stg = Usd.Stage.CreateNew(str(out_path))
    UsdGeom.SetStageUpAxis(stg, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stg, 1.0)

    root_path = f"/ycb_{name.replace('-', '_')}"
    root_xf = UsdGeom.Xform.Define(stg, root_path)
    root_prim = root_xf.GetPrim()
    stg.SetDefaultPrim(root_prim)

    mat = UsdShade.Material.Define(stg, f"{root_path}/Material")
    shader = UsdShade.Shader.Define(stg, f"{root_path}/Material/PBR")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*spec["color"]))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

    shape = spec["shape"]
    geo_path = f"{root_path}/Shape"
    if shape == "cylinder":
        geo = UsdGeom.Cylinder.Define(stg, geo_path)
        geo.CreateRadiusAttr(spec["r"])
        geo.CreateHeightAttr(spec["h"])
        geo.CreateAxisAttr("Z")
        UsdGeom.Xformable(geo.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0, spec["h"] / 2))
    elif shape == "box":
        geo = UsdGeom.Cube.Define(stg, geo_path)
        geo.CreateSizeAttr(1.0)
        d = spec["dims"]
        xf = UsdGeom.Xformable(geo.GetPrim())
        xf.AddTranslateOp().Set(Gf.Vec3d(0, 0, d[2] / 2))
        xf.AddScaleOp().Set(Gf.Vec3f(d[0], d[1], d[2]))
    elif shape == "sphere":
        geo = UsdGeom.Sphere.Define(stg, geo_path)
        geo.CreateRadiusAttr(spec["r"])
        UsdGeom.Xformable(geo.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0, spec["r"]))
    elif shape == "capsule":
        geo = UsdGeom.Capsule.Define(stg, geo_path)
        geo.CreateRadiusAttr(spec["r"])
        geo.CreateHeightAttr(spec["h"])
        geo.CreateAxisAttr("Y")
        UsdGeom.Xformable(geo.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0, spec["r"]))

    UsdShade.MaterialBindingAPI.Apply(stg.GetPrimAtPath(geo_path))
    UsdShade.MaterialBindingAPI(stg.GetPrimAtPath(geo_path)).Bind(mat)

    UsdPhysics.RigidBodyAPI.Apply(root_prim)
    UsdPhysics.CollisionAPI.Apply(root_prim)
    UsdPhysics.MassAPI.Apply(root_prim).CreateMassAttr(spec["mass"])

    stg.GetRootLayer().Save()
    print(f"  [gen]  {name} ({shape})")


if __name__ == "__main__":
    main()
