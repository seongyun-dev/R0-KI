"""
Jetson 내부 공용 로봇 상태 저장소.

각 장치 모듈은 자신이 담당하는 값만 갱신한다.

예:
- Serial Reader: 배터리, 모터, 라인센서
- Localization: x, y, heading
- Camera Monitor: 카메라 상태
- LiDAR Monitor: LiDAR 상태
- Obstacle Detector: 장애물 상태

MQTT Publisher는 이 저장소의 값을 읽기만 한다.
"""

from __future__ import annotations

import threading
from dataclasses import replace

from backend_state.models import (
    HardwareState,
    ObstacleState,
    PoseState,
    RobotStateSnapshot,
    RobotStatusState,
)


class RobotStateStore:
    """
    여러 스레드에서 안전하게 사용할 수 있는
    최신 로봇 상태 저장소.
    """

    def __init__(self) -> None:
        # Serial, ROS2, MQTT 스레드가 동시에 접근할 수 있으므로
        # Lock으로 읽기와 쓰기를 보호한다.
        self._lock = threading.Lock()

        # 실제 Localization 값을 받기 전에는
        # Pose가 존재하지 않는 것으로 처리한다.
        #
        # 가짜 좌표 0, 0, 0을 발행하지 않기 위함이다.
        self._pose: PoseState | None = None

        self._status = RobotStatusState()

        # 기본 DISCONNECTED 값과 ESP32가 실제로 보고한 DISCONNECTED를
        # 구분한다. MQTT는 최초 실제 보고 전까지 status를 발행하지 않는다.
        self._hardware_status_received = False

        # Status에 변화가 발생했는지 표시한다.
        #
        # True인 경우 정기 발행 시각을 기다리지 않고
        # Status를 즉시 발행할 수 있다.
        self._status_changed = False

    def update_hardware(
        self,
        hardware: HardwareState,
    ) -> None:
        """
        ESP32 장비 상태를 저장한다.

        이 함수는 ESP32가 담당하는 필드만 수정한다.
        카메라, LiDAR, 장애물 상태는 건드리지 않는다.
        """

        with self._lock:
            self._hardware_status_received = True
            updated_status = replace(
                self._status,
                battery=hardware.battery,
                motor=hardware.motor,
                line_sensor=hardware.line_sensor,
            )

            self._set_status_if_changed(updated_status)

    def update_robot_state(
        self,
        state: str,
    ) -> None:
        """
        로봇 전체 운행 상태를 수정한다.

        예:
        - IDLE
        - PATROLLING
        - ERROR

        장애물 정지는 로봇 운행 상태가 아니라
        obstacle.status 값으로 별도 관리한다.
        """

        with self._lock:
            updated_status = replace(
                self._status,
                state=state,
            )

            self._set_status_if_changed(updated_status)

    def update_camera_status(
        self,
        camera_status: str,
    ) -> None:
        """카메라 장치 상태만 수정한다."""

        with self._lock:
            updated_status = replace(
                self._status,
                camera=camera_status,
            )

            self._set_status_if_changed(updated_status)

    def update_lidar_status(
        self,
        lidar_status: str,
    ) -> None:
        """LiDAR 장치 상태만 수정한다."""

        with self._lock:
            updated_status = replace(
                self._status,
                lidar=lidar_status,
            )

            self._set_status_if_changed(updated_status)

    def update_obstacle(
        self,
        obstacle: ObstacleState,
    ) -> None:
        """
        장애물 감지 결과만 수정한다.

        장애물이 감지되어도 robot state는 변경하지 않는다.

        실제 모터 정지는 Jetson 내부 제어 경로에서
        즉시 수행하고, 서버에는 obstacle.status로 보고한다.
        """

        with self._lock:
            updated_status = replace(
                self._status,
                obstacle=obstacle,
            )

            self._set_status_if_changed(updated_status)

    def update_pose(
        self,
        pose: PoseState,
    ) -> None:
        """Localization에서 받은 최신 Pose를 저장한다."""

        with self._lock:
            self._pose = pose

    def get_pose(self) -> PoseState | None:
        """
        최신 Pose를 반환한다.

        데이터 모델이 frozen dataclass이므로
        외부에서 내부 상태를 직접 변경할 수 없다.
        """

        with self._lock:
            return self._pose

    def get_status(self) -> RobotStatusState:
        """최신 전체 로봇 상태를 반환한다."""

        with self._lock:
            return self._status

    def has_hardware_status(self) -> bool:
        """ESP32의 실제 장비 상태를 한 번 이상 수신했는지 반환한다."""

        with self._lock:
            return self._hardware_status_received

    def get_snapshot(self) -> RobotStateSnapshot:
        """
        현재 로봇의 Status와 Pose를 한 번에 반환한다.

        하나의 Lock 안에서 두 값을 함께 읽기 때문에
        동일한 시점의 일관된 상태를 조회할 수 있다.
        """

        with self._lock:
            return RobotStateSnapshot(
                status=self._status,
                pose=self._pose,
            )

    def has_status_changed(self) -> bool:
        """마지막 발행 이후 Status 변경 여부를 반환한다."""

        with self._lock:
            return self._status_changed

    def mark_status_published(self) -> None:
        """
        Status 발행 완료 상태로 표시한다.

        이후 다른 값이 변경되기 전까지는
        즉시 발행 대상이 아니다.
        """

        with self._lock:
            self._status_changed = False

    def _set_status_if_changed(
        self,
        updated_status: RobotStatusState,
    ) -> None:
        """
        실제 값이 달라진 경우에만 상태를 저장한다.

        호출하는 쪽에서 이미 Lock을 획득한 상태여야 한다.
        """

        if updated_status == self._status:
            return

        self._status = updated_status
        self._status_changed = True
