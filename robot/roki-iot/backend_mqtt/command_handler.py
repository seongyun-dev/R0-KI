"""Validated and idempotent backend MQTT command state machine."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from backend_config.settings import AppSettings
from backend_mqtt.client import MqttClient
from pipeline.patrol_pipeline import PatrolPipelineRunner
from serial_reader import ESP32SerialReader
from backend_state.robot_state_store import RobotStateStore


SEOUL = ZoneInfo("Asia/Seoul")
SUPPORTED_COMMANDS = frozenset(
    {
        "START_PATROL",
        "STOP_PATROL",
        "SET_TOKEN",
        "START_MAPPING",
        "STOP_MAPPING",
    }
)
ACK_STATUSES = frozenset({"SUCCEEDED", "REJECTED", "FAILED"})


@dataclass(frozen=True)
class ValidatedCommand:
    command: str
    command_id: str
    patrol_id: int | None
    mapping_session_id: int | None
    fingerprint: str
    expires_at: datetime


ReadinessCheck = Callable[[], tuple[bool, str] | bool]
TelemetryFlush = Callable[[], None]


class PatrolCommandHandler:
    """Own command validation, lifecycle ordering and replay-safe ACKs."""

    CACHE_SCHEMA_VERSION = 1
    MAX_CACHE_ENTRIES = 256
    MAX_FUTURE_CLOCK_SKEW = timedelta(seconds=30)
    MAX_PATROL_COMMAND_TTL = timedelta(seconds=30)
    MAX_TOKEN_COMMAND_TTL = timedelta(hours=25)

    def __init__(
        self,
        *,
        settings: AppSettings,
        mqtt_client: MqttClient,
        serial_reader: ESP32SerialReader,
        state_store: RobotStateStore,
        pipeline_runner: PatrolPipelineRunner,
        pipeline_enabled: bool = False,
        ai_controller: Any | None = None,
        mapping_runtime: Any | None = None,
        readiness_checks: Iterable[ReadinessCheck] = (),
        localization_preparer: Callable[[], tuple[bool, str]] | None = None,
        flush_telemetry: TelemetryFlush | None = None,
        command_cache_path: str | Path | None = None,
        wall_clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._mqtt_client = mqtt_client
        self._serial_reader = serial_reader
        self._state_store = state_store
        self._pipeline_runner = pipeline_runner
        self._pipeline_enabled = pipeline_enabled
        self._ai_controller = ai_controller
        self._mapping_runtime = mapping_runtime
        self._mapping_lifecycle_lock = threading.RLock()
        self._readiness_checks = tuple(readiness_checks)
        self._localization_preparer = localization_preparer
        self._flush_telemetry = flush_telemetry
        self._wall_clock = wall_clock or (lambda: datetime.now(tz=SEOUL))
        self._monotonic_clock = monotonic_clock
        self._clear_since: float | None = None
        self._cache_path = Path(
            command_cache_path
            if command_cache_path is not None
            else settings.command_cache_file
        )
        self._cache_persistence_enabled = (
            command_cache_path is not None or os.name == "posix"
        )
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._load_cache()

    def set_flush_telemetry(self, flush: TelemetryFlush) -> None:
        self._flush_telemetry = flush

    def handle(self, topic: str, payload: dict[str, Any]) -> None:
        """Validate one backend command and always fail closed."""

        if topic != self._settings.command_topic:
            return
        command_text = payload.get("command")
        command_id = payload.get("commandId")
        fingerprint = self._fingerprint(payload)

        if isinstance(command_id, str) and command_id in self._cache:
            cached = self._cache[command_id]
            if cached.get("fingerprint") == fingerprint:
                self._mqtt_client.publish(
                    topic=self._settings.command_response_topic,
                    payload=dict(cached["ack"]),
                )
                return
            if isinstance(command_text, str) and command_text:
                self._publish_uncached_ack(
                    command=command_text,
                    command_id=command_id,
                    status="REJECTED",
                    reason="DUPLICATE_PAYLOAD_MISMATCH",
                )
            return

        try:
            command = self._validate(payload, fingerprint=fingerprint)
        except ValueError as exc:
            if (
                isinstance(command_text, str)
                and command_text
                and isinstance(command_id, str)
                and command_id
            ):
                self._record_and_publish(
                    command=command_text,
                    command_id=command_id,
                    status="REJECTED",
                    fingerprint=fingerprint,
                    reason=str(exc),
                )
            print(f"[COMMAND] rejected reason={exc}")
            return

        if command.command == "START_PATROL":
            self._handle_start_patrol(command)
        elif command.command == "STOP_PATROL":
            self._handle_stop_patrol(command)
        elif command.command == "SET_TOKEN":
            self._handle_set_token(command, str(payload["token"]))
        elif command.command == "START_MAPPING":
            self._handle_start_mapping(command)
        else:
            self._handle_stop_mapping(command)

    def tick(self) -> None:
        """Advance map pose and enforce the LiDAR stop/resume interlock."""

        active_patrol = getattr(self._serial_reader, "active_patrol_id", None)
        if active_patrol is None:
            self._clear_since = None
            return
        status = self._state_store.get_status()
        obstacle_stop = status.obstacle.status == "STOP"
        lidar_stale = (
            getattr(self._settings, "lidar_required_for_patrol", False)
            and status.lidar != "NORMAL"
        )
        ai_unready = False
        ai_required = getattr(
            self._settings,
            "ai_required_for_patrol",
            False,
        )
        if ai_required and self._ai_controller is None:
            ai_unready = True
        elif ai_required:
            readiness = getattr(self._ai_controller, "readiness", None)
            if callable(readiness):
                decision = readiness()
                ai_unready = not (
                    decision[0] if isinstance(decision, tuple) else decision
                )
            else:
                ai_unready = True
            applied = getattr(self._ai_controller, "detection_applied", None)
            if (
                not ai_unready
                and not obstacle_stop
                and not lidar_stale
                and callable(applied)
                and not applied(active_patrol)
            ):
                try:
                    # A stale AI gate sends DISABLE. Confirm the matching
                    # patrol ENABLE again before the clear-hold may resume.
                    self._enable_ai(active_patrol)
                    ai_unready = not applied(active_patrol)
                except Exception as exc:
                    ai_unready = True
                    print(
                        "[AI] recovery enable failed "
                        f"type={type(exc).__name__}"
                    )
        if obstacle_stop or lidar_stale or ai_unready:
            reason = (
                "OBSTACLE"
                if obstacle_stop
                else "LIDAR_STALE"
                if lidar_stale
                else "AI_NOT_READY"
            )
            pause = getattr(self._serial_reader, "pause_patrol", None)
            if callable(pause):
                pause(reason)
            self._clear_since = None
            return
        if not getattr(self._serial_reader, "paused", False):
            self._clear_since = None
            tick = getattr(self._serial_reader, "tick", None)
            if callable(tick):
                tick()
            return
        now = self._monotonic_clock()
        if self._clear_since is None:
            self._clear_since = now
            return
        if now - self._clear_since < self._settings.obstacle_clear_hold_seconds:
            return
        if ai_required and self._ai_controller is not None:
            readiness = getattr(self._ai_controller, "readiness", None)
            applied = getattr(self._ai_controller, "detection_applied", None)
            decision = readiness() if callable(readiness) else False
            ready = decision[0] if isinstance(decision, tuple) else decision
            if (
                not ready
                or not callable(applied)
                or not applied(active_patrol)
            ):
                # Status can change during the hold interval. Re-enter the
                # paused recovery path instead of resuming drive alone.
                self._clear_since = None
                return
        resume = getattr(self._serial_reader, "resume_patrol", None)
        if callable(resume):
            resume()
        self._clear_since = None

    def shutdown(self) -> None:
        """Safe shutdown order: physical STOP, AI disable, final telemetry."""

        stop_failed = False
        with self._mapping_lifecycle_lock:
            if self._mapping_runtime is not None:
                try:
                    self._mapping_runtime.stop()
                except Exception as exc:
                    stop_failed = True
                    print(f"[SHUTDOWN] mapping STOP failed: {type(exc).__name__}")
        try:
            self._serial_reader.send_command("STOP_PATROL")
        except Exception as exc:
            stop_failed = True
            print(f"[SHUTDOWN] physical STOP failed: {type(exc).__name__}")
        ai_failed = False
        try:
            self._disable_ai("ROBOT_RUNTIME_STOPPING")
        except Exception as exc:
            ai_failed = True
            print(f"[SHUTDOWN] AI disable failed: {type(exc).__name__}")
        self._state_store.update_robot_state(
            "ERROR" if stop_failed or ai_failed else "IDLE"
        )
        self._flush()

    def on_destination_reached(self, _event: Any = None) -> None:
        """Disable detections as soon as local navigation has physically stopped."""

        try:
            self._disable_ai("DESTINATION_REACHED")
        except Exception as exc:
            self._state_store.update_robot_state("ERROR")
            print(f"[AI] destination disable failed type={type(exc).__name__}")
        self._flush()

    def on_runtime_failure(self, reason: str) -> None:
        """Close AI and telemetry state after an asynchronous robot failure."""

        self._clear_since = None
        with self._mapping_lifecycle_lock:
            mapping_command_id = None
            if self._mapping_runtime is not None and bool(
                getattr(self._mapping_runtime, "active", False)
            ):
                try:
                    mapping_command_id = self._mapping_runtime.abort(reason)
                except Exception as exc:
                    print(
                        "[MAPPING] runtime fault abort failed "
                        f"type={type(exc).__name__}"
                    )
            if mapping_command_id:
                cached = self._cache.get(mapping_command_id)
                try:
                    if cached is None:
                        self._publish_uncached_ack(
                            command="START_MAPPING",
                            command_id=mapping_command_id,
                            status="FAILED",
                        )
                    else:
                        self._record_and_publish(
                            command="START_MAPPING",
                            command_id=mapping_command_id,
                            status="FAILED",
                            fingerprint=str(cached["fingerprint"]),
                        )
                except Exception as exc:
                    print(
                        "[MAPPING] runtime fault ACK failed "
                        f"type={type(exc).__name__}"
                    )
        try:
            self._disable_ai(reason)
        except Exception as exc:
            print(
                "[AI] runtime failure disable failed "
                f"type={type(exc).__name__}"
            )
        self._state_store.update_robot_state("ERROR")
        self._flush()

    def _handle_start_patrol(self, command: ValidatedCommand) -> None:
        assert command.patrol_id is not None
        if self._mapping_runtime is not None and self._mapping_runtime.active:
            self._record_and_publish_command(
                command, "REJECTED", reason="MAPPING_ACTIVE"
            )
            print("[COMMAND] START_PATROL rejected reason=MAPPING_ACTIVE")
            return
        status = self._state_store.get_status()
        # ERROR is recoverable only through a new, fully validated backend
        # START after runtime/AI/LiDAR readiness has become healthy again.
        # No local telemetry transition can auto-resume the previous patrol.
        if status.state not in {"IDLE", "ERROR"}:
            self._record_and_publish_command(
                command, "REJECTED", reason="ROBOT_NOT_IDLE"
            )
            return

        prepare = getattr(self._serial_reader, "prepare_patrol", None)
        if callable(prepare):
            decision = prepare(expires_at=command.expires_at)
            ready, reason = (
                decision
                if isinstance(decision, tuple)
                else (bool(decision), "OTA_ACTIVATION_IN_PROGRESS")
            )
            if not ready:
                self._cancel_prepared_patrol()
                self._record_and_publish_command(
                    command, "REJECTED", reason=reason
                )
                print(f"[COMMAND] START_PATROL interlock rejected reason={reason}")
                return

        # 인계 전이므로 인계 결과물은 묻지 않는다.
        #
        # 이 게이트가 지도 좌표 pose 와 Nav2 준비를 요구하고 있었는데, 그것은
        # 아래 localization_preparer 가 만들어주는 것이다. 재시작 뒤 매핑을
        # 한 번도 안 한 부팅에서는 스캔 게이트가 닫혀 있어 pose 가 없고,
        # 그래서 여기서 MAP_POSE_NOT_READY 로 잘려 인계에 도달하지 못했다 --
        # 순찰이 영원히 시작되지 않는다(2026-08-09 00:35:35 실측). 시리얼과
        # 오도메트리처럼 지금 판정 가능한 것은 그대로 여기서 막는다.
        ready, reason = self._preflight_readiness()
        if not ready:
            self._cancel_prepared_patrol()
            self._record_and_publish_command(
                command, "REJECTED", reason=reason
            )
            print(f"[COMMAND] START_PATROL readiness rejected reason={reason}")
            return

        # 위치추정 인계를 여기서 다시 확인한다. 매핑 완료 시점의 인계는
        # 실패할 수 있고(그때는 지도를 이미 저장했으므로 세션을 실패로 만들지
        # 않는다), 재부팅한 뒤에는 아예 일어나지 않는다 -- 그 부팅에 매핑이
        # 없었으니 부르는 쪽이 없다. mapping_runtime 의 "순찰을 시작할 때 다시
        # 시도한다" 는 주석이 가리키던 경로가 없어서, 지금까지는 아무도
        # 포즈그래프를 적재하지 않은 채 순찰이 출발할 수 있었다.
        #
        # 순서상 readiness 다음이다. 적재에 수 초가 걸릴 수 있고, 그 시간은
        # 바로 아래 TTL 재확인이 걸러낸다.
        if self._localization_preparer is not None:
            ready, reason = self._localization_preparer()
            if not ready:
                self._cancel_prepared_patrol()
                self._record_and_publish_command(
                    command, "REJECTED", reason=reason
                )
                print(f"[COMMAND] START_PATROL localization rejected reason={reason}")
                return

        # Localization preparation opens the scan gate. Re-run the existing
        # readiness contract after that transition, before AI or motion.
        ready, reason = self._readiness()
        if not ready:
            self._cancel_prepared_patrol()
            self._record_and_publish_command(command, "REJECTED", reason=reason)
            print(f"[COMMAND] START_PATROL final readiness rejected reason={reason}")
            return

        # Route fetch, map validation and the OTA lease can consume most of a
        # short MQTT command TTL. Recheck at the last safe point before AI or
        # any physical START is allowed.
        if self._start_command_expired(command):
            self._reject_expired_start(command, ai_enabled=False)
            return

        try:
            self._enable_ai(command.patrol_id)
            # AI enable can itself block while a ROS service transitions. The
            # physical START must get its own immediate expiry check too.
            if self._start_command_expired(command):
                self._reject_expired_start(command, ai_enabled=True)
                return
            self._serial_reader.send_command(
                "START_PATROL",
                patrolId=command.patrol_id,
                expires_at=command.expires_at,
            )
            confirm_started = getattr(
                self._serial_reader,
                "confirm_patrol_started",
                None,
            )
            if callable(confirm_started):
                if not confirm_started(command.patrol_id):
                    raise RuntimeError(
                        "patrol was invalidated before START confirmation"
                    )
            else:
                if (
                    getattr(self._serial_reader, "active_patrol_id", None)
                    != command.patrol_id
                ):
                    raise RuntimeError(
                        "patrol was invalidated before START confirmation"
                    )
                self._state_store.update_robot_state("PATROLLING")
        except Exception as exc:
            reason = str(
                getattr(exc, "reason", type(exc).__name__)
            )
            if reason == "COMMAND_EXPIRED_DURING_START":
                self._reject_expired_start(
                    command,
                    ai_enabled=True,
                    reason=reason,
                )
                return
            self._cancel_prepared_patrol()
            self._disable_ai("START_PATROL_ROLLBACK")
            try:
                self._serial_reader.send_command("STOP_PATROL")
            except Exception:
                pass
            self._state_store.update_robot_state("ERROR")
            self._record_and_publish_command(
                command, "FAILED", reason=reason
            )
            print(f"[COMMAND] START_PATROL failed type={type(exc).__name__}")
            return

        self._record_and_publish_command(command, "SUCCEEDED")
        self._flush()
        print(
            "[COMMAND] START_PATROL succeeded "
            f"commandId={command.command_id} patrolId={command.patrol_id}"
        )

    def _handle_stop_patrol(self, command: ValidatedCommand) -> None:
        errors: list[str] = []
        try:
            self._serial_reader.send_command("STOP_PATROL")
        except Exception as exc:
            errors.append(str(exc) or type(exc).__name__)
        try:
            self._disable_ai("STOP_PATROL")
        except Exception as exc:
            errors.append(str(exc) or type(exc).__name__)

        self._state_store.update_robot_state("IDLE" if not errors else "ERROR")
        self._flush()
        self._record_and_publish_command(
            command,
            "SUCCEEDED" if not errors else "FAILED",
            reason=";".join(errors) if errors else None,
        )
        print(
            "[COMMAND] STOP_PATROL completed "
            f"commandId={command.command_id} errors={len(errors)}"
        )

    def _handle_start_mapping(self, command: ValidatedCommand) -> None:
        with self._mapping_lifecycle_lock:
            self._handle_start_mapping_locked(command)

    def _handle_start_mapping_locked(self, command: ValidatedCommand) -> None:
        assert command.mapping_session_id is not None
        if self._mapping_runtime is None:
            self._record_and_publish_command(
                command,
                "REJECTED",
                reason="MAPPING_RUNTIME_MISSING",
            )
            print("[COMMAND] START_MAPPING rejected reason=MAPPING_RUNTIME_MISSING")
            return
        status = self._state_store.get_status()
        # A previous mapping/runtime failure leaves ERROR latched. A fresh
        # command may recover only through ManualMappingRuntime.start(), which
        # reruns runtime, LiDAR, map-export and backend-token readiness before
        # activating the gamepad. The failed commandId itself remains cached as
        # FAILED and cannot resume motion.
        if status.state not in {"IDLE", "ERROR"} or getattr(
            self._serial_reader, "active_patrol_id", None
        ) is not None:
            self._record_and_publish_command(
                command,
                "REJECTED",
                reason="ROBOT_NOT_IDLE",
            )
            print("[COMMAND] START_MAPPING rejected reason=ROBOT_NOT_IDLE")
            return
        try:
            ready, reason = self._mapping_runtime.start(
                command.mapping_session_id,
                command.command_id,
            )
        except Exception as exc:
            self._record_and_publish_command(
                command,
                "FAILED",
                reason=type(exc).__name__,
            )
            print(f"[COMMAND] START_MAPPING failed type={type(exc).__name__}")
            return
        if not ready:
            lifecycle_failure = reason in {
                "RUNTIME_LIFECYCLE_CHANGED",
                "MAPPING_START_INTERRUPTED",
            }
            if lifecycle_failure:
                self._state_store.update_robot_state("ERROR")
            self._record_and_publish_command(
                command,
                "FAILED" if lifecycle_failure else "REJECTED",
                reason=reason,
            )
            print(f"[COMMAND] START_MAPPING rejected reason={reason}")
            return
        self._state_store.update_robot_state("IDLE")
        self._record_and_publish_command(command, "SUCCEEDED")
        print(
            "[COMMAND] START_MAPPING succeeded "
            f"commandId={command.command_id} "
            f"mappingSessionId={command.mapping_session_id}"
        )

    def _handle_stop_mapping(self, command: ValidatedCommand) -> None:
        with self._mapping_lifecycle_lock:
            self._handle_stop_mapping_locked(command)

    def _handle_stop_mapping_locked(self, command: ValidatedCommand) -> None:
        """Accept one session-bound finish request without duplicating work."""

        assert command.mapping_session_id is not None
        if self._mapping_runtime is None:
            self._record_and_publish_command(
                command,
                "REJECTED",
                reason="MAPPING_RUNTIME_MISSING",
            )
            print("[COMMAND] STOP_MAPPING rejected reason=MAPPING_RUNTIME_MISSING")
            return

        state, active_session_id = self._mapping_runtime.lifecycle_snapshot()
        if state == "IDLE":
            self._record_and_publish_command(
                command,
                "REJECTED",
                reason="MAPPING_NOT_ACTIVE",
            )
            print("[COMMAND] STOP_MAPPING rejected reason=MAPPING_NOT_ACTIVE")
            return
        if active_session_id != command.mapping_session_id:
            self._record_and_publish_command(
                command,
                "REJECTED",
                reason="MAPPING_SESSION_MISMATCH",
            )
            print(
                "[COMMAND] STOP_MAPPING rejected "
                "reason=MAPPING_SESSION_MISMATCH"
            )
            return

        if state in {"STOPPING", "SAVING", "UPLOADING"}:
            self._record_and_publish_command(command, "SUCCEEDED")
            print(
                "[COMMAND] STOP_MAPPING already accepted "
                f"mappingSessionId={command.mapping_session_id} state={state}"
            )
            return
        if state != "MAPPING":
            self._record_and_publish_command(
                command,
                "REJECTED",
                reason="MAPPING_NOT_STOPPABLE",
            )
            print(
                "[COMMAND] STOP_MAPPING rejected "
                f"reason=MAPPING_NOT_STOPPABLE state={state}"
            )
            return

        try:
            accepted = self._mapping_runtime.finish(command.mapping_session_id)
        except Exception as exc:
            self._record_and_publish_command(
                command,
                "FAILED",
                reason=type(exc).__name__,
            )
            print(f"[COMMAND] STOP_MAPPING failed type={type(exc).__name__}")
            return
        if not accepted:
            # A concurrent gamepad finish may have won after the snapshot. It
            # is still the same accepted stop operation, not a second export.
            current_state, current_session_id = (
                self._mapping_runtime.lifecycle_snapshot()
            )
            if (
                current_session_id == command.mapping_session_id
                and current_state in {"STOPPING", "SAVING", "UPLOADING"}
            ):
                self._record_and_publish_command(command, "SUCCEEDED")
                return
            self._record_and_publish_command(
                command,
                "FAILED",
                reason="MAPPING_FINISH_FAILED",
            )
            print("[COMMAND] STOP_MAPPING failed reason=MAPPING_FINISH_FAILED")
            return

        self._record_and_publish_command(command, "SUCCEEDED")
        print(
            "[COMMAND] STOP_MAPPING accepted "
            f"commandId={command.command_id} "
            f"mappingSessionId={command.mapping_session_id}"
        )

    def _handle_set_token(self, command: ValidatedCommand, token: str) -> None:
        try:
            self._write_secret(token)
            os.environ["AIOT_BACKEND_ACCESS_TOKEN"] = token
        except Exception as exc:
            self._record_and_publish_command(command, "FAILED")
            print(f"[COMMAND] SET_TOKEN failed type={type(exc).__name__}")
            return
        self._record_and_publish_command(command, "SUCCEEDED")
        print("[COMMAND] SET_TOKEN stored in protected runtime file")

    def _preflight_readiness(self) -> tuple[bool, str]:
        """위치추정 인계 전 게이트. 런타임이 얕은 판정을 제공하면 그것을 쓴다.

        제공하지 않으면 기존 계약 그대로 ``readiness`` 로 떨어진다 -- 이 훅이
        없는 런타임 구현(테스트 더블 포함)에서 동작이 달라지지 않아야 한다.
        """

        return self._readiness(preflight=True)

    def _readiness(self, *, preflight: bool = False) -> tuple[bool, str]:
        runtime_check = getattr(self._serial_reader, "readiness", None)
        if preflight:
            shallow = getattr(
                self._serial_reader, "patrol_preflight_readiness", None
            )
            if callable(shallow):
                runtime_check = shallow
        checks: list[ReadinessCheck] = []
        if callable(runtime_check):
            checks.append(runtime_check)
        checks.extend(self._readiness_checks)
        for check in checks:
            result = check()
            if isinstance(result, tuple):
                if not result[0]:
                    return False, str(result[1])
            elif not result:
                return False, "READINESS_CHECK_FAILED"

        status = self._state_store.get_status()
        if (
            getattr(self._settings, "lidar_required_for_patrol", False)
            and status.lidar != "NORMAL"
        ):
            return False, "LIDAR_NOT_READY"
        if getattr(self._settings, "ai_required_for_patrol", False):
            if self._ai_controller is None:
                return False, "AI_CONTROLLER_MISSING"
            readiness = getattr(self._ai_controller, "readiness", None)
            if not callable(readiness):
                return False, "AI_READINESS_UNAVAILABLE"
            result = readiness()
            if isinstance(result, tuple):
                if not result[0]:
                    return False, str(result[1])
            elif not result:
                return False, "AI_NOT_READY"
        return True, "READY"

    def _enable_ai(self, patrol_id: int) -> None:
        if self._ai_controller is not None:
            self._ai_controller.enable(patrol_id)
            return
        if self._pipeline_enabled:
            self._pipeline_runner.start()

    def _disable_ai(self, reason: str) -> None:
        if self._ai_controller is not None:
            self._ai_controller.disable(reason)
            return
        if self._pipeline_enabled:
            self._pipeline_runner.stop()

    def _flush(self) -> None:
        if self._flush_telemetry is None:
            return
        try:
            self._flush_telemetry()
        except Exception as exc:
            print(f"[TELEMETRY] final flush failed type={type(exc).__name__}")

    def _validate(
        self, payload: dict[str, Any], *, fingerprint: str
    ) -> ValidatedCommand:
        if payload.get("schemaVersion") != self._settings.schema_version:
            raise ValueError("unsupported schemaVersion")
        command = payload.get("command")
        command_id = payload.get("commandId")
        if not isinstance(command, str) or command not in SUPPORTED_COMMANDS:
            raise ValueError("unsupported command")
        if not isinstance(command_id, str) or not command_id.strip():
            raise ValueError("commandId is required")
        if len(command_id) > 128:
            raise ValueError("commandId is too long")

        issued = self._required_timestamp(payload, "issuedAt")
        expires = self._required_timestamp(payload, "expiresAt")
        now = self._wall_clock()
        if now.tzinfo is None:
            raise RuntimeError("wall clock must be timezone-aware")
        if expires <= issued:
            raise ValueError("expiresAt must be after issuedAt")
        maximum_ttl = (
            self.MAX_TOKEN_COMMAND_TTL
            if command == "SET_TOKEN"
            else self.MAX_PATROL_COMMAND_TTL
        )
        if expires - issued > maximum_ttl:
            raise ValueError("command TTL is too long")
        if now > expires:
            raise ValueError("command expired")
        if issued - now > self.MAX_FUTURE_CLOCK_SKEW:
            raise ValueError("issuedAt is too far in the future")

        patrol_id = payload.get("patrolId")
        if command == "START_PATROL":
            if (
                isinstance(patrol_id, bool)
                or not isinstance(patrol_id, int)
                or patrol_id <= 0
            ):
                raise ValueError("patrolId must be a positive integer")
        else:
            patrol_id = None
        mapping_session_id = payload.get("mappingSessionId")
        if command in {"START_MAPPING", "STOP_MAPPING"}:
            if (
                isinstance(mapping_session_id, bool)
                or not isinstance(mapping_session_id, int)
                or mapping_session_id <= 0
            ):
                raise ValueError("mappingSessionId must be a positive integer")
        else:
            mapping_session_id = None
        if command == "SET_TOKEN":
            token = payload.get("token")
            if not isinstance(token, str) or not token:
                raise ValueError("token is required")
        return ValidatedCommand(
            command=command,
            command_id=command_id,
            patrol_id=patrol_id,
            mapping_session_id=mapping_session_id,
            fingerprint=fingerprint,
            expires_at=expires,
        )

    def _cancel_prepared_patrol(self) -> None:
        cancel_prepared = getattr(
            self._serial_reader, "cancel_prepared_patrol", None
        )
        if callable(cancel_prepared):
            cancel_prepared()

    def _start_command_expired(self, command: ValidatedCommand) -> bool:
        return self._wall_clock() >= command.expires_at

    def _reject_expired_start(
        self,
        command: ValidatedCommand,
        *,
        ai_enabled: bool,
        reason: str = "COMMAND_EXPIRED_DURING_PREPARE",
    ) -> None:
        try:
            self._cancel_prepared_patrol()
        except Exception as exc:
            print(
                "[COMMAND] expired START route cleanup failed "
                f"type={type(exc).__name__}"
            )
        if ai_enabled:
            try:
                self._disable_ai("COMMAND_EXPIRED_DURING_START")
            except Exception as exc:
                print(
                    "[AI] expired START rollback failed "
                    f"type={type(exc).__name__}"
                )
        self._record_and_publish_command(
            command,
            "REJECTED",
            reason=reason,
        )
        print(
            "[COMMAND] START_PATROL rejected "
            f"reason={reason}"
        )

    @staticmethod
    def _required_timestamp(payload: dict[str, Any], field: str) -> datetime:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
        normalized = value.strip().replace("Z", "+00:00")
        if "." in normalized:
            head, rest = normalized.split(".", 1)
            digits = ""
            timezone_part = ""
            for index, character in enumerate(rest):
                if character.isdigit():
                    digits += character
                else:
                    timezone_part = rest[index:]
                    break
            normalized = f"{head}.{digits[:6].ljust(6, '0')}{timezone_part}"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"{field} must be ISO-8601") from exc
        if parsed.tzinfo is None:
            raise ValueError(f"{field} must include timezone")
        return parsed

    def _record_and_publish_command(
        self,
        command: ValidatedCommand,
        status: str,
        *,
        reason: str | None = None,
    ) -> None:
        self._record_and_publish(
            command=command.command,
            command_id=command.command_id,
            status=status,
            fingerprint=command.fingerprint,
            reason=reason,
        )

    def _record_and_publish(
        self,
        *,
        command: str,
        command_id: str,
        status: str,
        fingerprint: str,
        reason: str | None = None,
    ) -> None:
        if status != "SUCCEEDED" and not reason:
            reason = "UNSPECIFIED_FAILURE"
        ack = self._ack(command, command_id, status, reason=reason)
        self._cache[command_id] = {"fingerprint": fingerprint, "ack": ack}
        self._cache.move_to_end(command_id)
        while len(self._cache) > self.MAX_CACHE_ENTRIES:
            self._cache.popitem(last=False)
        self._persist_cache()
        self._mqtt_client.publish(
            topic=self._settings.command_response_topic,
            payload=ack,
        )

    def _publish_uncached_ack(
        self,
        *,
        command: str,
        command_id: str,
        status: str,
        reason: str | None = None,
    ) -> None:
        self._mqtt_client.publish(
            topic=self._settings.command_response_topic,
            payload=self._ack(command, command_id, status, reason=reason),
        )

    def _ack(
        self,
        command: str,
        command_id: str,
        status: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if status not in ACK_STATUSES:
            raise ValueError("invalid ACK status")
        ack = {
            "schemaVersion": self._settings.schema_version,
            "commandId": command_id,
            "command": command,
            "status": status,
            "receivedAt": self._wall_clock().isoformat(timespec="seconds"),
        }
        if reason:
            ack["reason"] = str(reason)[:128]
        return ack

    @staticmethod
    def _fingerprint(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _write_secret(self, token: str) -> None:
        path = Path(self._settings.service_token_file)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(token)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            temporary.unlink(missing_ok=True)

    def _load_cache(self) -> None:
        if not self._cache_persistence_enabled:
            return
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if raw.get("schemaVersion") != self.CACHE_SCHEMA_VERSION:
                return
            for item in raw.get("entries", [])[-self.MAX_CACHE_ENTRIES :]:
                command_id = item.get("commandId")
                fingerprint = item.get("fingerprint")
                ack = item.get("ack")
                if (
                    isinstance(command_id, str)
                    and isinstance(fingerprint, str)
                    and isinstance(ack, dict)
                ):
                    self._cache[command_id] = {
                        "fingerprint": fingerprint,
                        "ack": ack,
                    }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return

    def _persist_cache(self) -> None:
        if not self._cache_persistence_enabled:
            return
        payload = {
            "schemaVersion": self.CACHE_SCHEMA_VERSION,
            "entries": [
                {
                    "commandId": command_id,
                    "fingerprint": item["fingerprint"],
                    "ack": item["ack"],
                }
                for command_id, item in self._cache.items()
            ],
        }
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self._cache_path.name}.", dir=self._cache_path.parent
            )
            temporary = Path(temporary_name)
            try:
                if hasattr(os, "fchmod"):
                    os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, separators=(",", ":"))
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self._cache_path)
                os.chmod(self._cache_path, 0o600)
            finally:
                temporary.unlink(missing_ok=True)
        except OSError as exc:
            print(f"[COMMAND] command cache unavailable type={type(exc).__name__}")
