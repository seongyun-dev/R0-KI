"""Manual mapping lifecycle behind the existing Backend mapping session."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aiot_robot.backend_client import (
    BackendConfig,
    BackendError,
    BackendHttpError,
    BackendTransportError,
    RobotBackendClient,
)
from aiot_robot.mapping_artifacts import MapArtifact
from integration.explore_supervisor import ExploreSupervisor


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
FailureListener = Callable[[str], None]


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
        map_activator: Any,
        settings: MappingRuntimeSettings,
        client_factory: ClientFactory | None = None,
        explore_supervisor: Any | None = None,
        localization: Any | None = None,
    ) -> None:
        self._runtime_service = runtime_service
        self._state_store = state_store
        self._drive_controller = drive_controller
        self._gamepad_input = gamepad_input
        self._map_exporter = map_exporter
        self._map_activator = map_activator
        # 매핑<->순찰 전환. None 이면 전환을 시도하지 않는다 -- 기존 테스트가
        # 이 의존성을 모른 채로도 성립해야 한다.
        self._localization = localization
        self._settings = settings
        self._client_factory = client_factory or self._build_client
        # The explorer's lifetime belongs to the mapping session, not to the
        # ROS service (see explore_supervisor.py). Built from the environment
        # here so run_integrated's construction call stays untouched; None
        # when autonomous mapping is not enabled.
        self._explore = (
            explore_supervisor
            if explore_supervisor is not None
            else ExploreSupervisor.from_environment()
        )
        self._lock = threading.Lock()
        self._state = "IDLE"
        self._mapping_session_id: int | None = None
        self._command_id: str | None = None
        self._worker: threading.Thread | None = None
        self._shutdown = threading.Event()
        self._completed = threading.Event()
        self._last_error: str | None = None
        self._failure_listener: FailureListener | None = None

    @property
    def active(self) -> bool:
        with self._lock:
            return self._state != "IDLE"

    @property
    def motion_active(self) -> bool:
        with self._lock:
            return self._state in {"STARTING", "MAPPING", "STOPPING"}

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def lifecycle_snapshot(self) -> tuple[str, int | None]:
        """Return the current mapping state and session as one atomic snapshot."""

        with self._lock:
            return self._state, self._mapping_session_id

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def motion_timeline_diagnostic_context(self) -> dict[str, object]:
        """Aggregate read-only mapping/gamepad context for Runtime fault logs."""

        with self._lock:
            context: dict[str, object] = {
                "mappingState": self._state,
                "mappingMotionActive": self._state
                in {"STARTING", "MAPPING", "STOPPING"},
            }
        snapshot = getattr(self._gamepad_input, "diagnostic_snapshot", None)
        if not callable(snapshot):
            context.update(
                {
                    "gamepadDeviceOpen": "unavailable",
                    "gamepadThreadAlive": "unavailable",
                    "lastGamepadDecision": "unavailable",
                    "lastGamepadDecisionAgoMs": "unavailable",
                }
            )
            return context
        try:
            gamepad_context = snapshot()
        except Exception:
            gamepad_context = {}
        for key in (
            "gamepadDeviceOpen",
            "gamepadThreadAlive",
            "lastGamepadDecision",
            "lastGamepadDecisionAgoMs",
        ):
            context[key] = gamepad_context.get(key, "unavailable")
        return context

    def set_failure_listener(self, listener: FailureListener) -> None:
        """Report terminal mapping failures through the command ACK owner."""

        if not callable(listener):
            raise ValueError("mapping failure listener must be callable")
        with self._lock:
            self._failure_listener = listener

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

    def _enter_patrol_localization(self, activated: Any) -> None:
        """방금 활성화한 지도의 포즈그래프로 위치추정을 켠다.

        세션 디렉터리가 아니라 활성 지도 디렉터리를 쓴다. 세션 산출물은
        임시이고, 활성 번들이 다음 부팅에도 남는 쪽이다. 경로 규약은
        map_exporter/map_activation 과 짝을 이룬다: 디렉터리 안의
        ``posegraph`` 접두사에 .posegraph 와 .data 가 놓인다.
        """

        if self._localization is None:
            return
        posegraph = Path(activated.yaml_path).parent / "posegraph"
        ready, reason = self._localization.enter_patrol(str(posegraph))
        if not ready:
            # 지도는 이미 저장·업로드됐다. 순찰 시작 시 다시 시도하면 되므로
            # 매핑 세션을 실패로 되돌리지 않는다.
            print(f"[MAPPING] localization handover deferred reason={reason}")

    def start(self, mapping_session_id: int, command_id: str) -> tuple[bool, str]:
        if isinstance(mapping_session_id, bool) or not isinstance(
            mapping_session_id, int
        ):
            return False, "INVALID_MAPPING_SESSION_ID"
        if mapping_session_id <= 0 or not command_id:
            return False, "INVALID_MAPPING_SESSION"
        lifecycle_marker = self._capture_lifecycle_marker()
        with self._lock:
            if self._state != "IDLE":
                return False, "MAPPING_ALREADY_ACTIVE"
            self._state = "STARTING"
            self._mapping_session_id = mapping_session_id
            self._command_id = command_id
            self._last_error = None
            self._completed.clear()
            self._shutdown.clear()

        ready, reason = self.readiness()
        if not ready:
            self._rollback_start(reason)
            return False, reason
        # 새 세션은 깨끗한 지도에서 시작해야 한다. 위치추정 모드로 남아 있으면
        # 이전 지도의 포즈그래프 위에 그리게 되고, 매핑 모드로 돌리는 이 호출이
        # 위치추정 버퍼를 비운다. 예전에는 이걸 하려고 aiot-ros 를 재시작했다.
        if self._localization is not None:
            entered, mode_reason = self._localization.enter_mapping()
            if not entered:
                self._rollback_start(mode_reason)
                return False, mode_reason
        try:
            self._drive_controller.activate(mapping_session_id)
            self._gamepad_input.start()
        except Exception as exc:
            self._rollback_start(type(exc).__name__)
            return False, "GAMEPAD_NOT_READY"

        if not self._lifecycle_unchanged(lifecycle_marker):
            self._rollback_start("RUNTIME_LIFECYCLE_CHANGED")
            return False, "RUNTIME_LIFECYCLE_CHANGED"

        with self._lock:
            if self._state != "STARTING" or self._shutdown.is_set():
                interrupted = True
            else:
                interrupted = False
                self._state = "MAPPING"
        if interrupted:
            self._rollback_start("MAPPING_START_INTERRUPTED")
            return False, "MAPPING_START_INTERRUPTED"

        print(
            "[MAPPING] started "
            f"mappingSessionId={mapping_session_id} "
            f"controller={self._gamepad_input.device_path}"
        )
        # Only after the session is committed: the motion gate is open now, so
        # the explorer's very first goal can actually drive the chassis
        # instead of being refused and blacklisting its frontier.
        if self._explore is not None:
            self._explore.start(mapping_session_id)
        return True, "READY"

    def finish(self, mapping_session_id: int | None = None) -> bool:
        """Stop motion immediately, then save and upload in a worker thread."""

        with self._lock:
            if (
                mapping_session_id is not None
                and self._mapping_session_id != mapping_session_id
            ):
                return False
            if self._state != "MAPPING":
                return False
            self._state = "STOPPING"
            mapping_session_id = self._mapping_session_id
            command_id = self._command_id
        assert mapping_session_id is not None and command_id is not None

        # Silence the goal source before cutting the chassis: STOPPING still
        # keeps the motion gate open, so a live explorer would keep steering
        # the robot while the map is being saved.
        if self._explore is not None:
            self._explore.stop("finish")
        stop_failures = self._stop_mapping_motion("finish")
        if stop_failures:
            self._notify_failure("MAPPING_STOP_FAILED")
            return False

        worker = threading.Thread(
            target=self._finish_worker,
            args=(mapping_session_id, command_id),
            name="mapping-save-upload",
            daemon=True,
        )
        with self._lock:
            if self._state != "STOPPING" or self._shutdown.is_set():
                return False
            self._state = "SAVING"
            self._worker = worker
            try:
                worker.start()
            except Exception as exc:
                # Preserve the command/session until the failure listener has
                # published a terminal ACK. STOPPING is intentionally treated
                # as lifecycle-active by CommandHandler.on_runtime_failure().
                self._state = "STOPPING"
                self._last_error = type(exc).__name__
                print(
                    "[MAPPING] save worker start failed "
                    f"type={type(exc).__name__}"
                )
                worker_start_failed = True
            else:
                worker_start_failed = False
        if worker_start_failed:
            self._notify_failure("MAPPING_SAVE_WORKER_START_FAILED")
            return False
        return True

    def stop(self) -> None:
        self._shutdown.set()
        if self._explore is not None:
            self._explore.stop("shutdown")
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

    def abort(self, reason: str) -> str | None:
        """Fail-close active gamepad motion and require a new START_MAPPING."""

        if not reason:
            raise ValueError("mapping abort reason is required")
        with self._lock:
            if self._state == "IDLE":
                return None
            command_id = self._command_id
            self._state = "ABORTING"
            self._shutdown.set()
        self._stop_mapping_motion("abort")
        if self._explore is not None:
            self._explore.stop(reason)
        with self._lock:
            self._reset_locked()
            self._last_error = reason
        print(f"[MAPPING] aborted reason={reason}")
        return command_id

    def wait_for_completion(self, timeout: float) -> bool:
        return self._completed.wait(timeout)

    def _finish_worker(self, mapping_session_id: int, command_id: str) -> None:
        try:
            artifact = self._map_exporter.export(mapping_session_id)
        except Exception as exc:
            print(f"[MAPPING] map export failed type={type(exc).__name__}")
            with self._lock:
                if self._shutdown.is_set():
                    return
                self._state = "STARTING"
                self._last_error = type(exc).__name__
            restart_exc: Exception | None = None
            with self._lock:
                if self._state != "STARTING" or self._shutdown.is_set():
                    return
                try:
                    # Serialize recovery with abort(): once abort owns the
                    # lifecycle lock, no input source may be restarted after it
                    # has returned.
                    self._drive_controller.activate(mapping_session_id)
                    self._gamepad_input.start()
                except Exception as exc:
                    restart_exc = exc
                    self._last_error = type(exc).__name__
                else:
                    self._state = "MAPPING"
            if restart_exc is not None:
                print(
                    "[MAPPING] map export recovery failed "
                    f"type={type(restart_exc).__name__}"
                )
                self._notify_failure("MAPPING_RESTART_FAILED")
                return
            return

        with self._lock:
            self._state = "UPLOADING"
        delay = self._settings.upload_retry_initial_sec
        while not self._shutdown.is_set():
            try:
                response = self._upload(mapping_session_id, command_id, artifact)
            except BackendTransportError as exc:
                delay = self._schedule_upload_retry(exc, delay)
                continue
            except BackendHttpError as exc:
                if exc.retryable:
                    delay = self._schedule_upload_retry(exc, delay)
                    continue
                self._terminal_failure("MAPPING_UPLOAD_REJECTED", exc)
                return
            except BackendError as exc:
                self._terminal_failure("MAPPING_UPLOAD_INVALID_RESPONSE", exc)
                return
            except Exception as exc:
                self._terminal_failure("MAPPING_UPLOAD_FAILED", exc)
                return

            data = response.get("data")
            if (
                not isinstance(data, dict)
                or data.get("mappingStatus") != "COMPLETED"
                or data.get("mapId") is None
                or data.get("mapVersion") is None
            ):
                self._terminal_failure(
                    "MAPPING_UPLOAD_INVALID_RESPONSE",
                    RuntimeError("backend map upload did not complete the session"),
                )
                return
            try:
                activated = self._map_activator.activate(
                    artifact,
                    map_id=data["mapId"],
                    map_version=data["mapVersion"],
                )
            except Exception as exc:
                self._terminal_failure("MAPPING_ACTIVATION_FAILED", exc)
                return

            print(
                "[MAPPING] upload and activation completed "
                f"mappingSessionId={mapping_session_id} mapId={activated.map_id} "
                f"mapVersion={activated.map_version}"
            )
            # 방금 그린 지도로 위치추정을 시작한다. 예전에는 여기서 env 파일에
            # AIOT_ROS_MODE=patrol 을 적고 서비스를 재시작했다. 그 재시작이
            # 진행 중이던 세션을 고아로 만들고 시리얼을 다시 열게 했다.
            # 실패해도 매핑 자체는 성공이므로 세션을 실패로 만들지는 않는다 --
            # 순찰을 시작할 때 다시 시도한다.
            self._enter_patrol_localization(activated)
            with self._lock:
                self._reset_locked()
                self._last_error = None
            self._completed.set()
            return

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

    def _schedule_upload_retry(self, exc: Exception, delay: float) -> float:
        with self._lock:
            self._last_error = type(exc).__name__
        print(
            "[MAPPING] transient upload retry scheduled "
            f"type={type(exc).__name__} delaySec={delay:g}"
        )
        if self._shutdown.wait(delay):
            return delay
        return min(delay * 2.0, self._settings.upload_retry_max_sec)

    def _terminal_failure(self, reason: str, exc: Exception) -> None:
        with self._lock:
            self._last_error = type(exc).__name__
        print(f"[MAPPING] terminal failure reason={reason} type={type(exc).__name__}")
        self._notify_failure(reason)

    def _capture_lifecycle_marker(self) -> object | None:
        marker = getattr(self._runtime_service, "mapping_lifecycle_marker", None)
        return marker() if callable(marker) else None

    def _lifecycle_unchanged(self, marker: object | None) -> bool:
        current = getattr(
            self._runtime_service,
            "mapping_lifecycle_marker",
            None,
        )
        return marker is None or (callable(current) and current() == marker)

    def _rollback_start(self, reason: str) -> None:
        try:
            self._gamepad_input.stop()
        except Exception as exc:
            print(f"[MAPPING] gamepad rollback failed type={type(exc).__name__}")
        try:
            if self._drive_controller.active:
                self._drive_controller.deactivate()
        except Exception as exc:
            print(f"[MAPPING] drive rollback failed type={type(exc).__name__}")
        with self._lock:
            self._reset_locked()
            self._last_error = reason

    def _stop_mapping_motion(self, operation: str) -> list[Exception]:
        failures: list[Exception] = []
        try:
            self._gamepad_input.stop()
        except Exception as exc:
            failures.append(exc)
            print(
                f"[MAPPING] gamepad {operation} failed "
                f"type={type(exc).__name__}"
            )
        try:
            self._drive_controller.deactivate()
        except Exception as exc:
            failures.append(exc)
            print(
                f"[MAPPING] drive {operation} failed "
                f"type={type(exc).__name__}"
            )
        return failures

    def _notify_failure(self, reason: str) -> None:
        with self._lock:
            listener = self._failure_listener
        if listener is not None:
            try:
                listener(reason)
            except Exception as exc:
                print(
                    "[MAPPING] failure listener failed "
                    f"reason={reason} type={type(exc).__name__}"
                )
        # The production listener aborts and publishes the FAILED command ACK.
        # Keep standalone/test compositions fail-closed if it is absent or fails.
        if self.active:
            self.abort(reason)

    def _reset_locked(self) -> None:
        self._state = "IDLE"
        self._mapping_session_id = None
        self._command_id = None
        self._worker = None
