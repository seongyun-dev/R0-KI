"""
MQTT Payload 생성 모듈.

이 파일은 내부 상태 객체를
팀 MQTT 명세에 맞는 dict로 변환한다.

MQTT Broker에 연결하거나 메시지를 발행하지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from state.models import (
    PoseState,
    RobotStatusState,
)


KOREA_TIMEZONE = ZoneInfo("Asia/Seoul")


def create_timestamp() -> str:
    """
    한국 시간 기준 ISO 8601 timestamp를 생성한다.

    예:
    2026-07-27T14:30:00+09:00
    """

    return datetime.now(
        KOREA_TIMEZONE
    ).isoformat(timespec="seconds")


def build_pose_payload(
    *,
    schema_version: int,
    robot_key: str,
    pose: PoseState,
) -> dict[str, Any]:
    """
    내부 PoseState를 MQTT Pose Payload로 변환한다.

    데이터 변환만 담당하며 MQTT 발행은 하지 않는다.
    """

    return {
        "schemaVersion": schema_version,
        "robotKey": robot_key,
        "x": round(pose.x, 3),
        "y": round(pose.y, 3),
        "heading": round(pose.heading, 1),
        "timestamp": create_timestamp(),
    }


def build_status_payload(
    *,
    schema_version: int,
    robot_key: str,
    status: RobotStatusState,
) -> dict[str, Any]:
    """
    내부 RobotStatusState를
    MQTT Status Payload로 변환한다.

    팀 명세에 없는 필드는 절대 추가하지 않는다.
    """

    return {
        "schemaVersion": schema_version,
        "robotKey": robot_key,
        "battery": status.battery,
        "state": status.state,
        "motor": status.motor,
        "camera": status.camera,
        "lidar": status.lidar,
        "lineSensor": status.line_sensor,
        "obstacle": {
            "status": status.obstacle.status,
            "direction": status.obstacle.direction,
            "reasonMessage": (
                status.obstacle.reason_message
            ),
        },
        "timestamp": create_timestamp(),
    }
