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

import math

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from std_msgs.msg import String

# MoveIt messages
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import (
    Constraints,
    JointConstraint,
    MotionPlanRequest,
    PlanningOptions,
    RobotState,
)
from moveit_msgs.srv import GetPositionIK
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from builtin_interfaces.msg import Time, Duration
from geometry_msgs.msg import Twist, PoseStamped, Pose, Point, Quaternion
from sensor_msgs.msg import JointState


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

# ──────────────────────────────────────────────────────────────────────────────
# Tiago arm_torso joint targets.
#
# USD joint limits (from PhysX):
#    torso_lift_joint : [0.00,  0.35]
#    arm_1_joint      : [-1.178, 1.571]
#    arm_2_joint      : [-1.178, 1.571]
#    arm_3_joint      : [-0.785, 3.927]
#    arm_4_joint      : [-0.393, 2.356]
#    arm_5_joint      : [-2.094, 2.094]
#    arm_6_joint      : [-1.414, 1.414]
#    arm_7_joint      : [-2.094, 2.094]
# ──────────────────────────────────────────────────────────────────────────────

# "Ready" / home pose – arm tucked close to body.
# PAL Robotics standard tuck: shoulder back, elbow bent, wrist folded.
TIAGO_READY_JOINTS = {
    "torso_lift_joint": 0.15,
    "arm_1_joint": 0.20,
    "arm_2_joint": -0.35,
    "arm_3_joint": -0.20,
    "arm_4_joint": 1.90,
    "arm_5_joint": -1.57,
    "arm_6_joint": 1.20,
    "arm_7_joint": 0.0,
}

# Approach workzone – torso up, arm extended forward at mid-height.
TIAGO_APPROACH_WORKZONE_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_1_joint": 1.10,
    "arm_2_joint": -0.50,
    "arm_3_joint": -0.70,
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
    "arm_3_joint": -0.70,
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
GRIPPER_JOINTS = ["gripper_right_left_finger_joint", "gripper_right_right_finger_joint"]

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
    frame_id: str = "base_footprint",
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
PREFER_SIM_NATIVE_IK = os.environ.get("ROBOLAB_PREFER_SIM_NATIVE_IK", "0").lower() in ("1", "true", "yes")
_DISABLE_CORRECTIONS = os.environ.get("ROBOLAB_DISABLE_CORRECTIONS", "0").lower() in ("1", "true", "yes")
_ENABLE_ADAPT_GRASP = os.environ.get("ROBOLAB_ENABLE_ADAPT_GRASP", "0").lower() in ("1", "true", "yes")
_ENABLE_CLOSED_LOOP = os.environ.get("ROBOLAB_ENABLE_CLOSED_LOOP", "0").lower() in ("1", "true", "yes")
_ENABLE_RETRIES = os.environ.get("ROBOLAB_ENABLE_RETRIES", "0").lower() in ("1", "true", "yes")

JOINT_LIMITS = {
    "torso_lift_joint": (0.0, 0.35),
    "arm_1_joint": (-1.18, 1.57),
    "arm_2_joint": (-1.18, 1.57),
    "arm_3_joint": (-0.785, 3.927),
    "arm_4_joint": (-0.393, 2.356),
    "arm_5_joint": (-2.094, 2.094),
    "arm_6_joint": (0.0, 1.414),
    "arm_7_joint": (-2.094, 2.094),
}

REFERENCE_OBJECT_XYZ = (0.6, 0.0, 0.77)

_GRIPPER_GAP_CLOSED_EMPTY = 0.003
_GRIPPER_GAP_BLOCKING_MIN = 0.002
_MAX_PRE_CLOSE_ALIGNMENT_DIST = 0.12
_FAST_CLOSE_ALIGNMENT_DIST = 0.14
_RESIDUAL_CORRECTION_MAX_DIST = 0.18
_MOVEIT_NEAR_ALIGNMENT_DIST = 0.24
_GRASP_VERIFY_SETTLE_SEC = 1.5
_GRASP_VERIFY_WINDOW_SEC = 1.2
_GRASP_VERIFY_POLL_SEC = 0.2
_GRASP_VERIFY_MIN_STABLE_SAMPLES = 3
_GRASP_VERIFY_MIN_CONTACT_SAMPLES = 3


def clamp_joints(joints: dict, margin: float = 0.03) -> dict:
    """Clamp joint values to their mechanical limits with a safety margin
    so PD controllers don't fight against hard stops."""
    clamped = {}
    for name, val in joints.items():
        lo, hi = JOINT_LIMITS.get(name, (-3.14, 3.14))
        clamped[name] = max(lo + margin, min(hi - margin, val))
    return clamped


def _quat_conjugate(q):
    """Return conjugate (inverse for unit quaternion) [w,x,y,z]."""
    return (q[0], -q[1], -q[2], -q[3])


def _quat_rotate(q, v):
    """Rotate vector v by quaternion q=[w,x,y,z]. Returns (x,y,z)."""
    w, x, y, z = q
    vx, vy, vz = v
    # q * v * q^-1  (Hamilton product, v as pure quaternion)
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (vx + w * tx + y * tz - z * ty,
            vy + w * ty + z * tx - x * tz,
            vz + w * tz + x * ty - y * tx)


def _world_to_base_footprint(world_pos, robot_pos, robot_orient):
    """Transform a world-frame position to base_footprint frame.
    Uses full quaternion rotation (pitch/roll/yaw).
    robot_orient is [w, x, y, z] quaternion."""
    dx = world_pos[0] - robot_pos[0]
    dy = world_pos[1] - robot_pos[1]
    dz = world_pos[2] - robot_pos[2]
    q_inv = _quat_conjugate(robot_orient)
    return _quat_rotate(q_inv, (dx, dy, dz))


def _base_footprint_to_world(local_pos, robot_pos, robot_orient):
    """Transform a base_footprint-frame position to world frame.
    Uses full quaternion rotation (pitch/roll/yaw).
    robot_orient is [w, x, y, z] quaternion."""
    rx, ry, rz = _quat_rotate(robot_orient, local_pos)
    return (rx + robot_pos[0], ry + robot_pos[1], rz + robot_pos[2])


def query_object_pose_info(timeout: float = 2.0, preferred_class: str = None,
                           preferred_path: str = None, reference_position=None,
                           exclude_paths: list[str] | None = None):
    """Request object pose info from Isaac Sim via IPC.

    Returns a dict with local/world position, class, and path when available.
    Optional preferred_class/preferred_path bias selection toward a target.
    """
    try:
        FJT_PROXY_DIR.mkdir(parents=True, exist_ok=True)
        query_file = FJT_PROXY_DIR / "query_object_pose.json"
        result_file = FJT_PROXY_DIR / "object_pose_result.json"
        if result_file.exists():
            result_file.unlink()
        payload = {}
        if preferred_class:
            payload["preferred_class"] = preferred_class
        if preferred_path:
            payload["preferred_path"] = preferred_path
        if reference_position:
            payload["reference_position"] = list(reference_position)
        if exclude_paths:
            payload["exclude_paths"] = [str(p) for p in exclude_paths if p]
        query_file.write_text(json.dumps(payload), encoding="utf-8")

        deadline = _time.time() + timeout
        while _time.time() < deadline:
            if result_file.exists():
                data = json.loads(result_file.read_text(encoding="utf-8"))
                if data.get("position"):
                    world_pos = data["position"]
                    robot_pos = data.get("robot_position")
                    robot_orient = data.get("robot_orientation")
                    gripper_center = data.get("gripper_center")
                    grasp_target = data.get("grasp_target")
                    if robot_pos and robot_orient:
                        local_pos = _world_to_base_footprint(world_pos, robot_pos, robot_orient)
                        local_gc = _world_to_base_footprint(gripper_center, robot_pos, robot_orient) if gripper_center else None
                        local_gt = _world_to_base_footprint(grasp_target, robot_pos, robot_orient) if grasp_target else None
                    else:
                        local_pos = tuple(world_pos)
                        local_gc = tuple(gripper_center) if gripper_center else None
                        local_gt = tuple(grasp_target) if grasp_target else None
                    return {
                        "local_position": tuple(local_pos),
                        "world_position": tuple(world_pos),
                        "class": data.get("class", "unknown"),
                        "path": data.get("path"),
                        "gripper_center_world": tuple(gripper_center) if gripper_center else None,
                        "gripper_center_local": tuple(local_gc) if local_gc else None,
                        "grasp_target_world": tuple(grasp_target) if grasp_target else None,
                        "grasp_target_local": tuple(local_gt) if local_gt else None,
                        "blocking_objects": data.get("blocking_objects") or [],
                        "blocking_object_count": int(data.get("blocking_object_count", 0) or 0),
                    }
                return None
            _time.sleep(0.1)
    except Exception:
        pass
    return None


def query_object_pose(timeout: float = 2.0):
    """Request the nearest graspable object pose from Isaac Sim via IPC.
    Returns position in base_footprint frame (relative to robot)."""
    info = query_object_pose_info(timeout=timeout)
    if info:
        return info.get("local_position"), info.get("class", "unknown")
    return None, None


def _get_grasp_target_local(obj_info: dict | None):
    if not obj_info:
        return None
    return obj_info.get("grasp_target_local") or obj_info.get("local_position")


def verify_fk(label: str, intended_local: tuple | None = None, logger=None):
    """Query collector for current gripper position and log FK error vs intended target.
    Returns (gripper_local, error_m) or (None, None)."""
    info = query_object_pose_info(timeout=1.5)
    if not info:
        if logger:
            logger.warn(f"  FK verify [{label}]: no pose info")
        return None, None
    gc = info.get("gripper_center_local")
    if not gc:
        if logger:
            logger.warn(f"  FK verify [{label}]: no gripper center")
        return None, None
    if intended_local and len(intended_local) >= 3:
        dx = gc[0] - intended_local[0]
        dy = gc[1] - intended_local[1]
        dz = gc[2] - intended_local[2]
        err = math.sqrt(dx * dx + dy * dy + dz * dz)
        if logger:
            logger.info(
                f"  FK verify [{label}]: gripper=({gc[0]:.4f},{gc[1]:.4f},{gc[2]:.4f}) "
                f"target=({intended_local[0]:.4f},{intended_local[1]:.4f},{intended_local[2]:.4f}) "
                f"err=({dx:.4f},{dy:.4f},{dz:.4f}) |err|={err:.4f}m"
            )
        return gc, err
    if logger:
        logger.info(f"  FK verify [{label}]: gripper=({gc[0]:.4f},{gc[1]:.4f},{gc[2]:.4f})")
    return gc, None


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


_direct_traj_counter = [100]  # start at 100 to avoid collision with proxy IDs


