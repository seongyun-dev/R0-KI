#!/usr/bin/env python3
"""Safe, explicit bench-test client for the RO-KI ESP32 firmware."""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from dataclasses import dataclass

import serial


DEFAULT_PORT_GLOB = (
    "/dev/serial/by-id/"
    "usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_*-if00-port0"
)
SAFE_FIRMWARE_NAME = "roki-safe-hw-test"


class SafetyError(RuntimeError):
    """Raised when a movement safety precondition is not satisfied."""


@dataclass
class Esp32Client:
    port: str
    baudrate: int = 115200
    timeout: float = 0.2

    def __post_init__(self) -> None:
        self.serial: serial.Serial | None = None

    def __enter__(self) -> "Esp32Client":
        connection = serial.Serial(
            port=None,
            baudrate=self.baudrate,
            timeout=self.timeout,
        )
        connection.dtr = False
        connection.rts = False
        connection.port = self.port
        connection.open()
        self.serial = connection
        time.sleep(1.2)
        self.drain(0.5)
        return self

    def __exit__(self, *_: object) -> None:
        if self.serial is not None and self.serial.is_open:
            try:
                self.send("ESTOP")
                self.drain(0.2)
            finally:
                self.serial.close()
        self.serial = None

    def send(self, command: str) -> None:
        if self.serial is None or not self.serial.is_open:
            raise RuntimeError("serial port is not open")
        self.serial.write((command.rstrip() + "\n").encode("ascii"))
        self.serial.flush()

    def drain(self, duration: float, echo: bool = False) -> list[str]:
        if self.serial is None:
            return []
        lines: list[str] = []
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            raw = self.serial.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            lines.append(line)
            if echo:
                print(line)
        return lines

    def request(
        self,
        command: str,
        duration: float = 0.8,
        echo: bool = True,
    ) -> list[str]:
        self.send(command)
        return self.drain(duration, echo=echo)

    def require_safe_firmware(self) -> str:
        lines = self.request("PING", duration=1.0, echo=False)
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("firmware") == SAFE_FIRMWARE_NAME:
                version = str(payload.get("version", "unknown"))
                print(
                    "SAFE_FIRMWARE_OK "
                    f"version={version}"
                )
                return version
        raise SafetyError(
            "Safe firmware handshake failed; refusing any movement command."
        )


def find_port(explicit_port: str | None) -> str:
    if explicit_port:
        return explicit_port
    matches = sorted(glob.glob(DEFAULT_PORT_GLOB))
    if len(matches) != 1:
        raise SafetyError(
            "Expected exactly one CP2102 ESP32 device, "
            f"found {len(matches)}: {matches}"
        )
    return matches[0]


def require_confirmation(actual: str | None, expected: str) -> None:
    if actual != expected:
        raise SafetyError(
            f"Refusing movement: pass --confirm {expected} exactly."
        )


def run_preflight(client: Esp32Client) -> None:
    client.require_safe_firmware()
    client.request("ESTOP")
    client.request("STATUS")
    client.request("I2C_SCAN")
    print("PREFLIGHT_COMPLETE_NO_MOVEMENT")


def run_monitor(client: Esp32Client, seconds: float) -> None:
    client.require_safe_firmware()
    client.request("ESTOP")
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        client.request("STATUS", duration=0.4)
        time.sleep(0.1)


def run_motor_test(
    client: Esp32Client,
    side: str,
    channel: str,
    speed: int,
    duration_ms: int,
    confirmation: str | None,
) -> None:
    require_confirmation(confirmation, "WHEELS_OFF_GROUND")
    if not 1 <= speed <= 25:
        raise SafetyError("speed must be between 1 and 25 percent")
    if not 50 <= duration_ms <= 500:
        raise SafetyError("duration must be between 50 and 500 ms")

    client.require_safe_firmware()
    client.request("ESTOP")
    client.request("ENCODER_ZERO")
    client.request("ARM MOTORS")
    client.request(
        f"MOTOR {side} {channel} {speed} {duration_ms}",
        duration=(duration_ms / 1000.0) + 1.0,
    )
    client.request("STATUS")
    client.request("ESTOP")
    print("MOTOR_TEST_COMPLETE_AND_DISARMED")


