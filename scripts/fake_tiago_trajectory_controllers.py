#!/usr/bin/env python3
"""
Fake FollowJointTrajectory action servers for Tiago MoveIt smoke runs.

Starts:
  - /arm_controller/follow_joint_trajectory
  - /torso_controller/follow_joint_trajectory

Each goal is accepted and completed successfully after a short delay.
This is useful when validating MoveIt execution flow without real hardware
controllers.
"""

import argparse
import time

import rclpy
from control_msgs.action import FollowJointTrajectory
from rclpy.action import ActionServer, GoalResponse, CancelResponse
from rclpy.node import Node


class _FakeFjtServer:
    def __init__(self, node: Node, action_name: str, settle_delay_sec: float) -> None:
        self._node = node
        self._action_name = action_name
        self._settle_delay_sec = settle_delay_sec
        self._server = ActionServer(
            node,
            FollowJointTrajectory,
            action_name,
            goal_callback=self._goal_cb,
            cancel_callback=self._cancel_cb,
            execute_callback=self._execute_cb,
        )
        self._node.get_logger().info(f"Fake controller ready: {action_name}")

    def _goal_cb(self, goal_request: FollowJointTrajectory.Goal):
        joints = list(goal_request.trajectory.joint_names)
        points = len(goal_request.trajectory.points)
        self._node.get_logger().info(
            f"[{self._action_name}] goal accepted: joints={joints} points={points}"
        )
        return GoalResponse.ACCEPT

    def _cancel_cb(self, _goal_handle):
        self._node.get_logger().info(f"[{self._action_name}] cancel accepted")
        return CancelResponse.ACCEPT

    def _execute_cb(self, goal_handle):
        # Simulate a small controller execution delay.
        if self._settle_delay_sec > 0.0:
            time.sleep(self._settle_delay_sec)

        result = FollowJointTrajectory.Result()
        result.error_code = 0  # SUCCESSFUL
        result.error_string = ""
        goal_handle.succeed()
        self._node.get_logger().info(f"[{self._action_name}] goal succeeded")
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake Tiago FollowJointTrajectory servers")
    parser.add_argument(
        "--settle-delay-sec",
        type=float,
        default=0.15,
        help="Delay before returning success for each goal",
    )
    args = parser.parse_args()

    rclpy.init()
    node = Node("fake_tiago_trajectory_controllers")

    _FakeFjtServer(node, "/arm_controller/follow_joint_trajectory", args.settle_delay_sec)
    _FakeFjtServer(node, "/torso_controller/follow_joint_trajectory", args.settle_delay_sec)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

