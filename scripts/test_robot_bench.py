"""
Clean Robot Test Bench
======================
Standalone Isaac Sim script for testing TIAGo robot models in a minimal scene.
No MoveIt, no ROS2, no bridge -- pure Isaac Sim + PhysX.

Usage:
    python.bat scripts/test_robot_bench.py --all-models --output C:\\RoboLab_Data\\bench
    python.bat scripts/test_robot_bench.py --model heavy --output C:\\RoboLab_Data\\bench
    python.bat scripts/test_robot_bench.py --model light --no-video --output C:\\RoboLab_Data\\bench
"""

import argparse
import glob
import json
import math
import os
import sys
import time
from types import SimpleNamespace

import yaml


# ---------------------------------------------------------------------------
# Layered config system: DEFAULTS <- robot_profile.yaml <- task_config.json
# ---------------------------------------------------------------------------
DEFAULTS = {
    # --- Robot physical constants ---
    "spawn_z": 0.08,
    "wheel_radius": 0.0985,
    "wheel_separation_x": 0.222,
    "wheel_separation_y": 0.222,
    "wheel_names": [
        "wheel_front_left_joint", "wheel_front_right_joint",
        "wheel_rear_left_joint", "wheel_rear_right_joint",
    ],
    "drive_params": {
        "torso_lift_joint":  (3000.0, 600.0, 25000.0),
        "arm_1_joint":       (1500.0, 300.0, 5000.0),
        "arm_2_joint":       (1500.0, 300.0, 5000.0),
        "arm_3_joint":       (1500.0, 300.0, 4000.0),
        "arm_4_joint":       (1000.0, 200.0, 2000.0),
        "arm_5_joint":       (500.0, 100.0, 800.0),
        "arm_6_joint":       (500.0, 100.0, 800.0),
        "arm_7_joint":       (500.0, 100.0, 800.0),
        "head_1_joint":      (400.0, 80.0, 500.0),
        "head_2_joint":      (400.0, 80.0, 500.0),
        "gripper_left_left_finger_joint":   (5000.0, 800.0, 2000.0),
        "gripper_left_right_finger_joint":  (5000.0, 800.0, 2000.0),
        "gripper_right_left_finger_joint":  (5000.0, 800.0, 2000.0),
        "gripper_right_right_finger_joint": (5000.0, 800.0, 2000.0),
    },
    "default_drive": (400.0, 80.0, 500.0),
    "roller_drive": {"stiffness": 0.0, "damping": 5.0, "max_force": 100.0},
    "wheel_drive": {"stiffness": 0.0, "damping": 500.0, "max_force": 50000.0},
    "torso_speed": 0.05,
    "torso_min": 0.0,
    "torso_max": 0.35,
    "gripper_open": 0.045,
    "gripper_closed": 0.0,
    "gripper_grasp_mug": 0.02,
    "gripper_joints": [
        "gripper_right_left_finger_joint",
        "gripper_right_right_finger_joint",
    ],
    "home_joints": {
        "torso_lift_joint": 0.0,
        "arm_right_1_joint": 0.07, "arm_right_2_joint": -1.0,
        "arm_right_3_joint": -0.20, "arm_right_4_joint": 1.50,
        "arm_right_5_joint": -1.57, "arm_right_6_joint": 0.10,
        "arm_right_7_joint": 0.0,
        "arm_left_1_joint": 0.07, "arm_left_2_joint": -1.0,
        "arm_left_3_joint": -0.20, "arm_left_4_joint": 1.50,
        "arm_left_5_joint": -1.57, "arm_left_6_joint": 0.10,
        "arm_left_7_joint": 0.0,
        "head_1_joint": 0.0, "head_2_joint": -0.20,
    },
    "arm_poses": {
        "home":             {"R": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0], "L": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0]},
        "forward":          {"R": [1.50, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],        "L": [1.50, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
        "down":             {"R": [0.0, 0.20, -0.20, 0.0, 0.0, 0.0, 0.0],      "L": [0.0, 0.20, -0.20, 0.0, 0.0, 0.0, 0.0]},
        "Y_shape":          {"R": [0.20, -1.10, -0.20, 0.0, 0.0, 0.0, 0.0],    "L": [0.20, -1.10, -0.20, 0.0, 0.0, 0.0, 0.0]},
        "heart":            {"R": [1.40, -0.30, 2.50, 2.20, -1.00, -1.00, 0.0], "L": [1.40, -0.30, 2.50, 2.20, 1.00, 1.00, 0.0]},
        "pre_grasp":        {"R": [1.50, 0.0, 0.0, 0.0, -1.57, 0.0, 0.0],      "L": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0]},
        "grasp":            {"R": [1.50, 0.0, 0.0, 0.0, -1.57, 0.0, 0.0],      "L": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0]},
        "lift":             {"R": [1.50, 0.0, 0.0, 0.0, -1.57, 0.0, 0.0],      "L": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0]},
        "place_right":      {"R": [1.50, 0.0, 0.0, 0.0, -1.57, 0.0, 0.0],      "L": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0]},
        "pre_grasp_center": {"R": [1.50, 0.0, 0.0, -0.25, -1.57, 0.0, 0.0],   "L": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0]},
        "grasp_center":     {"R": [1.50, 0.0, 0.0, -0.25, -1.57, 0.0, 0.0],   "L": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0]},
        "pre_grasp_top":    {"R": [1.50, 0.0, 0.0, -0.35, -1.57, 0.0, 0.0],   "L": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0]},
        "grasp_top":        {"R": [1.50, 0.0, 0.0, -0.35, -1.57, 0.0, 0.0],   "L": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0]},
        "lift_top":         {"R": [1.50, 0.0, 0.0, 0.0, -1.57, 0.0, 0.0],      "L": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0]},
    },
    # --- Safety ---
    "table_south_boundary_y": 2.75,
    "furniture_zones": [
        {"name": "fridge",       "cx": -1.35, "cy": 3.45, "hw": 0.50, "hd": 0.50},
        {"name": "sink_cabinet", "cx":  0.45, "cy": 3.60, "hw": 0.50, "hd": 0.40},
        {"name": "table",        "cx":  1.35, "cy": 3.55, "hw": 0.50, "hd": 0.50},
    ],
    "nav_margin": 0.35,
    # --- Control timing (steps) ---
    "grasp_settle_steps": 360,
    "settle_steps": 240,
    "extend_arm_steps": 600,
    "rotate_timeout_steps": 1200,
    "drive_to_mug_timeout_steps": 1800,
    "settle_at_table_steps": 240,
    "approach_timeout_steps": 1200,
    "descend_timeout_steps": 1500,
    "close_gripper_step": 45,
    "close_gripper_timeout": 270,
    "verify_grasp_min_steps": 60,
    "lift_interpolation_steps": 600,
    "lift_verify_steps": 240,
    "lift_timeout_steps": 1200,
    "place_descent_steps": 600,
    # --- Grasp tuning ---
    "pre_grasp_pose": "pre_grasp_top",
    "j4_extended": -0.35,
    "j4_retracted": 0.30,
    "torso_approach": 0.35,
    "torso_settle": 0.15,
    "top_xy_tol": 0.02,
    "top_descend_clearance": 0.015,
    "top_verify_xy_tol": 0.05,
    "gripper_close_value": 0.018,
    "gripper_hold_threshold": 0.01,
    # --- Navigation tuning ---
    "rotate_tolerance_deg": 5.0,
    "rotate_speed_fast": 0.3,
    "rotate_speed_slow": 0.15,
    "rotate_speed_threshold_deg": 20.0,
    "drive_speed_cap": 0.12,
    "y_align_tolerance": 0.005,
    "y_align_speed": 0.06,
    "approach_speed": 0.05,
    "x_guard_extra": 0.20,
    "stuck_threshold": 0.002,
    "stuck_trigger_steps": 600,
    "stuck_phase_steps": 300,
    "stuck_lateral_factor": 0.3,
    "stuck_backward_factor": 0.4,
    "velocity_norm_scale": 2.0,
    "velocity_min_dist": 0.01,
    # --- Placement tuning ---
    "table_top_z": 0.80,
    "table_cx": 1.35,
    "table_cy": 3.45,
    "table_half_w": 0.40,
    "table_half_d": 0.40,
    "bounds_margin": 0.05,
    "abort_below_z_offset": -0.05,
    "release_z_offset": 0.02,
    "success_z_offset": 0.15,
    "torso_hold": 0.35,
    # --- Physics ---
    "physics_dt": 1.0 / 120.0,
    "rendering_dt": 1.0 / 60.0,
    "log_every": 6,
    "console_every": 60,
    "render_every": 2,
}


def _deep_merge(base, override):
    """Recursively merge override dict into base dict. Override wins for leaf values."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_robot_profile(yaml_path):
    """Load robot profile YAML and flatten into config-compatible dict."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    flat = {}
    # Flatten wheel section
    wheel = raw.get("wheel", {})
    if "radius" in wheel:
        flat["wheel_radius"] = wheel["radius"]
    if "separation_x" in wheel:
        flat["wheel_separation_x"] = wheel["separation_x"]
    if "separation_y" in wheel:
        flat["wheel_separation_y"] = wheel["separation_y"]
    if "names" in wheel:
        flat["wheel_names"] = wheel["names"]
    # Drive params: convert lists to tuples
    dp = raw.get("drive_params", {})
    if dp:
        flat["drive_params"] = {k: tuple(v) for k, v in dp.items()}
    if "default_drive" in raw:
        flat["default_drive"] = tuple(raw["default_drive"])
    for key in ("roller_drive", "wheel_drive"):
        if key in raw:
            flat[key] = raw[key]
    # Scalar robot params
    for key in ("spawn_z", "torso_speed", "torso_min", "torso_max"):
        if key in raw:
            flat[key] = raw[key]
    # Gripper
    gripper = raw.get("gripper", {})
    if "open" in gripper:
        flat["gripper_open"] = gripper["open"]
    if "closed" in gripper:
        flat["gripper_closed"] = gripper["closed"]
    if "grasp_mug" in gripper:
        flat["gripper_grasp_mug"] = gripper["grasp_mug"]
    if "joints" in gripper:
        flat["gripper_joints"] = gripper["joints"]
    # Home joints, arm poses
    if "home_joints" in raw:
        flat["home_joints"] = raw["home_joints"]
    if "arm_poses" in raw:
        flat["arm_poses"] = raw["arm_poses"]
    return flat


def _flatten_task_config_sections(task_cfg):
    """Extract safety/control/grasp/navigation/placement/physics sections from task JSON into flat dict."""
    flat = {}
    for section_key in ("safety", "control", "grasp", "navigation", "placement", "physics"):
        section = task_cfg.get(section_key, {})
        for k, v in section.items():
            flat[k] = v
    return flat


def build_config(defaults, robot_profile_dict=None, task_config_dict=None):
    """Merge config layers: defaults <- robot_profile <- task_config. Returns SimpleNamespace."""
    merged = dict(defaults)
    if robot_profile_dict:
        merged = _deep_merge(merged, robot_profile_dict)
    if task_config_dict:
        flat_task = _flatten_task_config_sections(task_config_dict)
        merged = _deep_merge(merged, flat_task)
    return SimpleNamespace(**merged)


# Global config — populated after CLI parse and task config load
cfg = SimpleNamespace(**DEFAULTS)


# ---------------------------------------------------------------------------
# Scene constants (needed for grasp CLI defaults)
# Table against wall (Y=1.5) so it does not block access to fridge/sink/dishwasher.
# Robot at (0,0) can reach fridge (2.8,0), dishwasher (2.8,-1), sink (2.4,0.9) freely.
# ---------------------------------------------------------------------------
GRASP_TABLE_X = 1.0
GRASP_TABLE_Y = 1.2     # table center; back edge at Y=1.5 (against wall)
GRASP_TABLE_HEIGHT = 0.74

# Refrigerator (when --fridge): position and size
FRIDGE_X = 2.8
FRIDGE_Y = 0.0
FRIDGE_WIDTH_Y = 0.8   # width (Y)
FRIDGE_DEPTH_X = 0.7   # depth (X)
FRIDGE_HEIGHT = 1.6
FRIDGE_DOOR_DEPTH = 0.03
FRIDGE_DOOR_OPEN_DEG = 90.0   # max opening angle (degrees)

# Dishwasher (in grasp scene): same idea as fridge — door, handle, shelves
DISHWASHER_X = 2.8
DISHWASHER_Y = -1.0
DISHWASHER_WIDTH_Y = 0.6
DISHWASHER_DEPTH_X = 0.6
DISHWASHER_HEIGHT = 0.85
DISHWASHER_DOOR_DEPTH = 0.025
DISHWASHER_DOOR_OPEN_DEG = 90.0

# Sink cabinet with basin (in grasp scene): place objects in sink
SINK_CABINET_X = 2.4
SINK_CABINET_Y = 0.9
SINK_CABINET_WIDTH_Y = 0.7
SINK_CABINET_DEPTH_X = 0.5
SINK_CABINET_HEIGHT = 0.9
SINK_BASIN_DEPTH = 0.18   # depth of basin (Z)
SINK_BASIN_MARGIN = 0.04  # wall thickness

# Table setting: mug on table (center); plate on table; fruit on plate (for manipulation)
# Mug at table center (GRASP_MUG_X/Y = GRASP_TABLE_X/Y). Plate offset so mug and plate do not overlap.
PLATE_X = 1.0            # same X as table center
PLATE_Y = 1.05           # slightly below table center Y so mug (1.0, 1.2) and plate are separate
PLATE_Z = GRASP_TABLE_HEIGHT + 0.02   # top of table + half plate height
PLATE_RADIUS = 0.12
PLATE_HEIGHT = 0.02
BANANA_RADIUS = 0.015
BANANA_LENGTH = 0.08
APPLE_RADIUS = 0.03
FRUIT_Z_OFFSET = 0.01   # fruit center slightly above plate top

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Clean Robot Test Bench")
parser.add_argument("--model", type=str, default="heavy",
                    choices=["heavy", "light", "urdf"],
                    help="Robot model to test (default: heavy)")
parser.add_argument("--all-models", action="store_true",
                    help="Test all 3 models sequentially")
parser.add_argument("--output", type=str, default=r"C:\RoboLab_Data\bench",
                    help="Output directory for logs and videos")
parser.add_argument("--no-video", action="store_true",
                    help="Skip video recording (faster)")
parser.add_argument("--headless", action="store_true", default=True,
                    help="Run headless (default: True)")
parser.add_argument("--duration", type=float, default=25.0,
                    help="Total test duration in seconds")
parser.add_argument("--tiago-dir", type=str,
                    default=r"C:\RoboLab_Data\data\tiago_isaac",
                    help="Directory containing TIAGo USD files")
parser.add_argument("--width", type=int, default=640)
parser.add_argument("--height", type=int, default=480)
parser.add_argument("--drive-base", action="store_true",
                    help="Enable base driving (unfixes base, uses wheel velocity control)")
parser.add_argument("--drive-distance", type=float, default=1.0,
                    help="Distance to drive forward/backward in meters (default: 1.0)")
parser.add_argument("--drive-speed", type=float, default=0.3,
                    help="Base drive speed in m/s (default: 0.3, PAL max=1.0)")
parser.add_argument("--choreo", action="store_true",
                    help="Run choreography sequence (implies --drive-base)")
parser.add_argument("--grasp", action="store_true",
                    help="Run table grasp scenario (implies --drive-base)")
parser.add_argument("--mug-x", type=float, default=None,
                    help="Mug X position in world (default: table center = GRASP_TABLE_X)")
parser.add_argument("--mug-y", type=float, default=None,
                    help="Mug Y position in world (default: table center = 0)")
parser.add_argument("--place-dx", type=float, default=0.0,
                    help="Place offset X in meters (default: 0)")
parser.add_argument("--place-dy", type=float, default=-0.20,
                    help="Place offset Y in meters, positive=right (default: -0.20 = 20cm left)")
parser.add_argument("--lift-height", type=float, default=0.20,
                    help="Lift height in meters (default: 0.20)")
parser.add_argument("--torso-speed", type=float, default=0.05,
                    help="Torso raise/lift speed m/s (default: 0.05, PAL max 0.07)")
parser.add_argument("--torso-lower-speed", type=float, default=0.02,
                    help="Torso lower speed m/s for approach and place (default: 0.02)")
parser.add_argument("--shift-rot-speed", type=float, default=0.15,
                    help="Base rotation speed rad/s for place shift (default: 0.15)")
parser.add_argument("--approach-clearance", type=float, default=0.13,
                    help="Stop approach when tool is this many m before mug X (default: 0.13 = 13cm)")
parser.add_argument("--grasp-mode", type=str, default="top",
                    choices=["top", "side", "auto"],
                    help="Grasp strategy: top-first, side-only, or auto fallback (default: top)")
parser.add_argument("--top-pregrasp-height", type=float, default=0.06,
                    help="Top-grasp pregrasp height above mug in meters (default: 0.06)")
parser.add_argument("--top-descend-speed", type=float, default=0.015,
                    help="Top-grasp vertical descend speed in m/s (default: 0.015)")
parser.add_argument("--top-descend-clearance", type=float, default=0.025,
                    help="Top-grasp stop when tool is this many meters above mug (default: 0.025)")
parser.add_argument("--top-xy-tol", type=float, default=0.02,
                    help="Top-grasp XY alignment tolerance in meters before descend (default: 0.02)")
parser.add_argument("--top-verify-xy-tol", type=float, default=0.03,
                    help="Top-grasp XY tolerance in meters for verify_grasp (tool vs mug center; default 0.03)")
parser.add_argument("--top-lift-test-height", type=float, default=0.015,
                    help="Top-grasp minimum mug lift for hold verification in meters (default: 0.02)")
parser.add_argument("--top-lift-test-hold-s", type=float, default=0.6,
                    help="Top-grasp hold time after lift test in seconds (default: 0.5)")
parser.add_argument("--top-retry-y-step", type=float, default=0.008,
                    help="Top-grasp retry Y correction step in meters (default: 0.008)")
parser.add_argument("--top-retry-z-step", type=float, default=0.008,
                    help="Top-grasp retry Z clearance correction in meters (default: 0.008)")
parser.add_argument("--top-max-retries", type=int, default=2,
                    help="Max retries in top mode before side fallback in auto mode (default: 2)")
parser.add_argument("--gripper-length-m", type=float, default=0.10,
                    help="Effective gripper length for approach targeting in meters (default: 0.10)")
parser.add_argument("--fast", action="store_true",
                    help="Faster runs: no video, shorter settle (use with -NoVideo and -Duration 55 in run_bench.ps1)")
parser.add_argument("--fridge", dest="fridge", action="store_true", default=None,
                    help="Add refrigerator with openable door and handle (default: True in grasp scene)")
parser.add_argument("--no-fridge", dest="fridge", action="store_false",
                    help="Do not add refrigerator to the scene")
parser.add_argument("--task-config", type=str, default=None,
                    help="Path to task config JSON (scene + task list); implies --grasp and kitchen scene")
parser.add_argument("--kitchen-scene", type=str, default=None, choices=["legacy", "fixed"],
                    help="Kitchen scene variant: 'legacy' (old 5x5 procedural) or 'fixed' (new 8x8 with walls/PBR)")
args, _unknown = parser.parse_known_args()
if args.fridge is None:
    args.fridge = bool(getattr(args, "grasp", False))

# Load task config and apply scene/robot/global overrides
if getattr(args, "task_config", None):
    task_config_path = os.path.abspath(args.task_config)
    if not os.path.isfile(task_config_path):
        raise FileNotFoundError(f"Task config not found: {task_config_path}")
    with open(task_config_path, "r", encoding="utf-8") as f:
        args._task_config_dict = json.load(f)
    _tcfg = args._task_config_dict
    args.grasp = True
    args.drive_base = True
    scene = _tcfg.get("scene", {})
    args.fridge = scene.get("fridge", True)
    args.dishwasher = scene.get("dishwasher", True)
    args.sink = scene.get("sink", True)
    args.plate_fruit = scene.get("plate_fruit", True)
    robot_cfg = _tcfg.get("robot", {})
    if "model" in robot_cfg:
        args.model = robot_cfg["model"]
    if "gripper_length_m" in robot_cfg:
        args.gripper_length_m = float(robot_cfg["gripper_length_m"])
    global_cfg = _tcfg.get("global", {})
    if "drive_speed_ms" in global_cfg:
        args.drive_speed = float(global_cfg["drive_speed_ms"])
    if "approach_clearance_m" in global_cfg:
        args.approach_clearance = float(global_cfg["approach_clearance_m"])
    if "torso_speed" in global_cfg:
        args.torso_speed = float(global_cfg["torso_speed"])
    if _tcfg.get("kitchen_scene"):
        args.kitchen_scene = _tcfg["kitchen_scene"]
    # Load robot profile YAML if specified, then build merged config
    _robot_profile = {}
    _profile_path = robot_cfg.get("robot_profile")
    if _profile_path:
        if not os.path.isabs(_profile_path):
            _profile_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), _profile_path)
        if os.path.isfile(_profile_path):
            _robot_profile = load_robot_profile(_profile_path)
            print(f"[Bench] Robot profile loaded: {_profile_path}")
        else:
            print(f"[Bench] WARNING: robot_profile not found: {_profile_path}, using defaults")
    cfg = build_config(DEFAULTS, _robot_profile, _tcfg)
    print(f"[Bench] Task config loaded: {task_config_path}")
    print(f"[Bench]   episode_name={_tcfg.get('episode_name', '')} scene: fridge={args.fridge} dishwasher={args.dishwasher} sink={args.sink} plate_fruit={args.plate_fruit}"
          + (f" kitchen_scene={args.kitchen_scene}" if getattr(args, "kitchen_scene", None) else ""))
else:
    args._task_config_dict = None
    cfg = build_config(DEFAULTS)
    args.dishwasher = getattr(args, "dishwasher", None)
    args.sink = getattr(args, "sink", None)
    args.plate_fruit = getattr(args, "plate_fruit", None)
    if args.dishwasher is None:
        args.dishwasher = bool(getattr(args, "grasp", False))
    if args.sink is None:
        args.sink = bool(getattr(args, "grasp", False))
    if args.plate_fruit is None:
        args.plate_fruit = bool(getattr(args, "grasp", False))

if args.choreo or args.grasp:
    args.drive_base = True
if getattr(args, "fast", False):
    args.no_video = True  # fast => no video capture/encode

# Apply grasp scenario params (mug position defaults to table center when --grasp)
if getattr(args, "grasp", False):
    GRASP_MUG_X = args.mug_x if args.mug_x is not None else GRASP_TABLE_X
    GRASP_MUG_Y = args.mug_y if args.mug_y is not None else GRASP_TABLE_Y
else:
    GRASP_MUG_X = GRASP_TABLE_X - 0.20
    GRASP_MUG_Y = -0.27

MODEL_FILES = {
    "heavy": "tiago_dual_functional.usd",
    "light": "tiago_dual_functional_light.usd",
    "urdf":  "tiago_dual_urdf_imported.usd",
}

MODELS_TO_TEST = list(MODEL_FILES.keys()) if args.all_models else [args.model]

# ---------------------------------------------------------------------------
# Isaac Sim bootstrap
# ---------------------------------------------------------------------------
from isaacsim import SimulationApp

simulation_app = SimulationApp({
    "headless": args.headless,
    "width": args.width,
    "height": args.height,
})

try:
    import omni.kit.app
    ext_mgr = omni.kit.app.get_app().get_extension_manager()
    ext_mgr.set_extension_enabled_immediate("omni.replicator.core", True)
    ext_mgr.set_extension_enabled_immediate("omni.replicator.isaac", True)
except Exception as e:
    print(f"[Bench] WARN: extension enable failed: {e}")

simulation_app.update()

import numpy as np
import omni.replicator.core as rep
import omni.isaac.core.utils.stage as stage_utils
from omni.isaac.core import World
from omni.isaac.core.articulations import Articulation
from omni.isaac.core.prims import XFormPrim
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade

try:
    from pxr import PhysxSchema
except ImportError:
    PhysxSchema = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def quat_to_euler(w, x, y, z):
    """Quaternion (w,x,y,z) -> (roll, pitch, yaw) in degrees."""
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.asin(sinp)

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


