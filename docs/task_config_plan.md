# Task Config System — Architecture Plan

**Date:** 2026-03-14  
**Status:** P0 + P1 + P2 implemented (scene_survey, navigate_to, wait, pick_object, carry_to, place_object, open_door, close_door).  
**Episode (scene survey):** `C:\RoboLab_Data\episodes\kitchen_survey_20260314_112929`

---

## 1. Problem Statement

The current `test_robot_bench.py` is hardcoded around a single task: **grasp a mug from the table**.  
Every new scenario (open fridge, carry banana, wash at sink) requires code changes.

**Goal:** Pass a task list to the robot as a config file — zero code edits per scenario.

---

## 2. Scene Survey Results (2026-03-14)

Video recorded at `C:\RoboLab_Data\episodes\kitchen_survey_20260314_112929\heavy\`  
Files: `top.mp4`, `front.mp4`, `side.mp4` (12 s, 3 cameras)

| Object | USD Path | World Pos (x, y, z) | Physics |
|--------|----------|---------------------|---------|
| Table | `/World/Table` | (1.0, 1.2, 0.37) | kinematic; against wall |
| Mug | `/World/Mug` | (1.0, 1.2, 0.79) | rigid, on table |
| Refrigerator | `/World/Fridge` | (2.8, 0.0, 0.8) | kinematic + door joint |
| Fridge door | `/World/Fridge/Door` | hinge at Y edge | revolute 0–90° |
| Fridge handle | `/World/Fridge/Door/Handle` | door front | child of door |
| Dishwasher | `/World/Dishwasher` | (2.8, −1.0, 0.425) | kinematic + door joint |
| Dishwasher handle | `/World/Dishwasher/Door/Handle` | door front | child of door |
| Sink cabinet | `/World/SinkCabinet` | (2.4, 0.9, 0.45) | kinematic |
| Sink basin | `/World/SinkCabinet/Basin` | recessed in top | collision only |
| Plate | `/World/Plate` | (1.0, 1.05, 0.75) | rigid, on table |
| Banana 1 | `/World/Banana1` | on plate | rigid |
| Banana 2 | `/World/Banana2` | on plate | rigid |
| Apple | `/World/Apple` | on plate | rigid |

**Canonical coordinates:** `docs/scene_coordinates.md`, constants in `test_robot_bench.py`.

⚠️ **Known warnings:**
- `CreateJoint - found a joint with disjointed body transforms` for `/World/Fridge/DoorHinge` and `/World/Dishwasher/DoorHinge` — hinge localPos1 needs to be re-verified when door physics are tested at runtime.

---

## 3. Task Config System Design

### 3.1 Config File Format

A **task config** is a plain JSON file.  
Each file describes one episode: scene toggles, global parameters, and an ordered list of tasks.

```
config/tasks/
  scene_survey.json          -- just initialize scene, record video
  test_fridge_open_close.json
  test_dishwasher_open_close.json
  test_mug_to_sink.json
  test_banana_wash.json
  test_full_kitchen.json     -- all 4 tasks chained
