"""프론티어 검출 -- explore_lite ``FrontierSearch`` 의 재현.

원본은 ``m-explore-ros2`` 326cf8a 에 이 저장소의 패치를 얹은 것이고
(``robot/patches/m-explore-ros2-326cf8a-roki-frontier-recovery.patch``),
여기서 따라간 함수는 ``FrontierSearch::searchFrom`` 과 ``buildNewFrontier`` 다.

**이 파일은 정답 지도를 볼 수 없다.** 공개 함수 두 개는 ``DiscoveredMap`` 만
인자로 받는다. ``GroundTruth`` 를 받는 오버로드도, 전역 참조도 없다 -- 미래
지도를 미리 보고 목표를 고르는 코드는 시그니처 단계에서 막힌다.

재현한 것과 의도적으로 다르게 한 것을 구분해 적는다.

재현:

* 로봇 셀에서 출발하는 **4연결 FREE 확장 BFS** 와 ``parent`` 기록.
  upstream 의 조건은 ``map_[nbr] <= map_[idx]`` 인데, 우리 지도는 FREE(0) /
  OCCUPIED(100) / UNKNOWN(-1) 세 값뿐이라 FREE 셀에서 그 조건을 통과하는 이웃은
  FREE 뿐이다. 그래서 "FREE 로만 확장" 이 같은 뜻이 된다.
* ``isNewFrontierCell`` -- UNKNOWN 이고, 아직 다른 클러스터에 속하지 않았고,
  4연결 이웃에 FREE 가 있는 셀. 시드에서 **8연결** BFS 로 클러스터를 모으고
  ``frontier_flag`` 로 각 UNKNOWN 셀이 정확히 한 클러스터에만 들어가게 한다.
* 크기 필터 ``size * resolution >= min_frontier_size``.
* 비용식 ``potential_scale * min_distance * res - gain_scale * size * res``
  (frontier_search.cpp:192). heading 항은 없다.
* 접근점 유도 -- ``boundary_free`` 에서 ``ceil(approach_distance / res)`` 홉만큼
  ``parent`` 체인을 거슬러 오르고, 뿌리(``parent[c] == c``)에 닿으면 멈춘다.
* 목표 yaw 폴백 -- 기준선이 1e-6 m 미만이면 로봇 방위로 되돌린다 (패치 makePlan).

의도적 차이:

* upstream ``buildNewFrontier`` 는 ``size`` 를 1 로 초기화해 시드를 세면서도
  시드를 ``points`` 와 ``min_distance`` 계산에서는 빼먹는다. 여기서는 시드를
  클러스터의 정식 구성원으로 넣는다 (개수는 어차피 같고, ``min_distance`` 는
  같거나 작아진다). 시드는 프론티어 셀이므로 거리 계산에서 빼는 근거가 없다.
* upstream ``searchFrom`` 은 로봇 셀과 ``nearestCell`` 결과를 큐에 **둘 다**
  넣고 앞의 것만 visited 로 표시한다. FREE 로만 확장하는 우리 조건에서는 로봇
  셀이 FREE 가 아니면 거기서 더 나갈 수 없으므로, 최근접 FREE 셀 하나만 넣는
  것과 결과가 같다.
* ``min_distance`` 는 **셀 단위** 거리로 잰다 (이 저장소의 비용식 정의).
  셀 거리 x res 는 정확히 미터 거리라, 비용의 첫 항은 ``potential_scale *
  min_distance_m`` 과 같은 값이 된다 -- ``FrontierCandidate.min_distance_m``
  에 채우는 값이 그것이다.
* 여유(clearance)는 점유셀까지의 거리에 **지도 경계까지의 거리** 를 함께
  본다. ``DiscoveredMap.min_obstacle_distance`` 는 점유셀만 재기 때문에
  경계를 따로 보지 않으면 지도 밖으로 나가는 footprint 를 안전하다고 답한다.
* UNKNOWN 은 여유 계산에서 장애물로 세지 **않는다.** 프론티어 접근점은 정의상
  미지 영역에 붙어 있어서, UNKNOWN 을 장애물로 세면 모든 후보가
  ``NO_APPROACH_CELL`` 이 된다. 실측 진단이 문제로 지목한 것도 점유셀까지의
  거리(0.063 m / 0.180 m)였다.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Sequence

from .contracts import (
    CandidateVerdict,
    CellState,
    FrontierCandidate,
    FrontierParams,
    GoalYawRule,
    GridSpec,
    Pose,
    RobotSpec,
)
from .worldmodel import DiscoveredMap


# 패치 makePlan 의 ``std::hypot(...) < 1e-6`` 과 같은 값. 기준선이 이보다 짧으면
# 방향이 없다고 보고 폴백한다.
_DEGENERATE_BASELINE_M = 1e-6

# 여유를 실제로 재는 상한 = 요구값 x 이 배수. 요구값을 넘는 여유는 "어떤
# 자세에서도 안전" 판정에 더 필요 없지만, alternate_approaches 가 "여유가 큰
# 순" 으로 줄을 세우려면 상한에서 전부 같은 값으로 뭉개져서는 안 된다.
# 전 지도 스캔을 피하면서 순서를 가릴 수 있는 최소 여지로 2배를 잡았다.
_CLEARANCE_PROBE_FACTOR = 2.0

# 재시도 대안 개수 상한 (요구사항).
_MAX_ALTERNATES = 5

# alternate_approaches 가 경계에서 물러나 볼 수 있는 최대 홉수 = 표준 후퇴
# 예산 x 이 배수. 더 멀리 간 점은 그 프론티어의 접근점이라고 부를 수 없고,
# LONG_BASELINE 이 heading 기준점으로 쓰는 "2배 홉" 셀이 딱 이 깊이에 있다.
_ALTERNATE_DEPTH_FACTOR = 2


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------


def detect(
    discovered: DiscoveredMap,
    robot_pose: Pose,
    params: FrontierParams,
    robot: RobotSpec,
    yaw_rule: GoalYawRule,
) -> list[FrontierCandidate]:
    """비용 오름차순으로 정렬된 후보 목록. 정답 지도를 절대 받지 않는다."""

    spec, states = _grid_snapshot(discovered)
    width = spec.width
    size = width * spec.height

    col, row = spec.world_to_cell(robot_pose.x, robot_pose.y)
    if not spec.contains(col, row):
        # upstream 의 worldToMap 실패와 같은 상황. 탐색을 시작할 셀이 없다.
        return []
    start = _nearest_free(states, spec.index(col, row), width, size)
    if start is None:
        # 발견 지도에 FREE 셀이 하나도 없다 (첫 관측 이전). 프론티어도 없다.
        return []

    visited = bytearray(size)
    flagged = bytearray(size)
    # parent 는 dict 보다 리스트가 빠르고, BFS 가 방문한 셀만 쓰기 때문에
    # 초기값 0 이 읽히는 경우는 없다.
    parent = [0] * size
    visited[start] = 1
    parent[start] = start
    # 거리 참조점은 **로봇 셀** 이다. upstream 은 buildNewFrontier(nbr, pos, ...) 로
    # 부르고 pos = costmap_->getIndex(mx, my) 즉 로봇 셀이며, BFS 시작점으로 쓰는
    # nearestCell 결과는 참조점이 아니다. 이 구분이 중요한 이유: 라이다 데드존
    # (min_range_m) 때문에 첫 tick 에서 로봇 셀은 UNKNOWN 이고 start 가 최대
    # 0.2 m 떨어진 셀이 된다. 그때 참조점을 start 로 쓰면 그 tick 의 모든 후보
    # 거리가 어긋나 정렬이 바뀐다.
    reference_col, reference_row = col, row

    queue = deque((start,))
    candidates: list[FrontierCandidate] = []
    while queue:
        index = queue.popleft()
        for neighbour in _nhood4(index, width, size):
            if states[neighbour] is CellState.FREE:
                if not visited[neighbour]:
                    visited[neighbour] = 1
                    parent[neighbour] = index
                    queue.append(neighbour)
            elif _is_new_frontier_cell(neighbour, states, flagged, width, size):
                # index 는 로봇에서 연결된 FREE 셀, neighbour 는 그에 맞닿은
                # UNKNOWN 시드다. 패치가 frontier_free 로 기록하는 셀이 index 다.
                cluster = _grow_cluster(neighbour, states, flagged, width, size)
                candidates.append(
                    _candidate_from_cluster(
                        discovered,
                        parent,
                        cluster,
                        index,
                        reference_col=reference_col,
                        reference_row=reference_row,
                        robot_pose=robot_pose,
                        params=params,
                        robot=robot,
                        yaw_rule=yaw_rule,
                    )
                )

    # 비용만으로 정렬한다. 파이썬 sort 는 안정 정렬이므로 비용이 같은 후보는
    # BFS 발견 순서를 유지한다 -- 리플레이 시뮬레이터에서 같은 입력이 같은
    # 순서를 내는 것이 tie-break 규칙보다 중요하다.
    candidates.sort(key=lambda candidate: candidate.cost)
    return candidates


def alternate_approaches(
    discovered: DiscoveredMap,
    candidate: FrontierCandidate,
    robot: RobotSpec,
    params: FrontierParams,
    yaw_rule: GoalYawRule,
    exclude: Sequence[tuple[float, float]],
) -> list[tuple[tuple[float, float], float, float]]:
    """(approach_xy, goal_yaw, clearance) 대안 목록. v0.2.6 의 재시도용.

    같은 클러스터의 **다른** ``boundary_free`` 셀들에서 접근점을 다시 유도한다.
    ``detect`` 의 로봇 기준 parent 체인은 여기서 다시 쓸 수 없다 (이 시그니처에
    로봇 자세가 없다). 대신 그 클러스터의 boundary_free 셀들을 동시 출발점으로
    두는 다중 시작 BFS 를 돌려, "경계에서 멀어지는 방향" 의 체인을 만든다.
    체인의 0 번은 boundary_free 셀이고 i 번은 거기서 i 홉 물러난 셀이라, 아래
    ``_select_on_chain`` 을 ``detect`` 와 그대로 공유한다.

    여유 조건은 프로필의 ``clearance_aware_approach`` 와 무관하게 항상 건다.
    재시도 자체가 v0.2.6 후보의 기능이고, 요구사항이 "clearance 를 만족하는
    것들" 이기 때문이다. 여유가 큰 순으로 최대 5개.
    """

    if not candidate.cluster_cells:
        return []

    # 여기서는 ``detect`` 처럼 지도 전체를 스냅샷 뜨지 않는다. 탐색 범위가 한
    # 클러스터 주변 depth_limit 홉으로 한정돼 있어서, 전수 스냅샷 비용이 실제
    # 탐색 비용보다 크다. 그래서 셀 상태를 그때그때 읽는다.
    spec = discovered.spec
    width = spec.width
    size = width * spec.height
    resolution = spec.resolution

    required = _required_clearance_m(params, robot)
    probe_limit = required * _CLEARANCE_PROBE_FACTOR
    retreat_cells = _retreat_cells(params, resolution)
    depth_limit = retreat_cells * _ALTERNATE_DEPTH_FACTOR

    sources = _cluster_boundary_cells(spec, discovered, candidate, width, size)
    if not sources:
        return []

    parent, depth, root = _multi_source_free_bfs(
        sources, discovered, width, size, depth_limit
    )

    # 뿌리(=boundary_free 셀)별로 가장 깊이 물러난 셀들만 체인 끝으로 쓴다.
    # 얕은 셀은 그 체인의 부분열이라 _select_on_chain 이 같은 답을 낸다.
    deepest: dict[int, int] = {}
    for cell, hops in depth.items():
        source = root[cell]
        if hops > deepest.get(source, -1):
            deepest[source] = hops

    results: list[tuple[tuple[float, float], float, float]] = []
    seen: set[int] = set()
    for cell, hops in depth.items():
        if hops == 0 or hops != deepest[root[cell]]:
            continue
        chain = _chain_from_parents(parent, cell)
        picked, clearance = _select_on_chain(
            discovered,
            chain,
            clearance_aware=True,
            retreat_cells=retreat_cells,
            required_clearance_m=required,
            probe_limit_m=probe_limit,
        )
        if picked is None or clearance is None:
            continue
        approach_index = chain[picked]
        if approach_index in seen:
            continue
        approach_xy = _cell_centre(spec, approach_index)
        if _is_excluded(approach_xy, exclude, resolution * 0.5):
            continue
        seen.add(approach_index)
        boundary_xy = _cell_centre(spec, chain[0])
        heading_xy = _cell_centre(spec, chain[min(2 * picked, len(chain) - 1)])
        goal_yaw = _goal_yaw(yaw_rule, None, boundary_xy, approach_xy, heading_xy)
        results.append((approach_xy, goal_yaw, clearance))

    # 여유가 큰 순. 안정 정렬이라 여유가 같으면 BFS 발견 순서를 유지한다.
    results.sort(key=lambda item: -item[2])
    return results[:_MAX_ALTERNATES]


# ---------------------------------------------------------------------------
# 발견 지도 읽기 -- 이 파일이 DiscoveredMap 에 요구하는 표면은 ``spec``,
# ``state_at_cell``, ``min_obstacle_distance`` 세 개뿐이다.
# ---------------------------------------------------------------------------


def _grid_snapshot(
    discovered: DiscoveredMap,
) -> tuple[GridSpec, list[CellState]]:
    """격자 기하와 셀 상태를 한 번만 평탄화해 둔다.

    ``state_at_cell`` 을 BFS 안에서 직접 부르면 셀당 여러 번 파이썬 함수 호출이
    일어나 그게 지배적 비용이 된다. 한 tick 에 한 번 스냅샷을 떠서 리스트
    첨자로 읽는다. 첨자는 ``spec.index(col, row) == row * width + col`` 이다.

    스냅샷을 뜨는 부수효과는 "이 tick 동안 지도가 고정된다" 는 것인데, 계획
    tick 안에서 지도가 바뀌지 않는 것이 오히려 explore 의 실제 동작(타이머
    tick 에서 costmap 을 한 번 읽는다)에 가깝다.
    """
    spec = discovered.spec
    reader = discovered.state_at_cell
    return spec, [
        reader(col, row)
        for row in range(spec.height)
        for col in range(spec.width)
    ]


def _clearance_m(
    discovered: DiscoveredMap, x: float, y: float, limit_m: float
) -> float:
    """(x, y) 에서 가장 가까운 **하드 경계** 까지의 거리, ``limit_m`` 에서 자름.

    하드 경계 = 점유셀 사각형 또는 지도 경계. ``min_obstacle_distance`` 는
    점유셀만 재기 때문에, 경계를 따로 보지 않으면 지도 밖으로 나가는
    footprint 를 안전하다고 답한다 (worldmodel 의 시작점 후보 선별도 같은
    이유로 두 검사를 함께 한다).
    """
    spec = discovered.spec
    edge = min(
        x - spec.origin_x,
        y - spec.origin_y,
        spec.origin_x + spec.width * spec.resolution - x,
        spec.origin_y + spec.height * spec.resolution - y,
    )
    if edge < 0.0:
        edge = 0.0
    return min(limit_m, edge, discovered.min_obstacle_distance(x, y, limit_m))


# ---------------------------------------------------------------------------
# 격자 이웃 -- index = row * width + col
# ---------------------------------------------------------------------------


def _nhood4(index: int, width: int, size: int) -> list[int]:
    column = index % width
    neighbours: list[int] = []
    if column > 0:
        neighbours.append(index - 1)
    if column + 1 < width:
        neighbours.append(index + 1)
    if index >= width:
        neighbours.append(index - width)
    if index + width < size:
        neighbours.append(index + width)
    return neighbours


def _nhood8(index: int, width: int, size: int) -> list[int]:
    column = index % width
    has_left = column > 0
    has_right = column + 1 < width
    has_below = index >= width
    has_above = index + width < size
    neighbours: list[int] = []
    if has_left:
        neighbours.append(index - 1)
    if has_right:
        neighbours.append(index + 1)
    if has_below:
        neighbours.append(index - width)
    if has_above:
        neighbours.append(index + width)
    if has_below and has_left:
        neighbours.append(index - width - 1)
    if has_below and has_right:
        neighbours.append(index - width + 1)
    if has_above and has_left:
        neighbours.append(index + width - 1)
    if has_above and has_right:
        neighbours.append(index + width + 1)
    return neighbours


def _cell_centre(spec: GridSpec, index: int) -> tuple[float, float]:
    return spec.cell_to_world(index % spec.width, index // spec.width)


# ---------------------------------------------------------------------------
# searchFrom 의 조각들
# ---------------------------------------------------------------------------


def _nearest_free(
    states: Sequence[CellState], start: int, width: int, size: int
) -> int | None:
    """upstream ``nearestCell(..., FREE_SPACE, ...)`` 재현.

    셀 상태를 무시한 8연결 BFS 로 퍼져 처음 만나는 FREE 셀. 로봇이 아직
    관측되지 않은(UNKNOWN) 셀 위에 서 있어도 탐색을 시작할 수 있게 한다.
    """
    # 대부분의 tick 에서 로봇 셀은 이미 FREE 다. 지도 크기만한 bytearray 를
    # 매 tick 할당하지 않으려고 그 경우를 먼저 걸러낸다.
    if states[start] is CellState.FREE:
        return start
    visited = bytearray(size)
    visited[start] = 1
    queue = deque((start,))
    while queue:
        index = queue.popleft()
        if states[index] is CellState.FREE:
            return index
        for neighbour in _nhood8(index, width, size):
            if not visited[neighbour]:
                visited[neighbour] = 1
                queue.append(neighbour)
    return None


def _is_new_frontier_cell(
    index: int,
    states: Sequence[CellState],
    flagged: bytearray,
    width: int,
    size: int,
) -> bool:
    """upstream ``isNewFrontierCell``: UNKNOWN + 미배정 + 4연결 FREE 이웃 존재."""
    if states[index] is not CellState.UNKNOWN or flagged[index]:
        return False
    for neighbour in _nhood4(index, width, size):
        if states[neighbour] is CellState.FREE:
            return True
    return False


def _grow_cluster(
    seed: int,
    states: Sequence[CellState],
    flagged: bytearray,
    width: int,
    size: int,
) -> list[int]:
    """시드에서 8연결로 UNKNOWN 프론티어 셀을 모은다.

    큐에 넣을 때 ``flagged`` 를 세우기 때문에 같은 셀이 두 번 들어가지 않고,
    한 번 어떤 클러스터에 들어간 셀은 다른 클러스터가 다시 가져갈 수 없다
    (upstream 의 ``frontier_flag`` 와 같은 역할).
    """
    flagged[seed] = 1
    cluster: list[int] = []
    queue = deque((seed,))
    while queue:
        index = queue.popleft()
        cluster.append(index)
        for neighbour in _nhood8(index, width, size):
            if _is_new_frontier_cell(neighbour, states, flagged, width, size):
                flagged[neighbour] = 1
                queue.append(neighbour)
    return cluster


def _retreat_cells(params: FrontierParams, resolution: float) -> int:
    """패치의 ``ceil(approach_distance_ / getResolution())``."""
    return math.ceil(params.approach_distance_m / resolution)


def _required_clearance_m(params: FrontierParams, robot: RobotSpec) -> float:
    """clearance 기준값. None 이면 circumscribed.

    circumscribed 를 쓰는 이유: footprint 는 어떤 yaw 에서도 반지름
    circumscribed 인 원 안에 들어간다. 따라서 여유가 그 값 이상이면 자세와
    무관하게 충돌하지 않는다 -- ``profiles.py`` 의 v0.2.6 후보가 요구하는
    "자세 무관 안전" 이 정확히 이 조건이다. (``contracts.FrontierParams`` 의
    주석은 inscribed 라고 적고 있는데, 실측 진단은 inscribed 0.135 와
    circumscribed 0.229 **사이** 의 목표가 특정 yaw 에서 충돌한 사례였다.
    inscribed 로는 그 사례를 못 걸러내므로 profiles.py 의 명시를 따른다.)
    """
    if params.required_clearance_m is not None:
        return params.required_clearance_m
    return robot.circumscribed_radius_m


# ---------------------------------------------------------------------------
# 접근점 유도
# ---------------------------------------------------------------------------


def _parent_chain(
    parent: Sequence[int], boundary: int, max_hops: int | None
) -> list[int]:
    """``boundary`` 에서 parent 를 거슬러 오른 체인. 0 번이 boundary.

    ``max_hops`` 가 None 이면 뿌리(``parent[c] == c``)까지 간다. 뿌리는 BFS
    출발 셀, 즉 로봇 쪽 끝이다.
    """
    chain = [boundary]
    current = boundary
    while max_hops is None or len(chain) <= max_hops:
        following = parent[current]
        if following == current:
            break
        current = following
        chain.append(current)
    return chain


def _select_on_chain(
    discovered: DiscoveredMap,
    chain: Sequence[int],
    *,
    clearance_aware: bool,
    retreat_cells: int,
    required_clearance_m: float,
    probe_limit_m: float,
) -> tuple[int | None, float | None]:
    """체인에서 접근점을 고른다. 반환은 (체인 첨자, 측정된 여유).

    현행(``clearance_aware=False``)은 고정 홉수로 물러난다 -- 여유를 보지 않기
    때문에 v0.2.5 가 여유 0.063 m 인 셀을 목표로 보낸 것이 그대로 재현된다.
    측정한 여유는 판정에 쓰지 않고 기록만 한다.

    v0.2.6 후보는 여유가 기준 이상인 첫 셀을 고른다. 첨자 0(= boundary_free
    셀 자신)은 건너뛴다: 그 셀을 목표로 잡으면 목표가 미지 경계에 딱 붙고
    boundary -> approach 기준선이 0 이 되어 yaw 규칙이 폴백해 버린다. 패치의
    의도는 "경계에서 물러난다" 이므로 최소 한 홉은 물러난 뒤부터 본다.
    """
    if not clearance_aware:
        index = min(retreat_cells, len(chain) - 1)
        x, y = _cell_centre(discovered.spec, chain[index])
        return index, _clearance_m(discovered, x, y, probe_limit_m)
    for index in range(1, len(chain)):
        x, y = _cell_centre(discovered.spec, chain[index])
        clearance = _clearance_m(discovered, x, y, probe_limit_m)
        if clearance >= required_clearance_m:
            return index, clearance
    return None, None


# ---------------------------------------------------------------------------
# 목표 yaw
# ---------------------------------------------------------------------------


def _bearing(
    origin: tuple[float, float], target: tuple[float, float]
) -> float | None:
    """``atan2(target - origin)``. 두 점이 1e-6 m 안이면 None (기준선 없음)."""
    dx = target[0] - origin[0]
    dy = target[1] - origin[1]
    if math.hypot(dx, dy) < _DEGENERATE_BASELINE_M:
        return None
    return math.atan2(dy, dx)


def _goal_yaw(
    yaw_rule: GoalYawRule,
    robot_pose: Pose | None,
    boundary_xy: tuple[float, float],
    approach_xy: tuple[float, float],
    heading_ref_xy: tuple[float, float],
) -> float:
    """GoalYawRule 세 가지.

    LONG_BASELINE 의 근거는 양자화다. 4연결 체인을 h 홉 거슬러 오르면 (장애물이
    없는 구간에서) 변위는 ``|dx| + |dy| == h`` 인 격자점에만 놓인다. 그래서
    가능한 방위가 유한하다.

    * h = 5 (approach_distance 0.25 m / res 0.05 m) -> 1사분면에서
      0 / 14.04 / 33.69 / 56.31 / 75.96 / 90 도 여섯 개.
      인접 간격 최대 22.62 도 -> **최악 오차 11.31 도**.
    * h = 10 -> 0 / 6.34 / 14.04 / 23.20 / 33.69 / 45 / 56.31 / 66.80 /
      75.96 / 83.66 / 90 도 열한 개. 최대 간격 11.31 도 -> **최악 오차 5.66 도**.

    그래서 heading 기준점을 approach 보다 2배 홉 뒤에서 잡는다. 목표 지점
    자체는 그대로 approach 이고 바뀌는 것은 바라보는 방향뿐이다.
    """
    if yaw_rule is GoalYawRule.APPROACH_TO_BOUNDARY_LONG_BASELINE:
        # 긴 기준선 -> 짧은 기준선(v0.2.5) -> 로봇 방위(패치) 순으로 폴백.
        for base in (heading_ref_xy, approach_xy):
            yaw = _bearing(base, boundary_xy)
            if yaw is not None:
                return yaw
    elif yaw_rule is GoalYawRule.APPROACH_TO_BOUNDARY:
        yaw = _bearing(approach_xy, boundary_xy)
        if yaw is not None:
            return yaw

    if robot_pose is None:
        # alternate_approaches 시그니처에 로봇 자세가 없어 BEARING_FROM_ROBOT
        # 을 계산할 방법이 없다. 내장 프로필에서 그 규칙을 쓰는 v0.2.2 는
        # retry_with_alternate_approach=False 라 이 경로에 오지 않는다. 새 프로필
        # 조합이 생겨 여기 오면 v0.2.5 규칙으로 낮춰 계산한다.
        yaw = _bearing(approach_xy, boundary_xy)
        return 0.0 if yaw is None else yaw

    yaw = _bearing((robot_pose.x, robot_pose.y), approach_xy)
    # 로봇이 접근점 셀 중심에 정확히 서 있는 경우. C++ 의 atan2(0, 0) == 0 은
    # "+x 를 본다" 는 뜻이 되어 조용히 틀리므로 현재 자세를 유지한다.
    return robot_pose.yaw if yaw is None else yaw


# ---------------------------------------------------------------------------
# 클러스터 -> 후보
# ---------------------------------------------------------------------------


def _candidate_from_cluster(
    discovered: DiscoveredMap,
    parent: Sequence[int],
    cluster: list[int],
    boundary: int,
    *,
    reference_col: int,
    reference_row: int,
    robot_pose: Pose,
    params: FrontierParams,
    robot: RobotSpec,
    yaw_rule: GoalYawRule,
) -> FrontierCandidate:
    spec = discovered.spec
    width = spec.width
    resolution = spec.resolution

    cells = tuple((index % width, index // width) for index in cluster)
    count = len(cells)
    size_m = count * resolution
    # upstream `buildNewFrontier` 는 `mapToWorld` 로 변환한 뒤 거리를 재므로
    # `Frontier::min_distance` 는 **미터**다. 그리고 `frontierCost` 가 그 미터값에
    # 해상도를 **한 번 더** 곱한다::
    #
    #   cost = potential_scale * min_distance[m] * res - gain_scale * size[셀] * res
    #
    # 그래서 거리항은 potential_scale * d_m * res 이지 potential_scale * d_m 이
    # 아니다. res=0.05 에서 둘은 20배 차이가 나고, 잘못 쓰면 explore.params.yaml
    # 이 potential_scale 을 0.5 로 낮추고 gain_scale 을 3.0 으로 올려 없앤
    # "가까운 주머니 선호" 가 시뮬레이터에서 되살아난다.
    min_distance_cells = min(
        math.hypot(column - reference_col, row - reference_row)
        for column, row in cells
    )
    min_distance_m = min_distance_cells * resolution
    cost = (
        params.potential_scale * min_distance_m * resolution
        - params.gain_scale * count * resolution
    )
    boundary_xy = _cell_centre(spec, boundary)
    # 시드 셀 좌표로 id 를 만든다. 각 UNKNOWN 셀은 한 클러스터에만 속하므로
    # 한 tick 안에서 유일하다. tick 을 넘어 같은 id 가 유지된다는 보장은 없다
    # (지도가 자라면 시드가 바뀔 수 있다) -- 재시도 병합은 좌표로 하고 id 로
    # 하지 않는 이유가 그것이다.
    candidate_id = f"f{cells[0][0]:04d}_{cells[0][1]:04d}"

    if size_m < params.min_frontier_size_m:
        # upstream 은 여기서 후보를 버린다. 리포트에 보이도록 남기되 접근점은
        # 유도하지 않는다 (여유 측정이 가장 비싼 단계이고, 이 후보는 선택될 수
        # 없다). min_frontier_size 0.35 가 개구부를 버리는 것을 드러내는 항목이다.
        return FrontierCandidate(
            candidate_id=candidate_id,
            cluster_cells=cells,
            size_m=size_m,
            min_distance_m=min_distance_m,
            cost=cost,
            boundary_free=boundary_xy,
            approach=None,
            goal_yaw=None,
            approach_clearance_m=None,
            verdict=CandidateVerdict.TOO_SMALL,
            reject_detail=(
                f"크기 {size_m:.2f} m < min_frontier_size "
                f"{params.min_frontier_size_m:.2f} m (셀 {count}개)"
            ),
        )

    retreat_cells = _retreat_cells(params, resolution)
    required = _required_clearance_m(params, robot)
    long_baseline = yaw_rule is GoalYawRule.APPROACH_TO_BOUNDARY_LONG_BASELINE
    if params.clearance_aware_approach:
        # 여유 조건을 만족하는 셀이 어디 있는지 모르므로 뿌리까지 열어 둔다.
        # "체인이 끝나도 못 찾으면 NO_APPROACH_CELL" 이 되려면 끝까지 봐야 한다.
        max_hops: int | None = None
    else:
        # 고정 홉수로 물러난다. LONG_BASELINE 이면 heading 기준점이 2배 홉에
        # 있으므로 그만큼 더 길게 만들어 둔다 (approach 는 그대로 retreat_cells).
        max_hops = retreat_cells * (2 if long_baseline else 1)
    chain = _parent_chain(parent, boundary, max_hops)

    picked, clearance = _select_on_chain(
        discovered,
        chain,
        clearance_aware=params.clearance_aware_approach,
        retreat_cells=retreat_cells,
        required_clearance_m=required,
        probe_limit_m=required * _CLEARANCE_PROBE_FACTOR,
    )
    if picked is None:
        return FrontierCandidate(
            candidate_id=candidate_id,
            cluster_cells=cells,
            size_m=size_m,
            min_distance_m=min_distance_m,
            cost=cost,
            boundary_free=boundary_xy,
            approach=None,
            goal_yaw=None,
            approach_clearance_m=None,
            verdict=CandidateVerdict.NO_APPROACH_CELL,
            reject_detail=(
                f"parent 체인 {len(chain)}셀에 여유 {required:.3f} m 이상인 "
                "셀이 없다"
            ),
        )

    approach_xy = _cell_centre(spec, chain[picked])
    heading_xy = _cell_centre(spec, chain[min(2 * picked, len(chain) - 1)])
    return FrontierCandidate(
        candidate_id=candidate_id,
        cluster_cells=cells,
        size_m=size_m,
        min_distance_m=min_distance_m,
        cost=cost,
        boundary_free=boundary_xy,
        approach=approach_xy,
        goal_yaw=_goal_yaw(
            yaw_rule, robot_pose, boundary_xy, approach_xy, heading_xy
        ),
        approach_clearance_m=clearance,
        verdict=CandidateVerdict.NOT_EVALUATED,
    )


# ---------------------------------------------------------------------------
# alternate_approaches 의 조각들
# ---------------------------------------------------------------------------


def _free_at(discovered: DiscoveredMap, index: int, width: int) -> bool:
    """평탄 첨자로 FREE 인지 묻는다. 국소 탐색용 (스냅샷을 뜨지 않는 경로)."""
    return discovered.state_at_cell(index % width, index // width) is CellState.FREE


def _cluster_boundary_cells(
    spec: GridSpec,
    discovered: DiscoveredMap,
    candidate: FrontierCandidate,
    width: int,
    size: int,
) -> list[int]:
    """클러스터에 맞닿은 FREE 셀들. 원래 쓰인 boundary_free 는 제외한다.

    ``detect`` 는 클러스터마다 **처음 만난** FREE 셀 하나만 boundary_free 로
    기록한다. 재시도가 볼 수 있는 다른 후보가 나머지 맞닿은 FREE 셀들이다.
    """
    used: int | None = None
    if candidate.boundary_free is not None:
        column, row = spec.world_to_cell(*candidate.boundary_free)
        if spec.contains(column, row):
            used = spec.index(column, row)

    boundary: list[int] = []
    seen: set[int] = set()
    for column, row in candidate.cluster_cells:
        if not spec.contains(column, row):
            continue
        for neighbour in _nhood4(spec.index(column, row), width, size):
            if neighbour in seen or neighbour == used:
                continue
            if not _free_at(discovered, neighbour, width):
                continue
            seen.add(neighbour)
            boundary.append(neighbour)
    return boundary


def _multi_source_free_bfs(
    sources: Sequence[int],
    discovered: DiscoveredMap,
    width: int,
    size: int,
    depth_limit: int,
) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    """출발점들에서 동시에 퍼지는 4연결 FREE BFS. (parent, depth, root).

    각 FREE 셀은 홉수가 가장 적은 출발점에 배정된다. 출발점을 하나씩 따로
    돌리는 것보다 싸고, 배정이 겹치지 않아 같은 접근점이 여러 boundary 셀
    이름으로 중복 반환되는 것도 막는다.

    ``sources`` 는 서로 다른 FREE 셀이어야 한다 (``_cluster_boundary_cells``
    가 보장한다).
    """
    parent: dict[int, int] = {}
    depth: dict[int, int] = {}
    root: dict[int, int] = {}
    queue: deque[int] = deque()
    for source in sources:
        parent[source] = source
        depth[source] = 0
        root[source] = source
        queue.append(source)
    while queue:
        index = queue.popleft()
        hops = depth[index]
        if hops >= depth_limit:
            continue
        for neighbour in _nhood4(index, width, size):
            if neighbour in depth or not _free_at(discovered, neighbour, width):
                continue
            parent[neighbour] = index
            depth[neighbour] = hops + 1
            root[neighbour] = root[index]
            queue.append(neighbour)
    return parent, depth, root


def _chain_from_parents(parent: dict[int, int], cell: int) -> list[int]:
    """``cell`` 에서 뿌리까지 올라간 뒤 뒤집어, 0 번이 뿌리(boundary_free)가 되게.

    ``_parent_chain`` 과 같은 규약을 맞추려는 것이다: 첨자 i = 경계에서 i 홉
    물러난 셀. 그래야 ``_select_on_chain`` 을 ``detect`` 와 공유할 수 있다.
    """
    chain = [cell]
    current = cell
    while parent[current] != current:
        current = parent[current]
        chain.append(current)
    chain.reverse()
    return chain


def _is_excluded(
    point: tuple[float, float],
    exclude: Sequence[tuple[float, float]],
    tolerance_m: float,
) -> bool:
    """이미 시도한 접근점인지. 접근점은 셀 중심이므로 반 셀이면 "같은 셀" 이다."""
    for x, y in exclude:
        if math.hypot(point[0] - x, point[1] - y) < tolerance_m:
            return True
    return False
