import tempfile
import unittest
from pathlib import Path

import yaml

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
            self.assertIn(
                "default_nav_through_poses_bt_xml: "
                "/opt/aiot/iot/current/robot/config/ros/"
                "nav2_fixed_path_through_poses.xml",
                rendered,
            )

    def test_fixed_path_trees_use_humble_compatible_ports(self):
        config_root = Path(__file__).resolve().parents[1] / "config" / "ros"

        for name in (
            "nav2_fixed_path.xml",
            "nav2_fixed_path_through_poses.xml",
        ):
            with self.subTest(name=name):
                tree = (config_root / name).read_text(encoding="utf-8")
                self.assertNotIn("error_code_id", tree)

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
            self.assertIn("      rolling_window: true", rendered)
            self.assertIn("      plugins: [inflation_layer]", rendered)
            self.assertNotIn("      plugins: [static_layer, inflation_layer]", rendered)
            self.assertIn("      allow_unknown: true", rendered)

    def test_rolling_global_costmap_uses_humble_integer_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nav2.yaml"
            template = (
                Path(__file__).resolve().parents[1]
                / "config"
                / "ros"
                / "nav2.params.yaml.template"
            )

            render_nav2_config(template, output, self.environment())
            config = yaml.safe_load(output.read_text(encoding="utf-8"))
            parameters = config["global_costmap"]["global_costmap"][
                "ros__parameters"
            ]

            self.assertIs(type(parameters["width"]), int)
            self.assertIs(type(parameters["height"]), int)
            self.assertEqual(parameters["width"], 20)
            self.assertEqual(parameters["height"], 20)
            self.assertTrue(parameters["rolling_window"])
            self.assertEqual(parameters["plugins"], ["inflation_layer"])

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

    def test_both_modes_declare_the_measured_rectangular_body(self):
        """Patrol must not plan against a circle 1.8x wider than the real chassis.

        robot_radius doubles as the inscribed radius in Nav2, so a 0.23 m circle
        marked the robot's own cell lethal within 0.23 m of a wall. The body is a
        physical fact, so patrol and mapping have to agree on it.
        """

        import math

        circumscribed = math.hypot(0.175, 0.125)
        template = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "ros"
            / "nav2.params.yaml.template"
        )
        environment = self.environment()
        environment["ROKI_NAV2_MAPPING_BT_XML"] = "/opt/aiot/mapping.xml"

        for mapping in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "nav2.yaml"
                render_nav2_config(template, output, environment, mapping=mapping)
                config = yaml.safe_load(output.read_text(encoding="utf-8"))

            for scope in ("global_costmap", "local_costmap"):
                with self.subTest(mapping=mapping, scope=scope):
                    params = config[scope][scope]["ros__parameters"]
                    self.assertEqual(
                        params["footprint"],
                        "[[0.175, 0.125], [0.175, -0.125], "
                        "[-0.175, -0.125], [-0.175, 0.125]]",
                    )
                    # Two geometries that disagree is worse than either alone.
                    self.assertNotIn("robot_radius", params)
                    # Nav2 reads inflation costs when it checks the footprint, so
                    # the skirt has to reach at least the circumscribed circle or
                    # collisions go silently unreported.
                    self.assertGreaterEqual(
                        float(params["inflation_layer"]["inflation_radius"]),
                        circumscribed,
                    )

    def test_mapping_collapses_near_zero_linear_to_stop_the_reversal_oscillation(self):
        """전진<->후진 전환의 0 통과 구간이 제자리회전으로 오인되지 않게."""

        template = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "ros"
            / "nav2.params.yaml.template"
        )
        environment = self.environment()
        environment["ROKI_NAV2_MAPPING_BT_XML"] = "/opt/aiot/mapping.xml"

        with tempfile.TemporaryDirectory() as directory:
            mapping_out = Path(directory) / "mapping.yaml"
            patrol_out = Path(directory) / "patrol.yaml"
            render_nav2_config(template, mapping_out, environment, mapping=True)
            render_nav2_config(template, patrol_out, environment)
            mapping = yaml.safe_load(mapping_out.read_text(encoding="utf-8"))
            patrol = yaml.safe_load(patrol_out.read_text(encoding="utf-8"))

        smoother = mapping["velocity_smoother"]["ros__parameters"]
        deadband = smoother["deadband_velocity"]
        controller_floor = float(
            mapping["controller_server"]["ros__parameters"]["FollowPath"][
                "regulated_linear_scaling_min_speed"
            ]
        )
        self.assertGreater(deadband[0], 0.0, "선속 데드밴드가 있어야 한다")
        self.assertLess(
            deadband[0],
            controller_floor,
            "정상 순항 명령까지 잘라내면 안 되므로 컨트롤러 하한보다 작아야 한다",
        )
        # 각속도는 건드리지 않는다: 조향은 정지 중에도 유지돼야 한다.
        self.assertEqual(deadband[1:], [0.0, 0.0])
        # 후진은 계속 허용돼야 REEDS_SHEPP 경로가 성립한다.
        self.assertLess(smoother["min_velocity"][0], 0.0)
        # 순찰은 DUBIN 전진 전용이라 이 보정이 필요 없다.
        self.assertEqual(
            patrol["velocity_smoother"]["ros__parameters"]["deadband_velocity"],
            [0.0, 0.0, 0.0],
        )

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
