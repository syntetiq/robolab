"""
kitchen_fixed_builder.py — Build a fixed 8x8m kitchen scene for TIAGo manipulation.

Usage (standalone via Isaac Sim python):
    python.bat scenes/kitchen_fixed/kitchen_fixed_builder.py [--config CONFIG] [--output OUTPUT]

Usage (as module from test_robot_bench.py):
    from scenes.kitchen_fixed.kitchen_fixed_builder import build_kitchen_scene
    build_kitchen_scene(stage, config_path="scenes/kitchen_fixed/kitchen_fixed_config.yaml")
"""

from __future__ import annotations
import os, sys, math, argparse, yaml
from pathlib import Path

# Ensure project root is on sys.path for standalone execution
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from scenes import scene_utils as su

ROOT = "/World/Kitchen"
LOOKS = f"{ROOT}/Looks"
FURN = f"{ROOT}/Furniture"
OBJ = f"{ROOT}/Objects"

_CALLER_DIR = str(Path(__file__).parent)

# ---------------------------------------------------------------------------
# Texture generation (kitchen-specific)
# ---------------------------------------------------------------------------

def _generate_textures(tex_dir: str):
    """Generate procedural PNG textures for kitchen materials."""
    os.makedirs(tex_dir, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        print("[kitchen] WARNING: Pillow not installed — skipping texture generation")
        return {}

    import random
    textures = {}
    sz = 512

    # --- Parquet floor: herringbone pattern ---
    img = Image.new("RGB", (sz, sz), (180, 140, 95))
    draw = ImageDraw.Draw(img)
    rng = random.Random(42)
    plank_w, plank_h = 24, 80
    colors = [(175, 135, 90), (185, 145, 100), (165, 125, 82), (190, 150, 105),
              (170, 130, 88), (180, 142, 96), (160, 120, 78)]
    for row in range(0, sz + plank_h, plank_h):
        for col in range(0, sz + plank_w * 2, plank_w * 2):
            c = colors[rng.randint(0, len(colors) - 1)]
            x0, y0 = col, row
            draw.rectangle([x0, y0, x0 + plank_w - 1, y0 + plank_h - 1], fill=c)
            draw.line([(x0, y0), (x0 + plank_w - 1, y0)], fill=(c[0] - 15, c[1] - 15, c[2] - 10), width=1)
            c2 = colors[rng.randint(0, len(colors) - 1)]
            x1 = col + plank_w
            draw.rectangle([x1, y0, x1 + plank_w - 1, y0 + plank_h - 1], fill=c2)
            draw.line([(x1, y0), (x1 + plank_w - 1, y0)], fill=(c2[0] - 15, c2[1] - 15, c2[2] - 10), width=1)
    for _ in range(2000):
        x, y = rng.randint(0, sz - 1), rng.randint(0, sz - 1)
        px = img.getpixel((x, y))
        d = rng.randint(-8, 8)
        img.putpixel((x, y), (max(0, min(255, px[0] + d)), max(0, min(255, px[1] + d)), max(0, min(255, px[2] + d))))
    p = os.path.join(tex_dir, "floor_tile.png")
    img.save(p)
    textures["floor_tile"] = p

    # --- Wall paint: warm off-white with subtle plaster texture ---
    img = Image.new("RGB", (sz, sz), (245, 240, 232))
    rng = random.Random(43)
    for _ in range(3000):
        x, y = rng.randint(0, sz - 1), rng.randint(0, sz - 1)
        v = rng.randint(232, 252)
        img.putpixel((x, y), (v, v - 2, v - 6))
    try:
        img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    except Exception:
        pass
    p = os.path.join(tex_dir, "wall_paint.png")
    img.save(p)
    textures["wall_paint"] = p

    # --- Appliance metal: brushed stainless steel ---
    img = Image.new("RGB", (sz, sz), (205, 207, 212))
    draw = ImageDraw.Draw(img)
    rng = random.Random(44)
    for y in range(sz):
        if rng.random() < 0.4:
            v = rng.randint(190, 220)
            draw.line([(0, y), (sz, y)], fill=(v, v + 1, v + 3), width=1)
    for _ in range(1500):
        x, y = rng.randint(0, sz - 1), rng.randint(0, sz - 1)
        v = rng.randint(195, 225)
        img.putpixel((x, y), (v, v, v + 2))
    p = os.path.join(tex_dir, "appliance_metal.png")
    img.save(p)
    textures["appliance_metal"] = p
    textures["appliance_door"] = p

    # --- Handle metal: dark brushed chrome ---
    hsz = 256
    img = Image.new("RGB", (hsz, hsz), (85, 85, 92))
    draw = ImageDraw.Draw(img)
    rng = random.Random(45)
    for y in range(hsz):
        if rng.random() < 0.3:
            v = rng.randint(70, 105)
            draw.line([(0, y), (hsz, y)], fill=(v, v, v + 3), width=1)
    p = os.path.join(tex_dir, "handle_metal.png")
    img.save(p)
    textures["handle_metal"] = p

    # --- Table wood: warm oak grain ---
    img = Image.new("RGB", (sz, sz), (162, 118, 78))
    draw = ImageDraw.Draw(img)
    rng = random.Random(46)
    for y in range(sz):
        wave = int(6 * math.sin(y * 0.04) + 3 * math.sin(y * 0.11))
        v = 145 + int(22 * math.sin(y * 0.09 + wave * 0.2))
        r, g, b = v, int(v * 0.73), int(v * 0.49)
        draw.line([(0, y), (sz, y)], fill=(r, g, b), width=1)
    for _ in range(600):
        x, y = rng.randint(0, sz - 1), rng.randint(0, sz - 1)
        v = rng.randint(130, 175)
        img.putpixel((x, y), (v, int(v * 0.72), int(v * 0.47)))
    # knots
    for _ in range(3):
        kx, ky = rng.randint(50, sz - 50), rng.randint(50, sz - 50)
        kr = rng.randint(8, 15)
        draw.ellipse([kx - kr, ky - kr, kx + kr, ky + kr], fill=(120, 82, 50))
    p = os.path.join(tex_dir, "table_wood.png")
    img.save(p)
    textures["table_wood"] = p

    # --- Cabinet wood: darker walnut ---
    img = Image.new("RGB", (sz, sz), (135, 98, 68))
    draw = ImageDraw.Draw(img)
    rng = random.Random(47)
    for y in range(sz):
        v = 115 + int(28 * math.sin(y * 0.07))
        draw.line([(0, y), (sz, y)], fill=(v, int(v * 0.71), int(v * 0.49)), width=1)
    for _ in range(400):
        x, y = rng.randint(0, sz - 1), rng.randint(0, sz - 1)
        v = rng.randint(105, 145)
        img.putpixel((x, y), (v, int(v * 0.70), int(v * 0.48)))
    p = os.path.join(tex_dir, "cabinet_wood.png")
    img.save(p)
    textures["cabinet_wood"] = p

    # --- Sink metal: polished steel ---
    img = Image.new("RGB", (hsz, hsz), (195, 195, 202))
    rng = random.Random(48)
    for _ in range(800):
        x, y = rng.randint(0, hsz - 1), rng.randint(0, hsz - 1)
        v = rng.randint(185, 215)
        img.putpixel((x, y), (v, v, v + 4))
    p = os.path.join(tex_dir, "sink_metal.png")
    img.save(p)
    textures["sink_metal"] = p

    # --- Ceramic white: plate with subtle glaze ---
    img = Image.new("RGB", (hsz, hsz), (245, 244, 240))
    rng = random.Random(49)
    for _ in range(400):
        x, y = rng.randint(0, hsz - 1), rng.randint(0, hsz - 1)
        v = rng.randint(238, 252)
        img.putpixel((x, y), (v, v, v - 2))
    p = os.path.join(tex_dir, "ceramic_white.png")
    img.save(p)
    textures["ceramic_white"] = p

    # --- Apple: realistic red with green/yellow gradient and spots ---
    img = Image.new("RGB", (hsz, hsz), (195, 30, 25))
    draw = ImageDraw.Draw(img)
    rng = random.Random(50)
    cx, cy = hsz // 2, hsz // 2
    for y in range(hsz):
        for x in range(hsz):
            dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2) / (hsz / 2)
            if dist > 1.0:
                continue
            angle = math.atan2(y - cy, x - cx)
            r = int(195 - 40 * dist + 15 * math.sin(angle * 3))
            g = int(25 + 35 * max(0, math.cos(angle + 1.0)) * (1 - dist))
            b = int(20 + 10 * dist)
            r = max(0, min(255, r + rng.randint(-5, 5)))
            g = max(0, min(255, g + rng.randint(-3, 3)))
            b = max(0, min(255, b))
            img.putpixel((x, y), (r, g, b))
    for _ in range(30):
        sx, sy = rng.randint(cx - 80, cx + 80), rng.randint(cy - 80, cy + 80)
        sr = rng.randint(2, 5)
        sc = (rng.randint(150, 180), rng.randint(120, 150), rng.randint(50, 80))
        draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=sc)
    p = os.path.join(tex_dir, "apple_red.png")
    img.save(p)
    textures["apple_red"] = p

    # --- Banana: yellow with brown spots, green tips ---
    img = Image.new("RGB", (hsz, hsz), (230, 205, 45))
    draw = ImageDraw.Draw(img)
    rng = random.Random(51)
    for y in range(hsz):
        for x in range(hsz):
            base_r = 230 + int(10 * math.sin(x * 0.05))
            base_g = 200 + int(15 * math.sin(y * 0.08))
            base_b = 40 + int(10 * math.sin((x + y) * 0.03))
            # green at edges
            if x < hsz * 0.15 or x > hsz * 0.85:
                base_g = int(base_g * 0.7 + 60)
                base_r = int(base_r * 0.6)
            img.putpixel((x, y), (max(0, min(255, base_r + rng.randint(-4, 4))),
                                   max(0, min(255, base_g + rng.randint(-4, 4))),
                                   max(0, min(255, base_b + rng.randint(-3, 3)))))
    # brown spots
    for _ in range(40):
        sx, sy = rng.randint(30, hsz - 30), rng.randint(30, hsz - 30)
        sr = rng.randint(2, 6)
        draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr],
                     fill=(rng.randint(100, 140), rng.randint(70, 100), rng.randint(20, 40)))
    p = os.path.join(tex_dir, "banana_yellow.png")
    img.save(p)
    textures["banana_yellow"] = p

    # --- Mug ceramic: glazed dark red ---
    img = Image.new("RGB", (hsz, hsz), (200, 48, 35))
    rng = random.Random(52)
    for y in range(hsz):
        for x in range(hsz):
            v = 200 + int(12 * math.sin(y * 0.1))
            img.putpixel((x, y), (max(0, min(255, v + rng.randint(-6, 6))),
                                   max(0, min(255, 48 + rng.randint(-5, 5))),
                                   max(0, min(255, 35 + rng.randint(-4, 4)))))
    p = os.path.join(tex_dir, "mug_ceramic.png")
    img.save(p)
    textures["mug_ceramic"] = p

    # --- Shelf metal ---
    img = Image.new("RGB", (hsz, hsz), (178, 178, 190))
    rng = random.Random(53)
    for _ in range(400):
        x, y = rng.randint(0, hsz - 1), rng.randint(0, hsz - 1)
        v = rng.randint(165, 200)
        img.putpixel((x, y), (v, v, v + 4))
    p = os.path.join(tex_dir, "shelf_metal.png")
    img.save(p)
    textures["shelf_metal"] = p

    # --- 4 Paintings: bright colorful circles on light background ---
    painting_names = ["painting_north", "painting_south", "painting_east", "painting_west"]
    circle_palettes = [
        [(220, 40, 40), (40, 120, 220), (250, 200, 30), (60, 190, 80), (200, 60, 180)],
        [(255, 100, 0), (0, 180, 220), (180, 30, 120), (100, 220, 50), (255, 220, 60)],
        [(80, 50, 200), (220, 60, 60), (50, 200, 150), (240, 180, 40), (200, 100, 220)],
        [(30, 160, 200), (230, 70, 50), (60, 200, 80), (240, 160, 200), (250, 210, 50)],
    ]
    bg_colors = [(245, 240, 230), (235, 245, 240), (240, 235, 245), (245, 245, 235)]
    for idx, (pname, pal) in enumerate(zip(painting_names, circle_palettes)):
        psz = 256
        img = Image.new("RGB", (psz, psz), bg_colors[idx])
        draw = ImageDraw.Draw(img)
        rng = random.Random(60 + idx)
        for _ in range(rng.randint(10, 18)):
            c = pal[rng.randint(0, len(pal) - 1)]
            cx_c = rng.randint(20, psz - 20)
            cy_c = rng.randint(20, psz - 20)
            r = rng.randint(15, 55)
            draw.ellipse([cx_c - r, cy_c - r, cx_c + r, cy_c + r], fill=c)
        p = os.path.join(tex_dir, f"{pname}.png")
        img.save(p)
        textures[pname] = p

    print(f"[kitchen] Generated {len(textures)} textures in {tex_dir}")
    return textures


