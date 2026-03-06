# MoveIt2 Setup (Windows)

This guide describes how to install MoveIt2 on Windows using RoboStack and configure RoboLab so that `moveitAvailable` becomes `true` in the teleop status.

## Prerequisites

- ROS2 Humble already installed (e.g. via Mambaforge + robostack-humble)
- ROS2 setup command configured in RoboLab (Configuration or Launch Profile)

## Installation

1. Activate your ROS2 conda environment:
   ```powershell
   conda activate ros2_humble
   ```

2. Install MoveIt2, Panda demo config, and ros2_control (required by demo):
   ```powershell
   mamba install -c conda-forge -c robostack-humble ros-humble-moveit ros-humble-moveit-resources-panda-moveit-config ros-humble-controller-manager ros-humble-ros2-control
   ```

3. Verify installation:
   ```powershell
   ros2 pkg list | findstr moveit
   ```

## Running MoveIt (Panda Demo)

The Panda demo launches `move_group` (which exposes `/move_action`) plus RViz and robot state publishers. To run manually:

```powershell
call C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat
ros2 launch moveit_resources_panda_moveit_config demo.launch.py
```

RViz will open with the Panda robot. The teleop bridge detects MoveIt when `ros2 action list` contains `/move_action` or `/move_group`.

## RoboLab Integration

### teleopLaunchTemplate for start_moveit_session

In your Launch Profile, set **Teleop Launch Template** to:

```text
{ROS2_SETUP} && ros2 launch moveit_resources_panda_moveit_config demo.launch.py
```

Ensure **ROS2 Setup Command** is configured (global or per-profile), for example:

```text
call C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat
```

When you click **Start MoveIt Session** in the Episode page, RoboLab will launch the Panda demo in a detached process. After a few seconds, `moveitAvailable` should become `true` in the teleop status.

### Stopping the Session

Click **Stop MoveIt Session** to terminate the MoveIt process (RViz and move_group).

### MoveIt Intent Bridge (intent → MoveGroup action)

The UI buttons `moveit_plan_pick` and `moveit_go_home` publish to `{namespace}/moveit/intent` (e.g. `/tiago/moveit/intent`). To turn these into real MoveGroup action calls, run the **Intent Bridge** in a separate terminal:

1. Start the MoveIt demo first (see above).
2. In a new terminal, with ROS2 sourced (use your env's python if conda not in PATH):
   ```powershell
   call C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat
   C:\Users\max\Mambaforge\envs\ros2_humble\python.exe C:\path\to\robolab\scripts\moveit_intent_bridge.py
   ```
   Or: `conda activate ros2_humble` then `python scripts/moveit_intent_bridge.py` from the project root.
3. The bridge subscribes to `/tiago/moveit/intent` and sends goals to `/move_action`:
   - `go_home` → Panda "ready" pose
   - `plan_pick` → Panda "extended" pose (placeholder)

Options:
- `--intent-topic /tiago/moveit/intent` — intent topic (default)
- `--move-action /move_action` — MoveGroup action name
- `--planning-group panda_arm` — planning group (use `arm_torso` for Tiago)
- `--robot panda|tiago` — robot type (default: panda)
- `--frame-id` — planning frame (default: panda_link0 for Panda, base_footprint for Tiago)

Supported intents: `go_home`, `plan_pick`, `plan_pick_sink`, `plan_pick_fridge`, `plan_place`.

For Tiago with MoveIt, run the bridge with:
```powershell
python scripts/moveit_intent_bridge.py --robot tiago --planning-group arm_torso
```

## Tiago MoveIt

See [tiago_moveit_setup.md](./tiago_moveit_setup.md) for building and launching `tiago_moveit_config`. The Panda demo is used here as a minimal, well-supported MoveIt stack to validate the bridge and `moveitAvailable` probe.
