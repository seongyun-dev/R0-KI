"""MQTT로 전송하는 로봇 관제 데이터 모델.

이 모듈은 MQTT payload의 구조를 정의한다.
응급 상황과 일반 탐지 이벤트는 REST API로 전송하므로 포함하지 않는다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    """현재 UTC 시각을 ISO 8601 문자열로 반환한다."""

    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RobotLocation:
    """실시간 로봇 위치 데이터."""

    robot_id: str
    x: float
    y: float
    heading: float
    timestamp: str

    @classmethod
    def create(
        cls,
        *,
        robot_id: str,
        x: float,
        y: float,
        heading: float,
    ) -> "RobotLocation":
        """현재 시각을 포함한 위치 데이터를 생성한다."""

        return cls(
            robot_id=robot_id,
            x=float(x),
            y=float(y),
            heading=float(heading),
            timestamp=utc_now_iso(),
        )

    def to_dict(self) -> dict[str, Any]:
        """MQTT JSON 변환에 사용할 딕셔너리를 반환한다."""

        return asdict(self)


@dataclass(frozen=True)
class RobotStatus:
    """실시간 로봇 장치 상태 데이터."""

    robot_id: str
    camera_status: str
    battery_percent: int
    motor_status: str
    timestamp: str

    @classmethod
    def create(
        cls,
        *,
        robot_id: str,
        camera_status: str,
        battery_percent: int,
        motor_status: str,
    ) -> "RobotStatus":
        """현재 시각을 포함한 상태 데이터를 생성한다."""

        if not 0 <= battery_percent <= 100:
            raise ValueError("battery_percent must be between 0 and 100")

        return cls(
            robot_id=robot_id,
            camera_status=camera_status,
            battery_percent=battery_percent,
            motor_status=motor_status,
            timestamp=utc_now_iso(),
        )

    def to_dict(self) -> dict[str, Any]:
        """MQTT JSON 변환에 사용할 딕셔너리를 반환한다."""

        return asdict(self)
