import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROBOT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROBOT_ROOT / "roki"))
# The bundled desktop test runtime has no PyYAML. This contract test exercises
# parse_route only; provide an inert import stub instead of installing packages.
if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda _source: None
    sys.modules["yaml"] = yaml_stub

from aiot_robot.navigation_config import (  # noqa: E402
    BackendNavigationConfigProvider,
    NavigationConfigError,
    NavigationConfigIdentity,
)
from aiot_robot.backend_client import BackendTransportError  # noqa: E402


NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


def response(*, map_version: int = 3, destination_action: str = "DESTINATION"):
    return {
        "success": True,
        "data": {
            "schemaVersion": 1,
            "map": {
                "mapId": 7,
                "mapVersion": map_version,
                "mapName": "demo",
                "resolution": 0.05,
                "originX": -1.0,
                "originY": -2.0,
                "originYaw": 0.0,
                "width": 200,
                "height": 100,
            },
            "zones": [
                {
                    "zoneId": 11,
                    "name": "지하 주차장",
                    "type": "PARKING",
                    "minX": 0.0,
                    "minY": 0.0,
                    "maxX": 3.0,
                    "maxY": 2.0,
                }
            ],
            "waypoints": [
                {
                    "waypointId": 21,
                    "sequence": 1,
                    "x": 0.0,
                    "y": 0.0,
                    "action": "SCAN",
                    "yaw": None,
                    "acceptanceRadius": 0.30,
                    "zoneId": 11,
                },
                {
                    "waypointId": 22,
                    "sequence": 2,
                    "x": 1.0,
                    "y": 0.0,
                    "action": destination_action,
                    "yaw": 1.5707963267948966,
                    "acceptanceRadius": None,
                    "zoneId": None,
                },
            ],
        },
    }


class FakeBackend:
    def __init__(self, payload):
        self.payload = payload
        self.timeout_seconds = None

    def get_navigation_config(self, *, timeout_seconds=None):
        self.timeout_seconds = timeout_seconds
        return self.payload


