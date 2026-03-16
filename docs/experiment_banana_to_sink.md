# Experiment 2: Banana to Sink (fixed_banana_to_sink)

Last verified: 2026-03-16
Episode: `fixed_banana_to_sink_20260316_084807`
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
| Sink cabinet |  0.45    | 3.45     | 0.80  | 0.80  | 0.90   |
| **Table**    |  **1.35**| **3.45** | **0.80**|**0.80**|**0.80**|

Sink basin: depth 0.18 m, margin 0.06 m, inner size 0.68 x 0.68 m, top Z = 0.90 m.

### Objects on Table

| Object | World X | World Y | World Z  | Size                   |
|--------|---------|---------|----------|------------------------|
| Plate  | 1.60    | 3.45    | 0.80     | r=0.15, h=0.025        |
| Banana | 1.55    | 3.45    | 0.855    | r=0.030, len=0.22, 0.05 kg |
| Apple  | 1.67    | 3.45    | 0.875    | r=0.05                 |
| Mug    | 1.15    | 3.30    | 0.80     | r=0.04, h=0.10         |

Banana is on the plate (plate center + offset_x=-0.05), lying flat (rotate_xyz=90,0,0). Banana material has friction_static=1.0, friction_dynamic=0.8.

## 2. Robot Configuration

- Model: TIAGo Dual (heavy), profile: `config/robots/tiago_heavy.yaml`
- Start pose: (0.0, 0.0) facing north (yaw=90)
- Spawn Z: 0.08 m
- Gripper length: 0.10 m

## 3. Task Sequence

Config file: `config/tasks/fixed_banana_to_sink.json`

### T1: navigate_to banana approach (T1_drive_to_banana)
- Target: (1.55, 2.50) -- south of banana
- Tolerance: 0.25 m
- Timeout: 50 s
- Result: **PASS** (703 steps, 5.86 s)

### T2: pick_object banana (T2_pick_banana)
- Object: `/World/Kitchen/Objects/Banana`
- Grasp mode: top
- Lift height: 0.20 m
- Approach arm retracted: true (gripper stays high during drive)
- Lift interpolation: 1200 steps (2x normal, smooth lift)
- Gripper: close=0.015, final=0.010, hold_threshold=0.005
- Top descend clearance: 0.04 m (larger than default 0.015)
- Timeout: 90 s
- Result: **PASS** (2660 steps, 22.17 s)

### T3: carry_to sink area (T3_carry_to_sink)
- Destination: (0.45, 2.80) -- south of sink cabinet, absolute
- Drive speed: 0.15 m/s (slow, prevents banana drop)
- Final heading: 180 deg (face west, so right arm extends north over sink)
- Object tracking: `/World/Kitchen/Objects/Banana`
- Tolerance: 0.20 m
- Timeout: 40 s
- Result: **PASS** (3120 steps, 26.0 s, includes rotation)

### T4: place_object in sink (T4_place_in_sink)
- Per-task placement overrides:
  - placement_top_z: 0.90 (sink top, not table 0.80)
  - placement_cx: 0.45, placement_cy: 3.10
  - placement_half_w: 0.50, placement_half_d: 0.50
  - placement_margin: 0.20 (wide bounds for drop placement)
  - placement_abort_z_offset: -0.30
  - placement_release_z_offset: 0.10
  - placement_success_z_offset: 0.30
- Timeout: 10 s
- Result: **PASS** (1200 steps, 9.99 s)

### T5: navigate_to start (T5_return_to_start)
- Target: (0.0, 0.0)
- Tolerance: 1.50 m (loose, best-effort)
- Timeout: 60 s
- Result: **PASS** (454 steps, 3.78 s)

## 4. Key Parameters (Banana-Specific)

