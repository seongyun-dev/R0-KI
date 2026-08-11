from __future__ import annotations

import unittest
from types import SimpleNamespace

from aiot_robot.detection_localization import (
    bbox_center_bearing_deg,
    project_detection,
)


class DetectionLocalizationTest(unittest.TestCase):
    def test_center_bbox_uses_camera_yaw(self) -> None:
        bearing = bbox_center_bearing_deg(
            {"x": 270, "y": 100, "width": 100, "height": 100},
            640,
            camera_horizontal_fov_deg=60,
            camera_yaw_deg=3,
        )

        self.assertAlmostEqual(bearing, 3.0)

    def test_image_left_is_positive_ros_yaw(self) -> None:
        left = bbox_center_bearing_deg(
            {"x": 0, "y": 0, "width": 64, "height": 64},
            640,
            camera_horizontal_fov_deg=60,
        )
        right = bbox_center_bearing_deg(
            {"x": 576, "y": 0, "width": 64, "height": 64},
            640,
            camera_horizontal_fov_deg=60,
        )

        self.assertGreater(left, 0)
        self.assertLess(right, 0)
        self.assertAlmostEqual(left, -right)

    def test_project_detection_combines_robot_heading_and_bearing(self) -> None:
        projected = project_detection(
            SimpleNamespace(x=1.0, y=2.0, heading=90.0),
            2.0,
            bearing_deg=-90.0,
        )

        self.assertAlmostEqual(projected.x, 3.0, places=6)
        self.assertAlmostEqual(projected.y, 2.0, places=6)

    def test_invalid_bbox_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            bbox_center_bearing_deg(
                {"x": 0, "width": 0},
                640,
                camera_horizontal_fov_deg=60,
            )


if __name__ == "__main__":
    unittest.main()
