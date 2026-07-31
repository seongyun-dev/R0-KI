import json
import unittest

from aiot_robot.backend_client import BackendConfig, RobotBackendClient


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return self._body


class CapturingUrlOpen:
    def __init__(self) -> None:
        self.request = None
        self.timeout = None

    def __call__(self, request, *, timeout):
        self.request = request
        self.timeout = timeout
        return FakeResponse({"success": True, "code": "SUCCESS", "data": {"eventId": 1}})


class BackendClientTest(unittest.TestCase):
    def test_create_event_uses_robot_bearer_contract(self) -> None:
        opener = CapturingUrlOpen()
        client = RobotBackendClient(
            BackendConfig("https://i15e103.p.ssafy.io", "secret", 3),
            urlopen=opener,
        )
        response = client.create_event(
            {
                "eventType": "EMERGENCY",
                "eventTitle": "test",
                "occurredAt": "2026-07-31T05:20:03Z",
                "x": 1.0,
                "y": 2.0,
                "riskLevel": "EMERGENCY",
            }
        )

        self.assertEqual(response["data"]["eventId"], 1)
        self.assertEqual(opener.timeout, 3)
        self.assertEqual(
            opener.request.full_url,
            "https://i15e103.p.ssafy.io/api/robot/events",
        )
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(
            json.loads(opener.request.data.decode())["riskLevel"], "EMERGENCY"
        )

    def test_requires_https(self) -> None:
        with self.assertRaises(ValueError):
            BackendConfig("http://example.com", "secret")


if __name__ == "__main__":
    unittest.main()