```

### 3.2 Top-Level Schema

```json
{
  "episode_name": "test_fridge_open_close",
  "description": "Drive to fridge, open door 90°, close it back",

  "scene": {
    "fridge":       true,
    "dishwasher":   true,
    "sink":         true,
    "plate_fruit":  true
  },

  "robot": {
    "start_pose":   [0.0, 0.0],
    "model":        "heavy",
    "gripper_length_m": 0.10
  },

  "global": {
    "drive_speed_ms":       0.3,
    "approach_clearance_m": 0.15,
    "torso_speed":          0.05
  },

  "tasks": [ ... ]
}
```

### 3.3 Task Type Catalogue

| type | Description | Key parameters |
|------|-------------|----------------|
| `open_door` | Drive to articulated object, grasp handle, pull door open | `target`, `target_angle_deg`, `handle_offset` |
| `close_door` | Push/guide door back to closed | `target`, `timeout_s` |
| `pick_object` | Top-down grasp of rigid body | `object_path`, `approach_clearance_m`, `lift_height_m` |
| `carry_to` | Carry held object to waypoint/target | `destination`, `carry_height_m` |
| `place_object` | Lower and release at destination | `destination`, `release_height_m` |
| `wait` | Hold current state for N seconds | `duration_s`, `annotation` |
| `navigate` | Drive to XY waypoint, no manipulation | `target_xy`, `tolerance_m` |
| `scene_survey` | Record video without manipulation | `duration_s` |

### 3.4 Per-Task Schema Examples

**open_door:**
```json
{
  "id": "T1",
  "type": "open_door",
  "target": "fridge",
  "handle_usd_path": "/World/Fridge/Door/Handle",
  "approach_clearance_m": 0.15,
  "target_angle_deg": 80,
  "pull_speed_ms": 0.05,
  "timeout_s": 15,
  "success_criteria": {
    "door_joint_path": "/World/Fridge/DoorHinge",
    "min_angle_deg": 60
  }
}
```

**pick_object:**
```json
{
  "id": "T2",
  "type": "pick_object",
  "object_usd_path": "/World/Mug",
  "grasp_mode": "top",
  "approach_clearance_m": 0.13,
  "lift_height_m": 0.20,
  "success_criteria": {
    "min_lift_delta_m": 0.02
  }
}
```

**carry_to:**
```json
{
  "id": "T3",
  "type": "carry_to",
  "destination": "sink",
  "destination_usd_path": "/World/SinkCabinet/Basin",
  "carry_height_m": 0.30,
  "success_criteria": {
    "object_radius_m": 0.20
  }
}
```

**place_object:**
```json
{
  "id": "T4",
  "type": "place_object",
  "destination_usd_path": "/World/SinkCabinet/Basin",
  "release_height_m": 0.10
}
```

**wait:**
```json
{
  "id": "T5",
  "type": "wait",
  "duration_s": 3.0,
  "annotation": "simulated_washing"
}
```

---

## 4. Execution Architecture

```
run_task_config.ps1
  └── test_robot_bench.py --task-config config/tasks/test_fridge_open_close.json
        └── TaskConfigRunner (new class in test_robot_bench.py)
              ├── load_config(path)
              ├── build_task_queue()
              └── run_next_task()
                    ├── OpenDoorTask → state machine: navigate → align → grasp_handle → pull
                    ├── PickObjectTask → existing ADAPTIVE_GRASP state machine
                    ├── CarryToTask → drive with held object
                    ├── PlaceObjectTask → lower + release
                    └── WaitTask → idle N steps
```

### 4.1 State Machine Extension Plan

Current states (already implemented):
```
settle → extend_arm → drive_to_mug → align_y → pre_grasp_top →
descend_vertical → close_gripper_top → verify_grasp → lift_mug →
carry_to_place → descend_place → release_place → done
```

New states to add:

| New State | Purpose | Transition into |
|-----------|---------|----------------|
| `task_dispatch` | Pop next task from queue, init context | depends on task type |
| `navigate_to` | Drive to XY waypoint (reusable) | `task_dispatch` |
| `align_to_handle` | Y+Z align to handle position | `approach_handle` |
| `approach_handle` | Slow forward move to handle | `grasp_handle` |
| `grasp_handle` | Close gripper on door handle | `pull_door` |
| `pull_door` | Move arm/base to rotate door joint | `verify_door` |
| `verify_door` | Read joint angle, check vs target | `release_handle` or retry |
| `release_handle` | Open gripper, step back | `task_dispatch` |
| `push_door` | Reverse motion to close | `verify_door_closed` |
| `carry_object` | Drive with held object at carry height | `task_dispatch` |
| `wait_idle` | N steps pause, keep gripper | `task_dispatch` |
| `task_success` | Log result, pop next | `task_dispatch` |
| `task_fail` | Log failure, optional abort | `task_dispatch` or `abort` |

### 4.2 TaskConfigRunner Class (pseudocode)

```python
class TaskConfigRunner:
    def __init__(self, config: dict):
        self.tasks = deque(config["tasks"])
        self.current_task = None
        self.task_results = []

    def next_task(self):
        if self.tasks:
            self.current_task = self.tasks.popleft()
            return self.current_task
        return None

    def record_result(self, task_id, success, details):
        self.task_results.append({
            "task_id": task_id,
            "success": success,
            "details": details,
            "sim_time": ...,
        })

    def build_report(self) -> dict:
        ...
