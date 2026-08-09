from __future__ import annotations

import math
import unittest

from localization.pose import PoseFrame, PoseSource
from localization.ros_pose_source_adapter import RosPoseSourceAdapter


class RosPoseSourceAdapterTest(unittest.TestCase):
    def test_map_to_base_link_is_labeled_as_map_source(self) -> None:
        pose = RosPoseSourceAdapter.from_map_to_base_link(
            x_m=1.0,
            y_m=2.0,
            heading_rad=math.pi / 4.0,
            timestamp=10.0,
            source=PoseSource.LOCALIZATION_MAP,
        )

        self.assertEqual(pose.frame_id, PoseFrame.MAP)
        self.assertEqual(pose.source, PoseSource.LOCALIZATION_MAP)
        self.assertTrue(pose.valid)

    def test_non_finite_ros_input_is_invalid(self) -> None:
        pose = RosPoseSourceAdapter.from_odom(
            x_m=float("nan"),
            y_m=0.0,
            heading_rad=0.0,
            timestamp=10.0,
        )

        self.assertFalse(pose.valid)


if __name__ == "__main__":
    unittest.main()
