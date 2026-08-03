from __future__ import annotations

import math
import unittest

from safety.obstacle_guard import (
    STOP_REASON_MESSAGE,
    FrontObstacleDetector,
    ObstacleDetectorSettings,
)


class FrontObstacleDetectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = FrontObstacleDetector(
            ObstacleDetectorSettings(
                front_angle_deg=30.0,
                stop_distance_m=0.6,
                clear_distance_m=0.7,
            )
        )

    def evaluate(self, ranges: list[float]):
        return self.detector.evaluate_scan(
            ranges=ranges,
            angle_min_rad=math.radians(-90),
            angle_increment_rad=math.radians(10),
            range_min_m=0.12,
            range_max_m=12.0,
        )

    @staticmethod
    def clear_scan() -> list[float]:
        return [1.0] * 19

    def test_one_meter_is_clear_and_contract_fields_are_exact(self) -> None:
        detection = self.evaluate(self.clear_scan())

        self.assertEqual(detection.obstacle.status, "CLEAR")
        self.assertEqual(detection.obstacle.direction, "NONE")
        self.assertIsNone(detection.obstacle.reason_message)
        self.assertEqual(detection.front_distance_m, 1.0)
        self.assertEqual(detection.stop_distance_m, 0.6)

    def test_close_front_obstacle_is_stop(self) -> None:
        ranges = self.clear_scan()
        ranges[9] = 0.4

        detection = self.evaluate(ranges)

        self.assertEqual(detection.obstacle.status, "STOP")
        self.assertEqual(detection.obstacle.direction, "FRONT")
        self.assertEqual(
            detection.obstacle.reason_message,
            STOP_REASON_MESSAGE,
        )

    def test_hysteresis_holds_stop_then_clears_at_clear_distance(self) -> None:
        ranges = self.clear_scan()
        ranges[9] = 0.4
        self.evaluate(ranges)

        ranges[9] = 0.65
        self.assertEqual(self.evaluate(ranges).obstacle.status, "STOP")

        ranges[9] = 0.7
        cleared = self.evaluate(ranges).obstacle
        self.assertEqual(cleared.status, "CLEAR")
        self.assertEqual(cleared.direction, "NONE")
        self.assertIsNone(cleared.reason_message)

    def test_side_obstacle_outside_sector_is_ignored(self) -> None:
        ranges = self.clear_scan()
        ranges[13] = 0.2  # +40 degrees

        self.assertEqual(self.evaluate(ranges).obstacle.status, "CLEAR")

    def test_invalid_ranges_are_ignored_and_previous_state_is_kept(self) -> None:
        stopped = self.clear_scan()
        stopped[9] = 0.4
        self.evaluate(stopped)

        invalid = [math.nan, math.inf, 0.0] * 6 + [math.nan]
        detection = self.evaluate(invalid)

        self.assertIsNone(detection.front_distance_m)
        self.assertEqual(detection.obstacle.status, "STOP")

    def test_invalid_ranges_do_not_invent_initial_stop(self) -> None:
        invalid = [math.nan, math.inf, 0.0] * 6 + [math.nan]

        self.assertEqual(self.evaluate(invalid).obstacle.status, "CLEAR")


if __name__ == "__main__":
    unittest.main()
