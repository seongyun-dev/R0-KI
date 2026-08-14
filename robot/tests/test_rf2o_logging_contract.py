"""RF2O must keep its scan-processing rate while avoiding journal floods."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class Rf2oLoggingContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.robot_root = Path(__file__).resolve().parent.parent
        cls.run_ros = (cls.robot_root / "scripts" / "run-ros.sh").read_text(
            encoding="utf-8"
        )
        cls.rf2o = yaml.safe_load(
            (cls.robot_root / "config" / "ros" / "rf2o.yaml").read_text(
                encoding="utf-8"
            )
        )["/**"]["ros__parameters"]

    def test_scan_polling_rate_is_not_reduced(self):
        self.assertEqual(self.rf2o["freq"], 20.0)

    def test_only_the_two_noisy_rf2o_loggers_are_filtered(self):
        self.assertIn("--log-level CLaserOdometry2D:=warn", self.run_ros)
        self.assertIn("--log-level CLaserOdometry2DNode:=error", self.run_ros)
        self.assertNotIn("--log-level warn", self.run_ros)


if __name__ == "__main__":
    unittest.main()
