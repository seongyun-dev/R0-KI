from __future__ import annotations

import copy
import unittest
from pathlib import Path

from navigation.route import RouteValidationError, WaypointAction, load_route, parse_route


EXAMPLE = {
    "schema_version": 1,
    "map_id": "map-1",
    "map_version": 1,
    "route_id": "route-1",
    "frame_id": "map",
    "waypoints": [
        {
            "sequence": 1,
            "name": "START",
            "x": 0.0,
            "y": 0.0,
            "yaw_deg": 0.0,
            "acceptance_radius_m": 0.3,
            "action": "PASS",
        },
        {
            "sequence": 2,
            "name": "DESTINATION",
            "x": 1.0,
            "y": 0.0,
            "yaw_deg": 0.0,
            "acceptance_radius_m": 0.2,
            "action": "DESTINATION",
        },
    ],
}


class RouteTest(unittest.TestCase):
    def test_repository_example_is_valid(self) -> None:
        path = Path(__file__).resolve().parents[1] / "config" / "route.example.yaml"
        route = load_route(path)
        self.assertEqual(route.frame_id, "map")
        self.assertEqual(route.waypoints[-1].action, WaypointAction.DESTINATION)

    def test_route_requires_contiguous_order_and_final_destination(self) -> None:
        invalid_sequence = copy.deepcopy(EXAMPLE)
        invalid_sequence["waypoints"][1]["sequence"] = 3
        with self.assertRaisesRegex(RouteValidationError, "contiguous"):
            parse_route(invalid_sequence)

        missing_destination = copy.deepcopy(EXAMPLE)
        missing_destination["waypoints"][1]["action"] = "PASS"
        with self.assertRaisesRegex(RouteValidationError, "DESTINATION"):
            parse_route(missing_destination)

    def test_rejects_invalid_action_radius_and_non_finite_coordinates(self) -> None:
        for field, value, message in (
            ("action", "TURN_IN_PLACE", "action"),
            ("acceptance_radius_m", 0.0, "acceptance_radius"),
            ("x", float("nan"), "finite"),
        ):
            raw = copy.deepcopy(EXAMPLE)
            raw["waypoints"][0][field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(RouteValidationError, message):
                    parse_route(raw)

    def test_rejects_overlapping_consecutive_acceptance_areas(self) -> None:
        raw = copy.deepcopy(EXAMPLE)
        raw["waypoints"][1]["x"] = 0.5

        with self.assertRaisesRegex(
            RouteValidationError,
            "acceptance areas must not overlap.*waypoint 1 -> 2",
        ):
            parse_route(raw)

        raw["waypoints"][1]["x"] = 0.5001
        self.assertEqual(parse_route(raw).waypoints[-1].x, 0.5001)

    def test_optional_yaw_preserves_none_and_explicit_local_yaml_value(self) -> None:
        raw = copy.deepcopy(EXAMPLE)
        del raw["waypoints"][0]["yaw_deg"]

        route = parse_route(raw)

        self.assertIsNone(route.waypoints[0].yaw_deg)
        self.assertEqual(route.waypoints[1].yaw_deg, 0.0)


if __name__ == "__main__":
    unittest.main()
