import json
import unittest

from aiot_robot.contracts import AiStatus
from aiot_robot.gate import AiGate


def ready_status() -> AiStatus:
    return AiStatus.from_json(
        json.dumps(
            {
                "schemaVersion": 1,
                "state": "READY",
                "ready": True,
                "cameraReady": True,
                "engineReady": True,
                "inferenceReady": True,
                "heartbeatAt": "2026-07-31T05:20:02Z",
            }
        )
    )


class AiGateTest(unittest.TestCase):
    def test_missing_status_is_limited(self) -> None:
        decision = AiGate(timeout_seconds=5).decision(now=10)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "AI_STATUS_MISSING")

    def test_fresh_ready_status_allows_patrol(self) -> None:
        gate = AiGate(timeout_seconds=5)
        gate.record(ready_status(), now=10)
        self.assertTrue(gate.decision(now=14.9).allowed)

    def test_stale_status_is_limited(self) -> None:
        gate = AiGate(timeout_seconds=5)
        gate.record(ready_status(), now=10)
        decision = gate.decision(now=15.1)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "AI_STATUS_STALE")


if __name__ == "__main__":
    unittest.main()
