"""Mapping lifecycle behind the existing Backend mapping session."""

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
    fresh_map_timeout_sec: float = 30.0

    def __post_init__(self) -> None:
        if not self.backend_base_url:
            raise ValueError("backend_base_url is required")
        if self.backend_timeout_sec <= 0:
            raise ValueError("backend_timeout_sec must be positive")
        if self.upload_retry_initial_sec <= 0:
            raise ValueError("upload_retry_initial_sec must be positive")
        if self.upload_retry_max_sec < self.upload_retry_initial_sec:
            raise ValueError("upload retry max must be >= initial")
        if self.fresh_map_timeout_sec <= 0:
            raise ValueError("fresh_map_timeout_sec must be positive")


ClientFactory = Callable[[], RobotBackendClient]
FailureListener = Callable[[str], None]


class ManualMappingRuntime:
    """Coordinate autonomous/manual motion, ROS export and idempotent upload."""

    def __init__(
        self,
        *,
        runtime_service: Any,
        state_store: Any,
        drive_controller: Any | None = None,
        gamepad_input: Any | None = None,
        map_exporter: Any,
        map_activator: Any,
        settings: MappingRuntimeSettings,
        client_factory: ClientFactory | None = None,
        explore_supervisor: Any | None = None,
        localization: Any | None = None,
        slam_session: Any | None = None,
        motion_authorization: Any | None = None,
    ) -> None:
        if (drive_controller is None) != (gamepad_input is None):
            raise ValueError(
                "drive_controller and gamepad_input must be configured together"
            )
        self._runtime_service = runtime_service
        self._state_store = state_store
        self._drive_controller = drive_controller
        self._gamepad_input = gamepad_input
        self._map_exporter = map_exporter
        self._map_activator = map_activator
        # 매핑<->순찰 전환. None 이면 전환을 시도하지 않는다 -- 기존 테스트가
        # 이 의존성을 모른 채로도 성립해야 한다.
        self._localization = localization
        self._slam_session = slam_session
        self._motion_authorization = motion_authorization
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
            # STARTING owns reset/readiness and STOPPING owns final shutdown;
            # neither state may authorise converted Nav2 motion.
            return self._state == "MAPPING"

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def localization(self) -> Any | None:
        """매핑/순찰 모드 전환기. 순찰 시작도 이걸 써서 인계를 다시 확인한다.

        이 클래스가 소유자인 이유는 매핑이 먼저 필요했기 때문이지 매핑
        전용이기 때문이 아니다. 순찰 시작 경로에도 내줘야 한다 --
        ``_enter_patrol_localization`` 이 실패했거나 그 부팅에 매핑이 없었으면
        아무도 포즈그래프를 적재하지 않은 채로 순찰이 출발한다.
        """

        return self._localization

    @property
    def slam_session(self) -> Any | None:
        """Internal SLAM scan boundary shared with patrol preparation."""

        return self._slam_session

    def lifecycle_snapshot(self) -> tuple[str, int | None]:
        """Return the current mapping state and session as one atomic snapshot."""

        with self._lock:
            return self._state, self._mapping_session_id

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def motion_timeline_diagnostic_context(self) -> dict[str, object]:
        """Aggregate read-only Mapping control context for Runtime fault logs."""

        with self._lock:
            context: dict[str, object] = {
                "mappingState": self._state,
                "mappingMotionActive": self._state
                in {"STARTING", "MAPPING", "STOPPING"},
            }
        context["mappingControlMode"] = (
            "GAMEPAD" if self._gamepad_input is not None else "AUTONOMOUS"
        )
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

    def _handover_pose(self) -> Any | None:
        """매핑이 끝난 **지금 그 자리**를 위치추정 시작점으로 넘긴다.

        넘기지 않으면 도킹 지점(0,0,0)이 쓰인다. 그런데 매핑을 마친 로봇은
        도킹 지점에 없다 -- 탐사하느라 움직였기 때문이다. 2026-08-09 09:22
        실측: 매핑 순변위 1.408 m 였는데 인계가 (0,0,0) 을 못 박았고, 순찰이
        엉뚱한 자리에서 출발해 ``Starting point in lethal space`` 로 계획이
        4회 연속 실패했다.

        slam 은 ``LOCALIZE_AT_POSE`` 를 받으면 첫 스캔의 자세를 그 값으로
        **강제**하고(``SetOdometricPose``) 그 **근처 노드에 대해서만**
        매칭한다(``ProcessAgainstNodesNearBy``). 전역 재위치추정은 없다.
        그러니 seed 가 틀리면 스캔매칭이 스스로 회복하지 못한다.

        좌표계가 맞는 이유: 지금 적재할 포즈그래프는 **방금 이 세션이 만든
        것**이고, 라이브 map->base_link 도 같은 지도의 좌표다. 재부팅 뒤
        예전 지도를 적재하는 경로(``ensure_patrol``)에서는 이 값이 무관한
        임시 지도의 좌표라서 쓰면 안 된다 -- 그쪽은 도킹 지점 그대로 둔다.

        읽지 못하면 None 을 돌려 기존 동작(도킹 지점)으로 떨어진다. 인계를
        실패시키지 않는다 -- 지도는 이미 저장·업로드됐다.
        """

        reader = getattr(self._slam_session, "current_map_pose", None)
        if not callable(reader):
            return None
        try:
            pose = reader()
        except Exception as exc:
            print(f"[MAPPING] handover pose read failed type={type(exc).__name__}")
            return None
        if pose is None:
            print("[MAPPING] handover pose unavailable; seeding at dock")
            return None
        x, y, yaw = pose
        print(f"[MAPPING] handover pose x={x:.3f} y={y:.3f} yaw={yaw:.3f}")
        from integration.localization_mode import DockPose

        return DockPose(x=x, y=y, theta=yaw)

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
        ready, reason = self._localization.enter_patrol(
            str(posegraph), self._handover_pose()
        )
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
        fresh_marker = None
        if self._slam_session is not None:
            try:
                # 정적(quiescence) 대기를 하지 않는다. slam 이 라이다를 직접
                # 구독하므로 스캔은 10Hz 로 계속 흐르고, 멎기를 기다리면 영원히
                # 안 온다. 그 대기는 게이트가 /slam_scan 을 끊던 시절의 것이다.
                #
                # 없어도 리셋은 깨끗하다. Mapper::Reset() 과 addScan 이 같은
                # smapper_mutex_ 를 쓰므로 직렬화된다(slam_toolbox_common.cpp:575,
                # laserCallback 이 아니라 addScan 이 락을 잡는다). 리셋 직전
                # 스캔은 리셋이 지우고, 직후 스캔은 새 지도의 첫 스캔이 된다.
                #
                # 마커는 리셋이 **반환한 뒤**에 잡는다. 앞에서 잡으면 리셋이
                # 진행되는 동안 도착한 (a) 마커 이후 스캔 한 장과 (b) 옛 그래프로
                # 만들어진 지도 한 장이 fresh_map_ready 의 세 가드를 전부
                # 통과한다. 리셋 자체는 이미 끝났으므로 지도가 겹치지는 않지만,
                # "새 지도가 실제로 생겼다"는 확인이 무의미해진다.
                self._slam_session.reset_slam()
                fresh_marker = self._slam_session.marker()
            except Exception as exc:
                print(
                    "[MAPPING] slam reset failed "
                    f"type={type(exc).__name__}"
                )
                self._rollback_start("SLAM_RESET_FAILED")
                return False, "SLAM_RESET_FAILED"

        # 새 세션은 깨끗한 지도에서 시작해야 한다. 위치추정 모드로 남아 있으면
        # 이전 지도의 포즈그래프 위에 그리게 되고, 매핑 모드로 돌리는 이 호출이
        # 위치추정 버퍼를 비운다. 예전에는 이걸 하려고 aiot-ros 를 재시작했다.
        if self._localization is not None:
            entered, mode_reason = self._localization.enter_mapping()
            if not entered:
                self._rollback_start(mode_reason)
                return False, mode_reason
        if self._slam_session is not None:
            assert fresh_marker is not None
            if not self._slam_session.wait_for_fresh_map(
                fresh_marker,
                timeout_sec=self._settings.fresh_map_timeout_sec,
            ):
                self._rollback_start("FRESH_MAP_NOT_READY")
                return False, "FRESH_MAP_NOT_READY"
            # Recheck the active Nav2 lifecycle after the post-reset map/TF is
            # ready. This second call is read-only when already in mapping.
            if self._localization is not None:
                entered, mode_reason = self._localization.enter_mapping()
                if not entered:
                    self._rollback_start(mode_reason)
                    return False, mode_reason
        if self._gamepad_input is not None:
            try:
                assert self._drive_controller is not None
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

        controller = (
            str(self._gamepad_input.device_path)
            if self._gamepad_input is not None
            else "autonomous-nav2"
        )
        print(
            "[MAPPING] started "
            f"mappingSessionId={mapping_session_id} controller={controller}"
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

        # STOPPING revokes the motion gate immediately. Silence the goal source
        # as well so Nav2 does not keep producing commands while the map saves.
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
        self._stop_mapping_motion("shutdown")
        worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2.0)
        with self._lock:
            self._reset_locked()

    def abort(self, reason: str) -> str | None:
        """Fail-close active Mapping motion and require a new START_MAPPING."""

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
                    if self._gamepad_input is not None:
                        assert self._drive_controller is not None
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
            if self._explore is not None:
                self._explore.start(mapping_session_id)
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
        self._stop_mapping_motion("rollback")
        with self._lock:
            self._reset_locked()
            self._last_error = reason

    def _stop_mapping_motion(self, operation: str) -> list[Exception]:
        failures: list[Exception] = []
        release = getattr(
            self._motion_authorization,
            "release_motion_authorization",
            None,
        )
        if callable(release):
            try:
                release(f"MAPPING_{operation.upper()}")
            except Exception as exc:
                failures.append(exc)
                print(
                    f"[MAPPING] motion authorization {operation} failed "
                    f"type={type(exc).__name__}"
                )
        if self._gamepad_input is not None:
            try:
                self._gamepad_input.stop()
            except Exception as exc:
                failures.append(exc)
                print(
                    f"[MAPPING] gamepad {operation} failed "
                    f"type={type(exc).__name__}"
                )
        if self._drive_controller is not None:
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
