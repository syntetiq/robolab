# RoboLab

Robotic data collection platform for training manipulation policies. Collects diverse demonstrations in NVIDIA Isaac Sim using PAL Tiago robot, with support for VR teleoperation, autonomous MoveIt-based task execution, and sim-to-real transfer.

```
 Web UI (Next.js)          MoveIt2            Isaac Sim
 ┌─────────────┐      ┌─────────────┐     ┌──────────────────┐
 │  Episodes    │      │ MoveGroup   │     │ data_collector   │
 │  Scenes      │─API──│ Intent      │─IPC─│ tiago.py         │
 │  Profiles    │      │ Bridge      │     │  ├─ Replicator    │
 │  ObjectSets  │      │ FJT Proxy   │     │  ├─ Articulation  │
 └──────┬───────┘      └──────┬──────┘     │  └─ Multi-camera  │
        │                     │            └────────┬─────────┘
        │              ┌──────┴──────┐              │
        │              │ sim2real    │         ┌────┴────┐
        │              │ bridge     │         │ HDF5    │
        │              └──────┬──────┘         │ Export  │
        │                     │               └────┬────┘
        │              ┌──────┴──────┐              │
        └──────────────│ Real Tiago  │         ML Training
                       └─────────────┘
```

## Quick Start

```powershell
# 1. Install & setup
npm install
npx prisma generate
npx prisma db push

# 2. Start web UI
npm run dev                    # http://localhost:3000

# 3. Set Isaac Sim path in Configuration page
# 4. Run a batch collection
.\scripts\run_batch_with_objects.ps1 -Reps 5
```

## Architecture

### Web Application (`src/`)

Next.js 14 app with Prisma/SQLite backend. Manages the full lifecycle of data collection experiments.

| Page | Purpose |
|------|---------|
| `/` | Dashboard |
| `/episodes` | List, create, start/stop data collection runs |
| `/episodes/[id]` | Live episode monitoring with SSE log streaming |
| `/scenes` | Manage simulation environments (USD stages) |
| `/launch-profiles` | Configure Isaac Sim launch parameters |
| `/object-sets` | Define diverse object sets for spawning |
| `/config` | Isaac Sim host, ROS2, streaming settings |

### Robot Control Pipeline (`scripts/`)

#### Core Scripts

| Script | Role |
|--------|------|
| `data_collector_tiago.py` | Isaac Sim episode runner: physics, articulation, cameras, data recording |
| `ros2_fjt_proxy.py` | ROS2 FollowJointTrajectory action servers + `/cmd_vel` subscriber via file-based IPC |
| `moveit_intent_bridge.py` | Translates high-level intents (e.g. `plan_pick_sink`) to MoveIt joint trajectories |
| `vr_teleop_node.py` | OpenVR/SteamVR input to ROS2 Twist commands for VR teleoperation |

#### Data Flow (File-Based IPC)

Isaac Sim cannot import ROS2 natively on Windows. The FJT Proxy bridges this gap:

```
MoveIt MoveGroup ──FJT Action──▶ ros2_fjt_proxy.py ──JSON files──▶ data_collector_tiago.py
                                      │                                     │
                                      ├─ pending_arm_*.json                 ├─ reads & applies via
                                      ├─ done_arm_*.json                    │  ArticulationAction
                                      ├─ joint_state.json  ◀───────────────┤
                                      └─ base_cmd.json                      └─ XFormPrim velocity
```

### MoveIt Configuration

`scripts/tiago_move_group_working.yaml` — self-contained config with:
- **URDF**: torso, right arm (7-DOF), left arm (7-DOF), gripper (2 fingers), head (pan/tilt)
- **SRDF groups**: `arm`, `arm_torso`, `arm_left`, `arm_left_torso`, `gripper`
- **Kinematics**: KDL solver for all groups
- **Controllers**: `arm_controller`, `arm_left_controller`, `torso_controller`, `gripper_controller`

`scripts/tiago_servo_config.yaml` — MoveIt Servo config for real-time VR Cartesian control.

### Available Intents (21 total)

**Manipulation** (right arm):
`go_home`, `plan_pick_sink`, `plan_pick_fridge`, `plan_pick_dishwasher`, `open_close_fridge`, `open_close_dishwasher`, `approach_workzone`

**Left arm**:
`left_plan_pick_sink`

