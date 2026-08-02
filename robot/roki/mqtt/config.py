"""MQTT 설정 로더."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class BrokerConfig:
    host: str
    port: int
    keepalive_sec: int
    reconnect_interval_sec: float


@dataclass(frozen=True)
class ClientConfig:
    client_id: str
    qos: int


@dataclass(frozen=True)
class TopicConfig:
    location: str
    status: str


@dataclass(frozen=True)
class MqttConfig:
    broker: BrokerConfig
    client: ClientConfig
    topics: TopicConfig


def load_mqtt_config(
    config_path: Path | str = "config/mqtt.yaml",
) -> MqttConfig:
    """mqtt.yaml을 읽어 MQTT 설정 객체를 반환한다."""

    with open(config_path, "r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    broker = BrokerConfig(**raw["broker"])
    client = ClientConfig(**raw["client"])
    topics = TopicConfig(**raw["topics"])

    return MqttConfig(
        broker=broker,
        client=client,
        topics=topics,
    )
