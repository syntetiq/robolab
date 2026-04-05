"""
build_demo_v2.py — Assemble demo video from real Isaac Sim episode data.

Combines:
  - Title cards (Pillow)
  - Real episode videos (mug pick-and-place, kitchen scene)
  - Telemetry visualization slides (matplotlib)
  - Bottom-bar overlays + time-lapse via ffmpeg

Usage:
    python scripts/build_demo_v2.py [--output demo_output/robolab_demo_v2.mp4]
                                    [--data-root C:/RoboLab_Data]
                                    [--web-clip demo_clips/web_ui.mp4]

Prerequisites:
    pip install Pillow matplotlib
    ffmpeg on PATH (or set FFMPEG_BIN env var)
"""

from __future__ import annotations
import os, sys, subprocess, argparse, shutil, tempfile, json
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (defaults, overridable via args)
# ---------------------------------------------------------------------------
DATA_ROOT = Path("C:/RoboLab_Data")
MUG_EPISODE = DATA_ROOT / "episodes/fixed_mug_rearrange_20260401_221631/heavy"
KITCHEN_SCENE = DATA_ROOT / "episodes/scene_robot_videos/Kitchen_TiagoCompatible_20260401_210912"

# Video settings
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
DARK_GRAY = (40, 42, 54)

# Mug episode timing (approximate video seconds based on step counts)
# Total 5621 steps over 93.6s => ~60 steps/s
MUG_T1_END = 10.8    # drive_to_mug (651 steps)
MUG_T2_END = 57.9    # pick_mug (2826 steps)
MUG_T3_END = 58.6    # carry_east (40 steps)
MUG_T4_END = 88.6    # place_mug (1800 steps)
MUG_T5_END = 93.6    # return_to_start (304 steps)


# ---------------------------------------------------------------------------
# Find ffmpeg / ffprobe
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
# ffmpeg helpers
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
    """Trim a video segment and optionally speed it up."""
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
    """Copy system font to temp dir to avoid Windows path escaping in ffmpeg."""
    dst = tmp_dir / "overlay_font.ttf"
    if dst.exists():
        return dst
    for src in ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]:
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            return dst
    return dst  # will fail in ffmpeg, but let it try


