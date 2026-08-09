#!/usr/bin/env python3
"""Bounded low-speed line-following field test for the operating firmware.

This is a diagnostic entrypoint, not the production Robot service. It must be
the only serial owner. Every non-following decision sends STOP immediately and
the finalizer sends STOP again before closing the port.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import serial

from esp32_port import Esp32PortError, resolve_esp32_port


def _add_roki_import_path() -> None:
    candidates = (
        Path(__file__).resolve().parents[1] / "roki",
        Path.home() / "roki",
    )
    for candidate in candidates:
        if (candidate / "control" / "line_follower.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    raise SystemExit("ERROR: RO-KI line_follower.py was not found")


_add_roki_import_path()

from control.line_follower import (  # noqa: E402
    LineFollower,
    LineFollowerSettings,
    LineFollowMode,
)


SUPPORTED_FIRMWARE_VERSIONS = {"2.2.0", "3.0.0"}
MIN_BATTERY_VOLTAGE = 9.0
MAX_BATTERY_VOLTAGE = 13.0
CONTROL_INTERVAL_SEC = 0.1
TELEMETRY_TIMEOUT_SEC = 0.35


class FieldTestError(RuntimeError):
    """Raised when a safety or protocol condition fails."""


class OperatingClient:
    def __init__(self, port_name: str) -> None:
        self.port_name = port_name
        self.port: serial.Serial | None = None
        self.sequence = 0

    def __enter__(self) -> "OperatingClient":
        connection = serial.Serial(
            port=None,
            baudrate=115200,
            timeout=0.02,
            exclusive=True,
        )
        connection.dtr = False
        connection.rts = False
        connection.port = self.port_name
        connection.open()
        self.port = connection
        time.sleep(1.5)
        connection.reset_input_buffer()
        return self

    def __exit__(self, *_: object) -> None:
        if self.port is None:
            return
        try:
            if self.port.is_open:
                for _ in range(3):
                    self.send("stop")
                    time.sleep(0.03)
        finally:
            self.port.close()
            self.port = None

    def send(self, message_type: str, **fields: Any) -> None:
        if self.port is None or not self.port.is_open:
            raise FieldTestError("serial port is not open")
        message = {
            "type": message_type,
            **fields,
            "sequence": self.sequence,
        }
        self.sequence += 1
        self.port.write(
            (json.dumps(message, separators=(",", ":")) + "\n").encode(
                "ascii"
            )
        )
        self.port.flush()

    def read(self) -> dict[str, Any] | None:
        if self.port is None:
            raise FieldTestError("serial port is not open")
        raw = self.port.readline()
        if not raw:
            return None
        try:
            payload = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def mandatory_handshake(self) -> dict[str, Any]:
        self.send("stop")
        self.send("hello", protocol=1)
        self.send("encoder_zero")
        self.send("status")
        seen = {
            "hello": False,
            "encoder": False,
            "odometry": False,
            "hardware": False,
        }
        latest_hardware: dict[str, Any] | None = None
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and not all(seen.values()):
            payload = self.read()
            if payload is None:
                continue
            message_type = payload.get("type")
            if message_type == "hello":
                seen["hello"] = (
                    payload.get("firmware") == "roki-operating"
                    and payload.get("version") in SUPPORTED_FIRMWARE_VERSIONS
                    and payload.get("protocol") == 1
                )
            elif message_type == "ack":
                if str(payload.get("command", "")).upper() == "ENCODER_ZERO":
                    seen["encoder"] = True
            elif message_type == "odometry":
                seen["odometry"] = all(
                    isinstance(payload.get(field), int)
                    and not isinstance(payload.get(field), bool)
                    for field in ("uptimeMs", "leftTicks", "rightTicks")
                )
            elif message_type == "hardwareStatus":
                self.validate_hardware(payload)
                latest_hardware = payload
                seen["hardware"] = True
        missing = [name for name, present in seen.items() if not present]
        if missing or latest_hardware is None:
            raise FieldTestError(
                "operating handshake incomplete: " + ",".join(missing)
            )
        return latest_hardware

    def fresh_operating_sample(self) -> dict[str, Any]:
        """Discard countdown backlog and wait for fresh status and odometry."""

        if self.port is None:
            raise FieldTestError("serial port is not open")
        self.port.reset_input_buffer()
        self.send("status")
        latest_hardware: dict[str, Any] | None = None
        odometry_seen = False
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            payload = self.read()
            if payload is None:
                continue
            message_type = payload.get("type")
            if message_type == "error":
                raise FieldTestError(f"ESP32 fault: {payload.get('fault')}")
            if message_type == "odometry":
                odometry_seen = all(
                    isinstance(payload.get(field), int)
                    and not isinstance(payload.get(field), bool)
                    for field in ("uptimeMs", "leftTicks", "rightTicks")
                )
            elif message_type == "hardwareStatus":
                self.validate_hardware(payload)
                latest_hardware = payload
            if odometry_seen and latest_hardware is not None:
                return latest_hardware
        raise FieldTestError("fresh hardwareStatus/odometry was not received")

    @staticmethod
    def validate_hardware(payload: dict[str, Any]) -> tuple[int, ...]:
        if payload.get("motor") != "NORMAL":
            raise FieldTestError(f"motor state is not NORMAL: {payload.get('motor')}")
        if payload.get("lineSensor") != "NORMAL":
            raise FieldTestError(
                f"line sensor state is not NORMAL: {payload.get('lineSensor')}"
            )
        voltage = payload.get("batteryVoltage")
        if (
            isinstance(voltage, bool)
            or not isinstance(voltage, (int, float))
            or not MIN_BATTERY_VOLTAGE <= float(voltage) <= MAX_BATTERY_VOLTAGE
        ):
            raise FieldTestError(
                "Battery B voltage is outside the field-test range: "
                f"{voltage} V"
            )
        line_values = payload.get("lineValues")
        if (
            not isinstance(line_values, list)
            or len(line_values) != 5
            or any(
                isinstance(value, bool) or value not in (0, 1)
                for value in line_values
            )
        ):
            raise FieldTestError(f"invalid lineValues: {line_values}")
        return tuple(line_values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bounded RO-KI low-speed line-following field test"
    )
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--port")
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--speed", type=int, default=45)
    parser.add_argument("--steering-sign", type=int, choices=(-1, 1), default=1)
    parser.add_argument("--kp", type=float, default=10.0)
    parser.add_argument("--kd", type=float, default=1.0)
    parser.add_argument(
        "--destination-min-black",
        type=int,
        default=0,
        help="0 disables destination detection for the first track test",
    )
    parser.add_argument("--destination-frames", type=int, default=3)
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("logs/line-follow/field-test.jsonl"),
    )
    return parser.parse_args()


def append_log(target: Any, event: str, **fields: Any) -> None:
    payload = {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    target.write(json.dumps(payload, ensure_ascii=False) + "\n")
    target.flush()


def main() -> int:
    args = parse_args()
    if args.confirm != "LINE_COURSE_CLEAR":
        raise SystemExit(
            "ERROR: use --confirm LINE_COURSE_CLEAR only after placing the "
            "robot on the line and clearing the floor course"
        )
    if not 3.0 <= args.seconds <= 30.0:
        raise SystemExit("ERROR: seconds must be 3..30")
    if not 45 <= args.speed <= 51:
        raise SystemExit("ERROR: speed must be 45..51")
    if not 0 <= args.destination_min_black <= 5:
        raise SystemExit("ERROR: destination-min-black must be 0..5")
    if not 2 <= args.destination_frames <= 10:
        raise SystemExit("ERROR: destination-frames must be 2..10")
    try:
        port_name = resolve_esp32_port(args.port)
    except Esp32PortError as error:
        raise SystemExit(f"ERROR: {error}") from error

    follower = LineFollower(
        LineFollowerSettings(
            drive_speed_pwm=args.speed,
            steering_sign=args.steering_sign,
            kp_deg_per_error=args.kp,
            kd_deg_per_error_delta=args.kd,
            destination_min_black_sensors=args.destination_min_black,
            destination_confirm_frames=args.destination_frames,
        )
    )
    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"ESP32_PORT={port_name}")
    print(f"LOG_FILE={args.log_file.resolve()}")
    print("Test limits: PWM 45..51, steering 60..100, maximum 30 seconds")

    try:
        with args.log_file.open("a", encoding="utf-8") as log_target:
            with OperatingClient(port_name) as client:
                handshake_hardware = client.mandatory_handshake()
                handshake_values = client.validate_hardware(handshake_hardware)
                initial = follower.update(handshake_values)
                if initial.mode is not LineFollowMode.FOLLOWING:
                    raise FieldTestError(
                        "the robot is not on a usable line at startup: "
                        f"{list(handshake_values)}"
                    )
                follower.reset()

                for remaining in (3, 2, 1):
                    client.send("stop")
                    print(f"Starting in {remaining}...")
                    time.sleep(1.0)

                latest_hardware = client.fresh_operating_sample()
                initial_values = client.validate_hardware(latest_hardware)
                initial = follower.update(initial_values)
                if initial.mode is not LineFollowMode.FOLLOWING:
                    raise FieldTestError(
                        "the line disappeared during the countdown: "
                        f"{list(initial_values)}"
                    )
                follower.reset()
                append_log(
                    log_target,
                    "preflight",
                    lineValues=list(initial_values),
                    batteryVoltage=latest_hardware.get("batteryVoltage"),
                )

                started = time.monotonic()
                last_hardware_at = started
                last_odometry_at = started
                next_control_at = started
                latest_decision = follower.update(initial_values)
                terminal_reason = "TIME_LIMIT"

                while time.monotonic() - started < args.seconds:
                    now = time.monotonic()
                    payload = client.read()
                    if payload is not None:
                        message_type = payload.get("type")
                        if message_type == "error":
                            raise FieldTestError(
                                f"ESP32 fault: {payload.get('fault')}"
                            )
                        if message_type == "odometry":
                            last_odometry_at = now
                            append_log(
                                log_target,
                                "odometry",
                                payload=payload,
                            )
                        elif message_type == "hardwareStatus":
                            values = client.validate_hardware(payload)
                            last_hardware_at = now
                            latest_decision = follower.update(values)
                            append_log(
                                log_target,
                                "decision",
                                lineValues=list(values),
                                mode=latest_decision.mode.value,
                                speed=latest_decision.speed_pwm,
                                steering=latest_decision.steering_deg,
                                error=latest_decision.error,
                                batteryVoltage=payload.get("batteryVoltage"),
                            )
                            print(
                                f"line={list(values)} "
                                f"mode={latest_decision.mode.value} "
                                f"speed={latest_decision.speed_pwm} "
                                f"steering={latest_decision.steering_deg}"
                            )
                            if latest_decision.mode in {
                                LineFollowMode.LINE_LOST,
                                LineFollowMode.DESTINATION,
                            }:
                                terminal_reason = latest_decision.mode.value
                                client.send("stop")
                                break

                    if now - last_hardware_at > TELEMETRY_TIMEOUT_SEC:
                        raise FieldTestError("hardwareStatus telemetry timeout")
                    if now - last_odometry_at > TELEMETRY_TIMEOUT_SEC:
                        raise FieldTestError("odometry telemetry timeout")
                    if now >= next_control_at:
                        if latest_decision.mode is LineFollowMode.FOLLOWING:
                            client.send(
                                "control",
                                speed=latest_decision.speed_pwm,
                                steering=latest_decision.steering_deg,
                            )
                        else:
                            client.send("stop")
                        next_control_at = now + CONTROL_INTERVAL_SEC

                client.send("stop")
                append_log(log_target, "stopped", reason=terminal_reason)
                print(f"FIELD_TEST_STOPPED reason={terminal_reason}")
        return 0
    except (FieldTestError, serial.SerialException, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
