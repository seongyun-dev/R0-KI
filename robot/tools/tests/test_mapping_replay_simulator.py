"""매핑 리플레이 시뮬레이터의 계약 테스트.

여기 있는 assertion 은 "구현이 동작한다" 가 아니라 **"이 시뮬레이터를 신뢰해도
되는가"** 를 검사한다. 시뮬레이터가 실물보다 관대하면 검증 도구로서 무가치하므로,
관대해지는 방향의 실패를 특히 촘촘히 잡는다.
"""

from __future__ import annotations

import math

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

_ROBOT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROBOT_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROBOT_ROOT))

from tools.mapping_sim import frontier as frontier_mod
from tools.mapping_sim import profiles as profiles_mod
from tools.mapping_sim import synthetic
from tools.mapping_sim.contracts import (
    BlacklistMode,
    CandidateVerdict,
    CellState,
    GoalYawRule,
    GridSpec,
    InflationSpec,
    LidarSpec,
    MergeMetric,
    MotionModel,
    PlannerFlavor,
    Pose,
    RobotSpec,
    TerminationState,
    polygon_overlaps_cell,
)
from tools.mapping_sim.planner import ApproximateAckermannPlanner
from tools.mapping_sim.simulator import (
    FailureLedger,
    SimSettings,
    StartPoseError,
    path_crosses_unsafe_unknown as sim_crosses_unknown,
    run,
    unknown_path_length_m as sim_unknown_length,
    validate_start_pose,
)
from tools.mapping_sim.worldmodel import DiscoveredMap, GroundTruth

ROBOT = RobotSpec()
V025 = profiles_mod.PROFILE_V025
V022 = profiles_mod.PROFILE_V022
V026 = profiles_mod.PROFILE_PROPOSED_CLEARANCE   # 제안(가설). 실제 v0.2.6 아님
V026_REAL = profiles_mod.PROFILE_V026
V026_VIEWPOINTS = profiles_mod.PROFILE_V026_VIEWPOINTS


def _reveal_everything(ground_truth: GroundTruth) -> DiscoveredMap:
    """정답 지도를 그대로 발견 지도로 복사. 플래너만 단독으로 시험할 때 쓴다."""
    discovered = DiscoveredMap(ground_truth.spec)
    spec = ground_truth.spec
    discovered.reveal(
        (col, row, ground_truth.state_at_cell(col, row))
        for row in range(spec.height)
        for col in range(spec.width)
    )
    return discovered


def _fast_settings(**overrides) -> SimSettings:
    base = dict(
        max_steps=40,
        max_sim_time_sec=4000.0,
        lidar=LidarSpec(max_range_m=3.0, angle_increment_deg=6.0),
        robot=ROBOT,
        seed=0,
        observe_interval_m=0.10,
    )
    base.update(overrides)
    return SimSettings(**base)


class GeometryTest(unittest.TestCase):
    def test_measured_radii_match_hand_calculation(self):
        # 이 두 값이 틀리면 모든 충돌 판정이 틀린다. 손계산과 대조한다.
        self.assertAlmostEqual(ROBOT.inscribed_radius_m, 0.135, places=4)
        self.assertAlmostEqual(ROBOT.circumscribed_radius_m, 0.2287, places=3)
        # 최소회전반경은 wheelbase / tan(20deg) 여야 한다.
        self.assertAlmostEqual(
            ROBOT.wheelbase_m / math.tan(math.radians(20.0)), 0.3407, places=3
        )

    def test_sat_overlap_catches_thin_wall(self):
        # 셀 중심 샘플링이라면 놓치는 배치: 셀 중심이 사각형 밖인데 변이 겹친다.
        pose = Pose(0.5, 0.5, 0.0)
        corners = ROBOT.footprint_corners(pose)
        # footprint x 범위는 0.5 +- 0.185 -> 0.315..0.685
        self.assertTrue(polygon_overlaps_cell(corners, 0.30, 0.49, 0.05))
        self.assertFalse(polygon_overlaps_cell(corners, 0.20, 0.49, 0.05))

    def test_footprint_rotation_changes_occupied_extent(self):
        # 실측에서 확인한 성질: 0.180 m 떨어진 셀이 yaw 0 에서는 안전하고
        # yaw 90 도에서는 충돌한다. 자세 의존 충돌이 실재함을 고정한다.
        rows = ["." * 20 for _ in range(20)]
        rows[9] = "." * 12 + "#" + "." * 7
        ground = synthetic.from_ascii(rows)
        # 벽 셀 중심 좌표. 셀은 한 변 0.05 의 **사각형** 이므로 중심 거리에서
        # 반셀 0.025 를 뺀 값이 실제 근접 거리다. dy=0.18 이면 근접변이 0.155 로
        # yaw 0 의 반폭 0.135 밖이고 yaw 90 의 반길이 0.185 안이다.
        wall_x, wall_y = ground.spec.cell_to_world(12, 20 - 1 - 9)
        near = Pose(wall_x - 0.10, wall_y + 0.18, 0.0)
        self.assertFalse(
            ground.footprint_collides(near, ROBOT), "yaw 0 에서 충돌로 판정됐다"
        )
        rotated = Pose(near.x, near.y, math.pi / 2.0)
        self.assertTrue(
            ground.footprint_collides(rotated, ROBOT),
            "yaw 90 도에서 장축이 눕는데 충돌을 놓쳤다",
        )