**Bimanual**:
`bimanual_pick_sink`

**Navigation** (mobile base):
`nav_forward`, `nav_backward`, `nav_left`, `nav_right`, `nav_rotate_left`, `nav_rotate_right`, `nav_to_table`, `nav_to_fridge`, `nav_to_sink`

**Combined**:
`nav_pick_place_table_to_sink`

## Scenes

Four production scenes selected from 10 evaluated (see `SCENE_RATING.md`):

| Scene | Tier | Best for |
|-------|------|----------|
| Kitchen_TiagoCompatible.usda | S | Full kitchen: sink, fridge, dishwasher, counters |
| L-Shaped_Modular_Kitchen_TiagoCompatible.usda | S | Multi-zone navigation + manipulation |
| Modern_Kitchen_TiagoCompatible.usda | A | Open-space pick-place, island counter |
| Small_House_Interactive.usd | A | Multi-room navigation, long-horizon tasks |

## Multi-Camera System

Enable via flags on `data_collector_tiago.py`:

| Camera | Flag | Mount Point | Purpose |
|--------|------|-------------|---------|
| Head (camera_0) | always on | `head_2_link` (VR) or fixed overhead | Primary RGB/depth/pointcloud/semantic |
| Wrist (camera_1) | `--wrist-camera` | `arm_tool_link` | Close-up manipulation view |
| External (camera_2) | `--external-camera` | Fixed world position | Scene overview, third-person |

Each camera writes to its own Replicator directory and encodes a separate MP4 video.

## Data Collection

### Single Episode (via web UI)

1. Create episode on `/episodes/new`, select scene + launch profile
2. Click Start — Isaac Sim launches, collects data for specified duration
3. Click Sync — validates artifacts, uploads to DB

### Batch Collection (automated)

```powershell
# Standard batch: 4 scenes x 5 intents x 5 reps = 100 episodes
.\scripts\run_batch_with_objects.ps1 -Reps 5 -DurationSec 50

# Balanced collection: fill under-represented scenes
.\scripts\run_balance_collection.ps1 -TargetPerScenePerIntent 5

# Web API collection: uses Next.js API for DB integration
.\scripts\run_web_collection.ps1
```

### Episode Output Structure

```
episodes/<uuid>/
├── dataset.json              # Per-frame: joints, poses, world objects, timestamps
├── metadata.json             # Scene, task, config info
├── telemetry.json            # Trajectory telemetry
├── dataset_manifest.json     # File listing
├── camera_0.mp4              # Head camera video
├── camera_1_wrist.mp4        # Wrist camera video (if --wrist-camera)
├── camera_2_external.mp4     # External camera video (if --external-camera)
└── replicator_data/          # Replicator output
    ├── rgb_0000.png ...
    ├── distance_to_camera_0000.npy ...
    ├── pointcloud_0000.npy ...
    └── semantic_segmentation_0000.png ...
```

## Dataset Export & Evaluation

### Quality Evaluation

```powershell
# Evaluate all episodes, generate JSON report
python scripts/evaluate_episodes.py --json-report report.json

# Export only successful episodes
python scripts/evaluate_episodes.py --export-list good_eps.txt --min-quality success
```

Metrics computed per episode:
- **arm_travel**: total joint displacement (rad)
- **gripper_delta**: finger position change (grasp detection)
- **object_max_dxy/dz**: object displacement (pick/place detection)
- **object_fell**: fell below z=0
- **arm_idle_ratio**: fraction of idle frames

Classification: **SUCCESS** / **PARTIAL** / **FAIL** with task-specific criteria.

### HDF5 Export

```powershell
python scripts/export_dataset_hdf5.py
python scripts/export_dataset_hdf5.py --last 50 --min-frames 100
```

HDF5 layout (robomimic/LeRobot compatible):

```
/data/<episode_id>/
  obs/
    joint_positions      (T, N_joints) float32
    joint_velocities     (T, N_joints) float32
    robot_pose           (T, 7) float32  [xyz + quaternion]
    world_object_poses   (T, N_objects, 7) float32
    cameras/
      camera_0/rgb_paths           string[]
      camera_1_wrist/rgb_paths     string[]
      camera_2_external/rgb_paths  string[]
  action/
    joint_positions      (T, N_joints) float32  [next-frame targets]
```

