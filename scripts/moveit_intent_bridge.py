#!/usr/bin/env python3
"""
MoveIt Intent Bridge: subscribes to {namespace}/moveit/intent (std_msgs/String)
and sends MoveGroup action goals to /move_action.

Supports: go_home, plan_pick, plan_pick_sink, plan_pick_fridge, plan_place.
Robots: panda (panda_arm), tiago (arm_torso).
Run alongside move_group.
"""

import argparse
import sys

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String

# MoveIt messages
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import (
    Constraints,
    JointConstraint,
    MotionPlanRequest,
    PlanningOptions,
)
from builtin_interfaces.msg import Time


# Panda arm "ready" pose (radians)
PANDA_READY_JOINTS = {
    "panda_joint1": 0.0,
    "panda_joint2": -0.785,
    "panda_joint3": 0.0,
    "panda_joint4": -2.356,
    "panda_joint5": 0.0,
    "panda_joint6": 1.571,
    "panda_joint7": 0.785,
}

# Panda arm poses for pick/place
PANDA_EXTENDED_JOINTS = {
    "panda_joint1": 0.0,
    "panda_joint2": 0.0,
    "panda_joint3": 0.0,
    "panda_joint4": -1.57,
    "panda_joint5": 0.0,
    "panda_joint6": 1.57,
    "panda_joint7": 0.785,
}

PANDA_PLACE_JOINTS = {
    "panda_joint1": 0.35,
    "panda_joint2": 0.0,
    "panda_joint3": 0.0,
    "panda_joint4": -1.57,
    "panda_joint5": 0.0,
    "panda_joint6": 1.57,
    "panda_joint7": 0.785,
}

# Tiago arm_torso "ready" pose (torso m, arm rad)
TIAGO_READY_JOINTS = {
    "torso_lift_joint": 0.15,
    "arm_1_joint": 0.1,
    "arm_2_joint": -0.2,
    "arm_3_joint": -0.15,
    "arm_4_joint": 0.0,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.0,
}

# Tiago pick poses (sink / fridge / generic)
TIAGO_PICK_SINK_JOINTS = {
    "torso_lift_joint": 0.2,
    "arm_1_joint": 0.5,
    "arm_2_joint": -0.3,
    "arm_3_joint": -0.2,
    "arm_4_joint": 0.8,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.0,
}

TIAGO_PICK_FRIDGE_JOINTS = {
    "torso_lift_joint": 0.35,
    "arm_1_joint": 0.2,
    "arm_2_joint": -0.4,
    "arm_3_joint": -0.1,
    "arm_4_joint": 0.6,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.0,
}

TIAGO_PLACE_JOINTS = {
    "torso_lift_joint": 0.15,
    "arm_1_joint": 0.0,
    "arm_2_joint": -0.5,
    "arm_3_joint": 0.0,
    "arm_4_joint": 0.5,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.0,
}


def build_joint_goal_constraint(joint_values: dict, tolerance: float = 0.001) -> Constraints:
    """Build Constraints with JointConstraints for a joint-space goal."""
    c = Constraints()
    for name, pos in joint_values.items():
        jc = JointConstraint()
        jc.joint_name = name
        jc.position = float(pos)
        jc.tolerance_above = tolerance
        jc.tolerance_below = tolerance
        jc.weight = 1.0
        c.joint_constraints.append(jc)
    return c


def build_motion_plan_request(
    group_name: str,
    joint_goal: dict,
    frame_id: str = "panda_link0",
    plan_only: bool = False,
) -> MotionPlanRequest:
    req = MotionPlanRequest()
    req.workspace_parameters.header.frame_id = frame_id
    req.workspace_parameters.header.stamp = Time(sec=0, nanosec=0)
    req.group_name = group_name
    req.num_planning_attempts = 10
    req.allowed_planning_time = 5.0
    req.max_velocity_scaling_factor = 0.1
    req.max_acceleration_scaling_factor = 0.1
    req.goal_constraints.append(build_joint_goal_constraint(joint_goal))
    return req


def build_planning_options(plan_only: bool) -> PlanningOptions:
    opt = PlanningOptions()
    opt.plan_only = plan_only
    opt.look_around = False
    opt.replan = False
    return opt