### Grasp Tuning
- `gripper_close_value`: 0.015 (tighter than mug's 0.018)
- `gripper_final_close_value`: 0.010 (prevents over-squeeze)
- `gripper_hold_threshold`: 0.005 (lower than mug's 0.01)
- `top_descend_clearance`: 0.04 (larger than mug's 0.015, avoids pushing banana)
- `approach_arm_retracted`: true (keeps gripper high during drive-to-object)
- `lift_interpolation_steps_override`: 1200 (2x slower than default 600)
- `lift_timeout_steps`: 1500

### Control Timing (Optimized)
- `grasp_settle_steps`: 120 (1.0s)
- `extend_arm_steps`: 300 (2.5s)
- `settle_at_table_steps`: 60 (0.5s)
- `approach_timeout_steps`: 600 (5.0s)
- `place_descent_steps`: 600 (5.0s)

### Placement Overrides (Sink vs Table)
The `place_object` handler supports per-task placement parameters that override the global `cfg.table_*` values. Wide bounds are used for the sink since the banana is dropped from above rather than precisely placed.

### Carry Strategy
The robot carries the banana west past the table to (0.45, 2.80), then rotates to face west (180 deg). This positions the right arm extending north over the sink cabinet. The slow carry speed (0.15 m/s) prevents the banana from slipping out of the gripper during lateral movement.

### Physics Adjustments
- Banana mass: 0.05 kg (reduced from 0.24 kg for reliable gripper friction)
- Banana material friction: static=1.0, dynamic=0.8 (added for grip)
- Banana orientation: rotate_xyz=(90, 0, 0) -- lies flat on plate instead of standing upright

## 5. Safety Boundaries

- TABLE_SOUTH_BOUNDARY_Y = 2.75 (same as experiment-1)
- Carry_to bypasses boundary when target is north of boundary (for sink approach)
- Furniture zones: fridge, sink_cabinet, table (for waypoint routing)
- NAV_MARGIN = 0.35 m

## 6. Code Changes from Experiment 1

1. **Per-task placement overrides** in `place_object` handler: reads `placement_top_z`, `placement_cx`, etc. from task dict, falling back to `cfg` globals.
2. **`approach_arm_retracted`** parameter: keeps J4 at retracted position during `extend_arm` and `drive_to_mug`, lowering to extended in `settle_at_table`. Prevents gripper from sweeping table objects.
3. **`lift_with_torso_only`** parameter: option to skip J4 retraction during lift (not used in final config).
4. **`lift_interpolation_steps_override`** parameter: allows per-task slower lift speed.
5. **`gripper_final_close_value`** parameter: controls the second-stage gripper close (step 45), defaults to GRIPPER_CLOSED.
6. **`carry_to` final_heading_deg**: rotates robot to specified heading after reaching destination, while maintaining gripper hold.
7. **`carry_to` object_usd_path**: tracks carried object position during carry for debugging.
8. **`carry_to` TABLE_SOUTH_BOUNDARY_Y bypass**: allows northward carry when target is north of the boundary.
9. **`place_object` place_heading_deg**: optional rotation before arm descent (available but not used in final config).
10. **Banana orientation fix**: rotate_xyz=(90, 0, 0) in scene builder so cylinder lies flat on plate.

## 7. How to Run

```powershell
# No video (fast iteration)
.\scripts\run_task_config.ps1 -Config config/tasks/fixed_banana_to_sink.json -NoVideo

# With video
.\scripts\run_task_config.ps1 -Config config/tasks/fixed_banana_to_sink.json

# Regression test (no Isaac Sim needed)
python scripts/test_banana_to_sink_regression.py
```

## 8. Verified Results

| Task | Type        | Success | Steps | Sim Time |
|------|-------------|---------|-------|----------|
| T1   | navigate_to | PASS    | 703   | 5.86 s   |
| T2   | pick_object | PASS    | 2660  | 22.17 s  |
| T3   | carry_to    | PASS    | 3120  | 26.00 s  |
| T4   | place_object| PASS    | 1200  | 9.99 s   |
| T5   | navigate_to | PASS    | 454   | 3.78 s   |

Total simulation: 8137 steps, ~67.8 s sim time, ~188 s wall time (no video), ~350 s (with video).
