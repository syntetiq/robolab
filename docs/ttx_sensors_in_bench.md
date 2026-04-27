# Sensors per Technical Specifications in the Bench Scene (test_robot_bench)

## Which Sensors Are Specified per TIAGo (PAL) Technical Specs

Per the specification and the implementation in `data_collector_tiago.py`, the following sensors are available for TIAGo in simulation:

| Sensor | Description | Data |
|--------|-------------|------|
| **Head camera** | Camera on the head (`head_2_link`) | RGB, depth (distance_to_camera), pointcloud, semantic |
| **Wrist camera** | Camera on the arm link (`arm_tool_link`) | RGB, depth, pointcloud |
| **External camera** | Fixed camera in the world | RGB, depth (optional) |
| **Contact sensors** | On gripper fingers (left/right finger link) | Contacts/forces during grasping |

In **test_robot_bench**, by default only **fixed scene cameras** (top_kitchen, isometric_kitchen, front_kitchen) are used, and there are **no** robot-mounted cameras, depth, or contact sensors.

---

## How to Enable Robot Sensors per Technical Specs in the Bench Scene

### 1. Enable sensors via launch flags

The following keys have been added to `run_task_config.ps1` (passed to `test_robot_bench.py`):

- `-RobotHeadCamera` — camera on `head_2_link`
- `-WristCamera` — camera on `arm_tool_link`
- `-ExternalCamera` — fixed external camera
- `-ReplicatorDepth` — write depth (distance_to_camera) and pointcloud
- `-ContactSensors` — enable contact sensors on gripper fingers

Examples:

```powershell
# Robot head camera (first-person view) and depth
.\scripts\run_task_config.ps1 -Config config/tasks/fixed_fridge_experiment3.json -RobotHeadCamera -ReplicatorDepth

# Full set per technical specs: head + wrist + external camera + depth + contact sensors
.\scripts\run_task_config.ps1 -Config config/tasks/fixed_fridge_experiment3.json -RobotHeadCamera -WristCamera -ExternalCamera -ReplicatorDepth -ContactSensors
```

### 2. Enable sensors via task configuration

In the task JSON configuration file (e.g. `fixed_fridge_experiment3.json`) you can add a `sensors` section:

```json
{
  "sensors": {
    "robot_head_camera": true,
    "wrist_camera": false,
    "external_camera": true,
    "replicator_depth": true,
    "contact_sensors": true
  }
}
```

If this section is present, the bench will set the corresponding flags before initialising cameras and sensors.

### 3. Where the data is stored

- **Video:** in the episode folder `heavy/`:
  `head_robot.mp4`, `wrist_robot.mp4`, `external_robot.mp4` (if enabled),
  plus as before `top_kitchen.mp4`, `isometric_kitchen.mp4`, `front_kitchen.mp4`.
- **Depth/pointcloud:** in Replicator subdirectories, e.g.
  `replicator_head_robot/distance_to_camera_*.npy`, `pointcloud_*.npy` (if `replicator_depth` is enabled).
- **Contact sensors:** data is available via the Isaac Sim ContactSensor API during simulation; if needed, it can be logged to physics_log or a separate file.

---

## Summary

- To enable robot sensors per technical specs in the bench scene: turn on **robot-head-camera** (and optionally wrist, external, replicator-depth, contact-sensors) via **flags** or via the **sensors** section in the task configuration.
- After that, the scene will utilise the head camera (and optionally the wrist and external cameras); with depth enabled — Replicator depth/pointcloud data; and with contact-sensors enabled — contact sensors on the gripper, as in data_collector and per the technical specifications.
