from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import run_integrated


class MappingPreflightTest(unittest.TestCase):
    def test_patrol_localization_reseeds_from_first_route_segment(self) -> None:
        calls: dict[str, object] = {}

        class Slam:
            def marker(self):
                return object()

            def wait_for_localization_ready(self, marker, *, timeout_sec):
                calls["marker"] = marker
                calls["ready_timeout"] = timeout_sec
                return True

            def relocalize(self, **kwargs):
                calls["relocalize"] = kwargs
                return True, "START_POSE_CONFIRMED"

        class Localization:
            def ensure_patrol(self, path):
                calls["posegraph"] = path
                return True, "ALREADY_PATROL"

        with tempfile.TemporaryDirectory() as directory:
            map_yaml = Path(directory) / "map.yaml"
            map_yaml.write_text("image: map.pgm\n", encoding="utf-8")
            route = SimpleNamespace(
                waypoints=(
                    SimpleNamespace(x=-0.076, y=-0.052, yaw_deg=None),
                    SimpleNamespace(x=0.067, y=-0.740, yaw_deg=None),
                )
            )
            runtime = SimpleNamespace(
                slam_session=Slam(),
                localization=Localization(),
            )
            with patch.dict(
                os.environ,
                {
                    "AIOT_ACTIVE_MAP_ENV_FILE": str(Path(directory) / "missing.env"),
                    "ROKI_MAP_YAML": str(map_yaml),
                    "AIOT_PATROL_LOCALIZATION_TIMEOUT_SEC": "5",
                    "AIOT_INITIALPOSE_TIMEOUT_SEC": "2",
                },
                clear=True,
            ):
                result = run_integrated._prepare_patrol_localization(
                    runtime,
                    route,
                    require_start_anchor=True,
                )

        self.assertEqual(result, (True, "START_POSE_CONFIRMED"))
        self.assertEqual(calls["posegraph"], str(Path(directory) / "posegraph"))
        seed = calls["relocalize"]
        self.assertAlmostEqual(seed["x"], -0.076)
        self.assertAlmostEqual(seed["y"], -0.052)
        self.assertAlmostEqual(seed["yaw_rad"], -1.365865, places=5)
        self.assertLessEqual(seed["timeout_sec"], 2.0)

    def test_mapping_only_preflight_allows_missing_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_route = Path(directory) / "route.local.yaml"
            with (
                patch.dict(
                    os.environ,
                    {
                        "AIOT_MAPPING_GAMEPAD_ENABLED": "true",
                        "ROKI_NAVIGATION_MODE": "encoder_limited",
                    },
                ),
                patch.object(run_integrated, "_validate_import_namespaces"),
            ):
                result = run_integrated.preflight(missing_route)

        self.assertFalse(result["routeConfigured"])
        self.assertTrue(result["mappingAvailable"])
        self.assertIsNone(result["routeId"])
        self.assertEqual(result["waypoints"], 0)

    def test_explicit_mapping_mode_ignores_stale_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stale_route = Path(directory) / "route.local.yaml"
            stale_route.write_text("stale: true\n", encoding="utf-8")
            with (
                patch.dict(
                    os.environ,
                    {
                        "AIOT_MAPPING_GAMEPAD_ENABLED": "true",
                        "AIOT_ROS_MODE": "mapping",
                        "ROKI_NAVIGATION_MODE": "nav2",
                    },
                ),
                patch.object(run_integrated, "_validate_import_namespaces"),
                patch.object(
                    run_integrated,
                    "_build_navigation_service",
                    side_effect=AssertionError("stale route must not be loaded"),
                ),
            ):
                result = run_integrated.preflight(stale_route)

        self.assertEqual(result["navigationMode"], "mapping")
        self.assertTrue(result["mappingModeRequested"])
        self.assertFalse(result["routeConfigured"])
        self.assertFalse(result["mapValidated"])

    def test_mapping_mode_remains_available_when_gamepad_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_route = Path(directory) / "route.local.yaml"
            with (
                patch.dict(
                    os.environ,
                    {
                        "AIOT_MAPPING_GAMEPAD_ENABLED": "false",
                        "AIOT_ROS_MODE": "mapping",
                        "ROKI_NAVIGATION_MODE": "encoder_limited",
                    },
                ),
                patch.object(run_integrated, "_validate_import_namespaces"),
            ):
                result = run_integrated.preflight(missing_route)

        self.assertTrue(result["mappingAvailable"])
        self.assertTrue(result["mappingModeRequested"])
        self.assertEqual(result["navigationMode"], "mapping")
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
