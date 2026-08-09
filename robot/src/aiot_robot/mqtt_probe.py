"""Credential-safe MQTT TLS and live contract observation for field setup."""

from __future__ import annotations

import argparse
import json
import os
import stat
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import paho.mqtt.client as mqtt


def summarize_message(topic: str, payload: bytes, retained: bool) -> dict[str, Any]:
    """Return contract metadata while deliberately excluding all body values."""

    summary: dict[str, Any] = {
        "topic": topic,
        "retained": bool(retained),
        "payloadBytes": len(payload),
    }
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        summary["jsonObject"] = False
        return summary
    summary["jsonObject"] = isinstance(decoded, dict)
    if not isinstance(decoded, dict):
        return summary
    summary["schemaVersion"] = decoded.get("schemaVersion")
    summary["messageType"] = decoded.get("command") or decoded.get("type")
    summary["commandIdPresent"] = isinstance(decoded.get("commandId"), str)
    summary["patrolIdPresent"] = "patrolId" in decoded
    summary["tokenPresent"] = any(
        key.lower() in {"token", "accesstoken", "servicetoken"}
        and isinstance(value, str)
        and bool(value)
        for key, value in decoded.items()
    )
    return summary


def token_file_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "nonempty": False, "mode": None}
    details = path.stat()
    return {
        "exists": True,
        "nonempty": details.st_size > 0,
        "mode": format(stat.S_IMODE(details.st_mode), "04o"),
    }


class MqttProbe:
    def __init__(self, *, observe: bool) -> None:
        self.host = _required_environment("MQTT_HOST")
        self.port = int(os.getenv("MQTT_PORT", "8883"))
        self.robot_key = _required_environment("ROBOT_KEY")
        self.observe = observe
        self.connected = threading.Event()
        self.failure: str | None = None
        self.messages: list[dict[str, Any]] = []
        client_id = f"{self.robot_key}-readiness-{uuid4().hex[:10]}"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        username = os.getenv("MQTT_USERNAME")
        password = os.getenv("MQTT_PASSWORD")
        if username:
            self.client.username_pw_set(username, password)
        if _boolean_environment("MQTT_USE_TLS", True):
            ca_file = os.getenv("MQTT_TLS_CA_FILE") or None
            self.client.tls_set(ca_certs=ca_file)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def run(self, timeout: float) -> dict[str, Any]:
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_start()
        try:
            if not self.connected.wait(timeout=min(timeout, 10.0)):
                raise TimeoutError(self.failure or "MQTT connection timed out")
            if self.observe:
                time.sleep(max(0.0, timeout))
            if self.failure:
                raise ConnectionError(self.failure)
            return {
                "connected": True,
                "tls": _boolean_environment("MQTT_USE_TLS", True),
                "host": self.host,
                "port": self.port,
                "observedMessages": self.messages,
            }
        finally:
            self.client.disconnect()
            self.client.loop_stop()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        del userdata, flags, properties
        if reason_code != 0:
            self.failure = f"broker rejected connection: {reason_code}"
            self.connected.set()
            return
        if self.observe:
            base = f"hanbakwi/v1/robots/{self.robot_key}"
            for topic in (
                f"{base}/command",
                f"{base}/command/ack",
                f"{base}/pose",
                f"{base}/status",
            ):
                result, _ = client.subscribe(topic, qos=1)
                if result != mqtt.MQTT_ERR_SUCCESS:
                    self.failure = f"subscription failed for {topic}: rc={result}"
                    break
        self.connected.set()

    def _on_message(self, client, userdata, message) -> None:
        del client, userdata
        self.messages.append(
            summarize_message(message.topic, message.payload, message.retain)
        )

    def _on_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties
    ) -> None:
        del client, userdata, disconnect_flags, properties
        if reason_code != 0 and self.connected.is_set():
            self.failure = f"unexpected MQTT disconnect: {reason_code}"


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _boolean_environment(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    if raw not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        raise ValueError(f"{name} must be a boolean")
    return raw in {"true", "1", "yes", "on"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observe-seconds", type=float, default=0.0)
    parser.add_argument(
        "--token-file",
        type=Path,
        default=Path(
            os.getenv(
                "AIOT_BACKEND_TOKEN_FILE",
                "/var/lib/aiot/secrets/robot-service-token",
            )
        ),
    )
    args = parser.parse_args(argv)
    if args.observe_seconds < 0 or args.observe_seconds > 300:
        raise ValueError("observe seconds must be between 0 and 300")
    result = MqttProbe(observe=args.observe_seconds > 0).run(args.observe_seconds)
    result["tokenFile"] = token_file_metadata(args.token_file)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
        print(json.dumps({"connected": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(1)
