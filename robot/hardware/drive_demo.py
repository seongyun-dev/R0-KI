#!/usr/bin/env python3
"""Keyboard-controlled straight-line rear-wheel demonstration.

This intentionally does not command the steering servo.  W and S latch a
low-speed direction; SPACE/X stop; Q exits.  The ESP32 requires a heartbeat
every 400 ms and stops locally if this process or the USB connection fails.
"""

from __future__ import annotations

import argparse
import json
import select
import signal
import sys
import time

import serial

from hw_test import Esp32Client, SafetyError, find_port, require_confirmation


MIN_BATTERY_VOLTAGE = 9.0
MAX_BATTERY_VOLTAGE = 12.8
HEARTBEAT_SECONDS = 0.15
STATUS_SECONDS = 1.0
REVERSAL_STOP_SECONDS = 0.35


def parse_status(lines: list[str]) -> dict[str, object] | None:
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "status":
            return payload
    return None


def require_live_drive_bus(client: Esp32Client) -> float:
    payload = parse_status(client.request("STATUS", duration=0.12, echo=False))
    if payload is None:
        raise SafetyError("ESP32 STATUS response is missing")
    voltage = float(payload.get("batteryVoltage", 0.0))
    if not MIN_BATTERY_VOLTAGE <= voltage <= MAX_BATTERY_VOLTAGE:
        raise SafetyError(
            "Battery B voltage is outside the allowed demo range: "
            f"{voltage:.2f} V"
        )
    return voltage


def send_stop(client: Esp32Client) -> None:
    client.send("DRIVE STOP")
    client.drain(0.1, echo=False)


def start_direction(
    client: Esp32Client,
    direction: str,
    speed: int,
    previous_direction: str | None,
) -> str:
    if previous_direction is not None and previous_direction != direction:
        send_stop(client)
        time.sleep(REVERSAL_STOP_SECONDS)
    if previous_direction != direction:
        client.request("ARM MOTORS", duration=0.15, echo=False)
    client.send(f"DRIVE {direction} {speed}")
    client.drain(0.1, echo=False)
    return direction


def run_teleop(client: Esp32Client, speed: int) -> None:
    import termios
    import tty

    version = client.require_safe_firmware()
    try:
        version_tuple = tuple(int(part) for part in version.split("."))
    except ValueError as error:
        raise SafetyError(f"invalid firmware version: {version}") from error
    if version_tuple < (1, 2, 0):
        raise SafetyError(
            "drive demo requires ESP32 firmware 1.2.0 or newer"
        )
    client.request("ESTOP", duration=0.2, echo=False)
    voltage = require_live_drive_bus(client)

    print(f"Battery B: {voltage:.2f} V")
    print("W=forward  S=reverse  SPACE/X=stop  Q=stop and quit")
    print("Steering servo is not used. Robot starts stopped.")

    old_terminal = termios.tcgetattr(sys.stdin.fileno())
    direction: str | None = None
    next_heartbeat = time.monotonic()
    next_status = time.monotonic() + STATUS_SECONDS

    try:
        tty.setcbreak(sys.stdin.fileno())
        while True:
            now = time.monotonic()
            timeout = max(0.0, min(0.05, next_heartbeat - now))
            readable, _, _ = select.select([sys.stdin], [], [], timeout)
            if readable:
                key = sys.stdin.read(1).lower()
                if key == "":
                    break
                if key == "w":
                    direction = start_direction(
                        client, "F", speed, direction
                    )
                    print("\rFORWARD ", end="", flush=True)
                elif key == "s":
                    direction = start_direction(
                        client, "R", speed, direction
                    )
                    print("\rREVERSE ", end="", flush=True)
                elif key in {" ", "x"}:
                    send_stop(client)
                    direction = None
                    print("\rSTOP    ", end="", flush=True)
                elif key == "q" or key == "\x03":
                    break

            now = time.monotonic()
            if direction is not None and now >= next_heartbeat:
                client.send(f"DRIVE {direction} {speed}")
                client.drain(0.02, echo=False)
                next_heartbeat = now + HEARTBEAT_SECONDS

            if now >= next_status:
                voltage = require_live_drive_bus(client)
                next_status = now + STATUS_SECONDS
    finally:
        termios.tcsetattr(
            sys.stdin.fileno(),
            termios.TCSADRAIN,
            old_terminal,
        )
        try:
            client.request("ESTOP", duration=0.2, echo=False)
        except (OSError, serial.SerialException):
            pass
        print("\nESTOP sent; demo ended.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RO-KI straight-line rear-wheel demo",
    )
    parser.add_argument("--port", help="explicit serial device path")
    parser.add_argument("--speed", type=int, default=15)
    parser.add_argument("--confirm")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        require_confirmation(args.confirm, "AREA_CLEAR")
        if not 10 <= args.speed <= 20:
            raise SafetyError("demo speed must be between 10 and 20 percent")
        if not sys.stdin.isatty():
            raise SafetyError("interactive terminal is required")

        port = find_port(args.port)
        print(f"ESP32_PORT={port}")
        with Esp32Client(port, timeout=0.03) as client:
            run_teleop(client, args.speed)
        return 0
    except (SafetyError, serial.SerialException, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


def handle_sigterm(*_: object) -> None:
    raise SystemExit(143)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_sigterm)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, handle_sigterm)
    raise SystemExit(main())
