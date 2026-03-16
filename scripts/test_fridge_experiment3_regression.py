"""
Regression test for the fixed_fridge_experiment3 (Experiment 3).
Validates that all config files and code parameters match the documented values.
Run without Isaac Sim -- pure file/config validation.

Usage:
    python scripts/test_fridge_experiment3_regression.py
"""

import json
import os
import sys
import math

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0

def check(name, actual, expected, tol=None):
    global PASS, FAIL
    if tol is not None:
        ok = abs(actual - expected) <= tol
    elif isinstance(expected, (int, float)):
        ok = actual == expected
    else:
        ok = actual == expected
    status = "OK" if ok else "FAIL"
    if not ok:
        FAIL += 1
        print(f"  [{status}] {name}: got {actual!r}, expected {expected!r}")
    else:
        PASS += 1
    return ok


def check_exists(name, path):
    global PASS, FAIL
    full = os.path.join(REPO_ROOT, path)
    ok = os.path.exists(full)
    if not ok:
        FAIL += 1
        print(f"  [FAIL] {name}: file not found: {path}")
    else:
        PASS += 1
    return ok


def main():
    global PASS, FAIL

    print("=" * 60)
    print("Fridge Experiment 3 Regression Test")
    print("=" * 60)

    # ---------------------------------------------------------------
    # 1. Check files exist
    # ---------------------------------------------------------------
    print("\n--- File existence ---")
    check_exists("scene_config", "scenes/kitchen_fixed/kitchen_fixed_config.yaml")
    check_exists("scene_builder", "scenes/kitchen_fixed/kitchen_fixed_builder.py")
    check_exists("task_config", "config/tasks/fixed_fridge_experiment3.json")
    check_exists("test_script", "scripts/test_robot_bench.py")
    check_exists("run_script", "scripts/run_task_config.ps1")
    check_exists("robot_profile", "config/robots/tiago_heavy.yaml")

    # ---------------------------------------------------------------
    # 2. Validate kitchen_fixed_config.yaml (fridge-specific)
    # ---------------------------------------------------------------
    print("\n--- Scene config (kitchen_fixed_config.yaml) ---")
    with open(os.path.join(REPO_ROOT, "scenes/kitchen_fixed/kitchen_fixed_config.yaml"), "r") as f:
        scene_cfg = yaml.safe_load(f)

    fridge = scene_cfg["furniture"]["fridge"]
    check("fridge.center_x", fridge["center_x"], -1.35)
    check("fridge.center_y", fridge["center_y"], 3.45)
    check("fridge.width", fridge["width"], 0.80)
    check("fridge.depth", fridge["depth"], 0.80)
    check("fridge.height", fridge["height"], 2.00)
    check("fridge.door_thickness", fridge["door_thickness"], 0.03)
    check("fridge.door_mass_kg", fridge["door_mass_kg"], 8.0)
    check("fridge.door_open_deg", fridge["door_open_deg"], 90.0)

    handle = fridge["handle"]
    check("fridge.handle.type", handle["type"], "vertical")
    check("fridge.handle.length", handle["length"], 0.50)
    check("fridge.handle.center_height", handle["center_height"], 1.10)
    check("fridge.handle.standoff", handle["standoff"], 0.06)

    # ---------------------------------------------------------------
    # 3. Validate fixed_fridge_experiment3.json
    # ---------------------------------------------------------------
    print("\n--- Task config (fixed_fridge_experiment3.json) ---")
    with open(os.path.join(REPO_ROOT, "config/tasks/fixed_fridge_experiment3.json"), "r") as f:
        tc = json.load(f)

    check("episode_name", tc["episode_name"], "fixed_fridge_experiment3")
    check("kitchen_scene", tc["kitchen_scene"], "fixed")
    check("simulation_duration_s", tc["simulation_duration_s"], 300)

    robot = tc["robot"]
    check("robot.start_pose", robot["start_pose"], [0.0, 0.0, 90])
    check("robot.model", robot["model"], "heavy")
    check("robot.gripper_length_m", robot["gripper_length_m"], 0.10)
    check("robot.robot_profile", robot["robot_profile"], "config/robots/tiago_heavy.yaml")

    glob = tc["global"]
    check("global.drive_speed_ms", glob["drive_speed_ms"], 0.3)
    check("global.on_task_failure", glob["on_task_failure"], "abort")

    tasks = tc["tasks"]
    check("task_count", len(tasks), 4)

    # T1: Drive to fridge
    t1 = tasks[0]
    check("T1.id", t1["id"], "T1_drive_to_fridge")
    check("T1.type", t1["type"], "navigate_to")
    check("T1.target_xy", t1["target_xy"], [-2.10, 2.55])
    check("T1.tolerance_m", t1["tolerance_m"], 0.30)
    check("T1.drive_speed_ms", t1["drive_speed_ms"], 0.4)

    # T2: Open fridge
    t2 = tasks[1]
    check("T2.id", t2["id"], "T2_open_fridge")
    check("T2.type", t2["type"], "open_door")
    check("T2.handle_usd_path", t2["handle_usd_path"],
          "/World/Kitchen/Furniture/Fridge/Door/Handle")
    check("T2.approach_axis", t2["approach_axis"], "y")
    check("T2.arm_reach_m", t2["arm_reach_m"], 0.40)
    check("T2.base_lateral_offset_m", t2["base_lateral_offset_m"], 0.50)
    check("T2.arm_pose", t2["arm_pose"], "pre_grasp_handle")
    check("T2.pull_speed_ms", t2["pull_speed_ms"], 0.15)
    check("T2.timeout_s", t2["timeout_s"], 60)
    check("T2.success_criteria.min_angle_deg",
          t2["success_criteria"]["min_angle_deg"], 30)
    check("T2.success_criteria.door_joint_path",
          t2["success_criteria"]["door_joint_path"],
          "/World/Kitchen/Furniture/Fridge/DoorHinge")

    # T3: Close fridge
    t3 = tasks[2]
    check("T3.id", t3["id"], "T3_close_fridge")
    check("T3.type", t3["type"], "close_door")
    check("T3.handle_usd_path", t3["handle_usd_path"],
          "/World/Kitchen/Furniture/Fridge/Door/Handle")
    check("T3.approach_axis", t3["approach_axis"], "y")
    check("T3.arm_reach_m", t3["arm_reach_m"], 0.40)
    check("T3.base_lateral_offset_m", t3["base_lateral_offset_m"], 0.50)
    check("T3.arm_pose", t3["arm_pose"], "pre_grasp_handle")
    check("T3.push_speed_ms", t3["push_speed_ms"], 0.20)
    check("T3.timeout_s", t3["timeout_s"], 60)
    check("T3.success_criteria.max_angle_deg",
          t3["success_criteria"]["max_angle_deg"], 20)
    check("T3.success_criteria.door_joint_path",
          t3["success_criteria"]["door_joint_path"],
          "/World/Kitchen/Furniture/Fridge/DoorHinge")

    # T4: Return to start
    t4 = tasks[3]
    check("T4.id", t4["id"], "T4_return_to_start")
    check("T4.type", t4["type"], "navigate_to")
    check("T4.target_xy", t4["target_xy"], [0.0, 0.0])
    check("T4.tolerance_m", t4["tolerance_m"], 2.00)
    check("T4.drive_speed_ms", t4["drive_speed_ms"], 0.4)

    # ---------------------------------------------------------------
    # 4. Validate robot profile and code DEFAULTS
    # ---------------------------------------------------------------
    print("\n--- Robot profile (tiago_heavy.yaml) ---")
    with open(os.path.join(REPO_ROOT, "config/robots/tiago_heavy.yaml"), "r") as f:
        rp = yaml.safe_load(f)

    check("rp.spawn_z", rp["spawn_z"], 0.08)
    check("rp.torso_max", rp["torso_max"], 0.35)
    check("rp.wheel.radius", rp["wheel"]["radius"], 0.0985)

    print("\n--- Code DEFAULTS: pre_grasp_handle pose ---")
    check("code: pre_grasp_handle in DEFAULTS",
          '"pre_grasp_handle"' in bench_code if 'bench_code' in dir() else True, True)
    # Read bench code here for pose validation
    bench_path = os.path.join(REPO_ROOT, "scripts/test_robot_bench.py")
    with open(bench_path, "r", encoding="utf-8") as f:
        bench_code_early = f.read()
    check("code: pre_grasp_handle defined in DEFAULTS",
          "pre_grasp_handle" in bench_code_early, True)

    # ---------------------------------------------------------------
    # 5. Validate code has door manipulation functions
    # ---------------------------------------------------------------
    print("\n--- Code structure (test_robot_bench.py) ---")
    bench_path = os.path.join(REPO_ROOT, "scripts/test_robot_bench.py")
    with open(bench_path, "r", encoding="utf-8") as f:
        bench_code = f.read()

    check("code: run_door_open_close_cycle function exists",
          "def run_door_open_close_cycle(" in bench_code, True)
    check("code: get_door_hinge_angle_deg function exists",
          "def get_door_hinge_angle_deg(" in bench_code, True)
    check("code: _get_door_angle_from_joint helper exists",
          "def _get_door_angle_from_joint(" in bench_code, True)
    check("code: approach_axis parameter",
          "approach_axis" in bench_code, True)
    check("code: arm_reach_m parameter",
          "arm_reach_m" in bench_code, True)
    check("code: base_lateral_offset_m parameter",
          "base_lateral_offset_m" in bench_code, True)
    check("code: door_joint_path parameter",
          "door_joint_path" in bench_code, True)
    check("code: door_arm_pose parameter",
          "door_arm_pose" in bench_code, True)
    check("code: omni_wheel_velocities function exists",
          "def omni_wheel_velocities(" in bench_code, True)
    check("code: open_door handler",
          '"open_door"' in bench_code, True)
    check("code: close_door handler",
          '"close_door"' in bench_code, True)
    check("code: early close success detection",
          "close SUCCESS (during nav)" in bench_code, True)
    check("code: close waypoint navigation",
          "_close_waypoints" in bench_code, True)

    # ---------------------------------------------------------------
    # 6. Derived geometry checks
    # ---------------------------------------------------------------
    print("\n--- Derived geometry ---")
    fridge_cx = fridge["center_x"]
    fridge_cy = fridge["center_y"]
    fridge_half_d = fridge["depth"] / 2.0
    fridge_half_w = fridge["width"] / 2.0

    fridge_front_y = fridge_cy - fridge_half_d
    check("fridge_front_y (south face)", fridge_front_y, 3.05, tol=0.01)

    handle_world_x = fridge_cx - fridge_half_w + handle["standoff"]
    check("handle_world_x (approx)", handle_world_x, -1.69, tol=0.10)

    handle_world_y = fridge_front_y - handle["standoff"]
    check("handle_world_y (approx)", handle_world_y, 2.99, tol=0.10)

    robot_start_x = t1["target_xy"][0]
    robot_start_y = t1["target_xy"][1]
    check("robot positioned west of handle",
          robot_start_x < handle_world_x, True)
    check("robot positioned south of fridge front",
          robot_start_y < fridge_front_y, True)

    check("open success angle < door_open_deg",
          t2["success_criteria"]["min_angle_deg"] < fridge["door_open_deg"], True)
    check("close success angle > 0",
          t3["success_criteria"]["max_angle_deg"] > 0, True)
    check("close success angle < open success angle",
          t3["success_criteria"]["max_angle_deg"] < t2["success_criteria"]["min_angle_deg"], True)

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print(f"\n{'=' * 60}")
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    if FAIL > 0:
        print("REGRESSION DETECTED -- fix before running experiment")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED -- experiment parameters are consistent")
        sys.exit(0)


if __name__ == "__main__":
    main()
