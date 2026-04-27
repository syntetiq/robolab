# RoboLab

Robotic data-collection platform for training manipulation policies. Collects diverse demonstrations in NVIDIA Isaac Sim using the PAL TIAGo robot, with VR teleoperation, autonomous MoveIt-based task execution, and sim-to-real transfer.

```
 Web UI (Next.js)          MoveIt 2           Isaac Sim
 ┌─────────────┐      ┌─────────────┐     ┌──────────────────┐
 │  Episodes    │      │ MoveGroup   │     │ data_collector   │
 │  Batches     │      │ Intent      │     │ tiago.py         │
 │  Experiments │─API──│ Bridge      │─IPC─│  ├─ Replicator   │
 │  Scenes      │      │ FJT Proxy   │     │  ├─ Articulation │
 │  Profiles    │      └──────┬──────┘     │  └─ Multi-camera │
 │  ObjectSets  │             │            └────────┬─────────┘
 └──────┬───────┘      ┌──────┴──────┐              │
        │              │ sim2real    │         ┌────┴────┐
        │              │ bridge      │         │ HDF5    │
        │              └──────┬──────┘         │ Export  │
        │                     │                └────┬────┘
        │              ┌──────┴──────┐              │
        └──────────────│ Real TIAGo  │         ML Training
                       └─────────────┘
```

## Quick start

```powershell
# 1. Install
npm install
npx prisma generate
npx prisma db push

# 2. Start the web console
npm run dev                     # http://localhost:3000

# 3. Set Isaac Sim host on the Configuration page
# 4. Either launch a single episode through the wizard
#    or run a batch via the Batch Queue page.
```

## Web console

Next.js 16 + Prisma/SQLite. Manages the full lifecycle of data-collection experiments.

| Page | Purpose |
|------|---------|
| `/` Dashboard | System health, quick actions |
| `/episodes` | List, create, monitor, stop episodes |
| `/episodes/new` | 5-step episode wizard with object randomisation |
| `/episodes/[id]` | Live monitoring, teleop controls, MoveIt actions, recorded artefacts |
| `/batches` | Queue and run N episodes with seed-incrementing variation |
| `/experiments` | Auto-discovered task configs from `config/tasks/`, plus visual task editor (6 task types) |
| `/recordings` | Searchable artefact library (videos, telemetry, datasets) |
| `/scenes` | Manage simulation environments (USD stages) |
| `/launch-profiles` | Configure Isaac Sim launch flags (GUI, WebRTC, VR, MoveIt, cameras) |
| `/config` | Isaac Sim host, ROS 2 setup, runner mode, streaming |

Every page has inline help tooltips (British English) explaining technical terms.

## Robot control pipeline (`scripts/`)

| Script | Role |
|--------|------|
| `data_collector_tiago.py` | Isaac Sim episode runner: physics, articulation, cameras, recording |
| `ros2_fjt_proxy.py` | ROS 2 FollowJointTrajectory action servers + `/cmd_vel` subscriber via file-based IPC |
| `moveit_intent_bridge.py` | Translates intents (e.g. `plan_pick_sink`) to MoveIt joint trajectories — **41 intents** |
| `vr_teleop_node.py` | OpenVR/SteamVR input → ROS 2 commands (Vive Pro 2 ready, see `docs/vr_readiness.md`) |
| `start_moveit_stack.ps1` | Launches MoveGroup + bridge + FJT proxy in one PowerShell stack |

### Data flow (file-based IPC)

Isaac Sim cannot import ROS 2 natively on Windows. The FJT Proxy bridges this gap:

```
MoveIt MoveGroup ──FJT Action──▶ ros2_fjt_proxy.py ──JSON files──▶ data_collector_tiago.py
                                      │                                     │
                                      ├─ pending_arm_*.json                 ├─ reads & applies via
                                      ├─ done_arm_*.json                    │  ArticulationAction
                                      ├─ joint_state.json  ◀────────────────┤
                                      └─ base_cmd.json                      └─ XFormPrim velocity
```

## Scenes

Two procedural scenes built directly from YAML configs (no raw mesh imports):

| Scene | Type | Builder | Use cases |
|-------|------|---------|-----------|
| Kitchen Fixed | home | `scenes/kitchen_fixed/kitchen_fixed_builder.py` | sink, fridge, table — 5 task configs |
| Office Fixed | office | `scenes/office_fixed/office_fixed_builder.py` | desks, cabinet, chair — pick & place |

