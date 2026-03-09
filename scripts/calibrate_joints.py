#!/usr/bin/env python3
"""
Joint calibration tool for sim-to-real offset measurement.

Procedure:
  1. Move the real robot to a known reference pose (e.g., go_home).
  2. Record the real joint encoder readings.
  3. Compare against the expected sim joint values for the same pose.
  4. Compute offsets and write them to config/sim2real.yaml.

Usage:
  python scripts/calibrate_joints.py --config config/sim2real.yaml
  python scripts/calibrate_joints.py --config config/sim2real.yaml --sim-episode C:/RoboLab_Data/episodes/abc
"""

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

SIM_HOME_POSE = {
    "torso_lift_joint": 0.20,
    "arm_1_joint": 0.20,
    "arm_2_joint": -1.34,
    "arm_3_joint": -0.20,
    "arm_4_joint": 1.94,
    "arm_5_joint": -1.57,
    "arm_6_joint": 1.37,
    "arm_7_joint": 0.0,
    "arm_left_1_joint": 0.20,
    "arm_left_2_joint": -1.34,
    "arm_left_3_joint": -0.20,
    "arm_left_4_joint": 1.94,
    "arm_left_5_joint": -1.57,
    "arm_left_6_joint": 1.37,
    "arm_left_7_joint": 0.0,
    "head_1_joint": 0.0,
    "head_2_joint": -0.50,
}


def read_real_joints_ros2() -> dict[str, float]:
    """Read current joint positions from real robot via /joint_states."""
    try:
        import rclpy
        from sensor_msgs.msg import JointState

        rclpy.init()
        node = rclpy.create_node("calibration_reader")

        result = {}
        received = [False]

        def cb(msg: JointState):
            for i, name in enumerate(msg.name):
                if i < len(msg.position):
                    result[name] = msg.position[i]
            received[0] = True

        node.create_subscription(JointState, "/joint_states", cb, 10)

        print("Waiting for /joint_states (5s)...")
        deadline = time.time() + 5.0
        while not received[0] and time.time() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)

        node.destroy_node()
        rclpy.shutdown()

        if not result:
            print("ERROR: no joint states received")
        return result

    except ImportError:
        print("ERROR: ROS2 not available. Install rclpy.")
        return {}


def read_sim_joints_from_episode(ep_dir: str) -> dict[str, float]:
    """Read first-frame joint positions from a sim episode."""
    ds_path = Path(ep_dir) / "dataset.json"
    if not ds_path.exists():
        print(f"ERROR: {ds_path} not found")
        return {}

    dataset = json.loads(ds_path.read_text(encoding="utf-8"))
    frames = dataset.get("frames", [])
    if not frames:
        print("ERROR: no frames")
        return {}

    joints = frames[0].get("robot_joints", {})
    return {name: data.get("position", 0.0) for name, data in joints.items()}


def compute_offsets(sim_joints: dict, real_joints: dict, mapping: dict) -> dict:
    """Compute offset = real - sim for each joint."""
    offsets = {}
    for sim_name, sim_pos in sim_joints.items():
        real_name = mapping.get(sim_name, sim_name)
        real_pos = real_joints.get(real_name)
        if real_pos is not None:
            offset = real_pos - sim_pos
            offsets[sim_name] = round(offset, 6)
            print(f"  {sim_name:>30s}: sim={sim_pos:+.4f}  real={real_pos:+.4f}  offset={offset:+.6f}")
        else:
            offsets[sim_name] = 0.0
            print(f"  {sim_name:>30s}: sim={sim_pos:+.4f}  real=N/A  offset=0.0")
    return offsets


def update_config(config_path: str, offsets: dict) -> None:
    """Write computed offsets back to the config YAML."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    config["joint_offsets"] = offsets

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"\nOffsets written to {config_path}")


def main():
    parser = argparse.ArgumentParser(description="Joint calibration for sim2real")
    parser.add_argument("--config", default="config/sim2real.yaml")
    parser.add_argument("--sim-episode", type=str, help="Use first frame of sim episode instead of default home pose")
    parser.add_argument("--manual-real", type=str, help="JSON file with manual real joint readings (skip ROS2)")
    parser.add_argument("--write", action="store_true", help="Write offsets to config file")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    mapping = config.get("joint_mapping", {})

    if args.sim_episode:
        print(f"Loading sim poses from episode: {args.sim_episode}")
        sim_joints = read_sim_joints_from_episode(args.sim_episode)
    else:
        print("Using default sim home pose")
        sim_joints = SIM_HOME_POSE

    if args.manual_real:
        print(f"Loading real poses from: {args.manual_real}")
        real_joints = json.loads(Path(args.manual_real).read_text(encoding="utf-8"))
    else:
        real_joints = read_real_joints_ros2()

    if not real_joints:
        print("\nNo real joint data available. Provide --manual-real or connect to robot.")
        print("Example manual file format:")
        print(json.dumps({"arm_right_1_joint": 0.19, "arm_right_2_joint": -1.35}, indent=2))
        sys.exit(1)

    print(f"\nComputing offsets ({len(sim_joints)} joints):")
    offsets = compute_offsets(sim_joints, real_joints, mapping)

    max_offset = max(abs(v) for v in offsets.values()) if offsets else 0.0
    print(f"\nMax absolute offset: {max_offset:.6f} rad")
    if max_offset > 0.1:
        print("WARNING: large offsets detected — verify robot pose matches sim home pose")

    if args.write:
        update_config(args.config, offsets)
    else:
        print("\nDry run — use --write to save offsets to config")


if __name__ == "__main__":
    main()
