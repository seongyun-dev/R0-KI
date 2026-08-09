"""Validate a Nav2 occupancy map and demo route without starting ROS."""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from navigation.route import Route, RouteValidationError


FREE = 0
UNKNOWN = -1
OCCUPIED = 100


@dataclass(frozen=True)
class OccupancyMapMetadata:
    yaml_path: Path
    image_path: Path
    resolution_m: float
    origin_x: float
    origin_y: float
    origin_yaw_rad: float
    negate: int
    occupied_thresh: float
    free_thresh: float
    width_px: int
    height_px: int

    @property
    def width_m(self) -> float:
        return self.width_px * self.resolution_m

    @property
    def height_m(self) -> float:
        return self.height_px * self.resolution_m


@dataclass(frozen=True)
class OccupancyGrid:
    metadata: OccupancyMapMetadata
    cells: tuple[int, ...]
    canonical_unknown_cells: int

    @property
    def known_coverage_ratio(self) -> float:
        return sum(cell != UNKNOWN for cell in self.cells) / len(self.cells)

    @property
    def free_coverage_ratio(self) -> float:
        return sum(cell == FREE for cell in self.cells) / len(self.cells)

    def cell_at(self, column: int, row_from_bottom: int) -> int:
        if not (0 <= column < self.metadata.width_px):
            raise IndexError(column)
        if not (0 <= row_from_bottom < self.metadata.height_px):
            raise IndexError(row_from_bottom)
        image_row = self.metadata.height_px - 1 - row_from_bottom
        return self.cells[image_row * self.metadata.width_px + column]


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def map_bundle_sha256(metadata: OccupancyMapMetadata) -> str:
    """Hash the exact map YAML and referenced image as one versioned bundle."""

    digest = hashlib.sha256(b"ROKI_MAP_BUNDLE_V1\0")
    for path in (metadata.yaml_path, metadata.image_path):
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


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
        yaml_path=yaml_path,
        image_path=image_path,
        resolution_m=resolution,
        origin_x=origin_x,
        origin_y=origin_y,
        origin_yaw_rad=origin_yaw,
        negate=negate,
        occupied_thresh=occupied,
        free_thresh=free,
        width_px=width,
        height_px=height,
    )


def load_occupancy_grid(metadata: OccupancyMapMetadata) -> OccupancyGrid:
    """Decode a dependency-free PGM map for fail-closed demo validation."""

    with metadata.image_path.open("rb") as source:
        magic = source.read(2)
    if magic not in (b"P2", b"P5"):
        raise RouteValidationError(
            "demo occupancy validation requires a P2 or P5 PGM map"
        )
    pixels, maximum, width, height = _read_pgm(metadata.image_path)
    if (width, height) != (metadata.width_px, metadata.height_px):
        raise RouteValidationError("map image dimensions changed during validation")
    cells: list[int] = []
    canonical_unknown_sample = round(205 * maximum / 255)
    canonical_unknown_cells = 0
    for pixel in pixels:
        if pixel == canonical_unknown_sample:
            cells.append(UNKNOWN)
            canonical_unknown_cells += 1
            continue
        shade = pixel / maximum
        occupancy = shade if metadata.negate else 1.0 - shade
        if occupancy > metadata.occupied_thresh:
            cells.append(OCCUPIED)
        elif occupancy < metadata.free_thresh:
            cells.append(FREE)
        else:
            cells.append(UNKNOWN)
    return OccupancyGrid(metadata, tuple(cells), canonical_unknown_cells)


