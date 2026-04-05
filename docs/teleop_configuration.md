# Tiago Teleoperation Configuration (working, 18.03.2026)

## System Components

### 1. Isaac Sim (data_collector_tiago.py)
- **Script**: `scripts/data_collector_tiago.py`
- **Launch**: via `kit.exe` with flags `--gui --moveit --mobile-base`
- **Scene**: `C:\RoboLab_Data\scenes\kitchen_fixed.usd`
- **Robot**: `/World/Tiago`, starting position `(0.8, 0.0, 0.08)`, yaw=0°
- **Physics**: `world.step(render=True)` — required to advance physics in GUI mode

### 2. MoveIt Stack (start_moveit_stack.ps1)
- **move_group.exe** — MoveIt2 planner, `arm_torso` group
- **ros2_fjt_proxy.py** — IPC bridge: `pending_*.json` → Isaac Sim → `done_*.json`
- **moveit_intent_bridge.py** — listens to `/tiago/moveit/intent`, executes sequences
- **ROS_DOMAIN_ID**: 77, **ROS_LOCALHOST_ONLY**: 1

### 3. Web Application (Next.js)
- **Port**: 3000
- **Launch Profile**: "GUI + MoveIt Teleop (Local)" (`enableGuiMode=true`, `enableMoveIt=true`)
- **Default scene**: "Kitchen Fixed (Experiments 1-3)"

## IPC Protocol

### Base Movement (base_cmd.json)
- **Path**: `C:\RoboLab_Data\fjt_proxy\base_cmd.json`
- **Format**: `{"vx": 0.3, "vy": 0.0, "vyaw": 0.0}`
- **Writing**: Node.js `fs.writeFileSync` (without BOM!)
- **Reading**: Isaac Sim every frame (60 Hz)
- **Expiry**: file older than 500ms is ignored → robot stops automatically
- **Axes**: `vx` = world +X, `vy` = world +Y, `vyaw` = rotation around Z

### Button → Velocity Mapping
| Button | vx | vy | vyaw |
|--------|-----|-----|------|
| Forward (+X) | +0.3 | 0 | 0 |
| Backward (-X) | -0.3 | 0 | 0 |
| Left (+Y) | 0 | +0.3 | 0 |
| Right (-Y) | 0 | -0.3 | 0 |
| Rotate Left | 0 | 0 | +0.5 |
| Rotate Right | 0 | 0 | -0.5 |
| Stop / E-Stop | 0 | 0 | 0 |

### Position Diagnostics (base_pose.json)
- **Path**: `C:\RoboLab_Data\fjt_proxy\base_pose.json`
- **Format**: `{"x": 0.8, "y": 0.0, "z": 0.08, "yaw_rad": 0.0, "yaw_deg": 0.0, "t": ...}`
- **Update**: every 30 frames (~0.5 sec)

### Arm Control (MoveIt intent)
- **Path**: ROS2 topic `/tiago/moveit/intent` (via `ros2_pub_string.py`)
- **Processing**: `moveit_intent_bridge.py` → sequences `move_direct` / `move` / `gripper`
- **IPC**: `pending_*.json` → Isaac Sim → `done_*.json` in `C:\RoboLab_Data\fjt_proxy\`

### Joint State (joint_state.json)
- **Path**: `C:\RoboLab_Data\fjt_proxy\joint_state.json`
- **Writing**: Isaac Sim every frame
- **Reading**: `moveit_intent_bridge.py` for current joint positions

## Launch Order

1. `npm run dev` — web app on port 3000
2. Create an episode (scene: Kitchen Fixed, profile: GUI + MoveIt Teleop)
3. Click "Start Episode" → launches Isaac Sim with `--gui --moveit --mobile-base`
4. Wait for loading (~90 sec), verify that `joint_state.json` is being updated
5. `scripts/start_moveit_stack.ps1 -RosDomainId 77` → MoveIt stack (~15 sec)
6. Open the episode page → Teleoperation Control Panel

## Important Details

- **BOM**: PowerShell `Out-File -Encoding utf8` adds BOM — Python cannot parse it. Use `[System.IO.File]::WriteAllText()` or Node.js `fs.writeFileSync()`.
- **`simulation_app.update()` vs `world.step()`**: DO NOT use `simulation_app.update()` in the main loop — it does not advance physics. Only `world.step(render=True)`.
- **`--mobile-base`**: without this flag the base is fixed, `base_cmd.json` is ignored.
- **Home Kitchen** (`Small_House_Interactive.usd`): disabled (`enabled=false`), do not use.

## Available MoveIt Commands (arm + gripper)

| UI Command | Intent | Action |
|------------|--------|--------|
| MoveIt Home | `go_home` | Arm to neutral pose (move_direct) |
| Plan Pick | `plan_pick` | Open gripper → pre-grasp → grasp → close → lift → to sink → open → home |
| Plan Place | `plan_place` | To location → open gripper → home |
| Pick Sink | `plan_pick_sink` | Same as plan_pick, target — sink |
| Pick Fridge | `plan_pick_fridge` | Same as above, target — fridge |
| Approach Workzone | `approach_workzone` | Arm to working zone in front of the table |
| Open/Close Fridge | `open_close_fridge` | Drive up → grasp handle → pull → release → close |
| Grasp Mug | `grasp_mug` | Via teleop intent (not MoveIt) |
