"""
ESP32와 Jetson 사이의 Serial 메시지 데이터 모델.

이 파일은 데이터 구조만 정의한다.

시리얼 포트를 열거나 JSON을 해석하거나
상태를 저장하는 동작은 수행하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HardwareStatusMessage:
    """
    ESP32에서 수신한 하드웨어 상태.

    ESP32가 최종적으로 담당하는 값:
    - battery
    - motor
    - line_sensor

    state는 기존 ESP32 테스트 코드와의
    임시 호환을 위해 선택적으로 보관한다.
    """

    battery: float
    motor: str
    line_sensor: str
    state: str | None = None

    def to_legacy_dict(self) -> dict[str, Any]:
        """
        기존 MQTT Publisher가 사용하던
        dict 형식으로 변환한다.

        기존 코드와의 호환만 담당하며
        MQTT Payload를 만드는 함수는 아니다.
        """

        result: dict[str, Any] = {
            "battery": self.battery,
            "motor": self.motor,
            "lineSensor": self.line_sensor,
        }

        if self.state is not None:
            result["state"] = self.state

        return result


@dataclass(frozen=True)
class OdometryMessage:
    """
    ESP32 엔코더 누적 Tick 메시지.

    seq:
        ESP32가 전송한 메시지 순번.

    uptime_ms:
        ESP32가 부팅된 이후 경과 시간.

    left_ticks, right_ticks:
        좌우 엔코더의 누적 Tick 값.
    """

    seq: int
    uptime_ms: int
    left_ticks: int
    right_ticks: int


@dataclass(frozen=True)
class CommandAckMessage:
    """
    Jetson이 보낸 명령에 대한 ESP32 응답.

    command:
        ESP32가 처리한 명령 이름.

    accepted:
        명령 수락 여부.

    message:
        ESP32가 추가로 보낸 설명.
    """

    command: str | None
    accepted: bool | None
    message: str | None
