# TIAGo Simulation Audit — Coordinate Systems, Base Stability, Factory Specs

**Date:** 2026-03-12  
**Scope:** Full audit of coordinate frames, base mass/tilt, joint limits, drive gains, and velocity constraints. Comparison of simulation parameters against PAL Robotics official specifications.

---

## 1. Coordinate Systems

### 1.1 Frames in Use

| Frame | Owner | Origin | Notes |
|-------|-------|--------|-------|
| `map` / Isaac world | Isaac Sim | (0, 0, 0) | Z-up, right-handed. All world positions are in this frame. |
| `/World/Tiago` (XForm) | Isaac Sim | (0.8, 0.0, 0.08) | Visual root of the robot. Set at startup. |
| `base_footprint` | Articulation root | (0.8, 0.0, 0.08) | PhysX articulation root. Should coincide with XForm root. `fixedBase=True` pins it. |
| `base_link` | URDF/USD | offset from `base_footprint` | Rigidly attached to `base_footprint`. MoveIt planning frame. |
| `arm_tool_link` | URDF/USD | end of arm chain | End-effector frame. MoveIt IK target frame. |
| `gripper_center_local` | Computed | midpoint of finger links | Computed at runtime as average of left/right finger XForm positions. |

### 1.2 Frame Transformations

- **Isaac Sim → MoveIt:** The bridge publishes `/joint_states` via `ros2_fjt_proxy`. MoveIt uses these to compute FK internally. The bridge's `--frame-id base_footprint` tells MoveIt to plan in the robot's local frame.
- **MoveIt → Isaac Sim:** IK solutions from MoveIt are joint-space targets. The bridge clamps them via `clamp_joints()` and sends them as FJT goals through the proxy. The collector applies them as PD drive targets.
- **Object positions** are reported by Isaac Sim in world frame (`map`). The bridge converts them to `base_footprint`-local by subtracting the robot's world position.

### 1.3 Known Frame Issues

**`_FK_COMP` empirical offset:**
```
_FK_COMP_X = +0.12   (push IK target 12cm forward)
_FK_COMP_Y = -0.02   (push IK target 2cm right)
_FK_COMP_Z = -0.28   (push IK target 28cm down)
```
This offset compensates for the mismatch between where MoveIt thinks the gripper is and where Isaac Sim PhysX actually places it. The Z component (-0.28m) is the largest and directly correlates with the robot's backward tilt (see §2). When the torso lifts and the robot tilts backward, the gripper ends up higher and further back than MoveIt expects.

**Root cause:** The tilt changes the effective `base_footprint` orientation, but MoveIt still plans assuming a level base. The `_FK_COMP` is a static hack that only works for one specific torso height and tilt angle.

**Joint axis inconsistency:** The `tiago_right_arm.urdf` uses Z-axis for revolute joints (ROS convention), while Isaac Sim USD may use X-axis depending on the import. The `tiago_move_group_working.yaml` and the URDF must agree on axis definitions. Currently they do, but this is fragile if the URDF is regenerated.

**Joint naming:** Isaac Sim USD uses `arm_right_N_joint`, MoveIt uses `arm_N_joint`. An alias map in `data_collector_tiago.py` handles this, but it's a runtime mapping that can silently fail if USD joint names change.

---

## 2. Base Stability and Tilt

### 2.1 Observed Problem

Video analysis (`camera_2_external.mp4`) shows the robot's upper body tilting backward by **10–15 degrees** when the torso lifts. The base wheels remain in contact with the ground — this is not slippage but a center-of-mass shift.

### 2.2 Current Configuration

- `physxArticulation:fixedBase = True` — pins the articulation root.
- Robot spawn position: `(0.8, 0.0, 0.08)` with identity orientation.
- Base drift monitor runs every 300 frames; tilt monitor reports pitch/roll > 0.5°.
- Self-collisions disabled on the articulation.

### 2.3 Analysis

`fixedBase=True` fixes the **root joint** (the first link in the articulation chain). If the root link is `base_footprint` (a virtual link with zero mass), the actual `base_link` and everything above it can still rotate relative to the fixed root through compliant joints or insufficiently stiff connections.

The PAL TIAGo real robot weighs ~70 kg with a low center of mass in the base. The base alone is ~45 kg. In simulation, if the base link mass is underspecified or the torso column joint is too compliant, the upper body will tilt when the arm extends.

### 2.4 Fix Strategy

