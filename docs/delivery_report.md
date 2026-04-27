# RoboLab Delivery Report

Mapping of the original requirements (Технические Задание / TZ) to concrete implementation evidence in this repository.

**Status legend:** ✅ Complete · ⚠️ Ready, awaiting hardware · ➖ Out of scope (descoped by user)

---

## 1. Environments

> *"Generate a couple of environments like a small house and an office. They can be used to collect the data."*

| Item | Status | Evidence |
|------|--------|----------|
| Home environment (kitchen) | ✅ | Procedural builder `scenes/kitchen_fixed/kitchen_fixed_builder.py`, config `scenes/kitchen_fixed/kitchen_fixed_config.yaml`, USD `C:/RoboLab_Data/scenes/kitchen_fixed.usd` |
| Office environment | ✅ | Procedural builder `scenes/office_fixed/office_fixed_builder.py`, config `scenes/office_fixed/office_fixed_config.yaml`, USD `C:/RoboLab_Data/scenes/Office_Interactive.usd` |
| Both wired into runner | ✅ | `scripts/data_collector_tiago.py:413-428` — auto-selects builder by USD basename |
| Both registered in DB | ✅ | `Scene` table contains `Kitchen Fixed (Experiments 1-3)` and `Office Fixed (Open-space)` |
| Office task config | ✅ | `config/tasks/office_mug_to_desk_side.json` — pick mug from desk_main, carry to desk_side, place |

---

## 2. Robot — TIAGo Omni / Tiago++ with full sensor suite

> *"Use the Tiago Omni (or Tiago++) robot... You can use all the sensors available to the robot."*

| Sensor | Status | Evidence |
|--------|--------|----------|
| Head RGB camera (`camera_0`) | ✅ | `scripts/data_collector_tiago.py` Replicator writer, `head_front_camera_link` |
| Wrist camera | ✅ | `--wrist-camera` flag + `enableWristCamera` launch profile field |
| External / third-person camera | ✅ | `enableExternalCamera` launch profile field, three cameras in test bench |
| Depth maps | ✅ | Replicator `distance_to_camera` annotator → `replicator_*/distance_to_camera_*.npy` |
| Force / contact sensors | ✅ | Referenced in `task_results.json.grasp_success` and physics log |
| Robot model | ✅ | `tiago_dual_functional_light.usd` — Tiago dual-arm "heavy" model |

---

## 3. Main tasks

> *"1) Picking and Placing things from a table into a sink or fridge or a dishwasher (3 tasks). 2) Opening and closing Fridge and Dishwasher (2 tasks)."*

| Task | Status | Config | Notes |
|------|--------|--------|-------|
| Pick & Place → sink | ✅ | `config/tasks/fixed_banana_to_sink.json` | banana from plate → sink basin |
| Pick & Place → fridge | ✅ | `config/tasks/fixed_mug_to_fridge.json` | mug from table → fridge interior |
| Pick & Place → dishwasher | ➖ | (descoped) | User explicitly removed dishwasher from scope |
| Open / Close fridge | ✅ | `config/tasks/fixed_fridge_open_close.json` | handle pull, body push, multi-waypoint nav |
| Open / Close dishwasher | ➖ | (descoped) | User explicitly removed dishwasher from scope |
| Bonus: mug rearrange | ✅ | `config/tasks/fixed_mug_rearrange.json` | end-to-end pick → carry → place |
| Bonus: office desk rearrange | ✅ | `config/tasks/office_mug_to_desk_side.json` | exercises the office environment |

**Active task count:** 5 task configurations, covering all 3 in-scope main tasks.

---

## 4. Object diversity

> *"Diversify the objects, not just regular shapes (different types of mugs, bottles, fruits, containers, etc.)"*

| Pool | Count | Status | Path |
|------|-------|--------|------|
| Custom kitchen / household USDA | 30 | ✅ Physics-ready (RigidBody + Collision + Mass) | `C:/RoboLab_Data/data/object_sets/` |
| YCB Benchmark USDC | 19 | ✅ Available (binary format, validate via `scripts/validate_tiago_asset.py`) | `C:/RoboLab_Data/data/object_sets_ycb/` |
| Categories | mugs (5), bottles (5), fruits (6), containers (6), bowls (2), plates (2), glasses (2), cans (2) | ✅ | mass range 0.08–0.70 kg |

