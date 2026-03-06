# Tiago MoveIt Setup (Windows)

This guide describes how to build and run `tiago_moveit_config` for MoveIt2 on Windows, and how to use the MoveIt Intent Bridge with Tiago.

## Prerequisites

- ROS2 Humble (e.g. via Mambaforge + robostack-humble)
- MoveIt2 installed: `mamba install -c conda-forge -c robostack-humble ros-humble-moveit`
- Tiago simulation packages (optional, for full simulation)

### Install colcon (required for building)

RoboStack may not include colcon by default. Install it:

```powershell
conda activate ros2_humble
mamba install -c conda-forge colcon-common-extensions
```

If `colcon-common-extensions` is not found, try:

```powershell
mamba install -c conda-forge ros-dev-tools
```

## tiago_moveit_config from Source

The official `tiago_moveit_config` package is maintained by PAL Robotics. On Windows, it typically needs to be built from source since it may not be available in RoboStack.

### 0. Install build tools (if missing)

If `colcon` is not found after sourcing ROS2, install it:

```powershell
conda activate ros2_humble
mamba install -c conda-forge colcon-common-extensions
```

If `ros-humble-tiago-description` is needed (for URDF/xacro), try:

```powershell
mamba install -c conda-forge -c robostack-humble ros-humble-tiago-description
```

### 1. Create a workspace

```powershell
mkdir -p C:\ros2_ws\src
cd C:\ros2_ws\src
```

### 2. Clone tiago_moveit_config (humble-devel branch)

```powershell
git clone -b humble-devel https://github.com/pal-robotics/tiago_moveit_config.git
```

### 3. Install dependencies

```powershell
call C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat
cd C:\ros2_ws
rosdep install --from-paths src --ignore-src -r -y
```

If `rosdep` fails, install dependencies manually. Common packages:

- `ros-humble-tiago-description`
- `ros-humble-xacro`
- `ros-humble-moveit-resources-panda-moveit-config` (for reference)

### 4. Build

**Required**: Visual Studio 2019/2022 or Build Tools (C++ workload). Open **x64 Native Tools Command Prompt for VS** and run:

```cmd
call C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat
cd C:\ros2_ws
colcon build --packages-select tiago_moveit_config
```

If colcon is not in PATH, use: `python -m colcon build --packages-select tiago_moveit_config`

**Without Visual Studio**: Build from source is not possible. Use Panda demo instead (see [moveit_setup.md](moveit_setup.md)); the Intent Bridge with `--robot tiago` will work once tiago_moveit_config is available.

### 5. Source and launch

```powershell
call C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat
call C:\ros2_ws\install\local_setup.bat
ros2 launch tiago_moveit_config moveit_rviz.launch.py
```

Or for simulation:

```powershell
ros2 launch tiago_moveit_config moveit_rviz.launch.py use_sim_time:=true
```

## Planning Groups

Tiago MoveIt config exposes planning groups such as:

- **arm_torso** — arm + torso (recommended for pick/place)
- **arm** — arm only
- **torso** — torso only

## RoboLab Integration

### Launch Profile for Tiago MoveIt

Set **Teleop Launch Template** to launch Tiago MoveIt:

```text
{ROS2_SETUP} && call C:\ros2_ws\install\local_setup.bat && ros2 launch tiago_moveit_config moveit_rviz.launch.py
```

### Intent Bridge for Tiago

Run the bridge with `--robot tiago` so it uses Tiago joint presets and `arm_torso`:

```powershell
call C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat
python scripts\moveit_intent_bridge.py --robot tiago --intent-topic /tiago/moveit/intent
```

Options:

- `--robot tiago` — use Tiago joint presets (arm_torso, base_footprint)
- `--planning-group arm_torso` — planning group (default for Tiago)
- `--frame-id base_footprint` — planning frame (default for Tiago)

### Supported Intents

| Intent            | Description                    |
|-------------------|--------------------------------|
| `go_home`         | Ready pose                     |
| `plan_pick`       | Generic pick (sink-like)       |
| `plan_pick_sink`  | Pick at sink                   |
| `plan_pick_fridge`| Pick at fridge                 |
| `plan_place`      | Place pose                     |

## Isaac Sim + MoveIt

When running the Tiago data collector with `--moveit`, the collector adds an OmniGraph ROS2 Joint State publisher so MoveIt can receive `/joint_states` from the simulated Tiago. Ensure:

1. Isaac Sim is launched with ROS2 bridge enabled (default when using the collector).
2. ROS2 is sourced in the terminal before launching Isaac Sim.
3. `FASTRTPS_DEFAULT_PROFILES_FILE` is set if required by your ROS2 setup.

See [moveit_setup.md](moveit_setup.md) for general MoveIt configuration.
