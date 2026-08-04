"""Manual mapping lifecycle behind the existing Backend mapping session."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aiot_robot.backend_client import BackendConfig, RobotBackendClient
from aiot_robot.mapping_artifacts import MapArtifact


@dataclass(frozen=True)
class MappingRuntimeSettings:
    backend_base_url: str
    backend_token_file: Path
    backend_timeout_sec: float = 10.0
    upload_retry_initial_sec: float = 2.0
    upload_retry_max_sec: float = 30.0

    def __post_init__(self) -> None:
        if not self.backend_base_url:
            raise ValueError("backend_base_url is required")
        if self.backend_timeout_sec <= 0:
            raise ValueError("backend_timeout_sec must be positive")
        if self.upload_retry_initial_sec <= 0:
            raise ValueError("upload_retry_initial_sec must be positive")
        if self.upload_retry_max_sec < self.upload_retry_initial_sec:
            raise ValueError("upload retry max must be >= initial")


ClientFactory = Callable[[], RobotBackendClient]


class ManualMappingRuntime:
    """Coordinate gamepad motion, ROS map export and idempotent upload."""

    def __init__(
        self,
        *,
        runtime_service: Any,
        state_store: Any,
        drive_controller: Any,
        gamepad_input: Any,
        map_exporter: Any,
        settings: MappingRuntimeSettings,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._runtime_service = runtime_service
        self._state_store = state_store
        self._drive_controller = drive_controller
        self._gamepad_input = gamepad_input
        self._map_exporter = map_exporter
        self._settings = settings
        self._client_factory = client_factory or self._build_client
        self._lock = threading.Lock()
        self._state = "IDLE"
        self._mapping_session_id: int | None = None
        self._command_id: str | None = None
        self._worker: threading.Thread | None = None
        self._shutdown = threading.Event()
        self._completed = threading.Event()
        self._last_error: str | None = None

    @property
    def active(self) -> bool:
        with self._lock:
            return self._state != "IDLE"

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def readiness(self) -> tuple[bool, str]:
        runtime_check = getattr(self._runtime_service, "mapping_readiness", None)
        if not callable(runtime_check):
            runtime_check = getattr(self._runtime_service, "readiness", None)
        if not callable(runtime_check):
            return False, "RUNTIME_READINESS_UNAVAILABLE"
        decision = runtime_check()
        ready, reason = (
            decision
            if isinstance(decision, tuple)
            else (bool(decision), "RUNTIME_NOT_READY")
        )
        if not ready:
            return False, str(reason)
        status = self._state_store.get_status()
        if getattr(status, "lidar", None) != "NORMAL":
            return False, "LIDAR_NOT_READY"
        export_ready = self._map_exporter.readiness()
        ready, reason = (
            export_ready
            if isinstance(export_ready, tuple)
            else (bool(export_ready), "MAP_EXPORT_NOT_READY")
        )
        if not ready:
            return False, str(reason)
        try:
            self._read_token()
        except RuntimeError as exc:
            return False, str(exc)
        return True, "READY"

    def start(self, mapping_session_id: int, command_id: str) -> tuple[bool, str]:
        if isinstance(mapping_session_id, bool) or not isinstance(
            mapping_session_id, int
        ):
            return False, "INVALID_MAPPING_SESSION_ID"
        if mapping_session_id <= 0 or not command_id:
            return False, "INVALID_MAPPING_SESSION"
        with self._lock:
            if self._state != "IDLE":
                return False, "MAPPING_ALREADY_ACTIVE"
        ready, reason = self.readiness()
        if not ready:
            return False, reason

        with self._lock:
            self._state = "STARTING"
            self._mapping_session_id = mapping_session_id
            self._command_id = command_id
            self._last_error = None
            self._completed.clear()
            self._shutdown.clear()
        try:
            self._drive_controller.activate(mapping_session_id)
            self._gamepad_input.start()
        except Exception as exc:
            try:
                self._drive_controller.deactivate()
            except Exception:
                pass
            with self._lock:
                self._reset_locked()
                self._last_error = type(exc).__name__
            return False, "GAMEPAD_NOT_READY"

        with self._lock:
            self._state = "MAPPING"
        print(
            "[MAPPING] started "
            f"mappingSessionId={mapping_session_id} "
            f"controller={self._gamepad_input.device_path}"
        )
        return True, "READY"

    def finish(self) -> bool:
        """Stop motion immediately, then save and upload in a worker thread."""

        with self._lock:
            if self._state != "MAPPING":
                return False
            self._state = "SAVING"
            mapping_session_id = self._mapping_session_id
            command_id = self._command_id
        assert mapping_session_id is not None and command_id is not None
        self._gamepad_input.stop()
        self._drive_controller.deactivate()
        self._worker = threading.Thread(
            target=self._finish_worker,
            args=(mapping_session_id, command_id),
            name="mapping-save-upload",
            daemon=True,
        )
        self._worker.start()
        return True

    def stop(self) -> None:
        self._shutdown.set()
        try:
            self._gamepad_input.stop()
        finally:
            if self._drive_controller.active:
                self._drive_controller.deactivate()
        worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2.0)
        with self._lock:
            self._reset_locked()

    def wait_for_completion(self, timeout: float) -> bool:
        return self._completed.wait(timeout)

    def _finish_worker(self, mapping_session_id: int, command_id: str) -> None:
        try:
            artifact = self._map_exporter.export(mapping_session_id)
        except Exception as exc:
            print(f"[MAPPING] map export failed type={type(exc).__name__}")
            with self._lock:
                self._state = "MAPPING"
                self._last_error = type(exc).__name__
            if not self._shutdown.is_set():
                try:
                    self._drive_controller.activate(mapping_session_id)
                    self._gamepad_input.start()
                except Exception as restart_exc:
                    with self._lock:
                        self._state = "IDLE"
                        self._last_error = type(restart_exc).__name__
            return

        with self._lock:
            self._state = "UPLOADING"
        delay = self._settings.upload_retry_initial_sec
        while not self._shutdown.is_set():
            try:
                response = self._upload(mapping_session_id, command_id, artifact)
                data = response.get("data")
                if (
                    not isinstance(data, dict)
                    or data.get("mappingStatus") != "COMPLETED"
                ):
                    raise RuntimeError(
                        "backend map upload did not complete the session"
                    )
                print(
                    "[MAPPING] upload completed "
                    f"mappingSessionId={mapping_session_id} mapId={data.get('mapId')} "
                    f"mapVersion={data.get('mapVersion')}"
                )
                with self._lock:
                    self._reset_locked()
                    self._last_error = None
                self._completed.set()
                return
            except Exception as exc:
                with self._lock:
                    self._last_error = type(exc).__name__
                print(
                    "[MAPPING] upload retry scheduled "
                    f"type={type(exc).__name__} delaySec={delay:g}"
                )
                if self._shutdown.wait(delay):
                    return
                delay = min(delay * 2.0, self._settings.upload_retry_max_sec)

    def _upload(
        self,
        mapping_session_id: int,
        command_id: str,
        artifact: MapArtifact,
    ) -> dict[str, Any]:
        response = self._client_factory().upload_map(
            mapping_session_id,
            command_id,
            artifact.png_path,
            resolution=artifact.resolution,
            origin_x=artifact.origin_x,
            origin_y=artifact.origin_y,
            origin_yaw=artifact.origin_yaw,
        )
        return dict(response)

    def _build_client(self) -> RobotBackendClient:
        return RobotBackendClient(
            BackendConfig(
                self._settings.backend_base_url,
                self._read_token(),
                self._settings.backend_timeout_sec,
            )
        )

    def _read_token(self) -> str:
        token = os.getenv("AIOT_BACKEND_ACCESS_TOKEN", "").strip()
        if not token:
            try:
                token = self._settings.backend_token_file.read_text(
                    encoding="utf-8"
                ).strip()
            except OSError as exc:
                raise RuntimeError("BACKEND_TOKEN_UNAVAILABLE") from exc
        if not token:
            raise RuntimeError("BACKEND_TOKEN_UNAVAILABLE")
        return token

    def _reset_locked(self) -> None:
        self._state = "IDLE"
        self._mapping_session_id = None
        self._command_id = None
        self._worker = None
