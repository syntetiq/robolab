#!/usr/bin/env python3
"""One-shot publish std_msgs/String to a topic. Usage: python ros2_pub_string.py <topic> <data>"""
import sys
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def main():
    if len(sys.argv) < 3:
        print("Usage: ros2_pub_string.py <topic> <data>", file=sys.stderr)
        sys.exit(1)
    topic = sys.argv[1]
    data = sys.argv[2]
    rclpy.init()
    node = Node("robolab_pub_string")
    pub = node.create_publisher(String, topic, 10)
    msg = String()
    msg.data = data
    # Give DDS discovery a brief chance to notice the subscriber, but avoid
    # spamming the same intent multiple times into the bridge.
    for _ in range(20):
        rclpy.spin_once(node, timeout_sec=0.05)
        if pub.get_subscription_count() > 0:
            break
        time.sleep(0.05)
    pub.publish(msg)
    rclpy.spin_once(node, timeout_sec=0.1)
    time.sleep(0.1)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
