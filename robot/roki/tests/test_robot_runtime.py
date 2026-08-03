from __future__ import annotations

import json
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
) -> tuple[RobotRuntime, RobotStateStore]:
    store = RobotStateStore()
    runtime = RobotRuntime(
        bridge=bridge,
        protocol_settings=ProtocolSettings(),
        mission=MissionController(80),
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
        runtime.mission.submit(MissionCommand(speed=30, steering_deg=80))
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
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
                runtime.mission.submit(MissionCommand(30, 80))
                bridge.connected = True
                runtime._on_connected()
                complete_handshake(runtime)
                runtime._handle_hardware_status(status)
                if emergency:
                    runtime.mission.emergency_stop()
                runtime._handle_odometry(Odometry(1, 100, 0, 0))
                runtime._handle_odometry(Odometry(2, 200, 1, 1))
                types = [message["type"] for message in bridge.written]
                self.assertNotIn("control", types)
                self.assertEqual(types[-1], "stop")

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
        runtime.mission.submit(MissionCommand(30, 80))
        bridge.connected = True
        runtime._on_connected()

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
        self.assertEqual(bridge.written[-1]["type"], "stop")

    def test_latest_emergency_stop_is_rechecked_before_control_write(self) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        runtime.mission.submit(MissionCommand(30, 80))
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
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
        runtime.mission.submit(MissionCommand(30, 80))
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
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
                runtime.mission.submit(MissionCommand(30, 80))
                bridge.connected = True
                runtime._on_connected()
                complete_handshake(runtime)
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

                controls_after = sum(
                    message["type"] == "control" for message in bridge.written
                )
                self.assertEqual(controls_after, controls_before)
                state = store.snapshot().motion_state
                assert state is not None
                self.assertEqual(state.encoder_error_ticks, 0)
                self.assertEqual(state.left_distance_m, 0.0)
                self.assertEqual(state.right_distance_m, 0.0)
                self.assertEqual(bridge.written[-1]["type"], "stop")

    def test_uptime_decrease_resets_and_baselines_odometry(self) -> None:
        bridge = FakeBridge([])
        runtime, store = create_runtime(bridge)
        runtime.mission.submit(MissionCommand(30, 80))
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
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
        snapshot = store.snapshot()
        self.assertIsNone(snapshot.hardware_status)
        assert snapshot.motion_state is not None
        self.assertEqual(snapshot.motion_state.encoder_error_ticks, 0)
        self.assertEqual(snapshot.motion_state.left_distance_m, 0.0)
        self.assertEqual(bridge.written[-1]["type"], "stop")


if __name__ == "__main__":
    unittest.main()
