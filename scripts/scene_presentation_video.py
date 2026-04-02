#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from scene_prep_contract import resolve_scene_prep_contract
from scene_video_profiles import resolve_scene_video_profile


def parse_args():
    p = argparse.ArgumentParser(description="Render scene+robot smoke presentation video.")
    p.add_argument("--scene-usd", required=True, help="Absolute path to scene USD/USDA/USDZ")
    p.add_argument("--isaac-python", default=r"C:\Users\max\Documents\IsaacSim\python.bat")
    p.add_argument("--output-root", default=r"C:\RoboLab_Data\episodes\scene_robot_videos")
    p.add_argument("--manifest", default=str(Path(__file__).resolve().parents[1] / "config" / "scene_prep_manifest.json"))
    p.add_argument("--video-profiles", default=str(Path(__file__).resolve().parents[1] / "config" / "scene_video_profiles.json"))
    p.add_argument("--headless", action="store_true", default=True)
    p.add_argument("--duration", type=int, default=0, help="Override duration from video profile when > 0")
    return p.parse_args()


def wait_for(path: Path, timeout_s: float) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        if path.exists():
            return True
        time.sleep(0.2)
    return False


def wait_for_new_base_pose(base_pose_file: Path, launched_at: float, timeout_s: float) -> dict | None:
    end = time.time() + timeout_s
    while time.time() < end:
        if base_pose_file.exists():
            try:
                pose = json.loads(base_pose_file.read_text(encoding="utf-8"))
                if base_pose_file.stat().st_mtime >= launched_at and float(pose.get("t", 0.0)) > launched_at - 1.0:
                    return pose
            except Exception:
                pass
        time.sleep(0.2)
    return None


def read_base_pose(base_pose_file: Path) -> dict | None:
    try:
        return json.loads(base_pose_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_base_cmd(proxy_dir: Path, vx: float, vy: float, vyaw: float) -> None:
    payload = {"vx": float(vx), "vy": float(vy), "vyaw": float(vyaw), "stamp": time.time()}
    tmp = proxy_dir / "base_cmd.tmp"
    target = proxy_dir / "base_cmd.json"
    body = json.dumps(payload)
    for attempt in range(8):
        try:
            tmp.write_text(body, encoding="utf-8")
            tmp.replace(target)
            return
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))
        except Exception:
            break
    for attempt in range(8):
        try:
            target.write_text(body, encoding="utf-8")
            return
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))


def stop_base(proxy_dir: Path) -> None:
    write_base_cmd(proxy_dir, 0.0, 0.0, 0.0)


def send_pending_traj(proxy_dir: Path, traj_id: int, joint_names: list[str], positions: list[float], t: float = 2.0) -> Path:
    payload = {"traj_id": traj_id, "joint_names": joint_names, "points": [{"positions": positions, "t": float(t)}]}
    pending = proxy_dir / f"pending_{traj_id}.json"
    pending.write_text(json.dumps(payload), encoding="utf-8")
    return proxy_dir / f"done_{traj_id}.json"


def rotate_360(proxy_dir: Path, base_pose_file: Path, omega: float, timeout_s: float) -> float:
    start = read_base_pose(base_pose_file)
    if not start:
        return 0.0
    accum = 0.0
    last_yaw = float(start.get("yaw_deg", 0.0))
    end = time.time() + timeout_s
    while time.time() < end and accum < 355.0:
        write_base_cmd(proxy_dir, 0.0, 0.0, omega)
        time.sleep(0.1)
        cur = read_base_pose(base_pose_file)
        if not cur:
            continue
        yaw = float(cur.get("yaw_deg", last_yaw))
        delta = yaw - last_yaw
        if delta > 180:
            delta -= 360
        elif delta < -180:
            delta += 360
        accum += abs(delta)
        last_yaw = yaw
    stop_base(proxy_dir)
    return accum


def drive_forward(proxy_dir: Path, base_pose_file: Path, max_dist_m: float, vx: float, timeout_s: float) -> float:
    start = read_base_pose(base_pose_file)
    if not start:
        return 0.0
    x0, y0 = float(start.get("x", 0.0)), float(start.get("y", 0.0))
    last_progress_t = time.time()
    last_dist = 0.0
    end = time.time() + timeout_s
    while time.time() < end and last_dist < max_dist_m:
        write_base_cmd(proxy_dir, vx, 0.0, 0.0)
        time.sleep(0.12)
        cur = read_base_pose(base_pose_file)
        if not cur:
            continue
        dx = float(cur.get("x", x0)) - x0
        dy = float(cur.get("y", y0)) - y0
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > last_dist + 0.01:
            last_progress_t = time.time()
            last_dist = dist
        elif time.time() - last_progress_t > 2.0:
            break
    stop_base(proxy_dir)
    return last_dist


