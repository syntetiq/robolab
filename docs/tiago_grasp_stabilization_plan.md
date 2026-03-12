# TIAGo Grasp Stabilization Plan

## Goal
Reach stable, target-correct grasping in Isaac Sim with minimal control-path ambiguity and zero known runtime errors in the normal pick flow.

## Engineering Rules
- One joint group, one control mode in the normal path.
- No teleport-based joint writes during normal grasp execution.
- Grasp success must be confirmed by a short physical hold window, not a single frame.
- Every behavior change must be accompanied by a smoke test and a short written report.

## Current Execution Strategy
- Default grasp-debug runtime uses `tiago_dual_functional_light.usd`.
- Sim-native IK is preferred when available.
- MoveIt fallback remains available, but must not be trusted as grasp success evidence by itself.

## Phases

### Phase 1. Control Path Cleanup
- Keep `direct_set` recovery-only.
- Route normal arm execution through target-based articulation drives.
- Ensure initial joint targets match current state at episode start.

### Phase 2. Grasp State Machine
- Add grasp candidate window before `grasp_confirmed`.
- Add release window before `object_released`.
- Add holding latch so the bridge does not repeatedly re-close an already holding gripper.

### Phase 3. Target-Aware Verification
- Remember the intended object selected at pick time.
- Reject grasps that stabilize on the wrong nearby object.
- Keep retries focused on the requested object, not any object between fingers.

### Phase 4. Contact and Collider Quality
- Review gripper collider geometry.
- Simplify object colliders where needed.
- Tune contact and rest offsets for small objects.
- Add or refine physics materials for gripper and graspable objects.

### Phase 5. End-Effector Frame Validation
- Confirm grasp center is between fingers.
- Add a dedicated grasp frame if needed.
- Recalibrate pre-grasp and grasp offsets only after the frame is correct.

### Phase 6. Physics Scene Tuning
- Raise physics update rate for grasp debugging.
- Increase solver iterations.
- Track base stability and object hold stability as explicit metrics.

### Phase 7. Heavy-Model Regression
- Return to `tiago_dual_functional.usd` only after stable results on light.
- Treat heavy mode as a regression stage, not the primary debug mode.

## Required Reports Per Iteration
- What changed.
- What test was run.
- Whether the target object matched.
- Whether hold was stable.
- What remains broken.