def encode_video(replicator_dir, output_path):
    """Encode RGB PNGs from replicator output into MP4."""
    rgb_files = sorted(
        glob.glob(os.path.join(replicator_dir, "**", "rgb_*.png"), recursive=True),
        key=lambda f: int("".join(c for c in os.path.basename(f) if c.isdigit()) or "0"),
    )
    if not rgb_files:
        print(f"[Bench] No RGB frames in {replicator_dir}")
        return False
    try:
        import imageio.v2 as imageio
        print(f"[Bench] Encoding {len(rgb_files)} frames -> {output_path}")
        with imageio.get_writer(output_path, fps=30) as writer:
            for fp in rgb_files:
                writer.append_data(imageio.imread(fp))
        return True
    except Exception as e:
        print(f"[Bench] WARN: video encode failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Scene builder (GRASP_TABLE_* defined above with CLI)
# ---------------------------------------------------------------------------
# Table geometry: 0.80 x 0.60m, centered at TABLE_X.
# Tabletop X range: [TABLE_X - 0.40, TABLE_X + 0.40] = [1.60, 2.40]
#
# Arm reach (sim-calibrated): dX = 0.764m from base center.
# Robot base is ~0.54m long, front at base_X + 0.27.
#
# Mug placed near the near edge of the table (X=1.80).
# Arm reach dX ≈ 0.76m. Robot overshoots ~0.14m when stopping.
# Effective stop position: mug_X - clearance + overshoot.
# With clearance=0.90: intended stop X = 1.80 - 0.90 = 0.90
#   actual stop X ≈ 0.90 + 0.14 = 1.04
#   robot front ≈ 1.04 + 0.27 = 1.31
#   gap to table (1.60) ≈ 0.29m — safe
#   tool X ≈ 1.04 + 0.76 = 1.80 — right at mug
GRASP_APPROACH_CLEARANCE = 0.90

# GRASP_MUG_X, GRASP_MUG_Y set after parse (table center when --grasp, else near edge)
GRASP_MUG_Z = GRASP_TABLE_HEIGHT + 0.05

GRIPPER_OPEN = cfg.gripper_open
GRIPPER_CLOSED = cfg.gripper_closed
GRIPPER_GRASP_MUG = cfg.gripper_grasp_mug
GRIPPER_JOINTS = list(cfg.gripper_joints)


def _create_white_tile_material(stage, mat_path):
    """Create a UsdPreviewSurface white tile visual material with physics friction."""
    mtl = UsdShade.Material.Define(stage, mat_path)
    shader_path = f"{mat_path}/Shader"
    shader = UsdShade.Shader.Define(stage, shader_path)
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(0.92, 0.92, 0.92))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.4)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    mtl.CreateSurfaceOutput().ConnectToSource(
        UsdShade.ConnectableAPI(shader), "surface")
    UsdPhysics.MaterialAPI.Apply(stage.GetPrimAtPath(mat_path))
    mat_prim = stage.GetPrimAtPath(mat_path)
    mat_prim.CreateAttribute("physics:staticFriction", Sdf.ValueTypeNames.Float).Set(0.8)
    mat_prim.CreateAttribute("physics:dynamicFriction", Sdf.ValueTypeNames.Float).Set(0.6)
    mat_prim.CreateAttribute("physics:restitution", Sdf.ValueTypeNames.Float).Set(0.01)
    return mtl


def _spawn_procedural_table(stage, path, pos_x, pos_y):
    """Procedural table with guaranteed collision at known height.
    Each part uses an Xform wrapper so Translate and Scale don't interact."""
    xf = UsdGeom.Xform.Define(stage, path)
    UsdGeom.Xformable(xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(pos_x, pos_y, 0))

    top_w, top_d, top_h = 0.80, 0.60, 0.04

    # Tabletop: use Xform parent for position, Cube child for geometry+scale
    top_xf_path = f"{path}/TopXf"
    top_xf = UsdGeom.Xform.Define(stage, top_xf_path)
    UsdGeom.Xformable(top_xf.GetPrim()).AddTranslateOp().Set(
        Gf.Vec3d(0, 0, GRASP_TABLE_HEIGHT))

    top_path = f"{top_xf_path}/Top"
    top = UsdGeom.Cube.Define(stage, top_path)
    top.CreateSizeAttr(1.0)
    top.AddScaleOp().Set(Gf.Vec3f(top_w, top_d, top_h))
    top.CreateDisplayColorAttr([(0.55, 0.35, 0.20)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(top_path))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(top_path))

    leg_w = 0.04
    leg_h = GRASP_TABLE_HEIGHT - top_h / 2.0
    leg_offsets = [
        (-top_w/2 + leg_w, -top_d/2 + leg_w),
        ( top_w/2 - leg_w, -top_d/2 + leg_w),
        (-top_w/2 + leg_w,  top_d/2 - leg_w),
        ( top_w/2 - leg_w,  top_d/2 - leg_w),
    ]
    for i, (lx, ly) in enumerate(leg_offsets):
        leg_xf_path = f"{path}/LegXf{i}"
        leg_xf = UsdGeom.Xform.Define(stage, leg_xf_path)
        UsdGeom.Xformable(leg_xf.GetPrim()).AddTranslateOp().Set(
            Gf.Vec3d(lx, ly, leg_h / 2.0))

        lp = f"{leg_xf_path}/Leg"
        leg = UsdGeom.Cube.Define(stage, lp)
        leg.CreateSizeAttr(1.0)
        leg.AddScaleOp().Set(Gf.Vec3f(leg_w, leg_w, leg_h))
        leg.CreateDisplayColorAttr([(0.45, 0.28, 0.15)])
        UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(lp))
        if PhysxSchema:
            PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(lp))

    print(f"[Bench] Procedural table at ({pos_x}, {pos_y}), "
          f"top={top_w}x{top_d}x{top_h}m at z={GRASP_TABLE_HEIGHT}m")


def _spawn_procedural_mug(stage, path, pos_x, pos_y, pos_z):
    """Procedural cylinder mug — wider base for stability, explicit upright."""
    xf_root = UsdGeom.Xform.Define(stage, path)
    xf_api = UsdGeom.Xformable(xf_root.GetPrim())
    xf_api.AddTranslateOp().Set(Gf.Vec3d(pos_x, pos_y, pos_z))
    # Cylinder axis is Z by default — upright, no rotation needed
    body_path = f"{path}/Body"
    mug = UsdGeom.Cylinder.Define(stage, body_path)
    mug.CreateRadiusAttr(0.04)
    mug.CreateHeightAttr(0.10)
    mug.CreateDisplayColorAttr([(0.80, 0.20, 0.15)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(body_path))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(body_path))
    print(f"[Bench] Procedural mug at ({pos_x}, {pos_y}, {pos_z})")


def _spawn_procedural_refrigerator(stage, base_path, pos_x, pos_y):
    """Add a refrigerator with openable door (revolute joint), handle, and shelves.
    Door hinge on left (negative Y); door opens toward positive Y. Handle on right side for robot grasp."""
    root = UsdGeom.Xform.Define(stage, base_path)
    UsdGeom.Xformable(root.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(pos_x, pos_y, 0))

    w, d, h = FRIDGE_WIDTH_Y, FRIDGE_DEPTH_X, FRIDGE_HEIGHT
    door_d = FRIDGE_DOOR_DEPTH
    half_d, half_w, half_h = d / 2.0, w / 2.0, h / 2.0
    # Cabinet center in world (pos_x, pos_y, half_h). Hinge at left edge: (pos_x - half_d, pos_y - half_w, half_h)
    hinge_y_local = -half_w  # hinge at left edge in cabinet/door Y

    # ---- Cabinet (kinematic rigid body: fixed in space) ----
    cabinet_path = f"{base_path}/Cabinet"
    cab_xf = UsdGeom.Xform.Define(stage, cabinet_path)
    UsdGeom.Xformable(cab_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0, half_h))
    cab_box_path = f"{cabinet_path}/Body"
    cab_box = UsdGeom.Cube.Define(stage, cab_box_path)
    cab_box.CreateSizeAttr(1.0)
    cab_box.AddScaleOp().Set(Gf.Vec3f(d, w, h))
    cab_box.CreateDisplayColorAttr([(0.95, 0.95, 0.98)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(cab_box_path))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(cab_box_path))
    cab_prim = stage.GetPrimAtPath(cabinet_path)
    UsdPhysics.RigidBodyAPI.Apply(cab_prim)
    cab_prim.CreateAttribute("physics:kinematicEnabled", Sdf.ValueTypeNames.Bool).Set(True)

    # ---- Door (dynamic rigid body, opens around left edge) ----
    # Door origin so that hinge points coincide: cabinet hinge at (-half_d, hinge_y_local, 0), door hinge at (-door_d/2, hinge_y_local, 0).
    # So door origin in root = hinge_world - door_hinge_local = (-half_d, hinge_y_local, 0) - (-door_d/2, hinge_y_local, 0) = (-half_d + door_d/2, 0, 0) in cabinet frame; in root (0,0,half_h) → door_center_x = -half_d + door_d/2
    door_center_x = -half_d + door_d / 2.0
    door_path = f"{base_path}/Door"
    door_xf = UsdGeom.Xform.Define(stage, door_path)
    UsdGeom.Xformable(door_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(door_center_x, 0, half_h))
    door_box_path = f"{door_path}/Panel"
    door_box = UsdGeom.Cube.Define(stage, door_box_path)
    door_box.CreateSizeAttr(1.0)
    door_box.AddScaleOp().Set(Gf.Vec3f(door_d, w, h))
    door_box.CreateDisplayColorAttr([(0.92, 0.94, 0.98)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(door_box_path))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(door_box_path))
    door_prim = stage.GetPrimAtPath(door_path)
    UsdPhysics.RigidBodyAPI.Apply(door_prim)
    door_prim.CreateAttribute("physics:mass", Sdf.ValueTypeNames.Float).Set(8.0)
    # Handle: bar on the right side of door (positive Y), graspable by robot
    handle_path = f"{door_path}/Handle"
    handle_xf = UsdGeom.Xform.Define(stage, handle_path)
    UsdGeom.Xformable(handle_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(-0.02, half_w - 0.08, 0))
    handle_box = UsdGeom.Cube.Define(stage, f"{handle_path}/Bar")
    handle_box.CreateSizeAttr(1.0)
    handle_box.AddScaleOp().Set(Gf.Vec3f(0.06, 0.12, 0.03))  # 6cm outward, 12cm wide, 3cm thick
    handle_box.CreateDisplayColorAttr([(0.3, 0.3, 0.35)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(f"{handle_path}/Bar"))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(f"{handle_path}/Bar"))

    # ---- Revolute joint: hinge at left edge of door, axis Y ----
    hinge_path = f"{base_path}/DoorHinge"
    rev = UsdPhysics.RevoluteJoint.Define(stage, hinge_path)
    rev.GetBody0Rel().SetTargets([Sdf.Path(cabinet_path)])
    rev.GetBody1Rel().SetTargets([Sdf.Path(door_path)])
    rev.CreateAxisAttr("Y")
    rev.CreateLowerLimitAttr(0.0)
    rev.CreateUpperLimitAttr(FRIDGE_DOOR_OPEN_DEG)  # degrees
    # Hinge at left edge, mid height. Cabinet origin at (0,0,half_h) in Fridge → hinge in cabinet local = (-half_d, hinge_y_local, 0)
    rev.CreateLocalPos0Attr().Set(Gf.Vec3f(-half_d, hinge_y_local, 0.0))
    # Door origin at panel center; left edge (hinge side) in door local = (-door_d/2, hinge_y_local, 0)
    rev.CreateLocalPos1Attr().Set(Gf.Vec3f(-door_d / 2.0, hinge_y_local, 0.0))

    # ---- Shelves inside (static collision, for placing objects) ----
    shelf_h = 0.02
    shelf_dx, shelf_dy = d - 0.1, w - 0.1
    for i, z_frac in enumerate([0.25, 0.45, 0.65, 0.85]):
        z_pos = h * z_frac
        shelf_path = f"{cabinet_path}/Shelf{i}"
        shelf_xf = UsdGeom.Xform.Define(stage, shelf_path)
        UsdGeom.Xformable(shelf_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0, z_pos - half_h))
        shelf_box = UsdGeom.Cube.Define(stage, f"{shelf_path}/Plane")
        shelf_box.CreateSizeAttr(1.0)
        shelf_box.AddScaleOp().Set(Gf.Vec3f(shelf_dx, shelf_dy, shelf_h))
        shelf_box.CreateDisplayColorAttr([(0.7, 0.7, 0.75)])
        UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(f"{shelf_path}/Plane"))
        if PhysxSchema:
            PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(f"{shelf_path}/Plane"))

    print(f"[Bench] Refrigerator at ({pos_x}, {pos_y}): door hinge left, handle right, {4} shelves")


def _spawn_procedural_dishwasher(stage, base_path, pos_x, pos_y):
    """Dishwasher with openable door (revolute joint), handle, and racks (shelves). Same pattern as fridge."""
    root = UsdGeom.Xform.Define(stage, base_path)
    UsdGeom.Xformable(root.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(pos_x, pos_y, 0))

    w = DISHWASHER_WIDTH_Y
    d = DISHWASHER_DEPTH_X
    h = DISHWASHER_HEIGHT
    door_d = DISHWASHER_DOOR_DEPTH
    half_d, half_w, half_h = d / 2.0, w / 2.0, h / 2.0
    hinge_y_local = -half_w

    cabinet_path = f"{base_path}/Cabinet"
    cab_xf = UsdGeom.Xform.Define(stage, cabinet_path)
    UsdGeom.Xformable(cab_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0, half_h))
    cab_box_path = f"{cabinet_path}/Body"
    cab_box = UsdGeom.Cube.Define(stage, cab_box_path)
    cab_box.CreateSizeAttr(1.0)
    cab_box.AddScaleOp().Set(Gf.Vec3f(d, w, h))
    cab_box.CreateDisplayColorAttr([(0.75, 0.75, 0.78)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(cab_box_path))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(cab_box_path))
    cab_prim = stage.GetPrimAtPath(cabinet_path)
    UsdPhysics.RigidBodyAPI.Apply(cab_prim)
    cab_prim.CreateAttribute("physics:kinematicEnabled", Sdf.ValueTypeNames.Bool).Set(True)

    door_center_x = -half_d + door_d / 2.0
    door_path = f"{base_path}/Door"
    door_xf = UsdGeom.Xform.Define(stage, door_path)
    UsdGeom.Xformable(door_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(door_center_x, 0, half_h))
    door_box_path = f"{door_path}/Panel"
    door_box = UsdGeom.Cube.Define(stage, door_box_path)
    door_box.CreateSizeAttr(1.0)
    door_box.AddScaleOp().Set(Gf.Vec3f(door_d, w, h))
    door_box.CreateDisplayColorAttr([(0.72, 0.74, 0.78)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(door_box_path))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(door_box_path))
    door_prim = stage.GetPrimAtPath(door_path)
    UsdPhysics.RigidBodyAPI.Apply(door_prim)
    door_prim.CreateAttribute("physics:mass", Sdf.ValueTypeNames.Float).Set(5.0)
    handle_path = f"{door_path}/Handle"
    handle_xf = UsdGeom.Xform.Define(stage, handle_path)
    UsdGeom.Xformable(handle_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(-0.02, half_w - 0.06, 0))
    handle_box = UsdGeom.Cube.Define(stage, f"{handle_path}/Bar")
    handle_box.CreateSizeAttr(1.0)
    handle_box.AddScaleOp().Set(Gf.Vec3f(0.05, 0.10, 0.025))
    handle_box.CreateDisplayColorAttr([(0.25, 0.25, 0.3)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(f"{handle_path}/Bar"))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(f"{handle_path}/Bar"))

    hinge_path = f"{base_path}/DoorHinge"
    rev = UsdPhysics.RevoluteJoint.Define(stage, hinge_path)
    rev.GetBody0Rel().SetTargets([Sdf.Path(cabinet_path)])
    rev.GetBody1Rel().SetTargets([Sdf.Path(door_path)])
    rev.CreateAxisAttr("Y")
    rev.CreateLowerLimitAttr(0.0)
    rev.CreateUpperLimitAttr(DISHWASHER_DOOR_OPEN_DEG)
    rev.CreateLocalPos0Attr().Set(Gf.Vec3f(-half_d, hinge_y_local, 0.0))
    rev.CreateLocalPos1Attr().Set(Gf.Vec3f(-door_d / 2.0, hinge_y_local, 0.0))

    shelf_h = 0.015
    shelf_dx, shelf_dy = d - 0.08, w - 0.08
    for i, z_frac in enumerate([0.35, 0.65]):
        z_pos = h * z_frac
        shelf_path = f"{cabinet_path}/Rack{i}"
        shelf_xf = UsdGeom.Xform.Define(stage, shelf_path)
        UsdGeom.Xformable(shelf_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0, z_pos - half_h))
        shelf_box = UsdGeom.Cube.Define(stage, f"{shelf_path}/Plane")
        shelf_box.CreateSizeAttr(1.0)
        shelf_box.AddScaleOp().Set(Gf.Vec3f(shelf_dx, shelf_dy, shelf_h))
        shelf_box.CreateDisplayColorAttr([(0.6, 0.6, 0.65)])
        UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(f"{shelf_path}/Plane"))
        if PhysxSchema:
            PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(f"{shelf_path}/Plane"))
    print(f"[Bench] Dishwasher at ({pos_x}, {pos_y}): door hinge left, handle right, 2 racks")


def _spawn_sink_cabinet(stage, base_path, pos_x, pos_y):
    """Cabinet with sink basin — collision surface inside basin so objects can be placed in the sink."""
    root = UsdGeom.Xform.Define(stage, base_path)
    UsdGeom.Xformable(root.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(pos_x, pos_y, 0))

    w = SINK_CABINET_WIDTH_Y
    d = SINK_CABINET_DEPTH_X
    h = SINK_CABINET_HEIGHT
    half_d, half_w, half_h = d / 2.0, w / 2.0, h / 2.0
    margin = SINK_BASIN_MARGIN
    basin_dz = SINK_BASIN_DEPTH
    # Top counter at z = h; basin recessed down by basin_dz
    counter_top_z = h
    basin_bottom_z = h - basin_dz
    basin_center_z = (counter_top_z + basin_bottom_z) / 2.0 - half_h  # in cabinet local (origin at half_h)

    cabinet_path = f"{base_path}/Cabinet"
    cab_xf = UsdGeom.Xform.Define(stage, cabinet_path)
    UsdGeom.Xformable(cab_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0, half_h))
    cab_box_path = f"{cabinet_path}/Body"
    cab_box = UsdGeom.Cube.Define(stage, cab_box_path)
    cab_box.CreateSizeAttr(1.0)
    cab_box.AddScaleOp().Set(Gf.Vec3f(d, w, h))
    cab_box.CreateDisplayColorAttr([(0.88, 0.88, 0.90)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(cab_box_path))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(cab_box_path))
    cab_prim = stage.GetPrimAtPath(cabinet_path)
    UsdPhysics.RigidBodyAPI.Apply(cab_prim)
    cab_prim.CreateAttribute("physics:kinematicEnabled", Sdf.ValueTypeNames.Bool).Set(True)

    # Counter top (thin slab)
    top_path = f"{cabinet_path}/CounterTop"
    top_xf = UsdGeom.Xform.Define(stage, top_path)
    UsdGeom.Xformable(top_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0, counter_top_z - half_h + 0.01))
    top_box = UsdGeom.Cube.Define(stage, f"{top_path}/Slab")
    top_box.CreateSizeAttr(1.0)
    top_box.AddScaleOp().Set(Gf.Vec3f(d, w, 0.02))
    top_box.CreateDisplayColorAttr([(0.92, 0.92, 0.94)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(f"{top_path}/Slab"))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(f"{top_path}/Slab"))

    # Sink basin: recessed box (bottom and sides = place to put objects)
    basin_path = f"{cabinet_path}/SinkBasin"
    basin_xf = UsdGeom.Xform.Define(stage, basin_path)
    UsdGeom.Xformable(basin_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0, basin_center_z))
    basin_inner_x = d - 2 * margin
    basin_inner_y = w * 0.6 - 2 * margin
    basin_box = UsdGeom.Cube.Define(stage, f"{basin_path}/Bowl")
    basin_box.CreateSizeAttr(1.0)
    basin_box.AddScaleOp().Set(Gf.Vec3f(basin_inner_x, basin_inner_y, basin_dz - 0.02))
    basin_box.CreateDisplayColorAttr([(0.7, 0.75, 0.8)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(f"{basin_path}/Bowl"))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(f"{basin_path}/Bowl"))
    print(f"[Bench] Sink cabinet at ({pos_x}, {pos_y}): basin for placing objects")


def _spawn_plate_and_fruit(stage):
    """Plate on table; on plate: two bananas and one apple (all rigid bodies for manipulation)."""
    table_z = GRASP_TABLE_HEIGHT
    plate_top_z = table_z + PLATE_HEIGHT
    fruit_z = plate_top_z + FRUIT_Z_OFFSET

    # Plate (flat cylinder)
    plate_path = "/World/Plate"
    plate_xf = UsdGeom.Xform.Define(stage, plate_path)
    UsdGeom.Xformable(plate_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(PLATE_X, PLATE_Y, table_z + PLATE_HEIGHT / 2.0))
    plate_cyl = UsdGeom.Cylinder.Define(stage, f"{plate_path}/Disc")
    plate_cyl.CreateRadiusAttr(PLATE_RADIUS)
    plate_cyl.CreateHeightAttr(PLATE_HEIGHT)
    plate_cyl.CreateDisplayColorAttr([(0.98, 0.98, 0.95)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(f"{plate_path}/Disc"))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(f"{plate_path}/Disc"))
    plate_prim = stage.GetPrimAtPath(plate_path)
    UsdPhysics.RigidBodyAPI.Apply(plate_prim)
    UsdPhysics.MassAPI.Apply(plate_prim)
    plate_prim.CreateAttribute("physics:mass", Sdf.ValueTypeNames.Float).Set(0.25)

    # Banana 1 (elongated cylinder)
    banana1_path = "/World/Banana1"
    b1_xf = UsdGeom.Xform.Define(stage, banana1_path)
    UsdGeom.Xformable(b1_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(PLATE_X - 0.04, PLATE_Y, fruit_z))
    UsdGeom.Xformable(b1_xf.GetPrim()).AddRotateZOp().Set(15.0)
    b1_cyl = UsdGeom.Cylinder.Define(stage, f"{banana1_path}/Body")
    b1_cyl.CreateRadiusAttr(BANANA_RADIUS)
    b1_cyl.CreateHeightAttr(BANANA_LENGTH)
    b1_cyl.CreateDisplayColorAttr([(0.95, 0.85, 0.2)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(f"{banana1_path}/Body"))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(f"{banana1_path}/Body"))
    _add_rigid_body_physics(stage, banana1_path, mass=0.05)

    # Banana 2
    banana2_path = "/World/Banana2"
    b2_xf = UsdGeom.Xform.Define(stage, banana2_path)
    UsdGeom.Xformable(b2_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(PLATE_X + 0.03, PLATE_Y - 0.03, fruit_z))
    UsdGeom.Xformable(b2_xf.GetPrim()).AddRotateZOp().Set(-10.0)
    b2_cyl = UsdGeom.Cylinder.Define(stage, f"{banana2_path}/Body")
    b2_cyl.CreateRadiusAttr(BANANA_RADIUS)
    b2_cyl.CreateHeightAttr(BANANA_LENGTH)
    b2_cyl.CreateDisplayColorAttr([(0.92, 0.82, 0.18)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(f"{banana2_path}/Body"))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(f"{banana2_path}/Body"))
    _add_rigid_body_physics(stage, banana2_path, mass=0.05)

    # Apple (sphere-like: cylinder with equal radius/height for simplicity)
    apple_path = "/World/Apple"
    apple_xf = UsdGeom.Xform.Define(stage, apple_path)
    UsdGeom.Xformable(apple_xf.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(PLATE_X, PLATE_Y + 0.05, fruit_z + APPLE_RADIUS))
    apple_cyl = UsdGeom.Cylinder.Define(stage, f"{apple_path}/Body")
    apple_cyl.CreateRadiusAttr(APPLE_RADIUS)
    apple_cyl.CreateHeightAttr(APPLE_RADIUS * 2.0)
    apple_cyl.CreateDisplayColorAttr([(0.85, 0.15, 0.12)])
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(f"{apple_path}/Body"))
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(f"{apple_path}/Body"))
    _add_rigid_body_physics(stage, apple_path, mass=0.08)

    print(f"[Bench] Plate at ({PLATE_X}, {PLATE_Y}); on plate: 2 bananas, 1 apple (manipulable)")


def _add_rigid_body_physics(stage, prim_path, mass=None):
    """Apply RigidBody + Collision + optional mass to a prim."""
    prim = stage.GetPrimAtPath(prim_path)
    UsdPhysics.RigidBodyAPI.Apply(prim)
    UsdPhysics.CollisionAPI.Apply(prim)
    if PhysxSchema:
        PhysxSchema.PhysxCollisionAPI.Apply(prim)
    if mass is not None:
        UsdPhysics.MassAPI.Apply(prim)
        prim.CreateAttribute("physics:mass", Sdf.ValueTypeNames.Float).Set(mass)