# ---------------------------------------------------------------------------
# Materials (kitchen-specific)
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
    for pname in ["painting_north", "painting_south", "painting_east", "painting_west"]:
        tp = textures.get(pname)
        if tp:
            mats[pname] = su.create_painting_material(stage, pname, tp, looks_path=LOOKS)

    # Frame material (dark wood)
    frame_cfg = {"diffuse": [0.15, 0.10, 0.06], "roughness": 0.6, "metallic": 0.0}
    mats["frame_wood"] = su.create_pbr_material(stage, "frame_wood", frame_cfg, looks_path=LOOKS)

    return mats


# ---------------------------------------------------------------------------
# Kitchen-specific furniture builders
# ---------------------------------------------------------------------------

def _build_paintings(stage, cfg: dict, mats: dict):
    """Add a framed painting on each wall."""
    room = cfg["room"]
    sx, sy = room["size_x"], room["size_y"]
    wt = room["wall_thickness"]
    wh = room["wall_height"]
    paint_z = wh * 0.55

    wall_paintings = {
        "South": {
            "pos": (0, -sy / 2 + wt + 0.005, paint_z),
            "rot": (90, 0, 0),
            "mat": "painting_south",
        },
        "East": {
            "pos": (sx / 2 - wt - 0.005, 0, paint_z),
            "rot": (90, 0, -90),
            "mat": "painting_east",
        },
        "West": {
            "pos": (-sx / 2 + wt + 0.005, 0, paint_z),
            "rot": (90, 0, 90),
            "mat": "painting_west",
        },
        "North": {
            "pos": (0, sy / 2 - wt - 0.005, paint_z),
            "rot": (90, 0, 180),
            "mat": "painting_north",
        },
    }
    su.build_paintings(stage, ROOT, cfg, mats, wall_paintings,
                       paint_w=1.0, paint_h=0.7, frame_t=0.04, frame_d=0.02,
                       label="kitchen")


