"""Release contract for the RO-KI mapping-only explore overlay."""

from __future__ import annotations

import unittest
from pathlib import Path


class ExploreOverlayContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.robot_root = Path(__file__).resolve().parent.parent
        cls.patch_text = (
            cls.robot_root
            / "patches"
            / "m-explore-ros2-326cf8a-roki-frontier-recovery.patch"
        ).read_text(encoding="utf-8")
        cls.params_text = (
            cls.robot_root / "config" / "ros" / "explore.params.yaml"
        ).read_text(encoding="utf-8")

    def test_patch_contains_mapping_recovery_layers(self):
        for token in (
            "frontier.approach",
            "ComputePathToPose",
            "frontier_retry_delay",
            "exploration_stalled",
            "MappingGridBased",
        ):
            self.assertIn(token, self.patch_text)

    def test_start_point_return_remains_disabled(self):
        self.assertIn("return_to_init: false", self.params_text)
        self.assertNotIn("return_to_init: true", self.params_text)

    def test_mapping_parameters_match_overlay_contract(self):
        self.assertIn("frontier_approach_distance: 0.25", self.params_text)
        self.assertIn("frontier_retry_delay: 15.0", self.params_text)
        self.assertIn("frontier_max_attempts: 2", self.params_text)
        self.assertIn("frontier_planner_id: MappingGridBased", self.params_text)


if __name__ == "__main__":
    unittest.main()