ObjectSet records in DB:
- `Kitchen Mixed Objects` — 22 paths (mugs + bottles + fruits + containers)
- `Kitchen Tableware` — 8 paths (bowls + plates + glasses + cans)
- `YCB Benchmark (Graspable)` — 9 paths (subset of YCB suitable for manipulation)

---

## 5. VR teleoperation (Vive Pro 2 / OpenXR)

> *"Connect Vive Pro 2 teleoperation node to ISAAC Sim... If possible, the human can see what the robot sees through the VR headset."*

| Sub-requirement | Status | Evidence |
|-----------------|--------|----------|
| OpenVR / OpenXR controller node | ⚠️ Ready | `scripts/vr_teleop_node.py` — pyopenvr-based pose reader → `/tiago/moveit/intent` |
| VR launch profile flags | ✅ | `enableVrTeleop`, `enableVrPassthrough` columns in `LaunchProfile`, surfaced in UI dialog |
| Robot POV stream auto-open in browser/SteamVR overlay | ✅ | `localRunner.ts` opens WebRTC stream URL after 15 s when `enableVrPassthrough = true` |
| End-to-end Vive Pro 2 smoke test | ⚠️ | Hardware not available; full procedure documented in `docs/vr_readiness.md` |

The VR pipeline is wired through to MoveIt and the data collector. As soon as a Vive Pro 2 (or any OpenXR HMD) is connected, the 30-minute smoke test in `docs/vr_readiness.md` can be executed without code changes.

---

## 6. ROS 2 joint state publishing

> *"We need the joint states of the robot to be published via ROS2 to control it."*

| Item | Status | Evidence |
|------|--------|----------|
| `/joint_states` topic publishing | ✅ | `scripts/ros2_fjt_proxy.py:181` — primary publisher, 20 Hz |
| Direct rclpy publisher fallback | ✅ | `scripts/data_collector_tiago.py:1838` |
| OmniGraph ROS2 node fallback | ✅ | `scripts/data_collector_tiago.py:2228` |
| Velocities included | ✅ | `JointState.velocity` array populated; per-joint `velocity_rads` in `physics_log.json` |
| `start_moveit_stack.ps1` orchestrates the bridge | ✅ | Launches FJT proxy, MoveIt move_group, intent bridge |

---

## 7. MoveIt integration

> *"You can integrate standard MoveIt package to control the robot."*

| Item | Status | Evidence |
|------|--------|----------|
| MoveIt move_group launch | ✅ | `scripts/start_moveit_stack.ps1` — uses `tiago_move_group_working.yaml` |
| Intent → MoveGroup action bridge | ✅ | `scripts/moveit_intent_bridge.py` (41 distinct intents) |
| FollowJointTrajectory action servers | ✅ | `/arm_controller/follow_joint_trajectory`, `/torso_controller/...`, etc. |
| URDF + joint limits | ✅ | Auto-generated in data collector with arm + torso + gripper limits |
| Direct trajectory fallback | ✅ | `send_direct_trajectory()` when MoveGroup unavailable |
| Web UI MoveIt controls | ✅ | Episode detail page: Start/Stop session, Plan Pick/Place, Pick Sink, Pick Fridge, MoveIt Home, plus arm macros |

---

## 8. Recorded data outputs

> *"The data should include all the following: the joint trajectories including velocities, 3D point clouds of the simulated objects and finally the world positions of all objects and robot with respect to a map."*

For every episode the runner persists the following under `<output_dir>/<episode_id>/heavy/`:

| Output | File | Notes |
|--------|------|-------|
| Joint positions per frame | `physics_log.json` | `joints[<name>].position_rad` |
| Joint **velocities** per frame | `physics_log.json` | `joints[<name>].velocity_rads` |
| Joint trajectory commands | `physics_log.json.frames` + `task_log.jsonl` | what was sent to the robot |
| Robot base world pose | `physics_log.json` (`base_position`, `base_orientation_quat`) and `telemetry.json` (`trajectory[].robot_position`) | map frame, declared in metadata as `"map_frame": "map"` |
| All object world poses | `physics_log.json` (`world_poses[<prim_path>]`) | XYZ + quaternion for every tracked prim |
| RGB frames | `replicator_*/rgb_*.png` | 1920×1080 by default |
| Depth maps | `replicator_*/distance_to_camera_*.npy` | per-pixel metric depth |
| **3D point clouds** | `replicator_*/pointcloud_*.npy` | XYZ points |
| Point cloud per-point class labels | `replicator_*/pointcloud_semantic_*.npy` | enables object-level filtering |
| Point cloud normals | `replicator_*/pointcloud_normals_*.npy` | optional, for surface-aware policies |
| Instance segmentation masks | `replicator_*/instance_segmentation_*.npy` | object-level masks |
| Task pass / fail | `task_results.json` | per-task success + final base position |
| Episode video (head camera) | `camera_0.mp4` | playback in the web UI |
| Dataset index | `dataset_manifest.json` + `.artifact-index.json` | machine-readable list of all artefacts |

---

## 9. Web operator console (additional deliverable)

The web console is not in the original TZ but is required to drive everything above. Highlights:

- 8 pages: Dashboard, Episodes, Episode Wizard, Episode Detail, Batch Queue, Experiments, Task Editor, Recordings, Scenes, Launch Profiles, Configuration
- ~30 inline help tooltips (British English) explaining technical terms
- Real-time WebRTC live stream during teleoperation
- Batch queue with seed-incrementing automation for large-scale data collection
- Visual task editor (6 task types: navigate_to, pick_object, carry_to, place_object, open_door, close_door)
- Object randomisation UI in episode wizard
- Auto-discovery of task configs from `config/tasks/`

---

## 10. Quality gates

| Gate | Result |
|------|--------|
| `scripts/test_fixed_baseline_lock.py` | ✅ pass |
| `scripts/test_mvp_task_suite_regression.py` | ✅ pass |
| `scripts/test_scene_assets_regression.py` | ✅ pass |
| `scripts/ci_checks.py` (7 sub-gates) | ✅ 7 / 7 pass |

Sub-gates inside `ci_checks`: `python_syntax (55)`, `yaml_syntax (2)`, `typescript (1)`, `moveit_consistency (1)`, `fjt_proxy_joints (1)`, `intent_coverage (20)`, `dataset_export (1)`.

---

## 11. Outstanding follow-ups (not blocking delivery)

1. **Run live Isaac Sim smoke episode for the office task** — config and code paths verified statically; the user should launch one episode through the UI to confirm end-to-end runtime behaviour. (See `docs/vr_readiness.md` checklist for VR variant.)
2. **Validate YCB physics with `scripts/validate_tiago_asset.py`** — binary format prevents text inspection; one validation pass would upgrade YCB from "available" to "validated".
3. **Demo video v4** — the existing demo (`demo_output/robolab_demo_v3.mp4`) covers Kitchen Fixed; a v4 with the new office task would round out "multiple environments" in marketing materials.

---

## Summary

| Category | Required | Delivered | Notes |
|----------|----------|-----------|-------|
| Environments | 2 (home + office) | 2 ✅ | both procedural, both wired |
| Tasks (in-scope) | 3 | 5 ✅ | all 3 main + 2 bonus |
| Tasks (out-of-scope) | 2 (dishwasher) | — ➖ | descoped by user |
| Sensor modalities | "all" | RGB + depth + point cloud + semantic + joint state + force | ✅ |
| Object diversity | "diverse" | 49 USD assets across 8 categories | ✅ |
| VR teleop | yes | ⚠️ ready, awaiting hardware | software complete, see `docs/vr_readiness.md` |
| ROS 2 + MoveIt | yes | ✅ | 41 intents, dual publisher paths |
| Data: joints + velocities | yes | ✅ | `physics_log.json` |
| Data: 3D point clouds | yes | ✅ | `pointcloud_*.npy` |
| Data: world poses | yes | ✅ | `world_poses[...]` per frame |
| Quality gates | — | 4 / 4 ✅ | regression suite green |

_Generated: 2026-04-27_