Builders share `scenes/scene_utils.py` (physics, walls, lights, cameras).

## Available task configs (auto-discovered from `config/tasks/`)

| Config | Scene | Description |
|--------|-------|-------------|
| `fixed_banana_to_sink.json` | Kitchen | banana → sink basin |
| `fixed_mug_to_fridge.json` | Kitchen | mug → fridge interior |
| `fixed_fridge_open_close.json` | Kitchen | open / close fridge door |
| `fixed_fridge_experiment3.json` | Kitchen | fridge handle pull, body push |
| `fixed_mug_rearrange.json` | Kitchen | end-to-end pick → carry → place |
| `office_mug_to_desk_side.json` | Office | desk → desk pick & place |

Custom configs can be authored in the Task Editor (`/experiments` → New Task Config).

## Multi-camera system

| Camera | Flag | Mount | Purpose |
|--------|------|-------|---------|
| Head (`camera_0`) | always on | `head_2_link` (or fixed overhead) | Primary RGB / depth / point cloud / semantic |
| Wrist (`camera_1_wrist`) | `--wrist-camera` | `arm_tool_link` | Close-up manipulation view |
| External (`camera_2_external`) | `--external-camera` | Fixed world position | Scene overview, third-person |

Each camera writes to its own Replicator directory and an MP4 video.

## Object diversity

49 USD assets across 8 categories, all physics-validated (`PhysicsRigidBodyAPI` + `CollisionAPI` + `MassAPI`):

| Set | Count | Categories |
|-----|-------|------------|
| Kitchen Mixed Objects | 22 | mugs, bottles, fruits, containers |
| Kitchen Tableware | 8 | bowls, cans, glasses, plates |
| YCB Benchmark | 19 | cans, boxes, bottles, household |

Object Sets are configured in the database; episode wizard offers per-task randomisation (layout, types, count, categories).

## Episode output structure

```
episodes/<uuid>/
├── dataset.json                 # Per-frame: joints, poses, world objects, timestamps
├── physics_log.json             # joint positions + velocities, base pose, world poses
├── telemetry.json               # Trajectory in map frame
├── task_results.json            # Per-task pass/fail + final positions
├── metadata.json                # Scene, task config, runtime info
├── dataset_manifest.json        # File index
├── camera_0.mp4                 # Head camera video
├── camera_1_wrist.mp4           # (if --wrist-camera)
├── camera_2_external.mp4        # (if --external-camera)
└── replicator_*/
    ├── rgb_*.png
    ├── distance_to_camera_*.npy        # depth maps
    ├── pointcloud_*.npy                # 3D point clouds
    ├── pointcloud_semantic_*.npy       # per-point class labels
    ├── pointcloud_normals_*.npy
    └── instance_segmentation_*.png
```

## Batch collection

The Batch Queue page launches N episodes with incrementing seeds. Polling-based execution engine (10-second cadence) auto-advances to the next episode when the previous completes or fails.

CLI alternatives are also available for headless runs:

```powershell
.\scripts\run_batch_with_objects.ps1 -Reps 5 -DurationSec 50
.\scripts\run_balance_collection.ps1 -TargetPerScenePerIntent 5
.\scripts\run_mass_collection.ps1
```

## Dataset export & evaluation

```powershell
# Episode quality classification
python scripts/evaluate_episodes.py --json-report report.json

# HDF5 export (robomimic / LeRobot compatible)
python scripts/export_dataset_hdf5.py --last 50 --min-frames 100

# Dataset validation
python scripts/validate_dataset.py --episodes-dir C:\RoboLab_Data\episodes
```

HDF5 layout:

```
/data/<episode_id>/
  obs/
    joint_positions      (T, N_joints) float32
    joint_velocities     (T, N_joints) float32
    robot_pose           (T, 7) float32   [xyz + quaternion]
    world_object_poses   (T, N_objects, 7) float32
    cameras/<camera>/rgb_paths   string[]
  action/
    joint_positions      (T, N_joints) float32
```

## VR teleoperation

The pipeline is software-complete and waiting for hardware. See `docs/vr_readiness.md` for the 30-minute Vive Pro 2 smoke-test checklist.

| Component | Status |
|-----------|--------|
| OpenVR controller node | ✅ `scripts/vr_teleop_node.py` |
| Launch profile flags (`enableVrTeleop`, `enableVrPassthrough`) | ✅ surfaced in UI |
| Robot POV WebRTC stream + auto-open in browser/SteamVR overlay | ✅ |
| End-to-end Vive Pro 2 hardware test | ⚠️ pending hardware |

