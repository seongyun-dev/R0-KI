"""Small, calibration-friendly helpers for vehicle map coordinates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class VehicleMapPosition:
    x: float
    y: float
    range_m: float


def find_containing_zone(
    x: float,
    y: float,
    zones: Iterable[Mapping[str, Any]],
) -> str | None:
    """Return a zone id using world-coordinate bounds, never map pixels."""

    point_x = float(x)
    point_y = float(y)
    if not math.isfinite(point_x) or not math.isfinite(point_y):
        return None
    for zone in zones:
        try:
            start_x = float(zone["startX"] if "startX" in zone else zone["xMin"])
            end_x = float(zone["endX"] if "endX" in zone else zone["xMax"])
            start_y = float(zone["startY"] if "startY" in zone else zone["yMin"])
            end_y = float(zone["endY"] if "endY" in zone else zone["yMax"])
        except (KeyError, TypeError, ValueError):
            continue
        bounds = (start_x, end_x, start_y, end_y)
        if not all(math.isfinite(value) for value in bounds):
            continue
        if (
            min(start_x, end_x) <= point_x <= max(start_x, end_x)
            and min(start_y, end_y) <= point_y <= max(start_y, end_y)
        ):
            zone_id = zone.get("id", zone.get("zoneId"))
            return str(zone_id) if zone_id is not None else None
    return None


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