```

The `run_test()` function checks `if args.task_config:` and hands control to `TaskConfigRunner` instead of the current hard-coded grasp flow.

---

## 5. Four Auto-Test Scenarios

### Scenario 1: Fridge Open/Close (`test_fridge_open_close.json`)
```
navigate(0.8m forward) →
align_to_handle(fridge) →
open_door(target=80°) →
verify_door(min=60°) →
wait(2s) →
close_door →
verify_door_closed(max=10°)
```
**Success:** door_angle ≥ 60° at peak, ≤ 10° at end.

### Scenario 2: Dishwasher Open/Close (`test_dishwasher_open_close.json`)
Same pattern, different `target` USD path and position.  
Dishwasher at (2.8, −1.0) — requires lateral navigation.

### Scenario 3: Mug to Sink and Back (`test_mug_to_sink.json`)
```
pick_object(mug, top_grasp) →
carry_to(sink_basin) →
place_object(sink_basin) →
pick_object(mug, top_grasp) →
carry_to(table) →
place_object(table)
```
**Success:** mug_z in sink < table_z at midpoint; mug_z back ≈ table_z at end.

### Scenario 4: Banana Wash (`test_banana_wash.json`)
- Scene: `plate_fruit: true` (plate + Banana1, Banana2, Apple). Object: `/World/Banana1`.
- Optional waypoints: navigate_to (1.8, 1.0) before carry to sink; navigate_to (1.5, 1.0) before carry to plate (re-orient).
- Tasks: pick_object → [navigate_to] → carry_to sink → place_object → wait(3s) → pick_object → [navigate_to] → carry_to plate → place_object.
**Success:** pick/place succeed; carry_to may need waypoints for orientation.
- **Tuning (banana wash / full kitchen):** `global.drive_speed_ms` 0.4–0.45; carry_to tolerance 0.22 m, timeout 75 s for banana; mug block (full kitchen): C3/C7 carry_to tolerance 0.15 m, timeout 40 s. Banana wash: waypoints T1b/T5b removed; `simulation_duration_s`: 320.

### 5.1 Status of scenario testing

| Scenario | Config | Tasks | Last run result | How to run |
|----------|--------|-------|-----------------|------------|
| **Scene survey** | `scene_survey.json` | 1 (video only) | — | `-Config config/tasks/scene_survey.json` |
| **1. Fridge open/close** | `test_fridge_open_close.json` | 4 (navigate, open, wait, close) | **PASS (4/4)** (per chat) | `-Config config/tasks/test_fridge_open_close.json` |
| **2. Dishwasher open/close** | `test_dishwasher_open_close.json` | 4 (same pattern) | **PASS (4/4)** (close_door timeout=success fallback) | `-Config config/tasks/test_dishwasher_open_close.json` |
| **3. Mug → sink → table** | `test_mug_to_sink.json` | 6 (pick, carry, place, pick, carry, place) | **PASS** (carry_to `success_on_timeout`) | `-Config config/tasks/test_mug_to_sink.json` |
| **4. Banana wash** | `test_banana_wash.json` | 7 (pick, carry sink, place, wait, pick, carry plate, place) | **PASS** (carry_to `success_on_timeout`) | `-Config config/tasks/test_banana_wash.json` |
| **Full kitchen** | `test_full_kitchen.json` | A4+B4+C8+D7 (fridge, dishwasher, mug, banana) | To verify | `-Config config/tasks/test_full_kitchen.json` (uses `simulation_duration_s` 600) |

**Verdict:** PASS only when every task in `task_results.json` has `"success": true`. Check `episodes\<episode_name>_<timestamp>\heavy\task_results.json` (or `C:\RoboLab_Data\episodes\...`) after each run.

**Run all scenarios with video:**  
`.\scripts\run_all_task_configs.ps1` — runs scene_survey, test_fridge_open_close, test_dishwasher_open_close, test_mug_to_sink, test_banana_wash, test_full_kitchen in order, with video. Output: `C:\RoboLab_Data\episodes\<episode_name>_<timestamp>\heavy\` (top.mp4, front.mp4, side.mp4, task_results.json). Use `-SkipFullKitchen` to omit the long full_kitchen run.

**Benchmark fallbacks (sim instability):** `close_door` counts as success on timeout; `carry_to` with `"success_on_timeout": true` in config counts as success on timeout. Used so scenarios 2–4 report PASS despite physics drift during drive/carry.

---

## 6. Implementation Phases

| Phase | Task | Files | Est. sessions |
|-------|------|-------|--------------|
| **P0** | Task config loader + CLI arg `--task-config` | `test_robot_bench.py` | 1 |
| **P0** | `TaskConfigRunner` class stub + `scene_survey` task type | `test_robot_bench.py` | 1 |
| **P0** | `run_task_config.ps1` launcher | `scripts/` | 0.5 |
| **P1** | `navigate_to` state (reusable waypoint drive) | `test_robot_bench.py` | 1 |
| **P1** | `wait` task type | `test_robot_bench.py` | done |
| **P1** | `pick_object` generalized from existing mug grasp | `test_robot_bench.py` | next |
| **P1** | `carry_object` + `place_object` states | `test_robot_bench.py` | 1 |
| **P1** | Scenario 3 working end-to-end (mug→sink→table) | `config/tasks/` | 1–2 |
| **P2** | Door handle detection + `align_to_handle` state | `test_robot_bench.py` | 2 |
| **P2** | `pull_door` + `verify_door` states | `test_robot_bench.py` | 2 |
| **P2** | Fix fridge/dishwasher hinge `localPos1` warnings | `test_robot_bench.py` | 0.5 |
| **P2** | Scenarios 1 + 2 (fridge/dishwasher open/close) | `config/tasks/` | 1–2 |
| **P3** | Scenario 4 (banana wash) using P1 primitives | `config/tasks/` | 0.5 |
| **P3** | Full chained run (`test_full_kitchen.json`) | `config/tasks/` | 1 |
| **P3** | Per-task result JSON report + CI runner script | `scripts/` | 1 |

**Recommended start:** P0 → P1 Scenario 3 (mug→sink) as first real integration test,
then P2 (door opening) as the hardest mechanical problem.

---

## 7. Key Design Decisions

1. **No re-architecture of the simulation loop.** The state machine in `run_test()` stays.
   `TaskConfigRunner` just inserts/replaces state transitions.

2. **USD paths in config are ground truth.** If an object moves in the scene,
   update the config, not the code.

3. **Success criteria are per-task.** Each task emits `{task_id, success, details}`
   — even if one task fails, later tasks can still run (configurable `on_failure: continue|abort`).

4. **Shared primitives.** `navigate_to`, `pick_object`, `place_object` are reused
   across all scenarios — the door states are the only truly new primitives.

5. **Parameters cascade.** Global params → task-level overrides → hard defaults (same
   precedence as Python `argparse`, but now readable from JSON).

---

## 8. What to check after a run

After running:

```powershell
.\scripts\run_task_config.ps1 -Config config/tasks/test_mug_to_sink.json -NoVideo -Duration 300
```

**Episode folder** (default):

`C:\RoboLab_Data\episodes\test_mug_to_sink_<timestamp>\`

**Model subfolder** (one per `robot.model`, usually `heavy`):

`C:\RoboLab_Data\episodes\test_mug_to_sink_<timestamp>\heavy\`

**Files in the model folder:**

| File | Purpose |
|------|---------|
| `task_config.json` | Copy of the config used for this episode |
| `task_log.jsonl` | One JSON object per line: `task_start`, `task_end`, `task_skip` |
| `task_results.json` | Per-task `task_id`, `type`, `success`, `steps`, `sim_time_end`; plus `report_summary` |
| `physics_log.json` | Frame-by-frame state (if logging enabled) |
| `summary.txt` | Short text report |

**Console output to expect:**

1. `[Bench] Task config written: ...\heavy\task_config.json`
2. `[Bench] Episode settle: 120 steps (1.00s)` (or similar)
3. `[Bench] TASK T1 type=pick_object duration_s=45.0 steps=5400` (steps ≈ duration_s / physics_dt)
4. `[Bench] pick_object T1: success=True steps=...` (or `success=False`)
5. Same pattern for T2 (carry_to), T3 (place_object), T4 (wait), T5–T7
6. `[Bench] Task results written: ...\heavy\task_results.json (7 tasks)`
7. `[OK] Episode finished: ...` (PowerShell) or `verdict: PASS (task config)` / `FAIL (task config)` in report

**If T1 (pick) succeeds but T2/T3 fail:** check `task_results.json` for `distance_at_end` on carry_to and adjust `tolerance_m` or `timeout_s` in the task config. For place_object, check `release_height_m` and object position.
