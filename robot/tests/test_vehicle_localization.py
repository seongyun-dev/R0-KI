import unittest
from types import SimpleNamespace

from aiot_robot.vehicle_localization import project_front_vehicle


class VehicleLocalizationTest(unittest.TestCase):
    def test_projects_range_using_robot_heading(self):
        pose = SimpleNamespace(x=1.0, y=2.0, heading=90.0)

        result = project_front_vehicle(pose, 2.0)

        self.assertAlmostEqual(result.x, 1.0, places=6)
        self.assertAlmostEqual(result.y, 4.0, places=6)

    def test_applies_camera_yaw_offset(self):
        pose = SimpleNamespace(x=1.0, y=2.0, heading=0.0)

        result = project_front_vehicle(pose, 1.0, camera_yaw_deg=-90.0)

        self.assertAlmostEqual(result.x, 1.0, places=6)
        self.assertAlmostEqual(result.y, 1.0, places=6)

    def test_rejects_nonpositive_range(self):
        pose = SimpleNamespace(x=0.0, y=0.0, heading=0.0)
        with self.assertRaisesRegex(ValueError, "positive"):
            project_front_vehicle(pose, 0.0)


if __name__ == "__main__":
    unittest.main()
