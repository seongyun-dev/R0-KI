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
from dataclasses import dataclass
from typing import Callable, Protocol

# slam_toolbox/srv/DeserializePoseGraph 의 match_type.
# 저장된 그래프를 주어진 포즈 근처에서 위치추정 시작점으로 삼는다.
LOCALIZE_AT_POSE = 3


@dataclass(frozen=True)
class DockPose:
    """지도 좌표계에서 본 도킹 지점. 위치추정의 초기 추정값이다."""

    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0


class ModeTransport(Protocol):
    """slam_toolbox 서비스 두 개로 좁힌 전송 경계."""

    def set_localization_mode(self, localization: bool) -> None:
        """실패하면 예외를 던진다. 조용히 실패하면 안 된다."""

    def deserialize_map(
        self,
        filename: str,
        match_type: int,
        initial_pose: DockPose,
    ) -> None:
        """실패하면 예외를 던진다."""


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
        report: Callable[[str], None] | None = None,
    ) -> None:
        self._transport = transport
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
        with self._lock:
            self._mode = self.MAPPING
            self._patrol_arguments = None
        self._say("mode=mapping")
        return True, "READY"

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
        pose = dock_pose or DockPose()
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
        with self._lock:
            self._mode = self.PATROL
            self._patrol_arguments = (posegraph_path, pose)
        self._say(f"mode=patrol posegraph={posegraph_path}")
        return True, "READY"

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
