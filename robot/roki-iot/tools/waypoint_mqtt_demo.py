#!/usr/bin/env python3
"""Publish one bounded patrol command and wait for its MQTT ACK.

The default mode is dry-run.  START_PATROL additionally requires the literal
physical-course confirmation even when --send is present.  This tool is a
broker diagnostic; the backend/frontend remain the production command source.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import paho.mqtt.client as mqtt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend_config.settings import AppSettings, load_settings  # noqa: E402


SEOUL = ZoneInfo("Asia/Seoul")
START_CONFIRMATION = "STRAIGHT_ROUTE_CLEAR"


def build_command_payload(
    command: str,
    *,
    patrol_id: int | None = None,
    command_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized = command.upper()
    if normalized not in {"START_PATROL", "STOP_PATROL"}:
        raise ValueError("command must be START_PATROL or STOP_PATROL")
    if normalized == "START_PATROL" and (
        isinstance(patrol_id, bool)
        or not isinstance(patrol_id, int)
        or patrol_id <= 0
    ):
        raise ValueError("START_PATROL requires a positive patrol_id")
    issued_at = now or datetime.now(tz=SEOUL)
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=SEOUL)
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "commandId": command_id or str(uuid.uuid4()),
        "command": normalized,
        "issuedAt": issued_at.isoformat(timespec="milliseconds"),
        "expiresAt": (issued_at + timedelta(seconds=30)).isoformat(
            timespec="milliseconds"
        ),
    }
    if normalized == "START_PATROL":
        payload["patrolId"] = patrol_id
    return payload


class AckWaiter:
    def __init__(self, *, settings: AppSettings, command_id: str) -> None:
        self._settings = settings
        self._command_id = command_id
        self._connected = threading.Event()
        self._subscribed = threading.Event()
        self._ack_event = threading.Event()
        self._ack: dict[str, Any] | None = None
        self._connect_error: str | None = None
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=(
                f"{settings.robot_key}-waypoint-demo-{uuid.uuid4().hex[:8]}"
            ),
        )
        if settings.mqtt_username:
            self._client.username_pw_set(
                settings.mqtt_username,
                settings.mqtt_password,
            )
        if settings.mqtt_use_tls:
            self._client.tls_set()
        self._client.on_connect = self._on_connect
        self._client.on_subscribe = self._on_subscribe
        self._client.on_message = self._on_message

    def publish_and_wait(
        self,
        *,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self._client.connect(
            self._settings.mqtt_host,
            self._settings.mqtt_port,
            keepalive=30,
        )
        self._client.loop_start()
        try:
            if not self._connected.wait(timeout=5.0):
                raise RuntimeError(
                    self._connect_error or "MQTT connection timed out"
                )
            if self._connect_error:
                raise RuntimeError(self._connect_error)
            if not self._subscribed.wait(timeout=5.0):
                raise RuntimeError(
                    self._connect_error or "MQTT ACK subscription timed out"
                )
            if self._connect_error:
                raise RuntimeError(self._connect_error)
            info = self._client.publish(
                self._settings.command_topic,
                json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
                qos=1,
                retain=False,
            )
            info.wait_for_publish(timeout=5.0)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT publish failed: rc={info.rc}")
            if not self._ack_event.wait(timeout=timeout_seconds):
                raise RuntimeError("command ACK timed out")
            if self._ack is None:
                raise RuntimeError("matching command ACK was not received")
            return self._ack
        finally:
            self._client.loop_stop()
            self._client.disconnect()

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: Any,
        _flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        if reason_code != 0:
            self._connect_error = f"MQTT connection rejected: {reason_code}"
            self._connected.set()
            return
        result, _mid = client.subscribe(
            self._settings.command_response_topic,
            qos=1,
        )
        if result != mqtt.MQTT_ERR_SUCCESS:
            self._connect_error = f"MQTT ACK subscribe failed: rc={result}"
            self._subscribed.set()
        self._connected.set()

    def _on_subscribe(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        _mid: int,
        reason_codes: list[mqtt.ReasonCode],
        _properties: mqtt.Properties | None,
    ) -> None:
        if any(code.is_failure for code in reason_codes):
            self._connect_error = (
                f"MQTT ACK subscription rejected: {reason_codes}"
            )
        self._subscribed.set()

    def _on_message(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        if message.topic != self._settings.command_response_topic:
            return
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        if payload.get("commandId") != self._command_id:
            return
        self._ack = payload
        self._ack_event.set()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RO-KI waypoint MQTT START/STOP ACK diagnostic"
    )
    parser.add_argument("command", choices=("start", "stop"))
    parser.add_argument("--patrol-id", type=int)
    parser.add_argument("--confirm")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--ack-timeout", type=float, default=8.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = "START_PATROL" if args.command == "start" else "STOP_PATROL"
    if not 1.0 <= args.ack_timeout <= 30.0:
        raise SystemExit("ERROR: --ack-timeout must be 1..30 seconds")
    try:
        payload = build_command_payload(
            command,
            patrol_id=args.patrol_id,
        )
    except ValueError as error:
        raise SystemExit(f"ERROR: {error}") from error

    settings = load_settings()
    print(f"COMMAND_TOPIC={settings.command_topic}")
    print(f"ACK_TOPIC={settings.command_response_topic}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.send:
        print("DRY_RUN_ONLY: no MQTT message was published")
        return 0
    if command == "START_PATROL" and args.confirm != START_CONFIRMATION:
        raise SystemExit(
            "ERROR: START requires --confirm STRAIGHT_ROUTE_CLEAR after "
            "clearing the physical course"
        )

    waiter = AckWaiter(
        settings=settings,
        command_id=str(payload["commandId"]),
    )
    try:
        ack = waiter.publish_and_wait(
            payload=payload,
            timeout_seconds=args.ack_timeout,
        )
    except (OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print("ACK=" + json.dumps(ack, ensure_ascii=False, separators=(",", ":")))
    return 0 if ack.get("status") == "SUCCEEDED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
