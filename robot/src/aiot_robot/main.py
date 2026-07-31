"""Stationary Robot process entrypoint used until the drive pipeline composes it."""

from __future__ import annotations

import os

import rclpy

from .outbox import DetectionOutbox
from .ros_bridge import AiRosBridge


def main() -> None:
    outbox = DetectionOutbox(
        os.getenv("AIOT_EVENT_OUTBOX_DIR", "/var/lib/aiot/outbox")
    )
    rclpy.init()
    node = AiRosBridge(outbox.enqueue)
    node.safe_disable("ROBOT_RUNTIME_STARTED")
    node.get_logger().info(
        "Robot ROS runtime started in stationary mode; motor commands are disabled"
    )
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.safe_disable("ROBOT_RUNTIME_STOPPING")
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
