"""YDLidar must not discard scans whose sample count varies by one or two."""

from __future__ import annotations

import unittest
from pathlib import Path

class YdLidarConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        robot_root = Path(__file__).resolve().parent.parent
        cls.config = (robot_root / "config" / "ros" / "ydlidar.yaml").read_text(
            encoding="utf-8"
        )

    def test_variable_resolution_frames_are_accepted(self) -> None:
        self.assertIn("    fixed_resolution: false\n", self.config)
        self.assertNotIn("    fixed_resolution: true\n", self.config)


if __name__ == "__main__":
    unittest.main()
