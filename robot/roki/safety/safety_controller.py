"""Hardware 상태와 운영 데이터 생존 여부를 판단하는 안전 정책.

Motion/Pose 계산, Serial I/O, MQTT publish는 수행하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from serial_comm.protocol import (
    HardwareStatus,
    LineSensorStatus,
    MotorStatus,
)


@dataclass(frozen=True)
class SafetySettings:
    odometry_timeout_sec: float
    hardware_status_timeout_sec: float
    low_battery_percent: float | None

    def __post_init__(self) -> None:
        if self.odometry_timeout_sec <= 0:
            raise ValueError("odometry_timeout_sec must be positive")
        if self.hardware_status_timeout_sec <= 0:
            raise ValueError("hardware_status_timeout_sec must be positive")
        if (
            self.low_battery_percent is not None
            and not 0.0 <= self.low_battery_percent <= 100.0
        ):
            raise ValueError("low_battery_percent must be between 0 and 100")


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    fault: str


class SafetyController:
    """Hardware 상태와 odometry/hardwareStatus 생존 여부를 평가한다."""

    def __init__(self, settings: SafetySettings) -> None:
        self._settings = settings
        self._last_odometry_time: float | None = None
        self._last_hardware_status_time: float | None = None
        self._latched_fault = ""

    @property
    def last_odometry_time(self) -> float | None:
        return self._last_odometry_time

    @property
    def last_hardware_status_time(self) -> float | None:
        return self._last_hardware_status_time

    def record_odometry(self, received_at: float) -> None:
        self._last_odometry_time = received_at

    def record_hardware_status(self, received_at: float) -> None:
        self._last_hardware_status_time = received_at

    def latch(self, fault: str) -> None:
        if not fault:
            raise ValueError("fault must not be empty")
        self._latched_fault = fault

    def clear_latched_fault(self) -> None:
        self._latched_fault = ""

    def reset_connection(self) -> None:
        self._last_odometry_time = None
        self._last_hardware_status_time = None
        self._latched_fault = ""

    def evaluate(
        self,
        *,
        now: float,
        connected: bool,
        hardware_status: HardwareStatus | None,
        emergency_stop: bool,
    ) -> SafetyDecision:
        if self._latched_fault:
            return SafetyDecision(False, self._latched_fault)
        if emergency_stop:
            return SafetyDecision(False, "EMERGENCY_STOP")
        if not connected:
            return SafetyDecision(False, "SERIAL_DISCONNECTED")

        odometry_fault = self._odometry_fault(now)
        if odometry_fault is not None:
            return SafetyDecision(False, odometry_fault)

        hardware_timeout_fault = self._hardware_status_timeout_fault(now)
        if hardware_timeout_fault is not None:
            return SafetyDecision(False, hardware_timeout_fault)
        if hardware_status is None:
            return SafetyDecision(False, "HARDWARE_STATUS_NOT_READY")

        hardware_fault = self._hardware_fault(hardware_status)
        if hardware_fault is not None:
            return SafetyDecision(False, hardware_fault)
        return SafetyDecision(True, "NONE")

    def _odometry_fault(self, now: float) -> str | None:
        if self._last_odometry_time is None:
            return "ODOMETRY_NOT_READY"
        if now - self._last_odometry_time > self._settings.odometry_timeout_sec:
            return "ODOMETRY_TIMEOUT"
        return None

    def _hardware_status_timeout_fault(self, now: float) -> str | None:
        if self._last_hardware_status_time is None:
            return "HARDWARE_STATUS_NOT_READY"
        if (
            now - self._last_hardware_status_time
            > self._settings.hardware_status_timeout_sec
        ):
            return "HARDWARE_STATUS_TIMEOUT"
        return None

    def _hardware_fault(
        self, hardware_status: HardwareStatus
    ) -> str | None:
        if hardware_status.motor is MotorStatus.FAULT:
            return "MOTOR_FAULT"
        if hardware_status.motor is MotorStatus.DISCONNECTED:
            return "MOTOR_DISCONNECTED"
        if hardware_status.line_sensor is LineSensorStatus.FAULT:
            return "LINE_SENSOR_FAULT"
        if hardware_status.line_sensor is LineSensorStatus.DISCONNECTED:
            return "LINE_SENSOR_DISCONNECTED"
        cutoff = self._settings.low_battery_percent
        if (
            cutoff is not None
            and hardware_status.battery_percent < cutoff
        ):
            return "LOW_BATTERY"
        return None
