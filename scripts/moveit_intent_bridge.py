#!/usr/bin/env python3
"""
MoveIt Intent Bridge: subscribes to {namespace}/moveit/intent (std_msgs/String)
and sends MoveGroup action goals to /move_action.

Supports multi-step sequences for pick/place with gripper control.
Robots: panda (panda_arm), tiago (arm_torso).
Run alongside move_group.
"""

import argparse
import json
import os
import sys
import time as _time
from pathlib import Path

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
from geometry_msgs.msg import Twist


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

# "Ready" / home pose – arm tucked close to body.
# PAL Robotics standard tuck: shoulder back, elbow bent, wrist folded.
TIAGO_READY_JOINTS = {
    "torso_lift_joint": 0.15,
    "arm_1_joint": 0.20,
    "arm_2_joint": -1.34,
    "arm_3_joint": -0.20,
    "arm_4_joint": 1.94,
    "arm_5_joint": -1.57,
    "arm_6_joint": 1.37,
    "arm_7_joint": 0.0,
}

# Approach workzone – torso up, arm extended forward at mid-height.
TIAGO_APPROACH_WORKZONE_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_1_joint": 1.10,
    "arm_2_joint": -0.50,
    "arm_3_joint": -1.20,
    "arm_4_joint": 1.50,
    "arm_5_joint": -0.80,
    "arm_6_joint": 0.20,
    "arm_7_joint": 0.0,
}

# Pick from sink – arm reaches to the side and forward.
TIAGO_PICK_SINK_JOINTS = {
    "torso_lift_joint": 0.25,
    "arm_1_joint": 1.50,
    "arm_2_joint": -0.30,
    "arm_3_joint": -1.80,
    "arm_4_joint": 1.80,
    "arm_5_joint": -1.00,
    "arm_6_joint": 0.50,
    "arm_7_joint": -0.30,
}

# Pick from fridge – arm extends forward at chest height.
TIAGO_PICK_FRIDGE_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_1_joint": 1.20,
    "arm_2_joint": -0.60,
    "arm_3_joint": -1.50,
    "arm_4_joint": 1.60,
    "arm_5_joint": -0.50,
    "arm_6_joint": 0.30,
    "arm_7_joint": -0.20,
}

# Pick from dishwasher – lower torso, arm reaching forward-low.
TIAGO_PICK_DISHWASHER_JOINTS = {
    "torso_lift_joint": 0.10,
    "arm_1_joint": 1.30,
    "arm_2_joint": 0.10,
    "arm_3_joint": -1.60,
    "arm_4_joint": 2.00,
    "arm_5_joint": -0.80,
    "arm_6_joint": 0.50,
    "arm_7_joint": 0.0,
}

# Place pose – arm extended to the side at table height.
TIAGO_PLACE_JOINTS = {
    "torso_lift_joint": 0.25,
    "arm_1_joint": 0.80,
    "arm_2_joint": -0.20,
    "arm_3_joint": -1.40,
    "arm_4_joint": 1.90,
    "arm_5_joint": -1.20,
    "arm_6_joint": 0.60,
    "arm_7_joint": 0.30,
}

# Open/close fridge – arm up and forward for handle grip.
TIAGO_OPEN_CLOSE_FRIDGE_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_1_joint": 1.00,
    "arm_2_joint": -0.80,
    "arm_3_joint": -1.30,
    "arm_4_joint": 1.50,
    "arm_5_joint": -0.70,
    "arm_6_joint": 0.40,
    "arm_7_joint": 0.50,
}

# Open/close dishwasher – arm down and forward for low handle.
TIAGO_OPEN_CLOSE_DISHWASHER_JOINTS = {
    "torso_lift_joint": 0.10,
    "arm_1_joint": 1.20,
    "arm_2_joint": 0.20,
    "arm_3_joint": -1.50,
    "arm_4_joint": 2.00,
    "arm_5_joint": -0.90,
    "arm_6_joint": 0.30,
    "arm_7_joint": 0.60,
}

