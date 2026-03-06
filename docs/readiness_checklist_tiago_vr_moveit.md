# Tiago + VR + MoveIt Readiness Checklist

## 1) Infrastructure / Runtime
- [ ] Node.js + npm available.
- [ ] Prisma schema synced and client generated.
- [ ] Next.js app starts successfully.
- [ ] Isaac Sim `python.bat` exists.
- [ ] Scene USD files exist (`Small_House_Interactive.usd`, `Office_Interactive.usd`).

## 2) ROS2 / MoveIt base availability
- [ ] `ros2` command available in shell.
- [ ] ROS2 setup command configured in app config or launch profile.
- [ ] MoveIt endpoints discoverable (`ros2 action list` contains move group action) OR documented as unavailable.

## 3) VR stack availability
- [ ] SteamVR/OpenXR runtime process detectable.
- [ ] Vive-related services/processes detectable (if installed).
- [ ] Teleop session start/stop path works from API.

## 4) Data pipeline smoke
- [ ] Episode start works from API.
- [ ] Episode stop works from API.
- [ ] Episode sync works from API.
- [ ] Required artifacts generated (`metadata.json`, `dataset.json`, `dataset_manifest.json`, `telemetry.json`, `camera_0.mp4`).

## 5) Teleop + bridge behavior
- [ ] Base motion command path works (`move_forward`).
- [ ] MoveIt command path works (`moveit_plan_pick`).
- [ ] Status endpoint returns bridge health (`ros2Available`, `moveitAvailable`, `bridgeMode`).
- [ ] Status endpoint returns ROS2 setup source/command.

## 6) Acceptance criteria from task
- [ ] Two environments available and selectable (`Small House`, `Office`).
- [ ] Pick/place & open/close task taxonomy represented in episodes/profiles.
- [ ] Joint trajectories include velocity.
- [ ] Pointcloud data present.
- [ ] World poses in map-referenced form present.

## Execution Log
- Run timestamp: 2026-03-06 (local).
- Checklist runner episode: `5747e354-20c4-4cef-a09a-26635c0a40a1`.
- Result summary:
  - Infrastructure: PASS
  - Pipeline: PASS
  - Teleop command paths: PASS
  - Dataset contract artifacts/content: PASS
  - ROS2 availability on host: FAIL (`ros2` command unavailable)
  - MoveIt availability on host: FAIL (dependent on ROS2 runtime)
- Notes:
  - `activeRos2SetupCommand` and source reported correctly (`launch_profile` override).
  - Dataset still uses `joint_source: synthetic_fallback`; real Tiago articulation remains pending for full production parity.