class MoveItIntentBridge(Node):
    def __init__(
        self,
        intent_topic: str,
        move_action_name: str,
        planning_group: str,
        frame_id: str = "panda_link0",
        robot: str = "panda",
        plan_only: bool = False,
    ):
        super().__init__("moveit_intent_bridge")
        self.planning_group = planning_group
        self.frame_id = frame_id
        self.robot = robot
        self.plan_only = plan_only
        self._action_client = ActionClient(self, MoveGroup, move_action_name)
        self._sub = self.create_subscription(
            String,
            intent_topic,
            self._on_intent,
            10,
        )
        self.get_logger().info(
            f"Bridge: subscribe {intent_topic} -> action {move_action_name}"
        )

    def _on_intent(self, msg: String):
        data = (msg.data or "").strip().lower()
        if not data:
            return
        self.get_logger().info(f"Intent received: {data}")
        joint_goal = self._resolve_intent(data)
        if joint_goal:
            self._send_goal(joint_goal)
        else:
            self.get_logger().warn(f"Unknown intent: {data}")

    def _resolve_intent(self, intent: str) -> dict | None:
        """Map intent string to joint goal dict. Returns None for unknown intents."""
        if self.robot == "tiago":
            intent_map = {
                "go_home": TIAGO_READY_JOINTS,
                "plan_pick": TIAGO_PICK_SINK_JOINTS,
                "plan_pick_sink": TIAGO_PICK_SINK_JOINTS,
                "plan_pick_fridge": TIAGO_PICK_FRIDGE_JOINTS,
                "plan_place": TIAGO_PLACE_JOINTS,
            }
        else:
            intent_map = {
                "go_home": PANDA_READY_JOINTS,
                "plan_pick": PANDA_EXTENDED_JOINTS,
                "plan_pick_sink": PANDA_EXTENDED_JOINTS,
                "plan_pick_fridge": PANDA_EXTENDED_JOINTS,
                "plan_place": PANDA_PLACE_JOINTS,
            }
        return intent_map.get(intent)

    def _send_goal(self, joint_goal: dict):
        if not self._action_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error("MoveGroup action server not available")
            return
        goal_msg = MoveGroup.Goal()
        goal_msg.request = build_motion_plan_request(
            self.planning_group, joint_goal, frame_id=self.frame_id, plan_only=self.plan_only
        )
        goal_msg.planning_options = build_planning_options(plan_only=self.plan_only)
        self.get_logger().info(f"Sending MoveGroup goal for {list(joint_goal.keys())[:3]}...")
        send_future = self._action_client.send_goal_async(goal_msg)
        send_future.add_done_callback(self._goal_response_cb)

    def _goal_response_cb(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error("Goal rejected")
            return
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._result_cb)

    def _result_cb(self, future):
        result = future.result().result
        code = result.error_code.val
        # moveit_msgs MoveItErrorCodes: SUCCESS=1
        if code == 1:
            self.get_logger().info("MoveGroup goal succeeded")
        else:
            self.get_logger().warn(f"MoveGroup goal finished with code {code}")


def main():
    parser = argparse.ArgumentParser(description="MoveIt Intent Bridge")
    parser.add_argument(
        "--intent-topic",
        default="/tiago/moveit/intent",
        help="Topic to subscribe for intent (std_msgs/String)",
    )
    parser.add_argument(
        "--move-action",
        default="/move_action",
        help="MoveGroup action name",
    )
    parser.add_argument(
        "--planning-group",
        default="panda_arm",
        help="Planning group name (panda_arm for Panda, arm_torso for Tiago)",
    )
    parser.add_argument(
        "--robot",
        choices=["panda", "tiago"],
        default="panda",
        help="Robot type (panda or tiago)",
    )
    parser.add_argument(
        "--frame-id",
        default=None,
        help="Planning frame (default: panda_link0 for Panda, base_footprint for Tiago)",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Only compute a plan (do not execute trajectory).",
    )
    args = parser.parse_args()

    frame_id = args.frame_id or ("base_footprint" if args.robot == "tiago" else "panda_link0")
    planning_group = args.planning_group
    if args.robot == "tiago" and planning_group == "panda_arm":
        planning_group = "arm_torso"

    rclpy.init(args=sys.argv)
    node = MoveItIntentBridge(
        intent_topic=args.intent_topic,
        move_action_name=args.move_action,
        planning_group=planning_group,
        frame_id=frame_id,
        robot=args.robot,
        plan_only=args.plan_only,
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
