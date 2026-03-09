"""ROS2 FJT Proxy — runs in conda ros2_humble Python (NOT inside Isaac Sim).

Bridges between MoveGroup's FollowJointTrajectory action servers and Isaac Sim
via a file-based IPC channel:

  {shared_dir}/joint_state.json      — written by Isaac Sim every ~50ms,
                                       read here to publish /joint_states
  {shared_dir}/pending_{N}.json      — written here when a FJT goal arrives,
                                       read by Isaac Sim to execute trajectory
  {shared_dir}/done_{N}.json         — written by Isaac Sim on completion,
                                       read here to respond to MoveGroup

This design avoids importing rclpy inside Isaac Sim (which causes DLL conflicts
on Windows with Isaac Sim 5.1 + conda ros2_humble).

Usage:
  python ros2_fjt_proxy.py [--shared-dir C:\\RoboLab_Data\\fjt_proxy]
                            [--joint-names arm_1_joint,...]
"""

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path


_MOVEIT_JOINTS = frozenset([
    "torso_lift_joint",
    "arm_1_joint", "arm_2_joint", "arm_3_joint", "arm_4_joint",
    "arm_5_joint", "arm_6_joint", "arm_7_joint",
    "arm_left_1_joint", "arm_left_2_joint", "arm_left_3_joint", "arm_left_4_joint",
    "arm_left_5_joint", "arm_left_6_joint", "arm_left_7_joint",
    "head_1_joint", "head_2_joint",
    "gripper_left_left_finger_joint", "gripper_right_left_finger_joint",
])


def parse_args():
    p = argparse.ArgumentParser(description="ROS2 FJT Proxy for Isaac Sim IPC")
    p.add_argument(
        "--shared-dir",
        type=str,
        default=os.environ.get("FJT_PROXY_DIR", r"C:\RoboLab_Data\fjt_proxy"),
        help="Directory used for IPC files between this proxy and Isaac Sim.",
    )
    p.add_argument(
        "--joint-state-topic",
        type=str,
        default="/joint_states",
        help="Topic to publish joint states on.",
    )
    p.add_argument(
        "--arm-action",
        type=str,
        default="/arm_controller/follow_joint_trajectory",
    )
    p.add_argument(
        "--arm-left-action",
        type=str,
        default="/arm_left_controller/follow_joint_trajectory",
    )
    p.add_argument(
        "--torso-action",
        type=str,
        default="/torso_controller/follow_joint_trajectory",
    )
    p.add_argument(
        "--gripper-action",
        type=str,
        default="/gripper_controller/follow_joint_trajectory",
    )
    p.add_argument(
        "--js-rate",
        type=float,
        default=20.0,
        help="Joint state publish rate (Hz).",
    )
    p.add_argument(
        "--exec-timeout",
        type=float,
        default=120.0,
        help="Max seconds to wait for Isaac Sim to execute a trajectory.",
    )
    p.add_argument(
        "--filter-joints",
        action="store_true",
        default=True,
        help="Only publish joints known to MoveGroup model (avoids 'not found' errors).",
    )
    return p.parse_args()


ARGS = parse_args()
SHARED = Path(ARGS.shared_dir)
SHARED.mkdir(parents=True, exist_ok=True)

# Clean up leftover IPC files from any previous run.
for f in SHARED.glob("pending_*.json"):
    f.unlink(missing_ok=True)
for f in SHARED.glob("done_*.json"):
    f.unlink(missing_ok=True)

print(f"[FJTProxy] Shared IPC dir: {SHARED}")


import rclpy
from rclpy.action import ActionServer, GoalResponse, CancelResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from sensor_msgs.msg import JointState
from control_msgs.action import FollowJointTrajectory

_traj_counter = 0
_counter_lock = threading.Lock()


def _next_traj_id() -> int:
    global _traj_counter
    with _counter_lock:
        _traj_counter += 1
        return _traj_counter


def _read_joint_state_file() -> dict:
    """Read joint_state.json from shared dir. Returns {} on error."""
    js_file = SHARED / "joint_state.json"
    try:
        data = json.loads(js_file.read_text(encoding="utf-8"))
        return data
    except Exception:
        return {}


def _write_pending_traj(traj_id: int, joint_names: list, points: list) -> Path:
    """Write a pending trajectory file atomically (write tmp → rename)."""
    payload = {
        "traj_id": traj_id,
        "joint_names": joint_names,
        "points": points,
        "created_at": time.time(),
    }
    path = SHARED / f"pending_{traj_id}.json"
    tmp = SHARED / f"pending_{traj_id}.tmp"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)
    return path


def _wait_for_done(traj_id: int, timeout: float) -> dict:
    """Poll until Isaac Sim writes done_{traj_id}.json or timeout."""
    done_path = SHARED / f"done_{traj_id}.json"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if done_path.exists():
            try:
                result = json.loads(done_path.read_text(encoding="utf-8"))
                done_path.unlink(missing_ok=True)
                return result
            except Exception:
                pass
        time.sleep(0.05)
    # Remove the pending file so Isaac Sim stops executing.
    (SHARED / f"pending_{traj_id}.json").unlink(missing_ok=True)
    return {"status": "timeout", "error": f"No response from Isaac Sim within {timeout}s"}