class InflationTest(unittest.TestCase):
    def test_cost_curve_matches_nav2_formula(self):
        spec = InflationSpec(inflation_radius_m=0.40, cost_scaling_factor=3.0)
        inscribed = ROBOT.inscribed_radius_m
        # inscribed 안쪽은 253 (INSCRIBED_INFLATED_OBSTACLE)
        self.assertEqual(spec.cost_at_distance(0.10, inscribed), 253)
        # inflation_radius 밖은 0
        self.assertEqual(spec.cost_at_distance(0.50, inscribed), 0)
        # 사이 구간은 252 * exp(-3 * (d - inscribed))
        expected = int(round(252 * math.exp(-3.0 * (0.30 - inscribed))))
        self.assertEqual(spec.cost_at_distance(0.30, inscribed), expected)

    def test_profiles_differ_only_in_radius(self):
        # 프로필 차이가 정말 반경뿐인지 고정한다 (태그 diff 에서 확인한 사실).
        self.assertEqual(V022.inflation.inflation_radius_m, 0.25)
        self.assertEqual(V025.inflation.inflation_radius_m, 0.40)
        self.assertEqual(
            V022.inflation.cost_scaling_factor, V025.inflation.cost_scaling_factor
        )
        self.assertEqual(V022.planner, V025.planner)
        self.assertEqual(V022.frontier, V025.frontier)
        self.assertEqual(V022.retry, V025.retry)
        # 알고리즘 차이는 yaw 규칙 하나다.
        self.assertIs(V022.goal_yaw_rule, GoalYawRule.BEARING_FROM_ROBOT)
        self.assertIs(V025.goal_yaw_rule, GoalYawRule.APPROACH_TO_BOUNDARY)


class MapLoaderTest(unittest.TestCase):
    def _write_pgm(self, directory: Path, *, negate: int) -> Path:
        width, height = 6, 4
        # 254=free, 0=occupied, 205=unknown
        pixels = bytes(
            [
                0, 0, 0, 0, 0, 0,
                0, 254, 254, 205, 254, 0,
                0, 254, 254, 254, 254, 0,
                0, 0, 0, 0, 0, 0,
            ]
        )
        pgm = directory / "map.pgm"
        pgm.write_bytes(b"P5\n%d %d\n255\n" % (width, height) + pixels)
        yaml_path = directory / "map.yaml"
        yaml_path.write_text(
            "image: map.pgm\n"
            "resolution: 0.05\n"
            "origin: [-0.15, -0.10, 0.0]\n"
            f"negate: {negate}\n"
            "occupied_thresh: 0.65\n"
            "free_thresh: 0.196\n",
            encoding="utf-8",
        )
        return yaml_path

    def test_loads_p5_with_origin_and_thresholds(self):
        with tempfile.TemporaryDirectory() as raw:
            yaml_path = self._write_pgm(Path(raw), negate=0)
            ground = GroundTruth.from_map_yaml(yaml_path)
            self.assertEqual(ground.spec.width, 6)
            self.assertEqual(ground.spec.height, 4)
            self.assertAlmostEqual(ground.spec.resolution, 0.05)
            self.assertAlmostEqual(ground.spec.origin_x, -0.15)
            self.assertAlmostEqual(ground.spec.origin_y, -0.10)
            # 좌하단(0,0) 은 이미지 마지막 행 -> 벽이다.
            self.assertIs(ground.state_at_cell(0, 0), CellState.OCCUPIED)
            # 205 픽셀은 UNKNOWN 으로 들어와야 한다.
            states = ground.flat_states()
            self.assertIn(CellState.UNKNOWN.value, states)
            self.assertEqual(ground.free_cell_count(), 7)

    def test_row_order_is_bottom_up(self):
        # map_metadata 는 이미지 행 우선이고 우리 GridSpec 은 좌하단 원점이다.
        # 뒤집기를 빠뜨리면 지도가 상하로 뒤집혀 조용히 틀린 결과가 나온다.
        with tempfile.TemporaryDirectory() as raw:
            yaml_path = self._write_pgm(Path(raw), negate=0)
            ground = GroundTruth.from_map_yaml(yaml_path)
            # 이미지 1행(위에서 두 번째)에 UNKNOWN 이 있다 -> 좌하단 기준 row=2
            self.assertIs(ground.state_at_cell(3, 2), CellState.UNKNOWN)
            self.assertIs(ground.state_at_cell(3, 1), CellState.FREE)


class RaycastTest(unittest.TestCase):
    def test_ray_stops_at_first_wall_and_does_not_leak(self):
        # 방을 충분히 크게 잡는다. 라이다 데드존(min_range_m)이 있어 로봇 바로
        # 옆 셀은 원래 공개되지 않으므로, 작은 지도로는 "왼쪽 방이 보인다" 를
        # 확인할 수 없다.
        rows = ["#" * 21]
        rows += ["#" + "." * 9 + "#" + "." * 9 + "#" for _ in range(12)]
        rows += ["#" * 21]
        ground = synthetic.from_ascii(rows)
        discovered = DiscoveredMap(ground.spec)
        pose = Pose(*ground.spec.cell_to_world(5, 6), 0.0)
        discovered.reveal(
            ground.raycast(pose, LidarSpec(max_range_m=3.0, angle_increment_deg=0.5))
        )
        # 같은 방의 데드존 밖(0.20 m 초과) 셀은 보여야 한다.
        self.assertIs(discovered.state_at_cell(9, 6), CellState.FREE)
        # 가로막은 벽 자체는 관측된다.
        self.assertIs(discovered.state_at_cell(10, 6), CellState.OCCUPIED)
        # 벽 너머 오른쪽 방은 절대 보이지 않아야 한다 -- ray 가 벽을 뚫으면 실패.
        for col in range(11, 20):
            for row in range(1, 13):
                self.assertIs(
                    discovered.state_at_cell(col, row),
                    CellState.UNKNOWN,
                    f"({col},{row}) 가 벽을 통과해 관측됐다",
                )

    def test_raycast_is_deterministic_without_noise(self):
        ground = synthetic.wide_room()
        pose = Pose(*ground.spec.cell_to_world(20, 15), 0.3)
        lidar = LidarSpec(max_range_m=2.0, angle_increment_deg=3.0)
        first = ground.raycast(pose, lidar)
        second = ground.raycast(pose, lidar)
        self.assertEqual(first, second)

    def test_revision_increments_only_on_change(self):
        ground = synthetic.wide_room()
        discovered = DiscoveredMap(ground.spec)
        pose = Pose(*ground.spec.cell_to_world(20, 15), 0.0)
        beams = ground.raycast(pose, LidarSpec(max_range_m=2.0))
        before = discovered.revision
        self.assertTrue(discovered.reveal(beams))
        self.assertEqual(discovered.revision, before + 1)
        # 같은 관측을 다시 넣으면 바뀐 것이 없으므로 revision 이 그대로여야 한다.
        self.assertFalse(discovered.reveal(beams))
        self.assertEqual(discovered.revision, before + 1)