1. **Verify base_link mass in USD** — should be ≥ 28 kg (PAL spec for mobile base platform).
2. **Increase torso column stiffness** — the `torso_lift_joint` drive already has high gains (2000, 400, 20000) but the prismatic joint connecting base to torso column may need additional stiffness.
3. **Check for intermediate revolute joints** between `base_footprint` and `torso_lift_link` that might allow rotation.
4. **After fix: recalibrate `_FK_COMP`** — with a stable base, the offset should be much smaller or zero.

---

## 3. Joint Limits — PAL Factory vs Simulation

### 3.1 Comparison Table

| Joint | PAL Official (rad) | Collector Default (rad) | Bridge (rad) | Status |
|-------|-------------------|------------------------|--------------|--------|
| `torso_lift_joint` | 0.0 – 0.35 m | (0.0, 0.35) | (0.0, 0.35) | OK |
| `arm_1_joint` | 0.07 – 2.749 | (-1.178, 1.571) | (-1.18, 1.57) | **WRONG** — PAL range is 0.07–2.749, ours allows negative values |
| `arm_2_joint` | -1.50 – 1.02 | (-1.178, 1.571) | (-1.18, 1.57) | **WRONG** — PAL upper limit is 1.02, ours is 1.571 |
| `arm_3_joint` | -3.46 – 1.57 | (-0.785, 3.927) | (-0.785, 3.927) | **WRONG** — PAL range is -3.46–1.57, ours has inverted/wrong upper limit |
| `arm_4_joint` | -0.32 – 2.27 | (-0.393, 2.356) | (-0.393, 2.356) | Close but slightly wider than PAL |
| `arm_5_joint` | -2.07 – 2.07 | (-2.094, 2.094) | (-2.094, 2.094) | OK (within rounding) |
| `arm_6_joint` | -1.39 – 1.39 | (-1.414, 1.414) | **(0.0, 1.414)** | Bridge restricted to positive-only due to observed sim behavior |
| `arm_7_joint` | -2.07 – 2.07 | (-2.094, 2.094) | (-2.094, 2.094) | OK (within rounding) |

**Note:** The collector reads limits from USD at runtime and may override defaults. The bridge uses hardcoded limits. These must be synchronized.

### 3.2 USD Model Limits (Actual Physical Constraints in Simulation)

The USD model (`tiago_dual_functional_light.usd`) has its own joint limits that are **tighter** than the PAL URDF:

| Joint | USD Limit (rad) | PAL URDF (rad) | Final (intersection) |
|-------|----------------|----------------|---------------------|
| `arm_1_joint` | (-1.178, 1.571) | (0.0, 2.68) | **(0.0, 1.571)** |
| `arm_2_joint` | (-1.178, 1.571) | (-1.50, 1.02) | **(-1.178, 1.02)** |
| `arm_3_joint` | (-0.785, 3.927) | (-3.46, 1.57) | **(-0.785, 1.57)** |

**Critical finding:** The USD model's `arm_3_joint` can only flex to -0.785 rad (-45°), while the real PAL robot can reach -3.46 rad. This severely limits the simulation workspace. All predefined poses must respect this constraint.

### 3.3 Resolution

All joint limits in the bridge, MoveIt YAML, and predefined poses have been updated to use the **intersection** of PAL URDF and USD model limits. The collector now uses `max(default_lo, usd_lo)` and `min(default_hi, usd_hi)` instead of expanding ranges.

---

## 4. Drive Gains — PAL Factory vs Simulation

### 4.1 Current Simulation Gains (acceleration mode)

| Joint | Stiffness (1/s²) | Damping (1/s) | Max Force (N·m) |
|-------|------------------|---------------|-----------------|
| `torso_lift_joint` | 2000 | 400 | 20000 |
| `arm_1_joint` | 1500 | 300 | 5000 |
| `arm_2_joint` | 1500 | 300 | 5000 |
| `arm_3_joint` | 1200 | 240 | 3000 |
| `arm_4_joint` | 1200 | 240 | 3000 |
| `arm_5_joint` | 1200 | 240 | 2000 |
| `arm_6_joint` | 1200 | 240 | 2000 |
| `arm_7_joint` | 1200 | 240 | 2000 |

### 4.2 PAL Factory Characteristics

PAL TIAGo uses Series Elastic Actuators (SEA) with high gear ratios:
- **Shoulder/elbow (joints 1–4):** ~100:1 reduction, ~40 N·m continuous torque, ~80 N·m peak.
- **Wrist (joints 5–7):** ~160:1 reduction, ~8 N·m continuous torque, ~15 N·m peak. These are much weaker than shoulder joints.

