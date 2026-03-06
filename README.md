# RoboLab MVP Console

A self-hosted MVP web application operator console for configuring and running teleoperation data-collection experiments in Isaac Sim using TIAGo Omni / TIAGo++.

## Features

- **Configuration Management**: Configure Isaac Sim host, user, ROS2 topics, streaming methods.
- **Scene and Object Set Management**: Maintain a library of scenes and object sets for task diversity.
- **Launch Profiles**: Customizable ROS and Isaac Sim command templates per runner type.
- **Episodes (Data Collection Runs)**: Step-by-step wizard to define metadata (Tasks, Sensors, Duration) and execute data logging safely.
- **Runner Abstraction**: Expandable architecture to run jobs locally (`LOCAL_RUNNER`), remotely via SSH (`SSH_RUNNER`), or via future agent orchestrators (`AGENT_RUNNER`).
- **Interactive UI**: Clean, responsive layout with Tailwind CSS and Next.js App Router. Features Server-Sent Events (SSE) for live streaming logs and status updates to the Episode Detail page.

## Prerequisite

- Node.js 20+
- npm

## Setup & Run

1. **Install Dependencies**
   ```bash
   npm install
   ```

2. **Initialize Database**
   Since this uses SQLite, Prisma schema is pre-configured. Generate the client and run the seed script:
   ```bash
   npx prisma generate
   npx prisma db push
   npx prisma db seed
   ```
   > The seed script automatically supplies Windows-local defaults for Isaac Sim (`localhost`, `LOCAL_RUNNER`, `C:\RoboLab_Data`), plus scenes for Home and Office, and a demo Object Set.

