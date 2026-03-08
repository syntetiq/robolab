#!/usr/bin/env python3
"""
VR Teleoperation Node for Tiago robot in Isaac Sim.

Connects Vive Pro 2 (via OpenXR/SteamVR) to control the Tiago robot's
end-effector through MoveIt Servo. The operator sees through the robot's
head camera via WebRTC streaming.

Architecture:
  - OpenXR provides HMD and controller poses
  - Right controller pose → end-effector goal (geometry_msgs/PoseStamped)
  - Right trigger → gripper close/open
  - MoveIt Servo tracks the goal in real-time
  - Isaac Sim streams head camera to VR headset via WebRTC

Usage:
  python vr_teleop_node.py [--servo-topic /servo_node/delta_twist_stamped]
                           [--ee-frame tool_link]

Requires: rclpy, geometry_msgs, std_msgs, control_msgs, pyopenvr
"""

import argparse
import math
import sys
import threading
import time

try:
    import openvr
    HAS_OPENVR = True
except ImportError:
    openvr = None
    HAS_OPENVR = False

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped, TwistStamped
from std_msgs.msg import Float64, Bool, String
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from builtin_interfaces.msg import Duration


def parse_args():
    p = argparse.ArgumentParser(description="VR Teleop Node for Tiago + Isaac Sim")
    p.add_argument(
        "--twist-topic",
        default="/servo_node/delta_twist_stamped",
        help="Topic for MoveIt Servo twist commands.",
    )
    p.add_argument(
        "--pose-topic",
        default="/servo_node/pose_target",
        help="Topic for MoveIt Servo pose targets.",
    )
    p.add_argument(
        "--gripper-topic",
        default="/gripper_controller/command",
        help="Topic for gripper commands.",
    )
    p.add_argument(
        "--intent-topic",
        default="/tiago/moveit/intent",
        help="Topic for intent-based fallback control.",
    )
    p.add_argument(
        "--ee-frame",
        default="arm_tool_link",
        help="End-effector frame for pose targets.",
    )
    p.add_argument(
        "--base-frame",
        default="base_footprint",
        help="Robot base frame.",
    )
    p.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Position scaling factor for VR→robot mapping.",
    )
    p.add_argument(
        "--rate",
        type=float,
        default=30.0,
        help="Control loop rate (Hz).",
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help="Run without actual VR hardware (for testing).",
    )
    return p.parse_args()


