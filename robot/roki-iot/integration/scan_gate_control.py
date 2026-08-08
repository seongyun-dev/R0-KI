"""Internal ROS control and readiness observation for the SLAM scan gate."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from integration.localization_mode import ServiceCallFailed, wait_for_response


@dataclass(frozen=True)
class ScanGateMarker:
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

    def marker(self) -> ScanGateMarker:
        return ScanGateMarker(self._scan_sequence, self._map_sequence)

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

    def first_scan_after(self, marker: ScanGateMarker) -> _Observation | None:
        return next(
            (item for item in self._scans if item.sequence > marker.scan_sequence),
            None,
        )

    def fresh_map_ready(self, marker: ScanGateMarker) -> bool:
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


class RosScanGateControl:
    """Control the gate/reset services and observe post-reset map readiness."""

    def __init__(
        self,
        *,
        node_name: str = "roki_scan_gate_control",
        gate_service: str = "/roki/scan_gate/set_enabled",
        reset_service: str = "/slam_toolbox/reset",
        scan_topic: str = "/slam_scan",
        map_topic: str = "/map",
        map_frame: str = "map",
        odom_frame: str = "odom",
        discovery_timeout_sec: float = 15.0,
        service_timeout_sec: float = 15.0,
        # 기동 시 map 프레임을 만들어 두는 창(_prime_map_frame 참고).
        # 라이다 10Hz 에서 스캔 한 장이면 되므로 여유가 크다.
        prime_timeout_sec: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._node_name = node_name
        self._gate_service = gate_service
        self._reset_service = reset_service
        self._scan_topic = scan_topic
        self._map_topic = map_topic
        self._map_frame = map_frame
        self._odom_frame = odom_frame
        self._discovery_timeout_sec = discovery_timeout_sec
        self._service_timeout_sec = service_timeout_sec
        self._prime_timeout_sec = prime_timeout_sec
        self._clock = clock
        self._lock = threading.Lock()
        self._condition = threading.Condition()
        self._tracker = FreshMapTracker(clock=clock)
        self._node: Any = None
        self._executor: Any = None
        self._thread: threading.Thread | None = None
        self._owns_rclpy_context = False
        self._gate_client: Any = None
        self._reset_client: Any = None
        self._set_bool_type: Any = None
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
            from std_srvs.srv import SetBool
            from tf2_ros import Buffer, TransformListener

            self._set_bool_type = SetBool
            self._reset_type = Reset
            self._time_type = Time
            self._duration_type = Duration
            self._owns_rclpy_context = not rclpy.ok()
            if self._owns_rclpy_context:
                rclpy.init(args=None)
            self._node = rclpy.create_node(self._node_name)
            self._gate_client = self._node.create_client(SetBool, self._gate_service)
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
                name="ros-scan-gate-control",
                daemon=True,
            )
            self._thread.start()
        try:
            # 먼저 닫아 릴레이 프로세스만 살아남은 경우의 상태를 확정한 뒤,
            # 기동 스캔을 열어 map 프레임을 세운다(_open_for_idle 참고).
            self.close()
            self._open_for_idle()
        except Exception:
            self.stop()
            raise

    def _open_for_idle(self) -> None:
        """기동 시 게이트를 열고 **열어 둔다**. IDLE 의 기본은 열림이다.

        Nav2 의 ``Costmap2DROS::on_activate`` 는 ``map`` 프레임이 생길 때까지
        2Hz 로 **무한히** 기다린다. 실패 반환 경로가 없어서 lifecycle 관리자도
        깨우지 못하고, 순차 활성화라 그 뒤 노드는 정의상 active 가 되지 못한다.
        표준 스택에서 이 대기가 초 단위로 끝나는 이유는 라이다가 항상 흐르기
        때문인데, 우리는 그 스캔을 기본 CLOSED 게이트 뒤에 두었다.

        그래서 게이트를 여는 코드보다 앞에 있는 Nav2 준비 확인이 전부 순환이
        된다. 2026-08-09 01:43~01:45 실측: START_MAPPING 이 NAV2_NOT_READY 로
        연속 거부되고, 그 거부가 게이트를 다시 닫아 회복 경로도 없었다.

        **한 번 열었다 닫는 것으로는 안 된다.** 2026-08-09 02:45 에 그렇게
        해봤고 실패했다. slam_toolbox 의 TF 발행 루프는
        ``msg.header.stamp = scan_timestamp + transform_timeout_`` 로 내는데
        (slam_toolbox_common.cpp:257-270), ``scan_timestamp`` 은 마지막으로
        처리한 스캔의 시각이다. 게이트를 닫으면 새 스캔이 없으므로 그 스탬프가
        얼어붙는다. Nav2 는 최신값 조회(TimePointZero)라 통과하지만, 지도
        좌표 pose 는 시각을 지정해 조회하므로 현재 시각의 ``odom->base_link``
        와 합성되지 않는다::

            Lookup would require extrapolation into the past.
            Requested time 1786211148.747976        <- 게이트를 닫은 순간
            but the earliest data is at 1786211399.764266

        pose 가 없으면 백엔드가 명령을 아예 로봇까지 보내지 않는다. 즉
        "Nav2 는 살았는데 아무 명령도 못 받는" 상태가 된다.

        신선한 map->odom 은 스캔이 **계속** 흘러야만 나온다. 우회로가 없다.

        열어두어도 이전 지도가 겹치지 않는다. 겹침(직사각형 방이 별모양이
        되던 문제)의 원인은 게이트가 아니라 ``toggleMode()`` 였다 --
        매핑->매핑이면 즉시 return 하고 매핑 그래프를 지우지 않는다
        (experimental/slam_toolbox_map_and_localization.cpp:59-63). 지우는
        것은 매핑 START 마다 부르는 ``reset_slam()`` -> ``Mapper::Reset()``
        뿐이고(karto_sdk/src/Mapper.cpp:2685, 그래프·스캔매처·센서매니저를
        delete), 실패하면 SLAM_RESET_FAILED 로 매핑이 시작조차 안 된다.
        IDLE 중 쌓인 스캔은 그 리셋이 통째로 지운다. 순찰은
        ``deserialize_map`` 이 그래프를 교체한다.

        실패해도 예외를 올리지 않는다. 못 열어도 첫 매핑이 열면서 같은 일이
        일어난다 -- 기동을 막을 이유는 없다.
        """

        try:
            self.open()
        except Exception as exc:
            print(f"[SCAN_GATE] idle open failed type={type(exc).__name__}")
            return
        deadline = self._clock() + self._prime_timeout_sec
        if self._wait_for_transform(deadline):
            print("[SCAN_GATE] idle OPEN, map frame ready")
        else:
            print(
                "[SCAN_GATE] idle OPEN, map frame not ready after "
                f"{self._prime_timeout_sec:.0f}s"
            )

    def stop(self) -> None:
        with self._lock:
            started = self._node is not None
        if started:
            try:
                self.close()
            except Exception as exc:
                print(
                    "[SCAN_GATE] shutdown close failed "
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
            self._gate_client = None
            self._reset_client = None
            self._tf_listener = None
            self._tf_buffer = None

    def open(self) -> None:
        self._set_enabled(True)

    def close(self) -> None:
        self._set_enabled(False)

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

    def marker(self) -> ScanGateMarker:
        with self._condition:
            return self._tracker.marker()

    def wait_for_fresh_map(
        self, marker: ScanGateMarker, *, timeout_sec: float
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
        self, marker: ScanGateMarker, *, timeout_sec: float
    ) -> bool:
        deadline = self._clock() + timeout_sec
        with self._condition:
            while self._tracker.first_scan_after(marker) is None:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    return False
                self._condition.wait(min(remaining, 0.2))
        return self._wait_for_transform(deadline)

    def wait_for_quiescence(
        self, *, quiet_sec: float = 0.25, timeout_sec: float = 2.0
    ) -> bool:
        deadline = self._clock() + timeout_sec
        with self._condition:
            sequence = self._tracker.scan_sequence
            stable_since = self._clock()
            while True:
                now = self._clock()
                current = self._tracker.scan_sequence
                if current != sequence:
                    sequence = current
                    stable_since = now
                if now - stable_since >= quiet_sec:
                    return True
                remaining = min(deadline - now, quiet_sec - (now - stable_since))
                if remaining <= 0:
                    return False
                self._condition.wait(min(remaining, 0.1))

    def _set_enabled(self, enabled: bool) -> None:
        if self._set_bool_type is None:
            raise ServiceCallFailed("scan gate transport is not started")
        request = self._set_bool_type.Request()
        request.data = bool(enabled)
        self._invoke(self._gate_client, request, self._gate_service)

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