def main() -> int:
    args = parse_args()
    scene = Path(args.scene_usd)
    isaac_python = Path(args.isaac_python)
    if not scene.exists():
        print(f"[FAIL] Scene not found: {scene}")
        return 2
    if not isaac_python.exists():
        print(f"[FAIL] Isaac python not found: {isaac_python}")
        return 2

    contract = resolve_scene_prep_contract(scene.name, manifest_path=Path(args.manifest))
    video_profile = resolve_scene_video_profile(scene.name, config_path=Path(args.video_profiles))
    duration_sec = int(args.duration) if int(args.duration) > 0 else int(video_profile.duration_sec)
    collector_duration = max(duration_sec + 120, 180)

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    run_name = f"{scene.stem}_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir = output_root / run_name
    out_dir.mkdir(parents=True, exist_ok=True)

    proxy_dir = Path(r"C:\RoboLab_Data\fjt_proxy")
    proxy_dir.mkdir(parents=True, exist_ok=True)
    for pat in ("pending_*.json", "done_*.json"):
        for f in proxy_dir.glob(pat):
            f.unlink(missing_ok=True)
    for fn in ("joint_state.json", "base_cmd.json", "base_pose.json"):
        (proxy_dir / fn).unlink(missing_ok=True)

    cam_pos = ",".join(f"{x:.3f}" for x in video_profile.external_camera_pos)
    cam_tgt = ",".join(f"{x:.3f}" for x in video_profile.external_camera_target)
    cmd = [
        str(isaac_python),
        str(Path(__file__).with_name("data_collector_tiago.py")),
        "--env",
        str(scene),
        "--output_dir",
        str(out_dir),
        "--duration",
        str(collector_duration),
        "--moveit",
        "--mobile-base",
        "--external-camera",
        "--external-camera-pos",
        cam_pos,
        "--external-camera-target",
        cam_tgt,
        "--width",
        str(int(video_profile.capture_width)),
        "--height",
        str(int(video_profile.capture_height)),
    ]
    if args.headless:
        cmd.append("--headless")

    env = os.environ.copy()
    env["ROS_DOMAIN_ID"] = env.get("ROS_DOMAIN_ID", "77")
    env["ROS_LOCALHOST_ONLY"] = env.get("ROS_LOCALHOST_ONLY", "1")
    env["FJT_PROXY_DIR"] = str(proxy_dir)

    report = {
        "scene_usd": str(scene),
        "profile_id": contract.profile_id,
        "video_profile_id": video_profile.profile_id,
        "camera": {
            "external_pos": video_profile.external_camera_pos,
            "external_target": video_profile.external_camera_target,
            "width": int(video_profile.capture_width),
            "height": int(video_profile.capture_height),
        },
        "checks": {},
        "artifacts": {},
        "status": "failed",
    }

    print(f"[INFO] Running presentation capture for: {scene.name}")
    proc = subprocess.Popen(cmd, env=env)
    launched_at = time.time()
    try:
        base_pose_file = proxy_dir / "base_pose.json"
        pose = wait_for_new_base_pose(base_pose_file, launched_at, 140.0)
        spawn_ok = pose is not None
        report["checks"]["spawn_ready"] = {"ok": spawn_ok, "pose": pose or {}}

        if spawn_ok:
            yaw_acc = rotate_360(
                proxy_dir,
                base_pose_file,
                omega=video_profile.smoke.rotate_omega,
                timeout_s=video_profile.smoke.rotate_timeout_sec,
            )
            report["checks"]["rotate_360"] = {"ok": yaw_acc >= 300.0, "yaw_accum_deg": round(yaw_acc, 2)}
            dist = drive_forward(
                proxy_dir,
                base_pose_file,
                max_dist_m=video_profile.smoke.forward_max_dist_m,
                vx=video_profile.smoke.forward_vx,
                timeout_s=video_profile.smoke.forward_timeout_sec,
            )
            report["checks"]["forward_drive"] = {"ok": dist >= 0.25, "distance_m": round(dist, 3)}
        else:
            report["checks"]["rotate_360"] = {"ok": False, "reason": "missing_base_pose"}
            report["checks"]["forward_drive"] = {"ok": False, "reason": "missing_base_pose"}

        traj_id = int(time.time()) % 1000000
        done_file = send_pending_traj(
            proxy_dir,
            traj_id,
            [f"arm_{i}_joint" for i in range(1, 8)],
            contract.manip_probe_joint_targets,
            t=3.0,
        )
        if not wait_for(done_file, 120.0):
            report["checks"]["arm_extend"] = {"ok": False, "reason": "trajectory_timeout"}
        else:
            payload = json.loads(done_file.read_text(encoding="utf-8"))
            status = str(payload.get("status", "unknown"))
            report["checks"]["arm_extend"] = {"ok": status == "succeeded", "status": status}

        try:
            proc.wait(timeout=collector_duration)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=15)

        external_video = out_dir / "camera_2_external.mp4"
        fallback_video = out_dir / "camera_0.mp4"
        final_video = external_video if external_video.exists() and external_video.stat().st_size > 0 else fallback_video
        report["artifacts"]["camera_0_mp4"] = str(fallback_video)
        report["artifacts"]["camera_2_external_mp4"] = str(external_video)
        report["artifacts"]["final_video"] = str(final_video)
        report["checks"]["video_recorded"] = {"ok": final_video.exists() and final_video.stat().st_size > 0}
        report["status"] = "passed" if all(v.get("ok") is True for v in report["checks"].values()) else "failed"
    finally:
        stop_base(proxy_dir)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()

    report_path = out_dir / "presentation_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[Presentation] report: {report_path}")
    print(f"[Presentation] status: {report['status']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