def _build_fridge(stage, cfg: dict, mats: dict):
    """Build fridge against north wall, front faces south (-Y after -90deg Z rotation).
    Cabinet is an open-front box (back + 2 sides + top + bottom) so the door and handle are visible."""
    fc = cfg["furniture"]["fridge"]
    w, d, h = fc["width"], fc["depth"], fc["height"]
    cx, cy = fc["center_x"], fc["center_y"]
    door_d = fc["door_thickness"]
    half_w, half_d, half_h = w / 2, d / 2, h / 2
    wall_t = 0.025  # cabinet wall thickness

    base = f"{FURN}/Fridge"
    # +90deg Z rotation: local -X (front/door) -> world -Y (toward room/south)
    su.xform(stage, base, translate=(cx, cy, 0), rotate_xyz=(0, 0, 90))

    # Cabinet: open-front box (kinematic). 5 panels: back, left, right, top, bottom.
    su.xform(stage, f"{base}/Cabinet", translate=(0, 0, half_h))

    cab_color = cfg["materials"]["appliance_metal"]["diffuse"]
    cab_mat = mats.get("appliance_metal", "")

    # Back wall (at +X, against north wall)
    bp = f"{base}/Cabinet/Back"
    su.xform(stage, bp, translate=(half_d - wall_t / 2, 0, 0))
    p = su.cube(stage, f"{bp}/Body", wall_t, w, h, color=cab_color)
    su.add_collision(stage, p); su.bind_material(stage, p, cab_mat)

    # Left side (-Y)
    lp = f"{base}/Cabinet/Left"
    su.xform(stage, lp, translate=(0, -half_w + wall_t / 2, 0))
    p = su.cube(stage, f"{lp}/Body", d, wall_t, h, color=cab_color)
    su.add_collision(stage, p); su.bind_material(stage, p, cab_mat)

    # Right side (+Y)
    rp = f"{base}/Cabinet/Right"
    su.xform(stage, rp, translate=(0, half_w - wall_t / 2, 0))
    p = su.cube(stage, f"{rp}/Body", d, wall_t, h, color=cab_color)
    su.add_collision(stage, p); su.bind_material(stage, p, cab_mat)

    # Top
    tp = f"{base}/Cabinet/Top"
    su.xform(stage, tp, translate=(0, 0, half_h - wall_t / 2))
    p = su.cube(stage, f"{tp}/Body", d, w, wall_t, color=cab_color)
    su.add_collision(stage, p); su.bind_material(stage, p, cab_mat)

    # Bottom
    btp = f"{base}/Cabinet/Bottom"
    su.xform(stage, btp, translate=(0, 0, -half_h + wall_t / 2))
    p = su.cube(stage, f"{btp}/Body", d, w, wall_t, color=cab_color)
    su.add_collision(stage, p); su.bind_material(stage, p, cab_mat)

    su.make_kinematic(stage, f"{base}/Cabinet")

    # Shelves inside cabinet
    shelf_h = 0.02
    shelf_dx, shelf_dy = d - 0.1, w - 0.1
    for i, z_frac in enumerate([0.25, 0.45, 0.65, 0.85]):
        sp = f"{base}/Cabinet/Shelf{i}"
        su.xform(stage, sp, translate=(0, 0, h * z_frac - half_h))
        sbp = su.cube(stage, f"{sp}/Plane", shelf_dx, shelf_dy, shelf_h,
                     color=cfg["materials"]["shelf_metal"]["diffuse"])
        su.add_collision(stage, sbp)
        su.bind_material(stage, sbp, mats.get("shelf_metal", ""))

    # Door: flush with front opening of cabinet (local -X face)
    door_center_x = -half_d + door_d / 2.0
    su.xform(stage, f"{base}/Door", translate=(door_center_x, 0, half_h))
    door_color = cfg["materials"]["appliance_door"]["diffuse"]
    door_panel = su.cube(stage, f"{base}/Door/Panel", door_d, w, h, color=door_color)
    su.add_collision(stage, door_panel)
    su.bind_material(stage, door_panel, mats.get("appliance_door", ""))
    su.make_dynamic(stage, f"{base}/Door", fc["door_mass_kg"])

    # Handle: vertical bar on the OUTSIDE of the door (local -X direction = outward toward south).
    hc = fc["handle"]
    handle_z_local = hc["center_height"] - half_h
    standoff = hc["standoff"]
    bar_len = hc["length"]
    bar_w   = hc["width"]
    bar_d   = hc["depth"]

    handle_x = -(door_d / 2.0 + standoff + bar_d / 2.0)
    handle_y = -(half_w - 0.10)  # near the free (left/east) edge

    su.xform(stage, f"{base}/Door/Handle",
           translate=(handle_x, handle_y, handle_z_local))

    handle_color = (0.08, 0.08, 0.08)
    bar_path = su.cube(stage, f"{base}/Door/Handle/Bar", bar_d, bar_w, bar_len,
                     color=handle_color)
    su.add_collision(stage, bar_path)
    fridge_handle_mat = mats.get(fc.get("handle_material", "handle_metal"), mats.get("handle_metal", ""))
    su.bind_material(stage, bar_path, fridge_handle_mat)

    bracket_d = standoff + 0.01
    for bi, bz in enumerate([bar_len / 2 - 0.04, -bar_len / 2 + 0.04]):
        bp_path = f"{base}/Door/Handle/Bracket{bi}"
        su.xform(stage, bp_path, translate=(bar_d / 2 + bracket_d / 2, 0, bz))
        bbp = su.cube(stage, f"{bp_path}/Body", bracket_d, bar_w, 0.03,
                     color=handle_color)
        su.add_collision(stage, bbp)
        su.bind_material(stage, bbp, fridge_handle_mat)

    print(f"[kitchen] Fridge handle: local pos=({handle_x:.3f}, {handle_y:.3f}, {handle_z_local:.3f}), bar {bar_d}x{bar_w}x{bar_len}")

    # Revolute joint: hinge at front-right edge (+Y local = west in world after 90deg Z rot);
    # door swings open toward south (room center) when pulled south.
    hinge_y_right = half_w  # +Y local = west side in world
    hinge = f"{base}/DoorHinge"
    rev = su.UsdPhysics.RevoluteJoint.Define(stage, hinge)
    rev.GetBody0Rel().SetTargets([su.Sdf.Path(f"{base}/Cabinet")])
    rev.GetBody1Rel().SetTargets([su.Sdf.Path(f"{base}/Door")])
    rev.CreateAxisAttr("Z")
    rev.CreateLowerLimitAttr(0.0)
    rev.CreateUpperLimitAttr(fc["door_open_deg"])
    rev.CreateLocalPos0Attr().Set(su.Gf.Vec3f(-half_d, hinge_y_right, 0.0))
    rev.CreateLocalPos1Attr().Set(su.Gf.Vec3f(-door_d / 2.0, hinge_y_right, 0.0))

    hinge_prim = stage.GetPrimAtPath(hinge)
    drive = su.UsdPhysics.DriveAPI.Apply(hinge_prim, "angular")
    drive.CreateDampingAttr().Set(5.0)
    drive.CreateStiffnessAttr().Set(0.0)

    print(f"[kitchen] Fridge at ({cx}, {cy}): face south; handle on door at /World/Kitchen/Furniture/Fridge/Door/Handle")