# Pre-grasp: arm extended forward, wrist aligned for top-down approach.
TIAGO_PRE_GRASP_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_1_joint": 1.30,
    "arm_2_joint": -0.40,
    "arm_3_joint": -1.60,
    "arm_4_joint": 1.80,
    "arm_5_joint": -0.80,
    "arm_6_joint": -0.50,
    "arm_7_joint": 0.0,
}

# Grasp: arm lowered from pre-grasp to object level.
TIAGO_GRASP_JOINTS = {
    "torso_lift_joint": 0.20,
    "arm_1_joint": 1.30,
    "arm_2_joint": 0.10,
    "arm_3_joint": -1.60,
    "arm_4_joint": 2.10,
    "arm_5_joint": -0.80,
    "arm_6_joint": -0.80,
    "arm_7_joint": 0.0,
}

# Lift: after grasping, raise arm with object.
TIAGO_LIFT_JOINTS = {
    "torso_lift_joint": 0.35,
    "arm_1_joint": 1.30,
    "arm_2_joint": -0.80,
    "arm_3_joint": -1.60,
    "arm_4_joint": 1.40,
    "arm_5_joint": -0.80,
    "arm_6_joint": -0.30,
    "arm_7_joint": 0.0,
}

# ──────────────────────────────────────────────────────────────────────────────
# Left arm mirrored poses (arm_left_{1-7}_joint).
# Mirrored from right arm: same joint angles work since the kinematic chain
# is symmetric. We only include arm joints (torso is shared).
# ──────────────────────────────────────────────────────────────────────────────

TIAGO_LEFT_READY_JOINTS = {
    "torso_lift_joint": 0.15,
    "arm_left_1_joint": 0.20,
    "arm_left_2_joint": -1.34,
    "arm_left_3_joint": -0.20,
    "arm_left_4_joint": 1.94,
    "arm_left_5_joint": -1.57,
    "arm_left_6_joint": 1.37,
    "arm_left_7_joint": 0.0,
}

TIAGO_LEFT_APPROACH_WORKZONE_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_left_1_joint": 1.10,
    "arm_left_2_joint": -0.50,
    "arm_left_3_joint": -1.20,
    "arm_left_4_joint": 1.50,
    "arm_left_5_joint": -0.80,
    "arm_left_6_joint": 0.20,
    "arm_left_7_joint": 0.0,
}

TIAGO_LEFT_PRE_GRASP_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_left_1_joint": 1.30,
    "arm_left_2_joint": -0.40,
    "arm_left_3_joint": -1.60,
    "arm_left_4_joint": 1.80,
    "arm_left_5_joint": -0.80,
    "arm_left_6_joint": -0.50,
    "arm_left_7_joint": 0.0,
}

TIAGO_LEFT_GRASP_JOINTS = {
    "torso_lift_joint": 0.20,
    "arm_left_1_joint": 1.30,
    "arm_left_2_joint": 0.10,
    "arm_left_3_joint": -1.60,
    "arm_left_4_joint": 2.10,
    "arm_left_5_joint": -0.80,
    "arm_left_6_joint": -0.80,
    "arm_left_7_joint": 0.0,
}

TIAGO_LEFT_LIFT_JOINTS = {
    "torso_lift_joint": 0.35,
    "arm_left_1_joint": 1.30,
    "arm_left_2_joint": -0.80,
    "arm_left_3_joint": -1.60,
    "arm_left_4_joint": 1.40,
    "arm_left_5_joint": -0.80,
    "arm_left_6_joint": -0.30,
    "arm_left_7_joint": 0.0,
}

TIAGO_LEFT_PICK_SINK_JOINTS = {
    "torso_lift_joint": 0.25,
    "arm_left_1_joint": 1.50,
    "arm_left_2_joint": -0.30,
    "arm_left_3_joint": -1.80,
    "arm_left_4_joint": 1.80,
    "arm_left_5_joint": -1.00,
    "arm_left_6_joint": 0.50,
    "arm_left_7_joint": -0.30,
}

