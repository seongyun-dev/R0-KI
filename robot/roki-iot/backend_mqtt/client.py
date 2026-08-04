"""
Mosquitto MQTT Client 모듈.

이 클래스는 다음 역할만 담당한다.

1. MQTT Broker 연결
2. MQTT 메시지 발행
3. MQTT 명령 토픽 구독
4. 수신 메시지를 등록된 콜백으로 전달
5. MQTT 연결 종료

Payload 내용을 해석하거나 순찰/센서 로직을
판단하지 않는다.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Callable

import paho.mqtt.client as mqtt

from backend_config.settings import AppSettings

CommandMessageHandler = Callable[[str, dict[str, Any]], None]
CommandEnvelope = tuple[str, dict[str, Any]]
_COMMAND_WORKER_STOP = object()


class MqttClient:
    """한바퀴 Jetson MQTT 클라이언트."""

    def __init__(
        self,
        settings: AppSettings,
    ) -> None:
        self._settings = settings
        self._connected = False
        self._on_command_message: (
            CommandMessageHandler | None
        ) = None
        self._command_queue: queue.Queue[
            CommandEnvelope | object
        ] = queue.Queue()
        self._command_worker_lock = threading.Lock()
        self._command_worker: threading.Thread | None = None
        self._accepting_commands = False
        self._discard_pending_commands = False

        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.mqtt_client_id,
        )
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

        self._configure_authentication()
        self._configure_tls()
        self._register_callbacks()

    def _configure_authentication(self) -> None:
        """MQTT 사용자 인증 정보를 설정한다."""

        if not self._settings.mqtt_username:
            return

        self._client.username_pw_set(
            username=self._settings.mqtt_username,
            password=self._settings.mqtt_password,
        )

    def _configure_tls(self) -> None:
        """TLS 사용이 활성화된 경우 TLS를 설정한다."""

        if not self._settings.mqtt_use_tls:
            return

        self._client.tls_set()

    def _register_callbacks(self) -> None:
        """MQTT 이벤트 콜백을 등록한다."""

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def set_command_handler(
        self,
        handler: CommandMessageHandler,
    ) -> None:
        """
        command 토픽 수신 시 호출할 핸들러를 등록한다.

        핸들러 인자:
        - topic: 수신 토픽 문자열
        - payload: JSON dict
        """

        self._on_command_message = handler

    def _subscribe_command_topic(self) -> None:
        """로봇 명령 토픽을 QoS 1로 구독한다."""

        topic = self._settings.command_topic
        result, _mid = self._client.subscribe(
            topic,
            qos=1,
        )

        if result != mqtt.MQTT_ERR_SUCCESS:
            print(
                "[MQTT ERROR] command 구독 실패: "
                f"topic={topic}, rc={result}"
            )
            return

        print(f"[MQTT] command 구독: {topic}")

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Broker 연결 결과를 처리한다."""

        if reason_code == 0:
            self._connected = True

            print(
                "[MQTT] 연결 완료: "
                f"{self._settings.mqtt_host}:"
                f"{self._settings.mqtt_port}"
            )

            # 재연결 시에도 구독이 유지되도록
            # 연결 성공 시점에 다시 구독한다.
            self._subscribe_command_topic()
            return

        print(
            "[MQTT ERROR] 연결 실패: "
            f"{reason_code}"
        )

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Broker 연결 종료 상태를 처리한다."""

        self._connected = False

        print(
            "[MQTT] 연결 종료: "
            f"{reason_code}"
        )

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        """
        수신 메시지를 JSON dict로 변환해
        등록된 command 핸들러로 전달한다.
        """

        if message.topic != self._settings.command_topic:
            return

        try:
            raw_text = message.payload.decode("utf-8")
            payload = json.loads(raw_text)
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            print(
                "[MQTT ERROR] command payload 해석 실패: "
                f"{exc}"
            )
            return

        if not isinstance(payload, dict):
            print(
                "[MQTT ERROR] command payload가 "
                "JSON object가 아닙니다."
            )
            return

        # SET_TOKEN is retained by the backend. Never log command bodies.
        print(
            "[MQTT] command received "
            f"topic={message.topic} command={payload.get('command')} "
            f"commandId={payload.get('commandId')} retained={message.retain}"
        )

        if self._on_command_message is None:
            print(
                "[MQTT] command 핸들러가 "
                "등록되지 않았습니다."
            )
            return

        if not self._enqueue_command(message.topic, payload):
            print("[MQTT] command ignored while worker is stopping")

    def _enqueue_command(self, topic: str, payload: dict[str, Any]) -> bool:
        """Enqueue without running application code on Paho's loop thread."""

        with self._command_worker_lock:
            if not self._accepting_commands:
                return False
            self._command_queue.put_nowait((topic, payload))
            return True

    def _start_command_worker(self) -> None:
        with self._command_worker_lock:
            if (
                self._command_worker is not None
                and self._command_worker.is_alive()
            ):
                self._accepting_commands = True
                return
            self._command_queue = queue.Queue()
            self._accepting_commands = True
            self._discard_pending_commands = False
            self._command_worker = threading.Thread(
                target=self._run_command_worker,
                name="mqtt-command-worker",
                daemon=True,
            )
            self._command_worker.start()

    def _run_command_worker(self) -> None:
        while True:
            item = self._command_queue.get()
            try:
                if item is _COMMAND_WORKER_STOP:
                    return
                with self._command_worker_lock:
                    if self._discard_pending_commands:
                        continue
                topic, payload = item
                handler = self._on_command_message
                if handler is None:
                    print("[MQTT] command handler is not registered")
                    continue
                try:
                    handler(topic, payload)
                except Exception as exc:
                    # One failed command must not kill FIFO processing for a
                    # later physical STOP.
                    print(
                        "[MQTT ERROR] command handler failed "
                        f"type={type(exc).__name__}"
                    )
            finally:
                self._command_queue.task_done()

    def stop_command_worker(
        self,
        *,
        drain: bool,
        timeout_seconds: float = 10.0,
    ) -> bool:
        """Stop intake, optionally process queued commands, and join worker."""

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        with self._command_worker_lock:
            self._accepting_commands = False
            self._discard_pending_commands = not drain
            worker = self._command_worker
            if worker is None:
                return True
            if not drain:
                while True:
                    try:
                        self._command_queue.get_nowait()
                    except queue.Empty:
                        break
                    else:
                        self._command_queue.task_done()
            self._command_queue.put_nowait(_COMMAND_WORKER_STOP)
        if worker is threading.current_thread():
            return False
        worker.join(timeout=timeout_seconds)
        stopped = not worker.is_alive()
        if stopped:
            with self._command_worker_lock:
                if self._command_worker is worker:
                    self._command_worker = None
        return stopped

    def connect(
        self,
        timeout_seconds: float = 5.0,
    ) -> None:
        """
        MQTT Broker에 연결한다.

        지정된 시간 안에 연결되지 않으면
        ConnectionError를 발생시킨다.
        """

        self._start_command_worker()
        try:
            self._client.connect(
                host=self._settings.mqtt_host,
                port=self._settings.mqtt_port,
                keepalive=60,
            )
        except Exception:
            self.stop_command_worker(drain=False)
            raise

        self._client.loop_start()

        deadline = time.monotonic() + timeout_seconds

        while (
            not self._connected
            and time.monotonic() < deadline
        ):
            time.sleep(0.1)

        if self._connected:
            return

        self._client.loop_stop()
        self.stop_command_worker(drain=False)
        raise ConnectionError(
            "MQTT Broker 연결 실패: "
            f"{self._settings.mqtt_host}:"
            f"{self._settings.mqtt_port}"
        )

    def publish(
        self,
        *,
        topic: str,
        payload: dict[str, Any],
    ) -> None:
        """
        dict Payload를 JSON으로 변환해 발행한다.

        모든 MQTT 메시지는 QoS 1,
        retain=False로 발행한다.
        """

        message = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        result = self._client.publish(
            topic=topic,
            payload=message,
            qos=1,
            retain=False,
        )

        result.wait_for_publish(timeout=3)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(
                "MQTT 발행 실패: "
                f"topic={topic}, rc={result.rc}"
            )

        print(f"[MQTT PUBLISH] topic={topic}")

    def disconnect(self) -> None:
        """MQTT 네트워크 루프와 연결을 종료한다."""

        self.stop_command_worker(drain=False)
        self._client.loop_stop()

        if self._connected:
            self._client.disconnect()