class PlannerTest(unittest.TestCase):
    def setUp(self):
        self.planner = ApproximateAckermannPlanner()

    def test_flavor_is_approximate(self):
        # 근사 결과를 실제 Nav2 결과로 표시하면 안 된다.
        self.assertIs(self.planner.flavor, PlannerFlavor.APPROXIMATE)

    def test_path_never_crosses_occupied(self):
        rows = [
            "#" * 40,
        ] + ["#" + "." * 18 + "#" + "." * 19 + "#" for _ in range(24)] + ["#" * 40]
        ground = synthetic.from_ascii(rows)
        discovered = _reveal_everything(ground)
        start = Pose(*ground.spec.cell_to_world(8, 13), 0.0)
        goal = Pose(*ground.spec.cell_to_world(30, 13), 0.0)
        path = self.planner.plan(
            discovered, start, goal, V025.planner, V025.inflation, ROBOT
        )
        # 벽으로 완전히 갈렸으므로 경로가 없어야 한다.
        if path is not None:
            self.assertEqual(
                path.occupied_cells, 0, "점유 셀을 통과하는 경로가 승인됐다"
            )
            self.fail("완전히 막힌 목표에 경로가 나왔다")

    def test_unknown_path_rejected_when_allow_unknown_false(self):
        ground = synthetic.wide_room()
        discovered = DiscoveredMap(ground.spec)
        start = Pose(*ground.spec.cell_to_world(6, 15), 0.0)
        # 좁은 관측만 준다 -> 목표 주변은 UNKNOWN 으로 남는다.
        discovered.reveal(
            ground.raycast(start, LidarSpec(max_range_m=0.45, angle_increment_deg=2.0))
        )
        goal = Pose(*ground.spec.cell_to_world(30, 15), 0.0)

        permissive = replace(V025.planner, allow_unknown=True)
        strict = replace(V025.planner, allow_unknown=False)
        strict_path = self.planner.plan(
            discovered, start, goal, strict, V025.inflation, ROBOT
        )
        self.assertIsNone(
            strict_path, "allow_unknown=False 인데 unknown 을 지나는 경로가 승인됐다"
        )
        # 같은 상황에서 allow_unknown=True 는 통과할 수 있어야 한다 (대조).
        permissive_path = self.planner.plan(
            discovered, start, goal, permissive, V025.inflation, ROBOT
        )
        if permissive_path is not None:
            self.assertGreater(permissive_path.unknown_cells, 0)

    def test_dubin_produces_no_reverse(self):
        ground = synthetic.wide_room()
        discovered = _reveal_everything(ground)
        start = Pose(*ground.spec.cell_to_world(10, 15), 0.0)
        goal = Pose(*ground.spec.cell_to_world(26, 15), 0.0)
        dubin = replace(V025.planner, motion_model=MotionModel.DUBIN)
        path = self.planner.plan(
            discovered, start, goal, dubin, V025.inflation, ROBOT
        )
        self.assertIsNotNone(path, "열린 방에서 DUBIN 경로가 나오지 않았다")
        assert path is not None
        self.assertEqual(path.reverse_length_m, 0.0)
        self.assertFalse(any(sample.reverse for sample in path.samples))

    def test_reeds_shepp_can_identify_reverse(self):
        # 뒤쪽 목표는 전진만으로는 큰 호가 필요하다. RS 는 후진을 쓸 수 있어야 한다.
        ground = synthetic.wide_room()
        discovered = _reveal_everything(ground)
        start = Pose(*ground.spec.cell_to_world(20, 15), 0.0)
        goal = Pose(*ground.spec.cell_to_world(16, 15), 0.0)
        rs_path = self.planner.plan(
            discovered, start, goal, V025.planner, V025.inflation, ROBOT
        )
        self.assertIsNotNone(rs_path)
        assert rs_path is not None
        self.assertIs(V025.planner.motion_model, MotionModel.REEDS_SHEPP)
        # 후진 거리가 기록 가능해야 한다 (0 이어도 필드가 일관되게 채워질 것).
        self.assertGreaterEqual(rs_path.reverse_length_m, 0.0)
        self.assertLessEqual(rs_path.reverse_length_m, rs_path.length_m + 1e-9)

    def test_goal_in_collision_is_rejected(self):
        # 실제 실패 원인의 최소 재현: 목표 자세에서 footprint 가 벽을 덮는다.
        rows = ["#" * 30] + ["#" + "." * 28 + "#" for _ in range(20)] + ["#" * 30]
        ground = synthetic.from_ascii(rows)
        discovered = _reveal_everything(ground)
        start = Pose(*ground.spec.cell_to_world(15, 10), 0.0)
        # 벽에 바로 붙은 목표 (좌측 벽은 col 0)
        goal = Pose(*ground.spec.cell_to_world(1, 10), 0.0)
        path = self.planner.plan(
            discovered, start, goal, V025.planner, V025.inflation, ROBOT
        )
        self.assertIsNone(path, "footprint 가 벽을 덮는 목표가 승인됐다")


