#!/usr/bin/env python3
"""
Episode Validation Protocol for RoboLab.

Checks collected episodes against quality thresholds:
  1. Robot Z stability (drift < 0.02m)
  2. Environment object stability (drift < 0.05m)
  3. Joint velocity sanity (max < 10 rad/s)
  4. Trajectory smoothness (no position jumps > 0.5 rad between frames)
  5. Point cloud presence
  6. Trajectory execution success rate

Usage:
  python validate_episodes.py [--episodes-dir C:\\RoboLab_Data\\episodes]
                               [--verbose]
"""

import argparse
import json
import os
import sys
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="Validate collected episode data")
    p.add_argument(
        "--episodes-dir",
        default=os.environ.get("ROBOLAB_EPISODES_DIR", r"C:\RoboLab_Data\episodes"),
        help="Root directory containing episode subdirectories.",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument(
        "--max-robot-z-drift", type=float, default=0.02,
        help="Max acceptable Z drift for robot base (meters).",
    )
    p.add_argument(
        "--max-object-drift", type=float, default=0.05,
        help="Max acceptable position drift for anchored env objects (meters).",
    )
    p.add_argument(
        "--max-joint-velocity", type=float, default=10.0,
        help="Max acceptable joint velocity (rad/s).",
    )
    p.add_argument(
        "--max-position-jump", type=float, default=0.5,
        help="Max acceptable position change between consecutive frames (rad).",
    )
    return p.parse_args()


def validate_episode(episode_dir: Path, args) -> dict:
    """Validate a single episode. Returns a dict of check results."""
    dataset_path = episode_dir / "dataset.json"
    if not dataset_path.exists():
        return {"error": "dataset.json not found", "valid": False}

    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)
    except Exception as e:
        return {"error": f"Failed to parse dataset.json: {e}", "valid": False}

    frames = dataset.get("frames", [])
    if not frames:
        return {"error": "No frames in dataset", "valid": False}

    results = {
        "episode": episode_dir.name,
        "frame_count": len(frames),
        "checks": {},
        "valid": True,
    }

    # 1. Robot Z stability
    robot_z_values = []
    for frame in frames:
        rp = frame.get("robot_pose", {})
        pos = rp.get("position", [])
        if len(pos) >= 3:
            robot_z_values.append(pos[2])
    if robot_z_values:
        z_min, z_max = min(robot_z_values), max(robot_z_values)
        z_drift = z_max - z_min
        z_ok = z_drift < args.max_robot_z_drift
        results["checks"]["robot_z_stability"] = {
            "pass": z_ok,
            "z_min": round(z_min, 4),
            "z_max": round(z_max, 4),
            "drift": round(z_drift, 4),
            "threshold": args.max_robot_z_drift,
        }
        if not z_ok:
            results["valid"] = False

    # 2. Environment object stability
    object_drifts = {}
    for frame in frames:
        wp = frame.get("world_poses", {})
        for prim_path, data in wp.items():
            if data.get("class") == "robot":
                continue
            pos = data.get("position", [])
            if len(pos) >= 3:
                if prim_path not in object_drifts:
                    object_drifts[prim_path] = {"first": pos[:3], "last": pos[:3], "class": data.get("class", "")}
                object_drifts[prim_path]["last"] = pos[:3]

    obj_stability_results = []
    for prim_path, info in object_drifts.items():
        f, l = info["first"], info["last"]
        drift = ((f[0]-l[0])**2 + (f[1]-l[1])**2 + (f[2]-l[2])**2) ** 0.5
        ok = drift < args.max_object_drift
        obj_stability_results.append({
            "prim": prim_path,
            "class": info["class"],
            "drift_m": round(drift, 4),
            "pass": ok,
        })
        if not ok:
            results["valid"] = False

    failed_objects = [o for o in obj_stability_results if not o["pass"]]
    results["checks"]["object_stability"] = {
        "pass": len(failed_objects) == 0,
        "total_objects": len(obj_stability_results),
        "failed_objects": len(failed_objects),
        "details": failed_objects[:5] if failed_objects else [],
    }

    # 3. Joint velocity sanity (exclude passive roller/wheel/caster joints)
    _PASSIVE_JOINT_KW = ("roller", "wheel", "caster", "suspension")
    max_vel = 0.0
    max_vel_joint = ""
    vel_violations = 0
    for frame in frames:
        joints = frame.get("robot_joints", {})
        for jname, jdata in joints.items():
            if any(kw in jname.lower() for kw in _PASSIVE_JOINT_KW):
                continue
            v = abs(jdata.get("velocity", 0.0))
            if v > max_vel:
                max_vel = v
                max_vel_joint = jname
            if v > args.max_joint_velocity:
                vel_violations += 1

    vel_ok = max_vel < args.max_joint_velocity
    results["checks"]["velocity_sanity"] = {
        "pass": vel_ok,
        "max_velocity": round(max_vel, 2),
        "max_velocity_joint": max_vel_joint,
        "violation_count": vel_violations,
        "threshold": args.max_joint_velocity,
    }
    if not vel_ok:
        results["valid"] = False

    # 4. Trajectory smoothness (position jumps between consecutive frames)
    max_jump = 0.0
    max_jump_joint = ""
    jump_violations = 0
    prev_joints = {}
    for frame in frames:
        joints = frame.get("robot_joints", {})
        for jname, jdata in joints.items():
            if any(kw in jname.lower() for kw in _PASSIVE_JOINT_KW):
                continue
            pos = jdata.get("position", 0.0)
            if jname in prev_joints:
                jump = abs(pos - prev_joints[jname])
                if jump > max_jump:
                    max_jump = jump
                    max_jump_joint = jname
                if jump > args.max_position_jump:
                    jump_violations += 1
            prev_joints[jname] = pos

    jump_ok = max_jump < args.max_position_jump
    results["checks"]["trajectory_smoothness"] = {
        "pass": jump_ok,
        "max_jump_rad": round(max_jump, 4),
        "max_jump_joint": max_jump_joint,
        "violation_count": jump_violations,
        "threshold": args.max_position_jump,
    }
    if not jump_ok:
        results["valid"] = False

    # 5. Point cloud / sensor data presence
    replicator_dir = episode_dir / "replicator_data"
    has_rgb = len(list(replicator_dir.glob("rgb_*.png"))) > 0 if replicator_dir.exists() else False
    has_depth = len(list(replicator_dir.glob("distance_to_camera_*.npy"))) > 0 if replicator_dir.exists() else False
    has_pointcloud = len(list(replicator_dir.glob("pointcloud_*.npy"))) > 0 if replicator_dir.exists() else False
    has_semantics = len(list(replicator_dir.glob("semantic_segmentation_*.png"))) > 0 if replicator_dir.exists() else False

    results["checks"]["sensor_data"] = {
        "pass": has_rgb,
        "rgb": has_rgb,
        "depth": has_depth,
        "pointcloud": has_pointcloud,
        "semantic_segmentation": has_semantics,
    }

    # 6. Trajectory execution
    executed = dataset.get("joint_trajectories_executed", [])
    succeeded = sum(1 for t in executed if t.get("status") == "succeeded")
    failed = sum(1 for t in executed if t.get("status") != "succeeded")
    results["checks"]["trajectory_execution"] = {
        "pass": len(executed) > 0 and failed == 0,
        "total": len(executed),
        "succeeded": succeeded,
        "failed": failed,
    }

    # Metadata
    meta = dataset.get("metadata", {})
    results["metadata"] = {
        "duration_sec": meta.get("duration_sec", 0),
        "joint_source": meta.get("joint_source", "unknown"),
        "moveit_mode": meta.get("moveit_mode_enabled", False),
        "vr_teleop": meta.get("vr_teleop_enabled", False),
        "replicator_subsample": meta.get("replicator_subsample", 0),
    }

    return results


