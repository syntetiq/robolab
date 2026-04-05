"""
build_demo_slideshow.py — Generate a demo video from screenshots and Isaac Sim frames.

Creates title cards, UI mockup slides, and Isaac Sim scene frames,
then assembles everything into a single MP4 with ffmpeg.

Usage:
    python scripts/build_demo_slideshow.py [--output demo_output/robolab_demo.mp4]

Prerequisites:
    pip install Pillow
    ffmpeg installed (winget install Gyan.FFmpeg)
"""

from __future__ import annotations
import os, sys, subprocess, argparse, shutil, tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Find ffmpeg
# ---------------------------------------------------------------------------

def find_ffmpeg() -> str:
    env = os.environ.get("FFMPEG_BIN")
    if env and os.path.isfile(env):
        return env
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    winget_path = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    for p in winget_path.rglob("ffmpeg.exe"):
        return str(p)
    print("ERROR: ffmpeg not found")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

W, H = 1920, 1080
FPS = 2  # slideshow pace — 2 fps = each frame shown 0.5 sec
TITLE_SECS = 4
SLIDE_SECS = 5
ISAAC_SECS = 3  # per isaac frame

# Colors
BG_DARK = (18, 18, 24)
BG_CARD = (30, 32, 40)
ACCENT = (59, 130, 246)
WHITE = (255, 255, 255)
GRAY = (160, 165, 180)
LIGHT_GRAY = (200, 205, 215)
GREEN = (34, 197, 94)
ORANGE = (249, 115, 22)

# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

_font_cache = {}

def get_font(size: int, bold: bool = False):
    from PIL import ImageFont
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]
    candidates = []
    if bold:
        candidates = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]
    else:
        candidates = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]
    for c in candidates:
        try:
            f = ImageFont.truetype(c, size)
            _font_cache[key] = f
            return f
        except (IOError, OSError):
            continue
    f = ImageFont.load_default()
    _font_cache[key] = f
    return f

# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def draw_rounded_rect(draw, xy, fill, radius=12):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.pieslice([x0, y0, x0 + 2*radius, y0 + 2*radius], 180, 270, fill=fill)
    draw.pieslice([x1 - 2*radius, y0, x1, y0 + 2*radius], 270, 360, fill=fill)
    draw.pieslice([x0, y1 - 2*radius, x0 + 2*radius, y1], 90, 180, fill=fill)
    draw.pieslice([x1 - 2*radius, y1 - 2*radius, x1, y1], 0, 90, fill=fill)

def draw_badge(draw, xy, text, color, font):
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 10, 4
    draw_rounded_rect(draw, (x, y, x + tw + 2*pad_x, y + th + 2*pad_y), fill=color, radius=6)
    draw.text((x + pad_x, y + pad_y), text, fill=WHITE, font=font)
    return tw + 2*pad_x + 8  # return width for next badge

def draw_overlay_bar(draw, text):
    """Draw semi-transparent bottom bar with text."""
    bar_h = 60
    bar_y = H - bar_h
    # Semi-transparent black bar
    for y in range(bar_y, H):
        for x in range(0, W, 1):
            pass  # Can't do alpha easily, use solid dark
    draw.rectangle([0, bar_y, W, H], fill=(10, 10, 15))
    # Accent line on top
    draw.rectangle([0, bar_y, W, bar_y + 2], fill=ACCENT)
    font = get_font(22)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, bar_y + 20), text, fill=LIGHT_GRAY, font=font)

# ---------------------------------------------------------------------------
# Slide generators
# ---------------------------------------------------------------------------

