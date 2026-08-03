from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from backend_mqtt.command_handler import PatrolCommandHandler


NOW = datetime(2026, 8, 3, 0, 0, tzinfo=timezone.utc)


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
        self.cancel_count = 0

    def readiness(self):
        return True, "READY"

    def prepare_patrol(self):
        return self.prepare_decision

    def cancel_prepared_patrol(self) -> None:
        self.cancel_count += 1

    def send_command(self, command: str, **parameters) -> None:
        self.calls.append((command, parameters))
        if self.order is not None:
            self.order.append("serial-start" if command == "START_PATROL" else "serial-stop")
        if command == "START_PATROL":
            self.active_patrol_id = parameters["patrolId"]
        elif command == "STOP_PATROL":
            self.active_patrol_id = None
            self.paused = False

    def pause_patrol(self, reason: str) -> None:
        del reason
        self.paused = True

    def resume_patrol(self) -> None:
        self.paused = False

    def tick(self) -> None:
        return None


class FakeAi:
    def __init__(self, order: list[str] | None = None) -> None:
        self.enabled: list[int] = []
        self.disabled: list[str] = []
        self.order = order

    def readiness(self):
        return True, "AI_READY"

    def enable(self, patrol_id: int) -> None:
        self.enabled.append(patrol_id)
        if self.order is not None:
            self.order.append("ai-enable")

    def disable(self, reason: str) -> None:
        self.disabled.append(reason)
        if self.order is not None:
            self.order.append("ai-disable")


def payload(command: str, command_id: str, *, patrol_id: int | None = None) -> dict:
    result = {
        "schemaVersion": 1,
        "command": command,
        "commandId": command_id,
        "issuedAt": NOW.isoformat(),
        "expiresAt": (NOW + timedelta(seconds=10)).isoformat(),
    }
    if patrol_id is not None:
        result["patrolId"] = patrol_id
    return result


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
        self.now_monotonic = 0.0
        self.handler = PatrolCommandHandler(
            settings=self.settings,
            mqtt_client=self.mqtt,
            serial_reader=self.runtime,
            state_store=self.store,
            pipeline_runner=SimpleNamespace(),
            ai_controller=self.ai,
            command_cache_path=self.settings.command_cache_file,
            wall_clock=lambda: NOW,
            monotonic_clock=lambda: self.now_monotonic,
        )

    def test_valid_start_is_idempotent_across_handler_restart(self) -> None:
        command = payload("START_PATROL", "start-1", patrol_id=7)
        self.handler.handle(self.settings.command_topic, command)
        self.handler.handle(self.settings.command_topic, command)

        self.assertEqual(self.runtime.calls, [("START_PATROL", {"patrolId": 7})])
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

    def test_same_command_id_with_different_payload_is_rejected(self) -> None:
        first = payload("START_PATROL", "same", patrol_id=7)
        second = payload("START_PATROL", "same", patrol_id=8)
        self.handler.handle(self.settings.command_topic, first)
        self.handler.handle(self.settings.command_topic, second)
        self.assertEqual(len(self.runtime.calls), 1)
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")

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

    def test_obstacle_requires_stable_clear_before_resume(self) -> None:
        self.runtime.active_patrol_id = 7
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

    def test_ota_activation_interlock_rejects_start_before_ai_or_motion(self) -> None:
        self.runtime.prepare_decision = (False, "OTA_ACTIVATION_IN_PROGRESS")

        self.handler.handle(
            self.settings.command_topic,
            payload("START_PATROL", "start-during-ota", patrol_id=7),
        )

        self.assertEqual(self.runtime.calls, [])
        self.assertEqual(self.ai.enabled, [])
        self.assertEqual(self.mqtt.messages[-1][1]["status"], "REJECTED")

    def test_retained_token_is_written_outside_git_and_not_in_cache(self) -> None:
        command = payload("SET_TOKEN", "token-1")
        command["token"] = "runtime-secret"
        self.handler.handle(self.settings.command_topic, command)
        token_path = Path(self.settings.service_token_file)
        self.assertEqual(token_path.read_text(encoding="utf-8").strip(), "runtime-secret")
        cache = Path(self.settings.command_cache_file).read_text(encoding="utf-8")
        self.assertNotIn("runtime-secret", cache)


if __name__ == "__main__":
    unittest.main()
