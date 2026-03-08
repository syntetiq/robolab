#!/usr/bin/env python3
"""One-shot publish std_msgs/String to a topic. Usage: python ros2_pub_string.py <topic> <data>"""
import sys
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
    import time
    time.sleep(2.5)
    for _ in range(5):
        pub.publish(msg)
        time.sleep(0.15)
    time.sleep(0.3)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
