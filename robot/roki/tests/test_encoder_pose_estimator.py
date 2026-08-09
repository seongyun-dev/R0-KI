from __future__ import annotations

import math
import unittest

from control.motion_controller import MotionState
from localization.encoder_pose_estimator import (
    EncoderPoseEstimator,
    EncoderPoseEstimatorSettings,
)


def motion(distance_m: float | None) -> MotionState:
    return MotionState(0, 0, 0, 0.0, 0.0, 0.0, distance_m, distance_m, distance_m)


class EncoderPoseEstimatorTest(unittest.TestCase):
    def test_initial_pose_and_first_sample_are_baseline_only(self) -> None:
        estimator = EncoderPoseEstimator(EncoderPoseEstimatorSettings(80))
        self.assertEqual((estimator.pose.x_m, estimator.pose.y_m), (0.0, 0.0))

        pose = estimator.update(motion(1.5), steering_command=80, timestamp=1.0)

        self.assertEqual((pose.x_m, pose.y_m, pose.heading_rad), (0.0, 0.0, 0.0))

    def test_forward_and_reverse_one_calibrated_revolution(self) -> None:
        circumference = math.pi * 0.065
        estimator = EncoderPoseEstimator(EncoderPoseEstimatorSettings(80))
        estimator.update(motion(0.0), steering_command=80, timestamp=1.0)

        forward = estimator.update(
            motion(circumference), steering_command=80, timestamp=2.0
        )
        reverse = estimator.update(motion(0.0), steering_command=80, timestamp=3.0)

        self.assertAlmostEqual(forward.x_m, 0.20420352248333656)
        self.assertAlmostEqual(reverse.x_m, 0.0)
        self.assertEqual(reverse.heading_rad, 0.0)

    def test_baseline_reset_does_not_reset_or_jump_pose(self) -> None:
        estimator = EncoderPoseEstimator(EncoderPoseEstimatorSettings(80))
        estimator.update(motion(0.0), steering_command=80, timestamp=1.0)
        before = estimator.update(motion(0.2), steering_command=80, timestamp=2.0)

        estimator.reset_baseline()
        after = estimator.update(motion(0.0), steering_command=80, timestamp=3.0)

        self.assertEqual((after.x_m, after.y_m), (before.x_m, before.y_m))

    def test_uncalibrated_turn_invalidates_pose_without_guessing(self) -> None:
        estimator = EncoderPoseEstimator(EncoderPoseEstimatorSettings(80))
        estimator.update(motion(0.0), steering_command=80, timestamp=1.0)

        pose = estimator.update(motion(0.1), steering_command=75, timestamp=2.0)

        self.assertFalse(pose.valid)
        self.assertEqual((pose.x_m, pose.y_m, pose.heading_rad), (0.0, 0.0, 0.0))

    def test_bicycle_model_and_heading_normalization_with_fixture_calibration(self) -> None:
        estimator = EncoderPoseEstimator(
            EncoderPoseEstimatorSettings(
                steering_center_command=80,
                wheelbase_m=0.25,
                steering_angle_rad_by_command={75: math.radians(20.0)},
            )
        )
        estimator.update(motion(0.0), steering_command=80, timestamp=1.0)

        pose = estimator.update(motion(3.0), steering_command=75, timestamp=2.0)

        self.assertTrue(pose.valid)
        self.assertGreaterEqual(pose.heading_rad, -math.pi)
        self.assertLess(pose.heading_rad, math.pi)


if __name__ == "__main__":
    unittest.main()