TIAGO_LEFT_PLACE_JOINTS = {
    "torso_lift_joint": 0.25,
    "arm_left_1_joint": 0.80,
    "arm_left_2_joint": -0.20,
    "arm_left_3_joint": -1.40,
    "arm_left_4_joint": 1.90,
    "arm_left_5_joint": -1.20,
    "arm_left_6_joint": 0.60,
    "arm_left_7_joint": 0.30,
}

# Place back on table: same height as grasp but offset laterally.
TIAGO_PLACE_TABLE_JOINTS = {
    "torso_lift_joint": 0.20,
    "arm_1_joint": 0.90,
    "arm_2_joint": 0.10,
    "arm_3_joint": -1.60,
    "arm_4_joint": 2.10,
    "arm_5_joint": -0.80,
    "arm_6_joint": -0.80,
    "arm_7_joint": 0.0,
}

# Stack: place object higher (on top of another object).
TIAGO_STACK_HOVER_JOINTS = {
    "torso_lift_joint": 0.35,
    "arm_1_joint": 0.90,
    "arm_2_joint": -0.20,
    "arm_3_joint": -1.60,
    "arm_4_joint": 1.70,
    "arm_5_joint": -0.80,
    "arm_6_joint": -0.50,
    "arm_7_joint": 0.0,
}

TIAGO_STACK_LOWER_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_1_joint": 0.90,
    "arm_2_joint": 0.0,
    "arm_3_joint": -1.60,
    "arm_4_joint": 1.90,
    "arm_5_joint": -0.80,
    "arm_6_joint": -0.70,
    "arm_7_joint": 0.0,
}

# Pour: tilt wrist ~90 degrees to pour contents.
TIAGO_POUR_TILT_JOINTS = {
    "torso_lift_joint": 0.35,
    "arm_1_joint": 1.30,
    "arm_2_joint": -0.80,
    "arm_3_joint": -1.60,
    "arm_4_joint": 1.40,
    "arm_5_joint": -0.80,
    "arm_6_joint": -0.30,
    "arm_7_joint": 1.57,
}

# Pour: return wrist upright after pouring.
TIAGO_POUR_UPRIGHT_JOINTS = {
    "torso_lift_joint": 0.35,
    "arm_1_joint": 1.30,
    "arm_2_joint": -0.80,
    "arm_3_joint": -1.60,
    "arm_4_joint": 1.40,
    "arm_5_joint": -0.80,
    "arm_6_joint": -0.30,
    "arm_7_joint": 0.0,
}

# Gripper positions (finger joint values).
GRIPPER_OPEN = 0.04
GRIPPER_CLOSED = 0.0
GRIPPER_JOINTS = ["gripper_left_left_finger_joint", "gripper_right_left_finger_joint"]

# Fridge door interaction poses.
TIAGO_FRIDGE_APPROACH_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_1_joint": 0.90,
    "arm_2_joint": -0.70,
    "arm_3_joint": -1.20,
    "arm_4_joint": 1.40,
    "arm_5_joint": -0.60,
    "arm_6_joint": 0.30,
    "arm_7_joint": 0.0,
}

TIAGO_FRIDGE_HANDLE_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_1_joint": 1.30,
    "arm_2_joint": -0.60,
    "arm_3_joint": -1.50,
    "arm_4_joint": 1.70,
    "arm_5_joint": -0.50,
    "arm_6_joint": 0.20,
    "arm_7_joint": 0.50,
}

TIAGO_FRIDGE_PULL_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_1_joint": 0.60,
    "arm_2_joint": -0.90,
    "arm_3_joint": -0.80,
    "arm_4_joint": 1.20,
    "arm_5_joint": -0.70,
    "arm_6_joint": 0.40,
    "arm_7_joint": 0.50,
}

# Dishwasher door interaction poses (lower than fridge).
TIAGO_DW_APPROACH_JOINTS = {
    "torso_lift_joint": 0.10,
    "arm_1_joint": 1.10,
    "arm_2_joint": 0.10,
    "arm_3_joint": -1.40,
    "arm_4_joint": 1.80,
    "arm_5_joint": -0.80,
    "arm_6_joint": 0.30,
    "arm_7_joint": 0.0,
}

