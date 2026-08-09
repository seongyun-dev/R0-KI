"""Convert calibrated wheel travel into a bounded straight map pose.

This is the temporary localization provider used before AMCL/Nav2 is ready.
It never writes Serial and never owns a motor command.  The runtime adapter
feeds it cumulative wheel distances and consumes the returned map poses.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass

from navigation.route import Route
from navigation.waypoint_mission import Pose2D


class EncoderWaypointError(RuntimeError):
    """Raised when an encoder-only patrol leaves its bounded assumptions."""


@dataclass(frozen=True)
class EncoderWaypointSettings:
    start_x_m: float = 1.0
    start_y_m: float = 2.5
    start_yaw_deg: float = 0.0
    maximum_reverse_m: float = 0.02
    maximum_wheel_disagreement_m: float = 0.15
    maximum_travel_m: float = 0.70
    interpolation_step_m: float = 0.01

    def __post_init__(self) -> None:
        numeric = (
            self.start_x_m,
            self.start_y_m,
            self.start_yaw_deg,
            self.maximum_reverse_m,
            self.maximum_wheel_disagreement_m,
            self.maximum_travel_m,
            self.interpolation_step_m,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("encoder waypoint settings must be finite")
        if self.maximum_reverse_m < 0:
            raise ValueError("maximum_reverse_m must not be negative")
        if self.maximum_wheel_disagreement_m <= 0:
            raise ValueError("maximum_wheel_disagreement_m must be positive")
        if self.maximum_travel_m <= 0:
            raise ValueError("maximum_travel_m must be positive")
        if not 0 < self.interpolation_step_m <= 0.05:
            raise ValueError("interpolation_step_m must be 0..0.05")


def validate_straight_encoder_route(
    route: Route,
    settings: EncoderWaypointSettings,
    *,
    maximum_destination_distance_m: float = 0.65,
) -> float:
    """Return destination distance and reject non-straight field routes."""

    previous_x = settings.start_x_m
    for waypoint in route.waypoints:
        if waypoint.x <= previous_x:
            raise EncoderWaypointError(
                "encoder-only route x coordinates must strictly increase"
            )
        if abs(waypoint.y - settings.start_y_m) > 0.01:
            raise EncoderWaypointError(
                "encoder-only route must remain on the configured start y"
            )
        if abs(waypoint.yaw_deg - settings.start_yaw_deg) > 0.01:
            raise EncoderWaypointError(
                "encoder-only route yaw must remain at the configured start yaw"
            )
        previous_x = waypoint.x

    destination_distance = route.waypoints[-1].x - settings.start_x_m
    if not 0.10 <= destination_distance <= maximum_destination_distance_m:
        raise EncoderWaypointError(
            "encoder-only destination must be 0.10.."
            f"{maximum_destination_distance_m:.2f} m ahead; "
            f"got {destination_distance:.3f} m"
        )
    if settings.maximum_travel_m <= destination_distance:
        raise EncoderWaypointError(
            "maximum_travel_m must leave positive destination overrun margin"
        )
    return destination_distance


class EncoderWaypointProgress:
    """Thread-safe logical encoder zero and map-pose interpolation."""

    def __init__(self, settings: EncoderWaypointSettings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._active = False
        self._baseline_left_m = 0.0
        self._baseline_right_m = 0.0
        self._previous_progress_m = 0.0

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    def start(self, *, left_distance_m: float, right_distance_m: float) -> None:
        self._validate_distance(left_distance_m, "left_distance_m")
        self._validate_distance(right_distance_m, "right_distance_m")
        with self._lock:
            if self._active:
                raise EncoderWaypointError("encoder waypoint patrol is already active")
            self._baseline_left_m = left_distance_m
            self._baseline_right_m = right_distance_m
            self._previous_progress_m = 0.0
            self._active = True

    def stop(self) -> None:
        with self._lock:
            self._active = False

    def update(
        self,
        *,
        left_distance_m: float,
        right_distance_m: float,
    ) -> tuple[Pose2D, ...]:
        self._validate_distance(left_distance_m, "left_distance_m")
        self._validate_distance(right_distance_m, "right_distance_m")
        with self._lock:
            if not self._active:
                return ()
            left_relative = left_distance_m - self._baseline_left_m
            right_relative = right_distance_m - self._baseline_right_m
            progress = (left_relative + right_relative) / 2.0
            if progress < -self._settings.maximum_reverse_m:
                raise EncoderWaypointError(
                    "reverse travel exceeded the encoder-only route limit"
                )
            if (
                abs(left_relative - right_relative)
                > self._settings.maximum_wheel_disagreement_m
            ):
                raise EncoderWaypointError(
                    "left/right encoder travel disagreement exceeded the limit"
                )
            if progress > self._settings.maximum_travel_m:
                raise EncoderWaypointError(
                    "encoder-only maximum travel guard was exceeded"
                )

            monotonic_progress = max(self._previous_progress_m, progress, 0.0)
            values = self._interpolate(
                self._previous_progress_m,
                monotonic_progress,
            )
            self._previous_progress_m = monotonic_progress

        return tuple(
            Pose2D(
                self._settings.start_x_m + value,
                self._settings.start_y_m,
                self._settings.start_yaw_deg,
            )
            for value in values
        )

    def _interpolate(self, previous: float, current: float) -> tuple[float, ...]:
        if current <= previous:
            return (current,)
        steps = max(
            1,
            math.ceil(
                (current - previous) / self._settings.interpolation_step_m
            ),
        )
        return tuple(
            previous + (current - previous) * index / steps
            for index in range(1, steps + 1)
        )

    @staticmethod
    def _validate_distance(value: float, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EncoderWaypointError(f"{name} must be numeric")
        if not math.isfinite(float(value)):
            raise EncoderWaypointError(f"{name} must be finite")
