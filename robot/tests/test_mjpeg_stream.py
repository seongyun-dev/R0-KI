import json
import threading
import time
import unittest
import urllib.request

from aiot_robot.mjpeg_stream import BOUNDARY, MjpegFrameHub, MjpegPublisher, MjpegStreamServer


class _Encoded:
    def __init__(self, value: bytes) -> None:
        self._value = value

    def tobytes(self) -> bytes:
        return self._value


class _FakeCv2:
    IMWRITE_JPEG_QUALITY = 1

    def __init__(self) -> None:
        self.calls = 0

    def imencode(self, extension, frame, options):
        self.calls += 1
        return True, _Encoded(b"jpeg:" + bytes(frame))


class MjpegStreamTest(unittest.TestCase):
    def test_frame_hub_keeps_latest_frame(self):
        hub = MjpegFrameHub()
        self.assertEqual(1, hub.publish(b"first"))
        self.assertEqual(2, hub.publish(b"second"))

        self.assertEqual((2, b"second"), hub.wait_for_frame(0, timeout=0.01))
        self.assertTrue(hub.health()["ready"])

    def test_stale_frame_is_not_ready_or_replayed_to_new_viewer(self):
        now = [100.0]
        hub = MjpegFrameHub(
            max_frame_age_seconds=2.0,
            clock=lambda: now[0],
        )
        self.assertEqual(1, hub.publish(b"patrol-frame"))
        self.assertTrue(hub.health()["ready"])

        now[0] = 102.001
        health = hub.health()
        self.assertFalse(health["ready"])
        self.assertGreater(health["frameAgeSeconds"], 2.0)
        self.assertIsNone(hub.wait_for_frame(0, timeout=0.0))

        self.assertEqual(2, hub.publish(b"new-patrol-frame"))
        self.assertEqual(
            (2, b"new-patrol-frame"),
            hub.wait_for_frame(0, timeout=0.0),
        )

    def test_frame_freshness_must_be_positive(self):
        with self.assertRaises(ValueError):
            MjpegFrameHub(max_frame_age_seconds=0)

    def test_publisher_throttles_jpeg_encoding(self):
        hub = MjpegFrameHub()
        cv2 = _FakeCv2()
        publisher = MjpegPublisher(hub, quality=70, max_fps=1)

        self.assertTrue(publisher.publish(b"a", cv2))
        self.assertFalse(publisher.publish(b"b", cv2))
        self.assertEqual(1, cv2.calls)
        self.assertEqual((1, b"jpeg:a"), hub.wait_for_frame(0, timeout=0.01))

    def test_health_and_stream_endpoints(self):
        server = MjpegStreamServer("127.0.0.1", 0)
        server.start()
        host, port = server.address
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/health") as response:
                health = json.load(response)
            self.assertFalse(health["ready"])

            server.hub.publish(b"jpeg-data")
            received = []

            def read_stream():
                with urllib.request.urlopen(
                    f"http://{host}:{port}/stream.mjpg", timeout=2
                ) as response:
                    header = b"".join(response.readline() for _ in range(4))
                    received.append(header + response.read(len(b"jpeg-data")))

            thread = threading.Thread(target=read_stream, daemon=True)
            thread.start()
            deadline = time.monotonic() + 2
            while not received and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(received)
            self.assertIn(f"--{BOUNDARY}".encode(), received[0])
            self.assertIn(b"jpeg-data", received[0])
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