def main():
    args = parse_args()
    episodes_dir = Path(args.episodes_dir)

    if not episodes_dir.exists():
        print(f"Episodes directory not found: {episodes_dir}")
        sys.exit(1)

    episode_dirs = sorted([
        d for d in episodes_dir.iterdir()
        if d.is_dir() and (d / "dataset.json").exists()
    ])

    if not episode_dirs:
        print(f"No episodes with dataset.json found in {episodes_dir}")
        sys.exit(1)

    print(f"Validating {len(episode_dirs)} episodes in {episodes_dir}\n")
    print("=" * 80)

    total_valid = 0
    total_invalid = 0
    all_results = []

    for ep_dir in episode_dirs:
        result = validate_episode(ep_dir, args)
        all_results.append(result)

        status = "PASS" if result.get("valid") else "FAIL"
        if result.get("valid"):
            total_valid += 1
        else:
            total_invalid += 1

        print(f"\n[{status}] {ep_dir.name} ({result.get('frame_count', 0)} frames)")

        if args.verbose or not result.get("valid"):
            checks = result.get("checks", {})
            for check_name, check_data in checks.items():
                check_status = "OK" if check_data.get("pass") else "FAIL"
                detail = ""
                if check_name == "robot_z_stability":
                    detail = f"drift={check_data.get('drift', '?')}m (max {check_data.get('threshold')}m)"
                elif check_name == "velocity_sanity":
                    detail = f"max={check_data.get('max_velocity', '?')} rad/s on {check_data.get('max_velocity_joint', '?')}"
                elif check_name == "trajectory_smoothness":
                    detail = f"max_jump={check_data.get('max_jump_rad', '?')} rad"
                elif check_name == "object_stability":
                    detail = f"{check_data.get('failed_objects', 0)}/{check_data.get('total_objects', 0)} drifted"
                elif check_name == "sensor_data":
                    parts = []
                    for s in ("rgb", "depth", "pointcloud", "semantic_segmentation"):
                        parts.append(f"{s}={'Y' if check_data.get(s) else 'N'}")
                    detail = ", ".join(parts)
                elif check_name == "trajectory_execution":
                    detail = f"{check_data.get('succeeded', 0)}/{check_data.get('total', 0)} succeeded"
                print(f"  {check_status:4s} {check_name}: {detail}")

    print("\n" + "=" * 80)
    print(f"\nSummary: {total_valid} PASS, {total_invalid} FAIL out of {len(episode_dirs)} episodes")

    # Save validation report
    report_path = episodes_dir / "validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_episodes": len(episode_dirs),
            "valid": total_valid,
            "invalid": total_invalid,
            "episodes": all_results,
        }, f, indent=2)
    print(f"Report saved: {report_path}")

    sys.exit(0 if total_invalid == 0 else 1)


if __name__ == "__main__":
    main()
