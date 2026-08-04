from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from aiot_robot.mapping_artifacts import MapArtifact
from integration.mapping_runtime import ManualMappingRuntime, MappingRuntimeSettings


class FakeDrive:
    def __init__(self) -> None:
        self.active = False
        self.activated: list[int] = []
        self.deactivated = 0

    def activate(self, session_id: int) -> None:
        self.active = True
        self.activated.append(session_id)

    def deactivate(self) -> None:
        self.active = False
        self.deactivated += 1


class FakeGamepad:
    device_path = Path("/dev/input/js0")

    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


class FakeExporter:
    def __init__(self, artifact: MapArtifact) -> None:
        self.artifact = artifact
        self.exported: list[int] = []

    def readiness(self):
        return True, "READY"

    def export(self, session_id: int) -> MapArtifact:
        self.exported.append(session_id)
        return self.artifact


class FakeClient:
    def __init__(self) -> None:
        self.uploads: list[tuple] = []

    def upload_map(self, *args, **kwargs):
        self.uploads.append((args, kwargs))
        return {
            "success": True,
            "data": {"mappingStatus": "COMPLETED", "mapId": 3, "mapVersion": 1},
        }


class MappingRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        token = root / "token"
        token.write_text("robot-token\n", encoding="utf-8")
        png = root / "map.png"
        png.write_bytes(b"png")
        self.artifact = MapArtifact(
            root,
            root / "map.yaml",
            root / "map.pgm",
            png,
            0.05,
            -1.0,
            -2.0,
            0.0,
        )
        self.drive = FakeDrive()
        self.gamepad = FakeGamepad()
        self.client = FakeClient()
        self.settings = MappingRuntimeSettings(
            "https://example.com", token, 3, 0.01, 0.02
        )
        self.store = SimpleNamespace(
            get_status=lambda: SimpleNamespace(
                lidar="NORMAL",
                obstacle=SimpleNamespace(status="STOP"),
            )
        )
        self.runtime = ManualMappingRuntime(
            runtime_service=SimpleNamespace(mapping_readiness=lambda: (True, "READY")),
            state_store=self.store,
            drive_controller=self.drive,
            gamepad_input=self.gamepad,
            map_exporter=FakeExporter(self.artifact),
            settings=self.settings,
            client_factory=lambda: self.client,
        )

    def tearDown(self) -> None:
        self.runtime.stop()

    def test_start_requires_only_mapping_readiness_not_obstacle_clear(self) -> None:
        self.assertEqual(self.runtime.start(12, "command-12"), (True, "READY"))
        self.assertTrue(self.runtime.active)
        self.assertEqual(self.drive.activated, [12])
        self.assertEqual(self.gamepad.started, 1)

    def test_finish_stops_motion_exports_and_uploads_existing_contract(self) -> None:
        self.assertEqual(self.runtime.start(12, "command-12"), (True, "READY"))
        self.assertTrue(self.runtime.finish())
        self.assertTrue(self.runtime.wait_for_completion(1.0))

        self.assertFalse(self.runtime.active)
        self.assertGreaterEqual(self.gamepad.stopped, 1)
        self.assertGreaterEqual(self.drive.deactivated, 1)
        args, kwargs = self.client.uploads[0]
        self.assertEqual(args[:3], (12, "command-12", self.artifact.png_path))
        self.assertEqual(kwargs["resolution"], 0.05)

    def test_lidar_is_a_required_mapping_dependency(self) -> None:
        self.store = SimpleNamespace(
            get_status=lambda: SimpleNamespace(lidar="DISCONNECTED")
        )
        runtime = ManualMappingRuntime(
            runtime_service=SimpleNamespace(mapping_readiness=lambda: (True, "READY")),
            state_store=self.store,
            drive_controller=self.drive,
            gamepad_input=self.gamepad,
            map_exporter=FakeExporter(self.artifact),
            settings=self.settings,
            client_factory=lambda: self.client,
        )
        self.assertEqual(runtime.start(12, "command-12"), (False, "LIDAR_NOT_READY"))


if __name__ == "__main__":
    unittest.main()
