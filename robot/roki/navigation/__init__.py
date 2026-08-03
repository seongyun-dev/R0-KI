"""Hardware-independent waypoint navigation primitives."""

from navigation.cmd_vel_adapter import (
    AckermannCommandSettings,
    CmdVelCommand,
    CmdVelToEsp32Adapter,
    MemoryControlTransport,
)
from navigation.encoder_waypoint import (
    EncoderWaypointError,
    EncoderWaypointProgress,
    EncoderWaypointSettings,
    validate_straight_encoder_route,
)
from navigation.map_metadata import (
    OccupancyMapMetadata,
    load_map_metadata,
    validate_route_bounds,
)
from navigation.route import (
    Route,
    RouteValidationError,
    Waypoint,
    WaypointAction,
    load_route,
    parse_route,
)
from navigation.service import NavigationEvent, WaypointNavigationService
from navigation.waypoint_mission import (
    MissionEvent,
    MissionEventType,
    MissionState,
    Pose2D,
    WaypointMission,
)

__all__ = [
    "AckermannCommandSettings",
    "CmdVelCommand",
    "CmdVelToEsp32Adapter",
    "EncoderWaypointError",
    "EncoderWaypointProgress",
    "EncoderWaypointSettings",
    "MemoryControlTransport",
    "MissionEvent",
    "MissionEventType",
    "MissionState",
    "NavigationEvent",
    "OccupancyMapMetadata",
    "Pose2D",
    "Route",
    "RouteValidationError",
    "Waypoint",
    "WaypointAction",
    "WaypointMission",
    "WaypointNavigationService",
    "load_route",
    "load_map_metadata",
    "parse_route",
    "validate_route_bounds",
    "validate_straight_encoder_route",
]
