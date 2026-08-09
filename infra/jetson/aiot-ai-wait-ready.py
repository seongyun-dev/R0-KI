#!/usr/bin/env python3
"""Wait for the AI READY heartbeat and atomically publish operations readiness."""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


def validate_ready_message(raw: str) -> dict[str, object]:
    message = json.loads(raw)
    if not isinstance(message, dict):
        raise ValueError("AI status must be a JSON object")
    if message.get("schemaVersion") != 1:
        raise ValueError("unsupported AI status schemaVersion")
    if message.get("state") != "READY":
        raise ValueError("AI state is not READY")
    for field in ("ready", "cameraReady", "engineReady", "inferenceReady"):
        if message.get(field) is not True:
            raise ValueError(f"{field} is not true")
    heartbeat = message.get("heartbeatAt")
    if not isinstance(heartbeat, str):
        raise ValueError("heartbeatAt is missing")
    parsed = datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("heartbeatAt must include a timezone")
    max_age = float(os.getenv("AIOT_AI_STATUS_MAX_AGE_SEC", "5"))
    age = (datetime.now(parsed.tzinfo) - parsed).total_seconds()
    if age < -max_age or age > max_age:
        raise ValueError("heartbeatAt is stale or too far in the future")
    return message


def atomic_write(path: Path, message: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(message)
    payload["observedReadyAt"] = datetime.now().astimezone().isoformat()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


class ReadyProbe(Node):
    def __init__(self) -> None:
        super().__init__("aiot_ai_ready_probe")
        self.ready_message: dict[str, object] | None = None
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.create_subscription(
            String,
            os.getenv("AIOT_AI_STATUS_TOPIC", "/ai/status"),
            self._on_status,
            qos,
        )

    def _on_status(self, status: String) -> None:
        try:
            self.ready_message = validate_ready_message(status.data)
        except (json.JSONDecodeError, ValueError) as exc:
            self.get_logger().info(f"AI not ready yet: {exc}")


def main() -> int:
    timeout = float(os.getenv("AIOT_AI_READY_TIMEOUT_SEC", "90"))
    if timeout <= 0:
        raise ValueError("AIOT_AI_READY_TIMEOUT_SEC must be positive")
    ready_path = Path(os.getenv("AIOT_AI_READY_FILE", "/run/aiot/ai-ready.json"))

    rclpy.init()
    node = ReadyProbe()
    deadline = time.monotonic() + timeout
    try:
        while node.ready_message is None and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.25)
        if node.ready_message is None:
            raise TimeoutError(f"AI READY heartbeat was not received within {timeout}s")
        atomic_write(ready_path, node.ready_message)
        node.get_logger().info(f"AI operations readiness written to {ready_path}")
        return 0
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TimeoutError, ValueError) as exc:
        print(f"AI readiness probe failed: {exc}", flush=True)
        raise SystemExit(1)
