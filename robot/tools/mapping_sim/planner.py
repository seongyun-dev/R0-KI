"""경로계획 backend. **근사 플래너와 실제 Nav2 를 절대 섞지 않는다.**

이 모듈은 backend 두 개를 제공한다.

``ApproximateAckermannPlanner``
    자체 SE2 격자 탐색(hybrid A* 계열). Nav2 ``SmacPlannerHybrid`` 와 **같은 비용식**
    (``NodeHybrid::getTraversalCost``) 을 쓰지만 같은 구현이 아니다. 결과에는 항상
    ``PlannerFlavor.APPROXIMATE`` 가 붙는다. 이 값을 실제 Nav2 결과로 읽으면 안 된다.

``Nav2ActionPlanner``
    ``ComputePathToPose`` 를 실호출하는 backend. ROS 2 환경이 없으면 생성 시
    ``RuntimeError`` 다. **자동 폴백은 없다** -- 근사 결과를 실측으로 표시하는 것이
    이 프로젝트에서 가장 하지 말아야 할 일이라서 그렇게 두었다.

지도 분리 불변식
----------------
plan() 은 ``DiscoveredMap`` 만 받는다. ``GroundTruth`` 를 받을 수 있는 인자가 아예
없으므로 "미래 지도를 미리 보고 경로를 고르는" 코드는 여기서 작성 자체가 불가능하다.
충돌 판정도 발견 지도 기준이며(계획은 아는 것만으로 한다), 실제 충돌은 시뮬레이터가
정답 지도로 따로 판정한다.

발견 지도에 기대는 표면
-----------------------
``worldmodel.DiscoveredMap`` 의 다음 네 가지만 쓴다::

    discovered.spec                                 -> GridSpec
    discovered.state_at_world(x, y)                 -> CellState
    discovered.inflation_cost_at_world(x, y, inflation, robot)          -> int
    discovered.footprint_collides(pose, robot, unknown_is_obstacle=...) -> bool

지도 밖 좌표는 조회에 관대하고(state 는 UNKNOWN, 비용은 LETHAL) 판정에 엄격하다
(footprint 는 충돌). 그것이 지도 쪽 계약이라 여기서 경계 방어코드를 따로 두지 않는다.
"""

from __future__ import annotations

import heapq
import math
import time
from typing import TYPE_CHECKING, Protocol

from .contracts import (
    COST_INFLATION_CEILING,
    CellState,
    InflationSpec,
    PathSample,
    PlannedPath,
    PlannerFlavor,
    PlannerParams,
    Pose,
    RobotSpec,
    normalize_angle,
)

if TYPE_CHECKING:  # 런타임 import 를 하지 않는다. import 부작용 금지 + 순환 회피.
    from .worldmodel import DiscoveredMap


# 벽시계 예산을 몇 번의 확장마다 확인할지. 매 확장마다 time.monotonic() 을 부르면
# 그 자체가 탐색 시간을 왜곡한다. 예산의 1차 기준은 iteration 수이고 벽시계는
# 폭주 방지용이라(ApproximateAckermannPlanner.plan 주석 참조) 이 정도 간격으로 봐도
# 충분하다.
_TIME_CHECK_INTERVAL = 512

# 벽시계 상한. `params.max_planning_time_sec` (3.5) 는 C++ Nav2 를 위한 값이라
# 순수 파이썬 backend 의 성패 기준으로 쓰면 호스트 속도가 결과를 바꾼다 -- 도달
# 가능한 목표가 느린 기계에서만 PATH_UNAVAILABLE 로 기록되고, 그러면 프로필 비교가
# 오염된다. 이 도구의 존재 이유가 재현 가능한 비교이므로 결정 요인은 iteration
# 예산이고, 벽시계는 무한 루프만 막는다.
_WALL_CLOCK_GUARD_SEC = 600.0


def _bins_per_primitive(
    radius: float, bin_rad: float, bins: int, resolution: float
) -> int:
    """현(chord)이 sqrt(2)*해상도 이상이 되는 최소 bin 수.

    Nav2 ``MotionTable::initDubin`` 과 같은 규칙이다. 프리미티브 하나가 현재 셀을
    반드시 벗어나게 만들어, 끝점이 같은 (셀, bin) 이 되어 버려지는 일을 막는다.
    """
    minimum_chord = math.sqrt(2.0) * resolution
    for count in range(1, max(2, bins)):
        if 2.0 * radius * math.sin(count * bin_rad / 2.0) >= minimum_chord:
            return count
    return 1


class PlannerBackend(Protocol):
    """시뮬레이터가 보는 플래너 인터페이스.

    ``flavor`` 를 프로토콜에 넣지 않은 이유: flavor 는 결과물인 ``PlannedPath`` 가
    직접 들고 다니므로(계약상 필수 필드) 리포트는 경로에서 읽으면 된다. 인터페이스를
    좁게 두면 다른 backend 를 끼우기가 쉽다.
    """

    def plan(self, discovered: DiscoveredMap, start: Pose, goal: Pose,
             params: PlannerParams, inflation: InflationSpec,
             robot: RobotSpec) -> PlannedPath | None: ...