### 4.3 Issues

Our simulation uses similar gain magnitudes for wrist and elbow joints. In reality, wrist joints are 3–5× weaker. This means:
- The simulation wrist can track aggressive trajectories that the real robot cannot.
- When MoveIt plans with real-robot velocity limits, the sim wrist overshoots because it's too powerful.
- Conversely, if MoveIt plans without velocity limits, the sim wrist can reach positions the real wrist would struggle with.

**Recommendation:** Reduce wrist gains to ~40% of elbow gains to better match the real torque hierarchy.

---

## 5. Velocity Limits

### 5.1 PAL Specifications

| Joint | Max Velocity (rad/s) |
|-------|---------------------|
| `torso_lift_joint` | 0.07 m/s |
| `arm_1_joint` | 2.35 |
| `arm_2_joint` | 2.35 |
| `arm_3_joint` | 2.35 |
| `arm_4_joint` | 2.35 |
| `arm_5_joint` | 1.76 |
| `arm_6_joint` | 1.76 |
| `arm_7_joint` | 1.76 |

### 5.2 Current State

**No explicit velocity limits are enforced** in the PD control loop. The `maxForce` parameter indirectly limits acceleration, but there is no velocity cap. MoveIt may plan trajectories respecting these limits (if configured in the YAML), but the Isaac Sim PD controller will try to reach targets as fast as the gains allow.

**Recommendation:** Add velocity limits to the drive configuration or enforce them in the trajectory interpolation.

---

## 6. Summary of Root Causes

| # | Problem | Impact | Priority |
|---|---------|--------|----------|
| 1 | Robot tilts backward on torso lift | `_FK_COMP` is a fragile static hack; all IK targets are wrong when tilt changes | **Critical** |
| 2 | `arm_1_joint` limits wrong (allows negative, cuts positive range) | Shoulder workspace severely limited; MoveIt plans infeasible poses | **High** |
| 3 | `arm_2_joint` upper limit too high (1.57 vs 1.02) | PD controller fights hard stop; settle failures | **High** |
| 4 | `arm_3_joint` limits inverted | Elbow can't flex properly; MoveIt plans in wrong half of range | **High** |
| 5 | Wrist drive gains too high relative to real robot | Unrealistic dynamics; masks trajectory tracking issues | **Medium** |
| 6 | No velocity limits enforced | Trajectories may exceed physical capabilities | **Medium** |

---

## 7. Changes Applied (2026-03-12)

### 7.1 Base Stability
- Added `base_link` mass override (45 kg) alongside existing `base_footprint` (increased to 250 kg).
- Increased `base_footprint` inertia from (5,5,2) to (8,8,3).
- Increased wheel masses from 1.0 to 1.5 kg.
- Fixed `_TIAGO_SEARCH_MIDS` to include double-nested path (`/tiago_dual_functional/tiago_dual_functional`) so mass overrides actually apply.
- **Result:** Base is perfectly stable at (0.800, 0.000, 0.080) with zero tilt.

### 7.2 Joint Limits
- Changed limit intersection logic from `(min, max)` (expanding) to `(max, min)` (intersecting) so USD limits constrain rather than expand.
- Updated bridge `JOINT_LIMITS`, MoveIt YAML, and collector defaults to use intersection of PAL URDF and USD model limits.
- Updated all predefined joint poses to respect `arm_3_joint ∈ [-0.785, 1.57]` and `arm_1_joint ∈ [0.0, 1.57]`.
- **Result:** All SETTLE goals converge. Zero settle failures.

### 7.3 FK Compensation
- Set `_FK_COMP` to (0, 0, 0) — with a stable base, the empirical offset is no longer needed.
- **Result:** MoveIt FK and Isaac Sim FK now agree without compensation.

### 7.4 Drive Gains
- Reduced wrist joint gains (arm_5, arm_6, arm_7) from (1200, 240, 2000) to (500, 100, 800).
- Increased arm_3 gains from (1200, 240, 3000) to (1500, 300, 4000).
- **Result:** More realistic torque hierarchy matching PAL SEA characteristics.

### 7.5 Velocity Limits
- Added PAL velocity limits (1.76 rad/s) for wrist joints in MoveIt YAML.
- Added `--trajectory-time-scale 2.0` to smoke pipeline for slower trajectory execution.

