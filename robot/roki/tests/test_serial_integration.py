from __future__ import annotations

import json
import unittest

from control.motion_controller import MotionController, MotionControllerSettings
from mission.mission_controller import MissionCommand, MissionController
from runtime.robot_runtime import RobotRuntime, RuntimeSettings
from safety.safety_controller import SafetyController, SafetySettings
from serial_comm.protocol import ProtocolSettings
from state.robot_state import RobotStateStore


class MockSerialBridge:
    """실제 USB 없이 line 단위 Serial 흐름을 재현한다."""

    def __init__(self, incoming: list[str]) -> None:
        self._connected = False
        self._new_connection = True
        self._incoming = incoming
        self.written: list[dict[str, object]] = []

    def ensure_connected(self) -> bool:
        if self._new_connection:
            self._new_connection = False
            self._connected = True
            return True
        return False

    def is_connected(self) -> bool:
        return self._connected

    def read_line(self) -> str | None:
        return self._incoming.pop(0) if self._incoming else None

    def write_line(self, line: str) -> bool:
        self.written.append(json.loads(line))
        return True

    def close(self, final_message: str | None = None) -> None:
        if final_message is not None:
            self.write_line(final_message)
        self._connected = False


class SerialIntegrationTest(unittest.TestCase):
    def test_full_serial_flow_with_voltage_in_battery_field(self) -> None:
        incoming = [
            json.dumps(
                {
                    "type": "hello",
                    "firmware": "roki-operating",
                    "version": "2.1.0",
                    "protocol": 1,
                    "sequence": 1,
                    "commandTimeoutMs": 400,
                    "telemetryIntervalMs": 100,
                }
            ),
            json.dumps(
                {"type": "ack", "command": "STOP", "sequence": 0}
            ),
            json.dumps(
                {
                    "type": "ack",
                    "command": "ENCODER_ZERO",
                    "sequence": 2,
                }
            ),
            json.dumps(
                {
                    "type": "hardwareStatus",
                    "battery": 11.82,
                    "motor": "NORMAL",
                    "lineSensor": "NORMAL",
                    "lineValues": [0, 0, 1, 0, 0],
                }
            ),
            json.dumps(
                {
                    "type": "odometry",
                    "seq": 1042,
                    "uptimeMs": 523010,
                    "leftTicks": 18240,
                    "rightTicks": 18192,
                }
            ),
            json.dumps(
                {
                    "type": "odometry",
                    "seq": 1043,
                    "uptimeMs": 523110,
                    "leftTicks": 18241,
                    "rightTicks": 18193,
                }
            ),
            json.dumps(
                {
                    "type": "odometry",
                    "seq": 1044,
                    "uptimeMs": 523210,
                    "leftTicks": 18242,
                    "rightTicks": 18194,
                }
            ),
        ]
        bridge = MockSerialBridge(incoming)
        protocol = ProtocolSettings()
        mission = MissionController(protocol.steering_center_deg)
        mission.submit(MissionCommand(speed=30, steering_deg=80))
        store = RobotStateStore()
        runtime = RobotRuntime(
            bridge=bridge,
            protocol_settings=protocol,
            mission=mission,
            motion=MotionController(
                MotionControllerSettings(
                    wheel_diameter_m=0.065,
                    encoder_ticks_per_revolution=100,
                    speed_min=10,
                    speed_max=255,
                    speed_ramp_per_update=10,
                    straight_correction_kp_deg_per_tick=0.5,
                    maximum_straight_correction_deg=5,
                    steering_center_deg=80,
                    steering_min_deg=60,
                    steering_max_deg=100,
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
            settings=RuntimeSettings(disconnected_poll_sec=0.0),
        )

        received_odometry = 0

        def stop_after_odometry(_odometry: object, _state: object) -> None:
            nonlocal received_odometry
            received_odometry += 1
            if received_odometry == 3:
                runtime.request_stop()

        runtime.add_odometry_listener(stop_after_odometry)
        runtime.run_forever()

        snapshot = store.snapshot()
        self.assertEqual(snapshot.odometry.seq, 1044)  # type: ignore[union-attr]
        self.assertEqual(
            snapshot.hardware_status.battery_percent,  # type: ignore[union-attr]
            11.82,
        )
        self.assertEqual(
            snapshot.hardware_status.line_values,  # type: ignore[union-attr]
            (0, 0, 1, 0, 0),
        )
        self.assertIsNotNone(snapshot.motion_state)
        self.assertNotEqual(
            snapshot.safety_decision.fault,  # type: ignore[union-attr]
            "LOW_BATTERY",
        )

        written_types = [message["type"] for message in bridge.written]
        self.assertEqual(
            written_types[:4],
            ["stop", "hello", "encoder_zero", "status"],
        )
        self.assertIn("control", written_types)
        self.assertGreaterEqual(written_types.count("stop"), 2)
        control = next(
            message
            for message in bridge.written
            if message["type"] == "control"
        )
        self.assertEqual(control["speed"], 10)
        self.assertEqual(control["steering"], 80)


if __name__ == "__main__":
    unittest.main()
