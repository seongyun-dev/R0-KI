#!/usr/bin/env python3
"""ROS2 장애물 정보를 기존 MQTT 로봇 상태 Payload에 결합한다."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


# /home/e103/roki를 Python import 경로에 추가한다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mqtt.publisher import RobotStatusPublisher  # noqa: E402


def current_timestamp() -> str:
    """현재 Jetson 로컬 시각을 ISO 8601 형식으로 반환한다."""

    return datetime.now().astimezone().isoformat(
        timespec="milliseconds"
    )


class RokiStatusMqttNode(Node):
    """ROS2 장애물 정보를 받아 MQTT status로 전송한다."""

    OBSTACLE_INFO_TOPIC = "/roki/obstacle_info"
    STATUS_PUBLISH_INTERVAL_SEC = 3.0

    def __init__(self) -> None:
        super().__init__("roki_status_mqtt_bridge")

        self._status_publisher = RobotStatusPublisher(
            robot_key="ROKI-01"
        )

        # 장애물이 없는 초기 상태에서도 obstacle 객체를 유지한다.
        self._latest_obstacle: dict[str, Any] = {
            "status": "CLEAR",
            "reasonMessage": "전방 주행 경로가 확보되었습니다.",
            "stateChangedAt": current_timestamp(),
        }

        # 현재 실제 센서 연결 전까지 사용할 기본 상태값이다.
        self._battery_percent = 100.0
        self._robot_state = "IDLE"
        self._motor_status = "NORMAL"
        self._camera_status = "NORMAL"
        self._lidar_status = "NORMAL"
        self._line_sensor_status = "NORMAL"

        self._obstacle_subscription = self.create_subscription(
            String,
            self.OBSTACLE_INFO_TOPIC,
            self._obstacle_callback,
            10,
        )

        self._status_timer = self.create_timer(
            self.STATUS_PUBLISH_INTERVAL_SEC,
            self._publish_status,
        )

        self._connect_mqtt()

        self.get_logger().info(
            "RO-KI ROS2 → MQTT 상태 브리지를 시작합니다."
        )
        self.get_logger().info(
            f"ROS2 구독 토픽: {self.OBSTACLE_INFO_TOPIC}"
        )
        self.get_logger().info(
            f"MQTT 상태 토픽: {self._status_publisher.topic}"
        )
        self.get_logger().info(
            f"상태 전송 주기: "
            f"{self.STATUS_PUBLISH_INTERVAL_SEC:.1f}초"
        )

    def _connect_mqtt(self) -> None:
        """MQTT Broker에 연결한다."""

        try:
            self._status_publisher.connect()
        except Exception as exc:
            self.get_logger().fatal(
                f"MQTT Broker 연결에 실패했습니다: {exc}"
            )
            raise

        self.get_logger().info(
            "MQTT Broker 연결이 완료되었습니다."
        )

    def _obstacle_callback(self, message: String) -> None:
        """장애물 감지 노드에서 전달된 최신 상태를 저장한다."""

        try:
            received_payload = json.loads(message.data)
        except json.JSONDecodeError as exc:
            self.get_logger().error(
                f"장애물 JSON 해석에 실패했습니다: {exc}"
            )
            return

        obstacle_status = received_payload.get("status")

        if obstacle_status not in {"STOP", "CLEAR"}:
            self.get_logger().warning(
                "지원하지 않는 obstacle.status입니다: "
                f"{obstacle_status}"
            )
            return

        self._latest_obstacle = {
            "status": obstacle_status,
            "reasonMessage": received_payload.get(
                "reasonMessage",
                (
                    "장애물이 감지되어 정지했습니다."
                    if obstacle_status == "STOP"
                    else "전방 주행 경로가 확보되었습니다."
                ),
            ),
            "stateChangedAt": received_payload.get(
                "stateChangedAt",
                current_timestamp(),
            ),
        }

        self.get_logger().info(
            "장애물 상태 수신 | "
            f"status={self._latest_obstacle['status']} | "
            f"stateChangedAt="
            f"{self._latest_obstacle['stateChangedAt']}"
        )

    def _publish_status(self) -> None:
        """현재 상태를 MQTT status 토픽으로 주기적으로 발행한다."""

        try:
            payload = self._status_publisher.publish_status(
                battery_percent=self._battery_percent,
                state=self._robot_state,
                motor_status=self._motor_status,
                camera_status=self._camera_status,
                lidar_status=self._lidar_status,
                line_sensor_status=self._line_sensor_status,
                obstacle=self._latest_obstacle,
            )
        except Exception as exc:
            self.get_logger().error(
                f"MQTT 상태 발행에 실패했습니다: {exc}"
            )
            return

        self.get_logger().info(
            "MQTT 상태 발행 완료 | "
            f"state={payload['state']} | "
            f"obstacle={payload['obstacle']['status']} | "
            f"timestamp={payload['timestamp']}"
        )

    def destroy_node(self) -> bool:
        """노드 종료 시 MQTT 연결도 함께 정리한다."""

        try:
            self._status_publisher.disconnect()
        except Exception as exc:
            self.get_logger().warning(
                f"MQTT 연결 종료 중 오류가 발생했습니다: {exc}"
            )

        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)

    node: RokiStatusMqttNode | None = None

    try:
        node = RokiStatusMqttNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        if node is not None:
            node.get_logger().info(
                "RO-KI 상태 브리지를 종료합니다."
            )
    except Exception as exc:
        if node is not None:
            node.get_logger().fatal(
                f"상태 브리지 실행 중 오류가 발생했습니다: {exc}"
            )
        else:
            print(
                f"상태 브리지 초기화 중 오류가 발생했습니다: {exc}",
                file=sys.stderr,
            )
    finally:
        if node is not None:
            node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
