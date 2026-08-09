"""Five-channel digital line follower with fail-closed decisions.

The controller is deliberately independent from Serial, MQTT and ROS so field
logs can be replayed before any movement test. A missing line produces speed
zero on the first frame; confirmation counters only classify the stop reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class LineFollowMode(str, Enum):
    FOLLOWING = "FOLLOWING"
    LINE_LOST_PENDING = "LINE_LOST_PENDING"
    LINE_LOST = "LINE_LOST"
    DESTINATION_PENDING = "DESTINATION_PENDING"
    DESTINATION = "DESTINATION"


@dataclass(frozen=True)
class LineFollowerSettings:
    black_value: int = 0
    weights: tuple[float, ...] = (-2.0, -1.0, 0.0, 1.0, 2.0)
    drive_speed_pwm: int = 45
    steering_center_deg: int = 80
    steering_min_deg: int = 60
    steering_max_deg: int = 100
    steering_sign: int = 1
    kp_deg_per_error: float = 10.0
    kd_deg_per_error_delta: float = 1.0
    maximum_correction_deg: int = 20
    lost_confirm_frames: int = 2
    destination_min_black_sensors: int = 4
    destination_confirm_frames: int = 3
    destination_arm_after_follow_frames: int = 10

    def __post_init__(self) -> None:
        if self.black_value not in (0, 1):
            raise ValueError("black_value must be 0 or 1")
        if len(self.weights) != 5:
            raise ValueError("weights must contain exactly five values")
        if not 1 <= self.drive_speed_pwm <= 51:
            raise ValueError("drive_speed_pwm must be 1..51 for field tests")
        if not (
            self.steering_min_deg
            <= self.steering_center_deg
            <= self.steering_max_deg
        ):
            raise ValueError("steering center must be within steering limits")
        if self.steering_sign not in (-1, 1):
            raise ValueError("steering_sign must be -1 or 1")
        if self.maximum_correction_deg <= 0:
            raise ValueError("maximum_correction_deg must be positive")
        if self.lost_confirm_frames <= 0:
            raise ValueError("lost_confirm_frames must be positive")
        if not 0 <= self.destination_min_black_sensors <= len(self.weights):
            raise ValueError("destination_min_black_sensors must be 0..5")
        if self.destination_confirm_frames <= 0:
            raise ValueError("destination_confirm_frames must be positive")
        if self.destination_arm_after_follow_frames < 0:
            raise ValueError("destination_arm_after_follow_frames must be >= 0")


@dataclass(frozen=True)
class LineFollowDecision:
    mode: LineFollowMode
    speed_pwm: int
    steering_deg: int
    error: float | None
    active_black_sensors: int
    line_values: tuple[int, ...]


class LineFollower:
    """Convert raw digital channels into bounded speed and steering targets."""

    def __init__(self, settings: LineFollowerSettings) -> None:
        self._settings = settings
        self.reset()

    @property
    def settings(self) -> LineFollowerSettings:
        return self._settings

    def reset(self) -> None:
        self._previous_error: float | None = None
        self._lost_frames = 0
        self._destination_frames = 0
        self._follow_frames = 0
        self._terminal_mode: LineFollowMode | None = None

    def update(self, line_values: Sequence[int]) -> LineFollowDecision:
        values = self._validate_values(line_values)
        if self._terminal_mode is not None:
            return self._stop_decision(
                self._terminal_mode,
                values,
                self._active_indices(values),
            )

        active = self._active_indices(values)
        if not active:
            self._lost_frames += 1
            self._destination_frames = 0
            mode = (
                LineFollowMode.LINE_LOST
                if self._lost_frames >= self._settings.lost_confirm_frames
                else LineFollowMode.LINE_LOST_PENDING
            )
            if mode is LineFollowMode.LINE_LOST:
                self._terminal_mode = mode
            return self._stop_decision(mode, values, active)

        self._lost_frames = 0
        destination_candidate = (
            self._settings.destination_min_black_sensors > 0
            and self._follow_frames
            >= self._settings.destination_arm_after_follow_frames
            and len(active)
            >= self._settings.destination_min_black_sensors
        )
        if destination_candidate:
            self._destination_frames += 1
            mode = (
                LineFollowMode.DESTINATION
                if self._destination_frames
                >= self._settings.destination_confirm_frames
                else LineFollowMode.DESTINATION_PENDING
            )
            if mode is LineFollowMode.DESTINATION:
                self._terminal_mode = mode
            return self._stop_decision(mode, values, active)

        self._destination_frames = 0
        error = sum(self._settings.weights[index] for index in active) / len(active)
        error_delta = (
            0.0
            if self._previous_error is None
            else error - self._previous_error
        )
        raw_correction = self._settings.steering_sign * (
            self._settings.kp_deg_per_error * error
            + self._settings.kd_deg_per_error_delta * error_delta
        )
        correction = self._clamp(
            round(raw_correction),
            -self._settings.maximum_correction_deg,
            self._settings.maximum_correction_deg,
        )
        steering = self._clamp(
            self._settings.steering_center_deg + correction,
            self._settings.steering_min_deg,
            self._settings.steering_max_deg,
        )
        self._previous_error = error
        self._follow_frames += 1
        return LineFollowDecision(
            LineFollowMode.FOLLOWING,
            self._settings.drive_speed_pwm,
            steering,
            error,
            len(active),
            values,
        )

    def _stop_decision(
        self,
        mode: LineFollowMode,
        values: tuple[int, ...],
        active: tuple[int, ...],
    ) -> LineFollowDecision:
        return LineFollowDecision(
            mode,
            0,
            self._settings.steering_center_deg,
            None,
            len(active),
            values,
        )

    def _active_indices(self, values: tuple[int, ...]) -> tuple[int, ...]:
        return tuple(
            index
            for index, value in enumerate(values)
            if value == self._settings.black_value
        )

    def _validate_values(self, line_values: Sequence[int]) -> tuple[int, ...]:
        values = tuple(line_values)
        if len(values) != len(self._settings.weights):
            raise ValueError("line_values must contain exactly five channels")
        if any(isinstance(value, bool) or value not in (0, 1) for value in values):
            raise ValueError("line_values channels must be integer 0 or 1")
        return values

    @staticmethod
    def _clamp(value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, value))
