"""
build_demo_v3.py — Professional demo video: real Web UI screencast + Isaac Sim footage.

Combines:
  - Playwright screencast of the live web application (real clicks, navigation)
  - Real Isaac Sim episode videos (mug pick-and-place, multi-camera)
  - Title cards (Pillow)
  - Telemetry visualization slides (matplotlib)
  - Bottom-bar overlays + time-lapse via ffmpeg

Usage:
    python scripts/build_demo_v3.py [--output demo_output/robolab_demo_v3.mp4]
                                    [--data-root C:/RoboLab_Data]
                                    [--base-url http://localhost:3000]
                                    [--episode-id <uuid>]

Prerequisites:
    pip install playwright Pillow matplotlib
    playwright install chromium
    ffmpeg on PATH (or set FFMPEG_BIN env var)
    Dev server running on localhost:3000
"""

from __future__ import annotations
import os, sys, subprocess, argparse, shutil, tempfile, json, asyncio
from pathlib import Path

# ---------------------------------------------------------------------------
# Video settings
# ---------------------------------------------------------------------------
WIDTH, HEIGHT = 1920, 1080
TITLE_DURATION = 3.5
SLIDE_DURATION = 6
OVERLAY_HEIGHT = 64
OVERLAY_OPACITY = 0.7
FPS = 30
DARK_BG = (18, 18, 28)
ACCENT_BLUE = (59, 130, 246)
ACCENT_GREEN = (34, 197, 94)
WHITE = (255, 255, 255)
GRAY = (160, 165, 180)

# Mug episode timing (from build_demo_v2.py)
MUG_T1_END = 10.8
MUG_T2_END = 57.9
MUG_T4_END = 88.6
MUG_T5_END = 93.6


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
    print("ERROR: ffmpeg not found. Install via: winget install Gyan.FFmpeg")
    sys.exit(1)


# ---------------------------------------------------------------------------
# ffmpeg helpers (from build_demo_v2.py)
# ---------------------------------------------------------------------------

def run_ffmpeg(ffmpeg: str, args: list[str], desc: str = "", cwd: str | None = None):
    cmd = [ffmpeg] + args
    if desc:
        print(f"  ffmpeg: {desc}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[-800:]}")
        sys.exit(1)


def image_to_video(ffmpeg: str, image_path: str, output_path: str, duration: float):
    run_ffmpeg(ffmpeg, [
        "-y", "-loop", "1", "-i", image_path,
        "-c:v", "libx264", "-t", str(duration),
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-vf", f"scale={WIDTH}:{HEIGHT}",
        output_path,
    ], f"image -> {duration}s video")


def trim_and_speed(ffmpeg: str, input_path: str, output_path: str,
                   ss: float, t: float, speed: float = 1.0):
    setpts = f"setpts=PTS/{speed}" if speed != 1.0 else "setpts=PTS"
    vf = (f"{setpts},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
          f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black")
    run_ffmpeg(ffmpeg, [
        "-y", "-ss", str(ss), "-t", str(t), "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-an", "-pix_fmt", "yuv420p", "-r", str(FPS),
        output_path,
    ], f"trim {ss:.1f}+{t:.1f}s @{speed}x -> {Path(output_path).name}")


def _ensure_overlay_font(tmp_dir: Path) -> Path:
    dst = tmp_dir / "overlay_font.ttf"
    if dst.exists():
        return dst
    for src in ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]:
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            return dst
    return dst


def add_overlay(ffmpeg: str, input_path: str, output_path: str, text: str,
                tmp_dir: Path | None = None):
    work = tmp_dir or Path(tempfile.gettempdir())
    font = _ensure_overlay_font(work)
    bar_y = HEIGHT - OVERLAY_HEIGHT
    text_y = bar_y + (OVERLAY_HEIGHT - 24) // 2
    txt_file = work / f"ov_{Path(output_path).stem}.txt"
    txt_file.write_text(text, encoding="utf-8")
    font_rel = font.name
    txt_rel = txt_file.name
    vf = (
        f"drawbox=x=0:y={bar_y}:w={WIDTH}:h={OVERLAY_HEIGHT}"
        f":color=black@{OVERLAY_OPACITY}:t=fill,"
        f"drawtext=fontfile={font_rel}"
        f":textfile={txt_rel}"
        f":fontcolor=white:fontsize=24"
        f":x=(w-text_w)/2:y={text_y}"
    )
    run_ffmpeg(ffmpeg, [
        "-y", "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-c:a", "copy", "-pix_fmt", "yuv420p",
        output_path,
    ], f"overlay -> {Path(output_path).name}", cwd=str(work))


