"""slam_toolbox 세션 제어와 준비 상태 관측.

예전에는 여기가 스캔 게이트 제어였다. 게이트는 08aa27f 에서 걷어냈고
(slam 이 라이다를 직접 구독한다) 리셋과 관측만 남았다.
"""

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
    """리셋 이후 첫 스캔의 산물인 지도만 새것으로 센다."""

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
    """리셋 서비스를 호출하고 리셋 이후의 지도/TF 가 실제로 왔는지 관측한다."""

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
        # map->odom 이 이보다 오래됐으면 위치추정이 살아 있다고 보지 않는다.
        # slam 이 죽어도 tf2 버퍼에 남은 값이 존재 검사를 통과하기 때문이다.
        # slam 은 스캔마다 발행하므로(10Hz) 정상 운행에서 1초를 넘길 일이 없다.
        transform_max_age_sec: float = 2.0,
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
        self._transform_max_age_sec = transform_max_age_sec
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
            raise ServiceCallFailed("slam session transport is not started")
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
        """map->odom 이 **최근에** 발행됐는지 본다. 존재만으로는 부족하다.

        예전에는 ``can_transform(..., Time())`` 으로 "가장 최근 것"을 물었다.
        그 조회는 나이를 보지 않으므로 **얼어붙은 TF 도 통과**한다.

        성립 경로: slam 프로세스만 죽고 라이다는 살아 있는 경우. 관측자는
        ``/scan`` 을 slam 을 거치지 않고 직접 구독하므로 "리셋 이후 스캔"
        조건은 만족되고, tf2 버퍼에 남아 있는 직전 map->odom 이 존재 검사를
        통과한다. 그러면 **죽은 위치추정 위에서 순찰이 출발한다.**

        2026-08-09 02:45 에 같은 부류를 실제로 겪었다. 그때는 스캔을 끊어
        스탬프가 얼어붙었고, pose 조회가 extrapolation 오류로 영구 실패했다.
        지금은 스캔이 항상 흐르므로 그 경로는 사라졌지만, slam 이 죽는 경우는
        남는다. 존재가 아니라 신선도를 물어야 그 부류가 닫힌다.
        """

        if self._tf_buffer is None:
            return False
        while self._clock() < deadline:
            try:
                transform = self._tf_buffer.lookup_transform(
                    self._map_frame,
                    self._odom_frame,
                    self._time_type(),
                    timeout=self._duration_type(seconds=0.1),
                )
            except Exception:
                time.sleep(0.05)
                continue
            if self._transform_is_fresh(transform):
                return True
            time.sleep(0.05)
        return False

    def _transform_is_fresh(self, transform: Any) -> bool:
        """발행 시각이 ROS 현재 시각에서 ``_transform_max_age_sec`` 이내인가.

        벽시계가 아니라 ROS 시계로 비교해야 한다. TF 스탬프는 ROS 시각이고,
        젯슨은 RTC 를 유지하지 않아 부팅 초반 두 시계가 크게 어긋난다.
        """

        if self._node is None:
            return True
        stamp_ns = self._stamp_ns(getattr(transform.header, "stamp", None))
        if not stamp_ns:
            return False
        now_ns = self._node.get_clock().now().nanoseconds
        age_sec = (now_ns - stamp_ns) / 1_000_000_000
        if age_sec <= self._transform_max_age_sec:
            return True
        print(
            f"[SLAM] {self._map_frame}->{self._odom_frame} is stale "
            f"ageSec={age_sec:.1f} -- slam 이 살아 있는지 확인할 것"
        )
        return False