def _build_dishwasher(stage, cfg: dict, mats: dict):
    """Build dishwasher straight against north wall (no rotation). Front faces -Y toward room."""
    dc = cfg["furniture"]["dishwasher"]
    w, d, h = dc["width"], dc["depth"], dc["height"]
    cx, cy = dc["center_x"], dc["center_y"]
    door_d = dc["door_thickness"]
    half_w, half_d, half_h = w / 2, d / 2, h / 2

    base = f"{FURN}/Dishwasher"
    su.xform(stage, base, translate=(cx, cy, 0))

    # Cabinet (kinematic)
    su.xform(stage, f"{base}/Cabinet", translate=(0, 0, half_h))
    cab_body = su.cube(stage, f"{base}/Cabinet/Body", d, w, h,
                     color=cfg["materials"]["appliance_metal"]["diffuse"])
    su.add_collision(stage, cab_body)
    su.bind_material(stage, cab_body, mats.get("appliance_metal", ""))
    su.make_kinematic(stage, f"{base}/Cabinet")

    # Racks
    for i, z_frac in enumerate([0.35, 0.65]):
        rp = f"{base}/Cabinet/Rack{i}"
        su.xform(stage, rp, translate=(0, 0, h * z_frac - half_h))
        rbp = su.cube(stage, f"{rp}/Plane", d - 0.1, w - 0.1, 0.02,
                     color=cfg["materials"]["shelf_metal"]["diffuse"])
        su.add_collision(stage, rbp)
        su.bind_material(stage, rbp, mats.get("shelf_metal", ""))

    # Door on front face (-X). Hinge on LEFT (local -Y) so door opens RIGHT toward +X = toward center.
    hinge_y_local = -half_w
    door_center_x = -half_d + door_d / 2.0
    su.xform(stage, f"{base}/Door", translate=(door_center_x, 0, half_h))
    door_panel = su.cube(stage, f"{base}/Door/Panel", door_d, w, h,
                       color=cfg["materials"]["appliance_door"]["diffuse"])
    su.add_collision(stage, door_panel)
    su.bind_material(stage, door_panel, mats.get("appliance_door", ""))
    su.make_dynamic(stage, f"{base}/Door", dc["door_mass_kg"])

    # Handle on right (free) side of door so pull opens toward center
    hc = dc["handle"]
    handle_z_local = hc["center_height"] - half_h
    standoff = hc["standoff"]
    bar_len, bar_w, bar_d = hc["length"], hc["width"], hc["depth"]

    su.xform(stage, f"{base}/Door/Handle",
           translate=(-door_d / 2 - standoff - bar_d / 2, half_w - 0.08, handle_z_local))
    bar_path = su.cube(stage, f"{base}/Door/Handle/Bar", bar_d, bar_len, bar_w,
                     color=cfg["materials"]["handle_metal"]["diffuse"])
    su.add_collision(stage, bar_path)
    su.bind_material(stage, bar_path, mats.get("handle_metal", ""))

    for bi, by in enumerate([bar_len / 2 - 0.02, -bar_len / 2 + 0.02]):
        bp = f"{base}/Door/Handle/Bracket{bi}"
        su.xform(stage, bp, translate=(bar_d / 2 + standoff / 2, by, 0))
        bbp = su.cube(stage, f"{bp}/Body", standoff, bar_w, bar_w,
                     color=cfg["materials"]["handle_metal"]["diffuse"])
        su.add_collision(stage, bbp)
        su.bind_material(stage, bbp, mats.get("handle_metal", ""))

    # Revolute: axis Z (vertical); hinge at left (-Y). Limits -90..0 so door opens toward +X (center).
    hinge = f"{base}/DoorHinge"
    rev = su.UsdPhysics.RevoluteJoint.Define(stage, hinge)
    rev.GetBody0Rel().SetTargets([su.Sdf.Path(f"{base}/Cabinet")])
    rev.GetBody1Rel().SetTargets([su.Sdf.Path(f"{base}/Door")])
    rev.CreateAxisAttr("Z")
    rev.CreateLowerLimitAttr(-dc["door_open_deg"])
    rev.CreateUpperLimitAttr(0.0)
    rev.CreateLocalPos0Attr().Set(su.Gf.Vec3f(-half_d, hinge_y_local, 0.0))
    rev.CreateLocalPos1Attr().Set(su.Gf.Vec3f(-door_d / 2.0, hinge_y_local, 0.0))

    print(f"[kitchen] Dishwasher at ({cx}, {cy}): straight against wall, handle length={hc['length']}m")


