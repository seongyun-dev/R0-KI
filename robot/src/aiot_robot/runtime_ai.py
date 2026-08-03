"""Lifecycle wrapper composing :class:`AiRosBridge` into Robot runtime."""

from __future__ import annotations

import threading
from typing import Any

from .ros_bridge import AiRosBridge


class RosAiCoordinator:
    def __init__(self, detection_sink: Any, state_store: Any) -> None:
        self._detection_sink = detection_sink
        self._state_store = state_store
        self._bridge: AiRosBridge | None = None
        self._executor: Any = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._rclpy: Any = None
        self._owns_rclpy_context = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        try:
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
        except ImportError as exc:
            raise RuntimeError("AI coordinator requires ROS 2 rclpy") from exc
        self._rclpy = rclpy
        self._owns_rclpy_context = not rclpy.ok()
        if self._owns_rclpy_context:
            rclpy.init(args=None)
        self._bridge = AiRosBridge(
            self._detection_sink,
            gate_listener=self._on_gate,
        )
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._bridge)
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._spin,
            name="ros-ai-coordinator",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self.disable("ROBOT_RUNTIME_STOPPING")
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        bridge = self._bridge
        executor = self._executor
        self._bridge = None
        self._executor = None
        if bridge is not None:
            if executor is not None:
                executor.remove_node(bridge)
            bridge.destroy_node()
        if executor is not None:
            executor.shutdown()
        if (
            self._owns_rclpy_context
            and self._rclpy is not None
            and self._rclpy.ok()
        ):
            self._rclpy.shutdown()
        self._rclpy = None
        self._owns_rclpy_context = False

    def readiness(self) -> tuple[bool, str]:
        if self._bridge is None:
            return False, "AI_COORDINATOR_NOT_RUNNING"
        decision = self._bridge.gate.decision()
        self._on_gate(decision)
        return decision.allowed, decision.reason

    def enable(self, patrol_id: int) -> None:
        if self._bridge is None:
            raise RuntimeError("AI coordinator is not running")
        self._bridge.set_detection_enabled(True, patrol_id, "PATROL_STARTED")

    def disable(self, reason: str) -> None:
        if self._bridge is not None:
            self._bridge.safe_disable(reason)

    def _on_gate(self, decision: Any) -> None:
        self._state_store.update_camera_status(
            "NORMAL" if decision.allowed else "ERROR"
        )

    def _spin(self) -> None:
        while (
            not self._stop_event.is_set()
            and self._rclpy is not None
            and self._rclpy.ok()
        ):
            self._executor.spin_once(timeout_sec=0.1)
