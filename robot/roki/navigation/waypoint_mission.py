"""Pose-driven waypoint progress without ROS, MQTT or Serial dependencies."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from navigation.route import Route, Waypoint, WaypointAction


class MissionState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"


class MissionEventType(str, Enum):
    STARTED = "STARTED"
    WAYPOINT_REACHED = "WAYPOINT_REACHED"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    DESTINATION_REACHED = "DESTINATION_REACHED"
    STOPPED = "STOPPED"


@dataclass(frozen=True)
class Pose2D:
    x: float
    y: float
    yaw_deg: float = 0.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.x, self.y, self.yaw_deg)):
            raise ValueError("pose values must be finite")


@dataclass(frozen=True)
class MissionEvent:
    event_type: MissionEventType
    waypoint: Waypoint | None


class WaypointMission:
    def __init__(self) -> None:
        self._route: Route | None = None
        self._state = MissionState.IDLE
        self._target_index = 0

    @property
    def state(self) -> MissionState:
        return self._state

    @property
    def route(self) -> Route | None:
        return self._route

    @property
    def current_waypoint(self) -> Waypoint | None:
        if (
            self._state is not MissionState.RUNNING
            or self._route is None
            or self._target_index >= len(self._route.waypoints)
        ):
            return None
        return self._route.waypoints[self._target_index]

    def start(self, route: Route) -> MissionEvent:
        self._route = route
        self._target_index = 0
        self._state = MissionState.RUNNING
        return MissionEvent(MissionEventType.STARTED, self.current_waypoint)

    def stop(self) -> MissionEvent | None:
        if self._state is not MissionState.RUNNING:
            return None
        waypoint = self.current_waypoint
        self._state = MissionState.STOPPED
        return MissionEvent(MissionEventType.STOPPED, waypoint)

    def update_pose(self, pose: Pose2D) -> tuple[MissionEvent, ...]:
        target = self.current_waypoint
        if target is None:
            return ()
        distance = math.hypot(pose.x - target.x, pose.y - target.y)
        if distance > target.acceptance_radius_m:
            return ()

        events = [
            MissionEvent(MissionEventType.WAYPOINT_REACHED, target),
        ]
        if target.action is WaypointAction.DESTINATION:
            self._state = MissionState.COMPLETED
            self._target_index += 1
            events.append(
                MissionEvent(MissionEventType.DESTINATION_REACHED, target)
            )
            return tuple(events)
        if target.action is WaypointAction.SCAN:
            events.append(MissionEvent(MissionEventType.ACTION_REQUIRED, target))
        self._target_index += 1
        return tuple(events)
