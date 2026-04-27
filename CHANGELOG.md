# Changelog

All notable changes to RoboLab. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-04-27 — TZ delivery

First milestone covering the full original technical specification, plus licensing, documentation, dead-code cleanup, and dependency audit.

### Licensing & docs
- Apache License 2.0 (`LICENSE`) and `NOTICE` attribution file.
- `CHANGELOG.md` (this file).
- `README.md` rewritten: 2 procedural scenes (was 4 raw USDZ), 41 MoveIt intents (was 21), batch queue + task editor + demo video sections, VR readiness summary, removed dishwasher references.

### Validated
- YCB asset physics validated via `scripts/validate_tiago_asset.py` (offline USD mode): 19/19 objects have `CollisionAPI` + `RigidBodyAPI` + `MassAPI`. Recommended fine-tuning: contactOffset, restOffset, friction material.

### Cleanup
- Dead code removed (11 files, ~700 LOC): 5 patch scripts (`patch_core_nodes.py`, `patch_webrtc.py`, `patch_remove_tf.py`, `patch_teardown.py`, `patch_graph.py`), 4 completed grasp/approach tuning scripts (`run_approach_sweep_15.ps1`, `run_approach_sweep_then_video.ps1`, `run_gripper_length_sweep.ps1`, `run_gripper_length_sweep_robust.py`), 2 superseded demo builders (`build_demo_v2.py`, `build_demo_slideshow.py`).
- Local `episodes` branch and its remote counterpart (merged via PR #1).

### Security
- npm dependencies: 13 transitive vulnerabilities auto-fixed via `npm audit fix` (`package.json` unchanged). 2 remaining (Next.js 16.1 → 16.2) require explicit upgrade.

---

## TZ feature delivery (also part of 1.0.0)

The release ships the following features that closed the original TZ.

### Added
- **Office environment**: procedural builder (`scenes/office_fixed/office_fixed_builder.py`) with desks, cabinet, chair, whiteboard, printer stand, doors, windows, ceiling grid, baseboards, outlets, and cable trunking.
- **Office task config**: `config/tasks/office_mug_to_desk_side.json` — 5-task pick & place from `desk_main` to `desk_side`.
- **Batch episode queue**: API (`/api/batches/*`), execution engine (`src/server/batchExecutor.ts`, polling-based), and full UI (`/batches`). Runs N episodes with seed-incrementing variation.
- **Visual task editor**: `/experiments` → New Task Config. 6 task types (`navigate_to`, `pick_object`, `carry_to`, `place_object`, `open_door`, `close_door`) with type-specific parameter editors.
- **Object randomisation UI** in episode wizard: layout positions, type shuffling, spawn count, category filters.
- **VR teleoperation infrastructure**:
  - `enableVrTeleop` and `enableVrPassthrough` Launch Profile flags wired to local + SSH runners.
  - WebRTC robot-POV stream auto-opens in browser/SteamVR overlay 15 s after episode start.
  - `scripts/vr_teleop_node.py` (OpenVR/`pyopenvr`) → MoveIt Servo via `/tiago/moveit/intent`.
- **ROS bag recording**: `rosbagLaunchTemplate` Launch Profile field; auto-start with template variable substitution (`{BAG_PATH}`, `{TOPICS}`, `{EPISODE_ID}`); auto-stop on episode end.
- **Demo video builder** (`scripts/build_demo_v3.py`): Playwright web-UI screencast + Isaac Sim multi-camera footage + Pillow title cards + matplotlib telemetry slides → 1920×1080 MP4 with bottom-bar annotations.
- **Inline help tooltips** (~30) across all 8 pages, British English, technical-term explanations.
- **Object Sets in DB**:
  - Kitchen Mixed Objects: 22 USDA assets (mugs, bottles, fruits, containers).
  - Kitchen Tableware: 8 USDA assets (bowls, cans, glasses, plates).
  - YCB Benchmark: 9 representative USDC assets.
- Documentation:
  - `docs/delivery_report.md` — TZ requirements → implementation evidence map.
  - `docs/vr_readiness.md` — Vive Pro 2 hardware smoke-test checklist.
  - 6 docs translated from Russian/Ukrainian to British English.

### Changed
- **Rebrand to SyntetiQ**: clickable link in sidebar, removed all "MVP" references in titles and copy.
- **Sidebar logo** redesigned: compact icon + bold title + subtitle.
- **Episode Detail page** restructured: 1/3 + 2/3 two-column grid, `Live Stream` card hidden when episode is not running, Output Dir shown in full width.
- **Status badges** fixed (was invisible white-on-white): `Completed`, `Running`, `Stopping` use `variant="outline"` with semantic colours.
- **Status field on Episodes list** — colour-coded outline badges with icons.
- **Launch Profiles** — added `VR Passthrough` checkbox under VR Teleoperation, conditionally enabled.
- Switched task config field semantics so `kitchen_scene: "office_fixed"` is accepted alongside `"fixed"`; runner selects builder based on USD basename.
- `scripts/test_scene_assets_regression.py` updated for current procedural builder architecture (was checking legacy `scenes/Office/*.usdz` and `scenes/kitchen/1/` raw meshes).
- `prisma/schema.prisma`: added `enableVrPassthrough Boolean` on `LaunchProfile`; added `EpisodeBatch` table; added `batchId` and `batchIndex` on `Episode`.

### Removed
- All `dishwasher` references (33 files): configs, scripts, docs, DB, intents, scene builders.
- 5 outdated docs: `scene_kitchen.md`, `scene_coordinates.md`, `scene_refrigerator.md`, `kitchen_manipulation_test_plan.md`, `grasp_lift_tuning_plan.md`.
- Duplicate scenes in DB: 4 unused experimental office scenes without USD files; 1 redundant Home Kitchen scene.
- Duplicate Launch Profile: stray "GUI + MoveIt Teleop (Local)" copy.
- Broken scene paths (`C:RoboLab_Datascenesoffice_fixed.usd` — missing backslashes).

### Fixed
- Office Fixed scene path corrected to existing `Office_Interactive.usd`.
- Office Experimental Launch Profile re-enabled; `Headless MoveIt Teleop (3 Cameras)` profile filled missing ROS 2 setup, teleop launch, and stop templates.
- `audit_tiago_lengths.py` UTF-8 BOM removed (was breaking `python_syntax` CI check).
- `VideoPlayerCard.test.tsx` aligned with `VideoArtifact` type (`playUrl` + `downloadUrl`).
- `episodes/[id]/page.tsx` `JSX.Element` → `React.ReactElement` (TypeScript 5 namespace removed).
- Removed `moveit_open_close_dishwasher` from immediate-actions allowlist.

### Security
- 13 npm transitive-dependency vulnerabilities fixed via `npm audit fix` (no `package.json` changes).

---

## Earlier history (pre-delivery)

Prior to v1.0.0 the project iterated through 3 named experiments and a stabilisation phase:

- **Experiment 1** (`fixed_mug_rearrange`): mug pick → carry 20 cm east → place on table.
- **Experiment 2** (`fixed_banana_to_sink`): banana from plate → carry → place in sink basin. Iteration covered grasp orientation, retracted-arm approach, J4 interpolation during settle, and arm retraction after place.
- **Experiment 3** (`fixed_fridge_open_close`, `fixed_fridge_experiment3`): fridge handle pull, body-push strategy, multi-waypoint close navigation, early success detection.
- **Grasp stabilisation phases 1-3**: physics-only control, grasp state machine, target-aware verification, `arm_6` joint limit fixes, wrist drive gain tuning, settle failure detection, IK wrist swing guard.
- **Robot test bench**: choreography, omni-drive, arm poses, FK chain diagnostics, joint control verification, frame roundtrip, asset validation, motion controller smoke tests.
- **Configuration system**: layered hierarchy (`config/grasp_tuning.json`, `config/object_diversity_profile.json`, `config/scene_*.json`, `config/tasks/*.json`, `config/robots/tiago_heavy.yaml`).

See git history for fine-grained commits before tag `v1.0.0`.
