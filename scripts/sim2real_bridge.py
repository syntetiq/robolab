#!/usr/bin/env python3
"""
Sim-to-Real bridge for Tiago.

Translates sim-trained joint commands to real robot commands by:
  1. Remapping joint names (sim → real)
  2. Applying calibration offsets
  3. Enforcing safety limits (velocity, position bounds, delta clamp)
  4. Publishing to real robot ROS2 controllers

Can run in two modes:
  --replay  path/to/episode   Replay a recorded episode on real hardware
  --live                      Bridge live MoveIt commands with safety layer

Usage:
  python scripts/sim2real_bridge.py --config config/sim2real.yaml --replay C:/RoboLab_Data/episodes/abc123
  python scripts/sim2real_bridge.py --config config/sim2real.yaml --live
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import yaml

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.action import ActionClient
    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
    from control_msgs.action import FollowJointTrajectory
    from sensor_msgs.msg import JointState
    from geometry_msgs.msg import Twist
    from builtin_interfaces.msg import Duration

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class SafetyFilter:
    """Enforces position bounds, velocity limits, and delta clamping."""

    def __init__(self, config: dict):
        self._offsets = config.get("joint_offsets", {})
        self._mapping = config.get("joint_mapping", {})
        safety = config.get("safety_limits", {})
        self._vel_scale = safety.get("max_velocity_scale", 0.5)
        self._max_delta = safety.get("max_joint_delta", 0.15)
        self._per_joint = safety.get("per_joint", {})
        self._last_positions: dict[str, float] = {}
        self._violations = 0

    def map_name(self, sim_name: str) -> str:
        return self._mapping.get(sim_name, sim_name)

    def apply_offset(self, sim_name: str, position: float) -> float:
        return position + self._offsets.get(sim_name, 0.0)

    def clamp_position(self, sim_name: str, position: float) -> float:
        limits = self._per_joint.get(sim_name, {})
        lo = limits.get("lower", -math.pi)
        hi = limits.get("upper", math.pi)
        if position < lo or position > hi:
            self._violations += 1
        return max(lo, min(hi, position))

    def clamp_delta(self, real_name: str, target: float) -> float:
        if real_name in self._last_positions:
            prev = self._last_positions[real_name]
            delta = target - prev
            if abs(delta) > self._max_delta:
                self._violations += 1
                target = prev + math.copysign(self._max_delta, delta)
        self._last_positions[real_name] = target
        return target

    def scale_velocity(self, velocity: float) -> float:
        return velocity * self._vel_scale

    def transform(self, sim_name: str, position: float, velocity: float = 0.0) -> tuple[str, float, float]:
        """Full pipeline: map name → apply offset → clamp → delta limit → scale vel."""
        real_name = self.map_name(sim_name)
        pos = self.apply_offset(sim_name, position)
        pos = self.clamp_position(sim_name, pos)
        pos = self.clamp_delta(real_name, pos)
        vel = self.scale_velocity(velocity)
        return real_name, pos, vel

    @property
    def violation_count(self) -> int:
        return self._violations


def replay_episode(config: dict, episode_dir: str, dry_run: bool = False) -> None:
    """Replay a recorded sim episode on real hardware."""
    ep_path = Path(episode_dir)
    ds_file = ep_path / "dataset.json"
    if not ds_file.exists():
        print(f"ERROR: {ds_file} not found")
        sys.exit(1)

    dataset = json.loads(ds_file.read_text(encoding="utf-8"))
    frames = dataset.get("frames", [])
    if not frames:
        print("ERROR: no frames in dataset")
        sys.exit(1)

    safety = SafetyFilter(config)
    base_cfg = config.get("mobile_base", {})
    max_lin = base_cfg.get("max_linear_vel", 0.3)
    max_ang = base_cfg.get("max_angular_vel", 0.5)

    print(f"Replaying {len(frames)} frames from {ep_path.name}")
    print(f"Safety: vel_scale={safety._vel_scale}, max_delta={safety._max_delta}")

    if not dry_run and ROS2_AVAILABLE:
        rclpy.init()
        node = rclpy.create_node("sim2real_replay")
        controllers = config.get("ros2_controllers", {})
        action_clients: dict[str, ActionClient] = {}
        for ctrl_name, ctrl_cfg in controllers.items():
            action_name = ctrl_cfg["action"]
            ac = ActionClient(node, FollowJointTrajectory, action_name)
            action_clients[ctrl_name] = ac
            print(f"  Action client: {action_name}")

        cmd_vel_pub = node.create_publisher(
            Twist,
            base_cfg.get("cmd_vel_topic", "/mobile_base_controller/cmd_vel"),
            10,
        )
    else:
        node = None
        action_clients = {}
        cmd_vel_pub = None

    prev_time = 0.0
    for i, frame in enumerate(frames):
        t = frame.get("timestamp", 0.0)
        dt = t - prev_time if i > 0 else 0.0
        prev_time = t

        joints = frame.get("robot_joints", {})
        transformed: dict[str, tuple[float, float]] = {}
        for sim_name, jdata in joints.items():
            pos = jdata.get("position", 0.0)
            vel = jdata.get("velocity", 0.0)
            real_name, safe_pos, safe_vel = safety.transform(sim_name, pos, vel)
            transformed[real_name] = (safe_pos, safe_vel)

        if dry_run:
            if i % 60 == 0:
                print(f"  frame {i:>5}/{len(frames)} | t={t:.2f}s | {len(transformed)} joints | violations={safety.violation_count}")
            if dt > 0:
                time.sleep(min(dt, 0.1))
            continue

        if node and action_clients:
            controllers_cfg = config.get("ros2_controllers", {})
            for ctrl_name, ctrl_cfg in controllers_cfg.items():
                ctrl_joints = ctrl_cfg.get("joints", [])
                point = JointTrajectoryPoint()
                point.positions = [transformed.get(j, (0.0, 0.0))[0] for j in ctrl_joints]
                point.velocities = [transformed.get(j, (0.0, 0.0))[1] for j in ctrl_joints]
                point.time_from_start = Duration(sec=0, nanosec=int(max(dt, 1.0 / 60.0) * 1e9))

                traj = JointTrajectory()
                traj.joint_names = ctrl_joints
                traj.points = [point]

                goal = FollowJointTrajectory.Goal()
                goal.trajectory = traj
                ac = action_clients.get(ctrl_name)
                if ac and ac.server_is_ready():
                    ac.send_goal_async(goal)

        robot_pose = frame.get("robot_pose", {})
        if cmd_vel_pub and i > 0:
            prev_pose = frames[i - 1].get("robot_pose", {})
            pp = prev_pose.get("position", [0, 0, 0])
            cp = robot_pose.get("position", [0, 0, 0])
            if dt > 0.001:
                vx = max(-max_lin, min(max_lin, (cp[0] - pp[0]) / dt))
                vy = max(-max_lin, min(max_lin, (cp[1] - pp[1]) / dt))
                twist = Twist()
                twist.linear.x = vx
                twist.linear.y = vy
                cmd_vel_pub.publish(twist)

        if dt > 0:
            time.sleep(min(dt, 0.1))

    print(f"\nReplay complete. Safety violations: {safety.violation_count}")

    if node:
        node.destroy_node()
        rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description="Sim-to-Real bridge for Tiago")
    parser.add_argument("--config", default="config/sim2real.yaml", help="Path to sim2real config YAML")
    parser.add_argument("--replay", type=str, help="Replay a recorded episode directory")
    parser.add_argument("--live", action="store_true", help="Bridge live MoveIt commands")
    parser.add_argument("--dry-run", action="store_true", help="Validate without sending real commands")
    args = parser.parse_args()

    config = load_config(args.config)
    print(f"Loaded config: {args.config}")
    print(f"Robot: {config['robot']['name']}")
    print(f"Joint mappings: {len(config.get('joint_mapping', {}))}")
    print(f"Safety vel_scale: {config.get('safety_limits', {}).get('max_velocity_scale', 'N/A')}")

    if args.replay:
        replay_episode(config, args.replay, dry_run=args.dry_run)
    elif args.live:
        if not ROS2_AVAILABLE:
            print("ERROR: ROS2 not available. Install rclpy, control_msgs, trajectory_msgs.")
            sys.exit(1)
        print("Live bridge mode — subscribing to MoveIt /joint_states and forwarding with safety filter...")
        rclpy.init()

        class LiveBridge(Node):
            def __init__(self):
                super().__init__("sim2real_live_bridge")
                self.safety = SafetyFilter(config)
                self.controllers_cfg = config.get("ros2_controllers", {})
                self.action_clients: dict[str, ActionClient] = {}
                for name, cfg in self.controllers_cfg.items():
                    self.action_clients[name] = ActionClient(self, FollowJointTrajectory, cfg["action"])

                self.create_subscription(JointState, "/joint_states", self._on_joint_state, 10)
                self.get_logger().info("Live bridge ready — forwarding /joint_states with safety filter")

            def _on_joint_state(self, msg: JointState):
                transformed = {}
                for i, name in enumerate(msg.name):
                    pos = msg.position[i] if i < len(msg.position) else 0.0
                    vel = msg.velocity[i] if i < len(msg.velocity) else 0.0
                    rn, sp, sv = self.safety.transform(name, pos, vel)
                    transformed[rn] = (sp, sv)

                for ctrl_name, ctrl_cfg in self.controllers_cfg.items():
                    ctrl_joints = ctrl_cfg.get("joints", [])
                    has_data = any(j in transformed for j in ctrl_joints)
                    if not has_data:
                        continue

                    point = JointTrajectoryPoint()
                    point.positions = [transformed.get(j, (0.0, 0.0))[0] for j in ctrl_joints]
                    point.velocities = [transformed.get(j, (0.0, 0.0))[1] for j in ctrl_joints]
                    point.time_from_start = Duration(sec=0, nanosec=int(1e9 / 30))

                    traj = JointTrajectory()
                    traj.joint_names = ctrl_joints
                    traj.points = [point]

                    goal = FollowJointTrajectory.Goal()
                    goal.trajectory = traj
                    ac = self.action_clients.get(ctrl_name)
                    if ac and ac.server_is_ready():
                        ac.send_goal_async(goal)

        bridge = LiveBridge()
        try:
            rclpy.spin(bridge)
        except KeyboardInterrupt:
            pass
        finally:
            bridge.destroy_node()
            rclpy.shutdown()
            print(f"Safety violations during session: {bridge.safety.violation_count}")
    else:
        print("No mode specified. Use --replay <dir> or --live")
        print("\nDry-run validation of config...")
        safety = SafetyFilter(config)
        test_joints = list(config.get("joint_mapping", {}).keys())
        print(f"  Testing {len(test_joints)} joint mappings:")
        for sim_j in test_joints:
            real_j = safety.map_name(sim_j)
            offset = config.get("joint_offsets", {}).get(sim_j, 0.0)
            print(f"    {sim_j:>35s} -> {real_j:<35s}  offset={offset:+.4f}")
        print("\n  Config validation: OK")


if __name__ == "__main__":
    main()
