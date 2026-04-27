"""
scene_utils.py — Shared helpers for procedural USD scene builders (kitchen, office, etc.).

This module owns lazy pxr imports and provides geometry, material, physics, and
structural building blocks used by all *_fixed_builder.py scene files.

Usage from a scene builder:
    from scenes import scene_utils as su
    su.ensure_pxr()
    su.cube(stage, path, sx, sy, sz)
"""

from __future__ import annotations
import os, yaml, math
from pathlib import Path

# ---------------------------------------------------------------------------
# Lazy pxr imports  (must call ensure_pxr() after SimulationApp is created)
# ---------------------------------------------------------------------------

_pxr_loaded = False
Usd = UsdGeom = UsdLux = UsdShade = UsdPhysics = Sdf = Gf = Vt = None
PhysxSchema = None


def ensure_pxr():
    """Import pxr modules into this module's globals.  Idempotent."""
    global _pxr_loaded, Usd, UsdGeom, UsdLux, UsdShade, UsdPhysics, Sdf, Gf, Vt, PhysxSchema
    if _pxr_loaded:
        return
    from pxr import Usd as _Usd, UsdGeom as _UsdGeom, UsdLux as _UsdLux
    from pxr import UsdShade as _UsdShade, UsdPhysics as _UsdPhysics
    from pxr import Sdf as _Sdf, Gf as _Gf, Vt as _Vt
    Usd, UsdGeom, UsdLux, UsdShade = _Usd, _UsdGeom, _UsdLux, _UsdShade
    UsdPhysics, Sdf, Gf, Vt = _UsdPhysics, _Sdf, _Gf, _Vt
    try:
        from pxr import PhysxSchema as _PhysxSchema
        PhysxSchema = _PhysxSchema
    except ImportError:
        PhysxSchema = None
    _pxr_loaded = True


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Texture path resolution
# ---------------------------------------------------------------------------

def resolve_texture_path(path_value: str | None,
                         tex_dir: str | None = None,
                         caller_dir: str | None = None) -> str | None:
    """Resolve a texture path from absolute, workspace-relative, or scene-local paths.

    *caller_dir* should be ``str(Path(__file__).parent)`` of the importing
    builder so that scene-local textures are found correctly.
    """
    if not path_value:
        return None
    raw = str(path_value).strip()
    if not raw:
        return None

    candidates = []
    if os.path.isabs(raw):
        candidates.append(raw)
    else:
        if tex_dir:
            candidates.append(os.path.join(tex_dir, raw))
        if caller_dir:
            candidates.append(os.path.join(caller_dir, raw))
        candidates.append(os.path.abspath(raw))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Material helpers
# ---------------------------------------------------------------------------

def create_pbr_material(stage, name: str, mat_cfg: dict,
                        texture_paths: dict[str, str] | None = None,
                        looks_path: str = "/World/Looks") -> str:
    """Create a UsdPreviewSurface material with optional texture maps and opacity."""
    mat_path = f"{looks_path}/{name}"
    mat = UsdShade.Material.Define(stage, mat_path)
    shader_path = f"{mat_path}/Shader"
    shader = UsdShade.Shader.Define(stage, shader_path)
    shader.CreateIdAttr("UsdPreviewSurface")

    d = mat_cfg.get("diffuse", [0.5, 0.5, 0.5])
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*d))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(
        float(mat_cfg.get("roughness", 0.5)))
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(
        float(mat_cfg.get("metallic", 0.0)))

    # Opacity (e.g. glass)
    opacity = mat_cfg.get("opacity")
    if opacity is not None:
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(opacity))

    spec = mat_cfg.get("specular", 0.04)
    if isinstance(spec, (list, tuple)) and len(spec) == 3:
        spec_vec = Gf.Vec3f(float(spec[0]), float(spec[1]), float(spec[2]))
    else:
        spec_scalar = float(spec)
        spec_vec = Gf.Vec3f(spec_scalar, spec_scalar, spec_scalar)
    shader.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set(spec_vec)

    texture_paths = texture_paths or {}
    st_reader = None

    def _get_st_reader():
        nonlocal st_reader
        if st_reader is None:
            st_reader = UsdShade.Shader.Define(stage, f"{mat_path}/STReader")
            st_reader.CreateIdAttr("UsdPrimvarReader_float2")
            st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
            st_reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
        return st_reader

    def _make_uv_texture(tex_name: str, file_path: str):
        tex_shader = UsdShade.Shader.Define(stage, f"{mat_path}/{tex_name}")
        tex_shader.CreateIdAttr("UsdUVTexture")
        tex_shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(file_path)
        tex_shader.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
        tex_shader.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
        tex_shader.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
            _get_st_reader().ConnectableAPI(), "result")
        return tex_shader

    diffuse_tex = texture_paths.get("diffuse")
    if diffuse_tex and os.path.isfile(diffuse_tex):
        tex_shader = _make_uv_texture("DiffuseTexture", diffuse_tex)
        tex_shader.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            tex_shader.ConnectableAPI(), "rgb")

    roughness_tex = texture_paths.get("roughness")
    if roughness_tex and os.path.isfile(roughness_tex):
        tex_shader = _make_uv_texture("RoughnessTexture", roughness_tex)
        tex_shader.CreateOutput("r", Sdf.ValueTypeNames.Float)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).ConnectToSource(
            tex_shader.ConnectableAPI(), "r")

    normal_tex = texture_paths.get("normal")
    if normal_tex and os.path.isfile(normal_tex):
        tex_shader = _make_uv_texture("NormalTexture", normal_tex)
        tex_shader.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        shader.CreateInput("normal", Sdf.ValueTypeNames.Normal3f).ConnectToSource(
            tex_shader.ConnectableAPI(), "rgb")

    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

    mat_prim = stage.GetPrimAtPath(mat_path)
    if mat_cfg.get("friction_static") is not None:
        UsdPhysics.MaterialAPI.Apply(mat_prim)
        mat_prim.CreateAttribute("physics:staticFriction", Sdf.ValueTypeNames.Float).Set(
            float(mat_cfg["friction_static"]))
        mat_prim.CreateAttribute("physics:dynamicFriction", Sdf.ValueTypeNames.Float).Set(
            float(mat_cfg.get("friction_dynamic", 0.5)))
        mat_prim.CreateAttribute("physics:restitution", Sdf.ValueTypeNames.Float).Set(
            float(mat_cfg.get("restitution", 0.01)))

    return mat_path


