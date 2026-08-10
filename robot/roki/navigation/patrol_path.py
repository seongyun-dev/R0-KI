"""Build continuous, curvature-friendly waypoint segments for Nav2 patrols."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


class PatrolPathError(ValueError):
    """Raised when route geometry cannot define a safe continuous heading."""


@dataclass(frozen=True)
class PatrolSegmentPose:
    waypoint: Any
    yaw_deg: float


def build_patrol_segment(route: Any, start_sequence: int) -> tuple[PatrolSegmentPose, ...]:
    """Return the remaining continuous segment ending at SCAN or DESTINATION.

    PASS waypoints remain inside one Nav2 action so the Ackermann chassis can
    follow a continuous curve.  SCAN and DESTINATION terminate a segment since
    they require a deliberate stop in the mission layer.
    """

    waypoints = tuple(getattr(route, "waypoints", ()) or ())
    if not waypoints:
        raise PatrolPathError("route has no waypoints")
    if not 1 <= int(start_sequence) <= len(waypoints):
        raise PatrolPathError("segment start sequence is outside the route")

    segment: list[PatrolSegmentPose] = []
    for index in range(int(start_sequence) - 1, len(waypoints)):
        waypoint = waypoints[index]
        segment.append(
            PatrolSegmentPose(
                waypoint=waypoint,
                yaw_deg=resolve_waypoint_yaw_deg(waypoints, index),
            )
        )
        action = getattr(getattr(waypoint, "action", None), "value", None)
        if action is None:
            action = str(getattr(waypoint, "action", ""))
        if action in {"SCAN", "DESTINATION"}:
            break

    if not segment:
        raise PatrolPathError("route segment is empty")
    return tuple(segment)


def resolve_waypoint_yaw_deg(waypoints: tuple[Any, ...], index: int) -> float:
    """Resolve a route-tangent heading for one hard pose constraint.

    An explicit backend yaw always wins.  Otherwise an intermediate waypoint
    uses the angle bisector of its incoming and outgoing unit vectors.  This
    asks Hybrid-A* to pass through a corner on one continuous Ackermann curve,
    instead of arriving already aligned with only the outgoing edge.
    """

    waypoint = waypoints[index]
    explicit = getattr(waypoint, "yaw_deg", None)
    if explicit is not None:
        yaw = float(explicit)
        if not math.isfinite(yaw):
            raise PatrolPathError(f"waypoint {index + 1} yaw is not finite")
        return _normalize_degrees(yaw)

    if len(waypoints) < 2:
        raise PatrolPathError("a null-yaw route requires at least two waypoints")
    if index == 0:
        return _edge_heading_deg(waypoints[0], waypoints[1], index + 1)
    if index == len(waypoints) - 1:
        return _edge_heading_deg(waypoints[index - 1], waypoint, index + 1)

    incoming = _unit_vector(waypoints[index - 1], waypoint, index + 1)
    outgoing = _unit_vector(waypoint, waypoints[index + 1], index + 1)
    tangent_x = incoming[0] + outgoing[0]
    tangent_y = incoming[1] + outgoing[1]
    if math.hypot(tangent_x, tangent_y) <= 1e-9:
        raise PatrolPathError(
            f"waypoint {index + 1} makes a 180-degree turn; "
            "add curvature-feasible intermediate waypoints"
        )
    return _normalize_degrees(math.degrees(math.atan2(tangent_y, tangent_x)))


def _edge_heading_deg(start: Any, end: Any, sequence: int) -> float:
    vector = _unit_vector(start, end, sequence)
    return _normalize_degrees(math.degrees(math.atan2(vector[1], vector[0])))


def _unit_vector(start: Any, end: Any, sequence: int) -> tuple[float, float]:
    dx = float(end.x) - float(start.x)
    dy = float(end.y) - float(start.y)
    length = math.hypot(dx, dy)
    if not math.isfinite(length) or length <= 1e-9:
        raise PatrolPathError(
            f"waypoint {sequence} has zero-length route geometry"
        )
    return dx / length, dy / length


def _normalize_degrees(value: float) -> float:
    normalized = (float(value) + 180.0) % 360.0 - 180.0
    return 180.0 if normalized == -180.0 else normalized