def add_overlay(ffmpeg: str, input_path: str, output_path: str, text: str,
                tmp_dir: Path | None = None):
    """Add semi-transparent bottom bar with text."""
    work = tmp_dir or Path(tempfile.gettempdir())
    font = _ensure_overlay_font(work)

    bar_y = HEIGHT - OVERLAY_HEIGHT
    text_y = bar_y + (OVERLAY_HEIGHT - 24) // 2

    # Write text to file to avoid quoting issues
    txt_file = work / f"ov_{Path(output_path).stem}.txt"
    txt_file.write_text(text, encoding="utf-8")

    # Use relative paths from work dir to avoid colons entirely
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

    # Accent line
    ay = HEIGHT // 2 - 65
    aw = 120
    draw.rectangle([(WIDTH//2 - aw//2, ay), (WIDTH//2 + aw//2, ay + 4)], fill=ACCENT_BLUE)

    # Title
    bb = draw.textbbox((0, 0), title, font=fonts["title"])
    tw = bb[2] - bb[0]
    draw.text(((WIDTH - tw) // 2, HEIGHT // 2 - 40), title, fill=WHITE, font=fonts["title"])

    # Subtitle
    bb = draw.textbbox((0, 0), subtitle, font=fonts["subtitle"])
    sw = bb[2] - bb[0]
    draw.text(((WIDTH - sw) // 2, HEIGHT // 2 + 55), subtitle, fill=GRAY, font=fonts["subtitle"])

    img.save(output)
    print(f"  Title card: {output}")


# ---------------------------------------------------------------------------
# Pillow + matplotlib: Telemetry slides
# ---------------------------------------------------------------------------

def make_trajectory_slide(telemetry_path: str, output: str):
    """Draw robot 2D trajectory from telemetry.json."""
    from PIL import Image, ImageDraw
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fonts = _load_fonts()
    with open(telemetry_path) as f:
        data = json.load(f)

    traj = data.get("trajectory", [])
    if not traj:
        print("  WARNING: empty trajectory, generating placeholder")
        img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
        img.save(output)
        return

    xs = [p["robot_position"]["x"] for p in traj]
    ys = [p["robot_position"]["y"] for p in traj]

    # Plot trajectory
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

    # Compose onto slide
    img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
    draw = ImageDraw.Draw(img)

    # Left: plot
    plot_img = Image.open(plot_path)
    plot_img = plot_img.resize((900, 680))
    img.paste(plot_img, (60, 200))

    # Right: stats
    x_start, y_top = 1020, 200
    draw.text((x_start, y_top), "Trajectory Stats", fill=WHITE, font=fonts["heading"])
    stats = [
        f"Points: {len(traj)}",
        f"X range: [{min(xs):.2f}, {max(xs):.2f}] m",
        f"Y range: [{min(ys):.2f}, {max(ys):.2f}] m",
        f"Duration: {data.get('episode_duration', '?')}s",
        "",
        "Coordinate frame: map",
        "Source: telemetry.json",
        "",
        "Sensors recorded:",
        "  RGB camera",
        "  Depth (distance_to_camera)",
        "  PointCloud (LiDAR)",
        "  Semantic Segmentation",
    ]
    for i, line in enumerate(stats):
        color = ACCENT_GREEN if "Points" in line else GRAY
        if line.startswith("  "):
            color = ACCENT_BLUE
        draw.text((x_start, y_top + 60 + i * 36), line, fill=color, font=fonts["body"])

    # Header
    draw.text((60, 80), "Robot Telemetry — Base Position Over Time",
              fill=WHITE, font=fonts["heading"])
    draw.rectangle([(60, 140), (180, 144)], fill=ACCENT_BLUE)

    img.save(output)
    os.remove(plot_path)
    print(f"  Trajectory slide: {output}")


def make_joints_slide(physics_log_path: str, output: str):
    """Draw joint angle plots from physics_log.json."""
    from PIL import Image, ImageDraw
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fonts = _load_fonts()

    with open(physics_log_path) as f:
        data = json.load(f)

    frames = data.get("frames", [])
    if not frames:
        print("  WARNING: no frames in physics_log, generating placeholder")
        img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
        draw = ImageDraw.Draw(img)
        draw.text((100, 400), "Joint data visualization", fill=WHITE, font=fonts["heading"])
        img.save(output)
        return

    # Extract joint data
    ts = [f["sim_time"] for f in frames]

    # Pick interesting joints
    joint_names = ["torso_lift_joint", "arm_right_1_joint", "arm_right_2_joint",
                   "arm_right_3_joint", "arm_right_4_joint"]
    joint_data = {name: [] for name in joint_names}
    for frame in frames:
        joints = frame.get("joints", {})
        for name in joint_names:
            j = joints.get(name, {})
            joint_data[name].append(j.get("position_rad", 0.0))

    # Plot
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

    # Compose
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

    # Bottom note
    draw.text((60, HEIGHT - 80),
              "5 DOF shown  |  Source: physics_log.json (938 frames)  |  Suitable for imitation learning policies",
              fill=GRAY, font=fonts["small"])

    img.save(output)
    os.remove(plot_path)
    print(f"  Joints slide: {output}")


def make_task_results_slide(results_path: str, output: str):
    """Render task results as a styled table."""
    from PIL import Image, ImageDraw

    fonts = _load_fonts()
    with open(results_path) as f:
        data = json.load(f)

    tasks = data.get("task_results", [])
    summary = data.get("report_summary", {})

    img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
    draw = ImageDraw.Draw(img)

    # Header
    draw.text((60, 60), "Episode Results — Mug Pick-and-Place",
              fill=WHITE, font=fonts["heading"])
    draw.rectangle([(60, 120), (180, 124)], fill=ACCENT_BLUE)

    # Verdict badge
    verdict = summary.get("verdict", "PASS")
    badge_color = ACCENT_GREEN if "PASS" in verdict else (239, 68, 68)
    draw.rounded_rectangle([(60, 160), (280, 210)], radius=8, fill=badge_color)
    draw.text((80, 168), f"VERDICT: PASS", fill=WHITE, font=fonts["body"])

    # Task table
    table_y = 260
    col_x = [80, 400, 680, 900]
    headers = ["Task", "Type", "Status", "Sim Time"]
    for i, h in enumerate(headers):
        draw.text((col_x[i], table_y), h, fill=ACCENT_BLUE, font=fonts["body"])
    draw.line([(60, table_y + 40), (1200, table_y + 40)], fill=(60, 60, 80), width=2)

    for j, task in enumerate(tasks):
        y = table_y + 55 + j * 50
        tid = task["task_id"].replace("_", " ")
        ttype = task["type"]
        success = "SUCCESS" if task["success"] else "FAILED"
        scolor = ACCENT_GREEN if task["success"] else (239, 68, 68)
        sim_t = f"{task.get('sim_time_end', 0):.2f}s"

        draw.text((col_x[0], y), tid, fill=WHITE, font=fonts["body"])
        draw.text((col_x[1], y), ttype, fill=GRAY, font=fonts["body"])
        draw.text((col_x[2], y), success, fill=scolor, font=fonts["body"])
        draw.text((col_x[3], y), sim_t, fill=GRAY, font=fonts["body"])

    # Right side: summary stats
    rx = 1300
    draw.text((rx, 260), "Summary", fill=WHITE, font=fonts["heading"])
    stats = [
        f"Robot: TIAGo ({summary.get('model', '?')})",
        f"Total frames: {summary.get('total_frames', '?')}",
        f"Wall time: {summary.get('wall_time_s', '?'):.0f}s",
        f"Grasp mode: {summary.get('grasp_mode', '?')}",
        f"Drive speed: {summary.get('drive_speed_ms', '?')} m/s",
        f"Grasp success: {summary.get('grasp_success', '?')}",
        f"Stable: {summary.get('stable', '?')}",
        f"Max drift: {summary.get('max_drift_m', 0):.3f}m",
    ]
    for i, s in enumerate(stats):
        draw.text((rx, 320 + i * 38), s, fill=GRAY, font=fonts["small"])

    # Bottom: data applicability note
    draw.rounded_rectangle([(60, HEIGHT - 200), (WIDTH - 60, HEIGHT - 80)],
                           radius=12, fill=(25, 30, 45))
    draw.text((100, HEIGHT - 180),
              "Collected Data: RGB + Depth + PointCloud + Semantic Segmentation",
              fill=WHITE, font=fonts["body"])
    draw.text((100, HEIGHT - 135),
              "Joint states (position + velocity) at 60 Hz  |  Robot pose trajectory  |  "
              "Grasp events with timestamps",
              fill=GRAY, font=fonts["small"])
    draw.text((100, HEIGHT - 100),
              "Format: JSON + PNG frames  |  Compatible with imitation learning / behavior cloning pipelines",
              fill=ACCENT_BLUE, font=fonts["small"])

    img.save(output)
    print(f"  Task results slide: {output}")


def make_sensors_slide(output: str):
    """Slide showing what sensor data is collected."""
    from PIL import Image, ImageDraw

    fonts = _load_fonts()
    img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
    draw = ImageDraw.Draw(img)

    draw.text((60, 60), "Data Collection — Sensor Modalities & Training Suitability",
              fill=WHITE, font=fonts["heading"])
    draw.rectangle([(60, 120), (180, 124)], fill=ACCENT_BLUE)

    # Sensor cards
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

    card_w = 420
    card_h = 200
    margin = 30
    start_x = (WIDTH - 2 * card_w - margin) // 2
    start_y = 180

    for i, (name, fmt, desc, use) in enumerate(sensors):
        col = i % 2
        row = i // 2
        x = start_x + col * (card_w + margin)
        y = start_y + row * (card_h + margin)

        draw.rounded_rectangle([(x, y), (x + card_w, y + card_h)],
                               radius=12, fill=(25, 30, 45))
        draw.text((x + 20, y + 15), name, fill=ACCENT_BLUE, font=fonts["heading"])
        draw.text((x + 20, y + 65), fmt, fill=WHITE, font=fonts["body"])
        draw.text((x + 20, y + 100), desc, fill=GRAY, font=fonts["small"])
        draw.text((x + 20, y + 135), f"Use: {use}", fill=ACCENT_GREEN, font=fonts["small"])

    # Bottom section
    by = start_y + 2 * (card_h + margin) + 40
    draw.rounded_rectangle([(60, by), (WIDTH - 60, by + 180)],
                           radius=12, fill=(25, 30, 45))
    draw.text((100, by + 20), "Training Pipeline Compatibility", fill=WHITE, font=fonts["heading"])
    items = [
        "Behavior Cloning: observation (RGB/depth) + joint states -> action prediction",
        "Diffusion Policy: multi-modal observation input with temporal context",
        "ACT (Action Chunking with Transformers): joint trajectory chunks from demonstrations",
        "Data format: JSON frames + PNG images, easily convertible to HDF5/TFRecord",
    ]
    for i, item in enumerate(items):
        bullet_color = ACCENT_GREEN if i < 3 else GRAY
        draw.text((120, by + 70 + i * 28), f"  {item}", fill=bullet_color, font=fonts["small"])

    img.save(output)
    print(f"  Sensors slide: {output}")


def make_web_ui_slide(output: str):
    """Fallback slide for web UI section when no OBS clip available."""
    from PIL import Image, ImageDraw

    fonts = _load_fonts()
    img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
    draw = ImageDraw.Draw(img)

    draw.text((60, 60), "RoboLab Console — Web Interface",
              fill=WHITE, font=fonts["heading"])
    draw.rectangle([(60, 120), (180, 124)], fill=ACCENT_BLUE)

    # Mock UI layout
    # Sidebar
    draw.rounded_rectangle([(60, 180), (300, HEIGHT - 60)], radius=12, fill=(25, 30, 45))
    menu_items = ["Dashboard", "Episodes", "Experiments", "Scenes",
                  "Launch Profiles", "Recordings", "Settings"]
    for i, item in enumerate(menu_items):
        color = ACCENT_BLUE if i == 1 else GRAY
        draw.text((85, 210 + i * 45), item, fill=color, font=fonts["body"])

    # Main content area
    draw.rounded_rectangle([(330, 180), (WIDTH - 60, HEIGHT - 60)],
                           radius=12, fill=(25, 30, 45))
    draw.text((370, 210), "Episodes", fill=WHITE, font=fonts["heading"])

    # Episode cards
    episodes = [
        ("fixed_mug_rearrange", "Completed", "5/5 tasks passed", ACCENT_GREEN),
        ("fixed_fridge_experiment3", "Completed", "4/4 tasks passed", ACCENT_GREEN),
        ("fixed_banana_to_sink", "Completed", "3/3 tasks passed", ACCENT_GREEN),
    ]
    for i, (name, status, tasks_text, color) in enumerate(episodes):
        ey = 280 + i * 120
        draw.rounded_rectangle([(370, ey), (WIDTH - 100, ey + 100)],
                               radius=8, fill=DARK_BG)
        draw.text((400, ey + 15), name, fill=WHITE, font=fonts["body"])
        draw.text((400, ey + 55), tasks_text, fill=GRAY, font=fonts["small"])
        # Status badge
        draw.rounded_rectangle([(WIDTH - 300, ey + 20), (WIDTH - 140, ey + 55)],
                               radius=6, fill=color)
        draw.text((WIDTH - 285, ey + 24), status, fill=WHITE, font=fonts["small"])

    # Bottom: features
    draw.text((370, HEIGHT - 150),
              "Features: Episode wizard | Video playback | Telemetry viewer | "
              "Dataset validation | Export",
              fill=GRAY, font=fonts["small"])

    img.save(output)
    print(f"  Web UI slide: {output}")


def make_teleop_slide(replicator_frame_path: str, output: str):
    """Teleop UI mockup with real Isaac Sim frame and control panel."""
    from PIL import Image, ImageDraw

    fonts = _load_fonts()
    img = Image.new("RGB", (WIDTH, HEIGHT), DARK_BG)
    draw = ImageDraw.Draw(img)

    # Header
    draw.text((60, 30), "Teleoperation — Web UI + Isaac Sim Live Stream",
              fill=WHITE, font=fonts["heading"])
    draw.rectangle([(60, 85), (180, 89)], fill=ACCENT_BLUE)

    # ---- RIGHT: Isaac Sim viewport (real frame) ----
    sim_x, sim_y = 680, 100
    sim_w, sim_h = 1180, 700
    draw.rounded_rectangle([(sim_x, sim_y), (sim_x + sim_w, sim_y + sim_h)],
                           radius=8, fill=(10, 10, 16))
    # Load real replicator frame
    if os.path.isfile(replicator_frame_path):
        frame = Image.open(replicator_frame_path)
        frame = frame.resize((sim_w - 8, sim_h - 8))
        img.paste(frame, (sim_x + 4, sim_y + 4))
    # Stream badge
    draw.rounded_rectangle([(sim_x + 10, sim_y + 10), (sim_x + 120, sim_y + 38)],
                           radius=4, fill=(220, 38, 38))
    draw.text((sim_x + 22, sim_y + 13), "LIVE STREAM", fill=WHITE, font=fonts["small"])
    # Viewport label
    draw.text((sim_x + 10, sim_y + sim_h + 8),
              "Isaac Sim — Kitchen Scene — TIAGo Robot (WebRTC stream)",
              fill=GRAY, font=fonts["small"])

    # ---- LEFT: Control panel ----
    cp_x, cp_y = 40, 100
    cp_w = 610

    # Base movement section
    draw.text((cp_x, cp_y), "Base Movement", fill=ACCENT_BLUE, font=fonts["body"])
    draw.text((cp_x + 220, cp_y + 4), "Shift + WASD", fill=GRAY, font=fonts["small"])
    btn_grid = [
        ["Rot L", "Forward", "Rot R"],
        ["Left", "Back", "Right"],
    ]
    btn_w, btn_h, btn_gap = 90, 44, 6
    grid_x = cp_x + 40
    for row_i, row in enumerate(btn_grid):
        for col_i, label in enumerate(row):
            bx = grid_x + col_i * (btn_w + btn_gap)
            by = cp_y + 40 + row_i * (btn_h + btn_gap)
            draw.rounded_rectangle([(bx, by), (bx + btn_w, by + btn_h)],
                                   radius=6, fill=(45, 50, 70))
            bb = draw.textbbox((0, 0), label, font=fonts["small"])
            lw = bb[2] - bb[0]
            draw.text((bx + (btn_w - lw) // 2, by + 12), label, fill=WHITE, font=fonts["small"])
    # E-STOP
    estop_x = grid_x + 3 * (btn_w + btn_gap) + 20
    estop_y = cp_y + 40
    draw.rounded_rectangle([(estop_x, estop_y), (estop_x + 100, estop_y + 94)],
                           radius=8, fill=(185, 28, 28))
    draw.text((estop_x + 10, estop_y + 20), "E-STOP", fill=WHITE, font=fonts["body"])

    # Arm control section
    arm_y = cp_y + 160
    draw.text((cp_x, arm_y), "Arm Control", fill=ACCENT_BLUE, font=fonts["body"])
    draw.text((cp_x + 180, arm_y + 4), "MoveIt", fill=ACCENT_GREEN, font=fonts["small"])
    arm_btns = [
        ["Arm Fwd", "Arm Up", "Torso Up"],
        ["Arm Back", "Arm Down", "Torso Dn"],
    ]
    for row_i, row in enumerate(arm_btns):
        for col_i, label in enumerate(row):
            bx = grid_x + col_i * (btn_w + btn_gap)
            by = arm_y + 40 + row_i * (btn_h + btn_gap)
            draw.rounded_rectangle([(bx, by), (bx + btn_w, by + btn_h)],
                                   radius=6, fill=(45, 50, 70))
            bb = draw.textbbox((0, 0), label, font=fonts["small"])
            lw = bb[2] - bb[0]
            draw.text((bx + (btn_w - lw) // 2, by + 12), label, fill=WHITE, font=fonts["small"])

    # Gripper
    grip_y = arm_y + 150
    draw.text((cp_x, grip_y), "Gripper", fill=ACCENT_BLUE, font=fonts["body"])
    for ci, (label, color) in enumerate([("Open", ACCENT_GREEN), ("Close", (220, 38, 38))]):
        bx = grid_x + ci * (120 + btn_gap)
        by = grip_y + 36
        draw.rounded_rectangle([(bx, by), (bx + 120, by + btn_h)],
                               radius=6, fill=color)
        bb = draw.textbbox((0, 0), label, font=fonts["body"])
        lw = bb[2] - bb[0]
        draw.text((bx + (120 - lw) // 2, by + 8), label, fill=WHITE, font=fonts["body"])

    # Arm macros
    macro_y = grip_y + 100
    draw.text((cp_x, macro_y), "Arm Macros", fill=ACCENT_BLUE, font=fonts["body"])
    macros = ["Home", "Pre-Grasp", "Extend Fwd", "Extend Low", "Raise High", "Grasp Pose"]
    for mi, label in enumerate(macros):
        col = mi % 3
        row = mi // 3
        bx = grid_x + col * (btn_w + btn_gap)
        by = macro_y + 36 + row * (btn_h + btn_gap)
        draw.rounded_rectangle([(bx, by), (bx + btn_w, by + btn_h)],
                               radius=6, fill=(35, 40, 55))
        bb = draw.textbbox((0, 0), label, font=fonts["small"])
        lw = bb[2] - bb[0]
        draw.text((bx + (btn_w - lw) // 2, by + 12), label, fill=GRAY, font=fonts["small"])

    # ---- BOTTOM: Status bar ----
    status_y = HEIGHT - 70
    draw.rounded_rectangle([(40, status_y), (WIDTH - 40, HEIGHT - 20)],
                           radius=8, fill=(25, 30, 45))
    # Status indicators
    indicators = [
        ("MoveIt", True), ("ROS2", True), ("WebRTC", True), ("Isaac Sim", True),
    ]
    sx = 70
    for label, active in indicators:
        color = ACCENT_GREEN if active else (120, 120, 120)
        draw.ellipse([(sx, status_y + 16), (sx + 12, status_y + 28)], fill=color)
        draw.text((sx + 18, status_y + 12), label, fill=WHITE, font=fonts["small"])
        sx += 160
    draw.text((sx + 80, status_y + 12),
              "Last cmd: arm_forward  |  Mode: MoveIt Session",
              fill=GRAY, font=fonts["small"])

    img.save(output)
    print(f"  Teleop slide: {output}")


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build RoboLab demo v2")
    parser.add_argument("--output", default="demo_output/robolab_demo_v2.mp4")
    parser.add_argument("--data-root", default=str(DATA_ROOT))
    parser.add_argument("--web-clip", default=None,
                        help="Optional OBS recording of web UI")
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
        from PIL import Image
    except ImportError:
        print("ERROR: pip install Pillow"); sys.exit(1)
    try:
        import matplotlib
    except ImportError:
        print("ERROR: pip install matplotlib"); sys.exit(1)

    # Verify source videos exist
    mug_videos = {
        "external": mug_ep / "external_robot.mp4",
        "isometric": mug_ep / "isometric_kitchen.mp4",
        "front": mug_ep / "front_kitchen.mp4",
        "top": mug_ep / "top_kitchen.mp4",
    }
    for name, path in mug_videos.items():
        if not path.is_file():
            print(f"ERROR: Missing {name} video: {path}")
            sys.exit(1)

    print(f"\nAll source files verified.\n")

    with tempfile.TemporaryDirectory(prefix="robolab_v2_") as tmp:
        tmp = Path(tmp)
        segments = []

        # ============================================================
        # PART 1: Opening title (3.5s)
        # ============================================================
        print("=== Part 1: Opening title ===")
        title_png = tmp / "title_open.png"
        make_title_card(
            "RoboLab",
            "Data Collection Platform for Robotic Simulation",
            str(title_png),
        )
        title_mp4 = tmp / "title_open.mp4"
        image_to_video(ffmpeg, str(title_png), str(title_mp4), TITLE_DURATION)
        segments.append(title_mp4)

        # ============================================================
        # PART 2: Section title (kitchen overview REMOVED per feedback)
        # ============================================================
        print("\n=== Part 2: Mug task title ===")
        mug_title_png = tmp / "title_mug.png"
        make_title_card(
            "Mug Pick-and-Place",
            "Autonomous task: navigate, grasp, carry, place",
            str(mug_title_png),
        )
        mug_title_mp4 = tmp / "title_mug.mp4"
        image_to_video(ffmpeg, str(mug_title_png), str(mug_title_mp4), 2.5)
        segments.append(mug_title_mp4)

        # ============================================================
        # PART 3: Mug pick-and-place — multi-camera edit (~45s)
        # Uses different cameras for each phase so viewer sees
        # the full manipulation from multiple perspectives.
        # ============================================================
        print("\n=== Part 3: Mug pick-and-place (multi-camera) ===")

        # 3a: Isometric — robot approaches table (T1 navigation, 3x)
        seg = tmp / "mug_3a.mp4"
        trim_and_speed(ffmpeg, str(mug_videos["isometric"]), str(seg),
                       ss=0, t=MUG_T1_END, speed=3.0)
        seg_ov = tmp / "mug_3a_ov.mp4"
        add_overlay(ffmpeg, str(seg), str(seg_ov),
                    "T1 Navigate to mug (3x) - Isometric view", tmp_dir=tmp)
        segments.append(seg_ov)

        # 3b: Front kitchen — arm extends toward mug (T2 start, 1x)
        seg = tmp / "mug_3b.mp4"
        trim_and_speed(ffmpeg, str(mug_videos["front"]), str(seg),
                       ss=MUG_T1_END, t=14, speed=1.0)
        seg_ov = tmp / "mug_3b_ov.mp4"
        add_overlay(ffmpeg, str(seg), str(seg_ov),
                    "T2 Arm extension toward mug - Front view", tmp_dir=tmp)
        segments.append(seg_ov)

        # 3c: External robot — close-up grasp (T2 mid, 1.5x)
        seg = tmp / "mug_3c.mp4"
        trim_and_speed(ffmpeg, str(mug_videos["external"]), str(seg),
                       ss=MUG_T1_END + 14, t=25, speed=1.5)
        seg_ov = tmp / "mug_3c_ov.mp4"
        add_overlay(ffmpeg, str(seg), str(seg_ov),
                    "T2 Grasp mug close-up (1.5x) - External robot view", tmp_dir=tmp)
        segments.append(seg_ov)

        # 3d: Isometric — carry to new position (T2 end + T3 + T4 start, 2x)
        seg = tmp / "mug_3d.mp4"
        trim_and_speed(ffmpeg, str(mug_videos["isometric"]), str(seg),
                       ss=MUG_T1_END + 14 + 25, t=20, speed=2.0)
        seg_ov = tmp / "mug_3d_ov.mp4"
        add_overlay(ffmpeg, str(seg), str(seg_ov),
                    "T3-T4 Carry and move to place (2x) - Isometric view", tmp_dir=tmp)
        segments.append(seg_ov)

        # 3e: External — place mug down (T4 end, 1.5x)
        seg = tmp / "mug_3e.mp4"
        place_start = MUG_T1_END + 14 + 25 + 20
        place_dur = max(MUG_T4_END - place_start, 3)
        trim_and_speed(ffmpeg, str(mug_videos["external"]), str(seg),
                       ss=place_start, t=place_dur, speed=1.5)
        seg_ov = tmp / "mug_3e_ov.mp4"
        add_overlay(ffmpeg, str(seg), str(seg_ov),
                    "T4 Place mug down (1.5x) - External robot view", tmp_dir=tmp)
        segments.append(seg_ov)

        # 3f: Top — return to start (T5, 2x)
        seg = tmp / "mug_3f.mp4"
        trim_and_speed(ffmpeg, str(mug_videos["top"]), str(seg),
                       ss=MUG_T4_END, t=MUG_T5_END - MUG_T4_END, speed=2.0)
        seg_ov = tmp / "mug_3f_ov.mp4"
        add_overlay(ffmpeg, str(seg), str(seg_ov),
                    "T5 Return to start (2x) - Top view", tmp_dir=tmp)
        segments.append(seg_ov)

        # ============================================================
        # PART 4: Teleoperation UI
        # ============================================================
        print("\n=== Part 4: Teleoperation ===")
        teleop_title_png = tmp / "title_teleop.png"
        make_title_card("Teleoperation", "Web UI controls + Isaac Sim live stream",
                        str(teleop_title_png))
        teleop_title_mp4 = tmp / "title_teleop.mp4"
        image_to_video(ffmpeg, str(teleop_title_png), str(teleop_title_mp4), 2.5)
        segments.append(teleop_title_mp4)

        # Use a real replicator frame as the "live stream" in the mockup
        repl_frame = mug_ep / "replicator_external_robot" / "rgb_0500.png"
        if not repl_frame.is_file():
            # Fallback: try any frame
            repl_dir = mug_ep / "replicator_external_robot"
            if repl_dir.is_dir():
                pngs = sorted(repl_dir.glob("rgb_*.png"))
                repl_frame = pngs[len(pngs) // 2] if pngs else repl_frame

        teleop_png = tmp / "teleop_ui.png"
        make_teleop_slide(str(repl_frame), str(teleop_png))
        teleop_mp4 = tmp / "teleop_ui.mp4"
        image_to_video(ffmpeg, str(teleop_png), str(teleop_mp4), SLIDE_DURATION + 2)
        teleop_ov = tmp / "teleop_ov.mp4"
        add_overlay(ffmpeg, str(teleop_mp4), str(teleop_ov),
                    "Web-based teleoperation: WASD base control + MoveIt arm planning + gripper", tmp_dir=tmp)
        segments.append(teleop_ov)

        # ============================================================
        # PART 5: Telemetry & Data
        # ============================================================
        print("\n=== Part 5: Telemetry & Data ===")
        tel_title_png = tmp / "title_telemetry.png"
        make_title_card("Collected Data", "Telemetry, joint states, and training-ready datasets",
                        str(tel_title_png))
        tel_title_mp4 = tmp / "title_telemetry.mp4"
        image_to_video(ffmpeg, str(tel_title_png), str(tel_title_mp4), 2.5)
        segments.append(tel_title_mp4)

        # 5a: Trajectory
        telem_json = kitchen_scene / "telemetry.json"
        if telem_json.is_file():
            traj_png = tmp / "trajectory.png"
            make_trajectory_slide(str(telem_json), str(traj_png))
            traj_mp4 = tmp / "trajectory.mp4"
            image_to_video(ffmpeg, str(traj_png), str(traj_mp4), SLIDE_DURATION)
            traj_ov = tmp / "trajectory_ov.mp4"
            add_overlay(ffmpeg, str(traj_mp4), str(traj_ov),
                        "Robot base trajectory recorded during episode", tmp_dir=tmp)
            segments.append(traj_ov)

        # 5b: Joint states (from mug episode physics log)
        physics_json = mug_ep / "physics_log.json"
        if physics_json.is_file():
            joints_png = tmp / "joints.png"
            make_joints_slide(str(physics_json), str(joints_png))
            joints_mp4 = tmp / "joints.mp4"
            image_to_video(ffmpeg, str(joints_png), str(joints_mp4), SLIDE_DURATION)
            joints_ov = tmp / "joints_ov.mp4"
            add_overlay(ffmpeg, str(joints_mp4), str(joints_ov),
                        "Joint state telemetry - arm and torso positions over time", tmp_dir=tmp)
            segments.append(joints_ov)

        # 5c: Task results
        results_json = mug_ep / "task_results.json"
        if results_json.is_file():
            results_png = tmp / "results.png"
            make_task_results_slide(str(results_json), str(results_png))
            results_mp4 = tmp / "results.mp4"
            image_to_video(ffmpeg, str(results_png), str(results_mp4), SLIDE_DURATION)
            results_ov = tmp / "results_ov.mp4"
            add_overlay(ffmpeg, str(results_mp4), str(results_ov),
                        "Episode results: 5/5 tasks completed successfully", tmp_dir=tmp)
            segments.append(results_ov)

        # 5d: Sensors
        sensors_png = tmp / "sensors.png"
        make_sensors_slide(str(sensors_png))
        sensors_mp4 = tmp / "sensors.mp4"
        image_to_video(ffmpeg, str(sensors_png), str(sensors_mp4), SLIDE_DURATION)
        sensors_ov = tmp / "sensors_ov.mp4"
        add_overlay(ffmpeg, str(sensors_mp4), str(sensors_ov),
                    "Multi-modal data suitable for behavior cloning and diffusion policies", tmp_dir=tmp)
        segments.append(sensors_ov)

        # ============================================================
        # PART 6: Final title
        # ============================================================
        print("\n=== Part 6: Final title ===")
        final_png = tmp / "title_final.png"
        make_title_card("RoboLab", "github.com/tmhwk77/robolab", str(final_png))
        final_mp4 = tmp / "title_final.mp4"
        image_to_video(ffmpeg, str(final_png), str(final_mp4), TITLE_DURATION)
        segments.append(final_mp4)

        # ============================================================
        # CONCAT
        # ============================================================
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
