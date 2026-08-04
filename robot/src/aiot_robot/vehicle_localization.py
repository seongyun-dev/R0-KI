"""Small, calibration-friendly helpers for vehicle map coordinates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VehicleMapPosition:
    x: float
    y: float
    range_m: float


def project_front_vehicle(
    pose: Any,
    range_m: float,
    *,
    camera_yaw_deg: float = 0.0,
) -> VehicleMapPosition:
    """Project a front-camera detection into the ROS ``map`` frame.

    ``pose.heading`` and ``camera_yaw_deg`` are degrees. Positive camera yaw is
    counter-clockwise from ``base_link``. The range must come from LiDAR; wheel
    encoders describe robot motion and cannot measure distance to a vehicle.
    """

    values = (
        float(pose.x),
        float(pose.y),
        float(pose.heading),
        float(range_m),
        float(camera_yaw_deg),
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("vehicle projection values must be finite")
    if values[3] <= 0:
        raise ValueError("vehicle range must be positive")
    angle_rad = math.radians(values[2] + values[4])
    return VehicleMapPosition(
        x=values[0] + values[3] * math.cos(angle_rad),
        y=values[1] + values[3] * math.sin(angle_rad),
        range_m=values[3],
    )