class ApproximateAckermannPlanner:
    """SE2 격자 탐색. Nav2 SmacPlannerHybrid 와 **같은 비용식**을 쓰지만 같은 구현이 아니다.

    같은 것: traversal cost 식(아래 ``_traversal_cost`` 주석에 원문 인용), 상태를
    (셀, 각도 bin) 으로 이산화하는 방식, 최소회전반경만으로 만든 모션 프리미티브.

    다른 것: Nav2 는 analytic expansion(Reeds-Shepp 해석해로 목표에 직결), 미리 계산한
    obstacle/distance 휴리스틱, 경로 스무딩을 함께 쓴다. 여기에는 그 세 가지가 없다.
    그래서 경로 길이는 Nav2 보다 몇 % 길게 나오는 것이 정상이며, 이 결과는
    ``PlannerFlavor.APPROXIMATE`` 로만 보고된다.

    이 backend 의 목적은 "Nav2 길이를 예측하는 것"이 아니라 **목표 자세가 애초에
    도달 가능한지**를 프로필별로 같은 규칙으로 판정하는 것이다. 2026-08-12 실측에서
    실패의 실제 원인은 경로 품질이 아니라 목표 자세의 footprint 충돌이었다.

    비용 특성 (CPython 3.12, 해상도 0.05 m, bins 64, 빈 방, 직선 목표 실측):

        1.0 m ->    424 확장 / 0.06 s        3.5 m -> 21432 확장 / 3.4 s
        2.0 m ->   3928 확장 / 0.59 s        4.0 m -> 33742 확장 / 4.9 s
        3.0 m ->  14746 확장 / 2.1 s         5.0 m -> 61622 확장 / 8.9 s

    확장 수가 거리에 대해 급히 자라는 것은 휴리스틱이 순수 유클리드라서다. 실제
    경로 비용은 선회 페널티(1.2) 때문에 길이의 1.2 배 가까이 되는데 휴리스틱은
    길이만 보므로, 목표 비용보다 f 가 작은 상태를 전부 열게 된다. 이를 줄이려면
    휴리스틱을 부풀려야 하고 그러면 최적성이 깨진다(``_heuristic_scale`` 주석 참조).

    **그래서 프로필의 max_planning_time_sec 3.5 를 그대로 쓰면 목표 3.5 m 가
    3.4 s 로 간신히 통과하고 4.0 m 부터 실패한다.** 그 값은 실물 로봇(C++ Nav2)용
    이고 이 backend 는 파이썬이다. 게다가 같은 입력·같은 확장수(424)의 벽시계가
    실측에서 0.062~0.078 s 로 흔들렸다. 즉 3.4 s 짜리 계획은 호스트 상태에 따라
    성공과 실패가 갈린다. 시뮬레이터 쪽에서 이 값을 넉넉히(예: 600 s) 덮어써야
    벽시계가 아니라 iteration 예산이 결정 요인이 되고, 그래야 같은 입력이 같은
    결과를 낸다. 덮어쓰지 않으면 호스트가 느릴 때만 나타나는 가짜
    PATH_UNAVAILABLE 이 프로필 비교를 오염시킨다.
    """

    flavor = PlannerFlavor.APPROXIMATE

    def __init__(self) -> None:
        # 마지막 plan() 이 예산 소진으로 끝났는지. 예산을 넘긴 탐색은 "계획 성공"이
        # 아니므로 timed_out=True 인 PlannedPath 를 만들지 않고 None 을 돌려준다.
        # 그러면 호출자가 "경로 없음"과 "시간 부족"을 구분할 수 없어 여기로 알린다.
        self.last_timeout = False

    def plan(
        self,
        discovered: DiscoveredMap,
        start: Pose,
        goal: Pose,
        params: PlannerParams,
        inflation: InflationSpec,
        robot: RobotSpec,
    ) -> PlannedPath | None:
        # inflation 과 robot 은 발견 지도의 inflation_cost_at_world 로 그대로 넘어간다.
        # 비용을 여기서 다시 계산하지 않는 이유: 지도가 셀 단위로 캐시하고 있고, 같은
        # 값을 두 곳에서 계산하면 어긋났을 때 어느 쪽이 진실인지 알 수 없게 된다.
        self.last_timeout = False
        started = time.monotonic()

        spec = discovered.spec
        unknown_is_obstacle = not params.allow_unknown
        # 요구사항: 해상도의 절반 이하 간격. 얇은 벽을 프리미티브가 뛰어넘지 못하게.
        sample_step = spec.resolution / 2.0

        # 목표 자세 검사를 탐색보다 **먼저** 한다. 이 프로젝트의 실제 실패 원인이
        # "목표 좌표의 셀은 FREE 인데 그 yaw 에서 footprint 가 벽을 덮는다" 였고
        # (2026-08-12: 목표 (1.373,0.137), 최근접 점유셀 0.180 m -- inscribed 0.135 와
        # circumscribed 0.229 사이라 특정 자세에서만 충돌), 그 경우 탐색은 예산을
        # 전부 태운 뒤 실패한다. 먼저 걸러야 실패 이유가 로그에 남는다.
        if discovered.footprint_collides(
            goal, robot, unknown_is_obstacle=unknown_is_obstacle
        ):
            return None

        bins = max(1, int(params.angle_quantization_bins))
        bin_rad = 2.0 * math.pi / bins
        radius = robot.min_turning_radius_m
        # 한 프리미티브는 반드시 현재 셀을 벗어나야 한다. bin 하나(0.0335 m)만
        # 돌게 잡으면 해상도 0.05 m 보다 짧아서, 직진은 yaw 가 안 바뀌므로 끝점이
        # 같은 (셀, bin) 이 되어 자기전이로 버려진다. 그러면 그 노드에서 선회만
        # 남아 탐색이 강제로 지그재그가 된다.
        #
        # Nav2 MotionTable::initDubin 과 같은 규칙으로 bin 수를 고른다:
        # 현(chord) 2R*sin(n*bin/2) 이 sqrt(2)*해상도 이상이 되는 최소 n.
        # 이 로봇 값(R=0.341, bin=2pi/64, res=0.05)에서는 n=3 -> arc 0.1004 m.
        turn_bins = _bins_per_primitive(radius, bin_rad, bins, spec.resolution)
        arc = radius * turn_bins * bin_rad
        primitives = _motion_primitives(params)
        heuristic_scale = _heuristic_scale(params)

        start_col, start_row = spec.world_to_cell(start.x, start.y)
        goal_col, goal_row = spec.world_to_cell(goal.x, goal.y)
        if (start_col, start_row) == (goal_col, goal_row) and _angle_bin(
            start.yaw, bins, bin_rad
        ) == _angle_bin(goal.yaw, bins, bin_rad):
            # 출발과 목표가 **같은 셀·같은 각도 bin** 일 때만 이동 0 경로를 낸다.
            # Nav2 의 trivial-path 예외도 같은 셀 조건이다.
            #
            # 여기서 tolerance_m(0.20) 를 조건으로 쓰면 안 된다. 해상도 0.05 에서
            # 0.20 m 는 4 셀이고, 그 거리의 목표는 Nav2 가 실제로 경로를 만들어
            # 주행한다. tolerance 로 단락시키면 프론티어 목표 상당수가 "이미 도착"
            # 으로 처리되어 로봇이 한 번도 움직이지 않는 가짜 교착이 생긴다.
            # tolerance 는 탐색 중 목표 도달 판정에만 쓴다(아래 루프).
            return _single_pose_path(
                discovered,
                start,
                self.flavor,
                time.monotonic() - started,
                inflation,
                robot,
            )
        start_key = (start_col, start_row, _angle_bin(start.yaw, bins, bin_rad))
        goal_key = (goal_col, goal_row, _angle_bin(goal.yaw, bins, bin_rad))
        # tolerance 안에 들어온 노드 중 목표에 가장 가까운 것. 정확한 목표 노드에
        # 닿지 못한 채 예산이 끝나면 이 노드까지의 경로를 돌려준다 (Nav2 의
        # best_heuristic_node 폴백과 같은 역할).
        fallback_key: tuple[int, int, int] | None = None
        fallback_distance = float("inf")
        # key -> (자세, 부모 key, 진입 프리미티브의 steer, 진입 프리미티브가 후진인지).
        # 시작 노드의 steer 는 None = "직전 동작이 없음" 이고, 첫 프리미티브에는
        # change 페널티가 붙지 않는다 (Nav2 도 첫 노드에 motion prior 가 없다).
        records: dict[
            tuple[int, int, int],
            tuple[Pose, tuple[int, int, int] | None, int | None, bool],
        ] = {start_key: (start, None, None, False)}
        best_cost: dict[tuple[int, int, int], float] = {start_key: 0.0}
        closed: set[tuple[int, int, int]] = set()
        # (f, 삽입순번, key). 삽입순번을 넣어 동점일 때 순서가 결정론적이 된다 --
        # 프로필 비교 도구라서 같은 입력이면 같은 경로가 나와야 한다.
        queue: list[tuple[float, int, tuple[int, int, int]]] = [
            (
                heuristic_scale * math.hypot(goal.x - start.x, goal.y - start.y),
                0,
                start_key,
            )
        ]
        sequence = 1
        iterations = 0

        def _finish_with_fallback() -> PlannedPath | None:
            """정확한 목표 노드에 못 닿았을 때 tolerance 안 최선 노드로 마무리.

            Nav2 AStarAlgorithm 의 ``_best_heuristic_node`` 폴백과 같은 역할이다.
            시작 노드도 후보에 포함되지만, 목표에 더 가까워진 노드가 하나라도
            있으면 그쪽이 이기므로 진행이 가능한 상황에서 이동 0 경로가 나오지는
            않는다.
            """
            if fallback_key is None:
                return None
            return _build_path(
                discovered=discovered,
                records=records,
                goal_key=fallback_key,
                traversal_cost=best_cost[fallback_key],
                flavor=self.flavor,
                arc=arc,
                radius=radius,
                sample_step=sample_step,
                iterations=iterations,
                elapsed=time.monotonic() - started,
                inflation=inflation,
                robot=robot,
            )

        while queue:
            # 예산은 iteration 이 1차 기준이다. 시뮬레이터는 실시간이 아니므로
            # max_planning_time_sec 를 그대로 쓰면 호스트 속도에 따라 같은 입력이
            # 다른 결과를 낸다(= 프로필 비교가 무의미해진다). 벽시계는 폭주를 막는
            # 안전장치로만 쓴다.
            if iterations >= params.max_iterations:
                self.last_timeout = True
                return _finish_with_fallback()
            if iterations and iterations % _TIME_CHECK_INTERVAL == 0:
                if time.monotonic() - started > _WALL_CLOCK_GUARD_SEC:
                    self.last_timeout = True
                    return _finish_with_fallback()

            _, _, key = heapq.heappop(queue)
            if key in closed:
                continue
            closed.add(key)
            iterations += 1

            pose, _parent, prior_steer, _reverse = records[key]
            # 목표 판정은 pop 시점에 한다. 생성 시점에 판정하면 최초로 발견한 경로가
            # 최소비용 경로가 아닐 수 있다.
            #
            # 도달 판정은 **정확한 (셀, 각도 bin) 일치** 다. Nav2 AStarAlgorithm::
            # isGoal 도 노드 인덱스 동일성으로 판정하고, tolerance 는 그 목표에
            # 못 닿았을 때의 **폴백**(best_heuristic_node) 으로만 쓴다.
            #
            # 여기서 tolerance 를 도달 조건으로 쓰면 시작 노드가 큐에서 가장 먼저
            # 나오면서 곧바로 "도달" 로 판정돼 이동 0 경로가 나온다. 그러면 로봇이
            # 영원히 움직이지 않는 가짜 교착이 만들어진다 -- 실제 Nav2 는 그 거리의
            # 목표에 경로를 만들어 주행한다.
            distance_to_goal = math.hypot(goal.x - pose.x, goal.y - pose.y)
            if distance_to_goal <= params.tolerance_m and (
                fallback_key is None or distance_to_goal < fallback_distance
            ):
                fallback_key = key
                fallback_distance = distance_to_goal
            if key == goal_key:
                return _build_path(
                    discovered=discovered,
                    records=records,
                    goal_key=key,
                    traversal_cost=best_cost[key],
                    flavor=self.flavor,
                    arc=arc,
                    radius=radius,
                    sample_step=sample_step,
                    iterations=iterations,
                    elapsed=time.monotonic() - started,
                    inflation=inflation,
                    robot=robot,
                )

            cost_here = best_cost[key]
            for steer, reverse in primitives:
                # 검사 순서는 싼 것부터다. footprint 충돌검사는 프리미티브 하나마다
                # 여러 자세 x 여러 셀의 SAT 라서 이 루프에서 가장 비싸고, 어차피
                # 버릴 간선에 그 비용을 쓰면 벽시계 예산이 iteration 예산보다 먼저
                # 소진된다 (= 호스트 속도가 결과를 바꾼다). 그래서 격자 범위,
                # closed, 비용 하한으로 먼저 걸러낸 뒤에만 충돌검사를 한다.
                # 걸러진 간선은 기록되지도 사용되지도 않으므로 결과는 동일하다.
                end = _advance(pose, steer, -arc if reverse else arc, radius)
                col, row = spec.world_to_cell(end.x, end.y)
                if not spec.contains(col, row):
                    continue  # 격자 밖은 지도가 아니다. 무한 공간으로 새는 것을 막는다.
                next_key = (col, row, _angle_bin(end.yaw, bins, bin_rad))
                # next_key == key 인 자기전이(한 bin 의 호가 셀·bin 을 못 벗어난 경우)는
                # key 가 이미 closed 이므로 여기서 걸러진다. 그 결과 셀 안에서의 짧은
                # 직진은 가끔 버려지고 대신 선회로 우회한다 -- 격자 플래너의 알려진
                # 이산화 손실이며, 그래서 이 backend 는 APPROXIMATE 다.
                if next_key in closed:
                    continue
                travel = _traversal_cost(
                    params=params,
                    primitive_length=arc,
                    inflation_cost=_inflation_cost(
                        discovered, end.x, end.y, inflation, robot
                    ),
                    steer=steer,
                    reverse=reverse,
                    prior_steer=prior_steer,
                )
                tentative = cost_here + travel
                if tentative >= best_cost.get(next_key, math.inf):
                    continue
                # 프리미티브의 **모든** 샘플 자세를 검사한다. 끝점만 보면 벽을
                # 스쳐 지나가는 호가 통과한다. 시작 자세(s=0)는 검사하지 않는다 --
                # 그건 이미 도달한 사실이고, 로봇이 서 있는 자리를 근거로 모든
                # 이동을 막으면 인플레이션에 살짝 걸친 상태에서 영원히 못 움직인다.
                if any(
                    discovered.footprint_collides(
                        sample, robot, unknown_is_obstacle=unknown_is_obstacle
                    )
                    for sample in _sample_primitive(
                        pose, steer, reverse, arc, radius, sample_step
                    )
                ):
                    continue
                best_cost[next_key] = tentative
                records[next_key] = (end, key, steer, reverse)
                heapq.heappush(
                    queue,
                    (
                        tentative
                        + heuristic_scale
                        * math.hypot(goal.x - end.x, goal.y - end.y),
                        sequence,
                        next_key,
                    ),
                )
                sequence += 1

        # 큐가 비었다 = 도달 가능한 상태를 다 봤는데 정확한 목표 노드가 없다.
        # tolerance 안에 들어온 노드가 있었다면 그쪽으로 마무리한다. 예산 소진과
        # 구분되게 last_timeout 은 False 로 남긴다.
        return _finish_with_fallback()


