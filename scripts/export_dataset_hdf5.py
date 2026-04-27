#!/usr/bin/env python3
"""
Export collected RoboLab episodes to HDF5 for ML training.

Produces a single HDF5 file compatible with robomimic / LeRobot conventions:
  /data/{episode_id}/obs/joint_positions       (T, N_joints) float32
  /data/{episode_id}/obs/joint_velocities      (T, N_joints) float32
  /data/{episode_id}/obs/robot_pose            (T, 7)        float32
  /data/{episode_id}/obs/world_object_poses    (T, N_objects, 7) float32
  /data/{episode_id}/obs/pointcloud            stored as path references
  /data/{episode_id}/action/joint_positions    obs shifted +1 frame (next-step target)

Metadata is stored as HDF5 attributes on each episode group.

Usage:
  python scripts/export_dataset_hdf5.py
  python scripts/export_dataset_hdf5.py --last 10 --min-frames 50
  python scripts/export_dataset_hdf5.py --episodes-dir D:\\data\\episodes --output out.hdf5
"""

import argparse
import json
import sys
from pathlib import Path

import h5py
import numpy as np


def load_episode(ep_dir: Path) -> dict | None:
    """Load and return parsed dataset.json, or None on failure."""
    ds_path = ep_dir / "dataset.json"
    if not ds_path.exists():
        return None
    try:
        with open(ds_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  SKIP {ep_dir.name}: failed to parse dataset.json: {e}")
        return None


def extract_joint_names(frames: list[dict]) -> list[str]:
    """Collect all joint names across frames, return sorted list."""
    names: set[str] = set()
    for frame in frames:
        names.update(frame.get("robot_joints", {}).keys())
    return sorted(names)


def extract_object_keys(frames: list[dict]) -> list[str]:
    """Collect all world_poses prim paths across frames, return sorted list."""
    keys: set[str] = set()
    for frame in frames:
        keys.update(frame.get("world_poses", {}).keys())
    return sorted(keys)


def build_arrays(
    frames: list[dict],
    joint_names: list[str],
    object_keys: list[str],
) -> dict[str, np.ndarray]:
    """Build numpy arrays from frames.

    Returns dict with keys:
      joint_positions, joint_velocities, robot_pose,
      world_object_poses, timestamps
    """
    T = len(frames)
    N_joints = len(joint_names)
    N_objects = len(object_keys)

    joint_positions = np.zeros((T, N_joints), dtype=np.float32)
    joint_velocities = np.zeros((T, N_joints), dtype=np.float32)
    robot_pose = np.zeros((T, 7), dtype=np.float32)
    world_object_poses = np.zeros((T, N_objects, 7), dtype=np.float32)
    timestamps = np.zeros(T, dtype=np.float64)

    joint_index = {name: i for i, name in enumerate(joint_names)}
    object_index = {key: i for i, key in enumerate(object_keys)}

    for t, frame in enumerate(frames):
        timestamps[t] = frame.get("timestamp", 0.0)

        rj = frame.get("robot_joints", {})
        for name, idx in joint_index.items():
            jdata = rj.get(name, {})
            joint_positions[t, idx] = jdata.get("position", 0.0)
            joint_velocities[t, idx] = jdata.get("velocity", 0.0)

        rp = frame.get("robot_pose", {})
        pos = rp.get("position", [0.0, 0.0, 0.0])
        ori = rp.get("orientation", [0.0, 0.0, 0.0, 1.0])
        robot_pose[t, :3] = pos[:3]
        robot_pose[t, 3:7] = ori[:4]

        wp = frame.get("world_poses", {})
        for key, oi in object_index.items():
            odata = wp.get(key, {})
            opos = odata.get("position", [0.0, 0.0, 0.0])
            oori = odata.get("orientation", [0.0, 0.0, 0.0, 1.0])
            world_object_poses[t, oi, :3] = opos[:3]
            world_object_poses[t, oi, 3:7] = oori[:4]

    return {
        "joint_positions": joint_positions,
        "joint_velocities": joint_velocities,
        "robot_pose": robot_pose,
        "world_object_poses": world_object_poses,
        "timestamps": timestamps,
    }


def collect_pointcloud_paths(ep_dir: Path, subdir: str = "replicator_data") -> list[str]:
    """Return sorted list of pointcloud .npy paths relative to episode dir."""
    rep_dir = ep_dir / subdir
    if not rep_dir.exists():
        return []
    paths = sorted(
        str(p.relative_to(ep_dir))
        for p in rep_dir.glob("pointcloud_*.npy")
    )
    return paths


def collect_rgb_paths(ep_dir: Path, subdir: str = "replicator_data") -> list[str]:
    """Return sorted list of RGB image paths relative to episode dir."""
    rep_dir = ep_dir / subdir
    if not rep_dir.exists():
        return []
    paths = sorted(
        str(p.relative_to(ep_dir))
        for p in rep_dir.rglob("rgb_*.png")
    )
    return paths


def collect_camera_dirs(ep_dir: Path) -> dict[str, str]:
    """Detect available camera replicator directories."""
    cameras = {}
    if (ep_dir / "replicator_data").exists():
        cameras["camera_0"] = "replicator_data"
    if (ep_dir / "replicator_wrist").exists():
        cameras["camera_1_wrist"] = "replicator_wrist"
    if (ep_dir / "replicator_external").exists():
        cameras["camera_2_external"] = "replicator_external"
    return cameras


def resolve_scene_name(dataset: dict, ep_dir: Path) -> str:
    """Best-effort scene name from metadata.json or dataset.json."""
    meta_path = ep_dir / "metadata.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            scene = meta.get("scene", {})
            if scene.get("name"):
                return scene["name"]
        except Exception:
            pass
    env_usd = dataset.get("metadata", {}).get("environment_usd", "")
    if env_usd:
        return Path(env_usd).stem
    return "unknown"


def resolve_task(ep_dir: Path) -> str:
    """Best-effort task label from metadata.json."""
    meta_path = ep_dir / "metadata.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            tasks = meta.get("tasks", "")
            if isinstance(tasks, str) and tasks.startswith("["):
                return tasks
            if isinstance(tasks, list):
                return json.dumps(tasks)
        except Exception:
            pass
    return ""


def write_episode(
    hf: h5py.File,
    episode_id: str,
    arrays: dict[str, np.ndarray],
    pointcloud_paths: list[str],
    joint_names: list[str],
    object_keys: list[str],
    fps: float,
    duration: float,
    scene_name: str,
    task: str,
    camera_data: dict[str, dict] | None = None,
) -> None:
    """Write one episode's data into the HDF5 file."""
    grp = hf.create_group(f"data/{episode_id}")

    obs = grp.create_group("obs")
    obs.create_dataset("joint_positions", data=arrays["joint_positions"], compression="gzip", compression_opts=4)
    obs.create_dataset("joint_velocities", data=arrays["joint_velocities"], compression="gzip", compression_opts=4)
    obs.create_dataset("robot_pose", data=arrays["robot_pose"], compression="gzip", compression_opts=4)

    if arrays["world_object_poses"].shape[1] > 0:
        obs.create_dataset("world_object_poses", data=arrays["world_object_poses"], compression="gzip", compression_opts=4)

    if pointcloud_paths:
        dt = h5py.string_dtype()
        obs.create_dataset("pointcloud_paths", data=pointcloud_paths, dtype=dt)

    # Multi-camera image paths (each camera gets its own dataset).
    if camera_data:
        cam_grp = obs.create_group("cameras")
        dt_str = h5py.string_dtype()
        for cam_name, cam_info in camera_data.items():
            cg = cam_grp.create_group(cam_name)
            if cam_info.get("rgb_paths"):
                cg.create_dataset("rgb_paths", data=cam_info["rgb_paths"], dtype=dt_str)
            if cam_info.get("pointcloud_paths"):
                cg.create_dataset("pointcloud_paths", data=cam_info["pointcloud_paths"], dtype=dt_str)
            cg.attrs["n_rgb"] = len(cam_info.get("rgb_paths", []))
            cg.attrs["n_pointcloud"] = len(cam_info.get("pointcloud_paths", []))
            cg.attrs["replicator_dir"] = cam_info.get("dir", "")

    act = grp.create_group("action")
    act_jp = arrays["joint_positions"]
    action_data = np.empty_like(act_jp)
    action_data[:-1] = act_jp[1:]
    action_data[-1] = act_jp[-1]
    act.create_dataset("joint_positions", data=action_data, compression="gzip", compression_opts=4)

    grp.attrs["fps"] = fps
    grp.attrs["duration"] = duration
    grp.attrs["scene_name"] = scene_name
    grp.attrs["task"] = task
    grp.attrs["n_frames"] = arrays["joint_positions"].shape[0]
    grp.attrs["n_joints"] = len(joint_names)
    grp.attrs["joint_names"] = json.dumps(joint_names)
    grp.attrs["n_objects"] = len(object_keys)
    grp.attrs["object_keys"] = json.dumps(object_keys)
    grp.attrs["n_cameras"] = len(camera_data) if camera_data else 1
    grp.attrs["camera_names"] = json.dumps(list(camera_data.keys()) if camera_data else ["camera_0"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export RoboLab episodes to HDF5 for ML training",
    )
    parser.add_argument(
        "--episodes-dir",
        default=r"C:\RoboLab_Data\episodes",
        help="Root directory containing episode subdirectories",
    )
    parser.add_argument(
        "--output",
        default=r"C:\RoboLab_Data\dataset_export.hdf5",
        help="Output HDF5 file path",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=0,
        help="Only export the N most-recent episodes (0 = all)",
    )
    parser.add_argument(
        "--min-frames",
        type=int,
        default=100,
        help="Skip episodes with fewer than N frames",
    )
    parser.add_argument(
        "--episode-id",
        default="",
        help="Export only this single episode (UUID matching directory name); ignores --last",
    )
    args = parser.parse_args()

    ep_root = Path(args.episodes_dir)
    if not ep_root.exists():
        print(f"ERROR: episodes directory not found: {ep_root}")
        sys.exit(1)

    ep_dirs = sorted(
        [d for d in ep_root.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if args.episode_id:
        ep_dirs = [d for d in ep_dirs if d.name == args.episode_id or d.name.startswith(f"{args.episode_id}_")]
        if not ep_dirs:
            print(f"ERROR: episode directory not found for id={args.episode_id} under {ep_root}")
            sys.exit(1)
    elif args.last > 0:
        ep_dirs = ep_dirs[: args.last]

    # Re-sort chronologically for export order
    ep_dirs.sort(key=lambda d: d.stat().st_mtime)

    print(f"Found {len(ep_dirs)} episode(s) in {ep_root}")
    print(f"Output: {args.output}")
    print(f"Min frames: {args.min_frames}")
    print()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    exported = 0
    skipped_no_data = 0
    skipped_few_frames = 0
    total_frames = 0

    with h5py.File(str(output_path), "w") as hf:
        hf.attrs["format"] = "robolab_v1"
        hf.attrs["source"] = str(ep_root)

        for i, ep_dir in enumerate(ep_dirs, 1):
            ep_id = ep_dir.name
            prefix = f"[{i}/{len(ep_dirs)}]"

            dataset = load_episode(ep_dir)
            if dataset is None:
                print(f"{prefix} SKIP {ep_id[:12]}.. (no dataset.json)")
                skipped_no_data += 1
                continue

            frames = dataset.get("frames", [])
            if len(frames) < args.min_frames:
                print(f"{prefix} SKIP {ep_id[:12]}.. ({len(frames)} frames < {args.min_frames})")
                skipped_few_frames += 1
                continue

            joint_names = extract_joint_names(frames)
            object_keys = extract_object_keys(frames)
            arrays = build_arrays(frames, joint_names, object_keys)
            pc_paths = collect_pointcloud_paths(ep_dir)

            cam_dirs = collect_camera_dirs(ep_dir)
            camera_data: dict[str, dict] = {}
            for cam_name, cam_subdir in cam_dirs.items():
                camera_data[cam_name] = {
                    "dir": cam_subdir,
                    "rgb_paths": collect_rgb_paths(ep_dir, cam_subdir),
                    "pointcloud_paths": collect_pointcloud_paths(ep_dir, cam_subdir),
                }

            timestamps = arrays["timestamps"]
            duration = float(timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else 0.0
            fps = len(frames) / duration if duration > 0 else 0.0

            scene_name = resolve_scene_name(dataset, ep_dir)
            task = resolve_task(ep_dir)

            write_episode(
                hf,
                ep_id,
                arrays,
                pc_paths,
                joint_names,
                object_keys,
                fps=fps,
                duration=duration,
                scene_name=scene_name,
                task=task,
                camera_data=camera_data if len(camera_data) > 0 else None,
            )

            exported += 1
            total_frames += len(frames)
            _cam_str = "/".join(f"{k}:{len(v.get('rgb_paths', []))}" for k, v in camera_data.items())
            print(
                f"{prefix} OK   {ep_id[:12]}.. | "
                f"{len(frames):>5} frames | "
                f"{fps:>5.1f} fps | "
                f"{len(joint_names):>3} joints | "
                f"{len(object_keys)} obj | "
                f"{len(pc_paths)} pc | "
                f"cams: {_cam_str or '0'}"
            )

        hf.attrs["n_episodes"] = exported
        hf.attrs["total_frames"] = total_frames

    print()
    print("=" * 60)
    print(f"Exported: {exported} episodes, {total_frames} total frames")
    print(f"Skipped:  {skipped_no_data} (no data) + {skipped_few_frames} (too few frames)")
    print(f"Output:   {output_path}  ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
