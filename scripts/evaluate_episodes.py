#!/usr/bin/env python3
"""
Evaluate episode quality and success rate for filtering training data.

Computes per-episode metrics and classifies each as SUCCESS / PARTIAL / FAIL
based on task-specific criteria. Outputs a report and optionally a filtered
episode list for HDF5 export.

Metrics computed:
  - arm_travel:        sum of absolute joint deltas across arm joints (rad)
  - gripper_delta:     max absolute change in gripper finger joints (m)
  - gripper_closed:    whether gripper closed (finger joints decreased)
  - object_max_dxy:    max horizontal displacement of any tracked object (m)
  - object_max_dz:     max vertical displacement of any tracked object (m)
  - object_fell:       any object dropped below z=0 (fell off table)
  - n_frames:          total frames recorded
  - duration_sec:      episode duration from timestamps
  - fps:               effective capture rate
  - arm_idle_ratio:    fraction of frames where arm barely moved

Usage:
  python scripts/evaluate_episodes.py
  python scripts/evaluate_episodes.py --episodes-dir D:\\data\\episodes --min-quality partial
  python scripts/evaluate_episodes.py --export-list good_episodes.txt --min-quality success
"""

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EpisodeMetrics:
    episode_id: str = ""
    scene: str = ""
    task: str = ""
    n_frames: int = 0
    duration_sec: float = 0.0
    fps: float = 0.0

    arm_travel: float = 0.0
    arm_left_travel: float = 0.0
    gripper_delta: float = 0.0
    gripper_closed: bool = False
    gripper_opened: bool = False

    object_count: int = 0
    graspable_count: int = 0
    object_max_dxy: float = 0.0
    object_max_dz: float = 0.0
    object_lifted: bool = False
    object_fell: bool = False
    objects_moved: int = 0
    furniture_unstable: int = 0

    base_travel: float = 0.0
    arm_idle_ratio: float = 0.0

    quality: str = "UNKNOWN"
    reasons: list = field(default_factory=list)


ARM_RIGHT_JOINTS = [
    "arm_1_joint", "arm_2_joint", "arm_3_joint", "arm_4_joint",
    "arm_5_joint", "arm_6_joint", "arm_7_joint",
]
ARM_LEFT_JOINTS = [
    "arm_left_1_joint", "arm_left_2_joint", "arm_left_3_joint",
    "arm_left_4_joint", "arm_left_5_joint", "arm_left_6_joint",
    "arm_left_7_joint",
]
GRIPPER_JOINTS = [
    "gripper_left_left_finger_joint", "gripper_left_right_finger_joint",
    "gripper_right_left_finger_joint", "gripper_right_right_finger_joint",
]

# Thresholds
MIN_ARM_TRAVEL = 0.5        # rad — arm barely moved below this
MIN_FRAMES = 50
MIN_DURATION = 2.0          # seconds
OBJECT_MOVE_THRESH = 0.03   # m — object considered moved
OBJECT_LIFT_THRESH = 0.05   # m — object considered lifted
OBJECT_FELL_THRESH = -0.1   # m — object fell below spawn height
GRIPPER_CLOSE_THRESH = 0.01 # m — gripper closed if delta > this
ARM_IDLE_FRAME_THRESH = 0.001  # rad — per-frame arm movement threshold


def load_episode_data(ep_dir: Path) -> dict | None:
    ds_path = ep_dir / "dataset.json"
    if not ds_path.exists():
        return None
    try:
        return json.loads(ds_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_task_from_metadata(ep_dir: Path) -> str:
    for enc in ("utf-8-sig", "utf-8"):
        meta_path = ep_dir / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding=enc))
                tasks = meta.get("tasks", "")
                if isinstance(tasks, list) and tasks:
                    return tasks[0] if len(tasks) == 1 else json.dumps(tasks)
                if isinstance(tasks, str) and tasks and tasks != "[]":
                    return tasks
            except Exception:
                continue
    return ""


def get_scene_from_metadata(ep_dir: Path, dataset: dict) -> str:
    for enc in ("utf-8-sig", "utf-8"):
        meta_path = ep_dir / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding=enc))
                scene = meta.get("scene", {})
                if isinstance(scene, dict) and scene.get("name"):
                    return scene["name"]
                if isinstance(scene, str) and scene:
                    return scene
            except Exception:
                continue
    env_usd = dataset.get("metadata", {}).get("environment_usd", "")
    if env_usd:
        return Path(env_usd).stem
    return "unknown"


