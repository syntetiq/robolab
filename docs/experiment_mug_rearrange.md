# Experiment: Mug Rearrange (fixed_mug_rearrange)

Last verified: 2026-03-15
Episode: `fixed_mug_rearrange_20260315_215519`
Verdict: **PASS (task config)** -- all 5 tasks succeed

## 1. Scene Setup

### Room

- Size: 8.0 x 8.0 m, wall height 2.8 m
- Wall thickness: 0.15 m
- Floor: 8x8 parquet texture
- World origin: center of room (0, 0, 0)
- North wall inner face: Y = 3.85

### Furniture (flush to north wall, left to right)

| Item         | Center X | Center Y | Width | Depth | Height |
|--------------|----------|----------|-------|-------|--------|
| Fridge       | -1.35    | 3.45     | 0.80  | 0.80  | 2.00   |
| Dishwasher   | -0.45    | 3.45     | 0.80  | 0.80  | 0.80   |
| Sink cabinet |  0.45    | 3.45     | 0.80  | 0.80  | 0.90   |
| **Table**    |  **1.35**| **3.45** | **0.80**|**0.80**|**0.80**|

Table bounds: X [0.95, 1.75], Y [3.05, 3.85]. Table top Z = 0.80 m.

### Objects on Table

| Object | World X | World Y | World Z  | Size                   |
|--------|---------|---------|----------|------------------------|
| Mug    | 1.15    | 3.30    | ~0.85    | r=0.04, h=0.10, 0.30kg |
| Plate  | 1.60    | 3.45    | ~0.825   | r=0.15, h=0.025, 0.25kg|
| Apple  | 1.67    | 3.45    | ~0.88    | r=0.05, 0.15kg         |
| Banana | 1.55    | 3.45    | ~0.86    | l=0.22, r=0.03, 0.24kg |

Object positions are relative to table center (1.35, 3.45):
- Mug: offset_x=-0.20, offset_y=-0.15 (NW, south-shifted for reachability)
- Plate: offset_x=+0.25, offset_y=0.0 (NE)
- Apple: on plate, offset_x=+0.07 from plate center
- Banana: on plate, offset_x=-0.05 from plate center

### Cameras

| Name       | Position           | Target          |
|------------|--------------------|-----------------|
| top        | (0.0, 0.0, 7.0)   | (0.0, 3.45, 0.0)|
| front      | (0.0, -2.0, 1.5)  | (0.0, 3.45, 0.8)|
| isometric  | (-3.5, -2.0, 3.5) | (0.0, 3.45, 0.8)|

### Lighting

- Dome light: 800 intensity
- 4 ceiling rect lights: 3000 intensity each, at Z=2.75

## 2. Robot Configuration

- Model: TIAGo Dual (heavy variant), `tiago_dual_functional.usd`
- Start pose: (0.0, 0.0, 0.08) with yaw=90 deg (facing north)
- Articulation: 85 DOFs (4 wheels, 60 rollers, torso, 2x7 arm joints, 2x2 gripper, 2 head)
- Drive: mecanum omnidirectional wheels
- Gripper: right hand, parallel jaw

### Key Joint Limits

| Joint             | Min     | Max    |
|-------------------|---------|--------|
| torso_lift_joint  | 0.00    | 0.35   |
| arm_right_1_joint | -1.178  | 1.571  |
| arm_right_4_joint | -0.393  | 2.356  |
| gripper_right_*   | 0.00    | 0.045  |

### Arm Poses

| Pose           | J1   | J2  | J3  | J4    | J5    | J6  | J7  |
|----------------|------|-----|-----|-------|-------|-----|-----|
| pre_grasp_top  | 1.50 | 0.0 | 0.0 | -0.35 | -1.57 | 0.0 | 0.0 |
| After lift     | 1.50 | 0.0 | 0.0 |  0.30 | -1.57 | 0.0 | 0.0 |
| After place    | 1.50 | 0.0 | 0.0 | -0.35 | -1.57 | 0.0 | 0.0 |

### Gripper Values

| State  | Opening (m) |
|--------|-------------|
| Open   | 0.045       |
| Grasp  | 0.020       |
| Closed | 0.000       |

## 3. Task Sequence

### Overview

```
T1: Navigate to mug approach position
T2: Pick mug (top grasp, lift 20cm)
T3: Carry mug 20cm east (relative)
T4: Place mug on table (extend arm down)
T5: Return to start
```

### T1: navigate_to -- Drive to Mug

- Target: (1.15, 2.50) -- 0.80m south of mug at (1.15, 3.30)
- Tolerance: 0.25 m
- Speed: 0.4 m/s
- Timeout: 50 s
- Result: ~5.4s, 653 steps

The robot starts at (0,0) facing north (yaw=90). Drives northeast to position south of the table. The arm reach is ~0.65m north from base, so from Y=2.50 the tool reaches Y~3.15 (inside table).

### T2: pick_object -- Grasp and Lift Mug

- Object: `/World/Kitchen/Objects/Mug`
- Grasp mode: top-down
- Lift height: 0.20 m
- Timeout: 90 s
- Result: ~22.6s, 2708 steps