def make_title_slide(title: str, subtitle: str) -> "Image":
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)

    # Accent line
    aw = 120
    ay = H // 2 - 70
    draw.rectangle([(W - aw) // 2, ay, (W + aw) // 2, ay + 4], fill=ACCENT)

    # Title
    font_title = get_font(68, bold=True)
    bbox = draw.textbbox((0, 0), title, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H // 2 - 45), title, fill=WHITE, font=font_title)

    # Subtitle
    font_sub = get_font(28)
    bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H // 2 + 45), subtitle, fill=GRAY, font=font_sub)

    return img


def make_dashboard_slide() -> "Image":
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), (245, 245, 248))
    draw = ImageDraw.Draw(img)

    # Sidebar
    draw.rectangle([0, 0, 200, H], fill=(255, 255, 255))
    draw.rectangle([200, 0, 202, H], fill=(230, 230, 235))

    # Logo
    font_logo = get_font(22, bold=True)
    draw.text((25, 25), "RoboLab", fill=(20, 20, 25), font=font_logo)
    font_sm = get_font(13)
    draw.text((25, 52), "Console", fill=(20, 20, 25), font=get_font(20, bold=True))
    draw.text((25, 78), "Data Collection MVP", fill=GRAY, font=font_sm)

    # Sidebar items
    items = ["Dashboard", "Episodes", "Experiments", "Recordings", "Scenes", "Launch Profiles", "Configuration"]
    font_menu = get_font(16)
    for i, item in enumerate(items):
        y = 120 + i * 40
        if i == 0:
            draw_rounded_rect(draw, (8, y - 5, 192, y + 28), fill=(20, 20, 25), radius=8)
            draw.text((25, y), item, fill=WHITE, font=font_menu)
        else:
            draw.text((25, y), item, fill=(80, 85, 95), font=font_menu)

    # Header
    font_h1 = get_font(32, bold=True)
    draw.text((240, 30), "System Dashboard", fill=(20, 20, 25), font=font_h1)

    # Instance Health card
    draw_rounded_rect(draw, (240, 85, 700, 280), fill=WHITE, radius=12)
    draw.text((270, 100), "Instance Health", fill=(20, 20, 25), font=get_font(18, bold=True))
    # CPU
    draw.text((270, 145), "CPU Load", fill=(80, 85, 95), font=get_font(15))
    draw.text((630, 145), "22%", fill=(20, 20, 25), font=get_font(15))
    draw.rectangle([270, 170, 670, 178], fill=(230, 230, 235))
    draw.rectangle([270, 170, 358, 178], fill=ACCENT)
    # Memory
    draw.text((270, 195), "Memory Usage", fill=(80, 85, 95), font=get_font(15))
    draw.text((630, 195), "44%", fill=(20, 20, 25), font=get_font(15))
    draw.rectangle([270, 220, 670, 228], fill=(230, 230, 235))
    draw.rectangle([270, 220, 446, 228], fill=GREEN)
    # Host/Runner
    draw.text((270, 245), "Host: localhost   Runner: LOCAL_RUNNER", fill=(80, 85, 95), font=get_font(14))

    # Quick Actions card
    draw_rounded_rect(draw, (730, 85, 1350, 280), fill=WHITE, radius=12)
    draw.text((760, 100), "Quick Actions", fill=(20, 20, 25), font=get_font(18, bold=True))
    actions = ["New Episode", "Manage Scenes", "Manage Objects", "Console Settings"]
    for i, act in enumerate(actions):
        x = 760 + i * 140
        draw_rounded_rect(draw, (x, 140, x + 125, 260), fill=(248, 248, 250), radius=10)
        draw.text((x + 15, 210), act, fill=(60, 65, 75), font=get_font(13))

    draw_overlay_bar(draw, "RoboLab Console — Data collection platform for robotic simulation")
    return img


def make_scenes_slide() -> "Image":
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), (245, 245, 248))
    draw = ImageDraw.Draw(img)

    # Sidebar (simplified)
    draw.rectangle([0, 0, 200, H], fill=(255, 255, 255))
    draw.rectangle([200, 0, 202, H], fill=(230, 230, 235))
    font_logo = get_font(22, bold=True)
    draw.text((25, 25), "RoboLab", fill=(20, 20, 25), font=font_logo)
    draw.text((25, 52), "Console", fill=(20, 20, 25), font=get_font(20, bold=True))
    items = ["Dashboard", "Episodes", "Experiments", "Recordings", "Scenes", "Launch Profiles", "Configuration"]
    font_menu = get_font(16)
    for i, item in enumerate(items):
        y = 120 + i * 40
        if i == 4:  # Scenes
            draw_rounded_rect(draw, (8, y - 5, 192, y + 28), fill=(20, 20, 25), radius=8)
            draw.text((25, y), item, fill=WHITE, font=font_menu)
        else:
            draw.text((25, y), item, fill=(80, 85, 95), font=font_menu)

    # Header
    draw.text((240, 30), "Scenes", fill=(20, 20, 25), font=get_font(32, bold=True))
    draw.text((240, 70), "Manage simulation environments available for episodes.", fill=GRAY, font=get_font(15))

    # Add Scene button
    draw_rounded_rect(draw, (1200, 30, 1340, 65), fill=(20, 20, 25), radius=8)
    draw.text((1225, 38), "+ Add Scene", fill=WHITE, font=get_font(15))

    # Table
    draw_rounded_rect(draw, (240, 105, 1380, 300), fill=WHITE, radius=12)
    cols = ["Name", "Type", "Stage USD Path", "Capabilities", "Actions"]
    col_x = [260, 420, 540, 880, 1280]
    font_th = get_font(14, bold=True)
    font_td = get_font(14)
    for ci, col in enumerate(cols):
        draw.text((col_x[ci], 120), col, fill=(80, 85, 95), font=font_th)
    draw.rectangle([255, 145, 1365, 146], fill=(235, 235, 240))

    # Row 1 — Kitchen
    y = 160
    draw.text((260, y), "Kitchen Fixed", fill=(20, 20, 25), font=font_td)
    draw.text((420, y), "Indoor", fill=(80, 85, 95), font=font_td)
    draw.text((540, y), "kitchen_fixed.usd", fill=(80, 85, 95), font=get_font(13))
    badge_font = get_font(12)
    bx = 880
    for badge in ["navigation", "manipulation", "pick_place_table"]:
        bx += draw_badge(draw, (bx, y), badge, (59, 130, 246), badge_font)

    # Row 2 — Office
    y = 210
    draw.rectangle([255, 195, 1365, 196], fill=(245, 245, 248))
    draw.text((260, y), "Office Fixed", fill=(20, 20, 25), font=font_td)
    draw.text((420, y), "Indoor", fill=(80, 85, 95), font=font_td)
    draw.text((540, y), "office_fixed.usd", fill=(80, 85, 95), font=get_font(13))
    bx = 880
    for badge in ["navigation", "manipulation", "open_close_cabinet"]:
        bx += draw_badge(draw, (bx, y), badge, (59, 130, 246), badge_font)

    draw_overlay_bar(draw, "Procedural 3D environments with physics and articulated furniture")
    return img


