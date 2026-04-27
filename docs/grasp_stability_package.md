# Grasp Stability Package

This package fixes and standardizes mug grasp validation for the TIAGo bench.

## What changed

- `scripts/test_robot_bench.py`
  - Added top-first grasp strategy with fallback:
    - `approach_overhead`
    - `descend_vertical`
    - `close_gripper_top`
    - fallback to side grasp in `auto` mode
  - Added explicit `verify_grasp` state after gripper close.
  - Added strict grasp metrics in report:
    - `grasp_success`
    - `grasp_retry_count`
    - `grasp_retry_count_top`, `grasp_retry_count_side`
    - `grasp_active_mode_final`, `grasp_fallback_used`
    - `grasp_lift_delta_m`
    - `grasp_final_tilt_deg`
    - `grasp_mug_z_start`, `grasp_mug_z_peak`, `grasp_mug_z_final`
  - Baseline defaults aligned for grasp:
    - `approach_clearance = 0.13`, `torso_lower_speed = 0.02`, `grasp_mode = top`
    - `top_descend_clearance = 0.025`, `top_xy_tol = 0.02`, `top_verify_xy_tol = 0.03`
    - `top_lift_test_height = 0.015`, gripper close = `GRIPPER_CLOSED` (0.0)
  - **Critical fix:** In `descend_vertical`, torso always descends (no early freeze); transition to `close_gripper_top` is by dZ only. See `docs/grasp_tuning_findings.md`.

- `scripts/run_bench.ps1`
  - Baseline: `ApproachClearance = 0.13`, `TopDescendClearance = 0.025`, `TopXyTol = 0.02`, `TopLiftTestHeight = 0.015`
  - Added top-grasp runtime knobs:
    - `-GraspMode top|side|auto`
    - `-TopPregraspHeight`
    - `-TopDescendSpeed`
    - `-TopDescendClearance`
    - `-TopXyTol`
    - `-TopLiftTestHeight`
    - `-TopLiftTestHold`
    - `-TopRetryYStep`, `-TopRetryZStep`, `-TopMaxRetries`

- `config/grasp_tuning.json`
  - Centralized baseline tuning for repeatable runs.
  - Production effective gripper length: **0.10 m** (override via `gripper_length_m` or `-GripperLengthM`).

- `scripts/run_grasp_stability.ps1`
  - Batch suite with random mug XY jitter.
  - Supports `-GraspMode top|side|auto`.
  - Aggregates success/retries/fallback/fail-codes into CSV/JSON/TXT.

## Quick start

Fast stability batch:

```powershell
.\scripts\run_grasp_stability.ps1 -Runs 12 -Fast -JitterXY 0.02 -GraspMode top
```

Single grasp run with baseline params:

```powershell
.\scripts\run_bench.ps1 -Grasp -Fast -GraspMode top
```

## Current success rule

`grasp_success = true` when:

1. Mug was lifted by at least **2 cm** (`grasp_lift_delta_m >= 0.02`)
2. Mug ends near table height (`grasp_mug_z_final <= grasp_mug_z_start + 0.05`)

Final tilt is not required for success (mug may tip during place; grasp and lift are what we validate). See `docs/grasp_tuning_findings.md` for the reasoning and parameter history.

## Top-grasp acceptance target

Recommended gate before moving to more complex scenarios:

1. `>= 80%` success on random mug positions (`10+` runs, no video, fast mode)
2. Mean retries `<= 1.5`
3. No critical collisions and no mug topple events in success runs

## References

- **`docs/grasp_tuning_findings.md`** — root-cause fixes (descend_vertical freeze, xy in descend), current parameters, success rule, scripts.
- **`docs/grasp_lift_tuning_plan.md`** — experiment plan, one-parameter-at-a-time, what to log.
- **`docs/episode_grasp_verify_analysis.md`** — why verify failed with good visual alignment (xy_ok / tool frame).
