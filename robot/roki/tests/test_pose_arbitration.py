from __future__ import annotations

import math
import unittest

from localization.pose import PoseEstimate, PoseFrame, PoseSource
from localization.pose_arbitrator import PoseArbitrator
from state.robot_state import RobotStateStore


def estimate(
    *,
    frame: PoseFrame,
    source: PoseSource,
    timestamp: float = 9.0,
    valid: bool = True,
) -> PoseEstimate:
    return PoseEstimate(1.0, 2.0, math.pi / 2.0, frame, source, valid, timestamp)


class PoseArbitrationTest(unittest.TestCase):
    def test_map_pose_is_selected_and_heading_converted_to_degrees(self) -> None:
        store = RobotStateStore(map_pose_timeout_sec=2.0, clock=lambda: 10.0)
        store.update_odom_pose(
            estimate(frame=PoseFrame.ODOM, source=PoseSource.ENCODER_ODOM)
        )
        store.update_map_pose(
            estimate(frame=PoseFrame.MAP, source=PoseSource.LOCALIZATION_MAP)
        )

        pose = store.get_pose()

        self.assertIsNotNone(pose)
        assert pose is not None
        self.assertEqual((pose.x, pose.y, pose.heading), (1.0, 2.0, 90.0))

    def test_stale_and_invalid_map_pose_are_rejected(self) -> None:
        for pose in (
            estimate(
                frame=PoseFrame.MAP,
                source=PoseSource.LOCALIZATION_MAP,
                timestamp=7.0,
            ),
            estimate(
                frame=PoseFrame.MAP,
                source=PoseSource.LOCALIZATION_MAP,
                valid=False,
            ),
        ):
            with self.subTest(pose=pose):
                store = RobotStateStore(map_pose_timeout_sec=2.0, clock=lambda: 10.0)
                store.update_map_pose(pose)
                self.assertIsNone(store.get_pose())

    def test_odom_pose_is_internal_only(self) -> None:
        store = RobotStateStore(map_pose_timeout_sec=2.0, clock=lambda: 10.0)
        odom = estimate(frame=PoseFrame.ODOM, source=PoseSource.ENCODER_ODOM)
        store.update_odom_pose(odom)

        self.assertIs(store.get_odom_pose(), odom)
        self.assertIsNone(store.get_pose())

    def test_mqtt_pose_is_disabled_without_configured_freshness(self) -> None:
        store = RobotStateStore(clock=lambda: 10.0)
        store.update_map_pose(
            estimate(frame=PoseFrame.MAP, source=PoseSource.SLAM_MAP)
        )

        self.assertIsNone(store.get_pose())

    def test_arbitrator_rejects_rf2o_pose_even_if_labeled_map_frame(self) -> None:
        arbitrator = PoseArbitrator(2.0)

        selected = arbitrator.select(
            map_pose=estimate(frame=PoseFrame.MAP, source=PoseSource.RF2O_ODOM),
            odom_pose=None,
            now=10.0,
        )

        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