def normalize_clip(ffmpeg: str, input_path: str, output_path: str):
    run_ffmpeg(ffmpeg, [
        "-y", "-i", input_path,
        "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
               f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-an", "-pix_fmt", "yuv420p", "-r", str(FPS),
        output_path,
    ], f"normalize -> {Path(output_path).name}")


def concat_videos(ffmpeg: str, file_list_path: str, output_path: str):
    run_ffmpeg(ffmpeg, [
        "-y", "-f", "concat", "-safe", "0",
        "-i", file_list_path,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        output_path,
    ], f"concat -> {Path(output_path).name}")


def trim_video(ffmpeg: str, input_path: str, output_path: str, ss: float, t: float):
    """Simple trim without speed change."""
    run_ffmpeg(ffmpeg, [
        "-y", "-ss", str(ss), "-t", str(t), "-i", input_path,
        "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
               f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-an", "-pix_fmt", "yuv420p", "-r", str(FPS),
        output_path,
    ], f"trim {ss:.1f}+{t:.1f}s -> {Path(output_path).name}")


# ---------------------------------------------------------------------------
# Pillow: Title cards
# ---------------------------------------------------------------------------

def _load_fonts():
    from PIL import ImageFont
    fonts = {}
    for name, path, size in [
        ("title", "C:/Windows/Fonts/segoeui.ttf", 72),
        ("subtitle", "C:/Windows/Fonts/segoeuil.ttf", 32),
        ("heading", "C:/Windows/Fonts/segoeuib.ttf", 40),
        ("body", "C:/Windows/Fonts/segoeui.ttf", 28),
        ("small", "C:/Windows/Fonts/segoeui.ttf", 22),
        ("mono", "C:/Windows/Fonts/consola.ttf", 22),
    ]:
        try:
            fonts[name] = ImageFont.truetype(path, size)
        except (IOError, OSError):
            try:
                fonts[name] = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)
            except (IOError, OSError):
                fonts[name] = ImageFont.load_default()
    return fonts


