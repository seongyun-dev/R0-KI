"""Composable ROS 2 bridge between the Robot mission process and AI service."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Callable

from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from .contracts import AiStatus, ContractError, DetectionEvent, control_message
from .gate import AiGate, GateDecision


DetectionSink = Callable[[DetectionEvent], None]
GateListener = Callable[[GateDecision], None]


class AiRosBridge(Node):
    """ROS node that can be composed into the future mission/drive runtime."""

    def __init__(
        self,
        detection_sink: DetectionSink,
        gate_listener: GateListener | None = None,
        *,
        status_timeout_seconds: float | None = None,
    ) -> None:
        super().__init__("aiot_robot")
        timeout = status_timeout_seconds or float(
            os.getenv("AIOT_AI_STATUS_TIMEOUT_SEC", "5")
        )
        self.gate = AiGate(timeout)
        self._detection_sink = detection_sink
        self._gate_listener = gate_listener
        self._last_decision: GateDecision | None = None
        self._status_condition = threading.Condition()
        self._last_status: AiStatus | None = None
        self._status_revision = 0
        self._active_patrol_id: int | None = None

        control_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        status_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        detection_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=100,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )

        self._control_publisher = self.create_publisher(
            String, os.getenv("AIOT_AI_CONTROL_TOPIC", "/ai/control"), control_qos
        )
        self.create_subscription(
            String,
            os.getenv("AIOT_AI_STATUS_TOPIC", "/ai/status"),
            self._on_status,
            status_qos,
        )
        self.create_subscription(
            String,
            os.getenv("AIOT_AI_DETECTIONS_TOPIC", "/ai/detections"),
            self._on_detection,
            detection_qos,
        )
        self.create_timer(1.0, self._refresh_gate)

    def set_detection_enabled(
        self, enabled: bool, patrol_id: int | None, reason: str
    ) -> int:
        if enabled:
            if patrol_id is None:
                raise ValueError("patrol_id is required when enabling AI detection")
            decision = self.gate.decision()
            if not decision.allowed:
                raise RuntimeError(f"AI gate rejected ENABLE: {decision.reason}")
        message = String()
        message.data = control_message(
            enabled=enabled,
            patrol_id=patrol_id,
            requested_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            reason=reason,
        )
        with self._status_condition:
            previous_patrol_id = self._active_patrol_id
            status_revision = self._status_revision
            self._active_patrol_id = patrol_id if enabled else None
            try:
                # Serialize the revision snapshot and publish against status
                # callbacks. A status observed after ``status_revision`` must
                # therefore have been received after this control publish.
                self._control_publisher.publish(message)
            except Exception:
                self._active_patrol_id = previous_patrol_id
                raise
        return status_revision

    def safe_disable(self, reason: str) -> int:
        with self._status_condition:
            patrol_id = self._active_patrol_id
        return self.set_detection_enabled(False, patrol_id, reason)

    def detection_applied(self, patrol_id: int) -> bool:
        with self._status_condition:
            status = self._last_status
            return (
                self._active_patrol_id == patrol_id
                and status is not None
                and status.detection_applied_for(patrol_id)
            )

    def wait_for_detection_state(
        self,
        enabled: bool,
        patrol_id: int | None,
        *,
        after_revision: int,
        timeout_seconds: float,
    ) -> bool:
        """Wait for an AI status newer than the corresponding control."""

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        deadline = time.monotonic() + timeout_seconds
        with self._status_condition:
            while True:
                status = self._last_status
                is_new = self._status_revision > after_revision
                if enabled:
                    applied = (
                        is_new
                        and self._active_patrol_id == patrol_id
                        and status is not None
                        and status.detection_applied_for(patrol_id)
                    )
                else:
                    applied = (
                        is_new
                        and self._active_patrol_id is None
                        and status is not None
                        and status.detection_enabled is False
                        and status.patrol_id is None
                    )
                if applied:
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._status_condition.wait(remaining)

    def _on_status(self, message: String) -> None:
        try:
            status = AiStatus.from_json(message.data)
        except ContractError as exc:
            self.get_logger().warning(f"Rejected /ai/status message: {exc}")
            return
        self.gate.record(status)
        with self._status_condition:
            self._last_status = status
            self._status_revision += 1
            self._status_condition.notify_all()
        self._refresh_gate()

    def _on_detection(self, message: String) -> None:
        try:
            event = DetectionEvent.from_json(message.data)
        except ContractError as exc:
            self.get_logger().warning(f"Rejected /ai/detections message: {exc}")
            return

        with self._status_condition:
            active_patrol_id = self._active_patrol_id
        if active_patrol_id is None:
            self.get_logger().warning("Rejected detection while AI detection is disabled")
            return
        if event.patrol_id != active_patrol_id:
            self.get_logger().warning(
                "Rejected detection for non-active patrol "
                f"{event.patrol_id}; active={active_patrol_id}"
            )
            return
        try:
            self._detection_sink(event)
        except Exception as exc:
            self.get_logger().error(f"Could not persist detection {event.event_id}: {exc}")

    def _refresh_gate(self) -> None:
        decision = self.gate.decision()
        changed = (
            self._last_decision is None
            or decision.allowed != self._last_decision.allowed
            or decision.reason != self._last_decision.reason
        )
        if not changed:
            return
        self._last_decision = decision
        self.get_logger().info(
            f"AI gate mode={decision.mode} allowed={decision.allowed} "
            f"reason={decision.reason}"
        )
        with self._status_condition:
            has_active_patrol = self._active_patrol_id is not None
        if not decision.allowed and has_active_patrol:
            self.safe_disable(decision.reason)
        if self._gate_listener is not None:
            self._gate_listener(decision)
