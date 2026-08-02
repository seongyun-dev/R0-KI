#!/usr/bin/env python3
"""No-movement validation for the RO-KI ESP32 operating JSON protocol."""

from __future__ import annotations

import json
import time
from pathlib import Path

import serial


PORT = Path(
    "/dev/serial/by-id/"
    "usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"
)
EXPECTED_FIRMWARE_VERSION = "2.2.0"


def send(port: serial.Serial, payload: dict[str, object]) -> None:
    message = json.dumps(payload, separators=(",", ":")) + "\n"
    port.write(message.encode("ascii"))
    port.flush()


def main() -> int:
    if not PORT.exists():
        raise SystemExit(f"ERROR: ESP32 serial path is missing: {PORT}")

    seen = {
        "stopAck": False,
        "hello": False,
        "encoderAck": False,
        "statusAck": False,
        "odometry": False,
        "hardwareStatus": False,
    }

    with serial.Serial(
        str(PORT),
        115200,
        timeout=0.1,
        exclusive=True,
    ) as port:
        time.sleep(2.0)
        port.reset_input_buffer()
        port.readline()

        commands = (
            {"type": "stop", "sequence": 0},
            {"type": "hello", "protocol": 1, "sequence": 1},
            {"type": "encoder_zero", "sequence": 2},
            {"type": "status", "sequence": 3},
        )
        for command in commands:
            send(port, command)
            time.sleep(0.05)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not all(seen.values()):
            raw = port.readline()
            if not raw:
                continue
            try:
                payload = json.loads(raw.decode("utf-8", errors="strict"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue

            message_type = payload.get("type")
            if message_type == "ack":
                key = (payload.get("command"), payload.get("sequence"))
                if key == ("STOP", 0):
                    seen["stopAck"] = True
                elif key == ("ENCODER_ZERO", 2):
                    seen["encoderAck"] = True
                elif key == ("STATUS", 3):
                    seen["statusAck"] = True
            elif message_type == "hello":
                seen["hello"] = (
                    payload.get("protocol") == 1
                    and payload.get("version") == EXPECTED_FIRMWARE_VERSION
                    and payload.get("sequence") == 1
                )
            elif message_type == "odometry":
                seen["odometry"] = all(
                    isinstance(payload.get(field), int)
                    for field in ("seq", "uptimeMs", "leftTicks", "rightTicks")
                )
            elif message_type == "hardwareStatus":
                battery = payload.get("battery")
                seen["hardwareStatus"] = (
                    isinstance(battery, (int, float))
                    and not isinstance(battery, bool)
                    and 0.0 <= float(battery) <= 100.0
                    and payload.get("motor") in {
                        "NORMAL",
                        "FAULT",
                        "DISCONNECTED",
                    }
                    and payload.get("lineSensor") in {
                        "NORMAL",
                        "FAULT",
                        "DISCONNECTED",
                    }
                )

        # STOP is accepted regardless of sequence state and is the final action.
        send(port, {"type": "stop", "sequence": 4})

    missing = [name for name, ok in seen.items() if not ok]
    if missing:
        print(json.dumps(seen, separators=(",", ":")))
        print("OPERATING_PREFLIGHT_FAIL missing=" + ",".join(missing))
        return 2

    print(json.dumps(seen, separators=(",", ":")))
    print("OPERATING_PREFLIGHT_PASS_NO_MOVEMENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
