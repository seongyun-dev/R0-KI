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
            "ROKI_INITIAL_POSE_X_M": "-1.25",
            "ROKI_INITIAL_POSE_Y_M": "2.5",
            "ROKI_INITIAL_POSE_YAW_RAD": "-1.5708",
            "ROKI_NAV2_DESIRED_LINEAR_SPEED_MPS": "0.20",
            "ROKI_MAXIMUM_LINEAR_SPEED_MPS": "0.40",
            "ROKI_NAV2_BT_XML": "/opt/aiot/nav.xml",
        }

    def test_derives_turning_radius_from_measurements(self):
        values = build_nav2_values(self.environment())

        self.assertAlmostEqual(float(values["MINIMUM_TURNING_RADIUS_M"]), 0.824243, places=5)
        self.assertEqual(values["ROBOT_RADIUS_M"], "0.25")
        self.assertEqual(values["INITIAL_POSE_X_M"], "-1.25")
        self.assertEqual(values["INITIAL_POSE_Y_M"], "2.5")
        self.assertEqual(values["INITIAL_POSE_YAW_RAD"], "-1.5708")
        self.assertEqual(values["XY_GOAL_TOLERANCE_M"], "0.2")

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

    def test_production_template_uses_the_shared_xy_goal_tolerance(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nav2.yaml"
            environment = self.environment()
            environment["ROKI_NAV2_XY_GOAL_TOLERANCE_M"] = "0.25"
            template = (
                Path(__file__).resolve().parents[1]
                / "config"
                / "ros"
                / "nav2.params.yaml.template"
            )

            render_nav2_config(template, output, environment)

            self.assertIn(
                "xy_goal_tolerance: 0.25",
                output.read_text(encoding="utf-8"),
            )

    def test_production_template_loads_default_nav2_recovery_plugins(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nav2.yaml"
            template = (
                Path(__file__).resolve().parents[1]
                / "config"
                / "ros"
                / "nav2.params.yaml.template"
            )

            render_nav2_config(template, output, self.environment())
            rendered = output.read_text(encoding="utf-8")

            self.assertIn("nav2_recovery_node_bt_node", rendered)
            self.assertIn("nav2_navigate_through_poses_action_bt_node", rendered)

    def test_zero_initial_pose_is_rendered_as_ros_double(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nav2.yaml"
            environment = self.environment()
            environment["ROKI_INITIAL_POSE_X_M"] = "0"
            environment["ROKI_INITIAL_POSE_Y_M"] = "0.0"
            environment["ROKI_INITIAL_POSE_YAW_RAD"] = "0"
            template = (
                Path(__file__).resolve().parents[1]
                / "config"
                / "ros"
                / "nav2.params.yaml.template"
            )

            render_nav2_config(template, output, environment)
            rendered = output.read_text(encoding="utf-8")

            self.assertIn("      x: 0.0", rendered)
            self.assertIn("      y: 0.0", rendered)
            self.assertIn("      yaw: 0.0", rendered)

    def test_rejects_missing_or_invalid_fixed_initial_pose(self):
        for name, value, message in (
            ("ROKI_INITIAL_POSE_X_M", "", "ROKI_INITIAL_POSE_X_M"),
            ("ROKI_INITIAL_POSE_Y_M", "nan", "ROKI_INITIAL_POSE_Y_M"),
            ("ROKI_INITIAL_POSE_YAW_RAD", "3.2", "-pi..pi"),
        ):
            with self.subTest(name=name, value=value):
                environment = self.environment()
                environment[name] = value
                with self.assertRaisesRegex(ValueError, message):
                    build_nav2_values(environment)

    def test_rejects_unsafe_xy_goal_tolerance(self):
        for value in ("0.01", "1.1", "nan"):
            with self.subTest(value=value):
                environment = self.environment()
                environment["ROKI_NAV2_XY_GOAL_TOLERANCE_M"] = value
                with self.assertRaisesRegex(
                    ValueError,
                    "ROKI_NAV2_XY_GOAL_TOLERANCE_M",
                ):
                    build_nav2_values(environment)


if __name__ == "__main__":
    unittest.main()
