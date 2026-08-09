"""MotionController의 거리 증분으로 odom frame Pose를 적분한다."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from control.motion_controller import MotionState
from localization.pose import PoseEstimate, PoseFrame, PoseSource


@dataclass(frozen=True)
class EncoderPoseEstimatorSettings:
    steering_center_command: int
    wheelbase_m: float | None = None
    steering_angle_rad_by_command: dict[int, float] | None = None


class EncoderPoseEstimator:
    """Ackermann/bicycle 차량의 시작점 기준 상대 Pose estimator.

    wheelbase와 실제 wheel angle calibration이 없으면 직진만 유효하다.
    조향 중 이동이 관측되면 그 뒤 Pose는 명시적 reset 전까지 invalid다.
    """

    def __init__(self, settings: EncoderPoseEstimatorSettings) -> None:
        self._settings = settings
        self._pose = PoseEstimate(
            0.0,
            0.0,
            0.0,
            PoseFrame.ODOM,
            PoseSource.ENCODER_ODOM,
            True,
            0.0,
        )
        self._previous_average_distance_m: float | None = None
        self._geometry_valid = True

    @property
    def pose(self) -> PoseEstimate:
        return self._pose

    def reset_baseline(self) -> None:
        """Reconnect/ENCODER_ZERO 시 거리 기준만 버리고 Pose는 유지한다."""

        self._previous_average_distance_m = None

    def reset_odom_pose(self, *, timestamp: float = 0.0) -> PoseEstimate:
        self._previous_average_distance_m = None
        self._geometry_valid = True
        self._pose = replace(
            self._pose,
            x_m=0.0,
            y_m=0.0,
            heading_rad=0.0,
            valid=True,
            timestamp=timestamp,
        )
        return self._pose

    def update(
        self,
        motion_state: MotionState,
        *,
        steering_command: int,
        timestamp: float,
    ) -> PoseEstimate:
        distance = motion_state.average_distance_m
        if distance is None:
            self._pose = replace(self._pose, valid=False, timestamp=timestamp)
            return self._pose
        if self._previous_average_distance_m is None:
            self._previous_average_distance_m = distance
            self._pose = replace(
                self._pose,
                valid=self._geometry_valid,
                timestamp=timestamp,
            )
            return self._pose

        delta_distance = distance - self._previous_average_distance_m
        self._previous_average_distance_m = distance
        if not self._geometry_valid:
            self._pose = replace(self._pose, valid=False, timestamp=timestamp)
            return self._pose

        steering_angle = self._steering_angle(steering_command)
        if steering_angle is None:
            if not math.isclose(delta_distance, 0.0, abs_tol=1e-12):
                self._geometry_valid = False
            self._pose = replace(self._pose, valid=False, timestamp=timestamp)
            return self._pose

        delta_heading = 0.0
        if not math.isclose(steering_angle, 0.0, abs_tol=1e-12):
            wheelbase = self._settings.wheelbase_m
            if wheelbase is None or wheelbase <= 0:
                self._geometry_valid = False
                self._pose = replace(self._pose, valid=False, timestamp=timestamp)
                return self._pose
            delta_heading = delta_distance * math.tan(steering_angle) / wheelbase

        midpoint_heading = self._pose.heading_rad + delta_heading / 2.0
        self._pose = replace(
            self._pose,
            x_m=self._pose.x_m + delta_distance * math.cos(midpoint_heading),
            y_m=self._pose.y_m + delta_distance * math.sin(midpoint_heading),
            heading_rad=self.normalize_heading(
                self._pose.heading_rad + delta_heading
            ),
            valid=True,
            timestamp=timestamp,
        )
        return self._pose

    def _steering_angle(self, command: int) -> float | None:
        if command == self._settings.steering_center_command:
            return 0.0
        calibration = self._settings.steering_angle_rad_by_command
        return None if calibration is None else calibration.get(command)

    @staticmethod
    def normalize_heading(heading_rad: float) -> float:
        return (heading_rad + math.pi) % (2.0 * math.pi) - math.pi
