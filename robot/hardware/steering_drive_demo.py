#!/usr/bin/env python3
"""Safe keyboard demo for steering and short rear-wheel drive bursts.

The installed ESP32 safe firmware stops the motors whenever a SERVO command is
received.  This client therefore uses a stop-steer-drive sequence:

1. stop the rear wheels,
2. set and settle the steering servo,
3. arm the rear motors,
4. drive for a short, bounded interval while refreshing the motor watchdog.

The robot always starts stopped.  SPACE/X and every exit path send ESTOP.
"""

from __future__ import annotations

import argparse
import json
import select
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import serial

from drive_demo import (
    HEARTBEAT_SECONDS,
    REVERSAL_STOP_SECONDS,
    require_live_drive_bus,
)
from hw_test import Esp32Client, SafetyError, find_port, require_confirmation


CENTER_ANGLE = 80
LOW_ANGLE = 75
HIGH_ANGLE = 85
STATUS_SECONDS = 0.8
SERVO_SETTLE_SECONDS = 0.45
MIN_BURST_SECONDS = 0.5
MAX_BURST_SECONDS = 2.0
MIN_FIRMWARE_VERSION = (1, 2, 0)


def append_log(path: Path, event: str, **fields: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "time": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


def find_payload(lines: list[str], payload_type: str) -> dict[str, object] | None:
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == payload_type:
            return payload
    return None


def require_pca9685(client: Esp32Client) -> None:
    payload = find_payload(
        client.request("PCA_STATUS", duration=0.3, echo=False),
        "pcaStatus",
    )
    if payload is None or payload.get("ok") is not True:
        raise SafetyError("PCA9685 CH0 status check failed")


def send_estop(client: Esp32Client) -> None:
    client.send("ESTOP")
    client.drain(0.12, echo=False)


def set_steering(client: Esp32Client, angle: int) -> None:
    """Set CH0 steering while stopped and verify the ESP32 response."""
    send_estop(client)
    client.request("ARM SERVO", duration=0.15, echo=False)
    response = client.request(f"SERVO {angle}", duration=0.25, echo=False)
    payload = find_payload(response, "servo")
    if payload is None or int(payload.get("angle", -1)) != angle:
        raise SafetyError(f"steering command was not accepted: {response}")
    time.sleep(SERVO_SETTLE_SECONDS)


def start_drive(client: Esp32Client, direction: str, speed: int) -> None:
    client.request("ARM MOTORS", duration=0.15, echo=False)
    response = client.request(
        f"DRIVE {direction} {speed}",
        duration=0.12,
        echo=False,
    )
    payload = find_payload(response, "drive")
    if payload is None or payload.get("direction") != direction:
        raise SafetyError(f"drive command was not accepted: {response}")


def stop_drive(client: Esp32Client) -> None:
    client.send("DRIVE STOP")
    client.drain(0.1, echo=False)


def run_demo(
    client: Esp32Client,
    speed: int,
    burst_seconds: float,
    log_path: Path,
) -> None:
    import termios
    import tty

    version = client.require_safe_firmware()
    try:
        version_tuple = tuple(int(part) for part in version.split("."))
    except ValueError as error:
        raise SafetyError(f"invalid firmware version: {version}") from error
    if version_tuple < MIN_FIRMWARE_VERSION:
        raise SafetyError("steering demo requires firmware 1.2.0 or newer")

    send_estop(client)
    voltage = require_live_drive_bus(client)
    require_pca9685(client)

    print(f"Battery B: {voltage:.2f} V")
    print("A=75deg  C=80deg(center)  D=85deg")
    print("W=forward burst  S=reverse burst  SPACE/X=ESTOP  Q=quit")
    print(
        f"Each drive command auto-stops after {burst_seconds:.1f}s. "
        "Changing steering stops the wheels first."
    )
    print("Robot starts stopped.")
    append_log(
        log_path,
        "demo_ready",
        firmware=version,
        batteryVoltage=round(voltage, 2),
        speedPercent=speed,
        burstSeconds=burst_seconds,
    )

    old_terminal = termios.tcgetattr(sys.stdin.fileno())
    steering_angle = CENTER_ANGLE
    direction: str | None = None
    drive_deadline: float | None = None
    next_heartbeat = time.monotonic()
    next_status = time.monotonic() + STATUS_SECONDS

    try:
        tty.setcbreak(sys.stdin.fileno())
        while True:
            now = time.monotonic()
            deadlines = [now + 0.05]
            if direction is not None:
                deadlines.append(next_heartbeat)
                if drive_deadline is not None:
                    deadlines.append(drive_deadline)
            timeout = max(0.0, min(deadlines) - now)
            readable, _, _ = select.select([sys.stdin], [], [], timeout)

            if readable:
                key = sys.stdin.read(1).lower()
                if key in {"q", "\x03"}:
                    break
                if key in {" ", "x"}:
                    send_estop(client)
                    direction = None
                    drive_deadline = None
                    append_log(log_path, "estop", source="keyboard")
                    print("\rESTOP                         ", end="", flush=True)
                    continue
                if key in {"a", "c", "d"}:
                    angle_by_key = {
                        "a": LOW_ANGLE,
                        "c": CENTER_ANGLE,
                        "d": HIGH_ANGLE,
                    }
                    steering_angle = angle_by_key[key]
                    set_steering(client, steering_angle)
                    direction = None
                    drive_deadline = None
                    append_log(
                        log_path,
                        "steering",
                        angle=steering_angle,
                    )
                    print(
                        f"\rSTEERING={steering_angle}deg             ",
                        end="",
                        flush=True,
                    )
                    continue
                if key in {"w", "s"}:
                    requested_direction = "F" if key == "w" else "R"
                    if direction is not None:
                        stop_drive(client)
                        direction = None
                        time.sleep(REVERSAL_STOP_SECONDS)

                    # Refresh the servo position immediately before every
                    # drive burst.  The firmware holds it for up to 3 seconds.
                    set_steering(client, steering_angle)
                    start_drive(client, requested_direction, speed)
                    direction = requested_direction
                    now = time.monotonic()
                    drive_deadline = now + burst_seconds
                    next_heartbeat = now + HEARTBEAT_SECONDS
                    append_log(
                        log_path,
                        "drive_started",
                        direction=direction,
                        speedPercent=speed,
                        steeringAngle=steering_angle,
                        maxSeconds=burst_seconds,
                    )
                    label = "FORWARD" if direction == "F" else "REVERSE"
                    print(
                        f"\r{label} steering={steering_angle}deg       ",
                        end="",
                        flush=True,
                    )

            now = time.monotonic()
            if (
                direction is not None
                and drive_deadline is not None
                and now >= drive_deadline
            ):
                completed_direction = direction
                stop_drive(client)
                direction = None
                drive_deadline = None
                append_log(
                    log_path,
                    "drive_completed",
                    direction=completed_direction,
                    result="AUTO_STOP",
                )
                print("\rAUTO_STOP / READY             ", end="", flush=True)
                continue

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
            send_estop(client)
        except (OSError, serial.SerialException):
            pass
        append_log(log_path, "demo_completed", result="ESTOP")
        print(f"\nESTOP sent; demo ended. Log: {log_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RO-KI steering and bounded rear-wheel drive demo",
    )
    parser.add_argument("--port", help="explicit serial device path")
    parser.add_argument("--speed", type=int, default=15)
    parser.add_argument("--burst-seconds", type=float, default=1.5)
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("logs/steering_drive_demo.jsonl"),
    )
    parser.add_argument("--confirm")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        require_confirmation(args.confirm, "AREA_CLEAR")
        if not 10 <= args.speed <= 20:
            raise SafetyError("demo speed must be between 10 and 20 percent")
        if not MIN_BURST_SECONDS <= args.burst_seconds <= MAX_BURST_SECONDS:
            raise SafetyError(
                "burst duration must be between "
                f"{MIN_BURST_SECONDS:.1f} and {MAX_BURST_SECONDS:.1f} seconds"
            )
        if not sys.stdin.isatty():
            raise SafetyError("interactive terminal is required")

        port = find_port(args.port)
        print(f"ESP32_PORT={port}")
        with Esp32Client(port, timeout=0.03) as client:
            run_demo(
                client,
                speed=args.speed,
                burst_seconds=args.burst_seconds,
                log_path=args.log_file,
            )
        return 0
    except (SafetyError, serial.SerialException, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


def handle_sigterm(*_: object) -> None:
    raise SystemExit(143)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_sigterm)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, handle_sigterm)
    raise SystemExit(main())