def _build_sink_cabinet(stage, cfg: dict, mats: dict):
    sc = cfg["furniture"]["sink_cabinet"]
    w, d, h = sc["width"], sc["depth"], sc["height"]
    cx, cy = sc["center_x"], sc["center_y"]
    half_w, half_d, half_h = w / 2, d / 2, h / 2

    base = f"{FURN}/SinkCabinet"
    su.xform(stage, base, translate=(cx, cy, 0))

    su.xform(stage, f"{base}/Cabinet", translate=(0, 0, half_h))
    cab_body = su.cube(stage, f"{base}/Cabinet/Body", d, w, h,
                     color=cfg["materials"]["cabinet_wood"]["diffuse"])
    su.add_collision(stage, cab_body)
    su.bind_material(stage, cab_body, mats.get("cabinet_wood", ""))

    ct_h = 0.03
    su.xform(stage, f"{base}/CounterTop", translate=(0, 0, h + ct_h / 2))
    ct_path = su.cube(stage, f"{base}/CounterTop/Slab", d, w, ct_h,
                    color=cfg["materials"]["sink_metal"]["diffuse"])
    su.add_collision(stage, ct_path)
    su.bind_material(stage, ct_path, mats.get("sink_metal", ""))

    bd = sc["basin_depth"]
    bm = sc["basin_margin"]
    basin_w = w - 2 * bm
    basin_d = d - 2 * bm
    basin_z = h - bd / 2
    su.xform(stage, f"{base}/Basin", translate=(0, 0, basin_z))

    su.xform(stage, f"{base}/Basin/Floor", translate=(0, 0, -bd / 2 + 0.01))
    bf = su.cube(stage, f"{base}/Basin/Floor/Slab", basin_d, basin_w, 0.02,
               color=cfg["materials"]["sink_metal"]["diffuse"])
    su.add_collision(stage, bf)
    su.bind_material(stage, bf, mats.get("sink_metal", ""))

    wall_t = 0.015
    for name, pos, sz in [
        ("WallN", (0, basin_w / 2 - wall_t / 2, 0), (basin_d, wall_t, bd)),
        ("WallS", (0, -basin_w / 2 + wall_t / 2, 0), (basin_d, wall_t, bd)),
        ("WallE", (basin_d / 2 - wall_t / 2, 0, 0), (wall_t, basin_w, bd)),
        ("WallW", (-basin_d / 2 + wall_t / 2, 0, 0), (wall_t, basin_w, bd)),
    ]:
        wp = f"{base}/Basin/{name}"
        su.xform(stage, wp, translate=pos)
        wbp = su.cube(stage, f"{wp}/Body", *sz,
                     color=cfg["materials"]["sink_metal"]["diffuse"])
        su.add_collision(stage, wbp)
        su.bind_material(stage, wbp, mats.get("sink_metal", ""))

    # Faucet
    ct_z = h + ct_h
    faucet_y = 0.24
    base_h = 0.08
    base_rad = 0.06
    faucet_color = cfg["materials"]["faucet_metal"]["diffuse"]
    su.xform(stage, f"{base}/Faucet", translate=(0, faucet_y, ct_z + base_h / 2))
    su.xform(stage, f"{base}/Faucet/Base", translate=(0, 0, 0))
    faucet_base = su.cylinder(stage, f"{base}/Faucet/Base/Cyl", base_rad, base_h, color=faucet_color)
    su.bind_material(stage, faucet_base, mats.get("faucet_metal", ""))
    stem_h = 0.15 * 1.5
    su.xform(stage, f"{base}/Faucet/Stem", translate=(0, 0, base_h / 2 + stem_h / 2))
    stem = su.cylinder(stage, f"{base}/Faucet/Stem/Cyl", base_rad * 0.6, stem_h, color=faucet_color)
    su.bind_material(stage, stem, mats.get("faucet_metal", ""))
    spout_len = 0.28 * 2
    spout_z = base_h / 2 + stem_h
    su.xform(stage, f"{base}/Faucet/Spout", translate=(0, -spout_len / 2, spout_z))
    spout = su.cube(stage, f"{base}/Faucet/Spout/Bar", 0.04, spout_len, 0.04, color=faucet_color)
    su.bind_material(stage, spout, mats.get("faucet_metal", ""))

    prim = stage.GetPrimAtPath(base)
    su.UsdPhysics.CollisionAPI.Apply(prim)
    print(f"[kitchen] Sink cabinet at ({cx}, {cy}): {w}x{d}x{h}m, basin depth={bd}m, faucet added")


