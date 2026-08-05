"""Validated local route contract for a fixed waypoint patrol."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class RouteValidationError(ValueError):
    """Raised when a route cannot be executed safely."""


class WaypointAction(str, Enum):
    PASS = "PASS"
    SCAN = "SCAN"
    DESTINATION = "DESTINATION"


@dataclass(frozen=True)
class Waypoint:
    sequence: int
    name: str
    x: float
    y: float
    # ``None`` means that the execution bridge must derive a heading from the
    # route geometry.  Existing local YAML files with an explicit yaw remain
    # byte-for-byte compatible and keep their exact behavior.
    yaw_deg: float | None
    acceptance_radius_m: float
    action: WaypointAction
    zone_id: int | None = None


@dataclass(frozen=True)
class Route:
    schema_version: int
    map_id: str
    map_version: int
    route_id: str
    frame_id: str
    waypoints: tuple[Waypoint, ...]


def load_route(path: str | Path) -> Route:
    import yaml

    route_path = Path(path)
    with route_path.open("r", encoding="utf-8") as source:
        raw = yaml.safe_load(source)
    if not isinstance(raw, Mapping):
        raise RouteValidationError("route YAML root must be an object")
    return parse_route(raw)


def parse_route(raw: Mapping[str, Any]) -> Route:
    schema_version = _integer(raw.get("schema_version"), "schema_version")
    if schema_version != 1:
        raise RouteValidationError("schema_version must be 1")

    map_id = _nonempty_text(raw.get("map_id"), "map_id", allow_integer=True)
    map_version = _integer(raw.get("map_version"), "map_version")
    if map_version <= 0:
        raise RouteValidationError("map_version must be positive")
    route_id = _nonempty_text(raw.get("route_id"), "route_id")
    frame_id = _nonempty_text(raw.get("frame_id"), "frame_id")
    if frame_id != "map":
        raise RouteValidationError("frame_id must be map")

    raw_waypoints = raw.get("waypoints")
    if not isinstance(raw_waypoints, list) or not raw_waypoints:
        raise RouteValidationError("waypoints must be a non-empty list")
    waypoints = tuple(
        _parse_waypoint(item, index=index)
        for index, item in enumerate(raw_waypoints, start=1)
    )
    sequences = [waypoint.sequence for waypoint in waypoints]
    if sequences != list(range(1, len(waypoints) + 1)):
        raise RouteValidationError(
            "waypoint sequence must be ordered and contiguous from 1"
        )
    destinations = [
        waypoint
        for waypoint in waypoints
        if waypoint.action is WaypointAction.DESTINATION
    ]
    if len(destinations) != 1 or waypoints[-1].action is not WaypointAction.DESTINATION:
        raise RouteValidationError(
            "route must contain exactly one final DESTINATION waypoint"
        )
    for previous, current in zip(waypoints, waypoints[1:]):
        distance = math.hypot(current.x - previous.x, current.y - previous.y)
        minimum_separation = (
            previous.acceptance_radius_m + current.acceptance_radius_m
        )
        if distance <= minimum_separation:
            raise RouteValidationError(
                "consecutive waypoint acceptance areas must not overlap: "
                f"waypoint {previous.sequence} -> {current.sequence} "
                f"distance {distance:.3f}m <= {minimum_separation:.3f}m"
            )
    return Route(
        schema_version,
        map_id,
        map_version,
        route_id,
        frame_id,
        waypoints,
    )


def _parse_waypoint(raw: Any, *, index: int) -> Waypoint:
    if not isinstance(raw, Mapping):
        raise RouteValidationError(f"waypoint {index} must be an object")
    sequence = _integer(raw.get("sequence"), f"waypoint {index} sequence")
    name = _nonempty_text(
        raw.get("name", f"WAYPOINT_{sequence}"),
        f"waypoint {index} name",
    )
    x = _finite_number(raw.get("x"), f"waypoint {index} x")
    y = _finite_number(raw.get("y"), f"waypoint {index} y")
    raw_yaw_deg = raw.get("yaw_deg")
    yaw_deg = (
        None
        if raw_yaw_deg is None
        else _finite_number(raw_yaw_deg, f"waypoint {index} yaw_deg")
    )
    radius = _finite_number(
        raw.get("acceptance_radius_m"),
        f"waypoint {index} acceptance_radius_m",
    )
    if not 0.01 <= radius <= 5.0:
        raise RouteValidationError(
            f"waypoint {index} acceptance_radius_m must be 0.01..5.0"
        )
    action_text = _nonempty_text(raw.get("action"), f"waypoint {index} action")
    try:
        action = WaypointAction(action_text.upper())
    except ValueError as error:
        raise RouteValidationError(
            f"waypoint {index} action must be PASS, SCAN or DESTINATION"
        ) from error
    zone_id = raw.get("zone_id")
    if zone_id is not None:
        zone_id = _integer(zone_id, f"waypoint {index} zone_id")
        if zone_id <= 0:
            raise RouteValidationError(
                f"waypoint {index} zone_id must be positive"
            )
    return Waypoint(sequence, name, x, y, yaw_deg, radius, action, zone_id)


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RouteValidationError(f"{field} must be an integer")
    return value


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RouteValidationError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise RouteValidationError(f"{field} must be finite")
    return result


def _nonempty_text(value: Any, field: str, *, allow_integer: bool = False) -> str:
    if allow_integer and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, str) or not value.strip():
        raise RouteValidationError(f"{field} must be a non-empty string")
    return value.strip()