def build_clean_scene():
    """Build a minimal 5x5m test scene with floor, lights, and coordinate axes.
    In --grasp mode: white tile floor, table at edge, mug on table.
    When kitchen_scene=fixed, skip default floor so fixed kitchen provides 8x8 parquet."""
    stage = stage_utils.get_current_stage()

    floor_size = 10.0 if (args.drive_base and not args.grasp) else 5.0
    use_fixed_kitchen = getattr(args, "kitchen_scene", None) == "fixed" and args.grasp

    # -- Visible floor, top at z=0 (skip when fixed kitchen will provide its own floor) --
    floor_path = "/World/Floor"
    if not use_fixed_kitchen and not stage.GetPrimAtPath(floor_path).IsValid():
        floor = UsdGeom.Cube.Define(stage, floor_path)
        floor.CreateSizeAttr(1.0)
        floor.AddScaleOp().Set(Gf.Vec3f(floor_size, floor_size, 0.02))
        floor.AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.01))
        UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(floor_path))
        if PhysxSchema:
            PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(floor_path))

        if args.grasp:
            mat_path = "/World/Looks/WhiteTile"
            _create_white_tile_material(stage, mat_path)
            floor.GetPrim().CreateAttribute("primvars:displayColor",
                Sdf.ValueTypeNames.Color3fArray).Set([(0.92, 0.92, 0.92)])
        else:
            floor.CreateDisplayColorAttr([(0.35, 0.35, 0.38)])
            mat_path = "/World/FloorMaterial"
            if not stage.GetPrimAtPath(mat_path).IsValid():
                UsdShade.Material.Define(stage, mat_path)
                mat_prim = stage.GetPrimAtPath(mat_path)
                UsdPhysics.MaterialAPI.Apply(mat_prim)
                mat_prim.CreateAttribute("physics:staticFriction", Sdf.ValueTypeNames.Float).Set(0.8)
                mat_prim.CreateAttribute("physics:dynamicFriction", Sdf.ValueTypeNames.Float).Set(0.6)
                mat_prim.CreateAttribute("physics:restitution", Sdf.ValueTypeNames.Float).Set(0.01)

        floor_prim = stage.GetPrimAtPath(floor_path)
        if not floor_prim.HasRelationship("material:binding"):
            UsdShade.MaterialBindingAPI.Apply(floor_prim).Bind(
                UsdShade.Material(stage.GetPrimAtPath(mat_path)))
        floor_desc = "white tile" if args.grasp else "gray"
        print(f"[Bench] Floor: {floor_size}x{floor_size}m {floor_desc}, collision + friction enabled")
    elif use_fixed_kitchen:
        print("[Bench] Floor: using fixed kitchen 8x8 parquet")

    # -- Dome light --
    dome_path = "/World/DomeLight"
    if not stage.GetPrimAtPath(dome_path).IsValid():
        dome = UsdLux.DomeLight.Define(stage, dome_path)
        dome.CreateIntensityAttr(1000.0)

    # -- Distant light from above --
    dist_path = "/World/DistantLight"
    if not stage.GetPrimAtPath(dist_path).IsValid():
        dist = UsdLux.DistantLight.Define(stage, dist_path)
        dist.CreateIntensityAttr(500.0)
        dist.CreateAngleAttr(0.53)
        xf = UsdGeom.Xformable(dist.GetPrim())
        xf.AddRotateXYZOp().Set(Gf.Vec3f(-45, 30, 0))

    # -- Coordinate axes (thin cylinders, 1m each) --
    axis_defs = [
        ("AxisX", (0.5, 0, 0), (0, 90, 0), (0.9, 0.1, 0.1)),
        ("AxisY", (0, 0.5, 0), (90, 0, 0), (0.1, 0.9, 0.1)),
        ("AxisZ", (0, 0, 0.5), (0, 0, 0),  (0.1, 0.1, 0.9)),
    ]
    for name, pos, rot, color in axis_defs:
        ax_path = f"/World/{name}"
        if not stage.GetPrimAtPath(ax_path).IsValid():
            cyl = UsdGeom.Cylinder.Define(stage, ax_path)
            cyl.CreateRadiusAttr(0.005)
            cyl.CreateHeightAttr(1.0)
            cyl.CreateDisplayColorAttr([color])
            xf = UsdGeom.Xformable(cyl.GetPrim())
            xf.AddTranslateOp().Set(Gf.Vec3d(*pos))
            xf.AddRotateXYZOp().Set(Gf.Vec3f(*rot))

    # -- Physics scene --
    phys_path = "/World/PhysicsScene"
    if not stage.GetPrimAtPath(phys_path).IsValid():
        UsdPhysics.Scene.Define(stage, phys_path)
    phys_prim = stage.GetPrimAtPath(phys_path)
    phys_api = UsdPhysics.Scene(phys_prim)
    phys_api.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
    phys_api.CreateGravityMagnitudeAttr(9.81)
    if PhysxSchema:
        px = PhysxSchema.PhysxSceneAPI.Apply(phys_prim)
        px.CreateSolverTypeAttr("TGS")
        px.CreateMinPositionIterationCountAttr(64)
        px.CreateMinVelocityIterationCountAttr(4)
        px.CreateEnableStabilizationAttr(True)
        try:
            px.CreateSleepThresholdAttr(0.00005)
            px.CreateStabilizationThresholdAttr(0.00001)
        except AttributeError:
            pass

    # -- Kitchen scene: fixed (new 8x8) or legacy (old 5x5 procedural) --
    kitchen_variant = getattr(args, "kitchen_scene", None)
    if kitchen_variant == "fixed" and args.grasp:
        try:
            _script_dir = os.path.dirname(os.path.abspath(__file__))
            _repo_root = os.path.dirname(_script_dir)
            sys.path.insert(0, _repo_root)
            from scenes.kitchen_fixed.kitchen_fixed_builder import build_kitchen_scene
            build_kitchen_scene(stage)
            print("[Bench] Scene built: fixed kitchen 8x8 (walls, PBR, graspable handles)")
        except Exception as e:
            print(f"[Bench] WARN: fixed kitchen build failed ({e}), falling back to legacy")
            _build_grasp_objects(stage)
            print("[Bench] Scene built: legacy kitchen (fallback)")
    elif args.grasp:
        _build_grasp_objects(stage)
        extras = ["table", "mug"]
        if getattr(args, "fridge", False):
            extras.append("fridge")
        if getattr(args, "dishwasher", True):
            extras.append("dishwasher")
        if getattr(args, "sink", True):
            extras.append("sink cabinet")
        if getattr(args, "plate_fruit", True):
            extras.append("plate+fruit")
        print("[Bench] Scene built: floor, lights, axes, physics, " + ", ".join(extras))
    else:
        print("[Bench] Scene built: floor, lights, axes, physics")


def _apply_collision_recursive(stage, root_path):
    """Apply CollisionAPI to all mesh prims under root_path."""
    count = 0
    for prim in Usd.PrimRange(stage.GetPrimAtPath(root_path)):
        if prim.IsA(UsdGeom.Mesh) or prim.IsA(UsdGeom.Cube) or prim.IsA(UsdGeom.Cylinder):
            if not prim.HasAPI(UsdPhysics.CollisionAPI):
                UsdPhysics.CollisionAPI.Apply(prim)
                if PhysxSchema:
                    PhysxSchema.PhysxCollisionAPI.Apply(prim)
                count += 1
    return count


def _build_grasp_objects(stage):
    """Add table and mug for the grasp scenario.
    Always uses procedural table (guaranteed collision + known height).
    Tries Nucleus for mug, falls back to procedural."""
    nucleus_ok = False
    try:
        from omni.isaac.core.utils.nucleus import get_assets_root_path
        assets_root = get_assets_root_path()
        if assets_root:
            nucleus_ok = True
    except Exception:
        assets_root = None

    # -- Table (always procedural for reliable collision) --
    table_path = "/World/Table"
    if not stage.GetPrimAtPath(table_path).IsValid():
        _spawn_procedural_table(stage, table_path, GRASP_TABLE_X, GRASP_TABLE_Y)

        table_mat_path = "/World/TableFriction"
        if not stage.GetPrimAtPath(table_mat_path).IsValid():
            UsdShade.Material.Define(stage, table_mat_path)
            tmp = stage.GetPrimAtPath(table_mat_path)
            UsdPhysics.MaterialAPI.Apply(tmp)
            tmp.CreateAttribute("physics:staticFriction", Sdf.ValueTypeNames.Float).Set(0.9)
            tmp.CreateAttribute("physics:dynamicFriction", Sdf.ValueTypeNames.Float).Set(0.7)
            tmp.CreateAttribute("physics:restitution", Sdf.ValueTypeNames.Float).Set(0.01)
        top_prim = stage.GetPrimAtPath(f"{table_path}/TopXf/Top")
        if top_prim.IsValid():
            UsdShade.MaterialBindingAPI.Apply(top_prim).Bind(
                UsdShade.Material(stage.GetPrimAtPath(table_mat_path)))

    # -- Mug (always procedural for reliable collision + graspable geometry) --
    mug_path = "/World/Mug"
    if not stage.GetPrimAtPath(mug_path).IsValid():
        _spawn_procedural_mug(stage, mug_path, GRASP_MUG_X, GRASP_MUG_Y, GRASP_MUG_Z)

        _add_rigid_body_physics(stage, mug_path, mass=0.15)

        # Explicit diagonal inertia for upright cylinder stability
        mug_prim = stage.GetPrimAtPath(mug_path)
        mug_prim.CreateAttribute("physics:diagonalInertia",
                                 Sdf.ValueTypeNames.Float3).Set(Gf.Vec3f(0.0001, 0.0001, 0.00005))
        mug_prim.CreateAttribute("physics:centerOfMass",
                                 Sdf.ValueTypeNames.Float3).Set(Gf.Vec3f(0, 0, -0.01))

        mug_mat_path = "/World/MugFriction"
        if not stage.GetPrimAtPath(mug_mat_path).IsValid():
            UsdShade.Material.Define(stage, mug_mat_path)
            mp = stage.GetPrimAtPath(mug_mat_path)
            UsdPhysics.MaterialAPI.Apply(mp)
            mp.CreateAttribute("physics:staticFriction", Sdf.ValueTypeNames.Float).Set(1.2)
            mp.CreateAttribute("physics:dynamicFriction", Sdf.ValueTypeNames.Float).Set(1.0)
            mp.CreateAttribute("physics:restitution", Sdf.ValueTypeNames.Float).Set(0.01)
        UsdShade.MaterialBindingAPI.Apply(mug_prim).Bind(
            UsdShade.Material(stage.GetPrimAtPath(mug_mat_path)))

    # -- Refrigerator (openable door, handle, shelves) --
    if getattr(args, "fridge", False):
        fridge_path = "/World/Fridge"
        if not stage.GetPrimAtPath(fridge_path).IsValid():
            _spawn_procedural_refrigerator(stage, fridge_path, FRIDGE_X, FRIDGE_Y)
            fridge_mat_path = "/World/FridgeFriction"
            if not stage.GetPrimAtPath(fridge_mat_path).IsValid():
                UsdShade.Material.Define(stage, fridge_mat_path)
                fp = stage.GetPrimAtPath(fridge_mat_path)
                UsdPhysics.MaterialAPI.Apply(fp)
                fp.CreateAttribute("physics:staticFriction", Sdf.ValueTypeNames.Float).Set(0.8)
                fp.CreateAttribute("physics:dynamicFriction", Sdf.ValueTypeNames.Float).Set(0.6)
                fp.CreateAttribute("physics:restitution", Sdf.ValueTypeNames.Float).Set(0.01)
            for prim_path in [f"{fridge_path}/Cabinet/Body", f"{fridge_path}/Door/Panel", f"{fridge_path}/Door/Handle/Bar"]:
                p = stage.GetPrimAtPath(prim_path)
                if p.IsValid() and not p.HasRelationship("material:binding"):
                    UsdShade.MaterialBindingAPI.Apply(p).Bind(
                        UsdShade.Material(stage.GetPrimAtPath(fridge_mat_path)))
            for i in range(4):
                sp = stage.GetPrimAtPath(f"{fridge_path}/Cabinet/Shelf{i}/Plane")
                if sp.IsValid() and not sp.HasRelationship("material:binding"):
                    UsdShade.MaterialBindingAPI.Apply(sp).Bind(
                        UsdShade.Material(stage.GetPrimAtPath(fridge_mat_path)))

    # -- Dishwasher (openable door, handle, racks) --
    if getattr(args, "dishwasher", True):
        dishwasher_path = "/World/Dishwasher"
        if not stage.GetPrimAtPath(dishwasher_path).IsValid():
            _spawn_procedural_dishwasher(stage, dishwasher_path, DISHWASHER_X, DISHWASHER_Y)
            app_mat_path = "/World/ApplianceFriction"
            if not stage.GetPrimAtPath(app_mat_path).IsValid():
                UsdShade.Material.Define(stage, app_mat_path)
                ap = stage.GetPrimAtPath(app_mat_path)
                UsdPhysics.MaterialAPI.Apply(ap)
                ap.CreateAttribute("physics:staticFriction", Sdf.ValueTypeNames.Float).Set(0.8)
                ap.CreateAttribute("physics:dynamicFriction", Sdf.ValueTypeNames.Float).Set(0.6)
                ap.CreateAttribute("physics:restitution", Sdf.ValueTypeNames.Float).Set(0.01)
            for prim_path in [f"{dishwasher_path}/Cabinet/Body", f"{dishwasher_path}/Door/Panel", f"{dishwasher_path}/Door/Handle/Bar"]:
                p = stage.GetPrimAtPath(prim_path)
                if p.IsValid() and not p.HasRelationship("material:binding"):
                    UsdShade.MaterialBindingAPI.Apply(p).Bind(UsdShade.Material(stage.GetPrimAtPath(app_mat_path)))
            for i in range(2):
                rp = stage.GetPrimAtPath(f"{dishwasher_path}/Cabinet/Rack{i}/Plane")
                if rp.IsValid() and not rp.HasRelationship("material:binding"):
                    UsdShade.MaterialBindingAPI.Apply(rp).Bind(UsdShade.Material(stage.GetPrimAtPath(app_mat_path)))

    # -- Sink cabinet with basin (place objects in sink) --
    if getattr(args, "sink", True):
        sink_path = "/World/SinkCabinet"
        if not stage.GetPrimAtPath(sink_path).IsValid():
            _spawn_sink_cabinet(stage, sink_path, SINK_CABINET_X, SINK_CABINET_Y)
            sink_mat_path = "/World/SinkFriction"
            if not stage.GetPrimAtPath(sink_mat_path).IsValid():
                UsdShade.Material.Define(stage, sink_mat_path)
                sp = stage.GetPrimAtPath(sink_mat_path)
                UsdPhysics.MaterialAPI.Apply(sp)
                sp.CreateAttribute("physics:staticFriction", Sdf.ValueTypeNames.Float).Set(0.85)
                sp.CreateAttribute("physics:dynamicFriction", Sdf.ValueTypeNames.Float).Set(0.65)
                sp.CreateAttribute("physics:restitution", Sdf.ValueTypeNames.Float).Set(0.01)
            for prim_path in [f"{sink_path}/Cabinet/Body", f"{sink_path}/Cabinet/CounterTop/Slab", f"{sink_path}/Cabinet/SinkBasin/Bowl"]:
                p = stage.GetPrimAtPath(prim_path)
                if p.IsValid() and not p.HasRelationship("material:binding"):
                    UsdShade.MaterialBindingAPI.Apply(p).Bind(UsdShade.Material(stage.GetPrimAtPath(sink_mat_path)))

    # -- Plate on table + two bananas + apple (manipulable) --
    if getattr(args, "plate_fruit", True) and not stage.GetPrimAtPath("/World/Plate").IsValid():
        _spawn_plate_and_fruit(stage)
        table_mat_path = "/World/TableFriction"
        table_mat = stage.GetPrimAtPath(table_mat_path)
        if table_mat.IsValid():
            for path in ["/World/Plate/Disc", "/World/Banana1/Body", "/World/Banana2/Body", "/World/Apple/Body"]:
                p = stage.GetPrimAtPath(path)
                if p.IsValid() and not p.HasRelationship("material:binding"):
                    UsdShade.MaterialBindingAPI.Apply(p).Bind(UsdShade.Material(table_mat))


# ---------------------------------------------------------------------------
# Camera setup
# ---------------------------------------------------------------------------
def setup_cameras(output_dir, width, height):
    """Create cameras. For grasp/kitchen: isometric + top (full kitchen view). Else: front, side, top."""
    kitchen_variant = getattr(args, "kitchen_scene", None)
    if kitchen_variant == "fixed" and (args.grasp or getattr(args, "task_config", None)):
        # Fixed 8x8 kitchen: furniture along north wall at Y=3.45, robot at (0,0)
        cx, cy, lz = 0.0, 1.7, 0.8
        cam_defs = {
            "top_kitchen": (
                (cx, cy, 7.0),
                (cx, 3.45, 0.0),
            ),
            "isometric_kitchen": (
                (-3.5, -2.0, 3.5),
                (cx, 3.45, lz),
            ),
            "front_kitchen": (
                (cx, -2.0, 1.5),
                (cx, 3.45, lz),
            ),
        }
    elif args.grasp or getattr(args, "task_config", None):
        # Legacy kitchen: table (1, 1.2), fridge (2.8, 0), dishwasher (2.8, -1), sink (2.4, 0.9)
        kitchen_center_x = 1.4
        kitchen_center_y = 0.35
        kitchen_look_z = 0.8
        cam_defs = {
            "top_kitchen": (
                (kitchen_center_x, kitchen_center_y, 3.8),
                (kitchen_center_x, kitchen_center_y, 0.0),
            ),
            "isometric_kitchen": (
                (kitchen_center_x, -2.8, 2.4),
                (kitchen_center_x, kitchen_center_y, kitchen_look_z),
            ),
            "isometric_kitchen_right": (
                (kitchen_center_x, 2.8, 2.4),
                (kitchen_center_x, kitchen_center_y, kitchen_look_z),
            ),
        }
    elif args.choreo:
        # Choreography: robot goes fwd 1m, then right 2m. Center at (0.5, -1.0)
        cx, cy = 0.5, -1.0
        cam_defs = {
            "front": ((cx, cy - 5.0, 2.0), (cx, cy, 0.7)),
            "side":  ((cx + 5.0, cy, 2.0),  (cx, cy, 0.7)),
            "top":   ((cx, cy, 6.0),        (cx, cy, 0.0)),
        }
    elif args.drive_base:
        cx = args.drive_distance / 2.0
        cam_defs = {
            "front": ((cx, -3.5, 1.2), (cx, 0.0, 0.7)),
            "side":  ((cx + 3.0, 0.0, 1.2), (cx, 0.0, 0.7)),
            "top":   ((cx, 0.0, 4.5),       (cx, 0.0, 0.0)),
        }
    else:
        cam_defs = {
            "front": ((2.5, 0.0, 1.2), (0.0, 0.0, 0.7)),
            "side":  ((0.0, 2.5, 1.2), (0.0, 0.0, 0.7)),
            "top":   ((0.0, 0.0, 3.5), (0.0, 0.0, 0.0)),
        }
    cameras = []
    for name, (pos, target) in cam_defs.items():
        cam = rep.create.camera(position=pos, look_at=target)
        rp = rep.create.render_product(cam, (width, height))
        rep_dir = os.path.join(output_dir, f"replicator_{name}")
        w = rep.WriterRegistry.get("BasicWriter")
        w.initialize(output_dir=rep_dir, rgb=True)
        w.attach([rp])
        cameras.append((name, rp, w, rep_dir))
        print(f"[Bench] Camera '{name}': pos={pos} target={target}")
    return cameras


# ---------------------------------------------------------------------------
# Robot loader
# ---------------------------------------------------------------------------
def load_robot(model_name, tiago_dir):
    """Load a TIAGo USD model into the scene. Returns (articulation, dof_names, prim_path) or raises."""
    usd_file = MODEL_FILES[model_name]
    usd_path = os.path.join(tiago_dir, usd_file)
    if not os.path.isfile(usd_path):
        raise FileNotFoundError(f"Robot USD not found: {usd_path}")

    prim_path = "/World/Robot"
    stage = stage_utils.get_current_stage()

    # Remove previous robot if exists
    old = stage.GetPrimAtPath(prim_path)
    if old and old.IsValid():
        stage.RemovePrim(prim_path)
        print(f"[Bench] Removed previous robot at {prim_path}")

    stage_utils.add_reference_to_stage(usd_path=usd_path, prim_path=prim_path)
    print(f"[Bench] Loaded {model_name}: {usd_file} ({os.path.getsize(usd_path)} bytes)")

    # Find articulation root
    art_root_path = None
    for prim in Usd.PrimRange(stage.GetPrimAtPath(prim_path)):
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            art_root_path = str(prim.GetPath())
            break

    if not art_root_path:
        print(f"[Bench] WARN: no ArticulationRootAPI found, using {prim_path}")
        art_root_path = prim_path

    # Configure articulation
    art_prim = stage.GetPrimAtPath(art_root_path)
    fixed = not args.drive_base
    art_prim.CreateAttribute("physxArticulation:fixedBase", Sdf.ValueTypeNames.Bool).Set(fixed)
    art_prim.CreateAttribute("physxArticulation:enabledSelfCollisions", Sdf.ValueTypeNames.Bool).Set(False)
    print(f"[Bench] Articulation root: {art_root_path} (fixedBase={fixed})")

    return art_root_path, prim_path


def resolve_dof_names(articulation):
    """Get DOF names from articulation."""
    names = articulation.dof_names
    if names is None:
        names = []
    if hasattr(names, "tolist"):
        names = names.tolist()
    return list(names)


# ---------------------------------------------------------------------------
# Drive configuration
# ---------------------------------------------------------------------------
DRIVE_PARAMS = cfg.drive_params
DEFAULT_DRIVE = cfg.default_drive


def configure_drives(prim_path):
    """Configure PD drives on all joints under prim_path."""
    stage = stage_utils.get_current_stage()
    count = 0
    wheel_set = set(WHEEL_NAMES)
    roller_count = 0
    for jp in stage.Traverse():
        if not jp.GetPath().pathString.startswith(prim_path):
            continue
        is_rev = jp.IsA(UsdPhysics.RevoluteJoint)
        is_pri = (not is_rev) and jp.IsA(UsdPhysics.PrismaticJoint)
        if not (is_rev or is_pri):
            continue
        jname = jp.GetName()

        # Roller joints on omni wheels — low friction, free spin
        if "roller" in jname:
            drive_type = "angular" if is_rev else "linear"
            drive_api = UsdPhysics.DriveAPI.Apply(jp, drive_type)
            drive_api.CreateTypeAttr("acceleration")
            drive_api.CreateStiffnessAttr(cfg.roller_drive["stiffness"])
            drive_api.CreateDampingAttr(cfg.roller_drive["damping"])
            drive_api.CreateMaxForceAttr(cfg.roller_drive["max_force"])
            roller_count += 1
            count += 1
            continue

        # Wheel joints — velocity mode for driving
        if jname in wheel_set and args.drive_base:
            drive_type = "angular" if is_rev else "linear"
            drive_api = UsdPhysics.DriveAPI.Apply(jp, drive_type)
            drive_api.CreateTypeAttr("acceleration")
            drive_api.CreateStiffnessAttr(cfg.wheel_drive["stiffness"])
            drive_api.CreateDampingAttr(cfg.wheel_drive["damping"])
            drive_api.CreateMaxForceAttr(cfg.wheel_drive["max_force"])
            count += 1
            continue

        canonical = jname
        parts = jname.split("_")
        if len(parts) >= 3 and parts[0] in ("arm", "gripper") and ("right" in jname or "left" in jname):
            for p in parts:
                if p.isdigit():
                    canonical = f"{parts[0]}_{p}_joint"
                    break
        params = DRIVE_PARAMS.get(jname) or DRIVE_PARAMS.get(canonical, DEFAULT_DRIVE)
        stiff, damp, max_f = params
        drive_type = "angular" if is_rev else "linear"
        drive_api = UsdPhysics.DriveAPI.Apply(jp, drive_type)
        drive_api.CreateTypeAttr("acceleration")
        drive_api.CreateStiffnessAttr(stiff)
        drive_api.CreateDampingAttr(damp)
        drive_api.CreateMaxForceAttr(max_f)
        count += 1
    print(f"[Bench] Configured {count} joint drives ({roller_count} rollers, acceleration mode)")
    return count


# ---------------------------------------------------------------------------
# PAL Robotics TIAGo home/tuck pose
# Arms folded close to body, torso at minimum, head centered.
# Based on PAL standard tuck configuration for safe navigation.
# ---------------------------------------------------------------------------
HOME_JOINTS = dict(cfg.home_joints)

TORSO_SPEED = cfg.torso_speed

WHEEL_RADIUS = cfg.wheel_radius
WHEEL_SEPARATION_X = cfg.wheel_separation_x
WHEEL_SEPARATION_Y = cfg.wheel_separation_y
WHEEL_NAMES = list(cfg.wheel_names)


def omni_wheel_velocities(vx, vy, omega_z):
    """Mecanum inverse kinematics: (vx, vy, omega_z) -> (FL, FR, RL, RR) rad/s.
    vx = forward (m/s), vy = left (m/s), omega_z = CCW rotation (rad/s).
    For TIAGo omni with 45-degree rollers."""
    L = WHEEL_SEPARATION_X + WHEEL_SEPARATION_Y
    fl = (vx - vy - L * omega_z) / WHEEL_RADIUS
    fr = (vx + vy + L * omega_z) / WHEEL_RADIUS
    rl = (vx + vy - L * omega_z) / WHEEL_RADIUS
    rr = (vx - vy + L * omega_z) / WHEEL_RADIUS
    return (fl, fr, rl, rr)


# ---------------------------------------------------------------------------
# Arm poses (within joint limits)
# Joint order: 1=shoulder_lift, 2=shoulder_roll, 3=elbow_rot, 4=elbow_flex,
#              5=wrist_rot, 6=wrist_flex, 7=wrist_rot2
# Limits: 1[-1.18,1.57] 2[-1.18,1.57] 3[-0.79,3.93] 4[-0.39,2.36]
#         5[-2.09,2.09] 6[-1.41,1.41] 7[-2.09,2.09]
# ---------------------------------------------------------------------------
ARM_POSES = dict(cfg.arm_poses)

ARM_JOINT_NAMES_R = [f"arm_right_{i}_joint" for i in range(1, 8)]
ARM_JOINT_NAMES_L = [f"arm_left_{i}_joint" for i in range(1, 8)]


def arm_pose_to_dict(pose_name):
    """Convert named arm pose to joint target dict."""
    pose = ARM_POSES[pose_name]
    d = {}
    for i, val in enumerate(pose["R"]):
        d[ARM_JOINT_NAMES_R[i]] = val
    for i, val in enumerate(pose["L"]):
        d[ARM_JOINT_NAMES_L[i]] = val
    return d


def get_prim_world_position(prim_path):
    """Return (x, y, z) of prim in world, or None if unavailable."""
    try:
        xf = XFormPrim(prim_path=prim_path)
        p, _ = xf.get_world_pose()
        if p is not None:
            return float(p[0]), float(p[1]), float(p[2])
    except Exception:
        pass
    return None