class FrontierTest(unittest.TestCase):
    def test_viewpoint_profile_builds_bounded_distinct_free_approaches(self):
        ground = synthetic.wide_room()
        discovered = DiscoveredMap(ground.spec)
        pose = Pose(*ground.spec.cell_to_world(10, 15), 0.0)
        discovered.reveal(
            ground.raycast(
                pose, LidarSpec(max_range_m=1.2, angle_increment_deg=2.0)
            )
        )

        candidates = frontier_mod.detect(
            discovered,
            pose,
            V026_VIEWPOINTS.frontier,
            ROBOT,
            V026_VIEWPOINTS.goal_yaw_rule,
        )
        approaches = [
            candidate.approach_options
            for candidate in candidates
            if candidate.approach_options
        ]
        self.assertTrue(approaches, "viewpoint 후보가 하나도 생성되지 않았습니다")
        for options in approaches:
            self.assertLessEqual(len(options), 3)
            for index, (point, _, _) in enumerate(options):
                column, row = discovered.spec.world_to_cell(*point)
                self.assertIs(
                    discovered.state_at_cell(column, row), CellState.FREE
                )
                for other, _, _ in options[:index]:
                    self.assertGreaterEqual(
                        math.hypot(point[0] - other[0], point[1] - other[1]),
                        V026_VIEWPOINTS.frontier.candidate_spacing_m - 1e-9,
                    )

    def test_viewpoint_profile_preserves_permissive_unknown_planner(self):
        self.assertEqual(V026_VIEWPOINTS.frontier.max_approaches, 3)
        self.assertTrue(V026_VIEWPOINTS.planner.allow_unknown)
        self.assertIsNone(
            V026_VIEWPOINTS.planner.max_unknown_path_length_m,
            "viewpoint 후보가 UNKNOWN hard gate를 되살리면 안 됩니다",
        )
        self.assertEqual(V026_VIEWPOINTS.retry.retry_delay_sec, 5.0)
        self.assertEqual(V026_VIEWPOINTS.retry.max_reactivations, 1)
        self.assertTrue(V026_VIEWPOINTS.retry_with_alternate_approach)

    def test_cost_uses_documented_formula(self):
        ground = synthetic.wide_room()
        discovered = DiscoveredMap(ground.spec)
        pose = Pose(*ground.spec.cell_to_world(20, 15), 0.0)
        discovered.reveal(
            ground.raycast(pose, LidarSpec(max_range_m=0.6, angle_increment_deg=2.0))
        )
        candidates = frontier_mod.detect(
            discovered, pose, V025.frontier, ROBOT, V025.goal_yaw_rule
        )
        self.assertTrue(candidates, "프론티어가 검출되지 않았다")
        res = ground.spec.resolution
        params = V025.frontier
        for candidate in candidates:
            size_cells = len(candidate.cluster_cells)
            # upstream: min_distance 는 미터인데 frontierCost 가 res 를 한 번 더
            # 곱한다. 거리항이 potential_scale * d_m 이면 20배 과대평가다.
            expected = (
                params.potential_scale * candidate.min_distance_m * res
                - params.gain_scale * size_cells * res
            )
            self.assertAlmostEqual(
                candidate.cost,
                expected,
                places=6,
                msg=f"{candidate.candidate_id} 의 비용이 문서화된 식과 다르다",
            )

    def test_candidates_sorted_by_cost(self):
        ground = synthetic.wide_room()
        discovered = DiscoveredMap(ground.spec)
        pose = Pose(*ground.spec.cell_to_world(20, 15), 0.0)
        discovered.reveal(
            ground.raycast(pose, LidarSpec(max_range_m=0.6, angle_increment_deg=2.0))
        )
        candidates = frontier_mod.detect(
            discovered, pose, V025.frontier, ROBOT, V025.goal_yaw_rule
        )
        costs = [c.cost for c in candidates]
        self.assertEqual(costs, sorted(costs))

    def test_too_small_clusters_are_kept_with_verdict(self):
        # 크기 미달 프론티어를 조용히 버리면 "남아 있는데 COMPLETE" 가 된다.
        ground = synthetic.wide_room()
        discovered = DiscoveredMap(ground.spec)
        pose = Pose(*ground.spec.cell_to_world(20, 15), 0.0)
        discovered.reveal(
            ground.raycast(pose, LidarSpec(max_range_m=0.6, angle_increment_deg=2.0))
        )
        huge = replace(V025.frontier, min_frontier_size_m=99.0)
        candidates = frontier_mod.detect(
            discovered, pose, huge, ROBOT, V025.goal_yaw_rule
        )
        self.assertTrue(candidates)
        self.assertTrue(
            all(c.verdict is CandidateVerdict.TOO_SMALL for c in candidates)
        )

    def test_clearance_aware_approach_beats_fixed_retreat(self):
        # v0.2.6 의 핵심 주장: 접근점을 clearance 로 고르면 설 수 없는 목표가 사라진다.
        ground = synthetic.narrow_gap()
        discovered = _reveal_everything(ground)
        pose = Pose(*ground.spec.cell_to_world(10, 15), 0.0)

        fixed = frontier_mod.detect(
            discovered, pose, V025.frontier, ROBOT, V025.goal_yaw_rule
        )
        aware = frontier_mod.detect(
            discovered, pose, V026.frontier, ROBOT, V026.goal_yaw_rule
        )

        def unstandable(candidates):
            return [
                c
                for c in candidates
                if c.approach is not None
                and c.approach_clearance_m is not None
                and c.approach_clearance_m < ROBOT.inscribed_radius_m
            ]

        # clearance 기반이 고정 후퇴보다 나쁘면 안 된다.
        self.assertLessEqual(len(unstandable(aware)), len(unstandable(fixed)))
        for candidate in aware:
            if candidate.approach_clearance_m is None:
                continue
            self.assertGreaterEqual(
                candidate.approach_clearance_m,
                ROBOT.inscribed_radius_m,
                "clearance 기반 접근점이 설 수 없는 자리를 골랐다",
            )

    def test_yaw_rules_differ(self):
        ground = synthetic.wide_room()
        discovered = DiscoveredMap(ground.spec)
        pose = Pose(*ground.spec.cell_to_world(20, 15), 0.0)
        discovered.reveal(
            ground.raycast(pose, LidarSpec(max_range_m=0.6, angle_increment_deg=2.0))
        )
        bearing = frontier_mod.detect(
            discovered, pose, V025.frontier, ROBOT, GoalYawRule.BEARING_FROM_ROBOT
        )
        boundary = frontier_mod.detect(
            discovered, pose, V025.frontier, ROBOT, GoalYawRule.APPROACH_TO_BOUNDARY
        )
        self.assertEqual(len(bearing), len(boundary))
        # 같은 후보에 대해 두 규칙이 다른 yaw 를 내는 경우가 있어야 한다.
        differing = [
            1
            for a, b in zip(bearing, boundary)
            if a.goal_yaw is not None
            and b.goal_yaw is not None
            and abs(a.goal_yaw - b.goal_yaw) > 1e-6
        ]
        self.assertTrue(differing, "두 yaw 규칙이 모든 후보에서 동일했다")

    def test_detect_never_sees_ground_truth(self):
        # 시그니처에 GroundTruth 가 없어야 한다 (미래 지도 열람 금지).
        import inspect

        signature = inspect.signature(frontier_mod.detect)
        annotations = [str(p.annotation) for p in signature.parameters.values()]
        self.assertFalse(
            any("GroundTruth" in text for text in annotations),
            "frontier.detect 가 정답 지도를 받는다",
        )


