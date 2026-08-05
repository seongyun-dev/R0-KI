from __future__ import annotations

import json
import threading
import unittest
from unittest.mock import Mock

from control.motion_controller import MotionController, MotionControllerSettings
from mission.mission_controller import MissionCommand, MissionController
from runtime.robot_runtime import RobotRuntime, RuntimeSettings
from safety.safety_controller import SafetyController, SafetySettings
from serial_comm.protocol import (
    HardwareStatus,
    LineSensorStatus,
    MotorStatus,
    Odometry,
    ProtocolSettings,
)
from state.robot_state import RobotStateStore


class FakeBridge:
    def __init__(self, incoming: list[str]) -> None:
        self.connected = False
        self.new_connection = True
        self.written: list[dict[str, object]] = []
        self.incoming = incoming

    def ensure_connected(self) -> bool:
        if self.new_connection:
            self.connected = True
            self.new_connection = False
            return True
        return False

    def is_connected(self) -> bool:
        return self.connected

    def write_line(self, line: str) -> bool:
        self.written.append(json.loads(line))
        return True

    def read_line(self) -> str | None:
        return self.incoming.pop(0) if self.incoming else None

    def close(self, final_message: str | None = None) -> None:
        if final_message:
            self.write_line(final_message)
        self.connected = False


class BlockingControlBridge(FakeBridge):
    """Hold one CONTROL before recording it to expose STOP/write races."""

    def __init__(self) -> None:
        super().__init__([])
        self.control_entered = threading.Event()
        self.release_control = threading.Event()

    def write_line(self, line: str) -> bool:
        message = json.loads(line)
        if message["type"] == "control":
            self.control_entered.set()
            if not self.release_control.wait(timeout=2.0):
                raise TimeoutError("test did not release blocked CONTROL")
        self.written.append(message)
        return True


class FailingStopBridge(FakeBridge):
    def write_line(self, line: str) -> bool:
        message = json.loads(line)
        self.written.append(message)
        return message["type"] != "stop"


class BlockingMissionController(MissionController):
    """Hold one mailbox submit to expose STOP/request ordering races."""

    def __init__(self, steering_center_deg: int) -> None:
        super().__init__(steering_center_deg)
        self.submit_entered = threading.Event()
        self.release_submit = threading.Event()

    def submit(self, command: MissionCommand) -> None:
        self.submit_entered.set()
        if not self.release_submit.wait(timeout=2.0):
            raise TimeoutError("test did not release blocked mission submit")
        super().submit(command)


def hardware_status_message() -> str:
    return json.dumps(
        {
            "type": "hardwareStatus",
            "battery": 82.5,
            "motor": "NORMAL",
            "lineSensor": "NORMAL",
        }
    )


def odometry_message(
    *,
    seq: int = 1,
    uptime_ms: int = 100,
    left_ticks: int = 0,
    right_ticks: int = 0,
) -> str:
    return json.dumps(
        {
            "type": "odometry",
            "seq": seq,
            "uptimeMs": uptime_ms,
            "leftTicks": left_ticks,
            "rightTicks": right_ticks,
        }
    )


def encoder_zero_ack_message() -> str:
    return json.dumps(
        {"type": "ack", "command": "ENCODER_ZERO", "sequence": 2}
    )


def complete_handshake(runtime: RobotRuntime) -> None:
    runtime._handle_ack("ENCODER_ZERO")


def create_runtime(
    bridge: FakeBridge,
    mission: MissionController | None = None,
) -> tuple[RobotRuntime, RobotStateStore]:
    store = RobotStateStore()
    runtime = RobotRuntime(
        bridge=bridge,
        protocol_settings=ProtocolSettings(),
        mission=mission or MissionController(80),
        motion=MotionController(
            MotionControllerSettings(
                0.065, 100, 10, 255, 10, 0.5, 5, 80, 60, 100
            )
        ),
        safety=SafetyController(
            SafetySettings(
                odometry_timeout_sec=0.3,
                hardware_status_timeout_sec=1.0,
                low_battery_percent=None,
            )
        ),
        state_store=store,
        settings=RuntimeSettings(0.0),
    )
    return runtime, store


