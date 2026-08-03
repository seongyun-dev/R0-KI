import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from aiot_robot.mqtt_probe import summarize_message, token_file_metadata


class MqttProbeTest(unittest.TestCase):
    def test_set_token_summary_never_contains_secret(self):
        secret = "do-not-print-this-token"
        summary = summarize_message(
            "hanbakwi/v1/robots/ROKI-01/command",
            json.dumps(
                {
                    "schemaVersion": 1,
                    "command": "SET_TOKEN",
                    "commandId": "cmd-1",
                    "token": secret,
                }
            ).encode(),
            True,
        )

        self.assertTrue(summary["tokenPresent"])
        self.assertNotIn(secret, json.dumps(summary))

    def test_token_file_reports_only_mode_and_presence(self):
        path = Mock()
        path.exists.return_value = True
        path.stat.return_value = SimpleNamespace(st_size=6, st_mode=0o100600)

        metadata = token_file_metadata(path)

        self.assertEqual(metadata, {"exists": True, "nonempty": True, "mode": "0600"})
        self.assertNotIn("secret", json.dumps(metadata))


if __name__ == "__main__":
    unittest.main()