class FJTProxyNode(Node):
    def __init__(self):
        super().__init__("ros2_fjt_proxy")

        js_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._js_pub = self.create_publisher(JointState, ARGS.joint_state_topic, js_qos)
        self._js_timer = self.create_timer(1.0 / ARGS.js_rate, self._publish_js)

        # FollowJointTrajectory action servers for arm and torso controllers.
        self._arm_server = ActionServer(
            self,
            FollowJointTrajectory,
            ARGS.arm_action,
            execute_callback=self._make_execute_cb("arm_controller"),
            goal_callback=lambda _: GoalResponse.ACCEPT,
            cancel_callback=lambda _: CancelResponse.ACCEPT,
        )
        self._arm_left_server = ActionServer(
            self,
            FollowJointTrajectory,
            ARGS.arm_left_action,
            execute_callback=self._make_execute_cb("arm_left_controller"),
            goal_callback=lambda _: GoalResponse.ACCEPT,
            cancel_callback=lambda _: CancelResponse.ACCEPT,
        )
        self._torso_server = ActionServer(
            self,
            FollowJointTrajectory,
            ARGS.torso_action,
            execute_callback=self._make_execute_cb("torso_controller"),
            goal_callback=lambda _: GoalResponse.ACCEPT,
            cancel_callback=lambda _: CancelResponse.ACCEPT,
        )
        self._gripper_server = ActionServer(
            self,
            FollowJointTrajectory,
            ARGS.gripper_action,
            execute_callback=self._make_execute_cb("gripper_controller"),
            goal_callback=lambda _: GoalResponse.ACCEPT,
            cancel_callback=lambda _: CancelResponse.ACCEPT,
        )
        self.get_logger().info(
            f"[FJTProxy] Action servers ready: {ARGS.arm_action}, {ARGS.arm_left_action}, {ARGS.torso_action}, {ARGS.gripper_action}"
        )
        self.get_logger().info(
            f"[FJTProxy] Publishing /joint_states at {ARGS.js_rate:.0f} Hz"
        )

    def _publish_js(self):
        snapshot = _read_joint_state_file()
        if ARGS.filter_joints:
            if snapshot:
                snapshot = {k: v for k, v in snapshot.items() if k in _MOVEIT_JOINTS}
            if not snapshot:
                snapshot = {j: {"position": 0.0, "velocity": 0.0} for j in _MOVEIT_JOINTS}
        elif not snapshot:
            return
        msg = JointState()
        _wall_ns = int(time.time() * 1_000_000_000)
        msg.header.stamp.sec = _wall_ns // 1_000_000_000
        msg.header.stamp.nanosec = _wall_ns % 1_000_000_000
        msg.name = list(snapshot.keys())
        msg.position = [float(snapshot[n]["position"]) for n in msg.name]
        msg.velocity = [float(snapshot[n].get("velocity", 0.0)) for n in msg.name]
        self._js_pub.publish(msg)

    def _make_execute_cb(self, controller_name: str):
        def _execute_cb(goal_handle):
            req = goal_handle.request
            traj = req.trajectory
            result = FollowJointTrajectory.Result()

            if traj is None or not traj.points:
                result.error_code = FollowJointTrajectory.Result.INVALID_GOAL
                result.error_string = "Empty trajectory"
                goal_handle.abort()
                return result

            joint_names = list(traj.joint_names)
            points = []
            for pt in traj.points:
                t = float(pt.time_from_start.sec) + float(pt.time_from_start.nanosec) * 1e-9
                positions = list(pt.positions)
                if len(positions) != len(joint_names):
                    continue
                points.append({"t": t, "positions": positions})

            if not points:
                result.error_code = FollowJointTrajectory.Result.INVALID_GOAL
                result.error_string = "Trajectory has no valid points"
                goal_handle.abort()
                return result

            traj_id = _next_traj_id()
            self.get_logger().info(
                f"[FJTProxy] {controller_name}: received {len(points)}-pt trajectory (id={traj_id})"
            )
            _write_pending_traj(traj_id, joint_names, points)

            done = _wait_for_done(traj_id, ARGS.exec_timeout)
            status = done.get("status", "timeout")

            if status == "succeeded":
                result.error_code = FollowJointTrajectory.Result.SUCCESSFUL
                result.error_string = ""
                goal_handle.succeed()
                self.get_logger().info(
                    f"[FJTProxy] {controller_name}: trajectory {traj_id} SUCCEEDED"
                )
            elif status == "timeout":
                result.error_code = FollowJointTrajectory.Result.GOAL_TOLERANCE_VIOLATED
                result.error_string = done.get("error", "Timeout")
                goal_handle.abort()
                self.get_logger().warn(
                    f"[FJTProxy] {controller_name}: trajectory {traj_id} TIMEOUT"
                )
            else:
                result.error_code = FollowJointTrajectory.Result.PATH_TOLERANCE_VIOLATED
                result.error_string = done.get("error", "Isaac Sim reported failure")
                goal_handle.abort()
                self.get_logger().warn(
                    f"[FJTProxy] {controller_name}: trajectory {traj_id} FAILED: {result.error_string}"
                )

            return result

        return _execute_cb


def main():
    rclpy.init(args=None)
    node = FJTProxyNode()
    executor = MultiThreadedExecutor(num_threads=6)
    executor.add_node(node)
    print("[FJTProxy] Spinning — ready for MoveGroup connections.")
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    print("[FJTProxy] Shutdown complete.")


if __name__ == "__main__":
    main()
