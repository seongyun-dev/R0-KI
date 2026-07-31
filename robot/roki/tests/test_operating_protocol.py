from __future__ import annotations

import json
import unittest

from serial_comm.protocol import (
    HardwareStatus,
    LineSensorStatus,
    MessageType,
    MotorStatus,
    Odometry,
    ProtocolSettings,
    SequenceCounter,
    build_control_command,
    build_encoder_zero_command,
    build_hello_command,
    build_status_command,
    build_stop_command,
    parse_hardware_status,
    parse_message,
    parse_odometry,
)


class OperatingProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = ProtocolSettings()

    def test_control_and_serial_control_messages_are_preserved(self) -> None:
        self.assertEqual(
            json.loads(build_control_command(-20, 80, 4, self.settings)),
            {"type": "control", "speed": -20, "steering": 80, "sequence": 4},
        )
        self.assertEqual(
            json.loads(build_stop_command(5)),
            {"type": "stop", "sequence": 5},
        )
        self.assertEqual(json.loads(build_status_command(6))["type"], "status")
        self.assertEqual(
            json.loads(build_encoder_zero_command(7))["type"],
            "encoder_zero",
        )
        self.assertEqual(json.loads(build_hello_command(8))["protocol"], 1)

    def test_control_rejects_invalid_values(self) -> None:
        invalid_commands = (
            (-256, 80, 0),
            (256, 80, 0),
            (0, 59, 0),
            (0, 101, 0),
        )
        for values in invalid_commands:
            with self.assertRaises(ValueError):
                build_control_command(*values, self.settings)

    def test_odometry_contract(self) -> None:
        payload = {
            "type": "odometry",
            "seq": 1042,
            "uptimeMs": 523010,
            "leftTicks": 18240,
            "rightTicks": 18192,
        }
        message = parse_message(json.dumps(payload), self.settings)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIs(message.message_type, MessageType.ODOMETRY)
        self.assertEqual(
            parse_odometry(message.payload),
            Odometry(1042, 523010, 18240, 18192),
        )

    def test_hardware_status_contract_and_enums(self) -> None:
        payload = {
            "type": "hardwareStatus",
            "battery": 82.5,
            "motor": "NORMAL",
            "lineSensor": "DISCONNECTED",
        }
        message = parse_message(json.dumps(payload), self.settings)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIs(message.message_type, MessageType.HARDWARE_STATUS)
        self.assertEqual(
            parse_hardware_status(message.payload),
            HardwareStatus(
                battery_percent=82.5,
                motor=MotorStatus.NORMAL,
                line_sensor=LineSensorStatus.DISCONNECTED,
            ),
        )

    def test_hardware_status_preserves_five_raw_line_channels(self) -> None:
        payload = {
            "type": "hardwareStatus",
            "battery": 11.82,
            "motor": "NORMAL",
            "lineSensor": "NORMAL",
            "lineValues": [0, 0, 1, 0, 0],
        }

        status = parse_hardware_status(payload)

        self.assertEqual(status.line_values, (0, 0, 1, 0, 0))

    def test_hardware_status_rejects_invalid_raw_line_channels(self) -> None:
        invalid_values = (
            [0, 1, 0, 1],
            [0, 1, 0, 1, 0, 1],
            [0, 1, 2, 1, 0],
            [0, 1, True, 1, 0],
            "00100",
        )
        for line_values in invalid_values:
            with self.subTest(line_values=line_values):
                with self.assertRaises(ValueError):
                    parse_hardware_status(
                        {
                            "battery": 11.82,
                            "motor": "NORMAL",
                            "lineSensor": "NORMAL",
                            "lineValues": line_values,
                        }
                    )

    def test_all_hardware_status_enum_values(self) -> None:
        for motor in MotorStatus:
            for line_sensor in LineSensorStatus:
                status = parse_hardware_status(
                    {
                        "battery": 50,
                        "motor": motor.value,
                        "lineSensor": line_sensor.value,
                    }
                )
                self.assertIs(status.motor, motor)
                self.assertIs(status.line_sensor, line_sensor)

    def test_invalid_contract_messages_are_rejected(self) -> None:
        invalid_payloads = (
            "not-json",
            json.dumps({"type": "odometry"}),
            json.dumps(
                {
                    "type": "odometry",
                    "seq": 1,
                    "uptimeMs": 2,
                    "leftTicks": True,
                    "rightTicks": 4,
                }
            ),
            json.dumps(
                {
                    "type": "hardwareStatus",
                    "battery": 101,
                    "motor": "NORMAL",
                    "lineSensor": "NORMAL",
                }
            ),
            json.dumps(
                {
                    "type": "hardwareStatus",
                    "battery": 50,
                    "motor": "UNKNOWN",
                    "lineSensor": "NORMAL",
                }
            ),
        )
        for raw_message in invalid_payloads:
            self.assertIsNone(parse_message(raw_message, self.settings))

    def test_hello_ack_and_error_are_preserved(self) -> None:
        messages = (
            (
                {
                    "type": "hello",
                    "firmware": "roki-operating",
                    "protocol": 1,
                    "sequence": 1,
                },
                MessageType.HELLO,
            ),
            (
                {"type": "ack", "command": "STOP", "sequence": 2},
                MessageType.ACK,
            ),
            (
                {"type": "error", "fault": "INVALID_CONTROL", "sequence": 3},
                MessageType.ERROR,
            ),
        )
        for payload, expected_type in messages:
            message = parse_message(json.dumps(payload), self.settings)
            self.assertIsNotNone(message)
            assert message is not None
            self.assertIs(message.message_type, expected_type)

    def test_accepts_all_firmware_error_faults(self) -> None:
        firmware_faults = (
            "INVALID_CONTROL",
            "STALE_SEQUENCE",
            "SERVO_WRITE_FAILED",
            "INVALID_HELLO",
            "INVALID_COMMAND",
            "INVALID_DRIVE_COMMAND",
            "STOP_BEFORE_DIRECTION_CHANGE",
            "DRIVE_NOT_ARMED",
            "MOTOR_NOT_ARMED",
            "INVALID_MOTOR_PULSE",
            "SERVO_NOT_ARMED",
            "INVALID_SERVO_ANGLE",
            "PCA9685_NOT_FOUND",
            "PCA9685_WRITE_FAILED",
            "UNKNOWN_COMMAND",
            "COMMAND_TIMEOUT",
            "COMMAND_TOO_LONG",
        )
        for fault in firmware_faults:
            with self.subTest(fault=fault):
                message = parse_message(
                    json.dumps({"type": "error", "fault": fault}),
                    self.settings,
                )
                self.assertIsNotNone(message)
                assert message is not None
                self.assertEqual(message.payload["fault"], fault)

    def test_error_requires_fault_and_rejects_legacy_code(self) -> None:
        self.assertIsNone(
            parse_message(
                json.dumps({"type": "error", "code": "COMMAND_TIMEOUT"}),
                self.settings,
            )
        )
        self.assertIsNone(
            parse_message(json.dumps({"type": "error"}), self.settings)
        )

    def test_sequence_counter(self) -> None:
        counter = SequenceCounter()
        self.assertEqual([counter.next(), counter.next()], [0, 1])


if __name__ == "__main__":
    unittest.main()
