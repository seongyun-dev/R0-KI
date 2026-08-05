"""ROS ``/scan`` freshness를 RobotStateStore의 LiDAR 상태로 전달한다."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
import math
import statistics
from typing import Any, Callable

from state.robot_state import ObstacleState


ObstacleActivityCheck = Callable[[], bool]


@dataclass(frozen=True)
class RosLidarHealthSettings:
    scan_topic: str
    scan_timeout_sec: float
    vehicle_center_angle_deg: float = 0.0
    vehicle_half_angle_deg: float = 8.0
    vehicle_max_range_m: float = 8.0
    vehicle_nearest_samples: int = 5
    vehicle_range_timeout_sec: float | None = None

    def __post_init__(self) -> None:
        if not self.scan_topic.strip():
            raise ValueError("lidar.scan_topic must not be empty")
        if self.scan_timeout_sec <= 0:
            raise ValueError("lidar.scan_timeout_sec must be positive")
        if not math.isfinite(self.vehicle_center_angle_deg):
            raise ValueError("vehicle_center_angle_deg must be finite")
        if not 0 < self.vehicle_half_angle_deg <= 90:
            raise ValueError("vehicle_half_angle_deg must be in (0, 90]")
        if self.vehicle_max_range_m <= 0:
            raise ValueError("vehicle_max_range_m must be positive")
        if self.vehicle_nearest_samples < 1:
            raise ValueError("vehicle_nearest_samples must be positive")
        if (
            self.vehicle_range_timeout_sec is not None
            and self.vehicle_range_timeout_sec <= 0
        ):
            raise ValueError("vehicle_range_timeout_sec must be positive")


class RosLidarHealthBridge:
    """LaserScan 수신 생존 여부만 판단하며 scan 내용은 해석하지 않는다."""

    SPIN_TIMEOUT_SEC = 0.1

    def __init__(
        self,
        *,
        state_store: Any,
        settings: RosLidarHealthSettings,
        obstacle_detector: Any | None = None,
        obstacle_activity_check: ObstacleActivityCheck | None = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._state_store = state_store
        self._settings = settings
        self._monotonic_clock = monotonic_clock
        self._obstacle_detector = obstacle_detector
        self._obstacle_activity_check = (
            obstacle_activity_check
            if obstacle_activity_check is not None
            else self._state_reports_active_operation
        )
        self._obstacle_was_active = False
        self._scan_lock = threading.Lock()
        self._last_scan_time: float | None = None
        self._front_range_m: float | None = None
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

    def set_obstacle_activity_check(
        self,
        check: ObstacleActivityCheck,
    ) -> None:
        """운행 lifecycle 소유자가 제공하는 read-only gate를 연결한다.

        Application 조립 단계에서 ROS thread 시작 전에 호출한다.
        """

        if not callable(check):
            raise ValueError("obstacle activity check must be callable")
        self._obstacle_activity_check = check

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

        timestamp = (
            self._monotonic_clock()
            if received_at is None
            else float(received_at)
        )
        with self._scan_lock:
            self._last_scan_time = timestamp
        self._set_status("NORMAL")

    def ingest_scan(
        self,
        *,
        ranges: Any,
        angle_min_rad: float,
        angle_increment_rad: float,
        range_min_m: float,
        range_max_m: float,
        received_at: float | None = None,
    ) -> float | None:
        """Record scan freshness and estimate a robust range in front of BRIO."""

        self.record_scan(received_at)
        center_angle = math.radians(self._settings.vehicle_center_angle_deg)
        half_angle = math.radians(self._settings.vehicle_half_angle_deg)
        upper = self._settings.vehicle_max_range_m
        if math.isfinite(range_max_m) and range_max_m > 0:
            upper = min(upper, float(range_max_m))
        lower = max(0.0, float(range_min_m))
        candidates: list[float] = []
        for index, raw_range in enumerate(ranges):
            angle = float(angle_min_rad) + index * float(angle_increment_rad)
            angle_delta = (angle - center_angle + math.pi) % (2 * math.pi) - math.pi
            if abs(angle_delta) > half_angle:
                continue
            try:
                distance = float(raw_range)
            except (TypeError, ValueError):
                continue
            if math.isfinite(distance) and lower <= distance <= upper:
                candidates.append(distance)
        if candidates:
            nearest = sorted(candidates)[: self._settings.vehicle_nearest_samples]
            front_range = float(statistics.median(nearest))
        else:
            front_range = None
        with self._scan_lock:
            self._front_range_m = front_range
        return front_range

    def get_front_range(self, now: float | None = None) -> float | None:
        """Return only a fresh front range so stale scans cannot place events."""

        current_time = self._monotonic_clock() if now is None else float(now)
        timeout = (
            self._settings.vehicle_range_timeout_sec
            if self._settings.vehicle_range_timeout_sec is not None
            else self._settings.scan_timeout_sec
        )
        with self._scan_lock:
            last_scan = self._last_scan_time
            front_range = self._front_range_m
        if (
            last_scan is None
            or current_time < last_scan
            or current_time - last_scan >= timeout
        ):
            return None
        return front_range

    def evaluate(self, now: float | None = None) -> str:
        """최근 scan이 timeout을 넘겼으면 DISCONNECTED로 전환한다."""

        current_time = self._monotonic_clock() if now is None else float(now)
        with self._scan_lock:
            last_scan = self._last_scan_time
        if (
            last_scan is None
            or current_time - last_scan >= self._settings.scan_timeout_sec
            or current_time < last_scan
        ):
            self._set_status("DISCONNECTED")
        else:
            self._set_status("NORMAL")
        self._synchronize_obstacle_activity()
        return self._current_status

    def _on_scan(self, _message: Any) -> None:
        self.ingest_scan(
            ranges=_message.ranges,
            angle_min_rad=float(_message.angle_min),
            angle_increment_rad=float(_message.angle_increment),
            range_min_m=float(_message.range_min),
            range_max_m=float(_message.range_max),
        )
        if self._obstacle_detector is None:
            return
        if not self._obstacle_detection_active():
            self._clear_inactive_obstacle()
            return
        self._obstacle_was_active = True
        detection = self._obstacle_detector.evaluate_scan(
            ranges=_message.ranges,
            angle_min_rad=float(_message.angle_min),
            angle_increment_rad=float(_message.angle_increment),
            range_min_m=float(_message.range_min),
            range_max_m=float(_message.range_max),
        )
        # 운행 종료와 scan callback이 겹쳐 stale STOP이 되살아나는 것을
        # 줄이기 위해 Store write 직전에 lifecycle을 다시 확인한다.
        if not self._obstacle_detection_active():
            self._clear_inactive_obstacle()
            return
        self._state_store.update_obstacle(detection.obstacle)

    def _state_reports_active_operation(self) -> bool:
        """Standalone runtime의 보수적인 fallback gate."""

        status = self._state_store.get_status()
        return status.state in {"PATROLLING", "MAPPING"}

    def _obstacle_detection_active(self) -> bool:
        return bool(self._obstacle_activity_check())

    def _synchronize_obstacle_activity(self) -> None:
        if (
            self._obstacle_detector is not None
            and not self._obstacle_detection_active()
        ):
            self._clear_inactive_obstacle()

    def _clear_inactive_obstacle(self) -> None:
        clear = ObstacleState()
        if self._obstacle_was_active:
            reset = getattr(self._obstacle_detector, "reset", None)
            if callable(reset):
                reset()
            self._obstacle_was_active = False
        if self._state_store.get_status().obstacle != clear:
            self._state_store.update_obstacle(clear)

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
