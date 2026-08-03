"""ROS ``/scan`` freshness를 RobotStateStore의 LiDAR 상태로 전달한다."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RosLidarHealthSettings:
    scan_topic: str
    scan_timeout_sec: float

    def __post_init__(self) -> None:
        if not self.scan_topic.strip():
            raise ValueError("lidar.scan_topic must not be empty")
        if self.scan_timeout_sec <= 0:
            raise ValueError("lidar.scan_timeout_sec must be positive")


class RosLidarHealthBridge:
    """LaserScan 수신 생존 여부만 판단하며 scan 내용은 해석하지 않는다."""

    SPIN_TIMEOUT_SEC = 0.1

    def __init__(
        self,
        *,
        state_store: Any,
        settings: RosLidarHealthSettings,
        obstacle_detector: Any | None = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._state_store = state_store
        self._settings = settings
        self._monotonic_clock = monotonic_clock
        self._obstacle_detector = obstacle_detector
        self._last_scan_time: float | None = None
        self._current_status = "DISCONNECTED"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._node: Any = None
        self._subscription: Any = None
        self._executor: Any = None
        self._rclpy: Any = None
        self._owns_rclpy_context = False

    @property
    def state_store(self) -> Any:
        return self._state_store

    def start(self) -> None:
        if self.is_running():
            return
        try:
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.qos import qos_profile_sensor_data
            from sensor_msgs.msg import LaserScan
        except ImportError as exc:
            raise RuntimeError(
                "ROS LiDAR health requires rclpy and sensor_msgs"
            ) from exc

        self._rclpy = rclpy
        self._owns_rclpy_context = not rclpy.ok()
        if self._owns_rclpy_context:
            rclpy.init(args=None)
        try:
            self._node = rclpy.create_node("roki_lidar_health_bridge")
            self._subscription = self._node.create_subscription(
                LaserScan,
                self._settings.scan_topic,
                self._on_scan,
                qos_profile_sensor_data,
            )
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="ros-lidar-health-bridge",
                daemon=True,
            )
            self._thread.start()
        except Exception:
            self._cleanup_ros()
            raise

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
        self._cleanup_ros()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def record_scan(self, received_at: float | None = None) -> None:
        """Mock과 ROS callback이 공유하는 scan 수신 경계."""

        self._last_scan_time = (
            self._monotonic_clock()
            if received_at is None
            else float(received_at)
        )
        self._set_status("NORMAL")

    def evaluate(self, now: float | None = None) -> str:
        """최근 scan이 timeout을 넘겼으면 DISCONNECTED로 전환한다."""

        current_time = self._monotonic_clock() if now is None else float(now)
        last_scan = self._last_scan_time
        if (
            last_scan is None
            or current_time - last_scan >= self._settings.scan_timeout_sec
            or current_time < last_scan
        ):
            self._set_status("DISCONNECTED")
        else:
            self._set_status("NORMAL")
        return self._current_status

    def _on_scan(self, _message: Any) -> None:
        self.record_scan()
        if self._obstacle_detector is None:
            return
        detection = self._obstacle_detector.evaluate_scan(
            ranges=_message.ranges,
            angle_min_rad=float(_message.angle_min),
            angle_increment_rad=float(_message.angle_increment),
            range_min_m=float(_message.range_min),
            range_max_m=float(_message.range_max),
        )
        self._state_store.update_obstacle(detection.obstacle)

    def _set_status(self, status: str) -> None:
        if status == self._current_status:
            return
        self._current_status = status
        self._state_store.update_lidar_status(status)

    def _run(self) -> None:
        assert self._rclpy is not None
        assert self._node is not None
        while not self._stop_event.is_set() and self._rclpy.ok():
            self._executor.spin_once(
                timeout_sec=self.SPIN_TIMEOUT_SEC,
            )
            self.evaluate()

    def _cleanup_ros(self) -> None:
        self._subscription = None
        executor = self._executor
        self._executor = None
        node = self._node
        self._node = None
        if node is not None:
            if executor is not None:
                executor.remove_node(node)
            node.destroy_node()
        if executor is not None:
            executor.shutdown()
        rclpy = self._rclpy
        self._rclpy = None
        if (
            self._owns_rclpy_context
            and rclpy is not None
            and rclpy.ok()
        ):
            rclpy.shutdown()
        self._owns_rclpy_context = False
