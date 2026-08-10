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
                    "detectionEnabled": True,
                    "patrolId": 17,
                    "modelVersion": "vehicle-v1",
                    "heartbeatAt": "2026-07-31T05:20:02Z",
                    "errorCode": None,
                    "message": None,
                }
            )
        )
        self.assertTrue(status.ready_for_patrol)
        self.assertTrue(status.detection_enabled)
        self.assertEqual(status.patrol_id, 17)
        self.assertTrue(status.detection_applied_for(17))

    def test_rejects_invalid_detection_application_status(self) -> None:
        payload = {
            "schemaVersion": 1,
            "state": "READY",
            "ready": True,
            "cameraReady": True,
            "engineReady": True,
            "inferenceReady": True,
            "detectionEnabled": "yes",
            "patrolId": 17,
            "heartbeatAt": "2026-07-31T05:20:02Z",
        }
        with self.assertRaises(ContractError):
            AiStatus.from_json(json.dumps(payload))

    def test_matching_detection_is_not_applied_while_ai_is_unready(self) -> None:
        for state in ("ERROR", "DEGRADED"):
            with self.subTest(state=state):
                status = AiStatus.from_json(
                    json.dumps(
                        {
                            "schemaVersion": 1,
                            "state": state,
                            "ready": False,
                            "cameraReady": True,
                            "engineReady": True,
                            "inferenceReady": True,
                            "detectionEnabled": True,
                            "patrolId": 17,
                            "heartbeatAt": "2026-08-04T00:00:00Z",
                        }
                    )
                )

                self.assertFalse(status.ready_for_patrol)
                self.assertFalse(status.detection_applied_for(17))

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