class Nav2ActionPlanner:
    """ComputePathToPose 를 실제로 호출하는 backend. ROS 환경이 없으면 생성 시 실패한다.

    폴백이 없는 것이 이 클래스의 요점이다. 근사 결과에 ``NAV2_ACTUAL`` 을 붙이면
    리포트 전체가 거짓이 되므로, ROS 가 없으면 생성 자체를 거부한다.
    """

    flavor = PlannerFlavor.NAV2_ACTUAL

    def __init__(
        self,
        action_name: str = "compute_path_to_pose",
        planner_id: str = "MappingGridBased",
    ) -> None:
        try:
            # 지연 import: 이 모듈을 import 하는 것만으로 ROS 를 끌어오면 안 된다.
            import rclpy  # noqa: F401
            from nav2_msgs.action import ComputePathToPose  # noqa: F401
        except ImportError as error:
            raise RuntimeError(
                "Nav2ActionPlanner 는 ROS 2 환경에서만 쓸 수 있다 "
                "(rclpy / nav2_msgs 없음). 근사 플래너로 자동 대체하지 않는다 -- "
                "근사 결과를 NAV2_ACTUAL 로 표시하면 안 되기 때문이다. "
                "젯슨에서 실행하거나 default_backend() 를 쓸 것."
            ) from error
        self._action_name = action_name
        self._planner_id = planner_id
        # 근사 플래너와 같은 자리에 같은 뜻으로 둔다 (서버 응답 없음 = 예산 초과).
        self.last_timeout = False

    def plan(
        self,
        discovered: DiscoveredMap,
        start: Pose,
        goal: Pose,
        params: PlannerParams,
        inflation: InflationSpec,
        robot: RobotSpec,
    ) -> PlannedPath | None:
        # robot / inflation / tolerance_m 을 Nav2 에 **보내지 않는다.** 실제 Nav2 는
        # 자기 costmap·자기 footprint·자기 planner_server 파라미터로 계획하고, 시뮬레이터
        # 쪽 값을 밀어넣으면 그건 "실제 Nav2 결과"가 아니게 된다 (ComputePathToPose 에
        # tolerance 필드도 없다). robot 과 inflation 은 돌려받은 경로의 각 샘플에
        # 우리 지도 기준 상태·비용을 **주석처럼 붙이는** 용도로만 쓴다. 그래야 두
        # backend 의 PlannedPath 를 같은 축으로 비교할 수 있다.
        import rclpy
        from geometry_msgs.msg import PoseStamped
        from nav2_msgs.action import ComputePathToPose
        from rclpy.action import ActionClient
        from rclpy.node import Node

        self.last_timeout = False
        started = time.monotonic()

        def remaining() -> float:
            return max(0.0, params.max_planning_time_sec - (time.monotonic() - started))

        # 이미 초기화된 컨텍스트를 쓰고 있으면 건드리지 않는다. 남의 노드를 죽이지 않기.
        context_owned = not rclpy.ok()
        if context_owned:
            rclpy.init()
        node = Node("mapping_sim_compute_path_to_pose")
        client = ActionClient(node, ComputePathToPose, self._action_name)
        try:
            if not client.wait_for_server(timeout_sec=remaining()):
                self.last_timeout = True
                return None

            request = ComputePathToPose.Goal()
            stamp = node.get_clock().now().to_msg()
            request.start = _pose_stamped(PoseStamped, start, stamp)
            request.goal = _pose_stamped(PoseStamped, goal, stamp)
            request.planner_id = self._planner_id
            request.use_start = True

            send_future = client.send_goal_async(request)
            rclpy.spin_until_future_complete(
                node, send_future, timeout_sec=remaining()
            )
            handle = send_future.result()
            if handle is None:
                self.last_timeout = True
                return None
            if not handle.accepted:
                return None

            result_future = handle.get_result_async()
            rclpy.spin_until_future_complete(
                node, result_future, timeout_sec=remaining()
            )
            outcome = result_future.result()
            if outcome is None:
                self.last_timeout = True
                return None
            return _path_from_msg(
                discovered,
                outcome.result.path,
                self.flavor,
                time.monotonic() - started,
                inflation,
                robot,
            )
        finally:
            client.destroy()
            node.destroy_node()
            if context_owned:
                rclpy.shutdown()