## Sim-to-real transfer

`config/sim2real.yaml` defines joint mapping, calibration offsets, safety limits, and ROS 2 topic mapping for the real TIAGo.

```powershell
python scripts/sim2real_bridge.py --config config/sim2real.yaml          # validate
python scripts/calibrate_joints.py --config config/sim2real.yaml --write # calibrate at home pose
python scripts/sim2real_bridge.py --replay <episode> --dry-run           # replay sim on real (dry)
python scripts/sim2real_bridge.py --config config/sim2real.yaml --live   # live bridge with safety filter
.\scripts\launch_real_tiago.ps1 -Intent plan_pick_sink -DryRun           # full launch stack
```

Safety filter pipeline:

```
sim joint command → name mapping → offset → position clamp → delta clamp → velocity scale → real robot
```

## Demo video builder

```bash
# Prerequisites: pip install playwright Pillow matplotlib; playwright install chromium; ffmpeg on PATH
python scripts/build_demo_v3.py --output demo_output/robolab_demo_v3.mp4
```

Combines Playwright web-UI screencast, real Isaac Sim multi-camera footage, title cards, and matplotlib telemetry slides into a 1920×1080 MP4 with annotated bottom-bar overlays.

## CI / automated checks

```powershell
python scripts/ci_checks.py
python scripts/test_fixed_baseline_lock.py
python scripts/test_mvp_task_suite_regression.py
python scripts/test_scene_assets_regression.py
```

`ci_checks.py` covers: Python syntax, YAML validity, TypeScript compilation, MoveIt consistency, FJT proxy joint coverage, intent bridge completeness, dataset export contract.

## Prerequisites

| Component | Version | Purpose |
|-----------|---------|---------|
| Node.js | 20+ | Web UI |
| Python | 3.10+ | Scripts |
| NVIDIA Isaac Sim | 4.x | Simulation |
| ROS 2 Humble | via Mambaforge | Robot control |
| MoveIt 2 | `ros-humble-moveit` | Motion planning |
| ffmpeg | latest | Video composition |
| h5py, PyYAML | latest | Dataset export, configs |
| Playwright + Pillow + matplotlib | latest | Demo video builder |

### Windows setup

```powershell
# ROS 2 + MoveIt via Mambaforge
mamba create -n ros2_humble -c conda-forge -c robostack-staging ros-humble-desktop ros-humble-moveit
mamba activate ros2_humble

# Python tooling
python -m pip install h5py pyyaml numpy playwright Pillow matplotlib
python -m playwright install chromium
winget install Gyan.FFmpeg
```

## Project structure

```
robolab/
├── config/
│   ├── tasks/                       # Auto-discovered task configs
│   ├── sim2real.yaml                # Real-robot bridge
│   └── object_diversity_profile.json
├── docs/
│   ├── delivery_report.md           # TZ → implementation evidence map
│   ├── vr_readiness.md              # VR Pro 2 hardware smoke-test
│   ├── teleop_configuration.md
│   └── (other technical references)
├── prisma/
│   ├── schema.prisma                # Episode, Scene, Batch, ObjectSet, LaunchProfile, ...
│   └── dev.db
├── scenes/
│   ├── kitchen_fixed/               # Procedural kitchen builder + textures
│   ├── office_fixed/                # Procedural office builder + textures
│   └── scene_utils.py               # Shared scene primitives
├── scripts/
│   ├── data_collector_tiago.py      # Isaac Sim runner
│   ├── ros2_fjt_proxy.py            # ROS 2 action server proxy
│   ├── moveit_intent_bridge.py      # 41 intents → MoveIt
│   ├── vr_teleop_node.py            # OpenVR controller node
│   ├── start_moveit_stack.ps1       # MoveIt stack launcher
│   ├── sim2real_bridge.py           # Real-robot bridge
│   ├── build_demo_v3.py             # Demo video builder
│   ├── ci_checks.py                 # Automated checks
│   └── tiago_move_group_working.yaml
├── src/
│   ├── app/                         # Next.js pages + API routes
│   ├── components/                  # UI components (Sidebar, Tooltips, Dialogs)
│   ├── server/                      # Runners (local + SSH), batch executor
│   └── lib/
├── SCENE_RATING.md
├── README.md
└── package.json
```

## License

Licensed under the [Apache License 2.0](LICENSE). Copyright © 2026 SyntetiQ.

See `NOTICE` for attribution.
