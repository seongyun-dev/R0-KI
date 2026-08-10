from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_integrated


class MappingPreflightTest(unittest.TestCase):
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

    def test_preflight_still_requires_route_when_mapping_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_route = Path(directory) / "route.local.yaml"
            with (
                patch.dict(
                    os.environ,
                    {
                        "AIOT_MAPPING_GAMEPAD_ENABLED": "false",
                        "ROKI_NAVIGATION_MODE": "encoder_limited",
                    },
                ),
                patch.object(run_integrated, "_validate_import_namespaces"),
            ):
                with self.assertRaisesRegex(RuntimeError, "route file is missing"):
                    run_integrated.preflight(missing_route)


if __name__ == "__main__":
    unittest.main()
