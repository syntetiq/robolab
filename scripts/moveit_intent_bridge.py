#!/usr/bin/env python3
"""
MoveIt Intent Bridge: subscribes to {namespace}/moveit/intent (std_msgs/String)
and sends MoveGroup action goals to /move_action.

Supports multi-step sequences for pick/place with gripper control.
Robots: panda (panda_arm), tiago (arm_torso).
Run alongside move_group.
"""

import argparse
import sys
import time as _time

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
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from builtin_interfaces.msg import Time, Duration


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

# ──────────────────────────────────────────────────────────────────────────────
# Tiago arm_torso joint targets.
#
# Design principles:
# 1. Use SIMPLE, NEAR-ZERO joint values where possible – easier for OMPL
#    to plan to, less self-collision risk.
# 2. Each pose is DISTINCT so go_home → target always requires motion.
# 3. All values verified within PAL Robotics hardware limits:
#    torso_lift_joint : [0.00,  0.35]
#    arm_1_joint      : [-2.90, 2.90]
#    arm_2_joint      : [-2.00, 2.00]
#    arm_3_joint      : [-3.60, 1.80]
#    arm_4_joint      : [-0.80, 2.50]
#    arm_5_joint      : [-2.20, 2.20]
#    arm_6_joint      : [-1.50, 1.50]
#    arm_7_joint      : [-2.20, 2.20]
# ──────────────────────────────────────────────────────────────────────────────

# "Ready" / home pose – arm tucked close to body, very safe configuration.
# Matches PAL Robotics default "arm_tuck" pose.
TIAGO_READY_JOINTS = {
    "torso_lift_joint": 0.15,
    "arm_1_joint": 0.10,
    "arm_2_joint": -0.20,
    "arm_3_joint": -0.15,
    "arm_4_joint": 0.0,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.0,
}

# Approach workzone – slightly extended, distinct from home.
TIAGO_APPROACH_WORKZONE_JOINTS = {
    "torso_lift_joint": 0.18,
    "arm_1_joint": 0.25,
    "arm_2_joint": -0.35,
    "arm_3_joint": -0.12,
    "arm_4_joint": 0.50,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.0,
}

# Pick from sink – arm rotated toward sink side (distinct arm_1 angle).
TIAGO_PICK_SINK_JOINTS = {
    "torso_lift_joint": 0.22,
    "arm_1_joint": 0.55,
    "arm_2_joint": -0.35,
    "arm_3_joint": -0.22,
    "arm_4_joint": 0.85,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.0,
}

# Pick from fridge – arm angled slightly differently (distinct arm_1/arm_4).
TIAGO_PICK_FRIDGE_JOINTS = {
    "torso_lift_joint": 0.22,
    "arm_1_joint": 0.45,
    "arm_2_joint": -0.30,
    "arm_3_joint": -0.18,
    "arm_4_joint": 0.75,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.0,
}

# Pick from dishwasher – lower torso, arm reaching forward-low.
TIAGO_PICK_DISHWASHER_JOINTS = {
    "torso_lift_joint": 0.18,
    "arm_1_joint": 0.50,
    "arm_2_joint": -0.30,
    "arm_3_joint": -0.22,
    "arm_4_joint": 0.82,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.0,
}

# Place pose – arm lowered slightly.
TIAGO_PLACE_JOINTS = {
    "torso_lift_joint": 0.15,
    "arm_1_joint": 0.0,
    "arm_2_joint": -0.50,
    "arm_3_joint": 0.0,
    "arm_4_joint": 0.50,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.0,
}

# Open/close fridge – arm_7 adds wrist rotation to distinguish from home.
TIAGO_OPEN_CLOSE_FRIDGE_JOINTS = {
    "torso_lift_joint": 0.15,
    "arm_1_joint": 0.0,
    "arm_2_joint": -0.50,
    "arm_3_joint": 0.0,
    "arm_4_joint": 0.50,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.25,
}