def validate_map_quality(
    grid: OccupancyGrid,
    *,
    minimum_known_coverage_ratio: float,
    minimum_free_coverage_ratio: float,
) -> None:
    """Reject a mostly unknown or effectively unusable SLAM snapshot."""

    for name, value in (
        ("minimum known coverage", minimum_known_coverage_ratio),
        ("minimum free coverage", minimum_free_coverage_ratio),
    ):
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise RouteValidationError(f"{name} ratio must be within 0.0..1.0")
    known = grid.known_coverage_ratio
    free = grid.free_coverage_ratio
    if known < minimum_known_coverage_ratio:
        raise RouteValidationError(
            "map known coverage is below demo minimum: "
            f"{known:.2%} < {minimum_known_coverage_ratio:.2%}"
        )
    if free < minimum_free_coverage_ratio:
        raise RouteValidationError(
            "map free coverage is below demo minimum: "
            f"{free:.2%} < {minimum_free_coverage_ratio:.2%}"
        )
    if grid.canonical_unknown_cells:
        unknown_shade = 205 / 255
        unknown_occupancy = (
            unknown_shade
            if grid.metadata.negate
            else 1.0 - unknown_shade
        )
        if (
            unknown_occupancy > grid.metadata.occupied_thresh
            or unknown_occupancy < grid.metadata.free_thresh
        ):
            raise RouteValidationError(
                "map thresholds classify canonical unknown pixels as traversable; "
                "adjust free_thresh before Nav2 patrol"
            )


def validate_route_bounds(route: Route, metadata: OccupancyMapMetadata) -> None:
    for waypoint in route.waypoints:
        validate_point_bounds(
            waypoint.x,
            waypoint.y,
            metadata,
            label=f"waypoint {waypoint.sequence}",
        )


def validate_point_bounds(
    x: float,
    y: float,
    metadata: OccupancyMapMetadata,
    *,
    label: str,
) -> None:
    """Reject a map-frame point that cannot exist in the loaded occupancy map."""

    if not math.isfinite(x) or not math.isfinite(y):
        raise RouteValidationError(f"{label} coordinates must be finite")
    map_x, map_y = _world_to_map(x, y, metadata)
    if not (0 <= map_x < metadata.width_m and 0 <= map_y < metadata.height_m):
        raise RouteValidationError(f"{label} is outside map bounds")


def validate_point_clearance(
    x: float,
    y: float,
    grid: OccupancyGrid,
    *,
    robot_radius_m: float,
    label: str,
) -> None:
    """Require the whole circular robot footprint to occupy FREE cells."""

    metadata = grid.metadata
    validate_point_bounds(x, y, metadata, label=label)
    if not math.isfinite(robot_radius_m) or robot_radius_m <= 0:
        raise RouteValidationError("robot radius must be a positive finite value")
    map_x, map_y = _world_to_map(x, y, metadata)
    if (
        map_x - robot_radius_m < 0
        or map_y - robot_radius_m < 0
        or map_x + robot_radius_m > metadata.width_m
        or map_y + robot_radius_m > metadata.height_m
    ):
        raise RouteValidationError(
            f"{label} lacks {robot_radius_m:.3f}m map-edge clearance"
        )

    resolution = metadata.resolution_m
    minimum_column = max(0, math.floor((map_x - robot_radius_m) / resolution))
    maximum_column = min(
        metadata.width_px - 1,
        math.floor((map_x + robot_radius_m) / resolution),
    )
    minimum_row = max(0, math.floor((map_y - robot_radius_m) / resolution))
    maximum_row = min(
        metadata.height_px - 1,
        math.floor((map_y + robot_radius_m) / resolution),
    )
    radius_squared = robot_radius_m * robot_radius_m
    for row in range(minimum_row, maximum_row + 1):
        cell_bottom = row * resolution
        cell_top = cell_bottom + resolution
        nearest_y = min(max(map_y, cell_bottom), cell_top)
        for column in range(minimum_column, maximum_column + 1):
            cell_left = column * resolution
            cell_right = cell_left + resolution
            nearest_x = min(max(map_x, cell_left), cell_right)
            if (
                (map_x - nearest_x) ** 2 + (map_y - nearest_y) ** 2
                > radius_squared
            ):
                continue
            state = grid.cell_at(column, row)
            if state != FREE:
                state_name = "occupied" if state == OCCUPIED else "unknown"
                raise RouteValidationError(
                    f"{label} robot footprint intersects {state_name} map cell"
                )


def validate_route_clearance(
    route: Route,
    grid: OccupancyGrid,
    *,
    robot_radius_m: float,
) -> None:
    for waypoint in route.waypoints:
        validate_point_clearance(
            waypoint.x,
            waypoint.y,
            grid,
            robot_radius_m=robot_radius_m,
            label=f"waypoint {waypoint.sequence}",
        )


