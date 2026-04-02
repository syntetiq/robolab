#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="QC and manifest generation for presentation videos.")
    p.add_argument("--output-root", default=r"C:\RoboLab_Data\episodes\scene_robot_videos")
    p.add_argument("--report", default="")
    p.add_argument("--min-bytes", type=int, default=150000)
    p.add_argument("--require-scenes", type=int, default=5)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_root = Path(args.output_root)
    if not out_root.exists():
        print(f"[FAIL] Output root not found: {out_root}")
        return 2

    runs = sorted([d for d in out_root.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
    by_scene: dict[str, Path] = {}
    for run in runs:
        report_file = run / "presentation_report.json"
        if not report_file.exists():
            continue
        payload = json.loads(report_file.read_text(encoding="utf-8"))
        scene_stem = Path(str(payload.get("scene_usd", run.name))).stem
        if scene_stem not in by_scene:
            by_scene[scene_stem] = run

    entries = []
    all_ok = True
    for scene_stem, run in sorted(by_scene.items()):
        rep = json.loads((run / "presentation_report.json").read_text(encoding="utf-8"))
        final_video = Path(str(rep.get("artifacts", {}).get("final_video", "")))
        exists = final_video.exists()
        size = final_video.stat().st_size if exists else 0
        checks_ok = bool(rep.get("status") == "passed")
        size_ok = size >= int(args.min_bytes)
        ok = exists and checks_ok and size_ok
        if not ok:
            all_ok = False
        entries.append(
            {
                "scene": scene_stem,
                "run_dir": str(run),
                "video": str(final_video),
                "exists": exists,
                "bytes": int(size),
                "min_bytes": int(args.min_bytes),
                "checks_ok": checks_ok,
                "ok": ok,
            }
        )

    if len(entries) < int(args.require_scenes):
        all_ok = False

    payload = {
        "output_root": str(out_root),
        "required_scene_count": int(args.require_scenes),
        "scene_count": len(entries),
        "status": "passed" if all_ok else "failed",
        "videos": entries,
    }
    report_path = Path(args.report) if args.report else out_root / "presentation_videos_manifest.json"
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"[QC] report: {report_path}")
    print(f"[QC] status: {payload['status']} | scenes={len(entries)}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