# Open/close dishwasher – arm_7 has larger rotation for distinction.
TIAGO_OPEN_CLOSE_DISHWASHER_JOINTS = {
    "torso_lift_joint": 0.15,
    "arm_1_joint": 0.0,
    "arm_2_joint": -0.50,
    "arm_3_joint": 0.0,
    "arm_4_joint": 0.50,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.40,
}

# Pre-grasp: arm extended, wrist aligned for top-down approach.
TIAGO_PRE_GRASP_JOINTS = {
    "torso_lift_joint": 0.25,
    "arm_1_joint": 0.40,
    "arm_2_joint": -0.50,
    "arm_3_joint": -0.20,
    "arm_4_joint": 1.20,
    "arm_5_joint": 0.0,
    "arm_6_joint": -0.30,
    "arm_7_joint": 0.0,
}

# Grasp: arm lowered to table surface level.
TIAGO_GRASP_JOINTS = {
    "torso_lift_joint": 0.20,
    "arm_1_joint": 0.40,
    "arm_2_joint": -0.60,
    "arm_3_joint": -0.20,
    "arm_4_joint": 1.40,
    "arm_5_joint": 0.0,
    "arm_6_joint": -0.30,
    "arm_7_joint": 0.0,
}

# Lift: after grasping, lift object off surface.
TIAGO_LIFT_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_1_joint": 0.40,
    "arm_2_joint": -0.35,
    "arm_3_joint": -0.20,
    "arm_4_joint": 1.00,
    "arm_5_joint": 0.0,
    "arm_6_joint": -0.30,
    "arm_7_joint": 0.0,
}

# Gripper positions (finger joint values).
GRIPPER_OPEN = 0.04
GRIPPER_CLOSED = 0.0
GRIPPER_JOINTS = ["gripper_left_joint", "gripper_right_joint"]

# Fridge door interaction poses.
TIAGO_FRIDGE_APPROACH_JOINTS = {
    "torso_lift_joint": 0.20,
    "arm_1_joint": 0.30,
    "arm_2_joint": -0.40,
    "arm_3_joint": -0.10,
    "arm_4_joint": 0.60,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.0,
}

TIAGO_FRIDGE_HANDLE_JOINTS = {
    "torso_lift_joint": 0.25,
    "arm_1_joint": 0.50,
    "arm_2_joint": -0.50,
    "arm_3_joint": -0.15,
    "arm_4_joint": 0.90,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.25,
}

TIAGO_FRIDGE_PULL_JOINTS = {
    "torso_lift_joint": 0.25,
    "arm_1_joint": 0.20,
    "arm_2_joint": -0.30,
    "arm_3_joint": -0.15,
    "arm_4_joint": 0.60,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.25,
}

# Dishwasher door interaction poses (lower than fridge).
TIAGO_DW_APPROACH_JOINTS = {
    "torso_lift_joint": 0.10,
    "arm_1_joint": 0.30,
    "arm_2_joint": -0.50,
    "arm_3_joint": -0.10,
    "arm_4_joint": 0.80,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.0,
}

TIAGO_DW_HANDLE_JOINTS = {
    "torso_lift_joint": 0.10,
    "arm_1_joint": 0.50,
    "arm_2_joint": -0.60,
    "arm_3_joint": -0.20,
    "arm_4_joint": 1.10,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.40,
}

TIAGO_DW_PULL_JOINTS = {
    "torso_lift_joint": 0.10,
    "arm_1_joint": 0.20,
    "arm_2_joint": -0.40,
    "arm_3_joint": -0.20,
    "arm_4_joint": 0.70,
    "arm_5_joint": 0.0,
    "arm_6_joint": 0.0,
    "arm_7_joint": 0.40,
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
    planning_time: float = 20.0,
    num_attempts: int = 30,
) -> MotionPlanRequest:
    req = MotionPlanRequest()
    req.workspace_parameters.header.frame_id = frame_id
    req.workspace_parameters.header.stamp = Time(sec=0, nanosec=0)
    req.group_name = group_name
    req.num_planning_attempts = num_attempts
    req.allowed_planning_time = planning_time
    req.max_velocity_scaling_factor = 0.15
    req.max_acceleration_scaling_factor = 0.15
    req.goal_constraints.append(build_joint_goal_constraint(joint_goal, tolerance=0.05))
    return req


