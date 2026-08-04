from __future__ import annotations

import unittest

from common.config_loader import load_robot_config, load_safety_config
from scripts.run_runtime import (
    build_localization_settings,
    build_ros_lidar_health_bridge,
    build_ros_tf_pose_bridge,
    build_runtime,
    build_safety_settings,
)
from state.robot_state import RobotStateStore


class RuntimeBootstrapTest(unittest.TestCase):
    def test_safety_config_loads_and_converts_milliseconds(self) -> None:
        settings = build_safety_settings(
            {
                "safety": {
                    "odometry_timeout_ms": 300,
                    "hardware_status_timeout_ms": 1000,
                    "low_battery_percent": 20.0,
                }
            }
        )
        self.assertEqual(settings.odometry_timeout_sec, 0.3)
        self.assertEqual(settings.hardware_status_timeout_sec, 1.0)
        self.assertEqual(settings.low_battery_percent, 20.0)

    def test_null_low_battery_percent_is_supported(self) -> None:
        settings = build_safety_settings(
            {
                "safety": {
                    "odometry_timeout_ms": 300,
                    "hardware_status_timeout_ms": 1000,
                    "low_battery_percent": None,
                }
            }
        )
        self.assertIsNone(settings.low_battery_percent)

    def test_missing_new_safety_setting_is_rejected_clearly(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"safety\.yaml\.safety\.hardware_status_timeout_ms",
        ):
            build_safety_settings(
                {
                    "safety": {
                        "odometry_timeout_ms": 300,
                        "low_battery_percent": 20.0,
                    }
                }
            )

    def test_legacy_safety_keys_do_not_satisfy_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "odometry_timeout_ms"):
            build_safety_settings(
                {
                    "safety": {
                        "telemetry_timeout_ms": 300,
                        "low_voltage_cutoff_v": 9.0,
                        "low_battery_percent": 20.0,
                    }
                }
            )

    def test_invalid_timeout_and_battery_are_rejected(self) -> None:
        base = {
            "odometry_timeout_ms": 300,
            "hardware_status_timeout_ms": 1000,
            "low_battery_percent": 20.0,
        }
        for key, invalid in (
            ("odometry_timeout_ms", 0),
            ("hardware_status_timeout_ms", -1),
            ("odometry_timeout_ms", "300"),
            ("low_battery_percent", 101.0),
        ):
            values = dict(base)
            values[key] = invalid
            with self.subTest(key=key, invalid=invalid):
                with self.assertRaises(ValueError):
                    build_safety_settings({"safety": values})

    def test_actual_config_builds_runtime_and_injects_store(self) -> None:
        runtime = build_runtime()
        self.assertIsInstance(runtime.state_store, RobotStateStore)
        self.assertIsNotNone(runtime.state_store.snapshot())
        settings = build_localization_settings(load_robot_config())
        self.assertEqual(settings.map_pose_timeout_sec, 2.0)
        self.assertEqual(settings.max_future_transform_sec, 0.75)
        bridge = build_ros_tf_pose_bridge(runtime.state_store)
        self.assertIs(bridge.state_store, runtime.state_store)
        lidar_bridge = build_ros_lidar_health_bridge(runtime.state_store)
        self.assertIs(lidar_bridge.state_store, runtime.state_store)

    def test_invalid_localization_timeout_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "map_pose_timeout_sec"):
            build_localization_settings(
                {
                    "localization": {
                        "map_frame": "map",
                        "base_frame": "base_link",
                        "map_pose_timeout_sec": 0,
                        "tf_poll_interval_sec": 0.1,
                    }
                }
            )

    def test_actual_config_disables_low_battery_until_soc_calibration(
        self,
    ) -> None:
        settings = build_safety_settings(load_safety_config())
        self.assertIsNone(settings.low_battery_percent)


if __name__ == "__main__":
    unittest.main()
