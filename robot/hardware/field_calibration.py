#!/usr/bin/env python3
"""No-movement capture tool for line sensors, encoders and battery telemetry.

This tool never sends CONTROL, DRIVE, MOTOR, ARM MOTORS or SERVO commands.
It opens the ESP32 exclusively, sends STOP first, and sends STOP again on exit.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import serial

from calibration_core import (
    parse_telemetry_line,
    summarize_records,
    ticks_per_revolution,
)
from esp32_port import Esp32PortError, resolve_esp32_port


EXPECTED_FIRMWARE = "roki-operating"
SUPPORTED_VERSIONS = frozenset({"2.2.0", "3.0.0"})
LINE_SCENARIOS = (
    ("floor", "Remove all black tape from below all five sensors."),
    ("physical_leftmost", "Put black tape below only the physical leftmost sensor."),
    ("physical_left", "Put black tape below only the second sensor from the left."),
    ("physical_center", "Put black tape below only the center sensor."),
    ("physical_right", "Put black tape below only the second sensor from the right."),
    ("physical_rightmost", "Put black tape below only the physical rightmost sensor."),
    ("normal_centered_line", "Center the intended route tape below the sensor board."),
    ("wide_destination_marker", "Put a wide transverse black marker below all sensors."),
)


class CalibrationError(RuntimeError):
    """Raised when a passive capture safety/contract check fails."""


def find_port(explicit_port: str | None) -> str:
    try:
        return resolve_esp32_port(explicit_port)
    except Esp32PortError as error:
        raise CalibrationError(str(error)) from error


def safe_label(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return normalized.strip("-.") or "capture"


class PassiveEsp32Session:
    def __init__(self, port: str, *, require_operating: bool = False) -> None:
        self._port_name = port
        self._port: serial.Serial | None = None
        self._sequence = 0
        self._require_operating = require_operating
        self.protocol: str | None = None

    def __enter__(self) -> "PassiveEsp32Session":
        connection = serial.Serial(
            port=None,
            baudrate=115200,
            timeout=0.1,
            exclusive=True,
        )
        connection.dtr = False
        connection.rts = False
        connection.port = self._port_name
        connection.open()
        self._port = connection
        try:
            time.sleep(1.5)
            connection.reset_input_buffer()
            self.send("stop")
            self.send("hello", protocol=1)
            self.send("status")
            handshake = self.capture(
                3.0,
                scenario="handshake",
                echo_changes=False,
            )
            hello_messages = [
                record["payload"]
                for record in handshake
                if record["payload"].get("type") == "hello"
            ]
            operating = any(
                payload.get("firmware") == EXPECTED_FIRMWARE
                and payload.get("version") in SUPPORTED_VERSIONS
                and payload.get("protocol") == 1
                for payload in hello_messages
            )
            line_debug = any(
                record["payload"].get("source") == "line-debug-text"
                for record in handshake
            )
            if operating:
                self.protocol = "operating-json"
            elif line_debug:
                self.protocol = "line-debug-text"
            else:
                raise CalibrationError(
                    "Neither a supported operating firmware nor the preserved "
                    "line-debug telemetry was detected; movement remains stopped."
                )
            if self._require_operating and not operating:
                raise CalibrationError(
                    "This command needs operating firmware 2.2.0 or 3.0.0. "
                    "The ESP32 is "
                    "currently running line-debug firmware, so encoder capture "
                    "is unavailable."
                )
            return self
        except Exception:
            connection.close()
            self._port = None
            raise

    def __exit__(self, *_: object) -> None:
        if self._port is not None and self._port.is_open:
            try:
                self.send("stop")
                self._port.flush()
                time.sleep(0.1)
            finally:
                self._port.close()
        self._port = None

    def send(self, message_type: str, **fields: Any) -> None:
        if self._port is None or not self._port.is_open:
            raise CalibrationError("serial port is not open")
        payload = {
            "type": message_type,
            **fields,
            "sequence": self._sequence,
        }
        self._sequence += 1
        encoded = json.dumps(payload, separators=(",", ":")) + "\n"
        self._port.write(encoded.encode("ascii"))
        self._port.flush()

    def zero_encoders(self) -> None:
        self.send("encoder_zero")
        self.send("status")
        time.sleep(0.2)

    def capture(
        self,
        seconds: float,
        *,
        scenario: str,
        echo_changes: bool = True,
    ) -> list[dict[str, Any]]:
        if self._port is None:
            raise CalibrationError("serial port is not open")
        records: list[dict[str, Any]] = []
        last_line: tuple[int, ...] | None = None
        deadline = time.monotonic() + seconds
        started = time.monotonic()
        while time.monotonic() < deadline:
            raw = self._port.readline()
            if not raw:
                continue
            payload = parse_telemetry_line(raw)
            if payload is None:
                continue
            record = {
                "capturedAt": datetime.now(timezone.utc).isoformat(),
                "elapsedSec": round(time.monotonic() - started, 6),
                "scenario": scenario,
                "payload": payload,
            }
            records.append(record)
            line_values = payload.get("lineValues")
            if (
                echo_changes
                and isinstance(line_values, list)
                and len(line_values) == 5
            ):
                line = tuple(int(value) for value in line_values)
                if line != last_line:
                    print(f"LINE scenario={scenario} values={list(line)}", flush=True)
                    last_line = line
        return records


def write_capture(
    records: list[dict[str, Any]],
    *,
    output_dir: Path,
    label: str,
) -> tuple[Path, Path, dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"{timestamp}-{safe_label(label)}"
    jsonl_path = output_dir / f"{stem}.jsonl"
    summary_path = output_dir / f"{stem}-summary.json"
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as target:
        for record in records:
            target.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            target.write("\n")
    summary = summarize_records(records)
    scenarios = sorted(
        {
            str(record.get("scenario"))
            for record in records
            if record.get("scenario") is not None
        }
    )
    summary["scenarios"] = {
        scenario: summarize_records(
            [record for record in records if record.get("scenario") == scenario]
        )
        for scenario in scenarios
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return jsonl_path, summary_path, summary


def run_passive(args: argparse.Namespace) -> int:
    with PassiveEsp32Session(find_port(args.port)) as session:
        print(f"DETECTED_PROTOCOL={session.protocol}")
        records = session.capture(args.seconds, scenario=args.label)
    paths = write_capture(records, output_dir=args.output_dir, label=args.label)
    print(json.dumps(paths[2], ensure_ascii=False, indent=2))
    print(f"RAW_LOG={paths[0]}")
    print(f"SUMMARY={paths[1]}")
    return 0


def run_line_session(args: argparse.Namespace) -> int:
    records: list[dict[str, Any]] = []
    print("Battery B must be disconnected. This session never commands movement.")
    with PassiveEsp32Session(find_port(args.port)) as session:
        print(f"DETECTED_PROTOCOL={session.protocol}")
        for label, instruction in LINE_SCENARIOS:
            input(
                f"\n[{label}] {instruction}\n"
                "Position the tape first, hold it still, then press Enter: "
            )
            if args.settle_seconds:
                print(
                    f"Settling for {args.settle_seconds:g}s; do not move the tape.",
                    flush=True,
                )
                time.sleep(args.settle_seconds)
            sample = session.capture(args.seconds_per_step, scenario=label)
            records.extend(sample)
            summary = summarize_records(sample)
            print("PATTERNS=" + json.dumps(summary["line"]["patterns"]))
    paths = write_capture(records, output_dir=args.output_dir, label="line-session")
    print(f"RAW_LOG={paths[0]}")
    print(f"SUMMARY={paths[1]}")
    return 0


def run_encoder_manual(args: argparse.Namespace) -> int:
    print("Battery B must be disconnected and both rear wheels must be off the ground.")
    print(
        f"Rotate only the {args.side} wheel {args.revolutions:g} full turns "
        "in the robot's forward direction during capture."
    )
    with PassiveEsp32Session(
        find_port(args.port),
        require_operating=True,
    ) as session:
        session.zero_encoders()
        for remaining in range(args.countdown, 0, -1):
            print(f"Starting in {remaining}...", flush=True)
            time.sleep(1.0)
        records = session.capture(
            args.seconds,
            scenario=f"encoder-{args.side}-forward",
            echo_changes=False,
        )
    paths = write_capture(
        records,
        output_dir=args.output_dir,
        label=f"encoder-{args.side}-forward",
    )
    encoder = paths[2]["encoder"]
    delta_key = "leftDelta" if args.side == "left" else "rightDelta"
    other_key = "rightDelta" if args.side == "left" else "leftDelta"
    if delta_key not in encoder:
        raise CalibrationError("No encoder samples were captured")
    result = {
        "side": args.side,
        "direction": "forward",
        "revolutions": args.revolutions,
        "deltaTicks": encoder[delta_key],
        "otherWheelDeltaTicks": encoder.get(other_key),
        "ticksPerWheelRevolution": ticks_per_revolution(
            int(encoder[delta_key]), args.revolutions
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"RAW_LOG={paths[0]}")
    print(f"SUMMARY={paths[1]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RO-KI no-movement field calibration capture",
    )
    parser.add_argument("--port", help="explicit ESP32 serial by-id path")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "logs" / "field-calibration",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    passive = commands.add_parser("passive")
    passive.add_argument("--label", required=True)
    passive.add_argument("--seconds", type=float, default=5.0)
    passive.set_defaults(handler=run_passive)

    line = commands.add_parser("line-session")
    line.add_argument("--seconds-per-step", type=float, default=2.0)
    line.add_argument("--settle-seconds", type=float, default=1.5)
    line.set_defaults(handler=run_line_session)

    encoder = commands.add_parser("encoder-manual")
    encoder.add_argument("--side", choices=("left", "right"), required=True)
    encoder.add_argument("--revolutions", type=float, default=10.0)
    encoder.add_argument("--seconds", type=float, default=15.0)
    encoder.add_argument("--countdown", type=int, default=5)
    encoder.set_defaults(handler=run_encoder_manual)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if getattr(args, "seconds", 1.0) <= 0:
        raise SystemExit("seconds must be positive")
    if getattr(args, "seconds_per_step", 1.0) <= 0:
        raise SystemExit("seconds-per-step must be positive")
    if getattr(args, "settle_seconds", 0.0) < 0:
        raise SystemExit("settle-seconds must not be negative")
    try:
        return int(args.handler(args))
    except (CalibrationError, serial.SerialException) as error:
        print(f"ERROR: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