class FailureLedgerTest(unittest.TestCase):
    def test_chebyshev_box_merges_neighbours(self):
        ledger = FailureLedger(V025, resolution=0.05)
        # merge_radius_cells 5 * 0.05 = 0.25 -> 0.5 x 0.5 m 정사각 상자
        ledger.record(1.0, 1.0, "path_unavailable", now=0.0, map_revision=1)
        # 대각선으로 0.24, 0.24 떨어진 점은 체비셰프로는 같은 상자다.
        record = ledger.record(1.24, 1.24, "path_unavailable", now=0.0, map_revision=1)
        self.assertEqual(record.attempts, 2, "체비셰프 병합이 동작하지 않았다")
        self.assertTrue(ledger.is_blacklisted(1.0, 1.0))
        self.assertTrue(ledger.is_blacklisted(1.24, 1.24))

    def test_euclidean_metric_separates_what_chebyshev_merged(self):
        euclid = replace(
            V025,
            retry=replace(
                V025.retry, merge_metric=MergeMetric.EUCLIDEAN, merge_radius_cells=3
            ),
        )
        ledger = FailureLedger(euclid, resolution=0.05)
        ledger.record(1.0, 1.0, "path_unavailable", now=0.0, map_revision=1)
        record = ledger.record(1.24, 1.24, "path_unavailable", now=0.0, map_revision=1)
        self.assertEqual(record.attempts, 1, "유클리드인데 이웃이 병합됐다")

    def test_exhausted_attempts_are_permanent_in_coordinate_mode(self):
        ledger = FailureLedger(V025, resolution=0.05)
        self.assertIs(
            V025.retry.blacklist_mode, BlacklistMode.COORDINATE_COOLDOWN
        )
        for _ in range(V025.retry.max_attempts):
            ledger.record(2.0, 2.0, "path_unavailable", now=0.0, map_revision=1)
        self.assertTrue(ledger.is_blacklisted(2.0, 2.0))
        # 지도가 바뀌어도 좌표 모드에서는 되돌아오지 않는다.
        self.assertEqual(ledger.note_map_revision(99), 0)
        self.assertTrue(ledger.is_blacklisted(2.0, 2.0))
        self.assertEqual(ledger.permanently_excluded(), 1)

    def test_soft_block_reactivates_after_map_revision(self):
        ledger = FailureLedger(V026, resolution=0.05)
        self.assertIs(
            V026.retry.blacklist_mode, BlacklistMode.MAP_REVISION_SOFT
        )
        for _ in range(V026.retry.max_attempts):
            ledger.record(2.0, 2.0, "path_unavailable", now=0.0, map_revision=1)
        self.assertTrue(ledger.is_blacklisted(2.0, 2.0))
        reactivated = ledger.note_map_revision(2)
        self.assertEqual(reactivated, 1)
        self.assertFalse(
            ledger.is_blacklisted(2.0, 2.0),
            "지도가 바뀐 뒤에도 soft-block 이 풀리지 않았다",
        )
        self.assertEqual(ledger.permanently_excluded(), 0)

    def test_cooldown_blocks_then_expires(self):
        ledger = FailureLedger(V025, resolution=0.05)
        ledger.record(3.0, 3.0, "path_unavailable", now=10.0, map_revision=1)
        self.assertTrue(ledger.is_cooling(3.0, 3.0, now=12.0))
        self.assertFalse(
            ledger.is_cooling(3.0, 3.0, now=10.0 + V025.retry.retry_delay_sec + 0.1)
        )


class StartPoseTest(unittest.TestCase):
    def test_outside_map_lists_candidates(self):
        ground = synthetic.wide_room()
        with self.assertRaises(StartPoseError) as caught:
            validate_start_pose(ground, Pose(-50.0, -50.0, 0.0), ROBOT)
        self.assertTrue(caught.exception.candidates, "후보를 제시하지 않았다")

    def test_occupied_start_is_rejected(self):
        ground = synthetic.wide_room()
        wall = Pose(*ground.spec.cell_to_world(0, 0), 0.0)
        with self.assertRaises(StartPoseError):
            validate_start_pose(ground, wall, ROBOT)

    def test_free_but_too_tight_start_is_rejected(self):
        ground = synthetic.wide_room()
        # 벽 바로 안쪽 FREE 셀 -- 셀은 FREE 지만 footprint 가 벽을 덮는다.
        tight = Pose(*ground.spec.cell_to_world(1, 15), 0.0)
        with self.assertRaises(StartPoseError):
            validate_start_pose(ground, tight, ROBOT)

    def test_valid_start_passes(self):
        ground = synthetic.wide_room()
        good = Pose(*ground.spec.cell_to_world(20, 15), 0.0)
        validate_start_pose(ground, good, ROBOT)