def create_painting_material(stage, name: str, texture_path: str,
                             looks_path: str = "/World/Looks") -> str:
    """Create a diffuse material for a painting with UV texture reader."""
    mat_path = f"{looks_path}/{name}"
    mat = UsdShade.Material.Define(stage, mat_path)
    shader = UsdShade.Shader.Define(stage, f"{mat_path}/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.5, 0.5, 0.5))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.3)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    if os.path.isfile(texture_path):
        st_reader = UsdShade.Shader.Define(stage, f"{mat_path}/STReader")
        st_reader.CreateIdAttr("UsdPrimvarReader_float2")
        st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        st_reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
        tex = UsdShade.Shader.Define(stage, f"{mat_path}/Tex")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(texture_path)
        tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
        tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
        tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
            st_reader.ConnectableAPI(), "result")
        tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            tex.ConnectableAPI(), "rgb")
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat_path


# ---------------------------------------------------------------------------
# Material / collision / physics binding
# ---------------------------------------------------------------------------

def bind_material(stage, prim_path: str, mat_path: str):
    prim = stage.GetPrimAtPath(prim_path)
    mat = UsdShade.Material.Get(stage, mat_path)
    if prim and mat:
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat)


def add_collision(stage, prim_path: str):
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(prim_path))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(prim_path))


def make_kinematic(stage, prim_path: str):
    prim = stage.GetPrimAtPath(prim_path)
    UsdPhysics.RigidBodyAPI.Apply(prim)
    prim.CreateAttribute("physics:kinematicEnabled", Sdf.ValueTypeNames.Bool).Set(True)


def make_dynamic(stage, prim_path: str, mass_kg: float):
    prim = stage.GetPrimAtPath(prim_path)
    UsdPhysics.RigidBodyAPI.Apply(prim)
    UsdPhysics.MassAPI.Apply(prim)
    prim.CreateAttribute("physics:mass", Sdf.ValueTypeNames.Float).Set(mass_kg)


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------

def cube(stage, path: str, sx: float, sy: float, sz: float, color=None) -> str:
    c = UsdGeom.Cube.Define(stage, path)
    c.CreateSizeAttr(1.0)
    c.AddScaleOp().Set(Gf.Vec3f(sx, sy, sz))
    if color:
        c.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    return path


def cylinder(stage, path: str, radius: float, height: float, color=None) -> str:
    c = UsdGeom.Cylinder.Define(stage, path)
    c.CreateRadiusAttr(radius)
    c.CreateHeightAttr(height)
    if color:
        c.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    return path


def xform(stage, path: str, translate=None, rotate_xyz=None) -> str:
    xf = UsdGeom.Xform.Define(stage, path)
    api = UsdGeom.Xformable(xf.GetPrim())
    if translate:
        api.AddTranslateOp().Set(Gf.Vec3d(*translate))
    if rotate_xyz:
        api.AddRotateXYZOp().Set(Gf.Vec3f(*rotate_xyz))
    return path


# ---------------------------------------------------------------------------
# Physics scene
# ---------------------------------------------------------------------------

def build_physics_scene(stage, root_path: str, cfg: dict):
    scene_path = f"{root_path}/PhysicsScene"
    scene = UsdPhysics.Scene.Define(stage, scene_path)
    scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0, 0, -1))
    scene.CreateGravityMagnitudeAttr().Set(9.81)
    prim = stage.GetPrimAtPath(scene_path)
    if PhysxSchema:
        ps = PhysxSchema.PhysxSceneAPI.Apply(prim)
        ps.CreateEnableCCDAttr().Set(False)
        ps.CreateEnableStabilizationAttr().Set(True)
        ps.CreateTimeStepsPerSecondAttr().Set(120)
        ps.CreateSolverTypeAttr().Set("TGS")
        try:
            ps.CreateGpuFoundLostPairsCapacityAttr().Set(1024)
            ps.CreateGpuTotalAggregatePairsCapacityAttr().Set(1024)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Structural builders (parameterized)