### 7.6 Smoke Test Result
- `plan_pick_table` sequence completes successfully (exit code 0).
- All 8 steps execute: gripper open → pre-grasp → grasp → gripper close → lift → place → gripper open → ready.
- All SETTLE goals converge (max error ≤ 0.05 rad).
- Base remains stable throughout.
- IK still fails for most orientations due to tight USD joint limits; falls back to adaptive poses.

## 8. Robot Model Benchmark (2026-03-12)

### 8.1 Test Setup

Clean scene benchmark (`scripts/test_robot_bench.py`): 5x5m visible floor, DomeLight + DistantLight, PhysicsScene (TGS, 64 pos iters, 4 vel iters, 120Hz), robot at origin (0,0,0.08), fixedBase=True. Action sequence: stand 3s → torso up (0.35) → hold 5s → torso down (0.0) → stand 3s. Total 16s. No MoveIt, no ROS2 — direct PD control via ArticulationAction.

### 8.2 Available Models

| Model | USD File | Size | DOFs | Description |
|-------|----------|------|------|-------------|
| **heavy** | `tiago_dual_functional.usd` | 14.5 MB | 85 | Full physics: realistic mecanum wheels with 60 roller joints, proper mass/inertia, sensors. PAL Robotics official Isaac Sim asset. |
| **light** | `tiago_dual_functional_light.usd` | 94 KB | 21 | Simplified: dummy wheels (no rollers), base velocity set via API. Reference file that loads heavy model with overrides. |
| **urdf** | `tiago_dual_urdf_imported.usd` | 8.5 MB | 25 | Basic URDF import: 4 wheel joints (no rollers), no custom sensors or wheel physics. |

### 8.3 Benchmark Results

| Metric | **heavy** | **light** | **urdf** |
|--------|-----------|-----------|----------|
| Max base drift (m) | **0.00008** | 0.092 | 0.021 |
| Max base tilt (deg) | **0.001** | 0.0 | 0.979 |
| Max joint error (rad) | 0.703 | 0.704 | 0.715 |
| Max joint velocity (rad/s) | 2.37 | 2.37 | 5.59 |
| Final base position | (0.00, 0.00, 0.01) | (-0.10, -0.02, 0.01) | (0.02, 0.02, 0.01) |
| Stable (drift<1cm, tilt<1deg) | **PASS** | FAIL | FAIL |
| Wall time (16s sim) | 34.1s | 24.7s | 21.7s |
| Realtime factor | 0.47x | 0.65x | 0.74x |

### 8.4 Analysis

- **heavy is the only stable model.** fixedBase works correctly — drift is 0.08mm (essentially zero). The 60 extra roller joints from mecanum wheels spin freely and do not interfere with arm control.
- **light drifts 9.2cm** in 16 seconds despite fixedBase=True. The dummy wheel implementation lacks proper ground contact, so PhysX cannot anchor the base. No tilt (0 deg) — it slides, not tips.
- **urdf drifts 2.1cm and tilts 0.98 deg.** Better than light but still fails stability. The 4 basic wheel joints provide some ground contact but not enough.
- **Joint limits are identical** across all 3 models for arms, torso, head, and grippers.
- **Joint tracking error** (~0.7 rad peak) is similar across models — this is the transient error during torso movement, not a steady-state issue.

### 8.5 Decision

**Use `tiago_dual_functional.usd` (heavy) for all simulation work.** The 35% speed penalty is acceptable for correct physics. The light model was used previously and caused all the base drift/tilt problems that required mass overrides (200-500kg hacks).

Data: `C:\RoboLab_Data\bench\comparison.json`, per-model logs in `C:\RoboLab_Data\bench\{heavy,light,urdf}\physics_log.json`.

---

## 9. Remaining Issues

| # | Issue | Impact | Priority |
|---|-------|--------|----------|
| 1 | **Switch data_collector to heavy model** | Light model caused all base drift problems; heavy is stable | **Critical** |
| 2 | IK fails with tight USD limits | Gripper doesn't reach object accurately | **High** |
| 3 | USD `arm_3_joint` range (-0.785, 1.57) much tighter than real robot (-3.46, 1.57) | Limited workspace | **High** |
| 4 | Gripper "did not respond to open command" warning | May affect grasp quality | **Medium** |
| 5 | Micro-lift verification fails | Grasp not confirmed as physically held | **Medium** |
| 6 | Mass overrides in data_collector (500kg base_footprint) | Hack for light model; should be removed with heavy model | **Medium** |