def default_backend() -> PlannerBackend:
    """ApproximateAckermannPlanner 를 돌려준다.

    ROS 가 보이면 Nav2 로 갈아타는 식의 "똑똑한" 선택을 하지 않는다. 같은 명령이
    환경에 따라 다른 flavor 를 내면 리포트끼리 비교할 수 없게 된다.
    """
    return ApproximateAckermannPlanner()


# ---------------------------------------------------------------------------
# 발견 지도 접근 -- 지도 API 에 의존하는 곳을 여기 두 함수로 모아 둔다.
# ---------------------------------------------------------------------------


def _inflation_cost(
    discovered: DiscoveredMap,
    x: float,
    y: float,
    inflation: InflationSpec,
    robot: RobotSpec,
) -> int:
    """인플레이션 비용. 지도가 셀 단위로 캐시하므로 여기서 따로 캐시하지 않는다.

    지도가 InflationSpec 과 RobotSpec 을 인자로 받는다(inscribed 반경이 필요하다).
    그래서 plan() 이 받은 ``inflation`` 은 쓰이지 않는 인자가 아니라 여기로 흘러간다.
    """
    return int(discovered.inflation_cost_at_world(x, y, inflation, robot))


# ---------------------------------------------------------------------------
# 모션 프리미티브와 비용
# ---------------------------------------------------------------------------


