"""Internal ROS control and readiness observation for the SLAM scan gate."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from integration.localization_mode import ServiceCallFailed, wait_for_response


@dataclass(frozen=True)
class SlamMarker:
    scan_sequence: int
    map_sequence: int


@dataclass(frozen=True)
class _Observation:
    sequence: int
    stamp_ns: int
    arrival: float


class FreshMapTracker:
    """Identify a map generated after the first post-reset relayed scan."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._scan_sequence = 0
        self._map_sequence = 0
        self._scans: deque[_Observation] = deque(maxlen=256)
        self._maps: deque[_Observation] = deque(maxlen=256)

    def marker(self) -> SlamMarker:
        return SlamMarker(self._scan_sequence, self._map_sequence)

    def note_scan(self, stamp_ns: int, *, arrival: float | None = None) -> None:
        self._scan_sequence += 1
        self._scans.append(
            _Observation(
                self._scan_sequence,
                int(stamp_ns),
                self._clock() if arrival is None else float(arrival),
            )
        )

    def note_map(self, stamp_ns: int, *, arrival: float | None = None) -> None:
        self._map_sequence += 1
        self._maps.append(
            _Observation(
                self._map_sequence,
                int(stamp_ns),
                self._clock() if arrival is None else float(arrival),
            )
        )

    def first_scan_after(self, marker: SlamMarker) -> _Observation | None:
        return next(
            (item for item in self._scans if item.sequence > marker.scan_sequence),
            None,
        )

    def fresh_map_ready(self, marker: SlamMarker) -> bool:
        first_scan = self.first_scan_after(marker)
        if first_scan is None:
            return False
        for item in self._maps:
            if item.sequence <= marker.map_sequence or item.arrival < first_scan.arrival:
                continue
            if first_scan.stamp_ns and item.stamp_ns < first_scan.stamp_ns:
                continue
            return True
        return False

    @property
    def scan_sequence(self) -> int:
        return self._scan_sequence

    @property
    def last_scan_arrival(self) -> float | None:
        return self._scans[-1].arrival if self._scans else None


