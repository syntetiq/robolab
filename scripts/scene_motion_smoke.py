"""
Run motion smoke test in a single scene and record video.

Sequence:
1) Spawn robot in scene.
2) Rotate 360 deg.
3) Drive forward up to 1m (stop early if movement stalls / likely obstacle).
4) Extend right arm forward via pending trajectory IPC.
5) Ensure camera_0.mp4 is produced.
"""

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
    p = argparse.ArgumentParser(description="Scene motion smoke + video capture")
    p.add_argument("--scene-usd", required=True, help="Absolute path to scene USD/USDA/USDZ")
    p.add_argument("--isaac-python", default=r"C:\Users\max\Documents\IsaacSim\python.bat")
    p.add_argument("--output-root", default=r"C:\RoboLab_Data\episodes")
    p.add_argument("--duration", type=int, default=90)
    p.add_argument("--headless", action="store_true", default=True)
    p.add_argument("--manifest", default=str(Path(__file__).resolve().parents[1] / "config" / "scene_prep_manifest.json"))
    return p.parse_args()


def wait_for(path: Path, timeout_s: float) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        if path.exists():
            return True
        time.sleep(0.2)
    return False


def wait_for_new_base_pose(base_pose_file: Path, launched_at: float, timeout_s: float) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        if base_pose_file.exists():
            try:
                # Ensure this pose file was written by the current collector process.
                if base_pose_file.stat().st_mtime >= launched_at:
                    pose = json.loads(base_pose_file.read_text(encoding="utf-8"))
                    if float(pose.get("t", 0.0)) > launched_at - 1.0:
                        return True
            except Exception:
                pass
        time.sleep(0.2)
    return False