def make_episode_wizard_slide() -> "Image":
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), (245, 245, 248))
    draw = ImageDraw.Draw(img)

    # Sidebar
    draw.rectangle([0, 0, 200, H], fill=(255, 255, 255))
    draw.rectangle([200, 0, 202, H], fill=(230, 230, 235))
    draw.text((25, 25), "RoboLab", fill=(20, 20, 25), font=get_font(22, bold=True))
    draw.text((25, 52), "Console", fill=(20, 20, 25), font=get_font(20, bold=True))

    # Header
    draw.text((240, 30), "New Episode", fill=(20, 20, 25), font=get_font(32, bold=True))

    # Steps indicator
    steps = ["Scene", "Profile", "Sensors", "Parameters", "Review"]
    for i, step in enumerate(steps):
        x = 260 + i * 180
        color = GREEN if i < 4 else ACCENT
        draw.ellipse([x, 85, x + 28, 113], fill=color)
        draw.text((x + 9, 89), str(i + 1), fill=WHITE, font=get_font(14, bold=True))
        draw.text((x + 36, 90), step, fill=(20, 20, 25) if i <= 4 else GRAY, font=get_font(15))
        if i < 4:
            draw.rectangle([x + 28 + len(step) * 8 + 40, 98, x + 170, 100], fill=(220, 220, 225))

    # Review card
    draw_rounded_rect(draw, (240, 140, 1100, 620), fill=WHITE, radius=12)
    draw.text((270, 160), "Step 5: Review Execution Plan", fill=(20, 20, 25), font=get_font(22, bold=True))

    rows = [
        ("Scene:", "Office Fixed (open-space)"),
        ("Launch Profile:", "Default Safe Live Teleop"),
        ("Sensors:", "RGB, Depth, JointStates"),
        ("Seed:", "42"),
        ("Duration:", "60 seconds"),
        ("Output Directory:", "C:\\RoboLab_Data\\episodes\\"),
        ("Runner Mode:", "LOCAL_RUNNER"),
    ]
    for i, (label, value) in enumerate(rows):
        y = 210 + i * 50
        draw.text((290, y), label, fill=(80, 85, 95), font=get_font(16))
        draw.text((520, y), value, fill=(20, 20, 25), font=get_font(16))

    # Create button
    draw_rounded_rect(draw, (270, 570, 440, 605), fill=(20, 20, 25), radius=8)
    draw.text((300, 578), "Create Episode", fill=WHITE, font=get_font(15))

    draw_overlay_bar(draw, "5-step wizard: scene \u2192 profile \u2192 sensors \u2192 parameters \u2192 launch")
    return img


