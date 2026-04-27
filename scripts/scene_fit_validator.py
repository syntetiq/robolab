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


def parse_args():
    p = argparse.ArgumentParser(description="Strict scene-fit validator (spawn/base/nav/manip/video).")
    p.add_argument("--scene-usd", required=True)
    p.add_argument("--isaac-python", default=r"C:\Users\max\Documents\IsaacSim\python.bat")
    p.add_argument("--output-root", default=r"C:\RoboLab_Data\episodes")
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--headless", action="store_true", default=True)
    p.add_argument("--manifest", default=str(Path(__file__).resolve().parents[1] / "config" / "scene_prep_manifest.json"))
    return p.parse_args()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
    # Fallback for transient Windows file locks.
    for attempt in range(8):
        try:
            target.write_text(body, encoding="utf-8")
            return
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))


def stop_base(proxy_dir: Path) -> None:
    write_base_cmd(proxy_dir, 0.0, 0.0, 0.0)


def send_pending_traj(proxy_dir: Path, traj_id: int, joint_names: list[str], positions: list[float], t: float = 3.0) -> Path:
    payload = {"traj_id": traj_id, "joint_names": joint_names, "points": [{"positions": positions, "t": float(t)}]}
    pending = proxy_dir / f"pending_{traj_id}.json"
    pending.write_text(json.dumps(payload), encoding="utf-8")
    return proxy_dir / f"done_{traj_id}.json"


def wait_for(path: Path, timeout_s: float) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        if path.exists():
            return True
        time.sleep(0.2)
    return False


def dist_xy(a: dict, b: dict) -> float:
    return ((float(a.get("x", 0.0)) - float(b.get("x", 0.0))) ** 2 + (float(a.get("y", 0.0)) - float(b.get("y", 0.0))) ** 2) ** 0.5


def rotate_360(proxy_dir: Path, base_pose_file: Path, timeout_s: float = 25.0) -> dict:
    start = read_base_pose(base_pose_file)
    if not start:
        return {"ok": False, "reason": "missing_base_pose", "yaw_accum_deg": 0.0}
    last = float(start.get("yaw_deg", 0.0))
    accum = 0.0
    end = time.time() + timeout_s
    while time.time() < end and accum < 340.0:
        write_base_cmd(proxy_dir, 0.0, 0.0, 0.55)
        time.sleep(0.1)
        cur = read_base_pose(base_pose_file)
        if not cur:
            continue
        yaw = float(cur.get("yaw_deg", last))
        delta = yaw - last
        if delta > 180:
            delta -= 360
        elif delta < -180:
            delta += 360
        accum += abs(delta)
        last = yaw
    stop_base(proxy_dir)
    return {"ok": accum >= 300.0, "yaw_accum_deg": round(accum, 2)}


def forward_probe(proxy_dir: Path, base_pose_file: Path, timeout_s: float = 20.0) -> dict:
    start = read_base_pose(base_pose_file)
    if not start:
        return {"ok": False, "reason": "missing_base_pose", "distance_m": 0.0}
    last_dist = 0.0
    blocked = False
    last_progress_t = time.time()
    end = time.time() + timeout_s
    while time.time() < end and last_dist < 1.0:
        write_base_cmd(proxy_dir, 0.18, 0.0, 0.0)
        time.sleep(0.12)
        cur = read_base_pose(base_pose_file)
        if not cur:
            continue
        d = dist_xy(cur, start)
        if d > last_dist + 0.01:
            last_dist = d
            last_progress_t = time.time()
        elif time.time() - last_progress_t > 2.0:
            blocked = True
            break
    stop_base(proxy_dir)
    ok = last_dist >= 0.8 or blocked
    return {"ok": ok, "distance_m": round(last_dist, 3), "blocked": blocked}


