"""
build_demo_video.py — Assemble demo video from OBS screen-capture clips.

Generates title cards (Pillow), adds bottom-bar overlays to each clip,
and concatenates everything into a single MP4 via ffmpeg.

Usage:
    python scripts/build_demo_video.py [--clips-dir demo_clips] [--output demo_output/robolab_demo.mp4]

Prerequisites:
    pip install Pillow
    ffmpeg on PATH (or set FFMPEG_BIN env var)
"""

from __future__ import annotations
import os, sys, subprocess, argparse, shutil, tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Config: scenes with titles and overlay text
# ---------------------------------------------------------------------------

SCENES = [
    {
        "title": "RoboLab Console",
        "subtitle": "Data Collection Platform for Robotic Simulation",
        "overlay": "RoboLab Console — платформа сбора данных для робототехники",
        "clip": "clip_1.mp4",
    },
    {
        "title": "Scenes & Configuration",
        "subtitle": "Procedural 3D environments with physics and articulated furniture",
        "overlay": "Процедурные 3D-среды с физикой и артикулированной мебелью",
        "clip": "clip_2.mp4",
    },
    {
        "title": "Episode Creation",
        "subtitle": "5-step wizard: scene → profile → sensors → parameters → launch",
        "overlay": "5-шаговый визард: сцена → профиль → сенсоры → параметры → запуск",
        "clip": "clip_3.mp4",
    },
    {
        "title": "Episode Results",
        "subtitle": "Video, telemetry, dataset validation — all in one interface",
        "overlay": "Видео, телеметрия, валидация датасета — всё в одном интерфейсе",
        "clip": "clip_4.mp4",
    },
    {
        "title": "Artifacts & Simulation",
        "subtitle": "Recordings library, JSON data, TIAGo robot frames in Isaac Sim",
        "overlay": "Библиотека записей, JSON-данные, кадры робота TIAGo в Isaac Sim",
        "clip": "clip_5.mp4",
    },
]

FINAL_TITLE = {
    "title": "RoboLab Console",
    "subtitle": "github.com/tmhwk77/robolab",
}

# Video settings
WIDTH, HEIGHT = 1920, 1080
TITLE_DURATION = 3  # seconds
OVERLAY_HEIGHT = 70  # pixels
OVERLAY_OPACITY = 0.65
FPS = 30

# ---------------------------------------------------------------------------
# Find ffmpeg
# ---------------------------------------------------------------------------

def find_ffmpeg() -> str:
    env = os.environ.get("FFMPEG_BIN")
    if env and os.path.isfile(env):
        return env
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    # winget install location
    winget_path = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    for p in winget_path.rglob("ffmpeg.exe"):
        return str(p)
    print("ERROR: ffmpeg not found. Install via: winget install Gyan.FFmpeg")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Title card generation (Pillow)
# ---------------------------------------------------------------------------

