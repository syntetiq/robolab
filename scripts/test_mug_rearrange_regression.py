"""
Regression test for the fixed_mug_rearrange experiment.
Validates that all config files and code parameters match the documented values.
Run without Isaac Sim -- pure file/config validation.

Usage:
    python scripts/test_mug_rearrange_regression.py
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
    print("Mug Rearrange Regression Test")
    print("=" * 60)

    # ---------------------------------------------------------------
    # 1. Check files exist
    # ---------------------------------------------------------------
    print("\n--- File existence ---")
    check_exists("scene_config", "scenes/kitchen_fixed/kitchen_fixed_config.yaml")
    check_exists("scene_builder", "scenes/kitchen_fixed/kitchen_fixed_builder.py")
    check_exists("task_config", "config/tasks/fixed_mug_rearrange.json")
    check_exists("test_script", "scripts/test_robot_bench.py")
    check_exists("run_script", "scripts/run_task_config.ps1")
    check_exists("documentation", "docs/experiment_mug_rearrange.md")

    # ---------------------------------------------------------------
    # 2. Validate kitchen_fixed_config.yaml
    # ---------------------------------------------------------------
    print("\n--- Scene config (kitchen_fixed_config.yaml) ---")
    with open(os.path.join(REPO_ROOT, "scenes/kitchen_fixed/kitchen_fixed_config.yaml"), "r") as f:
        cfg = yaml.safe_load(f)

    room = cfg["room"]
    check("room.size_x", room["size_x"], 8.0)
    check("room.size_y", room["size_y"], 8.0)
    check("room.wall_height", room["wall_height"], 2.8)

    table = cfg["furniture"]["table"]
    check("table.center_x", table["center_x"], 1.35)
    check("table.center_y", table["center_y"], 3.45)
    check("table.width", table["width"], 0.80)
    check("table.depth", table["depth"], 0.80)
    check("table.height", table["height"], 0.80)

    fridge = cfg["furniture"]["fridge"]
    check("fridge.center_x", fridge["center_x"], -1.35)
    check("fridge.center_y", fridge["center_y"], 3.45)

    sink = cfg["furniture"]["sink_cabinet"]
    check("sink.center_x", sink["center_x"], 0.45)
    check("sink.center_y", sink["center_y"], 3.45)

    mug = cfg["objects"]["mug"]
    check("mug.offset_x", mug["offset_x"], -0.20)
    check("mug.offset_y", mug["offset_y"], -0.15)
    check("mug.radius", mug["radius"], 0.04)
    check("mug.height", mug["height"], 0.10)
    check("mug.mass_kg", mug["mass_kg"], 0.30)

    plate = cfg["objects"]["plate"]
    check("plate.offset_x", plate["offset_x"], 0.25)
    check("plate.offset_y", plate["offset_y"], 0.0)
    check("plate.radius", plate["radius"], 0.15)

    apple = cfg["objects"]["apple"]
    check("apple.offset_x", apple["offset_x"], 0.07)
    check("apple.offset_y", apple["offset_y"], 0.0)

    banana = cfg["objects"]["banana"]
    check("banana.offset_x", banana["offset_x"], -0.05)
    check("banana.offset_y", banana["offset_y"], 0.0)
    check("banana.length", banana["length"], 0.22)

    # ---------------------------------------------------------------
    # 3. Validate fixed_mug_rearrange.json
    # ---------------------------------------------------------------
    print("\n--- Task config (fixed_mug_rearrange.json) ---")
    with open(os.path.join(REPO_ROOT, "config/tasks/fixed_mug_rearrange.json"), "r") as f:
        tc = json.load(f)

    check("episode_name", tc["episode_name"], "fixed_mug_rearrange")
    check("kitchen_scene", tc["kitchen_scene"], "fixed")
    check("simulation_duration_s", tc["simulation_duration_s"], 300)

    robot = tc["robot"]
    check("robot.start_pose", robot["start_pose"], [0.0, 0.0, 90])
    check("robot.model", robot["model"], "heavy")
    check("robot.gripper_length_m", robot["gripper_length_m"], 0.10)

    glob = tc["global"]
    check("global.drive_speed_ms", glob["drive_speed_ms"], 0.3)
    check("global.approach_clearance_m", glob["approach_clearance_m"], 0.13)
    check("global.on_task_failure", glob["on_task_failure"], "abort")

    tasks = tc["tasks"]
    check("task_count", len(tasks), 5)

    t1 = tasks[0]
    check("T1.id", t1["id"], "T1_drive_to_mug")
    check("T1.type", t1["type"], "navigate_to")
    check("T1.target_xy", t1["target_xy"], [1.15, 2.50])
    check("T1.tolerance_m", t1["tolerance_m"], 0.25)
    check("T1.drive_speed_ms", t1["drive_speed_ms"], 0.4)

    t2 = tasks[1]
    check("T2.id", t2["id"], "T2_pick_mug")
    check("T2.type", t2["type"], "pick_object")
    check("T2.object_usd_path", t2["object_usd_path"], "/World/Kitchen/Objects/Mug")
    check("T2.grasp_mode", t2["grasp_mode"], "top")
    check("T2.lift_height_m", t2["lift_height_m"], 0.20)

    t3 = tasks[2]
    check("T3.id", t3["id"], "T3_carry_east")
    check("T3.type", t3["type"], "carry_to")
    check("T3.destination_xy", t3["destination_xy"], [0.20, 0.0])
    check("T3.relative", t3["relative"], True)
    check("T3.tolerance_m", t3["tolerance_m"], 0.10)

    t4 = tasks[3]
    check("T4.id", t4["id"], "T4_place_mug")
    check("T4.type", t4["type"], "place_object")
    check("T4.release_height_m", t4["release_height_m"], 0.05)
    check("T4.success_criteria.object_usd_path",
          t4["success_criteria"]["object_usd_path"],
          "/World/Kitchen/Objects/Mug")

    t5 = tasks[4]
    check("T5.id", t5["id"], "T5_return_to_start")
    check("T5.type", t5["type"], "navigate_to")
    check("T5.target_xy", t5["target_xy"], [0.0, 0.0])
    check("T5.tolerance_m", t5["tolerance_m"], 1.50)

    # Verify no T3b exists
    task_ids = [t["id"] for t in tasks]
    check("no_T3b_task", "T3b_drive_to_table" not in task_ids, True)

    # ---------------------------------------------------------------
    # 4. Validate key constants in test_robot_bench.py
    # ---------------------------------------------------------------
    print("\n--- Code constants (test_robot_bench.py) ---")
    bench_path = os.path.join(REPO_ROOT, "scripts/test_robot_bench.py")
    with open(bench_path, "r", encoding="utf-8") as f:
        bench_code = f.read()

    check("TABLE_SOUTH_BOUNDARY_Y defined",
          "TABLE_SOUTH_BOUNDARY_Y = 2.75" in bench_code, True)
    check("GRIPPER_OPEN = 0.045",
          "GRIPPER_OPEN = 0.045" in bench_code, True)
    check("GRIPPER_GRASP_MUG = 0.02",
          "GRIPPER_GRASP_MUG = 0.02" in bench_code, True)

    # place_object uses arm extension (j4), not torso descent
    check("place_object: j4_end = -0.35",
          "j4_end = -0.35" in bench_code, True)
    check("place_object: descent_steps = 600",
          "descent_steps = 600" in bench_code, True)
    check("place_object: torso stays (torso_start)",
          'current_targets["torso_lift_joint"] = torso_start' in bench_code, True)

    # lift_mug retracts arm (j4 -> 0.30)
    check("lift_mug: j4_target = 0.30",
          "j4_target = 0.30" in bench_code, True)

    # Wheels always stopped after navigate_to and carry_to
    # (no "if not reached:" before wheel stop)
    nav_section = bench_code[bench_code.index("elif task_type == \"navigate_to\""):
                             bench_code.index("elif task_type == \"carry_to\"")]
    check("navigate_to: unconditional wheel stop",
          "if not reached:" not in nav_section.split("vel_array = np.zeros")[0][-200:], True)

    # XY bounds check in place_object
    check("place_object: XY bounds check",
          "outside table bounds" in bench_code, True)

    # Below-table abort check
    check("place_object: below-table abort",
          "below table" in bench_code, True)

    # pre_grasp_top pose
    check("pre_grasp_top: J4=-0.35",
          '"pre_grasp_top": {\n        "R": [1.50, 0.0, 0.0, -0.35, -1.57, 0.0, 0.0]' in bench_code, True)

    # ---------------------------------------------------------------
    # 5. Derived geometry checks
    # ---------------------------------------------------------------
    print("\n--- Derived geometry ---")
    table_cx, table_cy = 1.35, 3.45
    table_hw, table_hd = 0.40, 0.40
    table_south_edge = table_cy - table_hd
    check("table_south_edge", table_south_edge, 3.05, tol=0.001)

    mug_world_x = table_cx + mug["offset_x"]
    mug_world_y = table_cy + mug["offset_y"]
    check("mug_world_x", mug_world_x, 1.15, tol=0.001)
    check("mug_world_y", mug_world_y, 3.30, tol=0.001)

    robot_approach_y = t1["target_xy"][1]
    arm_reach = mug_world_y - robot_approach_y
    check("arm_reach_to_mug", arm_reach, 0.80, tol=0.01)
    check("robot_approach_south_of_boundary",
          robot_approach_y < 2.75, True)

    plate_world_x = table_cx + plate["offset_x"]
    plate_world_y = table_cy + plate["offset_y"]
    check("plate_world_x", plate_world_x, 1.60, tol=0.001)
    check("plate_world_y", plate_world_y, 3.45, tol=0.001)

    # Apple and banana fit within plate
    apple_dist = abs(apple["offset_x"])
    banana_half = banana["length"] / 2.0 + abs(banana["offset_x"])
    check("apple_within_plate", apple_dist + apple["radius"] <= plate["radius"], True)
    check("banana_mostly_on_plate", banana_half <= plate["radius"] + 0.02, True)

    # Carry distance
    carry_dx = t3["destination_xy"][0]
    check("carry_distance_east", carry_dx, 0.20)

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