3. **Run Development Server**
   ```bash
   npm run dev
   ```
   The application will be accessible at [http://localhost:3000](http://localhost:3000).

4. **Set Local Isaac Sim Path**
   In `Configuration -> Isaac Sim Install Path`, set your local Isaac Sim folder (must contain `python.bat`), for example:
   ```text
   C:\Users\<your-user>\Documents\IsaacSim
   ```

5. **Generate Interactive Data-Collection Scenes**
   Build both `Small House` and `Office` interactive environments with deterministic object variability:
   ```bash
   "C:\Users\<your-user>\Documents\IsaacSim\python.bat" scripts\create_interactive_scenes.py --scene all --output-dir "C:\RoboLab_Data\scenes" --seed 42
   ```
   Generated scene files:
   - `C:\RoboLab_Data\scenes\Small_House_Interactive.usd`
   - `C:\RoboLab_Data\scenes\Office_Interactive.usd`

## Tiago Dataset Pipeline (Milestone 1)

- The default episode runner script is `data_collector_tiago.py`.
- Scene path resolution order for episode launch:
  1. Launch profile `environmentUsd`
  2. Episode scene `stageUsdPath`
  3. Fallback `C:\RoboLab_Data\scenes\Small_House_Interactive.usd`
- Collector output now includes:
  - `dataset.json` (frames with map-frame robot pose, joints with velocity, world poses)
  - `dataset_manifest.json`
  - `telemetry.json`
  - `camera_0.mp4`
  - `replicator_data/` (rgb, depth, pointcloud, semantic outputs)

### Runtime Validation

On episode stop/completion and sync, RoboLab validates required artifacts. If files are missing or `dataset.json` is incomplete, the episode transitions to `failed` with validation details in `notes`.

Required files:
- `metadata.json`
- `dataset.json`
- `dataset_manifest.json`
- `telemetry.json`
- `camera_0.mp4`

## Milestone 2: VR + MoveIt Hooks

RoboLab now exposes first-class VR/MoveIt integration hooks via Launch Profiles:

- `enableVrTeleop`: enables `--vr` collector mode and VR session controls in Episode UI.
- `enableMoveIt`: enables `--moveit` collector mode and MoveIt action controls in Episode UI.
- `robotPovCameraPrim`: controls POV camera parent prim (for robot-view teleoperation).

### Collector Flags

When the profile enables these modes, runners pass:

- `--vr`
- `--moveit`
- `--robot_pov_camera_prim "<prim path>"`

The collector stores these settings in `dataset.json -> metadata`:

- `vr_teleop_enabled`
- `moveit_mode_enabled`
- `robot_pov_camera_prim`

### Teleop Template Tokens

`teleopLaunchTemplate` supports token replacement for VR/MoveIt session commands:

- `{EPISODE_ID}`
- `{OUTPUT_DIR}`
- `{SCENE_USD}`
- `{ACTION}`
- `{ROS2_SETUP}` — value of ROS2 Setup Command (from config or launch profile)

Example:

```text
powershell -Command "echo [TeleopTemplate] {ACTION} for {EPISODE_ID} >> C:\RoboLab_Data\episodes\{EPISODE_ID}_stdout.log"
```

Example for MoveIt session (requires [MoveIt2 setup](#moveit2-setup-windows)):

```text
{ROS2_SETUP} && ros2 launch moveit_resources_panda_moveit_config demo.launch.py
```

### Managed VR/MoveIt Sessions

For `LOCAL_RUNNER`, VR and MoveIt are now managed as explicit sessions:

- `start_vr_session` / `stop_vr_session`
- `start_moveit_session` / `stop_moveit_session`

Behavior:

- start commands launch detached processes and persist PID files under `C:\RoboLab_Data\episodes`.
- stop commands terminate process trees by PID (`taskkill /T`).
- state is persisted in `C:\RoboLab_Data\episodes\<episodeId>_teleop_state.json`.
- teleop event log is written to `C:\RoboLab_Data\episodes\<episodeId>_teleop.log`.

API:

- `GET /api/episodes/{id}/teleop` returns current teleop state (`vrSessionActive`, `moveitSessionActive`, `lastCommand`, `lastError`).

### ROS2 Environment Auto-Setup

To enable real ROS2 command dispatch without manually opening a sourced shell, configure:

- Global: `Configuration -> ROS2 -> ROS2 Setup Command`
- Per launch profile override: `ROS2 Setup Command Override`

Typical Windows value:

```text
call C:\dev\ros2_humble\local_setup.bat
```

When set, teleop bridge executes:

- `<setup command> && ros2 ...`

before default ROS2/MoveIt commands and probes.

### MoveIt2 Setup (Windows)

To get `moveitAvailable: true` in teleop status, install MoveIt2 and configure the teleop template. See [docs/moveit_setup.md](docs/moveit_setup.md) for:

- Mamba install: `ros-humble-moveit`, `ros-humble-moveit-resources-panda-moveit-config`
- `teleopLaunchTemplate`: `{ROS2_SETUP} && ros2 launch moveit_resources_panda_moveit_config demo.launch.py`
- **Intent Bridge** (`scripts/moveit_intent_bridge.py`): subscribes to `/tiago/moveit/intent` and sends MoveGroup goals for `go_home` / `plan_pick`
- Manual run and verification steps

## Testing

This project uses `vitest` for unit tests. To run tests:

```bash
npm run test
```

Tests ensure correctness of Configuration Zod Schemas, the `HostLock` concurrent episode runner locking logic, and the `Runner` factory.

## Future Hooks

- **ROS2 & MoveIt**: Hooks in the Episode runner logic allow injecting pre/post-operation verification scripts.
- **Agent API**: The `AGENT_RUNNER` stub expects cloud-based task definitions in a later iteration.
- **Teleoperation**: The Dashboard and Episode pages render explicit setup instructions when external WebRTC streaming Mode is configured for the Vive VR headsets.

## WebRTC Teleoperation Known Limitations (Isaac Sim on Windows via SSH)

When launching Isaac Sim via the `SSH_RUNNER` with WebRTC streaming enabled (`SimulationApp({ "livestream": 2 })`), be aware of the following Isaac Sim constraints:

1. **Active Display Requirement:** The Isaac Sim host (e.g. Windows PC) **MUST** have an active display attached. If executed headlessly via SSH on a server without a monitor, Isaac Sim will crash during `world.reset()` or fail to initialize the NVENC streaming device (`Couldn't initialize the capture device`, `Net Stream Creation failed, 0x800E8504`). 
   - **Fix:** Start an RDP session into the Windows box before launching, or install a hardware HDMI Dummy Plug.
2. **Absolute USD Paths:** Models loaded via `stage_utils.add_reference_to_stage` must use **Absolute Paths** on the remote target (e.g. `C:/RoboLab_Data/tiago_isaac/...`). Using relative paths will fail because SSH `python.bat` execution runs from the root Isaac Sim directory, causing empty Articulation roots and PhysX access violations.
