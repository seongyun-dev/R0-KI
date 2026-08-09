from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TOOLS_ROOT = Path(__file__).resolve().parent / "tools"
sys.path.insert(0, str(TOOLS_ROOT))

from waypoint_mqtt_demo import build_command_payload  # noqa: E402


class WaypointMqttDemoTest(unittest.TestCase):
    def test_start_payload_matches_command_contract(self) -> None:
        now = datetime(2026, 8, 2, 20, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        payload = build_command_payload(
            "START_PATROL",
            patrol_id=23,
            command_id="start-23",
            now=now,
        )
        self.assertEqual(
            payload,
            {
                "schemaVersion": 1,
                "commandId": "start-23",
                "command": "START_PATROL",
                "issuedAt": "2026-08-02T20:00:00.000+09:00",
                "expiresAt": "2026-08-02T20:00:30.000+09:00",
                "patrolId": 23,
            },
        )

    def test_stop_payload_has_no_patrol_id(self) -> None:
        payload = build_command_payload("STOP_PATROL", command_id="stop-1")
        self.assertNotIn("patrolId", payload)
        self.assertEqual(payload["command"], "STOP_PATROL")

    def test_start_rejects_missing_or_invalid_patrol_id(self) -> None:
        for value in (None, 0, -1, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    build_command_payload("START_PATROL", patrol_id=value)


if __name__ == "__main__":
    unittest.main()
