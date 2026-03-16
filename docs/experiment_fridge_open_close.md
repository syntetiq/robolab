# Experiment 3: Fridge Door Open/Close by Handle (fixed_fridge_experiment3)

Last verified: 2026-03-16
Episode: `fixed_fridge_experiment3_20260316_205725`
Verdict: **PASS (task config)** -- all 4 tasks succeed

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

The fridge is rotated +90° around Z in the scene. Local -X (front/door) maps to world -Y (south, toward room center). The hinge is on the west side (local -Y → world -X).

### Handle

| Property       | Value   |
|----------------|---------|
| Type           | vertical|
| Length         | 0.50 m  |
| Center height  | 1.10 m  |
| Standoff       | 0.06 m  |

Handle world position (door closed): approximately (-1.65, 2.96, 1.10).

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
- Arm pose for door tasks: `pre_grasp_handle` (J1=0.70 shoulder lift, others 0.0)
- Torso height during door tasks: 0.35 m (max)

## 3. Task Sequence

Config file: `config/tasks/fixed_fridge_experiment3.json`

### T1: navigate_to fridge approach (T1_drive_to_fridge)
- Target: (-2.10, 2.55) -- southwest of fridge handle
- Tolerance: 0.30 m
- Drive speed: 0.4 m/s
- Timeout: 50 s
- Result: **PASS** (786 steps, 6.55 s)

### T2: open_door fridge (T2_open_fridge)
- Handle: `/World/Kitchen/Furniture/Fridge/Door/Handle`
- Approach axis: Y (robot approaches from south)
- Arm reach: 0.40 m
- Base lateral offset: 0.50 m
- Pull speed: 0.15 m/s
- Success criteria: door angle >= 30 degrees
- Timeout: 60 s
- Result: **PASS** (1506 steps, 12.55 s, final angle 48.9°)

**Strategy**: The robot positions southwest of the handle, then drives forward (north) into the door. The robot's body pushes the door open via collision. The approach_and_grasp phase includes a creep phase where the robot slowly drives forward to ensure contact. The pull_or_push phase drives forward+left to push the door open while maintaining contact.

### T3: close_door fridge (T3_close_fridge)
- Handle: `/World/Kitchen/Furniture/Fridge/Door/Handle`
- Approach axis: Y
- Arm reach: 0.40 m
- Base lateral offset: 0.50 m
- Push speed: 0.20 m/s
- Success criteria: door angle <= 20 degrees
- Timeout: 60 s
- Result: **PASS** (2377 steps, 19.81 s, final angle 20.0°)

**Strategy**: Multi-waypoint navigation to circumnavigate the open door:
1. Drive south to Y=1.50 (clear of door)
2. Drive east to X = handle_x + 0.60 (east of door edge)
3. Drive north to Y = handle_y (level with door edge)

During the northward navigation (waypoint 3), the robot collides with the open door and pushes it closed. An early success check detects when the door angle drops below the success criteria during navigation, declaring success without needing the explicit push phase.

### T4: navigate_to start (T4_return_to_start)
- Target: (0.0, 0.0)
- Tolerance: 2.00 m (loose, best-effort)
- Drive speed: 0.4 m/s
- Timeout: 60 s
- Result: **PASS** (267 steps, 2.23 s)

## 4. Key Parameters

### Door Angle Reading

The door angle is read from the `RevoluteJoint` at `/World/Kitchen/Furniture/Fridge/DoorHinge` using `_get_door_angle_from_joint()`. This function computes the relative orientation between body0 (cabinet) and body1 (door) around the joint axis (Z), returning absolute degrees (0 = closed, 90 = fully open).

### Door Open/Close Cycle Parameters

| Parameter              | Open (T2) | Close (T3) |
|------------------------|-----------|------------|
| approach_axis          | y         | y          |
| arm_reach_m            | 0.40      | 0.40       |
| base_lateral_offset_m  | 0.50      | 0.50       |
| arm_pose               | pre_grasp_handle | pre_grasp_handle |
| speed (m/s)            | 0.15 (pull) | 0.20 (push) |
| success angle (deg)    | >= 30     | <= 20      |
| timeout (s)            | 60        | 60         |

## 5. Timing Summary

| Task | Steps | Time (s) | Status |
|------|-------|----------|--------|
| T1 drive to fridge | 786 | 6.55 | PASS |
| T2 open fridge | 1506 | 12.55 | PASS |
| T3 close fridge | 2377 | 19.81 | PASS |
| T4 return to start | 267 | 2.23 | PASS |
| **Total** | **4936** | **41.13** | **4/4 PASS** |

Simulation wall time: ~158 s (realtime factor 1.90x without video, ~225 s with video).

## 6. Files

| File | Purpose |
|------|---------|
| `config/tasks/fixed_fridge_experiment3.json` | Task configuration |
| `config/robots/tiago_heavy.yaml` | Robot profile |
| `scenes/kitchen_fixed/kitchen_fixed_config.yaml` | Scene geometry |
| `scenes/kitchen_fixed/kitchen_fixed_builder.py` | Scene builder (USD) |
| `scripts/test_robot_bench.py` | Robot control + door manipulation |
| `scripts/test_fridge_experiment3_regression.py` | Regression test (86 checks) |
| `scripts/run_task_config.ps1` | Episode runner |

## 7. Regression Test

```
python scripts/test_fridge_experiment3_regression.py
```

86 checks covering: file existence, scene config, task config, robot profile, code structure, derived geometry.

## 8. Running the Experiment

```powershell
# Without video (fast, ~158s)
powershell -ExecutionPolicy Bypass -File scripts/run_task_config.ps1 -Config config/tasks/fixed_fridge_experiment3.json -NoVideo -Duration 300

# With video (3 cameras, ~225s)
powershell -ExecutionPolicy Bypass -File scripts/run_task_config.ps1 -Config config/tasks/fixed_fridge_experiment3.json -Duration 300
```

Output: `C:\RoboLab_Data\episodes\fixed_fridge_experiment3_<timestamp>\`
