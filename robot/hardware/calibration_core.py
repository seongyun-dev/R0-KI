"""Pure summary helpers for RO-KI field calibration telemetry."""

from __future__ import annotations

import json
import re
from collections import Counter
from statistics import fmean
from typing import Any, Iterable


LINE_DEBUG_PATTERN = re.compile(
    r"^\s*S1\s*:\s*([01])\s+S2\s*:\s*([01])\s+"
    r"S3\s*:\s*([01])\s+S4\s*:\s*([01])\s+S5\s*:\s*([01])\s*$"
)


def parse_telemetry_line(raw: bytes | str) -> dict[str, Any] | None:
    """Decode operating JSON or the preserved line-debug text format."""

    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return None
    else:
        text = raw
    stripped = text.strip()
    if not stripped:
        return None

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        match = LINE_DEBUG_PATTERN.fullmatch(stripped)
        if match is None:
            return None
        return {
            "type": "hardwareStatus",
            "source": "line-debug-text",
            "lineValues": [int(value) for value in match.groups()],
        }
    return payload if isinstance(payload, dict) else None


def _payloads(
    records: Iterable[dict[str, Any]],
    message_type: str,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for record in records:
        payload = record.get("payload", record)
        if isinstance(payload, dict) and payload.get("type") == message_type:
            payloads.append(payload)
    return payloads


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize line, encoder and battery evidence without assumptions."""

    hardware = _payloads(records, "hardwareStatus")
    odometry = _payloads(records, "odometry")
    errors = _payloads(records, "error")

    valid_lines = [
        tuple(int(value) for value in payload["lineValues"])
        for payload in hardware
        if isinstance(payload.get("lineValues"), list)
        and len(payload["lineValues"]) == 5
        and all(value in (0, 1) for value in payload["lineValues"])
    ]
    patterns = Counter("".join(str(value) for value in line) for line in valid_lines)
    channels: list[dict[str, int]] = []
    for index in range(5):
        values = [line[index] for line in valid_lines]
        channels.append(
            {
                "index": index,
                "zeroCount": values.count(0),
                "oneCount": values.count(1),
                "transitionCount": sum(
                    current != previous
                    for previous, current in zip(values, values[1:])
                ),
            }
        )

    encoder_summary: dict[str, Any] = {"sampleCount": len(odometry)}
    if odometry:
        left_values = [int(payload["leftTicks"]) for payload in odometry]
        right_values = [int(payload["rightTicks"]) for payload in odometry]
        encoder_summary.update(
            {
                "leftStart": left_values[0],
                "leftEnd": left_values[-1],
                "leftDelta": left_values[-1] - left_values[0],
                "leftMin": min(left_values),
                "leftMax": max(left_values),
                "rightStart": right_values[0],
                "rightEnd": right_values[-1],
                "rightDelta": right_values[-1] - right_values[0],
                "rightMin": min(right_values),
                "rightMax": max(right_values),
            }
        )

    voltages = [
        float(payload["batteryVoltage"])
        for payload in hardware
        if isinstance(payload.get("batteryVoltage"), (int, float))
        and not isinstance(payload.get("batteryVoltage"), bool)
    ]
    battery_summary: dict[str, Any] = {"sampleCount": len(voltages)}
    if voltages:
        battery_summary.update(
            {
                "minimumVoltage": min(voltages),
                "maximumVoltage": max(voltages),
                "averageVoltage": fmean(voltages),
            }
        )

    return {
        "recordCount": len(records),
        "line": {
            "sampleCount": len(valid_lines),
            "patterns": dict(patterns.most_common()),
            "channels": channels,
        },
        "encoder": encoder_summary,
        "battery": battery_summary,
        "errors": errors,
    }


def ticks_per_revolution(delta_ticks: int, revolutions: float) -> float:
    if revolutions <= 0:
        raise ValueError("revolutions must be positive")
    return abs(delta_ticks) / revolutions
