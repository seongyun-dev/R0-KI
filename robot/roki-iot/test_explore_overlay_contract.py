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
        cls.bt_text = (
            cls.robot_root / "config" / "ros" / "nav2_mapping_replan.xml"
        ).read_text(encoding="utf-8")

    def test_patch_contains_mapping_recovery_layers(self):
        for token in (
            "frontier.approaches",
            "frontier_max_approaches",
            "all_approaches_unreachable",
            "ComputePathToPose",
            "FollowPath",
            "sendFollowPathGoal",
            "buildExecutablePath",
            "frontier_unknown_bridge_standoff",
            "frontier_retry_delay",
            "reactivated after local FREE growth",
            "frontier.local_free_cells",
            "exploration_stalled",
            "MappingGridBased",
            "canceling_goal_",
            "goal_cancel_timeout",
            "planning_generation_",
            "Previous frontier goal reached a terminal state",
        ):
            self.assertIn(token, self.patch_text)

        self.assertNotIn("max_unknown_path_length", self.patch_text)
        self.assertNotIn("pathCrossesUnsafeUnknown", self.patch_text)
        self.assertIn(
            "approach.position.y - robot_pose.position.y",
            self.patch_text,
            "다중 접근점 변경이 8c7a466의 robot-to-target yaw를 바꾸면 안 된다",
        )
        self.assertNotIn(
            "approach.boundary.y - approach.position.y",
            self.patch_text,
        )

        # The path accepted by MappingGridBased must be the one sent to the
        # controller. NavigateToPose is retained only for the deferred
        # return-to-origin path, not frontier execution.
        self.assertIn("goal.path = path", self.patch_text)
        self.assertIn(
            "follow_path_client_->async_send_goal(goal, send_goal_options)",
            self.patch_text,
        )
        self.assertNotIn("sendNavigationGoal", self.patch_text)

    def test_start_point_return_remains_disabled(self):
        self.assertIn("return_to_init: false", self.params_text)
        self.assertNotIn("return_to_init: true", self.params_text)

    def test_mapping_parameters_match_overlay_contract(self):
        self.assertIn("frontier_approach_distance: 0.25", self.params_text)
        self.assertIn("frontier_max_approaches: 3", self.params_text)
        self.assertIn("frontier_candidate_spacing: 0.20", self.params_text)
        self.assertIn("frontier_retry_delay: 5.0", self.params_text)
        self.assertIn("frontier_cancel_timeout: 5.0", self.params_text)
        self.assertIn("frontier_max_attempts: 2", self.params_text)
        self.assertIn("frontier_max_reactivations: 1", self.params_text)
        self.assertIn("frontier_reactivation_radius: 0.50", self.params_text)
        self.assertIn("frontier_reactivation_min_free_cells: 8", self.params_text)
        self.assertIn("frontier_failure_match_radius: 0.25", self.params_text)
        self.assertIn("frontier_planner_id: MappingGridBased", self.params_text)
        self.assertIn(
            "frontier_max_internal_unknown_run: 0.30", self.params_text
        )
        self.assertIn(
            "frontier_unknown_bridge_standoff: 0.10", self.params_text
        )
        self.assertIn("frontier_controller_id: FollowPath", self.params_text)
        self.assertIn(
            "frontier_goal_checker_id: mapping_goal_checker", self.params_text
        )

    def test_mapping_bt_has_one_bounded_retry_without_costmap_clear(self):
        self.assertIn('number_of_retries="1"', self.bt_text)
        self.assertIn('planner_id="MappingGridBased"', self.bt_text)
        self.assertIn('controller_id="MappingFollowPath"', self.bt_text)
        self.assertIn('<Wait wait_duration="1.0"/>', self.bt_text)
        self.assertNotIn("<ClearEntireCostmap", self.bt_text)
        self.assertNotIn("<Spin", self.bt_text)
        self.assertNotIn("<BackUp", self.bt_text)


if __name__ == "__main__":
    unittest.main()
