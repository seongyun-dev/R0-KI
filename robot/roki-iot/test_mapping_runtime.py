from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aiot_robot.backend_client import BackendHttpError, BackendTransportError
from aiot_robot.mapping_artifacts import MapArtifact
from integration.mapping_runtime import ManualMappingRuntime, MappingRuntimeSettings


class FakeDrive:
    def __init__(self) -> None:
        self.active = False
        self.activated: list[int] = []
        self.deactivated = 0
        self.activate_failures_remaining = 0
        self.deactivate_failures_remaining = 0
        self.restart_entered: threading.Event | None = None
        self.restart_release: threading.Event | None = None

    def activate(self, session_id: int) -> None:
        self.active = True
        self.activated.append(session_id)
        if self.activate_failures_remaining:
            self.activate_failures_remaining -= 1
            raise RuntimeError("drive activation failed")
        if len(self.activated) > 1 and self.restart_entered is not None:
            self.restart_entered.set()
            assert self.restart_release is not None
            if not self.restart_release.wait(1.0):
                raise RuntimeError("restart release timed out")

    def deactivate(self) -> None:
        self.active = False
        self.deactivated += 1
        if self.deactivate_failures_remaining:
            self.deactivate_failures_remaining -= 1
            raise RuntimeError("drive deactivation failed")


class FakeGamepad:
    device_path = Path("/dev/input/js0")

    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self.start_failures_remaining = 0
        self.stop_failures_remaining = 0

    def start(self) -> None:
        self.started += 1
        if self.start_failures_remaining:
            self.start_failures_remaining -= 1
            raise RuntimeError("gamepad start failed")

    def stop(self) -> None:
        self.stopped += 1
        if self.stop_failures_remaining:
            self.stop_failures_remaining -= 1
            raise RuntimeError("gamepad stop failed")


class FakeExporter:
    def __init__(self, artifact: MapArtifact) -> None:
        self.artifact = artifact
        self.exported: list[int] = []
        self.failures_remaining = 0

    def readiness(self):
        return True, "READY"

    def export(self, session_id: int) -> MapArtifact:
        self.exported.append(session_id)
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("map export failed")
        return self.artifact


class FakeClient:
    def __init__(self) -> None:
        self.uploads: list[tuple] = []
        self.errors: list[Exception] = []

    def upload_map(self, *args, **kwargs):
        self.uploads.append((args, kwargs))
        if self.errors:
            raise self.errors.pop(0)
        return {
            "success": True,
            "data": {"mappingStatus": "COMPLETED", "mapId": 3, "mapVersion": 1},
        }


class FakeActivator:
    def __init__(self) -> None:
        self.activations: list[tuple[MapArtifact, object, object]] = []
        self.error: Exception | None = None

    def activate(self, artifact, *, map_id, map_version):
        self.activations.append((artifact, map_id, map_version))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(map_id=int(map_id), map_version=int(map_version))


