import unittest

from aiot_robot.ai_capture import CaptureSettings, configure_capture


class FakeCv2:
    CAP_PROP_FOURCC = 1
    CAP_PROP_FRAME_WIDTH = 2
    CAP_PROP_FRAME_HEIGHT = 3
    CAP_PROP_FPS = 4
    CAP_PROP_BUFFERSIZE = 5

    @staticmethod
    def VideoWriter_fourcc(*characters):
        return sum(ord(character) << (8 * index) for index, character in enumerate(characters))


class FakeCapture:
    def __init__(self, *, ignore_width=False):
        self.values = {}
        self.ignore_width = ignore_width

    def set(self, property_id, value):
        if property_id != FakeCv2.CAP_PROP_FRAME_WIDTH or not self.ignore_width:
            self.values[property_id] = value
        return True

    def get(self, property_id):
        return self.values.get(property_id, 320.0 if property_id == 2 else 0.0)


class CaptureSettingsTest(unittest.TestCase):
    def test_applies_verified_dual_camera_defaults(self):
        capture = FakeCapture()

        actual = configure_capture(capture, FakeCv2, CaptureSettings())

        self.assertEqual(actual, {"width": 640.0, "height": 480.0, "fps": 30.0})
        self.assertEqual(capture.values[FakeCv2.CAP_PROP_BUFFERSIZE], 1.0)

    def test_rejects_camera_that_ignores_requested_dimensions(self):
        with self.assertRaisesRegex(RuntimeError, "camera width mismatch"):
            configure_capture(
                FakeCapture(ignore_width=True), FakeCv2, CaptureSettings()
            )

    def test_rejects_invalid_fourcc(self):
        with self.assertRaisesRegex(ValueError, "fourcc"):
            CaptureSettings(fourcc="MJPEG")


if __name__ == "__main__":
    unittest.main()