def read_base_pose(base_pose_file: Path) -> dict | None:
    try:
        return json.loads(base_pose_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_base_cmd(proxy_dir: Path, vx: float, vy: float, vyaw: float) -> None:
    payload = {"vx": float(vx), "vy": float(vy), "vyaw": float(vyaw), "stamp": time.time()}
    tmp = proxy_dir / "base_cmd.tmp"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(proxy_dir / "base_cmd.json")


def send_pending_traj(proxy_dir: Path, traj_id: int, joint_names: list[str], positions: list[float], t: float = 2.0) -> Path:
    payload = {
        "traj_id": traj_id,
        "joint_names": joint_names,
        "points": [{"positions": positions, "t": float(t)}],
    }
    pending = proxy_dir / f"pending_{traj_id}.json"
    pending.write_text(json.dumps(payload), encoding="utf-8")
    return proxy_dir / f"done_{traj_id}.json"


def rotate_360(proxy_dir: Path, base_pose_file: Path, omega: float = 0.55, timeout_s: float = 20.0) -> float:
    if not wait_for(base_pose_file, 15.0):
        return 0.0

    start = read_base_pose(base_pose_file)
    if not start:
        return 0.0
    start_yaw = float(start.get("yaw_deg", 0.0))
    accumulated = 0.0
    last_yaw = start_yaw
    t_end = time.time() + timeout_s
    while time.time() < t_end and accumulated < 355.0:
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
        accumulated += abs(delta)
        last_yaw = yaw
    write_base_cmd(proxy_dir, 0.0, 0.0, 0.0)
    return accumulated


def drive_forward_if_clear(proxy_dir: Path, base_pose_file: Path, max_dist_m: float = 1.0, vx: float = 0.18, timeout_s: float = 20.0) -> float:
    if not wait_for(base_pose_file, 5.0):
        return 0.0
    start = read_base_pose(base_pose_file)
    if not start:
        return 0.0
    x0 = float(start.get("x", 0.0))
    y0 = float(start.get("y", 0.0))
    last_progress_t = time.time()
    last_dist = 0.0
    t_end = time.time() + timeout_s
    while time.time() < t_end and last_dist < max_dist_m:
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
            # likely blocked by obstacle
            break
    write_base_cmd(proxy_dir, 0.0, 0.0, 0.0)
    return last_dist


def command_base_for_duration(proxy_dir: Path, vx: float, vy: float, vyaw: float, duration_s: float) -> None:
    t_end = time.time() + max(0.1, duration_s)
    while time.time() < t_end:
        write_base_cmd(proxy_dir, vx, vy, vyaw)
        time.sleep(0.1)
    write_base_cmd(proxy_dir, 0.0, 0.0, 0.0)


def main() -> int:
    args = parse_args()
    scene = Path(args.scene_usd)
    if not scene.exists():
        print(f"[FAIL] Scene not found: {scene}")
        return 2
    isaac_python = Path(args.isaac_python)
    if not isaac_python.exists():
        print(f"[FAIL] Isaac python not found: {isaac_python}")
        return 2

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    run_name = f"scene_smoke_{scene.stem}_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir = output_root / run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    contract = resolve_scene_prep_contract(scene.name, manifest_path=Path(args.manifest))

    proxy_dir = Path(r"C:\RoboLab_Data\fjt_proxy")
    proxy_dir.mkdir(parents=True, exist_ok=True)
    for pat in ("pending_*.json", "done_*.json"):
        for f in proxy_dir.glob(pat):
            f.unlink(missing_ok=True)
    for fn in ("joint_state.json", "base_cmd.json", "base_pose.json"):
        (proxy_dir / fn).unlink(missing_ok=True)

    cmd = [
        str(isaac_python),
        str(Path(__file__).with_name("data_collector_tiago.py")),
        "--env", str(scene),
        "--output_dir", str(out_dir),
        "--duration", str(int(args.duration)),
        "--moveit",
        "--mobile-base",
    ]
    if args.headless:
        cmd.append("--headless")

    env = os.environ.copy()
    env["ROS_DOMAIN_ID"] = env.get("ROS_DOMAIN_ID", "77")
    env["ROS_LOCALHOST_ONLY"] = env.get("ROS_LOCALHOST_ONLY", "1")
    env["FJT_PROXY_DIR"] = str(proxy_dir)

    print(f"[INFO] Launching collector: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, env=env)
    launched_at = time.time()

    base_pose_file = proxy_dir / "base_pose.json"
    done_ok = False
    try:
        base_pose_ready = wait_for_new_base_pose(base_pose_file, launched_at, 75.0)
        if not base_pose_ready:
            print("[WARN] base_pose.json not ready in time; skipping base motion checks.")
            # Fallback: still command the requested maneuver sequence even without pose feedback.
            command_base_for_duration(proxy_dir, 0.0, 0.0, 0.55, 11.5)  # ~360 deg
            command_base_for_duration(proxy_dir, 0.18, 0.0, 0.0, 5.6)   # ~1m
        else:
            yaw_accum = rotate_360(proxy_dir, base_pose_file)
            print(f"[INFO] rotate accumulated yaw: {yaw_accum:.1f} deg")
            dist = drive_forward_if_clear(proxy_dir, base_pose_file, max_dist_m=1.0)
            print(f"[INFO] forward progress: {dist:.3f} m")

        # Extend right arm forward (safe single-point trajectory).
        joint_names = [f"arm_{i}_joint" for i in range(1, 8)]
        positions = contract.manip_probe_joint_targets
        traj_id = int(time.time()) % 1_000_000
        done_file = send_pending_traj(proxy_dir, traj_id, joint_names, positions, t=2.0)
        if not wait_for(done_file, 30.0):
            print("[WARN] arm trajectory done file not received in time")
        else:
            res = json.loads(done_file.read_text(encoding="utf-8"))
            print(f"[INFO] arm trajectory status: {res.get('status')}")

        # allow a few extra seconds for video encoding and graceful shutdown
        try:
            proc.wait(timeout=max(10, int(args.duration)))
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

        video = out_dir / "camera_0.mp4"
        if video.exists() and video.stat().st_size > 0:
            done_ok = True
            print(f"[OK] video saved: {video}")
        else:
            print(f"[FAIL] video missing: {video}")
            return 4
    finally:
        write_base_cmd(proxy_dir, 0.0, 0.0, 0.0)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
        # copy scene path for quick audit
        (out_dir / "scene_path.txt").write_text(str(scene), encoding="utf-8")

    return 0 if done_ok else 1


if __name__ == "__main__":
    sys.exit(main())