class RacingRuntimeService:
    def __init__(self) -> None:
        self.generation = 0

    def mapping_lifecycle_marker(self) -> tuple[int, int]:
        return self.generation, 0

    def mapping_readiness(self) -> tuple[bool, str]:
        self.generation += 1
        return True, "READY"


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
        self.activator = FakeActivator()
        self.exporter = FakeExporter(self.artifact)
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
            map_exporter=self.exporter,
            map_activator=self.activator,
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
        self.assertEqual(self.activator.activations, [(self.artifact, 3, 1)])

    def test_transient_upload_failure_retries_then_activates(self) -> None:
        self.client.errors.append(BackendTransportError("offline"))
        self.assertEqual(self.runtime.start(12, "command-12"), (True, "READY"))

        self.assertTrue(self.runtime.finish())
        self.assertTrue(self.runtime.wait_for_completion(1.0))

        self.assertEqual(len(self.client.uploads), 2)
        self.assertEqual(len(self.activator.activations), 1)

    def test_retryable_http_failure_retries_then_activates(self) -> None:
        self.client.errors.append(BackendHttpError(503, "unavailable"))
        self.assertEqual(self.runtime.start(12, "command-12"), (True, "READY"))

        self.assertTrue(self.runtime.finish())
        self.assertTrue(self.runtime.wait_for_completion(1.0))

        self.assertEqual(len(self.client.uploads), 2)
        self.assertEqual(len(self.activator.activations), 1)

    def test_permanent_http_failure_stops_without_retry(self) -> None:
        self.client.errors.append(BackendHttpError(401, "unauthorized"))
        failed = threading.Event()
        reasons: list[str] = []

        def on_failure(reason: str) -> None:
            reasons.append(reason)
            self.runtime.abort(reason)
            failed.set()

        self.runtime.set_failure_listener(on_failure)
        self.assertEqual(self.runtime.start(12, "command-12"), (True, "READY"))

        self.assertTrue(self.runtime.finish())
        self.assertTrue(failed.wait(1.0))

        self.assertEqual(reasons, ["MAPPING_UPLOAD_REJECTED"])
        self.assertEqual(len(self.client.uploads), 1)
        self.assertEqual(self.activator.activations, [])
        self.assertFalse(self.runtime.active)

    def test_activation_failure_is_terminal(self) -> None:
        self.activator.error = RuntimeError("disk full")
        failed = threading.Event()
        reasons: list[str] = []

        def on_failure(reason: str) -> None:
            reasons.append(reason)
            self.runtime.abort(reason)
            failed.set()

        self.runtime.set_failure_listener(on_failure)
        self.assertEqual(self.runtime.start(12, "command-12"), (True, "READY"))

        self.assertTrue(self.runtime.finish())
        self.assertTrue(failed.wait(1.0))

        self.assertEqual(reasons, ["MAPPING_ACTIVATION_FAILED"])
        self.assertEqual(len(self.client.uploads), 1)
        self.assertFalse(self.runtime.active)

    def test_finish_stop_failure_attempts_both_and_reports_failure(self) -> None:
        failures: list[tuple[str, str, bool]] = []

        def on_failure(reason: str) -> None:
            failures.append((reason, self.runtime.state, self.runtime.motion_active))
            self.runtime.abort(reason)

        self.runtime.set_failure_listener(on_failure)
        self.assertEqual(self.runtime.start(12, "command-12"), (True, "READY"))
        self.gamepad.stop_failures_remaining = 1
        self.drive.deactivate_failures_remaining = 1

        self.assertFalse(self.runtime.finish())

        self.assertEqual(failures, [("MAPPING_STOP_FAILED", "STOPPING", True)])
        self.assertGreaterEqual(self.gamepad.stopped, 2)
        self.assertGreaterEqual(self.drive.deactivated, 1)
        self.assertEqual(self.exporter.exported, [])
        self.assertFalse(self.runtime.active)
        self.assertEqual(self.runtime.last_error, "MAPPING_STOP_FAILED")

    def test_finish_worker_start_failure_reports_terminal_failure(self) -> None:
        failures: list[tuple[str, str, bool]] = []

        def on_failure(reason: str) -> None:
            failures.append((reason, self.runtime.state, self.runtime.motion_active))
            self.runtime.abort(reason)

        self.runtime.set_failure_listener(on_failure)
        self.assertEqual(self.runtime.start(12, "command-12"), (True, "READY"))

        with patch(
            "integration.mapping_runtime.threading.Thread.start",
            side_effect=RuntimeError("thread start failed"),
        ):
            self.assertFalse(self.runtime.finish())

        self.assertEqual(
            failures,
            [("MAPPING_SAVE_WORKER_START_FAILED", "STOPPING", True)],
        )
        self.assertEqual(self.exporter.exported, [])
        self.assertFalse(self.runtime.active)
        self.assertEqual(
            self.runtime.last_error,
            "MAPPING_SAVE_WORKER_START_FAILED",
        )

    def test_export_failure_and_restart_failure_reports_terminal_failure(self) -> None:
        failures: list[tuple[str, str, bool]] = []
        failed = threading.Event()

        def on_failure(reason: str) -> None:
            failures.append((reason, self.runtime.state, self.runtime.motion_active))
            self.runtime.abort(reason)
            failed.set()

        self.runtime.set_failure_listener(on_failure)
        self.assertEqual(self.runtime.start(12, "command-12"), (True, "READY"))
        self.exporter.failures_remaining = 1
        self.drive.activate_failures_remaining = 1

        self.assertTrue(self.runtime.finish())
        self.assertTrue(failed.wait(1.0))

        self.assertEqual(
            failures,
            [("MAPPING_RESTART_FAILED", "STARTING", True)],
        )
        self.assertEqual(self.exporter.exported, [12])
        self.assertEqual(self.drive.activated, [12, 12])
        self.assertEqual(self.client.uploads, [])
        self.assertFalse(self.runtime.active)
        self.assertEqual(self.runtime.last_error, "MAPPING_RESTART_FAILED")

    def test_abort_cannot_finish_before_export_recovery_restart_is_stopped(self) -> None:
        restart_entered = threading.Event()
        restart_release = threading.Event()
        abort_attempted = threading.Event()
        abort_completed = threading.Event()
        self.drive.restart_entered = restart_entered
        self.drive.restart_release = restart_release
        self.assertEqual(self.runtime.start(12, "command-12"), (True, "READY"))
        self.exporter.failures_remaining = 1

        self.assertTrue(self.runtime.finish())
        self.assertTrue(restart_entered.wait(1.0))

        def abort_runtime() -> None:
            abort_attempted.set()
            self.runtime.abort("SERIAL_CONNECTION_RESET")
            abort_completed.set()

        abort_thread = threading.Thread(target=abort_runtime)
        abort_thread.start()
        self.assertTrue(abort_attempted.wait(1.0))
        self.assertFalse(abort_completed.wait(0.05))

        restart_release.set()
        abort_thread.join(timeout=1.0)

        self.assertTrue(abort_completed.is_set())
        self.assertFalse(self.drive.active)
        self.assertEqual(self.runtime.state, "IDLE")
        self.assertEqual(self.runtime.last_error, "SERIAL_CONNECTION_RESET")

    def test_abort_stops_motion_and_requires_a_fresh_start(self) -> None:
        self.assertEqual(self.runtime.start(12, "command-12"), (True, "READY"))
        self.assertTrue(self.runtime.motion_active)

        self.assertEqual(self.runtime.abort("SERIAL_CONNECTION_RESET"), "command-12")

        self.assertFalse(self.runtime.active)
        self.assertFalse(self.runtime.motion_active)
        self.assertEqual(self.runtime.state, "IDLE")
        self.assertEqual(self.runtime.last_error, "SERIAL_CONNECTION_RESET")
        self.assertGreaterEqual(self.gamepad.stopped, 1)
        self.assertGreaterEqual(self.drive.deactivated, 1)

        self.assertEqual(self.runtime.start(13, "command-13"), (True, "READY"))
        self.assertTrue(self.runtime.motion_active)
        self.assertEqual(self.drive.activated, [12, 13])

    def test_reconnect_between_readiness_and_activation_rolls_back(self) -> None:
        runtime = ManualMappingRuntime(
            runtime_service=RacingRuntimeService(),
            state_store=self.store,
            drive_controller=self.drive,
            gamepad_input=self.gamepad,
            map_exporter=FakeExporter(self.artifact),
            map_activator=self.activator,
            settings=self.settings,
            client_factory=lambda: self.client,
        )

        self.assertEqual(
            runtime.start(12, "mapping-race"),
            (False, "RUNTIME_LIFECYCLE_CHANGED"),
        )
        self.assertFalse(runtime.active)
        self.assertFalse(runtime.motion_active)
        self.assertFalse(self.drive.active)
        self.assertEqual(self.drive.activated, [12])
        self.assertGreaterEqual(self.drive.deactivated, 1)
        self.assertGreaterEqual(self.gamepad.stopped, 1)

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
            map_activator=self.activator,
            settings=self.settings,
            client_factory=lambda: self.client,
        )
        self.assertEqual(runtime.start(12, "command-12"), (False, "LIDAR_NOT_READY"))


if __name__ == "__main__":
    unittest.main()