class RosSlamSessionControl:
    """Control the gate/reset services and observe post-reset map readiness."""

    def __init__(
        self,
        *,
        node_name: str = "roki_slam_session_control",
        reset_service: str = "/slam_toolbox/reset",
        scan_topic: str = "/scan",
        map_topic: str = "/map",
        map_frame: str = "map",
        odom_frame: str = "odom",
        discovery_timeout_sec: float = 15.0,
        service_timeout_sec: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._node_name = node_name
        self._reset_service = reset_service
        self._scan_topic = scan_topic
        self._map_topic = map_topic
        self._map_frame = map_frame
        self._odom_frame = odom_frame
        self._discovery_timeout_sec = discovery_timeout_sec
        self._service_timeout_sec = service_timeout_sec
        self._clock = clock
        self._lock = threading.Lock()
        self._condition = threading.Condition()
        self._tracker = FreshMapTracker(clock=clock)
        self._node: Any = None
        self._executor: Any = None
        self._thread: threading.Thread | None = None
        self._owns_rclpy_context = False
        self._reset_client: Any = None
        self._reset_type: Any = None
        self._tf_buffer: Any = None
        self._tf_listener: Any = None
        self._time_type: Any = None
        self._duration_type: Any = None

    def start(self) -> None:
        with self._lock:
            if self._node is not None:
                return
            import rclpy
            from nav_msgs.msg import OccupancyGrid
            from rclpy.duration import Duration
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.qos import (
                DurabilityPolicy,
                HistoryPolicy,
                QoSProfile,
                ReliabilityPolicy,
                qos_profile_sensor_data,
            )
            from rclpy.time import Time
            from sensor_msgs.msg import LaserScan
            from slam_toolbox.srv import Reset
            from tf2_ros import Buffer, TransformListener

            self._reset_type = Reset
            self._time_type = Time
            self._duration_type = Duration
            self._owns_rclpy_context = not rclpy.ok()
            if self._owns_rclpy_context:
                rclpy.init(args=None)
            self._node = rclpy.create_node(self._node_name)
            self._reset_client = self._node.create_client(Reset, self._reset_service)
            self._node.create_subscription(
                LaserScan,
                self._scan_topic,
                self._on_scan,
                qos_profile_sensor_data,
            )
            map_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            self._node.create_subscription(
                OccupancyGrid, self._map_topic, self._on_map, map_qos
            )
            self._tf_buffer = Buffer()
            self._tf_listener = TransformListener(
                self._tf_buffer, self._node, spin_thread=False
            )
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._thread = threading.Thread(
                target=self._executor.spin,
                name="ros-slam-session-control",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            started = self._node is not None
        if started:
            try:
                self.close()
            except Exception as exc:
                print(
                    "[SLAM] shutdown close failed "
                    f"type={type(exc).__name__}"
                )
        with self._lock:
            if self._executor is not None:
                self._executor.shutdown()
            if self._thread is not None:
                self._thread.join(timeout=2.0)
            if self._node is not None:
                self._node.destroy_node()
            if self._owns_rclpy_context:
                import rclpy

                if rclpy.ok():
                    rclpy.shutdown()
            self._node = None
            self._executor = None
            self._thread = None
            self._reset_client = None
            self._tf_listener = None
            self._tf_buffer = None

    def reset_slam(self) -> None:
        if self._reset_type is None:
            raise ServiceCallFailed("scan gate transport is not started")
        request = self._reset_type.Request()
        request.pause_new_measurements = False
        response = self._invoke(
            self._reset_client,
            request,
            self._reset_service,
        )
        if int(getattr(response, "result", -1)) != int(
            self._reset_type.Response.RESULT_SUCCESS
        ):
            raise ServiceCallFailed(
                f"{self._reset_service} failed result={getattr(response, 'result', None)}"
            )

    def marker(self) -> SlamMarker:
        with self._condition:
            return self._tracker.marker()

    def wait_for_fresh_map(
        self, marker: SlamMarker, *, timeout_sec: float
    ) -> bool:
        deadline = self._clock() + timeout_sec
        with self._condition:
            while not self._tracker.fresh_map_ready(marker):
                remaining = deadline - self._clock()
                if remaining <= 0:
                    return False
                self._condition.wait(min(remaining, 0.2))
        return self._wait_for_transform(deadline)

    def wait_for_localization_ready(
        self, marker: SlamMarker, *, timeout_sec: float
    ) -> bool:
        deadline = self._clock() + timeout_sec
        with self._condition:
            while self._tracker.first_scan_after(marker) is None:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    return False
                self._condition.wait(min(remaining, 0.2))
        return self._wait_for_transform(deadline)

    def _invoke(self, client: Any, request: Any, description: str) -> Any:
        if client is None:
            raise ServiceCallFailed(f"{description} transport is not started")
        if not client.wait_for_service(timeout_sec=self._discovery_timeout_sec):
            raise ServiceCallFailed(f"{description} is not available")
        return wait_for_response(
            client.call_async(request),
            timeout_sec=self._service_timeout_sec,
            description=description,
        )

    def _on_scan(self, message: Any) -> None:
        with self._condition:
            self._tracker.note_scan(self._stamp_ns(message))
            self._condition.notify_all()

    def _on_map(self, message: Any) -> None:
        with self._condition:
            self._tracker.note_map(self._stamp_ns(message))
            self._condition.notify_all()

    @staticmethod
    def _stamp_ns(message: Any) -> int:
        stamp = getattr(getattr(message, "header", None), "stamp", None)
        if stamp is None:
            return 0
        return int(getattr(stamp, "sec", 0)) * 1_000_000_000 + int(
            getattr(stamp, "nanosec", 0)
        )

    def _wait_for_transform(self, deadline: float) -> bool:
        while self._clock() < deadline:
            if self._tf_buffer is not None and self._tf_buffer.can_transform(
                self._map_frame,
                self._odom_frame,
                self._time_type(),
                timeout=self._duration_type(seconds=0.1),
            ):
                return True
            time.sleep(0.05)
        return False