def _build_table(stage, cfg: dict, mats: dict):
    tc = cfg["furniture"]["table"]
    w, d, h = tc["width"], tc["depth"], tc["height"]
    cx, cy = tc["center_x"], tc["center_y"]
    top_h = tc["top_thickness"]
    leg_w = tc["leg_width"]

    base = f"{FURN}/Table"
    su.xform(stage, base, translate=(cx, cy, 0))

    top_z = h - top_h / 2
    su.xform(stage, f"{base}/Top", translate=(0, 0, top_z))
    tp = su.cube(stage, f"{base}/Top/Slab", d, w, top_h,
               color=cfg["materials"]["table_wood"]["diffuse"])
    su.add_collision(stage, tp)
    su.bind_material(stage, tp, mats.get("table_wood", ""))

    leg_h = h - top_h
    su.UsdGeom.Xform.Define(stage, f"{base}/Legs")
    offsets = [
        (-d / 2 + leg_w, -w / 2 + leg_w),
        (d / 2 - leg_w, -w / 2 + leg_w),
        (-d / 2 + leg_w, w / 2 - leg_w),
        (d / 2 - leg_w, w / 2 - leg_w),
    ]
    for i, (lx, ly) in enumerate(offsets):
        lp = f"{base}/Legs/Leg{i}"
        su.xform(stage, lp, translate=(lx, ly, leg_h / 2))
        lbp = su.cube(stage, f"{lp}/Body", leg_w, leg_w, leg_h,
                     color=[c * 0.8 for c in cfg["materials"]["table_wood"]["diffuse"]])
        su.add_collision(stage, lbp)
        su.bind_material(stage, lbp, mats.get("table_wood", ""))

    print(f"[kitchen] Table at ({cx}, {cy}): {w}x{d}x{h}m, top at z={h}m")