def _motion_primitives(params: PlannerParams) -> tuple[tuple[int, bool], ...]:
    """(steer, reverse) 목록. steer 는 +1 좌선회 / 0 직진 / -1 우선회.

    호길이와 곡률은 모두 최소회전반경 하나로 정해지므로 여기서는 조향 부호와 진행
    방향만 고른다. DUBIN 이면 후진 프리미티브를 **아예 만들지 않는다** -- 나중에
    걸러내는 방식은 "만들었지만 안 쓴다"는 상태를 남기고, 결과 경로의 후진 구간이
    0 이라는 보장을 코드에서 읽을 수 없게 만든다.
    """
    forward: tuple[tuple[int, bool], ...] = ((0, False), (1, False), (-1, False))
    if not params.motion_model.allows_reverse:
        return forward
    return forward + ((0, True), (1, True), (-1, True))


def _advance(pose: Pose, steer: int, signed_length: float, radius: float) -> Pose:
    """부호 있는 호길이만큼 나아간 자세. signed_length < 0 이면 후진.

    자전거 모델의 정확한 호 적분을 쓴다 (오일러 근사는 반경 0.341 m 처럼 작은
    회전반경에서 반경을 눈에 띄게 키운다).
    """
    if steer == 0:
        return Pose(
            pose.x + signed_length * math.cos(pose.yaw),
            pose.y + signed_length * math.sin(pose.yaw),
            pose.yaw,
        )
    curvature = steer / radius
    delta = curvature * signed_length
    return Pose(
        pose.x + (math.sin(pose.yaw + delta) - math.sin(pose.yaw)) / curvature,
        pose.y - (math.cos(pose.yaw + delta) - math.cos(pose.yaw)) / curvature,
        normalize_angle(pose.yaw + delta),
    )


