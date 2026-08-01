"""
MQTT command 수신 처리 모듈.

책임:
1. command payload 검증
2. START_PATROL / STOP_PATROL / SET_TOKEN 분기
3. ESP32 Serial 명령 전달
4. YOLO 파이프라인 기동/중지
5. command/ack 발행

MQTT 연결 자체는 MqttClient가 담당한다.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from config.settings import AppSettings
from mqtt.client import MqttClient
from pipeline.patrol_pipeline import PatrolPipelineRunner
from serial_reader import ESP32SerialReader
from state.robot_state_store import RobotStateStore

SEOUL = ZoneInfo("Asia/Seoul")

TOKEN_FILE_PATH = (
    Path(__file__).resolve().parents[1]
    / "runtime"
    / "robot_service_token"
)


class PatrolCommandHandler:
    """로봇 MQTT command를 처리한다."""

    def __init__(
        self,
        *,
        settings: AppSettings,
        mqtt_client: MqttClient,
        serial_reader: ESP32SerialReader,
        state_store: RobotStateStore,
        pipeline_runner: PatrolPipelineRunner,
        pipeline_enabled: bool = True,
    ) -> None:
        self._settings = settings
        self._mqtt_client = mqtt_client
        self._serial_reader = serial_reader
        self._state_store = state_store
        self._pipeline_runner = pipeline_runner
        self._pipeline_enabled = pipeline_enabled

    def handle(
        self,
        topic: str,
        payload: dict[str, Any],
    ) -> None:
        """MqttClient on_message 콜백 진입점."""

        del topic

        command = payload.get("command")
        command_id = payload.get("commandId")

        if not isinstance(command, str) or not command:
            print("[COMMAND] command 필드가 없습니다.")
            return

        if not isinstance(command_id, str) or not command_id:
            print("[COMMAND] commandId 필드가 없습니다.")
            return

        if self._is_expired(payload):
            self._publish_ack(
                command=command,
                command_id=command_id,
                status="REJECTED",
            )
            print(
                "[COMMAND] 만료된 명령 거절: "
                f"command={command}, "
                f"commandId={command_id}"
            )
            return

        if command == "START_PATROL":
            self._handle_start_patrol(payload)
            return

        if command == "STOP_PATROL":
            self._handle_stop_patrol(payload)
            return

        if command == "SET_TOKEN":
            self._handle_set_token(payload)
            return

        if command == "START_MAPPING":
            print(
                "[COMMAND] START_MAPPING은 "
                "현재 무시합니다."
            )
            return

        print(f"[COMMAND] 알 수 없는 명령: {command}")

    def _handle_start_patrol(
        self,
        payload: dict[str, Any],
    ) -> None:
        """순찰 시작: Serial → 파이프라인 → ACK."""

        command = "START_PATROL"
        command_id = str(payload["commandId"])
        patrol_id = payload.get("patrolId")

        current_state = (
            self._state_store.get_status().state
        )

        if current_state == "PATROLLING":
            self._publish_ack(
                command=command,
                command_id=command_id,
                status="REJECTED",
            )
            print(
                "[COMMAND] 이미 순찰 중이라 "
                "START_PATROL을 거절합니다."
            )
            return

        if (
            self._pipeline_enabled
            and self._pipeline_runner.is_running()
        ):
            self._publish_ack(
                command=command,
                command_id=command_id,
                status="REJECTED",
            )
            print(
                "[COMMAND] 파이프라인이 이미 "
                "실행 중이라 START_PATROL을 거절합니다."
            )
            return

        if self._pipeline_enabled:
            try:
                self._pipeline_runner.start()
            except Exception as exc:
                self._publish_ack(
                    command=command,
                    command_id=command_id,
                    status="FAILED",
                )
                print(
                    "[COMMAND ERROR] 파이프라인 시작 실패: "
                    f"{exc}"
                )
                return
        else:
            print(
                "[PIPELINE] disabled: hardware-only patrol mode"
            )

        serial_kwargs: dict[str, Any] = {}
        if patrol_id is not None:
            serial_kwargs["patrolId"] = patrol_id

        try:
            self._serial_reader.send_command(
                "START_PATROL",
                **serial_kwargs,
            )
        except Exception as exc:
            # START is successful only when the physical runtime accepted the
            # motion target. Roll back any AI process before sending FAILED.
            if self._pipeline_enabled:
                try:
                    self._pipeline_runner.stop()
                except Exception as stop_error:
                    print(
                        "[COMMAND ERROR] Serial 실패 후 파이프라인 중지 오류: "
                        f"{stop_error}"
                    )
            self._publish_ack(
                command=command,
                command_id=command_id,
                status="FAILED",
            )
            print(
                "[COMMAND ERROR] ESP32 START_PATROL 실패: "
                f"{exc}"
            )
            return

        self._state_store.update_robot_state(
            "PATROLLING"
        )

        self._publish_ack(
            command=command,
            command_id=command_id,
            status="SUCCEEDED",
        )

        print(
            "[COMMAND] START_PATROL 성공: "
            f"commandId={command_id}, "
            f"patrolId={patrol_id}"
        )

    def _handle_stop_patrol(
        self,
        payload: dict[str, Any],
    ) -> None:
        """순찰 종료: Serial → 파이프라인 중지 → ACK."""

        command = "STOP_PATROL"
        command_id = str(payload["commandId"])

        serial_error: Exception | None = None
        pipeline_error: Exception | None = None

        try:
            self._serial_reader.send_command(
                "STOP_PATROL",
            )
        except Exception as exc:
            serial_error = exc
            print(
                "[COMMAND ERROR] ESP32 STOP_PATROL "
                f"실패: {exc}"
            )

        if self._pipeline_enabled:
            try:
                self._pipeline_runner.stop()
            except Exception as exc:
                pipeline_error = exc
                print(
                    "[COMMAND ERROR] 파이프라인 중지 실패: "
                    f"{exc}"
                )

        self._state_store.update_robot_state("IDLE")

        if serial_error is not None or pipeline_error is not None:
            self._publish_ack(
                command=command,
                command_id=command_id,
                status="FAILED",
            )
            print(
                "[COMMAND] STOP_PATROL FAILED: "
                f"commandId={command_id}"
            )
            return

        self._publish_ack(
            command=command,
            command_id=command_id,
            status="SUCCEEDED",
        )

        print(
            "[COMMAND] STOP_PATROL 성공: "
            f"commandId={command_id}"
        )

    def _handle_set_token(
        self,
        payload: dict[str, Any],
    ) -> None:
        """서비스 토큰을 저장하고 ACK를 보낸다."""

        command = "SET_TOKEN"
        command_id = str(payload["commandId"])
        token = payload.get("token")

        if not isinstance(token, str) or not token:
            self._publish_ack(
                command=command,
                command_id=command_id,
                status="REJECTED",
            )
            print("[COMMAND] SET_TOKEN token 없음")
            return

        try:
            TOKEN_FILE_PATH.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            TOKEN_FILE_PATH.write_text(
                token,
                encoding="utf-8",
            )
            os.environ["ROBOT_SERVICE_TOKEN"] = token
        except Exception as exc:
            self._publish_ack(
                command=command,
                command_id=command_id,
                status="FAILED",
            )
            print(
                "[COMMAND ERROR] SET_TOKEN 저장 실패: "
                f"{exc}"
            )
            return

        self._publish_ack(
            command=command,
            command_id=command_id,
            status="SUCCEEDED",
        )

        print(
            "[COMMAND] SET_TOKEN 저장 완료: "
            f"{TOKEN_FILE_PATH}"
        )

    def _is_expired(
        self,
        payload: dict[str, Any],
    ) -> bool:
        """expiresAt이 지났으면 True."""

        expires_at = payload.get("expiresAt")

        if not isinstance(expires_at, str):
            return False

        try:
            expire_time = self._parse_iso_datetime(
                expires_at
            )
        except ValueError:
            print(
                "[COMMAND] expiresAt 파싱 실패: "
                f"{expires_at}"
            )
            # 파싱 실패를 만료로 처리하면 retained SET_TOKEN
            # 같은 정상 명령이 거절되므로, 만료 검사만 스킵한다.
            return False

        now = datetime.now(tz=SEOUL)

        if expire_time.tzinfo is None:
            expire_time = expire_time.replace(
                tzinfo=SEOUL
            )

        return now > expire_time

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime:
        """
        ISO-8601 시각을 파싱한다.

        백엔드는 나노초(소수 9자리)를 보낼 수 있는데,
        Python 3.10 fromisoformat은 최대 6자리만 받는다.
        """

        normalized = value.strip()

        # 예: 2026-08-01T11:22:31.247765164+09:00
        #                 ^^^^^^^^^^^^^^^^ → 6자리로 자름
        if "." in normalized:
            head, fraction_and_tz = normalized.split(
                ".",
                1,
            )

            digits = []
            tz_part = ""

            for index, char in enumerate(
                fraction_and_tz
            ):
                if char.isdigit():
                    digits.append(char)
                    continue

                tz_part = fraction_and_tz[index:]
                break

            fraction = "".join(digits)[:6].ljust(6, "0")
            normalized = (
                f"{head}.{fraction}{tz_part}"
            )

        return datetime.fromisoformat(normalized)

    def _publish_ack(
        self,
        *,
        command: str,
        command_id: str,
        status: str,
    ) -> None:
        """command/ack 토픽으로 ACK를 발행한다."""

        ack_payload = {
            "schemaVersion": (
                self._settings.schema_version
            ),
            "commandId": command_id,
            "command": command,
            "status": status,
            "receivedAt": datetime.now(
                tz=SEOUL
            ).isoformat(timespec="seconds"),
        }

        self._mqtt_client.publish(
            topic=self._settings.command_response_topic,
            payload=ack_payload,
        )
