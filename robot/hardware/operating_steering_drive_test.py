#!/usr/bin/env python3
"""Short, bounded motor + steering test using the operating JSON protocol."""

from __future__ import annotations

import argparse
import json
import time

import serial

from esp32_port import Esp32PortError, resolve_esp32_port

MAX_TEST_SPEED_PWM = 51
MIN_ANGLE = 60
MAX_ANGLE = 100
SUPPORTED_FIRMWARE_VERSIONS = {"2.2.0", "3.0.0"}


def send(port: serial.Serial, payload: dict[str, object]) -> None:
    port.write(
        (json.dumps(payload, separators=(",", ":")) + "\n").encode("ascii")
    )
    port.flush()


def read_messages(
    port: serial.Serial,
    *,
    duration: float,
) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        raw = port.readline()
        if not raw:
            continue
        try:
            payload = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            messages.append(payload)
    return messages


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="explicit ESP32 serial device path")
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--speed", type=int, default=51)
    parser.add_argument("--segment-ms", type=int, default=600)
    parser.add_argument(
        "--angles",
        default="80,85,80,75,80",
        help="comma-separated absolute servo angles",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expected_confirmation = (
        "STEERING_CLEAR" if args.speed == 0 else "DRIVE_AREA_CLEAR"
    )
    if args.confirm != expected_confirmation:
        raise SystemExit(
            f"ERROR: use --confirm {expected_confirmation} only after "
            "clearing the steering linkage and test area."
        )
    if not 0 <= args.speed <= MAX_TEST_SPEED_PWM:
        raise SystemExit(f"ERROR: speed must be 0..{MAX_TEST_SPEED_PWM}")
    if not 200 <= args.segment_ms <= 1000:
        raise SystemExit("ERROR: segment-ms must be 200..1000")

    try:
        angles = [int(value.strip()) for value in args.angles.split(",")]
    except ValueError as error:
        raise SystemExit("ERROR: angles must be comma-separated integers") from error
    if not angles or len(angles) > 6:
        raise SystemExit("ERROR: provide 1..6 steering angles")
    if any(not MIN_ANGLE <= angle <= MAX_ANGLE for angle in angles):
        raise SystemExit(f"ERROR: every angle must be {MIN_ANGLE}..{MAX_ANGLE}")
    if args.segment_ms * len(angles) > 5000:
        raise SystemExit("ERROR: total powered test time must not exceed 5 seconds")
    try:
        port_name = resolve_esp32_port(args.port)
    except Esp32PortError as error:
        raise SystemExit(f"ERROR: {error}") from error
    print(f"ESP32_PORT={port_name}")

    sequence = 0
    with serial.Serial(
        port_name,
        115200,
        timeout=0.03,
        exclusive=True,
    ) as port:
        time.sleep(2.0)
        port.reset_input_buffer()
        read_messages(port, duration=0.2)
        try:
            send(port, {"type": "stop", "sequence": sequence})
            sequence += 1
            send(
                port,
                {"type": "hello", "protocol": 1, "sequence": sequence},
            )
            sequence += 1
            send(port, {"type": "encoder_zero", "sequence": sequence})
            sequence += 1
            send(port, {"type": "status", "sequence": sequence})
            sequence += 1

            preflight = read_messages(port, duration=1.0)
            hello_ok = any(
                message.get("type") == "hello"
                and message.get("firmware") == "roki-operating"
                and message.get("protocol") == 1
                and message.get("version") in SUPPORTED_FIRMWARE_VERSIONS
                for message in preflight
            )
            batteries = [
                float(message["battery"])
                for message in preflight
                if message.get("type") == "hardwareStatus"
                and isinstance(message.get("battery"), (int, float))
            ]
            if not hello_ok:
                raise RuntimeError("supported operating firmware handshake failed")
            if not batteries or max(batteries) <= 0.0:
                raise RuntimeError(
                    "Battery B is not detected; refusing a movement command"
                )

            heartbeat_interval = 0.1
            if args.speed == 0:
                print("STEERING_ONLY: motor PWM remains zero")
            for angle in angles:
                print(f"CONTROL speed={args.speed} steering={angle}")
                segment_deadline = (
                    time.monotonic() + args.segment_ms / 1000.0
                )
                while time.monotonic() < segment_deadline:
                    send(
                        port,
                        {
                            "type": "control",
                            "speed": args.speed,
                            "steering": angle,
                            "sequence": sequence,
                        },
                    )
                    sequence += 1
                    messages = read_messages(
                        port,
                        duration=heartbeat_interval,
                    )
                    faults = [
                        message.get("fault")
                        for message in messages
                        if message.get("type") == "error"
                    ]
                    if faults:
                        raise RuntimeError(f"ESP32 fault: {faults[-1]}")
        finally:
            # STOP is always accepted by firmware, even after a sequence error.
            send(port, {"type": "stop", "sequence": sequence})
            read_messages(port, duration=0.2)

    print("OPERATING_STEERING_DRIVE_TEST_COMPLETE_AND_STOPPED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
