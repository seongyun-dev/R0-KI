from __future__ import annotations

import unittest

from control.line_follower import (
    LineFollower,
    LineFollowerSettings,
    LineFollowMode,
)


class LineFollowerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.follower = LineFollower(LineFollowerSettings())

    def test_center_left_and_right_patterns_are_bounded(self) -> None:
        center = self.follower.update((1, 1, 0, 1, 1))
        self.assertEqual(center.mode, LineFollowMode.FOLLOWING)
        self.assertEqual((center.speed_pwm, center.steering_deg), (45, 80))
        self.assertEqual(center.error, 0.0)

        left = self.follower.update((0, 1, 1, 1, 1))
        self.assertEqual((left.speed_pwm, left.steering_deg), (45, 60))
        self.assertEqual(left.error, -2.0)

        right = self.follower.update((1, 1, 1, 1, 0))
        self.assertEqual((right.speed_pwm, right.steering_deg), (45, 100))
        self.assertEqual(right.error, 2.0)

    def test_multiple_black_sensors_use_weighted_centroid(self) -> None:
        decision = self.follower.update((1, 1, 0, 0, 1))
        self.assertEqual(decision.error, 0.5)
        self.assertEqual(decision.steering_deg, 85)

    def test_missing_line_stops_on_first_frame_and_latches(self) -> None:
        pending = self.follower.update((1, 1, 1, 1, 1))
        self.assertEqual(pending.mode, LineFollowMode.LINE_LOST_PENDING)
        self.assertEqual(pending.speed_pwm, 0)

        lost = self.follower.update((1, 1, 1, 1, 1))
        self.assertEqual(lost.mode, LineFollowMode.LINE_LOST)
        self.assertEqual(lost.speed_pwm, 0)

        still_lost = self.follower.update((1, 1, 0, 1, 1))
        self.assertEqual(still_lost.mode, LineFollowMode.LINE_LOST)
        self.assertEqual(still_lost.speed_pwm, 0)

        self.follower.reset()
        recovered = self.follower.update((1, 1, 0, 1, 1))
        self.assertEqual(recovered.mode, LineFollowMode.FOLLOWING)

    def test_destination_requires_arming_and_consecutive_frames(self) -> None:
        marker = (0, 0, 0, 0, 1)
        for _ in range(10):
            decision = self.follower.update((1, 1, 0, 1, 1))
            self.assertEqual(decision.mode, LineFollowMode.FOLLOWING)

        first = self.follower.update(marker)
        second = self.follower.update(marker)
        destination = self.follower.update(marker)
        self.assertEqual(first.mode, LineFollowMode.DESTINATION_PENDING)
        self.assertEqual(second.mode, LineFollowMode.DESTINATION_PENDING)
        self.assertEqual(destination.mode, LineFollowMode.DESTINATION)
        self.assertEqual(first.speed_pwm, 0)
        self.assertEqual(destination.speed_pwm, 0)

    def test_destination_can_be_disabled_for_initial_track_test(self) -> None:
        follower = LineFollower(
            LineFollowerSettings(destination_min_black_sensors=0)
        )
        decision = follower.update((0, 0, 0, 0, 0))
        self.assertEqual(decision.mode, LineFollowMode.FOLLOWING)
        self.assertEqual(decision.steering_deg, 80)

    def test_reverse_steering_sign_is_configurable(self) -> None:
        follower = LineFollower(LineFollowerSettings(steering_sign=-1))
        decision = follower.update((1, 1, 1, 1, 0))
        self.assertEqual(decision.steering_deg, 60)

    def test_invalid_values_and_settings_are_rejected(self) -> None:
        for values in ((1, 1, 1), (1, 1, 2, 1, 1), (1, 1, True, 1, 1)):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.follower.update(values)

        with self.assertRaises(ValueError):
            LineFollowerSettings(drive_speed_pwm=52)
        with self.assertRaises(ValueError):
            LineFollowerSettings(steering_sign=0)


if __name__ == "__main__":
    unittest.main()
