"""
office_fixed_builder.py — Build a fixed 10x8m open-space office scene for TIAGo manipulation.

Usage (standalone via Isaac Sim python):
    python.bat scenes/office_fixed/office_fixed_builder.py [--config CONFIG] [--output OUTPUT]

Usage (as module from test_robot_bench.py):
    from scenes.office_fixed.office_fixed_builder import build_office_scene
    build_office_scene(stage, config_path="scenes/office_fixed/office_fixed_config.yaml")
"""

from __future__ import annotations
import os, sys, math, argparse, yaml
from pathlib import Path

# Ensure project root is on sys.path for standalone execution
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from scenes import scene_utils as su

ROOT = "/World/Office"
LOOKS = f"{ROOT}/Looks"
FURN = f"{ROOT}/Furniture"
OBJ = f"{ROOT}/Objects"
ARCH = f"{ROOT}/Architecture"

_CALLER_DIR = str(Path(__file__).parent)

# ---------------------------------------------------------------------------
# Texture generation (office-specific)
# ---------------------------------------------------------------------------

def _generate_textures(tex_dir: str):
    """Generate procedural PNG textures for office materials."""
    os.makedirs(tex_dir, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        print("[office] WARNING: Pillow not installed — skipping texture generation")
        return {}

    import random
    textures = {}
    sz = 512
    hsz = 256

    # --- Carpet floor: blue-grey noise ---
    img = Image.new("RGB", (sz, sz), (105, 112, 125))
    rng = random.Random(100)
    for _ in range(8000):
        x, y = rng.randint(0, sz - 1), rng.randint(0, sz - 1)
        px = img.getpixel((x, y))
        d = rng.randint(-12, 12)
        img.putpixel((x, y), (max(0, min(255, px[0] + d)),
                               max(0, min(255, px[1] + d + rng.randint(-2, 2))),
                               max(0, min(255, px[2] + d + rng.randint(-1, 3)))))
    try:
        img = img.filter(ImageFilter.GaussianBlur(radius=0.6))
    except Exception:
        pass
    p = os.path.join(tex_dir, "floor_carpet.png")
    img.save(p)
    textures["floor_carpet"] = p

    # --- Wall paint: light grey with plaster noise ---
    img = Image.new("RGB", (sz, sz), (235, 235, 230))
    rng = random.Random(101)
    for _ in range(3000):
        x, y = rng.randint(0, sz - 1), rng.randint(0, sz - 1)
        v = rng.randint(226, 242)
        img.putpixel((x, y), (v, v, v - 2))
    try:
        img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    except Exception:
        pass
    p = os.path.join(tex_dir, "wall_paint.png")
    img.save(p)
    textures["wall_paint"] = p

    # --- Desk wood: light birch/oak with grain ---
    img = Image.new("RGB", (sz, sz), (185, 155, 115))
    draw = ImageDraw.Draw(img)
    rng = random.Random(102)
    for y in range(sz):
        wave = int(5 * math.sin(y * 0.035) + 3 * math.sin(y * 0.09))
        v = 170 + int(20 * math.sin(y * 0.07 + wave * 0.15))
        r, g, b = v, int(v * 0.82), int(v * 0.62)
        draw.line([(0, y), (sz, y)], fill=(r, g, b), width=1)
    for _ in range(500):
        x, y = rng.randint(0, sz - 1), rng.randint(0, sz - 1)
        v = rng.randint(155, 195)
        img.putpixel((x, y), (v, int(v * 0.81), int(v * 0.61)))
    for _ in range(2):
        kx, ky = rng.randint(50, sz - 50), rng.randint(50, sz - 50)
        kr = rng.randint(6, 12)
        draw.ellipse([kx - kr, ky - kr, kx + kr, ky + kr], fill=(145, 115, 78))
    p = os.path.join(tex_dir, "desk_wood.png")
    img.save(p)
    textures["desk_wood"] = p

    # --- Cabinet laminate: light grey smooth ---
    img = Image.new("RGB", (sz, sz), (224, 224, 220))
    rng = random.Random(103)
    for _ in range(1500):
        x, y = rng.randint(0, sz - 1), rng.randint(0, sz - 1)
        v = rng.randint(215, 232)
        img.putpixel((x, y), (v, v, v - 1))
    p = os.path.join(tex_dir, "cabinet_laminate.png")
    img.save(p)
    textures["cabinet_laminate"] = p
    textures["cabinet_door"] = p

    # --- Handle metal: chrome ---
    img = Image.new("RGB", (hsz, hsz), (140, 140, 148))
    draw = ImageDraw.Draw(img)
    rng = random.Random(104)
    for y in range(hsz):
        if rng.random() < 0.35:
            v = rng.randint(125, 160)
            draw.line([(0, y), (hsz, y)], fill=(v, v, v + 3), width=1)
    p = os.path.join(tex_dir, "handle_metal.png")
    img.save(p)
    textures["handle_metal"] = p

    # --- Chair fabric: dark grey woven ---
    img = Image.new("RGB", (hsz, hsz), (62, 62, 70))
    rng = random.Random(105)
    for y in range(hsz):
        for x in range(hsz):
            base = 62 + ((x + y) % 3) * 2
            img.putpixel((x, y), (base + rng.randint(-4, 4),
                                   base + rng.randint(-4, 4),
                                   base + 6 + rng.randint(-4, 4)))
    p = os.path.join(tex_dir, "chair_fabric.png")
    img.save(p)
    textures["chair_fabric"] = p

    # --- Whiteboard surface: nearly white with faint grid ---
    img = Image.new("RGB", (hsz, hsz), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    grid_color = (235, 235, 235)
    for x in range(0, hsz, 32):
        draw.line([(x, 0), (x, hsz)], fill=grid_color, width=1)
    for y in range(0, hsz, 32):
        draw.line([(0, y), (hsz, y)], fill=grid_color, width=1)
    p = os.path.join(tex_dir, "whiteboard_surface.png")
    img.save(p)
    textures["whiteboard_surface"] = p

    # --- Plastic black ---
    img = Image.new("RGB", (hsz, hsz), (20, 20, 25))
    rng = random.Random(106)
    for _ in range(300):
        x, y = rng.randint(0, hsz - 1), rng.randint(0, hsz - 1)
        v = rng.randint(15, 30)
        img.putpixel((x, y), (v, v, v + 2))
    p = os.path.join(tex_dir, "plastic_black.png")
    img.save(p)
    textures["plastic_black"] = p

    # --- Plastic dark ---
    img = Image.new("RGB", (hsz, hsz), (45, 50, 55))
    rng = random.Random(107)
    for _ in range(300):
        x, y = rng.randint(0, hsz - 1), rng.randint(0, hsz - 1)
        v = rng.randint(38, 60)
        img.putpixel((x, y), (v, v + 1, v + 3))
    p = os.path.join(tex_dir, "plastic_dark.png")
    img.save(p)
    textures["plastic_dark"] = p

    # --- Mug ceramic: white office mug ---
    img = Image.new("RGB", (hsz, hsz), (235, 235, 230))
    rng = random.Random(108)
    for y in range(hsz):
        for x in range(hsz):
            v = 230 + int(8 * math.sin(y * 0.12))
            img.putpixel((x, y), (max(0, min(255, v + rng.randint(-4, 4))),
                                   max(0, min(255, v + rng.randint(-4, 4))),
                                   max(0, min(255, v - 3 + rng.randint(-4, 4)))))
    p = os.path.join(tex_dir, "mug_ceramic.png")
    img.save(p)
    textures["mug_ceramic"] = p

    # --- Book cover: dark blue ---
    img = Image.new("RGB", (hsz, hsz), (25, 38, 115))
    draw = ImageDraw.Draw(img)
    rng = random.Random(109)
    for y in range(hsz):
        v = 105 + int(15 * math.sin(y * 0.06))
        draw.line([(0, y), (hsz, y)], fill=(22 + rng.randint(-3, 3),
                                              35 + rng.randint(-3, 3),
                                              v + rng.randint(-5, 5)), width=1)
    p = os.path.join(tex_dir, "book_cover.png")
    img.save(p)
    textures["book_cover"] = p

    # --- Shelf metal ---
    img = Image.new("RGB", (hsz, hsz), (178, 178, 190))
    rng = random.Random(110)
    for _ in range(400):
        x, y = rng.randint(0, hsz - 1), rng.randint(0, hsz - 1)
        v = rng.randint(165, 200)
        img.putpixel((x, y), (v, v, v + 4))
    p = os.path.join(tex_dir, "shelf_metal.png")
    img.save(p)
    textures["shelf_metal"] = p

    # --- Ceiling tile ---
    img = Image.new("RGB", (hsz, hsz), (240, 240, 235))
    rng = random.Random(111)
    for _ in range(500):
        x, y = rng.randint(0, hsz - 1), rng.randint(0, hsz - 1)
        v = rng.randint(232, 248)
        img.putpixel((x, y), (v, v, v - 2))
    p = os.path.join(tex_dir, "ceiling_tile.png")
    img.save(p)
    textures["ceiling_tile"] = p

    # --- Door wood: medium oak with grain ---
    img = Image.new("RGB", (sz, sz), (168, 130, 90))
    draw = ImageDraw.Draw(img)
    rng = random.Random(112)
    for y in range(sz):
        wave = int(4 * math.sin(y * 0.04))
        v = 155 + int(18 * math.sin(y * 0.06 + wave * 0.1))
        draw.line([(0, y), (sz, y)], fill=(v, int(v * 0.77), int(v * 0.53)), width=1)
    for _ in range(300):
        x, y = rng.randint(0, sz - 1), rng.randint(0, sz - 1)
        v = rng.randint(140, 180)
        img.putpixel((x, y), (v, int(v * 0.76), int(v * 0.52)))
    p = os.path.join(tex_dir, "door_wood.png")
    img.save(p)
    textures["door_wood"] = p

    # --- Chair mat: translucent dark plastic ---
    img = Image.new("RGB", (hsz, hsz), (88, 95, 100))
    rng = random.Random(113)
    for _ in range(600):
        x, y = rng.randint(0, hsz - 1), rng.randint(0, hsz - 1)
        v = rng.randint(78, 108)
        img.putpixel((x, y), (v, v + 2, v + 4))
    p = os.path.join(tex_dir, "chair_mat_plastic.png")
    img.save(p)
    textures["chair_mat_plastic"] = p

    # --- Wall paint normal map: subtle plaster bumps ---
    img = Image.new("RGB", (sz, sz), (128, 128, 255))  # neutral normal
    rng = random.Random(114)
    for _ in range(6000):
        x, y = rng.randint(0, sz - 1), rng.randint(0, sz - 1)
        nx = 128 + rng.randint(-8, 8)
        ny = 128 + rng.randint(-8, 8)
        img.putpixel((x, y), (nx, ny, 255))
    try:
        img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
    except Exception:
        pass
    p = os.path.join(tex_dir, "wall_paint_normal.png")
    img.save(p)
    textures["wall_paint_normal"] = p

    # --- Carpet normal map: fibrous bumps ---
    img = Image.new("RGB", (sz, sz), (128, 128, 255))
    rng = random.Random(115)
    for _ in range(10000):
        x, y = rng.randint(0, sz - 1), rng.randint(0, sz - 1)
        nx = 128 + rng.randint(-15, 15)
        ny = 128 + rng.randint(-15, 15)
        img.putpixel((x, y), (nx, ny, 250))
    try:
        img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    except Exception:
        pass
    p = os.path.join(tex_dir, "floor_carpet_normal.png")
    img.save(p)
    textures["floor_carpet_normal"] = p

    # --- 3 Paintings: abstract office art ---
    painting_names = ["painting_south", "painting_east", "painting_west"]
    circle_palettes = [
        [(40, 80, 160), (200, 200, 210), (120, 150, 180), (60, 120, 200), (180, 190, 200)],
        [(50, 140, 120), (200, 210, 180), (80, 170, 150), (160, 200, 170), (40, 100, 90)],
        [(180, 100, 50), (240, 200, 140), (200, 140, 80), (160, 80, 40), (220, 180, 120)],
    ]
    bg_colors = [(240, 242, 245), (238, 245, 242), (245, 242, 238)]
    for idx, (pname, pal) in enumerate(zip(painting_names, circle_palettes)):
        psz = 256
        img = Image.new("RGB", (psz, psz), bg_colors[idx])
        draw = ImageDraw.Draw(img)
        rng = random.Random(120 + idx)
        for _ in range(rng.randint(8, 14)):
            c = pal[rng.randint(0, len(pal) - 1)]
            cx_c = rng.randint(20, psz - 20)
            cy_c = rng.randint(20, psz - 20)
            r = rng.randint(15, 55)
            draw.ellipse([cx_c - r, cy_c - r, cx_c + r, cy_c + r], fill=c)
        p = os.path.join(tex_dir, f"{pname}.png")
        img.save(p)
        textures[pname] = p

    print(f"[office] Generated {len(textures)} textures in {tex_dir}")
    return textures


# ---------------------------------------------------------------------------
# Materials (office-specific)
# ---------------------------------------------------------------------------

def _build_materials(stage, cfg: dict, tex_dir: str = None) -> dict[str, str]:
    """Create all UsdPreviewSurface materials with textures, return name->path map."""
    su.UsdGeom.Xform.Define(stage, LOOKS)

    if tex_dir is None:
        tex_dir = str(Path(__file__).parent / "textures")
    textures = _generate_textures(tex_dir)

    mats = {}
    for name, mat_cfg in cfg.get("materials", {}).items():
        texture_paths = {"diffuse": textures.get(name)}

        # Auto-discover normal maps from generated textures
        normal_key = f"{name}_normal"
        if normal_key in textures:
            texture_paths["normal"] = textures[normal_key]

        cfg_roughness = mat_cfg.get("roughness_texture") or mat_cfg.get("texture_roughness")
        cfg_normal = mat_cfg.get("normal_texture") or mat_cfg.get("texture_normal")
        auto_roughness = su.resolve_texture_path(f"{name}_roughness.png", tex_dir=tex_dir, caller_dir=_CALLER_DIR)
        auto_normal = su.resolve_texture_path(f"{name}_normal.png", tex_dir=tex_dir, caller_dir=_CALLER_DIR)

        roughness_path = su.resolve_texture_path(cfg_roughness, tex_dir=tex_dir, caller_dir=_CALLER_DIR) or auto_roughness
        normal_path = su.resolve_texture_path(cfg_normal, tex_dir=tex_dir, caller_dir=_CALLER_DIR) or auto_normal
        if roughness_path:
            texture_paths["roughness"] = roughness_path
        if normal_path:
            texture_paths["normal"] = normal_path

        mats[name] = su.create_pbr_material(stage, name, mat_cfg, texture_paths=texture_paths, looks_path=LOOKS)

    # Painting materials
    for pname in ["painting_south", "painting_east", "painting_west"]:
        tp = textures.get(pname)
        if tp:
            mats[pname] = su.create_painting_material(stage, pname, tp, looks_path=LOOKS)

    # Frame material (dark wood)
    frame_cfg = {"diffuse": [0.15, 0.10, 0.06], "roughness": 0.6, "metallic": 0.0}
    mats["frame_wood"] = su.create_pbr_material(stage, "frame_wood", frame_cfg, looks_path=LOOKS)

    # Whiteboard frame (aluminium)
    wb_frame_cfg = {"diffuse": [0.75, 0.75, 0.78], "roughness": 0.2, "metallic": 0.8}
    mats["whiteboard_frame"] = su.create_pbr_material(stage, "whiteboard_frame", wb_frame_cfg, looks_path=LOOKS)

    return mats


# ---------------------------------------------------------------------------
# Paintings (office-specific wall selection)
# ---------------------------------------------------------------------------

def _build_paintings(stage, cfg: dict, mats: dict):
    """Framed paintings on south and west walls (east has windows, north has whiteboard)."""
    room = cfg["room"]
    sx, sy = room["size_x"], room["size_y"]
    wt = room["wall_thickness"]
    wh = room["wall_height"]
    paint_z = wh * 0.55

    wall_paintings = {
        "South": {
            "pos": (1.5, -sy / 2 + wt + 0.005, paint_z),
            "rot": (90, 0, 0),
            "mat": "painting_south",
        },
        "West": {
            "pos": (-sx / 2 + wt + 0.005, 0, paint_z),
            "rot": (90, 0, 90),
            "mat": "painting_west",
        },
    }
    su.build_paintings(stage, ROOT, cfg, mats, wall_paintings,
                       paint_w=0.90, paint_h=0.65, frame_t=0.035, frame_d=0.02,
                       label="office")


# ---------------------------------------------------------------------------
# Architectural elements
# ---------------------------------------------------------------------------

def _build_door(stage, cfg: dict, mats: dict):
    """Build an interior door on the south wall with RevoluteJoint."""
    room = cfg["room"]
    sy = room["size_y"]
    wt = room["wall_thickness"]
    dc = cfg["door"]
    dw, dh, dt = dc["width"], dc["height"], dc["thickness"]
    cx = dc["center_x"]
    half_w = dw / 2

    base = f"{ARCH}/Door"
    wall_y = -sy / 2 + wt / 2
    su.xform(stage, base, translate=(cx, wall_y, 0))

    # Frame (3 pieces: left jamb, right jamb, header)
    fw = dc["frame_width"]
    fd = dc["frame_depth"]
    frame_mat = mats.get(dc.get("frame_material", "door_frame"), "")
    frame_color = cfg["materials"].get(dc.get("frame_material", "door_frame"), {}).get("diffuse", [0.88, 0.88, 0.85])

    su.xform(stage, f"{base}/Frame")
    for fname, fpos, fsz in [
        ("Left", (-half_w - fw / 2, 0, dh / 2), (fw, fd, dh)),
        ("Right", (half_w + fw / 2, 0, dh / 2), (fw, fd, dh)),
        ("Header", (0, 0, dh + fw / 2), (dw + 2 * fw, fd, fw)),
    ]:
        fp = f"{base}/Frame/{fname}"
        su.xform(stage, fp, translate=fpos)
        fbp = su.cube(stage, f"{fp}/Body", *fsz, color=frame_color)
        su.add_collision(stage, fbp)
        su.bind_material(stage, fbp, frame_mat)

    # Door panel (dynamic, hinged)
    door_mat = mats.get(dc.get("material", "door_wood"), "")
    door_color = cfg["materials"].get(dc.get("material", "door_wood"), {}).get("diffuse", [0.65, 0.50, 0.35])

    su.xform(stage, f"{base}/Panel", translate=(0, 0, dh / 2))
    dp = su.cube(stage, f"{base}/Panel/Body", dw, dt, dh, color=door_color)
    su.add_collision(stage, dp)
    su.bind_material(stage, dp, door_mat)
    su.make_dynamic(stage, f"{base}/Panel", dc["mass_kg"])

    # Door handle (lever type on both sides)
    hc = dc["handle"]
    h_z = hc["center_height"] - dh / 2
    h_standoff = hc["standoff"]
    h_len, h_w, h_d = hc["length"], hc["width"], hc["depth"]
    h_mat = mats.get(hc.get("material", dc.get("handle_material", "handle_metal")), "")
    h_color = cfg["materials"].get("handle_metal", {}).get("diffuse", [0.55, 0.55, 0.58])

    for side_name, y_sign in [("HandleFront", -1), ("HandleBack", 1)]:
        hy = y_sign * (dt / 2 + h_standoff + h_d / 2)
        su.xform(stage, f"{base}/Panel/{side_name}", translate=(half_w - 0.08, hy, h_z))
        # Lever arm
        lp = su.cube(stage, f"{base}/Panel/{side_name}/Lever", h_len, h_d, h_w, color=h_color)
        su.add_collision(stage, lp)
        su.bind_material(stage, lp, h_mat)
        # Return to door
        su.xform(stage, f"{base}/Panel/{side_name}/Stem",
               translate=(-h_len / 2 + h_w / 2, y_sign * (h_d / 2 + h_standoff / 2), 0))
        sp = su.cube(stage, f"{base}/Panel/{side_name}/Stem/Body",
                   h_w, h_standoff, h_w, color=h_color)
        su.bind_material(stage, sp, h_mat)

    # Revolute joint: hinge on left jamb edge
    hinge = f"{base}/DoorHinge"
    rev = su.UsdPhysics.RevoluteJoint.Define(stage, hinge)
    rev.GetBody0Rel().SetTargets([su.Sdf.Path(f"{base}/Frame")])
    rev.GetBody1Rel().SetTargets([su.Sdf.Path(f"{base}/Panel")])
    rev.CreateAxisAttr("Z")
    rev.CreateLowerLimitAttr(0.0)
    rev.CreateUpperLimitAttr(dc["open_deg"])
    rev.CreateLocalPos0Attr().Set(su.Gf.Vec3f(-half_w, 0.0, dh / 2))
    rev.CreateLocalPos1Attr().Set(su.Gf.Vec3f(-half_w, 0.0, 0.0))
    su.make_kinematic(stage, f"{base}/Frame")

    hinge_prim = stage.GetPrimAtPath(hinge)
    drive = su.UsdPhysics.DriveAPI.Apply(hinge_prim, "angular")
    drive.CreateDampingAttr().Set(8.0)
    drive.CreateStiffnessAttr().Set(0.0)

    print(f"[office] Door at south wall X={cx}: {dw}x{dh}m, RevoluteJoint 0-{dc['open_deg']}deg")


def _build_windows(stage, cfg: dict, mats: dict):
    """Build windows on the east wall with glass pane, frame, and sill."""
    room = cfg["room"]
    sx = room["size_x"]
    wt = room["wall_thickness"]
    windows = cfg.get("windows", [])
    if not windows:
        return

    su.UsdGeom.Xform.Define(stage, f"{ARCH}/Windows")

    for i, wc in enumerate(windows):
        ww, wh = wc["width"], wc["height"]
        sill_h = wc["sill_height"]
        fw = wc["frame_width"]
        fd = wc["frame_depth"]
        gt = wc["glass_thickness"]
        center_y = wc["center_y"]
        glass_z = sill_h + wh / 2

        wall_x = sx / 2 - wt
        base = f"{ARCH}/Windows/Window{i}"
        su.xform(stage, base, translate=(wall_x, center_y, glass_z))

        # Glass pane (semi-transparent)
        glass_mat = mats.get(wc.get("material", "window_glass"), "")
        glass_color = cfg["materials"].get("window_glass", {}).get("diffuse", [0.85, 0.90, 0.95])
        gp = su.cube(stage, f"{base}/Glass", gt, ww - 2 * fw, wh - 2 * fw, color=glass_color)
        su.add_collision(stage, gp)
        su.bind_material(stage, gp, glass_mat)

        # Frame (4 bars)
        frame_mat = mats.get(wc.get("frame_material", "window_frame"), "")
        frame_color = cfg["materials"].get("window_frame", {}).get("diffuse", [0.90, 0.90, 0.88])
        hw, hh = ww / 2, wh / 2
        for fname, fpos, fsz in [
            ("Top", (0, 0, hh - fw / 2), (fd, ww, fw)),
            ("Bottom", (0, 0, -hh + fw / 2), (fd, ww, fw)),
            ("Left", (0, -hw + fw / 2, 0), (fd, fw, wh - 2 * fw)),
            ("Right", (0, hw - fw / 2, 0), (fd, fw, wh - 2 * fw)),
        ]:
            fp = f"{base}/Frame/{fname}"
            su.xform(stage, fp, translate=fpos)
            fbp = su.cube(stage, f"{fp}/Body", *fsz, color=frame_color)
            su.add_collision(stage, fbp)
            su.bind_material(stage, fbp, frame_mat)

        # Cross bar (horizontal mullion at center)
        su.xform(stage, f"{base}/Frame/Mullion", translate=(0, 0, 0))
        mbp = su.cube(stage, f"{base}/Frame/Mullion/Body", fd, ww - 2 * fw, fw, color=frame_color)
        su.bind_material(stage, mbp, frame_mat)

        # Window sill
        sill_mat = mats.get(wc.get("sill_material", "window_sill"), "")
        sill_color = cfg["materials"].get("window_sill", {}).get("diffuse", [0.92, 0.92, 0.90])
        sill_depth = 0.12
        sill_z = -hh - 0.01
        su.xform(stage, f"{base}/Sill", translate=(-sill_depth / 2, 0, sill_z))
        sp = su.cube(stage, f"{base}/Sill/Body", sill_depth, ww + 0.04, 0.025, color=sill_color)
        su.add_collision(stage, sp)
        su.bind_material(stage, sp, sill_mat)

    print(f"[office] Windows: {len(windows)} on east wall")


def _build_baseboard(stage, cfg: dict, mats: dict):
    """Build baseboard (skirting) around the room perimeter."""
    room = cfg["room"]
    sx, sy = room["size_x"], room["size_y"]
    wt = room["wall_thickness"]
    bc = cfg.get("baseboard", {})
    bh = bc.get("height", 0.08)
    bt = bc.get("thickness", 0.012)
    mat_name = bc.get("material", "baseboard_white")
    b_mat = mats.get(mat_name, "")
    b_color = cfg["materials"].get(mat_name, {}).get("diffuse", [0.95, 0.95, 0.93])

    base = f"{ARCH}/Baseboard"
    su.xform(stage, base)

    inner_sx = sx - 2 * wt
    inner_sy = sy - 2 * wt

    segments = [
        ("North", (0, sy / 2 - wt - bt / 2, bh / 2), (inner_sx, bt, bh)),
        ("South", (0, -sy / 2 + wt + bt / 2, bh / 2), (inner_sx, bt, bh)),
        ("East", (sx / 2 - wt - bt / 2, 0, bh / 2), (bt, inner_sy - 2 * bt, bh)),
        ("West", (-sx / 2 + wt + bt / 2, 0, bh / 2), (bt, inner_sy - 2 * bt, bh)),
    ]
    for sname, spos, ssz in segments:
        sp = f"{base}/{sname}"
        su.xform(stage, sp, translate=spos)
        sbp = su.cube(stage, f"{sp}/Body", *ssz, color=b_color)
        su.bind_material(stage, sbp, b_mat)

    print(f"[office] Baseboard: {bh*100:.0f}cm height around perimeter")


def _build_ceiling_grid(stage, cfg: dict, mats: dict):
    """Build a suspended ceiling grid (T-bar system)."""
    room = cfg["room"]
    sx, sy = room["size_x"], room["size_y"]
    wt = room["wall_thickness"]
    wh = room["wall_height"]
    gc = cfg.get("ceiling_grid", {})
    tile_sz = gc.get("tile_size", 0.60)
    rw = gc.get("rail_width", 0.02)
    rd = gc.get("rail_depth", 0.025)
    drop = gc.get("drop", 0.05)
    tile_mat = mats.get(gc.get("material", "ceiling_tile"), "")
    rail_mat = mats.get(gc.get("rail_material", "ceiling_rail"), "")
    tile_color = cfg["materials"].get("ceiling_tile", {}).get("diffuse", [0.94, 0.94, 0.92])
    rail_color = cfg["materials"].get("ceiling_rail", {}).get("diffuse", [0.85, 0.85, 0.82])

    grid_z = wh - drop
    inner_sx = sx - 2 * wt
    inner_sy = sy - 2 * wt
    base = f"{ARCH}/CeilingGrid"
    su.xform(stage, base)

    # Ceiling slab
    tile_h = 0.008
    su.xform(stage, f"{base}/Tiles", translate=(0, 0, grid_z + tile_h / 2))
    tp = su.cube(stage, f"{base}/Tiles/Slab", inner_sx, inner_sy, tile_h, color=tile_color)
    su.bind_material(stage, tp, tile_mat)

    # X-direction rails
    rail_idx = 0
    y_start = -inner_sy / 2 + tile_sz
    y = y_start
    while y < inner_sy / 2 - 0.01:
        rp = f"{base}/RailX{rail_idx}"
        su.xform(stage, rp, translate=(0, y, grid_z - rd / 2))
        rbp = su.cube(stage, f"{rp}/Body", inner_sx, rw, rd, color=rail_color)
        su.bind_material(stage, rbp, rail_mat)
        rail_idx += 1
        y += tile_sz

    # Y-direction rails
    rail_idx = 0
    x_start = -inner_sx / 2 + tile_sz
    x = x_start
    while x < inner_sx / 2 - 0.01:
        rp = f"{base}/RailY{rail_idx}"
        su.xform(stage, rp, translate=(x, 0, grid_z - rd / 2))
        rbp = su.cube(stage, f"{rp}/Body", rw, inner_sy, rd, color=rail_color)
        su.bind_material(stage, rbp, rail_mat)
        rail_idx += 1
        x += tile_sz

    print(f"[office] Ceiling grid: {tile_sz}m tiles at z={grid_z:.2f}m")


def _build_outlets(stage, cfg: dict, mats: dict):
    """Build electrical outlets/switches on walls."""
    room = cfg["room"]
    sx, sy = room["size_x"], room["size_y"]
    wt = room["wall_thickness"]
    outlets = cfg.get("outlets", [])
    os_cfg = cfg.get("outlet_size", {})
    ow = os_cfg.get("width", 0.07)
    oh = os_cfg.get("height", 0.11)
    od = os_cfg.get("depth", 0.005)
    mat_name = os_cfg.get("material", "plastic_white")
    o_mat = mats.get(mat_name, "")
    o_color = cfg["materials"].get(mat_name, {}).get("diffuse", [0.92, 0.92, 0.90])

    base = f"{ARCH}/Outlets"
    su.xform(stage, base)

    wall_positions = {
        "north": lambda cx, cz: (cx, sy / 2 - wt - od / 2, cz),
        "south": lambda cx, cz: (cx, -sy / 2 + wt + od / 2, cz),
        "east": lambda cy, cz: (sx / 2 - wt - od / 2, cy, cz),
        "west": lambda cy, cz: (-sx / 2 + wt + od / 2, cy, cz),
    }
    wall_sizes = {
        "north": (ow, od, oh),
        "south": (ow, od, oh),
        "east": (od, ow, oh),
        "west": (od, ow, oh),
    }

    for i, oc in enumerate(outlets):
        wall = oc["wall"]
        cz = oc["center_z"]
        if wall in ("north", "south"):
            cx = oc.get("center_x", 0)
            pos = wall_positions[wall](cx, cz)
        else:
            cy = oc.get("center_y", 0)
            pos = wall_positions[wall](cy, cz)
        sz = wall_sizes[wall]
        op = f"{base}/Outlet{i}"
        su.xform(stage, op, translate=pos)
        obp = su.cube(stage, f"{op}/Body", *sz, color=o_color)
        su.bind_material(stage, obp, o_mat)

    print(f"[office] Outlets: {len(outlets)} wall outlets")


def _build_cable_trunking(stage, cfg: dict, mats: dict):
    """Build cable trunking (cable channels) along the floor."""
    ct = cfg.get("cable_trunking", {})
    cw = ct.get("width", 0.04)
    ch = ct.get("height", 0.025)
    segments = ct.get("segments", [])
    mat_name = ct.get("material", "cable_trunking")
    c_mat = mats.get(mat_name, "")
    c_color = cfg["materials"].get(mat_name, {}).get("diffuse", [0.85, 0.85, 0.82])

    base = f"{ARCH}/CableTrunking"
    su.xform(stage, base)

    for i, seg in enumerate(segments):
        x0, y0 = seg["from"]
        x1, y1 = seg["to"]
        z = seg.get("z", 0.02)
        dx, dy = x1 - x0, y1 - y0
        length = math.sqrt(dx * dx + dy * dy)
        mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
        angle = math.degrees(math.atan2(dx, dy))

        sp = f"{base}/Segment{i}"
        su.xform(stage, sp, translate=(mid_x, mid_y, z + ch / 2), rotate_xyz=(0, 0, angle))
        sbp = su.cube(stage, f"{sp}/Body", cw, length, ch, color=c_color)
        su.add_collision(stage, sbp)
        su.bind_material(stage, sbp, c_mat)

    print(f"[office] Cable trunking: {len(segments)} segments")


def _build_chair_mat(stage, cfg: dict, mats: dict):
    """Build a transparent floor mat under the chair."""
    cm = cfg.get("chair_mat", {})
    if not cm:
        return
    radius = cm.get("radius", 0.55)
    thickness = cm.get("thickness", 0.005)
    cx = cm.get("center_x", 0)
    cy = cm.get("center_y", 0.5)
    mat_name = cm.get("material", "chair_mat_plastic")
    c_mat = mats.get(mat_name, "")
    c_color = cfg["materials"].get(mat_name, {}).get("diffuse", [0.35, 0.38, 0.40])

    base = f"{ARCH}/ChairMat"
    su.xform(stage, base, translate=(cx, cy, thickness / 2))
    mp = su.cylinder(stage, f"{base}/Body", radius, thickness, color=c_color)
    su.add_collision(stage, mp)
    su.bind_material(stage, mp, c_mat)
    print(f"[office] Chair mat: r={radius}m at ({cx}, {cy})")


# ---------------------------------------------------------------------------
# Furniture builders
# ---------------------------------------------------------------------------

def _build_desk(stage, cfg: dict, mats: dict, desk_key: str, desk_cfg: dict):
    w, d, h = desk_cfg["width"], desk_cfg["depth"], desk_cfg["height"]
    cx, cy = desk_cfg["center_x"], desk_cfg["center_y"]
    top_h = desk_cfg["top_thickness"]
    leg_w = desk_cfg["leg_width"]
    mat_name = desk_cfg.get("material", "desk_wood")
    base = f"{FURN}/{desk_key}"
    su.xform(stage, base, translate=(cx, cy, 0))
    top_z = h - top_h / 2
    su.xform(stage, f"{base}/Top", translate=(0, 0, top_z))
    tp = su.cube(stage, f"{base}/Top/Slab", d, w, top_h,
               color=cfg["materials"][mat_name]["diffuse"])
    su.add_collision(stage, tp)
    su.bind_material(stage, tp, mats.get(mat_name, ""))
    leg_h = h - top_h
    su.UsdGeom.Xform.Define(stage, f"{base}/Legs")
    offsets = [
        (-d / 2 + leg_w, -w / 2 + leg_w), (d / 2 - leg_w, -w / 2 + leg_w),
        (-d / 2 + leg_w, w / 2 - leg_w), (d / 2 - leg_w, w / 2 - leg_w),
    ]
    leg_color = [c * 0.8 for c in cfg["materials"][mat_name]["diffuse"]]
    for i, (lx, ly) in enumerate(offsets):
        lp = f"{base}/Legs/Leg{i}"
        su.xform(stage, lp, translate=(lx, ly, leg_h / 2))
        lbp = su.cube(stage, f"{lp}/Body", leg_w, leg_w, leg_h, color=leg_color)
        su.add_collision(stage, lbp)
        su.bind_material(stage, lbp, mats.get(mat_name, ""))
    print(f"[office] Desk '{desk_key}' at ({cx}, {cy}): {w}x{d}x{h}m")


def _build_desks(stage, cfg: dict, mats: dict):
    furn = cfg["furniture"]
    for key in ["desk_main", "desk_side", "desk_back"]:
        if key in furn:
            _build_desk(stage, cfg, mats, key, furn[key])


def _build_chair(stage, cfg: dict, mats: dict):
    cc = cfg["furniture"]["chair"]
    sw, sd = cc["seat_w"], cc["seat_d"]
    sh = cc["seat_h"]
    seat_t = cc["seat_thickness"]
    back_h = cc["back_h"]
    back_t = cc["back_thickness"]
    leg_w = cc["leg_width"]
    cx, cy = cc["center_x"], cc["center_y"]
    mat_name = cc.get("material", "chair_fabric")
    base = f"{FURN}/Chair"
    su.xform(stage, base, translate=(cx, cy, 0))
    seat_z = sh - seat_t / 2
    su.xform(stage, f"{base}/Seat", translate=(0, 0, seat_z))
    sp = su.cube(stage, f"{base}/Seat/Slab", sd, sw, seat_t,
               color=cfg["materials"][mat_name]["diffuse"])
    su.add_collision(stage, sp)
    su.bind_material(stage, sp, mats.get(mat_name, ""))
    back_z = sh + back_h / 2
    su.xform(stage, f"{base}/Back", translate=(0, -(sd / 2 - back_t / 2), back_z))
    bp = su.cube(stage, f"{base}/Back/Panel", back_t, sw, back_h,
               color=cfg["materials"][mat_name]["diffuse"])
    su.add_collision(stage, bp)
    su.bind_material(stage, bp, mats.get(mat_name, ""))
    leg_h = sh - seat_t
    su.UsdGeom.Xform.Define(stage, f"{base}/Legs")
    offsets = [
        (-sd / 2 + leg_w, -sw / 2 + leg_w), (sd / 2 - leg_w, -sw / 2 + leg_w),
        (-sd / 2 + leg_w, sw / 2 - leg_w), (sd / 2 - leg_w, sw / 2 - leg_w),
    ]
    for i, (lx, ly) in enumerate(offsets):
        lp = f"{base}/Legs/Leg{i}"
        su.xform(stage, lp, translate=(lx, ly, leg_h / 2))
        su.cube(stage, f"{lp}/Body", leg_w, leg_w, leg_h, color=[0.12, 0.12, 0.14])
        su.add_collision(stage, f"{lp}/Body")
    su.make_kinematic(stage, base)
    print(f"[office] Chair at ({cx}, {cy}): seat at z={sh}m")


def _build_cabinet(stage, cfg: dict, mats: dict):
    fc = cfg["furniture"]["cabinet"]
    w, d, h = fc["width"], fc["depth"], fc["height"]
    cx, cy = fc["center_x"], fc["center_y"]
    door_d = fc["door_thickness"]
    half_w, half_d, half_h = w / 2, d / 2, h / 2
    wall_t = 0.02
    base = f"{FURN}/Cabinet"
    su.xform(stage, base, translate=(cx, cy, 0))
    su.xform(stage, f"{base}/Body", translate=(0, 0, half_h))
    cab_color = cfg["materials"][fc["material"]]["diffuse"]
    cab_mat = mats.get(fc["material"], "")
    for pname, ppos, psz in [
        ("Back", (0, half_d - wall_t / 2, 0), (w, wall_t, h)),
        ("Left", (-half_w + wall_t / 2, 0, 0), (wall_t, d, h)),
        ("Right", (half_w - wall_t / 2, 0, 0), (wall_t, d, h)),
        ("Top", (0, 0, half_h - wall_t / 2), (w, d, wall_t)),
        ("Bottom", (0, 0, -half_h + wall_t / 2), (w, d, wall_t)),
    ]:
        pp = f"{base}/Body/{pname}"
        su.xform(stage, pp, translate=ppos)
        p = su.cube(stage, f"{pp}/Panel", *psz, color=cab_color)
        su.add_collision(stage, p); su.bind_material(stage, p, cab_mat)
    su.make_kinematic(stage, f"{base}/Body")
    n_shelves = fc.get("shelf_count", 3)
    for i in range(n_shelves):
        z_frac = (i + 1) / (n_shelves + 1)
        sp = f"{base}/Body/Shelf{i}"
        su.xform(stage, sp, translate=(0, 0, h * z_frac - half_h))
        sbp = su.cube(stage, f"{sp}/Plane", w - 0.08, d - 0.08, 0.015,
                     color=cfg["materials"]["shelf_metal"]["diffuse"])
        su.add_collision(stage, sbp)
        su.bind_material(stage, sbp, mats.get("shelf_metal", ""))
    # Door
    su.xform(stage, f"{base}/Door", translate=(0, -half_d + door_d / 2, half_h))
    door_color = cfg["materials"][fc["door_material"]]["diffuse"]
    dp = su.cube(stage, f"{base}/Door/Panel", w, door_d, h, color=door_color)
    su.add_collision(stage, dp)
    su.bind_material(stage, dp, mats.get(fc["door_material"], ""))
    su.make_dynamic(stage, f"{base}/Door", fc["door_mass_kg"])
    # Handle
    hc = fc["handle"]
    h_z = hc["center_height"] - half_h
    standoff = hc["standoff"]
    bar_len, bar_w, bar_d = hc["length"], hc["width"], hc["depth"]
    h_y = -(door_d / 2 + standoff + bar_d / 2)
    h_x = half_w - 0.10
    h_color = cfg["materials"][fc["handle_material"]]["diffuse"]
    su.xform(stage, f"{base}/Door/Handle", translate=(h_x, h_y, h_z))
    bar_path = su.cube(stage, f"{base}/Door/Handle/Bar", bar_w, bar_d, bar_len, color=h_color)
    su.add_collision(stage, bar_path)
    su.bind_material(stage, bar_path, mats.get(fc["handle_material"], ""))
    for bi, bz in enumerate([bar_len / 2 - 0.04, -bar_len / 2 + 0.04]):
        bp_path = f"{base}/Door/Handle/Bracket{bi}"
        su.xform(stage, bp_path, translate=(0, bar_d / 2 + standoff / 2, bz))
        bbp = su.cube(stage, f"{bp_path}/Body", bar_w, standoff, 0.025, color=h_color)
        su.add_collision(stage, bbp)
        su.bind_material(stage, bbp, mats.get(fc["handle_material"], ""))
    # Hinge
    hinge = f"{base}/DoorHinge"
    rev = su.UsdPhysics.RevoluteJoint.Define(stage, hinge)
    rev.GetBody0Rel().SetTargets([su.Sdf.Path(f"{base}/Body")])
    rev.GetBody1Rel().SetTargets([su.Sdf.Path(f"{base}/Door")])
    rev.CreateAxisAttr("Z")
    rev.CreateLowerLimitAttr(-fc["door_open_deg"])
    rev.CreateUpperLimitAttr(0.0)
    rev.CreateLocalPos0Attr().Set(su.Gf.Vec3f(-half_w, -half_d, 0.0))
    rev.CreateLocalPos1Attr().Set(su.Gf.Vec3f(-half_w, -door_d / 2, 0.0))
    drive = su.UsdPhysics.DriveAPI.Apply(stage.GetPrimAtPath(hinge), "angular")
    drive.CreateDampingAttr().Set(5.0)
    drive.CreateStiffnessAttr().Set(0.0)
    print(f"[office] Cabinet at ({cx}, {cy}): {w}x{d}x{h}m with door")


def _build_whiteboard(stage, cfg: dict, mats: dict):
    room = cfg["room"]
    sy = room["size_y"]
    wt = room["wall_thickness"]
    wb = cfg["furniture"]["whiteboard"]
    wb_w, wb_h, wb_t = wb["width"], wb["height"], wb["thickness"]
    wb_cx = wb["center_x"]
    wb_z = wb["mount_height"]
    wall_inner_y = sy / 2 - wt
    wb_y = wall_inner_y - wb_t / 2 - 0.005
    base = f"{FURN}/Whiteboard"
    su.xform(stage, base, translate=(wb_cx, wb_y, wb_z))
    board_path = su.cube(stage, f"{base}/Board", wb_w, wb_t, wb_h,
                       color=cfg["materials"]["whiteboard_surface"]["diffuse"])
    su.add_collision(stage, board_path)
    su.bind_material(stage, board_path, mats.get("whiteboard_surface", ""))
    frame_t = 0.025
    frame_d = wb_t + 0.01
    hw, hh = wb_w / 2, wb_h / 2
    for fname, fpos, fsz in [
        ("Top", (0, 0, hh + frame_t / 2), (wb_w + 2 * frame_t, frame_d, frame_t)),
        ("Bottom", (0, 0, -hh - frame_t / 2), (wb_w + 2 * frame_t, frame_d, frame_t)),
        ("Left", (-hw - frame_t / 2, 0, 0), (frame_t, frame_d, wb_h)),
        ("Right", (hw + frame_t / 2, 0, 0), (frame_t, frame_d, wb_h)),
    ]:
        fp = f"{base}/Frame/{fname}"
        su.xform(stage, fp, translate=fpos)
        fbp = su.cube(stage, f"{fp}/Body", *fsz, color=[0.75, 0.75, 0.78])
        su.bind_material(stage, fbp, mats.get("whiteboard_frame", ""))
    tray_w = wb_w * 0.6
    su.xform(stage, f"{base}/Tray", translate=(0, -wb_t / 2 - 0.03, -hh - frame_t - 0.015))
    tray_path = su.cube(stage, f"{base}/Tray/Body", tray_w, 0.06, 0.03, color=[0.75, 0.75, 0.78])
    su.add_collision(stage, tray_path)
    su.bind_material(stage, tray_path, mats.get("whiteboard_frame", ""))
    print(f"[office] Whiteboard at ({wb_cx}, {wb_y:.2f}): {wb_w}x{wb_h}m")


def _build_printer_stand(stage, cfg: dict, mats: dict):
    ps = cfg["furniture"]["printer_stand"]
    w, d, h = ps["width"], ps["depth"], ps["height"]
    cx, cy = ps["center_x"], ps["center_y"]
    top_h = ps["top_thickness"]
    leg_w = ps["leg_width"]
    mat_name = ps.get("material", "cabinet_laminate")
    base = f"{FURN}/PrinterStand"
    su.xform(stage, base, translate=(cx, cy, 0))
    top_z = h - top_h / 2
    su.xform(stage, f"{base}/Top", translate=(0, 0, top_z))
    tp = su.cube(stage, f"{base}/Top/Slab", d, w, top_h,
               color=cfg["materials"][mat_name]["diffuse"])
    su.add_collision(stage, tp)
    su.bind_material(stage, tp, mats.get(mat_name, ""))
    leg_h = h - top_h
    su.UsdGeom.Xform.Define(stage, f"{base}/Legs")
    offsets = [
        (-d / 2 + leg_w, -w / 2 + leg_w), (d / 2 - leg_w, -w / 2 + leg_w),
        (-d / 2 + leg_w, w / 2 - leg_w), (d / 2 - leg_w, w / 2 - leg_w),
    ]
    leg_color = [c * 0.85 for c in cfg["materials"][mat_name]["diffuse"]]
    for i, (lx, ly) in enumerate(offsets):
        lp = f"{base}/Legs/Leg{i}"
        su.xform(stage, lp, translate=(lx, ly, leg_h / 2))
        lbp = su.cube(stage, f"{lp}/Body", leg_w, leg_w, leg_h, color=leg_color)
        su.add_collision(stage, lbp)
        su.bind_material(stage, lbp, mats.get(mat_name, ""))
    print(f"[office] Printer stand at ({cx}, {cy}): {w}x{d}x{h}m")


def _build_objects(stage, cfg: dict, mats: dict):
    furn = cfg["furniture"]
    objs = cfg["objects"]
    desk_tops = {}
    for key in ["desk_main", "desk_side", "desk_back"]:
        if key in furn:
            dc = furn[key]
            desk_tops[key] = {"cx": dc["center_x"], "cy": dc["center_y"], "top_z": dc["height"]}
    su.UsdGeom.Xform.Define(stage, OBJ)
    for obj_name, oc in objs.items():
        desk_key = oc.get("on", "desk_main")
        dt = desk_tops.get(desk_key)
        if not dt:
            continue
        base_x = dt["cx"] + oc.get("offset_x", 0.0)
        base_y = dt["cy"] + oc.get("offset_y", 0.0)
        top_z = dt["top_z"]
        mat_name = oc.get("material", "plastic_black")
        obj_type = oc.get("type", "box")
        obj_path = f"{OBJ}/{obj_name.capitalize()}"
        if obj_type == "cylinder":
            radius, height = oc["radius"], oc["height"]
            su.xform(stage, obj_path, translate=(base_x, base_y, top_z + height / 2))
            bp = su.cylinder(stage, f"{obj_path}/Body", radius, height,
                           color=cfg["materials"][mat_name]["diffuse"])
            su.add_collision(stage, bp)
            su.bind_material(stage, bp, mats.get(mat_name, ""))
        else:
            _sx, _sy, _sz = oc["sx"], oc["sy"], oc["sz"]
            su.xform(stage, obj_path, translate=(base_x, base_y, top_z + _sz / 2))
            bp = su.cube(stage, f"{obj_path}/Body", _sx, _sy, _sz,
                       color=cfg["materials"][mat_name]["diffuse"])
            su.add_collision(stage, bp)
            su.bind_material(stage, bp, mats.get(mat_name, ""))
        su.make_dynamic(stage, obj_path, oc["mass_kg"])
        print(f"[office] Object '{obj_name}' on {desk_key} at ({base_x:.2f}, {base_y:.2f})")


def _build_lights(stage, cfg: dict, mats: dict):
    lc = cfg.get("lights", {})
    su.xform(stage, f"{ROOT}/Lights")

    dc = lc.get("dome", {})
    dome = su.UsdLux.DomeLight.Define(stage, f"{ROOT}/Lights/DomeLight")
    dome.CreateIntensityAttr(dc.get("intensity", 400.0))
    dome.CreateColorAttr(su.Gf.Vec3f(*dc.get("color", [1.0, 0.98, 0.95])))
    dome_texture = su.resolve_texture_path(dc.get("texture"), tex_dir=str(Path(__file__).parent / "textures"), caller_dir=_CALLER_DIR)
    if dome_texture:
        try:
            dome.CreateTextureFileAttr().Set(su.Sdf.AssetPath(dome_texture))
        except Exception:
            pass

    cc = lc.get("ceiling", {})
    positions = cc.get("positions", [])
    ceiling_color = cc.get("color", [1.0, 0.98, 0.94])
    for i, pos in enumerate(positions):
        lp = f"{ROOT}/Lights/CeilingLight{i}"
        light = su.UsdLux.RectLight.Define(stage, lp)
        light.CreateIntensityAttr(cc.get("intensity", 2500.0))
        light.CreateWidthAttr(cc.get("width", 0.8))
        light.CreateHeightAttr(cc.get("height", 0.4))
        light.CreateColorAttr(su.Gf.Vec3f(*ceiling_color))
        xf = su.UsdGeom.Xformable(light.GetPrim())
        xf.AddTranslateOp().Set(su.Gf.Vec3d(pos[0], pos[1], cc.get("z", 2.75)))
        xf.AddRotateXYZOp().Set(su.Gf.Vec3f(180, 0, 0))

    # Window lights — warm sunlight from outside the east windows
    wl = lc.get("window_lights", {})
    windows = cfg.get("windows", [])
    if wl and windows:
        room = cfg["room"]
        sx = room["size_x"]
        for i, wc in enumerate(windows):
            wlp = f"{ROOT}/Lights/WindowLight{i}"
            wlight = su.UsdLux.RectLight.Define(stage, wlp)
            wlight.CreateIntensityAttr(wl.get("intensity", 4000.0))
            wlight.CreateWidthAttr(wl.get("width", 1.2))
            wlight.CreateHeightAttr(wl.get("height", 1.0))
            wlight.CreateColorAttr(su.Gf.Vec3f(*wl.get("color", [1.0, 0.96, 0.88])))
            xf = su.UsdGeom.Xformable(wlight.GetPrim())
            win_z = wc["sill_height"] + wc["height"] / 2
            xf.AddTranslateOp().Set(su.Gf.Vec3d(sx / 2 + 0.5, wc["center_y"], win_z))
            xf.AddRotateXYZOp().Set(su.Gf.Vec3f(0, 0, -90))

    print(f"[office] Lights: dome + {len(positions)} ceiling + {len(windows)} window lights")


def _build_cameras(stage, cfg: dict):
    cams = cfg.get("cameras", {})
    su.xform(stage, f"{ROOT}/Cameras")
    for name, cc in cams.items():
        cp = f"{ROOT}/Cameras/{name}"
        cam = su.UsdGeom.Camera.Define(stage, cp)
        xf = su.UsdGeom.Xformable(cam.GetPrim())
        pos = cc["position"]
        tgt = cc["target"]
        xf.AddTranslateOp().Set(su.Gf.Vec3d(*pos))
        dx, dy, dz = tgt[0] - pos[0], tgt[1] - pos[1], tgt[2] - pos[2]
        dist_xy = math.sqrt(dx * dx + dy * dy)
        pitch = -math.degrees(math.atan2(dz, dist_xy))
        yaw = math.degrees(math.atan2(dx, dy))
        xf.AddRotateXYZOp().Set(su.Gf.Vec3f(pitch, 0, yaw))
    print(f"[office] Cameras: {list(cams.keys())}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_office_scene(stage, config_path: str | None = None, cfg: dict | None = None):
    su.ensure_pxr()

    if cfg is None:
        if config_path is None:
            config_path = str(Path(__file__).parent / "office_fixed_config.yaml")
        cfg = su.load_config(config_path)

    su.UsdGeom.Xform.Define(stage, ROOT)
    su.UsdGeom.SetStageUpAxis(stage, su.UsdGeom.Tokens.z)
    su.UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    print("[office] Building fixed office scene...")
    su.build_physics_scene(stage, ROOT, cfg)
    mats = _build_materials(stage, cfg)
    su.build_floor(stage, ROOT, cfg, mats, floor_mat_key="floor_carpet", label="office")
    su.build_walls(stage, ROOT, cfg, mats, label="office")

    # Architecture
    su.UsdGeom.Xform.Define(stage, ARCH)
    _build_door(stage, cfg, mats)
    _build_windows(stage, cfg, mats)
    _build_baseboard(stage, cfg, mats)
    _build_ceiling_grid(stage, cfg, mats)
    _build_outlets(stage, cfg, mats)
    _build_cable_trunking(stage, cfg, mats)
    _build_chair_mat(stage, cfg, mats)

    # Furniture
    _build_paintings(stage, cfg, mats)
    _build_whiteboard(stage, cfg, mats)
    _build_desks(stage, cfg, mats)
    _build_chair(stage, cfg, mats)
    _build_cabinet(stage, cfg, mats)
    _build_printer_stand(stage, cfg, mats)

    # Objects
    _build_objects(stage, cfg, mats)

    # Lighting & cameras
    _build_lights(stage, cfg, mats)
    _build_cameras(stage, cfg)
    print("[office] Scene build complete.")

    return cfg


def main():
    parser = argparse.ArgumentParser(description="Build fixed office USD scene")
    parser.add_argument("--config", type=str,
                        default=str(Path(__file__).parent / "office_fixed_config.yaml"))
    parser.add_argument("--output", type=str,
                        default=str(Path(__file__).parent / "office_fixed.usd"))
    parser.add_argument("--usda", action="store_true",
                        help="Save as .usda (ASCII) instead of binary .usd")
    args = parser.parse_args()

    import sys as _sys
    _log = lambda msg: _sys.stderr.write(msg + "\n")

    _log("[office] Starting SimulationApp for USD generation...")
    from isaacsim import SimulationApp
    sim_app = SimulationApp({"headless": True})

    su.ensure_pxr()

    out_path = os.path.abspath(args.output)
    if args.usda and out_path.endswith(".usd"):
        out_path = out_path + "a"
    if os.path.exists(out_path):
        os.remove(out_path)

    _log(f"[office] Creating stage: {out_path}")
    stage = su.Usd.Stage.CreateNew(out_path)
    try:
        build_office_scene(stage, config_path=args.config)
        stage.GetRootLayer().Save()
        _log(f"[office] Saved: {out_path}")

        prim_count = sum(1 for _ in stage.Traverse())
        _log(f"[office] Total prims: {prim_count}")
    except Exception as e:
        _log(f"[office] ERROR: {e}")
        import traceback
        traceback.print_exc(file=_sys.stderr)
        sim_app.close()
        _sys.exit(1)

    sim_app.close()


if __name__ == "__main__":
    main()
