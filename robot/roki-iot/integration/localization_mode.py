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
from typing import Any, Callable, Mapping, Protocol, Sequence

from aiot_robot.ros_config import (
    GOAL_CHECKER_PROFILE_IDS,
    MODE_PROFILES,
    PLANNER_PROFILE_IDS,
)

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
    """slam_toolbox 서비스 두 개와 Nav2 상태 조회로 좁힌 전송 경계.

    파라미터를 **쓰는** 경로는 일부러 없다. 2026-08-08 실측으로
    ``/planner_server`` 에 SetParameters 를 하면 노드가 23~29초 블록되고,
    4초 bond heartbeat 를 놓쳐 Nav2 스택 전체가 내려가는 것이 확인됐다.
    운행별 값은 기동 시 인스턴스별로 올라가고(MappingGridBased /
    PatrolGridBased) BT 가 goal 마다 고른다. 여기서는 읽어서 확인만 한다.
    """

    def set_localization_mode(self, localization: bool) -> None:
        """실패하면 예외를 던진다. 조용히 실패하면 안 된다."""

    def deserialize_map(
        self,
        filename: str,
        match_type: int,
        initial_pose: DockPose,
    ) -> None:
        """실패하면 예외를 던진다."""

    def get_node_parameters(
        self,
        node_name: str,
        names: Sequence[str],
    ) -> Mapping[str, object]:
        """현재 값을 돌려준다. 조회가 불완전하면 실패해야 한다."""

    def get_lifecycle_state(self, node_name: str) -> str:
        """Return the lifecycle state label; raise when it cannot be read."""


def _profile_value_matches(current: object, requested: object) -> bool:
    """ROS 파라미터의 값과 타입이 모두 같은지 본다.

    Python에서는 ``True == 1`` 이므로 값만 비교하면 bool/int 타입 오류를
    놓친다. profile에는 bool, int, float, str만 허용되므로 타입까지 확인한다.
    """

    if isinstance(requested, bool):
        return isinstance(current, bool) and current is requested
    if isinstance(requested, float):
        return (
            isinstance(current, float)
            and not isinstance(current, bool)
            and current == requested
        )
    return type(current) is type(requested) and current == requested