def _build_objects(stage, cfg: dict, mats: dict):
    tc = cfg["furniture"]["table"]
    table_cx, table_cy = tc["center_x"], tc["center_y"]
    table_top_z = tc["height"]
    objs = cfg["objects"]

    # Plate
    pc = objs["plate"]
    plate_x = table_cx + pc["offset_x"]
    plate_y = table_cy + pc["offset_y"]
    plate_z = table_top_z + pc["height"] / 2
    su.xform(stage, f"{OBJ}/Plate", translate=(plate_x, plate_y, plate_z))
    pp = su.cylinder(stage, f"{OBJ}/Plate/Disc", pc["radius"], pc["height"],
                   color=cfg["materials"]["ceramic_white"]["diffuse"])
    su.add_collision(stage, pp)
    su.bind_material(stage, pp, mats.get("ceramic_white", ""))
    su.make_dynamic(stage, f"{OBJ}/Plate", pc["mass_kg"])

    # Apple
    ac = objs["apple"]
    apple_x = plate_x + ac["offset_x"]
    apple_y = plate_y + ac["offset_y"]
    apple_z = table_top_z + pc["height"] + ac["radius"]
    su.xform(stage, f"{OBJ}/Apple", translate=(apple_x, apple_y, apple_z))
    ap = f"{OBJ}/Apple/Body"
    sphere = su.UsdGeom.Sphere.Define(stage, ap)
    sphere.CreateRadiusAttr(ac["radius"])
    sphere.CreateDisplayColorAttr([su.Gf.Vec3f(*cfg["materials"]["apple_red"]["diffuse"])])
    su.add_collision(stage, ap)
    su.bind_material(stage, ap, mats.get("apple_red", ""))
    su.make_dynamic(stage, f"{OBJ}/Apple", ac["mass_kg"])

    # Banana: on the plate surface
    bc = objs["banana"]
    banana_x = plate_x + bc["offset_x"]
    banana_y = plate_y + bc["offset_y"]
    banana_z = table_top_z + pc["height"] + bc["radius"]
    su.xform(stage, f"{OBJ}/Banana", translate=(banana_x, banana_y, banana_z),
           rotate_xyz=(90, 0, 0))
    bp = su.cylinder(stage, f"{OBJ}/Banana/Body", bc["radius"], bc["length"],
                   color=cfg["materials"]["banana_yellow"]["diffuse"])
    su.add_collision(stage, bp)
    su.bind_material(stage, bp, mats.get("banana_yellow", ""))
    su.make_dynamic(stage, f"{OBJ}/Banana", bc["mass_kg"])

    # Mug
    mc = objs["mug"]
    mug_x = table_cx + mc["offset_x"]
    mug_y = table_cy + mc["offset_y"]
    mug_z = table_top_z + mc["height"] / 2
    su.xform(stage, f"{OBJ}/Mug", translate=(mug_x, mug_y, mug_z))
    mp = su.cylinder(stage, f"{OBJ}/Mug/Body", mc["radius"], mc["height"],
                   color=cfg["materials"]["mug_ceramic"]["diffuse"])
    su.add_collision(stage, mp)
    su.bind_material(stage, mp, mats.get("mug_ceramic", ""))
    su.make_dynamic(stage, f"{OBJ}/Mug", mc["mass_kg"])

    print(f"[kitchen] Objects: plate({plate_x:.2f},{plate_y:.2f}), "
          f"apple, banana, mug({mug_x:.2f},{mug_y:.2f})")


