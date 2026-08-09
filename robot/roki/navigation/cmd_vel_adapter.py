"""Convert ROS-style cmd_vel values into bounded ESP32 control targets."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class AckermannCommandSettings:
    wheelbase_m: float | None
    maximum_road_wheel_angle_deg: float | None
    maximum_linear_speed_mps: float = 0.4
    minimum_drive_pwm: int = 45
    maximum_drive_pwm: int = 51
    steering_left_deg: int = 60
    steering_center_deg: int = 80
    steering_right_deg: int = 100
    linear_deadband_mps: float = 0.01
    angular_deadband_radps: float = 0.01

    def __post_init__(self) -> None:
        if self.wheelbase_m is not None and self.wheelbase_m <= 0:
            raise ValueError("wheelbase_m must be positive or None")
        if (
            self.maximum_road_wheel_angle_deg is not None
            and self.maximum_road_wheel_angle_deg <= 0
        ):
            raise ValueError(
                "maximum_road_wheel_angle_deg must be positive or None"
            )
        if self.maximum_linear_speed_mps <= 0:
            raise ValueError("maximum_linear_speed_mps must be positive")
        if not 0 <= self.minimum_drive_pwm <= self.maximum_drive_pwm <= 255:
            raise ValueError("drive PWM range is invalid")
        if not (
            self.steering_left_deg
            < self.steering_center_deg
            < self.steering_right_deg
        ):
            raise ValueError("steering angles must be left < center < right")
        if self.linear_deadband_mps < 0 or self.angular_deadband_radps < 0:
            raise ValueError("deadbands must be non-negative")


@dataclass(frozen=True)
class CmdVelCommand:
    speed_pwm: int
    steering_deg: int
    stop_reason: str | None = None
    road_wheel_angle_deg: float = 0.0

    @property
    def stopped(self) -> bool:
        return self.speed_pwm == 0


class CmdVelToEsp32Adapter:
    def __init__(self, settings: AckermannCommandSettings) -> None:
        self._settings = settings

    def convert(self, linear_x_mps: float, angular_z_radps: float) -> CmdVelCommand:
        if not math.isfinite(linear_x_mps) or not math.isfinite(angular_z_radps):
            raise ValueError("cmd_vel values must be finite")
        settings = self._settings
        if abs(linear_x_mps) <= settings.linear_deadband_mps:
            reason = (
                "IN_PLACE_ROTATION_REJECTED"
                if abs(angular_z_radps) > settings.angular_deadband_radps
                else "STOPPED"
            )
            return CmdVelCommand(0, settings.steering_center_deg, reason)

        steering_deg = settings.steering_center_deg
        road_wheel_angle_deg = 0.0
        if abs(angular_z_radps) > settings.angular_deadband_radps:
            if (
                settings.wheelbase_m is None
                or settings.maximum_road_wheel_angle_deg is None
            ):
                return CmdVelCommand(
                    0,
                    settings.steering_center_deg,
                    "STEERING_NOT_CALIBRATED",
                )
            road_wheel_angle = math.atan(
                settings.wheelbase_m * angular_z_radps / linear_x_mps
            )
            road_wheel_angle_deg = math.degrees(road_wheel_angle)
            maximum = settings.maximum_road_wheel_angle_deg
            road_wheel_angle_deg = _clamp(road_wheel_angle_deg, -maximum, maximum)
            ratio = road_wheel_angle_deg / maximum
            # ROS positive angular.z is left; assembled servo uses lower angles left.
            if ratio >= 0:
                steering_deg = round(
                    settings.steering_center_deg
                    - ratio
                    * (settings.steering_center_deg - settings.steering_left_deg)
                )
            else:
                steering_deg = round(
                    settings.steering_center_deg
                    - ratio
                    * (settings.steering_right_deg - settings.steering_center_deg)
                )

        clamped_linear = _clamp(
            linear_x_mps,
            -settings.maximum_linear_speed_mps,
            settings.maximum_linear_speed_mps,
        )
        speed_ratio = abs(clamped_linear) / settings.maximum_linear_speed_mps
        pwm_span = settings.maximum_drive_pwm - settings.minimum_drive_pwm
        pwm = settings.minimum_drive_pwm + round(speed_ratio * pwm_span)
        if clamped_linear < 0:
            pwm = -pwm
        return CmdVelCommand(pwm, steering_deg, None, road_wheel_angle_deg)


class MemoryControlTransport:
    """Non-hardware transport used by integration tests and dry runs."""

    def __init__(self) -> None:
        self.commands: list[CmdVelCommand] = []

    def send(self, command: CmdVelCommand) -> None:
        self.commands.append(command)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
