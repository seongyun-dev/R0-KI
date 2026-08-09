from __future__ import annotations

import unittest

from navigation.route import parse_route
from navigation.service import WaypointNavigationService
from navigation.waypoint_mission import MissionEventType, MissionState, Pose2D


def destination_route():
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
                    "action": "DESTINATION",
                }
            ],
        }
    )


class NavigationServiceTest(unittest.TestCase):
    def test_confirm_start_anchor_completes_single_start_destination(self) -> None:
        service = WaypointNavigationService(destination_route())
        service.start_patrol(patrol_id=7)

        events = service.confirm_start_anchor()

        self.assertEqual(
            [event.mission_event.event_type for event in events],
            [
                MissionEventType.WAYPOINT_REACHED,
                MissionEventType.DESTINATION_REACHED,
            ],
        )
        self.assertEqual(service.state, MissionState.COMPLETED)

    def test_start_pose_destination_and_completion_events(self) -> None:
        service = WaypointNavigationService(destination_route())
        received = []
        service.add_event_listener(received.append)
        service.start_patrol(patrol_id=17)
        self.assertEqual(service.state, MissionState.RUNNING)
        self.assertEqual(service.patrol_id, 17)

        events = service.update_pose(Pose2D(1.0, 0.0))
        self.assertEqual(
            [event.mission_event.event_type for event in events],
            [MissionEventType.WAYPOINT_REACHED, MissionEventType.DESTINATION_REACHED],
        )
        self.assertEqual(service.state, MissionState.COMPLETED)
        self.assertIsNone(service.patrol_id)
        self.assertEqual(len(received), 3)

    def test_rejects_missing_patrol_id_and_duplicate_start(self) -> None:
        service = WaypointNavigationService(destination_route())
        with self.assertRaisesRegex(ValueError, "patrol_id"):
            service.start_patrol(patrol_id=None)
        service.start_patrol(patrol_id=1)
        with self.assertRaisesRegex(RuntimeError, "already running"):
            service.start_patrol(patrol_id=2)
        stopped = service.stop_patrol()
        self.assertEqual(
            stopped.mission_event.event_type, MissionEventType.STOPPED  # type: ignore[union-attr]
        )
        self.assertEqual(service.state, MissionState.STOPPED)


if __name__ == "__main__":
    unittest.main()
