"""
Regression test for the fixed_banana_to_sink experiment (Experiment 2).
Validates that all config files and code parameters match the documented values.
Run without Isaac Sim -- pure file/config validation.

Usage:
    python scripts/test_banana_to_sink_regression.py
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
    print("Banana-to-Sink Regression Test (Experiment 2)")
    print("=" * 60)

    # ---------------------------------------------------------------
    # 1. File existence
    # ---------------------------------------------------------------
    print("\n--- File existence ---")
    check_exists("scene_config", "scenes/kitchen_fixed/kitchen_fixed_config.yaml")
    check_exists("task_config", "config/tasks/fixed_banana_to_sink.json")
    check_exists("robot_profile", "config/robots/tiago_heavy.yaml")
    check_exists("test_script", "scripts/test_robot_bench.py")
    check_exists("documentation", "docs/experiment_banana_to_sink.md")
    check_exists("scene_builder", "scenes/kitchen_fixed/kitchen_fixed_builder.py")

    # ---------------------------------------------------------------
    # 2. Scene config: banana and sink
    # ---------------------------------------------------------------
    print("\n--- Scene config (banana & sink) ---")
    with open(os.path.join(REPO_ROOT, "scenes/kitchen_fixed/kitchen_fixed_config.yaml"), "r") as f:
        scene_cfg = yaml.safe_load(f)

    sink = scene_cfg["furniture"]["sink_cabinet"]
    check("sink.center_x", sink["center_x"], 0.45)
    check("sink.center_y", sink["center_y"], 3.45)
    check("sink.width", sink["width"], 0.80)
    check("sink.depth", sink["depth"], 0.80)
    check("sink.height", sink["height"], 0.90)
    check("sink.basin_depth", sink["basin_depth"], 0.18)
    check("sink.basin_margin", sink["basin_margin"], 0.06)

    banana = scene_cfg["objects"]["banana"]
    check("banana.length", banana["length"], 0.22)
    check("banana.radius", banana["radius"], 0.030)
    check("banana.mass_kg", banana["mass_kg"], 0.05)
    check("banana.offset_x", banana["offset_x"], -0.05)
    check("banana.offset_y", banana["offset_y"], 0.0)

    banana_mat = scene_cfg["materials"]["banana_yellow"]
    check("banana_mat.friction_static", banana_mat.get("friction_static"), 1.0)
    check("banana_mat.friction_dynamic", banana_mat.get("friction_dynamic"), 0.8)

    plate = scene_cfg["objects"]["plate"]
    check("plate.offset_x", plate["offset_x"], 0.25)
    check("plate.offset_y", plate["offset_y"], 0.0)

    table = scene_cfg["furniture"]["table"]
    check("table.center_x", table["center_x"], 1.35)
    check("table.center_y", table["center_y"], 3.45)
    check("table.height", table["height"], 0.80)

    # ---------------------------------------------------------------
    # 2b. Scene builder: banana orientation
    # ---------------------------------------------------------------
    print("\n--- Scene builder (banana orientation) ---")
    builder_path = os.path.join(REPO_ROOT, "scenes/kitchen_fixed/kitchen_fixed_builder.py")
    with open(builder_path, "r", encoding="utf-8") as f:
        builder_code = f.read()
    check("banana rotate_xyz=(90, 0, 0)",
          "rotate_xyz=(90, 0, 0)" in builder_code, True)

    # ---------------------------------------------------------------
    # 3. Task config: fixed_banana_to_sink.json
    # ---------------------------------------------------------------
    print("\n--- Task config (fixed_banana_to_sink.json) ---")
    with open(os.path.join(REPO_ROOT, "config/tasks/fixed_banana_to_sink.json"), "r") as f:
        tc = json.load(f)

    check("episode_name", tc["episode_name"], "fixed_banana_to_sink")
    check("kitchen_scene", tc["kitchen_scene"], "fixed")
    check("scene.sink", tc["scene"]["sink"], True)
    check("scene.plate_fruit", tc["scene"]["plate_fruit"], True)

    robot = tc["robot"]
    check("robot.start_pose", robot["start_pose"], [0.0, 0.0, 90])
    check("robot.robot_profile", robot["robot_profile"], "config/robots/tiago_heavy.yaml")

    # Control timing parameters
    control = tc.get("control", {})
    check("control.grasp_settle_steps", control.get("grasp_settle_steps"), 120)
    check("control.extend_arm_steps", control.get("extend_arm_steps"), 300)
    check("control.settle_at_table_steps", control.get("settle_at_table_steps"), 60)
    check("control.approach_timeout_steps", control.get("approach_timeout_steps"), 600)
    check("control.lift_timeout_steps", control.get("lift_timeout_steps"), 1500)
    check("control.place_descent_steps", control.get("place_descent_steps"), 600)

    tasks = tc["tasks"]
    check("task_count", len(tasks), 5)

    # T1: navigate to banana
    t1 = tasks[0]
    check("T1.id", t1["id"], "T1_drive_to_banana")
    check("T1.type", t1["type"], "navigate_to")
    check("T1.target_xy", t1["target_xy"], [1.55, 2.50])
    check("T1.tolerance_m", t1["tolerance_m"], 0.25)

    # T2: pick banana
    t2 = tasks[1]
    check("T2.id", t2["id"], "T2_pick_banana")
    check("T2.type", t2["type"], "pick_object")
    check("T2.object_usd_path", t2["object_usd_path"], "/World/Kitchen/Objects/Banana")
    check("T2.grasp_mode", t2["grasp_mode"], "top")
    check("T2.lift_height_m", t2["lift_height_m"], 0.20)
    check("T2.approach_arm_retracted", t2["approach_arm_retracted"], True)
    check("T2.lift_interpolation_steps_override", t2["lift_interpolation_steps_override"], 1200)

    # T3: carry to sink
    t3 = tasks[2]
    check("T3.id", t3["id"], "T3_carry_to_sink")
    check("T3.type", t3["type"], "carry_to")
    check("T3.destination_xy", t3["destination_xy"], [0.45, 2.80])
    check("T3.relative", t3["relative"], False)
    check("T3.drive_speed_ms", t3["drive_speed_ms"], 0.15)
    check("T3.final_heading_deg", t3["final_heading_deg"], 180)
    check("T3.object_usd_path", t3["object_usd_path"], "/World/Kitchen/Objects/Banana")

    # T4: place in sink
    t4 = tasks[3]
    check("T4.id", t4["id"], "T4_place_in_sink")
    check("T4.type", t4["type"], "place_object")
    check("T4.timeout_s", t4["timeout_s"], 10)
    check("T4.placement_top_z", t4["placement_top_z"], 0.90)
    check("T4.placement_cx", t4["placement_cx"], 0.45)
    check("T4.placement_cy", t4["placement_cy"], 3.10)
    check("T4.placement_half_w", t4["placement_half_w"], 0.50)
    check("T4.placement_half_d", t4["placement_half_d"], 0.50)
    check("T4.placement_margin", t4["placement_margin"], 0.20)
    check("T4.placement_abort_z_offset", t4["placement_abort_z_offset"], -0.30)
    check("T4.placement_release_z_offset", t4["placement_release_z_offset"], 0.10)
    check("T4.placement_success_z_offset", t4["placement_success_z_offset"], 0.30)
    check("T4.success_criteria.object_usd_path",
          t4["success_criteria"]["object_usd_path"],
          "/World/Kitchen/Objects/Banana")

    # T5: return
    t5 = tasks[4]
    check("T5.id", t5["id"], "T5_return_to_start")
    check("T5.type", t5["type"], "navigate_to")
    check("T5.target_xy", t5["target_xy"], [0.0, 0.0])
    check("T5.tolerance_m", t5["tolerance_m"], 1.50)

    # ---------------------------------------------------------------
    # 4. Grasp tuning for banana
    # ---------------------------------------------------------------
    print("\n--- Grasp tuning (banana-specific) ---")
    grasp = tc.get("grasp", {})
    check("grasp.gripper_close_value", grasp.get("gripper_close_value"), 0.015)
    check("grasp.gripper_final_close_value", grasp.get("gripper_final_close_value"), 0.010)
    check("grasp.gripper_hold_threshold", grasp.get("gripper_hold_threshold"), 0.005)
    check("grasp.top_descend_clearance", grasp.get("top_descend_clearance"), 0.04)
    check("grasp.j4_extended", grasp.get("j4_extended"), -0.35)
    check("grasp.j4_retracted", grasp.get("j4_retracted"), 0.30)
    check("grasp.torso_approach", grasp.get("torso_approach"), 0.35)
    check("grasp.torso_hold", grasp.get("torso_hold"), 0.35)

    # ---------------------------------------------------------------
    # 5. Code features for experiment-2
    # ---------------------------------------------------------------
    print("\n--- Code features (test_robot_bench.py) ---")
    bench_path = os.path.join(REPO_ROOT, "scripts/test_robot_bench.py")
    with open(bench_path, "r", encoding="utf-8") as f:
        bench_code = f.read()

    check("code: per-task placement_top_z",
          'task.get("placement_top_z"' in bench_code, True)
    check("code: per-task placement_cx",
          'task.get("placement_cx"' in bench_code, True)
    check("code: per-task placement_cy",
          'task.get("placement_cy"' in bench_code, True)
    check("code: per-task placement_half_w",
          'task.get("placement_half_w"' in bench_code, True)
    check("code: per-task placement_half_d",
          'task.get("placement_half_d"' in bench_code, True)
    check("code: per-task placement_margin",
          'task.get("placement_margin"' in bench_code, True)
    check("code: approach_arm_retracted param",
          "approach_arm_retracted" in bench_code, True)
    check("code: lift_with_torso_only param",
          "lift_with_torso_only" in bench_code, True)
    check("code: lift_interpolation_steps_override param",
          "lift_interpolation_steps_override" in bench_code, True)
    check("code: gripper_final_close_value",
          "gripper_final_close_value" in bench_code, True)
    check("code: outside placement bounds",
          "outside placement bounds" in bench_code, True)
    check("code: carry_to final_heading_deg",
          "final_heading_deg" in bench_code, True)
    check("code: carry_to object tracking",
          "carry_obj_path" in bench_code, True)
    check("code: place_object place_heading_deg",
          "place_heading_deg" in bench_code, True)
    check("code: carry_to TABLE_SOUTH_BOUNDARY_Y bypass",
          "target_y <= TABLE_SOUTH_BOUNDARY_Y" in bench_code, True)

    # ---------------------------------------------------------------
    # 6. Derived geometry
    # ---------------------------------------------------------------
    print("\n--- Derived geometry ---")
    table_cx = table["center_x"]
    table_cy = table["center_y"]
    plate_x = table_cx + plate["offset_x"]
    plate_y = table_cy + plate["offset_y"]
    banana_x = plate_x + banana["offset_x"]
    banana_y = plate_y + banana["offset_y"]
    check("banana_world_x", banana_x, 1.55, tol=0.001)
    check("banana_world_y", banana_y, 3.45, tol=0.001)

    sink_cx = sink["center_x"]
    sink_cy = sink["center_y"]
    basin_inner = sink["width"] - 2 * sink["basin_margin"]
    check("basin_inner_size", basin_inner, 0.68, tol=0.001)
    check("sink_top_z", sink["height"], 0.90)

    t1_approach_y = t1["target_xy"][1]
    check("T1 approach south of boundary",
          t1_approach_y < tc["safety"]["table_south_boundary_y"], True)

    t3_dest = t3["destination_xy"]
    check("T3 dest near sink X", abs(t3_dest[0] - sink_cx) < 0.10, True)
    check("T3 dest south of sink", t3_dest[1] < sink_cy, True)

    t4_cx = t4["placement_cx"]
    check("T4 placement near sink center X", t4_cx, sink_cx)
    check("T4 placement_top_z matches sink height", t4["placement_top_z"], sink["height"])

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
        print("ALL CHECKS PASSED -- experiment-2 parameters are consistent")
        sys.exit(0)


if __name__ == "__main__":
    main()