def generate_title_card(title: str, subtitle: str, output_path: str):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (WIDTH, HEIGHT), (18, 18, 24))
    draw = ImageDraw.Draw(img)

    # Try to use a nice font, fall back to default
    title_size = 72
    subtitle_size = 32
    try:
        title_font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", title_size)
        subtitle_font = ImageFont.truetype("C:/Windows/Fonts/segoeuil.ttf", subtitle_size)
    except (IOError, OSError):
        try:
            title_font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", title_size)
            subtitle_font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", subtitle_size)
        except (IOError, OSError):
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()

    # Accent line
    accent_y = HEIGHT // 2 - 60
    accent_w = 120
    draw.rectangle(
        [(WIDTH // 2 - accent_w // 2, accent_y), (WIDTH // 2 + accent_w // 2, accent_y + 4)],
        fill=(59, 130, 246),  # blue accent
    )

    # Title
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(
        ((WIDTH - title_w) // 2, HEIGHT // 2 - 40),
        title, fill=(255, 255, 255), font=title_font,
    )

    # Subtitle
    sub_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    sub_w = sub_bbox[2] - sub_bbox[0]
    draw.text(
        ((WIDTH - sub_w) // 2, HEIGHT // 2 + 50),
        subtitle, fill=(160, 165, 180), font=subtitle_font,
    )

    img.save(output_path)
    print(f"  Title card: {output_path}")


# ---------------------------------------------------------------------------
# ffmpeg helpers
# ---------------------------------------------------------------------------

def run_ffmpeg(ffmpeg: str, args: list[str], desc: str = ""):
    cmd = [ffmpeg] + args
    if desc:
        print(f"  ffmpeg: {desc}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[-500:]}")
        sys.exit(1)


def image_to_video(ffmpeg: str, image_path: str, output_path: str, duration: float):
    """Convert a static image to a video clip."""
    run_ffmpeg(ffmpeg, [
        "-y", "-loop", "1", "-i", image_path,
        "-c:v", "libx264",  "-t", str(duration),
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-vf", f"scale={WIDTH}:{HEIGHT}",
        output_path,
    ], f"title → {duration}s video")


def add_overlay_bar(ffmpeg: str, input_path: str, output_path: str, text: str):
    """Add a semi-transparent bottom bar with text overlay to a clip."""
    # Escape special chars for ffmpeg drawtext
    safe_text = text.replace("'", "'\\''").replace(":", "\\:")

    # Try Segoe UI first, fall back to Arial
    font_file = "C\\\\:/Windows/Fonts/segoeui.ttf"
    if not os.path.isfile("C:/Windows/Fonts/segoeui.ttf"):
        font_file = "C\\\\:/Windows/Fonts/arial.ttf"

    bar_y = HEIGHT - OVERLAY_HEIGHT
    filter_str = (
        f"drawbox=x=0:y={bar_y}:w={WIDTH}:h={OVERLAY_HEIGHT}"
        f":color=black@{OVERLAY_OPACITY}:t=fill,"
        f"drawtext=fontfile='{font_file}'"
        f":text='{safe_text}'"
        f":fontcolor=white:fontsize=26"
        f":x=(w-text_w)/2:y={bar_y + (OVERLAY_HEIGHT - 26) // 2}"
    )

    run_ffmpeg(ffmpeg, [
        "-y", "-i", input_path,
        "-vf", filter_str,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        output_path,
    ], f"overlay → {Path(output_path).name}")


def normalize_clip(ffmpeg: str, input_path: str, output_path: str):
    """Normalize clip to target resolution and pixel format for concat."""
    run_ffmpeg(ffmpeg, [
        "-y", "-i", input_path,
        "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
               f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-an",  # drop audio for consistency
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        output_path,
    ], f"normalize → {Path(output_path).name}")


def concat_videos(ffmpeg: str, file_list_path: str, output_path: str):
    """Concatenate videos using ffmpeg concat demuxer."""
    run_ffmpeg(ffmpeg, [
        "-y", "-f", "concat", "-safe", "0",
        "-i", file_list_path,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        output_path,
    ], f"concat → {Path(output_path).name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build RoboLab demo video")
    parser.add_argument("--clips-dir", default="demo_clips",
                        help="Directory with clip_1.mp4 ... clip_5.mp4")
    parser.add_argument("--output", default="demo_output/robolab_demo.mp4",
                        help="Output video path")
    args = parser.parse_args()

    clips_dir = Path(args.clips_dir)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = find_ffmpeg()
    print(f"ffmpeg: {ffmpeg}")

    # Check Pillow
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow not installed. Run: pip install Pillow")
        sys.exit(1)

    # Check clips exist
    missing = []
    for scene in SCENES:
        clip_path = clips_dir / scene["clip"]
        if not clip_path.is_file():
            missing.append(str(clip_path))
    if missing:
        print(f"\nMissing clips ({len(missing)}):")
        for m in missing:
            print(f"  - {m}")
        print(f"\nRecord these clips via OBS and place in '{clips_dir}/'")
        print("Clip filenames: " + ", ".join(s["clip"] for s in SCENES))
        sys.exit(1)

    # Work in temp dir
    with tempfile.TemporaryDirectory(prefix="robolab_demo_") as tmp:
        tmp = Path(tmp)
        segments = []  # ordered list of normalized video files for concat

        for i, scene in enumerate(SCENES):
            print(f"\n--- Scene {i + 1}: {scene['title']} ---")

            # 1. Generate title card
            title_png = tmp / f"title_{i + 1}.png"
            generate_title_card(scene["title"], scene["subtitle"], str(title_png))

            # 2. Title card → video
            title_mp4 = tmp / f"title_{i + 1}.mp4"
            image_to_video(ffmpeg, str(title_png), str(title_mp4), TITLE_DURATION)
            segments.append(title_mp4)

            # 3. Add overlay to clip
            clip_path = clips_dir / scene["clip"]
            overlay_mp4 = tmp / f"overlay_{i + 1}.mp4"
            add_overlay_bar(ffmpeg, str(clip_path), str(overlay_mp4), scene["overlay"])

            # 4. Normalize
            norm_mp4 = tmp / f"norm_{i + 1}.mp4"
            normalize_clip(ffmpeg, str(overlay_mp4), str(norm_mp4))
            segments.append(norm_mp4)

        # Final title card
        print(f"\n--- Final title ---")
        final_png = tmp / "title_final.png"
        generate_title_card(FINAL_TITLE["title"], FINAL_TITLE["subtitle"], str(final_png))
        final_mp4 = tmp / "title_final.mp4"
        image_to_video(ffmpeg, str(final_png), str(final_mp4), TITLE_DURATION)
        segments.append(final_mp4)

        # Concat all
        print(f"\n--- Concatenating {len(segments)} segments ---")
        filelist = tmp / "filelist.txt"
        with open(filelist, "w") as f:
            for seg in segments:
                f.write(f"file '{seg}'\n")

        concat_videos(ffmpeg, str(filelist), str(output_path))

    print(f"\nDone! Output: {output_path}")
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Size: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