def compute_metrics(ep_dir: Path, dataset: dict) -> EpisodeMetrics:
    m = EpisodeMetrics()
    m.episode_id = ep_dir.name
    m.scene = get_scene_from_metadata(ep_dir, dataset)
    m.task = get_task_from_metadata(ep_dir)

    frames = dataset.get("frames", [])
    m.n_frames = len(frames)
    if m.n_frames < 2:
        m.quality = "FAIL"
        m.reasons.append("too_few_frames")
        return m

    timestamps = [f.get("timestamp", 0.0) for f in frames]
    m.duration_sec = timestamps[-1] - timestamps[0]
    m.fps = m.n_frames / m.duration_sec if m.duration_sec > 0 else 0.0

    # Arm travel: sum of absolute joint position changes between consecutive frames
    arm_travel_r = 0.0
    arm_travel_l = 0.0
    idle_frames = 0

    for i in range(1, len(frames)):
        rj_prev = frames[i - 1].get("robot_joints", {})
        rj_curr = frames[i].get("robot_joints", {})
        frame_delta = 0.0

        for j in ARM_RIGHT_JOINTS:
            p0 = rj_prev.get(j, {}).get("position", 0.0)
            p1 = rj_curr.get(j, {}).get("position", 0.0)
            d = abs(p1 - p0)
            arm_travel_r += d
            frame_delta += d

        for j in ARM_LEFT_JOINTS:
            p0 = rj_prev.get(j, {}).get("position", 0.0)
            p1 = rj_curr.get(j, {}).get("position", 0.0)
            arm_travel_l += abs(p1 - p0)

        if frame_delta < ARM_IDLE_FRAME_THRESH:
            idle_frames += 1

    m.arm_travel = arm_travel_r
    m.arm_left_travel = arm_travel_l
    m.arm_idle_ratio = idle_frames / (len(frames) - 1) if len(frames) > 1 else 1.0

    # Gripper analysis: compare first and last frame
    rj0 = frames[0].get("robot_joints", {})
    rjN = frames[-1].get("robot_joints", {})
    max_g_delta = 0.0
    for gj in GRIPPER_JOINTS:
        g0 = rj0.get(gj, {}).get("position", 0.0)
        gN = rjN.get(gj, {}).get("position", 0.0)
        d = gN - g0
        max_g_delta = max(max_g_delta, abs(d))
        if d < -GRIPPER_CLOSE_THRESH:
            m.gripper_closed = True
        if d > GRIPPER_CLOSE_THRESH:
            m.gripper_opened = True
    m.gripper_delta = max_g_delta

    # Also check mid-episode for open→close→open pattern (pick and place)
    mid = len(frames) // 2
    rj_mid = frames[mid].get("robot_joints", {})
    for gj in GRIPPER_JOINTS:
        g0 = rj0.get(gj, {}).get("position", 0.0)
        gM = rj_mid.get(gj, {}).get("position", 0.0)
        gN = rjN.get(gj, {}).get("position", 0.0)
        if g0 > gM + GRIPPER_CLOSE_THRESH and gN > gM + GRIPPER_CLOSE_THRESH:
            m.gripper_closed = True
            m.gripper_opened = True

    # Object displacement — separate graspable objects from furniture.
    # Furniture (fridge, table, sink, etc.) is environment geometry that
    # may have unstable physics but should NOT cause episode failure.
    _FURNITURE_KEYWORDS = frozenset((
        "fridge", "refrigerator", "dishwasher", "sink", "counter", "table",
        "shelf", "cabinet", "oven", "microwave", "door", "wall", "floor",
        "ceiling", "tiago", "light", "lamp",
    ))

    def _is_furniture(prim_path: str, obj_class: str) -> bool:
        """True if this is environment furniture, not a graspable object."""
        if "/GraspableObjects/" in prim_path:
            return False
        if "/Environment/" in prim_path:
            return True
        name_low = prim_path.split("/")[-1].lower()
        cls_low = obj_class.lower()
        return any(kw in name_low or kw in cls_low for kw in _FURNITURE_KEYWORDS)

    wp0 = frames[0].get("world_poses", {})
    wpN = frames[-1].get("world_poses", {})
    m.object_count = len(wp0)

    for key in wp0:
        p0 = wp0[key].get("position", [0, 0, 0])
        pN = wpN.get(key, {}).get("position", [0, 0, 0])
        obj_class = wp0[key].get("class", "")
        dxy = math.sqrt((pN[0] - p0[0]) ** 2 + (pN[1] - p0[1]) ** 2)
        dz = pN[2] - p0[2]

        is_furn = _is_furniture(key, obj_class)

        if is_furn:
            if abs(dz) > 0.1 or dxy > 0.1:
                m.furniture_unstable += 1
            continue

        m.graspable_count += 1
        m.object_max_dxy = max(m.object_max_dxy, dxy)
        m.object_max_dz = max(m.object_max_dz, abs(dz))
        if dxy > OBJECT_MOVE_THRESH or abs(dz) > OBJECT_MOVE_THRESH:
            m.objects_moved += 1
        if dz > OBJECT_LIFT_THRESH:
            m.object_lifted = True
        if pN[2] < OBJECT_FELL_THRESH:
            m.object_fell = True

    # Base travel
    rp0 = frames[0].get("robot_pose", {}).get("position", [0, 0, 0])
    rpN = frames[-1].get("robot_pose", {}).get("position", [0, 0, 0])
    m.base_travel = math.sqrt(
        (rpN[0] - rp0[0]) ** 2 + (rpN[1] - rp0[1]) ** 2
    )

    return m


