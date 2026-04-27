> **LEGACY**: These findings are from early grasp tuning. Per-task overrides now live in `config/tasks/*.json`. See experiment docs for current values.

# Top-Grasp Tuning Results (March 2026)

This document records findings and fixes that led to stable grasping and lifting of the mug in the Isaac Sim simulation.

---

## 1. Critical bug: torso did not descend in `descend_vertical`

### Symptoms

- In all runs `grasp_lift_delta_m` was ~4–5 mm instead of the required 20+ mm.
- In the `TOP_DESCEND` logs the **dZ** value (tool_z − mug_z) stabilised at **~0.055 m** and never reached `top_descend_clearance` (0.045 m).
- The transition `descend_vertical → close_gripper_top` occurred **only on timeout** (1500 steps), not by the dZ condition.

### Cause

Upon entering the `descend_vertical` state the following condition was evaluated:

```text
if (tz - mz) <= target_gap  →  _freeze_torso()
```

where `target_gap = top_pregrasp_height + retry_z_bias ≈ 0.06`. Since dZ was already ~0.054 (< 0.06), the torso was **immediately frozen** and did not descend at all. The tool remained 5.5 cm above the mug; the gripper closed "in the air" rather than around the mug.

### Fix

- **Removed the early freeze logic** upon entering `descend_vertical`.
- Now in this state `_set_torso(0.0, top_descend_speed, sim_time)` is **always** called — the torso descends to its minimum.
- The transition to `close_gripper_top` occurs on the condition **dZ ≤ top_descend_clearance** (without an additional xy check in descend).

**Conclusion:** dZ and xy should only be checked for the transition into `close_gripper_top`. The torso should not be frozen upon entering `descend_vertical` if the goal is to lower the tool closer to the mug.

---

## 2. XY check in descend prevented the transition

### Symptoms

After fix #1 the torso began descending, dZ decreased (0.054 → 0.032 → 0.005), but the transition to `close_gripper_top` still occurred on timeout.

### Cause

The transition condition included **xy_ok** (tool–mug distance in XY ≤ `top_xy_tol`). Due to the gripper frame offset relative to the mug centre, this offset was often 2–3 cm — greater than `top_xy_tol = 0.01–0.02`. While xy_ok was not satisfied the dZ transition was not triggered, and the tool descended below the mug (dZ became negative).

### Fix

- In the `descend_vertical` state the transition to `close_gripper_top` is now **based on dZ only**: `dz <= (top_descend_clearance + retry_z_bias)`.
- The XY check is retained only in **verify_grasp** (with a relaxed `top_verify_xy_tol = 0.03`), where it makes sense for grasp confirmation.

---

## 3. Gripper: full closure for retention

- The final closure value in `close_gripper_top` must be **GRIPPER_CLOSED (0.0)**, not 0.02.
- At 0.02 the grasp in the simulation turned out to be too weak — the mug did not hold during lifting.
- Details: `docs/grasp_lift_tuning_plan.md`.

---

## 4. Current parameters (stable baseline)

| Parameter | Value | Note |
|-----------|-------|------|
| `gripper_length_m` | 0.10 | Effective gripper length for targeting |
| `approach_clearance` | 0.13 | Base stop distance before mug (m) |
| `top_descend_clearance` | **0.025** | Close gripper when tool is 2.5 cm above mug |
| `top_xy_tol` | 0.02 | XY tolerance for approach_overhead (m) |
| `top_verify_xy_tol` | 0.03 | XY tolerance in verify_grasp (gripper frame offset from mug centre) |
| `top_lift_test_height` | 0.015 | Minimum mug lift for lift-test success (m) |
| `top_lift_test_hold_s` | 0.6 | Hold time for lift before proceeding |

Source of truth: `config/grasp_tuning.json`, `scripts/run_bench.ps1`, `scripts/test_robot_bench.py`.

---

## 5. grasp_success criterion

Current formula (after fixes):

```text
grasp_success = (lift_delta >= 0.02  AND  mug_final_z <= mug_z0 + 0.05)
```

- **lift_delta** — the difference between the maximum mug height during lifting and the initial height (m).
- The lift threshold was lowered from 0.03 to **0.02 m** (2 cm) as a realistic value for top-grasp.
- The **final_tilt** constraint was removed from the final success check: the mug may tip over during placement (place_mug/release) — that is a separate task; the grasp and lift are considered successful based on lift_delta and mug_final_z.

---

## 6. Scripts and runs

- **Quick tests without video:** `scripts/run_quick_grasp_test.ps1` — several clearance values (3, 8, 13 cm); on first success a rerun **with video**.
- Episodes with video are saved in `C:\RoboLab_Data\episodes\<uuid>\` (camera_0/1/2.mp4, metadata, telemetry, physics_log).

---

## 7. What to log for further diagnostics

- The logs already contain: `TOP_DESCEND` (tool, mug, dZ), state transitions, `LIFT t=...`, `verify failed` / `mug did not pass lift-test`.
- It is useful to check: whether the transition `descend_vertical → close_gripper_top` occurs **before** the 1500-step timeout and with dZ in a reasonable range (e.g. 0.02–0.04 m), rather than with a negative dZ.

---

## Summary

1. **Descend:** the torso must descend in `descend_vertical`; do not freeze it on entry based on target_gap.
2. **Transition to close_gripper_top:** based on dZ only, without xy in descend; check xy in verify_grasp.
3. **Gripper:** full closure (0.0) for reliable retention during lifting.
4. **Parameters and success:** use values from `grasp_tuning.json` and the success formula above; record changes in this document and in the config.
