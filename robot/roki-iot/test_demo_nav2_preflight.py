from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from navigation.map_metadata import (
    file_sha256,
    load_map_metadata,
    map_bundle_sha256,
)
from navigation.route import RouteValidationError
from run_integrated import (
    _build_navigation_service,
    _navigation_mode,
    _validate_backend_map_metadata_against_local,
)
from aiot_robot.navigation_config import NavigationConfigError


class DemoNav2PreflightTest(unittest.TestCase):
    def nav2_environment(self) -> dict[str, str]:
        return {
            "ROKI_NAVIGATION_MODE": "nav2",
            "ROKI_WHEELBASE_M": "0.124",
            "ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG": "8.6",
            "ROKI_INITIAL_POSE_X_M": "0.5",
            "ROKI_INITIAL_POSE_Y_M": "0.5",
            "ROKI_INITIAL_POSE_YAW_RAD": "0.0",
        }

    def make_map_and_route(
        self,
        root: Path,
        *,
        waypoint_x: float = 1.0,
        acceptance_radius_m: float = 0.2,
        frame_id: str = "map",
        map_pixels: bytes | None = None,
    ) -> tuple[Path, Path]:
        pixels = map_pixels if map_pixels is not None else bytes([255]) * 10_000
        self.assertEqual(len(pixels), 10_000)
        (root / "map.pgm").write_bytes(b"P5\n100 100\n255\n" + pixels)
        map_path = root / "map.yaml"
        map_path.write_text(
            """image: map.pgm
resolution: 0.05
origin: [0.0, 0.0, 0.0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.25
""",
            encoding="utf-8",
        )
        route_path = root / "route.yaml"
        route_path.write_text(
            f"""schema_version: 1
map_id: demo-map
map_version: 1
route_id: demo-route
frame_id: {frame_id}
waypoints:
  - sequence: 1
    name: DESTINATION
    x: {waypoint_x}
    y: 1.0
    yaw_deg: 0.0
    acceptance_radius_m: {acceptance_radius_m}
    action: DESTINATION
""",
            encoding="utf-8",
        )
        return map_path, route_path

    def deployment_environment(
        self,
        map_path: Path,
        route_path: Path,
    ) -> dict[str, str]:
        metadata = load_map_metadata(map_path)
        return {
            **self.nav2_environment(),
            "ROKI_MAP_YAML": str(map_path),
            "ROKI_MAP_ID": "demo-map",
            "ROKI_MAP_VERSION": "1",
            "ROKI_MAP_SHA256": map_bundle_sha256(metadata),
            "ROKI_ROUTE_SHA256": file_sha256(route_path),
        }

    def test_auto_and_encoder_limited_modes_are_rejected(self) -> None:
        for mode in ("auto", "encoder_limited"):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(RuntimeError, "DEMO_NAV2_REQUIRED"):
                    _navigation_mode(SimpleNamespace(navigation_mode=mode))

    def test_nav2_requires_complete_fixed_dock_configuration(self) -> None:
        environment = self.nav2_environment()
        del environment["ROKI_INITIAL_POSE_X_M"]
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(
                RuntimeError, "NAV2_FIELD_CONFIG_INVALID.*ROKI_INITIAL_POSE_X_M"
            ):
                _navigation_mode(SimpleNamespace(navigation_mode="nav2"))

    def test_nav2_mode_passes_when_packages_and_field_values_exist(self) -> None:
        with patch.dict(os.environ, self.nav2_environment(), clear=True), patch(
            "run_integrated.importlib.util.find_spec", return_value=object()
        ):
            self.assertEqual(
                _navigation_mode(SimpleNamespace(navigation_mode="nav2")),
                "nav2",
            )

    def test_production_route_identity_and_bounds_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            map_path, route_path = self.make_map_and_route(root)
            environment = self.deployment_environment(map_path, route_path)
            with patch.dict(os.environ, environment, clear=True):
                service = _build_navigation_service(
                    route_path,
                    encoder_limited=False,
                )
            self.assertEqual(service.route.route_id, "demo-route")

    def test_route_radius_cannot_be_smaller_than_rendered_nav2_tolerance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            map_path, route_path = self.make_map_and_route(
                root,
                acceptance_radius_m=0.24,
            )
            environment = self.deployment_environment(map_path, route_path)
            environment["ROKI_NAV2_XY_GOAL_TOLERANCE_M"] = "0.25"
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(
                    RouteValidationError,
                    "below Nav2 xy_goal_tolerance",
                ):
                    _build_navigation_service(
                        route_path,
                        encoder_limited=False,
                    )

    def test_out_of_bounds_route_is_rejected_but_dock_is_not_a_route_gate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            map_path, route_path = self.make_map_and_route(
                root, waypoint_x=10.0
            )
            environment = self.deployment_environment(map_path, route_path)
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(RouteValidationError, "waypoint 1.*outside"):
                    _build_navigation_service(route_path, encoder_limited=False)

            map_path, valid_route = self.make_map_and_route(root)
            environment = self.deployment_environment(map_path, valid_route)
            environment["ROKI_INITIAL_POSE_X_M"] = "10.0"
            with patch.dict(os.environ, environment, clear=True):
                service = _build_navigation_service(
                    valid_route,
                    encoder_limited=False,
                )
            self.assertEqual(service.route.route_id, "demo-route")

    def test_non_map_route_and_encoder_diagnostic_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            map_path, route_path = self.make_map_and_route(
                root, frame_id="odom"
            )
            environment = self.deployment_environment(map_path, route_path)
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(RouteValidationError, "frame_id must be map"):
                    _build_navigation_service(route_path, encoder_limited=False)
                with self.assertRaisesRegex(RuntimeError, "DEMO_NAV2_REQUIRED"):
                    _build_navigation_service(route_path, encoder_limited=True)

    def test_mostly_unknown_map_is_left_to_nav2_live_costmaps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pixels = bytes([255]) * 314 + bytes([128]) * 9_686
            map_path, route_path = self.make_map_and_route(
                root,
                map_pixels=pixels,
            )
            environment = self.deployment_environment(map_path, route_path)

            with patch.dict(os.environ, environment, clear=True):
                service = _build_navigation_service(
                    route_path,
                    encoder_limited=False,
                )
            self.assertEqual(service.route.route_id, "demo-route")

    def test_waypoint_footprint_is_left_to_nav2_live_costmaps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pixels = bytearray([255] * 10_000)
            # world (1.0m, 1.0m) -> grid column 20, image row 79.
            pixels[79 * 100 + 20] = 0
            map_path, route_path = self.make_map_and_route(
                root,
                map_pixels=bytes(pixels),
            )
            environment = self.deployment_environment(map_path, route_path)

            with patch.dict(os.environ, environment, clear=True):
                service = _build_navigation_service(
                    route_path,
                    encoder_limited=False,
                )
            self.assertEqual(service.route.route_id, "demo-route")

    def test_rejects_missing_or_mismatched_deployment_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            map_path, route_path = self.make_map_and_route(root)
            environment = self.deployment_environment(map_path, route_path)
            del environment["ROKI_MAP_ID"]
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(RuntimeError, "ROKI_MAP_ID"):
                    _build_navigation_service(route_path, encoder_limited=False)

            environment = self.deployment_environment(map_path, route_path)
            environment["ROKI_ROUTE_SHA256"] = "0" * 64
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(
                    RouteValidationError,
                    "route SHA256",
                ):
                    _build_navigation_service(route_path, encoder_limited=False)

    def test_backend_map_metadata_must_match_local_occupancy_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            map_path, _route_path = self.make_map_and_route(root)
            map_path.write_text(
                """image: map.pgm
resolution: 0.05004
origin: [0.1234, -0.5678, 0.004]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.25
""",
                encoding="utf-8",
            )
            config = {
                "resolution": 0.05,
                "originX": 0.123,
                "originY": -0.568,
                "originYaw": 0.0,
                "width": 100,
                "height": 100,
            }
            with patch.dict(os.environ, {"ROKI_MAP_YAML": str(map_path)}):
                # Backend DECIMAL scales may round the original YAML by up to
                # half of the stored unit; this is the same uploaded map.
                _validate_backend_map_metadata_against_local(config)
                config["originX"] = 0.1241
                with self.assertRaises(NavigationConfigError) as raised:
                    _validate_backend_map_metadata_against_local(config)

            self.assertEqual(
                raised.exception.reason,
                "NAVIGATION_MAP_METADATA_MISMATCH",
            )
            self.assertFalse(raised.exception.local_fallback_allowed)


if __name__ == "__main__":
    unittest.main()
