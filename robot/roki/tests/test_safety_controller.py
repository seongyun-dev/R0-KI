from __future__ import annotations

import unittest

from safety.safety_controller import SafetyController, SafetySettings
from serial_comm.protocol import (
    HardwareStatus,
    LineSensorStatus,
    MotorStatus,
)


def hardware_status(
    battery: float = 82.5,
    motor: MotorStatus = MotorStatus.NORMAL,
    line_sensor: LineSensorStatus = LineSensorStatus.NORMAL,
) -> HardwareStatus:
    return HardwareStatus(
        battery_percent=battery,
        motor=motor,
        line_sensor=line_sensor,
    )


class SafetyControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.safety = SafetyController(
            SafetySettings(
                odometry_timeout_sec=0.3,
                hardware_status_timeout_sec=1.0,
                low_battery_percent=20.0,
            )
        )
        self.safety.record_odometry(10.0)
        self.safety.record_hardware_status(10.0)

    def evaluate(
        self,
        *,
        now: float = 10.1,
        status: HardwareStatus | None = None,
        connected: bool = True,
        emergency_stop: bool = False,
    ):
        return self.safety.evaluate(
            now=now,
            connected=connected,
            hardware_status=status or hardware_status(),
            emergency_stop=emergency_stop,
        )

    def test_allows_normal_hardware_with_live_messages(self) -> None:
        self.assertEqual(self.evaluate().fault, "NONE")
        self.assertTrue(self.evaluate().allowed)

    def test_tracks_receive_times_independently(self) -> None:
        self.safety.record_odometry(11.0)
        self.assertEqual(self.safety.last_odometry_time, 11.0)
        self.assertEqual(self.safety.last_hardware_status_time, 10.0)
        self.safety.record_hardware_status(12.0)
        self.assertEqual(self.safety.last_odometry_time, 11.0)
        self.assertEqual(self.safety.last_hardware_status_time, 12.0)

    def test_odometry_not_ready_and_timeout_are_distinct(self) -> None:
        self.safety.reset_connection()
        not_ready = self.evaluate(now=20.0)
        self.assertEqual(not_ready.fault, "ODOMETRY_NOT_READY")
        self.safety.record_odometry(20.0)
        self.safety.record_hardware_status(20.4)
        timeout = self.evaluate(now=20.31)
        self.assertEqual(timeout.fault, "ODOMETRY_TIMEOUT")

    def test_hardware_status_not_ready_and_timeout_are_distinct(self) -> None:
        self.safety.reset_connection()
        self.safety.record_odometry(20.0)
        not_ready = self.evaluate(now=20.1)
        self.assertEqual(not_ready.fault, "HARDWARE_STATUS_NOT_READY")
        self.safety.record_hardware_status(20.0)
        self.safety.record_odometry(21.1)
        timeout = self.evaluate(now=21.01)
        self.assertEqual(timeout.fault, "HARDWARE_STATUS_TIMEOUT")

    def test_motor_states(self) -> None:
        self.assertEqual(
            self.evaluate(
                status=hardware_status(motor=MotorStatus.FAULT)
            ).fault,
            "MOTOR_FAULT",
        )
        self.assertEqual(
            self.evaluate(
                status=hardware_status(motor=MotorStatus.DISCONNECTED)
            ).fault,
            "MOTOR_DISCONNECTED",
        )

    def test_line_sensor_states(self) -> None:
        self.assertEqual(
            self.evaluate(
                status=hardware_status(line_sensor=LineSensorStatus.FAULT)
            ).fault,
            "LINE_SENSOR_FAULT",
        )
        self.assertEqual(
            self.evaluate(
                status=hardware_status(
                    line_sensor=LineSensorStatus.DISCONNECTED
                )
            ).fault,
            "LINE_SENSOR_DISCONNECTED",
        )

    def test_low_battery_uses_hardware_status_percent(self) -> None:
        self.assertEqual(
            self.evaluate(status=hardware_status(battery=19.9)).fault,
            "LOW_BATTERY",
        )
        self.assertTrue(
            self.evaluate(status=hardware_status(battery=20.0)).allowed
        )

    def test_calibrated_policy_rejects_missing_battery_percent(self) -> None:
        status = HardwareStatus(
            battery_percent=None,
            battery_voltage=11.82,
            motor=MotorStatus.NORMAL,
            line_sensor=LineSensorStatus.NORMAL,
        )

        self.assertEqual(
            self.evaluate(status=status).fault,
            "BATTERY_PERCENT_UNAVAILABLE",
        )

    def test_disconnected_emergency_stop_and_latched_fault(self) -> None:
        self.assertEqual(
            self.evaluate(connected=False).fault,
            "SERIAL_DISCONNECTED",
        )
        self.assertEqual(
            self.evaluate(emergency_stop=True).fault,
            "EMERGENCY_STOP",
        )
        self.safety.latch("MANUAL_FAULT")
        self.assertEqual(self.evaluate().fault, "MANUAL_FAULT")
        self.safety.clear_latched_fault()
        self.assertTrue(self.evaluate().allowed)

    def test_invalid_settings_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SafetySettings(0.0, 1.0, None)
        with self.assertRaises(ValueError):
            SafetySettings(0.3, 0.0, None)
        with self.assertRaises(ValueError):
            SafetySettings(0.3, 1.0, 101.0)


if __name__ == "__main__":
    unittest.main()