def _build_lights(stage, cfg: dict):
    lc = cfg.get("lights", {})
    su.xform(stage, f"{ROOT}/Lights")

    # Dome light
    dc = lc.get("dome", {})
    dome = su.UsdLux.DomeLight.Define(stage, f"{ROOT}/Lights/DomeLight")
    dome.CreateIntensityAttr(dc.get("intensity", 800.0))
    dome_color = dc.get("color", [1.0, 0.96, 0.90])
    dome.CreateColorAttr(su.Gf.Vec3f(*dome_color))
    dome_texture = su.resolve_texture_path(dc.get("texture"), tex_dir=str(Path(__file__).parent / "textures"), caller_dir=_CALLER_DIR)
    if dome_texture:
        try:
            dome.CreateTextureFileAttr().Set(su.Sdf.AssetPath(dome_texture))
            print(f"[kitchen] Dome texture: {dome_texture}")
        except Exception as e:
            print(f"[kitchen] WARNING: failed to set dome texture '{dome_texture}': {e}")
    elif str(dc.get("texture", "")).strip():
        print(f"[kitchen] WARNING: dome texture not found: {dc.get('texture')}")

    # Ceiling area lights
    cc = lc.get("ceiling", {})
    positions = cc.get("positions", [])
    ceiling_color = cc.get("color", [1.0, 0.95, 0.88])
    for i, pos in enumerate(positions):
        lp = f"{ROOT}/Lights/CeilingLight{i}"
        light = su.UsdLux.RectLight.Define(stage, lp)
        light.CreateIntensityAttr(cc.get("intensity", 3000.0))
        light.CreateWidthAttr(cc.get("width", 0.6))
        light.CreateHeightAttr(cc.get("height", 0.6))
        light.CreateColorAttr(su.Gf.Vec3f(*ceiling_color))
        xf = su.UsdGeom.Xformable(light.GetPrim())
        xf.AddTranslateOp().Set(su.Gf.Vec3d(pos[0], pos[1], cc.get("z", 2.75)))
        xf.AddRotateXYZOp().Set(su.Gf.Vec3f(180, 0, 0))

    print(f"[kitchen] Lights: warm dome + {len(positions)} warm ceiling panels")


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

    print(f"[kitchen] Cameras: {list(cams.keys())}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_kitchen_scene(stage, config_path: str | None = None, cfg: dict | None = None):
    su.ensure_pxr()

    if cfg is None:
        if config_path is None:
            config_path = str(Path(__file__).parent / "kitchen_fixed_config.yaml")
        cfg = su.load_config(config_path)

    su.UsdGeom.Xform.Define(stage, ROOT)
    su.UsdGeom.SetStageUpAxis(stage, su.UsdGeom.Tokens.z)
    su.UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    print("[kitchen] Building fixed kitchen scene...")
    su.build_physics_scene(stage, ROOT, cfg)
    mats = _build_materials(stage, cfg)
    su.build_floor(stage, ROOT, cfg, mats, floor_mat_key="floor_tile", label="kitchen")
    su.build_walls(stage, ROOT, cfg, mats, label="kitchen")
    _build_paintings(stage, cfg, mats)
    _build_fridge(stage, cfg, mats)
    _build_sink_cabinet(stage, cfg, mats)
    _build_table(stage, cfg, mats)
    _build_objects(stage, cfg, mats)
    _build_lights(stage, cfg)
    _build_cameras(stage, cfg)
    print("[kitchen] Scene build complete.")

    return cfg


def main():
    parser = argparse.ArgumentParser(description="Build fixed kitchen USD scene")
    parser.add_argument("--config", type=str,
                        default=str(Path(__file__).parent / "kitchen_fixed_config.yaml"))
    parser.add_argument("--output", type=str,
                        default=str(Path(__file__).parent / "kitchen_fixed.usd"))
    parser.add_argument("--usda", action="store_true",
                        help="Save as .usda (ASCII) instead of binary .usd")
    args = parser.parse_args()

    import sys as _sys
    _log = lambda msg: _sys.stderr.write(msg + "\n")

    _log("[kitchen] Starting SimulationApp for USD generation...")
    from isaacsim import SimulationApp
    sim_app = SimulationApp({"headless": True})

    su.ensure_pxr()

    out_path = os.path.abspath(args.output)
    if args.usda and out_path.endswith(".usd"):
        out_path = out_path + "a"
    if os.path.exists(out_path):
        os.remove(out_path)

    _log(f"[kitchen] Creating stage: {out_path}")
    stage = su.Usd.Stage.CreateNew(out_path)
    try:
        build_kitchen_scene(stage, config_path=args.config)
        stage.GetRootLayer().Save()
        _log(f"[kitchen] Saved: {out_path}")

        prim_count = sum(1 for _ in stage.Traverse())
        _log(f"[kitchen] Total prims: {prim_count}")
    except Exception as e:
        _log(f"[kitchen] ERROR: {e}")
        import traceback
        traceback.print_exc(file=_sys.stderr)
        sim_app.close()
        _sys.exit(1)

    sim_app.close()


if __name__ == "__main__":
    main()
