"""
Bridge MoveIt Servo JointTrajectory topic to FollowJointTrajectory action.

This node subscribes to a trajectory topic (default: /arm_controller/joint_trajectory)
and forwards the latest message as a FollowJointTrajectory goal to the action server
(default: /arm_controller/follow_joint_trajectory). It is intended for simulation
teleoperation on Windows where the controller layer is represented by the FJT proxy.
"""

import argparse
from typing import Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectory


def parse_args():
    parser = argparse.ArgumentParser(description="Servo JointTrajectory -> FJT action bridge")
    parser.add_argument(
        "--trajectory-topic",
        type=str,
        default="/arm_controller/joint_trajectory",
        help="Input topic with trajectory_msgs/JointTrajectory",
    )
    parser.add_argument(
        "--action-name",
        type=str,
        default="/arm_controller/follow_joint_trajectory",
        help="FollowJointTrajectory action server name",
    )
    parser.add_argument(
        "--queue-depth",
        type=int,
        default=10,
        help="ROS subscription queue depth",
    )
    return parser.parse_args()


class ServoTrajectoryBridge(Node):
    def __init__(self, trajectory_topic: str, action_name: str, queue_depth: int):
        super().__init__("servo_joint_trajectory_bridge")
        self._latest_msg: Optional[JointTrajectory] = None
        self._goal_in_flight = False
        self._client = ActionClient(self, FollowJointTrajectory, action_name)

        self.create_subscription(JointTrajectory, trajectory_topic, self._on_traj, queue_depth)
        self.create_timer(0.05, self._try_send_goal)
        self.get_logger().info(
            f"Bridge ready: topic '{trajectory_topic}' -> action '{action_name}'"
        )

    def _on_traj(self, msg: JointTrajectory):
        if not msg.points or not msg.joint_names:
            return
        self._latest_msg = msg

    def _try_send_goal(self):
        if self._goal_in_flight or self._latest_msg is None:
            return
        if not self._client.server_is_ready():
            if not self._client.wait_for_server(timeout_sec=0.0):
                return

        goal = FollowJointTrajectory.Goal()
        goal.trajectory = self._latest_msg
        self._latest_msg = None
        self._goal_in_flight = True

        future = self._client.send_goal_async(goal)
        future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future):
        goal_handle = future.result()
        if not goal_handle or not goal_handle.accepted:
            self.get_logger().warning("Trajectory goal rejected by action server.")
            self._goal_in_flight = False
            return
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._on_goal_result)

    def _on_goal_result(self, future):
        try:
            result = future.result().result
            code = int(result.error_code)
            if code != FollowJointTrajectory.Result.SUCCESSFUL:
                self.get_logger().warning(
                    f"FJT execution reported non-success error_code={code}"
                )
        except Exception as exc:
            self.get_logger().warning(f"Failed to read goal result: {exc}")
        finally:
            self._goal_in_flight = False


def main():
    args = parse_args()
    rclpy.init()
    node = ServoTrajectoryBridge(
        trajectory_topic=args.trajectory_topic,
        action_name=args.action_name,
        queue_depth=max(1, int(args.queue_depth)),
    )
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
