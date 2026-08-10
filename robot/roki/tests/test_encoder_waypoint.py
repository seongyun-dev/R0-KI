from __future__ import annotations

import unittest

from navigation.encoder_waypoint import (
    EncoderWaypointError,
    EncoderWaypointProgress,
    EncoderWaypointSettings,
    validate_straight_encoder_route,
)
from navigation.route import parse_route


def destination_route(*, x: float = 1.6, y: float = 2.5):
    return parse_route(
        {
            "schema_version": 1,
            "map_id": "dummy-rectangle",
            "map_version": 1,
            "route_id": "short-route",
            "frame_id": "map",
            "waypoints": [
                {
                    "sequence": 1,
                    "name": "DESTINATION",
                    "x": x,
                    "y": y,
                    "yaw_deg": 0.0,
                    "acceptance_radius_m": 0.04,
                    "action": "DESTINATION",
                }
            ],
        }
    )


class EncoderWaypointTest(unittest.TestCase):
    def test_validates_only_short_straight_route(self) -> None:
        settings = EncoderWaypointSettings()
        self.assertAlmostEqual(
            validate_straight_encoder_route(destination_route(), settings),
            0.6,
        )
        for route in (
            destination_route(x=0.9),
            destination_route(x=2.0),
            destination_route(y=2.6),
        ):
            with self.subTest(route=route):
                with self.assertRaises(EncoderWaypointError):
                    validate_straight_encoder_route(route, settings)

    def test_logical_zero_and_interpolation_return_map_poses(self) -> None:
        progress = EncoderWaypointProgress(EncoderWaypointSettings())
        progress.start(left_distance_m=2.0, right_distance_m=3.0)

        poses = progress.update(left_distance_m=2.2, right_distance_m=3.2)

        self.assertGreaterEqual(len(poses), 20)
        self.assertAlmostEqual(poses[-1].x, 1.2)
        self.assertAlmostEqual(poses[-1].y, 2.5)
        self.assertTrue(progress.active)
        progress.stop()
        self.assertEqual(
            progress.update(left_distance_m=2.3, right_distance_m=3.3),
            (),
        )

    def test_reverse_disagreement_and_overrun_fail_closed(self) -> None:
        scenarios = (
            (-0.03, -0.03),
            (0.20, 0.00),
            (0.71, 0.71),
        )
        for left, right in scenarios:
            with self.subTest(left=left, right=right):
                progress = EncoderWaypointProgress(EncoderWaypointSettings())
                progress.start(left_distance_m=0.0, right_distance_m=0.0)
                with self.assertRaises(EncoderWaypointError):
                    progress.update(
                        left_distance_m=left,
                        right_distance_m=right,
                    )


if __name__ == "__main__":
    unittest.main()