def make_title_card(title: str, subtitle: str, output: str):
    from PIL import Image, ImageDraw
    fonts = _load_fonts()
    img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
    draw = ImageDraw.Draw(img)
    ay = HEIGHT // 2 - 65
    aw = 120
    draw.rectangle([(WIDTH//2 - aw//2, ay), (WIDTH//2 + aw//2, ay + 4)], fill=ACCENT_BLUE)
    bb = draw.textbbox((0, 0), title, font=fonts["title"])
    tw = bb[2] - bb[0]
    draw.text(((WIDTH - tw) // 2, HEIGHT // 2 - 40), title, fill=WHITE, font=fonts["title"])
    bb = draw.textbbox((0, 0), subtitle, font=fonts["subtitle"])
    sw = bb[2] - bb[0]
    draw.text(((WIDTH - sw) // 2, HEIGHT // 2 + 55), subtitle, fill=GRAY, font=fonts["subtitle"])
    img.save(output)
    print(f"  Title card: {output}")


# ---------------------------------------------------------------------------
# matplotlib: Telemetry slides (from build_demo_v2.py)
# ---------------------------------------------------------------------------

def make_trajectory_slide(telemetry_path: str, output: str):
    from PIL import Image, ImageDraw
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fonts = _load_fonts()
    with open(telemetry_path) as f:
        data = json.load(f)

    traj = data.get("trajectory", [])
    if not traj:
        img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
        img.save(output)
        return

    xs = [p["robot_position"]["x"] for p in traj]
    ys = [p["robot_position"]["y"] for p in traj]

    fig, ax = plt.subplots(figsize=(8, 6), facecolor="#12121c")
    ax.set_facecolor("#1a1a2e")
    ax.plot(xs, ys, color="#3b82f6", linewidth=2.5, alpha=0.9)
    ax.scatter(xs[0], ys[0], color="#22c55e", s=120, zorder=5, label="Start")
    ax.scatter(xs[-1], ys[-1], color="#ef4444", s=120, zorder=5, marker="s", label="End")
    ax.set_xlabel("X (m)", color="white", fontsize=14)
    ax.set_ylabel("Y (m)", color="white", fontsize=14)
    ax.set_title("Robot Base Trajectory", color="white", fontsize=18, pad=15)
    ax.tick_params(colors="gray")
    ax.legend(fontsize=12, facecolor="#1a1a2e", edgecolor="gray", labelcolor="white")
    ax.grid(True, alpha=0.15)
    for spine in ax.spines.values():
        spine.set_color("gray")

    plot_path = output.replace(".png", "_plot.png")
    fig.savefig(plot_path, dpi=150, bbox_inches="tight", facecolor="#12121c")
    plt.close(fig)

    img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
    draw = ImageDraw.Draw(img)
    plot_img = Image.open(plot_path)
    plot_img = plot_img.resize((900, 680))
    img.paste(plot_img, (60, 200))

    x_start, y_top = 1020, 200
    draw.text((x_start, y_top), "Trajectory Stats", fill=WHITE, font=fonts["heading"])
    stats = [
        f"Points: {len(traj)}",
        f"X range: [{min(xs):.2f}, {max(xs):.2f}] m",
        f"Y range: [{min(ys):.2f}, {max(ys):.2f}] m",
        f"Duration: {data.get('episode_duration', '?')}s",
        "", "Coordinate frame: map", "Source: telemetry.json",
        "", "Sensors recorded:", "  RGB camera", "  Depth (distance_to_camera)",
        "  Point Cloud (LiDAR)", "  Semantic Segmentation",
    ]
    for i, line in enumerate(stats):
        color = ACCENT_GREEN if "Points" in line else GRAY
        if line.startswith("  "):
            color = ACCENT_BLUE
        draw.text((x_start, y_top + 60 + i * 36), line, fill=color, font=fonts["body"])

    draw.text((60, 80), "Robot Telemetry — Base Position Over Time",
              fill=WHITE, font=fonts["heading"])
    draw.rectangle([(60, 140), (180, 144)], fill=ACCENT_BLUE)
    img.save(output)
    os.remove(plot_path)
    print(f"  Trajectory slide: {output}")


def make_joints_slide(physics_log_path: str, output: str):
    from PIL import Image, ImageDraw
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fonts = _load_fonts()
    with open(physics_log_path) as f:
        data = json.load(f)

    frames = data.get("frames", [])
    if not frames:
        img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
        img.save(output)
        return

    ts = [f["sim_time"] for f in frames]
    joint_names = ["torso_lift_joint", "arm_right_1_joint", "arm_right_2_joint",
                   "arm_right_3_joint", "arm_right_4_joint"]
    joint_data = {name: [] for name in joint_names}
    for frame in frames:
        joints = frame.get("joints", {})
        for name in joint_names:
            j = joints.get(name, {})
            joint_data[name].append(j.get("position_rad", 0.0))

    fig, axes = plt.subplots(len(joint_names), 1, figsize=(10, 7),
                             facecolor="#12121c", sharex=True)
    colors = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7"]
    for i, (name, vals) in enumerate(joint_data.items()):
        ax = axes[i]
        ax.set_facecolor("#1a1a2e")
        ax.plot(ts, vals, color=colors[i], linewidth=1.5)
        short_name = name.replace("_joint", "").replace("arm_right_", "R")
        ax.set_ylabel(short_name, color="white", fontsize=9, rotation=0, labelpad=50)
        ax.tick_params(colors="gray", labelsize=8)
        ax.grid(True, alpha=0.1)
        for spine in ax.spines.values():
            spine.set_color("#333")
    axes[-1].set_xlabel("Time (s)", color="white", fontsize=11)
    fig.suptitle("Joint Positions During Mug Pick-and-Place", color="white", fontsize=14, y=0.98)
    fig.tight_layout(rect=[0.08, 0.02, 1, 0.95])

    plot_path = output.replace(".png", "_plot.png")
    fig.savefig(plot_path, dpi=150, facecolor="#12121c")
    plt.close(fig)

    img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
    draw = ImageDraw.Draw(img)
    plot_img = Image.open(plot_path)
    pw, ph = plot_img.size
    scale = min(1600 / pw, 850 / ph)
    plot_img = plot_img.resize((int(pw * scale), int(ph * scale)))
    px = (WIDTH - plot_img.width) // 2
    img.paste(plot_img, (px, 180))
    draw.text((60, 60), "Joint State Telemetry — Arm & Torso Positions",
              fill=WHITE, font=fonts["heading"])
    draw.rectangle([(60, 120), (180, 124)], fill=ACCENT_BLUE)
    draw.text((60, HEIGHT - 80),
              "5 DOF shown  |  Source: physics_log.json  |  Suitable for imitation learning policies",
              fill=GRAY, font=fonts["small"])
    img.save(output)
    os.remove(plot_path)
    print(f"  Joints slide: {output}")


def make_sensors_slide(output: str):
    from PIL import Image, ImageDraw
    fonts = _load_fonts()
    img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
    draw = ImageDraw.Draw(img)

    draw.text((60, 60), "Data Collection — Sensor Modalities & Training Suitability",
              fill=WHITE, font=fonts["heading"])
    draw.rectangle([(60, 120), (180, 124)], fill=ACCENT_BLUE)

    sensors = [
        ("RGB Camera", "1920x1080 @ 10Hz", "Head-mounted + external views",
         "Visual observation for policy input"),
        ("Depth Map", "distance_to_camera", "Per-pixel depth in meters",
         "3D perception, obstacle avoidance"),
        ("Point Cloud", "LiDAR-style 3D points", "Scene geometry reconstruction",
         "Spatial reasoning, grasp planning"),
        ("Semantic Seg.", "Per-pixel class labels", "Object & surface identification",
         "Scene understanding, affordance detection"),
    ]
    card_w, card_h, margin = 420, 200, 30
    start_x = (WIDTH - 2 * card_w - margin) // 2
    start_y = 180

    for i, (name, fmt, desc, use) in enumerate(sensors):
        col, row = i % 2, i // 2
        x = start_x + col * (card_w + margin)
        y = start_y + row * (card_h + margin)
        draw.rounded_rectangle([(x, y), (x + card_w, y + card_h)], radius=12, fill=(25, 30, 45))
        draw.text((x + 20, y + 15), name, fill=ACCENT_BLUE, font=fonts["heading"])
        draw.text((x + 20, y + 65), fmt, fill=WHITE, font=fonts["body"])
        draw.text((x + 20, y + 100), desc, fill=GRAY, font=fonts["small"])
        draw.text((x + 20, y + 135), f"Use: {use}", fill=ACCENT_GREEN, font=fonts["small"])

    by = start_y + 2 * (card_h + margin) + 40
    draw.rounded_rectangle([(60, by), (WIDTH - 60, by + 180)], radius=12, fill=(25, 30, 45))
    draw.text((100, by + 20), "Training Pipeline Compatibility", fill=WHITE, font=fonts["heading"])
    items = [
        "Behavior Cloning: observation (RGB/depth) + joint states -> action prediction",
        "Diffusion Policy: multi-modal observation input with temporal context",
        "ACT (Action Chunking with Transformers): joint trajectory chunks from demonstrations",
        "Data format: JSON frames + PNG images, easily convertible to HDF5/TFRecord",
    ]
    for i, item in enumerate(items):
        color = ACCENT_GREEN if i < 3 else GRAY
        draw.text((120, by + 70 + i * 28), f"  {item}", fill=color, font=fonts["small"])
    img.save(output)
    print(f"  Sensors slide: {output}")


# ---------------------------------------------------------------------------
# Playwright: Web UI screencast
# ---------------------------------------------------------------------------

async def record_web_ui(output_dir: Path, base_url: str, episode_id: str) -> Path:
    """Record Web UI navigation as a single video file."""
    from playwright.async_api import async_playwright

    print("\n=== Recording Web UI screencast ===")
    vid_dir = output_dir / "playwright_video"
    vid_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            record_video_dir=str(vid_dir),
            record_video_size={"width": WIDTH, "height": HEIGHT},
        )
        page = await context.new_page()

        WAIT = "load"  # "networkidle" hangs with Next.js HMR WebSocket
        NAV_TIMEOUT = 60000

        async def safe_goto(url: str):
            await page.goto(url, wait_until=WAIT, timeout=NAV_TIMEOUT)
            await page.wait_for_timeout(1500)  # let JS hydrate

        async def safe_click(selector: str, timeout: int = 5000):
            try:
                await page.click(selector, timeout=timeout)
                return True
            except Exception:
                print(f"    (click failed: {selector})")
                return False

        # ---- Seg 2: Dashboard -> Scenes -> Launch Profiles ----
        print("  Recording: Dashboard -> Scenes -> Profiles")
        await safe_goto(f"{base_url}/")
        await page.wait_for_timeout(3500)

        await safe_click('nav >> a:has-text("Scenes")')
        await page.wait_for_timeout(3500)

        await safe_click('nav >> a:has-text("Launch Profiles")')
        await page.wait_for_timeout(3000)

        if await safe_click('button:has-text("Add Profile")'):
            await page.wait_for_timeout(3500)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(800)
        else:
            await page.wait_for_timeout(2000)

        # ---- Seg 3: Episode Wizard ----
        print("  Recording: Episode Wizard (5 steps)")
        await safe_goto(f"{base_url}/episodes/new")
        await page.wait_for_timeout(2500)

        for step_num in range(4):
            if not await safe_click('button:has-text("Next")'):
                print(f"    (Next button not found at step {step_num + 1})")
                break
            await page.wait_for_timeout(2800)
        await page.wait_for_timeout(4000)

        # ---- Seg 7: Episode Detail (Teleop UI) ----
        print(f"  Recording: Episode Detail ({episode_id[:12]}...)")
        await safe_goto(f"{base_url}/episodes/{episode_id}")
        await page.wait_for_timeout(3000)

        for _ in range(8):
            await page.evaluate("window.scrollBy(0, 80)")
            await page.wait_for_timeout(200)
        await page.wait_for_timeout(3000)

        for _ in range(6):
            await page.evaluate("window.scrollBy(0, 80)")
            await page.wait_for_timeout(200)
        await page.wait_for_timeout(3000)

        # ---- Seg 8: Batch Queue + Experiments ----
        print("  Recording: Batch Queue + Experiments")
        await safe_goto(f"{base_url}/batches")
        await page.wait_for_timeout(2500)

        if await safe_click('button:has-text("New Batch")'):
            await page.wait_for_timeout(3500)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(800)
        else:
            await page.wait_for_timeout(2000)

        await safe_goto(f"{base_url}/experiments")
        await page.wait_for_timeout(3500)

        if await safe_click('button:has-text("New Task Config")'):
            await page.wait_for_timeout(3500)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(800)
        else:
            await page.wait_for_timeout(2000)

        # ---- Seg 9: Recordings ----
        print("  Recording: Recordings")
        await safe_goto(f"{base_url}/recordings")
        await page.wait_for_timeout(3500)

        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 60)")
            await page.wait_for_timeout(200)
        await page.wait_for_timeout(3000)

        # Done - close to finalize video
        await context.close()
        await browser.close()

    # Find the recorded video
    videos = list(vid_dir.glob("*.webm"))
    if not videos:
        print("ERROR: No video recorded by Playwright")
        sys.exit(1)
    video_path = videos[0]
    print(f"  Screencast saved: {video_path} ({video_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return video_path


# ---------------------------------------------------------------------------
# Screencast timing map (cumulative seconds from video start)
# Used to trim the single Playwright video into segments
# ---------------------------------------------------------------------------

# These are approximate — adjusted to match the wait_for_timeout calls above
SCREENCAST_SEGMENTS = {
    "seg2_overview": {"start": 0, "duration": 18},      # Dashboard + Scenes + Profiles + dialog
    "seg3_wizard":   {"start": 18, "duration": 20},      # Episode wizard 5 steps
    "seg7_teleop":   {"start": 38, "duration": 14},      # Episode detail + scroll
    "seg8_batch_exp":{"start": 52, "duration": 16},      # Batch Queue + Experiments
    "seg9_recordings":{"start": 68, "duration": 10},     # Recordings
}


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build RoboLab demo v3 (screencast + Isaac Sim)")
    parser.add_argument("--output", default="demo_output/robolab_demo_v3.mp4")
    parser.add_argument("--data-root", default="C:/RoboLab_Data")
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument("--episode-id", default=None,
                        help="Episode UUID for teleop demo (auto-detected if omitted)")
    parser.add_argument("--skip-record", action="store_true",
                        help="Skip Playwright recording (reuse existing screencast)")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    mug_ep = data_root / "episodes/fixed_mug_rearrange_20260401_221631/heavy"
    kitchen_scene = data_root / "episodes/scene_robot_videos/Kitchen_TiagoCompatible_20260401_210912"
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = find_ffmpeg()
    print(f"ffmpeg: {ffmpeg}")

    # Check deps
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("ERROR: pip install Pillow"); sys.exit(1)
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("ERROR: pip install matplotlib"); sys.exit(1)

    # Auto-detect episode ID
    episode_id = args.episode_id
    if not episode_id:
        try:
            import urllib.request
            resp = urllib.request.urlopen(f"{args.base_url}/api/episodes")
            episodes = json.loads(resp.read())
            completed = [e for e in episodes if e.get("status") == "completed"]
            if completed:
                episode_id = completed[0]["id"]
                print(f"Auto-detected episode: {episode_id[:12]}...")
            else:
                episode_id = episodes[0]["id"] if episodes else "unknown"
        except Exception as e:
            print(f"WARNING: Could not auto-detect episode: {e}")
            episode_id = "unknown"

    # Verify Isaac Sim source videos
    mug_videos = {
        "external": mug_ep / "external_robot.mp4",
        "isometric": mug_ep / "isometric_kitchen.mp4",
        "front": mug_ep / "front_kitchen.mp4",
        "top": mug_ep / "top_kitchen.mp4",
    }
    for name, path in mug_videos.items():
        if not path.is_file():
            print(f"WARNING: Missing {name} video: {path}")

    print(f"\nStarting demo video build...")

    with tempfile.TemporaryDirectory(prefix="robolab_v3_") as tmp:
        tmp = Path(tmp)
        segments = []

        # ==============================================================
        # STEP 1: Record Web UI screencast (or reuse existing)
        # ==============================================================
        screencast_path = output_path.parent / "screencast_raw.webm"
        if args.skip_record and screencast_path.exists():
            print(f"\nReusing existing screencast: {screencast_path}")
        else:
            recorded = asyncio.run(record_web_ui(tmp, args.base_url, episode_id))
            shutil.copy2(recorded, screencast_path)
            print(f"Screencast copied to: {screencast_path}")

        # Normalize screencast to 1920x1080 mp4
        screencast_mp4 = tmp / "screencast.mp4"
        normalize_clip(ffmpeg, str(screencast_path), str(screencast_mp4))

        # ==============================================================
        # SEG 1: Opening title (3.5s)
        # ==============================================================
        print("\n=== Seg 1: Opening title ===")
        title_png = tmp / "title_open.png"
        make_title_card(
            "RoboLab Console",
            "Data Collection Platform for Robotic Manipulation",
            str(title_png),
        )
        title_mp4 = tmp / "seg01_title.mp4"
        image_to_video(ffmpeg, str(title_png), str(title_mp4), TITLE_DURATION)
        segments.append(title_mp4)

        # ==============================================================
        # SEG 2: Dashboard -> Scenes -> Profiles (from screencast)
        # ==============================================================
        print("\n=== Seg 2: Dashboard -> Scenes -> Profiles ===")
        seg2_raw = tmp / "seg02_raw.mp4"
        s = SCREENCAST_SEGMENTS["seg2_overview"]
        trim_video(ffmpeg, str(screencast_mp4), str(seg2_raw), s["start"], s["duration"])
        seg2_ov = tmp / "seg02_overview.mp4"
        add_overlay(ffmpeg, str(seg2_raw), str(seg2_ov),
                    "Web Console: Dashboard > Scenes > Launch Profiles", tmp_dir=tmp)
        segments.append(seg2_ov)

        # ==============================================================
        # SEG 3: Episode Wizard (from screencast)
        # ==============================================================
        print("\n=== Seg 3: Episode Wizard ===")
        seg3_raw = tmp / "seg03_raw.mp4"
        s = SCREENCAST_SEGMENTS["seg3_wizard"]
        trim_video(ffmpeg, str(screencast_mp4), str(seg3_raw), s["start"], s["duration"])
        seg3_ov = tmp / "seg03_wizard.mp4"
        add_overlay(ffmpeg, str(seg3_raw), str(seg3_ov),
                    "5-step Episode Wizard: scene, profile, sensors, randomization, review",
                    tmp_dir=tmp)
        segments.append(seg3_ov)

        # ==============================================================
        # SEG 4: Section title — Isaac Sim (2.5s)
        # ==============================================================
        print("\n=== Seg 4: Isaac Sim section title ===")
        isaac_title_png = tmp / "title_isaac.png"
        make_title_card(
            "Isaac Sim Episode",
            "Autonomous Mug Pick-and-Place (5 tasks)",
            str(isaac_title_png),
        )
        isaac_title_mp4 = tmp / "seg04_title.mp4"
        image_to_video(ffmpeg, str(isaac_title_png), str(isaac_title_mp4), 2.5)
        segments.append(isaac_title_mp4)

        # ==============================================================
        # SEG 5: Mug pick-and-place multi-camera edit (~35s)
        # ==============================================================
        print("\n=== Seg 5: Mug pick-and-place (multi-camera) ===")
        if all(p.is_file() for p in mug_videos.values()):
            # 5a: Isometric — navigate to mug (3x)
            seg = tmp / "mug_5a.mp4"
            trim_and_speed(ffmpeg, str(mug_videos["isometric"]), str(seg),
                           ss=0, t=MUG_T1_END, speed=3.0)
            seg_ov = tmp / "mug_5a_ov.mp4"
            add_overlay(ffmpeg, str(seg), str(seg_ov),
                        "T1 Navigate to mug (3x) — Isometric view", tmp_dir=tmp)
            segments.append(seg_ov)

            # 5b: Front — arm extension (1x)
            seg = tmp / "mug_5b.mp4"
            trim_and_speed(ffmpeg, str(mug_videos["front"]), str(seg),
                           ss=MUG_T1_END, t=14, speed=1.0)
            seg_ov = tmp / "mug_5b_ov.mp4"
            add_overlay(ffmpeg, str(seg), str(seg_ov),
                        "T2 Arm extension toward mug — Front view", tmp_dir=tmp)
            segments.append(seg_ov)

            # 5c: External — close-up grasp (1.5x)
            seg = tmp / "mug_5c.mp4"
            trim_and_speed(ffmpeg, str(mug_videos["external"]), str(seg),
                           ss=MUG_T1_END + 14, t=25, speed=1.5)
            seg_ov = tmp / "mug_5c_ov.mp4"
            add_overlay(ffmpeg, str(seg), str(seg_ov),
                        "T2 Grasp mug close-up (1.5x) — External robot view", tmp_dir=tmp)
            segments.append(seg_ov)

            # 5d: Isometric — carry + place (2x)
            seg = tmp / "mug_5d.mp4"
            trim_and_speed(ffmpeg, str(mug_videos["isometric"]), str(seg),
                           ss=MUG_T1_END + 14 + 25, t=20, speed=2.0)
            seg_ov = tmp / "mug_5d_ov.mp4"
            add_overlay(ffmpeg, str(seg), str(seg_ov),
                        "T3-T4 Carry and place mug (2x) — Isometric view", tmp_dir=tmp)
            segments.append(seg_ov)

            # 5e: External — place down (1.5x)
            seg = tmp / "mug_5e.mp4"
            place_start = MUG_T1_END + 14 + 25 + 20
            place_dur = max(MUG_T4_END - place_start, 3)
            trim_and_speed(ffmpeg, str(mug_videos["external"]), str(seg),
                           ss=place_start, t=place_dur, speed=1.5)
            seg_ov = tmp / "mug_5e_ov.mp4"
            add_overlay(ffmpeg, str(seg), str(seg_ov),
                        "T4 Place mug down (1.5x) — External robot view", tmp_dir=tmp)
            segments.append(seg_ov)

            # 5f: Top — return (2x)
            seg = tmp / "mug_5f.mp4"
            trim_and_speed(ffmpeg, str(mug_videos["top"]), str(seg),
                           ss=MUG_T4_END, t=MUG_T5_END - MUG_T4_END, speed=2.0)
            seg_ov = tmp / "mug_5f_ov.mp4"
            add_overlay(ffmpeg, str(seg), str(seg_ov),
                        "T5 Return to start (2x) — Top view", tmp_dir=tmp)
            segments.append(seg_ov)
        else:
            print("  WARNING: Isaac Sim videos not found, skipping mug task segment")

        # ==============================================================
        # SEG 6: Section title — Teleoperation (2.5s)
        # ==============================================================
        print("\n=== Seg 6: Teleoperation section title ===")
        teleop_title_png = tmp / "title_teleop.png"
        make_title_card("Teleoperation",
                        "Web UI controls + Isaac Sim live stream",
                        str(teleop_title_png))
        teleop_title_mp4 = tmp / "seg06_title.mp4"
        image_to_video(ffmpeg, str(teleop_title_png), str(teleop_title_mp4), 2.5)
        segments.append(teleop_title_mp4)

        # ==============================================================
        # SEG 7: Teleop UI (from screencast)
        # ==============================================================
        print("\n=== Seg 7: Teleop UI ===")
        seg7_raw = tmp / "seg07_raw.mp4"
        s = SCREENCAST_SEGMENTS["seg7_teleop"]
        trim_video(ffmpeg, str(screencast_mp4), str(seg7_raw), s["start"], s["duration"])
        seg7_ov = tmp / "seg07_teleop.mp4"
        add_overlay(ffmpeg, str(seg7_raw), str(seg7_ov),
                    "Episode Control: teleop, arm macros, gripper, live stream, data validation",
                    tmp_dir=tmp)
        segments.append(seg7_ov)

        # ==============================================================
        # SEG 8: Batch Queue + Experiments (from screencast)
        # ==============================================================
        print("\n=== Seg 8: Batch Queue + Experiments ===")
        seg8_raw = tmp / "seg08_raw.mp4"
        s = SCREENCAST_SEGMENTS["seg8_batch_exp"]
        trim_video(ffmpeg, str(screencast_mp4), str(seg8_raw), s["start"], s["duration"])
        seg8_ov = tmp / "seg08_batch_exp.mp4"
        add_overlay(ffmpeg, str(seg8_raw), str(seg8_ov),
                    "Batch collection + visual task builder for automated experiments",
                    tmp_dir=tmp)
        segments.append(seg8_ov)

        # ==============================================================
        # SEG 9: Recordings (from screencast)
        # ==============================================================
        print("\n=== Seg 9: Recordings ===")
        seg9_raw = tmp / "seg09_raw.mp4"
        s = SCREENCAST_SEGMENTS["seg9_recordings"]
        trim_video(ffmpeg, str(screencast_mp4), str(seg9_raw), s["start"], s["duration"])
        seg9_ov = tmp / "seg09_recordings.mp4"
        add_overlay(ffmpeg, str(seg9_raw), str(seg9_ov),
                    "Recordings library: video, telemetry, datasets — searchable & downloadable",
                    tmp_dir=tmp)
        segments.append(seg9_ov)

        # ==============================================================
        # SEG 10: Section title — Data (2.5s)
        # ==============================================================
        print("\n=== Seg 10: Data section title ===")
        data_title_png = tmp / "title_data.png"
        make_title_card("Collected Data",
                        "Telemetry, joint states, and training-ready datasets",
                        str(data_title_png))
        data_title_mp4 = tmp / "seg10_title.mp4"
        image_to_video(ffmpeg, str(data_title_png), str(data_title_mp4), 2.5)
        segments.append(data_title_mp4)

        # ==============================================================
        # SEG 11: Data visualization slides (18s)
        # ==============================================================
        print("\n=== Seg 11: Data visualization ===")

        # 11a: Trajectory
        telem_json = kitchen_scene / "telemetry.json"
        if telem_json.is_file():
            traj_png = tmp / "trajectory.png"
            make_trajectory_slide(str(telem_json), str(traj_png))
            traj_mp4 = tmp / "seg11a_trajectory.mp4"
            image_to_video(ffmpeg, str(traj_png), str(traj_mp4), SLIDE_DURATION)
            traj_ov = tmp / "seg11a_ov.mp4"
            add_overlay(ffmpeg, str(traj_mp4), str(traj_ov),
                        "Robot base trajectory recorded during episode", tmp_dir=tmp)
            segments.append(traj_ov)

        # 11b: Joint states
        physics_json = mug_ep / "physics_log.json"
        if physics_json.is_file():
            joints_png = tmp / "joints.png"
            make_joints_slide(str(physics_json), str(joints_png))
            joints_mp4 = tmp / "seg11b_joints.mp4"
            image_to_video(ffmpeg, str(joints_png), str(joints_mp4), SLIDE_DURATION)
            joints_ov = tmp / "seg11b_ov.mp4"
            add_overlay(ffmpeg, str(joints_mp4), str(joints_ov),
                        "Joint state telemetry — arm and torso positions over time", tmp_dir=tmp)
            segments.append(joints_ov)

        # 11c: Sensors
        sensors_png = tmp / "sensors.png"
        make_sensors_slide(str(sensors_png))
        sensors_mp4 = tmp / "seg11c_sensors.mp4"
        image_to_video(ffmpeg, str(sensors_png), str(sensors_mp4), SLIDE_DURATION)
        sensors_ov = tmp / "seg11c_ov.mp4"
        add_overlay(ffmpeg, str(sensors_mp4), str(sensors_ov),
                    "Multi-modal sensor data for behavior cloning and diffusion policies",
                    tmp_dir=tmp)
        segments.append(sensors_ov)

        # ==============================================================
        # SEG 12: Closing title (3.5s)
        # ==============================================================
        print("\n=== Seg 12: Closing title ===")
        final_png = tmp / "title_final.png"
        make_title_card("RoboLab Console", "github.com/tmhwk77/robolab", str(final_png))
        final_mp4 = tmp / "seg12_final.mp4"
        image_to_video(ffmpeg, str(final_png), str(final_mp4), TITLE_DURATION)
        segments.append(final_mp4)

        # ==============================================================
        # CONCAT all segments
        # ==============================================================
        print(f"\n=== Concatenating {len(segments)} segments ===")
        filelist = tmp / "filelist.txt"
        with open(filelist, "w") as f:
            for seg in segments:
                f.write(f"file '{seg}'\n")

        concat_videos(ffmpeg, str(filelist), str(output_path))

    print(f"\nDone! Output: {output_path}")
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Size: {size_mb:.1f} MB")
    print(f"Segments: {len(segments)}")


if __name__ == "__main__":
    main()