class LocalizationModeController:
    """매핑/순찰 모드를 서비스 호출로 전환한다.

    호출자는 두 가지만 알면 된다: ``enter_mapping`` 과 ``enter_patrol``.
    순서와 실패 처리는 여기가 책임진다.
    """

    MAPPING = "mapping"
    PATROL = "patrol"
    MAPPING_NAV2_NODES = (
        "/planner_server",
        "/controller_server",
        "/bt_navigator",
    )

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
        # 운행별 Nav2 값의 기준표. 주입하지 않고 검증에만 쓴다 -- 값은 기동 시
        # MappingGridBased / PatrolGridBased 인스턴스에 이미 올라와 있고, BT 가
        # goal 마다 고른다. 기본값을 두는 이유는 검증 기준이 코드와 한곳에서
        # 나와야 하기 때문이다(ros_config.MODE_PROFILES).
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
            already_mapping = self._mode == self.MAPPING
        if already_mapping:
            ready, reason = self._mapping_readiness()
            return (True, "ALREADY_MAPPING") if ready else (False, reason)
        try:
            self._transport.set_localization_mode(False)
        except Exception as exc:
            # 모드를 미확정으로 남긴다. 다음 요청이 다시 전송하도록.
            self._invalidate()
            self._say(f"mode switch to mapping failed type={type(exc).__name__}")
            return False, "SET_MAPPING_MODE_FAILED"
        # 렌더된 파일은 이미 매핑 값을 담는다. 같은 값을 SetParameters 로 다시
        # 보내면 SmacPlannerHybrid 가 휴리스틱 테이블을 동기적으로 재생성하고,
        # 그동안 planner_server bond heartbeat 가 끊겨 Nav2 전체가 내려간다.
        # mapping START 에서는 현재 값을 읽어 기록만 한다. 막지 않는 이유는
        # _report_mode_profile 주석 참고 -- 값이 런타임에 바뀔 경로가 없고,
        # 여기서 막으면 /planner_server 가 응답 못 하는 동안 매핑 자체가 선다.
        # Nav2 가 실제로 살아 있는지는 바로 아래 _mapping_readiness 가 본다.
        self._report_mode_profile(self.MAPPING)
        ready, readiness_reason = self._mapping_readiness()
        if not ready:
            self._invalidate()
            return False, readiness_reason
        with self._lock:
            self._mode = self.MAPPING
            self._patrol_arguments = None
        self._say("mode=mapping")
        return True, "READY"

    def _mapping_readiness(self) -> tuple[bool, str]:
        """Require responsive, active Nav2 servers before mapping is ACK-ready."""

        for node_name in self.MAPPING_NAV2_NODES:
            try:
                state = self._transport.get_lifecycle_state(node_name)
            except Exception as exc:
                self._say(
                    f"lifecycle read failed node={node_name} "
                    f"type={type(exc).__name__}"
                )
                return False, "NAV2_NOT_READY"
            if state.strip().lower() != "active":
                self._say(f"lifecycle not active node={node_name} state={state}")
                return False, "NAV2_NOT_READY"
        return True, "READY"

    @staticmethod
    def _profile_instance_names(
        mode: str, node_name: str, expected: Mapping[str, object]
    ) -> dict[str, str]:
        """프로필 키를 그 운행의 BT 가 실제로 부르는 인스턴스로 옮긴다.

        ``MODE_PROFILES`` 는 두 운행을 ``GridBased.`` /
        ``general_goal_checker.`` 라는 같은 접두사로 적어둔다 -- 그래야 두
        프로필이 같은 항목을 덮는지 한눈에 대조된다. 실제 인스턴스는
        ``apply_slam_shape`` 이 그 표를 deepcopy 해서 만들고
        (MappingGridBased / PatrolGridBased, mapping_goal_checker /
        patrol_goal_checker), BT 가 goal 마다 planner_id / goal_checker_id 로
        고른다.

        그래서 접두사 그대로 조회하면 아무도 부르지 않는 기준 인스턴스를 읽게
        된다. 값이 우연히 맞아도 그 검증은 주행과 무관하다.
        """

        identifiers = (
            PLANNER_PROFILE_IDS
            if node_name == "/planner_server"
            else GOAL_CHECKER_PROFILE_IDS
        )
        instance = identifiers.get(mode)
        if instance is None:
            return {name: name for name in expected}
        return {
            name: f"{instance}.{name.partition('.')[2]}" for name in expected
        }

    def _report_mode_profile(self, mode: str) -> None:
        """활성 Nav2 프로필을 읽어 기록한다. **막지 않는다.**

        2026-08-08 13:10(4cb2422)에 이 검사를 넣을 때는 전환이 SetParameters
        주입이었고, 주입이 실패하면 순찰이 매핑 값(REEDS_SHEPP / yaw 3.15)으로
        달리므로 fail-close 가 옳았다.

        그 위험은 인스턴스 분리로 사라졌다(adb91d6). 지금은 두 운행 값이
        기동 시 각자의 플러그인 인스턴스로 올라오고(ros_config.apply_slam_shape
        -> _preload_nav2_mode_plugins) BT 가 goal 마다 planner_id /
        goal_checker_id 로 고른다. 실행 중에 이 값을 바꾸는 코드 경로가 없다
        -- 쓰기 경로를 전송 경계에서 제거했다. 값이 틀릴 수 있는 경우는 렌더된
        launch 파일이 틀렸을 때뿐이고, 그것은 순찰마다가 아니라 기동 시점의
        속성이다.

        그런데 이 검사가 fail-close 로 남아 매핑과 순찰을 둘 다 세우고 있었다.
        2026-08-09 01:15~01:34 실측: /planner_server 가 map 프레임을 기다리며
        코스트맵 TF 루프에 갇혀 GetParameters 에 응답하지 않고, 그 map 프레임은
        스캔 게이트가 열려야 생기는데 게이트를 여는 단계가 이 검사 **뒤**에
        있다. START_PATROL 과 START_MAPPING 이 함께 막혔다.

        막을 이유가 사라진 위험을 계속 막으면서 두 운행을 세우는 것은 남는
        장사가 아니다. 관측은 유지한다 -- 불일치가 생기면 그 사실은 여전히
        알아야 하고, 로그가 그것을 남긴다.
        """

        profile = self._profiles.get(mode)
        if not profile:
            return
        for node_name, expected in profile.items():
            names = self._profile_instance_names(mode, node_name, expected)
            try:
                current = self._transport.get_node_parameters(
                    node_name, tuple(names.values())
                )
                current = {
                    name: current[names[name]]
                    for name in expected
                    if names[name] in current
                }
                if set(current) != set(expected):
                    raise RuntimeError("parameter query returned incomplete values")
            except Exception as exc:
                self._say(
                    f"profile read failed mode={mode} node={node_name} "
                    f"type={type(exc).__name__}  <- 관측만 실패. 운행은 진행한다"
                )
                continue

            mismatched = [
                names[name]
                for name, value in expected.items()
                if not _profile_value_matches(current[name], value)
            ]
            if mismatched:
                # 인스턴스 이름을 그대로 찍는다. 어느 플러그인이 어긋났는지
                # 모르면 로그를 보고도 어디를 고쳐야 할지 알 수 없다.
                self._say(
                    f"profile mismatch mode={mode} node={node_name} "
                    f"parameters={','.join(mismatched)}  <- launch 파일 확인 필요"
                )
                continue
        self._say(f"profile verified mode={mode}")

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
        # 순찰도 매핑과 같이 주입하지 않고 읽어서 대조한다.
        #
        # 2026-08-08 실측: /planner_server 에 SetParameters 를 하면 노드가
        # 23~29초 블록되고, 4초 bond heartbeat 를 놓쳐 Nav2 스택 전체가
        # 내려간다. 매핑 쪽은 이미 검증으로 바꿨는데 순찰만 주입으로 남아
        # 있어서, 순찰을 시작하는 순간 Nav2 가 죽는 상태였다.
        #
        # 그리고 주입할 이유도 사라졌다. planner_plugins 가
        # [GridBased, MappingGridBased, PatrolGridBased] 로 나뉘고 BT 가
        # goal 마다 PatrolGridBased 를 고르므로, 순찰 값은 기동 시점에 이미
        # 제자리에 있다. 남은 일은 그것이 맞는지 확인하는 것뿐이다.
        #
        # 대조는 하되 막지는 않는다(_report_mode_profile 주석 참고). 여기서
        # 막으면 /planner_server 가 map 프레임을 기다리는 동안 순찰이 서고,
        # 그 map 프레임은 이 함수가 성공해야 열리는 스캔 게이트에서 나온다 --
        # 서로를 기다린다. 2026-08-09 01:15 실측.
        self._report_mode_profile(self.PATROL)
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
        # 그래프는 그대로 두되 프로필은 다시 기록한다. 생애주기 복구가 launch
        # 파일을 다시 읽었을 수 있으니 관측 가치는 남아 있다. 막지는 않는다.
        self._report_mode_profile(self.PATROL)
        return True, "ALREADY_PATROL"

    def note_lifecycle_recovery(self, detail: str = "") -> None:
        """생애주기 관리자가 스택을 복구했음을 기록만 한다.

        복구는 configure 를 다시 돌리고, 그 configure 가 launch 시점 파라미터
        파일을 다시 읽는다. 예전에는 그 파일에 매핑 값만 있고 순찰 값은 실행
        중 주입이었으므로, **순찰 중 복구가 순찰을 조용히 매핑으로 되돌렸다**
        -- REEDS_SHEPP 과 yaw 3.15 로 돌아가 후진하고 아무 방향으로나 도착
        판정을 했다. 지금은 두 운행 값이 각자의 플러그인 인스턴스로 그 파일에
        박혀 있어(ros_config.apply_slam_shape) 복구가 무엇도 잃지 않는다.

        그래도 기록은 남긴다. 복구 자체가 bond 끊김의 신호이고, 그 빈도는
        아직 재본 적이 없다. 파라미터 손실은 사라졌지만 복구 중 목표가
        취소되는 것은 그대로다.
        """

        with self._lock:
            mode = self._mode
        self._say(
            f"lifecycle recovery observed mode={mode or 'unknown'}"
            f"{' ' + detail if detail else ''}"
        )

    def reassert(self) -> tuple[bool, str]:
        """마지막으로 성립한 모드를 다시 적용한다.

        Nav2 파라미터는 이제 스스로 복구된다 -- 생애주기 관리자가 다시 읽는
        파일에 두 운행 값이 다 들어 있다. 하지만 slam_toolbox 의 위치추정
        모드와 적재된 포즈그래프는 파일이 아니라 **서비스 호출로만** 정해지는
        런타임 상태다. 그 노드가 다시 뜨면 매핑 모드에 빈 그래프로 돌아오고,
        되돌릴 방법은 같은 호출을 다시 하는 것뿐이다. 여기가 그 경로다.
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
        # 파라미터 읽기는 관측용이라 짧게 끊는다. /planner_server 가 map 프레임을
        # 기다리며 코스트맵 TF 루프에 갇히면 이 호출은 그냥 응답이 없는데,
        # 15초를 기다리면 노드당 그만큼이 START 명령의 TTL(30초)에서 빠진다.
        # 2026-08-09 01:15:41 -> 01:15:56 실측이 정확히 그 15초였다.
        parameter_query_timeout_sec: float = 3.0,
        # 생애주기 상태는 여전히 운행을 막는 판정(NAV2_NOT_READY)이라 넉넉히 준다.
        lifecycle_query_timeout_sec: float = 15.0,
    ) -> None:
        self._node_name = node_name
        self._set_mode_service = set_mode_service
        self._deserialize_service = deserialize_service
        self._discovery_timeout_sec = discovery_timeout_sec
        self._set_mode_timeout_sec = set_mode_timeout_sec
        self._deserialize_timeout_sec = deserialize_timeout_sec
        self._parameter_query_timeout_sec = parameter_query_timeout_sec
        self._lifecycle_query_timeout_sec = lifecycle_query_timeout_sec
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
        self._get_parameter_clients: dict[str, Any] = {}
        self._lifecycle_clients: dict[str, Any] = {}
        self._get_parameters_type: Any = None
        self._get_state_type: Any = None
        self._parameter_type_ids: Any = None

    def start(self) -> None:
        with self._lock:
            if self._node is not None:
                return
            import rclpy
            from geometry_msgs.msg import Pose2D
            from rcl_interfaces.msg import ParameterType
            from rcl_interfaces.srv import GetParameters
            from rclpy.executors import SingleThreadedExecutor
            from lifecycle_msgs.srv import GetState
            from slam_toolbox.srv import DeserializePoseGraph
            from std_srvs.srv import SetBool

            self._set_bool_type = SetBool
            self._deserialize_type = DeserializePoseGraph
            self._pose_type = Pose2D
            self._get_parameters_type = GetParameters
            self._get_state_type = GetState
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
            self._get_parameter_clients.clear()
            self._lifecycle_clients.clear()

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

    def get_node_parameters(
        self,
        node_name: str,
        names: Sequence[str],
    ) -> Mapping[str, object]:
        client = self._get_parameter_client(node_name)
        request = self._get_parameters_type.Request()
        request.names = list(names)
        service = f"{node_name}/get_parameters"
        response = self._invoke(
            client, request, service, self._parameter_query_timeout_sec
        )
        values = list(getattr(response, "values", []))
        if len(values) != len(request.names):
            raise ServiceCallFailed(
                f"{service} returned {len(values)} values for "
                f"{len(request.names)} parameters"
            )
        return {
            name: self._parameter_value_to_python(name, value)
            for name, value in zip(request.names, values)
        }

    def get_lifecycle_state(self, node_name: str) -> str:
        client = self._lifecycle_client(node_name)
        service = f"{node_name}/get_state"
        response = self._invoke(
            client,
            self._get_state_type.Request(),
            service,
            self._lifecycle_query_timeout_sec,
        )
        state = getattr(response, "current_state", None)
        label = str(getattr(state, "label", "") or "").strip()
        if not label:
            raise ServiceCallFailed(f"{service} returned no lifecycle label")
        return label

    def _get_parameter_client(self, node_name: str) -> Any:
        with self._lock:
            if self._node is None:
                raise ServiceCallFailed(
                    f"{node_name}/get_parameters transport is not started"
                )
            client = self._get_parameter_clients.get(node_name)
            if client is None:
                client = self._node.create_client(
                    self._get_parameters_type, f"{node_name}/get_parameters"
                )
                self._get_parameter_clients[node_name] = client
            return client

    def _lifecycle_client(self, node_name: str) -> Any:
        with self._lock:
            if self._node is None:
                raise ServiceCallFailed(
                    f"{node_name}/get_state transport is not started"
                )
            client = self._lifecycle_clients.get(node_name)
            if client is None:
                client = self._node.create_client(
                    self._get_state_type, f"{node_name}/get_state"
                )
                self._lifecycle_clients[node_name] = client
            return client

    def _parameter_value_to_python(self, name: str, value: Any) -> object:
        value_type = int(getattr(value, "type", 0))
        types = self._parameter_type_ids
        if value_type == types.PARAMETER_BOOL:
            return bool(value.bool_value)
        if value_type == types.PARAMETER_INTEGER:
            return int(value.integer_value)
        if value_type == types.PARAMETER_DOUBLE:
            return float(value.double_value)
        if value_type == types.PARAMETER_STRING:
            return str(value.string_value)
        raise ServiceCallFailed(
            f"unsupported or unset parameter type for {name}: {value_type}"
        )

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
