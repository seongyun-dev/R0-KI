"""MQTT 토픽 관리."""

from __future__ import annotations

from mqtt.config import load_mqtt_config

_config = load_mqtt_config()

LOCATION_TOPIC = _config.topics.location
STATUS_TOPIC = _config.topics.status