class NavigationConfigProviderTest(unittest.TestCase):
    def provider(self, payload):
        return BackendNavigationConfigProvider(
            backend_factory=lambda: FakeBackend(payload),
            navigation_factory=lambda route: route,
            identity=NavigationConfigIdentity("7", 3),
            wall_clock=lambda: NOW,
        )

    def test_converts_backend_contract_to_existing_route(self) -> None:
        route = self.provider(response()).load_navigation()

        self.assertEqual(route.map_id, "7")
        self.assertEqual(route.map_version, 3)
        self.assertEqual(route.route_id, "backend-map-7-v3")
        self.assertEqual(route.waypoints[0].zone_id, 11)
        self.assertEqual(route.waypoints[0].name, "지하 주차장")
        self.assertIsNone(route.waypoints[0].yaw_deg)
        self.assertEqual(route.waypoints[1].yaw_deg, 90.0)
        self.assertEqual(route.waypoints[1].acceptance_radius_m, 0.30)

    def test_rejects_remote_map_identity_mismatch(self) -> None:
        with self.assertRaises(NavigationConfigError) as raised:
            self.provider(response(map_version=4)).load_navigation()

        self.assertEqual(raised.exception.reason, "NAVIGATION_MAP_MISMATCH")

    def test_rejects_route_without_final_destination(self) -> None:
        with self.assertRaises(NavigationConfigError) as raised:
            self.provider(response(destination_action="PASS")).load_navigation()

        self.assertEqual(raised.exception.reason, "NAVIGATION_CONFIG_INVALID")

    def test_rejects_backend_radius_outside_contract(self) -> None:
        for radius in (0.199, 1.01):
            with self.subTest(radius=radius):
                payload = response()
                payload["data"]["waypoints"][0]["acceptanceRadius"] = radius

                with self.assertRaises(NavigationConfigError) as raised:
                    self.provider(payload).load_navigation()

                self.assertEqual(
                    raised.exception.reason,
                    "NAVIGATION_CONFIG_INVALID",
                )

    def test_masks_transport_failure_as_safe_reason(self) -> None:
        class UnavailableBackend:
            def get_navigation_config(self, *, timeout_seconds=None):
                del timeout_seconds
                raise BackendTransportError("secret")

        provider = BackendNavigationConfigProvider(
            backend_factory=UnavailableBackend,
            navigation_factory=lambda route: route,
            identity=NavigationConfigIdentity("7", 3),
            wall_clock=lambda: NOW,
        )

        with self.assertRaises(NavigationConfigError) as raised:
            provider.load_navigation()

        self.assertEqual(raised.exception.reason, "NAVIGATION_CONFIG_UNAVAILABLE")
        self.assertTrue(raised.exception.local_fallback_allowed)
        self.assertNotIn("secret", str(raised.exception))

    def test_factory_and_map_safety_failures_do_not_allow_fallback(self) -> None:
        factory_failure = BackendNavigationConfigProvider(
            backend_factory=lambda: (_ for _ in ()).throw(RuntimeError("secret")),
            navigation_factory=lambda route: route,
            identity=NavigationConfigIdentity("7", 3),
            wall_clock=lambda: NOW,
        )
        with self.assertRaises(NavigationConfigError) as raised:
            factory_failure.load_navigation()
        self.assertEqual(raised.exception.reason, "NAVIGATION_CONFIG_INVALID")
        self.assertFalse(raised.exception.local_fallback_allowed)

        unsafe_route = BackendNavigationConfigProvider(
            backend_factory=lambda: FakeBackend(response()),
            navigation_factory=lambda _route: (_ for _ in ()).throw(
                RuntimeError("occupancy unsafe")
            ),
            identity=NavigationConfigIdentity("7", 3),
            wall_clock=lambda: NOW,
        )
        with self.assertRaises(NavigationConfigError) as raised:
            unsafe_route.load_navigation()
        self.assertEqual(raised.exception.reason, "NAVIGATION_ROUTE_INVALID")
        self.assertFalse(raised.exception.local_fallback_allowed)

    def test_navigation_fetch_timeout_is_bounded_by_command_deadline(self) -> None:
        backend = FakeBackend(response())
        provider = BackendNavigationConfigProvider(
            backend_factory=lambda: backend,
            navigation_factory=lambda route: route,
            identity=NavigationConfigIdentity("7", 3),
            wall_clock=lambda: NOW,
        )

        provider.load_navigation(deadline=NOW + timedelta(seconds=2))

        self.assertAlmostEqual(backend.timeout_seconds, 1.95)

    def test_elapsed_deadline_rejects_before_backend_call(self) -> None:
        backend = FakeBackend(response())
        provider = BackendNavigationConfigProvider(
            backend_factory=lambda: backend,
            navigation_factory=lambda route: route,
            identity=NavigationConfigIdentity("7", 3),
            wall_clock=lambda: NOW,
        )

        with self.assertRaises(NavigationConfigError) as raised:
            provider.load_navigation(deadline=NOW)

        self.assertEqual(raised.exception.reason, "NAVIGATION_COMMAND_EXPIRED")
        self.assertIsNone(backend.timeout_seconds)

    def test_local_map_metadata_validator_is_mandatory_and_fail_closed(self) -> None:
        observed = []
        provider = BackendNavigationConfigProvider(
            backend_factory=lambda: FakeBackend(response()),
            navigation_factory=lambda route: route,
            identity=NavigationConfigIdentity("7", 3),
            wall_clock=lambda: NOW,
            map_metadata_validator=observed.append,
        )

        provider.load_navigation()

        self.assertEqual(observed[0]["resolution"], 0.05)
        self.assertEqual(observed[0]["width"], 200)

        def reject(_map_config):
            raise NavigationConfigError("NAVIGATION_MAP_METADATA_MISMATCH")

        mismatched = BackendNavigationConfigProvider(
            backend_factory=lambda: FakeBackend(response()),
            navigation_factory=lambda route: route,
            identity=NavigationConfigIdentity("7", 3),
            wall_clock=lambda: NOW,
            map_metadata_validator=reject,
        )
        with self.assertRaises(NavigationConfigError) as raised:
            mismatched.load_navigation()
        self.assertEqual(
            raised.exception.reason,
            "NAVIGATION_MAP_METADATA_MISMATCH",
        )
        self.assertFalse(raised.exception.local_fallback_allowed)


if __name__ == "__main__":
    unittest.main()