def make_episode_detail_slide() -> "Image":
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), (245, 245, 248))
    draw = ImageDraw.Draw(img)

    # Sidebar
    draw.rectangle([0, 0, 200, H], fill=(255, 255, 255))
    draw.rectangle([200, 0, 202, H], fill=(230, 230, 235))
    draw.text((25, 25), "RoboLab", fill=(20, 20, 25), font=get_font(22, bold=True))
    draw.text((25, 52), "Console", fill=(20, 20, 25), font=get_font(20, bold=True))

    # Header
    draw.text((240, 20), "Episode Detail", fill=(20, 20, 25), font=get_font(28, bold=True))

    # Status badge
    draw_rounded_rect(draw, (500, 22, 610, 50), fill=GREEN, radius=6)
    draw.text((515, 27), "Completed", fill=WHITE, font=get_font(14, bold=True))

    # Left column — Details
    draw_rounded_rect(draw, (240, 70, 680, 320), fill=WHITE, radius=12)
    draw.text((270, 85), "Episode Details", fill=(20, 20, 25), font=get_font(18, bold=True))
    details = [
        ("ID:", "f429b318-5f5d-..."),
        ("Scene:", "Office Fixed"),
        ("Seed:", "42"),
        ("Duration:", "60s"),
        ("Output:", "C:\\RoboLab_Data\\episodes\\f429b318..."),
    ]
    for i, (k, v) in enumerate(details):
        y = 125 + i * 35
        draw.text((290, y), k, fill=GRAY, font=get_font(14))
        draw.text((420, y), v, fill=(20, 20, 25), font=get_font(14))

    # Download button
    draw_rounded_rect(draw, (270, 280, 440, 305), fill=(248, 248, 250), radius=6)
    draw.text((285, 285), "Download Metadata", fill=(60, 65, 75), font=get_font(13))

    # Right column — Video
    draw_rounded_rect(draw, (700, 70, 1380, 420), fill=WHITE, radius=12)
    draw.text((730, 85), "Recorded Videos", fill=(20, 20, 25), font=get_font(18, bold=True))
    # Video player mockup
    draw.rectangle([730, 120, 1350, 400], fill=(15, 15, 20))
    # Play button triangle
    cx, cy = 1040, 260
    draw.polygon([(cx - 20, cy - 25), (cx - 20, cy + 25), (cx + 20, cy)], fill=(255, 255, 255, 180))
    draw.text((730, 405), "camera_0.mp4", fill=GRAY, font=get_font(13))

    # Dataset Validation
    draw_rounded_rect(draw, (240, 340, 680, 500), fill=WHITE, radius=12)
    draw.text((270, 355), "Dataset Validation", fill=(20, 20, 25), font=get_font(18, bold=True))
    draw_rounded_rect(draw, (270, 395, 350, 418), fill=GREEN, radius=6)
    draw.text((280, 398), "Valid", fill=WHITE, font=get_font(13, bold=True))
    draw.text((270, 430), "Required: joint_trajectories, video, world_poses", fill=(80, 85, 95), font=get_font(13))
    draw.text((270, 455), "Missing: none", fill=GREEN, font=get_font(13))

    # Sensors
    draw_rounded_rect(draw, (700, 440, 1380, 540), fill=WHITE, radius=12)
    draw.text((730, 455), "Recording Sensors", fill=(20, 20, 25), font=get_font(18, bold=True))
    bx = 730
    badge_font = get_font(13)
    for s in ["RGB", "Depth", "JointStates", "CameraInfo"]:
        bx += draw_badge(draw, (bx, 490), s, (80, 85, 100), badge_font)

    draw_overlay_bar(draw, "Video, telemetry, dataset validation \u2014 all in one interface")
    return img


