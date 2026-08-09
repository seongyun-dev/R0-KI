"""기본 주행 명령과 encoder odometry 계산.

Mission 목표를 speed/steering으로 변환하고 PWM ramp 및 직진 조향 보정을
수행한다. Serial, Safety, MQTT에는 의존하지 않는다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from serial_comm.protocol import Odometry


@dataclass(frozen=True)
class MotionControllerSettings:
    wheel_diameter_m: float
    encoder_ticks_per_revolution: int | None
    speed_min: int | None
    speed_max: int
    speed_ramp_per_update: int | None
    straight_correction_kp_deg_per_tick: float | None
    maximum_straight_correction_deg: int | None
    steering_center_deg: int
    steering_min_deg: int
    steering_max_deg: int

    @property
    def drive_calibrated(self) -> bool:
        return all(
            value is not None
            for value in (
                self.encoder_ticks_per_revolution,
                self.speed_min,
                self.speed_ramp_per_update,
                self.straight_correction_kp_deg_per_tick,
                self.maximum_straight_correction_deg,
            )
        )


@dataclass(frozen=True)
class MotionTarget:
    speed: int
    steering_deg: int


@dataclass(frozen=True)
class MotionCommand:
    speed: int
    steering_deg: int


@dataclass(frozen=True)
class MotionState:
    left_ticks: int
    right_ticks: int
    encoder_error_ticks: int
    left_speed_mps: float | None
    right_speed_mps: float | None
    average_speed_mps: float | None
    left_distance_m: float | None
    right_distance_m: float | None
    average_distance_m: float | None


class MotionController:
    def __init__(self, settings: MotionControllerSettings) -> None:
        self._settings = settings
        self._previous: Odometry | None = None
        self._left_distance_m = 0.0
        self._right_distance_m = 0.0
        self._current_speed = 0

    @property
    def drive_calibrated(self) -> bool:
        return self._settings.drive_calibrated

    def reset(self) -> None:
        self._previous = None
        self._left_distance_m = 0.0
        self._right_distance_m = 0.0
        self._current_speed = 0

    def stop_command(self) -> MotionCommand:
        self._current_speed = 0
        return MotionCommand(0, self._settings.steering_center_deg)

    def update(
        self,
        odometry: Odometry,
        target: MotionTarget,
    ) -> tuple[MotionCommand, MotionState]:
        delta_left = 0
        delta_right = 0
        delta_seconds = 0.0
        if self._previous is not None:
            delta_ms = odometry.uptime_ms - self._previous.uptime_ms
            if delta_ms <= 0:
                raise ValueError("odometry uptime must increase")
            delta_seconds = delta_ms / 1000.0
            delta_left = odometry.left_ticks - self._previous.left_ticks
            delta_right = odometry.right_ticks - self._previous.right_ticks

        state = self._build_state(
            odometry, delta_left, delta_right, delta_seconds
        )
        steering = self._clamp(
            target.steering_deg,
            self._settings.steering_min_deg,
            self._settings.steering_max_deg,
        )
        if (
            target.speed != 0
            and target.steering_deg == self._settings.steering_center_deg
            and self._settings.straight_correction_kp_deg_per_tick is not None
            and self._settings.maximum_straight_correction_deg is not None
        ):
            correction = round(
                state.encoder_error_ticks
                * self._settings.straight_correction_kp_deg_per_tick
            )
            correction = self._clamp(
                correction,
                -self._settings.maximum_straight_correction_deg,
                self._settings.maximum_straight_correction_deg,
            )
            direction = 1 if target.speed > 0 else -1
            steering = self._clamp(
                steering - direction * correction,
                self._settings.steering_min_deg,
                self._settings.steering_max_deg,
            )

        target_speed = self._clamp(
            target.speed, -self._settings.speed_max, self._settings.speed_max
        )
        self._current_speed = self._ramp(self._current_speed, target_speed)
        self._previous = odometry
        return MotionCommand(self._current_speed, steering), state

    def _build_state(
        self,
        odometry: Odometry,
        delta_left: int,
        delta_right: int,
        delta_seconds: float,
    ) -> MotionState:
        ticks = self._settings.encoder_ticks_per_revolution
        if ticks is None or ticks <= 0:
            return MotionState(
                odometry.left_ticks,
                odometry.right_ticks,
                delta_left - delta_right,
                None, None, None, None, None, None,
            )
        metres_per_tick = math.pi * self._settings.wheel_diameter_m / ticks
        left_delta = delta_left * metres_per_tick
        right_delta = delta_right * metres_per_tick
        self._left_distance_m += left_delta
        self._right_distance_m += right_delta
        left_speed = left_delta / delta_seconds if delta_seconds else 0.0
        right_speed = right_delta / delta_seconds if delta_seconds else 0.0
        return MotionState(
            odometry.left_ticks,
            odometry.right_ticks,
            delta_left - delta_right,
            left_speed,
            right_speed,
            (left_speed + right_speed) / 2.0,
            self._left_distance_m,
            self._right_distance_m,
            (self._left_distance_m + self._right_distance_m) / 2.0,
        )

    def _ramp(self, current: int, target: int) -> int:
        step = self._settings.speed_ramp_per_update
        minimum = self._settings.speed_min
        if target == 0:
            return 0
        if step is None or minimum is None:
            return 0
        if 0 < abs(target) < minimum:
            target = minimum if target > 0 else -minimum
        if target > current:
            return min(current + step, target)
        return max(current - step, target)

    @staticmethod
    def _clamp(value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, value))