# ---------------------------------------------------------------------------

def build_floor(stage, root_path: str, cfg: dict, mats: dict,
                floor_mat_key: str = "floor_tile", label: str = "scene"):
    room = cfg["room"]
    sx, sy = room["size_x"], room["size_y"]
    fh = room.get("floor_thickness", 0.02)
    xform(stage, f"{root_path}/Floor", translate=(0, 0, -fh / 2))
    fp = cube(stage, f"{root_path}/Floor/Slab", sx, sy, fh)
    add_collision(stage, fp)
    bind_material(stage, fp, mats.get(floor_mat_key, ""))
    print(f"[{label}] Floor: {sx}x{sy}m ({floor_mat_key})")


def build_walls(stage, root_path: str, cfg: dict, mats: dict, label: str = "scene"):
    room = cfg["room"]
    sx, sy = room["size_x"], room["size_y"]
    wh = room["wall_height"]
    wt = room["wall_thickness"]
    xform(stage, f"{root_path}/Walls")

    specs = {
        "NorthWall": {"pos": (0, sy / 2 - wt / 2, wh / 2), "size": (sx, wt, wh)},
        "SouthWall": {"pos": (0, -sy / 2 + wt / 2, wh / 2), "size": (sx, wt, wh)},
        "EastWall":  {"pos": (sx / 2 - wt / 2, 0, wh / 2), "size": (wt, sy - 2 * wt, wh)},
        "WestWall":  {"pos": (-sx / 2 + wt / 2, 0, wh / 2), "size": (wt, sy - 2 * wt, wh)},
    }
    for name, s in specs.items():
        wp = f"{root_path}/Walls/{name}"
        xform(stage, wp, translate=s["pos"])
        bp = cube(stage, f"{wp}/Body", *s["size"])
        add_collision(stage, bp)
        bind_material(stage, bp, mats.get("wall_paint", ""))
    print(f"[{label}] Walls: 4 walls, height={wh}m, thickness={wt}m")


def build_paintings(stage, root_path: str, cfg: dict, mats: dict,
                    wall_paintings: dict,
                    paint_w: float = 1.0, paint_h: float = 0.7,
                    frame_t: float = 0.04, frame_d: float = 0.02,
                    label: str = "scene"):
    """Build framed paintings on walls.

    *wall_paintings* is a dict like::

        {"South": {"pos": (x,y,z), "rot": (rx,ry,rz), "mat": "painting_south"}, ...}
    """
    UsdGeom.Xform.Define(stage, f"{root_path}/Paintings")

    for wname, spec in wall_paintings.items():
        base = f"{root_path}/Paintings/{wname}"
        xform(stage, base, translate=spec["pos"], rotate_xyz=spec["rot"])

        # Canvas as Mesh quad with UV
        cw = paint_w - 2 * frame_t
        ch = paint_h - 2 * frame_t
        canvas_path = f"{base}/Canvas"
        mesh = UsdGeom.Mesh.Define(stage, canvas_path)
        hw_c, hh_c = cw / 2, ch / 2
        mesh.CreatePointsAttr([
            Gf.Vec3f(-hw_c, -hh_c, 0), Gf.Vec3f(hw_c, -hh_c, 0),
            Gf.Vec3f(hw_c, hh_c, 0), Gf.Vec3f(-hw_c, hh_c, 0),
        ])
        mesh.CreateFaceVertexCountsAttr([4])
        mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
        mesh.CreateNormalsAttr([Gf.Vec3f(0, 0, 1)] * 4)
        mesh.SetNormalsInterpolation("vertex")
        st_primvar = UsdGeom.PrimvarsAPI(mesh.GetPrim()).CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray, "vertex")
        st_primvar.Set([Gf.Vec2f(0, 0), Gf.Vec2f(1, 0), Gf.Vec2f(1, 1), Gf.Vec2f(0, 1)])
        if spec["mat"] in mats:
            bind_material(stage, canvas_path, mats[spec["mat"]])

        # Frame (4 bars)
        hw, hh = paint_w / 2, paint_h / 2
        for fname, fpos, fsz in [
            ("Top", (0, hh - frame_t / 2, 0), (paint_w, frame_t, frame_d)),
            ("Bottom", (0, -hh + frame_t / 2, 0), (paint_w, frame_t, frame_d)),
            ("Left", (-hw + frame_t / 2, 0, 0), (frame_t, paint_h - 2 * frame_t, frame_d)),
            ("Right", (hw - frame_t / 2, 0, 0), (frame_t, paint_h - 2 * frame_t, frame_d)),
        ]:
            fp = f"{base}/Frame/{fname}"
            xform(stage, fp, translate=fpos)
            fbp = cube(stage, f"{fp}/Body", *fsz, color=[0.15, 0.10, 0.06])
            bind_material(stage, fbp, mats.get("frame_wood", ""))

    print(f"[{label}] Paintings: {len(wall_paintings)} framed paintings on walls")