def _sample_primitive(
    pose: Pose,
    steer: int,
    reverse: bool,
    arc: float,
    radius: float,
    sample_step: float,
) -> list[Pose]:
    """프리미티브를 sample_step 이하 간격으로 쪼갠 자세들. 시작 자세는 넣지 않는다.

    시작 자세를 빼는 이유는 두 가지다. (1) 이미 검사·기록된 자세라 중복이다.
    (2) 경로 샘플에서 이음매마다 같은 자세가 두 번 나오면 시뮬레이터의 구간 길이
    합산에 0 짜리 구간이 끼어 통계가 지저분해진다.

    마지막 샘플은 ``arc * count / count`` 대신 ``arc`` 를 그대로 쓴다. 탐색은 노드
    자세를 ``_advance(pose, steer, arc)`` 로 따로 구하고 경로 복원은 이 함수로
    다시 구하는데, 두 값이 1 ULP 만 달라도 셀 경계에서 상태 키와 기록된 기하가
    엇갈릴 수 있다. 같은 식으로 계산해 그 가능성을 없앤다.
    """
    count = max(1, int(math.ceil(arc / sample_step)))
    poses: list[Pose] = []
    for index in range(1, count + 1):
        length = arc if index == count else arc * index / count
        poses.append(_advance(pose, steer, -length if reverse else length, radius))
    return poses


def _angle_bin(yaw: float, bins: int, bin_rad: float) -> int:
    return int(round(normalize_angle(yaw) / bin_rad)) % bins


def _traversal_cost(
    *,
    params: PlannerParams,
    primitive_length: float,
    inflation_cost: int,
    steer: int,
    reverse: bool,
    prior_steer: int | None,
) -> float:
    """Nav2 ``NodeHybrid::getTraversalCost`` 와 **같은 식**. 구현은 다르다.

    인용한 식은 다음과 같다::

        normalized = inflation_cost / 252            (0..1 로 클램프)
        raw = primitive_length * (1 + cost_penalty * normalized)
        if 직진이고 방향전환 없음:  travel = raw
        else:                       travel = raw * (change_penalty * changed
                                                    + non_straight_penalty)
        if 후진:                    travel *= reverse_penalty

    ``changed`` 는 조향 방향이 직전 프리미티브와 다르면 1, 같으면 0. 시작 노드는
    직전 동작이 없으므로 0 이다.

    비용을 프리미티브 **끝점**의 인플레이션 비용으로 매기는 것도 Nav2 와 같다
    (getTraversalCost 는 자식 노드의 cost 를 본다). 중간 샘플의 비용은 경로
    샘플에 그대로 기록되므로 리포트에서 따로 볼 수 있다.

    ``retrospective_penalty`` 는 쓰지 않는다. 요구된 비용식에 없고, Nav2 가 그
    값을 어디에 곱하는지 이 저장소에서 확인하지 못했다. 확인 못 한 것을 추측으로
    채우면 "같은 비용식"이라는 주장 자체가 거짓이 된다.
    """
    normalized = min(1.0, max(0.0, inflation_cost / COST_INFLATION_CEILING))
    raw = primitive_length * (1.0 + params.cost_penalty * normalized)
    changed = 1.0 if (prior_steer is not None and steer != prior_steer) else 0.0
    # 자식 프리미티브가 직진이면 페널티가 붙지 않는다. Nav2 NodeHybrid::
    # getTraversalCost 는 **자식의 선회 방향으로만** 분기하므로, 선회 직후의
    # 직진에도 non_straight_penalty 가 붙지 않는다. 여기에 changed 를 함께
    # 조건으로 걸면 (change_penalty 0.0, non_straight 1.2 인 이 프로필에서)
    # 선회 직후 직진 전부가 1.2배로 계상돼 비용식이 Nav2 와 달라진다.
    if steer == 0:
        travel = raw
    else:
        travel = raw * (params.change_penalty * changed + params.non_straight_penalty)
    if reverse:
        travel *= params.reverse_penalty
    return travel


