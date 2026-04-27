# Experiment 3: fridge handle dimensions and simulation sensors

## 1. Fridge handle dimensions (fixed kitchen)

Source: `scenes/kitchen_fixed/kitchen_fixed_config.yaml` → `furniture.fridge.handle`.

| Parameter | Value | Description |
|-----------|-------|-------------|
| **type** | vertical | Vertical handle |
| **length** | **0.50 m** | Handle height (vertical) |
| **width** | **0.06 m** | Width (horizontal along the door) |
| **depth** | **0.06 m** | Depth (protrusion from the door) |
| **standoff** | 0.06 m | Gap between the door and the handle |
| **center_height** | 1.10 m | Height of the handle centre above the floor |

In the code (`kitchen_fixed_builder.py`) the handle is assembled as a `Bar` cuboid with dimensions **depth × width × length** = **0.06 × 0.06 × 0.50 m** and two brackets (Bracket0, Bracket1). Scene path: `/World/Kitchen/Furniture/Fridge/Door/Handle`.

**Handle dimensions summary:** 6 cm × 6 cm × 50 cm (depth × width × height).

---

## 2. Sensors used during simulation (test_robot_bench)

### 2.1 Cameras (Replicator, video recording)

When launched with video (`run_task_config.ps1` without `-NoVideo`) 3 cameras are created:

| Camera | Position (approximate) | Direction | Data |
|--------|----------------------|-----------|------|
| **top_kitchen** | (0, 1.7, 7) | Down onto the kitchen | RGB, every frame → `replicator_top_kitchen/rgb_*.png` → encoded as `top_kitchen.mp4` |
| **isometric_kitchen** | (-3.5, -2, 3.5) | Towards the kitchen centre | Same → `isometric_kitchen.mp4` |
| **front_kitchen** | (0, -2, 1.5) | Front view of the kitchen | Same → `front_kitchen.mp4` |

Resolution is set via the arguments `--width`, `--height` (default 640×480). **Data:** RGB images only; they are not fed into the robot control logic (recording only, for analysis and datasets).

### 2.2 Robot state (logging and control)

Data from **Articulation** (Isaac Sim) is used:

| Data | Source | Usage |
|------|--------|-------|
| **Base position and orientation** | `articulation.get_world_pose()` | Navigation, approach target point calculation, yaw calculation |
| **Joint positions (DOF)** | `articulation.get_joint_positions()` | Arm/gripper control, pose checking (pre_grasp_handle, handle_reach_left, etc.) |
| **Joint velocities** | `articulation.get_joint_velocities()` | Optionally in the logger (physics_log), not in door control |
| **EE (tool/gripper) link position** | Via `get_prim_world_pose(ee_link_path)` over USD | Distance to handle, transition to pull_or_push |

The exact DOF names are defined in `resolve_dof_names(articulation)` (all revolute and prismatic joints of the robot, including wheels, torso, arms, gripper).

### 2.3 Scene (for door logic)

| Data | Source | Usage |
|------|--------|-------|
| **Handle position in world** | `get_prim_world_position(handle_usd_path)` | Approach target (drive_to_handle), distance to gripper |
| **Door angle** | RevoluteJoint or door primitive orientation | Success criterion for open/close (min_angle_deg / max_angle_deg) |
| **Hinge position (hinge_world_xy)** | From the task configuration | Pull/push direction along the tangent to the door arc |

### 2.4 What is absent from test_robot_bench

- **Tactile/contact sensors** are not used in the bench. In `data_collector_tiago.py` for the real/VR scenario there are contact sensors on the gripper fingers (Contact_Sensor on the left/right finger link) — they are absent in the bench simulation.
- **Depth/Lidar** are not used.
- **Joint forces/torques** are not read for control purposes.

---

## 3. Saving episode video

When launched **with video** (without `-NoVideo`):

- Output folder: `C:\RoboLab_Data\episodes\fixed_fridge_experiment3_<timestamp>\`
- Videos are located in the `heavy\` subfolder:
  - `top_kitchen.mp4`
  - `isometric_kitchen.mp4`
  - `front_kitchen.mp4`

Command for a single run with video:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_task_config.ps1 -Config config/tasks/fixed_fridge_experiment3.json
```

Videos are encoded from Replicator PNG frames after the simulation and saved automatically.
