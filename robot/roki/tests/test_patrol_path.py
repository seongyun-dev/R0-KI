from __future__ import annotations

import unittest

from navigation.patrol_path import (
    PatrolPathError,
    build_patrol_segment,
    resolve_waypoint_yaw_deg,
)
from navigation.route import parse_route


def route_with(waypoints):
    return parse_route(
        {
            "schema_version": 1,
            "map_id": "map-1",
            "map_version": 1,
            "route_id": "route-1",
            "frame_id": "map",
            "waypoints": waypoints,
        }
    )


class PatrolPathTest(unittest.TestCase):
    def test_current_route_uses_corner_bisector_and_incoming_destination_yaw(self):
        route = route_with(
            [
                {
                    "sequence": 1,
                    "x": 0.541,
                    "y": 0.930,
                    "yaw_deg": None,
                    "acceptance_radius_m": 0.3,
                    "action": "PASS",
                },
                {
                    "sequence": 2,
                    "x": 0.552,
                    "y": 1.666,
                    "yaw_deg": None,
                    "acceptance_radius_m": 0.3,
                    "action": "PASS",
                },
                {
                    "sequence": 3,
                    "x": -0.145,
                    "y": 1.765,
                    "yaw_deg": None,
                    "acceptance_radius_m": 0.3,
                    "action": "DESTINATION",
                },
            ]
        )

        segment = build_patrol_segment(route, 2)

        self.assertEqual([item.waypoint.sequence for item in segment], [2, 3])
        self.assertAlmostEqual(segment[0].yaw_deg, 130.53, places=2)
        self.assertAlmostEqual(segment[1].yaw_deg, 171.92, places=2)

    def test_scan_terminates_one_segment_and_next_segment_reaches_destination(self):
        route = route_with(
            [
                {"sequence": 1, "x": 0, "y": 0, "yaw_deg": None, "acceptance_radius_m": 0.1, "action": "PASS"},
                {"sequence": 2, "x": 1, "y": 0, "yaw_deg": None, "acceptance_radius_m": 0.1, "action": "PASS"},
                {"sequence": 3, "x": 2, "y": 1, "yaw_deg": None, "acceptance_radius_m": 0.1, "action": "SCAN"},
                {"sequence": 4, "x": 3, "y": 1, "yaw_deg": None, "acceptance_radius_m": 0.1, "action": "PASS"},
                {"sequence": 5, "x": 4, "y": 1, "yaw_deg": None, "acceptance_radius_m": 0.1, "action": "DESTINATION"},
            ]
        )

        self.assertEqual(
            [item.waypoint.sequence for item in build_patrol_segment(route, 2)],
            [2, 3],
        )
        self.assertEqual(
            [item.waypoint.sequence for item in build_patrol_segment(route, 4)],
            [4, 5],
        )

    def test_explicit_yaw_overrides_route_tangent(self):
        route = route_with(
            [
                {"sequence": 1, "x": 0, "y": 0, "yaw_deg": None, "acceptance_radius_m": 0.1, "action": "PASS"},
                {"sequence": 2, "x": 1, "y": 0, "yaw_deg": -45, "acceptance_radius_m": 0.1, "action": "PASS"},
                {"sequence": 3, "x": 1, "y": 1, "yaw_deg": None, "acceptance_radius_m": 0.1, "action": "DESTINATION"},
            ]
        )

        self.assertEqual(resolve_waypoint_yaw_deg(route.waypoints, 1), -45.0)

    def test_wrapped_corner_uses_short_angle_bisector(self):
        route = route_with(
            [
                {"sequence": 1, "x": 1.0, "y": -0.1763, "yaw_deg": None, "acceptance_radius_m": 0.05, "action": "PASS"},
                {"sequence": 2, "x": 0.0, "y": 0.0, "yaw_deg": None, "acceptance_radius_m": 0.05, "action": "PASS"},
                {"sequence": 3, "x": -1.0, "y": -0.1763, "yaw_deg": None, "acceptance_radius_m": 0.05, "action": "DESTINATION"},
            ]
        )

        self.assertAlmostEqual(
            abs(resolve_waypoint_yaw_deg(route.waypoints, 1)),
            180.0,
            places=1,
        )

    def test_exact_u_turn_fails_before_nav2_motion(self):
        route = route_with(
            [
                {"sequence": 1, "x": 0, "y": 0, "yaw_deg": None, "acceptance_radius_m": 0.1, "action": "PASS"},
                {"sequence": 2, "x": 1, "y": 0, "yaw_deg": None, "acceptance_radius_m": 0.1, "action": "PASS"},
                {"sequence": 3, "x": 0, "y": 0, "yaw_deg": None, "acceptance_radius_m": 0.1, "action": "DESTINATION"},
            ]
        )

        with self.assertRaisesRegex(PatrolPathError, "180-degree turn"):
            build_patrol_segment(route, 2)


if __name__ == "__main__":
    unittest.main()
