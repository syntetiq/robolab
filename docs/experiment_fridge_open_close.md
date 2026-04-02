# Experiment 3: Fridge Door Open/Close by Handle (fixed_fridge_experiment3)

Last verified: 2026-03-17
Episode: `fixed_fridge_experiment3_20260317`
Verdict: **PASS (all 4 tasks)** -- proper handle grasp with left arm, gripper-to-handle distance < 0.10m

## 1. Scene Setup

### Room

- Size: 8.0 x 8.0 m, wall height 2.8 m
- Wall thickness: 0.15 m
- World origin: center of room (0, 0, 0)
- North wall inner face: Y = 3.85

### Fridge

| Property       | Value   |
|----------------|---------|
| Center X       | -1.35   |
| Center Y       | 3.45    |
| Width          | 0.80 m  |
| Depth          | 0.80 m  |
| Height         | 2.00 m  |
| Door thickness | 0.03 m  |
| Door mass      | 8.0 kg  |
| Max open angle | 90 deg  |

The fridge is rotated +90° around Z in the scene. Local -X (front/door) maps to world -Y (south, toward room center). The hinge is on the east side at world (-0.95, 3.05).

### Handle

| Property       | Value   |
|----------------|---------|
| Type           | vertical|
| Length         | 0.50 m  |
| Center height  | 1.10 m  |
| Standoff       | 0.06 m  |

Handle world position (door closed): approximately (-1.65, 2.96, 1.10).
Handle world position (door 90° open): approximately (-1.04, 3.75, 1.10).

### Door Arc Geometry

The handle traces an arc around the hinge at (-0.95, 3.05):
- **Opening**: handle moves north-east (from (-1.65, 2.96) toward (-1.04, 3.75))
- **Closing**: handle moves south-west (reverse)
- The robot pulls/pushes tangent to this arc using `hinge_world_xy` for arc-following

### USD Paths

- Fridge base: `/World/Kitchen/Furniture/Fridge`
- Door: `/World/Kitchen/Furniture/Fridge/Door`
- Handle: `/World/Kitchen/Furniture/Fridge/Door/Handle`
- Hinge joint: `/World/Kitchen/Furniture/Fridge/DoorHinge` (RevoluteJoint, axis Z, limits [-90, 0])

## 2. Robot Configuration

- Model: TIAGo Dual (heavy), profile: `config/robots/tiago_heavy.yaml`
- Start pose: (0.0, 0.0) facing north (yaw=90)
- Spawn Z: 0.08 m
- Gripper length: 0.10 m
- **Arm used**: LEFT arm (extends north-west, better reach for handle)
- Arm pose for door tasks: `handle_reach_left` (L: [1.35, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0] -- J1=1.35 forward, R: tucked home)
- Torso height during door tasks: 0.35 m (max)
- Left gripper joints: `gripper_left_left_finger_joint`, `gripper_left_right_finger_joint`

## 3. Task Sequence

Config file: `config/tasks/fixed_fridge_experiment3.json`

### T1: navigate_to fridge approach (T1_drive_to_fridge)
- Target: (-1.25, 2.10) -- south of fridge handle
- Tolerance: 0.30 m
- Drive speed: 0.4 m/s
- Timeout: 50 s
- Result: **PASS**

### T2: open_door fridge (T2_open_fridge)
- Handle: `/World/Kitchen/Furniture/Fridge/Door/Handle`
- Approach axis: Y (robot approaches from south)
- Use arm: LEFT
- Arm reach: 0.75 m
- Base lateral offset: 0.34 m (robot shifts east so left arm reaches handle)
- Pull speed: 0.12 m/s
- Hinge: (-0.95, 3.05) for arc-following
- Success criteria: door angle >= 30 degrees
- Timeout: 80 s
- Result: **PASS** (2739 steps, final angle 30.2°)

**Strategy**: The robot positions south of the handle with the left arm extended forward (J1=1.35). During approach_and_grasp, the robot uses closed-loop X-only creep to align the gripper with the handle bar in the east-west direction, opens the gripper, then closes it around the handle. The gripper achieves < 0.10m distance to the handle center. In pull_or_push, the robot drives along the tangent to the door arc (computed from hinge position), pulling the handle to open the door. The door angle starts increasing while the robot base is still well south of the door edge, confirming gripper-based pulling (not body push).

