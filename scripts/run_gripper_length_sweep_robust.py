import argparse
import csv
import json
import random
import subprocess
import time
from pathlib import Path


def read_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_kill_tree(pid: int) -> None:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def run_one(
    repo: Path,
    run_bench: Path,
    isaac_python: str,
    out_dir: Path,
    cfg: dict,
    mode: str,
    gripper_len_m: float,
    mug_x: float,
    mug_y: float,
    timeout_sec: int,
) -> dict:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(run_bench),
        "-Grasp",
        "-NoVideo",
        "-Fast",
        "-Output",
        str(out_dir),
        "-IsaacPython",
        isaac_python,
        "-Duration",
        str(cfg.get("duration_s_fast", 55.0)),
        "-MugX",
        f"{mug_x:.6f}",
        "-MugY",
        f"{mug_y:.6f}",
        "-PlaceDx",
        str(cfg.get("place_dx", 0.0)),
        "-PlaceDy",
        str(cfg.get("place_dy", -0.2)),
        "-LiftHeight",
        str(cfg.get("lift_height", 0.2)),
        "-TorsoSpeed",
        str(cfg.get("torso_speed", 0.05)),
        "-TorsoLowerSpeed",
        str(cfg.get("torso_lower_speed", 0.02)),
        "-ShiftRotSpeed",
        str(cfg.get("shift_rot_speed", 0.15)),
        "-DriveSpeed",
        str(cfg.get("drive_speed", 0.12)),
        "-ApproachClearance",
        str(cfg.get("approach_clearance", 0.01)),
        "-GraspMode",
        mode,
        "-TopPregraspHeight",
        str(cfg.get("top_pregrasp_height", 0.06)),
        "-TopDescendSpeed",
        str(cfg.get("top_descend_speed", 0.015)),
        "-TopDescendClearance",
        str(cfg.get("top_descend_clearance", 0.045)),
        "-TopXyTol",
        str(cfg.get("top_xy_tol", 0.01)),
        "-TopLiftTestHeight",
        str(cfg.get("top_lift_test_height", 0.03)),
        "-TopLiftTestHold",
        str(cfg.get("top_lift_test_hold_s", 0.5)),
        "-TopRetryYStep",
        str(cfg.get("top_retry_y_step", 0.008)),
        "-TopRetryZStep",
        str(cfg.get("top_retry_z_step", 0.008)),
        "-TopMaxRetries",
        str(cfg.get("top_max_retries", 2)),
        "-GripperLengthM",
        str(gripper_len_m),
    ]

    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=str(repo))
    timed_out = False
    exit_code = -1
    try:
        exit_code = proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        timed_out = True
        safe_kill_tree(proc.pid)
        exit_code = -9
    wall = round(time.time() - t0, 2)

    log_path = out_dir / "heavy" / "physics_log.json"
    if timed_out:
        return {
            "success": False,
            "retries": -1,
            "retries_top": -1,
            "retries_side": -1,
            "mode_final": "timeout",
            "fallback_used": False,
            "lift_delta_m": 0.0,
            "final_tilt_deg": 0.0,
            "fail_code": "timeout",
            "wall_time_s": wall,
            "exit_code": exit_code,
        }
    if exit_code != 0:
        return {
            "success": False,
            "retries": -1,
            "retries_top": -1,
            "retries_side": -1,
            "mode_final": "bench_error",
            "fallback_used": False,
            "lift_delta_m": 0.0,
            "final_tilt_deg": 0.0,
            "fail_code": f"bench_exit_{exit_code}",
            "wall_time_s": wall,
            "exit_code": exit_code,
        }
    if not log_path.exists():
        return {
            "success": False,
            "retries": -1,
            "retries_top": -1,
            "retries_side": -1,
            "mode_final": "missing_log",
            "fallback_used": False,
            "lift_delta_m": 0.0,
            "final_tilt_deg": 0.0,
            "fail_code": "missing_log",
            "wall_time_s": wall,
            "exit_code": exit_code,
        }

    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
        rep = payload.get("report", {})
    except Exception:
        rep = {}
    return {
        "success": bool(rep.get("grasp_success", False)),
        "retries": int(rep.get("grasp_retry_count", -1)),
        "retries_top": int(rep.get("grasp_retry_count_top", -1)),
        "retries_side": int(rep.get("grasp_retry_count_side", -1)),
        "mode_final": str(rep.get("grasp_active_mode_final", "")),
        "fallback_used": bool(rep.get("grasp_fallback_used", False)),
        "lift_delta_m": float(rep.get("grasp_lift_delta_m", 0.0)),
        "final_tilt_deg": float(rep.get("grasp_final_tilt_deg", 0.0)),
        "fail_code": "" if bool(rep.get("grasp_success", False)) else str(rep.get("verdict", "fail")),
        "wall_time_s": wall,
        "exit_code": exit_code,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lengths", default="0.05,0.08,0.10,0.11,0.12,0.13,0.14")
    ap.add_argument("--runs-per-length", type=int, default=10)
    ap.add_argument("--grasp-mode", choices=["top", "side", "auto"], default="side")
    ap.add_argument("--jitter-xy", type=float, default=0.015)
    ap.add_argument("--timeout-sec", type=int, default=420)
    ap.add_argument("--repo", default=r"C:\Users\max\Documents\Cursor\robolab")
    ap.add_argument("--output-root", default=r"C:\RoboLab_Data\gripper_length_sweep")
    ap.add_argument("--config", default=r"C:\Users\max\Documents\Cursor\robolab\config\grasp_tuning.json")
    ap.add_argument("--isaac-python", default=r"C:\Users\max\Documents\IsaacSim\python.bat")
    args = ap.parse_args()

    repo = Path(args.repo)
    run_bench = repo / "scripts" / "run_bench.ps1"
    cfg = read_config(Path(args.config))
    lengths = [float(s.strip()) for s in args.lengths.split(",") if s.strip()]

    stamp = time.strftime("%Y%m%d_%H%M%S")
    sweep_dir = Path(args.output_root) / f"sweep_robust_{stamp}"
    sweep_dir.mkdir(parents=True, exist_ok=True)
    print(f"[RobustSweep] Output root: {sweep_dir}")

    all_rows = []
    ranked_rows = []
    center_x = float(cfg.get("mug_x", 2.0))
    center_y = float(cfg.get("mug_y", 0.0))

    for idx, L in enumerate(lengths, start=1):
        print(f"[RobustSweep] [{idx}/{len(lengths)}] length={L:.3f} mode={args.grasp_mode}")
        l_dir = sweep_dir / f"length_{L:.3f}".replace(".", "_")
        l_dir.mkdir(parents=True, exist_ok=True)
        length_rows = []
        succ = 0

        for run_i in range(1, args.runs_per_length + 1):
            dx = random.uniform(-args.jitter_xy, args.jitter_xy)
            dy = random.uniform(-args.jitter_xy, args.jitter_xy)
            mug_x = center_x + dx
            mug_y = center_y + dy
            run_name = f"run_{run_i:03d}"
            out_dir = l_dir / run_name
            out_dir.mkdir(parents=True, exist_ok=True)
            print(f"  [{run_i}/{args.runs_per_length}] mug=({mug_x:.3f},{mug_y:.3f})")

            row = run_one(
                repo=repo,
                run_bench=run_bench,
                isaac_python=args.isaac_python,
                out_dir=out_dir,
                cfg=cfg,
                mode=args.grasp_mode,
                gripper_len_m=L,
                mug_x=mug_x,
                mug_y=mug_y,
                timeout_sec=args.timeout_sec,
            )
            row["run"] = run_name
            row["mug_x"] = round(mug_x, 4)
            row["mug_y"] = round(mug_y, 4)
            row["gripper_length_m"] = L
            length_rows.append(row)
            all_rows.append(row)
            if row["success"]:
                succ += 1
            print(
                f"    -> success={row['success']} retries={row['retries']} "
                f"lift={row['lift_delta_m']:.4f} fail={row['fail_code']}"
            )

        success_rate = round(100.0 * succ / max(1, args.runs_per_length), 2)
        avg_retries = round(sum(r["retries"] for r in length_rows if r["retries"] >= 0) / max(1, len([r for r in length_rows if r["retries"] >= 0])), 3)
        avg_lift = round(sum(r["lift_delta_m"] for r in length_rows) / max(1, len(length_rows)), 4)
        timeout_count = sum(1 for r in length_rows if r["fail_code"] == "timeout")
        ranked_rows.append({
            "gripper_length_m": L,
            "runs": args.runs_per_length,
            "success_count": succ,
            "success_rate_percent": success_rate,
            "avg_retries": avg_retries,
            "avg_lift_delta_m": avg_lift,
            "timeout_count": timeout_count,
            "length_dir": str(l_dir),
        })

    ranked_rows.sort(key=lambda r: (-r["success_rate_percent"], r["avg_retries"], -r["avg_lift_delta_m"], r["timeout_count"]))

    details_csv = sweep_dir / "robust_sweep_details.csv"
    ranked_csv = sweep_dir / "robust_sweep_ranked.csv"
    summary_txt = sweep_dir / "robust_sweep_summary.txt"
    summary_json = sweep_dir / "robust_sweep_results.json"

    if all_rows:
        with details_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            w.writerows(all_rows)

    if ranked_rows:
        with ranked_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(ranked_rows[0].keys()))
            w.writeheader()
            w.writerows(ranked_rows)

    payload = {
        "mode": args.grasp_mode,
        "runs_per_length": args.runs_per_length,
        "jitter_xy_m": args.jitter_xy,
        "timeout_sec": args.timeout_sec,
        "lengths": lengths,
        "ranked": ranked_rows,
    }
    summary_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "TIAGo Robust Gripper Length Sweep",
        "================================",
        f"mode: {args.grasp_mode}",
        f"runs_per_length: {args.runs_per_length}",
        f"jitter_xy_m: {args.jitter_xy}",
        f"timeout_sec: {args.timeout_sec}",
        f"lengths: {', '.join(f'{x:.3f}' for x in lengths)}",
        "",
        "Ranked:",
    ]
    for r in ranked_rows:
        lines.append(
            f"L={r['gripper_length_m']:.3f} | success={r['success_count']}/{r['runs']} "
            f"({r['success_rate_percent']}%) | avg_retries={r['avg_retries']} "
            f"| avg_lift={r['avg_lift_delta_m']} | timeouts={r['timeout_count']}"
        )
    lines.extend([
        "",
        f"details_csv: {details_csv}",
        f"ranked_csv: {ranked_csv}",
        f"json: {summary_json}",
    ])
    summary_txt.write_text("\n".join(lines), encoding="utf-8")
    print(f"[RobustSweep] Done. Summary: {summary_txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
