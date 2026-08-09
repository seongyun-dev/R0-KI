"""RO-KI 로봇 상태 MQTT Payload 생성 및 발행 모듈."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from mqtt.client import MqttClient
from mqtt.config import load_mqtt_config
from mqtt.topics import STATUS_TOPIC


def current_timestamp() -> str:
    """현재 Jetson 로컬 시각을 ISO 8601 형식으로 반환한다."""

    return datetime.now().astimezone().isoformat(
        timespec="milliseconds"
    )


class RobotStatusPublisher:
    """로봇 상태를 기존 MQTT status 토픽으로 발행한다."""

    def __init__(
        self,
        *,
        robot_key: str = "ROKI-01",
    ) -> None:
        self._robot_key = robot_key

        mqtt_config = load_mqtt_config()
        self._mqtt_client = MqttClient(mqtt_config)

    @property
    def topic(self) -> str:
        """현재 사용하는 MQTT 상태 토픽을 반환한다."""

        return STATUS_TOPIC

    def connect(self) -> None:
        """MQTT Broker에 연결한다."""

        self._mqtt_client.connect()

    def disconnect(self) -> None:
        """MQTT Broker 연결을 종료한다."""

        self._mqtt_client.disconnect()

    def publish_status(
        self,
        *,
        battery_percent: float,
        state: str,
        motor_status: str,
        camera_status: str,
        lidar_status: str,
        line_sensor_status: str,
        obstacle: dict[str, Any],
    ) -> dict[str, Any]:
        """현재 로봇 상태와 장애물 정보를 하나의 Payload로 발행한다."""

        payload: dict[str, Any] = {
            "schemaVersion": 1,
            "robotKey": self._robot_key,
            "battery": round(float(battery_percent), 1),
            "state": state,
            "motor": motor_status,
            "camera": camera_status,
            "lidar": lidar_status,
            "lineSensor": line_sensor_status,
            "obstacle": {
                "status": obstacle.get("status", "CLEAR"),
                "reasonMessage": obstacle.get(
                    "reasonMessage",
                    "전방 주행 경로가 확보되었습니다.",
                ),
                "stateChangedAt": obstacle.get(
                    "stateChangedAt",
                    current_timestamp(),
                ),
            },
            # MQTT 메시지를 보낼 때마다 새로 갱신된다.
            "timestamp": current_timestamp(),
        }

        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        self._mqtt_client.publish(
            topic=self.topic,
            payload=payload_json,
            retain=False,
        )

        return payload