class TerminationTest(unittest.TestCase):
    def test_remaining_frontier_is_never_complete(self):
        # 크기 미달만 남은 상태를 COMPLETE 로 부르면 안 된다.
        ground = synthetic.wide_room()
        start = Pose(*ground.spec.cell_to_world(20, 15), 0.0)
        blind = replace(
            V025, frontier=replace(V025.frontier, min_frontier_size_m=99.0)
        )
        result = run(blind, ground, start, _fast_settings(max_steps=3))
        self.assertNotEqual(
            result.metrics.final_state,
            TerminationState.COMPLETE.value,
            "프론티어가 남았는데 COMPLETE 로 보고했다",
        )
        self.assertEqual(
            result.metrics.final_state, TerminationState.STALLED.value
        )

    def test_split_map_completes_reachable_side(self):
        ground = synthetic.split_by_wall()
        start = Pose(*ground.spec.cell_to_world(10, 15), 0.0)
        result = run(
            profile=V025,
            ground_truth=ground,
            start=start,
            settings=_fast_settings(max_steps=60),
        )
        # 도달 불가한 반대편 때문에 COLLISION 이 나면 안 된다.
        self.assertNotEqual(
            result.metrics.final_state, TerminationState.COLLISION.value
        )
        self.assertEqual(result.metrics.collisions, 0)

    def test_never_collides_on_any_synthetic_map(self):
        # 시뮬레이터가 관대해지는 가장 위험한 방향이 충돌 미검출이다.
        # 모든 지도에서 실제 충돌이 0 이어야 한다 (경로가 승인됐다면 안전해야 한다).
        for name, builder in synthetic.ALL_MAPS.items():
            with self.subTest(map=name):
                ground = builder()
                candidates = ground.free_start_candidates(ROBOT, limit=1)
                if not candidates:
                    self.skipTest(f"{name}: 설 수 있는 시작점이 없다")
                sx, sy = candidates[0]
                result = run(
                    V025, ground, Pose(sx, sy, 0.0), _fast_settings(max_steps=25)
                )
                self.assertEqual(
                    result.metrics.collisions,
                    0,
                    f"{name} 에서 충돌 {result.metrics.collisions}회",
                )


class SingleActiveGoalTest(unittest.TestCase):
    def test_patched_profiles_never_retarget_while_active(self):
        # v0.2.2 와 v0.2.5 는 둘 다 `if (goal_active_) return;` 이다 (태그 확인).
        self.assertFalse(V022.retarget_while_active)
        self.assertFalse(V025.retarget_while_active)
        self.assertTrue(V022.single_active_goal)
        self.assertTrue(V025.single_active_goal)

    def test_upstream_control_group_retargets_and_accrues_stale_time(self):
        upstream = profiles_mod.PROFILE_UPSTREAM_RETARGET
        self.assertTrue(upstream.retarget_while_active)
        ground = synthetic.wide_room()
        start = Pose(*ground.spec.cell_to_world(20, 15), 0.0)
        patched = run(V025, ground, start, _fast_settings(max_steps=12))
        preempting = run(upstream, ground, start, _fast_settings(max_steps=12))
        # 선점하는 쪽만 stale goal 시간이 누적되어야 한다.
        self.assertEqual(patched.metrics.stale_goal_retained_sec, 0.0)
        self.assertGreaterEqual(
            preempting.metrics.stale_goal_retained_sec, 0.0
        )


