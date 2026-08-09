from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


HARDWARE_ROOT = Path(__file__).resolve().parents[1] / "hardware"
sys.path.insert(0, str(HARDWARE_ROOT))

from odom_waypoint_field_test import (  # noqa: E402
    FieldTestError,
    TICKS_PER_REVOLUTION,
    WHEEL_DIAMETER_M,
    encoder_metres,
    interpolated_progress,
    validate_hardware,
    validate_straight_route,
)
from navigation.route import parse_route  # noqa: E402
from navigation.route import load_route  # noqa: E402
from navigation.service import WaypointNavigationService  # noqa: E402
from navigation.waypoint_mission import MissionEventType, Pose2D  # noqa: E402


def route_with_destination(x: float = 1.6, y: float = 2.5):
    return parse_route(
        {
            "schema_version": 1,
            "map_id": "dummy-rectangle",
            "map_version": 1,
            "route_id": "test-route",
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


class OdomWaypointFieldTest(unittest.TestCase):
    def test_one_revolution_uses_measured_wheel_constants(self) -> None:
        self.assertAlmostEqual(
            encoder_metres(int(TICKS_PER_REVOLUTION)),
            math.pi * WHEEL_DIAMETER_M,
        )

    def test_interpolation_cannot_skip_a_small_acceptance_radius(self) -> None:
        samples = interpolated_progress(0.0, 0.2)
        self.assertLessEqual(
            max(b - a for a, b in zip((0.0, *samples), samples)),
            0.0100001,
        )
        self.assertAlmostEqual(samples[-1], 0.2)

    def test_accepts_only_short_straight_positive_x_route(self) -> None:
        self.assertAlmostEqual(validate_straight_route(route_with_destination()), 0.6)
        for route in (
            route_with_destination(x=0.9),
            route_with_destination(x=2.0),
            route_with_destination(y=2.6),
        ):
            with self.subTest(route=route):
                with self.assertRaises(FieldTestError):
                    validate_straight_route(route)

    def test_hardware_validation_does_not_depend_on_line_sensor(self) -> None:
        payload = {
            "type": "hardwareStatus",
            "motor": "NORMAL",
            "lineSensor": "DISCONNECTED",
            "batteryVoltage": 12.4,
        }
        self.assertEqual(validate_hardware(payload), 12.4)
        for override in (
            {"motor": "FAULT"},
            {"batteryVoltage": 0.71},
            {"batteryVoltage": 13.1},
        ):
            unsafe = {**payload, **override}
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(FieldTestError):
                    validate_hardware(unsafe)

    def test_checked_in_route_emits_scan_then_destination(self) -> None:
        route_path = (
            Path(__file__).resolve().parents[1]
            / "roki"
            / "maps"
            / "dummy_rectangle"
            / "route.short-straight.yaml"
        )
        service = WaypointNavigationService(load_route(route_path))
        service.start_patrol(patrol_id=1)
        emitted: list[MissionEventType] = []
        previous = 0.0
        for distance in (0.24, 0.44, 0.64):
            for progress in interpolated_progress(previous, distance):
                emitted.extend(
                    event.mission_event.event_type
                    for event in service.update_pose(
                        Pose2D(1.0 + progress, 2.5, 0.0)
                    )
                )
            previous = distance
        self.assertEqual(
            emitted,
            [
                MissionEventType.WAYPOINT_REACHED,
                MissionEventType.WAYPOINT_REACHED,
                MissionEventType.ACTION_REQUIRED,
                MissionEventType.WAYPOINT_REACHED,
                MissionEventType.DESTINATION_REACHED,
            ],
        )


if __name__ == "__main__":
    unittest.main()
