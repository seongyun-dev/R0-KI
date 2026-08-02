#!/usr/bin/env python3
"""Exercise map/route/mission completion without ROS, Serial or motors."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from navigation.map_metadata import load_map_metadata, validate_route_bounds
from navigation.route import load_route
from navigation.service import WaypointNavigationService
from navigation.waypoint_mission import MissionState, Pose2D


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--patrol-id", type=int, default=1)
    args = parser.parse_args()

    metadata = load_map_metadata(args.map)
    route = load_route(args.route)
    validate_route_bounds(route, metadata)
    service = WaypointNavigationService(route)
    service.add_event_listener(
        lambda event: print(
            f"patrol={event.patrol_id} "
            f"event={event.mission_event.event_type.value} "
            f"waypoint={getattr(event.mission_event.waypoint, 'name', None)}"
        )
    )
    service.start_patrol(patrol_id=args.patrol_id)
    for waypoint in route.waypoints:
        service.update_pose(Pose2D(waypoint.x, waypoint.y, waypoint.yaw_deg))
    if service.state is not MissionState.COMPLETED:
        raise RuntimeError(f"dry-run did not complete: {service.state.value}")
    print("DUMMY_WAYPOINT_DRY_RUN_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