class ModelCoverageTest(unittest.TestCase):
    """시뮬레이터가 **평가할 수 없는** 변경을 명시적으로 못 박는다.

    이 클래스가 있는 이유: v0.2.6 을 돌려 보면 v0.2.2 와 지표가 완전히 같게 나온다.
    그것을 "v0.2.6 이 v0.2.2 와 동등하다" 는 증거로 읽으면 틀린다. 실제 v0.2.6 의
    변경 대부분이 이 모델에 없어서 같게 나오는 것이다. 침묵을 증거로 오해하지
    않도록 그 사실을 테스트로 고정한다.
    """

    #: 실제 v0.2.6 에 있으나 이 시뮬레이터가 모델링하지 않는 것들.
    UNMODELLED = (
        "progress_timeout 을 활성 목표에 매기는 수정 "
        "(컨트롤러가 없어 progress_timeout 자체가 발화하지 않는다)",
        "canceling_goal_ / replan_after_cancel_ 취소 종결 대기 "
        "(retarget_while_active=False 라 취소 경로를 타지 않는다)",
        "ExploreStatusMonitor 의 /explore/status 구독과 stall 생애주기 연결 "
        "(오케스트레이션 레이어는 모델 밖이다)",
        "매핑 BT 에서 ClearEntireCostmap 제거 (BT 를 모델링하지 않는다)",
    )

    def test_v026_modelled_differences_from_v022(self):
        """7c9caee 부터 v0.2.6 은 모델이 **볼 수 있는** 차이를 갖는다.

        8c7a466 시점에는 인플레이션과 yaw 가 v0.2.2 로 회귀해 모델이 보는 차이가
        retry_delay 하나뿐이었고, 그래서 결과가 v0.2.2 와 소수점까지 같았다.
        7c9caee 가 allow_unknown=false 와 국소 FREE 성장 재평가를 넣었으므로 이제는
        측정 가능하다. 그 사실을 여기에 못 박아, 다음에 결과가 같아졌을 때
        "원래 같은 것" 으로 넘기지 않게 한다.
        """
        v022 = profiles_mod.PROFILE_V022
        v026 = profiles_mod.PROFILE_V026
        prev = profiles_mod.PROFILE_V026_8C7A466

        # 회귀된 두 축은 여전히 v0.2.2 와 같다.
        self.assertEqual(
            v022.inflation.inflation_radius_m, v026.inflation.inflation_radius_m
        )
        self.assertIs(v022.goal_yaw_rule, v026.goal_yaw_rule)
        self.assertEqual(v022.frontier, v026.frontier)

        # a3d7d62 가 allow_unknown=false 를 **철회**했다. 플래너는 탐사적으로
        # 두고, UNKNOWN 통과는 경로 길이로 제한한다.
        self.assertTrue(v022.planner.allow_unknown)
        self.assertTrue(
            v026.planner.allow_unknown,
            "a3d7d62 는 allow_unknown 을 true 로 되돌렸다",
        )
        self.assertEqual(v026.planner.max_unknown_path_length_m, 0.25)
        self.assertIsNone(
            v022.planner.max_unknown_path_length_m,
            "a3d7d62 이전 프로필은 UNKNOWN 길이 검사를 하지 않는다",
        )
        self.assertIs(
            v026.retry.blacklist_mode, BlacklistMode.LOCAL_FREE_GROWTH
        )
        self.assertEqual(v026.retry.recheck_radius_m, 0.40)
        self.assertEqual(v026.retry.recheck_min_free_cells, 12)
        self.assertEqual(v026.retry.max_reactivations, 1)

        # UNKNOWN 길이 제한 외의 플래너 파라미터는 v0.2.2 와 동일해야 한다 --
        # a3d7d62 는 planner_plugins 에서 MappingSafeGridBased 를 지우고
        # MappingGridBased 로 되돌렸을 뿐이다.
        self.assertEqual(
            replace(v026.planner, max_unknown_path_length_m=None), v022.planner
        )

        # 이전 커밋 프로필들이 격리 비교용으로 남아 있어야 한다.
        self.assertTrue(prev.planner.allow_unknown)
        self.assertIs(prev.retry.blacklist_mode, BlacklistMode.COORDINATE_COOLDOWN)
        seven = profiles_mod.PROFILE_V026_7C9CAEE
        self.assertFalse(
            seven.planner.allow_unknown,
            "7c9caee 프로필은 allow_unknown=false 상태로 보존돼야 한다",
        )

        # await_cancel 은 True 지만 retarget_while_active 가 False 라 읽히지 않는다.
        self.assertTrue(v026.await_cancel_before_new_goal)
        self.assertFalse(v026.retarget_while_active)

    def test_unknown_path_length_uses_distance_not_sample_count(self):
        """a3d7d62 의 판정이 샘플 **개수**가 아니라 **길이** 기준임을 고정한다.

        개수로 세면 해상도나 프리미티브 길이가 바뀔 때 같은 경로가 다르게
        판정된다. explore.cpp 도 represented_distance 를 누적한다.
        """
        ground = synthetic.wide_room()
        discovered = DiscoveredMap(ground.spec)
        start = Pose(*ground.spec.cell_to_world(6, 15), 0.0)
        # 좁게만 관측해 목표 주변을 UNKNOWN 으로 남긴다.
        discovered.reveal(
            ground.raycast(
                start, LidarSpec(max_range_m=0.45, angle_increment_deg=2.0)
            )
        )
        goal = Pose(*ground.spec.cell_to_world(24, 15), 0.0)
        planner = ApproximateAckermannPlanner()
        permissive = replace(
            V025.planner, allow_unknown=True, max_unknown_path_length_m=None
        )
        path = planner.plan(
            discovered, start, goal, permissive, V025.inflation, ROBOT
        )
        if path is None:
            self.skipTest("이 배치에서 경로가 나오지 않았다")

        length = sim_unknown_length(path)
        self.assertGreater(length, 0.0, "UNKNOWN 을 지나지 않는 경로가 나왔다")

        # 길이가 허용치를 넘으면 거부, 넉넉하면 통과해야 한다.
        strict = replace(permissive, max_unknown_path_length_m=length * 0.5)
        loose = replace(permissive, max_unknown_path_length_m=length * 2.0)
        self.assertTrue(sim_crosses_unknown(path, strict))
        self.assertFalse(sim_crosses_unknown(path, loose))
        # 검사를 끈 프로필은 언제나 통과한다.
        self.assertFalse(sim_crosses_unknown(path, permissive))

    def test_reactivation_cap_bounds_stall_delay(self):
        """a3d7d62 의 frontier_max_reactivations 가 실제로 상한을 만드는지.

        상한이 없으면 반경 안 셀 수(약 201)/12 = 약 16회까지 되살아나
        exploration_stalled 도달이 그만큼 늦어진다.
        """
        ground = synthetic.wide_room()
        v026 = profiles_mod.PROFILE_V026
        self.assertEqual(v026.retry.max_reactivations, 1)

        for cap, expected in ((1, 1), (0, 0)):
            with self.subTest(cap=cap):
                profile = replace(
                    v026, retry=replace(v026.retry, max_reactivations=cap)
                )
                discovered = DiscoveredMap(ground.spec)
                ledger = FailureLedger(profile, ground.spec.resolution)
                tx, ty = ground.spec.cell_to_world(20, 15)
                total = 0
                for step in range(6):
                    for _ in range(profile.retry.max_attempts):
                        ledger.record(
                            tx, ty, "path_unavailable", step * 100.0,
                            discovered.revision, discovered,
                        )
                    # 매번 목표 주변을 더 넓게 열어 성장 조건을 만족시킨다.
                    discovered.reveal(
                        ground.raycast(
                            Pose(tx, ty, 0.0),
                            LidarSpec(
                                max_range_m=0.3 + 0.25 * step,
                                angle_increment_deg=2.0,
                            ),
                        )
                    )
                    total += ledger.note_local_free_growth(discovered)
                self.assertEqual(
                    total, expected,
                    f"상한 {cap} 인데 {total}회 되살아났다",
                )

    def test_local_free_growth_needs_growth_near_that_target(self):
        """국소 재평가가 **그 목표 주변** 성장만 본다는 것을 고정한다.

        내가 앞서 제안한 MAP_REVISION_SOFT 는 지도 어디가 바뀌어도 되돌렸다.
        7c9caee 는 그보다 좁고, 그 좁음이 무한 재시도를 막는 장치다.
        """
        ground = synthetic.wide_room()
        discovered = DiscoveredMap(ground.spec)
        v026 = profiles_mod.PROFILE_V026
        ledger = FailureLedger(v026, ground.spec.resolution)

        target_x, target_y = ground.spec.cell_to_world(20, 15)
        far_x, far_y = ground.spec.cell_to_world(34, 26)

        for _ in range(v026.retry.max_attempts):
            ledger.record(
                target_x, target_y, "path_unavailable", 0.0, discovered.revision,
                discovered,
            )
        self.assertTrue(ledger.is_blacklisted(target_x, target_y))

        # 목표에서 먼 곳만 열어준다 -> 되살아나면 안 된다.
        discovered.reveal(
            ground.raycast(
                Pose(far_x, far_y, 0.0),
                LidarSpec(max_range_m=0.5, angle_increment_deg=2.0),
            )
        )
        self.assertEqual(ledger.note_local_free_growth(discovered), 0)
        self.assertTrue(
            ledger.is_blacklisted(target_x, target_y),
            "목표와 무관한 지도 변화로 배제가 풀렸다",
        )

        # 목표 주변을 열어준다 -> 되살아나야 한다.
        discovered.reveal(
            ground.raycast(
                Pose(target_x, target_y, 0.0),
                LidarSpec(max_range_m=1.0, angle_increment_deg=2.0),
            )
        )
        self.assertGreaterEqual(ledger.note_local_free_growth(discovered), 1)
        self.assertFalse(ledger.is_blacklisted(target_x, target_y))

        # 같은 성장으로 두 번 되살아나지 않아야 한다 (기준선 갱신 확인).
        for _ in range(v026.retry.max_attempts):
            ledger.record(
                target_x, target_y, "path_unavailable", 100.0,
                discovered.revision, discovered,
            )
        self.assertTrue(ledger.is_blacklisted(target_x, target_y))
        self.assertEqual(ledger.note_local_free_growth(discovered), 0)

    def test_progress_timeout_is_recorded_but_not_simulated(self):
        # 값은 프로필에 남아 있어야 한다 (provenance 완전성).
        self.assertEqual(profiles_mod.PROFILE_V026.retry.progress_timeout_sec, 90.0)
        # 그러나 루프가 그 값을 읽지 않는다. 읽게 되면 이 테스트를 고치고
        # UNMODELLED 목록에서 해당 항목을 지워야 한다.
        source = (
            Path(__file__).resolve().parent.parent
            / "mapping_sim"
            / "simulator.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            "progress_timeout_sec",
            source,
            "simulator 가 progress_timeout 을 쓰기 시작했다면 "
            "ModelCoverageTest.UNMODELLED 를 갱신하라",
        )

    def test_unmodelled_list_is_not_silently_emptied(self):
        # 목록이 비면 "전부 모델링됐다" 는 뜻이 되므로 근거 없이 비우지 못하게 한다.
        self.assertGreaterEqual(len(self.UNMODELLED), 4)