def _read_joint_state_snapshot() -> dict:
    js_file = FJT_PROXY_DIR / "joint_state.json"
    if not js_file.exists():
        return {}
    try:
        data = json.loads(js_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _wait_for_joint_targets(joint_targets: dict, timeout: float = 10.0, tolerance: float = 0.18, stable_samples: int = 3) -> bool:
    deadline = _time.time() + timeout
    stable = 0
    last_errors = []
    while _time.time() < deadline:
        js_data = _read_joint_state_snapshot()
        if not js_data:
            _time.sleep(0.1)
            continue
        max_err = 0.0
        seen = 0
        cur_errors = []
        for name, target in joint_targets.items():
            cur = None
            if name in js_data and isinstance(js_data[name], dict):
                cur = js_data[name].get("position")
            elif name in js_data and isinstance(js_data[name], (int, float)):
                cur = js_data[name]
            if cur is None:
                continue
            seen += 1
            err = abs(float(cur) - float(target))
            max_err = max(max_err, err)
            cur_errors.append((err, name, float(cur), float(target)))
        if cur_errors:
            last_errors = cur_errors
        if seen and max_err <= tolerance:
            stable += 1
            if stable >= stable_samples:
                return True
        else:
            stable = 0
        _time.sleep(0.12)
    if last_errors:
        preview = ", ".join(
            f"{name}: cur={cur:.3f} tgt={target:.3f} err={err:.3f}"
            for err, name, cur, target in sorted(last_errors, reverse=True)[:4]
        )
        print(f"[moveit_intent_bridge] Joint settle timeout: {preview}", flush=True)
    return False


def send_direct_trajectory(joint_targets: dict, duration: float = 4.0, timeout: float = 30.0):
    """Send joint targets directly to data collector via IPC, bypassing MoveGroup.
    Reads current joint positions from joint_state.json and creates a smooth
    linear interpolation from current to target so the PD controller can track.
    Returns True on success."""
    import time as _t
    try:
        FJT_PROXY_DIR.mkdir(parents=True, exist_ok=True)
        _direct_traj_counter[0] += 1
        traj_id = _direct_traj_counter[0]

        ordered_names = ["torso_lift_joint"] + [f"arm_{i}_joint" for i in range(1, 8)] + GRIPPER_JOINTS
        joint_names = []
        target_positions = []
        used = set()
        for name in ordered_names:
            if name in joint_targets:
                joint_names.append(name)
                target_positions.append(float(joint_targets[name]))
                used.add(name)
        for name, value in joint_targets.items():
            if name in used:
                continue
            joint_names.append(name)
            target_positions.append(float(value))

        if not joint_names:
            return False

        current_positions = list(target_positions)
        try:
            js_data = _read_joint_state_snapshot()
            for i, name in enumerate(joint_names):
                if name in js_data and isinstance(js_data[name], dict):
                    current_positions[i] = float(js_data[name].get("position", target_positions[i]))
                elif name in js_data and isinstance(js_data[name], (int, float)):
                    current_positions[i] = float(js_data[name])
        except Exception:
            pass

        max_delta = max(abs(t - c) for t, c in zip(target_positions, current_positions)) if joint_names else 0.0
        # 1.5 rad/s max joint speed → duration = max_delta / 1.5, with min 2s
        auto_duration = max(2.0, max_delta / 1.5)
        duration = max(duration, auto_duration)

        n_steps = max(20, int(duration * 20))
        points = []
        for step in range(1, n_steps + 1):
            alpha = step / n_steps
            t = duration * alpha
            interp = [
                cur + alpha * (tgt - cur)
                for cur, tgt in zip(current_positions, target_positions)
            ]
            points.append({"t": t, "positions": interp})

        payload = {
            "traj_id": traj_id,
            "joint_names": joint_names,
            "points": points,
            "created_at": _t.time(),
        }
        path = FJT_PROXY_DIR / f"pending_{traj_id}.json"
        tmp = FJT_PROXY_DIR / f"pending_{traj_id}.tmp"
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)

        done_path = FJT_PROXY_DIR / f"done_{traj_id}.json"
        deadline = _t.time() + timeout
        while _t.time() < deadline:
            if done_path.exists():
                try:
                    _done = json.loads(done_path.read_text(encoding="utf-8"))
                except Exception:
                    _done = {"status": "failed", "error": "invalid done payload"}
                done_path.unlink(missing_ok=True)
                return str(_done.get("status", "")).lower() == "succeeded"
            _t.sleep(0.1)
        return False
    except Exception:
        return False


def send_direct_set(joint_targets: dict, timeout: float = 10.0) -> bool:
    """Recovery-only snap of articulation joints for diagnostics or rescue."""
    import time as _t
    try:
        FJT_PROXY_DIR.mkdir(parents=True, exist_ok=True)
        _direct_traj_counter[0] += 1
        traj_id = _direct_traj_counter[0]
        joint_names = list(joint_targets.keys())
        if not joint_names:
            return False
        payload = {
            "traj_id": traj_id,
            "joint_names": joint_names,
            "points": [{
                "t": 0.0,
                "positions": [float(joint_targets[name]) for name in joint_names],
            }],
            "created_at": _t.time(),
            "direct_set": True,
            "recovery_mode": True,
        }
        path = FJT_PROXY_DIR / f"pending_{traj_id}.json"
        tmp = FJT_PROXY_DIR / f"pending_{traj_id}.tmp"
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)

        done_path = FJT_PROXY_DIR / f"done_{traj_id}.json"
        deadline = _t.time() + timeout
        while _t.time() < deadline:
            if done_path.exists():
                try:
                    _done = json.loads(done_path.read_text(encoding="utf-8"))
                except Exception:
                    _done = {"status": "failed", "error": "invalid done payload"}
                done_path.unlink(missing_ok=True)
                return str(_done.get("status", "")).lower() == "succeeded"
            _t.sleep(0.1)
        return False
    except Exception:
        return False


def send_interpolated_teleport(joint_targets: dict, n_steps: int = 8, timeout: float = 60.0) -> bool:
    """Move to target via a series of small teleport steps.
    Each step interpolates between current and target positions,
    allowing physics to carry grasped objects along."""
    import time as _t
    try:
        js_data = _read_joint_state_snapshot()
        current = {}
        for name in joint_targets:
            if name in js_data and isinstance(js_data[name], dict):
                current[name] = float(js_data[name].get("position", joint_targets[name]))
            elif name in js_data and isinstance(js_data[name], (int, float)):
                current[name] = float(js_data[name])
            else:
                current[name] = float(joint_targets[name])
    except Exception:
        current = dict(joint_targets)

    step_timeout = max(5.0, timeout / n_steps)
    for step in range(1, n_steps + 1):
        alpha = step / n_steps
        interp = {}
        for name in joint_targets:
            cur = current.get(name, float(joint_targets[name]))
            tgt = float(joint_targets[name])
            interp[name] = cur + alpha * (tgt - cur)
        ok = send_direct_set(interp, timeout=step_timeout)
        if not ok:
            return False
        _t.sleep(0.1)
    return True


def query_sim_ik(target_world_pos, seed_joints=None, timeout=10.0, max_error_m=0.025):
    """Request IK computation from Isaac Sim using actual robot kinematics.
    Returns joint dict (MoveIt naming) or None on failure."""
    try:
        FJT_PROXY_DIR.mkdir(parents=True, exist_ok=True)
        query_file = FJT_PROXY_DIR / "query_ik.json"
        result_file = FJT_PROXY_DIR / "ik_result.json"
        if result_file.exists():
            result_file.unlink()
        req = {"target_position": list(target_world_pos)}
        if seed_joints:
            req["seed_joints"] = seed_joints
        tmp_query = FJT_PROXY_DIR / f"query_ik.{os.getpid()}.tmp"
        tmp_query.write_text(json.dumps(req), encoding="utf-8")
        tmp_query.replace(query_file)

        deadline = _time.time() + timeout
        while _time.time() < deadline:
            if result_file.exists():
                data = json.loads(result_file.read_text(encoding="utf-8"))
                result_file.unlink(missing_ok=True)
                if data.get("success") and data.get("joints"):
                    return data["joints"]
                if data.get("joints") and data.get("error_m") is not None:
                    try:
                        if float(data["error_m"]) <= float(max_error_m):
                            return data["joints"]
                    except Exception:
                        pass
                return None
            _time.sleep(0.15)
    except Exception:
        pass
    return None