def build_planning_options(plan_only: bool) -> PlanningOptions:
    opt = PlanningOptions()
    opt.plan_only = plan_only
    opt.look_around = False
    opt.replan = False
    return opt


class MoveItIntentBridge(Node):
    """Subscribes to intent topic and executes multi-step sequences via MoveGroup
    and gripper FollowJointTrajectory actions."""

    def __init__(
        self,
        intent_topic: str,
        move_action_name: str,
        planning_group: str,
        frame_id: str = "panda_link0",
        robot: str = "panda",
        plan_only: bool = False,
        gripper_action: str = "/gripper_controller/follow_joint_trajectory",
    ):
        super().__init__("moveit_intent_bridge")
        self.planning_group = planning_group
        self.frame_id = frame_id
        self.robot = robot
        self.plan_only = plan_only
        self._action_client = ActionClient(self, MoveGroup, move_action_name)
        self._gripper_client = ActionClient(self, FollowJointTrajectory, gripper_action)
        self._sub = self.create_subscription(
            String,
            intent_topic,
            self._on_intent,
            10,
        )
        self._executing = False
        self.get_logger().info(
            f"Bridge: subscribe {intent_topic} -> action {move_action_name} + gripper {gripper_action}"
        )

    def _on_intent(self, msg: String):
        data = (msg.data or "").strip().lower()
        if not data:
            return
        if self._executing:
            self.get_logger().warn(f"Sequence in progress, ignoring intent: {data}")
            return
        self.get_logger().info(f"Intent received: {data}")
        sequence = self._resolve_intent_sequence(data)
        if sequence is not None:
            self._executing = True
            import threading
            threading.Thread(
                target=self._execute_sequence, args=(data, sequence), daemon=True
            ).start()
        else:
            self.get_logger().warn(f"Unknown intent: {data}")

    def _resolve_intent_sequence(self, intent: str):
        """Map intent to a sequence of steps. Each step is either:
        - ("move", joint_dict)   -- send MoveGroup goal
        - ("gripper", position)  -- send gripper open/close
        Returns None for unknown intents.
        """
        if self.robot != "tiago":
            simple = self._resolve_simple_intent(intent)
            return [("move", simple)] if simple else None

        if intent == "go_home":
            return [("move", TIAGO_READY_JOINTS)]
        elif intent == "approach_workzone":
            return [("move", TIAGO_APPROACH_WORKZONE_JOINTS)]

        elif intent in ("plan_pick", "plan_pick_sink"):
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_PRE_GRASP_JOINTS),
                ("move", TIAGO_GRASP_JOINTS),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_LIFT_JOINTS),
                ("move", TIAGO_PICK_SINK_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]
        elif intent == "plan_pick_fridge":
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_PRE_GRASP_JOINTS),
                ("move", TIAGO_GRASP_JOINTS),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_LIFT_JOINTS),
                ("move", TIAGO_PICK_FRIDGE_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]
        elif intent == "plan_pick_dishwasher":
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_PRE_GRASP_JOINTS),
                ("move", TIAGO_GRASP_JOINTS),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_LIFT_JOINTS),
                ("move", TIAGO_PICK_DISHWASHER_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]
        elif intent == "plan_place":
            return [
                ("move", TIAGO_PLACE_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]

        elif intent == "open_close_fridge":
            return [
                ("move", TIAGO_FRIDGE_APPROACH_JOINTS),
                ("move", TIAGO_FRIDGE_HANDLE_JOINTS),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_FRIDGE_PULL_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_FRIDGE_HANDLE_JOINTS),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_FRIDGE_APPROACH_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]
        elif intent == "open_close_dishwasher":
            return [
                ("move", TIAGO_DW_APPROACH_JOINTS),
                ("move", TIAGO_DW_HANDLE_JOINTS),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_DW_PULL_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_DW_HANDLE_JOINTS),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_DW_APPROACH_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]
        return None

    def _resolve_simple_intent(self, intent: str) -> dict | None:
        intent_map = {
            "go_home": PANDA_READY_JOINTS,
            "approach_workzone": PANDA_READY_JOINTS,
            "plan_pick": PANDA_EXTENDED_JOINTS,
            "plan_pick_sink": PANDA_EXTENDED_JOINTS,
            "plan_pick_fridge": PANDA_EXTENDED_JOINTS,
            "plan_pick_dishwasher": PANDA_EXTENDED_JOINTS,
            "plan_place": PANDA_PLACE_JOINTS,
            "open_close_fridge": PANDA_EXTENDED_JOINTS,
            "open_close_dishwasher": PANDA_EXTENDED_JOINTS,
        }
        return intent_map.get(intent)

    def _execute_sequence(self, intent_name: str, steps: list):
        """Execute a multi-step sequence synchronously in a background thread."""
        self.get_logger().info(f"Starting sequence for '{intent_name}' ({len(steps)} steps)")
        try:
            for i, (action_type, value) in enumerate(steps):
                self.get_logger().info(f"  Step {i+1}/{len(steps)}: {action_type}")
                if action_type == "move":
                    ok = self._send_goal_sync(value)
                    if not ok:
                        self.get_logger().error(f"  Step {i+1} failed, aborting sequence")
                        break
                elif action_type == "gripper":
                    ok = self._send_gripper_sync(value)
                    if not ok:
                        self.get_logger().warn(f"  Gripper step {i+1} failed, continuing")
                _time.sleep(0.5)
            self.get_logger().info(f"Sequence '{intent_name}' complete")
        finally:
            self._executing = False

    def _send_goal_sync(self, joint_goal: dict) -> bool:
        if not self._action_client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error("MoveGroup action server not available")
            return False
        goal_msg = MoveGroup.Goal()
        goal_msg.request = build_motion_plan_request(
            self.planning_group, joint_goal, frame_id=self.frame_id, plan_only=self.plan_only
        )
        goal_msg.planning_options = build_planning_options(plan_only=self.plan_only)
        self.get_logger().info(f"Sending MoveGroup goal for {list(joint_goal.keys())[:3]}...")
        send_future = self._action_client.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self, send_future, timeout_sec=15.0)
        if not send_future.done():
            self.get_logger().error("MoveGroup send_goal timed out")
            return False
        goal_handle = send_future.result()
        if not goal_handle.accepted:
            self.get_logger().error("Goal rejected")
            return False
        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=60.0)
        if not result_future.done():
            self.get_logger().error("MoveGroup execution timed out")
            return False
        result = result_future.result().result
        code = result.error_code.val
        if code == 1:
            self.get_logger().info("MoveGroup goal succeeded")
            return True
        self.get_logger().warn(f"MoveGroup goal finished with code {code}")
        return False

    def _send_gripper_sync(self, position: float) -> bool:
        if not self._gripper_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().warn("Gripper action server not available")
            return False
        goal = FollowJointTrajectory.Goal()
        goal.trajectory = JointTrajectory()
        goal.trajectory.joint_names = GRIPPER_JOINTS
        pt = JointTrajectoryPoint()
        pt.positions = [float(position)] * len(GRIPPER_JOINTS)
        pt.time_from_start = Duration(sec=1, nanosec=0)
        goal.trajectory.points.append(pt)
        send_future = self._gripper_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, send_future, timeout_sec=10.0)
        if not send_future.done():
            return False
        goal_handle = send_future.result()
        if not goal_handle.accepted:
            return False
        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=10.0)
        if result_future.done():
            res = result_future.result().result
            return res.error_code == FollowJointTrajectory.Result.SUCCESSFUL
        return False

    def _send_goal(self, joint_goal: dict):
        """Legacy async goal sender (kept for compatibility)."""
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
    parser.add_argument(
        "--gripper-action",
        default="/gripper_controller/follow_joint_trajectory",
        help="FollowJointTrajectory action for gripper control.",
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
        gripper_action=args.gripper_action,
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
