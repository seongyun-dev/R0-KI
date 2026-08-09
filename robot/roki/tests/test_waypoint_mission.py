from __future__ import annotations

import unittest

from navigation.route import parse_route
from navigation.waypoint_mission import (
    MissionEventType,
    MissionState,
    Pose2D,
    WaypointMission,
)


def route():
    return parse_route(
        {
            "schema_version": 1,
            "map_id": "map-1",
            "map_version": 1,
            "route_id": "route-1",
            "frame_id": "map",
            "waypoints": [
                {
                    "sequence": 1,
                    "x": 1.0,
                    "y": 0.0,
                    "yaw_deg": 0.0,
                    "acceptance_radius_m": 0.2,
                    "action": "PASS",
                },
                {
                    "sequence": 2,
                    "x": 2.0,
                    "y": 0.0,
                    "yaw_deg": 0.0,
                    "acceptance_radius_m": 0.2,
                    "action": "SCAN",
                },
                {
                    "sequence": 3,
                    "x": 3.0,
                    "y": 0.0,
                    "yaw_deg": 0.0,
                    "acceptance_radius_m": 0.2,
                    "action": "DESTINATION",
                },
            ],
        }
    )


class WaypointMissionTest(unittest.TestCase):
    def test_progresses_pass_scan_and_destination(self) -> None:
        mission = WaypointMission()
        start = mission.start(route())
        self.assertEqual(start.event_type, MissionEventType.STARTED)
        self.assertEqual(mission.current_waypoint.sequence, 1)  # type: ignore[union-attr]
        self.assertEqual(mission.update_pose(Pose2D(0.0, 0.0)), ())

        first = mission.update_pose(Pose2D(0.9, 0.0))
        self.assertEqual([event.event_type for event in first], [MissionEventType.WAYPOINT_REACHED])
        scan = mission.update_pose(Pose2D(2.0, 0.0))
        self.assertEqual(
            [event.event_type for event in scan],
            [MissionEventType.WAYPOINT_REACHED, MissionEventType.ACTION_REQUIRED],
        )
        destination = mission.update_pose(Pose2D(3.1, 0.0))
        self.assertEqual(
            [event.event_type for event in destination],
            [MissionEventType.WAYPOINT_REACHED, MissionEventType.DESTINATION_REACHED],
        )
        self.assertEqual(mission.state, MissionState.COMPLETED)
        self.assertIsNone(mission.current_waypoint)

    def test_stop_latches_until_a_new_start(self) -> None:
        mission = WaypointMission()
        mission.start(route())
        event = mission.stop()
        self.assertEqual(event.event_type, MissionEventType.STOPPED)  # type: ignore[union-attr]
        self.assertEqual(mission.state, MissionState.STOPPED)
        self.assertEqual(mission.update_pose(Pose2D(1.0, 0.0)), ())
        mission.start(route())
        self.assertEqual(mission.state, MissionState.RUNNING)


if __name__ == "__main__":
    unittest.main()
