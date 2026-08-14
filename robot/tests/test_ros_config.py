import tempfile
import unittest
from pathlib import Path

import yaml

from aiot_robot.ros_config import (
    MODE_PROFILES,
    build_nav2_values,
    render_nav2_config,
)


class RosConfigTest(unittest.TestCase):
    def environment(self):
        return {
            "ROKI_WHEELBASE_M": "0.30",
            "ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG": "20",
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
                "skirt: $INFLATION_RADIUS_M\nturn: $MINIMUM_TURNING_RADIUS_M\n",
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

    def test_global_costmap_follows_the_live_slam_map(self):
        """전역 코스트맵은 slam_toolbox 의 /map 을 따라간다.

        예전에는 순찰만 회전 창(20x20, inflation 만)을 썼다. 저장된 지도를
        map_server 가 따로 발행하던 시절의 구조다. 지금은 두 운행 모두
        slam_toolbox 의 /map 을 보므로 모양이 같을 수밖에 없고, 같아야
        순찰이 저장된 지도로 전역 계획을 할 수 있다.

        미탐사 공간은 구분 가능하게 남긴다. 탐사가 프론티어를 찾으려면
        필요하고, 계획기는 allow_unknown 으로 그 위를 지날 수 있다 -- 회전반경
        0.34 m 짜리 차체는 알려진 공간만으로는 호를 그릴 여유가 없다.
        """

        config = self._render()
        parameters = config["global_costmap"]["global_costmap"]["ros__parameters"]

        self.assertFalse(parameters["rolling_window"])
        self.assertTrue(parameters["track_unknown_space"])
        self.assertTrue(
            config["planner_server"]["ros__parameters"]["GridBased"]["allow_unknown"]
        )
        self.assertEqual(parameters["plugins"], ["static_layer", "inflation_layer"])
        self.assertEqual(
            parameters["static_layer"]["plugin"],
            "nav2_costmap_2d::StaticLayer",
        )
        # 회전 창일 때만 의미가 있던 값이다. 남아 있으면 다음 사람이 헷갈린다.
        self.assertNotIn("width", parameters)
        self.assertNotIn("height", parameters)
        # 자라는 코스트맵에 obstacle_layer 를 두면 지나온 자리의 마크가 지워지지
        # 않아 탐사가 스스로를 가둔다. /map 이 이미 같은 스캔을 담고 있다.
        self.assertNotIn("obstacle_layer", parameters)

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

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nav2.yaml"
            render_nav2_config(template, output, environment)
            config = yaml.safe_load(output.read_text(encoding="utf-8"))

        for scope in ("global_costmap", "local_costmap"):
            with self.subTest(scope=scope):
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

    def test_open_field_uses_a_broad_shared_inflation_skirt(self):
        """Both costmaps should steer paths away from walls consistently."""

        config = self._render()

        for scope in ("global_costmap", "local_costmap"):
            with self.subTest(scope=scope):
                inflation = config[scope][scope]["ros__parameters"][
                    "inflation_layer"
                ]
                self.assertEqual(float(inflation["inflation_radius"]), 0.40)
                self.assertEqual(float(inflation["cost_scaling_factor"]), 3.0)

    def _render(self):
        template = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "ros"
            / "nav2.params.yaml.template"
        )
        environment = self.environment()
        environment["ROKI_NAV2_MAPPING_BT_XML"] = "/opt/aiot/mapping.xml"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nav2.yaml"
            render_nav2_config(template, output, environment)
            return yaml.safe_load(output.read_text(encoding="utf-8"))

    def test_collapses_near_zero_linear_to_stop_the_reversal_oscillation(self):
        """전진<->후진 전환의 0 통과 구간이 제자리회전으로 오인되지 않게."""

        config = self._render()
        smoother = config["velocity_smoother"]["ros__parameters"]
        deadband = smoother["deadband_velocity"]
        controller_floor = float(
            config["controller_server"]["ros__parameters"]["FollowPath"][
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

    def test_mapping_lookahead_is_isolated_from_patrol_controller(self):
        config = self._render()
        controller = config["controller_server"]["ros__parameters"]

        self.assertEqual(
            controller["controller_plugins"],
            ["FollowPath", "MappingFollowPath"],
        )
        self.assertEqual(controller["FollowPath"]["min_lookahead_dist"], 0.45)
        self.assertEqual(controller["FollowPath"]["lookahead_dist"], 0.50)
        self.assertEqual(controller["FollowPath"]["max_lookahead_dist"], 0.65)
        self.assertEqual(
            controller["MappingFollowPath"]["min_lookahead_dist"], 0.85
        )
        self.assertEqual(controller["MappingFollowPath"]["lookahead_dist"], 0.90)
        self.assertEqual(
            controller["MappingFollowPath"]["max_lookahead_dist"], 1.00
        )
        self.assertEqual(
            controller["MappingFollowPath"]["desired_linear_vel"],
            controller["FollowPath"]["desired_linear_vel"],
        )

    def test_localization_servers_are_gone(self):
        """slam_toolbox 가 두 운행의 위치추정을 다 맡으므로 중복 발행자를 없앴다.

        amcl 이나 map_server 가 함께 뜨면 map->odom 을 두 노드가 발행해 TF 가
        싸운다. 템플릿에 남겨두면 언젠가 누가 다시 켠다.
        """

        config = self._render()

        self.assertNotIn("amcl", config)
        self.assertNotIn("map_server", config)
        # 프론트에 줄 .pgm 은 계속 필요하므로 map_saver 는 남는다.
        self.assertIn("map_saver", config)

    def test_rendered_baseline_carries_the_mapping_profile(self):
        """스택은 매핑 모드로 뜨고, 생애주기 복구도 이 파일로 되돌아간다.

        2026-08-07 실측: 생애주기 관리자가 bond 끊김으로 스택을 복구하면
        configure 가 이 파일을 다시 읽어 실행 중 주입한 값을 버린다. 그래서
        기본값이 매핑이어야 복구가 매핑을 매핑으로 되돌린다.
        """

        config = self._render()
        planner = config["planner_server"]["ros__parameters"]["GridBased"]
        checker = config["controller_server"]["ros__parameters"][
            "general_goal_checker"
        ]

        for dotted, expected in MODE_PROFILES["mapping"]["/planner_server"].items():
            self.assertEqual(planner[dotted.split(".", 1)[1]], expected)
        self.assertEqual(
            checker["yaw_goal_tolerance"],
            MODE_PROFILES["mapping"]["/controller_server"][
                "general_goal_checker.yaw_goal_tolerance"
            ],
        )

    def test_preloads_both_planner_profiles_with_legacy_mapping_id(self):
        config = self._render()
        planner = config["planner_server"]["ros__parameters"]

        self.assertEqual(
            planner["planner_plugins"],
            ["GridBased", "MappingGridBased", "PatrolGridBased"],
        )
        for mode, plugin_id in (
            ("mapping", "MappingGridBased"),
            ("patrol", "PatrolGridBased"),
        ):
            with self.subTest(mode=mode):
                plugin = planner[plugin_id]
                self.assertEqual(
                    plugin["plugin"],
                    "nav2_smac_planner/SmacPlannerHybrid",
                )
                for dotted, expected in MODE_PROFILES[mode][
                    "/planner_server"
                ].items():
                    self.assertEqual(plugin[dotted.split(".", 1)[1]], expected)

    def test_mapping_uses_verified_smac_costs_without_changing_patrol(self):
        config = self._render()
        planner = config["planner_server"]["ros__parameters"]
        mapping = planner["MappingGridBased"]
        patrol = planner["PatrolGridBased"]

        self.assertEqual(mapping["motion_model_for_search"], "REEDS_SHEPP")
        self.assertEqual(mapping["reverse_penalty"], 2.0)
        self.assertEqual(mapping["change_penalty"], 0.0)
        self.assertEqual(mapping["non_straight_penalty"], 1.2)
        self.assertEqual(mapping["cost_penalty"], 2.0)

        self.assertEqual(patrol["motion_model_for_search"], "DUBIN")
        self.assertEqual(patrol["reverse_penalty"], 2.1)
        self.assertEqual(patrol["change_penalty"], 0.0)
        self.assertEqual(patrol["non_straight_penalty"], 1.2)
        self.assertEqual(patrol["cost_penalty"], 2.0)

    def test_preloads_both_goal_checkers_with_legacy_mapping_id(self):
        config = self._render()
        controller = config["controller_server"]["ros__parameters"]

        self.assertEqual(
            controller["goal_checker_plugins"],
            [
                "general_goal_checker",
                "mapping_goal_checker",
                "patrol_goal_checker",
            ],
        )
        for mode, plugin_id in (
            ("mapping", "mapping_goal_checker"),
            ("patrol", "patrol_goal_checker"),
        ):
            with self.subTest(mode=mode):
                checker = controller[plugin_id]
                self.assertEqual(
                    checker["plugin"],
                    "nav2_controller::SimpleGoalChecker",
                )
                self.assertEqual(checker["xy_goal_tolerance"], 0.2)
                self.assertEqual(
                    checker["yaw_goal_tolerance"],
                    MODE_PROFILES[mode]["/controller_server"][
                        "general_goal_checker.yaw_goal_tolerance"
                    ],
                )

    def test_mode_profiles_cover_the_same_parameters(self):
        """한쪽에만 있는 항목은 전환해도 이전 모드 값이 남는다."""

        mapping = MODE_PROFILES["mapping"]
        patrol = MODE_PROFILES["patrol"]

        self.assertEqual(set(mapping), set(patrol))
        for node in mapping:
            self.assertEqual(
                set(mapping[node]),
                set(patrol[node]),
                f"{node} 의 항목이 두 프로필에서 다르다",
            )
            self.assertTrue(
                any(
                    mapping[node][name] != patrol[node][name]
                    for name in mapping[node]
                ),
                f"{node} 프로필 전체가 같다면 분리할 이유가 없다",
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
