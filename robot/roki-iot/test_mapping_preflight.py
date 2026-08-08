from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_integrated


FIELD_ENV = {
    "ROKI_NAVIGATION_MODE": "nav2",
    "ROKI_WHEELBASE_M": "0.124",
    "ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG": "20",
    "ROKI_INITIAL_POSE_X_M": "0",
    "ROKI_INITIAL_POSE_Y_M": "0",
    "ROKI_INITIAL_POSE_YAW_RAD": "0",
}


class MappingPreflightTest(unittest.TestCase):
    def test_mapping_only_preflight_allows_missing_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_route = Path(directory) / "route.local.yaml"
            with (
                patch.dict(
                    os.environ,
                    {
                        **FIELD_ENV,
                        "AIOT_MAPPING_GAMEPAD_ENABLED": "true",
                    },
                ),
                patch.object(
                    run_integrated.importlib.util,
                    "find_spec",
                    return_value=object(),
                ),
                patch.object(run_integrated, "_validate_import_namespaces"),
            ):
                result = run_integrated.preflight(missing_route)

        self.assertFalse(result["routeConfigured"])
        self.assertTrue(result["mappingAvailable"])
        self.assertIsNone(result["routeId"])
        self.assertEqual(result["waypoints"], 0)

    def test_legacy_ros_mode_does_not_replace_the_unified_nav2_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stale_route = Path(directory) / "route.local.yaml"
            stale_route.write_text("stale: true\n", encoding="utf-8")
            with (
                patch.dict(
                    os.environ,
                    {
                        **FIELD_ENV,
                        "AIOT_MAPPING_GAMEPAD_ENABLED": "true",
                        "AIOT_ROS_MODE": "mapping",
                    },
                ),
                patch.object(
                    run_integrated.importlib.util,
                    "find_spec",
                    return_value=object(),
                ),
                patch.object(run_integrated, "_validate_import_namespaces"),
                patch.object(
                    run_integrated,
                    "_build_navigation_service",
                    side_effect=AssertionError("stale route must not be loaded"),
                ),
            ):
                result = run_integrated.preflight(stale_route)

        self.assertEqual(result["navigationMode"], "nav2")
        self.assertFalse(result["mappingModeRequested"])
        self.assertFalse(result["routeConfigured"])
        self.assertFalse(result["mapValidated"])

    def test_mapping_mode_remains_available_when_gamepad_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_route = Path(directory) / "route.local.yaml"
            with (
                patch.dict(
                    os.environ,
                    {
                        **FIELD_ENV,
                        "AIOT_MAPPING_GAMEPAD_ENABLED": "false",
                        "AIOT_ROS_MODE": "mapping",
                    },
                ),
                patch.object(
                    run_integrated.importlib.util,
                    "find_spec",
                    return_value=object(),
                ),
                patch.object(run_integrated, "_validate_import_namespaces"),
            ):
                result = run_integrated.preflight(missing_route)

        self.assertTrue(result["mappingAvailable"])
        self.assertFalse(result["mappingModeRequested"])
        self.assertEqual(result["navigationMode"], "nav2")
        self.assertFalse(result["routeConfigured"])

    def test_disabled_mapping_input_never_opens_device_or_thread(self) -> None:
        mapping_input = run_integrated._DisabledMappingInput()

        mapping_input.start()
        snapshot = mapping_input.diagnostic_snapshot()
        mapping_input.stop()

        self.assertEqual(mapping_input.device_path, Path("disabled"))
        self.assertFalse(snapshot["gamepadDeviceOpen"])
        self.assertFalse(snapshot["gamepadThreadAlive"])
        self.assertEqual(snapshot["lastGamepadDecision"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
