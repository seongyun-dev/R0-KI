"""
로봇 상태 데이터 모델.

이 파일은 로봇 내부에서 공유할 데이터의
형태만 정의한다.

MQTT 발행, Serial 통신, ROS2 구독 등의
동작은 수행하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PoseState:
    """
    지도 기준 로봇 위치.

    x, y:
        단위는 meter.

    heading:
        단위는 degree.
        0도는 map 좌표계의 +X 방향이다.
        반시계 방향을 양수로 사용한다.
    """

    x: float
    y: float
    heading: float


@dataclass(frozen=True)
class ObstacleState:
    """
    장애물 감지 결과.

    status:
        CLEAR 또는 STOP.

    direction:
        FRONT, LEFT, RIGHT, REAR, NONE.

    reason_message:
        관리자 화면에 표시할 장애물 설명.
    """

    status: str = "CLEAR"
    direction: str = "NONE"
    reason_message: str | None = None


@dataclass(frozen=True)
class HardwareState:
    """
    ESP32에서 전달받는 장비 상태.

    ESP32는 아래 값만 책임진다.

    - battery
    - motor
    - line_sensor
    """

    battery: float | None = None
    motor: str = "DISCONNECTED"
    line_sensor: str = "DISCONNECTED"


@dataclass(frozen=True)
class RobotStatusState:
    """
    Jetson이 관리하는 로봇 전체 상태.

    ESP32 장비 상태와 Jetson 장치 상태,
    장애물 상태를 하나의 객체로 묶는다.
    """

    battery: float | None = None
    state: str = "IDLE"

    motor: str = "DISCONNECTED"
    camera: str = "DISCONNECTED"
    lidar: str = "DISCONNECTED"
    line_sensor: str = "DISCONNECTED"

    obstacle: ObstacleState = field(
        default_factory=ObstacleState
    )


@dataclass(frozen=True)
class RobotStateSnapshot:
    """
    특정 시점의 로봇 전체 상태 복사본.

    status:
        배터리, 모터, 카메라, LiDAR,
        라인센서, 운행 상태, 장애물 상태.

    pose:
        Localization에서 실제 위치를 받기 전에는 None.
    """

    status: RobotStatusState
    pose: PoseState | None
