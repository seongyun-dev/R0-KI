"""slam_toolbox 하나로 매핑과 위치추정을 오간다.

지금까지 모드 전환은 프로세스 교체였다. `AIOT_ROS_MODE` 를 다시 쓰고
`aiot-ros` 를 재시작해 launch 파일 자체를 바꿔 끼웠고, 시리얼 소유자인
`aiot-robot` 까지 함께 내려갔다. 그 재시작 하나가 다섯 가지 고장을 만들었다
(2026-08-07 현장 관측):

- 전환에 약 3분
- 재시작마다 시리얼 재동기화 폭풍 수백 건 -> ENCODER_ZERO 핸드셰이크 2회 실패
- 진행 중이던 매핑 세션이 고아가 되어 다음 START_MAPPING 이 409 로 거부됨
- DDS 그래프가 갈아엎히며 ROS 데몬 캐시가 낡아 bt_navigator 를 "Node not found"
  로 답함 -> explore 가 NAV2_NOT_ACTIVE 로 기동하지 않음
- 사람이 aiot-prepare-mapping 을 손으로 돌려야 함

slam_toolbox 는 이 전환을 서비스 호출로 제공한다. `map_and_localization`
노드가 `slam_toolbox/set_localization_mode`(std_srvs/SetBool)를 열어두고,
`deserialize_map` 이 저장된 포즈그래프를 LOCALIZE_AT_POSE 로 불러온다.
2026-08-07 이 젯슨에서 왕복 전환과 7.2MB 그래프 적재를 실증했다.

이 모듈은 정책만 담는다. 실제 서비스 호출은 주입받는다. ROS 없이 테스트할 수
있어야 하고, 전송 방식이 바뀌어도 순서와 안전 규칙은 그대로여야 하기 때문이다.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from aiot_robot.ros_config import MODE_PROFILES

# slam_toolbox/srv/DeserializePoseGraph 의 match_type.
# 저장된 그래프를 주어진 포즈 근처에서 위치추정 시작점으로 삼는다.
LOCALIZE_AT_POSE = 3


@dataclass(frozen=True)
class DockPose:
    """지도 좌표계에서 본 도킹 지점. 위치추정의 초기 추정값이다."""

    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0


def posegraph_files_present(posegraph_path: str) -> bool:
    """slam_toolbox 가 실제로 읽을 두 파일이 다 있는지 본다.

    직렬화는 확장자 없는 경로를 받아 ``.posegraph`` 와 ``.data`` 두 개를
    만든다. 하나만 있으면 적재는 실패하는데 서비스는 그 실패를 알려주지
    않으므로, 호출 전에 여기서 걸러야 한다.
    """

    from pathlib import Path

    base = Path(posegraph_path)
    return (
        base.with_suffix(".posegraph").is_file()
        and base.with_suffix(".data").is_file()
    )


class ModeTransport(Protocol):
    """slam_toolbox 서비스 두 개와 Nav2 파라미터 주입으로 좁힌 전송 경계."""

    def set_localization_mode(self, localization: bool) -> None:
        """실패하면 예외를 던진다. 조용히 실패하면 안 된다."""

    def deserialize_map(
        self,
        filename: str,
        match_type: int,
        initial_pose: DockPose,
    ) -> None:
        """실패하면 예외를 던진다."""

    def set_node_parameters(
        self,
        node_name: str,
        values: Mapping[str, object],
    ) -> None:
        """실패하면 예외를 던진다. 하나라도 거부되면 실패다."""


class LocalizationModeController:
    """매핑/순찰 모드를 서비스 호출로 전환한다.

    호출자는 두 가지만 알면 된다: ``enter_mapping`` 과 ``enter_patrol``.
    순서와 실패 처리는 여기가 책임진다.
    """

    MAPPING = "mapping"
    PATROL = "patrol"

    def __init__(
        self,
        transport: ModeTransport,
        *,
        dock_pose: DockPose | None = None,
        posegraph_exists: Callable[[str], bool] | None = None,
        report: Callable[[str], None] | None = None,
        profiles: Mapping[str, Mapping[str, Mapping[str, object]]] | None = None,
    ) -> None:
        self._transport = transport
        # 운행별 Nav2 값. 렌더된 파라미터 파일은 매핑 값을 담고, 순찰 값은
        # 전환 시 여기서 주입된다 -- ros_config.MODE_PROFILES 의 주석이 그렇게
        # 설계라고 적어두었는데 주입하는 쪽이 없었다. 기본값을 두는 이유는
        # 그것이다: 주입을 잊으면 "정의만 되고 적용되지 않는" 상태로 되돌아간다.
        self._profiles = MODE_PROFILES if profiles is None else profiles
        # 그래프를 불러올 때 줄 초기 추정값. 규약상 웨이포인트 1 = 도킹 지점 =
        # 매핑 시작점 = map (0,0,0) 이므로 기본값이 곧 정답이지만, 도킹 표시를
        # 옮기면 ROKI_INITIAL_POSE_* 로 알려줘야 스캔 매칭이 수렴한다.
        self._dock_pose = dock_pose or DockPose()
        self._posegraph_exists = posegraph_exists or posegraph_files_present
        self._report = report
        self._lock = threading.Lock()
        # 시작 시점의 모드를 안다고 가정하지 않는다. 첫 전환이 실제 상태를
        # 확정한다. 모른다고 두면 첫 요청을 반드시 전송하게 되어 안전하다.
        self._mode: str | None = None
        self._patrol_arguments: tuple[str, DockPose] | None = None

    @property
    def mode(self) -> str | None:
        with self._lock:
            return self._mode

    def enter_mapping(self) -> tuple[bool, str]:
        """새 지도를 그릴 수 있는 상태로 만든다.

        ``set_localization_mode(False)`` 는 위치추정 버퍼를 비우고 map saver 를
        다시 켠다. 즉 이 호출 하나가 "이전 순찰의 잔재를 지우고 새 세션을
        시작한다"는 뜻이다. 예전에는 이걸 하려고 aiot-ros 를 재시작했다.
        """

        with self._lock:
            if self._mode == self.MAPPING:
                return True, "ALREADY_MAPPING"
        try:
            self._transport.set_localization_mode(False)
        except Exception as exc:
            # 모드를 미확정으로 남긴다. 다음 요청이 다시 전송하도록.
            self._invalidate()
            self._say(f"mode switch to mapping failed type={type(exc).__name__}")
            return False, "SET_MAPPING_MODE_FAILED"
        # 매핑 진입에서는 플래너 파라미터를 주입하지 않는다.
        #
        # 2026-08-08 실측: /planner_server 에 SetParameters 를 하면 노드가
        # 23~29초 블록된다(유휴/바쁨 무관, 동적 파라미터 콜백이 플래너를
        # 재초기화한다). 그러면 4초 bond heartbeat 를 놓쳐 lifecycle manager 가
        # Nav2 전체를 비활성화하고, explore 는 비활성 Nav2 에 목표를 보내지
        # 않으므로 매핑이 조용히 한 발도 움직이지 못한다.
        #
        #   idle: cache_obstacle_heuristic   28.05s
        #   busy: motion_model_for_search    28.24s
        #   busy: 3개 동시                    28.92s
        #
        # 그리고 매핑 쪽 주입은 애초에 얻는 것이 없다. 렌더된 파라미터 파일이
        # 이미 매핑 값을 담고 있다(ros_config.apply_slam_shape). 순찰을 돌고 온
        # 뒤 되돌리는 용도였는데, 그 대가가 Nav2 사망이라면 성립하지 않는다.
        # 순찰 뒤 매핑으로 돌아갈 때 플래너를 되돌리는 문제는 별도로 풀어야
        # 한다(스택 재기동, 또는 lifecycle 전환을 끼운 안전한 주입).
        self._apply_mode_profile(self.MAPPING, planner=False)
        with self._lock:
            self._mode = self.MAPPING
            self._patrol_arguments = None
        self._say("mode=mapping")
        return True, "READY"

    #: SetParameters 가 노드를 20초 넘게 블록하는 대상. 2026-08-08 실측.
    #: bond heartbeat 가 4초라 이 노드에 주입하면 Nav2 스택이 내려간다.
    SLOW_PARAMETER_NODES = ("/planner_server",)

    def _apply_mode_profile(self, mode: str, *, planner: bool = True) -> str | None:
        """운행별 Nav2 파라미터를 실행 중에 주입한다.

        2026-08-08 실기 확인: 순찰이 돌아야 하는 자리에 매핑 값이 그대로
        올라가 있었다 -- planner ``motion_model_for_search=REEDS_SHEPP``,
        ``reverse_penalty=1.3``, controller ``yaw_goal_tolerance=3.15``.
        ``MODE_PROFILES["patrol"]`` 은 정의만 돼 있고 읽는 쪽이 테스트뿐이었다.
        그래서 순찰이 후진하고 아무 방향으로나 도착 판정을 했다.

        실패하면 이유를 돌려주되 판단은 호출자에게 맡긴다. 매핑과 순찰이
        실패를 다르게 감당하기 때문이다.
        """

        profile = self._profiles.get(mode)
        if not profile:
            return None
        for node_name, overrides in profile.items():
            if not planner and node_name in self.SLOW_PARAMETER_NODES:
                self._say(f"profile skipped mode={mode} node={node_name} reason=SLOW_NODE")
                continue
            try:
                self._transport.set_node_parameters(node_name, overrides)
            except Exception as exc:
                # 이유까지 남긴다. 2026-08-08 실기에서 type=ServiceCallFailed
                # 만 찍혀서 "서비스가 없다" 와 "노드가 값을 거부했다" 를
                # 구분할 수 없었다. 그 둘은 고칠 곳이 다르다.
                self._say(
                    f"profile apply failed mode={mode} node={node_name} "
                    f"type={type(exc).__name__} detail={exc}"
                )
                return "MODE_PROFILE_APPLY_FAILED"
        self._say(f"profile applied mode={mode}")
        return None

    def enter_patrol(
        self,
        posegraph_path: str,
        dock_pose: DockPose | None = None,
    ) -> tuple[bool, str]:
        """저장된 포즈그래프로 위치추정을 시작한다.

        순서가 중요하다. 모드를 먼저 위치추정으로 바꾸고 나서 그래프를 읽는다.
        위치추정 모드는 map saver 를 끄는데, 매핑 모드로 남은 채 그래프를
        읽으면 저장 경로가 살아 있어 원본 그래프를 덮어쓸 위험이 있다
        (upstream 경고: "Be sure to not serialize the graph in localization
        mode, you will corrupt it").
        """

        if not posegraph_path:
            return False, "POSEGRAPH_PATH_MISSING"
        # 파일 존재를 여기서 막지 않으면 아무도 막지 못한다.
        # DeserializePoseGraph 는 빈 응답을 돌려주는 서비스라 실패 신호가 없다.
        # 2026-08-07 실기 확인: 없는 경로를 주면 노드는
        # "serialization::Read: Failed to open requested file" 을 찍는데
        # 서비스는 정상 응답한다. 그대로 두면 지도 없이 순찰을 시작한다.
        if not self._posegraph_exists(posegraph_path):
            self._say(f"posegraph not found path={posegraph_path}")
            return False, "POSEGRAPH_MISSING"
        pose = dock_pose or self._dock_pose
        try:
            self._transport.set_localization_mode(True)
        except Exception as exc:
            self._invalidate()
            self._say(f"mode switch to patrol failed type={type(exc).__name__}")
            return False, "SET_LOCALIZATION_MODE_FAILED"
        try:
            self._transport.deserialize_map(posegraph_path, LOCALIZE_AT_POSE, pose)
        except Exception as exc:
            # 모드는 바뀌었는데 그래프가 없다 -- 지도 없이 순찰하는 상태다.
            # 미확정으로 남겨 호출자가 재시도하거나 중단하게 한다.
            self._invalidate()
            self._say(f"posegraph load failed type={type(exc).__name__}")
            return False, "POSEGRAPH_LOAD_FAILED"
        # 순찰은 매핑과 달리 실패를 감당할 수 없다. 렌더된 파일에는 매핑 값이
        # 들어 있으므로, 주입이 실패한 채 순찰을 READY 로 알리면 그 순찰은
        # REEDS_SHEPP 으로 후진하며 아무 방향으로나 도착 판정을 한다.
        # 미확정으로 남겨 다음 요청이 다시 전송하게 한다.
        profile_failure = self._apply_mode_profile(self.PATROL)
        if profile_failure is not None:
            self._invalidate()
            return False, profile_failure
        with self._lock:
            self._mode = self.PATROL
            self._patrol_arguments = (posegraph_path, pose)
        self._say(f"mode=patrol posegraph={posegraph_path}")
        return True, "READY"

    def ensure_patrol(
        self,
        posegraph_path: str,
        dock_pose: DockPose | None = None,
    ) -> tuple[bool, str]:
        """순찰을 시작할 수 있는 상태임을 보장한다.

        매핑 완료 시점의 인계(``mapping_runtime._enter_patrol_localization``)는
        실패할 수 있고, 재부팅한 뒤에는 아예 일어나지 않는다 -- 그 부팅에는
        매핑이 없었으므로 호출하는 쪽이 없다. 그 주석이 "순찰을 시작할 때
        다시 시도한다" 고 적어둔 경로가 실제로는 없어서, 재부팅 뒤 바로 순찰하면
        slam_toolbox 가 빈 매핑 상태로 남았다. 여기가 그 경로다.

        이미 같은 그래프로 위치추정 중이면 그래프를 다시 읽지 않는다. 7.2MB
        적재에 수 초가 걸려서(2026-08-07 실측) START_PATROL 의 TTL 을 그만큼
        붙잡는다. 대신 프로필은 항상 다시 밀어넣는다 -- 생애주기 복구가
        되돌려놓았을 수 있고, 그 확인은 서비스 호출 두 번이면 끝난다.
        """

        pose = dock_pose or self._dock_pose
        with self._lock:
            already = self._mode == self.PATROL and self._patrol_arguments == (
                posegraph_path,
                pose,
            )
        if not already:
            return self.enter_patrol(posegraph_path, dock_pose)
        profile_failure = self._apply_mode_profile(self.PATROL)
        if profile_failure is not None:
            self._invalidate()
            return False, profile_failure
        return True, "ALREADY_PATROL"

    def note_lifecycle_recovery(self, detail: str = "") -> None:
        """생애주기 관리자가 스택을 복구했음을 기록만 한다.

        복구는 configure 를 다시 돌리고, 그 configure 가 launch 시점 파라미터
        파일을 읽어 실행 중 주입한 값을 버린다. 렌더된 파일이 매핑 값을 담고
        있으므로 **매핑 중 복구는 무해하고, 순찰 중 복구만 물린다** --
        REEDS_SHEPP 과 yaw_goal_tolerance 3.15 로 되돌아가 순찰이 조용히
        후진하고 아무 방향으로나 도착 판정을 하게 된다.

        여기서 자동 재적용을 하지 않는 이유: 복구가 실제로 얼마나 자주
        일어나는지 아직 모른다. 빈도를 모르는 채 감시자를 만들면 폴링 주기를
        추측으로 정하게 된다. 먼저 재고, 그 다음에 설계한다.
        """

        with self._lock:
            mode = self._mode
        self._say(
            f"lifecycle recovery observed mode={mode or 'unknown'}"
            f"{' ' + detail if detail else ''}"
            + ("  ← 순찰 프로필이 매핑으로 되돌아갔을 수 있다" if mode == self.PATROL else "")
        )

    def reassert(self) -> tuple[bool, str]:
        """마지막으로 성립한 모드를 다시 적용한다.

        Nav2 생애주기 관리자는 bond 가 끊기면 관리 노드 전체를 복구하고, 그
        과정의 configure 가 launch 시점 파라미터 파일을 다시 읽는다. 실행 중
        주입한 값은 그때 사라진다(2026-08-07 실측: DUBIN 으로 바꿔둔
        motion_model_for_search 가 복구 후 REEDS_SHEPP 으로 되돌아옴).
        같은 일이 slam_toolbox 에도 일어날 수 있으므로 재적용 경로를 둔다.
        """

        with self._lock:
            mode = self._mode
            arguments = self._patrol_arguments
        if mode == self.MAPPING:
            self._forget()
            return self.enter_mapping()
        if mode == self.PATROL and arguments is not None:
            self._forget()
            return self.enter_patrol(arguments[0], arguments[1])
        return False, "NO_MODE_TO_REASSERT"

    def _invalidate(self) -> None:
        with self._lock:
            self._mode = None

    def _forget(self) -> None:
        # reassert 가 "이미 그 모드"라는 이유로 무시되지 않게 한다.
        with self._lock:
            self._mode = None

    def _say(self, message: str) -> None:
        if self._report is not None:
            self._report(f"[LOCALIZATION] {message}")


class ServiceCallFailed(RuntimeError):
    """서비스 호출이 응답을 못 받았거나 실패를 응답했다."""


def wait_for_response(
    future: Any,
    *,
    timeout_sec: float,
    description: str,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    poll_sec: float = 0.02,
) -> Any:
    """실행기가 다른 스레드에서 돌리는 future 를 기다린다.

    ``rclpy.spin_until_future_complete`` 를 쓰지 않는다. 우리 노드는 이미
    전용 실행기가 스핀하고 있어서, 같은 노드를 또 스핀하면 충돌한다.
    스핀은 실행기에 맡기고 여기서는 완료만 기다린다.
    """

    deadline = clock() + timeout_sec
    while not future.done():
        if clock() >= deadline:
            future.cancel()
            raise ServiceCallFailed(f"{description} timed out after {timeout_sec}s")
        sleep(poll_sec)
    exception = future.exception()
    if exception is not None:
        raise ServiceCallFailed(f"{description} raised {type(exception).__name__}")
    response = future.result()
    if response is None:
        raise ServiceCallFailed(f"{description} returned no response")
    # SetBool 은 success/message 를 준다. DeserializePoseGraph 는 빈 응답이라
    # 여기서 걸리지 않는다 -- 예외 없이 돌아온 것 자체가 성공이다.
    if getattr(response, "success", True) is False:
        detail = getattr(response, "message", "") or "no message"
        raise ServiceCallFailed(f"{description} rejected: {detail}")
    return response


class RosLocalizationModeTransport:
    """``LocalizationModeController`` 가 쓰는 실제 ROS 서비스 클라이언트.

    rclpy 는 ``start()`` 안에서 늦게 임포트한다. 이 모듈을 임포트하는 것만으로
    ROS 가 필요해지면 정책 클래스의 테스트까지 ROS 설치에 묶인다.
    """

    def __init__(
        self,
        *,
        node_name: str = "roki_localization_mode",
        set_mode_service: str = "/slam_toolbox/set_localization_mode",
        deserialize_service: str = "/slam_toolbox/deserialize_map",
        discovery_timeout_sec: float = 15.0,
        set_mode_timeout_sec: float = 15.0,
        # 7.2MB 포즈그래프 적재에 수 초가 걸린다(2026-08-07 실측). 넉넉히 준다.
        deserialize_timeout_sec: float = 60.0,
        set_parameters_timeout_sec: float = 15.0,
    ) -> None:
        self._node_name = node_name
        self._set_mode_service = set_mode_service
        self._deserialize_service = deserialize_service
        self._discovery_timeout_sec = discovery_timeout_sec
        self._set_mode_timeout_sec = set_mode_timeout_sec
        self._deserialize_timeout_sec = deserialize_timeout_sec
        self._set_parameters_timeout_sec = set_parameters_timeout_sec
        self._lock = threading.Lock()
        self._node: Any = None
        self._executor: Any = None
        self._thread: threading.Thread | None = None
        self._owns_rclpy_context = False
        self._set_mode_client: Any = None
        self._deserialize_client: Any = None
        self._set_bool_type: Any = None
        self._deserialize_type: Any = None
        self._pose_type: Any = None
        # 노드마다 클라이언트가 따로 필요하다(/planner_server, /controller_server).
        # 어느 노드를 쓸지는 MODE_PROFILES 가 정하므로 지연 생성한다.
        self._parameter_clients: dict[str, Any] = {}
        self._set_parameters_type: Any = None
        self._parameter_type: Any = None
        self._parameter_value_type: Any = None
        self._parameter_type_ids: Any = None

    def start(self) -> None:
        with self._lock:
            if self._node is not None:
                return
            import rclpy
            from geometry_msgs.msg import Pose2D
            from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
            from rcl_interfaces.srv import SetParameters
            from rclpy.executors import SingleThreadedExecutor
            from slam_toolbox.srv import DeserializePoseGraph
            from std_srvs.srv import SetBool

            self._set_bool_type = SetBool
            self._deserialize_type = DeserializePoseGraph
            self._pose_type = Pose2D
            self._set_parameters_type = SetParameters
            self._parameter_type = Parameter
            self._parameter_value_type = ParameterValue
            self._parameter_type_ids = ParameterType

            self._owns_rclpy_context = not rclpy.ok()
            if self._owns_rclpy_context:
                rclpy.init(args=None)
            self._node = rclpy.create_node(self._node_name)
            self._set_mode_client = self._node.create_client(
                SetBool, self._set_mode_service
            )
            self._deserialize_client = self._node.create_client(
                DeserializePoseGraph, self._deserialize_service
            )
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._thread = threading.Thread(
                target=self._executor.spin,
                name="ros-localization-mode",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if self._executor is not None:
                self._executor.shutdown()
            if self._node is not None:
                self._node.destroy_node()
            if self._owns_rclpy_context:
                import rclpy

                if rclpy.ok():
                    rclpy.shutdown()
            self._node = None
            self._executor = None
            self._thread = None
            # 노드를 파괴하면 그 노드가 만든 클라이언트도 죽는다. 남겨 두면
            # 다음 start() 가 죽은 클라이언트를 재사용한다.
            self._parameter_clients.clear()

    def set_localization_mode(self, localization: bool) -> None:
        request = self._set_bool_type.Request()
        request.data = bool(localization)
        self._invoke(
            self._set_mode_client,
            request,
            self._set_mode_service,
            self._set_mode_timeout_sec,
        )

    def deserialize_map(
        self,
        filename: str,
        match_type: int,
        initial_pose: DockPose,
    ) -> None:
        request = self._deserialize_type.Request()
        request.filename = filename
        request.match_type = int(match_type)
        pose = self._pose_type()
        pose.x = float(initial_pose.x)
        pose.y = float(initial_pose.y)
        pose.theta = float(initial_pose.theta)
        request.initial_pose = pose
        self._invoke(
            self._deserialize_client,
            request,
            self._deserialize_service,
            self._deserialize_timeout_sec,
        )

    def set_node_parameters(
        self,
        node_name: str,
        values: Mapping[str, object],
    ) -> None:
        """Nav2 노드에 파라미터를 실행 중 주입한다.

        SetParameters 응답에는 ``success`` 가 없다. 요청마다 결과 배열이
        따로 오고 거부는 그 안의 ``successful`` 로만 나타난다. ``_invoke``
        의 일반 검사로는 걸리지 않으므로 여기서 직접 본다.
        """

        client = self._parameter_client(node_name)
        request = self._set_parameters_type.Request()
        request.parameters = [
            self._parameter_message(name, value) for name, value in values.items()
        ]
        service = f"{node_name}/set_parameters"
        response = self._invoke(
            client, request, service, self._set_parameters_timeout_sec
        )
        results = list(getattr(response, "results", []))
        if len(results) != len(request.parameters):
            raise ServiceCallFailed(
                f"{service} returned {len(results)} results for "
                f"{len(request.parameters)} parameters"
            )
        for parameter, result in zip(request.parameters, results):
            if not getattr(result, "successful", False):
                detail = getattr(result, "reason", "") or "no reason"
                raise ServiceCallFailed(
                    f"{service} rejected {parameter.name}: {detail}"
                )

    def _parameter_client(self, node_name: str) -> Any:
        with self._lock:
            if self._node is None:
                raise ServiceCallFailed(
                    f"{node_name}/set_parameters transport is not started"
                )
            client = self._parameter_clients.get(node_name)
            if client is None:
                client = self._node.create_client(
                    self._set_parameters_type, f"{node_name}/set_parameters"
                )
                self._parameter_clients[node_name] = client
            return client

    def _parameter_message(self, name: str, value: object) -> Any:
        parameter = self._parameter_type()
        parameter.name = name
        parameter_value = self._parameter_value_type()
        # bool 을 int 보다 먼저 본다. 파이썬에서 bool 은 int 의 하위형이라
        # 순서를 뒤집으면 cache_obstacle_heuristic 이 정수로 전송되고
        # Nav2 가 형 불일치로 거부한다.
        if isinstance(value, bool):
            parameter_value.type = self._parameter_type_ids.PARAMETER_BOOL
            parameter_value.bool_value = value
        elif isinstance(value, int):
            parameter_value.type = self._parameter_type_ids.PARAMETER_INTEGER
            parameter_value.integer_value = value
        elif isinstance(value, float):
            parameter_value.type = self._parameter_type_ids.PARAMETER_DOUBLE
            parameter_value.double_value = value
        elif isinstance(value, str):
            parameter_value.type = self._parameter_type_ids.PARAMETER_STRING
            parameter_value.string_value = value
        else:
            raise ServiceCallFailed(
                f"unsupported parameter type for {name}: {type(value).__name__}"
            )
        parameter.value = parameter_value
        return parameter

    def _invoke(
        self,
        client: Any,
        request: Any,
        description: str,
        timeout_sec: float,
    ) -> Any:
        if client is None:
            raise ServiceCallFailed(f"{description} transport is not started")
        if not client.wait_for_service(timeout_sec=self._discovery_timeout_sec):
            raise ServiceCallFailed(f"{description} is not available")
        return wait_for_response(
            client.call_async(request),
            timeout_sec=timeout_sec,
            description=description,
        )
