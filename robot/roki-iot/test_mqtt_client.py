from __future__ import annotations

import json
import threading
import unittest
from types import SimpleNamespace

from backend_mqtt.client import MqttClient


def settings():
    return SimpleNamespace(
        mqtt_client_id="test-robot",
        mqtt_username=None,
        mqtt_password=None,
        mqtt_use_tls=False,
        mqtt_host="127.0.0.1",
        mqtt_port=1883,
        command_topic="hanbakwi/v1/robots/test-robot/command",
    )


def message(command_id: str):
    return SimpleNamespace(
        topic=settings().command_topic,
        payload=json.dumps(
            {"command": "STOP_PATROL", "commandId": command_id}
        ).encode("utf-8"),
        retain=False,
    )


class MqttCommandWorkerTest(unittest.TestCase):
    def create_client(self) -> MqttClient:
        client = MqttClient(settings())
        self.addCleanup(
            lambda: client.stop_command_worker(
                drain=False,
                timeout_seconds=1.0,
            )
        )
        return client

    def test_paho_callback_returns_while_handler_is_blocked(self) -> None:
        client = self.create_client()
        handler_entered = threading.Event()
        release_handler = threading.Event()
        callback_returned = threading.Event()
        handler_threads: list[str] = []

        def handler(_topic: str, _payload: dict) -> None:
            handler_threads.append(threading.current_thread().name)
            handler_entered.set()
            release_handler.wait(timeout=1.0)

        client.set_command_handler(handler)
        client._start_command_worker()

        callback_thread = threading.Thread(
            target=lambda: (
                client._on_message(None, None, message("first")),
                callback_returned.set(),
            ),
            name="fake-paho-loop",
        )
        callback_thread.start()

        self.assertTrue(handler_entered.wait(timeout=0.5))
        self.assertTrue(callback_returned.wait(timeout=0.1))
        self.assertEqual(handler_threads, ["mqtt-command-worker"])
        release_handler.set()
        callback_thread.join(timeout=1.0)
        self.assertTrue(client.stop_command_worker(drain=True))

    def test_drain_preserves_fifo_order(self) -> None:
        client = self.create_client()
        received: list[str] = []
        client.set_command_handler(
            lambda _topic, payload: received.append(payload["commandId"])
        )
        client._start_command_worker()

        for command_id in ("one", "two", "three"):
            client._on_message(None, None, message(command_id))

        self.assertTrue(client.stop_command_worker(drain=True))
        self.assertEqual(received, ["one", "two", "three"])

    def test_non_draining_shutdown_discards_pending_commands(self) -> None:
        client = self.create_client()
        first_entered = threading.Event()
        release_first = threading.Event()
        received: list[str] = []

        def handler(_topic: str, payload: dict) -> None:
            received.append(payload["commandId"])
            if payload["commandId"] == "first":
                first_entered.set()
                release_first.wait(timeout=1.0)

        client.set_command_handler(handler)
        client._start_command_worker()
        client._on_message(None, None, message("first"))
        self.assertTrue(first_entered.wait(timeout=0.5))
        client._on_message(None, None, message("discarded"))

        stopped: list[bool] = []
        shutdown_thread = threading.Thread(
            target=lambda: stopped.append(
                client.stop_command_worker(
                    drain=False,
                    timeout_seconds=1.0,
                )
            )
        )
        shutdown_thread.start()
        release_first.set()
        shutdown_thread.join(timeout=1.0)

        self.assertEqual(stopped, [True])
        self.assertEqual(received, ["first"])
        self.assertFalse(client._enqueue_command(settings().command_topic, {}))


if __name__ == "__main__":
    unittest.main()