def nav_probe(proxy_dir: Path, base_pose_file: Path, targets: list[list[float]], timeout_per_target: float = 12.0) -> dict:
    if not targets:
        return {"ok": False, "reason": "no_nav_targets"}
    start = read_base_pose(base_pose_file)
    if not start:
        return {"ok": False, "reason": "missing_base_pose"}
    reached = 0
    details = []
    for tx, ty in targets:
        t_end = time.time() + timeout_per_target
        reached_this = False
        while time.time() < t_end:
            cur = read_base_pose(base_pose_file)
            if not cur:
                time.sleep(0.1)
                continue
            ex = float(tx) - float(cur.get("x", 0.0))
            ey = float(ty) - float(cur.get("y", 0.0))
            d = (ex * ex + ey * ey) ** 0.5
            if d < 0.18:
                reached_this = True
                break
            vx = max(-0.2, min(0.2, ex * 0.8))
            vy = max(-0.2, min(0.2, ey * 0.8))
            write_base_cmd(proxy_dir, vx, vy, 0.0)
            time.sleep(0.1)
        stop_base(proxy_dir)
        details.append({"target_xy": [tx, ty], "reached": reached_this})
        if reached_this:
            reached += 1
    return {"ok": reached >= max(1, len(targets) - 1), "reached": reached, "targets": details}


def manip_probe(proxy_dir: Path, joint_targets: list[float], timeout_s: float = 90.0) -> dict:
    traj_id = int(time.time()) % 1000000
    done_file = send_pending_traj(proxy_dir, traj_id, [f"arm_{i}_joint" for i in range(1, 8)], joint_targets, t=3.0)
    if not wait_for(done_file, timeout_s):
        return {"ok": False, "reason": "trajectory_timeout"}
    try:
        payload = json.loads(done_file.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "reason": "invalid_done_payload"}
    status = str(payload.get("status", "unknown"))
    return {"ok": status == "succeeded", "status": status, "error": str(payload.get("error", ""))}


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
    out_dir = Path(args.output_root) / f"scene_fit_{scene.stem}_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    proxy_dir = Path(r"C:\RoboLab_Data\fjt_proxy")
    proxy_dir.mkdir(parents=True, exist_ok=True)
    for pat in ("pending_*.json", "done_*.json"):
        for f in proxy_dir.glob(pat):
            f.unlink(missing_ok=True)
    for fn in ("joint_state.json", "base_cmd.json", "base_pose.json"):
        (proxy_dir / fn).unlink(missing_ok=True)

    collector_duration = max(int(args.duration) + 120, 180)
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
        "checks": {},
        "artifacts": {},
        "status": "failed",
    }

    proc = subprocess.Popen(cmd, env=env)
    launched_at = time.time()
    try:
        base_pose_file = proxy_dir / "base_pose.json"
        startup_timeout_s = max(120.0, float(args.duration) + 30.0)
        pose = wait_for_new_base_pose(base_pose_file, launched_at, startup_timeout_s)
        spawn_ok = pose is not None and (-0.15 <= float((pose or {}).get("z", 0.0)) <= 0.35)
        report["checks"]["spawn_clearance"] = {
            "ok": spawn_ok,
            "pose": pose or {},
            "reason": "" if spawn_ok else "base_pose_missing_or_invalid_z",
        }

        report["checks"]["base_motion"] = rotate_360(proxy_dir, base_pose_file)
        report["checks"]["forward_probe"] = forward_probe(proxy_dir, base_pose_file)
        report["checks"]["nav_probe"] = nav_probe(proxy_dir, base_pose_file, contract.nav_probe_targets)
        report["checks"]["manip_probe"] = manip_probe(
            proxy_dir,
            contract.manip_probe_joint_targets,
            timeout_s=120.0,
        )

        try:
            proc.wait(timeout=max(20, collector_duration))
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=10)

        video = out_dir / "camera_0.mp4"
        report["artifacts"]["camera_0_mp4"] = str(video)
        report["checks"]["video_recorded"] = {"ok": video.exists() and video.stat().st_size > 0}

        all_ok = all(v.get("ok") is True for v in report["checks"].values())
        report["status"] = "passed" if all_ok else "failed"
    finally:
        stop_base(proxy_dir)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()

    report_file = out_dir / "scene_fit_report.json"
    write_json(report_file, report)
    print(f"[SceneFit] report: {report_file}")
    print(f"[SceneFit] status: {report['status']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
