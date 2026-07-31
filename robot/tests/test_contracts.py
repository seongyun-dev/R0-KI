import json
import unittest

from aiot_robot.contracts import AiStatus, ContractError, DetectionEvent


class AiStatusTest(unittest.TestCase):
    def test_ready_status(self) -> None:
        status = AiStatus.from_json(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "state": "READY",
                    "ready": True,
                    "cameraReady": True,
                    "engineReady": True,
                    "inferenceReady": True,
                    "modelVersion": "vehicle-v1",
                    "heartbeatAt": "2026-07-31T05:20:02Z",
                    "errorCode": None,
                    "message": None,
                }
            )
        )
        self.assertTrue(status.ready_for_patrol)

    def test_rejects_unsupported_schema(self) -> None:
        with self.assertRaises(ContractError):
            AiStatus.from_json('{"schemaVersion":2}')


class DetectionEventTest(unittest.TestCase):
    def test_detection_round_trip(self) -> None:
        raw = json.dumps(
            {
                "schemaVersion": 1,
                "eventId": "event-1",
                "patrolId": 15,
                "eventType": "ILLEGAL_PARKING",
                "cameraId": "front",
                "trackId": "track-42",
                "confidence": 0.93,
                "observedAt": "2026-07-31T05:20:03Z",
                "evidencePath": "/var/lib/aiot/evidence/event-1.jpg",
                "bbox": {"x": 120, "y": 80, "width": 300, "height": 180},
                "attributes": {"plateText": "12가3456"},
            }
        )
        event = DetectionEvent.from_json(raw)
        self.assertEqual(event.event_id, "event-1")
        self.assertEqual(event.to_dict()["patrolId"], 15)

    def test_rejects_evidence_outside_persistent_root(self) -> None:
        raw = json.dumps(
            {
                "schemaVersion": 1,
                "eventId": "event-1",
                "eventType": "ILLEGAL_PARKING",
                "cameraId": "front",
                "trackId": "track-42",
                "confidence": 0.93,
                "observedAt": "2026-07-31T05:20:03Z",
                "evidencePath": "/tmp/event-1.jpg",
                "bbox": {"x": 0, "y": 0, "width": 1, "height": 1},
            }
        )
        with self.assertRaises(ContractError):
            DetectionEvent.from_json(raw)

    def test_rejects_evidence_path_traversal(self) -> None:
        raw = json.dumps(
            {
                "schemaVersion": 1,
                "eventId": "event-1",
                "eventType": "ILLEGAL_PARKING",
                "cameraId": "front",
                "trackId": "track-42",
                "confidence": 0.93,
                "observedAt": "2026-07-31T05:20:03Z",
                "evidencePath": "/var/lib/aiot/evidence/../secret.txt",
                "bbox": {"x": 0, "y": 0, "width": 1, "height": 1},
            }
        )
        with self.assertRaises(ContractError):
            DetectionEvent.from_json(raw)


if __name__ == "__main__":
    unittest.main()
