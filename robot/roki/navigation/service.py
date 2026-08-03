"""Thread-safe facade joining a fixed Route with pose updates."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from navigation.route import Route
from navigation.waypoint_mission import MissionEvent, MissionState, Pose2D, WaypointMission


@dataclass(frozen=True)
class NavigationEvent:
    patrol_id: int
    mission_event: MissionEvent


NavigationEventListener = Callable[[NavigationEvent], None]


class WaypointNavigationService:
    """Own one local route and publish deterministic mission progress events."""

    def __init__(self, route: Route) -> None:
        self._route = route
        self._mission = WaypointMission()
        self._patrol_id: int | None = None
        self._listeners: list[NavigationEventListener] = []
        self._lock = threading.Lock()

    @property
    def state(self) -> MissionState:
        with self._lock:
            return self._mission.state

    @property
    def route(self) -> Route:
        return self._route

    @property
    def patrol_id(self) -> int | None:
        with self._lock:
            return self._patrol_id

    def add_event_listener(self, listener: NavigationEventListener) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def start_patrol(self, *, patrol_id: int | None) -> NavigationEvent:
        if isinstance(patrol_id, bool) or not isinstance(patrol_id, int) or patrol_id <= 0:
            raise ValueError("patrol_id must be a positive integer")
        with self._lock:
            if self._mission.state is MissionState.RUNNING:
                raise RuntimeError("waypoint mission is already running")
            self._patrol_id = patrol_id
            event = NavigationEvent(patrol_id, self._mission.start(self._route))
            listeners = tuple(self._listeners)
        self._notify(listeners, (event,))
        return event

    def stop_patrol(self) -> NavigationEvent | None:
        with self._lock:
            patrol_id = self._patrol_id
            if patrol_id is None:
                return None
            mission_event = self._mission.stop()
            self._patrol_id = None
            listeners = tuple(self._listeners)
        if mission_event is None:
            return None
        event = NavigationEvent(patrol_id, mission_event)
        self._notify(listeners, (event,))
        return event

    def update_pose(self, pose: Pose2D) -> tuple[NavigationEvent, ...]:
        with self._lock:
            patrol_id = self._patrol_id
            if patrol_id is None:
                return ()
            mission_events = self._mission.update_pose(pose)
            events = tuple(
                NavigationEvent(patrol_id, mission_event)
                for mission_event in mission_events
            )
            if self._mission.state is MissionState.COMPLETED:
                self._patrol_id = None
            listeners = tuple(self._listeners)
        self._notify(listeners, events)
        return events

    @staticmethod
    def _notify(
        listeners: tuple[NavigationEventListener, ...],
        events: tuple[NavigationEvent, ...],
    ) -> None:
        for event in events:
            for listener in listeners:
                listener(event)
