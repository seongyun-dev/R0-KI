"""Dependency and ROS node creation smoke check; sends no actuator commands."""

from __future__ import annotations

import json
import platform

import rclpy
from std_msgs.msg import String


def main() -> None:
    rclpy.init()
    node = rclpy.create_node("aiot_robot_smoke")
    try:
        publisher = node.create_publisher(String, "/aiot/smoke", 1)
        node.destroy_publisher(publisher)
        print(
            json.dumps(
                {
                    "ok": True,
                    "python": platform.python_version(),
                    "rclpy": rclpy.__file__,
                    "movementCommandSent": False,
                },
                sort_keys=True,
            )
        )
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
