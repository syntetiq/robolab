#!/usr/bin/env python3
"""
Evaluate episode quality and success rate for filtering training data.

Computes per-episode metrics (arm travel, gripper state, object displacement,
grasp events timeline) and classifies each as PERFECT / SUCCESS / PARTIAL / FAIL.
Outputs a report with quality scores 0-100 and optionally a filtered episode list.

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

    # Grasp event metrics (from grasp_events.json)
    grasp_attempts: int = 0
    grasp_successes: int = 0
    grasp_success_rate: float = 0.0
    grip_duration_sec: float = 0.0
    lift_detected: bool = False
    object_dropped_during_transport: bool = False
    grasp_retries: int = 0
    grasp_phases: list = field(default_factory=list)

    # Per-frame grasp state metrics (from dataset.json grasp_state)
    max_gripper_gap: float = 0.0
    min_gripper_gap: float = 1.0
    frames_with_object: int = 0
    frames_object_stable: int = 0
    max_contact_force: float = 0.0
    frames_with_contact: int = 0

    # Composite quality score
    quality_score: int = 0

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
GRIPPER_CLOSE_THRESH = 0.003 # m — gripper closed if delta > this (calibrated from 50-ep analysis)
ARM_IDLE_FRAME_THRESH = 0.001  # rad — per-frame arm movement threshold


def load_grasp_events(ep_dir: Path) -> list:
    """Load grasp_events.json if present."""
    ge_path = ep_dir / "grasp_events.json"
    if not ge_path.exists():
        return []
    try:
        return json.loads(ge_path.read_text(encoding="utf-8"))
    except Exception:
        return []


def analyze_grasp_events(events: list, duration: float) -> dict:
    """Extract structured grasp metrics from the event log."""
    close_starts = [e for e in events if e.get("event") == "gripper_close_start"]
    confirms = [e for e in events if e.get("event") == "grasp_confirmed"]
    lifts = [e for e in events if e.get("event") == "lift_detected"]
    releases = [e for e in events if e.get("event") == "object_released"]

    grasp_attempts = len(close_starts)
    grasp_successes = len(confirms)

    grip_dur = 0.0
    for conf in confirms:
        conf_time = conf.get("time", 0.0)
        next_release = None
        for rel in releases:
            if rel.get("time", 0.0) > conf_time:
                next_release = rel
                break
        end_time = next_release["time"] if next_release else duration
        grip_dur += end_time - conf_time

    dropped = any(
        r.get("z") is not None and r["z"] < 0.3
        for r in releases
        if any(l.get("object") == r.get("object") for l in lifts)
    )

    phases = []
    for i, cs in enumerate(close_starts):
        phase = {"phase": i + 1, "close_frame": cs.get("frame", 0),
                 "close_time": cs.get("time", 0.0)}
        matching_confirm = next(
            (c for c in confirms if c.get("time", 0) >= cs.get("time", 0)), None)
        if matching_confirm:
            phase["confirmed"] = True
            phase["object"] = matching_confirm.get("object", "")
            phase["gap"] = matching_confirm.get("gap", 0)
            matching_lift = next(
                (l for l in lifts if l.get("object") == matching_confirm.get("object")
                 and l.get("time", 0) >= matching_confirm.get("time", 0)), None)
            if matching_lift:
                phase["lifted"] = True
                phase["lift_z"] = matching_lift.get("z", 0)
            else:
                phase["lifted"] = False
        else:
            phase["confirmed"] = False
        phases.append(phase)

    return {
        "grasp_attempts": grasp_attempts,
        "grasp_successes": grasp_successes,
        "grasp_success_rate": grasp_successes / grasp_attempts if grasp_attempts > 0 else 0.0,
        "grip_duration_sec": grip_dur,
        "lift_detected": len(lifts) > 0,
        "object_dropped_during_transport": dropped,
        "phases": phases,
    }


def analyze_frame_grasp_states(frames: list) -> dict:
    """Extract aggregate metrics from per-frame grasp_state fields."""
    max_gap = 0.0
    min_gap = 1.0
    frames_with_obj = 0
    frames_stable = 0
    max_contact_force = 0.0
    frames_with_contact = 0
    for f in frames:
        gs = f.get("grasp_state")
        if not gs:
            continue
        gap = gs.get("gripper_gap", 0.0)
        max_gap = max(max_gap, gap)
        min_gap = min(min_gap, gap)
        if gs.get("object_in_gripper"):
            frames_with_obj += 1
        if gs.get("gripped_object_stable"):
            frames_stable += 1
        cf = gs.get("contact_forces", {})
        lf = cf.get("left_finger", [0, 0, 0])
        rf = cf.get("right_finger", [0, 0, 0])
        total_force = sum(abs(v) for v in lf) + sum(abs(v) for v in rf)
        max_contact_force = max(max_contact_force, total_force)
        if gs.get("left_finger_contact") or gs.get("right_finger_contact"):
            frames_with_contact += 1
    return {
        "max_gripper_gap": max_gap,
        "min_gripper_gap": min_gap,
        "frames_with_object": frames_with_obj,
        "frames_object_stable": frames_stable,
        "max_contact_force": max_contact_force,
        "frames_with_contact": frames_with_contact,
    }


def compute_quality_score(m) -> int:
    """Compute a 0-100 quality score based on weighted metrics."""
    score = 0

    if m.n_frames >= MIN_FRAMES:
        score += 10
    if m.duration_sec >= MIN_DURATION:
        score += 5

    arm_score = min(m.arm_travel / 3.0, 1.0) * 15
    score += int(arm_score)

    if m.arm_idle_ratio < 0.5:
        score += 10
    elif m.arm_idle_ratio < 0.8:
        score += 5

    if m.gripper_closed:
        score += 10
    if m.gripper_opened:
        score += 5

    if m.grasp_successes > 0:
        score += 15
    if m.lift_detected:
        score += 10

    if m.grip_duration_sec > 1.0:
        score += 5
    if m.grip_duration_sec > 3.0:
        score += 5

    if m.frames_with_object > 0:
        hold_ratio = m.frames_object_stable / max(m.frames_with_object, 1)
        score += int(hold_ratio * 5)

    if m.max_contact_force > 0.1:
        score += 5

    if not m.object_fell:
        score += 5
    if not m.object_dropped_during_transport:
        score += 5

    if m.grasp_attempts > 0 and m.grasp_successes == m.grasp_attempts:
        score += 5
    elif m.grasp_attempts > 0 and m.grasp_success_rate >= 0.5:
        score += 2

    if m.objects_moved > 0:
        score += 5

    return min(score, 100)


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

    # Grasp events analysis
    grasp_events = load_grasp_events(ep_dir)
    if grasp_events:
        ge = analyze_grasp_events(grasp_events, m.duration_sec)
        m.grasp_attempts = ge["grasp_attempts"]
        m.grasp_successes = ge["grasp_successes"]
        m.grasp_success_rate = ge["grasp_success_rate"]
        m.grip_duration_sec = ge["grip_duration_sec"]
        m.lift_detected = ge["lift_detected"]
        m.object_dropped_during_transport = ge["object_dropped_during_transport"]
        m.grasp_phases = ge["phases"]

    # Per-frame grasp state analysis
    fgs = analyze_frame_grasp_states(frames)
    m.max_gripper_gap = fgs["max_gripper_gap"]
    m.min_gripper_gap = fgs["min_gripper_gap"]
    m.frames_with_object = fgs["frames_with_object"]
    m.frames_object_stable = fgs["frames_object_stable"]
    m.max_contact_force = fgs["max_contact_force"]
    m.frames_with_contact = fgs["frames_with_contact"]

    return m


def classify_episode(m: EpisodeMetrics) -> EpisodeMetrics:
    """Classify episode quality based on metrics and task type.

    Four-tier classification:
      PERFECT - task fully completed without retries, object stable throughout
      SUCCESS - task completed (possibly with retries)
      PARTIAL - some progress but incomplete (e.g. grasped but dropped)
      FAIL    - critical failure or no meaningful activity
    """
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
    if m.object_dropped_during_transport:
        reasons.append("dropped_during_transport")

    task = m.task.strip('"').strip("'").strip("$").strip('"')

    is_pick_task = task.startswith("plan_pick") or task.startswith("left_plan_pick")
    is_bimanual = task.startswith("bimanual")
    is_nav_pick = task.startswith("nav_pick")

    pick_perfect = False

    if is_pick_task or is_nav_pick:
        if m.arm_travel < MIN_ARM_TRAVEL:
            reasons.append("arm_barely_moved")
        if m.grasp_successes > 0 and m.lift_detected and not m.object_dropped_during_transport:
            if m.grasp_attempts == m.grasp_successes:
                pick_perfect = True
        elif m.gripper_closed and m.object_lifted:
            pass
        elif m.grasp_successes > 0:
            reasons.append("grasped_but_not_lifted")
        elif m.gripper_closed:
            reasons.append("gripper_closed_but_no_grasp")
        elif m.arm_travel >= MIN_ARM_TRAVEL:
            reasons.append("arm_moved_but_no_grasp")
        else:
            reasons.append("no_manipulation")

        if is_nav_pick and m.base_travel < 0.1:
            reasons.append("base_barely_moved")

    elif task.startswith("open_close"):
        if m.arm_travel < MIN_ARM_TRAVEL:
            reasons.append("arm_barely_moved")
        if m.arm_idle_ratio > 0.9:
            reasons.append("mostly_idle")

    elif task.startswith("nav_"):
        if m.base_travel < 0.1:
            reasons.append("base_barely_moved")

    elif is_bimanual:
        if m.arm_travel < MIN_ARM_TRAVEL and m.arm_left_travel < MIN_ARM_TRAVEL:
            reasons.append("arms_barely_moved")
        if m.grasp_successes > 0 and m.lift_detected and not m.object_dropped_during_transport:
            if m.grasp_attempts == m.grasp_successes:
                pick_perfect = True

    else:
        if m.arm_travel < MIN_ARM_TRAVEL and m.base_travel < 0.05:
            reasons.append("no_activity")

    m.reasons = reasons

    fail_reasons = {"too_few_frames", "too_short", "graspable_object_fell",
                    "no_manipulation", "no_activity"}
    has_fail = bool(fail_reasons & set(reasons))

    if not reasons and pick_perfect:
        m.quality = "PERFECT"
    elif not reasons:
        m.quality = "SUCCESS"
    elif has_fail:
        m.quality = "FAIL"
    else:
        m.quality = "PARTIAL"

    m.quality_score = compute_quality_score(m)

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
        choices=["perfect", "success", "partial", "fail", "all"],
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
    counts = {"PERFECT": 0, "SUCCESS": 0, "PARTIAL": 0, "FAIL": 0}

    for i, ep_dir in enumerate(ep_dirs, 1):
        dataset = load_episode_data(ep_dir)
        if dataset is None:
            print(f"[{i:>3}] SKIP {ep_dir.name[:12]}.. (no data)")
            continue

        m = compute_metrics(ep_dir, dataset)
        m = classify_episode(m)
        results.append(m)
        counts[m.quality] = counts.get(m.quality, 0) + 1

        reasons_str = ", ".join(m.reasons) if m.reasons else "-"
        grasp_info = ""
        if m.grasp_attempts > 0:
            grasp_info = f"grasp={m.grasp_successes}/{m.grasp_attempts} "
        print(
            f"[{i:>3}] {m.quality:<8s} Q={m.quality_score:>3} {m.episode_id[:12]}.. | "
            f"{m.n_frames:>5} fr | "
            f"arm={m.arm_travel:>6.1f}r | "
            f"grip={m.gripper_delta:>.3f} | "
            f"{grasp_info}"
            f"obj={m.graspable_count} dxy={m.object_max_dxy:>.3f} dz={m.object_max_dz:>.3f} | "
            f"furn={m.furniture_unstable} | "
            f"{reasons_str}"
        )

    total = len(results)
    avg_score = sum(m.quality_score for m in results) / total if total else 0
    print(f"\n{'=' * 80}")
    print(f"SUMMARY: {total} episodes evaluated | avg quality score: {avg_score:.1f}/100")
    if total:
        print(f"  PERFECT: {counts.get('PERFECT', 0):>4} ({counts.get('PERFECT', 0) / total * 100:.1f}%)")
        print(f"  SUCCESS: {counts.get('SUCCESS', 0):>4} ({counts.get('SUCCESS', 0) / total * 100:.1f}%)")
        print(f"  PARTIAL: {counts.get('PARTIAL', 0):>4} ({counts.get('PARTIAL', 0) / total * 100:.1f}%)")
        print(f"  FAIL:    {counts.get('FAIL', 0):>4} ({counts.get('FAIL', 0) / total * 100:.1f}%)")
    print(f"{'=' * 80}")

    # Breakdown by scene
    scene_counts: dict[str, dict] = {}
    scene_scores: dict[str, list] = {}
    for m in results:
        if m.scene not in scene_counts:
            scene_counts[m.scene] = {"PERFECT": 0, "SUCCESS": 0, "PARTIAL": 0, "FAIL": 0, "total": 0}
            scene_scores[m.scene] = []
        scene_counts[m.scene][m.quality] = scene_counts[m.scene].get(m.quality, 0) + 1
        scene_counts[m.scene]["total"] += 1
        scene_scores[m.scene].append(m.quality_score)
    print("\nBy scene:")
    for scene, sc in sorted(scene_counts.items()):
        ok = sc.get("PERFECT", 0) + sc.get("SUCCESS", 0)
        sr = ok / sc["total"] * 100 if sc["total"] > 0 else 0
        avg_s = sum(scene_scores[scene]) / len(scene_scores[scene]) if scene_scores[scene] else 0
        print(f"  {scene:<35s}: {sc['total']:>3} eps | "
              f"{sc.get('PERFECT',0)}P/{sc.get('SUCCESS',0)}S/{sc.get('PARTIAL',0)}W/{sc.get('FAIL',0)}F | "
              f"SR={sr:.0f}% avgQ={avg_s:.0f}")

    # Breakdown by task
    task_counts: dict[str, dict] = {}
    task_scores: dict[str, list] = {}
    for m in results:
        t = m.task or "(unlabeled)"
        if t not in task_counts:
            task_counts[t] = {"PERFECT": 0, "SUCCESS": 0, "PARTIAL": 0, "FAIL": 0, "total": 0}
            task_scores[t] = []
        task_counts[t][m.quality] = task_counts[t].get(m.quality, 0) + 1
        task_counts[t]["total"] += 1
        task_scores[t].append(m.quality_score)
    print("\nBy task:")
    for task, tc in sorted(task_counts.items()):
        ok = tc.get("PERFECT", 0) + tc.get("SUCCESS", 0)
        sr = ok / tc["total"] * 100 if tc["total"] > 0 else 0
        avg_s = sum(task_scores[task]) / len(task_scores[task]) if task_scores[task] else 0
        print(f"  {task:<35s}: {tc['total']:>3} eps | "
              f"{tc.get('PERFECT',0)}P/{tc.get('SUCCESS',0)}S/{tc.get('PARTIAL',0)}W/{tc.get('FAIL',0)}F | "
              f"SR={sr:.0f}% avgQ={avg_s:.0f}")

    # Common failure reasons
    reason_counts: dict[str, int] = {}
    for m in results:
        for r in m.reasons:
            reason_counts[r] = reason_counts.get(r, 0) + 1
    if reason_counts:
        print("\nFailure/warning reasons:")
        for reason, cnt in sorted(reason_counts.items(), key=lambda x: -x[1]):
            print(f"  {reason:<30s}: {cnt}")

    # Score distribution
    if total:
        buckets = {"0-24": 0, "25-49": 0, "50-74": 0, "75-89": 0, "90-100": 0}
        for m in results:
            if m.quality_score >= 90:
                buckets["90-100"] += 1
            elif m.quality_score >= 75:
                buckets["75-89"] += 1
            elif m.quality_score >= 50:
                buckets["50-74"] += 1
            elif m.quality_score >= 25:
                buckets["25-49"] += 1
            else:
                buckets["0-24"] += 1
        print("\nQuality score distribution:")
        for bucket, cnt in buckets.items():
            bar = "#" * int(cnt / total * 40) if total else ""
            print(f"  {bucket:>6}: {cnt:>3} {bar}")

    # Grasp performance summary
    pick_episodes = [m for m in results
                     if m.task.strip('"').strip("'").startswith("plan_pick")
                     or m.task.strip('"').strip("'").startswith("left_plan_pick")
                     or m.task.strip('"').strip("'").startswith("nav_pick")
                     or m.task.strip('"').strip("'").startswith("bimanual")]
    if pick_episodes:
        total_attempts = sum(m.grasp_attempts for m in pick_episodes)
        total_successes = sum(m.grasp_successes for m in pick_episodes)
        total_lifts = sum(1 for m in pick_episodes if m.lift_detected)
        total_drops = sum(1 for m in pick_episodes if m.object_dropped_during_transport)
        print(f"\nGrasp performance ({len(pick_episodes)} manipulation episodes):")
        print(f"  Grasp attempts: {total_attempts} | successes: {total_successes} "
              f"({total_successes/total_attempts*100:.0f}%)" if total_attempts else
              "  Grasp attempts: 0 (no grasp events logged)")
        print(f"  Lifts: {total_lifts} | drops during transport: {total_drops}")

    # Export filtered list
    quality_rank = {"PERFECT": 4, "SUCCESS": 3, "PARTIAL": 2, "FAIL": 1}
    min_rank = {"perfect": 4, "success": 3, "partial": 2, "fail": 1, "all": 0}[args.min_quality]
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
                "quality_score": m.quality_score,
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
                "grasp_attempts": m.grasp_attempts,
                "grasp_successes": m.grasp_successes,
                "grasp_success_rate": round(m.grasp_success_rate, 3),
                "grip_duration_sec": round(m.grip_duration_sec, 2),
                "lift_detected": m.lift_detected,
                "object_dropped_during_transport": m.object_dropped_during_transport,
                "max_gripper_gap": round(m.max_gripper_gap, 5),
                "min_gripper_gap": round(m.min_gripper_gap, 5),
                "frames_with_object": m.frames_with_object,
                "frames_object_stable": m.frames_object_stable,
                "max_contact_force": round(m.max_contact_force, 3),
                "frames_with_contact": m.frames_with_contact,
                "grasp_phases": m.grasp_phases,
                "reasons": m.reasons,
            })
        Path(args.json_report).write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(f"JSON report: {args.json_report}")


if __name__ == "__main__":
    main()
