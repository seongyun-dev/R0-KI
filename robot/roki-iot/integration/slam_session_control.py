"""slam_toolbox 세션 제어와 준비 상태 관측.

예전에는 여기가 스캔 게이트 제어였다. 게이트는 08aa27f 에서 걷어냈고
(slam 이 라이다를 직접 구독한다) 리셋과 관측만 남았다.
"""

from __future__ import annotations

import math
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


@dataclass(frozen=True)
class LocalizationPoseObservation:
    """One pose produced by slam_toolbox after localization processing."""

    sequence: int
    stamp_ns: int
    arrival: float
    frame_id: str
    x: float
    y: float
    yaw_rad: float
    covariance_x: float
    covariance_y: float
    covariance_yaw: float


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
        # slam_toolbox 의 pose 발행은 **네임스페이스** 기준으로 풀린다.
        # 서비스만 이름에 "slam_toolbox/" 접두사가 박혀 있고(serialize_map 등)
        # pose_pub_ 는 그냥 "pose" 라서 `/slam_toolbox/pose` 가 아니라 `/pose` 다.
        # /map, /scan 과 같은 자리다. 실기 확인: Publisher count 1.
        pose_topic: str = "/pose",
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
        self._pose_topic = pose_topic
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
        self._initialpose_publisher: Any = None
        self._initialpose_type: Any = None
        self._tf_buffer: Any = None
        self._tf_listener: Any = None
        self._time_type: Any = None
        self._duration_type: Any = None
        self._last_localization_pose_at: float | None = None
        self._last_localization_stamp_ns: int = 0
        self._localization_pose_sequence = 0
        self._last_localization_pose: LocalizationPoseObservation | None = None

    def start(self) -> None:
        with self._lock:
            if self._node is not None:
                return
            import rclpy
            from geometry_msgs.msg import PoseWithCovarianceStamped
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
            self._initialpose_type = PoseWithCovarianceStamped
            self._initialpose_publisher = self._node.create_publisher(
                PoseWithCovarianceStamped,
                "/initialpose",
                10,
            )
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
            self._node.create_subscription(
                PoseWithCovarianceStamped,
                self._pose_topic,
                self._on_localization_pose,
                10,
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
            self._initialpose_publisher = None
            self._initialpose_type = None
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

    def relocalize(
        self,
        *,
        x: float,
        y: float,
        yaw_rad: float,
        timeout_sec: float,
        position_tolerance_m: float,
        yaw_tolerance_rad: float,
    ) -> tuple[bool, str]:
        """Seed slam_toolbox and accept only a new matching localization pose.

        Waiting for a subscriber avoids the discovery race of a short-lived
        ``ros2 topic pub --once`` process. Publishing is not considered an ACK;
        only a subsequently observed matching ``/pose`` confirms localization.
        """

        publisher = self._initialpose_publisher
        message_type = self._initialpose_type
        node = self._node
        if publisher is None or message_type is None or node is None:
            return False, "INITIALPOSE_TRANSPORT_NOT_READY"
        if timeout_sec <= 0:
            return False, "INITIALPOSE_TIMEOUT"

        deadline = self._clock() + float(timeout_sec)
        while self._clock() < deadline:
            try:
                if int(publisher.get_subscription_count()) > 0:
                    break
            except (AttributeError, TypeError, ValueError):
                return False, "INITIALPOSE_TRANSPORT_NOT_READY"
            time.sleep(0.05)
        else:
            return False, "INITIALPOSE_SUBSCRIBER_MISSING"

        with self._condition:
            marker = self._localization_pose_sequence

        message = message_type()
        message.header.frame_id = self._map_frame
        message.header.stamp = node.get_clock().now().to_msg()
        message.pose.pose.position.x = float(x)
        message.pose.pose.position.y = float(y)
        message.pose.pose.position.z = 0.0
        message.pose.pose.orientation.x = 0.0
        message.pose.pose.orientation.y = 0.0
        message.pose.pose.orientation.z = math.sin(float(yaw_rad) / 2.0)
        message.pose.pose.orientation.w = math.cos(float(yaw_rad) / 2.0)
        # A useful search prior without pretending centimeter-level certainty.
        message.pose.covariance[0] = 0.25**2
        message.pose.covariance[7] = 0.25**2
        message.pose.covariance[35] = math.radians(15.0) ** 2

        published_at = self._clock()
        publisher.publish(message)
        print(
            "[INITIALPOSE] published "
            f"x={x:.3f} y={y:.3f} yawDeg={math.degrees(yaw_rad):.1f}"
        )

        last_observation: LocalizationPoseObservation | None = None
        observed_sequence = marker
        with self._condition:
            while self._clock() < deadline:
                observation = self._last_localization_pose
                if (
                    observation is not None
                    and observation.sequence > observed_sequence
                    and observation.arrival >= published_at
                ):
                    observed_sequence = observation.sequence
                    last_observation = observation
                    if self._localization_pose_matches(
                        observation,
                        x=float(x),
                        y=float(y),
                        yaw_rad=float(yaw_rad),
                        position_tolerance_m=float(position_tolerance_m),
                        yaw_tolerance_rad=float(yaw_tolerance_rad),
                    ):
                        print(
                            "[INITIALPOSE] confirmed "
                            f"x={observation.x:.3f} y={observation.y:.3f} "
                            f"yawDeg={math.degrees(observation.yaw_rad):.1f}"
                        )
                        return True, "START_POSE_CONFIRMED"
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break
                self._condition.wait(min(remaining, 0.2))

        if last_observation is None:
            return False, "INITIALPOSE_POSE_TIMEOUT"
        distance = math.hypot(
            last_observation.x - float(x),
            last_observation.y - float(y),
        )
        yaw_error = abs(
            self._angle_difference(last_observation.yaw_rad, float(yaw_rad))
        )
        print(
            "[INITIALPOSE] rejected "
            f"frame={last_observation.frame_id or '?'} "
            f"distance={distance:.3f}m yawErrorDeg={math.degrees(yaw_error):.1f}"
        )
        return False, "START_POSE_MISMATCH"

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

    def _on_localization_pose(self, message: Any) -> None:
        """slam 이 스캔을 **실제로 처리했을 때만** 오는 메시지.

        slam_toolbox 는 ``processed`` 가 참일 때에만 ``setTransformFromPoses`` 와
        ``publishPose`` 를 부른다(slam_toolbox_localization.cpp:194-203). 그래서
        이 한 건이 "위치추정이 실행됐다"는 직접 증거다. ``map->odom`` 은 값이
        바뀌지 않아도 ``transform_publish_period`` 마다(50Hz) 재발행되므로
        그쪽 신선도로는 실행 여부를 알 수 없다 -- 어제 얼어붙은 TF 에 당한
        지점이 정확히 그것이다.

        ``HasMovedEnough`` 는 모터가 아니라 **오도메트리 변화**를 본다. 그래서
        섀시가 서 있어도 발행된다 -- 2026-08-09 14:32:42~14:33:24 실측:
        ``auth=0 fwd=0 rev=0`` 로 295초간 인가 명령이 0건인 구간에서 16건.
        rf2o 가 정지 중 임계값(0.10m / 0.10rad)을 넘게 흘러가고 스캔매칭이
        매번 당겨오기 때문이다. 그때 교정된 자세는 ±3cm 안에서 흔들릴 뿐
        누적되지 않았고 covXX/covYY 0.0012~0.0019, covYaw 0.0001~0.0004 였다.
        이것이 **정상 배치의 기준선**이다.

        간격은 그 구간에서 중앙값 약 2초, 최대 10.4초였다. 판정에 "N건을
        기다린다" 를 넣을 때 이 최대값을 넘겨야 한다.

        한 건이 증명하는 것은 "스캔이 처리되고 자세가 발행됐다" 까지다.
        재위치추정이 **맞았다**는 증거가 아니고, 매핑 모드에서도 발행되므로
        위치추정 모드라는 증거도 아니다. 강제 매칭인지 일상적인
        ``ProcessLocalization`` 인지도 이 메시지만으로는 구별되지 않는다.

        지금은 **관측만 한다.** covariance 임계값을 지금 추측으로 정하면
        근거 없는 상수가 하나 더 생길 뿐이다. 배치를 바꿔가며 실측한 분포가
        나온 뒤에 판정을 붙인다.
        """

        pose = getattr(getattr(message, "pose", None), "pose", None)
        if pose is None:
            return
        arrival = self._clock()
        stamp_ns = self._stamp_ns(message)
        covariance = getattr(getattr(message, "pose", None), "covariance", None)
        yaw = self._yaw_from_quaternion(pose.orientation)
        frame = getattr(getattr(message, "header", None), "frame_id", "") or ""
        with self._condition:
            previous_arrival = self._last_localization_pose_at
            previous_stamp = self._last_localization_stamp_ns
            self._last_localization_pose_at = arrival
            self._last_localization_stamp_ns = stamp_ns
            self._localization_pose_sequence += 1
            self._last_localization_pose = LocalizationPoseObservation(
                sequence=self._localization_pose_sequence,
                stamp_ns=stamp_ns,
                arrival=arrival,
                frame_id=frame,
                x=float(pose.position.x),
                y=float(pose.position.y),
                yaw_rad=float(yaw),
                covariance_x=self._covariance_at(covariance, 0),
                covariance_y=self._covariance_at(covariance, 7),
                covariance_yaw=self._covariance_at(covariance, 35),
            )
            self._condition.notify_all()
        # 도착 간격과 발행 간격을 따로 적는다. executor 가 밀리면 오래된
        # 메시지가 몰려 도착해 도착 간격만 짧아진다. slam 이 언제 처리했는지는
        # 스탬프로만 안다.
        arrival_gap = (
            "-"
            if previous_arrival is None
            else f"{arrival - previous_arrival:.2f}"
        )
        source_gap = (
            "-"
            if not previous_stamp or not stamp_ns
            else f"{(stamp_ns - previous_stamp) / 1_000_000_000:.2f}"
        )
        print(
            "[SLAM POSE] "
            f"frame={frame or '?'} "
            f"x={pose.position.x:.3f} y={pose.position.y:.3f} "
            f"yawDeg={math.degrees(yaw):.1f} "
            f"covXX={self._covariance_at(covariance, 0):.4f} "
            f"covYY={self._covariance_at(covariance, 7):.4f} "
            f"covYaw={self._covariance_at(covariance, 35):.4f} "
            f"arrivalGapSec={arrival_gap} sourceGapSec={source_gap}"
        )

    @staticmethod
    def _covariance_at(covariance: Any, index: int) -> float:
        """36칸 공분산에서 대각 성분 하나. 못 읽으면 nan.

        rclpy 콜백에서 예외가 나가면 executor spin 이 죽는다. 로그 한 줄 때문에
        구독 전체를 잃을 수는 없다.
        """

        try:
            return float(covariance[index])
        except (TypeError, IndexError, ValueError, KeyError):
            return float("nan")

    @staticmethod
    def _yaw_from_quaternion(rotation: Any) -> float:
        # 평면 주행이라 yaw 만 쓴다. z/x/y 회전 성분은 무시한다.
        return math.atan2(
            2.0 * (rotation.w * rotation.z + rotation.x * rotation.y),
            1.0 - 2.0 * (rotation.y * rotation.y + rotation.z * rotation.z),
        )

    def _localization_pose_matches(
        self,
        observation: LocalizationPoseObservation,
        *,
        x: float,
        y: float,
        yaw_rad: float,
        position_tolerance_m: float,
        yaw_tolerance_rad: float,
    ) -> bool:
        if observation.frame_id != self._map_frame:
            return False
        if math.hypot(observation.x - x, observation.y - y) > position_tolerance_m:
            return False
        return (
            abs(self._angle_difference(observation.yaw_rad, yaw_rad))
            <= yaw_tolerance_rad
        )

    @staticmethod
    def _angle_difference(actual: float, expected: float) -> float:
        return math.atan2(math.sin(actual - expected), math.cos(actual - expected))

    @staticmethod
    def _stamp_ns(message: Any) -> int:
        stamp = getattr(getattr(message, "header", None), "stamp", None)
        if stamp is None:
            return 0
        return int(getattr(stamp, "sec", 0)) * 1_000_000_000 + int(
            getattr(stamp, "nanosec", 0)
        )

    def current_map_pose(self) -> tuple[float, float, float] | None:
        """지금 slam 이 믿고 있는 지도 좌표계 자세 ``(x, y, yaw)``.

        **호출자가 좌표계를 책임진다.** 이 값은 slam 이 *현재* 들고 있는 지도의
        좌표계에 있다. 매핑 직후라면 방금 저장한 포즈그래프와 같은 좌표계이므로
        그 그래프를 적재할 때 seed 로 쓸 수 있다. 반대로 재부팅 뒤 예전 지도를
        적재하는 경우에는 무관한 임시 지도의 좌표라서 쓰면 안 된다 -- 그때는
        도킹 지점이 맞다.

        신선하지 않으면 None 을 준다. 얼어붙은 TF 로 seed 를 잡으면 로봇이
        과거 위치에서 위치추정을 시작한다.
        """

        if self._tf_buffer is None:
            return None
        try:
            transform = self._tf_buffer.lookup_transform(
                self._map_frame,
                "base_link",
                self._time_type(),
                timeout=self._duration_type(seconds=0.5),
            )
        except Exception as exc:
            print(f"[SLAM] map pose read failed type={type(exc).__name__}")
            return None
        if not self._transform_is_fresh(transform):
            return None
        translation = transform.transform.translation
        yaw = self._yaw_from_quaternion(transform.transform.rotation)
        return float(translation.x), float(translation.y), float(yaw)

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
        """발행 시각이 지금으로부터 ``_transform_max_age_sec`` 이내인가.

        slam 은 스탬프에 ``transform_timeout_`` 를 더해 발행하므로 정상
        운행에서 나이가 **음수**(미래)로 나온다. 실측 -0.10 ~ -0.12초.
        그래서 상한만 보면 안 된다 -- 얼어붙은 TF 가 미래 스탬프를 달고 있으면
        영원히 신선해 보인다. 아래로도 같은 폭만큼 막는다.
        """

        if self._node is None:
            return True
        # _stamp_ns 는 **메시지**를 받아 header.stamp 를 푼다. 여기서 stamp 를
        # 미리 풀어 넘기면 Time 에 .header 가 없어 항상 0 이 나오고, 아래
        # `if not stamp_ns` 가 항상 참이 되어 이 함수가 **상수 False** 가 된다.
        stamp_ns = self._stamp_ns(transform)
        if not stamp_ns:
            return False
        now_ns = self._node.get_clock().now().nanoseconds
        age_sec = (now_ns - stamp_ns) / 1_000_000_000
        if -self._transform_max_age_sec <= age_sec <= self._transform_max_age_sec:
            return True
        print(
            f"[SLAM] {self._map_frame}->{self._odom_frame} is stale "
            f"ageSec={age_sec:.1f} -- slam 이 살아 있는지 확인할 것"
        )
        return False