### Dataset Validation

```powershell
python scripts/validate_dataset.py --episodes-dir C:\RoboLab_Data\episodes
```

## Sim-to-Real Transfer

### Configuration

`config/sim2real.yaml` defines:
- **Joint mapping**: sim names → real Tiago names (e.g. `arm_1_joint` → `arm_right_1_joint`)
- **Calibration offsets**: measured via `scripts/calibrate_joints.py`
- **Safety limits**: velocity scaling (0.5x), per-joint bounds, max delta clamping
- **Controller config**: real robot ROS2 controller action names
- **Camera topics**: real robot camera ROS2 topics

### Usage

```powershell
# Validate config
python scripts/sim2real_bridge.py --config config/sim2real.yaml

# Calibrate offsets (robot at home pose)
python scripts/calibrate_joints.py --config config/sim2real.yaml --write

# Replay sim episode on real robot (dry run)
python scripts/sim2real_bridge.py --replay C:\RoboLab_Data\episodes\<id> --dry-run

# Live bridge with safety filter
python scripts/sim2real_bridge.py --config config/sim2real.yaml --live

# Full real robot launch
.\scripts\launch_real_tiago.ps1 -Intent plan_pick_sink -DryRun
```

### Safety Filter Pipeline

```
sim joint command → name mapping → offset → position clamp → delta clamp → velocity scale → real robot
```

## CI / Automated Checks

```powershell
python scripts/ci_checks.py
python scripts/ci_checks.py --skip-tsc    # skip TypeScript compilation
```

Checks: Python syntax, YAML validity, MoveIt config consistency, FJT proxy joint coverage, intent bridge completeness.

## Prerequisites

| Component | Version | Purpose |
|-----------|---------|---------|
| Node.js | 20+ | Web UI |
| Python | 3.10+ | Scripts |
| NVIDIA Isaac Sim | 4.x | Simulation |
| ROS2 Humble | (Mambaforge) | Robot control |
| MoveIt2 | ros-humble-moveit | Motion planning |
| h5py | latest | Dataset export |
| PyYAML | latest | Config parsing |

### Windows-specific

```powershell
# ROS2 + MoveIt via Mambaforge
mamba create -n ros2_humble -c conda-forge -c robostack-staging ros-humble-desktop ros-humble-moveit
mamba activate ros2_humble

# Python deps
pip install h5py pyyaml numpy
```

## Project Structure

```
robolab/
├── config/
│   └── sim2real.yaml              # Sim-to-real joint mapping & safety
├── prisma/
│   ├── schema.prisma              # DB schema (Episode, Scene, ObjectSet, etc.)
│   └── dev.db                     # SQLite database
├── scripts/
│   ├── data_collector_tiago.py    # Isaac Sim data collector
│   ├── ros2_fjt_proxy.py          # ROS2 FJT action server proxy
│   ├── moveit_intent_bridge.py    # Intent → MoveIt translator
│   ├── sim2real_bridge.py         # Safety bridge for real robot
│   ├── calibrate_joints.py        # Joint offset calibration
│   ├── evaluate_episodes.py       # Episode quality evaluation
│   ├── export_dataset_hdf5.py     # HDF5 dataset export
│   ├── validate_dataset.py        # Dataset file validation
│   ├── generate_object_assets.py  # USD object asset generator (30 objects)
│   ├── ci_checks.py               # Automated CI validation
│   ├── run_batch_with_objects.ps1  # Batch collection orchestrator
│   ├── run_balance_collection.ps1  # Dataset balancing script
│   ├── run_web_collection.ps1     # Web API-driven collection
│   ├── launch_real_tiago.ps1      # Real robot launch stack
│   ├── tiago_move_group_working.yaml  # MoveIt config (URDF+SRDF+controllers)
│   └── tiago_servo_config.yaml    # MoveIt Servo for VR
├── src/
│   ├── app/                       # Next.js pages & API routes
│   ├── components/                # React UI components
│   ├── server/                    # Backend logic (runners, orchestration)
│   └── lib/                       # Utilities (Prisma, schemas)
├── SCENE_RATING.md                # Scene evaluation & selection rationale
└── README.md
```

## Testing

```powershell
npm run test                     # Vitest unit tests
python scripts/ci_checks.py     # Script & config validation
```