def make_isaac_slide(frame_path: str, label: str) -> "Image":
    """Create a slide from an Isaac Sim replicator frame."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)

    # Load and resize the Isaac Sim frame
    try:
        frame = Image.open(frame_path).convert("RGB")
        # Center-fit into 1720x880 area
        area_w, area_h = 1720, 880
        frame.thumbnail((area_w, area_h), Image.LANCZOS)
        fw, fh = frame.size
        x = (W - fw) // 2
        y = (H - fh) // 2 - 20
        img.paste(frame, (x, y))
        # Border
        draw.rectangle([x - 2, y - 2, x + fw + 1, y + fh + 1], outline=(50, 55, 65), width=2)
    except Exception as e:
        draw.text((W // 2 - 100, H // 2), f"Frame: {e}", fill=GRAY, font=get_font(18))

    draw_overlay_bar(draw, label)
    return img

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build RoboLab demo slideshow video")
    parser.add_argument("--output", default="demo_output/robolab_demo.mp4")
    parser.add_argument("--episodes-dir", default="C:/RoboLab_Data/episodes")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = find_ffmpeg()
    print(f"ffmpeg: {ffmpeg}")

    try:
        from PIL import Image
    except ImportError:
        print("ERROR: pip install Pillow")
        sys.exit(1)

    # Find Isaac Sim frames
    episodes_dir = Path(args.episodes_dir)
    isaac_frames = []
    # Office episode
    for ep_dir in sorted(episodes_dir.glob("f429b318*")):
        rd = ep_dir / "replicator_data"
        if rd.exists():
            for fname in ["rgb_0015.png", "rgb_0060.png", "rgb_0120.png", "rgb_0200.png"]:
                fp = rd / fname
                if fp.exists():
                    isaac_frames.append(("office", str(fp)))
    # Kitchen episode
    for ep_dir in sorted(episodes_dir.glob("*")):
        rd = ep_dir / "replicator_data"
        if rd.exists() and ep_dir.name != "f429b318-5f5d-4286-a929-5ac3b3a31f61":
            for fname in ["rgb_0060.png"]:
                fp = rd / fname
                if fp.exists():
                    isaac_frames.append(("kitchen", str(fp)))
                    break
            if len([f for f in isaac_frames if f[0] == "kitchen"]) > 0:
                break

    print(f"Found {len(isaac_frames)} Isaac Sim frames")

    # Generate all slides
    slides = []

    # 1. Title
    print("Generating title...")
    slides.append(("title", make_title_slide("RoboLab Console", "Data Collection Platform for Robotic Simulation"), TITLE_SECS))

    # 2. Dashboard
    print("Generating dashboard...")
    slides.append(("dashboard", make_dashboard_slide(), SLIDE_SECS))

    # 3. Title: Scenes
    slides.append(("title_scenes", make_title_slide("Scenes & Configuration", "Procedural 3D environments with physics and articulated furniture"), TITLE_SECS))

    # 4. Scenes page
    print("Generating scenes page...")
    slides.append(("scenes", make_scenes_slide(), SLIDE_SECS))

    # 5. Title: Episode Creation
    slides.append(("title_wizard", make_title_slide("Episode Creation", "5-step wizard: scene \u2192 profile \u2192 sensors \u2192 parameters \u2192 launch"), TITLE_SECS))

    # 6. Episode wizard
    print("Generating episode wizard...")
    slides.append(("wizard", make_episode_wizard_slide(), SLIDE_SECS))

    # 7. Title: Results
    slides.append(("title_results", make_title_slide("Episode Results", "Video, telemetry, dataset validation \u2014 all in one interface"), TITLE_SECS))

    # 8. Episode detail
    print("Generating episode detail...")
    slides.append(("detail", make_episode_detail_slide(), SLIDE_SECS))

    # 9. Title: Simulation
    slides.append(("title_sim", make_title_slide("Isaac Sim Scenes", "TIAGo robot in procedural environments"), TITLE_SECS))

    # 10. Isaac Sim frames
    for i, (scene_type, frame_path) in enumerate(isaac_frames):
        label = f"TIAGo robot in {scene_type} scene \u2014 Isaac Sim replicator frame"
        print(f"Adding Isaac frame: {Path(frame_path).name} ({scene_type})")
        slides.append((f"isaac_{i}", make_isaac_slide(frame_path, label), ISAAC_SECS))

    # 11. Final title
    slides.append(("final", make_title_slide("RoboLab Console", "github.com/tmhwk77/robolab"), TITLE_SECS))

    print(f"\nTotal: {len(slides)} slides, ~{sum(s[2] for s in slides)}s")

    # Save slides and build video
    with tempfile.TemporaryDirectory(prefix="robolab_demo_") as tmp:
        tmp = Path(tmp)
        segments = []

        for i, (name, img, duration) in enumerate(slides):
            png_path = tmp / f"{i:03d}_{name}.png"
            mp4_path = tmp / f"{i:03d}_{name}.mp4"
            img.save(str(png_path), "PNG")

            # Image to video
            cmd = [
                ffmpeg, "-y", "-loop", "1", "-i", str(png_path),
                "-c:v", "libx264", "-t", str(duration),
                "-pix_fmt", "yuv420p", "-r", str(FPS),
                "-vf", f"scale={W}:{H}",
                str(mp4_path),
            ]
            subprocess.run(cmd, capture_output=True)
            segments.append(mp4_path)
            print(f"  [{i+1}/{len(slides)}] {name} ({duration}s)")

        # Concat
        filelist = tmp / "filelist.txt"
        with open(filelist, "w") as f:
            for seg in segments:
                f.write(f"file '{seg}'\n")

        print(f"\nConcatenating {len(segments)} segments...")
        cmd = [
            ffmpeg, "-y", "-f", "concat", "-safe", "0",
            "-i", str(filelist),
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR: {result.stderr[-300:]}")
            sys.exit(1)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\nDone! {output_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