def make_lift_from_grasp(grasp_joints: dict) -> dict:
    """Create a smooth lift pose from the actual grasp configuration.
    Only raises torso and slightly adjusts arm_2 (shoulder pitch) to lift
    without requiring large joint-space jumps that MoveIt can't plan."""
    lift = dict(grasp_joints)
    lift["torso_lift_joint"] = min(lift.get("torso_lift_joint", 0.2) + 0.10, 0.35)
    lift["arm_2_joint"] = lift.get("arm_2_joint", 0.0) - 0.25
    lift["arm_4_joint"] = lift.get("arm_4_joint", 2.0) - 0.20
    return clamp_joints(lift)


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
        frame_id: str = "base_footprint",
        robot: str = "tiago",
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
        self._service_cb_group = ReentrantCallbackGroup()
        self._ik_client = self.create_client(
            GetPositionIK, "/compute_ik", callback_group=self._service_cb_group)
        self._cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self._sub = self.create_subscription(
            String,
            intent_topic,
            self._on_intent,
            10,
        )
        self._executing = False
        self._expected_grasp_object = None
        self._expected_grasp_object_path = None
        self._expected_grasp_world = None
        self._ik_available = self._ik_client.wait_for_service(timeout_sec=3.0)
        if self._ik_available:
            self.get_logger().info("IK service /compute_ik available — will use IK-based grasping")
        else:
            self.get_logger().warn("IK service /compute_ik NOT available — falling back to fixed poses")
        self.get_logger().info(
            f"Bridge: subscribe {intent_topic} -> action {move_action_name} + gripper {gripper_action} + /cmd_vel"
        )
        if _DISABLE_CORRECTIONS:
            _overrides = []
            if _ENABLE_ADAPT_GRASP:
                _overrides.append("adapt_grasp=ON")
            if _ENABLE_CLOSED_LOOP:
                _overrides.append("closed_loop=ON")
            if _ENABLE_RETRIES:
                _overrides.append("retries=ON")
            _override_str = f" (overrides: {', '.join(_overrides)})" if _overrides else ""
            self.get_logger().info(
                f"CORRECTIONS DISABLED (ROBOLAB_DISABLE_CORRECTIONS=1){_override_str}"
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

    # Top-down gripper orientation: 180° around Y so tool Z points down (-Z world).
    _TOP_DOWN_QUAT = Quaternion(x=0.0, y=1.0, z=0.0, w=0.0)
    # 45° from vertical (angled approach, useful for table edges).
    _ANGLED_QUAT = Quaternion(x=0.0, y=0.9239, z=0.0, w=0.3827)
    # 30° from vertical (shallower angle).
    _ANGLED_30_QUAT = Quaternion(x=0.0, y=0.9659, z=0.0, w=0.2588)
    # Side approach: gripper horizontal, pointing forward.
    _SIDE_QUAT = Quaternion(x=0.0, y=0.7071, z=0.0, w=0.7071)
    # Side-tilted: 60° from vertical.
    _ANGLED_60_QUAT = Quaternion(x=0.0, y=0.8660, z=0.0, w=0.5000)

    def _compute_ik(self, target_position, target_orientation=None, seed_joints=None):
        """Call MoveIt IK service for a Cartesian target pose.
        Returns joint dict on success, None on failure."""
        if not self._ik_available:
            return None

        req = GetPositionIK.Request()
        req.ik_request.group_name = self.planning_group
        req.ik_request.avoid_collisions = True
        req.ik_request.timeout.sec = 2
        req.ik_request.timeout.nanosec = 0

        pose = PoseStamped()
        pose.header.frame_id = self.frame_id
        pose.pose.position = Point(
            x=float(target_position[0]),
            y=float(target_position[1]),
            z=float(target_position[2]),
        )
        pose.pose.orientation = target_orientation or self._TOP_DOWN_QUAT
        req.ik_request.pose_stamped = pose

        _seed = seed_joints or TIAGO_PRE_GRASP_JOINTS
        rs = RobotState()
        rs.joint_state = JointState()
        rs.joint_state.name = list(_seed.keys())
        rs.joint_state.position = [float(v) for v in _seed.values()]
        req.ik_request.robot_state = rs

        try:
            future = self._ik_client.call_async(req)
            _deadline = _time.time() + 8.0
            while not future.done():
                _time.sleep(0.05)
                if _time.time() > _deadline:
                    self.get_logger().warn("IK service call timed out (8s)")
                    future.cancel()
                    return None
            response = future.result()
            if response.error_code.val != 1:
                self.get_logger().warn(f"IK failed with code {response.error_code.val}")
                return None
            js = response.solution.joint_state
            result = {}
            for name, pos in zip(js.name, js.position):
                if name in JOINT_LIMITS or name == "torso_lift_joint":
                    result[name] = float(pos)
            if result:
                clamped = clamp_joints(result)
                _max_wrist_swing = 0.0
                for _wj in ("arm_5_joint", "arm_6_joint", "arm_7_joint"):
                    if _wj in clamped and _wj in _seed:
                        _swing = abs(clamped[_wj] - _seed[_wj])
                        _max_wrist_swing = max(_max_wrist_swing, _swing)
                if _max_wrist_swing > 2.0:
                    self.get_logger().warn(
                        f"IK rejected: wrist swing {_max_wrist_swing:.2f} rad exceeds 2.0 rad limit")
                    return None
                _jstr = {k: round(v, 4) for k, v in clamped.items()}
                self.get_logger().info(f"IK solution found ({len(clamped)} joints): {_jstr}")
                return clamped
        except Exception as e:
            self.get_logger().warn(f"IK service error: {e}")
        return None

    _TOOL_TO_FINGER_DIST = 0.12

    _GRASP_OFFSETS = {
        "top-down":  (0.0,  0.0, _TOOL_TO_FINGER_DIST),
        "angled-45": (0.0,  0.0, 0.085),
        "angled-30": (0.0,  0.0, 0.065),
        "angled-60": (0.0,  0.0, 0.10),
        "side":      (0.0,  0.0, 0.05),
    }

    # Empirical FK offset: MoveIt IK solutions place the gripper ~6cm short
    # in X and ~10cm too high in Z compared to Isaac Sim PhysX FK.
    # Compensate by shifting the IK target in the opposite direction.
    _FK_COMP_X = 0.12
    _FK_COMP_Y = -0.02
    _FK_COMP_Z = -0.28

    def _get_ik_grasp_sequence(self, object_xyz, destination_joints, base_pre=None, base_grasp=None):
        """Build a full grasp sequence using IK for the given object position.
        First tries native Isaac Sim IK (accurate kinematics), then falls back
        to MoveIt IK with multiple orientations and seed poses."""
        seed = base_pre or TIAGO_PRE_GRASP_JOINTS
        grasp_offset_z = 0.035
        object_xyz = (
            object_xyz[0] + self._FK_COMP_X,
            object_xyz[1] + self._FK_COMP_Y,
            object_xyz[2] + self._FK_COMP_Z,
        )

        def _try_sim_ik_for_target(local_xyz, seed_joints):
            def _pose_score(joints: dict, reference: dict) -> float:
                score = 0.0
                for _jn, _ref in reference.items():
                    if _jn in joints:
                        score += abs(float(joints[_jn]) - float(_ref))
                score += max(0.0, float(joints.get("arm_4_joint", 0.0)) - 1.9) * 4.0
                score += max(0.0, float(joints.get("arm_2_joint", 0.0)) - 0.8) * 3.0
                score += abs(float(joints.get("arm_6_joint", 0.0)) - float(TIAGO_APPROACH_WORKZONE_JOINTS.get("arm_6_joint", 0.0))) * 0.5
                return score

            grasp_world_local = (local_xyz[0], local_xyz[1], local_xyz[2] + grasp_offset_z)
            pre_grasp_world_local = (grasp_world_local[0], grasp_world_local[1], grasp_world_local[2] + 0.06)
            self.get_logger().info(
                f"Trying sim-native IK for target ({grasp_world_local[0]:.3f}, "
                f"{grasp_world_local[1]:.3f}, {grasp_world_local[2]:.3f})"
            )
            candidate_seeds = []
            for _seed_candidate in (seed_joints, TIAGO_APPROACH_WORKZONE_JOINTS, TIAGO_READY_JOINTS):
                if _seed_candidate and _seed_candidate not in candidate_seeds:
                    candidate_seeds.append(_seed_candidate)

            best_pair = (None, None)
            best_score = None
            for _seed_candidate in candidate_seeds:
                pre_local = query_sim_ik(
                    pre_grasp_world_local,
                    seed_joints=_seed_candidate,
                    timeout=30.0,
                    max_error_m=0.06,
                )
                if not pre_local:
                    continue
                grasp_local = query_sim_ik(
                    grasp_world_local,
                    seed_joints=pre_local,
                    timeout=30.0,
                    max_error_m=0.06,
                )
                if not grasp_local:
                    continue
                _score = (
                    _pose_score(pre_local, TIAGO_APPROACH_WORKZONE_JOINTS)
                    + _pose_score(grasp_local, TIAGO_APPROACH_WORKZONE_JOINTS)
                )
                self.get_logger().info(f"Sim IK candidate score={_score:.3f} seed_arm1={float(_seed_candidate.get('arm_1_joint', 0.0)):.3f}")
                if best_score is None or _score < best_score:
                    best_score = _score
                    best_pair = (pre_local, grasp_local)

            pre_local, grasp_local = best_pair
            if pre_local:
                self.get_logger().info(f"Sim IK pre-grasp solved: {pre_local}")
            if grasp_local:
                self.get_logger().info(f"Sim IK grasp solved: {grasp_local}")
            return pre_local, grasp_local

        pre_ik = None
        grasp_ik = None
        if PREFER_SIM_NATIVE_IK:
            pre_ik, grasp_ik = _try_sim_ik_for_target(object_xyz, seed)
        else:
            self.get_logger().info("Sim-native IK disabled by default; using external IK oracle first")

        if PREFER_SIM_NATIVE_IK and not (pre_ik and grasp_ik) and self._expected_grasp_object_path:
            excluded_paths = [self._expected_grasp_object_path]
            for attempt_idx in range(2):
                alt_info = self._select_pick_candidate(
                    max_candidates=6,
                    excluded_paths=excluded_paths,
                )
                if not alt_info or not alt_info.get("local_position") or not alt_info.get("path"):
                    break
                alt_pos = alt_info["local_position"]
                self.get_logger().info(
                    f"Sim IK retry candidate {attempt_idx + 1}: "
                    f"'{alt_info.get('class', 'unknown')}' at "
                    f"({alt_pos[0]:.3f}, {alt_pos[1]:.3f}, {alt_pos[2]:.3f})"
                )
                alt_pre, alt_grasp = _try_sim_ik_for_target(alt_pos, seed)
                excluded_paths.append(alt_info["path"])
                if alt_pre and alt_grasp:
                    object_xyz = alt_pos
                    pre_ik = alt_pre
                    grasp_ik = alt_grasp
                    self._expected_grasp_object = alt_info.get("class", self._expected_grasp_object)
                    self._expected_grasp_object_path = alt_info.get("path", self._expected_grasp_object_path)
                    self._expected_grasp_world = alt_info.get("world_position", self._expected_grasp_world)
                    self.get_logger().info(
                        f"Switched grasp target to '{self._expected_grasp_object}' after sim IK failure"
                    )
                    break

        _use_sim_ik = bool(pre_ik and grasp_ik)

        if not _use_sim_ik:
            self.get_logger().info("Sim IK failed, falling back to MoveIt IK")
            orientations_to_try = [
                ("top-down", self._TOP_DOWN_QUAT),
                ("angled-45", self._ANGLED_QUAT),
                ("angled-30", self._ANGLED_30_QUAT),
                ("angled-60", self._ANGLED_60_QUAT),
                ("side", self._SIDE_QUAT),
            ]
            seeds_to_try = [seed, TIAGO_APPROACH_WORKZONE_JOINTS]
            pre_ik = None
            grasp_ik = None
            _urdf_usd_offset = getattr(self, '_urdf_usd_offset', None)
            for seed_attempt in seeds_to_try:
                for orient_name, orient_quat in orientations_to_try:
                    dx, dy, dz = self._GRASP_OFFSETS.get(orient_name, (0.0, 0.0, self._TOOL_TO_FINGER_DIST))
                    grasp_pos = (object_xyz[0] + dx, object_xyz[1] + dy, object_xyz[2] + dz)
                    if _urdf_usd_offset:
                        grasp_pos = (grasp_pos[0] + _urdf_usd_offset[0],
                                     grasp_pos[1] + _urdf_usd_offset[1],
                                     grasp_pos[2] + _urdf_usd_offset[2])
                    pre_grasp_pos = (grasp_pos[0], grasp_pos[1], grasp_pos[2] + 0.10)
                    pre_ik = self._compute_ik(pre_grasp_pos, target_orientation=orient_quat, seed_joints=seed_attempt)
                    if pre_ik:
                        grasp_ik = self._compute_ik(grasp_pos, target_orientation=orient_quat, seed_joints=pre_ik)
                        if grasp_ik:
                            self.get_logger().info(f"MoveIt IK solved with {orient_name} approach")
                            break
                    if orient_name == "top-down":
                        self.get_logger().info("Top-down IK failed, trying alternative orientations")
                if pre_ik and grasp_ik:
                    break

        if pre_ik and grasp_ik:
            self.get_logger().info(
                f"Using IK grasp at ({object_xyz[0]:.2f}, {object_xyz[1]:.2f}, {object_xyz[2]:.2f})")
            lift_joints = dict(grasp_ik)
            if "torso_lift_joint" in lift_joints:
                lift_joints["torso_lift_joint"] = min(
                    lift_joints["torso_lift_joint"] + 0.10, 0.35)
            lift_joints = clamp_joints(lift_joints)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre_ik),
                ("move_smooth_direct", grasp_ik),
                ("gripper", GRIPPER_CLOSED),
                ("move_smooth_direct", lift_joints),
                ("move", destination_joints),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]
        return None

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

    def _select_pick_candidate(
        self,
        max_candidates: int = 8,
        excluded_paths: list[str] | None = None,
        reference_position=None,
    ):
        """Query a few objects and choose a bridge-side best candidate for right-arm grasping."""
        excluded_paths = list(excluded_paths or [])
        candidates = []
        for _ in range(max_candidates):
            info = query_object_pose_info(
                timeout=1.5,
                exclude_paths=excluded_paths,
                reference_position=reference_position,
            )
            if not info or not info.get("local_position") or not info.get("path"):
                break
            pos = info["local_position"]
            grip_local = info.get("gripper_center_local")
            blockers = info.get("blocking_objects") or []
            obj_class = str(info.get("class", "unknown")).lower()
            x = float(pos[0])
            y = float(pos[1])
            z = float(pos[2])
            score = (
                abs(x - 0.34) * 1.4
                + abs(y + 0.12) * 2.2
                + abs(z - 0.74) * 0.7
            )
            if grip_local:
                grip_dist = math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(pos, grip_local)))
                score += grip_dist * 1.3
            if x > 0.46:
                score += 1.2 + (x - 0.46) * 5.0
            if x > 0.58:
                score += 1.2 + (x - 0.58) * 8.0
            if x < 0.18:
                score += 0.8 + (0.18 - x) * 2.0
            if y < -0.22:
                score += 1.0 + abs(y + 0.22) * 3.0
            if y > -0.10:
                score += 1.8 + abs(y + 0.10) * 5.5
            if y > -0.02:
                score += 3.0 + (y + 0.02) * 10.0
            if y > 0.02:
                score += 3.5 + (y - 0.02) * 12.0
            if x > 0.48 and y > -0.12:
                score += 1.4 + max(0.0, x - 0.48) * 5.0 + max(0.0, y + 0.12) * 6.0
            if z < 0.64 or z > 0.82:
                score += 1.0 + abs(z - 0.73) * 3.0
            if z > 0.86:
                score += 1.4 + (z - 0.86) * 6.0
            if z > 0.90:
                score += 2.2 + (z - 0.90) * 8.0
            if any(token in obj_class for token in ("plate", "bowl", "clamp", "pitcher")):
                score += 4.2
            if any(token in obj_class for token in ("bottle", "juice", "milk")):
                score += 2.3
            if any(token in obj_class for token in ("glass", "wineglass", "cup_glass")):
                score += 1.2
            if any(token in obj_class for token in ("fruit", "apple", "orange", "banana", "pear", "lemon", "peach")):
                score += 1.6
            if any(token in obj_class for token in ("mug", "cup", "box", "carton", "can")):
                score -= 1.4
            if x > 0.48 and z > 0.84:
                score += 1.8 + max(0.0, x - 0.48) * 4.0 + max(0.0, z - 0.84) * 6.0
            if blockers:
                score += min(4.0, len(blockers) * 0.9)
                for blocker in blockers[:3]:
                    kind = str(blocker.get("kind", ""))
                    dist_target = float(blocker.get("distance_to_target", 0.25) or 0.25)
                    segment_dist = blocker.get("segment_distance")
                    score += max(0.0, 0.22 - dist_target) * 8.0
                    if "line" in kind:
                        score += 1.5
                        if segment_dist is not None:
                            score += max(0.0, 0.18 - float(segment_dist)) * 8.0
                    if "target" in kind:
                        score += 1.0
            candidates.append((score, info))
            excluded_paths.append(info["path"])

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        best_score, best_info = candidates[0]
        best_pos = best_info["local_position"]
        best_blockers = best_info.get("blocking_objects") or []
        self.get_logger().info(
            f"Selected pick candidate: '{best_info.get('class', 'unknown')}' "
            f"at ({best_pos[0]:.3f}, {best_pos[1]:.3f}, {best_pos[2]:.3f}) "
            f"score={best_score:.3f} blockers={len(best_blockers)}"
        )
        return best_info

    def _resolve_intent_sequence(self, intent: str):
        """Map intent to a sequence of steps. Each step is either:
        - ("move", joint_dict)   -- send MoveGroup goal
        - ("gripper", position)  -- send gripper open/close
        Returns None for unknown intents.
        """
        self._expected_grasp_object = None
        self._expected_grasp_object_path = None
        self._expected_grasp_world = None
        if self.robot != "tiago":
            simple = self._resolve_simple_intent(intent)
            return [("move", simple)] if simple else None

        if intent == "go_home":
            return [("move_direct", TIAGO_READY_JOINTS)]
        elif intent == "approach_workzone":
            return [("move_direct", TIAGO_APPROACH_WORKZONE_JOINTS)]

        elif intent in ("plan_pick", "plan_pick_sink"):
            obj_info = query_object_pose_info(timeout=2.0)
            if obj_info and obj_info.get("local_position") is not None:
                obj_pos = obj_info["local_position"]
                obj_class = obj_info.get("class", "unknown")
                self._expected_grasp_object = obj_class
                self._expected_grasp_object_path = obj_info.get("path")
                self._expected_grasp_world = obj_info.get("world_position")
                self.get_logger().info(f"Pick target: '{obj_class}' at {[round(v,3) for v in obj_pos]}")
                ik_seq = self._get_ik_grasp_sequence(
                    obj_pos, TIAGO_PICK_SINK_JOINTS,
                    TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
                if ik_seq:
                    return ik_seq
                pre = adapt_grasp_pose(TIAGO_PRE_GRASP_JOINTS, obj_pos)
                grasp = adapt_grasp_pose(TIAGO_GRASP_JOINTS, obj_pos)
            else:
                pre, grasp = TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS
            lift = make_lift_from_grasp(grasp)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", lift),
                ("move", TIAGO_PICK_SINK_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]
        elif intent == "plan_pick_fridge":
            obj_info = query_object_pose_info(timeout=2.0)
            if obj_info and obj_info.get("local_position") is not None:
                obj_pos = obj_info["local_position"]
                obj_class = obj_info.get("class", "unknown")
                self._expected_grasp_object = obj_class
                self._expected_grasp_object_path = obj_info.get("path")
                self._expected_grasp_world = obj_info.get("world_position")
                self.get_logger().info(f"Pick target: '{obj_class}' at {[round(v,3) for v in obj_pos]}")
                ik_seq = self._get_ik_grasp_sequence(
                    obj_pos, TIAGO_PICK_FRIDGE_JOINTS,
                    TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
                if ik_seq:
                    return ik_seq
                pre = adapt_grasp_pose(TIAGO_PRE_GRASP_JOINTS, obj_pos)
                grasp = adapt_grasp_pose(TIAGO_GRASP_JOINTS, obj_pos)
            else:
                pre, grasp = TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS
            lift = make_lift_from_grasp(grasp)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", lift),
                ("move", TIAGO_PICK_FRIDGE_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]
        elif intent == "plan_pick_dishwasher":
            obj_info = query_object_pose_info(timeout=2.0)
            if obj_info and obj_info.get("local_position") is not None:
                obj_pos = obj_info["local_position"]
                obj_class = obj_info.get("class", "unknown")
                self._expected_grasp_object = obj_class
                self._expected_grasp_object_path = obj_info.get("path")
                self._expected_grasp_world = obj_info.get("world_position")
                self.get_logger().info(f"Pick target: '{obj_class}' at {[round(v,3) for v in obj_pos]}")
                ik_seq = self._get_ik_grasp_sequence(
                    obj_pos, TIAGO_PICK_DISHWASHER_JOINTS,
                    TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
                if ik_seq:
                    return ik_seq
                pre = adapt_grasp_pose(TIAGO_PRE_GRASP_JOINTS, obj_pos)
                grasp = adapt_grasp_pose(TIAGO_GRASP_JOINTS, obj_pos)
            else:
                pre, grasp = TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS
            lift = make_lift_from_grasp(grasp)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", lift),
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
            obj_info = self._select_pick_candidate(max_candidates=3)
            if obj_info and obj_info.get("local_position") is not None:
                obj_pos = obj_info["local_position"]
                planning_target = _get_grasp_target_local(obj_info) or obj_pos
                obj_class = obj_info.get("class", "unknown")
                self._expected_grasp_object = obj_class
                self._expected_grasp_object_path = obj_info.get("path")
                self._expected_grasp_world = obj_info.get("world_position")
                self.get_logger().info(
                    f"Pick target: '{obj_class}' at ({obj_pos[0]:.3f}, {obj_pos[1]:.3f}, {obj_pos[2]:.3f})")
                if planning_target != obj_pos:
                    self.get_logger().info(
                        f"Using grasp target for planning: "
                        f"({planning_target[0]:.3f}, {planning_target[1]:.3f}, {planning_target[2]:.3f})"
                    )
                self._planning_target_local = planning_target
                ik_seq = self._get_ik_grasp_sequence(
                    planning_target, TIAGO_PLACE_TABLE_JOINTS,
                    TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
                if ik_seq:
                    return ik_seq
                self.get_logger().info("IK failed for all orientations, using adaptive fallback")
                if _DISABLE_CORRECTIONS and not _ENABLE_ADAPT_GRASP:
                    pre = TIAGO_PRE_GRASP_JOINTS
                    grasp = TIAGO_GRASP_JOINTS
                else:
                    pre = adapt_grasp_pose(TIAGO_PRE_GRASP_JOINTS, planning_target)
                    grasp = adapt_grasp_pose(TIAGO_GRASP_JOINTS, planning_target)
            else:
                self.get_logger().warn("No object found, using default poses")
                pre, grasp = TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS
            lift = make_lift_from_grasp(grasp)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", lift),
                ("move", TIAGO_PLACE_TABLE_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", TIAGO_READY_JOINTS),
            ]

        elif intent == "stack_objects":
            obj_info = query_object_pose_info(timeout=2.0)
            if obj_info and obj_info.get("local_position") is not None:
                obj_pos = obj_info["local_position"]
                obj_class = obj_info.get("class", "unknown")
                self._expected_grasp_object = obj_class
                self._expected_grasp_object_path = obj_info.get("path")
                self._expected_grasp_world = obj_info.get("world_position")
                ik_seq = self._get_ik_grasp_sequence(
                    obj_pos, TIAGO_STACK_HOVER_JOINTS,
                    TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
                if ik_seq:
                    ik_seq.pop()
                    ik_seq.extend([
                        ("move", TIAGO_STACK_LOWER_JOINTS),
                        ("gripper", GRIPPER_OPEN),
                        ("move", make_lift_from_grasp(TIAGO_STACK_LOWER_JOINTS)),
                        ("move", TIAGO_READY_JOINTS),
                    ])
                    return ik_seq
                pre = adapt_grasp_pose(TIAGO_PRE_GRASP_JOINTS, obj_pos)
                grasp = adapt_grasp_pose(TIAGO_GRASP_JOINTS, obj_pos)
            else:
                pre, grasp = TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS
            lift = make_lift_from_grasp(grasp)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", lift),
                ("move", TIAGO_STACK_HOVER_JOINTS),
                ("move", TIAGO_STACK_LOWER_JOINTS),
                ("gripper", GRIPPER_OPEN),
                ("move", make_lift_from_grasp(TIAGO_STACK_LOWER_JOINTS)),
                ("move", TIAGO_READY_JOINTS),
            ]

        elif intent == "pour":
            obj_info = query_object_pose_info(timeout=2.0)
            if obj_info and obj_info.get("local_position") is not None:
                obj_pos = obj_info["local_position"]
                obj_class = obj_info.get("class", "unknown")
                self._expected_grasp_object = obj_class
                self._expected_grasp_object_path = obj_info.get("path")
                self._expected_grasp_world = obj_info.get("world_position")
                ik_seq = self._get_ik_grasp_sequence(
                    obj_pos, TIAGO_POUR_TILT_JOINTS,
                    TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS)
                if ik_seq:
                    ik_seq.pop()
                    ik_seq.extend([
                        ("wait", 2.0),
                        ("move", TIAGO_POUR_UPRIGHT_JOINTS),
                        ("move", TIAGO_PLACE_TABLE_JOINTS),
                        ("gripper", GRIPPER_OPEN),
                        ("move", TIAGO_READY_JOINTS),
                    ])
                    return ik_seq
                pre = adapt_grasp_pose(TIAGO_PRE_GRASP_JOINTS, obj_pos)
                grasp = adapt_grasp_pose(TIAGO_GRASP_JOINTS, obj_pos)
            else:
                pre, grasp = TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS
            lift = make_lift_from_grasp(grasp)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", lift),
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
            lift = make_lift_from_grasp(grasp)
            return [
                ("gripper", GRIPPER_OPEN),
                ("move_left", TIAGO_LEFT_APPROACH_WORKZONE_JOINTS),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", lift),
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
            obj_info = query_object_pose_info(timeout=2.0)
            if obj_info and obj_info.get("local_position") is not None:
                obj_pos = obj_info["local_position"]
                obj_class = obj_info.get("class", "unknown")
                self._expected_grasp_object = obj_class
                self._expected_grasp_object_path = obj_info.get("path")
                self._expected_grasp_world = obj_info.get("world_position")
                pre = adapt_grasp_pose(TIAGO_PRE_GRASP_JOINTS, obj_pos)
                grasp = adapt_grasp_pose(TIAGO_GRASP_JOINTS, obj_pos)
            else:
                pre, grasp = TIAGO_PRE_GRASP_JOINTS, TIAGO_GRASP_JOINTS
            lift = make_lift_from_grasp(grasp)
            return [
                ("nav", (0.3, 0.0, 0.0, 2.0)),
                ("gripper", GRIPPER_OPEN),
                ("move", pre),
                ("move", grasp),
                ("gripper", GRIPPER_CLOSED),
                ("move", lift),
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

    def _verify_grasp(self, allow_blocking_only: bool = True) -> bool:
        """Check whether the gripper is physically holding an object via IPC.

        We require a short hold window instead of accepting a single frame.
        This reduces false positives where the bridge sees a transient gap
        increase but the object is released immediately afterwards.
        """
        _time.sleep(_GRASP_VERIFY_SETTLE_SEC)
        deadline = _time.time() + _GRASP_VERIFY_WINDOW_SEC
        stable_samples = 0
        contact_samples = 0
        blocking_samples = 0
        empty_samples = 0
        close_samples = 0
        seen_objects = []
        matching_samples = 0
        contact_body_match_samples = 0
        expected_obj = self._expected_grasp_object
        expected_path = self._expected_grasp_object_path
        last_result = None

        while _time.time() < deadline:
            result = read_grasp_result()
            if result is not None:
                last_result = result
                gap = result.get("gripper_gap")
                obj = result.get("object_in_gripper")
                obj_path = result.get("object_in_gripper_path")
                stable = bool(result.get("gripped_object_stable"))
                hold_frames = int(result.get("hold_frames", 0) or 0)
                obj_dist = result.get("object_distance_to_gripper")
                contact_left = result.get("left_finger_contact", False)
                contact_right = result.get("right_finger_contact", False)
                contact_left_count = int(result.get("left_finger_contact_count", 0) or 0)
                contact_right_count = int(result.get("right_finger_contact_count", 0) or 0)
                contact_left_bodies = result.get("left_finger_contact_bodies", []) or []
                contact_right_bodies = result.get("right_finger_contact_bodies", []) or []
                any_contact = (
                    bool(contact_left)
                    or bool(contact_right)
                    or contact_left_count > 0
                    or contact_right_count > 0
                )

                if obj:
                    seen_objects.append(obj)
                if obj_dist is not None and float(obj_dist) <= 0.10:
                    close_samples += 1
                if obj and stable and hold_frames >= 3:
                    stable_samples += 1
                    if expected_path:
                        if obj_path == expected_path:
                            matching_samples += 1
                    elif expected_obj is None or obj == expected_obj:
                        matching_samples += 1
                if any_contact:
                    contact_samples += 1
                if expected_path and any(expected_path in str(body) for body in (contact_left_bodies + contact_right_bodies)):
                    contact_body_match_samples += 1
                if gap is not None and gap > _GRIPPER_GAP_CLOSED_EMPTY:
                    blocking_samples += 1
                if gap is not None and gap <= _GRIPPER_GAP_CLOSED_EMPTY:
                    empty_samples += 1
            _time.sleep(_GRASP_VERIFY_POLL_SEC)

        if last_result is None:
            self.get_logger().warn("Grasp result IPC unavailable, treating grasp as failed")
            return False

        gap = last_result.get("gripper_gap")
        obj = last_result.get("object_in_gripper")
        hold_frames = int(last_result.get("hold_frames", 0) or 0)
        contact_force = last_result.get("contact_forces", {})
        self.get_logger().info(
            "Grasp check: "
            f"gap={gap}, obj={obj}, hold_frames={hold_frames}, "
            f"stable_samples={stable_samples}, matching={matching_samples}, "
            f"expected={expected_obj}, expected_path={expected_path}, contacts={contact_samples}, "
            f"contact_path_matches={contact_body_match_samples}, close={close_samples}, "
            f"blocking={blocking_samples}, empty={empty_samples}, force={contact_force}"
        )

        if (
            stable_samples >= _GRASP_VERIFY_MIN_STABLE_SAMPLES
            and close_samples >= _GRASP_VERIFY_MIN_STABLE_SAMPLES
            and contact_samples >= _GRASP_VERIFY_MIN_STABLE_SAMPLES
            and (
                expected_obj is None
                or matching_samples >= _GRASP_VERIFY_MIN_STABLE_SAMPLES
                or contact_body_match_samples >= _GRASP_VERIFY_MIN_STABLE_SAMPLES
            )
        ):
            held_obj = obj or (max(seen_objects, key=seen_objects.count) if seen_objects else "unknown")
            self.get_logger().info(f"Grasp verified: holding '{held_obj}'")
            return True
        if expected_obj is not None and stable_samples >= _GRASP_VERIFY_MIN_STABLE_SAMPLES:
            held_obj = obj or (max(seen_objects, key=seen_objects.count) if seen_objects else "unknown")
            self.get_logger().warn(
                f"Wrong object grasped: expected '{expected_obj}', observed '{held_obj}'"
            )
            return False
        if empty_samples >= _GRASP_VERIFY_MIN_STABLE_SAMPLES:
            self.get_logger().warn(
                f"Empty grasp: gripper repeatedly closed to gap={gap:.4f} <= {_GRIPPER_GAP_CLOSED_EMPTY}"
            )
            return False
        if contact_samples >= _GRASP_VERIFY_MIN_CONTACT_SAMPLES and blocking_samples >= _GRASP_VERIFY_MIN_CONTACT_SAMPLES:
            self.get_logger().warn("Grasp is only contact-based without stable object tracking; treating as failed")
            return False
        if blocking_samples >= _GRASP_VERIFY_MIN_STABLE_SAMPLES:
            if not allow_blocking_only and not _DISABLE_CORRECTIONS:
                self.get_logger().warn(
                    "Blocking-only grasp ignored because pre-close alignment stayed too far from target"
                )
                return False
            if gap is not None and float(gap) >= _GRIPPER_GAP_BLOCKING_MIN:
                self.get_logger().info(
                    f"Grasp verified via blocking: gap={gap:.4f}, blocking={blocking_samples} — object blocks gripper closure"
                )
                return True
            self.get_logger().warn(
                f"Object appears to block closure (gap={gap}), but gap too small to confirm grasp "
                f"(need >= {_GRIPPER_GAP_BLOCKING_MIN:.3f})"
            )
            return False
        self.get_logger().warn("Grasp verification failed: no stable hold window observed")
        return False

    def _get_target_retry_joints(self, fallback_joints: dict) -> dict:
        """Re-target retries toward the originally selected object when possible."""
        if not self._expected_grasp_object and not self._expected_grasp_object_path:
            return clamp_joints(dict(fallback_joints))

        obj_info = query_object_pose_info(
            timeout=1.5,
            preferred_class=self._expected_grasp_object,
            preferred_path=self._expected_grasp_object_path,
            reference_position=self._expected_grasp_world,
        )
        if not obj_info or not obj_info.get("local_position"):
            return clamp_joints(dict(fallback_joints))

        target_pos = _get_grasp_target_local(obj_info) or obj_info["local_position"]
        self._expected_grasp_object = obj_info.get("class", self._expected_grasp_object)
        self._expected_grasp_object_path = obj_info.get("path", self._expected_grasp_object_path)
        self._expected_grasp_world = obj_info.get("world_position", self._expected_grasp_world)
        self.get_logger().info(
            f"  Retry retargeted to '{self._expected_grasp_object}' grasp target at "
            f"({target_pos[0]:.3f}, {target_pos[1]:.3f}, {target_pos[2]:.3f})"
        )
        return adapt_grasp_pose(TIAGO_GRASP_JOINTS, target_pos)

    def _log_blocking_objects(self, obj_info: dict | None, prefix: str = "") -> None:
        if not obj_info:
            return
        blockers = obj_info.get("blocking_objects") or []
        if not blockers:
            return
        preview = blockers[:2]
        summary = ", ".join(
            f"{item.get('class', 'unknown')}[{item.get('kind', 'nearby')}] "
            f"dt={float(item.get('distance_to_target', 0.0)):.2f}"
            + (
                f" ds={float(item.get('segment_distance', 0.0)):.2f}"
                if item.get("segment_distance") is not None else ""
            )
            for item in preview
        )
        label = f"{prefix}: " if prefix else ""
        self.get_logger().info(
            f"  {label}blocking objects near grasp corridor ({len(blockers)}): {summary}"
        )

    def _refine_sim_grasp(self, grasp_offset_z: float, fallback_joints: dict | None = None) -> dict | None:
        """Run a closed-loop sim-IK refinement from the robot's current state."""
        if not self._expected_grasp_object and not self._expected_grasp_object_path:
            return None
        obj_info = query_object_pose_info(
            timeout=1.5,
            preferred_class=self._expected_grasp_object,
            preferred_path=self._expected_grasp_object_path,
            reference_position=self._expected_grasp_world,
        )
        if not obj_info or not obj_info.get("world_position"):
            return None
        self._expected_grasp_world = obj_info.get("world_position", self._expected_grasp_world)
        self._log_blocking_objects(obj_info, "refine")
        grip_local = obj_info.get("gripper_center_local")
        target_local = _get_grasp_target_local(obj_info)
        err_dx = err_dy = err_dz = None
        if grip_local and target_local:
            err_dx = float(target_local[0] - grip_local[0])
            err_dy = float(target_local[1] - grip_local[1])
            err_dz = float(target_local[2] - grip_local[2])
            self.get_logger().info(
                "  Closed-loop align error: "
                f"dx={err_dx:.3f}, "
                f"dy={err_dy:.3f}, "
                f"dz={err_dz:.3f}"
            )
        target_local_for_ik = None
        _REFINE_GAIN = 0.6
        if target_local:
            def _bounded_cart(val: float, limit: float) -> float:
                return max(-limit, min(limit, val))

            cart_dx = cart_dy = cart_dz = 0.0
            if err_dx is not None and err_dy is not None and err_dz is not None:
                cart_dx = _bounded_cart(err_dx * _REFINE_GAIN, 0.05)
                cart_dy = _bounded_cart(err_dy * _REFINE_GAIN, 0.05)
                cart_dz = _bounded_cart(err_dz * _REFINE_GAIN, 0.03)
            target_local_for_ik = (
                float(target_local[0]) + cart_dx,
                float(target_local[1]) + cart_dy,
                float(target_local[2]) + float(grasp_offset_z) + cart_dz,
            )
            if abs(cart_dx) > 1e-3 or abs(cart_dy) > 1e-3 or abs(cart_dz) > 1e-3:
                self.get_logger().info(
                    f"  Applying Cartesian refine correction (gain={_REFINE_GAIN}): "
                    f"dx={cart_dx:.3f}, dy={cart_dy:.3f}, dz={cart_dz:.3f}"
                )
        refined = (
            query_sim_ik(
                target_local_for_ik,
                seed_joints=fallback_joints,
                timeout=20.0,
                max_error_m=0.08,
            )
            if target_local_for_ik
            else None
        )
        candidate = dict(refined or fallback_joints or {})
        if refined:
            self.get_logger().info("  Closed-loop sim-IK refinement solved")

        return clamp_joints(candidate) if candidate else None

    def _wait_for_target_alignment(self, timeout: float = 4.0, accept_distance_m: float = 0.45) -> float | None:
        """Wait briefly for the real gripper center to settle toward the intended target."""
        if not self._expected_grasp_object and not self._expected_grasp_object_path:
            return None

        deadline = _time.time() + timeout
        first_dist = None
        best_dist = None
        last_obj_info = None
        while _time.time() < deadline:
            obj_info = query_object_pose_info(
                timeout=0.5,
                preferred_class=self._expected_grasp_object,
                preferred_path=self._expected_grasp_object_path,
                reference_position=self._expected_grasp_world,
            )
            last_obj_info = obj_info
            if obj_info and obj_info.get("world_position"):
                self._expected_grasp_world = obj_info.get("world_position", self._expected_grasp_world)
            grip_local = obj_info.get("gripper_center_local") if obj_info else None
            target_local = _get_grasp_target_local(obj_info)
            if grip_local and target_local:
                dist = math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(target_local, grip_local)))
                if first_dist is None:
                    first_dist = dist
                best_dist = dist if best_dist is None else min(best_dist, dist)
                if dist <= accept_distance_m:
                    self.get_logger().info(
                        f"  Alignment settled near target: dist={dist:.3f}m"
                    )
                    return dist
            _time.sleep(0.2)

        if first_dist is not None and best_dist is not None:
            self.get_logger().info(
                f"  Alignment settle window: start={first_dist:.3f}m best={best_dist:.3f}m"
            )
            if best_dist > accept_distance_m and last_obj_info:
                self._log_blocking_objects(last_obj_info, "alignment")
        return best_dist

    def _compute_closed_loop_moveit_grasp(
        self,
        fallback_joints: dict | None,
        grasp_offset_z: float = 0.035,
        error_bias_gain_xy: float = 0.0,
        error_bias_gain_z: float = 0.0,
        target_z_bias: float = 0.0,
    ) -> dict | None:
        """Use live object/gripper error to build a corrected MoveIt IK target."""
        if not fallback_joints:
            return None
        obj_info = query_object_pose_info(
            timeout=1.5,
            preferred_class=self._expected_grasp_object,
            preferred_path=self._expected_grasp_object_path,
            reference_position=self._expected_grasp_world,
        )
        target_local = _get_grasp_target_local(obj_info)
        if not obj_info or not target_local or not obj_info.get("gripper_center_local"):
            return None

        self._expected_grasp_world = obj_info.get("world_position", self._expected_grasp_world)
        grip_local = obj_info["gripper_center_local"]
        err_dx = float(target_local[0] - grip_local[0])
        err_dy = float(target_local[1] - grip_local[1])
        err_dz = float(target_local[2] - grip_local[2])
        dist = math.sqrt(err_dx * err_dx + err_dy * err_dy + err_dz * err_dz)
        self.get_logger().info(
            "  Closed-loop MoveIt correction: "
            f"dist={dist:.3f}, dx={err_dx:.3f}, dy={err_dy:.3f}, dz={err_dz:.3f}"
        )
        if dist <= 0.05:
            return None

        def _bounded(val: float, limit: float) -> float:
            return max(-limit, min(limit, val))

        base_target = (
            float(target_local[0]),
            float(target_local[1]),
            float(target_local[2] + grasp_offset_z),
        )
        bias_x = _bounded(err_dx * error_bias_gain_xy, 0.05)
        bias_y = _bounded(err_dy * error_bias_gain_xy, 0.03)
        bias_z = _bounded(err_dz * error_bias_gain_z, 0.04) + float(target_z_bias)
        if abs(bias_x) > 1e-3 or abs(bias_y) > 1e-3 or abs(bias_z) > 1e-3:
            self.get_logger().info(
                "  Closed-loop MoveIt target bias: "
                f"bx={bias_x:.3f}, by={bias_y:.3f}, bz={bias_z:.3f}"
            )
        corrected_target = (
            base_target[0] + bias_x,
            base_target[1] + bias_y,
            base_target[2] + bias_z,
        )
        for _orient_name, _orient_q in [
            ("angled-45", self._ANGLED_QUAT),
            ("top-down", self._TOP_DOWN_QUAT),
            ("angled-30", self._ANGLED_30_QUAT),
        ]:
            corrected = self._compute_ik(
                corrected_target,
                target_orientation=_orient_q,
                seed_joints=fallback_joints,
            )
            if corrected:
                self.get_logger().info(f"  Closed-loop MoveIt IK solved with {_orient_name}")
                return corrected
        return None

    def _compute_preclose_nudge(self, fallback_joints: dict | None) -> dict | None:
        """Build a short final nudge before gripper close from live alignment error."""
        if not self._expected_grasp_object and not self._expected_grasp_object_path:
            return None

        obj_info = query_object_pose_info(
            timeout=1.0,
            preferred_class=self._expected_grasp_object,
            preferred_path=self._expected_grasp_object_path,
            reference_position=self._expected_grasp_world,
        )
        target_local = _get_grasp_target_local(obj_info)
        if not obj_info or not target_local or not obj_info.get("gripper_center_local"):
            return None

        self._expected_grasp_world = obj_info.get("world_position", self._expected_grasp_world)
        grip_local = obj_info["gripper_center_local"]
        err_dx = float(target_local[0] - grip_local[0])
        err_dy = float(target_local[1] - grip_local[1])
        err_dz = float(target_local[2] - grip_local[2])
        dist = math.sqrt(err_dx * err_dx + err_dy * err_dy + err_dz * err_dz)
        if dist <= 0.05 and abs(err_dz) <= 0.03 and abs(err_dy) <= 0.03:
            return None

        def _bounded(val: float, limit: float) -> float:
            return max(-limit, min(limit, val))

        base = dict(fallback_joints or {})
        if not base:
            return None
        nudged = dict(base)
        nudged["torso_lift_joint"] = nudged.get("torso_lift_joint", 0.0) + _bounded(err_dz * 0.45, 0.10)
        nudged["arm_1_joint"] = nudged.get("arm_1_joint", 0.0) + _bounded(err_dy * 0.75, 0.24)
        nudged["arm_2_joint"] = nudged.get("arm_2_joint", 0.0) + _bounded(err_dx * -0.12, 0.04) + _bounded(err_dy * -0.12, 0.06)
        nudged["arm_4_joint"] = nudged.get("arm_4_joint", 0.0) + _bounded(err_dz * -0.34, 0.14)
        self.get_logger().info(
            "  Pre-close nudge from live error: "
            f"dist={dist:.3f}, dx={err_dx:.3f}, dy={err_dy:.3f}, dz={err_dz:.3f}"
        )
        return clamp_joints(nudged)

    def _verify_blocking_hold_with_micro_lift(self, grasp_joints: dict | None) -> bool:
        """Confirm that a blocking-only grasp actually carries the object on lift."""
        if not grasp_joints or (not self._expected_grasp_object and not self._expected_grasp_object_path):
            return False

        baseline = query_object_pose_info(
            timeout=1.0,
            preferred_class=self._expected_grasp_object,
            preferred_path=self._expected_grasp_object_path,
            reference_position=self._expected_grasp_world,
        )
        baseline_target = _get_grasp_target_local(baseline)
        if not baseline or not baseline.get("world_position") or not baseline.get("gripper_center_local") or not baseline_target:
            return False

        self._expected_grasp_world = baseline.get("world_position", self._expected_grasp_world)
        baseline_z = float(baseline["world_position"][2])
        baseline_dist = math.sqrt(sum(
            (float(a) - float(b)) ** 2
            for a, b in zip(baseline_target, baseline["gripper_center_local"])
        ))

        lifted_joints = dict(grasp_joints)
        lifted_joints["torso_lift_joint"] = lifted_joints.get("torso_lift_joint", 0.0) + 0.035
        lifted_joints = clamp_joints(lifted_joints)

        lifted_ok = send_direct_trajectory(lifted_joints, duration=2.0, timeout=6.0)
        if not lifted_ok:
            return False
        _time.sleep(1.5)

        lifted = query_object_pose_info(
            timeout=1.0,
            preferred_class=self._expected_grasp_object,
            preferred_path=self._expected_grasp_object_path,
            reference_position=self._expected_grasp_world,
        )

        send_direct_trajectory(grasp_joints, duration=1.5, timeout=6.0)
        _time.sleep(0.5)

        lifted_target = _get_grasp_target_local(lifted)
        if not lifted or not lifted.get("world_position") or not lifted.get("gripper_center_local") or not lifted_target:
            return False

        self._expected_grasp_world = lifted.get("world_position", self._expected_grasp_world)
        lifted_z = float(lifted["world_position"][2])
        lifted_dist = math.sqrt(sum(
            (float(a) - float(b)) ** 2
            for a, b in zip(lifted_target, lifted["gripper_center_local"])
        ))
        rise = lifted_z - baseline_z
        self.get_logger().info(
            "  Blocking micro-lift check: "
            f"baseline_dist={baseline_dist:.3f}m lifted_dist={lifted_dist:.3f}m rise={rise:.3f}m"
        )
        return rise >= 0.01 and lifted_dist <= 0.50

    def _resolve_verified_holding_object(self, grasp_result: dict | None) -> str:
        """Prefer the expected grasp target once lift verification proves the hold is real."""
        result = grasp_result or {}
        held_obj = result.get("object_in_gripper")
        if held_obj:
            return str(held_obj)
        if self._expected_grasp_object:
            return str(self._expected_grasp_object)
        if self._expected_grasp_object_path:
            return str(self._expected_grasp_object_path).rsplit("/", 1)[-1]
        return "unknown"

    def _execute_sequence(self, intent_name: str, steps: list):
        """Execute a multi-step sequence synchronously in a background thread."""
        self.get_logger().info(f"Starting sequence for '{intent_name}' ({len(steps)} steps)")
        _last_grasp_move = None
        _last_grasp_group = None
        _holding_object = None
        _best_grasp_move = None
        _best_grasp_dist = None
        try:
            for i, (action_type, value) in enumerate(steps):
                self.get_logger().info(f"  Step {i+1}/{len(steps)}: {action_type}")
                if action_type == "move_direct":
                    self.get_logger().info(f"  Direct trajectory: {list(value.keys())[:3]}...")
                    direct_targets = clamp_joints(value)
                    snapped = send_direct_trajectory(direct_targets, duration=2.0, timeout=15.0)
                    if not snapped:
                        self.get_logger().warn(f"  Step {i+1}: trajectory failed, falling back to direct_set")
                        snapped = send_direct_set(direct_targets, timeout=6.0)
                    if not snapped:
                        self.get_logger().error(f"  Step {i+1} direct move failed, aborting")
                        break
                    _last_grasp_move = value
                    _last_grasp_group = None
                    if _holding_object is None:
                        settled = _wait_for_joint_targets(
                            direct_targets,
                            timeout=3.0,
                            tolerance=0.12,
                            stable_samples=2,
                        )
                        if settled:
                            self.get_logger().info(f"  Step {i+1}: direct_set settled")
                        else:
                            self.get_logger().warn(f"  Step {i+1}: direct_set applied, settling incomplete")
                        _dist = self._wait_for_target_alignment(timeout=3.0, accept_distance_m=0.35)
                        if _dist is not None and (_best_grasp_dist is None or _dist < _best_grasp_dist):
                            _best_grasp_dist = _dist
                            _best_grasp_move = dict(direct_targets)
                elif action_type == "move_precise_direct":
                    self.get_logger().info(f"  Precise PD trajectory: {list(value.keys())[:3]}...")
                    precise_targets = clamp_joints(value)
                    ok = send_direct_trajectory(precise_targets, duration=6.0, timeout=35.0)
                    if not ok:
                        self.get_logger().error(f"  Step {i+1} PD trajectory failed (no teleport), aborting")
                        break
                    _last_grasp_move = value
                    _last_grasp_group = None
                    if _holding_object is None:
                        settled = _wait_for_joint_targets(
                            precise_targets,
                            timeout=2.5,
                            tolerance=0.14,
                            stable_samples=2,
                        )
                        if settled:
                            self.get_logger().info(f"  Step {i+1}: precise direct settled")
                        else:
                            self.get_logger().warn(f"  Step {i+1}: precise direct dispatched, settling incomplete")
                        _dist = self._wait_for_target_alignment(timeout=1.5, accept_distance_m=0.30)
                        if _dist is not None and (_best_grasp_dist is None or _dist < _best_grasp_dist):
                            _best_grasp_dist = _dist
                            _best_grasp_move = dict(precise_targets)
                        _fk_target = getattr(self, '_planning_target_local', None)
                        verify_fk(f"step{i+1}_precise", intended_local=_fk_target, logger=self.get_logger())
                elif action_type == "move_smooth_direct":
                    self.get_logger().info(f"  Smooth direct trajectory: {list(value.keys())[:3]}...")
                    smooth_targets = clamp_joints(value)
                    ok = send_direct_trajectory(smooth_targets, duration=6.0, timeout=35.0)
                    if not ok:
                        self.get_logger().error(f"  Step {i+1} PD trajectory failed (no teleport fallback), aborting")
                        break
                    _last_grasp_move = value
                    _last_grasp_group = None
                    if _holding_object is None:
                        settled = _wait_for_joint_targets(
                            smooth_targets,
                            timeout=6.0,
                            tolerance=0.25,
                            stable_samples=2,
                        )
                        if settled:
                            self.get_logger().info(f"  Step {i+1}: smooth direct settled")
                        else:
                            self.get_logger().warn(f"  Step {i+1}: smooth direct dispatched, settling incomplete")
                        self._wait_for_target_alignment(timeout=2.5, accept_distance_m=0.45)
                elif action_type == "direct_set":
                    ds_targets = clamp_joints(value)
                    self.get_logger().info(f"  Direct-set: {list(ds_targets.keys())[:4]}...")
                    ds_ok = send_direct_set(ds_targets, timeout=10.0)
                    if not ds_ok:
                        ds_ok = send_direct_trajectory(ds_targets, duration=2.0, timeout=10.0)
                    if not ds_ok:
                        self.get_logger().error(f"  Step {i+1} direct_set failed, aborting")
                        break
                    _time.sleep(0.3)
                    _last_grasp_move = value
                    _last_grasp_group = None
                    if _holding_object is None:
                        _dist = self._wait_for_target_alignment(timeout=2.0, accept_distance_m=0.40)
                        if _dist is not None and (_best_grasp_dist is None or _dist < _best_grasp_dist):
                            _best_grasp_dist = _dist
                            _best_grasp_move = dict(ds_targets)
                elif action_type == "move":
                    ok = self._send_goal_sync(value, group_override=None)
                    if not ok:
                        perturbed = dict(value)
                        for _jn in ("arm_2_joint", "arm_3_joint", "arm_4_joint"):
                            if _jn in perturbed:
                                perturbed[_jn] += 0.05
                        perturbed = clamp_joints(perturbed)
                        self.get_logger().info(f"  Step {i+1} failed, retrying with perturbation")
                        ok = self._send_goal_sync(perturbed, group_override=None)
                        if not ok:
                            self.get_logger().error(f"  Step {i+1} retry also failed, aborting")
                            break
                        value = perturbed
                    _last_grasp_move = value
                    _last_grasp_group = None
                    _fk_target = getattr(self, '_planning_target_local', None)
                    verify_fk(f"step{i+1}_move", intended_local=_fk_target, logger=self.get_logger())
                elif action_type == "move_left":
                    ok = self._send_goal_sync(value, group_override="arm_left_torso")
                    if not ok:
                        self.get_logger().error(f"  Step {i+1} (left arm) failed, aborting sequence")
                        break
                    _last_grasp_move = value
                    _last_grasp_group = "arm_left_torso"
                elif action_type == "gripper":
                    if value == GRIPPER_CLOSED and _holding_object is not None:
                        self.get_logger().info(f"  Skip gripper close: already holding '{_holding_object}'")
                        _time.sleep(0.5)
                        continue
                    if value == GRIPPER_CLOSED and _best_grasp_move:
                        if _last_grasp_move != _best_grasp_move:
                            self.get_logger().info(
                                f"  Restoring best grasp pose before close: dist={_best_grasp_dist:.3f}m"
                            )
                            _restore_ok = send_direct_trajectory(_best_grasp_move, duration=0.8, timeout=5.0)
                            if not _restore_ok:
                                _restore_ok = send_direct_set(_best_grasp_move, timeout=4.0)
                            if _restore_ok:
                                _last_grasp_move = dict(_best_grasp_move)
                                _wait_for_joint_targets(
                                    _best_grasp_move,
                                    timeout=2.0,
                                    tolerance=0.12,
                                    stable_samples=2,
                                )
                                _restored_dist = self._wait_for_target_alignment(timeout=1.0, accept_distance_m=0.20)
                                if _restored_dist is not None and (
                                    _best_grasp_dist is None or _restored_dist < _best_grasp_dist
                                ):
                                    self.get_logger().info(
                                        f"  Restored best grasp pose improved alignment: "
                                        f"{_best_grasp_dist if _best_grasp_dist is not None else float('nan'):.3f}m -> "
                                        f"{_restored_dist:.3f}m"
                                    )
                                    _best_grasp_dist = _restored_dist
                        if (
                            not PREFER_SIM_NATIVE_IK
                            and (not _DISABLE_CORRECTIONS or _ENABLE_CLOSED_LOOP)
                            and _best_grasp_dist is not None
                            and _best_grasp_dist > 0.12
                        ):
                            for _cl_iter in range(2):
                                _closed_loop_moveit = self._compute_closed_loop_moveit_grasp(
                                    _best_grasp_move,
                                    grasp_offset_z=0.035,
                                )
                                if not _closed_loop_moveit:
                                    break
                                self.get_logger().info(
                                    f"  Trying closed-loop MoveIt correction {(_cl_iter + 1)}/2 before close: "
                                    f"dist={_best_grasp_dist:.3f}m"
                                )
                                _cl_ok = send_direct_trajectory(_closed_loop_moveit, duration=1.0, timeout=8.0)
                                if not _cl_ok:
                                    _cl_ok = send_direct_set(_closed_loop_moveit, timeout=5.0)
                                if not _cl_ok:
                                    break
                                _wait_for_joint_targets(
                                    _closed_loop_moveit,
                                    timeout=2.5,
                                    tolerance=0.12,
                                    stable_samples=2,
                                )
                                _cl_dist = self._wait_for_target_alignment(timeout=0.8, accept_distance_m=0.20)
                                if _cl_dist is None or _cl_dist >= (_best_grasp_dist - 0.01):
                                    _restore_cl = send_direct_trajectory(_best_grasp_move, duration=0.5, timeout=4.0)
                                    if not _restore_cl:
                                        _restore_cl = send_direct_set(_best_grasp_move, timeout=4.0)
                                    if _restore_cl:
                                        _last_grasp_move = dict(_best_grasp_move)
                                        _wait_for_joint_targets(
                                            _best_grasp_move,
                                            timeout=1.5,
                                            tolerance=0.12,
                                            stable_samples=2,
                                        )
                                        self._wait_for_target_alignment(timeout=0.4, accept_distance_m=0.20)
                                    break
                                self.get_logger().info(
                                    f"  Closed-loop MoveIt correction improved alignment: "
                                    f"{_best_grasp_dist:.3f}m -> {_cl_dist:.3f}m"
                                )
                                _best_grasp_dist = _cl_dist
                                _best_grasp_move = dict(_closed_loop_moveit)
                                _last_grasp_move = dict(_closed_loop_moveit)
                                if _best_grasp_dist <= _RESIDUAL_CORRECTION_MAX_DIST:
                                    break
                        _near_moveit_alignment = (
                            _best_grasp_dist is not None
                            and _best_grasp_dist <= _MOVEIT_NEAR_ALIGNMENT_DIST
                        )
                        if (
                            not _DISABLE_CORRECTIONS
                            and _best_grasp_dist is not None
                            and _best_grasp_dist > 0.05
                            and _best_grasp_dist > _FAST_CLOSE_ALIGNMENT_DIST
                            and not _near_moveit_alignment
                        ):
                            for _nudge_attempt in range(2):
                                nudge_joints = self._compute_preclose_nudge(_best_grasp_move)
                                if not nudge_joints:
                                    break
                                self.get_logger().info(
                                    f"  Trying pre-close nudge {(_nudge_attempt + 1)}/2 from best pose: dist={_best_grasp_dist:.3f}m"
                                )
                                _nudge_ok = send_direct_trajectory(nudge_joints, duration=0.6, timeout=4.0)
                                if not _nudge_ok:
                                    _nudge_ok = send_direct_set(nudge_joints, timeout=4.0)
                                if not _nudge_ok:
                                    break
                                _wait_for_joint_targets(
                                    nudge_joints,
                                    timeout=2.0,
                                    tolerance=0.12,
                                    stable_samples=2,
                                )
                                nudge_dist = self._wait_for_target_alignment(timeout=1.0, accept_distance_m=0.20)
                                if nudge_dist is not None and nudge_dist < (_best_grasp_dist - 0.005):
                                    self.get_logger().info(
                                        f"  Pre-close nudge improved alignment: {_best_grasp_dist:.3f}m -> {nudge_dist:.3f}m"
                                    )
                                    _best_grasp_dist = nudge_dist
                                    _best_grasp_move = dict(nudge_joints)
                                    _last_grasp_move = dict(nudge_joints)
                                    if _best_grasp_dist <= 0.08:
                                        break
                                    continue
                                self.get_logger().info("  Pre-close nudge did not improve alignment, restoring best pose")
                                _nudge_restore = send_direct_trajectory(_best_grasp_move, duration=0.6, timeout=4.0)
                                if not _nudge_restore:
                                    _nudge_restore = send_direct_set(_best_grasp_move, timeout=4.0)
                                if _nudge_restore:
                                    _last_grasp_move = dict(_best_grasp_move)
                                    _wait_for_joint_targets(
                                        _best_grasp_move,
                                        timeout=2.0,
                                        tolerance=0.12,
                                        stable_samples=2,
                                    )
                                    self._wait_for_target_alignment(timeout=1.0, accept_distance_m=0.20)
                                break
                        if (
                            not _DISABLE_CORRECTIONS
                            and _best_grasp_dist is not None
                            and _best_grasp_dist > 0.10
                            and not _near_moveit_alignment
                        ):
                            final_refine = self._refine_sim_grasp(0.0, fallback_joints=_best_grasp_move)
                            if final_refine:
                                self.get_logger().info(
                                    f"  Trying final seeded refine before close: dist={_best_grasp_dist:.3f}m"
                                )
                                _refine_ok = send_direct_trajectory(final_refine, duration=0.8, timeout=5.0)
                                if not _refine_ok:
                                    _refine_ok = send_direct_set(final_refine, timeout=4.0)
                                if _refine_ok:
                                    _wait_for_joint_targets(
                                        final_refine,
                                        timeout=2.0,
                                        tolerance=0.12,
                                        stable_samples=2,
                                    )
                                    final_refine_dist = self._wait_for_target_alignment(timeout=1.0, accept_distance_m=0.20)
                                    if final_refine_dist is not None and final_refine_dist < _best_grasp_dist:
                                        self.get_logger().info(
                                            f"  Final refine improved alignment: {_best_grasp_dist:.3f}m -> {final_refine_dist:.3f}m"
                                        )
                                        _best_grasp_dist = final_refine_dist
                                        _best_grasp_move = dict(final_refine)
                                        _last_grasp_move = dict(final_refine)
                        if (
                            not PREFER_SIM_NATIVE_IK
                            and (not _DISABLE_CORRECTIONS or _ENABLE_CLOSED_LOOP)
                            and _best_grasp_dist is not None
                            and _MAX_PRE_CLOSE_ALIGNMENT_DIST < _best_grasp_dist <= _MOVEIT_NEAR_ALIGNMENT_DIST
                        ):
                            _residual_moveit = self._compute_closed_loop_moveit_grasp(
                                _best_grasp_move,
                                grasp_offset_z=0.015,
                                error_bias_gain_xy=0.35,
                                error_bias_gain_z=0.25,
                                target_z_bias=-0.01,
                            )
                            if _residual_moveit:
                                self.get_logger().info(
                                    f"  Trying residual MoveIt correction before close: dist={_best_grasp_dist:.3f}m"
                                )
                                _residual_ok = send_direct_trajectory(_residual_moveit, duration=0.7, timeout=6.0)
                                if not _residual_ok:
                                    _residual_ok = send_direct_set(_residual_moveit, timeout=4.0)
                                if _residual_ok:
                                    _wait_for_joint_targets(
                                        _residual_moveit,
                                        timeout=2.0,
                                        tolerance=0.10,
                                        stable_samples=2,
                                    )
                                    _residual_dist = self._wait_for_target_alignment(timeout=0.6, accept_distance_m=0.20)
                                    if _residual_dist is not None and _residual_dist < _best_grasp_dist:
                                        self.get_logger().info(
                                            f"  Residual MoveIt correction improved alignment: "
                                            f"{_best_grasp_dist:.3f}m -> {_residual_dist:.3f}m"
                                        )
                                        _best_grasp_dist = _residual_dist
                                        _best_grasp_move = dict(_residual_moveit)
                                        _last_grasp_move = dict(_residual_moveit)
                    _allow_blocking_only = True
                    if value == GRIPPER_CLOSED and _last_grasp_move is not None:
                        _fast_close_ready = (
                            _best_grasp_dist is not None and _best_grasp_dist <= _FAST_CLOSE_ALIGNMENT_DIST
                        )
                        _preclose_settle_timeout = 0.15 if _fast_close_ready else (
                            0.4 if (_best_grasp_dist is not None and _best_grasp_dist <= 0.18) else 1.5
                        )
                        settle_dist = self._wait_for_target_alignment(timeout=_preclose_settle_timeout, accept_distance_m=0.20)
                        if settle_dist is not None:
                            self.get_logger().info(f"  Pre-close settle: dist={settle_dist:.3f}m")
                            _gate_dist = min(settle_dist, _best_grasp_dist) if _best_grasp_dist is not None else settle_dist
                            if _gate_dist > _MAX_PRE_CLOSE_ALIGNMENT_DIST:
                                if _DISABLE_CORRECTIONS:
                                    self.get_logger().warn(
                                        f"  Pre-close alignment far ({_gate_dist:.3f}m > {_MAX_PRE_CLOSE_ALIGNMENT_DIST:.3f}m) "
                                        f"but corrections disabled — allowing grasp attempt for diagnostics"
                                    )
                                else:
                                    _allow_blocking_only = False
                                    self.get_logger().warn(
                                        f"  Pre-close alignment still too far for blocking-only grasp: "
                                        f"{_gate_dist:.3f}m > {_MAX_PRE_CLOSE_ALIGNMENT_DIST:.3f}m"
                                    )
                        if _last_grasp_move:
                            if _fast_close_ready:
                                self.get_logger().info(
                                    f"  Fast-close path: preserving best alignment at {_best_grasp_dist:.3f}m"
                                )
                            else:
                                _wait_for_joint_targets(
                                    _last_grasp_move,
                                    timeout=2.0,
                                    tolerance=0.08,
                                    stable_samples=3,
                                )
                                _time.sleep(0.25)
                    _hold = _last_grasp_move if value == GRIPPER_CLOSED else None
                    ok = self._send_gripper_sync(value, hold_arm_joints=_hold)
                    if not ok:
                        self.get_logger().warn(f"  Gripper step {i+1} failed, continuing")

                    if value == GRIPPER_CLOSED and _last_grasp_move is not None:
                        _grasp_ok = self._verify_grasp(allow_blocking_only=_allow_blocking_only)
                        if _grasp_ok:
                            _grasp_result = read_grasp_result() or {}
                            _candidate_holding_object = _grasp_result.get("object_in_gripper") or "unknown"
                            if (
                                _candidate_holding_object == "unknown"
                                and not self._verify_blocking_hold_with_micro_lift(_last_grasp_move)
                            ):
                                self.get_logger().warn("  Blocking grasp failed micro-lift verification")
                                _grasp_ok = False
                                _holding_object = None
                            else:
                                _holding_object = self._resolve_verified_holding_object(_grasp_result)
                        if not _grasp_ok and (not _DISABLE_CORRECTIONS or _ENABLE_RETRIES):
                            _holding_object = None
                            retried = False
                            _offsets = [
                                {"torso_lift_joint": -0.02},
                                {"torso_lift_joint": -0.04, "arm_2_joint": 0.05},
                                {"torso_lift_joint": -0.02, "arm_1_joint": -0.05},
                            ]
                            for attempt in range(1, self._MAX_GRASP_RETRIES + 1):
                                off = _offsets[min(attempt - 1, len(_offsets) - 1)]
                                self.get_logger().info(
                                    f"  Retry {attempt}/{self._MAX_GRASP_RETRIES}: offsets={off}")
                                self._send_gripper_sync(GRIPPER_OPEN)
                                _time.sleep(0.5)
                                retry_joints = self._get_target_retry_joints(_last_grasp_move)
                                for jn, joff in off.items():
                                    if jn in retry_joints:
                                        retry_joints[jn] += joff
                                retry_joints = clamp_joints(retry_joints)
                                self._send_goal_sync(retry_joints, group_override=_last_grasp_group)
                                _time.sleep(0.3)
                                _retry_settle_dist = self._wait_for_target_alignment(timeout=1.0, accept_distance_m=0.20)
                                _retry_allow_blocking = (
                                    _retry_settle_dist is None or _retry_settle_dist <= _MAX_PRE_CLOSE_ALIGNMENT_DIST
                                )
                                if _retry_settle_dist is not None:
                                    self.get_logger().info(f"  Retry pre-close settle: dist={_retry_settle_dist:.3f}m")
                                self._send_gripper_sync(GRIPPER_CLOSED)
                                if self._verify_grasp(allow_blocking_only=_retry_allow_blocking):
                                    _grasp_result = read_grasp_result() or {}
                                    _candidate_holding_object = _grasp_result.get("object_in_gripper") or "unknown"
                                    if _candidate_holding_object == "unknown" and not self._verify_blocking_hold_with_micro_lift(retry_joints):
                                        self.get_logger().warn("  Retry blocking grasp failed micro-lift verification")
                                        _holding_object = None
                                        continue
                                    _holding_object = self._resolve_verified_holding_object(_grasp_result)
                                    self.get_logger().info(f"  Retry {attempt} succeeded!")
                                    retried = True
                                    break
                            if not retried:
                                self.get_logger().warn("  All grasp retries failed, continuing sequence")
                        else:
                            self.get_logger().info(f"  Holding latch enabled for '{_holding_object}'")
                    elif value == GRIPPER_OPEN:
                        if _holding_object is not None:
                            self.get_logger().info(f"  Released holding latch for '{_holding_object}'")
                        _holding_object = None
                elif action_type == "nav":
                    self._send_nav_sync(value)
                elif action_type == "correct_grasp":
                    _cg_offset_z = 0.035
                    _cg_max_corr = 6
                    if isinstance(value, dict):
                        _cg_offset_z = float(value.get("grasp_offset_z", _cg_offset_z))
                        _cg_max_corr = int(value.get("max_corrections", _cg_max_corr))
                    for _corr_iter in range(_cg_max_corr):
                        _time.sleep(0.5)
                        _cg_info = query_object_pose_info(timeout=2.0,
                            preferred_class=self._expected_grasp_object,
                            preferred_path=self._expected_grasp_object_path)
                        _cg_obj = _get_grasp_target_local(_cg_info)
                        if not _cg_info or not _cg_obj or not _cg_info.get("gripper_center_local"):
                            self.get_logger().warn(f"  correct_grasp iter {_corr_iter}: no pose info")
                            break
                        _cg_grip = _cg_info["gripper_center_local"]
                        _cg_dx = _cg_obj[0] - _cg_grip[0]
                        _cg_dy = _cg_obj[1] - _cg_grip[1]
                        _cg_dz = (_cg_obj[2] + _cg_offset_z) - _cg_grip[2]
                        _cg_dist = (_cg_dx**2 + _cg_dy**2 + _cg_dz**2)**0.5
                        self.get_logger().info(
                            f"  correct_grasp iter {_corr_iter}: grip=({_cg_grip[0]:.3f},{_cg_grip[1]:.3f},{_cg_grip[2]:.3f}) "
                            f"obj=({_cg_obj[0]:.3f},{_cg_obj[1]:.3f},{_cg_obj[2]:.3f}) dist={_cg_dist:.3f}m")
                        if _cg_dist < 0.05:
                            self.get_logger().info(f"  correct_grasp: converged at dist={_cg_dist:.3f}m")
                            break
                        _cg_gain = min(1.0, 0.85 + _corr_iter * 0.05)
                        _cg_target = (
                            _cg_grip[0] + _cg_dx * _cg_gain,
                            _cg_grip[1] + _cg_dy * _cg_gain,
                            _cg_grip[2] + _cg_dz * _cg_gain,
                        )
                        _cg_ik = None
                        for _orient_name, _orient_q in [
                            ("angled-45", self._ANGLED_QUAT),
                            ("top-down", self._TOP_DOWN_QUAT),
                            ("angled-30", self._ANGLED_30_QUAT),
                        ]:
                            _cg_ik = self._compute_ik(
                                _cg_target,
                                target_orientation=_orient_q,
                                seed_joints=_last_grasp_move,
                            )
                            if _cg_ik:
                                break
                        if not _cg_ik:
                            self.get_logger().warn(f"  correct_grasp iter {_corr_iter}: IK failed")
                            break
                        _cg_ok = self._send_goal_sync(_cg_ik, group_override=None)
                        if _cg_ok:
                            _last_grasp_move = _cg_ik
                            _last_grasp_group = None
                        else:
                            self.get_logger().warn(f"  correct_grasp iter {_corr_iter}: MoveGroup failed")
                            break
                elif action_type == "refine_grasp":
                    grasp_offset_z = 0.015
                    if isinstance(value, dict):
                        grasp_offset_z = float(value.get("grasp_offset_z", grasp_offset_z))
                    _prev_joints = dict(_last_grasp_move) if _last_grasp_move else None
                    _prev_dist = self._wait_for_target_alignment(timeout=0.4, accept_distance_m=999.0)
                    refined = self._refine_sim_grasp(
                        grasp_offset_z,
                        fallback_joints=_last_grasp_move,
                    )
                    if refined:
                        self.get_logger().info(f"  Step {i+1}: applying closed-loop grasp refinement")
                        moved = send_direct_trajectory(refined, duration=2.0, timeout=8.0)
                        if not moved:
                            self.get_logger().warn(
                                f"  Step {i+1}: refine trajectory failed, falling back to direct_set"
                            )
                            moved = send_direct_set(refined, timeout=6.0)
                        if moved:
                            _last_grasp_move = refined
                            _last_grasp_group = None
                            if _holding_object is None:
                                settled = _wait_for_joint_targets(
                                    refined,
                                    timeout=3.0,
                                    tolerance=0.12,
                                    stable_samples=2,
                                )
                                if settled:
                                    self.get_logger().info(f"  Step {i+1}: refine settled")
                                else:
                                    self.get_logger().warn(f"  Step {i+1}: refine dispatched, settling incomplete")
                                new_dist = self._wait_for_target_alignment(timeout=3.0, accept_distance_m=0.20)
                                if new_dist is not None and (_best_grasp_dist is None or new_dist < _best_grasp_dist):
                                    _best_grasp_dist = new_dist
                                    _best_grasp_move = dict(refined)
                                _worsened_vs_prev = (
                                    new_dist is not None
                                    and _prev_dist is not None
                                    and new_dist > (_prev_dist + 0.03)
                                )
                                if (
                                    new_dist is not None
                                    and _worsened_vs_prev
                                    and _prev_joints
                                ):
                                    self.get_logger().warn(
                                        f"  Step {i+1}: refine worsened alignment "
                                        f"prev={_prev_dist if _prev_dist is not None else float('nan'):.3f}m "
                                        f"new={new_dist:.3f}m, rolling back"
                                    )
                                    send_direct_set(_prev_joints, timeout=4.0)
                                    _wait_for_joint_targets(
                                        _prev_joints,
                                        timeout=2.0,
                                        tolerance=0.12,
                                        stable_samples=2,
                                    )
                                    _rolled_back_dist = self._wait_for_target_alignment(timeout=1.0, accept_distance_m=0.20)
                                    if _rolled_back_dist is not None and (
                                        _best_grasp_dist is None or _rolled_back_dist < _best_grasp_dist
                                    ):
                                        _best_grasp_dist = _rolled_back_dist
                                        _best_grasp_move = dict(_prev_joints)
                                    _last_grasp_move = _prev_joints
                        else:
                            self.get_logger().warn("  Closed-loop grasp refinement move failed, continuing")
                elif action_type == "wait":
                    self.get_logger().info(f"  Waiting {value}s...")
                    _time.sleep(float(value))
                _time.sleep(0.5)
            self.get_logger().info(f"Sequence '{intent_name}' complete")
        finally:
            self._expected_grasp_object = None
            self._executing = False

    def _wait_future(self, future, timeout_sec: float, label: str = "future") -> bool:
        """Poll a future until done or timeout. Works from any thread."""
        deadline = _time.time() + timeout_sec
        while not future.done():
            _time.sleep(0.05)
            if _time.time() > deadline:
                self.get_logger().error(f"{label} timed out ({timeout_sec}s)")
                future.cancel()
                return False
        return True

    def _send_goal_sync(self, joint_goal: dict, group_override: str = None) -> bool:
        if not self._action_client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error("MoveGroup action server not available")
            return False
        group = group_override or self.planning_group
        joint_goal = clamp_joints(joint_goal)
        goal_msg = MoveGroup.Goal()
        goal_msg.request = build_motion_plan_request(
            group, joint_goal, frame_id=self.frame_id, plan_only=self.plan_only
        )
        goal_msg.planning_options = build_planning_options(plan_only=self.plan_only)
        self.get_logger().info(f"Sending MoveGroup goal for {list(joint_goal.keys())[:3]}...")
        send_future = self._action_client.send_goal_async(goal_msg)
        if not self._wait_future(send_future, 15.0, "send_goal"):
            return False
        goal_handle = send_future.result()
        if not goal_handle.accepted:
            self.get_logger().error("Goal rejected")
            return False
        result_future = goal_handle.get_result_async()
        if not self._wait_future(result_future, 60.0, "MoveGroup execution"):
            return False
        result = result_future.result().result
        code = result.error_code.val
        if code == 1:
            self.get_logger().info("MoveGroup goal succeeded")
            return True
        self.get_logger().warn(f"MoveGroup goal finished with code {code}")
        return False

    def _send_gripper_sync(self, position: float, hold_arm_joints: dict | None = None) -> bool:
        direct_targets = {joint_name: float(position) for joint_name in GRIPPER_JOINTS}
        _duration = 1.5 if position <= GRIPPER_CLOSED else 1.0
        ok = send_direct_trajectory(direct_targets, duration=_duration, timeout=25.0)
        if not ok:
            self.get_logger().warn("Gripper PD trajectory failed (no teleport fallback)")
        if ok:
            gripper_only = {joint_name: float(position) for joint_name in GRIPPER_JOINTS}
            settled = _wait_for_joint_targets(
                gripper_only,
                timeout=4.0,
                tolerance=0.01,
                stable_samples=2,
            )
            if hold_arm_joints:
                _hold_refresh = send_direct_trajectory(clamp_joints(hold_arm_joints), duration=0.35, timeout=3.0)
                if not _hold_refresh:
                    self.get_logger().warn("Arm hold refresh after gripper action failed")
            if not settled:
                self.get_logger().warn("Gripper dispatched but did not fully settle")
            return True
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
        default="arm_torso",
        help="Planning group name (arm_torso for Tiago, panda_arm for Panda)",
    )
    parser.add_argument(
        "--robot",
        choices=["panda", "tiago"],
        default="tiago",
        help="Robot type (tiago or panda)",
    )
    parser.add_argument(
        "--frame-id",
        default=None,
        help="Planning frame (default: base_footprint for Tiago, panda_link0 for Panda)",
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
    from rclpy.executors import MultiThreadedExecutor
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
