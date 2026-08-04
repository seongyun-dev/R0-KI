"""Lifecycle wrapper composing :class:`AiRosBridge` into Robot runtime."""

from __future__ import annotations

import os
import threading
from typing import Any, Callable


class RosAiCoordinator:
    def __init__(
        self,
        detection_sink: Any,
        state_store: Any,
        *,
        bridge_factory: Callable[..., Any] | None = None,
        control_apply_timeout_seconds: float | None = None,
    ) -> None:
        self._detection_sink = detection_sink
        self._state_store = state_store
        self._bridge_factory = bridge_factory
        self._control_apply_timeout_seconds = (
            float(
                os.getenv("AIOT_AI_CONTROL_APPLY_TIMEOUT_SEC", "3")
            )
            if control_apply_timeout_seconds is None
            else control_apply_timeout_seconds
        )
        if self._control_apply_timeout_seconds <= 0:
            raise ValueError("AI control apply timeout must be positive")
        self._bridge: Any = None
        self._executor: Any = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._rclpy: Any = None
        self._owns_rclpy_context = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        rclpy, executor_type = self._load_ros_runtime()
        self._rclpy = rclpy
        self._owns_rclpy_context = not rclpy.ok()
        if self._owns_rclpy_context:
            rclpy.init(args=None)
        self._bridge = self._create_bridge(
            self._detection_sink,
            gate_listener=self._on_gate,
        )
        # The transient-local publisher makes this startup DISABLE visible to
        # an AI process that was left enabled by a previous Robot crash.
        self._bridge.safe_disable("ROBOT_RUNTIME_STARTED")
        self._executor = executor_type()
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
        revision = self._bridge.set_detection_enabled(
            True,
            patrol_id,
            "PATROL_STARTED",
        )
        applied = self._bridge.wait_for_detection_state(
            True,
            patrol_id,
            after_revision=revision,
            timeout_seconds=self._control_apply_timeout_seconds,
        )
        if applied:
            return
        self._bridge.safe_disable("AI_ENABLE_NOT_APPLIED")
        raise RuntimeError("AI ENABLE was not confirmed by /ai/status")

    def disable(self, reason: str) -> None:
        if self._bridge is not None:
            self._bridge.safe_disable(reason)

    def detection_applied(self, patrol_id: int) -> bool:
        return bool(
            self._bridge is not None
            and self._bridge.detection_applied(patrol_id)
        )

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

    def _create_bridge(self, *args: Any, **kwargs: Any) -> Any:
        if self._bridge_factory is not None:
            return self._bridge_factory(*args, **kwargs)
        try:
            from .ros_bridge import AiRosBridge
        except ImportError as exc:
            raise RuntimeError("AI coordinator requires ROS 2 rclpy") from exc
        return AiRosBridge(*args, **kwargs)

    @staticmethod
    def _load_ros_runtime() -> tuple[Any, Any]:
        try:
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
        except ImportError as exc:
            raise RuntimeError("AI coordinator requires ROS 2 rclpy") from exc
        return rclpy, SingleThreadedExecutor
