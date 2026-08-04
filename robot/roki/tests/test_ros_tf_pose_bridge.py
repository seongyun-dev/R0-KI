from __future__ import annotations

import math
import unittest
from types import SimpleNamespace

from localization.pose import PoseFrame, PoseSource
from localization.ros_tf_pose_bridge import (
    RosTfPoseBridge,
    RosTfPoseBridgeSettings,
)
from state.robot_state import RobotStateStore


def transform(
    *,
    x: float = 1.25,
    y: float = -0.5,
    yaw: float = math.pi / 2,
    stamp_sec: int = 9,
    stamp_nanosec: int = 500_000_000,
    frame: str = "map",
    child_frame: str = "base_link",
) -> SimpleNamespace:
    return SimpleNamespace(
        header=SimpleNamespace(
            frame_id=frame,
            stamp=SimpleNamespace(sec=stamp_sec, nanosec=stamp_nanosec),
        ),
        child_frame_id=child_frame,
        transform=SimpleNamespace(
            translation=SimpleNamespace(x=x, y=y, z=0.0),
            rotation=SimpleNamespace(
                x=0.0,
                y=0.0,
                z=math.sin(yaw / 2),
                w=math.cos(yaw / 2),
            ),
        ),
    )


class RosTfPoseBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = RobotStateStore(
            map_pose_timeout_sec=2.0,
            clock=lambda: 101.0,
        )
        self.bridge = RosTfPoseBridge(
            state_store=self.store,
            settings=RosTfPoseBridgeSettings(
                map_frame="map",
                base_frame="base_link",
                map_pose_timeout_sec=2.0,
                tf_poll_interval_sec=0.1,
            ),
            monotonic_clock=lambda: 100.0,
        )

    def test_fresh_map_transform_is_converted_and_stored(self) -> None:
        updated = self.bridge.ingest_transform(
            transform(), ros_now_sec=10.0, received_at=100.0
        )

        self.assertTrue(updated)
        pose = self.store.get_map_pose()
        self.assertIsNotNone(pose)
        assert pose is not None
        self.assertAlmostEqual(pose.x_m, 1.25)
        self.assertAlmostEqual(pose.y_m, -0.5)
        self.assertAlmostEqual(pose.heading_rad, math.pi / 2)
        self.assertIs(pose.source, PoseSource.SLAM_MAP)
        self.assertIs(pose.frame_id, PoseFrame.MAP)
        self.assertTrue(pose.valid)
        mqtt_pose = self.store.get_pose()
        self.assertIsNotNone(mqtt_pose)
        assert mqtt_pose is not None
        self.assertAlmostEqual(mqtt_pose.heading, 90.0)

    def test_stale_and_wrong_frame_transforms_are_not_stored(self) -> None:
        for value, now in (
            (transform(stamp_sec=7, stamp_nanosec=0), 10.0),
            (transform(frame="odom"), 10.0),
            (transform(child_frame="camera_link"), 10.0),
        ):
            with self.subTest(value=value):
                self.assertFalse(
                    self.bridge.ingest_transform(value, ros_now_sec=now)
                )
                self.assertIsNone(self.store.get_pose())

    def test_allows_small_amcl_future_stamp_but_rejects_large_future(self) -> None:
        within_amcl_tolerance = transform(
            stamp_sec=10,
            stamp_nanosec=500_000_000,
        )
        self.assertTrue(
            self.bridge.ingest_transform(
                within_amcl_tolerance,
                ros_now_sec=10.0,
                received_at=100.0,
            )
        )
        pose = self.store.get_map_pose()
        self.assertIsNotNone(pose)
        assert pose is not None
        # Freshness remains tied to local receipt time, not the future TF stamp.
        self.assertEqual(pose.timestamp, 100.0)

        far_future = transform(stamp_sec=11, stamp_nanosec=0)
        self.assertFalse(
            self.bridge.ingest_transform(far_future, ros_now_sec=10.0)
        )

    def test_lookup_failure_does_not_create_publishable_pose(self) -> None:
        def fail() -> object:
            raise RuntimeError("TF missing")

        self.assertFalse(
            self.bridge.lookup_and_update(fail, ros_now_sec=10.0)
        )
        self.assertIsNone(self.store.get_map_pose())
        self.assertIsNone(self.store.get_pose())

    def test_non_finite_values_and_zero_quaternion_are_rejected(self) -> None:
        invalid = [
            transform(x=math.nan),
            transform(y=math.inf),
        ]
        non_finite_quaternion = transform()
        non_finite_quaternion.transform.rotation.z = math.inf
        invalid.append(non_finite_quaternion)
        zero_quaternion = transform()
        zero_quaternion.transform.rotation = SimpleNamespace(
            x=0.0, y=0.0, z=0.0, w=0.0
        )
        invalid.append(zero_quaternion)

        for value in invalid:
            with self.subTest(value=value):
                self.assertFalse(
                    self.bridge.ingest_transform(value, ros_now_sec=10.0)
                )
        self.assertIsNone(self.store.get_pose())


if __name__ == "__main__":
    unittest.main()