### T3: close_door fridge (T3_close_fridge)
- Handle: `/World/Kitchen/Furniture/Fridge/Door/Handle`
- Approach axis: Y
- Use arm: LEFT
- Arm reach: 0.75 m
- Base lateral offset: 0.34 m
- Push speed: 0.15 m/s
- Hinge: (-0.95, 3.05) for arc-following
- Success criteria: door angle <= 20 degrees
- Timeout: 80 s
- Result: **PASS** (2691 steps, final angle 6.0°)

**Strategy**: Multi-waypoint navigation to circumnavigate the open door:
1. Drive south to Y = hinge_y - 0.80 (clear of door swing)
2. Drive east to X = hinge_x + 0.30 (east of hinge)
3. Drive north to Y = hinge_y + 0.20 (north of hinge, east side of door)

From the east approach position, the robot creeps west (left) to bring the left gripper toward the handle. The gripper grasps the handle and the robot pushes along the door arc to close the door.

### T4: navigate_to start (T4_return_to_start)
- Target: (0.0, 0.0)
- Tolerance: 2.00 m (loose, best-effort)
- Drive speed: 0.4 m/s
- Timeout: 60 s
- Result: **PASS**

## 4. Key Parameters

### Door Angle Reading

The door angle is read from the `RevoluteJoint` at `/World/Kitchen/Furniture/Fridge/DoorHinge` using `_get_door_angle_from_joint()`. This function computes the relative orientation between body0 (cabinet) and body1 (door) around the joint axis (Z), returning absolute degrees (0 = closed, 90 = fully open).

### Arc-Following Pull/Push

During pull_or_push, the robot computes the tangent direction to the door arc at the current handle position:
- Radius vector: (handle_x - hinge_x, handle_y - hinge_y)
- Tangent (opening): perpendicular to radius, rotated 90° CCW
- Tangent (closing): opposite direction
- World velocity is converted to robot-local frame using the robot's yaw

### Door Open/Close Cycle Parameters

| Parameter              | Open (T2) | Close (T3) |
|------------------------|-----------|------------|
| approach_axis          | y         | y          |
| use_arm                | left      | left       |
| arm_reach_m            | 0.75      | 0.75       |
| base_lateral_offset_m  | 0.34      | 0.34       |
| arm_pose               | handle_reach_left | handle_reach_left |
| speed (m/s)            | 0.12 (pull) | 0.15 (push) |
| success angle (deg)    | >= 30     | <= 20      |
| timeout (s)            | 80        | 80         |
| hinge_world_xy         | (-0.95, 3.05) | (-0.95, 3.05) |

## 5. Timing Summary

| Task | Steps | Status |
|------|-------|--------|
| T1 drive to fridge | 561 | PASS |
| T2 open fridge | 2739 | PASS |
| T3 close fridge | 2691 | PASS |
| T4 return to start | 278 | PASS |
| **Total** | **6269** | **4/4 PASS** |

## 6. Files

| File | Purpose |
|------|---------|
| `config/tasks/fixed_fridge_experiment3.json` | Task configuration |
| `config/robots/tiago_heavy.yaml` | Robot profile |
| `scenes/kitchen_fixed/kitchen_fixed_config.yaml` | Scene geometry |
| `scenes/kitchen_fixed/kitchen_fixed_builder.py` | Scene builder (USD) |
| `scripts/test_robot_bench.py` | Robot control + door manipulation |
| `scripts/test_fridge_experiment3_regression.py` | Regression test (92 checks) |
| `scripts/run_task_config.ps1` | Episode runner |

## 7. Regression Test

```
python scripts/test_fridge_experiment3_regression.py
```

92 checks covering: file existence, scene config, task config, robot profile, code structure (left arm support, gripper joints, hinge coordinates, arm pose values), derived geometry.

## 8. Running the Experiment

```powershell
# Without video (fast)
powershell -ExecutionPolicy Bypass -File scripts/run_task_config.ps1 -Config config/tasks/fixed_fridge_experiment3.json -NoVideo

# With video (3 cameras)
powershell -ExecutionPolicy Bypass -File scripts/run_task_config.ps1 -Config config/tasks/fixed_fridge_experiment3.json
```

Output: `C:\RoboLab_Data\episodes\fixed_fridge_experiment3_<timestamp>\`
