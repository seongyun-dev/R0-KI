"""End-to-end local ROS topic smoke test with no hardware commands."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from .outbox import DetectionOutbox
from .ros_bridge import AiRosBridge


def _message(payload: dict[str, object]) -> String:
    message = String()
    message.data = json.dumps(payload, separators=(",", ":"))
    return message


def main() -> None:
    topic_prefix = f"/aiot/robot_smoke/p{os.getpid()}"
    os.environ["AIOT_AI_CONTROL_TOPIC"] = f"{topic_prefix}/control"
    os.environ["AIOT_AI_STATUS_TOPIC"] = f"{topic_prefix}/status"
    os.environ["AIOT_AI_DETECTIONS_TOPIC"] = f"{topic_prefix}/detections"

    qos = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=10,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )

    with tempfile.TemporaryDirectory(prefix="aiot-robot-smoke.") as directory:
        rclpy.init()
        bridge = AiRosBridge(DetectionOutbox(directory).enqueue)
        probe = Node("aiot_robot_smoke_probe")
        status_publisher = probe.create_publisher(
            String, os.environ["AIOT_AI_STATUS_TOPIC"], qos
        )
        detection_publisher = probe.create_publisher(
            String, os.environ["AIOT_AI_DETECTIONS_TOPIC"], qos
        )
        executor = SingleThreadedExecutor()
        executor.add_node(bridge)
        executor.add_node(probe)
        try:
            deadline = time.monotonic() + 3.0
            while (
                status_publisher.get_subscription_count() < 1
                or detection_publisher.get_subscription_count() < 1
            ):
                if time.monotonic() >= deadline:
                    raise RuntimeError("ROS publishers did not discover Robot subscribers")
                executor.spin_once(timeout_sec=0.05)

            status_publisher.publish(
                _message(
                    {
                        "schemaVersion": 1,
                        "state": "READY",
                        "ready": True,
                        "cameraReady": True,
                        "engineReady": True,
                        "inferenceReady": True,
                        "modelVersion": "smoke",
                        "heartbeatAt": "2026-07-31T05:20:02Z",
                        "errorCode": None,
                        "message": None,
                    }
                )
            )
            deadline = time.monotonic() + 3.0
            while not bridge.gate.decision().allowed:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Robot did not consume AI readiness status")
                executor.spin_once(timeout_sec=0.05)

            bridge.set_detection_enabled(True, 1, "SMOKE_STARTED")
            detection_publisher.publish(
                _message(
                    {
                        "schemaVersion": 1,
                        "eventId": "ros-smoke-event",
                        "patrolId": 1,
                        "eventType": "SMOKE_TEST",
                        "cameraId": "virtual",
                        "trackId": "smoke-track",
                        "confidence": 1.0,
                        "observedAt": "2026-07-31T05:20:03Z",
                        "evidencePath": "/var/lib/aiot/evidence/ros-smoke-event.jpg",
                        "bbox": {"x": 0, "y": 0, "width": 1, "height": 1},
                        "attributes": {},
                    }
                )
            )

            event_path = Path(directory) / "ros-smoke-event.json"
            deadline = time.monotonic() + 3.0
            while not event_path.exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("Robot did not consume AI detection topic")
                executor.spin_once(timeout_sec=0.05)

            bridge.safe_disable("SMOKE_COMPLETE")
            print(
                json.dumps(
                    {
                        "ok": True,
                        "aiGate": bridge.gate.decision().mode,
                        "detectionSpooled": event_path.name,
                        "movementCommandSent": False,
                    },
                    sort_keys=True,
                )
            )
        finally:
            executor.remove_node(probe)
            executor.remove_node(bridge)
            probe.destroy_node()
            bridge.destroy_node()
            executor.shutdown()
            rclpy.shutdown()


if __name__ == "__main__":
    main()