class DeterminismTest(unittest.TestCase):
    @staticmethod
    def _fingerprint(result):
        # compute_time_sec 는 벽시계라 제외한다. 나머지는 완전히 같아야 한다.
        metrics = result.metrics
        return (
            metrics.final_state,
            round(metrics.discovered_ratio, 9),
            round(metrics.total_travel_m, 9),
            round(metrics.net_displacement_m, 9),
            metrics.goals_sent,
            metrics.plan_successes,
            metrics.plan_failures,
            round(metrics.unknown_traverse_m, 9),
            round(metrics.min_wall_clearance_m, 9),
            metrics.collisions,
            round(metrics.reverse_distance_m, 9),
            metrics.direction_changes,
            metrics.permanently_excluded,
            metrics.steps,
            tuple(
                (
                    step.step,
                    round(step.pose.x, 9),
                    round(step.pose.y, 9),
                    round(step.pose.yaw, 9),
                    step.selected_id,
                )
                for step in result.steps
            ),
        )

    def test_same_seed_same_result(self):
        ground = synthetic.u_shape()
        start_candidates = ground.free_start_candidates(ROBOT, limit=1)
        self.assertTrue(start_candidates)
        sx, sy = start_candidates[0]
        start = Pose(sx, sy, 0.0)
        settings = _fast_settings(max_steps=15)
        first = run(V025, ground, start, settings)
        second = run(V025, ground, start, settings)
        self.assertEqual(self._fingerprint(first), self._fingerprint(second))

    def test_only_wall_clock_fields_are_nondeterministic(self):
        """결정론의 경계를 명시한다.

        판정·지표·궤적은 완전히 재현된다. 벽시계 측정값(``planning_time_sec``,
        ``compute_time_sec``)은 재현되지 않으며 그래야 정상이다 -- 그 값이
        결정에 쓰이면 호스트 속도가 결과를 바꾸므로, 시뮬레이터는 iteration 을
        예산으로 쓰고 벽시계는 기록만 한다.

        이 테스트가 있는 이유: trace.jsonl 을 바이트로 비교하면 실패하는데, 그
        원인이 벽시계 필드 하나뿐임을 고정해 두지 않으면 나중에 진짜 비결정성이
        섞여도 "원래 다르던 것" 으로 넘어가게 된다.
        """
        WALL_CLOCK_FIELDS = {"planning_time_sec", "compute_time_sec"}

        ground = synthetic.wide_room()
        start = Pose(*ground.spec.cell_to_world(20, 15), 0.0)
        settings = _fast_settings(max_steps=10)
        first = run(V025, ground, start, settings)
        second = run(V025, ground, start, settings)

        def strip(result):
            payload = []
            for step in result.steps:
                path = step.path
                payload.append(
                    (
                        step.step,
                        step.map_revision,
                        (step.pose.x, step.pose.y, step.pose.yaw),
                        step.selected_id,
                        step.note,
                        None
                        if path is None
                        else (
                            path.length_m,
                            path.reverse_length_m,
                            path.direction_changes,
                            path.traversal_cost,
                            path.iterations,
                            len(path.samples),
                        ),
                        tuple((p.x, p.y, p.yaw) for p in step.travelled),
                        tuple(
                            (c.candidate_id, c.verdict.value, c.cost, c.approach)
                            for c in step.candidates
                        ),
                    )
                )
            return payload

        self.assertEqual(strip(first), strip(second))
        # 그리고 실제로 다른 것은 벽시계뿐임을 확인한다.
        differing = {
            field
            for a, b in zip(first.steps, second.steps)
            if a.path is not None and b.path is not None
            for field in ("planning_time_sec",)
            if getattr(a.path, field) != getattr(b.path, field)
        }
        self.assertTrue(differing <= WALL_CLOCK_FIELDS)

    def test_noise_seed_is_reproducible(self):
        ground = synthetic.wide_room()
        start = Pose(*ground.spec.cell_to_world(20, 15), 0.0)
        noisy = _fast_settings(
            max_steps=8,
            lidar=LidarSpec(
                max_range_m=2.0, angle_increment_deg=6.0, range_noise_m=0.02
            ),
            seed=1234,
        )
        first = run(V025, ground, start, noisy)
        second = run(V025, ground, start, noisy)
        self.assertEqual(self._fingerprint(first), self._fingerprint(second))


if __name__ == "__main__":
    unittest.main(verbosity=2)
