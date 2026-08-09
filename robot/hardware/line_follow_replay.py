#!/usr/bin/env python3
"""Replay field-calibration JSONL through the line follower without hardware."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


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
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="No-movement line-following JSONL replay"
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--scenario")
    parser.add_argument("--speed", type=int, default=45)
    parser.add_argument("--steering-sign", type=int, choices=(-1, 1), default=1)
    parser.add_argument("--kp", type=float, default=5.0)
    parser.add_argument("--kd", type=float, default=1.0)
    parser.add_argument("--destination-min-black", type=int, default=4)
    parser.add_argument("--show-decisions", action="store_true")
    return parser.parse_args()


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise SystemExit(f"ERROR: replay file does not exist: {path}")
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise SystemExit(
                f"ERROR: invalid JSON at {path}:{line_number}: {error}"
            ) from error
        if isinstance(value, dict):
            records.append(value)
    return records


def main() -> int:
    args = parse_args()
    settings = LineFollowerSettings(
        drive_speed_pwm=args.speed,
        steering_sign=args.steering_sign,
        kp_deg_per_error=args.kp,
        kd_deg_per_error_delta=args.kd,
        destination_min_black_sensors=args.destination_min_black,
    )
    follower = LineFollower(settings)
    records = read_records(args.path)
    summaries: dict[str, dict[str, Any]] = {}
    current_scenario: str | None = None
    last_decision: tuple[str, int, int] | None = None

    for record in records:
        scenario = str(record.get("scenario") or "capture")
        if args.scenario and scenario != args.scenario:
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        line_values = payload.get("lineValues")
        if not isinstance(line_values, list):
            continue
        if scenario != current_scenario:
            follower.reset()
            current_scenario = scenario
            last_decision = None
        decision = follower.update(line_values)
        summary = summaries.setdefault(
            scenario,
            {
                "samples": 0,
                "modes": Counter(),
                "steeringMin": None,
                "steeringMax": None,
                "firstTerminal": None,
            },
        )
        summary["samples"] += 1
        summary["modes"][decision.mode.value] += 1
        minimum = summary["steeringMin"]
        maximum = summary["steeringMax"]
        summary["steeringMin"] = (
            decision.steering_deg
            if minimum is None
            else min(minimum, decision.steering_deg)
        )
        summary["steeringMax"] = (
            decision.steering_deg
            if maximum is None
            else max(maximum, decision.steering_deg)
        )
        if decision.mode.value in {"LINE_LOST", "DESTINATION"}:
            if summary["firstTerminal"] is None:
                summary["firstTerminal"] = decision.mode.value
        compact = (
            decision.mode.value,
            decision.speed_pwm,
            decision.steering_deg,
        )
        if args.show_decisions and compact != last_decision:
            print(
                "DECISION "
                f"scenario={scenario} line={list(decision.line_values)} "
                f"mode={decision.mode.value} speed={decision.speed_pwm} "
                f"steering={decision.steering_deg} error={decision.error}"
            )
            last_decision = compact

    if not summaries:
        raise SystemExit("ERROR: no matching lineValues records were found")
    serializable = {
        scenario: {
            **summary,
            "modes": dict(summary["modes"]),
        }
        for scenario, summary in summaries.items()
    }
    print(json.dumps(serializable, ensure_ascii=False, indent=2))
    print("LINE_FOLLOW_REPLAY_COMPLETE_NO_MOVEMENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