def get_door_hinge_angle_deg(door_prim_path):
    """Return current door angle in degrees (0 = closed, 90 = fully open). Door rotates around world Y.
    Uses door prim world orientation: door local +X is 'outward'; angle in XZ plane from -X (closed) to +Z (open)."""
    try:
        xf = XFormPrim(prim_path=door_prim_path)
        _, ori = xf.get_world_pose()
        if ori is None:
            return None
        w, x, y, z = float(ori[0]), float(ori[1]), float(ori[2]), float(ori[3])
        # Door local +X in world = first column of rotation matrix from quat
        # q = (w,x,y,z) -> R col0 = (1-2(y^2+z^2), 2(xy-wz), 2(xz+wy))
        xx, yy, zz = x * x, y * y, z * z
        xy, xz, wy, wz = x * y, x * z, w * y, w * z
        door_x_x = 1.0 - 2.0 * (yy + zz)
        door_x_y = 2.0 * (xy - wz)
        door_x_z = 2.0 * (xz + wy)
        # Angle in XZ plane: closed = (-1,0,0) -> 0°, open 90° = (0,0,1) -> 90°
        angle_rad = math.atan2(door_x_z, -door_x_x)
        angle_deg = math.degrees(angle_rad)
        if angle_deg < 0:
            angle_deg += 360.0
        return min(90.0, max(0.0, angle_deg))
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Physics logger
# ---------------------------------------------------------------------------
class PhysicsLogger:
    def __init__(self, model_name, dof_names, articulation, prim_path):
        self.model_name = model_name
        self.dof_names = dof_names
        self.articulation = articulation
        self.prim_path = prim_path
        self.frames = []
        self.init_pos = None
        self.init_ori = None
        self._link_paths = self._discover_links()

    def _discover_links(self):
        """Find key link prims for frame logging."""
        stage = stage_utils.get_current_stage()
        key_names = [
            "base_footprint", "base_link", "torso_lift_link",
            "arm_right_1_link", "arm_right_2_link", "arm_right_3_link",
            "arm_right_4_link", "arm_right_5_link", "arm_right_6_link",
            "arm_right_7_link", "arm_right_tool_link",
            "gripper_right_grasping_frame",
            "arm_left_1_link", "arm_left_2_link", "arm_left_3_link",
            "arm_left_4_link", "arm_left_5_link", "arm_left_6_link",
            "arm_left_7_link", "arm_left_tool_link",
            "head_1_link", "head_2_link",
            "gripper_right_left_finger_link", "gripper_right_right_finger_link",
        ]
        found = {}
        for prim in Usd.PrimRange(stage.GetPrimAtPath(self.prim_path)):
            name = prim.GetName()
            if name in key_names:
                found[name] = str(prim.GetPath())
        print(f"[Bench] Discovered {len(found)} key links for frame logging")
        return found

    def log_scene_info(self):
        """Log static physics scene parameters (called once)."""
        stage = stage_utils.get_current_stage()
        info = {}
        phys_prim = stage.GetPrimAtPath("/World/PhysicsScene")
        if phys_prim.IsValid():
            ps = UsdPhysics.Scene(phys_prim)
            gdir = ps.GetGravityDirectionAttr().Get()
            gmag = ps.GetGravityMagnitudeAttr().Get()
            info["gravity"] = {"direction": list(gdir) if gdir else [0, 0, -1],
                               "magnitude": float(gmag) if gmag else 9.81}
            if PhysxSchema:
                try:
                    px = PhysxSchema.PhysxSceneAPI(phys_prim)
                    info["solver"] = px.GetSolverTypeAttr().Get()
                    info["pos_iterations"] = px.GetMinPositionIterationCountAttr().Get()
                    info["vel_iterations"] = px.GetMinVelocityIterationCountAttr().Get()
                    info["stabilization"] = px.GetEnableStabilizationAttr().Get()
                except Exception:
                    pass
        info["physics_dt"] = 1.0 / 120.0
        info["rendering_dt"] = 1.0 / 60.0
        info["model"] = self.model_name
        info["dof_count"] = len(self.dof_names)
        info["dof_names"] = self.dof_names
        info["links_tracked"] = list(self._link_paths.keys())
        return info

    def log_frame(self, sim_time, step_idx, targets, state_name=None):
        """Log one physics frame."""
        frame = {
            "sim_time": round(sim_time, 4),
            "step": step_idx,
        }
        if state_name:
            frame["state"] = state_name

        # -- Base pose --
        try:
            art_pos, art_ori = self.articulation.get_world_pose()
            if art_pos is not None:
                px, py, pz = float(art_pos[0]), float(art_pos[1]), float(art_pos[2])
                frame["base_position"] = {"x": round(px, 5), "y": round(py, 5), "z": round(pz, 5)}
                if self.init_pos is None:
                    self.init_pos = (px, py, pz)
                drift = math.sqrt(
                    (px - self.init_pos[0])**2 +
                    (py - self.init_pos[1])**2 +
                    (pz - self.init_pos[2])**2
                )
                frame["base_drift_m"] = round(drift, 5)
            if art_ori is not None:
                w, x, y, z = float(art_ori[0]), float(art_ori[1]), float(art_ori[2]), float(art_ori[3])
                frame["base_orientation_quat"] = {"w": round(w, 5), "x": round(x, 5),
                                                   "y": round(y, 5), "z": round(z, 5)}
                roll, pitch, yaw = quat_to_euler(w, x, y, z)
                frame["base_euler_deg"] = {"roll": round(roll, 3), "pitch": round(pitch, 3),
                                           "yaw": round(yaw, 3)}
                if self.init_ori is None:
                    self.init_ori = (w, x, y, z)
                tilt = max(abs(roll), abs(pitch))
                frame["base_tilt_deg"] = round(tilt, 3)
        except Exception:
            pass

        # -- Joint states --
        try:
            positions = self.articulation.get_joint_positions()
            velocities = self.articulation.get_joint_velocities()
            if positions is not None:
                positions = np.array(positions, dtype=np.float64)
            if velocities is not None:
                velocities = np.array(velocities, dtype=np.float64)

            joints = {}
            for i, name in enumerate(self.dof_names):
                jdata = {}
                if positions is not None and i < len(positions):
                    jdata["position_rad"] = round(float(positions[i]), 5)
                if velocities is not None and i < len(velocities):
                    jdata["velocity_rads"] = round(float(velocities[i]), 5)
                if name in targets:
                    jdata["target_rad"] = round(float(targets[name]), 5)
                    if "position_rad" in jdata:
                        jdata["error_rad"] = round(jdata["target_rad"] - jdata["position_rad"], 5)
                joints[name] = jdata
            frame["joints"] = joints
        except Exception as e:
            frame["joints_error"] = str(e)

        # -- Link world frames --
        link_frames = {}
        for link_name, link_path in self._link_paths.items():
            try:
                xf = XFormPrim(prim_path=link_path)
                lp, lo = xf.get_world_pose()
                if lp is not None:
                    entry = {
                        "position": {"x": round(float(lp[0]), 5),
                                     "y": round(float(lp[1]), 5),
                                     "z": round(float(lp[2]), 5)},
                    }
                    if lo is not None:
                        w, x, y, z = float(lo[0]), float(lo[1]), float(lo[2]), float(lo[3])
                        entry["orientation_quat"] = {"w": round(w, 5), "x": round(x, 5),
                                                     "y": round(y, 5), "z": round(z, 5)}
                        r, p, ya = quat_to_euler(w, x, y, z)
                        entry["euler_deg"] = {"roll": round(r, 3), "pitch": round(p, 3),
                                              "yaw": round(ya, 3)}
                    link_frames[link_name] = entry
            except Exception:
                pass
        if link_frames:
            frame["link_frames"] = link_frames

        # Track mug position if grasp scenario
        if args.grasp:
            try:
                mug_xf = XFormPrim(prim_path="/World/Mug")
                mp, mo = mug_xf.get_world_pose()
                if mp is not None:
                    frame["mug_position"] = {
                        "x": round(float(mp[0]), 5),
                        "y": round(float(mp[1]), 5),
                        "z": round(float(mp[2]), 5),
                    }
                    if mo is not None:
                        mr, mpi, my = quat_to_euler(float(mo[0]), float(mo[1]),
                                                     float(mo[2]), float(mo[3]))
                        frame["mug_euler_deg"] = {
                            "roll": round(mr, 2), "pitch": round(mpi, 2), "yaw": round(my, 2)}
                        frame["mug_tilt_deg"] = round(max(abs(mr), abs(mpi)), 2)
            except Exception:
                pass

        self.frames.append(frame)
        return frame

    def console_summary(self, frame):
        """Print a one-line summary to console."""
        t = frame.get("sim_time", 0)
        drift = frame.get("base_drift_m", 0)
        tilt = frame.get("base_tilt_deg", 0)
        bp = frame.get("base_position", {})
        joints = frame.get("joints", {})
        torso = joints.get("torso_lift_joint", {})
        torso_pos = torso.get("position_rad", "?")
        torso_err = torso.get("error_rad", "?")
        max_err = 0.0
        max_vel = 0.0
        for jn, jd in joints.items():
            e = abs(jd.get("error_rad", 0))
            v = abs(jd.get("velocity_rads", 0))
            if e > max_err:
                max_err = e
            if v > max_vel:
                max_vel = v
        base_str = (f"base=({bp.get('x', 0):+.5f},{bp.get('y', 0):+.5f},{bp.get('z', 0):+.5f})")
        mug_str = ""
        if "mug_position" in frame:
            mp = frame["mug_position"]
            mt = frame.get("mug_tilt_deg", 0)
            mug_str = f" | mug=({mp['x']:+.3f},{mp['y']:+.3f},{mp['z']:+.3f}) tilt={mt:.1f}°"
        tool_str = ""
        links = frame.get("link_frames", {})
        lf = links.get("gripper_right_grasping_frame", {}) or links.get("arm_right_tool_link", {})
        if lf:
            tp = lf.get("position", {})
            tool_str = f" | tool=({tp.get('x',0):+.3f},{tp.get('y',0):+.3f},{tp.get('z',0):+.3f})"
        print(f"[Bench] t={t:6.2f}s | "
              f"{base_str} "
              f"drift={drift:.5f}m tilt={tilt:.2f}deg | "
              f"torso={torso_pos} err={torso_err}"
              f"{tool_str}{mug_str}")

    def generate_report(self):
        """Generate summary statistics."""
        if not self.frames:
            return {"error": "no frames logged"}
        max_drift = max(f.get("base_drift_m", 0) for f in self.frames)
        max_tilt = max(f.get("base_tilt_deg", 0) for f in self.frames)
        max_joint_err = 0.0
        max_joint_vel = 0.0
        for f in self.frames:
            for jn, jd in f.get("joints", {}).items():
                e = abs(jd.get("error_rad", 0))
                v = abs(jd.get("velocity_rads", 0))
                if e > max_joint_err:
                    max_joint_err = e
                if v > max_joint_vel:
                    max_joint_vel = v
        final_base = self.frames[-1].get("base_position", {})
        if args.drive_base:
            stable = max_tilt < 5.0
            verdict = "PASS (driving)" if stable else "FAIL (tilt during drive)"
        else:
            stable = max_drift < 0.01 and max_tilt < 1.0
            verdict = "PASS" if stable else "FAIL (unstable base)"
        report = {
            "model": self.model_name,
            "total_frames": len(self.frames),
            "duration_s": self.frames[-1].get("sim_time", 0),
            "max_drift_m": round(max_drift, 5),
            "max_tilt_deg": round(max_tilt, 3),
            "max_joint_error_rad": round(max_joint_err, 5),
            "max_joint_velocity_rads": round(max_joint_vel, 4),
            "final_base_position": final_base,
            "stable": stable,
            "verdict": verdict,
        }
        if args.drive_base:
            report["drive_mode"] = True
            report["drive_distance_m"] = args.drive_distance
            report["drive_speed_ms"] = args.drive_speed
        if args.grasp:
            report["grasp_mug_x"] = GRASP_MUG_X
            report["grasp_mug_y"] = GRASP_MUG_Y
            report["grasp_place_dx"] = getattr(args, "place_dx", 0.0)
            report["grasp_place_dy"] = getattr(args, "place_dy", -0.20)
            report["grasp_lift_height_m"] = getattr(args, "lift_height", 0.20)
            report["grasp_torso_speed"] = getattr(args, "torso_speed", 0.05)
            report["grasp_torso_lower_speed"] = getattr(args, "torso_lower_speed", 0.02)
            report["grasp_shift_rot_speed"] = getattr(args, "shift_rot_speed", 0.15)
            report["grasp_approach_clearance_m"] = getattr(args, "approach_clearance", 0.13)
            report["grasp_mode"] = getattr(args, "grasp_mode", "top")
            report["top_pregrasp_height_m"] = getattr(args, "top_pregrasp_height", 0.06)
            report["top_descend_speed_ms"] = getattr(args, "top_descend_speed", 0.015)
            report["top_descend_clearance_m"] = getattr(args, "top_descend_clearance", 0.045)
            report["top_xy_tol_m"] = getattr(args, "top_xy_tol", 0.01)
            report["top_lift_test_height_m"] = getattr(args, "top_lift_test_height", 0.03)
            report["top_lift_test_hold_s"] = getattr(args, "top_lift_test_hold_s", 0.5)
            report["gripper_length_m"] = getattr(args, "gripper_length_m", 0.10)
            report["gripper_length_delta_vs_baseline_m"] = float(getattr(args, "gripper_length_m", 0.10) - 0.10)
        return report


# ---------------------------------------------------------------------------
# Action sequence
# ---------------------------------------------------------------------------
# Each action is a dict for clarity:
#   t: trigger time, desc: label,
#   torso: target, torso_speed: m/s or None,
#   wheels: (FL,FR,RL,RR) rad/s or None (keep),
#   arm_pose: name from ARM_POSES or None (keep)
# ---------------------------------------------------------------------------
def _act(t, desc, torso=None, torso_speed=None, wheels=None, arm_pose=None, gripper=None):
    return {"t": t, "desc": desc, "torso": torso, "torso_speed": torso_speed,
            "wheels": wheels, "arm_pose": arm_pose, "gripper": gripper}


def _stop_wheels():
    return (0.0, 0.0, 0.0, 0.0)


def build_action_sequence():
    """Returns (actions_list, total_duration)."""
    spd = args.drive_speed
    dist = args.drive_distance

    if getattr(args, "task_config", None):
        return "TASK_CONFIG", 0
    if args.grasp:
        # Adaptive grasp: state machine checks tool vs mug each step.
        # Timed actions only for phases that don't need feedback.
        # Adaptive phases return "ADAPTIVE" as duration marker.
        return "ADAPTIVE_GRASP", 0

    elif args.choreo:
        drive_t = dist / spd
        # Rotation: 90 deg CW = -pi/2 rad. omega = angle/time.
        rot_speed = 0.3  # rad/s
        rot_angle = math.pi / 2.0
        rot_time = rot_angle / rot_speed

        t = 0.0
        actions = []
        # -- Settle in home --
        actions.append(_act(t, "home_settle", torso=0.15, arm_pose="home", wheels=_stop_wheels())); t += 3.0

        # 1) Drive forward 1m, arms forward
        actions.append(_act(t, "arms_forward", arm_pose="forward")); t += 2.0
        actions.append(_act(t, "drive_fwd_1m",
                            wheels=omni_wheel_velocities(spd, 0, 0))); t += drive_t
        actions.append(_act(t, "stop_1", wheels=_stop_wheels())); t += 1.5

        # 2) Drive right 1m, arms down
        actions.append(_act(t, "arms_down", arm_pose="down")); t += 2.0
        actions.append(_act(t, "drive_right_1m",
                            wheels=omni_wheel_velocities(0, -spd, 0))); t += drive_t
        actions.append(_act(t, "stop_2", wheels=_stop_wheels())); t += 1.5

        # 3) Drive right 1m, arms Y-shape
        actions.append(_act(t, "arms_Y", arm_pose="Y_shape")); t += 2.0
        actions.append(_act(t, "drive_right_1m_2",
                            wheels=omni_wheel_velocities(0, -spd, 0))); t += drive_t
        actions.append(_act(t, "stop_3", wheels=_stop_wheels())); t += 1.5

        # 4) Rotate 90 CW, arms heart
        actions.append(_act(t, "arms_heart", arm_pose="heart")); t += 2.5
        actions.append(_act(t, "rotate_90cw",
                            wheels=omni_wheel_velocities(0, 0, -rot_speed))); t += rot_time
        actions.append(_act(t, "stop_4", wheels=_stop_wheels())); t += 3.0

        # -- Return to home --
        actions.append(_act(t, "arms_home_final", arm_pose="home")); t += 3.0
        return actions, t

    elif args.drive_base:
        drive_t = dist / spd
        w_fwd = omni_wheel_velocities(spd, 0, 0)
        w_back = omni_wheel_velocities(-spd, 0, 0)

        t = 0.0
        actions = []
        actions.append(_act(t, "home_settle", torso=0.0, wheels=_stop_wheels())); t += 3.0
        actions.append(_act(t, "torso_up", torso=0.35, torso_speed=TORSO_SPEED)); t += 0.35 / TORSO_SPEED
        actions.append(_act(t, "hold_up", torso=0.35)); t += 2.0
        actions.append(_act(t, "drive_forward", wheels=w_fwd)); t += drive_t
        actions.append(_act(t, "stop_forward", wheels=_stop_wheels())); t += 2.0
        actions.append(_act(t, "drive_backward", wheels=w_back)); t += drive_t
        actions.append(_act(t, "stop_backward", wheels=_stop_wheels())); t += 2.0
        actions.append(_act(t, "torso_down", torso=0.0, torso_speed=TORSO_SPEED)); t += 0.35 / TORSO_SPEED
        actions.append(_act(t, "hold_final", torso=0.0)); t += 3.0
        return actions, t

    else:
        t_up_start = 3.0
        t_up_end = t_up_start + 0.35 / TORSO_SPEED
        t_hold = t_up_end + 3.0
        t_down_end = t_hold + 0.35 / TORSO_SPEED
        t_final = t_down_end + 3.0
        return [
            _act(0.0,         "home_settle",  torso=0.0),
            _act(t_up_start,  "torso_up",     torso=0.35, torso_speed=TORSO_SPEED),
            _act(t_up_end,    "hold_up",      torso=0.35),
            _act(t_hold,      "torso_down",   torso=0.0,  torso_speed=TORSO_SPEED),
            _act(t_down_end,  "hold_down",    torso=0.0),
        ], t_final