def run_right_wheel_cycle(
    client: Esp32Client,
    speed: int,
    duration_ms: int,
    pause_ms: int,
) -> None:
    """Pulse only the right wheel in both directions in one serial session."""
    if not 1 <= speed <= 20:
        raise SafetyError("right-wheel speed must be between 1 and 20 percent")
    if not 50 <= duration_ms <= 400:
        raise SafetyError("right-wheel pulse must be between 50 and 400 ms")
    if not 500 <= pause_ms <= 3000:
        raise SafetyError("right-wheel pause must be between 500 and 3000 ms")

    client.require_safe_firmware()
    client.request("ESTOP")

    for label, channel in (("DIRECTION_A", "A"), ("DIRECTION_B", "B")):
        print(f"===== RIGHT_WHEEL_{label} =====")
        client.request("ENCODER_ZERO")
        client.request("ARM MOTORS")
        client.request(
            f"MOTOR R {channel} {speed} {duration_ms}",
            duration=(duration_ms / 1000.0) + 1.0,
        )
        client.request("STATUS")
        client.request("ESTOP")
        if channel == "A":
            time.sleep(pause_ms / 1000.0)

    print("RIGHT_WHEEL_FORWARD_REVERSE_TEST_COMPLETE_AND_DISARMED")
    client.request("ESTOP")


def run_rear_wheels_test(
    client: Esp32Client,
    speed: int,
    duration_ms: int,
    pause_ms: int,
) -> None:
    """Test both rear wheels independently in both directions."""
    if not 1 <= speed <= 20:
        raise SafetyError("rear-wheels speed must be between 1 and 20 percent")
    if not 50 <= duration_ms <= 400:
        raise SafetyError("rear-wheels pulse must be between 50 and 400 ms")
    if not 500 <= pause_ms <= 3000:
        raise SafetyError("rear-wheels pause must be between 500 and 3000 ms")

    client.require_safe_firmware()
    client.request("ESTOP")

    sequence = (
        ("LEFT_DIRECTION_A", "L", "A"),
        ("LEFT_DIRECTION_B", "L", "B"),
        ("RIGHT_DIRECTION_A", "R", "A"),
        ("RIGHT_DIRECTION_B", "R", "B"),
    )
    for index, (label, side, channel) in enumerate(sequence):
        print(f"===== REAR_WHEELS_{label} =====")
        client.request("ENCODER_ZERO")
        client.request("ARM MOTORS")
        client.request(
            f"MOTOR {side} {channel} {speed} {duration_ms}",
            duration=(duration_ms / 1000.0) + 1.0,
        )
        client.request("STATUS")
        client.request("ESTOP")
        if index + 1 < len(sequence):
            time.sleep(pause_ms / 1000.0)

    print("REAR_WHEELS_INDEPENDENT_TEST_COMPLETE_AND_DISARMED")
    client.request("ESTOP")


def run_servo_test(
    client: Esp32Client,
    angle: int,
    confirmation: str | None,
) -> None:
    require_confirmation(confirmation, "LINKAGE_CLEAR")
    if not 60 <= angle <= 100:
        raise SafetyError("servo test is limited to 60..100 degrees")

    client.require_safe_firmware()
    client.request("ESTOP")
    client.request("PCA_STATUS")
    client.request("ARM SERVO")
    client.request(f"SERVO {angle}", duration=1.2)
    client.request("PCA_STATUS")
    client.request("SERVO_OFF")
    client.request("PCA_STATUS")
    print("SERVO_TEST_COMPLETE_AND_OUTPUT_OFF")