TIAGO_DW_HANDLE_JOINTS = {
    "torso_lift_joint": 0.10,
    "arm_1_joint": 1.40,
    "arm_2_joint": 0.30,
    "arm_3_joint": -1.60,
    "arm_4_joint": 2.10,
    "arm_5_joint": -0.70,
    "arm_6_joint": 0.20,
    "arm_7_joint": 0.60,
}

TIAGO_DW_PULL_JOINTS = {
    "torso_lift_joint": 0.10,
    "arm_1_joint": 0.70,
    "arm_2_joint": -0.20,
    "arm_3_joint": -1.00,
    "arm_4_joint": 1.40,
    "arm_5_joint": -0.90,
    "arm_6_joint": 0.50,
    "arm_7_joint": 0.60,
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
    req.max_velocity_scaling_factor = 0.20
    req.max_acceleration_scaling_factor = 0.20
    req.goal_constraints.append(build_joint_goal_constraint(joint_goal, tolerance=0.05))
    return req


def build_planning_options(plan_only: bool) -> PlanningOptions:
    opt = PlanningOptions()
    opt.plan_only = plan_only
    opt.look_around = False
    opt.replan = False
    return opt


FJT_PROXY_DIR = Path(os.environ.get("FJT_PROXY_DIR", r"C:\RoboLab_Data\fjt_proxy"))

JOINT_LIMITS = {
    "torso_lift_joint": (0.0, 0.35),
    "arm_1_joint": (0.07, 2.68),
    "arm_2_joint": (-1.50, 1.02),
    "arm_3_joint": (-3.46, 1.57),
    "arm_4_joint": (0.0, 2.29),
    "arm_5_joint": (-2.07, 2.07),
    "arm_6_joint": (-1.39, 1.39),
    "arm_7_joint": (-2.07, 2.07),
}

REFERENCE_OBJECT_XYZ = (1.0, -0.56, 0.85)

_GRIPPER_GAP_EMPTY = 0.002


def clamp_joints(joints: dict) -> dict:
    """Clamp joint values to their mechanical limits."""
    clamped = {}
    for name, val in joints.items():
        lo, hi = JOINT_LIMITS.get(name, (-3.14, 3.14))
        clamped[name] = max(lo, min(hi, val))
    return clamped


def query_object_pose(timeout: float = 2.0):
    """Request the nearest graspable object pose from Isaac Sim via IPC."""
    try:
        FJT_PROXY_DIR.mkdir(parents=True, exist_ok=True)
        query_file = FJT_PROXY_DIR / "query_object_pose.json"
        result_file = FJT_PROXY_DIR / "object_pose_result.json"
        if result_file.exists():
            result_file.unlink()
        query_file.write_text("{}", encoding="utf-8")

        deadline = _time.time() + timeout
        while _time.time() < deadline:
            if result_file.exists():
                data = json.loads(result_file.read_text(encoding="utf-8"))
                if data.get("position"):
                    return tuple(data["position"]), data.get("class", "unknown")
                return None, None
            _time.sleep(0.1)
    except Exception:
        pass
    return None, None


def read_grasp_result():
    """Read the current grasp result from Isaac Sim IPC."""
    try:
        gr_file = FJT_PROXY_DIR / "grasp_result.json"
        if gr_file.exists():
            data = json.loads(gr_file.read_text(encoding="utf-8"))
            return data
    except Exception:
        pass
    return None


def adapt_grasp_pose(base_joints: dict, object_xyz: tuple,
                     reference_xyz: tuple = REFERENCE_OBJECT_XYZ) -> dict:
    """Compute parametric joint correction based on object vs reference position.

    Coefficients calibrated from 50-episode analysis:
      - torso (dz * 0.6): conservative to stay within 0.0-0.35 range
      - arm_1 (dy * 0.25): shoulder yaw for lateral offset, range 0.07-2.68
      - arm_2 (dx * 0.15): shoulder pitch for forward reach, range -1.5 to 1.02
      - arm_4 (dz * -0.3): elbow compensation for height changes
    """
    dx = object_xyz[0] - reference_xyz[0]
    dy = object_xyz[1] - reference_xyz[1]
    dz = object_xyz[2] - reference_xyz[2]
    adapted = dict(base_joints)
    adapted["torso_lift_joint"] = adapted.get("torso_lift_joint", 0.2) + dz * 0.6
    adapted["arm_1_joint"] = adapted.get("arm_1_joint", 1.3) + dy * 0.25
    adapted["arm_2_joint"] = adapted.get("arm_2_joint", 0.1) + dx * 0.15
    adapted["arm_4_joint"] = adapted.get("arm_4_joint", 2.1) + dz * -0.3
    return clamp_joints(adapted)


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
        self._cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self._sub = self.create_subscription(
            String,
            intent_topic,
            self._on_intent,
            10,
        )
        self._executing = False
        self.get_logger().info(
            f"Bridge: subscribe {intent_topic} -> action {move_action_name} + gripper {gripper_action} + /cmd_vel"
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

    def _get_adaptive_grasp_poses(self, base_pre: dict, base_grasp: dict):
        """Query object pose from sim and return adapted (pre_grasp, grasp) joint dicts."""
        obj_pos, obj_class = query_object_pose(timeout=2.0)
        if obj_pos is not None:
            self.get_logger().info(
                f"Object '{obj_class}' at {[round(v,3) for v in obj_pos]}, adapting grasp pose"
            )
            adapted_pre = adapt_grasp_pose(base_pre, obj_pos)
            adapted_grasp = adapt_grasp_pose(base_grasp, obj_pos)
            return adapted_pre, adapted_grasp
        self.get_logger().info("No object pose available, using default grasp pose")
        return base_pre, base_grasp

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
            pre, grasp = self._get_adaptive_grasp_poses(
                TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_LIFT_JOINTS),
                ("move", TIAGO_PICK_SINK_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]
        elif intent == "plan_pick_fridge":
            pre, grasp = self._get_adaptive_grasp_poses(
                TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_LIFT_JOINTS),
                ("move", TIAGO_PICK_FRIDGE_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]
        elif intent == "plan_pick_dishwasher":
            pre, grasp = self._get_adaptive_grasp_poses(
                TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
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

        elif intent == "plan_pick_table":
            pre, grasp = self._get_adaptive_grasp_poses(
                TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_LIFT_JOINTS),
                ("move", TIAGO_PLACE_TABLE_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]

        elif intent == "stack_objects":
            pre, grasp = self._get_adaptive_grasp_poses(
                TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_LIFT_JOINTS),
                ("move", TIAGO_STACK_HOVER_JOINTS),
                ("move", TIAGO_STACK_LOWER_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_LIFT_JOINTS),
                ("move", TIAGO_READY_JOINTS),
            ]

        elif intent == "pour":
            pre, grasp = self._get_adaptive_grasp_poses(
                TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_LIFT_JOINTS),
                ("move", TIAGO_POUR_TILT_JOINTS),
                ("wait", 2.0),
                ("move", TIAGO_POUR_UPRIGHT_JOINTS),
                ("move", TIAGO_PLACE_TABLE_JOINTS),
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

        # Left arm intents
        elif intent == "left_go_home":
            return [("move_left", TIAGO_LEFT_READY_JOINTS)]
        elif intent == "left_approach_workzone":
            return [("move_left", TIAGO_LEFT_APPROACH_WORKZONE_JOINTS)]
        elif intent == "left_plan_pick_sink":
            pre, grasp = self._get_adaptive_grasp_poses(
                TIAGO_LEFT_PRE_GRASP_JOINTS, TIAGO_LEFT_GRASP_JOINTS)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move_left", pre),
                ("move_left", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move_left", TIAGO_LEFT_LIFT_JOINTS),
                ("move_left", TIAGO_LEFT_PICK_SINK_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move_left", TIAGO_LEFT_READY_JOINTS),
            ]
        elif intent == "left_plan_place":
            return [
                ("move_left", TIAGO_LEFT_PLACE_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move_left", TIAGO_LEFT_READY_JOINTS),
            ]

        # Bimanual: right arm picks, left arm assists
        elif intent == "bimanual_pick_sink":
            pre, grasp = self._get_adaptive_grasp_poses(
                TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move_left", TIAGO_LEFT_APPROACH_WORKZONE_JOINTS),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_LIFT_JOINTS),
                ("move_left", TIAGO_LEFT_PRE_GRASP_JOINTS),
                ("move", TIAGO_PICK_SINK_JOINTS),
                ("move_left", TIAGO_LEFT_READY_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]

        # Navigation intents: (vx, vy, vyaw, duration_sec)
        elif intent == "nav_forward":
            return [("nav", (0.3, 0.0, 0.0, 2.0))]
        elif intent == "nav_backward":
            return [("nav", (-0.3, 0.0, 0.0, 2.0))]
        elif intent == "nav_left":
            return [("nav", (0.0, 0.3, 0.0, 2.0))]
        elif intent == "nav_right":
            return [("nav", (0.0, -0.3, 0.0, 2.0))]
        elif intent == "nav_rotate_left":
            return [("nav", (0.0, 0.0, 0.5, 3.14))]
        elif intent == "nav_rotate_right":
            return [("nav", (0.0, 0.0, -0.5, 3.14))]
        elif intent == "nav_to_table":
            return [
                ("nav", (0.3, 0.0, 0.0, 3.0)),
                ("nav", (0.0, 0.0, 0.0, 0.5)),
            ]
        elif intent == "nav_to_fridge":
            return [
                ("nav", (0.0, 0.0, 0.5, 1.57)),
                ("nav", (0.3, 0.0, 0.0, 2.0)),
                ("nav", (0.0, 0.0, 0.0, 0.5)),
            ]
        elif intent == "nav_to_sink":
            return [
                ("nav", (0.0, 0.0, -0.5, 1.57)),
                ("nav", (0.3, 0.0, 0.0, 2.0)),
                ("nav", (0.0, 0.0, 0.0, 0.5)),
            ]

        # Combined navigation + manipulation
        elif intent == "nav_pick_place_table_to_sink":
            pre, grasp = self._get_adaptive_grasp_poses(
                TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
            return [
                ("nav", (0.3, 0.0, 0.0, 2.0)),
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", TIAGO_LIFT_JOINTS),
                ("move", TIAGO_READY_JOINTS),
                ("nav", (0.0, 0.0, -0.5, 1.57)),
                ("nav", (0.3, 0.0, 0.0, 2.0)),
                ("move", TIAGO_PICK_SINK_JOINTS),
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
            "plan_pick_table": PANDA_EXTENDED_JOINTS,
            "stack_objects": PANDA_EXTENDED_JOINTS,
            "pour": PANDA_EXTENDED_JOINTS,
            "plan_place": PANDA_PLACE_JOINTS,
            "open_close_fridge": PANDA_EXTENDED_JOINTS,
            "open_close_dishwasher": PANDA_EXTENDED_JOINTS,
        }
        return intent_map.get(intent)

    _MAX_GRASP_RETRIES = 2
    _GRASP_RETRY_DZ = -0.02

    def _verify_grasp(self) -> bool:
        """Check whether the gripper is holding an object via IPC."""
        _time.sleep(0.5)
        result = read_grasp_result()
        if result is None:
            self.get_logger().warn("Grasp result IPC unavailable, assuming success")
            return True
        gap = result.get("gripper_gap")
        obj = result.get("object_in_gripper")
        if obj:
            self.get_logger().info(f"Grasp verified: holding '{obj}' (gap={gap})")
            return True
        if gap is not None and gap < _GRIPPER_GAP_EMPTY:
            self.get_logger().warn(f"Empty grasp detected (gap={gap:.4f})")
            return False
        self.get_logger().info(f"Grasp check inconclusive (gap={gap}), assuming success")
        return True

    def _execute_sequence(self, intent_name: str, steps: list):
        """Execute a multi-step sequence synchronously in a background thread."""
        self.get_logger().info(f"Starting sequence for '{intent_name}' ({len(steps)} steps)")
        _last_grasp_move = None
        _last_grasp_group = None
        try:
            for i, (action_type, value) in enumerate(steps):
                self.get_logger().info(f"  Step {i+1}/{len(steps)}: {action_type}")
                if action_type == "move":
                    ok = self._send_goal_sync(value, group_override=None)
                    if not ok:
                        self.get_logger().error(f"  Step {i+1} failed, aborting sequence")
                        break
                    _last_grasp_move = value
                    _last_grasp_group = None
                elif action_type == "move_left":
                    ok = self._send_goal_sync(value, group_override="arm_left_torso")
                    if not ok:
                        self.get_logger().error(f"  Step {i+1} (left arm) failed, aborting sequence")
                        break
                    _last_grasp_move = value
                    _last_grasp_group = "arm_left_torso"
                elif action_type == "gripper":
                    ok = self._send_gripper_sync(value)
                    if not ok:
                        self.get_logger().warn(f"  Gripper step {i+1} failed, continuing")

                    if value == GRIPPER_CLOSED and _last_grasp_move is not None:
                        if not self._verify_grasp():
                            retried = False
                            for attempt in range(1, self._MAX_GRASP_RETRIES + 1):
                                self.get_logger().info(
                                    f"  Retry {attempt}/{self._MAX_GRASP_RETRIES}: "
                                    f"offset dz={self._GRASP_RETRY_DZ * attempt:.3f}")
                                self._send_gripper_sync(GRIPPER_OPEN)
                                _time.sleep(0.3)
                                retry_joints = dict(_last_grasp_move)
                                if "torso_lift_joint" in retry_joints:
                                    retry_joints["torso_lift_joint"] += self._GRASP_RETRY_DZ * attempt
                                retry_joints = clamp_joints(retry_joints)
                                self._send_goal_sync(retry_joints, group_override=_last_grasp_group)
                                self._send_gripper_sync(GRIPPER_CLOSED)
                                if self._verify_grasp():
                                    self.get_logger().info(f"  Retry {attempt} succeeded!")
                                    retried = True
                                    break
                            if not retried:
                                self.get_logger().warn("  All grasp retries failed, continuing sequence")
                elif action_type == "nav":
                    self._send_nav_sync(value)
                elif action_type == "wait":
                    self.get_logger().info(f"  Waiting {value}s...")
                    _time.sleep(float(value))
                _time.sleep(0.5)
            self.get_logger().info(f"Sequence '{intent_name}' complete")
        finally:
            self._executing = False

    def _send_goal_sync(self, joint_goal: dict, group_override: str = None) -> bool:
        if not self._action_client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error("MoveGroup action server not available")
            return False
        group = group_override or self.planning_group
        goal_msg = MoveGroup.Goal()
        goal_msg.request = build_motion_plan_request(
            group, joint_goal, frame_id=self.frame_id, plan_only=self.plan_only
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

    def _send_nav_sync(self, params: tuple):
        """Publish cmd_vel for a given duration. params = (vx, vy, vyaw, duration_sec)."""
        vx, vy, vyaw, duration = params
        self.get_logger().info(f"Nav: vx={vx:.2f} vy={vy:.2f} vyaw={vyaw:.2f} for {duration:.1f}s")
        msg = Twist()
        msg.linear.x = float(vx)
        msg.linear.y = float(vy)
        msg.angular.z = float(vyaw)
        hz = 10.0
        steps = int(duration * hz)
        for _ in range(steps):
            self._cmd_vel_pub.publish(msg)
            _time.sleep(1.0 / hz)
        stop = Twist()
        self._cmd_vel_pub.publish(stop)
        self.get_logger().info("Nav: stopped")

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
