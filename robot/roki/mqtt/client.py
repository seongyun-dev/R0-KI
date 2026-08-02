"""MQTT 브로커 연결과 메시지 발행을 관리하는 모듈.

이 모듈은 MQTT 연결 자체만 담당한다.
위치와 상태 payload 생성은 publisher.py가 담당한다.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import paho.mqtt.client as mqtt

from mqtt.config import MqttConfig


logger = logging.getLogger(__name__)


class MqttConnectionError(RuntimeError):
    """MQTT 브로커 연결에 실패했을 때 발생한다."""


class MqttPublishError(RuntimeError):
    """MQTT 메시지 발행에 실패했을 때 발생한다."""


@dataclass(frozen=True)
class PublishResult:
    """MQTT 메시지 발행 결과."""

    topic: str
    message_id: int


class MqttClient:
    """MQTT 연결과 메시지 발행을 관리한다."""

    def __init__(self, config: MqttConfig) -> None:
        self._config = config
        self._connected_event = threading.Event()

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.client.client_id,
            protocol=mqtt.MQTTv311,
        )

        self._client.reconnect_delay_set(
            min_delay=max(
                1,
                int(config.broker.reconnect_interval_sec),
            ),
            max_delay=30,
        )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    def connect(self, timeout_sec: float = 5.0) -> None:
        """MQTT 브로커에 연결하고 네트워크 루프를 시작한다."""

        if self.is_connected():
            return

        self._connected_event.clear()

        try:
            self._client.connect(
                host=self._config.broker.host,
                port=self._config.broker.port,
                keepalive=self._config.broker.keepalive_sec,
            )
            self._client.loop_start()
        except OSError as exc:
            raise MqttConnectionError(
                f"MQTT 브로커 연결 요청에 실패했습니다: {exc}"
            ) from exc

        if not self._connected_event.wait(timeout=timeout_sec):
            self._client.loop_stop()

            raise MqttConnectionError(
                "제한 시간 안에 MQTT 브로커 연결이 완료되지 않았습니다."
            )

    def disconnect(self) -> None:
        """MQTT 연결을 안전하게 종료한다."""

        if self.is_connected():
            self._client.disconnect()

        self._client.loop_stop()
        self._connected_event.clear()

    def is_connected(self) -> bool:
        """현재 MQTT 브로커 연결 여부를 반환한다."""

        return self._client.is_connected()

    def publish(
        self,
        *,
        topic: str,
        payload: str,
        qos: int | None = None,
        retain: bool = False,
        timeout_sec: float = 5.0,
    ) -> PublishResult:
        """문자열 payload를 지정된 MQTT 토픽으로 발행한다."""

        if not self.is_connected():
            raise MqttConnectionError(
                "MQTT 브로커에 연결되지 않았습니다."
            )

        publish_qos = self._config.client.qos if qos is None else qos

        if publish_qos not in {0, 1, 2}:
            raise ValueError("qos must be 0, 1, or 2")

        info = self._client.publish(
            topic=topic,
            payload=payload,
            qos=publish_qos,
            retain=retain,
        )

        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise MqttPublishError(
                f"MQTT 메시지 발행 요청에 실패했습니다: rc={info.rc}"
            )

        info.wait_for_publish(timeout=timeout_sec)

        if not info.is_published():
            raise MqttPublishError(
                "제한 시간 안에 MQTT 메시지 발행이 완료되지 않았습니다."
            )

        return PublishResult(
            topic=topic,
            message_id=info.mid,
        )

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """브로커 연결 결과를 내부 상태에 반영한다."""

        del client, userdata, flags, properties

        if reason_code.is_failure:
            logger.error(
                "MQTT broker connection rejected: reason=%s",
                reason_code,
            )
            self._connected_event.clear()
            return

        logger.info("MQTT broker connected")
        self._connected_event.set()

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: object,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """브로커 연결 종료를 내부 상태에 반영한다."""

        del client, userdata, disconnect_flags, properties

        self._connected_event.clear()

        if reason_code.is_failure:
            logger.warning(
                "MQTT broker disconnected unexpectedly: reason=%s",
                reason_code,
            )
