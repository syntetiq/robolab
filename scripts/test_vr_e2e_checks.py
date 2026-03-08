#!/usr/bin/env python3
"""
VR E2E sub-checks called from test_vr_e2e.ps1.

Usage:
  python test_vr_e2e_checks.py <check_name> [args...]

Checks:
  rclpy_import         - verify rclpy is importable
  msgs_import          - verify geometry_msgs available
  servo_config <path>  - validate servo YAML params
  topic_align <servo_yaml> <vr_script> - check topic names match
  joint_states         - subscribe /joint_states for 5s
  vr_status            - subscribe /vr_teleop/status for 5s
  twist_publish        - publish test twist commands
  intent_roundtrip     - publish+subscribe intent topic
"""

import re
import sys
import time


def check_rclpy_import():
    try:
        import rclpy  # noqa: F401
        print("result=PASS")
    except ImportError as e:
        print(f"result=FAIL detail={e}")


def check_msgs_import():
    try:
        from geometry_msgs.msg import TwistStamped, PoseStamped  # noqa: F401
        from std_msgs.msg import String  # noqa: F401
        from sensor_msgs.msg import JointState  # noqa: F401
        print("result=PASS")
    except ImportError as e:
        print(f"result=FAIL detail={e}")


def check_servo_config(yaml_path):
    try:
        import yaml
    except ImportError:
        print("result=FAIL detail=pyyaml not installed")
        return

    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)

    p = cfg["servo_node"]["ros__parameters"]
    checks = {
        "move_group": p.get("move_group_name") == "arm_torso",
        "planning_frame": p.get("planning_frame") == "base_footprint",
        "ee_frame": p.get("ee_frame_name") == "arm_tool_link",
        "twist_topic": "/servo_node/" in p.get("cartesian_command_in_topic", ""),
        "pose_topic": "/servo_node/" in p.get("pose_tracking_input_topic", ""),
        "joint_topic": p.get("joint_topic") == "/joint_states",
    }
    for name, ok in checks.items():
        print(f"  {name}: {'OK' if ok else 'FAIL'}")
    all_ok = all(checks.values())
    print(f"result={'PASS' if all_ok else 'FAIL'}")


def check_topic_align(servo_yaml, vr_script):
    try:
        import yaml
    except ImportError:
        print("result=FAIL detail=pyyaml not installed")
        return

    with open(servo_yaml) as f:
        cfg = yaml.safe_load(f)
    sp = cfg["servo_node"]["ros__parameters"]

    with open(vr_script) as f:
        vr_src = f.read()

    servo_twist = sp["cartesian_command_in_topic"]
    servo_pose = sp["pose_tracking_input_topic"]

    vr_twist_m = re.search(r'default="(/servo_node/[^"]+)"', vr_src)
    vr_pose_m = re.search(r'default="(/servo_node/pose[^"]+)"', vr_src)
    vr_twist = vr_twist_m.group(1) if vr_twist_m else "NOT_FOUND"
    vr_pose = vr_pose_m.group(1) if vr_pose_m else "NOT_FOUND"

    print(f"  Servo twist: {servo_twist}")
    print(f"  VR    twist: {vr_twist}")
    print(f"  Servo pose:  {servo_pose}")
    print(f"  VR    pose:  {vr_pose}")

    ok = servo_twist == vr_twist and servo_pose == vr_pose
    print(f"result={'PASS' if ok else 'FAIL'}")


def check_joint_states():
    import rclpy
    from sensor_msgs.msg import JointState

    rclpy.init()
    node = rclpy.create_node("e2e_js_checker")
    received = [False]
    joint_count = [0]

    def cb(msg):
        received[0] = True
        joint_count[0] = len(msg.name)

    node.create_subscription(JointState, "/joint_states", cb, 10)
    end = time.time() + 5
    while time.time() < end and not received[0]:
        rclpy.spin_once(node, timeout_sec=0.5)
    node.destroy_node()
    rclpy.shutdown()

    if received[0]:
        print(f"  Received /joint_states with {joint_count[0]} joints")
        print("result=PASS")
    else:
        print("  No /joint_states received within 5s")
        print("result=FAIL")


def check_vr_status():
    import rclpy
    from std_msgs.msg import String

    rclpy.init()
    node = rclpy.create_node("e2e_vr_status_checker")
    status = [None]

    def cb(msg):
        status[0] = msg.data

    node.create_subscription(String, "/vr_teleop/status", cb, 10)
    end = time.time() + 5
    while time.time() < end and status[0] is None:
        rclpy.spin_once(node, timeout_sec=0.5)
    node.destroy_node()
    rclpy.shutdown()

    if status[0] is not None:
        print(f"  VR status: {status[0]}")
        print("result=PASS")
    else:
        print("  No /vr_teleop/status received within 5s")
        print("result=FAIL")


def check_twist_publish():
    import rclpy
    from geometry_msgs.msg import TwistStamped

    rclpy.init()
    node = rclpy.create_node("e2e_twist_pub")
    pub = node.create_publisher(TwistStamped, "/servo_node/delta_twist_stamped", 10)
    for _ in range(5):
        msg = TwistStamped()
        msg.header.stamp = node.get_clock().now().to_msg()
        msg.header.frame_id = "base_footprint"
        msg.twist.linear.x = 0.01
        pub.publish(msg)
        rclpy.spin_once(node, timeout_sec=0.1)
        time.sleep(0.1)
    node.destroy_node()
    rclpy.shutdown()
    print("  Published 5 twist commands to /servo_node/delta_twist_stamped")
    print("result=PASS")


def check_intent_roundtrip():
    import rclpy
    from std_msgs.msg import String

    rclpy.init()
    node = rclpy.create_node("e2e_intent_test")
    pub = node.create_publisher(String, "/tiago/moveit/intent", 10)
    received = [False]

    def cb(msg):
        received[0] = True

    node.create_subscription(String, "/tiago/moveit/intent", cb, 10)
    time.sleep(0.5)
    msg = String()
    msg.data = "gripper_open"
    pub.publish(msg)
    end = time.time() + 3
    while time.time() < end and not received[0]:
        rclpy.spin_once(node, timeout_sec=0.5)
    node.destroy_node()
    rclpy.shutdown()

    if received[0]:
        print("  Intent round-trip OK")
        print("result=PASS")
    else:
        print("  Intent message not received back")
        print("result=FAIL")


CHECKS = {
    "rclpy_import": lambda args: check_rclpy_import(),
    "msgs_import": lambda args: check_msgs_import(),
    "servo_config": lambda args: check_servo_config(args[0]),
    "topic_align": lambda args: check_topic_align(args[0], args[1]),
    "joint_states": lambda args: check_joint_states(),
    "vr_status": lambda args: check_vr_status(),
    "twist_publish": lambda args: check_twist_publish(),
    "intent_roundtrip": lambda args: check_intent_roundtrip(),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CHECKS:
        print(f"Usage: {sys.argv[0]} <check_name> [args...]")
        print(f"Available: {', '.join(CHECKS)}")
        sys.exit(1)
    check_name = sys.argv[1]
    check_args = sys.argv[2:]
    CHECKS[check_name](check_args)


if __name__ == "__main__":
    main()