class RobotRuntimeTest(unittest.TestCase):
    def test_routes_final_contract_messages_and_updates_store(self) -> None:
        bridge = FakeBridge([
            encoder_zero_ack_message(),
            hardware_status_message(),
            odometry_message(),
            odometry_message(seq=2, uptime_ms=200),
        ])
        runtime, store = create_runtime(bridge)
        received_hardware: list[HardwareStatus] = []
        received_odometry: list[Odometry] = []

        runtime.add_hardware_status_listener(received_hardware.append)

        def odometry_listener(odometry: Odometry, _state: object) -> None:
            received_odometry.append(odometry)
            if odometry.seq == 2:
                runtime.request_stop()

        runtime.add_odometry_listener(odometry_listener)
        runtime.run_forever()

        snapshot = store.snapshot()
        self.assertEqual(
            snapshot.hardware_status,
            HardwareStatus(
                battery_percent=82.5,
                motor=MotorStatus.NORMAL,
                line_sensor=LineSensorStatus.NORMAL,
            ),
        )
        self.assertEqual(
            snapshot.odometry,
            Odometry(2, 200, 0, 0),
        )
        self.assertIsNotNone(snapshot.motion_state)
        self.assertIsNotNone(snapshot.safety_decision)
        self.assertEqual(len(received_hardware), 1)
        self.assertEqual(len(received_odometry), 2)

        written_types = [item["type"] for item in bridge.written]
        self.assertEqual(
            written_types[:4],
            ["stop", "hello", "encoder_zero", "status"],
        )
        self.assertEqual(written_types[-1], "stop")

    def test_hardware_status_and_odometry_are_independent(self) -> None:
        bridge = FakeBridge(
            [
                encoder_zero_ack_message(),
                odometry_message(),
                hardware_status_message(),
            ]
        )
        runtime, store = create_runtime(bridge)

        def stop_after_hardware(_status: HardwareStatus) -> None:
            runtime.request_stop()

        runtime.add_hardware_status_listener(stop_after_hardware)
        runtime.run_forever()
        snapshot = store.snapshot()
        self.assertIsNotNone(snapshot.odometry)
        self.assertIsNotNone(snapshot.hardware_status)
        self.assertIsNotNone(snapshot.motion_state)

    def test_allowed_safety_sends_control_after_baseline(self) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime.mission.start_patrol(speed=30, steering_deg=80)
        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(1, 100, 10, 10))
        runtime._handle_odometry(Odometry(2, 200, 11, 11))

        self.assertEqual(
            [message["type"] for message in bridge.written].count("control"),
            1,
        )

    def test_fault_and_emergency_stop_never_send_control(self) -> None:
        scenarios = (
            (
                False,
                HardwareStatus(
                    82.5, MotorStatus.FAULT, LineSensorStatus.NORMAL
                ),
            ),
            (
                True,
                HardwareStatus(
                    82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL
                ),
            ),
        )
        for emergency, status in scenarios:
            with self.subTest(emergency=emergency):
                bridge = FakeBridge([])
                runtime, _store = create_runtime(bridge)
                bridge.connected = True
                runtime._on_connected()
                complete_handshake(runtime)
                runtime.mission.start_patrol(speed=30, steering_deg=80)
                runtime._handle_hardware_status(status)
                if emergency:
                    runtime.mission.emergency_stop()
                runtime._handle_odometry(Odometry(1, 100, 0, 0))
                runtime._handle_odometry(Odometry(2, 200, 1, 1))
                types = [message["type"] for message in bridge.written]
                self.assertNotIn("control", types)
                self.assertEqual(types[-1], "stop")

    def test_serial_protocol_faults_require_reconnect_and_new_start(self) -> None:
        for reason in ("INVALID_PROTOCOL_MESSAGE", "ESP32_COMMAND_TIMEOUT"):
            with self.subTest(reason=reason):
                bridge = FakeBridge([])
                runtime, _store = create_runtime(bridge)
                faults: list[str] = []
                runtime.add_safety_fault_listener(faults.append)
                bridge.connected = True
                runtime._on_connected()
                complete_handshake(runtime)
                runtime._handle_hardware_status(
                    HardwareStatus(
                        82.5,
                        MotorStatus.NORMAL,
                        LineSensorStatus.NORMAL,
                    )
                )
                runtime._handle_odometry(Odometry(1, 100, 0, 0))
                runtime.mission.start_patrol(speed=30, steering_deg=80)

                runtime._handle_serial_protocol_fault(
                    reason,
                    active_only=reason == "INVALID_PROTOCOL_MESSAGE",
                )

                self.assertFalse(bridge.connected)
                self.assertFalse(runtime.mission.snapshot().patrol_active)
                self.assertEqual(faults, [reason])
                control_count = sum(
                    item["type"] == "control" for item in bridge.written
                )

                # Fresh valid telemetry after the mandatory handshake cannot
                # resurrect the command that preceded the bad Serial frame.
                bridge.connected = True
                runtime._on_connected()
                complete_handshake(runtime)
                runtime._handle_hardware_status(
                    HardwareStatus(
                        82.5,
                        MotorStatus.NORMAL,
                        LineSensorStatus.NORMAL,
                    )
                )
                runtime._handle_odometry(Odometry(1, 100, 0, 0))
                runtime._handle_odometry(Odometry(2, 200, 1, 1))
                self.assertEqual(
                    sum(item["type"] == "control" for item in bridge.written),
                    control_count,
                )

                runtime.mission.start_patrol(speed=30, steering_deg=80)
                runtime._handle_odometry(Odometry(3, 300, 2, 2))
                self.assertGreater(
                    sum(item["type"] == "control" for item in bridge.written),
                    control_count,
                )

    def test_boot_garbage_is_stopped_without_reconnect_loop(self) -> None:
        bridge = FakeBridge(
            [
                "ets Jun  8 2016 00:22:57",
                encoder_zero_ack_message(),
                hardware_status_message(),
            ]
        )
        runtime, store = create_runtime(bridge)

        runtime.add_hardware_status_listener(
            lambda _status: runtime.request_stop()
        )
        runtime.run_forever()

        self.assertIsNotNone(store.snapshot().hardware_status)
        self.assertEqual(runtime.connection_generation, 1)
        self.assertEqual(
            [item["type"] for item in bridge.written[:5]],
            ["stop", "hello", "encoder_zero", "status", "stop"],
        )

    def test_invalid_frame_reconnects_when_outer_nav_patrol_is_pending(
        self,
    ) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime.add_safety_fault_listener(lambda _reason: True)

        runtime._handle_serial_protocol_fault(
            "INVALID_PROTOCOL_MESSAGE",
            active_only=True,
        )

        self.assertFalse(bridge.connected)
        self.assertEqual(bridge.written[-1]["type"], "stop")

    def test_active_hardware_fault_cannot_auto_resume_when_status_recovers(
        self,
    ) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        faults: list[str] = []
        runtime.add_safety_fault_listener(faults.append)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(1, 100, 0, 0))
        runtime.mission.start_patrol(speed=30, steering_deg=80)

        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.FAULT, LineSensorStatus.NORMAL)
        )

        self.assertFalse(runtime.mission.snapshot().patrol_active)
        self.assertEqual(faults, ["MOTOR_FAULT"])
        control_count = sum(
            item["type"] == "control" for item in bridge.written
        )
        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(2, 200, 1, 1))
        self.assertEqual(
            sum(item["type"] == "control" for item in bridge.written),
            control_count,
        )

    def test_active_telemetry_timeout_abandons_patrol(self) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        now = [0.0]
        runtime._clock = lambda: now[0]
        faults: list[str] = []
        runtime.add_safety_fault_listener(faults.append)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(1, 100, 0, 0))
        runtime.mission.start_patrol(speed=30, steering_deg=80)

        now[0] = 0.31
        runtime._evaluate_idle_safety()

        self.assertFalse(runtime.mission.snapshot().patrol_active)
        self.assertEqual(faults, ["ODOMETRY_TIMEOUT"])

    def test_hardware_status_does_not_call_motion_update(self) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        update = Mock(wraps=runtime._motion.update)
        runtime._motion.update = update

        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )

        update.assert_not_called()

    def test_raw_line_values_are_stored_and_logged_without_motion_update(
        self,
    ) -> None:
        bridge = FakeBridge([])
        runtime, store = create_runtime(bridge)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        update = Mock(wraps=runtime._motion.update)
        runtime._motion.update = update
        status = HardwareStatus(
            11.82,
            MotorStatus.NORMAL,
            LineSensorStatus.NORMAL,
            (0, 0, 1, 0, 0),
        )

        with self.assertLogs("runtime.robot_runtime", level="INFO") as logs:
            runtime._handle_hardware_status(status)
            runtime._handle_hardware_status(status)

        self.assertEqual(store.snapshot().hardware_status, status)
        self.assertEqual(
            [line for line in logs.output if "[LINE]" in line],
            ["INFO:runtime.robot_runtime:[LINE] raw=[0, 0, 1, 0, 0]"],
        )
        update.assert_not_called()

    def test_operating_data_before_encoder_zero_ack_cannot_control(self) -> None:
        bridge = FakeBridge([])
        runtime, store = create_runtime(bridge)
        bridge.connected = True
        runtime._on_connected()
        runtime.mission.start_patrol(speed=30, steering_deg=80)

        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(1, 100, 10, 10))
        runtime._handle_odometry(Odometry(2, 200, 11, 11))

        self.assertNotIn(
            "control", [message["type"] for message in bridge.written]
        )
        self.assertIsNone(store.snapshot().odometry)
        self.assertIsNone(store.snapshot().hardware_status)
        self.assertEqual(
            [message["type"] for message in bridge.written],
            ["stop", "hello", "encoder_zero", "status"],
        )

    def test_missing_encoder_zero_ack_retries_then_reconnects(self) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        now = 0.0
        runtime._clock = lambda: now
        bridge.connected = True
        runtime._on_connected()

        with self.assertLogs("runtime.robot_runtime", level="WARNING") as logs:
            runtime._handle_hardware_status(
                HardwareStatus(
                    82.5,
                    MotorStatus.NORMAL,
                    LineSensorStatus.NORMAL,
                )
            )
            runtime._handle_odometry(Odometry(1, 100, 0, 0))
            now = 0.5
            runtime._maintain_encoder_zero_handshake()
            now = 1.0
            runtime._maintain_encoder_zero_handshake()
            now = 1.5
            runtime._maintain_encoder_zero_handshake()

        self.assertFalse(bridge.connected)
        self.assertEqual(
            [message["type"] for message in bridge.written],
            [
                "stop",
                "hello",
                "encoder_zero",
                "status",
                "stop",
                "encoder_zero",
                "status",
                "stop",
                "encoder_zero",
                "status",
                "stop",
            ],
        )
        waiting_logs = [
            line for line in logs.output if "Operating data ignored" in line
        ]
        self.assertEqual(len(waiting_logs), 1)
        self.assertTrue(
            any("reconnecting Serial" in line for line in logs.output)
        )

    def test_encoder_zero_ack_after_retry_opens_operating_gate(self) -> None:
        bridge = FakeBridge([])
        runtime, store = create_runtime(bridge)
        now = 0.0
        runtime._clock = lambda: now
        bridge.connected = True
        runtime._on_connected()

        now = 0.5
        runtime._maintain_encoder_zero_handshake()
        runtime._handle_ack("ENCODER_ZERO")
        status = HardwareStatus(
            82.5,
            MotorStatus.NORMAL,
            LineSensorStatus.NORMAL,
        )
        runtime._handle_hardware_status(status)

        self.assertTrue(bridge.connected)
        self.assertEqual(store.snapshot().hardware_status, status)
        self.assertEqual(
            [message["type"] for message in bridge.written].count(
                "encoder_zero"
            ),
            2,
        )

    def test_latest_emergency_stop_is_rechecked_before_control_write(self) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime.mission.start_patrol(speed=30, steering_deg=80)
        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(1, 100, 0, 0))

        runtime.add_odometry_listener(
            lambda _odometry, _state: runtime.mission.emergency_stop()
        )
        runtime._handle_odometry(Odometry(2, 200, 1, 1))

        types = [message["type"] for message in bridge.written]
        self.assertNotIn("control", types)
        self.assertEqual(types[-1], "stop")

    def test_manual_mailbox_applies_motion_on_serial_owner_thread(self) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(1, 100, 0, 0))

        before = len(bridge.written)
        runtime.request_motion_target(45, 81)
        self.assertEqual(len(bridge.written), before)
        runtime._handle_odometry(Odometry(2, 200, 1, 1))
        runtime._handle_odometry(Odometry(3, 300, 2, 2))

        controls = [item for item in bridge.written if item["type"] == "control"]
        self.assertGreater(controls[-1]["speed"], 0)
        self.assertLessEqual(controls[-1]["speed"], 45)
        self.assertEqual(controls[-1]["steering"], 81)

    def test_repeated_identical_manual_targets_do_not_starve_control(self) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(1, 100, 0, 0))

        for sequence in range(2, 7):
            runtime.request_motion_target(45, 81)
            runtime._handle_odometry(
                Odometry(sequence, sequence * 100, sequence - 1, sequence - 1)
            )

        controls = [item for item in bridge.written if item["type"] == "control"]
        self.assertTrue(controls)
        self.assertGreater(controls[-1]["speed"], 0)
        self.assertEqual(controls[-1]["steering"], 81)

    def test_manual_stationary_steering_sends_one_zero_speed_control(self) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(1, 100, 0, 0))

        runtime.request_motion_target(0, 79, stationary_steering=True)
        runtime._handle_odometry(Odometry(2, 200, 0, 0))
        runtime._handle_odometry(Odometry(3, 300, 0, 0))

        controls = [item for item in bridge.written if item["type"] == "control"]
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["speed"], 0)
        self.assertEqual(controls[0]["steering"], 79)

    def test_listener_normal_stop_is_rechecked_before_control_write(self) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime.mission.start_patrol(speed=30, steering_deg=80)
        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(1, 100, 0, 0))

        runtime.add_odometry_listener(
            lambda _odometry, _state: runtime.stop_patrol("DESTINATION_REACHED")
        )
        runtime._handle_odometry(Odometry(2, 200, 1, 1))

        types = [message["type"] for message in bridge.written]
        self.assertNotIn("control", types)
        self.assertEqual(types[-1], "stop")

    def test_concurrent_stop_is_last_on_wire_after_inflight_control(self) -> None:
        bridge = BlockingControlBridge()
        runtime, _store = create_runtime(bridge)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime.mission.start_patrol(speed=30, steering_deg=80)
        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(1, 100, 0, 0))
        before = len(bridge.written)

        control_thread = threading.Thread(
            target=lambda: runtime._handle_odometry(Odometry(2, 200, 1, 1))
        )
        control_thread.start()
        self.assertTrue(bridge.control_entered.wait(timeout=1.0))

        stop_done = threading.Event()

        def stop_patrol() -> None:
            runtime.stop_patrol("CONCURRENT_STOP")
            stop_done.set()

        stop_thread = threading.Thread(target=stop_patrol)
        stop_thread.start()
        self.assertFalse(stop_done.wait(timeout=0.1))
        bridge.release_control.set()
        control_thread.join(timeout=1.0)
        stop_thread.join(timeout=1.0)

        self.assertFalse(control_thread.is_alive())
        self.assertFalse(stop_thread.is_alive())
        self.assertTrue(stop_done.is_set())
        self.assertEqual(
            [message["type"] for message in bridge.written[before:]],
            ["control", "stop"],
        )

    def test_concurrent_stop_cannot_be_undone_by_drained_manual_request(
        self,
    ) -> None:
        bridge = FakeBridge([])
        mission = BlockingMissionController(80)
        runtime, _store = create_runtime(bridge, mission)
        bridge.connected = True
        runtime.request_motion_target(45, 81)

        drain_thread = threading.Thread(target=runtime._drain_motion_requests)
        drain_thread.start()
        self.assertTrue(mission.submit_entered.wait(timeout=1.0))

        stop_done = threading.Event()

        def stop_patrol() -> None:
            runtime.stop_patrol("CONCURRENT_MAILBOX_STOP")
            stop_done.set()

        stop_thread = threading.Thread(target=stop_patrol)
        stop_thread.start()
        self.assertFalse(stop_done.wait(timeout=0.1))

        mission.release_submit.set()
        drain_thread.join(timeout=1.0)
        stop_thread.join(timeout=1.0)

        self.assertFalse(drain_thread.is_alive())
        self.assertFalse(stop_thread.is_alive())
        self.assertTrue(stop_done.is_set())
        self.assertFalse(runtime.mission.patrol_active)
        self.assertEqual(runtime.mission.current().speed, 0)
        self.assertFalse(runtime._manual_motion_active)
        self.assertEqual(bridge.written[-1]["type"], "stop")

    def test_connection_listener_failure_cannot_rearm_or_abort_handshake(
        self,
    ) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        bridge.connected = True
        observed: list[tuple[str, int]] = []

        def failing_listener(generation: int) -> None:
            observed.append(("failing", generation))
            runtime.mission.start_patrol(speed=45, steering_deg=81)
            raise RuntimeError("listener cleanup failed")

        runtime.add_connection_listener(failing_listener)
        runtime.add_connection_listener(
            lambda generation: observed.append(("next", generation))
        )

        runtime._on_connected()

        self.assertEqual(
            observed,
            [("failing", 1), ("next", 1)],
        )
        self.assertEqual(runtime.connection_generation, 1)
        self.assertFalse(runtime.mission.patrol_active)
        self.assertEqual(runtime.mission.current().speed, 0)
        self.assertEqual(
            [message["type"] for message in bridge.written[-4:]],
            ["stop", "hello", "encoder_zero", "status"],
        )

    def test_public_stop_surfaces_serial_delivery_failure_after_fail_close(
        self,
    ) -> None:
        for bridge in (FailingStopBridge([]), FakeBridge([])):
            with self.subTest(connected=isinstance(bridge, FailingStopBridge)):
                runtime, _store = create_runtime(bridge)
                bridge.connected = isinstance(bridge, FailingStopBridge)
                runtime.mission.start_patrol(speed=40, steering_deg=81)

                with self.assertRaisesRegex(
                    RuntimeError,
                    "ESP32 STOP was not delivered",
                ):
                    runtime.stop_patrol("MQTT_STOP_PATROL")

                self.assertFalse(runtime.mission.patrol_active)
                self.assertEqual(runtime.mission.current().speed, 0)
                self.assertFalse(runtime._manual_motion_active)

    def test_firmware_error_latches_fault_and_stops(self) -> None:
        bridge = FakeBridge([
            json.dumps({"type": "error", "fault": "COMMAND_TIMEOUT"})
        ])
        runtime, _store = create_runtime(bridge)

        def stop_after_read() -> None:
            runtime.request_stop()

        original_read = bridge.read_line

        def read_once() -> str | None:
            line = original_read()
            if line is not None:
                stop_after_read()
            return line

        bridge.read_line = read_once
        runtime.run_forever()

        self.assertEqual(bridge.written[-2]["type"], "stop")

    def test_reconnect_uses_first_odometry_as_baseline(self) -> None:
        for first_ticks_after_reconnect in (0, 110):
            with self.subTest(first_ticks=first_ticks_after_reconnect):
                bridge = FakeBridge([])
                runtime, store = create_runtime(bridge)
                bridge.connected = True
                runtime._on_connected()
                complete_handshake(runtime)
                runtime.mission.start_patrol(speed=30, steering_deg=80)
                normal = HardwareStatus(
                    82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL
                )
                runtime._handle_hardware_status(normal)
                runtime._handle_odometry(Odometry(1, 100, 100, 100))
                runtime._handle_odometry(Odometry(2, 200, 110, 110))
                controls_before = sum(
                    message["type"] == "control" for message in bridge.written
                )

                runtime._on_connected()
                complete_handshake(runtime)
                self.assertEqual(
                    [message["type"] for message in bridge.written[-4:]],
                    ["stop", "hello", "encoder_zero", "status"],
                )
                runtime._handle_hardware_status(normal)
                runtime._handle_odometry(
                    Odometry(
                        3,
                        300,
                        first_ticks_after_reconnect,
                        first_ticks_after_reconnect,
                    )
                )
                baseline_state = store.snapshot().motion_state
                assert baseline_state is not None
                self.assertEqual(baseline_state.encoder_error_ticks, 0)
                self.assertEqual(baseline_state.left_distance_m, 0.0)
                self.assertEqual(baseline_state.right_distance_m, 0.0)
                self.assertEqual(bridge.written[-1]["type"], "stop")
                runtime._handle_odometry(
                    Odometry(
                        4,
                        400,
                        first_ticks_after_reconnect + 1,
                        first_ticks_after_reconnect + 1,
                    )
                )

                controls_after = sum(
                    message["type"] == "control" for message in bridge.written
                )
                self.assertEqual(controls_after, controls_before)
                self.assertFalse(runtime.mission.patrol_active)
                runtime.mission.submit(MissionCommand(30, 80))
                runtime._handle_odometry(
                    Odometry(
                        5,
                        500,
                        first_ticks_after_reconnect + 2,
                        first_ticks_after_reconnect + 2,
                    )
                )
                self.assertEqual(
                    sum(
                        message["type"] == "control"
                        for message in bridge.written
                    ),
                    controls_before,
                )
                runtime.mission.start_patrol(speed=30, steering_deg=80)
                runtime._handle_odometry(
                    Odometry(
                        6,
                        600,
                        first_ticks_after_reconnect + 3,
                        first_ticks_after_reconnect + 3,
                    )
                )
                self.assertEqual(
                    sum(
                        message["type"] == "control"
                        for message in bridge.written
                    ),
                    controls_before + 1,
                )

    def test_uptime_decrease_requires_reconnect_and_new_start(self) -> None:
        bridge = FakeBridge([])
        runtime, store = create_runtime(bridge)
        faults: list[str] = []
        runtime.add_safety_fault_listener(faults.append)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime.mission.start_patrol(speed=30, steering_deg=80)
        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(1, 1000, 100, 100))
        runtime._handle_odometry(Odometry(2, 1100, 110, 110))
        controls_before = sum(
            message["type"] == "control" for message in bridge.written
        )

        runtime._handle_odometry(Odometry(0, 10, 0, 0))

        self.assertEqual(
            sum(message["type"] == "control" for message in bridge.written),
            controls_before,
        )
        self.assertEqual(bridge.written[-1]["type"], "stop")
        self.assertFalse(runtime.mission.patrol_active)
        self.assertFalse(bridge.connected)
        self.assertEqual(faults, ["ESP32_UPTIME_RESET"])

        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime._handle_hardware_status(
            HardwareStatus(82.5, MotorStatus.NORMAL, LineSensorStatus.NORMAL)
        )
        runtime._handle_odometry(Odometry(1, 20, 1, 1))
        runtime._handle_odometry(Odometry(2, 30, 2, 2))
        self.assertEqual(
            sum(message["type"] == "control" for message in bridge.written),
            controls_before,
        )
        runtime.mission.start_patrol(speed=30, steering_deg=80)
        runtime._handle_odometry(Odometry(3, 40, 3, 3))
        self.assertEqual(
            sum(message["type"] == "control" for message in bridge.written),
            controls_before + 1,
        )


if __name__ == "__main__":
    unittest.main()
