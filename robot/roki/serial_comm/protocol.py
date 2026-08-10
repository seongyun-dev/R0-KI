"""RO-KI ESP32 운영 JSON line protocol.

명령/응답의 wire format 생성과 검증은 이 파일만 담당한다.
시리얼 포트, 재연결, 주행 계산은 알지 못한다.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any


PROTOCOL_VERSION = 1
SEQUENCE_MAX = 2_147_483_647
LINE_SENSOR_CHANNEL_COUNT = 5


class MessageType(str, Enum):
    HELLO = "hello"
    ACK = "ack"
    ODOMETRY = "odometry"
    HARDWARE_STATUS = "hardwareStatus"
    ERROR = "error"


class MotorStatus(str, Enum):
    NORMAL = "NORMAL"
    FAULT = "FAULT"
    DISCONNECTED = "DISCONNECTED"


class LineSensorStatus(str, Enum):
    NORMAL = "NORMAL"
    FAULT = "FAULT"
    DISCONNECTED = "DISCONNECTED"


@dataclass(frozen=True)
class ProtocolSettings:
    speed_min: int = -255
    speed_max: int = 255
    steering_min_deg: int = 40
    steering_max_deg: int = 120
    steering_center_deg: int = 80


@dataclass(frozen=True)
class Odometry:
    seq: int
    uptime_ms: int
    left_ticks: int
    right_ticks: int


@dataclass(frozen=True)
class HardwareStatus:
    battery_percent: float | None
    motor: MotorStatus
    line_sensor: LineSensorStatus
    line_values: tuple[int, ...] | None = None
    battery_voltage: float | None = None


@dataclass(frozen=True)
class ProtocolMessage:
    message_type: MessageType
    payload: dict[str, Any]


class SequenceCounter:
    """프로토콜 sequence를 범위 내에서 순환시킨다."""

    def __init__(self) -> None:
        self._value = 0
        self._lock = threading.Lock()

    def next(self) -> int:
        with self._lock:
            value = self._value
            self._value = 0 if value == SEQUENCE_MAX else value + 1
            return value


def _json_line(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _sequence(value: object) -> int:
    sequence = _integer(value, "sequence")
    if not 0 <= sequence <= SEQUENCE_MAX:
        raise ValueError("sequence is out of range")
    return sequence


def build_control_command(
    speed: int,
    steering_deg: int,
    sequence: int,
    settings: ProtocolSettings,
) -> str:
    _integer(speed, "speed")
    _integer(steering_deg, "steering_deg")
    _sequence(sequence)
    if not settings.speed_min <= speed <= settings.speed_max:
        raise ValueError("speed is out of range")
    if not settings.steering_min_deg <= steering_deg <= settings.steering_max_deg:
        raise ValueError("steering_deg is out of range")
    return _json_line(
        {
            "type": "control",
            "speed": speed,
            "steering": steering_deg,
            "sequence": sequence,
        }
    )


def build_stop_command(sequence: int) -> str:
    return _json_line({"type": "stop", "sequence": _sequence(sequence)})


def build_status_command(sequence: int) -> str:
    return _json_line({"type": "status", "sequence": _sequence(sequence)})


def build_encoder_zero_command(sequence: int) -> str:
    return _json_line({"type": "encoder_zero", "sequence": _sequence(sequence)})


def build_hello_command(sequence: int) -> str:
    return _json_line(
        {
            "type": "hello",
            "protocol": PROTOCOL_VERSION,
            "sequence": _sequence(sequence),
        }
    )


def parse_message(raw_message: str, settings: ProtocolSettings) -> ProtocolMessage | None:
    try:
        payload = json.loads(raw_message.strip())
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        message_type = MessageType(payload["type"])
        if message_type is MessageType.ODOMETRY:
            parse_odometry(payload)
        elif message_type is MessageType.HARDWARE_STATUS:
            parse_hardware_status(payload)
        elif message_type is MessageType.HELLO:
            _sequence(payload["sequence"])
            if not isinstance(payload["firmware"], str):
                return None
            if _integer(payload["protocol"], "protocol") != PROTOCOL_VERSION:
                return None
        elif message_type is MessageType.ACK:
            _sequence(payload["sequence"])
            if not isinstance(payload["command"], str):
                return None
        elif message_type is MessageType.ERROR:
            if not isinstance(payload["fault"], str):
                return None
            if "sequence" in payload:
                _sequence(payload["sequence"])
    except (KeyError, TypeError, ValueError):
        return None
    return ProtocolMessage(message_type, payload)


def parse_odometry(payload: dict[str, Any]) -> Odometry:
    """최종 ESP32 odometry 계약을 검증하고 변환한다."""

    return Odometry(
        seq=_sequence(payload["seq"]),
        uptime_ms=_integer(payload["uptimeMs"], "uptimeMs"),
        left_ticks=_integer(payload["leftTicks"], "leftTicks"),
        right_ticks=_integer(payload["rightTicks"], "rightTicks"),
    )


def parse_hardware_status(payload: dict[str, Any]) -> HardwareStatus:
    """최종 ESP32 hardwareStatus 계약을 검증하고 변환한다."""

    battery = payload["battery"]
    battery_percent: float | None = None
    if battery is not None:
        if isinstance(battery, bool) or not isinstance(battery, (int, float)):
            raise ValueError("battery must be numeric or null")
        battery_percent = float(battery)
        if not 0.0 <= battery_percent <= 100.0:
            raise ValueError("battery must be between 0 and 100 percent")

    battery_voltage_payload = payload.get("batteryVoltage")
    battery_voltage: float | None = None
    if battery_voltage_payload is not None:
        if (
            isinstance(battery_voltage_payload, bool)
            or not isinstance(battery_voltage_payload, (int, float))
        ):
            raise ValueError("batteryVoltage must be numeric")
        battery_voltage = float(battery_voltage_payload)
        if battery_voltage < 0.0:
            raise ValueError("batteryVoltage must not be negative")
    if battery_percent is None and battery_voltage is None:
        raise ValueError("batteryVoltage is required when battery is null")
    try:
        motor = MotorStatus(payload["motor"])
        line_sensor = LineSensorStatus(payload["lineSensor"])
    except (TypeError, ValueError) as error:
        raise ValueError("invalid hardware status enum") from error
    line_values_payload = payload.get("lineValues")
    line_values: tuple[int, ...] | None = None
    if line_values_payload is not None:
        if (
            not isinstance(line_values_payload, list)
            or len(line_values_payload) != LINE_SENSOR_CHANNEL_COUNT
        ):
            raise ValueError("lineValues must contain exactly 5 channels")
        if any(
            isinstance(value, bool) or value not in (0, 1)
            for value in line_values_payload
        ):
            raise ValueError("lineValues channels must be integer 0 or 1")
        line_values = tuple(line_values_payload)
    return HardwareStatus(
        battery_percent=battery_percent,
        motor=motor,
        line_sensor=line_sensor,
        line_values=line_values,
        battery_voltage=battery_voltage,
    )
