from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from backend_mqtt.command_handler import PatrolCommandHandler


NOW = datetime(2026, 8, 3, 0, 0, tzinfo=timezone.utc)


class FakePatrolStartExpired(RuntimeError):
    reason = "COMMAND_EXPIRED_DURING_START"

    def __init__(self) -> None:
        super().__init__(self.reason)


class FakeMqtt:
    def __init__(self, order: list[str] | None = None) -> None:
        self.messages: list[tuple[str, dict]] = []
        self.order = order

    def publish(self, *, topic: str, payload: dict) -> None:
        self.messages.append((topic, payload))
        if self.order is not None:
            self.order.append("mqtt")


class FakeStore:
    def __init__(self, order: list[str] | None = None) -> None:
        self.state = "IDLE"
        self.lidar = "NORMAL"
        self.obstacle = "CLEAR"
        self.order = order

    def get_status(self):
        return SimpleNamespace(
            state=self.state,
            lidar=self.lidar,
            obstacle=SimpleNamespace(status=self.obstacle),
        )

    def update_robot_state(self, state: str) -> None:
        self.state = state
        if self.order is not None:
            self.order.append(f"state-{state}")


class FakeRuntimeService:
    def __init__(self, order: list[str] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.active_patrol_id: int | None = None
        self.paused = False
        self.order = order
        self.prepare_decision = (True, "READY")
        self.ready_decision = (True, "READY")
        self.cancel_count = 0
        self.start_error: Exception | None = None
        self.invalidate_after_start = False
        self.stop_error: Exception | None = None
        self.prepare_callback = None
        self.prepared_expires_at = None
        self.start_dispatch_callback = None
        self.wall_clock = None
        self.actual_start_count = 0

    def readiness(self):
        return self.ready_decision

    def prepare_patrol(self, *, expires_at=None):
        self.prepared_expires_at = expires_at
        if self.prepare_callback is not None:
            self.prepare_callback()
        return self.prepare_decision

    def cancel_prepared_patrol(self) -> None:
        self.cancel_count += 1

    def send_command(self, command: str, **parameters) -> None:
        self.calls.append((command, parameters))
        if self.order is not None:
            self.order.append("serial-start" if command == "START_PATROL" else "serial-stop")
        if command == "START_PATROL":
            if self.start_dispatch_callback is not None:
                self.start_dispatch_callback()
            expires_at = parameters.get("expires_at")
            if (
                expires_at is not None
                and self.wall_clock is not None
                and self.wall_clock() >= expires_at
            ):
                raise FakePatrolStartExpired()
            if self.start_error is not None:
                raise self.start_error
            self.actual_start_count += 1
            self.active_patrol_id = parameters["patrolId"]
            if self.invalidate_after_start:
                self.active_patrol_id = None
        elif command == "STOP_PATROL":
            self.active_patrol_id = None
            self.paused = False
            if self.stop_error is not None:
                raise self.stop_error

    def pause_patrol(self, reason: str) -> None:
        del reason
        self.paused = True

    def resume_patrol(self) -> None:
        self.paused = False
        if self.order is not None:
            self.order.append("serial-resume")

    def tick(self) -> None:
        return None


class FakeAi:
    def __init__(self, order: list[str] | None = None) -> None:
        self.enabled: list[int] = []
        self.disabled: list[str] = []
        self.order = order
        self.ready = True
        self.applied_patrol_id: int | None = None
        self.enable_callback = None

    def readiness(self):
        return self.ready, "AI_READY" if self.ready else "AI_STATUS_STALE"

    def enable(self, patrol_id: int) -> None:
        self.enabled.append(patrol_id)
        self.applied_patrol_id = patrol_id
        if self.enable_callback is not None:
            self.enable_callback()
        if self.order is not None:
            self.order.append("ai-enable")

    def disable(self, reason: str) -> None:
        self.disabled.append(reason)
        self.applied_patrol_id = None
        if self.order is not None:
            self.order.append("ai-disable")

    def detection_applied(self, patrol_id: int) -> bool:
        return self.applied_patrol_id == patrol_id


def payload(
    command: str,
    command_id: str,
    *,
    patrol_id: int | None = None,
    mapping_session_id: int | None = None,
) -> dict:
    result = {
        "schemaVersion": 1,
        "command": command,
        "commandId": command_id,
        "issuedAt": NOW.isoformat(),
        "expiresAt": (NOW + timedelta(seconds=10)).isoformat(),
    }
    if patrol_id is not None:
        result["patrolId"] = patrol_id
    if mapping_session_id is not None:
        result["mappingSessionId"] = mapping_session_id
    return result


class FakeMappingRuntime:
    def __init__(self) -> None:
        self.active = False
        self.state = "IDLE"
        self.mapping_session_id: int | None = None
        self.starts: list[tuple[int, str]] = []
        self.finishes: list[int | None] = []
        self.stops = 0
        self.aborts: list[str] = []
        self.command_id: str | None = None
        self.start_decision = (True, "READY")

    @property
    def motion_active(self) -> bool:
        return self.active

    def start(self, mapping_session_id: int, command_id: str):
        self.starts.append((mapping_session_id, command_id))
        if self.start_decision[0]:
            self.active = True
            self.state = "MAPPING"
            self.mapping_session_id = mapping_session_id
            self.command_id = command_id
        return self.start_decision

    def lifecycle_snapshot(self):
        return self.state, self.mapping_session_id

    def finish(self, mapping_session_id: int | None = None) -> bool:
        self.finishes.append(mapping_session_id)
        if self.state != "MAPPING" or mapping_session_id != self.mapping_session_id:
            return False
        self.state = "SAVING"
        return True

    def stop(self) -> None:
        self.stops += 1
        self.active = False
        self.state = "IDLE"
        self.mapping_session_id = None
        self.command_id = None

    def abort(self, reason: str) -> str | None:
        if not self.active:
            return None
        self.aborts.append(reason)
        command_id = self.command_id
        self.active = False
        self.state = "IDLE"
        self.mapping_session_id = None
        self.command_id = None
        return command_id


class CommandStateMachineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.settings = SimpleNamespace(
            schema_version=1,
            command_topic="hanbakwi/v1/robots/ROKI-01/command",
            command_response_topic="hanbakwi/v1/robots/ROKI-01/command/ack",
            ai_required_for_patrol=True,
            lidar_required_for_patrol=True,
            obstacle_clear_hold_seconds=1.0,
            service_token_file=str(root / "secrets" / "token"),
            command_cache_file=str(root / "state" / "commands.json"),
        )
        self.mqtt = FakeMqtt()
        self.store = FakeStore()
        self.runtime = FakeRuntimeService()
        self.ai = FakeAi()
        self.mapping = FakeMappingRuntime()
        self.now_monotonic = 0.0
        self.now_wall = NOW
        self.handler = PatrolCommandHandler(
            settings=self.settings,
            mqtt_client=self.mqtt,
            serial_reader=self.runtime,
            state_store=self.store,
            pipeline_runner=SimpleNamespace(),
            ai_controller=self.ai,
            mapping_runtime=self.mapping,
            command_cache_path=self.settings.command_cache_file,
            wall_clock=lambda: self.now_wall,
            monotonic_clock=lambda: self.now_monotonic,
        )

    def _handler_with_localization(self, decisions: list) -> object:
        return PatrolCommandHandler(
            settings=self.settings,
            mqtt_client=self.mqtt,
            serial_reader=self.runtime,
            state_store=self.store,
            pipeline_runner=SimpleNamespace(),
            ai_controller=self.ai,
            mapping_runtime=self.mapping,
            command_cache_path=self.settings.command_cache_file,
            wall_clock=lambda: self.now_wall,
            monotonic_clock=lambda: self.now_monotonic,
            localization_preparer=lambda: decisions.pop(0),
        )

    def test_start_patrol_prepares_localization_before_the_physical_start(self) -> None:
        """재부팅 뒤 첫 순찰은 아무도 포즈그래프를 적재해주지 않는다.

        매핑 완료 시점의 인계는 그 부팅에 매핑이 없었으면 일어나지 않는다.
        여기서 다시 확인하지 않으면 순찰이 지도 없이 출발한다.
        """

        order: list[str] = []
        self.runtime.order = order
        handler = self._handler_with_localization(
            [(True, "READY")],
        )
        original = handler._localization_preparer

        def recording_preparer():
            order.append("localization")
            return original()

        handler._localization_preparer = recording_preparer

        handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "start-loc-1", patrol_id=11),
        )

        self.assertEqual(order, ["localization", "serial-start"])
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "SUCCEEDED")

    def test_start_patrol_is_rejected_when_localization_cannot_be_prepared(self) -> None:
        """적재 실패를 삼키면 지도 없는 순찰이 성공으로 보고된다."""

        handler = self._handler_with_localization([(False, "POSEGRAPH_MISSING")])

        handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "start-loc-2", patrol_id=12),
        )

        self.assertEqual(self.runtime.calls, [], "물리 START 는 나가면 안 된다")
        acknowledgement = self.mqtt.messages[-1][1]
        self.assertEqual(acknowledgement["status"], "REJECTED")
        self.assertEqual(acknowledgement["reason"], "POSEGRAPH_MISSING")
        self.assertEqual(self.runtime.cancel_count, 1)

    def test_valid_start_is_idempotent_across_handler_restart(self) -> None:
        command = payload("START_PATROL", "start-1", patrol_id=7)
        self.handler.handle(self.settings.command_topic, command)
        self.handler.handle(self.settings.command_topic, command)

        self.assertEqual(
            self.runtime.calls,
            [
                (
                    "START_PATROL",
                    {
                        "patrolId": 7,
                        "expires_at": NOW + timedelta(seconds=10),
                    },
                )
            ],
        )
        self.assertEqual(self.ai.enabled, [7])
        self.assertEqual([m[1]["status"] for m in self.mqtt.messages], ["SUCCEEDED", "SUCCEEDED"])

        restarted = PatrolCommandHandler(
            settings=self.settings,
            mqtt_client=self.mqtt,
            serial_reader=self.runtime,
            state_store=self.store,
            pipeline_runner=SimpleNamespace(),
            ai_controller=self.ai,
            command_cache_path=self.settings.command_cache_file,
            wall_clock=lambda: NOW,
        )
        restarted.handle(self.settings.command_topic, command)
        self.assertEqual(len(self.runtime.calls), 1)
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "SUCCEEDED")

    def test_lifecycle_invalidated_start_is_failed_not_acknowledged(self) -> None:
        self.runtime.start_error = RuntimeError(
            "runtime lifecycle changed during START_PATROL"
        )

        self.handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "start-raced", patrol_id=7),
        )

        self.assertEqual(self.store.state, "ERROR")
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "FAILED")
        self.assertIsNone(self.runtime.active_patrol_id)
        self.assertEqual(self.ai.disabled, ["START_PATROL_ROLLBACK"])

    def test_silent_invalidation_before_confirmation_is_failed(self) -> None:
        self.runtime.invalidate_after_start = True

        self.handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "start-invalidated", patrol_id=7),
        )

        self.assertEqual(self.store.state, "ERROR")
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "FAILED")
        self.assertIsNone(self.runtime.active_patrol_id)

    def test_explicit_start_can_recover_error_only_after_readiness(self) -> None:
        self.store.state = "ERROR"
        self.runtime.ready_decision = (False, "ODOMETRY_NOT_READY")
        self.handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "recover-not-ready", patrol_id=7),
        )
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")
        self.assertEqual(
            self.mqtt.messages[-1][1]["reason"], "ODOMETRY_NOT_READY"
        )
        self.assertEqual(self.runtime.cancel_count, 1)
        self.assertEqual(self.runtime.calls, [])

        self.runtime.ready_decision = (True, "READY")
        self.handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "recover-ready", patrol_id=7),
        )
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "SUCCEEDED")
        self.assertEqual(self.store.state, "PATROLLING")

    def test_runtime_failure_disables_ai_and_publishes_error_state(self) -> None:
        self.ai.enable(7)

        self.handler.on_runtime_failure("MOTOR_FAULT")

        self.assertEqual(self.ai.disabled, ["MOTOR_FAULT"])
        self.assertEqual(self.store.state, "ERROR")

    def test_expired_and_malformed_commands_fail_closed(self) -> None:
        expired = payload("START_PATROL", "expired", patrol_id=7)
        expired["expiresAt"] = (NOW - timedelta(seconds=1)).isoformat()
        malformed = payload("START_PATROL", "malformed", patrol_id=7)
        del malformed["schemaVersion"]
        overlong = payload("START_PATROL", "overlong", patrol_id=7)
        overlong["expiresAt"] = (NOW + timedelta(minutes=5)).isoformat()

        self.handler.handle(self.settings.command_topic, expired)
        self.handler.handle(self.settings.command_topic, malformed)
        self.handler.handle(self.settings.command_topic, overlong)

        self.assertEqual(self.runtime.calls, [])
        self.assertEqual(
            [m[1]["status"] for m in self.mqtt.messages],
            ["REJECTED", "REJECTED", "REJECTED"],
        )
        self.assertTrue(
            all(message[1].get("reason") for message in self.mqtt.messages)
        )

    def test_same_command_id_with_different_payload_is_rejected(self) -> None:
        first = payload("START_PATROL", "same", patrol_id=7)
        second = payload("START_PATROL", "same", patrol_id=8)
        self.handler.handle(self.settings.command_topic, first)
        self.handler.handle(self.settings.command_topic, second)
        self.assertEqual(len(self.runtime.calls), 1)
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")
        self.assertEqual(
            self.mqtt.messages[-1][1]["reason"],
            "DUPLICATE_PAYLOAD_MISMATCH",
        )

    def test_stop_orders_physical_ai_flush_then_ack(self) -> None:
        order: list[str] = []
        mqtt = FakeMqtt(order)
        store = FakeStore(order)
        runtime = FakeRuntimeService(order)
        runtime.active_patrol_id = 7
        store.state = "PATROLLING"
        ai = FakeAi(order)
        handler = PatrolCommandHandler(
            settings=self.settings,
            mqtt_client=mqtt,
            serial_reader=runtime,
            state_store=store,
            pipeline_runner=SimpleNamespace(),
            ai_controller=ai,
            command_cache_path=Path(self.temporary.name) / "order.json",
            flush_telemetry=lambda: order.append("flush"),
            wall_clock=lambda: NOW,
        )
        handler.handle(self.settings.command_topic, payload("STOP_PATROL", "stop-1"))
        self.assertEqual(
            order[:5],
            ["serial-stop", "ai-disable", "state-IDLE", "flush", "mqtt"],
        )

    def test_unconfirmed_physical_stop_publishes_failed_ack(self) -> None:
        self.runtime.active_patrol_id = 7
        self.runtime.stop_error = RuntimeError("ESP32 STOP was not delivered")
        self.store.state = "PATROLLING"

        self.handler.handle(
            self.settings.command_topic,
            payload("STOP_PATROL", "stop-write-failed"),
        )

        self.assertIsNone(self.runtime.active_patrol_id)
        self.assertEqual(self.store.state, "ERROR")
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "FAILED")
        self.assertEqual(
            self.mqtt.messages[-1][1]["reason"],
            "ESP32 STOP was not delivered",
        )
        self.assertEqual(self.ai.disabled, ["STOP_PATROL"])

    def test_obstacle_requires_stable_clear_before_resume(self) -> None:
        self.runtime.active_patrol_id = 7
        self.ai.applied_patrol_id = 7
        self.store.state = "PATROLLING"
        self.store.obstacle = "STOP"
        self.handler.tick()
        self.assertTrue(self.runtime.paused)
        self.store.obstacle = "CLEAR"
        self.handler.tick()
        self.now_monotonic = 0.9
        self.handler.tick()
        self.assertTrue(self.runtime.paused)
        self.now_monotonic = 1.0
        self.handler.tick()
        self.assertFalse(self.runtime.paused)

    def test_ai_stale_recovery_reenables_before_drive_resume(self) -> None:
        order: list[str] = []
        runtime = FakeRuntimeService(order)
        runtime.active_patrol_id = 7
        store = FakeStore(order)
        store.state = "PATROLLING"
        ai = FakeAi(order)
        ai.applied_patrol_id = 7
        handler = PatrolCommandHandler(
            settings=self.settings,
            mqtt_client=FakeMqtt(order),
            serial_reader=runtime,
            state_store=store,
            pipeline_runner=SimpleNamespace(),
            ai_controller=ai,
            command_cache_path=Path(self.temporary.name) / "ai-recovery.json",
            wall_clock=lambda: NOW,
            monotonic_clock=lambda: self.now_monotonic,
        )

        ai.ready = False
        ai.applied_patrol_id = None
        handler.tick()
        self.assertTrue(runtime.paused)

        ai.ready = True
        handler.tick()
        self.assertTrue(runtime.paused)
        self.assertEqual(ai.enabled, [7])
        self.assertNotIn("serial-resume", order)

        self.now_monotonic = 1.0
        handler.tick()
        self.assertFalse(runtime.paused)
        self.assertLess(order.index("ai-enable"), order.index("serial-resume"))

    def test_ota_activation_interlock_rejects_start_before_ai_or_motion(self) -> None:
        self.runtime.prepare_decision = (False, "OTA_ACTIVATION_IN_PROGRESS")

        self.handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "start-during-ota", patrol_id=7),
        )

        self.assertEqual(self.runtime.calls, [])
        self.assertEqual(self.ai.enabled, [])
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")
        self.assertEqual(
            self.mqtt.messages[-1][1]["reason"],
            "OTA_ACTIVATION_IN_PROGRESS",
        )

    def test_slow_route_prepare_cannot_start_after_command_expiry(self) -> None:
        self.runtime.prepare_callback = lambda: setattr(
            self, "now_wall", NOW + timedelta(seconds=11)
        )

        self.handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "slow-route", patrol_id=7),
        )

        self.assertEqual(
            self.runtime.prepared_expires_at,
            NOW + timedelta(seconds=10),
        )
        self.assertEqual(self.runtime.cancel_count, 1)
        self.assertEqual(self.runtime.calls, [])
        self.assertEqual(self.ai.enabled, [])
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")
        self.assertEqual(
            self.mqtt.messages[-1][1]["reason"],
            "COMMAND_EXPIRED_DURING_PREPARE",
        )

    def test_slow_ai_enable_cannot_start_motor_after_command_expiry(self) -> None:
        self.ai.enable_callback = lambda: setattr(
            self, "now_wall", NOW + timedelta(seconds=11)
        )

        self.handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "slow-ai", patrol_id=7),
        )

        self.assertEqual(self.runtime.calls, [])
        self.assertEqual(self.runtime.cancel_count, 1)
        self.assertEqual(self.ai.enabled, [7])
        self.assertEqual(self.ai.disabled, ["COMMAND_EXPIRED_DURING_START"])
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")
        self.assertEqual(
            self.mqtt.messages[-1][1]["reason"],
            "COMMAND_EXPIRED_DURING_PREPARE",
        )

    def test_runtime_dispatch_expiry_is_rejected_without_start_or_stop(self) -> None:
        self.runtime.wall_clock = lambda: self.now_wall
        self.runtime.start_dispatch_callback = lambda: setattr(
            self, "now_wall", NOW + timedelta(seconds=10)
        )

        self.handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "dispatch-expired", patrol_id=7),
        )

        self.assertEqual(self.runtime.actual_start_count, 0)
        self.assertEqual(
            self.runtime.calls,
            [
                (
                    "START_PATROL",
                    {
                        "patrolId": 7,
                        "expires_at": NOW + timedelta(seconds=10),
                    },
                )
            ],
        )
        self.assertEqual(self.runtime.cancel_count, 1)
        self.assertEqual(self.ai.enabled, [7])
        self.assertEqual(self.ai.disabled, ["COMMAND_EXPIRED_DURING_START"])
        self.assertEqual(self.store.state, "IDLE")
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")
        self.assertEqual(
            self.mqtt.messages[-1][1]["reason"],
            "COMMAND_EXPIRED_DURING_START",
        )

    def test_expired_start_still_disables_ai_and_acks_when_cleanup_fails(
        self,
    ) -> None:
        self.runtime.wall_clock = lambda: self.now_wall
        self.runtime.start_dispatch_callback = lambda: setattr(
            self, "now_wall", NOW + timedelta(seconds=10)
        )

        def fail_cleanup() -> None:
            self.runtime.cancel_count += 1
            raise RuntimeError("lease release failed")

        self.runtime.cancel_prepared_patrol = fail_cleanup

        self.handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "cleanup-failed", patrol_id=7),
        )

        self.assertEqual(self.runtime.actual_start_count, 0)
        self.assertEqual(self.runtime.cancel_count, 1)
        self.assertEqual(self.ai.disabled, ["COMMAND_EXPIRED_DURING_START"])
        self.assertEqual(self.store.state, "IDLE")
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")
        self.assertEqual(
            self.mqtt.messages[-1][1]["reason"],
            "COMMAND_EXPIRED_DURING_START",
        )

    def test_retained_token_is_written_outside_git_and_not_in_cache(self) -> None:
        command = payload("SET_TOKEN", "token-1")
        command["token"] = "runtime-secret"
        self.handler.handle(self.settings.command_topic, command)
        token_path = Path(self.settings.service_token_file)
        self.assertEqual(token_path.read_text(encoding="utf-8").strip(), "runtime-secret")
        cache = Path(self.settings.command_cache_file).read_text(encoding="utf-8")
        self.assertNotIn("runtime-secret", cache)

    def test_start_mapping_uses_existing_backend_contract(self) -> None:
        self.handler.handle(
            self.settings.command_topic,
            payload(
                "START_MAPPING",
                "map-command",
                mapping_session_id=12,
            ),
        )

        self.assertEqual(self.mapping.starts, [(12, "map-command")])
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "SUCCEEDED")

    def test_stop_mapping_finishes_same_session_once_and_acks_success(self) -> None:
        self.mapping.active = True
        self.mapping.state = "MAPPING"
        self.mapping.mapping_session_id = 12

        command = payload(
            "STOP_MAPPING",
            "stop-map-1",
            mapping_session_id=12,
        )
        self.handler.handle(self.settings.command_topic, command)
        self.handler.handle(self.settings.command_topic, command)

        self.assertEqual(self.mapping.finishes, [12])
        self.assertEqual(
            [message[1]["status"] for message in self.mqtt.messages[-2:]],
            ["SUCCEEDED", "SUCCEEDED"],
        )
        self.assertEqual(self.mqtt.messages[-1][1]["command"], "STOP_MAPPING")

    def test_stop_mapping_is_idempotent_while_save_or_upload_is_active(self) -> None:
        for state in ("STOPPING", "SAVING", "UPLOADING"):
            with self.subTest(state=state):
                self.mapping.active = True
                self.mapping.state = state
                self.mapping.mapping_session_id = 12
                self.mapping.finishes.clear()

                self.handler.handle(
                    self.settings.command_topic,
                    payload(
                        "STOP_MAPPING",
                        f"stop-map-{state.lower()}",
                        mapping_session_id=12,
                    ),
                )

                self.assertEqual(self.mapping.finishes, [])
                self.assertEqual(self.mqtt.messages[-1][1]["status"], "SUCCEEDED")

    def test_stop_mapping_rejects_a_different_session(self) -> None:
        self.mapping.active = True
        self.mapping.state = "MAPPING"
        self.mapping.mapping_session_id = 12

        self.handler.handle(
            self.settings.command_topic,
            payload("STOP_MAPPING", "wrong-map", mapping_session_id=13),
        )

        self.assertEqual(self.mapping.finishes, [])
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")
        self.assertEqual(
            self.mqtt.messages[-1][1]["reason"],
            "MAPPING_SESSION_MISMATCH",
        )

    def test_stop_mapping_rejects_idle_without_starting_work(self) -> None:
        self.handler.handle(
            self.settings.command_topic,
            payload("STOP_MAPPING", "idle-map", mapping_session_id=12),
        )

        self.assertEqual(self.mapping.finishes, [])
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")
        self.assertEqual(
            self.mqtt.messages[-1][1]["reason"],
            "MAPPING_NOT_ACTIVE",
        )

    def test_runtime_failure_aborts_mapping_and_replays_failed_ack(self) -> None:
        command = payload(
            "START_MAPPING",
            "map-fault",
            mapping_session_id=12,
        )
        self.handler.handle(self.settings.command_topic, command)
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "SUCCEEDED")

        self.handler.on_runtime_failure("MOTOR_FAULT")

        self.assertEqual(self.mapping.aborts, ["MOTOR_FAULT"])
        self.assertFalse(self.mapping.active)
        self.assertEqual(self.mqtt.messages[-1][1]["command"], "START_MAPPING")
        self.assertEqual(self.mqtt.messages[-1][1]["commandId"], "map-fault")
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "FAILED")
        self.assertEqual(self.store.state, "ERROR")

        self.handler.handle(self.settings.command_topic, command)
        self.assertEqual(self.mapping.starts, [(12, "map-fault")])
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "FAILED")

        self.handler.handle(
            self.settings.command_topic,
            payload(
                "START_MAPPING",
                "map-retry",
                mapping_session_id=12,
            ),
        )
        self.assertEqual(
            self.mapping.starts,
            [(12, "map-fault"), (12, "map-retry")],
        )
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "SUCCEEDED")
        self.assertEqual(self.store.state, "IDLE")

    def test_mapping_start_lifecycle_race_is_failed_not_rejected(self) -> None:
        self.mapping.start_decision = (False, "RUNTIME_LIFECYCLE_CHANGED")

        self.handler.handle(
            self.settings.command_topic,
            payload(
                "START_MAPPING",
                "map-start-race",
                mapping_session_id=12,
            ),
        )

        self.assertEqual(self.mqtt.messages[-1][1]["status"], "FAILED")
        self.assertEqual(
            self.mqtt.messages[-1][1]["reason"],
            "RUNTIME_LIFECYCLE_CHANGED",
        )
        self.assertEqual(self.store.state, "ERROR")

    def test_mapping_readiness_rejection_publishes_reason(self) -> None:
        self.mapping.start_decision = (False, "ODOMETRY_NOT_READY")

        self.handler.handle(
            self.settings.command_topic,
            payload(
                "START_MAPPING",
                "map-not-ready",
                mapping_session_id=12,
            ),
        )

        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")
        self.assertEqual(
            self.mqtt.messages[-1][1]["reason"],
            "ODOMETRY_NOT_READY",
        )

    def test_mapping_requires_session_id_and_blocks_patrol_concurrency(self) -> None:
        self.handler.handle(
            self.settings.command_topic,
            payload("START_MAPPING", "missing-session"),
        )
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")

        self.mapping.active = True
        self.handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "patrol-during-map", patrol_id=7),
        )
        self.assertEqual(self.runtime.calls, [])
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