def _world_to_map(
    x: float,
    y: float,
    metadata: OccupancyMapMetadata,
) -> tuple[float, float]:
    cosine = math.cos(metadata.origin_yaw_rad)
    sine = math.sin(metadata.origin_yaw_rad)
    dx = x - metadata.origin_x
    dy = y - metadata.origin_y
    return cosine * dx + sine * dy, -sine * dx + cosine * dy


def _image_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as source:
        header = source.read(32)
    if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
        width, height = struct.unpack(">II", header[16:24])
    elif header.startswith((b"P5", b"P2")):
        _, width, height, _, _ = _pgm_header(path.read_bytes())
    else:
        raise RouteValidationError("map image must be PNG, P2 PGM or P5 PGM")
    if width <= 0 or height <= 0:
        raise RouteValidationError("map image dimensions must be positive")
    return width, height


def _read_pgm(path: Path) -> tuple[tuple[int, ...], int, int, int]:
    data = path.read_bytes()
    magic, width, height, maximum, offset = _pgm_header(data)
    count = width * height
    if magic == b"P2":
        values: list[int] = []
        cursor = offset
        while len(values) < count:
            token, cursor = _next_pgm_token(data, cursor)
            if token is None:
                raise RouteValidationError("PGM raster is shorter than declared")
            try:
                value = int(token)
            except ValueError as error:
                raise RouteValidationError("P2 PGM raster contains non-integer data") from error
            values.append(value)
    else:
        if offset >= len(data) or data[offset] not in b" \t\r\n\v\f":
            raise RouteValidationError("P5 PGM header lacks raster separator")
        if data[offset : offset + 2] == b"\r\n":
            offset += 2
        else:
            offset += 1
        bytes_per_sample = 1 if maximum < 256 else 2
        expected = count * bytes_per_sample
        raster = data[offset : offset + expected]
        if len(raster) != expected:
            raise RouteValidationError("PGM raster is shorter than declared")
        if bytes_per_sample == 1:
            values = list(raster)
        else:
            values = [
                int.from_bytes(raster[index : index + 2], "big")
                for index in range(0, len(raster), 2)
            ]
    if any(value < 0 or value > maximum for value in values):
        raise RouteValidationError("PGM raster sample exceeds max value")
    return tuple(values), maximum, width, height


def _pgm_header(data: bytes) -> tuple[bytes, int, int, int, int]:
    tokens: list[bytes] = []
    cursor = 0
    while len(tokens) < 4:
        token, cursor = _next_pgm_token(data, cursor)
        if token is None:
            raise RouteValidationError("PGM header is incomplete")
        tokens.append(token)
    magic = tokens[0]
    if magic not in (b"P2", b"P5"):
        raise RouteValidationError(
            "demo occupancy validation requires a P2 or P5 PGM map"
        )
    try:
        width, height, maximum = (int(value) for value in tokens[1:])
    except ValueError as error:
        raise RouteValidationError("PGM header contains invalid integers") from error
    if width <= 0 or height <= 0:
        raise RouteValidationError("map image dimensions must be positive")
    if not 1 <= maximum <= 65535:
        raise RouteValidationError("PGM max value must be within 1..65535")
    return magic, width, height, maximum, cursor


def _next_pgm_token(data: bytes, cursor: int) -> tuple[bytes | None, int]:
    whitespace = b" \t\r\n\v\f"
    while cursor < len(data):
        if data[cursor] in whitespace:
            cursor += 1
            continue
        if data[cursor] == ord("#"):
            newline = data.find(b"\n", cursor)
            cursor = len(data) if newline < 0 else newline + 1
            continue
        break
    if cursor >= len(data):
        return None, cursor
    start = cursor
    while (
        cursor < len(data)
        and data[cursor] not in whitespace
        and data[cursor] != ord("#")
    ):
        cursor += 1
    return data[start:cursor], cursor


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RouteValidationError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise RouteValidationError(f"{field} must be finite")
    return result
