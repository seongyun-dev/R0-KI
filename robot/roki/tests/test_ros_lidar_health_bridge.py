from __future__ import annotations

import unittest
from types import SimpleNamespace

from safety.obstacle_guard import (
    FrontObstacleDetector,
    ObstacleDetectorSettings,
)
from sensors.ros_lidar_health_bridge import (
    RosLidarHealthBridge,
    RosLidarHealthSettings,
)
from state.robot_state import RobotStateStore


class RosLidarHealthBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = RobotStateStore()
        self.bridge = RosLidarHealthBridge(
            state_store=self.store,
            settings=RosLidarHealthSettings(
                scan_topic="/scan",
                scan_timeout_sec=1.0,
            ),
            monotonic_clock=lambda: 10.0,
        )

    def test_scan_sets_normal_and_camera_remains_disconnected(self) -> None:
        self.bridge.record_scan(received_at=10.0)

        self.assertEqual(self.bridge.evaluate(now=10.999), "NORMAL")
        status = self.store.get_status()
        self.assertEqual(status.lidar, "NORMAL")
        self.assertEqual(status.camera, "DISCONNECTED")

    def test_scan_timeout_sets_disconnected(self) -> None:
        self.bridge.record_scan(received_at=10.0)

        self.assertEqual(self.bridge.evaluate(now=11.0), "DISCONNECTED")
        self.assertEqual(
            self.store.get_status().lidar,
            "DISCONNECTED",
        )

    def test_no_scan_remains_disconnected(self) -> None:
        self.assertEqual(self.bridge.evaluate(now=10.0), "DISCONNECTED")
        self.assertEqual(
            self.store.get_status().lidar,
            "DISCONNECTED",
        )

    def test_scan_updates_obstacle_without_touching_motion_or_safety(self) -> None:
        bridge = RosLidarHealthBridge(
            state_store=self.store,
            settings=RosLidarHealthSettings(
                scan_topic="/scan",
                scan_timeout_sec=1.0,
            ),
            obstacle_detector=FrontObstacleDetector(
                ObstacleDetectorSettings(30.0, 0.6, 0.7)
            ),
            monotonic_clock=lambda: 10.0,
        )
        scan = SimpleNamespace(
            ranges=[1.0, 0.4, 1.0],
            angle_min=-0.1,
            angle_increment=0.1,
            range_min=0.12,
            range_max=12.0,
        )

        bridge._on_scan(scan)

        status = self.store.get_status()
        self.assertEqual(status.obstacle.status, "STOP")
        self.assertEqual(status.obstacle.direction, "FRONT")
        self.assertEqual(status.camera, "DISCONNECTED")
        self.assertEqual(status.motor, "DISCONNECTED")
        self.assertEqual(status.line_sensor, "DISCONNECTED")
        self.assertIsNone(self.store.snapshot().safety_decision)


if __name__ == "__main__":
    unittest.main()
