# Sample data — `data/episodes/`

This folder ships **one** illustrative episode collected during MS3
development of the SyntetiQ RoboLab platform. It is intended for
reviewers and new contributors to inspect the data layout, validate
the import path, and run the dataset-export tooling end-to-end without
having to first run a fresh Isaac Sim collection. **It is not a
training-grade dataset** — see "Recording your own episodes" below for
how to generate full datasets.

## What ships in this folder

| Episode UUID | Task | Duration | Cameras | Notes |
|---|---|---|---|---|
| `4c4390a3-44d4-479f-8228-ebc9d391bafc` | choreography (fwd 1m arms-forward → right 1m arms-down → right 1m Y-pose → rotate 90° CW heart-pose) | 49 s | head, side, top (RGB) | seed = 42; recorded 2026-03-12 |

Files inside the episode folder:

| File | Size | Purpose |
|---|---|---|
| `camera_0.mp4` | ~795 KB | Head-camera RGB video (front view) |
| `camera_1.mp4` | ~824 KB | Side-camera RGB video |
| `camera_2.mp4` | ~750 KB | Top-camera RGB video |
| `metadata.json` | ~800 B | Episode definition (id, scene, sensors, seed, status, timestamps, output dir, notes) |
| `telemetry.json` | ~8.4 MB | Per-frame trajectory in the map frame (joint positions and velocities, base pose, world-object poses) |

For the full per-episode artefact contract (including `dataset.json`,
`physics_log.json`, `task_results.json`, `dataset_manifest.json`, and
the `replicator_*/` sub-folder with depth maps, point clouds and
semantic segmentation), see the **Episode output structure** section
of the root `README.md`. The bundled sample omits the `replicator_*`
sub-folder to keep the repository checkout small; fresh recordings
write the full set.

## Recording your own episodes

Three ways to record real data:

1. **Web console (single episode).** Start the dev server (`npm run
   dev`), open `http://localhost:3000/episodes/new`, run the 5-step
   wizard. New episodes are written to `data/episodes/<new-uuid>/`.

2. **Batch queue (web).** `http://localhost:3000/batches` queues N
   episodes with incrementing seeds; the polling engine auto-advances
   when an episode completes or fails.

3. **CLI (headless).** From a PowerShell shell on Windows:

   ```powershell
   .\scripts\run_batch_with_objects.ps1 -Reps 5 -DurationSec 50
   .\scripts\run_balance_collection.ps1 -TargetPerScenePerIntent 5
   .\scripts\run_mass_collection.ps1
   ```

All three paths require a running Isaac Sim host (configured via the
`/config` page or the `ISAAC_SIM_HOST` environment variable) and a
working MoveIt 2 stack — see the **Prerequisites** section of the
root `README.md`.

## Sharing larger datasets

Recordings of full batch runs are typically too large for the
repository (each episode with all `replicator_*/` artefacts can reach
hundreds of MB). Recommended distribution channels:

- Internal: shared bucket / cloud drive, with a manifest of episode UUIDs.
- External: a Zenodo dataset record, separate from the source-code DOI.

See `docs/delivery_report.md` for the MS3 delivery summary and
`docs/sample_data.md` (if present) for any reproducibility notes
specific to a given dataset release.
