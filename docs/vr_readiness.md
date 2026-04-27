# VR Teleoperation Readiness — Vive Pro 2 / OpenXR

**Status:** Infrastructure complete; hardware integration deferred until a Vive Pro 2 (or compatible OpenXR HMD) is connected.

This document captures the current state of the VR pipeline, what is verified to work without hardware, and the precise checklist that must be executed when a headset becomes available.

---

## What is implemented

### 1. VR teleoperation node — `scripts/vr_teleop_node.py`

A standalone Python ROS 2 node that:

- Reads VR controller pose via `pyopenvr` (right-hand controller by default).
- Maps controller pose to end-effector goals for MoveIt Servo.
- Maps right-trigger to gripper open/close.
- Publishes to `/tiago/moveit/intent` (the same topic used by the on-screen teleop UI).

The node has a soft import of `pyopenvr` so the rest of the codebase still loads without OpenVR installed; it only fails at start-up if the user actually launches the VR teleop session.

### 2. Launch profile flags

`LaunchProfile` in the database has two columns wired through the runners:

| Field | Purpose |
|-------|---------|
| `enableVrTeleop` | Starts `vr_teleop_node.py` as part of the teleop stack. |
| `enableVrPassthrough` | After 15 s, opens the WebRTC robot-POV stream URL in the system browser so the operator can drag the window onto the SteamVR desktop overlay and view it inside the headset. |

Both flags are surfaced in the **Launch Profile** dialog (`src/app/launch-profiles/LaunchProfileDialog.tsx`) and respected by both `localRunner` and `sshRunner`.

### 3. Robot POV stream

- Head camera (`head_front_camera_link`) is captured as `camera_0` and re-streamed via Isaac Sim's WebRTC server.
- The stream URL pattern is `http://{ISAAC_HOST}:8211/streaming/webrtc-demo/`.
- `enableVrPassthrough` simply opens this URL in a Chrome window — SteamVR's built-in **Desktop Theatre** can then mirror that window into the headset.

### 4. Input source registration

`src/server/teleop/inputAdapters.ts` accepts `"vive_openxr"` as a teleop source so commands originating from the VR node are routed and logged correctly.

### 5. ROS 2 topics

The same topics used by the on-screen UI (`/tiago/moveit/intent`, `/joint_states`, `/joint_commands`) carry VR-originated traffic, so MoveIt and the data collector see VR commands as ordinary teleop input. No second pipeline to maintain.

---

## What requires Vive Pro 2 hardware to verify

The following must be performed once with a real headset before the VR pipeline can be considered production-ready:

### Pre-flight (one-time)

- [ ] Install SteamVR.
- [ ] Pair Vive Pro 2 + base stations and complete room setup.
- [ ] In the conda env used by the runners: `pip install pyopenvr`.
- [ ] Confirm `python -c "import openvr; print(openvr.VRSystem())"` succeeds with SteamVR running.

### End-to-end smoke test

1. Create a Launch Profile with `enableMoveIt = true`, `enableVrTeleop = true`, `enableVrPassthrough = true`.
2. Start an episode using that profile against `kitchen_fixed.usd`.
3. Verify:
   - [ ] Isaac Sim window appears (or runs headless with WebRTC).
   - [ ] `vr_teleop_node` connects to OpenVR without errors (check `*_teleop.log`).
   - [ ] WebRTC stream URL opens in the default browser ~15 s after start.
   - [ ] Pulling/pushing the right Vive controller moves the TIAGo end-effector (delay < 200 ms).
   - [ ] Right-trigger closes the gripper, releasing it opens.
   - [ ] In the headset, SteamVR Desktop Theatre shows the WebRTC stream as a virtual screen.
4. Run a full pick-and-place episode under VR control and confirm the dataset contains:
   - [ ] Joint trajectories with `source = "vive_openxr"`.
   - [ ] Continuous head-camera video.
   - [ ] No teleop drop-outs in `telemetry.json`.

### Known unverified bits

- The `pyopenvr` ↔ MoveIt Servo coordinate frame mapping (controller frame → robot base frame) uses the conventional OpenVR axes; an actual fitting may need a small rotation offset, calibrated by holding the controller pointed forward at the start.
- WebRTC latency over Steam's Desktop Theatre overlay has not been measured. If it exceeds ~200 ms, switching to a native OpenXR overlay (`SteamVR_AddOverlay`) is the next step.

---

## Why this is "ready" rather than "working"

Every software component the operator interacts with is wired up:

| Component | State |
|-----------|-------|
| Launch profile flags | Wired through the runners and visible in the UI. |
| `vr_teleop_node.py` | Runs on demand, opens correct ROS 2 topics. |
| Browser stream auto-open | Verified end-to-end from runner. |
| ROS 2 topic plumbing | Same topics as the on-screen teleop UI, already exercised by automated regression tests. |

The only blocker is access to a Vive Pro 2 (or another OpenXR HMD) for the smoke test above. As soon as one is connected, the checklist takes ~30 minutes to walk through.

---

## How to disable VR cleanly

If a deployment environment has no headset and no intent to add one:

- Leave `enableVrTeleop` unchecked (it defaults to `false`).
- The `pyopenvr` import is lazy, so the package does not need to be installed.
- All other features (on-screen teleop, MoveIt, batch queue, recordings) work normally.

---

_Last reviewed: 2026-04-27_