def _heuristic_scale(params: PlannerParams) -> float:
    """유클리드 휴리스틱에 곱할 안전 계수. **하한을 유지**하기 위한 것이다.

    한 프리미티브의 비용은 ``길이 x (1 + cost_penalty*normalized) x 곱셈계수`` 이고
    앞의 괄호는 cost_penalty >= 0 이므로 1 이상이다. 따라서 곱셈계수의 최솟값만
    반영하면 "남은 직선거리 x 계수" 는 남은 실제 비용의 하한이 된다. 계수가 1 이상인
    기본 프로필(non_straight 1.2, reverse 2.0)에서는 그냥 1.0 이 되어 순수
    유클리드와 같다. 과대평가는 최적성을 깨므로 이쪽으로만 틀린다.

    change_penalty 는 항상 **더해지는** 음이 아닌 값이라 무시해도 하한이 유지된다.

    Dubins/Reeds-Shepp 하한을 쓰지 않은 이유(중요 -- 나중에 "개선"하려다 틀리기 쉽다):
    목표 판정이 **위치만** 보기 때문이다. 목표 자세까지의 RS 거리는 목표 yaw 를
    맞추는 비용까지 포함하는데, 목표 위치 0.1 m 앞에 yaw 가 반대로 서 있는 상태는
    tolerance 안이라 그 자리에서 즉시 도달로 인정된다(남은 비용 0). 그런 상태에
    "RS 로 1.5 m" 를 매기면 과대평가이고 최적성이 깨진다. 위치만 보는 목표 판정과
    짝이 맞는 하한은 유클리드 거리다.
    """
    factors = [1.0, params.non_straight_penalty]
    if params.motion_model.allows_reverse:
        factors.extend(factor * params.reverse_penalty for factor in tuple(factors))
    return max(0.0, min(factors))


# ---------------------------------------------------------------------------
# 결과 조립
# ---------------------------------------------------------------------------


def _path_sample(
    discovered: DiscoveredMap,
    pose: Pose,
    reverse: bool,
    inflation: InflationSpec,
    robot: RobotSpec,
) -> PathSample:
    return PathSample(
        pose=pose,
        reverse=reverse,
        cell_state=discovered.state_at_world(pose.x, pose.y),
        inflation_cost=_inflation_cost(discovered, pose.x, pose.y, inflation, robot),
    )


def _count_states(samples: list[PathSample]) -> tuple[int, int, int]:
    """(free, unknown, occupied) 샘플 수.

    샘플 자세의 **중심 셀** 상태를 센다. footprint 충돌 여부와는 다른 지표다 --
    UNKNOWN 을 얼마나 지나가는지(unknown_traverse_m)를 보기 위한 것이다.
    """
    free = sum(1 for sample in samples if sample.cell_state is CellState.FREE)
    unknown = sum(1 for sample in samples if sample.cell_state is CellState.UNKNOWN)
    occupied = sum(1 for sample in samples if sample.cell_state is CellState.OCCUPIED)
    return free, unknown, occupied


def _single_pose_path(
    discovered: DiscoveredMap,
    pose: Pose,
    flavor: PlannerFlavor,
    elapsed: float,
    inflation: InflationSpec,
    robot: RobotSpec,
) -> PlannedPath:
    """이동 없는 경로. 이미 허용오차 안에서 시작한 경우."""
    samples = [_path_sample(discovered, pose, False, inflation, robot)]
    free, unknown, occupied = _count_states(samples)
    return PlannedPath(
        flavor=flavor,
        samples=tuple(samples),
        length_m=0.0,
        reverse_length_m=0.0,
        direction_changes=0,
        traversal_cost=0.0,
        free_cells=free,
        unknown_cells=unknown,
        occupied_cells=occupied,
        planning_time_sec=elapsed,
        iterations=0,
        timed_out=False,
    )