Substates:
1. **extend_arm**: Set pre_grasp_top pose (J4=-0.35), torso to approach height
2. **rotate_to_target**: Orient robot front toward mug (yaw correction)
3. **drive_to_mug**: Closed-loop drive until tool is over mug (dx_r, dy_r alignment)
4. **settle_at_table**: Stop and wait 240 steps
5. **approach_overhead**: Fine XY alignment of tool over mug (top_xy_tol=0.02m)
6. **descend_vertical**: Lower torso until tool is at mug height + clearance
7. **close_gripper**: Close to GRIPPER_GRASP_MUG (0.02)
8. **verify_grasp**: Check gripper is holding (hold_ok)
9. **lift_mug**: Torso to 0.35 + J4 from -0.35 to 0.30 over 600 steps (retracts arm upward)

Success criteria: mug Z delta >= 0.015m, tool Z delta >= 0.20m

### T3: carry_to -- Carry 20cm East

- Destination: [0.20, 0.0] relative to current position
- Tolerance: 0.10 m
- Speed: 0.3 m/s (global default)
- Timeout: 45 s
- Result: ~0.3s, 39 steps

Uses relative mode: reads current base position, adds offset. Robot translates east without rotation. Wheels always stopped on completion (both success and failure).

### T4: place_object -- Place Mug on Table

- Release height: 0.05 m (unused -- arm extension controls descent)
- Timeout: 15 s
- Result: ~15.0s, 1800 steps

**Placement method: arm extension (not torso descent)**

The arm J4 extends from 0.30 (retracted/elbow bent up) to -0.35 (extended/elbow straight) over 600 steps (5 seconds). Torso stays at 0.35 (max height). This lowers only the forearm+gripper+mug, keeping the elbow above the table.

Release trigger: mug Z <= table_top_z + 0.02 (0.82m), or arm fully extended.

Safety checks:
- If mug Z < table_top_z - 0.05 (0.75m): abort, open gripper, report failure
- XY bounds check: mug must be within table bounds (X [0.90, 1.80], Y [3.00, 3.90])
- Z check: mug Z must be <= table_top_z + 0.15 (0.95m)

### T5: navigate_to -- Return to Start

- Target: (0.0, 0.0)
- Tolerance: 1.50 m (best-effort)
- Speed: 0.4 m/s
- Timeout: 60 s
- Result: ~2.5s, 297 steps

## 4. Safety Boundaries

### Table South Boundary

`TABLE_SOUTH_BOUNDARY_Y = 2.75`

Both `navigate_to` and `carry_to` clamp northward velocity to zero when the robot base Y >= 2.75. This prevents the robot from driving into the table zone (south edge at Y=3.05). The boundary is 0.30m south of the table edge.

### Furniture Zones (waypoint navigation)

| Zone         | Center X | Center Y | Half-W | Half-D |
|--------------|----------|----------|--------|--------|
| Fridge       | -1.35    | 3.45     | 0.50   | 0.50   |
| Sink cabinet |  0.45    | 3.60     | 0.50   | 0.40   |
| Table        |  1.35    | 3.55     | 0.50   | 0.50   |

Navigation margin: 0.35m south of zone for waypoint insertion.

### Wheel Stop Policy

Wheels are always zeroed at the end of every `navigate_to` and `carry_to` task, regardless of success or failure. Wheels are also explicitly zeroed at the start of `place_object`.

## 5. Physics Parameters

| Parameter          | Value          |
|--------------------|----------------|
| Physics DT         | 1/120 s        |
| Rendering DT       | 1/60 s         |
| Solver             | TGS            |
| Position iterations| 64             |
| Velocity iterations| 4              |
| Gravity            | (0, 0, -9.81)  |
| Stabilization      | True           |

## 6. Verified Results (2026-03-15)

| Task | Type        | Success | Sim Time | Steps |
|------|-------------|---------|----------|-------|
| T1   | navigate_to | True    | 5.44s    | 653   |
| T2   | pick_object | True    | 22.57s   | 2708  |
| T3   | carry_to    | True    | 0.33s    | 39    |
| T4   | place_object| True    | 14.99s   | 1800  |
| T5   | navigate_to | True    | 2.48s    | 297   |

Total wall time: ~170s. Verdict: **PASS (task config)**.

Video recordings: 3 cameras (top, front, isometric) in episode directory.

## 7. Config Files

- Scene config: `scenes/kitchen_fixed/kitchen_fixed_config.yaml`
- Scene builder: `scenes/kitchen_fixed/kitchen_fixed_builder.py`
- Task config: `config/tasks/fixed_mug_rearrange.json`
- Test script: `scripts/test_robot_bench.py`
- Run script: `scripts/run_task_config.ps1`

## 8. How to Run

```powershell
# Without video (fast iteration)
.\scripts\run_task_config.ps1 -Config config/tasks/fixed_mug_rearrange.json -NoVideo

# With video recording
.\scripts\run_task_config.ps1 -Config config/tasks/fixed_mug_rearrange.json

# With custom duration
.\scripts\run_task_config.ps1 -Config config/tasks/fixed_mug_rearrange.json -Duration 300
```

## 9. Regression Test

Run `scripts/test_mug_rearrange_regression.py` to validate that all config parameters match the documented values without running the simulation.

```powershell
python scripts/test_mug_rearrange_regression.py
```
