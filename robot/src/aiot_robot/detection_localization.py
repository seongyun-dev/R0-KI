"""Map-coordinate projection helpers shared by camera detections."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class DetectionMapPosition:
    x: float
    y: float
    range_m: float
    bearing_deg: float


def bbox_center_bearing_deg(
    bbox: Mapping[str, Any],
    frame_width: float,
    *,
    camera_horizontal_fov_deg: float,
    camera_yaw_deg: float = 0.0,
) -> float:
    """Convert a bbox center pixel into a base_link-relative bearing.

    ROS yaw is positive counter-clockwise. Image x increases to the right, so
    a bbox on the right side of the image produces a negative bearing.
    """

    values = (
        float(bbox["x"]),
        float(bbox["width"]),
        float(frame_width),
        float(camera_horizontal_fov_deg),
        float(camera_yaw_deg),
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("detection bearing values must be finite")
    x, width, image_width, horizontal_fov, camera_yaw = values
    if x < 0 or width <= 0 or image_width <= 0:
        raise ValueError("detection bbox and frame width must be positive")
    if not 0 < horizontal_fov < 180:
        raise ValueError("camera horizontal FOV must be between 0 and 180 degrees")
    center_x = x + width / 2.0
    if center_x < 0 or center_x > image_width:
        raise ValueError("detection bbox center is outside the frame")
    normalized_x = (center_x / image_width - 0.5) * 2.0
    return camera_yaw - normalized_x * horizontal_fov / 2.0


def project_detection(
    pose: Any,
    range_m: float,
    *,
    bearing_deg: float = 0.0,
) -> DetectionMapPosition:
    """Project a relative camera/LiDAR observation into the ROS map frame."""

    values = (
        float(pose.x),
        float(pose.y),
        float(pose.heading),
        float(range_m),
        float(bearing_deg),
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("detection projection values must be finite")
    if values[3] <= 0:
        raise ValueError("detection range must be positive")
    angle_rad = math.radians(values[2] + values[4])
    return DetectionMapPosition(
        x=values[0] + values[3] * math.cos(angle_rad),
        y=values[1] + values[3] * math.sin(angle_rad),
        range_m=values[3],
        bearing_deg=values[4],
    )
