# Tiago MoveIt Working Launch (Windows)

This is a stable fallback launch for Tiago MoveIt on Windows when
`ros2 launch tiago_moveit_config ...` crashes due URDF/SRDF loading issues.

It uses a compact Tiago-compatible MoveIt config from:

- `scripts/tiago_move_group_working.yaml`

## Run

From `cmd.exe`:

```bat
set HOME=%USERPROFILE%
call C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat
C:\Users\max\Mambaforge\envs\ros2_humble\Library\lib\moveit_ros_move_group\move_group.EXE --ros-args --params-file C:\Users\max\Documents\Cursor\robolab\scripts\tiago_move_group_working.yaml
```

## Verify

In another terminal (with the same `local_setup.bat`):

```bat
ros2 action list
```

Expected actions include:

- `/move_action`
- `/execute_trajectory`

By default, this setup expects real trajectory execution from Isaac via direct
`FollowJointTrajectory` servers inside `data_collector_tiago.py`.

If you need a fallback, you can still run fake controllers:

```bat
set HOME=%USERPROFILE%
set ROS_DOMAIN_ID=0
set ROS_LOCALHOST_ONLY=0
call C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat
C:\Users\max\Mambaforge\envs\ros2_humble\python.exe C:\Users\max\Documents\Cursor\robolab\scripts\fake_tiago_trajectory_controllers.py
```

Then action list should include:

- `/arm_controller/follow_joint_trajectory`
- `/torso_controller/follow_joint_trajectory`

## One-command Execute Smoke

To run the full stack (move_group + bridge + smoke + single intent):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tiago_moveit_execute_smoke.ps1 -Duration 30 -RequireRealTiago
```

The orchestration script now does:

- explicit stale-process cleanup (`move_group`, bridge, optional fake controllers),
- PID-based lifecycle for started processes,
- per-run process logs in `logs/exec_smoke/<timestamp>/`,
- readiness gating before single-intent publish (`/joint_states` publisher + arm/torso actions),
- wait-until-result from bridge logs.

Useful options:

```powershell
# Override intent delay (seconds)
powershell -ExecutionPolicy Bypass -File .\scripts\run_tiago_moveit_execute_smoke.ps1 -Duration 30 -IntentDelaySec 12 -RequireRealTiago

# Override wait timeout for final bridge result
powershell -ExecutionPolicy Bypass -File .\scripts\run_tiago_moveit_execute_smoke.ps1 -Duration 30 -IntentResultTimeoutSec 45 -RequireRealTiago
```

To force fake controllers fallback:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tiago_moveit_execute_smoke.ps1 -Duration 30 -UseFakeControllers
```

## Success Criteria

For end-to-end success without fake controllers, expect all of:

- `[Smoke] PASS: All artifacts present`
- `[ExecSmoke] Bridge result: MoveGroup goal succeeded`
- `[ExecSmoke] Done`

At the end of the run, script prints exact paths to `move_group` and bridge logs
for quick debugging.

## Real Isaac Tiago Requirement

For real (non-synthetic) Tiago execution in Isaac, the collector must load a Tiago
USD that contains an articulation root. If the USD is missing or empty, the
collector falls back to synthetic joints.

Use strict mode to fail fast:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tiago_moveit_execute_smoke.ps1 -Duration 30 -RequireRealTiago
```

If this fails, provide a valid Tiago USD via `--tiago-usd` (or `TIAGO_USD_PATH`)
that actually contains articulation data.

Current expected local path:

- `C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional.usd`