def _build_path(
    *,
    discovered: DiscoveredMap,
    records: dict[
        tuple[int, int, int],
        tuple[Pose, tuple[int, int, int] | None, int | None, bool],
    ],
    goal_key: tuple[int, int, int],
    traversal_cost: float,
    flavor: PlannerFlavor,
    arc: float,
    radius: float,
    sample_step: float,
    iterations: int,
    elapsed: float,
    inflation: InflationSpec,
    robot: RobotSpec,
) -> PlannedPath:
    """탐색 기록을 되짚어 PlannedPath 를 만든다.

    노드마다 샘플을 들고 있지 않고 여기서 **다시 계산**한다. 확장 수가 백만 단위라
    샘플을 전부 보관하면 메모리가 터지고, ``_advance`` 는 결정론적이라 같은 부모
    자세에서 같은 프리미티브를 다시 굴리면 같은 자세가 나온다.

    ``direction_changes`` 는 **전진/후진이 바뀐 횟수**(cusp)로 센다. 조향 방향이
    바뀐 횟수가 아니다 -- 제자리 회전이 불가능한 이 섀시에서 실제 비용을 만드는 것은
    cusp 이고, RunMetrics 가 reverse_distance_m 과 나란히 이 값을 모으기 때문이다.
    (비용식의 ``changed`` 는 조향 기준이며 그건 별개 개념이다.)
    """
    # 목표 노드에서 시작 노드까지 거슬러 올라간다.
    chain: list[tuple[Pose, int | None, bool]] = []
    cursor: tuple[int, int, int] | None = goal_key
    while cursor is not None:
        pose, parent, steer, reverse = records[cursor]
        chain.append((pose, steer, reverse))
        cursor = parent
    chain.reverse()

    samples = [_path_sample(discovered, chain[0][0], False, inflation, robot)]
    length = 0.0
    reverse_length = 0.0
    direction_changes = 0
    previous_reverse: bool | None = None
    for index in range(1, len(chain)):
        parent_pose = chain[index - 1][0]
        _, steer, reverse = chain[index]
        # 시작 노드만 steer 가 None 이고 그것은 index 0 이므로 여기 오지 않는다.
        for pose in _sample_primitive(
            parent_pose, 0 if steer is None else steer, reverse, arc, radius, sample_step
        ):
            samples.append(_path_sample(discovered, pose, reverse, inflation, robot))
        length += arc
        if reverse:
            reverse_length += arc
        if previous_reverse is not None and reverse != previous_reverse:
            direction_changes += 1
        previous_reverse = reverse

    free, unknown, occupied = _count_states(samples)
    return PlannedPath(
        flavor=flavor,
        samples=tuple(samples),
        length_m=length,
        reverse_length_m=reverse_length,
        direction_changes=direction_changes,
        traversal_cost=traversal_cost,
        free_cells=free,
        unknown_cells=unknown,
        occupied_cells=occupied,
        planning_time_sec=elapsed,
        # 예산을 넘긴 탐색은 None 으로 끝나므로 여기 도달한 경로는 항상 timed_out=False 다.
        iterations=iterations,
        timed_out=False,
    )


# ---------------------------------------------------------------------------
# Nav2 메시지 변환 -- ROS 타입을 최상위로 끌어올리지 않기 위해 클래스를 인자로 받는다.
# ---------------------------------------------------------------------------


def _pose_stamped(pose_stamped_cls, pose: Pose, stamp):  # type: ignore[no-untyped-def]
    """map 프레임의 PoseStamped 를 만든다. 메시지 타입은 호출자가 넘긴다."""
    message = pose_stamped_cls()
    message.header.frame_id = "map"
    message.header.stamp = stamp
    message.pose.position.x = float(pose.x)
    message.pose.position.y = float(pose.y)
    message.pose.position.z = 0.0
    message.pose.orientation.x = 0.0
    message.pose.orientation.y = 0.0
    message.pose.orientation.z = math.sin(pose.yaw / 2.0)
    message.pose.orientation.w = math.cos(pose.yaw / 2.0)
    return message


def _yaw_from_quaternion(orientation) -> float:  # type: ignore[no-untyped-def]
    return math.atan2(
        2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
        1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z),
    )


def _path_from_msg(
    discovered: DiscoveredMap,
    path_msg,  # type: ignore[no-untyped-def]
    flavor: PlannerFlavor,
    elapsed: float,
    inflation: InflationSpec,
    robot: RobotSpec,
) -> PlannedPath | None:
    """nav_msgs/Path 를 PlannedPath 로. **비용과 확장수는 채우지 않는다.**

    ComputePathToPose 결과에는 planner 내부 g-cost 도 확장 횟수도 들어 있지 않다.
    근사식으로 재계산해 채우면 "실제 Nav2 값"이 아닌데 그렇게 보이므로,
    traversal_cost 와 iterations 는 0 = 미측정으로 둔다.

    후진 구간은 경로에 플래그가 없어 유도한다: 구간 진행 방향과 직전 자세의 차체
    방향의 내적이 음수면 후진. Reeds-Shepp 경로의 cusp 를 이렇게 셀 수 있다.
    """
    poses = [
        Pose(
            stamped.pose.position.x,
            stamped.pose.position.y,
            _yaw_from_quaternion(stamped.pose.orientation),
        )
        for stamped in path_msg.poses
    ]
    if not poses:
        return None

    samples = [_path_sample(discovered, poses[0], False, inflation, robot)]
    length = 0.0
    reverse_length = 0.0
    direction_changes = 0
    previous_reverse: bool | None = None
    for index in range(1, len(poses)):
        previous, current = poses[index - 1], poses[index]
        dx, dy = current.x - previous.x, current.y - previous.y
        segment = math.hypot(dx, dy)
        reverse = (
            dx * math.cos(previous.yaw) + dy * math.sin(previous.yaw)
        ) < 0.0
        length += segment
        if reverse:
            reverse_length += segment
        if previous_reverse is not None and reverse != previous_reverse:
            direction_changes += 1
        previous_reverse = reverse
        samples.append(_path_sample(discovered, current, reverse, inflation, robot))

    free, unknown, occupied = _count_states(samples)
    return PlannedPath(
        flavor=flavor,
        samples=tuple(samples),
        length_m=length,
        reverse_length_m=reverse_length,
        direction_changes=direction_changes,
        traversal_cost=0.0,
        free_cells=free,
        unknown_cells=unknown,
        occupied_cells=occupied,
        planning_time_sec=elapsed,
        iterations=0,
        timed_out=False,
    )