def run_servo_sweep(client: Esp32Client) -> None:
    """Calibrate CH0 around the observed 80-degree steering center."""
    client.require_safe_firmware()
    client.request("ESTOP")
    client.request("PCA_STATUS")

    for angle in (80, 85, 90, 95, 100, 80, 75, 70, 65, 80):
        print(f"===== SERVO_CH0_{angle}_DEGREES =====")
        client.request("ARM SERVO")
        client.request(f"SERVO {angle}", duration=1.2)
        client.request("PCA_STATUS")
        client.request("SERVO_OFF")
        time.sleep(0.5)

    client.request("PCA_STATUS")
    client.request("ESTOP")
    print("SERVO_CH0_SWEEP_COMPLETE_AND_OUTPUT_OFF")


def run_servo_mini_test(
    client: Esp32Client,
    confirmation: str | None,
) -> None:
    """Test small steering movements around the observed 80-degree center."""
    require_confirmation(confirmation, "LINKAGE_CLEAR")
    client.require_safe_firmware()
    client.request("ESTOP", duration=0.2)

    status_lines = client.request("STATUS", duration=0.3, echo=False)
    battery_voltage: float | None = None
    for line in reversed(status_lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "status":
            battery_voltage = float(payload.get("batteryVoltage", 0.0))
            break
    if battery_voltage is None:
        raise SafetyError("ESP32 STATUS response is missing")
    if not 9.0 <= battery_voltage <= 12.8:
        raise SafetyError(
            "Battery B voltage is outside the servo-test range: "
            f"{battery_voltage:.2f} V"
        )
    print(f"BATTERY_B_OK voltage={battery_voltage:.2f}V")

    pca_lines = client.request("PCA_STATUS", duration=0.3, echo=False)
    pca_ok = False
    for line in reversed(pca_lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "pcaStatus":
            pca_ok = payload.get("ok") is True
            break
    if not pca_ok:
        raise SafetyError("PCA9685 CH0 status check failed")
    print("PCA9685_OK address=0x60 channel=0")

    sequence = (
        (80, "CENTER"),
        (85, "PLUS_5"),
        (80, "CENTER"),
        (75, "MINUS_5"),
        (80, "CENTER"),
    )
    for angle, label in sequence:
        print(f"===== SERVO_{label}_{angle}_DEGREES =====")
        client.request("ARM SERVO", duration=0.15)
        client.request(f"SERVO {angle}", duration=0.2)
        time.sleep(1.0)
        client.request("SERVO_OFF", duration=0.15)
        time.sleep(0.6)

    client.request("ESTOP", duration=0.2)
    print("SERVO_MINI_TEST_COMPLETE_CENTERED_AND_OUTPUT_OFF")


def run_servo_low_test(
    client: Esp32Client,
    confirmation: str | None,
) -> None:
    """Exercise only the lower side of the 80-degree steering center."""
    require_confirmation(confirmation, "LINKAGE_CLEAR")
    client.require_safe_firmware()
    client.request("ESTOP", duration=0.2)

    status_lines = client.request("STATUS", duration=0.3, echo=False)
    battery_voltage: float | None = None
    for line in reversed(status_lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "status":
            battery_voltage = float(payload.get("batteryVoltage", 0.0))
            break
    if battery_voltage is None:
        raise SafetyError("ESP32 STATUS response is missing")
    if not 9.0 <= battery_voltage <= 12.8:
        raise SafetyError(
            "Battery B voltage is outside the servo-test range: "
            f"{battery_voltage:.2f} V"
        )
    print(f"BATTERY_B_OK voltage={battery_voltage:.2f}V")

    pca_lines = client.request("PCA_STATUS", duration=0.3, echo=False)
    pca_ok = False
    for line in reversed(pca_lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "pcaStatus":
            pca_ok = payload.get("ok") is True
            break
    if not pca_ok:
        raise SafetyError("PCA9685 CH0 status check failed")
    print("PCA9685_OK address=0x60 channel=0")

    sequence = (
        (80, "CENTER"),
        (75, "MINUS_5"),
        (70, "MINUS_10"),
        (65, "MINUS_15"),
        (70, "RETURN_70"),
        (75, "RETURN_75"),
        (80, "CENTER"),
    )
    for angle, label in sequence:
        print(f"===== SERVO_{label}_{angle}_DEGREES =====")
        client.request("ARM SERVO", duration=0.15)
        client.request(f"SERVO {angle}", duration=0.2)
        time.sleep(1.0)
        client.request("SERVO_OFF", duration=0.15)
        time.sleep(0.6)

    client.request("ESTOP", duration=0.2)
    print("SERVO_LOW_TEST_COMPLETE_CENTERED_AND_OUTPUT_OFF")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RO-KI safe ESP32 hardware bench tests",
    )
    parser.add_argument("--port", help="explicit serial device path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("preflight")

    monitor_parser = subparsers.add_parser("monitor")
    monitor_parser.add_argument("--seconds", type=float, default=10.0)

    motor_parser = subparsers.add_parser("motor")
    motor_parser.add_argument("--side", choices=["L", "R", "BOTH"], required=True)
    motor_parser.add_argument("--channel", choices=["A", "B"], required=True)
    motor_parser.add_argument("--speed", type=int, default=15)
    motor_parser.add_argument("--ms", type=int, default=250)
    motor_parser.add_argument("--confirm")

    right_wheel_parser = subparsers.add_parser("right-wheel")
    right_wheel_parser.add_argument("--speed", type=int, default=20)
    right_wheel_parser.add_argument("--ms", type=int, default=400)
    right_wheel_parser.add_argument("--pause-ms", type=int, default=1000)

    rear_wheels_parser = subparsers.add_parser("rear-wheels")
    rear_wheels_parser.add_argument("--speed", type=int, default=20)
    rear_wheels_parser.add_argument("--ms", type=int, default=400)
    rear_wheels_parser.add_argument("--pause-ms", type=int, default=1000)

    servo_parser = subparsers.add_parser("servo")
    servo_parser.add_argument("--angle", type=int, default=100)
    servo_parser.add_argument("--confirm")

    subparsers.add_parser("servo-sweep")

    servo_mini_parser = subparsers.add_parser("servo-mini")
    servo_mini_parser.add_argument("--confirm")

    servo_low_parser = subparsers.add_parser("servo-low")
    servo_low_parser.add_argument("--confirm")

    subparsers.add_parser("estop")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        port = find_port(args.port)
        print(f"ESP32_PORT={port}")
        with Esp32Client(port) as client:
            if args.command == "preflight":
                run_preflight(client)
            elif args.command == "monitor":
                run_monitor(client, max(0.5, args.seconds))
            elif args.command == "motor":
                run_motor_test(
                    client,
                    side=args.side,
                    channel=args.channel,
                    speed=args.speed,
                    duration_ms=args.ms,
                    confirmation=args.confirm,
                )
            elif args.command == "right-wheel":
                run_right_wheel_cycle(
                    client,
                    speed=args.speed,
                    duration_ms=args.ms,
                    pause_ms=args.pause_ms,
                )
            elif args.command == "rear-wheels":
                run_rear_wheels_test(
                    client,
                    speed=args.speed,
                    duration_ms=args.ms,
                    pause_ms=args.pause_ms,
                )
            elif args.command == "servo":
                run_servo_test(
                    client,
                    angle=args.angle,
                    confirmation=args.confirm,
                )
            elif args.command == "servo-sweep":
                run_servo_sweep(client)
            elif args.command == "servo-mini":
                run_servo_mini_test(
                    client,
                    confirmation=args.confirm,
                )
            elif args.command == "servo-low":
                run_servo_low_test(
                    client,
                    confirmation=args.confirm,
                )
            elif args.command == "estop":
                client.require_safe_firmware()
                client.request("ESTOP")
                print("ESTOP_SENT")
        return 0
    except (SafetyError, serial.SerialException, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
