#!/usr/bin/env python3
"""Bounded straight-line waypoint field test using ESP32 wheel odometry.

This diagnostic deliberately does not claim SLAM/Nav2 localization.  It maps
the average left/right encoder travel onto the +X axis of a validated dummy
map, advances the shared waypoint mission, and stops at DESTINATION or on any
safety fault.  It must be the only ESP32 serial owner.
"""

from __future__ import annotations

import argparse
import json
import math
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
        if (candidate / "navigation" / "service.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    raise SystemExit("ERROR: RO-KI navigation package was not found")


_add_roki_import_path()

from navigation.map_metadata import (  # noqa: E402
    load_map_metadata,
    validate_route_bounds,
)
from navigation.route import Route, load_route  # noqa: E402
from navigation.service import WaypointNavigationService  # noqa: E402
from navigation.waypoint_mission import (  # noqa: E402
    MissionEventType,
    Pose2D,
)


SUPPORTED_FIRMWARE_VERSIONS = {"3.0.0"}
WHEEL_DIAMETER_M = 0.065
TICKS_PER_REVOLUTION = 329.0
MIN_BATTERY_VOLTAGE = 9.0
MAX_BATTERY_VOLTAGE = 13.0
CONTROL_INTERVAL_SEC = 0.1
TELEMETRY_TIMEOUT_SEC = 0.35
MAX_ENCODER_DISAGREEMENT_M = 0.15
MAX_ROUTE_DISTANCE_M = 0.65
MAX_OVERRUN_M = 0.10
START_X_M = 1.0
START_Y_M = 2.5


class FieldTestError(RuntimeError):
    """Raised when a safety, route, or protocol condition fails."""


def encoder_metres(ticks: int) -> float:
    return float(ticks) * math.pi * WHEEL_DIAMETER_M / TICKS_PER_REVOLUTION


def interpolated_progress(
    previous_m: float,
    current_m: float,
    *,
    max_step_m: float = 0.01,
) -> tuple[float, ...]:
    """Fill odometry gaps so a telemetry sample cannot skip a waypoint."""

    if current_m <= previous_m:
        return (current_m,)
    steps = max(1, math.ceil((current_m - previous_m) / max_step_m))
    return tuple(
        previous_m + (current_m - previous_m) * index / steps
        for index in range(1, steps + 1)
    )


def validate_straight_route(
    route: Route,
    *,
    start_x: float = START_X_M,
    start_y: float = START_Y_M,
) -> float:
    """Return destination travel and reject anything but a short +X route."""

    previous_x = start_x
    for waypoint in route.waypoints:
        if waypoint.x <= previous_x:
            raise FieldTestError("field route x coordinates must increase")
        if abs(waypoint.y - start_y) > 0.01:
            raise FieldTestError("field route must remain on the start y coordinate")
        if abs(waypoint.yaw_deg) > 0.01:
            raise FieldTestError("field route yaw must remain 0 degrees")
        previous_x = waypoint.x
    travel = route.waypoints[-1].x - start_x
    if not 0.10 <= travel <= MAX_ROUTE_DISTANCE_M:
        raise FieldTestError(
            f"field route destination must be 0.10..{MAX_ROUTE_DISTANCE_M:.2f} m "
            f"ahead; got {travel:.3f} m"
        )
    return travel


def validate_hardware(payload: dict[str, Any]) -> float:
    if payload.get("motor") != "NORMAL":
        raise FieldTestError(f"motor state is not NORMAL: {payload.get('motor')}")
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
    return float(voltage)


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
        message = {"type": message_type, **fields, "sequence": self.sequence}
        self.sequence += 1
        self.port.write(
            (json.dumps(message, separators=(",", ":")) + "\n").encode("ascii")
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

    def mandatory_handshake(self) -> tuple[dict[str, Any], dict[str, Any]]:
        self.send("stop")
        self.send("hello", protocol=1)
        self.send("encoder_zero")
        self.send("status")
        seen = {"hello": False, "encoder": False}
        latest_odometry: dict[str, Any] | None = None
        latest_hardware: dict[str, Any] | None = None
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            payload = self.read()
            if payload is None:
                continue
            message_type = payload.get("type")
            if message_type == "error":
                raise FieldTestError(f"ESP32 fault: {payload.get('fault')}")
            if message_type == "hello":
                seen["hello"] = (
                    payload.get("firmware") == "roki-operating"
                    and payload.get("version") in SUPPORTED_FIRMWARE_VERSIONS
                    and payload.get("protocol") == 1
                )
            elif message_type == "ack":
                if str(payload.get("command", "")).upper() == "ENCODER_ZERO":
                    seen["encoder"] = True
            elif message_type == "odometry" and _valid_odometry(payload):
                latest_odometry = payload
            elif message_type == "hardwareStatus":
                validate_hardware(payload)
                latest_hardware = payload
            if all(seen.values()) and latest_odometry and latest_hardware:
                return latest_odometry, latest_hardware
        missing = [name for name, present in seen.items() if not present]
        if latest_odometry is None:
            missing.append("odometry")
        if latest_hardware is None:
            missing.append("hardware")
        raise FieldTestError("operating handshake incomplete: " + ",".join(missing))

    def reset_input(self) -> None:
        if self.port is None:
            raise FieldTestError("serial port is not open")
        self.port.reset_input_buffer()


def _valid_odometry(payload: dict[str, Any]) -> bool:
    return all(
        isinstance(payload.get(field), int)
        and not isinstance(payload.get(field), bool)
        for field in ("uptimeMs", "leftTicks", "rightTicks")
    )


def _append_log(target: Any, event: str, **fields: Any) -> None:
    payload = {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    target.write(json.dumps(payload, ensure_ascii=False) + "\n")
    target.flush()


def parse_args() -> argparse.Namespace:
    root = Path.home() / "roki" / "maps" / "dummy_rectangle"
    parser = argparse.ArgumentParser(
        description="Bounded 60 cm dummy-map waypoint field test"
    )
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--port")
    parser.add_argument("--speed", type=int, default=45)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--map", type=Path, default=root / "map.yaml")
    parser.add_argument(
        "--route", type=Path, default=root / "route.short-straight.yaml"
    )
    parser.add_argument("--patrol-id", type=int, default=1)
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("logs/waypoint/odom-field-test.jsonl"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.confirm != "STRAIGHT_ROUTE_CLEAR":
        raise SystemExit(
            "ERROR: use --confirm STRAIGHT_ROUTE_CLEAR only after raising the "
            "robot for a first test or clearing a straight 1 m floor route"
        )
    if args.speed != 45:
        raise SystemExit("ERROR: this first field test is fixed at speed 45")
    if not 3.0 <= args.seconds <= 15.0:
        raise SystemExit("ERROR: seconds must be 3..15")
    if args.patrol_id <= 0:
        raise SystemExit("ERROR: patrol-id must be positive")

    route = load_route(args.route)
    map_metadata = load_map_metadata(args.map)
    validate_route_bounds(route, map_metadata)
    target_distance = validate_straight_route(route)
    try:
        port_name = resolve_esp32_port(args.port)
    except Esp32PortError as error:
        raise SystemExit(f"ERROR: {error}") from error

    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"ESP32_PORT={port_name}")
    print(f"MAP={args.map.resolve()}")
    print(f"ROUTE={args.route.resolve()}")
    print(f"LOG_FILE={args.log_file.resolve()}")
    print(
        f"Dummy-map test: +X {target_distance:.2f} m, speed=45, "
        "steering=80, encoder-only pose"
    )

    navigation = WaypointNavigationService(route)
    try:
        with args.log_file.open("a", encoding="utf-8") as log_target:
            with OperatingClient(port_name) as client:
                _, hardware = client.mandatory_handshake()
                voltage = validate_hardware(hardware)
                started_event = navigation.start_patrol(patrol_id=args.patrol_id)
                _append_log(
                    log_target,
                    "mission",
                    eventType=started_event.mission_event.event_type.value,
                    batteryVoltage=voltage,
                )

                for remaining in (3, 2, 1):
                    client.send("stop")
                    print(f"Starting in {remaining}...")
                    time.sleep(1.0)

                client.reset_input()
                client.send("status")
                started = time.monotonic()
                last_odometry_at = started
                last_hardware_at = started
                next_control_at = started
                destination_reached = False
                previous_distance_m = 0.0

                while time.monotonic() - started < args.seconds:
                    now = time.monotonic()
                    payload = client.read()
                    if payload is not None:
                        message_type = payload.get("type")
                        if message_type == "error":
                            raise FieldTestError(
                                f"ESP32 fault: {payload.get('fault')}"
                            )
                        if message_type == "hardwareStatus":
                            voltage = validate_hardware(payload)
                            last_hardware_at = now
                        elif message_type == "odometry":
                            if not _valid_odometry(payload):
                                raise FieldTestError("invalid odometry payload")
                            last_odometry_at = now
                            left_m = encoder_metres(payload["leftTicks"])
                            right_m = encoder_metres(payload["rightTicks"])
                            distance_m = (left_m + right_m) / 2.0
                            if distance_m < -0.02:
                                raise FieldTestError(
                                    "encoders report reverse travel during +X test"
                                )
                            if abs(left_m - right_m) > MAX_ENCODER_DISAGREEMENT_M:
                                raise FieldTestError(
                                    "left/right encoder travel differs by more than "
                                    f"{MAX_ENCODER_DISAGREEMENT_M:.2f} m"
                                )
                            if distance_m > target_distance + MAX_OVERRUN_M:
                                raise FieldTestError("destination overrun guard triggered")

                            mission_updates = []
                            for progress_m in interpolated_progress(
                                previous_distance_m, distance_m
                            ):
                                pose = Pose2D(
                                    START_X_M + progress_m,
                                    START_Y_M,
                                    0.0,
                                )
                                mission_updates.extend(
                                    (event, progress_m)
                                    for event in navigation.update_pose(pose)
                                )
                            previous_distance_m = max(
                                previous_distance_m, distance_m
                            )
                            _append_log(
                                log_target,
                                "pose",
                                x=pose.x,
                                y=pose.y,
                                leftMetres=left_m,
                                rightMetres=right_m,
                                batteryVoltage=voltage,
                            )
                            for event, event_distance_m in mission_updates:
                                mission_event = event.mission_event
                                waypoint = mission_event.waypoint
                                print(
                                    f"EVENT={mission_event.event_type.value} "
                                    f"waypoint={waypoint.name if waypoint else '-'} "
                                    f"distance={event_distance_m:.3f}m"
                                )
                                _append_log(
                                    log_target,
                                    "mission",
                                    eventType=mission_event.event_type.value,
                                    waypoint=waypoint.name if waypoint else None,
                                    distanceMetres=event_distance_m,
                                )
                                if (
                                    mission_event.event_type
                                    is MissionEventType.DESTINATION_REACHED
                                ):
                                    destination_reached = True
                                    client.send("stop")
                                    break

                    if destination_reached:
                        break
                    if now - last_hardware_at > TELEMETRY_TIMEOUT_SEC:
                        raise FieldTestError("hardwareStatus telemetry timeout")
                    if now - last_odometry_at > TELEMETRY_TIMEOUT_SEC:
                        raise FieldTestError("odometry telemetry timeout")
                    if now >= next_control_at:
                        client.send("control", speed=args.speed, steering=80)
                        next_control_at = now + CONTROL_INTERVAL_SEC

                client.send("stop")
                if not destination_reached:
                    raise FieldTestError("time limit reached before DESTINATION")
                _append_log(log_target, "stopped", reason="DESTINATION_REACHED")
                print("FIELD_TEST_COMPLETE reason=DESTINATION_REACHED state=STOPPED")
        return 0
    except KeyboardInterrupt:
        print("INTERRUPTED: STOP sent; field test ended", file=sys.stderr)
        return 130
    except (FieldTestError, serial.SerialException, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
