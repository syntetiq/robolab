#!/usr/bin/env python3
"""
Validate collected dataset quality across all episodes.

Checks:
  - dataset.json: frame count, FPS, joint positions+velocities, world_poses, robot_pose
  - camera_0.mp4: existence and file size
  - replicator_data/: pointcloud, depth, RGB, semantic segmentation counts
  - metadata.json, telemetry.json, dataset_manifest.json

Usage:
  python scripts/validate_dataset.py [--episodes-dir C:/RoboLab_Data/episodes]
                                      [--last N]  # only check last N episodes
"""

import argparse
import json
import os
import sys
from pathlib import Path


def human_size(nbytes):
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024.0:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024.0
    return f"{nbytes:.1f} TB"


def validate_episode(ep_dir: Path) -> dict:
    result = {
        "id": ep_dir.name,
        "status": "PASS",
        "warnings": [],
        "errors": [],
        "frames": 0,
        "fps": 0.0,
        "duration_s": 0.0,
        "joints": 0,
        "has_velocities": False,
        "world_objects": 0,
        "has_robot_pose": False,
        "video_size": 0,
        "pointclouds": 0,
        "depth_maps": 0,
        "rgb_images": 0,
        "semantic_masks": 0,
        "total_size": 0,
    }

    total_size = 0
    for f in ep_dir.rglob("*"):
        if f.is_file():
            total_size += f.stat().st_size
    result["total_size"] = total_size

    # dataset.json
    ds_path = ep_dir / "dataset.json"
    if not ds_path.exists():
        result["errors"].append("missing dataset.json")
        result["status"] = "FAIL"
    else:
        try:
            ds = json.loads(ds_path.read_text(encoding="utf-8"))
            frames = ds.get("frames", [])
            result["frames"] = len(frames)
            if not frames:
                result["errors"].append("dataset.json has 0 frames")
                result["status"] = "FAIL"
            else:
                t0 = frames[0].get("timestamp", 0)
                t1 = frames[-1].get("timestamp", 0)
                result["duration_s"] = round(t1 - t0, 2)
                if result["duration_s"] > 0:
                    result["fps"] = round(len(frames) / result["duration_s"], 1)

                f0 = frames[0]
                rj = f0.get("robot_joints", {})
                result["joints"] = len(rj)
                if result["joints"] == 0:
                    result["errors"].append("no robot_joints in frames")
                    result["status"] = "FAIL"

                first_joint = next(iter(rj.values()), {}) if rj else {}
                result["has_velocities"] = "velocity" in first_joint
                if not result["has_velocities"]:
                    result["warnings"].append("robot_joints missing velocity data")

                wp = f0.get("world_poses", {})
                result["world_objects"] = len(wp)
                if result["world_objects"] == 0:
                    result["warnings"].append("no world_poses tracked")

                result["has_robot_pose"] = "robot_pose" in f0
                if not result["has_robot_pose"]:
                    result["warnings"].append("missing robot_pose in frames")
        except Exception as e:
            result["errors"].append(f"failed to parse dataset.json: {e}")
            result["status"] = "FAIL"

    # camera_0.mp4
    vid_path = ep_dir / "camera_0.mp4"
    if vid_path.exists():
        result["video_size"] = vid_path.stat().st_size
        if result["video_size"] < 10_000:
            result["warnings"].append(f"video very small ({human_size(result['video_size'])})")
    else:
        result["warnings"].append("missing camera_0.mp4")

    # replicator_data
    rep_dir = ep_dir / "replicator_data"
    if rep_dir.exists():
        for f in rep_dir.iterdir():
            name = f.name
            if name.startswith("pointcloud_") and name.endswith(".npy"):
                result["pointclouds"] += 1
            elif name.startswith("distance_to_camera_") and name.endswith(".npy"):
                result["depth_maps"] += 1
            elif name.startswith("rgb_") and name.endswith(".png"):
                result["rgb_images"] += 1
            elif name.startswith("semantic_segmentation_") and name.endswith(".png"):
                result["semantic_masks"] += 1
    else:
        result["warnings"].append("missing replicator_data/")

    if result["pointclouds"] == 0:
        result["warnings"].append("no pointcloud data")
    if result["rgb_images"] == 0:
        result["warnings"].append("no replicator RGB images")

    # metadata.json
    if not (ep_dir / "metadata.json").exists():
        result["warnings"].append("missing metadata.json")

    # telemetry.json
    if not (ep_dir / "telemetry.json").exists():
        result["warnings"].append("missing telemetry.json")

    # dataset_manifest.json
    if not (ep_dir / "dataset_manifest.json").exists():
        result["warnings"].append("missing dataset_manifest.json")

    if result["errors"]:
        result["status"] = "FAIL"
    elif result["warnings"]:
        result["status"] = "WARN"

    return result


def main():
    parser = argparse.ArgumentParser(description="Validate dataset quality")
    parser.add_argument("--episodes-dir", default=r"C:\RoboLab_Data\episodes",
                        help="Root directory containing episode subdirectories")
    parser.add_argument("--last", type=int, default=0,
                        help="Only validate the N most recent episodes (0 = all)")
    parser.add_argument("--json-out", default="",
                        help="Write results as JSON to this file")
    args = parser.parse_args()

    ep_root = Path(args.episodes_dir)
    if not ep_root.exists():
        print(f"ERROR: episodes directory not found: {ep_root}")
        sys.exit(1)

    ep_dirs = sorted(
        [d for d in ep_root.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )

    if args.last > 0:
        ep_dirs = ep_dirs[:args.last]

    print(f"Validating {len(ep_dirs)} episodes in {ep_root}...")
    print()

    results = []
    pass_count = warn_count = fail_count = 0

    for ep_dir in ep_dirs:
        r = validate_episode(ep_dir)
        results.append(r)
        tag = r["status"]
        if tag == "PASS":
            pass_count += 1
        elif tag == "WARN":
            warn_count += 1
        else:
            fail_count += 1

        status_marker = {"PASS": "OK", "WARN": "!!", "FAIL": "XX"}[tag]
        print(f"[{status_marker}] {r['id'][:12]}.. | {r['frames']:>5} frames | "
              f"{r['fps']:>5.1f} fps | {r['joints']:>3} joints | "
              f"{r['world_objects']} obj | "
              f"pc:{r['pointclouds']} rgb:{r['rgb_images']} depth:{r['depth_maps']} sem:{r['semantic_masks']} | "
              f"{human_size(r['total_size'])}")
        if r["errors"]:
            for e in r["errors"]:
                print(f"     ERR: {e}")
        if r["warnings"]:
            for w in r["warnings"]:
                print(f"     WRN: {w}")

    print()
    print(f"{'='*70}")
    print(f"SUMMARY: {len(results)} episodes | "
          f"PASS: {pass_count} | WARN: {warn_count} | FAIL: {fail_count}")
    total_frames = sum(r["frames"] for r in results)
    total_size = sum(r["total_size"] for r in results)
    print(f"Total frames: {total_frames} | Total size: {human_size(total_size)}")
    print(f"{'='*70}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"JSON results written to {args.json_out}")

    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