def classify_episode(m: EpisodeMetrics) -> EpisodeMetrics:
    """Classify episode quality based on metrics and task type."""
    reasons = []

    # Universal fail conditions
    if m.n_frames < MIN_FRAMES:
        reasons.append("too_few_frames")
    if m.duration_sec < MIN_DURATION:
        reasons.append("too_short")
    if m.object_fell:
        reasons.append("graspable_object_fell")
    if m.furniture_unstable > 0:
        reasons.append(f"furniture_unstable({m.furniture_unstable})")

    task = m.task.strip('"').strip("'").strip("$").strip('"')

    if task.startswith("plan_pick"):
        # Pick tasks: arm should move, gripper should close, ideally object lifts
        if m.arm_travel < MIN_ARM_TRAVEL:
            reasons.append("arm_barely_moved")
        if m.gripper_closed and m.object_lifted:
            pass  # full success
        elif m.gripper_closed:
            reasons.append("gripper_closed_but_no_lift")
        elif m.arm_travel >= MIN_ARM_TRAVEL:
            reasons.append("arm_moved_but_no_grasp")
        else:
            reasons.append("no_manipulation")

    elif task.startswith("open_close"):
        # Open/close: arm should move substantially
        if m.arm_travel < MIN_ARM_TRAVEL:
            reasons.append("arm_barely_moved")
        if m.arm_idle_ratio > 0.9:
            reasons.append("mostly_idle")

    elif task.startswith("nav_"):
        # Navigation: base should move
        if m.base_travel < 0.1:
            reasons.append("base_barely_moved")

    elif task.startswith("bimanual"):
        if m.arm_travel < MIN_ARM_TRAVEL and m.arm_left_travel < MIN_ARM_TRAVEL:
            reasons.append("arms_barely_moved")

    else:
        # Generic / unlabeled episodes
        if m.arm_travel < MIN_ARM_TRAVEL and m.base_travel < 0.05:
            reasons.append("no_activity")

    m.reasons = reasons

    fail_reasons = {"too_few_frames", "too_short", "graspable_object_fell", "no_manipulation", "no_activity"}
    has_fail = bool(fail_reasons & set(reasons))
    has_warn = bool(set(reasons) - fail_reasons)

    if not reasons:
        m.quality = "SUCCESS"
    elif has_fail:
        m.quality = "FAIL"
    else:
        m.quality = "PARTIAL"

    return m


