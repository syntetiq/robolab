# TIAGo Grasp Progress Report

## Date
2026-03-10

## Scope
Early implementation of the grasp stabilization plan for TIAGo in Isaac Sim.

## Completed In This Stage
- Removed `direct_set` from the normal `move_direct` execution path.
- Kept `direct_set` marked as recovery/debug-only.
- Switched default grasp-debug runtime to `tiago_dual_functional_light.usd`.
- Strengthened bridge-side grasp verification from a single-frame heuristic to a short hold window.
- Added bridge-side holding latch behavior.
- Added collector-side confirm/release windows to reduce false `grasp_confirmed` and `object_released` events.
- Added target-aware bridge verification so a stable grasp on the wrong object is treated as failure.
- Added collector-side close-cycle latch to reduce repeated `gripper_close_start` event spam.

## Observed Test Outcome
- Smoke test on light runtime completed successfully.
- The new verification logic rejected an initial false positive grasp.
- A later grasp was considered physically stable, but it stabilized on the wrong object.
- In the latest observed run, the intended target was `010_potted_meat_can`, while the observed held object was `003_cracker_box`.

## What Improved
- Normal execution no longer depends on teleport-based arm motion.
- Grasp confirmation is more conservative and more physically plausible.
- The system now distinguishes between "something is between the fingers" and "the intended object is stably held".

## What Still Fails
- Target selection is not yet reliable.
- MoveIt fallback can still lead the hand toward nearby non-target objects.
- Collector event stream still needs another validation pass after the close-cycle latch update.
- Sim-native IK on the light model did not succeed in the latest run and needs a focused follow-up.

## Immediate Next Steps
1. Re-run smoke after the target-aware verification and close-cycle latch changes.
2. Check whether `gripper_close_start` spam is gone in `grasp_events.json`.
3. Keep retries tied to the intended target object.
4. Investigate why sim-native IK failed on the light model for the latest pick target.

## Zero-Error Policy For Next Iterations
- No known syntax or linter errors before test runs.
- No silent fallback acceptance as "success".
- No undocumented control-path changes.
- No promotion of a phase until smoke-test evidence is recorded.