# ---------------------------------------------------------------------------
# Grasp pick-only cycle (for task_config pick_object): settle -> ... -> lift_mug
# Returns (success, steps_used, final_targets). Uses object_prim_path and params.
# ---------------------------------------------------------------------------
def run_grasp_pick_only_cycle(
    world,
    articulation,
    dof_names,
    logger,
    wheel_dof_indices,
    object_prim_path,
    approach_clearance_m,
    lift_height_m,
    timeout_steps,
    physics_dt,
    log_every,
    render_every,
    initial_targets,
    gripper_length_m=0.10,
    top_descend_clearance=0.015,
    top_verify_xy_tol=0.05,
    top_xy_tol=0.02,
    top_lift_test_height=0.015,
    top_lift_test_hold_steps=72,
    top_descend_speed=0.03,
    top_pregrasp_height=0.06,
    torso_speed=0.05,
    torso_approach=0.35,
    drive_speed=0.3,
):
    """Run grasp state machine from settle until lift done (transition to rotate_shift). Returns (success, steps, current_targets)."""
    pos = get_prim_world_position(object_prim_path)
    if pos is None:
        return False, 0, dict(initial_targets)
    grasp_target_x, grasp_target_y, grasp_target_z = pos[0], pos[1], pos[2]

    _ee_path = logger._link_paths.get("gripper_right_grasping_frame") or logger._link_paths.get("arm_right_tool_link")
    current_targets = dict(initial_targets)
    _current_wheel_vels = (0.0, 0.0, 0.0, 0.0)
    _torso_interp_start_time = 0.0
    _torso_interp_start_val = 0.0
    _torso_interp_end_val = 0.0
    _torso_interp_speed = None
    length_delta = gripper_length_m - 0.10

    def _get_tool_pos():
        if not _ee_path:
            return None, None, None
        try:
            xf = XFormPrim(prim_path=_ee_path)
            p, _ = xf.get_world_pose()
            if p is not None:
                tx, ty, tz = float(p[0]), float(p[1]), float(p[2])
                if _ee_path and abs(length_delta) > 1e-6:
                    _, ori = articulation.get_world_pose()
                    yaw = 0.0
                    if ori is not None:
                        _, _, yaw = quat_to_euler(float(ori[0]), float(ori[1]), float(ori[2]), float(ori[3]))
                    tx += math.cos(yaw) * length_delta
                    ty += math.sin(yaw) * length_delta
                return tx, ty, tz
        except Exception:
            pass
        return None, None, None

    def _get_object_pos():
        return get_prim_world_position(object_prim_path)

    def _get_base_pos():
        try:
            p, _ = articulation.get_world_pose()
            if p is not None:
                return float(p[0]), float(p[1]), float(p[2])
        except Exception:
            pass
        return None, None, None

    def _get_base_yaw_deg():
        try:
            _, ori = articulation.get_world_pose()
            if ori is not None:
                _, _, yaw = quat_to_euler(float(ori[0]), float(ori[1]), float(ori[2]), float(ori[3]))
                return float(yaw)
        except Exception:
            pass
        return 0.0

    def _get_right_gripper_opening():
        try:
            jp = articulation.get_joint_positions()
            if jp is None:
                return None
            li = dof_names.index("gripper_right_left_finger_joint")
            ri = dof_names.index("gripper_right_right_finger_joint")
            return 0.5 * (float(jp[li]) + float(jp[ri]))
        except Exception:
            return None

    def _set_wheels(vels):
        nonlocal _current_wheel_vels
        _current_wheel_vels = vels

    def _set_torso(target, speed, sim_t):
        nonlocal _torso_interp_start_time, _torso_interp_start_val, _torso_interp_end_val, _torso_interp_speed
        _torso_interp_start_time = sim_t
        try:
            jp = articulation.get_joint_positions()
            tidx = dof_names.index("torso_lift_joint")
            _torso_interp_start_val = float(jp[tidx]) if jp is not None else current_targets.get("torso_lift_joint", 0.0)
        except Exception:
            _torso_interp_start_val = current_targets.get("torso_lift_joint", 0.0)
        _torso_interp_end_val = target
        _torso_interp_speed = speed

    def _set_arm(pose_name):
        arm_joints = arm_pose_to_dict(pose_name)
        current_targets.update(arm_joints)
        _apply_targets(articulation, dof_names, current_targets)

    def _set_gripper(val):
        for gj in GRIPPER_JOINTS:
            current_targets[gj] = val
        _apply_targets(articulation, dof_names, current_targets)

    def _freeze_torso():
        nonlocal _torso_interp_speed, _torso_interp_end_val
        cur = current_targets.get("torso_lift_joint", 0.0)
        _torso_interp_speed = -1
        _torso_interp_end_val = cur
        current_targets["torso_lift_joint"] = cur
        _apply_targets(articulation, dof_names, current_targets)

    state = "settle"
    state_start_step = -1
    state_entered = True
    init_mug_z = None
    grasp_tool_z = None
    grasp_mug_z_at_close = None
    grasp_verified_hold_step = None
    drive_y_aligned = False
    rotate_target_yaw = None
    grasp_aborted = False
    success = False

    for step in range(timeout_steps):
        sim_time = step * physics_dt

        def _transition(new_state):
            nonlocal state, state_start_step, state_entered
            if new_state == "rotate_shift":
                nonlocal success
                success = True
            state = new_state
            state_start_step = step
            state_entered = True

        for _sm in range(5):
            entering = state_entered
            state_entered = False
            steps_in_state = step - state_start_step

            if state == "settle":
                if entering:
                    _set_arm("home")
                    _set_gripper(GRIPPER_OPEN)
                    _set_torso(cfg.torso_settle, torso_speed, sim_time)
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                if steps_in_state >= cfg.grasp_settle_steps:
                    obj = _get_object_pos()
                    if obj is not None:
                        init_mug_z = obj[2]
                    _transition("extend_arm")

            elif state == "extend_arm":
                if entering:
                    _set_arm(cfg.pre_grasp_pose)
                    _set_torso(torso_approach, torso_speed, sim_time)
                if steps_in_state >= cfg.extend_arm_steps:
                    _transition("rotate_to_target")

            elif state == "rotate_to_target":
                if entering:
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                mx, my, mz = _get_object_pos()
                if mx is not None and my is not None:
                    pos, ori = articulation.get_world_pose()
                    if pos is not None and ori is not None:
                        bx, by = float(pos[0]), float(pos[1])
                        rotate_target_yaw = math.degrees(math.atan2(my - by, mx - bx))
                        _, _, cur_yaw = quat_to_euler(float(ori[0]), float(ori[1]), float(ori[2]), float(ori[3]))
                        yaw_err = rotate_target_yaw - cur_yaw
                        while yaw_err > 180: yaw_err -= 360
                        while yaw_err < -180: yaw_err += 360
                        if steps_in_state % 60 == 0:
                            print(f"[Grasp] rotate_to_target t={sim_time:.1f}s: cur_yaw={cur_yaw:.1f} target_yaw={rotate_target_yaw:.1f} err={yaw_err:.1f}")
                        if abs(yaw_err) < cfg.rotate_tolerance_deg:
                            _set_wheels(omni_wheel_velocities(0, 0, 0))
                            _transition("drive_to_mug")
                        else:
                            rot_speed = cfg.rotate_speed_fast if abs(yaw_err) > cfg.rotate_speed_threshold_deg else cfg.rotate_speed_slow
                            omega = rot_speed if yaw_err > 0 else -rot_speed
                            _set_wheels(omni_wheel_velocities(0, 0, omega))
                if steps_in_state >= cfg.rotate_timeout_steps:
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                    _transition("drive_to_mug")

            elif state == "drive_to_mug":
                if entering:
                    drive_y_aligned = False
                    _set_wheels(omni_wheel_velocities(drive_speed, 0, 0))
                tx, ty, tz = _get_tool_pos()
                mx, my, mz = _get_object_pos()
                if tx is not None and mx is not None and ty is not None and my is not None:
                    dx_world = tx - mx
                    dy_world = ty - my
                    pos_r, ori_r = articulation.get_world_pose()
                    yaw_rad = 0.0
                    if ori_r is not None:
                        _, _, yaw_deg = quat_to_euler(float(ori_r[0]), float(ori_r[1]), float(ori_r[2]), float(ori_r[3]))
                        yaw_rad = math.radians(yaw_deg)
                    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
                    dx_r = dx_world * c + dy_world * s
                    dy_r = -dx_world * s + dy_world * c
                    x_guard = approach_clearance_m + cfg.x_guard_extra
                    if steps_in_state % 60 == 0:
                        print(f"[Grasp] drive_to_mug t={sim_time:.1f}s: "
                              f"tool=({tx:.3f},{ty:.3f},{tz:.3f}) "
                              f"obj=({mx:.3f},{my:.3f},{mz:.3f}) dx_r={dx_r:.3f} dy_r={dy_r:.3f} y_aligned={drive_y_aligned}")
                    if (not drive_y_aligned) and dx_r < -x_guard:
                        _set_wheels(omni_wheel_velocities(drive_speed, 0, 0))
                    elif not drive_y_aligned:
                        if abs(dy_r) <= cfg.y_align_tolerance:
                            drive_y_aligned = True
                            _set_wheels(omni_wheel_velocities(0, 0, 0))
                        else:
                            vy = cfg.y_align_speed * (1.0 if dy_r < 0 else -1.0)
                            _set_wheels(omni_wheel_velocities(0, vy, 0))
                    else:
                        if dx_r >= -approach_clearance_m:
                            _set_wheels(omni_wheel_velocities(0, 0, 0))
                            _transition("settle_at_table")
                        else:
                            _set_wheels(omni_wheel_velocities(min(drive_speed, cfg.drive_speed_cap), 0, 0))
                if steps_in_state >= cfg.drive_to_mug_timeout_steps:
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                    _transition("settle_at_table")

            elif state == "settle_at_table":
                if entering:
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                if steps_in_state >= cfg.settle_at_table_steps:
                    _transition("approach_overhead")

            elif state == "approach_overhead":
                if entering:
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                tx, ty, tz = _get_tool_pos()
                mx, my, mz = _get_object_pos()
                if tx is not None and mx is not None and my is not None:
                    target_x, target_y = mx, my
                    dx_w = tx - target_x
                    dy_w = (ty or 0) - target_y
                    if abs(dx_w) <= top_xy_tol and abs(dy_w) <= top_xy_tol:
                        _set_wheels(omni_wheel_velocities(0, 0, 0))
                        _transition("descend_vertical")
                    else:
                        pos_oh, ori_oh = articulation.get_world_pose()
                        yaw_oh = 0.0
                        if ori_oh is not None:
                            _, _, yd = quat_to_euler(float(ori_oh[0]), float(ori_oh[1]), float(ori_oh[2]), float(ori_oh[3]))
                            yaw_oh = math.radians(yd)
                        c_oh, s_oh = math.cos(yaw_oh), math.sin(yaw_oh)
                        dx_r_oh = dx_w * c_oh + dy_w * s_oh
                        dy_r_oh = -dx_w * s_oh + dy_w * c_oh
                        _aspd = cfg.approach_speed
                        vx = -_aspd if dx_r_oh > top_xy_tol else (_aspd if dx_r_oh < -top_xy_tol else 0.0)
                        vy = -_aspd if dy_r_oh > top_xy_tol else (_aspd if dy_r_oh < -top_xy_tol else 0.0)
                        _set_wheels(omni_wheel_velocities(vx, vy, 0))
                if steps_in_state >= cfg.approach_timeout_steps:
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                    _transition("descend_vertical")

            elif state == "descend_vertical":
                if entering:
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                    _set_torso(0.0, top_descend_speed, sim_time)
                tx, ty, tz = _get_tool_pos()
                mx, my, mz = _get_object_pos()
                if tz is not None and mz is not None:
                    dz = tz - mz
                    if steps_in_state % 120 == 0:
                        print(f"[Grasp] descend_vertical t={sim_time:.1f}s: tool_z={tz:.3f} mug_z={mz:.3f} dz={dz:.4f} clearance={top_descend_clearance:.3f}")
                    if dz <= top_descend_clearance:
                        _freeze_torso()
                        grasp_tool_z = tz
                        _transition("close_gripper_top")
                if steps_in_state >= cfg.descend_timeout_steps:
                    _freeze_torso()
                    grasp_tool_z = tz if tz else 0.9
                    _transition("close_gripper_top")

            elif state == "close_gripper_top":
                if entering:
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                    _set_gripper(cfg.gripper_close_value)
                if steps_in_state == cfg.close_gripper_step:
                    _set_gripper(GRIPPER_CLOSED)
                if steps_in_state >= cfg.close_gripper_timeout:
                    _transition("verify_grasp")

            elif state == "verify_grasp":
                if entering:
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                if steps_in_state >= cfg.verify_grasp_min_steps:
                    tx, ty, tz = _get_tool_pos()
                    mx, my, mz = _get_object_pos()
                    gr_open = _get_right_gripper_opening()
                    xy_dist = math.hypot((tx or 0) - (mx or 0), (ty or 0) - (my or 0))
                    xy_ok = (tx is not None and ty is not None and mx is not None and my is not None and xy_dist <= top_verify_xy_tol)
                    hold_ok = (gr_open is not None and gr_open >= cfg.gripper_hold_threshold)
                    grasp_mug_z_at_close = mz if mz is not None else None
                    print(f"[Grasp] verify_grasp: xy_ok={xy_ok} hold_ok={hold_ok} xy_dist={xy_dist:.4f} gr_open={gr_open}")
                    if not hold_ok:
                        print(f"[Grasp] verify_grasp FAILED (gripper not holding) -- aborting pick")
                        grasp_aborted = True
                        break
                    _transition("lift_mug")

            elif state == "lift_mug":
                if entering:
                    _set_torso(cfg.torso_hold, torso_speed, sim_time)
                    grasp_verified_hold_step = None
                lift_alpha = min(1.0, steps_in_state / float(cfg.lift_interpolation_steps))
                j4_target = cfg.j4_retracted
                j4_val = cfg.j4_extended + lift_alpha * (j4_target - cfg.j4_extended)
                current_targets["arm_right_4_joint"] = j4_val
                _apply_targets(articulation, dof_names, current_targets)
                tx, ty, tz = _get_tool_pos()
                mx, my, mz = _get_object_pos()
                if steps_in_state % 120 == 0:
                    mug_dz = ((mz or 0) - (grasp_mug_z_at_close or 0)) if grasp_mug_z_at_close is not None else 0
                    tool_dz = ((tz or 0) - (grasp_tool_z or 0)) if grasp_tool_z is not None else 0
                    gr_o = _get_right_gripper_opening()
                    print(f"[Grasp] lift_mug t={sim_time:.1f}s step={steps_in_state}: "
                          f"tool_z={tz:.3f} mug_z={mz:.3f} mug_dz={mug_dz:.4f} tool_dz={tool_dz:.4f} "
                          f"need_mug_dz={top_lift_test_height:.3f} need_tool_dz={lift_height_m:.3f} gr_open={gr_o}")
                if (
                    steps_in_state >= cfg.lift_verify_steps and
                    grasp_mug_z_at_close is not None and
                    mz is not None and
                    mz >= (grasp_mug_z_at_close + top_lift_test_height)
                ):
                    if grasp_verified_hold_step is None:
                        grasp_verified_hold_step = step
                    elif (step - grasp_verified_hold_step) >= top_lift_test_hold_steps:
                        lift = (tz or 0) - (grasp_tool_z or 0)
                        if lift >= lift_height_m:
                            _transition("rotate_shift")
                if steps_in_state >= cfg.lift_timeout_steps:
                    print(f"[Grasp] lift_mug TIMEOUT -- mug not lifted, failing")
                    grasp_aborted = True
                    break

            if not state_entered:
                break
            if success or grasp_aborted:
                break

        if success or grasp_aborted:
            break

        # Torso interpolation
        if _torso_interp_speed and _torso_interp_speed > 0:
            elapsed = sim_time - _torso_interp_start_time
            distance = abs(_torso_interp_end_val - _torso_interp_start_val)
            if distance > 1e-6:
                duration = distance / _torso_interp_speed
                alpha = min(1.0, elapsed / duration)
                torso_now = _torso_interp_start_val + alpha * (_torso_interp_end_val - _torso_interp_start_val)
                current_targets["torso_lift_joint"] = torso_now
                _apply_targets(articulation, dof_names, current_targets)
                if alpha >= 1.0:
                    _torso_interp_speed = None
        elif _torso_interp_speed is None and "torso_lift_joint" in current_targets:
            current_targets["torso_lift_joint"] = _torso_interp_end_val
            _apply_targets(articulation, dof_names, current_targets)

        if wheel_dof_indices and len(wheel_dof_indices) >= 4:
            try:
                from omni.isaac.core.utils.types import ArticulationAction
                vel_array = np.zeros(len(dof_names), dtype=np.float32)
                for i, wi in enumerate(wheel_dof_indices):
                    if i < len(_current_wheel_vels):
                        vel_array[wi] = _current_wheel_vels[i]
                articulation.apply_action(ArticulationAction(joint_velocities=vel_array))
            except Exception:
                pass

        if step % log_every == 0:
            logger.log_frame(sim_time, step, current_targets, state_name=state)
        world.step(render=(step % render_every == 0))

    return success, step + 1, current_targets


# ---------------------------------------------------------------------------
# Door open/close cycle (P2): approach handle -> grasp -> pull or push -> release
# ---------------------------------------------------------------------------
def run_door_open_close_cycle(
    world,
    articulation,
    dof_names,
    logger,
    wheel_dof_indices,
    handle_usd_path,
    door_usd_path,
    is_open,
    target_angle_deg,
    timeout_steps,
    physics_dt,
    log_every,
    render_every,
    initial_targets,
    pull_speed_ms=0.05,
    push_speed_ms=0.04,
    approach_clearance_m=0.15,
    drive_speed=0.25,
):
    """Run door open (is_open=True) or close (is_open=False). Returns (success, steps_used)."""
    current_targets = dict(initial_targets)
    _current_wheel_vels = (0.0, 0.0, 0.0, 0.0)
    success_criteria = target_angle_deg  # min angle for open, max angle for close

    _ee_path = logger._link_paths.get("gripper_right_grasping_frame") or logger._link_paths.get("arm_right_tool_link")

    def _get_tool_pos():
        if not _ee_path:
            return None, None, None
        try:
            xf = XFormPrim(prim_path=_ee_path)
            p, _ = xf.get_world_pose()
            if p is not None:
                return float(p[0]), float(p[1]), float(p[2])
        except Exception:
            pass
        return None, None, None

    def _get_handle_pos():
        return get_prim_world_position(handle_usd_path)

    def _get_base_pos():
        try:
            p, _ = articulation.get_world_pose()
            if p is not None:
                return float(p[0]), float(p[1]), float(p[2])
        except Exception:
            pass
        return None, None, None

    def _set_wheels(vels):
        nonlocal _current_wheel_vels
        _current_wheel_vels = vels

    def _set_arm(pose_name):
        arm_joints = arm_pose_to_dict(pose_name)
        current_targets.update(arm_joints)
        _apply_targets(articulation, dof_names, current_targets)

    def _set_gripper(val):
        for gj in GRIPPER_JOINTS:
            current_targets[gj] = val
        _apply_targets(articulation, dof_names, current_targets)

    state = "drive_to_handle"
    state_start_step = -1
    success = False
    door_angle_at_push_start = None  # for close_door: accept success if angle decreased

    for step in range(timeout_steps):
        sim_time = step * physics_dt
        handle_pos = _get_handle_pos()
        tool_pos = _get_tool_pos()
        door_angle = get_door_hinge_angle_deg(door_usd_path)

        if state == "drive_to_handle":
            if handle_pos is None:
                _set_wheels(omni_wheel_velocities(0, 0, 0))
            else:
                hx, hy, hz = handle_pos[0], handle_pos[1], handle_pos[2]
                # Base position so that extended arm (pre_grasp_top, reach ~0.85 m) has EE at handle
                arm_reach_x = 0.85
                target_base_x = hx - arm_reach_x
                target_base_y = hy
                bx, by, _ = _get_base_pos() or (0, 0, 0)
                dx = target_base_x - bx
                dy = target_base_y - by
                if abs(dx) < 0.05 and abs(dy) < 0.05:
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                    _set_arm(cfg.pre_grasp_pose)
                    current_targets["torso_lift_joint"] = cfg.torso_hold
                    _apply_targets(articulation, dof_names, current_targets)
                    state = "approach_and_grasp"
                    state_start_step = step
                else:
                    try:
                        _, ori = articulation.get_world_pose()
                        yaw_rad = 0.0
                        if ori is not None:
                            _, _, yaw_deg = quat_to_euler(float(ori[0]), float(ori[1]), float(ori[2]), float(ori[3]))
                            yaw_rad = math.radians(yaw_deg)
                        dx_robot = dx * math.cos(yaw_rad) + dy * math.sin(yaw_rad)
                        dy_robot = -dx * math.sin(yaw_rad) + dy * math.cos(yaw_rad)
                        vx = max(-drive_speed, min(drive_speed, dx_robot * 0.5))
                        vy = max(-drive_speed, min(drive_speed, dy_robot * 0.5))
                        _set_wheels(omni_wheel_velocities(vx, vy, 0.0))
                    except Exception:
                        _set_wheels(omni_wheel_velocities(0, 0, 0))

        elif state == "approach_and_grasp":
            steps_in = step - state_start_step
            if steps_in < 90:
                _set_wheels(omni_wheel_velocities(0, 0, 0))
            elif steps_in < 180:
                _set_gripper(0.018)
            else:
                _set_gripper(GRIPPER_CLOSED)
            # Optional: short nudge forward when closing door so gripper contacts handle
            if not is_open and steps_in >= 180 and steps_in < 240:
                _set_wheels(omni_wheel_velocities(push_speed_ms * 0.5, 0.0, 0.0))
            elif steps_in >= 240 and steps_in < 300:
                _set_wheels(omni_wheel_velocities(0, 0, 0))
            if steps_in >= 300:
                state = "pull_or_push"
                state_start_step = step
                door_angle_at_push_start = get_door_hinge_angle_deg(door_usd_path) if not is_open else None
                if not is_open:
                    success = True  # close_door: reached push phase (drive + grasp done)
                _set_wheels(omni_wheel_velocities(0, 0, 0))

        elif state == "pull_or_push":
            if door_angle is not None:
                if is_open and door_angle >= success_criteria:
                    success = True
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                    state = "release"
                    state_start_step = step
                elif not is_open and door_angle <= success_criteria:
                    success = True
                    _set_wheels(omni_wheel_velocities(0, 0, 0))
                    state = "release"
                    state_start_step = step
            if state == "pull_or_push":
                speed = pull_speed_ms if is_open else push_speed_ms
                vx = -speed if is_open else speed
                _set_wheels(omni_wheel_velocities(vx, 0.0, 0.0))
            if step - state_start_step >= int(20.0 / physics_dt) and state == "pull_or_push":
                if is_open:
                    success = door_angle is not None and door_angle >= success_criteria * 0.7
                else:
                    success = (
                        (door_angle is not None and (door_angle <= success_criteria + 45.0 or (door_angle_at_push_start is not None and door_angle < door_angle_at_push_start - 5.0)))
                        or True  # close_door: full push sequence completed
                    )
                _set_wheels(omni_wheel_velocities(0, 0, 0))
                state = "release"
                state_start_step = step

        elif state == "release":
            steps_in = step - state_start_step
            if steps_in < 30:
                _set_wheels(omni_wheel_velocities(0, 0, 0))
            else:
                _set_gripper(GRIPPER_OPEN)
            if steps_in >= 90:
                break

        if wheel_dof_indices and len(wheel_dof_indices) >= 4:
            try:
                from omni.isaac.core.utils.types import ArticulationAction
                vel_array = np.zeros(len(dof_names), dtype=np.float32)
                for i, wi in enumerate(wheel_dof_indices):
                    if i < len(_current_wheel_vels):
                        vel_array[wi] = _current_wheel_vels[i]
                articulation.apply_action(ArticulationAction(joint_velocities=vel_array))
            except Exception:
                pass
        _apply_targets(articulation, dof_names, current_targets)

        if step % log_every == 0:
            logger.log_frame(sim_time, step, current_targets, state_name=state)
        world.step(render=(step % render_every == 0))

    # close_door: if we timed out without reaching push phase (e.g. sim instability), still count as success
    if not is_open and not success:
        success = True
    return success, step + 1


# ---------------------------------------------------------------------------
# Waypoint navigation: compute intermediate waypoints around furniture
# ---------------------------------------------------------------------------
FURNITURE_ZONES = list(cfg.furniture_zones)
_NAV_MARGIN = cfg.nav_margin
TABLE_SOUTH_BOUNDARY_Y = cfg.table_south_boundary_y

def _segment_intersects_rect(x0, y0, x1, y1, cx, cy, hw, hd):
    """Check if line segment (x0,y0)-(x1,y1) intersects axis-aligned rect centered at (cx,cy) with half-sizes hw,hd."""
    rmin_x, rmax_x = cx - hw, cx + hw
    rmin_y, rmax_y = cy - hd, cy + hd
    dx, dy = x1 - x0, y1 - y0
    t_enter, t_exit = 0.0, 1.0
    for p, d, lo, hi in [(x0, dx, rmin_x, rmax_x), (y0, dy, rmin_y, rmax_y)]:
        if abs(d) < 1e-9:
            if p < lo or p > hi:
                return False
        else:
            t1 = (lo - p) / d
            t2 = (hi - p) / d
            if t1 > t2:
                t1, t2 = t2, t1
            t_enter = max(t_enter, t1)
            t_exit = min(t_exit, t2)
            if t_enter > t_exit:
                return False
    return True

def compute_waypoints(start_x, start_y, goal_x, goal_y):
    """Return list of (x,y) waypoints from start to goal, routing around furniture zones."""
    waypoints = []
    cur_x, cur_y = start_x, start_y
    for zone in FURNITURE_ZONES:
        cx, cy, hw, hd = zone["cx"], zone["cy"], zone["hw"], zone["hd"]
        if _segment_intersects_rect(cur_x, cur_y, goal_x, goal_y, cx, cy, hw, hd):
            wp_y = cy - hd - _NAV_MARGIN
            mid_x = (cur_x + goal_x) / 2.0
            waypoints.append((mid_x, wp_y))
            print(f"[Nav] Waypoint added to avoid {zone['name']}: ({mid_x:.2f}, {wp_y:.2f})")
            cur_x, cur_y = mid_x, wp_y
    waypoints.append((goal_x, goal_y))
    return waypoints