def main():
    parser = argparse.ArgumentParser(description="Evaluate episode quality and success rate")
    parser.add_argument(
        "--episodes-dir",
        default=r"C:\RoboLab_Data\episodes",
        help="Root directory containing episode subdirectories",
    )
    parser.add_argument(
        "--min-quality",
        choices=["success", "partial", "fail", "all"],
        default="all",
        help="Minimum quality to include in export list",
    )
    parser.add_argument(
        "--export-list",
        type=str,
        default="",
        help="Write filtered episode IDs to this file (one per line)",
    )
    parser.add_argument(
        "--json-report",
        type=str,
        default="",
        help="Write full metrics as JSON to this file",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=0,
        help="Only evaluate the N most recent episodes",
    )
    args = parser.parse_args()

    ep_root = Path(args.episodes_dir)
    if not ep_root.exists():
        print(f"ERROR: {ep_root} not found")
        sys.exit(1)

    ep_dirs = sorted(
        [d for d in ep_root.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if args.last > 0:
        ep_dirs = ep_dirs[: args.last]
    ep_dirs.sort(key=lambda d: d.stat().st_mtime)

    print(f"Evaluating {len(ep_dirs)} episodes from {ep_root}\n")

    results: list[EpisodeMetrics] = []
    counts = {"SUCCESS": 0, "PARTIAL": 0, "FAIL": 0}

    for i, ep_dir in enumerate(ep_dirs, 1):
        dataset = load_episode_data(ep_dir)
        if dataset is None:
            print(f"[{i:>3}] SKIP {ep_dir.name[:12]}.. (no data)")
            continue

        m = compute_metrics(ep_dir, dataset)
        m = classify_episode(m)
        results.append(m)
        counts[m.quality] = counts.get(m.quality, 0) + 1

        status_color = {"SUCCESS": "", "PARTIAL": "", "FAIL": ""}
        reasons_str = ", ".join(m.reasons) if m.reasons else "-"
        print(
            f"[{i:>3}] {m.quality:<8s} {m.episode_id[:12]}.. | "
            f"{m.n_frames:>5} fr | "
            f"arm={m.arm_travel:>6.1f}r | "
            f"grip={m.gripper_delta:>.3f} | "
            f"obj={m.graspable_count} dxy={m.object_max_dxy:>.3f} dz={m.object_max_dz:>.3f} | "
            f"furn={m.furniture_unstable} | "
            f"{reasons_str}"
        )

    total = len(results)
    print(f"\n{'=' * 80}")
    print(f"SUMMARY: {total} episodes evaluated")
    print(f"  SUCCESS: {counts.get('SUCCESS', 0):>4} ({counts.get('SUCCESS', 0) / total * 100:.1f}%)" if total else "")
    print(f"  PARTIAL: {counts.get('PARTIAL', 0):>4} ({counts.get('PARTIAL', 0) / total * 100:.1f}%)" if total else "")
    print(f"  FAIL:    {counts.get('FAIL', 0):>4} ({counts.get('FAIL', 0) / total * 100:.1f}%)" if total else "")
    print(f"{'=' * 80}")

    # Breakdown by scene
    scene_counts: dict[str, dict] = {}
    for m in results:
        if m.scene not in scene_counts:
            scene_counts[m.scene] = {"SUCCESS": 0, "PARTIAL": 0, "FAIL": 0, "total": 0}
        scene_counts[m.scene][m.quality] += 1
        scene_counts[m.scene]["total"] += 1
    print("\nBy scene:")
    for scene, sc in sorted(scene_counts.items()):
        sr = sc["SUCCESS"] / sc["total"] * 100 if sc["total"] > 0 else 0
        print(f"  {scene:<35s}: {sc['total']:>3} eps | {sc['SUCCESS']} ok / {sc['PARTIAL']} partial / {sc['FAIL']} fail | SR={sr:.0f}%")

    # Breakdown by task
    task_counts: dict[str, dict] = {}
    for m in results:
        t = m.task or "(unlabeled)"
        if t not in task_counts:
            task_counts[t] = {"SUCCESS": 0, "PARTIAL": 0, "FAIL": 0, "total": 0}
        task_counts[t][m.quality] += 1
        task_counts[t]["total"] += 1
    print("\nBy task:")
    for task, tc in sorted(task_counts.items()):
        sr = tc["SUCCESS"] / tc["total"] * 100 if tc["total"] > 0 else 0
        print(f"  {task:<35s}: {tc['total']:>3} eps | {tc['SUCCESS']} ok / {tc['PARTIAL']} partial / {tc['FAIL']} fail | SR={sr:.0f}%")

    # Common failure reasons
    reason_counts: dict[str, int] = {}
    for m in results:
        for r in m.reasons:
            reason_counts[r] = reason_counts.get(r, 0) + 1
    if reason_counts:
        print("\nFailure/warning reasons:")
        for reason, cnt in sorted(reason_counts.items(), key=lambda x: -x[1]):
            print(f"  {reason:<30s}: {cnt}")

    # Export filtered list
    quality_rank = {"SUCCESS": 3, "PARTIAL": 2, "FAIL": 1}
    min_rank = {"success": 3, "partial": 2, "fail": 1, "all": 0}[args.min_quality]
    filtered = [m for m in results if quality_rank.get(m.quality, 0) >= min_rank]

    if args.export_list:
        out = Path(args.export_list)
        out.write_text("\n".join(m.episode_id for m in filtered), encoding="utf-8")
        print(f"\nExported {len(filtered)} episode IDs to {out}")

    if args.json_report:
        report = []
        for m in results:
            report.append({
                "episode_id": m.episode_id,
                "scene": m.scene,
                "task": m.task,
                "quality": m.quality,
                "n_frames": m.n_frames,
                "duration_sec": round(m.duration_sec, 2),
                "fps": round(m.fps, 1),
                "arm_travel": round(m.arm_travel, 3),
                "arm_left_travel": round(m.arm_left_travel, 3),
                "gripper_delta": round(m.gripper_delta, 4),
                "gripper_closed": m.gripper_closed,
                "gripper_opened": m.gripper_opened,
                "object_count": m.object_count,
                "graspable_count": m.graspable_count,
                "object_max_dxy": round(m.object_max_dxy, 4),
                "object_max_dz": round(m.object_max_dz, 4),
                "object_lifted": m.object_lifted,
                "object_fell": m.object_fell,
                "objects_moved": m.objects_moved,
                "furniture_unstable": m.furniture_unstable,
                "base_travel": round(m.base_travel, 4),
                "arm_idle_ratio": round(m.arm_idle_ratio, 3),
                "reasons": m.reasons,
            })
        Path(args.json_report).write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(f"JSON report: {args.json_report}")


if __name__ == "__main__":
    main()
