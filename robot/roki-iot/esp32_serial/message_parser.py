"""
ESP32 JSON 메시지 검증 및 변환 모듈.

이 파일의 책임:

1. JSON 문자열을 dict로 변환
2. 메시지 type 분류
3. 필수 필드 검증
4. 데이터 모델 생성

시리얼 포트 접근이나 최신 상태 저장은 하지 않는다.
"""

from __future__ import annotations

import json
from typing import Any

from esp32_serial.models import (
    CommandAckMessage,
    HardwareStatusMessage,
    OdometryMessage,
)


ParsedEsp32Message = (
    HardwareStatusMessage
    | OdometryMessage
    | CommandAckMessage
)


class InvalidEsp32MessageError(ValueError):
    """ESP32 메시지 내용이 명세와 다를 때 발생한다."""


class UnknownEsp32MessageError(ValueError):
    """지원하지 않는 메시지 type일 때 발생한다."""


class Esp32MessageParser:
    """ESP32 JSON 문자열을 내부 메시지 객체로 변환한다."""

    def parse(
        self,
        frame: str,
    ) -> ParsedEsp32Message:
        """
        JSON 프레임 하나를 검증하고 변환한다.

        JSON 문법 오류:
            InvalidEsp32MessageError

        알 수 없는 type:
            UnknownEsp32MessageError
        """

        data = self._decode_json(frame)

        message_type = data.get("type")

        if message_type == "hardwareStatus":
            return self._parse_hardware_status(data)

        if message_type == "odometry":
            return self._parse_odometry(data)

        if message_type == "commandAck":
            return self._parse_command_ack(data)

        # 현재 ESP32 테스트 코드는 type 없이
        # battery, motor, state를 보내고 있다.
        #
        # 새 프로토콜 전환 전까지 호환성을 유지한다.
        if self._is_legacy_status(data):
            return self._parse_legacy_status(data)

        raise UnknownEsp32MessageError(
            f"지원하지 않는 메시지: {data}"
        )

    @staticmethod
    def _decode_json(
        frame: str,
    ) -> dict[str, Any]:
        """JSON 문자열을 dict로 변환한다."""

        try:
            data = json.loads(frame)
        except json.JSONDecodeError as error:
            raise InvalidEsp32MessageError(
                f"JSON 문법 오류: {frame}"
            ) from error

        if not isinstance(data, dict):
            raise InvalidEsp32MessageError(
                "JSON 최상위 값은 객체여야 합니다."
            )

        return data

    def _parse_hardware_status(
        self,
        data: dict[str, Any],
    ) -> HardwareStatusMessage:
        """
        최종 hardwareStatus 프로토콜을 변환한다.

        예상 형식:
        {
          "type": "hardwareStatus",
          "battery": 82.5,
          "motor": "NORMAL",
          "lineSensor": "NORMAL"
        }
        """

        battery = self._required_number(
            data,
            "battery",
        )

        motor = self._required_string(
            data,
            "motor",
        )

        line_sensor = self._required_string(
            data,
            "lineSensor",
        )

        return HardwareStatusMessage(
            battery=battery,
            motor=motor,
            line_sensor=line_sensor,
        )

    def _parse_legacy_status(
        self,
        data: dict[str, Any],
    ) -> HardwareStatusMessage:
        """
        현재 ESP32 테스트 형식을 변환한다.

        예상 형식:
        {
          "battery": 0.0,
          "motor": "NORMAL",
          "state": "PATROLLING"
        }

        lineSensor가 없으므로 DISCONNECTED를 사용한다.
        """

        return HardwareStatusMessage(
            battery=self._required_number(
                data,
                "battery",
            ),
            motor=self._required_string(
                data,
                "motor",
            ),
            line_sensor=self._optional_string(
                data,
                "lineSensor",
                default="DISCONNECTED",
            ),
            state=self._optional_string(
                data,
                "state",
                default=None,
            ),
        )

    def _parse_odometry(
        self,
        data: dict[str, Any],
    ) -> OdometryMessage:
        """
        odometry 메시지를 변환한다.

        예상 형식:
        {
          "type": "odometry",
          "seq": 1042,
          "uptimeMs": 523010,
          "leftTicks": 18240,
          "rightTicks": 18192
        }
        """

        return OdometryMessage(
            seq=self._required_integer(
                data,
                "seq",
            ),
            uptime_ms=self._required_integer(
                data,
                "uptimeMs",
            ),
            left_ticks=self._required_integer(
                data,
                "leftTicks",
            ),
            right_ticks=self._required_integer(
                data,
                "rightTicks",
            ),
        )

    def _parse_command_ack(
        self,
        data: dict[str, Any],
    ) -> CommandAckMessage:
        """명령 처리 결과 메시지를 변환한다."""

        accepted_value = data.get("accepted")

        if (
            accepted_value is not None
            and not isinstance(accepted_value, bool)
        ):
            raise InvalidEsp32MessageError(
                "accepted는 bool이어야 합니다."
            )

        return CommandAckMessage(
            command=self._optional_string(
                data,
                "command",
                default=None,
            ),
            accepted=accepted_value,
            message=self._optional_string(
                data,
                "message",
                default=None,
            ),
        )

    @staticmethod
    def _is_legacy_status(
        data: dict[str, Any],
    ) -> bool:
        """기존 ESP32 상태 형식인지 확인한다."""

        return all(
            key in data
            for key in (
                "battery",
                "motor",
                "state",
            )
        )

    @staticmethod
    def _required_string(
        data: dict[str, Any],
        key: str,
    ) -> str:
        """필수 문자열 필드를 검증한다."""

        value = data.get(key)

        if not isinstance(value, str) or not value:
            raise InvalidEsp32MessageError(
                f"{key}는 비어 있지 않은 문자열이어야 합니다."
            )

        return value

    @staticmethod
    def _optional_string(
        data: dict[str, Any],
        key: str,
        default: str | None,
    ) -> str | None:
        """선택 문자열 필드를 검증한다."""

        value = data.get(key, default)

        if value is None:
            return None

        if not isinstance(value, str):
            raise InvalidEsp32MessageError(
                f"{key}는 문자열이어야 합니다."
            )

        return value

    @staticmethod
    def _required_number(
        data: dict[str, Any],
        key: str,
    ) -> float:
        """필수 숫자 필드를 float로 변환한다."""

        value = data.get(key)

        # bool은 Python에서 int의 하위 타입이므로
        # 숫자로 잘못 허용되지 않도록 별도로 제외한다.
        if isinstance(value, bool):
            raise InvalidEsp32MessageError(
                f"{key}는 숫자여야 합니다."
            )

        if not isinstance(value, (int, float)):
            raise InvalidEsp32MessageError(
                f"{key}는 숫자여야 합니다."
            )

        return float(value)

    @staticmethod
    def _required_integer(
        data: dict[str, Any],
        key: str,
    ) -> int:
        """필수 정수 필드를 검증한다."""

        value = data.get(key)

        if isinstance(value, bool) or not isinstance(
            value,
            int,
        ):
            raise InvalidEsp32MessageError(
                f"{key}는 정수여야 합니다."
            )

        return value