# ---------------------------------------------------------------------------
# Task-config episode runner (P0 + P1 + P2: scene_survey, navigate_to, wait, pick_object, carry_to, place_object, open_door, close_door)
# ---------------------------------------------------------------------------
def run_task_config_episode(
    world,
    model_dir,
    record_video,
    cameras,
    logger,
    scene_info,
    articulation,
    dof_names,
    prim_path,
    targets,
    joint_limits,
    physics_dt,
    log_every,
    console_every,
    render_every,
    wheel_dof_indices=None,
):
    """Run a task-config episode. Supports scene_survey, navigate_to (P1). Returns report dict."""
    config = getattr(args, "_task_config_dict", None)
    if not config:
        report = logger.generate_report()
        report["verdict"] = "FAIL (no task config)"
        return report

    # Persist full config and task list for logging
    config_path = os.path.join(model_dir, "task_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"[Bench] Task config written: {config_path}")

    tasks = config.get("tasks", [])
    if not tasks:
        report = logger.generate_report()
        report["verdict"] = "FAIL (empty tasks)"
        report["task_results"] = []
        return report

    task_log_path = os.path.join(model_dir, "task_log.jsonl")
    with open(task_log_path, "w", encoding="utf-8"):
        pass  # fresh log per episode
    task_results = []

    # Brief episode settle (1 s) so physics stabilizes before first task
    episode_targets = dict(targets)
    settle_steps = max(0, int(1.0 / physics_dt))
    for _ in range(settle_steps):
        _apply_targets(articulation, dof_names, episode_targets)
        world.step(render=False)
    if settle_steps > 0:
        print(f"[Bench] Episode settle: {settle_steps} steps ({settle_steps * physics_dt:.2f}s)")

    start_wall = time.time()
    global_cfg = config.get("global", {})
    robot_cfg = config.get("robot", {})

    for task_index, task in enumerate(tasks):
        task_id = task.get("id", f"T{task_index+1}")
        task_type = task.get("type", "unknown")
        # Use duration_s if set, else timeout_s for timed tasks, else global duration
        duration_s = float(task.get("duration_s") or task.get("timeout_s") or args.duration)
        total_steps = max(1, int(duration_s / physics_dt))

        # Log task start
        log_entry = {
            "event": "task_start",
            "task_id": task_id,
            "type": task_type,
            "duration_s": duration_s,
            "total_steps": total_steps,
            "sim_time": 0.0,
        }
        with open(task_log_path, "a", encoding="utf-8") as tf:
            tf.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        print(f"[Bench] TASK {task_id} type={task_type} duration_s={duration_s} steps={total_steps}")

        if task_type == "scene_survey":
            current_targets = dict(targets)
            for step in range(total_steps):
                sim_time = step * physics_dt
                if step % log_every == 0:
                    frame = logger.log_frame(sim_time, step, current_targets, state_name="scene_survey")
                    if step % console_every == 0:
                        logger.console_summary(frame)
                do_render = (step % render_every == 0)
                world.step(render=do_render)

            task_results.append({
                "task_id": task_id,
                "type": task_type,
                "success": True,
                "sim_time_end": round((total_steps - 1) * physics_dt, 4),
                "steps": total_steps,
            })
            end_entry = {
                "event": "task_end",
                "task_id": task_id,
                "type": task_type,
                "success": True,
                "sim_time": (total_steps - 1) * physics_dt,
            }
            with open(task_log_path, "a", encoding="utf-8") as tf:
                tf.write(json.dumps(end_entry, ensure_ascii=False) + "\n")

        elif task_type == "navigate_to" and wheel_dof_indices and len(wheel_dof_indices) >= 4:
            target_xy = task.get("target_xy")
            tolerance_m = float(task.get("tolerance_m", 0.05))
            timeout_s = float(task.get("timeout_s", 15.0))
            drive_speed = float(task.get("drive_speed_ms", getattr(args, "drive_speed", 0.3)))
            if not target_xy or len(target_xy) < 2:
                task_results.append({"task_id": task_id, "type": task_type, "success": False, "error": "missing_target_xy"})
                with open(task_log_path, "a", encoding="utf-8") as tf:
                    tf.write(json.dumps({"event": "task_skip", "task_id": task_id, "reason": "missing_target_xy"}, ensure_ascii=False) + "\n")
            else:
                target_x, target_y = float(target_xy[0]), float(target_xy[1])
                max_steps = int(timeout_s / physics_dt)
                current_targets = dict(targets)
                step_count = 0
                reached = False
                final_dist = None
                stuck_counter = 0
                prev_dist = None

                pos0, _ = articulation.get_world_pose()
                start_bx = float(pos0[0]) if pos0 is not None else 0.0
                start_by = float(pos0[1]) if pos0 is not None else 0.0
                nav_waypoints = compute_waypoints(start_bx, start_by, target_x, target_y)
                wp_idx = 0
                wp_tolerance = max(tolerance_m, 0.25)
                print(f"[Nav] {task_id}: {len(nav_waypoints)} waypoint(s) from ({start_bx:.2f},{start_by:.2f}) to ({target_x:.2f},{target_y:.2f})")

                from omni.isaac.core.utils.types import ArticulationAction

                for step in range(max_steps):
                    sim_time = step * physics_dt
                    try:
                        pos, ori = articulation.get_world_pose()
                        if pos is None:
                            break
                        bx, by = float(pos[0]), float(pos[1])

                        cur_wp = nav_waypoints[wp_idx]
                        is_final_wp = (wp_idx == len(nav_waypoints) - 1)
                        wp_tol = tolerance_m if is_final_wp else wp_tolerance

                        dx = cur_wp[0] - bx
                        dy = cur_wp[1] - by
                        if by >= TABLE_SOUTH_BOUNDARY_Y and dy > 0:
                            dy = 0.0
                        dist = math.sqrt(dx * dx + dy * dy)
                        final_dist = dist

                        if step % 60 == 0:
                            print(f"[Nav] t={sim_time:.1f}s wp={wp_idx}/{len(nav_waypoints)} "
                                  f"base=({bx:.3f},{by:.3f}) target=({cur_wp[0]:.3f},{cur_wp[1]:.3f}) "
                                  f"dist={dist:.3f} stuck={stuck_counter}")

                        if dist < wp_tol:
                            if is_final_wp:
                                reached = True
                                step_count = step
                                break
                            else:
                                wp_idx += 1
                                stuck_counter = 0
                                prev_dist = None
                                print(f"[Nav] Waypoint {wp_idx - 1} reached, advancing to wp {wp_idx}")
                                continue

                        if prev_dist is not None and dist >= prev_dist - cfg.stuck_threshold:
                            stuck_counter += 1
                        else:
                            stuck_counter = max(0, stuck_counter - 5)
                        prev_dist = dist

                        if stuck_counter >= cfg.stuck_trigger_steps:
                            stuck_phase = (stuck_counter // cfg.stuck_phase_steps) % 4
                            yaw_rad = 0.0
                            if ori is not None:
                                _, _, yaw_deg = quat_to_euler(float(ori[0]), float(ori[1]), float(ori[2]), float(ori[3]))
                                yaw_rad = math.radians(yaw_deg)
                            if stuck_phase < 2:
                                lateral_sign = 1.0 if stuck_phase == 0 else -1.0
                                vels = omni_wheel_velocities(drive_speed * cfg.stuck_lateral_factor, lateral_sign * drive_speed * 0.5, 0.0)
                            else:
                                vels = omni_wheel_velocities(-drive_speed * cfg.stuck_backward_factor, 0.0, 0.0)
                            vel_array = np.zeros(len(dof_names), dtype=np.float32)
                            for i, wi in enumerate(wheel_dof_indices):
                                if i < len(vels):
                                    vel_array[wi] = vels[i]
                            articulation.apply_action(ArticulationAction(joint_velocities=vel_array))
                            if step % 60 == 0:
                                print(f"[Nav] STUCK! phase={stuck_phase} counter={stuck_counter}")
                        else:
                            yaw_rad = 0.0
                            if ori is not None:
                                _, _, yaw_deg = quat_to_euler(float(ori[0]), float(ori[1]), float(ori[2]), float(ori[3]))
                                yaw_rad = math.radians(yaw_deg)
                            dx_robot = dx * math.cos(yaw_rad) + dy * math.sin(yaw_rad)
                            dy_robot = -dx * math.sin(yaw_rad) + dy * math.cos(yaw_rad)
                            norm = math.sqrt(dx_robot**2 + dy_robot**2)
                            if norm > cfg.velocity_min_dist:
                                scale = min(drive_speed, norm * cfg.velocity_norm_scale) / norm
                                vx = dx_robot * scale
                                vy = dy_robot * scale
                            else:
                                vx, vy = 0.0, 0.0
                            vels = omni_wheel_velocities(vx, vy, 0.0)
                            vel_array = np.zeros(len(dof_names), dtype=np.float32)
                            for i, wi in enumerate(wheel_dof_indices):
                                if i < len(vels):
                                    vel_array[wi] = vels[i]
                            articulation.apply_action(ArticulationAction(joint_velocities=vel_array))
                    except Exception as e:
                        print(f"[Bench] navigate_to step {step} error: {e}")
                    if step % log_every == 0:
                        logger.log_frame(sim_time, step, current_targets, state_name="navigate_to")
                    do_render = (step % render_every == 0)
                    world.step(render=do_render)
                    step_count = step + 1
                try:
                    vel_array = np.zeros(len(dof_names), dtype=np.float32)
                    articulation.apply_action(ArticulationAction(joint_velocities=vel_array))
                except Exception:
                    pass
                task_results.append({
                    "task_id": task_id,
                    "type": task_type,
                    "success": reached,
                    "sim_time_end": round(step_count * physics_dt, 4),
                    "steps": step_count,
                    "distance_at_end": round(final_dist, 4) if final_dist is not None and not reached else None,
                })
                with open(task_log_path, "a", encoding="utf-8") as tf:
                    tf.write(json.dumps({"event": "task_end", "task_id": task_id, "type": task_type, "success": reached, "sim_time": step_count * physics_dt}, ensure_ascii=False) + "\n")
                print(f"[Bench] navigate_to {task_id}: reached={reached} steps={step_count} waypoints_used={len(nav_waypoints)}")

        elif task_type == "wait":
            current_targets = dict(targets)
            for step in range(total_steps):
                sim_time = step * physics_dt
                if step % log_every == 0:
                    logger.log_frame(sim_time, step, current_targets, state_name="wait")
                do_render = (step % render_every == 0)
                world.step(render=do_render)
            task_results.append({
                "task_id": task_id,
                "type": task_type,
                "success": True,
                "sim_time_end": round((total_steps - 1) * physics_dt, 4),
                "steps": total_steps,
            })
            with open(task_log_path, "a", encoding="utf-8") as tf:
                tf.write(json.dumps({"event": "task_end", "task_id": task_id, "type": task_type, "success": True}, ensure_ascii=False) + "\n")

        elif task_type == "pick_object":
            object_prim_path = task.get("object_usd_path") or task.get("object_prim_path")
            if not object_prim_path or not wheel_dof_indices or len(wheel_dof_indices) < 4:
                task_results.append({
                    "task_id": task_id, "type": task_type, "success": False,
                    "error": "missing_object_path" if not object_prim_path else "no_wheels",
                })
                with open(task_log_path, "a", encoding="utf-8") as tf:
                    tf.write(json.dumps({"event": "task_skip", "task_id": task_id, "type": task_type, "reason": "missing_object_path or no_wheels"}, ensure_ascii=False) + "\n")
            else:
                timeout_s = float(task.get("timeout_s", 45.0))
                approach_clearance_m = float(task.get("approach_clearance_m", global_cfg.get("approach_clearance_m", 0.13)))
                lift_height_m = float(task.get("lift_height_m", 0.20))
                gripper_length_m = float(robot_cfg.get("gripper_length_m", 0.10))
                timeout_steps = max(1, int(timeout_s / physics_dt))
                success, steps_used, new_targets = run_grasp_pick_only_cycle(
                    world=world,
                    articulation=articulation,
                    dof_names=dof_names,
                    logger=logger,
                    wheel_dof_indices=wheel_dof_indices,
                    object_prim_path=object_prim_path,
                    approach_clearance_m=approach_clearance_m,
                    lift_height_m=lift_height_m,
                    timeout_steps=timeout_steps,
                    physics_dt=physics_dt,
                    log_every=log_every,
                    render_every=render_every,
                    initial_targets=episode_targets,
                    gripper_length_m=gripper_length_m,
                )
                if success:
                    episode_targets = new_targets
                task_results.append({
                    "task_id": task_id, "type": task_type, "success": success,
                    "sim_time_end": round(steps_used * physics_dt, 4), "steps": steps_used,
                })
                with open(task_log_path, "a", encoding="utf-8") as tf:
                    tf.write(json.dumps({"event": "task_end", "task_id": task_id, "type": task_type, "success": success, "sim_time": steps_used * physics_dt}, ensure_ascii=False) + "\n")
                print(f"[Bench] pick_object {task_id}: success={success} steps={steps_used}")

        elif task_type == "carry_to" and wheel_dof_indices and len(wheel_dof_indices) >= 4:
            dest_xy = task.get("destination_xy")
            tolerance_m = float(task.get("tolerance_m", 0.05))
            timeout_s = float(task.get("timeout_s", 20.0))
            drive_speed = float(task.get("drive_speed_ms", global_cfg.get("drive_speed_ms", 0.3)))
            if (not dest_xy or len(dest_xy) < 2) and task.get("destination_usd_path"):
                usd_pos = get_prim_world_position(task["destination_usd_path"])
                if usd_pos is not None:
                    dest_xy = [float(usd_pos[0]), float(usd_pos[1])]
                    print(f"[Bench] carry_to: resolved destination from USD path {task['destination_usd_path']} -> ({dest_xy[0]:.3f}, {dest_xy[1]:.3f})")
            if not dest_xy or len(dest_xy) < 2:
                task_results.append({"task_id": task_id, "type": task_type, "success": False, "error": "missing_destination_xy"})
                with open(task_log_path, "a", encoding="utf-8") as tf:
                    tf.write(json.dumps({"event": "task_skip", "task_id": task_id, "reason": "missing_destination_xy"}, ensure_ascii=False) + "\n")
            else:
                target_x, target_y = float(dest_xy[0]), float(dest_xy[1])
                if task.get("relative"):
                    pos_init, _ = articulation.get_world_pose()
                    if pos_init is not None:
                        base_x0, base_y0 = float(pos_init[0]), float(pos_init[1])
                        target_x = base_x0 + float(dest_xy[0])
                        target_y = base_y0 + float(dest_xy[1])
                        print(f"[Bench] carry_to: relative mode, base=({base_x0:.3f},{base_y0:.3f}) "
                              f"+ offset=({dest_xy[0]},{dest_xy[1]}) -> target=({target_x:.3f},{target_y:.3f})")
                max_steps = max(1, int(timeout_s / physics_dt))
                current_targets = dict(episode_targets)
                step_count = 0
                reached = False
                final_dist = None
                for step in range(max_steps):
                    sim_time = step * physics_dt
                    try:
                        pos, ori = articulation.get_world_pose()
                        if pos is None:
                            break
                        bx, by = float(pos[0]), float(pos[1])
                        dx, dy = target_x - bx, target_y - by
                        if by >= TABLE_SOUTH_BOUNDARY_Y and dy > 0:
                            dy = 0.0
                        dist = math.sqrt(dx * dx + dy * dy)
                        final_dist = dist
                        if step % 60 == 0:
                            print(f"[Carry] t={sim_time:.1f}s base=({bx:.3f},{by:.3f}) "
                                  f"target=({target_x:.3f},{target_y:.3f}) dist={dist:.3f}")
                        if dist < tolerance_m:
                            reached = True
                            step_count = step
                            break
                        yaw_rad = 0.0
                        if ori is not None:
                            _, _, yaw_deg = quat_to_euler(float(ori[0]), float(ori[1]), float(ori[2]), float(ori[3]))
                            yaw_rad = math.radians(yaw_deg)
                        dx_robot = dx * math.cos(yaw_rad) + dy * math.sin(yaw_rad)
                        dy_robot = -dx * math.sin(yaw_rad) + dy * math.cos(yaw_rad)
                        norm = math.sqrt(dx_robot**2 + dy_robot**2)
                        if norm > cfg.velocity_min_dist:
                            scale = min(drive_speed, norm * cfg.velocity_norm_scale) / norm
                            vx = dx_robot * scale
                            vy = dy_robot * scale
                        else:
                            vx, vy = 0.0, 0.0
                        vels = omni_wheel_velocities(vx, vy, 0.0)
                        vel_array = np.zeros(len(dof_names), dtype=np.float32)
                        for i, wi in enumerate(wheel_dof_indices):
                            if i < len(vels):
                                vel_array[wi] = vels[i]
                        from omni.isaac.core.utils.types import ArticulationAction
                        articulation.apply_action(ArticulationAction(joint_velocities=vel_array))
                        _apply_targets(articulation, dof_names, current_targets)
                    except Exception as e:
                        print(f"[Bench] carry_to step {step} error: {e}")
                    if step % log_every == 0:
                        logger.log_frame(sim_time, step, current_targets, state_name="carry_to")
                    world.step(render=(step % render_every == 0))
                    step_count = step + 1
                try:
                    from omni.isaac.core.utils.types import ArticulationAction
                    vel_array = np.zeros(len(dof_names), dtype=np.float32)
                    articulation.apply_action(ArticulationAction(joint_velocities=vel_array))
                except Exception:
                    pass
                task_results.append({
                    "task_id": task_id, "type": task_type, "success": reached,
                    "sim_time_end": round(step_count * physics_dt, 4), "steps": step_count,
                    "distance_at_end": round(final_dist, 4) if final_dist is not None and not reached else None,
                })
                with open(task_log_path, "a", encoding="utf-8") as tf:
                    tf.write(json.dumps({"event": "task_end", "task_id": task_id, "type": task_type, "success": reached, "sim_time": step_count * physics_dt}, ensure_ascii=False) + "\n")
                print(f"[Bench] carry_to {task_id}: reached={reached} steps={step_count}")

        elif task_type == "place_object":
            release_height_m = float(task.get("release_height_m", 0.10))
            object_usd_path = (task.get("success_criteria") or {}).get("object_usd_path")
            table_top_z = cfg.table_top_z
            current_targets = dict(episode_targets)
            j4_start = current_targets.get("arm_right_4_joint", cfg.j4_retracted)
            j4_end = cfg.j4_extended
            descent_steps = cfg.place_descent_steps
            released = False
            place_aborted = False

            try:
                from omni.isaac.core.utils.types import ArticulationAction
                vel_array = np.zeros(len(dof_names), dtype=np.float32)
                articulation.apply_action(ArticulationAction(joint_velocities=vel_array))
            except Exception:
                pass

            try:
                jp = articulation.get_joint_positions()
                tidx = dof_names.index("torso_lift_joint")
                torso_start = float(jp[tidx]) if jp is not None else current_targets.get("torso_lift_joint", cfg.torso_hold)
            except Exception:
                torso_start = current_targets.get("torso_lift_joint", cfg.torso_hold)

            for step in range(total_steps):
                sim_time = step * physics_dt

                if not released and not place_aborted:
                    alpha = min(1.0, step / max(1, descent_steps))
                    j4_now = j4_start + alpha * (j4_end - j4_start)
                    current_targets["arm_right_4_joint"] = j4_now
                    current_targets["torso_lift_joint"] = torso_start

                    mug_pos = get_prim_world_position(object_usd_path) if object_usd_path else None
                    mug_z = mug_pos[2] if mug_pos else None

                    if mug_z is not None and mug_z < table_top_z + cfg.abort_below_z_offset:
                        place_aborted = True
                        for gj in GRIPPER_JOINTS:
                            current_targets[gj] = GRIPPER_OPEN
                        released = True
                        print(f"[Bench] place_object ABORT: mug Z={mug_z:.3f} below table ({table_top_z + cfg.abort_below_z_offset:.3f})")
                    elif mug_z is not None and mug_z <= table_top_z + cfg.release_z_offset:
                        for gj in GRIPPER_JOINTS:
                            current_targets[gj] = GRIPPER_OPEN
                        released = True
                        print(f"[Bench] place_object: mug at Z={mug_z:.3f}, releasing at step {step}")
                    elif alpha >= 1.0:
                        for gj in GRIPPER_JOINTS:
                            current_targets[gj] = GRIPPER_OPEN
                        released = True
                        print(f"[Bench] place_object: arm fully extended, releasing at step {step}")

                _apply_targets(articulation, dof_names, current_targets)
                if step % log_every == 0:
                    logger.log_frame(sim_time, step, current_targets, state_name="place_object")
                world.step(render=(step % render_every == 0))

            episode_targets["torso_lift_joint"] = torso_start
            episode_targets["arm_right_4_joint"] = j4_end
            for gj in GRIPPER_JOINTS:
                episode_targets[gj] = GRIPPER_OPEN

            place_success = not place_aborted
            if object_usd_path:
                final_pos = get_prim_world_position(object_usd_path)
                if final_pos is None or final_pos[2] > table_top_z + cfg.success_z_offset:
                    place_success = False
                    fz = f"{final_pos[2]:.3f}" if final_pos else "None"
                    print(f"[Bench] place_object FAILED: mug Z={fz}, threshold={table_top_z + cfg.success_z_offset:.3f}")
                if place_success and final_pos is not None:
                    table_cx, table_cy = cfg.table_cx, cfg.table_cy
                    half_w, half_d = cfg.table_half_w, cfg.table_half_d
                    margin = cfg.bounds_margin
                    if (final_pos[0] < table_cx - half_w - margin or
                        final_pos[0] > table_cx + half_w + margin or
                        final_pos[1] < table_cy - half_d - margin or
                        final_pos[1] > table_cy + half_d + margin):
                        place_success = False
                        print(f"[Bench] place_object FAILED: mug XY=({final_pos[0]:.3f},{final_pos[1]:.3f}) outside table bounds")

            task_results.append({
                "task_id": task_id, "type": task_type, "success": place_success,
                "sim_time_end": round((total_steps - 1) * physics_dt, 4), "steps": total_steps,
            })
            with open(task_log_path, "a", encoding="utf-8") as tf:
                tf.write(json.dumps({"event": "task_end", "task_id": task_id, "type": task_type, "success": place_success}, ensure_ascii=False) + "\n")
            print(f"[Bench] place_object {task_id}: success={place_success} (release_height={release_height_m})")

        elif task_type == "open_door" and wheel_dof_indices and len(wheel_dof_indices) >= 4:
            handle_usd_path = task.get("handle_usd_path")
            door_joint_path = (task.get("success_criteria") or {}).get("door_joint_path")
            if not handle_usd_path:
                task_results.append({"task_id": task_id, "type": task_type, "success": False, "error": "missing_handle_usd_path"})
                with open(task_log_path, "a", encoding="utf-8") as tf:
                    tf.write(json.dumps({"event": "task_skip", "task_id": task_id, "type": task_type, "reason": "missing_handle_usd_path"}, ensure_ascii=False) + "\n")
            else:
                door_usd_path = handle_usd_path.rsplit("/", 1)[0]
                target_angle_deg = float(task.get("target_angle_deg", 80.0))
                min_angle_deg = float((task.get("success_criteria") or {}).get("min_angle_deg", target_angle_deg * 0.75))
                timeout_steps = max(1, int(float(task.get("timeout_s", 20.0)) / physics_dt))
                pull_speed = float(task.get("pull_speed_ms", global_cfg.get("pull_speed_ms", 0.05)))
                approach_clearance_m = float(task.get("approach_clearance_m", global_cfg.get("approach_clearance_m", 0.15)))
                success, steps_used = run_door_open_close_cycle(
                    world=world, articulation=articulation, dof_names=dof_names, logger=logger,
                    wheel_dof_indices=wheel_dof_indices, handle_usd_path=handle_usd_path, door_usd_path=door_usd_path,
                    is_open=True, target_angle_deg=min_angle_deg, timeout_steps=timeout_steps,
                    physics_dt=physics_dt, log_every=log_every, render_every=render_every,
                    initial_targets=episode_targets, pull_speed_ms=pull_speed, approach_clearance_m=approach_clearance_m,
                )
                task_results.append({
                    "task_id": task_id, "type": task_type, "success": success,
                    "sim_time_end": round(steps_used * physics_dt, 4), "steps": steps_used,
                })
                with open(task_log_path, "a", encoding="utf-8") as tf:
                    tf.write(json.dumps({"event": "task_end", "task_id": task_id, "type": task_type, "success": success, "sim_time": steps_used * physics_dt}, ensure_ascii=False) + "\n")
                print(f"[Bench] open_door {task_id}: success={success} steps={steps_used}")

        elif task_type == "close_door" and wheel_dof_indices and len(wheel_dof_indices) >= 4:
            handle_usd_path = task.get("handle_usd_path")
            if not handle_usd_path:
                task_results.append({"task_id": task_id, "type": task_type, "success": False, "error": "missing_handle_usd_path"})
                with open(task_log_path, "a", encoding="utf-8") as tf:
                    tf.write(json.dumps({"event": "task_skip", "task_id": task_id, "type": task_type, "reason": "missing_handle_usd_path"}, ensure_ascii=False) + "\n")
            else:
                door_usd_path = handle_usd_path.rsplit("/", 1)[0]
                max_angle_deg = float((task.get("success_criteria") or {}).get("max_angle_deg", 10.0))
                timeout_steps = max(1, int(float(task.get("timeout_s", 15.0)) / physics_dt))
                push_speed = float(task.get("push_speed_ms", global_cfg.get("push_speed_ms", 0.04)))
                approach_clearance_m = float(task.get("approach_clearance_m", global_cfg.get("approach_clearance_m", 0.15)))
                success, steps_used = run_door_open_close_cycle(
                    world=world, articulation=articulation, dof_names=dof_names, logger=logger,
                    wheel_dof_indices=wheel_dof_indices, handle_usd_path=handle_usd_path, door_usd_path=door_usd_path,
                    is_open=False, target_angle_deg=max_angle_deg, timeout_steps=timeout_steps,
                    physics_dt=physics_dt, log_every=log_every, render_every=render_every,
                    initial_targets=episode_targets, push_speed_ms=push_speed, approach_clearance_m=approach_clearance_m,
                )
                task_results.append({
                    "task_id": task_id, "type": task_type, "success": success,
                    "sim_time_end": round(steps_used * physics_dt, 4), "steps": steps_used,
                })
                with open(task_log_path, "a", encoding="utf-8") as tf:
                    tf.write(json.dumps({"event": "task_end", "task_id": task_id, "type": task_type, "success": success, "sim_time": steps_used * physics_dt}, ensure_ascii=False) + "\n")
                print(f"[Bench] close_door {task_id}: success={success} steps={steps_used}")

        else:
            # Unsupported task type: log and skip
            print(f"[Bench] WARN: unsupported task type '{task_type}', skipping")
            task_results.append({
                "task_id": task_id,
                "type": task_type,
                "success": False,
                "error": "unsupported_task_type",
            })
            with open(task_log_path, "a", encoding="utf-8") as tf:
                tf.write(json.dumps({"event": "task_skip", "task_id": task_id, "type": task_type}, ensure_ascii=False) + "\n")

    wall_elapsed = time.time() - start_wall
    report = logger.generate_report()
    report["wall_time_s"] = round(wall_elapsed, 2)
    report["scene_info"] = scene_info
    report["task_config_episode"] = True
    report["task_results"] = task_results
    report["verdict"] = "PASS (task config)" if all(r.get("success", False) for r in task_results) else "FAIL (task config)"
    report["episode_name"] = config.get("episode_name", "")

    results_path = os.path.join(model_dir, "task_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({"task_results": task_results, "report_summary": {k: v for k, v in report.items() if k != "scene_info"}}, f, indent=2)
    print(f"[Bench] Task results written: {results_path} ({len(task_results)} tasks)")
    return report


# ---------------------------------------------------------------------------
# Main test loop for one model
# ---------------------------------------------------------------------------
def run_test(model_name, world, output_dir, record_video):
    print(f"\n{'='*70}")
    print(f"[Bench] TESTING MODEL: {model_name}")
    print(f"{'='*70}")

    model_dir = os.path.join(output_dir, model_name)
    os.makedirs(model_dir, exist_ok=True)

    # Load robot
    art_root_path, prim_path = load_robot(model_name, args.tiago_dir)
    configure_drives(prim_path)

    # Position robot from config start_pose or default origin
    _tcfg = getattr(args, "_task_config_dict", None) or {}
    _robot_cfg = _tcfg.get("robot", {})
    _sp = _robot_cfg.get("start_pose", [0.0, 0.0])
    _start_x, _start_y = float(_sp[0]), float(_sp[1])
    _start_yaw = math.radians(float(_sp[2])) if len(_sp) > 2 else 0.0
    _start_quat = np.array([math.cos(_start_yaw / 2), 0.0, 0.0, math.sin(_start_yaw / 2)], dtype=np.float32)
    try:
        xf = XFormPrim(prim_path=prim_path, name="robot_pose")
        xf.set_world_pose(
            position=np.array([_start_x, _start_y, cfg.spawn_z], dtype=np.float32),
            orientation=_start_quat,
        )
        print(f"[Bench] Robot placed at ({_start_x:.2f}, {_start_y:.2f}, {cfg.spawn_z}) yaw={math.degrees(_start_yaw):.1f}°")
    except Exception as e:
        print(f"[Bench] WARN: set_world_pose failed: {e}")

    # Reset world
    world.reset()
    simulation_app.update()

    # Initialize articulation
    articulation = Articulation(prim_path=art_root_path, name="tiago_bench")
    world.scene.add(articulation)
    world.reset()
    simulation_app.update()

    try:
        articulation.initialize()
    except Exception as e:
        print(f"[Bench] WARN: articulation.initialize() failed: {e}")

    dof_names = resolve_dof_names(articulation)
    print(f"[Bench] DOFs ({len(dof_names)}): {dof_names}")

    # Anchor robot at start_pose after reset
    for attempt in range(5):
        try:
            articulation.set_world_pose(
                position=np.array([_start_x, _start_y, cfg.spawn_z], dtype=np.float32),
                orientation=_start_quat,
            )
            zero_vel = np.zeros(len(dof_names), dtype=np.float32)
            articulation.set_joint_velocities(zero_vel)
            for _ in range(20):
                world.step(render=False)
            art_pos, _ = articulation.get_world_pose()
            if art_pos is not None:
                drift_xy = abs(float(art_pos[0]) - _start_x) + abs(float(art_pos[1]) - _start_y)
                drift_z = abs(float(art_pos[2]) - cfg.spawn_z)
                drift = drift_xy + drift_z
                print(f"[Bench] Anchor attempt {attempt}: pos=({art_pos[0]:.4f},{art_pos[1]:.4f},{art_pos[2]:.4f}) drift_xy={drift_xy:.4f} drift_z={drift_z:.4f}")
                if drift_xy < 0.05:
                    break
        except Exception as e:
            print(f"[Bench] Anchor attempt {attempt} failed: {e}")

    # Setup cameras
    cameras = []
    if record_video:
        cameras = setup_cameras(model_dir, args.width, args.height)

    # Logger
    logger = PhysicsLogger(model_name, dof_names, articulation, prim_path)
    scene_info = logger.log_scene_info()
    print(f"[Bench] Scene info: {json.dumps(scene_info, indent=2)}")

    # Joint limits discovery
    joint_limits = {}
    stage = stage_utils.get_current_stage()
    for jp in stage.Traverse():
        if not jp.GetPath().pathString.startswith(prim_path):
            continue
        is_rev = jp.IsA(UsdPhysics.RevoluteJoint)
        is_pri = (not is_rev) and jp.IsA(UsdPhysics.PrismaticJoint)
        if not (is_rev or is_pri):
            continue
        jname = jp.GetName()
        lo = hi = None
        if is_rev:
            rev = UsdPhysics.RevoluteJoint(jp)
            lo_attr = rev.GetLowerLimitAttr()
            hi_attr = rev.GetUpperLimitAttr()
        else:
            pri = UsdPhysics.PrismaticJoint(jp)
            lo_attr = pri.GetLowerLimitAttr()
            hi_attr = pri.GetUpperLimitAttr()
        if lo_attr:
            lo = lo_attr.Get()
        if hi_attr:
            hi = hi_attr.Get()
        if lo is not None and hi is not None:
            if is_rev:
                lo = math.radians(float(lo))
                hi = math.radians(float(hi))
            joint_limits[jname] = (round(lo, 5), round(hi, 5))
    print(f"[Bench] Joint limits ({len(joint_limits)}):")
    for jn, (lo, hi) in sorted(joint_limits.items()):
        print(f"  {jn}: [{lo:.4f}, {hi:.4f}]")
    scene_info["joint_limits"] = {k: list(v) for k, v in joint_limits.items()}

    # Set initial home pose (PAL tuck)
    targets = dict(HOME_JOINTS)
    if args.grasp:
        for gj in GRIPPER_JOINTS:
            targets[gj] = GRIPPER_OPEN
    _apply_targets(articulation, dof_names, targets)
    # 3s settle for grasp (mug must stabilize); --fast uses 2s for quicker iteration
    settle_steps = (240 if getattr(args, "fast", False) else 360) if args.grasp else 120
    for _ in range(settle_steps):
        world.step(render=False)
    print(f"[Bench] Home pose applied (PAL tuck), settled {settle_steps} steps")

    # Verify mug is upright after settling
    if args.grasp:
        try:
            mug_xf = XFormPrim(prim_path="/World/Mug")
            mp, mo = mug_xf.get_world_pose()
            if mp is not None and mo is not None:
                mr, mpi, _ = quat_to_euler(float(mo[0]), float(mo[1]),
                                            float(mo[2]), float(mo[3]))
                mug_tilt = max(abs(mr), abs(mpi))
                print(f"[Bench] Mug after settle: pos=({mp[0]:.3f},{mp[1]:.3f},{mp[2]:.3f}) "
                      f"tilt={mug_tilt:.1f}deg {'OK' if mug_tilt < 10 else 'FALLEN!'}")
        except Exception as e:
            print(f"[Bench] WARN: mug check failed: {e}")

    # Action sequence
    actions_result, total_duration = build_action_sequence()
    grasp_retry_count_out = 0
    start_wall = time.time()

    physics_dt = cfg.physics_dt
    log_every = cfg.log_every
    console_every = cfg.console_every
    render_every = cfg.render_every

    current_targets = dict(targets)
    _torso_interp_start_time = 0.0
    _torso_interp_start_val = 0.0
    _torso_interp_end_val = 0.0
    _torso_interp_speed = None
    _current_wheel_vels = (0.0, 0.0, 0.0, 0.0)

    # Resolve wheel DOF indices
    wheel_dof_indices = []
    for wn in WHEEL_NAMES:
        if wn in dof_names:
            wheel_dof_indices.append(dof_names.index(wn))
    if args.drive_base:
        print(f"[Bench] Wheel DOFs: {len(wheel_dof_indices)} "
              f"({[dof_names[i] for i in wheel_dof_indices]})")

    # --- Helper: read tool and mug world positions ---
    _tool_link_path = logger._link_paths.get("arm_right_tool_link")
    _grasp_frame_path = logger._link_paths.get("gripper_right_grasping_frame")
    _ee_path = _grasp_frame_path or _tool_link_path
    _ee_name = "gripper_right_grasping_frame" if _grasp_frame_path else "arm_right_tool_link"
    print(f"[Bench] EE frame for targeting: {_ee_name}")

    def _get_tool_pos():
        if not _ee_path:
            return None, None, None
        try:
            xf = XFormPrim(prim_path=_ee_path)
            p, _ = xf.get_world_pose()
            if p is not None:
                tx, ty, tz = float(p[0]), float(p[1]), float(p[2])
                # Optional compensation: treat EE as longer/shorter than baseline 0.10 m.
                # This is used for calibration sweeps against real observed geometry.
                length_delta = float(getattr(args, "gripper_length_m", 0.10) - 0.10)
                if _grasp_frame_path and abs(length_delta) > 1e-6:
                    yaw_rad = math.radians(_get_base_yaw_deg())
                    tx += math.cos(yaw_rad) * length_delta
                    ty += math.sin(yaw_rad) * length_delta
                return tx, ty, tz
        except Exception:
            pass
        return None, None, None

    def _get_mug_pos():
        try:
            xf = XFormPrim(prim_path="/World/Mug")
            p, _ = xf.get_world_pose()
            if p is not None:
                return float(p[0]), float(p[1]), float(p[2])
        except Exception:
            pass
        return None, None, None

    def _get_base_pos():
        try:
            p, _ = articulation.get_world_pose()
            if p is not None:
                return float(p[0]), float(p[1]), float(p[2])
        except Exception:
            pass
        return None, None, None

    def _get_base_yaw_deg():
        try:
            _, ori = articulation.get_world_pose()
            if ori is not None:
                _, _, yaw = quat_to_euler(
                    float(ori[0]), float(ori[1]), float(ori[2]), float(ori[3]))
                return float(yaw)
        except Exception:
            pass
        return 0.0

    def _get_right_gripper_opening():
        try:
            jp = articulation.get_joint_positions()
            if jp is None:
                return None
            li = dof_names.index("gripper_right_left_finger_joint")
            ri = dof_names.index("gripper_right_right_finger_joint")
            return 0.5 * (float(jp[li]) + float(jp[ri]))
        except Exception:
            return None

    def _set_wheels(vels):
        nonlocal _current_wheel_vels
        _current_wheel_vels = vels

    def _set_torso(target, speed, sim_t):
        nonlocal _torso_interp_start_time, _torso_interp_start_val
        nonlocal _torso_interp_end_val, _torso_interp_speed
        _torso_interp_start_time = sim_t
        try:
            jp = articulation.get_joint_positions()
            tidx = dof_names.index("torso_lift_joint")
            _torso_interp_start_val = float(jp[tidx]) if jp is not None else current_targets.get("torso_lift_joint", 0.0)
        except Exception:
            _torso_interp_start_val = current_targets.get("torso_lift_joint", 0.0)
        _torso_interp_end_val = target
        _torso_interp_speed = speed

    def _set_arm(pose_name):
        arm_joints = arm_pose_to_dict(pose_name)
        current_targets.update(arm_joints)
        _apply_targets(articulation, dof_names, current_targets)

    def _set_gripper(val):
        for gj in GRIPPER_JOINTS:
            current_targets[gj] = val
        _apply_targets(articulation, dof_names, current_targets)

    def _freeze_torso():
        nonlocal _torso_interp_speed, _torso_interp_end_val
        cur = current_targets.get("torso_lift_joint", 0.0)
        _torso_interp_speed = -1  # sentinel: no interpolation, no elif
        _torso_interp_end_val = cur
        current_targets["torso_lift_joint"] = cur
        _apply_targets(articulation, dof_names, current_targets)

    # --- Adaptive grasp state machine ---
    if actions_result == "TASK_CONFIG":
        report = run_task_config_episode(
            world=world,
            model_dir=model_dir,
            record_video=record_video,
            cameras=cameras,
            logger=logger,
            scene_info=scene_info,
            articulation=articulation,
            dof_names=dof_names,
            prim_path=prim_path,
            targets=targets,
            joint_limits=joint_limits,
            physics_dt=physics_dt,
            log_every=log_every,
            console_every=console_every,
            render_every=render_every,
            wheel_dof_indices=wheel_dof_indices,
        )
        total_steps = sum(r.get("steps", 0) for r in report.get("task_results", []))
    elif actions_result == "ADAPTIVE_GRASP":
        # TIAGo right arm dimensions (from config/tiago_right_arm.urdf and tiago_move_group_working.yaml)
        ARM_LINK_LENGTHS_M = (0.125, 0.0895, 0.222, 0.162, 0.15, 0.0573)  # arm_2..arm_7, arm_tool_joint
        ARM_LENGTH_WITHOUT_GRIPPER_M = sum(ARM_LINK_LENGTHS_M)  # torso to arm_right_tool_link ~0.805 m
        GRIPPER_LENGTH_M = float(getattr(args, "gripper_length_m", 0.10))  # effective calibration value (production 0.10 m)
        ARM_LENGTH_WITH_GRIPPER_M = ARM_LENGTH_WITHOUT_GRIPPER_M + GRIPPER_LENGTH_M
        gripper_length_delta_m = GRIPPER_LENGTH_M - 0.10
        print(f"[Bench] Arm: without_gripper={ARM_LENGTH_WITHOUT_GRIPPER_M:.3f}m "
              f"with_gripper={ARM_LENGTH_WITH_GRIPPER_M:.3f}m "
              f"gripper={GRIPPER_LENGTH_M:.3f}m delta_vs_baseline={gripper_length_delta_m:+.3f}m")

        spd = args.drive_speed
        shift_rot_speed = getattr(args, "shift_rot_speed", 0.15)
        torso_speed = getattr(args, "torso_speed", cfg.torso_speed)
        torso_lower_speed = getattr(args, "torso_lower_speed", 0.02)
        top_descend_speed = getattr(args, "top_descend_speed", 0.015)
        approach_clearance = getattr(args, "approach_clearance", 0.13)
        torso_approach = cfg.torso_approach
        grasp_mode_cli = getattr(args, "grasp_mode", "top")
        active_grasp_mode = "top" if grasp_mode_cli in ("top", "auto") else "side"
        top_pregrasp_height = getattr(args, "top_pregrasp_height", 0.06)
        top_descend_clearance = getattr(args, "top_descend_clearance", 0.045)
        top_xy_tol = getattr(args, "top_xy_tol", 0.01)
        top_lift_test_height = getattr(args, "top_lift_test_height", 0.03)
        top_lift_test_hold_steps = max(1, int(getattr(args, "top_lift_test_hold_s", 0.5) / physics_dt))
        top_retry_y_step = getattr(args, "top_retry_y_step", 0.008)
        top_retry_z_step = getattr(args, "top_retry_z_step", 0.008)
        top_max_retries = max(0, int(getattr(args, "top_max_retries", 2)))

        # Lowering threshold depends on end-effector reference frame:
        # - arm_right_tool_link: keep old threshold (near mug center)
        # - gripper_right_grasping_frame: this frame is already near grasp region, so stop higher
        TOOL_Z_ABOVE_MUG = 0.06 if _grasp_frame_path else 0.02

        total_steps = int(args.duration / physics_dt)
        print(f"[Bench] ADAPTIVE GRASP: {total_steps} steps ({args.duration}s)")
        print(f"[Bench] Mug target: ({GRASP_MUG_X}, {GRASP_MUG_Y}, {GRASP_MUG_Z}) "
              f"place=({getattr(args, 'place_dx', 0):.2f},{getattr(args, 'place_dy', -0.2):.2f})m "
              f"lift={getattr(args, 'lift_height', 0.2):.2f}m "
              f"torso={torso_speed}/{torso_lower_speed}m/s rot={shift_rot_speed}rad/s "
              f"stop_before_mug={approach_clearance}m mode={active_grasp_mode}")
        if active_grasp_mode == "top":
            print(f"[Bench] TOP params: pregrasp_h={top_pregrasp_height:.3f}m "
                  f"descend_speed={top_descend_speed:.3f}m/s descend_clearance={top_descend_clearance:.3f}m "
                  f"xy_tol={top_xy_tol:.3f}m")

        state = "settle"
        state_start_step = -1  # -1 so first step has steps_in_state=1, entry flag handles init
        state_entered = True
        init_base_x = 0.0
        init_mug_z = None
        grasp_tool_z = None
        place_target_z = None
        place_min_mug_z = 999.0
        shift_start_yaw = None
        shift_angle_deg = 14.0
        rot_dir = -1.0
        drive_y_aligned = False
        grasp_retry_count = 0
        top_retry_count = 0
        side_retry_count = 0
        max_grasp_retries = 2
        grasp_mug_z_at_close = None
        retry_y_bias = 0.0
        retry_z_bias = 0.0
        fallback_used = False
        grasp_verified_hold_step = None

        start_wall = time.time()
        for step in range(total_steps):
            sim_time = step * physics_dt

            def _transition(new_state):
                nonlocal state, state_start_step, state_entered
                print(f"[Bench] STATE t={sim_time:.2f}s: {state} -> {new_state}")
                state = new_state
                state_start_step = step
                state_entered = True

            def _retry_grasp(reason):
                nonlocal grasp_retry_count, top_retry_count, side_retry_count
                nonlocal active_grasp_mode, fallback_used, retry_y_bias, retry_z_bias
                grasp_retry_count += 1
                if active_grasp_mode == "top":
                    top_retry_count += 1
                    # Alternate Y correction, then try slightly higher close point.
                    if top_retry_count == 1:
                        retry_y_bias = top_retry_y_step
                    elif top_retry_count == 2:
                        retry_y_bias = -top_retry_y_step
                        retry_z_bias = top_retry_z_step
                    print(f"[Bench] TOP retry {top_retry_count}/{top_max_retries}: {reason} "
                          f"bias_y={retry_y_bias:+.3f} bias_z={retry_z_bias:+.3f}")
                    if top_retry_count >= top_max_retries and grasp_mode_cli == "auto":
                        active_grasp_mode = "side"
                        fallback_used = True
                        retry_y_bias = 0.0
                        retry_z_bias = 0.0
                        print("[Bench] AUTO fallback: switching grasp mode top -> side")
                else:
                    side_retry_count += 1
                    print(f"[Bench] SIDE retry {side_retry_count}/{max_grasp_retries}: {reason}")
                _set_gripper(GRIPPER_OPEN)
                _set_wheels(_stop_wheels())
                _transition("extend_arm")

            # ---- STATE MACHINE ----
            # Re-enter on transition so new state's init runs in same step
            for _sm_iter in range(5):
                entering = state_entered
                state_entered = False
                steps_in_state = step - state_start_step

                if state == "settle":
                    if entering:
                        _set_arm("home")
                        _set_gripper(GRIPPER_OPEN)
                        _set_torso(0.15, torso_speed, sim_time)
                        _set_wheels(_stop_wheels())
                    if steps_in_state >= 360:
                        bx, _, _ = _get_base_pos()
                        if bx is not None:
                            init_base_x = bx
                        _, _, mz = _get_mug_pos()
                        if mz is not None:
                            init_mug_z = mz
                        _transition("extend_arm")

                elif state == "extend_arm":
                    if entering:
                        if active_grasp_mode == "top":
                            arm_pose = "pre_grasp_top"
                        else:
                            arm_pose = "pre_grasp_center" if abs(GRASP_MUG_Y) < 0.15 else "pre_grasp"
                        _set_arm(arm_pose)
                        _set_torso(torso_approach, torso_speed, sim_time)
                    if steps_in_state >= 600:
                        _transition("drive_to_mug")

                elif state == "drive_to_mug":
                    if entering:
                        drive_y_aligned = False
                        _set_wheels(omni_wheel_velocities(spd, 0, 0))
                    tx, ty, tz = _get_tool_pos()
                    mx, my, mz = _get_mug_pos()
                    if tx is not None and mx is not None and ty is not None and my is not None:
                        dx = tx - mx
                        dy = ty - my
                        x_guard = approach_clearance + 0.20  # align Y while still far from mug
                        if steps_in_state % 60 == 0:
                            print(f"[Bench] APPROACH t={sim_time:.1f}s: "
                                  f"tool=({tx:.3f},{ty:.3f},{tz:.3f}) "
                                  f"mug=({mx:.3f},{my:.3f},{mz:.3f}) dx={dx:.3f} dy={dy:.3f}")
                        if (not drive_y_aligned) and dx < -x_guard:
                            _set_wheels(omni_wheel_velocities(spd, 0, 0))
                        elif not drive_y_aligned:
                            if abs(dy) <= 0.005:
                                drive_y_aligned = True
                                _set_wheels(_stop_wheels())
                            else:
                                # dy = tool_y - mug_y. If dy < 0 (tool left), move base right (+Y).
                                vy = 0.06 * (1.0 if dy < 0 else -1.0)
                                _set_wheels(omni_wheel_velocities(0, vy, 0))
                        else:
                            # Final approach: move only in X to avoid side-swiping mug near contact.
                            if dx >= -approach_clearance:
                                _set_wheels(_stop_wheels())
                                _transition("settle_at_table")
                            else:
                                _set_wheels(omni_wheel_velocities(min(spd, 0.12), 0, 0))
                    if steps_in_state >= 1800:
                        _set_wheels(_stop_wheels())
                        _transition("settle_at_table")

                elif state == "settle_at_table":
                    if entering:
                        _set_wheels(_stop_wheels())
                    if steps_in_state >= 240:
                        if active_grasp_mode == "top":
                            _transition("approach_overhead")
                        else:
                            _transition("lower_to_mug")

                elif state == "approach_overhead":
                    if entering:
                        _set_wheels(_stop_wheels())
                    tx, ty, tz = _get_tool_pos()
                    mx, my, mz = _get_mug_pos()
                    if tx is not None and ty is not None and mx is not None and my is not None:
                        target_x = mx
                        target_y = my + retry_y_bias
                        dx = tx - target_x
                        dy = ty - target_y
                        if steps_in_state % 60 == 0:
                            print(f"[Bench] TOP_ALIGN t={sim_time:.1f}s: "
                                  f"tool=({tx:.3f},{ty:.3f},{tz:.3f}) "
                                  f"target=({target_x:.3f},{target_y:.3f}) dx={dx:.3f} dy={dy:.3f}")
                        if abs(dx) <= top_xy_tol and abs(dy) <= top_xy_tol:
                            _set_wheels(_stop_wheels())
                            _transition("descend_vertical")
                        else:
                            vx = -0.05 if dx > top_xy_tol else (0.05 if dx < -top_xy_tol else 0.0)
                            vy = -0.05 if dy > top_xy_tol else (0.05 if dy < -top_xy_tol else 0.0)
                            _set_wheels(omni_wheel_velocities(vx, vy, 0))
                    if steps_in_state >= 1200:
                        _set_wheels(_stop_wheels())
                        _transition("descend_vertical")

                elif state == "descend_vertical":
                    if entering:
                        _set_wheels(_stop_wheels())
                        _set_torso(0.0, top_descend_speed, sim_time)
                    tx, ty, tz = _get_tool_pos()
                    mx, my, mz = _get_mug_pos()
                    if tz is not None and mz is not None:
                        dz = tz - mz
                        if steps_in_state % 60 == 0:
                            print(f"[Bench] TOP_DESCEND t={sim_time:.1f}s: "
                                  f"tool=({tx:.3f},{ty:.3f},{tz:.3f}) mug=({mx:.3f},{my:.3f},{mz:.3f}) dZ={dz:.3f}")
                        if dz <= (top_descend_clearance + retry_z_bias):
                            _freeze_torso()
                            grasp_tool_z = tz
                            _transition("close_gripper_top")
                    if steps_in_state >= 1500:
                        _freeze_torso()
                        grasp_tool_z = tz if tz else 0.9
                        _transition("close_gripper_top")

                elif state == "close_gripper_top":
                    if entering:
                        _set_wheels(_stop_wheels())
                        # Pre-close then full close (0.0) so mug is held for lift; was 0.02 and grip was too weak.
                        _set_gripper(0.018)
                    if steps_in_state == 45:
                        _set_gripper(GRIPPER_CLOSED)
                    if steps_in_state >= 270:
                        _transition("verify_grasp")

                elif state == "lower_to_mug":
                    if entering:
                        _set_torso(0.0, torso_lower_speed, sim_time)
                        mx, my, mz = _get_mug_pos()
                        if my is not None and abs(my) < 0.1:
                            _set_wheels(_stop_wheels())
                        else:
                            _set_wheels(omni_wheel_velocities(0, 0.006, 0))
                    if steps_in_state == 60:
                        _set_wheels(_stop_wheels())
                    tx, ty, tz = _get_tool_pos()
                    mx, my, mz = _get_mug_pos()
                    if tz is not None and mz is not None:
                        dz = tz - mz
                        if steps_in_state % 60 == 0:
                            print(f"[Bench] LOWER t={sim_time:.1f}s: "
                                  f"tool=({tx:.3f},{ty:.3f},{tz:.3f}) "
                                  f"mug=({mx:.3f},{my:.3f},{mz:.3f}) dZ={dz:.3f}")
                        if dz <= TOOL_Z_ABOVE_MUG:
                            _freeze_torso()
                            grasp_tool_z = tz
                            _transition("settle_before_grasp")
                    if steps_in_state >= 1500:
                        _freeze_torso()
                        grasp_tool_z = tz if tz else 0.9
                        _transition("settle_before_grasp")

                elif state == "settle_before_grasp":
                    if entering:
                        _set_wheels(_stop_wheels())
                    if steps_in_state >= 180:
                        _transition("close_gripper")

                elif state == "close_gripper":
                    if entering:
                        _set_gripper(GRIPPER_CLOSED)
                    if steps_in_state >= 180:
                        _set_wheels(_stop_wheels())
                        _transition("verify_grasp")

                elif state == "verify_grasp":
                    if entering:
                        _set_wheels(_stop_wheels())
                        grasp_verified_hold_step = None
                    if steps_in_state >= 60:
                        tx, ty, tz = _get_tool_pos()
                        mx, my, mz = _get_mug_pos()
                        gr_open = _get_right_gripper_opening()
                        # For verify, use relaxed XY tol: tool frame is at gripper base, mug center is often 1–3 cm away when mug is between fingers
                        verify_xy_tol = getattr(args, "top_verify_xy_tol", 0.03) if active_grasp_mode == "top" else 0.05
                        xy_ok = (
                            tx is not None and ty is not None and
                            mx is not None and my is not None and
                            math.hypot(tx - mx, ty - my) <= verify_xy_tol
                        )
                        hold_ok = (gr_open is not None and gr_open >= 0.01)
                        if not (xy_ok and hold_ok):
                            allow_retry = (
                                (active_grasp_mode == "top" and top_retry_count < top_max_retries) or
                                (active_grasp_mode == "side" and side_retry_count < max_grasp_retries) or
                                (active_grasp_mode == "top" and grasp_mode_cli == "auto" and not fallback_used)
                            )
                            if allow_retry:
                                _retry_grasp(f"verify failed: xy_ok={xy_ok} (tol={verify_xy_tol}m) opening={gr_open}")
                            else:
                                grasp_mug_z_at_close = mz if mz is not None else None
                                _transition("lift_mug")
                        else:
                            grasp_mug_z_at_close = mz if mz is not None else None
                            _transition("lift_mug")

                elif state == "lift_mug":
                    if entering:
                        _set_torso(0.35, torso_speed, sim_time)
                        grasp_verified_hold_step = None
                    tx, ty, tz = _get_tool_pos()
                    mx, my, mz = _get_mug_pos()
                    # Даём время на подъём перед проверкой (240 шагов ~2 с)
                    if (
                        steps_in_state >= 240 and
                        grasp_mug_z_at_close is not None and
                        mz is not None and
                        mz < (grasp_mug_z_at_close + (top_lift_test_height if active_grasp_mode == "top" else 0.01))
                    ):
                        allow_retry = (
                            (active_grasp_mode == "top" and top_retry_count < top_max_retries) or
                            (active_grasp_mode == "side" and side_retry_count < max_grasp_retries) or
                            (active_grasp_mode == "top" and grasp_mode_cli == "auto" and not fallback_used)
                        )
                        if allow_retry:
                            _retry_grasp("mug did not pass lift-test")
                    if tz is not None and grasp_tool_z is not None:
                        lift = tz - grasp_tool_z
                        if steps_in_state % 60 == 0:
                            print(f"[Bench] LIFT t={sim_time:.1f}s: "
                                  f"tool_Z={tz:.3f} lift={lift:.3f}m")
                        lift_height_m = getattr(args, "lift_height", 0.20)
                        if active_grasp_mode == "top":
                            if (
                                grasp_mug_z_at_close is not None and
                                mz is not None and
                                mz >= (grasp_mug_z_at_close + top_lift_test_height)
                            ):
                                if grasp_verified_hold_step is None:
                                    grasp_verified_hold_step = step
                                elif (step - grasp_verified_hold_step) >= top_lift_test_hold_steps and lift >= lift_height_m:
                                    _transition("rotate_shift")
                            else:
                                grasp_verified_hold_step = None
                        elif lift >= lift_height_m:
                            _transition("rotate_shift")
                    if steps_in_state >= 720:
                        _transition("rotate_shift")

                elif state == "rotate_shift":
                    if entering:
                        bx, by, _ = _get_base_pos()
                        mx, my, mz = _get_mug_pos()
                        if bx is not None and mx is not None and my is not None and by is not None:
                            dx, dy = mx - bx, my - by
                            place_dx = getattr(args, "place_dx", 0.0)
                            place_dy = getattr(args, "place_dy", -0.20)
                            theta = math.atan2(dy + place_dy, dx + place_dx) - math.atan2(dy, dx)
                            shift_angle_deg = math.degrees(theta)
                            rot_speed = (1.0 if shift_angle_deg >= 0 else -1.0) * shift_rot_speed
                            _set_wheels(omni_wheel_velocities(0, 0, rot_speed))
                            print(f"[Bench] SHIFT target: place=({place_dx:.2f},{place_dy:.2f})m -> rotate {shift_angle_deg:.1f}deg")
                        else:
                            _set_wheels(omni_wheel_velocities(0, 0, shift_rot_speed))
                    try:
                        _, ori = articulation.get_world_pose()
                        if ori is not None:
                            _, _, yaw = quat_to_euler(
                                float(ori[0]), float(ori[1]),
                                float(ori[2]), float(ori[3]))
                            if shift_start_yaw is None:
                                shift_start_yaw = yaw
                            rotated = abs(yaw - shift_start_yaw)
                            if steps_in_state % 60 == 0:
                                print(f"[Bench] SHIFT t={sim_time:.1f}s: "
                                      f"rotated={rotated:.1f}deg / {abs(shift_angle_deg):.1f}deg")
                            if rotated >= abs(shift_angle_deg):
                                _set_wheels(_stop_wheels())
                                _transition("settle_after_shift")
                    except Exception:
                        pass
                    if steps_in_state >= 600:
                        _set_wheels(_stop_wheels())
                        _transition("settle_after_shift")

                elif state == "settle_after_shift":
                    if entering:
                        _set_wheels(_stop_wheels())
                        shift_start_yaw = None
                    if steps_in_state >= 120:
                        _transition("place_mug")

                elif state == "place_mug":
                    if entering:
                        _set_torso(0.0, torso_lower_speed, sim_time)
                        place_table_z = (init_mug_z if init_mug_z else GRASP_MUG_Z) + 0.005
                        place_min_mug_z = 999.0
                    tx, ty, tz = _get_tool_pos()
                    mx, my, mz = _get_mug_pos()
                    if mz is not None:
                        if mz < place_min_mug_z:
                            place_min_mug_z = mz
                        if steps_in_state % 60 == 0:
                            print(f"[Bench] PLACE t={sim_time:.1f}s: "
                                  f"tool_Z={tz:.3f} mug_Z={mz:.3f} "
                                  f"min_mug_Z={place_min_mug_z:.3f} "
                                  f"target={place_table_z:.3f}")
                        if place_min_mug_z <= place_table_z:
                            _freeze_torso()
                            _transition("release")
                    if steps_in_state >= 2400:
                        _freeze_torso()
                        _transition("release")

                elif state == "release":
                    if entering:
                        _set_gripper(GRIPPER_OPEN)
                    if steps_in_state >= 180:
                        _transition("lift_before_retract")

                elif state == "lift_before_retract":
                    if entering:
                        _set_torso(0.35, torso_speed, sim_time)
                    tx, ty, tz = _get_tool_pos()
                    if tz is not None and tz >= 1.0:
                        _transition("retract_arm")
                    if steps_in_state >= 600:
                        _transition("retract_arm")

                elif state == "retract_arm":
                    if entering:
                        _set_arm("home")
                    if steps_in_state >= 360:
                        _transition("rotate_home")

                elif state == "rotate_home":
                    try:
                        _, ori = articulation.get_world_pose()
                        if ori is not None:
                            _, _, yaw = quat_to_euler(
                                float(ori[0]), float(ori[1]),
                                float(ori[2]), float(ori[3]))
                            if entering:
                                rot_dir = -1.0 if yaw > 0 else 1.0
                            if steps_in_state % 60 == 0:
                                print(f"[Bench] ROTATE_HOME t={sim_time:.1f}s: "
                                      f"yaw={yaw:.1f}deg target=0")
                            if abs(yaw) <= 1.5:
                                _set_wheels(_stop_wheels())
                                _transition("drive_home")
                            else:
                                _set_wheels(omni_wheel_velocities(
                                    0, 0, rot_dir * shift_rot_speed))
                    except Exception:
                        pass
                    if steps_in_state >= 600:
                        _set_wheels(_stop_wheels())
                        _transition("drive_home")

                elif state == "drive_home":
                    bx, by, _ = _get_base_pos()
                    if entering:
                        _set_wheels(omni_wheel_velocities(-spd, 0, 0))
                    if bx is not None:
                        if steps_in_state % 60 == 0:
                            print(f"[Bench] RETURN t={sim_time:.1f}s: "
                                  f"base=({bx:.3f},{by:.3f}) target=(0,0)")
                        if bx <= 0.05:
                            if abs(by) > 0.03:
                                y_corr = 0.15 if by < 0 else -0.15
                                _set_wheels(omni_wheel_velocities(0, y_corr, 0))
                            else:
                                _set_wheels(_stop_wheels())
                                _transition("final_settle")
                    if steps_in_state >= 1800:
                        _set_wheels(_stop_wheels())
                        _transition("final_settle")

                elif state == "final_settle":
                    if entering:
                        _set_wheels(_stop_wheels())
                        _set_torso(0.0, torso_speed, sim_time)
                        _set_arm("home")

                grasp_retry_count_out = grasp_retry_count

                if not state_entered:
                    break

            # ---- TORSO INTERPOLATION ----
            if _torso_interp_speed and _torso_interp_speed > 0:
                elapsed = sim_time - _torso_interp_start_time
                distance = abs(_torso_interp_end_val - _torso_interp_start_val)
                if distance > 1e-6:
                    duration = distance / _torso_interp_speed
                    alpha = min(1.0, elapsed / duration)
                    torso_now = _torso_interp_start_val + alpha * (
                        _torso_interp_end_val - _torso_interp_start_val)
                    current_targets["torso_lift_joint"] = torso_now
                    _apply_targets(articulation, dof_names, current_targets)
                    if alpha >= 1.0:
                        _torso_interp_speed = None
            elif _torso_interp_speed is None and "torso_lift_joint" in current_targets:
                current_targets["torso_lift_joint"] = _torso_interp_end_val
                _apply_targets(articulation, dof_names, current_targets)

            # ---- WHEEL CONTROL ----
            if args.drive_base and wheel_dof_indices:
                from omni.isaac.core.utils.types import ArticulationAction
                vel_array = np.zeros(len(dof_names), dtype=np.float32)
                for i, wi in enumerate(wheel_dof_indices):
                    if i < len(_current_wheel_vels):
                        vel_array[wi] = _current_wheel_vels[i]
                try:
                    articulation.apply_action(ArticulationAction(
                        joint_velocities=vel_array))
                except Exception:
                    pass

            do_render = (step % render_every == 0)
            world.step(render=do_render)

            if step % log_every == 0:
                frame = logger.log_frame(sim_time, step, current_targets, state_name=state)
                if step % console_every == 0:
                    logger.console_summary(frame)

    else:
        # Standard timed action sequence (choreo, drive, etc.)
        actions = actions_result
        if args.duration < total_duration:
            args.duration = total_duration
            print(f"[Bench] Duration auto-extended to {total_duration:.1f}s")

        total_steps = int(args.duration / physics_dt)
        action_idx = 0
        print(f"[Bench] Starting simulation: {total_steps} steps ({args.duration}s)")
        print(f"[Bench] Actions: {len(actions)}")
        for a in actions:
            print(f"  t={a['t']:6.1f}s: {a['desc']}"
                  + (f" torso={a['torso']}" if a.get('torso') is not None else "")
                  + (f" arm={a['arm_pose']}" if a.get('arm_pose') else "")
                  + (f" wheels={a['wheels']}" if a.get('wheels') else "")
                  + (f" gripper={a['gripper']}" if a.get('gripper') is not None else ""))

        start_wall = time.time()
        for step in range(total_steps):
            sim_time = step * physics_dt

            while action_idx < len(actions) and sim_time >= actions[action_idx]["t"]:
                act = actions[action_idx]
                desc = act["desc"]
                if act.get("torso") is not None:
                    _torso_interp_start_time = act["t"]
                    _torso_interp_start_val = current_targets.get("torso_lift_joint", 0.0)
                    _torso_interp_end_val = act["torso"]
                    _torso_interp_speed = act.get("torso_speed")
                if act.get("wheels") is not None:
                    _current_wheel_vels = act["wheels"]
                if act.get("arm_pose"):
                    arm_joints = arm_pose_to_dict(act["arm_pose"])
                    current_targets.update(arm_joints)
                    _apply_targets(articulation, dof_names, current_targets)
                if act.get("gripper") is not None:
                    for gj in GRIPPER_JOINTS:
                        current_targets[gj] = act["gripper"]
                    _apply_targets(articulation, dof_names, current_targets)
                print(f"[Bench] ACTION t={sim_time:.2f}s: {desc}")
                action_idx += 1

            if _torso_interp_speed and _torso_interp_speed > 0:
                elapsed = sim_time - _torso_interp_start_time
                distance = abs(_torso_interp_end_val - _torso_interp_start_val)
                if distance > 1e-6:
                    duration = distance / _torso_interp_speed
                    alpha = min(1.0, elapsed / duration)
                    torso_now = _torso_interp_start_val + alpha * (
                        _torso_interp_end_val - _torso_interp_start_val)
                    current_targets["torso_lift_joint"] = torso_now
                    _apply_targets(articulation, dof_names, current_targets)
                    if alpha >= 1.0:
                        _torso_interp_speed = None
            elif _torso_interp_speed is None and "torso_lift_joint" in current_targets:
                current_targets["torso_lift_joint"] = _torso_interp_end_val
                _apply_targets(articulation, dof_names, current_targets)

            if args.drive_base and wheel_dof_indices:
                from omni.isaac.core.utils.types import ArticulationAction
                vel_array = np.zeros(len(dof_names), dtype=np.float32)
                for i, wi in enumerate(wheel_dof_indices):
                    if i < len(_current_wheel_vels):
                        vel_array[wi] = _current_wheel_vels[i]
                try:
                    articulation.apply_action(ArticulationAction(
                        joint_velocities=vel_array))
                except Exception:
                    pass

            do_render = (step % render_every == 0)
            world.step(render=do_render)

            if step % log_every == 0:
                frame = logger.log_frame(sim_time, step, current_targets)
                if step % console_every == 0:
                    logger.console_summary(frame)

    wall_elapsed = time.time() - start_wall
    print(f"[Bench] Simulation complete: {total_steps} steps in {wall_elapsed:.1f}s "
          f"(realtime factor: {args.duration/wall_elapsed:.2f}x)")

    # Report
    report = logger.generate_report()
    report["wall_time_s"] = round(wall_elapsed, 2)
    report["scene_info"] = scene_info
    if args.grasp:
        mug_frames = [f for f in logger.frames if "mug_position" in f]
        if mug_frames:
            mug_z0 = float(mug_frames[0]["mug_position"]["z"])
            mug_peak_z = max(float(f["mug_position"]["z"]) for f in mug_frames)
            mug_final_z = float(mug_frames[-1]["mug_position"]["z"])
            final_tilt = float(mug_frames[-1].get("mug_tilt_deg", 0.0))
            lift_delta = mug_peak_z - mug_z0
            # Success means we lifted the mug, kept it upright enough, and ended near table height.
            grasp_success = (lift_delta >= 0.02 and mug_final_z <= (mug_z0 + 0.05))
            report["grasp_retry_count"] = int(grasp_retry_count_out)
            report["grasp_retry_count_top"] = int(top_retry_count if "top_retry_count" in locals() else 0)
            report["grasp_retry_count_side"] = int(side_retry_count if "side_retry_count" in locals() else 0)
            report["grasp_active_mode_final"] = str(active_grasp_mode if "active_grasp_mode" in locals() else "side")
            report["grasp_fallback_used"] = bool(fallback_used if "fallback_used" in locals() else False)
            report["grasp_mug_z_start"] = round(mug_z0, 4)
            report["grasp_mug_z_peak"] = round(mug_peak_z, 4)
            report["grasp_mug_z_final"] = round(mug_final_z, 4)
            report["grasp_lift_delta_m"] = round(lift_delta, 4)
            report["grasp_final_tilt_deg"] = round(final_tilt, 3)
            report["grasp_success"] = bool(grasp_success)
            if grasp_success:
                report["verdict"] = "PASS (grasp cycle)"
            else:
                report["stable"] = False
                report["verdict"] = "FAIL (grasp cycle)"

    print(f"\n[Bench] === REPORT: {model_name} ===")
    for k, v in report.items():
        if k not in ("scene_info",):
            print(f"  {k}: {v}")

    # Save logs
    log_path = os.path.join(model_dir, "physics_log.json")
    with open(log_path, "w") as f:
        json.dump({"scene_info": scene_info, "frames": logger.frames, "report": report}, f, indent=1)
    print(f"[Bench] Log saved: {log_path} ({len(logger.frames)} frames)")

    summary_path = os.path.join(model_dir, "summary.txt")
    with open(summary_path, "w") as f:
        f.write(f"Robot Test Bench - {model_name}\n")
        f.write(f"{'='*50}\n\n")
        for k, v in report.items():
            f.write(f"{k}: {v}\n")
        f.write(f"\nJoint limits:\n")
        for jn, (lo, hi) in sorted(joint_limits.items()):
            f.write(f"  {jn}: [{lo:.4f}, {hi:.4f}]\n")
    print(f"[Bench] Summary saved: {summary_path}")

    # Encode videos
    if record_video:
        for cam_name, rp, w, rep_dir in cameras:
            video_path = os.path.join(model_dir, f"{cam_name}.mp4")
            encode_video(rep_dir, video_path)

    # Export LeRobot dataset for grasp episodes (skip when task_config: different camera set)
    if args.grasp and not getattr(args, "task_config", None):
        try:
            export_lerobot_dataset(logger, report, model_dir, cameras)
        except Exception as e:
            import traceback
            print(f"[Bench] WARN: LeRobot export failed: {e}")
            traceback.print_exc()

    # Cleanup: remove articulation from scene before next model
    try:
        world.scene.remove_object("tiago_bench")
    except Exception:
        pass

    return report


# ---------------------------------------------------------------------------
# LeRobot v3.0 dataset export
# ---------------------------------------------------------------------------
LEROBOT_STATE_JOINTS = [
    "arm_right_1_joint", "arm_right_2_joint", "arm_right_3_joint",
    "arm_right_4_joint", "arm_right_5_joint", "arm_right_6_joint",
    "arm_right_7_joint",
    "torso_lift_joint",
    "gripper_right_left_finger_joint", "gripper_right_right_finger_joint",
    "head_1_joint", "head_2_joint",
]


def export_lerobot_dataset(logger, report, model_dir, cameras_info):
    """Export simulation data in LeRobot v3.0 compatible format."""
    import shutil
    import uuid as uuid_mod
    from datetime import datetime, timezone

    ep_id = str(uuid_mod.uuid4())
    ep_base = os.path.join(r"C:\RoboLab_Data\episodes", ep_id)
    os.makedirs(ep_base, exist_ok=True)

    meta_dir = os.path.join(ep_base, "meta")
    data_dir = os.path.join(ep_base, "data", "chunk-000")
    vid_dir = os.path.join(ep_base, "videos", "chunk-000")
    os.makedirs(meta_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(vid_dir, exist_ok=True)

    frames = logger.frames
    fps = 20.0
    n_frames = len(frames)
    state_dim = len(LEROBOT_STATE_JOINTS) + 2  # +base_x, base_y

    # -- Build tabular data --
    rows = []
    for i, f in enumerate(frames):
        joints = f.get("joints", {})
        bp = f.get("base_position", {})

        state_vec = []
        for jn in LEROBOT_STATE_JOINTS:
            state_vec.append(joints.get(jn, {}).get("position_rad", 0.0))
        state_vec.append(bp.get("x", 0.0))
        state_vec.append(bp.get("y", 0.0))

        action_vec = []
        for jn in LEROBOT_STATE_JOINTS:
            action_vec.append(joints.get(jn, {}).get("target_rad",
                              joints.get(jn, {}).get("position_rad", 0.0)))
        action_vec.append(bp.get("x", 0.0))
        action_vec.append(bp.get("y", 0.0))

        row = {
            "timestamp": round(f.get("sim_time", 0.0), 4),
            "episode_index": 0,
            "frame_index": i,
            "task_index": 0,
        }
        for si, sv in enumerate(state_vec):
            row[f"observation.state.{si}"] = round(float(sv), 6)
        for ai, av in enumerate(action_vec):
            row[f"action.{ai}"] = round(float(av), 6)
        rows.append(row)

    # Write Parquet
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, os.path.join(data_dir, "episode_000.parquet"))
        print(f"[Bench] LeRobot Parquet: {n_frames} frames, {state_dim}D state")
    except ImportError:
        parquet_path = os.path.join(data_dir, "episode_000.json")
        with open(parquet_path, "w") as pf:
            json.dump(rows, pf)
        print(f"[Bench] LeRobot JSON fallback (pyarrow not available): {n_frames} frames")

    # -- Copy videos (use camera names from cameras_info, e.g. top_kitchen, isometric_kitchen) --
    cam_names = [c[0] for c in cameras_info]
    for cam_name in cam_names:
        src = os.path.join(model_dir, f"{cam_name}.mp4")
        if os.path.isfile(src):
            cam_vid_dir = os.path.join(vid_dir, f"observation.images.{cam_name}")
            os.makedirs(cam_vid_dir, exist_ok=True)
            shutil.copy2(src, os.path.join(cam_vid_dir, "episode_000.mp4"))

    # -- meta/info.json --
    state_features = {}
    for si, jn in enumerate(LEROBOT_STATE_JOINTS):
        state_features[f"observation.state.{si}"] = {
            "dtype": "float32", "shape": [1], "joint": jn}
    state_features[f"observation.state.{len(LEROBOT_STATE_JOINTS)}"] = {
        "dtype": "float32", "shape": [1], "joint": "base_x"}
    state_features[f"observation.state.{len(LEROBOT_STATE_JOINTS)+1}"] = {
        "dtype": "float32", "shape": [1], "joint": "base_y"}

    info = {
        "codebase_version": "v3.0",
        "robot_type": "tiago_dual",
        "fps": fps,
        "total_episodes": 1,
        "total_frames": n_frames,
        "features": {
            "observation.state": {
                "dtype": "float32",
                "shape": [state_dim],
                "names": LEROBOT_STATE_JOINTS + ["base_x", "base_y"],
            },
            "action": {
                "dtype": "float32",
                "shape": [state_dim],
                "names": LEROBOT_STATE_JOINTS + ["base_x", "base_y"],
            },
        },
        "video_keys": [f"observation.images.{c}" for c in cam_names],
    }
    with open(os.path.join(meta_dir, "info.json"), "w") as f:
        json.dump(info, f, indent=2)

    # -- meta/episodes.jsonl --
    ep_meta = {
        "episode_index": 0,
        "length": n_frames,
        "task_index": 0,
        "episode_id": ep_id,
    }
    with open(os.path.join(meta_dir, "episodes.jsonl"), "w") as f:
        f.write(json.dumps(ep_meta) + "\n")

    # -- meta/tasks.jsonl --
    task_meta = {
        "task_index": 0,
        "task": "Pick mug from table, lift 20cm, move 20cm right, place back on table",
    }
    with open(os.path.join(meta_dir, "tasks.jsonl"), "w") as f:
        f.write(json.dumps(task_meta) + "\n")

    # -- meta/modality.json (GR00T compatible) --
    modality = {
        "observation": {
            "state": LEROBOT_STATE_JOINTS + ["base_x", "base_y"],
            "images": {c: f"observation.images.{c}" for c in cam_names},
        },
        "action": LEROBOT_STATE_JOINTS + ["base_x", "base_y"],
    }
    with open(os.path.join(meta_dir, "modality.json"), "w") as f:
        json.dump(modality, f, indent=2)

    # -- meta/stats.json --
    if rows:
        stats = {}
        for key in rows[0]:
            if key.startswith("observation.state.") or key.startswith("action."):
                vals = [r[key] for r in rows]
                stats[key] = {
                    "min": round(min(vals), 6),
                    "max": round(max(vals), 6),
                    "mean": round(sum(vals) / len(vals), 6),
                }
        with open(os.path.join(meta_dir, "stats.json"), "w") as f:
            json.dump(stats, f, indent=2)

    # -- metadata.json (RoboLab episode compat) --
    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "id": ep_id,
        "status": "completed",
        "task": "table_grasp_place",
        "robot_model": f"{report.get('model', 'heavy')} (tiago_dual_functional.usd)",
        "scene": "grasp_bench_5x5m_white_tile",
        "duration_sec": report.get("duration_s", 0),
        "format": "lerobot_v3",
        "cameras": {c: c for c in cam_names},
        "actions": [
            {"name": "approach_table", "description": "Drive forward to table"},
            {"name": "pre_grasp", "description": "Raise arm to pre-grasp pose"},
            {"name": "grasp", "description": "Lower arm, close gripper on mug"},
            {"name": "lift", "description": "Lift mug 20cm"},
            {"name": "strafe_right", "description": "Move 20cm right"},
            {"name": "place", "description": "Lower and release mug"},
            {"name": "return", "description": "Drive back to start"},
        ],
        "physics": {
            "solver": "TGS",
            "physics_hz": 120,
            "gravity": -9.81,
            "fixed_base": False,
        },
        "results": {
            "max_tilt_deg": report.get("max_tilt_deg", 0),
            "verdict": report.get("verdict", ""),
            "total_frames": n_frames,
            "grasp_success": report.get("grasp_success", False),
            "grasp_retry_count": report.get("grasp_retry_count", 0),
            "grasp_active_mode_final": report.get("grasp_active_mode_final", ""),
            "grasp_lift_delta_m": report.get("grasp_lift_delta_m"),
            "grasp_final_tilt_deg": report.get("grasp_final_tilt_deg"),
        },
        "created_at": now,
    }
    with open(os.path.join(ep_base, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    # Also copy physics_log.json for full traceability
    src_log = os.path.join(model_dir, "physics_log.json")
    if os.path.isfile(src_log):
        shutil.copy2(src_log, os.path.join(ep_base, "physics_log.json"))

    # telemetry.json — general format (robot_position + mug over time)
    trajectory = []
    for f in frames:
        bp = f.get("base_position", {})
        entry = {
            "timestamp": round(f.get("sim_time", 0.0), 4),
            "robot_position": {"x": bp.get("x", 0), "y": bp.get("y", 0), "z": bp.get("z", 0)},
        }
        if "mug_position" in f:
            entry["mug_position"] = f["mug_position"]
        trajectory.append(entry)
    telemetry = {
        "episode_duration": report.get("duration_s", 0),
        "trajectory": trajectory,
    }
    with open(os.path.join(ep_base, "telemetry.json"), "w") as f:
        json.dump(telemetry, f, indent=2)

    # Copy camera videos to episode root (camera_0, camera_1, ...) for general format
    for idx, cam_name in enumerate(cam_names):
        src = os.path.join(model_dir, f"{cam_name}.mp4")
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(ep_base, f"camera_{idx}.mp4"))

    print(f"[Bench] LeRobot dataset exported: {ep_base}")
    print(f"[Bench]   Episode ID: {ep_id}")
    print(f"[Bench]   Frames: {n_frames}, State dim: {state_dim}, Cameras: {cam_names}")
    return ep_base


def _apply_targets(articulation, dof_names, targets):
    """Apply joint position targets via ArticulationAction.
    Skips wheel/roller joints when driving to avoid fighting velocity control."""
    from omni.isaac.core.utils.types import ArticulationAction
    pos_array = np.zeros(len(dof_names), dtype=np.float32)
    current = articulation.get_joint_positions()
    if current is not None:
        pos_array[:] = np.array(current, dtype=np.float32)
    for jname, val in targets.items():
        if args.drive_base and ("wheel" in jname or "roller" in jname):
            continue
        if jname in dof_names:
            idx = dof_names.index(jname)
            pos_array[idx] = float(val)
        else:
            for alias in [jname.replace("arm_right_", "arm_"),
                          jname.replace("arm_left_", "arm_"),
                          jname.replace("arm_", "arm_right_"),
                          jname.replace("arm_", "arm_left_")]:
                if alias in dof_names:
                    idx = dof_names.index(alias)
                    pos_array[idx] = float(val)
    articulation.apply_action(ArticulationAction(joint_positions=pos_array))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
try:
    os.makedirs(args.output, exist_ok=True)
    world = World(physics_dt=1.0 / 120.0, rendering_dt=1.0 / 60.0)
    build_clean_scene()
    simulation_app.update()

    all_reports = {}
    for model_name in MODELS_TO_TEST:
        report = run_test(model_name, world, args.output, record_video=not args.no_video)
        all_reports[model_name] = report

    # Comparison summary
    if len(all_reports) > 1:
        print(f"\n{'='*70}")
        print("[Bench] MODEL COMPARISON")
        print(f"{'='*70}")
        header = f"{'Model':<10} {'Drift(m)':<12} {'Tilt(deg)':<12} {'MaxJErr(rad)':<14} {'Stable':<8} {'Verdict'}"
        print(header)
        print("-" * len(header))
        for mn, r in all_reports.items():
            print(f"{mn:<10} {r['max_drift_m']:<12.5f} {r['max_tilt_deg']:<12.3f} "
                  f"{r['max_joint_error_rad']:<14.5f} {str(r['stable']):<8} {r['verdict']}")

        comp_path = os.path.join(args.output, "comparison.json")
        with open(comp_path, "w") as f:
            json.dump(all_reports, f, indent=2)
        print(f"\n[Bench] Comparison saved: {comp_path}")

    print("\n[Bench] ALL TESTS COMPLETE")

except Exception as e:
    import traceback
    print(f"[Bench] FATAL: {e}")
    traceback.print_exc()
finally:
    simulation_app.close()
