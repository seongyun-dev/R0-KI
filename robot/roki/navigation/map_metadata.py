"""Validate a Nav2 occupancy map and route bounds without starting ROS."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from navigation.route import Route, RouteValidationError


@dataclass(frozen=True)
class OccupancyMapMetadata:
    yaml_path: Path
    image_path: Path
    resolution_m: float
    origin_x: float
    origin_y: float
    origin_yaw_rad: float
    width_px: int
    height_px: int

    @property
    def width_m(self) -> float:
        return self.width_px * self.resolution_m

    @property
    def height_m(self) -> float:
        return self.height_px * self.resolution_m


def load_map_metadata(path: str | Path) -> OccupancyMapMetadata:
    yaml_path = Path(path).resolve()
    with yaml_path.open("r", encoding="utf-8") as source:
        raw = yaml.safe_load(source)
    if not isinstance(raw, Mapping):
        raise RouteValidationError("map YAML root must be an object")
    image_value = raw.get("image")
    if not isinstance(image_value, str) or not image_value.strip():
        raise RouteValidationError("map image must be a non-empty path")
    image_path = (yaml_path.parent / image_value).resolve()
    if not image_path.is_file():
        raise RouteValidationError(f"map image is missing: {image_path}")
    resolution = _finite(raw.get("resolution"), "map resolution")
    if resolution <= 0:
        raise RouteValidationError("map resolution must be positive")
    origin = raw.get("origin")
    if not isinstance(origin, list) or len(origin) != 3:
        raise RouteValidationError("map origin must contain x, y and yaw")
    origin_x, origin_y, origin_yaw = (
        _finite(value, f"map origin[{index}]")
        for index, value in enumerate(origin)
    )
    negate = raw.get("negate")
    if isinstance(negate, bool) or negate not in (0, 1):
        raise RouteValidationError("map negate must be 0 or 1")
    occupied = _finite(raw.get("occupied_thresh"), "occupied_thresh")
    free = _finite(raw.get("free_thresh"), "free_thresh")
    if not 0 <= free < occupied <= 1:
        raise RouteValidationError(
            "map thresholds must satisfy 0 <= free < occupied <= 1"
        )
    width, height = _image_size(image_path)
    return OccupancyMapMetadata(
        yaml_path,
        image_path,
        resolution,
        origin_x,
        origin_y,
        origin_yaw,
        width,
        height,
    )


def validate_route_bounds(route: Route, metadata: OccupancyMapMetadata) -> None:
    cosine = math.cos(metadata.origin_yaw_rad)
    sine = math.sin(metadata.origin_yaw_rad)
    for waypoint in route.waypoints:
        dx = waypoint.x - metadata.origin_x
        dy = waypoint.y - metadata.origin_y
        map_x = cosine * dx + sine * dy
        map_y = -sine * dx + cosine * dy
        if not (0 <= map_x <= metadata.width_m and 0 <= map_y <= metadata.height_m):
            raise RouteValidationError(
                f"waypoint {waypoint.sequence} is outside map bounds"
            )


def _image_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as source:
        header = source.read(32)
    if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
        width, height = struct.unpack(">II", header[16:24])
    elif header.startswith((b"P5", b"P2")):
        tokens: list[bytes] = []
        with path.open("rb") as source:
            for line in source:
                stripped = line.split(b"#", 1)[0]
                tokens.extend(stripped.split())
                if len(tokens) >= 4:
                    break
        if len(tokens) < 4:
            raise RouteValidationError("PGM header is incomplete")
        try:
            width, height = int(tokens[1]), int(tokens[2])
        except ValueError as error:
            raise RouteValidationError("PGM dimensions are invalid") from error
    else:
        raise RouteValidationError("map image must be PNG, P2 PGM or P5 PGM")
    if width <= 0 or height <= 0:
        raise RouteValidationError("map image dimensions must be positive")
    return width, height


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RouteValidationError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise RouteValidationError(f"{field} must be finite")
    return result
