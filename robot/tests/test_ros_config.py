import tempfile
import unittest
from pathlib import Path

from aiot_robot.ros_config import build_nav2_values, render_nav2_config


class RosConfigTest(unittest.TestCase):
    def environment(self):
        return {
            "ROKI_WHEELBASE_M": "0.30",
            "ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG": "20",
            "ROKI_ROBOT_RADIUS_M": "0.25",
            "ROKI_NAV2_DESIRED_LINEAR_SPEED_MPS": "0.20",
            "ROKI_MAXIMUM_LINEAR_SPEED_MPS": "0.40",
            "ROKI_NAV2_BT_XML": "/opt/aiot/nav.xml",
        }

    def test_derives_turning_radius_from_measurements(self):
        values = build_nav2_values(self.environment())

        self.assertAlmostEqual(float(values["MINIMUM_TURNING_RADIUS_M"]), 0.824243, places=5)
        self.assertEqual(values["ROBOT_RADIUS_M"], "0.25")

    def test_refuses_to_guess_missing_measurements(self):
        environment = self.environment()
        del environment["ROKI_WHEELBASE_M"]

        with self.assertRaisesRegex(ValueError, "ROKI_WHEELBASE_M"):
            build_nav2_values(environment)

    def test_renders_all_tokens_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.yaml"
            output = root / "output.yaml"
            template.write_text(
                "radius: $ROBOT_RADIUS_M\nturn: $MINIMUM_TURNING_RADIUS_M\n",
                encoding="utf-8",
            )

            render_nav2_config(template, output, self.environment())

            self.assertNotIn("$", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