class VRTeleopNode(Node):
    """Maps VR controller input to robot end-effector commands."""

    def __init__(self, args):
        super().__init__("vr_teleop_node")
        self.args = args
        self.scale = args.scale

        self._twist_pub = self.create_publisher(TwistStamped, args.twist_topic, 10)
        self._pose_pub = self.create_publisher(PoseStamped, args.pose_topic, 10)
        self._intent_pub = self.create_publisher(String, args.intent_topic, 10)
        self._status_pub = self.create_publisher(String, "/vr_teleop/status", 10)

        self._vr_system = None
        self._controller_idx = None
        self._hmd_idx = 0
        self._gripper_closed = False
        self._clutch_engaged = False
        self._last_controller_pose = None
        self._base_controller_pose = None
        self._base_ee_pose = None

        if not args.mock:
            self._init_openvr()
        else:
            self.get_logger().info("Running in mock mode (no VR hardware)")

        self._timer = self.create_timer(1.0 / args.rate, self._control_loop)
        self.get_logger().info(
            f"VR Teleop ready: twist→{args.twist_topic}, "
            f"pose→{args.pose_topic}, rate={args.rate}Hz"
        )

    def _init_openvr(self):
        if not HAS_OPENVR:
            self.get_logger().error(
                "pyopenvr not installed. Install with: pip install openvr\n"
                "Also ensure SteamVR is running with Vive Pro 2 connected."
            )
            return
        try:
            self._vr_system = openvr.init(openvr.VRApplication_Other)
            self.get_logger().info("OpenVR initialized successfully")
            self._find_controllers()
        except Exception as e:
            self.get_logger().error(f"Failed to initialize OpenVR: {e}")
            self._vr_system = None

    def _find_controllers(self):
        if not self._vr_system:
            return
        for i in range(openvr.k_unMaxTrackedDeviceCount):
            dev_class = self._vr_system.getTrackedDeviceClass(i)
            if dev_class == openvr.TrackedDeviceClass_Controller:
                role = self._vr_system.getControllerRoleForTrackedDeviceIndex(i)
                if role == openvr.TrackedControllerRole_RightHand:
                    self._controller_idx = i
                    self.get_logger().info(f"Right controller found at index {i}")
                    break
        if self._controller_idx is None:
            self.get_logger().warn("No right controller found, will retry...")

    def _get_controller_pose(self):
        """Get right controller pose from OpenVR. Returns (pos, rot) or None."""
        if self._vr_system is None:
            return None

        if self._controller_idx is None:
            self._find_controllers()
            if self._controller_idx is None:
                return None

        poses = self._vr_system.getDeviceToAbsoluteTrackingPose(
            openvr.TrackingUniverseStanding, 0, openvr.k_unMaxTrackedDeviceCount
        )
        pose = poses[self._controller_idx]
        if not pose.bPoseIsValid:
            return None

        m = pose.mDeviceToAbsoluteTracking
        pos = (m[0][3], m[1][3], m[2][3])
        # Extract quaternion from 3x4 matrix
        rot = self._matrix_to_quat(m)
        return pos, rot

    def _get_controller_buttons(self):
        """Get trigger and grip state. Returns (trigger_pressed, grip_pressed)."""
        if self._vr_system is None or self._controller_idx is None:
            return False, False
        try:
            _, state = self._vr_system.getControllerState(self._controller_idx)
            trigger = state.rAxis[1].x > 0.8
            grip = bool(state.ulButtonPressed & (1 << openvr.k_EButton_Grip))
            return trigger, grip
        except Exception:
            return False, False

    @staticmethod
    def _matrix_to_quat(m):
        """Convert OpenVR 3x4 matrix to quaternion (w, x, y, z)."""
        trace = m[0][0] + m[1][1] + m[2][2]
        if trace > 0:
            s = 0.5 / math.sqrt(trace + 1.0)
            w = 0.25 / s
            x = (m[2][1] - m[1][2]) * s
            y = (m[0][2] - m[2][0]) * s
            z = (m[1][0] - m[0][1]) * s
        elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
            s = 2.0 * math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2])
            w = (m[2][1] - m[1][2]) / s
            x = 0.25 * s
            y = (m[0][1] + m[1][0]) / s
            z = (m[0][2] + m[2][0]) / s
        elif m[1][1] > m[2][2]:
            s = 2.0 * math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2])
            w = (m[0][2] - m[2][0]) / s
            x = (m[0][1] + m[1][0]) / s
            y = 0.25 * s
            z = (m[1][2] + m[2][1]) / s
        else:
            s = 2.0 * math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1])
            w = (m[1][0] - m[0][1]) / s
            x = (m[0][2] + m[2][0]) / s
            y = (m[1][2] + m[2][1]) / s
            z = 0.25 * s
        return (w, x, y, z)

    def _control_loop(self):
        status = "active" if (self._vr_system or self.args.mock) else "no_vr"
        status_msg = String()
        status_msg.data = status
        self._status_pub.publish(status_msg)

        if self.args.mock:
            return

        pose_data = self._get_controller_pose()
        if pose_data is None:
            return

        pos, rot = pose_data
        trigger, grip = self._get_controller_buttons()

        # Grip button = clutch: when pressed, controller motion maps to robot.
        if grip and not self._clutch_engaged:
            self._clutch_engaged = True
            self._base_controller_pose = pos
            self.get_logger().info("Clutch engaged")
        elif not grip and self._clutch_engaged:
            self._clutch_engaged = False
            self._base_controller_pose = None
            self.get_logger().info("Clutch released")

        # Trigger = gripper toggle.
        if trigger and not self._gripper_closed:
            self._gripper_closed = True
            self._publish_intent("gripper_close")
        elif not trigger and self._gripper_closed:
            self._gripper_closed = False
            self._publish_intent("gripper_open")

        if not self._clutch_engaged:
            self._publish_zero_twist()
            return

        if self._base_controller_pose is None:
            return

        dx = (pos[0] - self._base_controller_pose[0]) * self.scale
        dy = (pos[1] - self._base_controller_pose[1]) * self.scale
        dz = (pos[2] - self._base_controller_pose[2]) * self.scale

        twist = TwistStamped()
        twist.header.stamp = self.get_clock().now().to_msg()
        twist.header.frame_id = self.args.base_frame
        twist.twist.linear.x = self._clamp(dx, -0.5, 0.5)
        twist.twist.linear.y = self._clamp(dy, -0.5, 0.5)
        twist.twist.linear.z = self._clamp(dz, -0.5, 0.5)
        self._twist_pub.publish(twist)

        self._base_controller_pose = pos

    def _publish_zero_twist(self):
        twist = TwistStamped()
        twist.header.stamp = self.get_clock().now().to_msg()
        twist.header.frame_id = self.args.base_frame
        self._twist_pub.publish(twist)

    def _publish_intent(self, intent: str):
        msg = String()
        msg.data = intent
        self._intent_pub.publish(msg)
        self.get_logger().info(f"Published intent: {intent}")

    @staticmethod
    def _clamp(v, lo, hi):
        return max(lo, min(hi, v))

    def destroy_node(self):
        if self._vr_system is not None:
            try:
                openvr.shutdown()
            except Exception:
                pass
        super().destroy_node()


def main():
    args = parse_args()
    rclpy.init()
    node = VRTeleopNode(args)
    print("[VRTeleop] Node spinning — connect Vive Pro 2 via SteamVR")
    print("[VRTeleop] Controls: Grip=clutch (hold to move), Trigger=gripper toggle")
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    print("[VRTeleop] Shutdown complete.")


if __name__ == "__main__":
    main()
