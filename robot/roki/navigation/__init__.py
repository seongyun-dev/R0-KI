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
    OccupancyGrid,
    OccupancyMapMetadata,
    file_sha256,
    load_map_metadata,
    load_occupancy_grid,
    map_bundle_sha256,
    validate_map_quality,
    validate_point_clearance,
    validate_route_clearance,
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
    "OccupancyGrid",
    "OccupancyMapMetadata",
    "Pose2D",
    "Route",
    "RouteValidationError",
    "Waypoint",
    "WaypointAction",
    "WaypointMission",
    "WaypointNavigationService",
    "file_sha256",
    "load_route",
    "load_map_metadata",
    "load_occupancy_grid",
    "map_bundle_sha256",
    "parse_route",
    "validate_map_quality",
    "validate_point_clearance",
    "validate_route_clearance",
    "validate_route_bounds",
    "validate_straight_encoder_route",
]
