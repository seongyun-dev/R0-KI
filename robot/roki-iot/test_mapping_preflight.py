from __future__ import annotations

import os
import builtins
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch

import run_integrated


FIELD_ENV = {
    "ROKI_NAVIGATION_MODE": "nav2",
    "ROKI_WHEELBASE_M": "0.124",
    "ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG": "20",
    "ROKI_INITIAL_POSE_X_M": "0",
    "ROKI_INITIAL_POSE_Y_M": "0",
    "ROKI_INITIAL_POSE_YAW_RAD": "0",
    # Unit tests must not inherit a map selected by another test or the host.
    "ROKI_MAP_YAML": "",
}


class MappingPreflightTest(unittest.TestCase):
    def test_default_autonomous_builder_never_imports_manual_modules(self) -> None:
        captured: dict[str, object] = {}

        class FakeTransport:
            def start(self) -> None:
                return

        class FakeRuntime:
            def __init__(self, **kwargs) -> None:
                captured.update(kwargs)

        def module(name: str, **attributes: object) -> ModuleType:
            value = ModuleType(name)
            for key, attribute in attributes.items():
                setattr(value, key, attribute)
            return value

        fake_modules = {
            "aiot_robot.mapping_artifacts": module(
                "aiot_robot.mapping_artifacts",
                MapExportSettings=lambda *args, **kwargs: SimpleNamespace(),
                SlamMapExporter=lambda *args, **kwargs: SimpleNamespace(
                    readiness=lambda: (True, "READY")
                ),
            ),
            "integration.localization_mode": module(
                "integration.localization_mode",
                DockPose=lambda **kwargs: SimpleNamespace(**kwargs),
                LocalizationModeController=lambda *args, **kwargs: SimpleNamespace(),
                RosLocalizationModeTransport=FakeTransport,
            ),
            "integration.map_activation": module(
                "integration.map_activation",
                CurrentMapActivator=lambda *args, **kwargs: SimpleNamespace(),
                MapActivationSettings=lambda *args, **kwargs: SimpleNamespace(),
            ),
            "integration.mapping_runtime": module(
                "integration.mapping_runtime",
                ManualMappingRuntime=FakeRuntime,
                MappingRuntimeSettings=lambda *args, **kwargs: SimpleNamespace(),
            ),
            "integration.slam_session_control": module(
                "integration.slam_session_control",
                RosSlamSessionControl=lambda *args, **kwargs: SimpleNamespace(),
            ),
        }
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name in {
                "control.manual_drive_controller",
                "integration.linux_gamepad_input",
            }:
                raise AssertionError(f"manual module imported: {name}")
            return original_import(name, *args, **kwargs)

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.dict(sys.modules, fake_modules),
            patch("builtins.__import__", side_effect=guarded_import),
        ):
            run_integrated._build_mapping_runtime(
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(service_token_file="/tmp/token"),
                SimpleNamespace(release_motion_authorization=lambda _reason: None),
            )

        self.assertIsNone(captured["drive_controller"])
        self.assertIsNone(captured["gamepad_input"])
        self.assertIsNotNone(captured["motion_authorization"])

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

    def test_no_active_map_ignores_stale_route_with_legacy_ros_mode(self) -> None:
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
