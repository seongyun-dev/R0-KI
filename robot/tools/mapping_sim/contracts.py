"""매핑 리플레이 시뮬레이터의 공유 자료형.

이 모듈은 **자료형과 상수만** 담는다. 알고리즘은 각 모듈에 있다.
모든 모듈이 이 계약만 보고 조립되므로, 여기 없는 필드를 임의로 추가하지 말 것.

핵심 불변식 두 가지:

1. **정답 지도와 발견 지도는 분리된다.** ``GroundTruth`` 는 raycast 와 실제 충돌
   판정에만 쓰인다. 프론티어 검출·경로계획·목표선택은 ``DiscoveredMap`` 만 본다.
   그래서 두 타입을 아예 다른 클래스로 두었다 -- 함수 시그니처가 위반을 잡는다.

2. **근사와 실측을 구분한다.** 이 시뮬레이터의 플래너는 Nav2 SmacPlannerHybrid 가
   아니라 같은 비용식을 쓰는 자체 SE2 격자 탐색이다. 결과에는 항상
   ``PlannerFlavor.APPROXIMATE`` 가 붙는다. 실제 Nav2 를 호출한 경우에만
   ``PlannerFlavor.NAV2_ACTUAL`` 을 쓴다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


# ---------------------------------------------------------------------------
# 실측값 -- CLAUDE.md B-7 (줄자 검증) 과 robot/config/robot.env.example 기준.
# 여기 있는 숫자는 추정이 아니라 이 로봇에서 직접 측정된 값이다.
# ---------------------------------------------------------------------------

FOOTPRINT_LENGTH_M = 0.35
FOOTPRINT_WIDTH_M = 0.25
WHEELBASE_M = 0.124
MAX_STEER_RAD = math.radians(20.0)
MIN_TURNING_RADIUS_M = 0.341          # wheelbase / tan(20deg) = 0.3407
DRIVE_SPEED_MPS = 0.09
FOOTPRINT_PADDING_M = 0.01            # Nav2 기본값. 템플릿에 키가 없어 이 값이 쓰인다.

# footprint 유래 반경. Nav2 InflationLayer 와 충돌검사가 이 두 값을 쓴다.
INSCRIBED_RADIUS_M = FOOTPRINT_WIDTH_M / 2.0 + FOOTPRINT_PADDING_M      # 0.135
CIRCUMSCRIBED_RADIUS_M = (
    math.hypot(FOOTPRINT_LENGTH_M / 2.0 + FOOTPRINT_PADDING_M,
               FOOTPRINT_WIDTH_M / 2.0 + FOOTPRINT_PADDING_M)
)                                                                        # 0.2287

# Nav2 costmap_2d 비용 상수 (nav2_costmap_2d/cost_values.hpp).
COST_LETHAL = 254
COST_INSCRIBED = 253
COST_UNKNOWN = 255
COST_FREE = 0
COST_INFLATION_CEILING = 252     # InflationLayer 지수감쇠의 상한


class CellState(Enum):
    """점유격자 한 칸의 상태. nav_msgs/OccupancyGrid 의 -1/0/100 에 대응."""

    UNKNOWN = -1
    FREE = 0
    OCCUPIED = 100


class MotionModel(Enum):
    """Nav2 SmacPlannerHybrid 의 motion_model_for_search 에 대응."""

    DUBIN = "DUBIN"
    REEDS_SHEPP = "REEDS_SHEPP"

    @property
    def allows_reverse(self) -> bool:
        return self is MotionModel.REEDS_SHEPP


class PlannerFlavor(Enum):
    """결과가 실제 Nav2 인지 자체 근사인지. 리포트에 그대로 노출된다."""

    APPROXIMATE = "APPROXIMATE"        # 자체 SE2 격자 탐색. Smac 아님.
    NAV2_ACTUAL = "NAV2_ACTUAL"        # ComputePathToPose 실호출.


class BlacklistMode(Enum):
    """실패 후보를 배제하는 방식들. 비교 대상이다."""

    # 좌표 상자 + 고정 쿨다운 + 시도횟수 소진 시 영구 배제 (v0.2.2 ~ v0.2.6 8c7a466).
    COORDINATE_COOLDOWN = "coordinate_cooldown"
    # 지도 개정(map revision) 이 바뀌면 soft-block 을 전부 재평가.
    # 내가 제안했던 방식이고, 지도 어디가 바뀌어도 되돌린다는 점이 거칠다.
    MAP_REVISION_SOFT = "map_revision_soft"
    # v0.2.6 (7c9caee): **그 목표 주변**의 FREE 셀이 일정 수 이상 늘었을 때만
    # attempts 를 0 으로 되돌린다. 지도 다른 곳의 변화는 이력을 지우지 않는다.
    # MAP_REVISION_SOFT 보다 국소적이라 무한 재시도로 흐를 위험이 작다.
    LOCAL_FREE_GROWTH = "local_free_growth"


class MergeMetric(Enum):
    """실패 레코드를 병합할 때 쓰는 거리 척도."""

    CHEBYSHEV = "chebyshev"    # 현행 explore.cpp: fabs(dx)<r && fabs(dy)<r -> 정사각 상자
    EUCLIDEAN = "euclidean"    # 후보: hypot(dx,dy) < r


class CandidateVerdict(Enum):
    """한 프론티어 후보가 이번 tick 에 어떻게 처리됐는가."""

    SELECTED = "selected"
    BLACKLISTED = "blacklisted"
    COOLING_DOWN = "cooling_down"
    TOO_SMALL = "too_small"                  # min_frontier_size 미달
    NO_APPROACH_CELL = "no_approach_cell"    # 접근점을 만들 수 없음
    PATH_UNAVAILABLE = "path_unavailable"    # 사전검사 실패
    # a3d7d62: 반환된 경로가 UNKNOWN 을 허용치보다 길게 통과한다
    PATH_CROSSES_UNKNOWN = "path_crosses_unknown"
    GOAL_IN_COLLISION = "goal_in_collision"  # 목표 자세에서 footprint 충돌
    NOT_EVALUATED = "not_evaluated"          # 더 좋은 후보가 먼저 뽑혀 평가 안 함


class TerminationState(Enum):
    """탐사 종료 사유. COMPLETE 와 STALLED 를 절대 섞지 않는다."""

    COMPLETE = "COMPLETE"      # 유효 프론티어가 실제로 없음
    WAITING = "WAITING"        # 재시도 쿨다운 중 (중간 상태)
    STALLED = "STALLED"        # 프론티어는 있으나 모든 후보가 실패/제외
    COLLISION = "COLLISION"    # footprint 가 정답 지도의 점유 셀과 충돌
    LOOP = "LOOP"              # 동일 상태·목표 반복
    TIMEOUT = "TIMEOUT"        # 최대 step 또는 시뮬레이션 시간 초과
    FAILED = "FAILED"          # 입력 또는 내부 오류


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    yaw: float

    def __str__(self) -> str:
        return f"({self.x:.3f}, {self.y:.3f}, {math.degrees(self.yaw):.1f}deg)"


@dataclass(frozen=True)
class GridSpec:
    """격자 기하. 셀 인덱스는 좌하단 원점 기준 (map 프레임과 같은 방향)."""

    width: int
    height: int
    resolution: float
    origin_x: float
    origin_y: float

    def world_to_cell(self, x: float, y: float) -> tuple[int, int]:
        return (
            math.floor((x - self.origin_x) / self.resolution),
            math.floor((y - self.origin_y) / self.resolution),
        )

    def cell_to_world(self, col: int, row: int) -> tuple[float, float]:
        """셀 중심의 world 좌표."""
        return (
            self.origin_x + (col + 0.5) * self.resolution,
            self.origin_y + (row + 0.5) * self.resolution,
        )

    def contains(self, col: int, row: int) -> bool:
        return 0 <= col < self.width and 0 <= row < self.height

    def index(self, col: int, row: int) -> int:
        return row * self.width + col


@dataclass(frozen=True)
class RobotSpec:
    """차체 제약. 기본값은 실측값이며 CLI 로 덮어쓸 수 있다."""

    length_m: float = FOOTPRINT_LENGTH_M
    width_m: float = FOOTPRINT_WIDTH_M
    wheelbase_m: float = WHEELBASE_M
    min_turning_radius_m: float = MIN_TURNING_RADIUS_M
    speed_mps: float = DRIVE_SPEED_MPS
    padding_m: float = FOOTPRINT_PADDING_M

    @property
    def inscribed_radius_m(self) -> float:
        return self.width_m / 2.0 + self.padding_m

    @property
    def circumscribed_radius_m(self) -> float:
        return math.hypot(self.length_m / 2.0 + self.padding_m,
                          self.width_m / 2.0 + self.padding_m)

    def footprint_corners(self, pose: Pose) -> tuple[tuple[float, float], ...]:
        """pose 에서의 footprint 사각형 네 꼭짓점 (padding 포함)."""
        half_l = self.length_m / 2.0 + self.padding_m
        half_w = self.width_m / 2.0 + self.padding_m
        cos_t, sin_t = math.cos(pose.yaw), math.sin(pose.yaw)
        local = ((half_l, half_w), (half_l, -half_w),
                 (-half_l, -half_w), (-half_l, half_w))
        return tuple(
            (pose.x + lx * cos_t - ly * sin_t, pose.y + lx * sin_t + ly * cos_t)
            for lx, ly in local
        )


@dataclass(frozen=True)
class InflationSpec:
    """Nav2 InflationLayer 재현. 프로필 간 유일한 costmap 차이가 이 반경이다."""

    inflation_radius_m: float
    cost_scaling_factor: float = 3.0

    def cost_at_distance(self, distance_m: float, inscribed_m: float) -> int:
        """장애물까지 distance 인 칸의 비용. nav2 InflationLayer::computeCost 와 동일."""
        if distance_m <= 0.0:
            return COST_LETHAL
        if distance_m <= inscribed_m:
            return COST_INSCRIBED
        if distance_m > self.inflation_radius_m:
            return COST_FREE
        factor = math.exp(
            -self.cost_scaling_factor * (distance_m - inscribed_m)
        )
        return int(round(COST_INFLATION_CEILING * factor))


@dataclass(frozen=True)
class LidarSpec:
    """가상 360도 LiDAR. 기본은 결정론적(노이즈 0)."""

    max_range_m: float = 8.0
    min_range_m: float = 0.20          # ydlidar range_min 실값
    angle_increment_deg: float = 1.0
    range_noise_m: float = 0.0         # 0 이면 결정론적

    @property
    def beam_count(self) -> int:
        return max(1, int(round(360.0 / self.angle_increment_deg)))


@dataclass(frozen=True)
class FrontierParams:
    """explore_lite 의 프론티어 검출·비용 파라미터.

    비용식은 이 저장소의 explore.params.yaml 주석이 명시한 그대로다::

        cost = potential_scale * min_distance * res - gain_scale * size * res

    (frontier_search.cpp:192. heading 항은 존재하지 않는다 -- orientation_scale 은
    선언만 되고 FrontierSearch 로 전달되지 않는 죽은 파라미터다.)
    """

    min_frontier_size_m: float = 0.35
    potential_scale: float = 0.5
    gain_scale: float = 3.0
    approach_distance_m: float = 0.25
    max_approaches: int = 1
    candidate_spacing_m: float = 0.20
    # 접근점을 clearance 로 고를지 (v0.2.6 후보) 아니면 고정 홉수로 후퇴할지 (현행)
    clearance_aware_approach: bool = False
    # clearance_aware_approach 일 때 요구할 최소 여유. None 이면 inscribed 사용.
    required_clearance_m: float | None = None


@dataclass(frozen=True)
class PlannerParams:
    """Nav2 SmacPlannerHybrid 파라미터. 값은 nav2.params.yaml.template 에서 온다."""

    motion_model: MotionModel
    tolerance_m: float = 0.20
    allow_unknown: bool = True
    angle_quantization_bins: int = 64
    max_planning_time_sec: float = 3.5
    max_iterations: int = 1_000_000
    # 아래 네 개가 traversal cost 를 만든다. NodeHybrid::getTraversalCost 참조.
    reverse_penalty: float = 2.0
    change_penalty: float = 0.0
    non_straight_penalty: float = 1.2
    cost_penalty: float = 2.0
    retrospective_penalty: float = 0.025
    # a3d7d62: 플래너는 allow_unknown 으로 UNKNOWN 을 지날 수 있지만, explore
    # 오버레이가 **반환된 경로**의 UNKNOWN 통과 길이를 재서 이 값을 넘으면 거부한다.
    # 프론티어 자세는 필연적으로 차체 일부가 미지 칸 옆에 놓이므로 약간은 허용해야
    # 하고(그렇지 않으면 모든 목표가 막힌다), 긴 미지 지름길은 막아야 한다.
    # None 이면 검사하지 않는다 (a3d7d62 이전 프로필).
    max_unknown_path_length_m: float | None = None


@dataclass(frozen=True)
class RetryParams:
    """실패 후보의 재시도·배제 정책."""

    max_attempts: int = 2
    retry_delay_sec: float = 15.0
    # explore.cpp 는 tolerance=5 셀을 체비셰프로 비교해 0.5x0.5 m 상자를 만든다.
    merge_radius_cells: int = 5
    # LOCAL_FREE_GROWTH 용. explore.params.yaml 의 frontier_recheck_* 에 대응한다.
    recheck_radius_m: float = 0.40
    recheck_min_free_cells: int = 12
    # a3d7d62: 목표 하나가 되살아날 수 있는 최대 횟수. 0 이면 재평가 없음.
    # 이 상한이 없으면 반경 안 셀 수(약 201)/12 = 약 16회까지 되살아나 stall
    # 신호 도달이 지연된다.
    max_reactivations: int = 1
    merge_metric: MergeMetric = MergeMetric.CHEBYSHEV
    blacklist_mode: BlacklistMode = BlacklistMode.COORDINATE_COOLDOWN
    # planner_frequency 0.15 -> upstream 의 uint16_t 캐스트로 6666 ms 가 된다.
    planner_period_sec: float = 6.666
    # 기록용이며 **이 시뮬레이터는 모델링하지 않는다.**
    #
    # 실제 explore 에서 progress_timeout 이 발화하는 조건은 "목표를 향해 주행 중인데
    # 가까워지지 않는다" 이고, 그 상황은 컨트롤러가 실패할 때 생긴다. 이 시뮬레이터는
    # 컨트롤러가 없어서 계획 경로를 그대로 따라가므로 목표는 항상 종결된다. 게다가
    # 속도 0.09 m/s 에 90 s 면 8.1 m 인데 대부분의 경로가 그보다 짧다.
    #
    # 따라서 이 값을 profiles 에 적어 두는 것은 프로필의 provenance 를 완전하게
    # 남기기 위한 것이고, 이 값에 의존하는 결론을 내면 안 된다.
    progress_timeout_sec: float = 90.0


class GoalYawRule(Enum):
    """목표 자세를 정하는 규칙. v0.2.2 와 v0.2.5 의 유일한 알고리즘 차이."""

    # v0.2.2: atan2(approach - robot_pose). 로봇에서 목표까지의 현 방위.
    BEARING_FROM_ROBOT = "bearing_from_robot"
    # v0.2.5: atan2(frontier_free - approach). 목표점의 자유공간 접선.
    APPROACH_TO_BOUNDARY = "approach_to_boundary"
    # v0.2.6 후보: 위와 같으나 더 긴 기준선으로 양자화 오차를 줄인다.
    APPROACH_TO_BOUNDARY_LONG_BASELINE = "approach_to_boundary_long_baseline"


@dataclass(frozen=True)
class ProfileProvenance:
    """이 프로필의 각 값이 어느 태그·파일에서 왔는지. 추측 금지의 증거."""

    tag: str
    commit: str
    sources: tuple[str, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Profile:
    """한 릴리스의 매핑 동작을 재현하는 설정 묶음."""

    name: str
    provenance: ProfileProvenance
    frontier: FrontierParams
    planner: PlannerParams
    retry: RetryParams
    inflation: InflationSpec
    goal_yaw_rule: GoalYawRule
    # 동시에 활성 목표를 최대 1개로 제한할지.
    single_active_goal: bool = True
    # 활성 목표가 있는 동안 더 좋은 후보가 생기면 갈아탈지.
    #
    # v0.2.2 와 v0.2.5 의 패치는 **둘 다** `if (goal_active_) return;` 이라
    # 갈아타지 않는다 (직접 확인). upstream 원본은 `same_goal && goal_active_`
    # 조건이라 매 지도 갱신마다 갈아탄다. 패치 주석이 밝힌 이유는:
    # "Humble 은 그 선점을 실제 ABORT 와 구별하지 못해 이전 프론티어의 재시도
    # 예산을 소모한다". 그 주장을 시뮬레이터로 검증하려고 이 플래그를 둔다.
    retarget_while_active: bool = False
    # 갈아탈 때 이전 목표의 취소 완료를 기다릴지. 기다리지 않으면 이전 목표가
    # cancel_latency_sec 동안 살아 있는 것으로 계상된다 (stale_goal_retained_sec).
    await_cancel_before_new_goal: bool = False
    # 취소 요청부터 취소 완료까지의 모델 지연. 계획 tick 한 주기를 기본으로 둔다.
    # 실측값이 아니라 모델 파라미터이므로 리포트에 그대로 노출한다.
    cancel_latency_sec: float = 6.666
    # 사전검사 실패 시 다른 접근점으로 재시도할지 (v0.2.6 후보)
    retry_with_alternate_approach: bool = False


# ---------------------------------------------------------------------------
# 실행 중 기록되는 자료
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrontierCandidate:
    """한 프론티어 클러스터와 그로부터 유도된 목표."""

    candidate_id: str
    cluster_cells: tuple[tuple[int, int], ...]
    size_m: float
    min_distance_m: float
    cost: float
    failure_key: tuple[float, float]
    # 경계에 맞닿은 FREE 셀 (v0.2.5 의 frontier_free)
    boundary_free: tuple[float, float] | None
    # 실제로 목표로 보낼 지점
    approach: tuple[float, float] | None
    goal_yaw: float | None
    approach_clearance_m: float | None
    approach_options: tuple[tuple[tuple[float, float], float, float], ...] = ()
    verdict: CandidateVerdict = CandidateVerdict.NOT_EVALUATED
    reject_detail: str = ""


@dataclass(frozen=True)
class PathSample:
    """계획 경로 위의 한 자세와 그 지점의 지도 상태."""

    pose: Pose
    reverse: bool
    cell_state: CellState
    inflation_cost: int


@dataclass(frozen=True)
class PlannedPath:
    """사전검사를 통과한 경로. flavor 로 근사 여부를 항상 밝힌다."""

    flavor: PlannerFlavor
    samples: tuple[PathSample, ...]
    length_m: float
    reverse_length_m: float
    direction_changes: int
    traversal_cost: float
    free_cells: int
    unknown_cells: int
    occupied_cells: int
    planning_time_sec: float
    iterations: int
    timed_out: bool = False

    @property
    def crosses_occupied(self) -> bool:
        return self.occupied_cells > 0


@dataclass(frozen=True)
class FailureRecord:
    """한 좌표(또는 상자)에 누적된 실패."""

    x: float
    y: float
    attempts: int
    retry_after_sec: float
    last_reason: str
    map_revision_at_failure: int
    reactivated_by_map_change: bool = False
    # 실패 당시 목표 주변 recheck_radius_m 안의 FREE 셀 수. LOCAL_FREE_GROWTH 가
    # 이 값 대비 증가분을 본다.
    local_free_cells: int = 0
    # 이 레코드가 되살아난 횟수. max_reactivations 와 비교한다.
    reactivations: int = 0


@dataclass
class StepRecord:
    """한 계획 tick 의 전체 기록. trace.jsonl 한 줄이 된다."""

    step: int
    sim_time_sec: float
    map_revision: int
    pose: Pose
    state: TerminationState | None
    candidates: list[FrontierCandidate] = field(default_factory=list)
    selected_id: str | None = None
    path: PlannedPath | None = None
    travelled: list[Pose] = field(default_factory=list)
    discovered_ratio: float = 0.0
    known_cells: int = 0
    note: str = ""
    # 취소 상태 전이 기록: (sim_time, event)
    goal_events: list[tuple[float, str]] = field(default_factory=list)


@dataclass
class RunMetrics:
    """8절의 비교 지표."""

    final_state: str = TerminationState.FAILED.value
    discovered_ratio: float = 0.0
    ground_truth_free_cells: int = 0
    discovered_free_cells: int = 0
    total_travel_m: float = 0.0
    net_displacement_m: float = 0.0
    goals_sent: int = 0
    goals_succeeded_without_motion: int = 0
    plan_successes: int = 0
    plan_failures: int = 0
    unknown_traverse_m: float = 0.0
    min_wall_clearance_m: float = float("inf")
    collisions: int = 0
    reverse_distance_m: float = 0.0
    reverse_ratio: float = 0.0
    direction_changes: int = 0
    stale_goal_retained_sec: float = 0.0
    frontier_retries: int = 0
    permanently_excluded: int = 0
    compute_time_sec: float = 0.0
    steps: int = 0
    # 근사 플래너가 예산을 소진해 실패한 횟수. 이건 실물 Nav2(C++)의 실패가
    # 아니라 시뮬레이터의 한계다. 0 이 아니면 그 실행의 계획 실패 수치를
    # 그대로 믿으면 안 된다.
    plan_budget_exhausted: int = 0
    # 경로는 나왔으나 UNKNOWN 통과가 허용치를 넘어 거부된 횟수 (a3d7d62).
    plan_rejected_unknown: int = 0
    # 국소 FREE 성장으로 되살아난 실패 레코드 수.
    failures_reactivated: int = 0
    planner_flavor: str = PlannerFlavor.APPROXIMATE.value


@dataclass
class SimResult:
    profile_name: str
    map_yaml: str
    start_pose: Pose
    metrics: RunMetrics
    steps: list[StepRecord] = field(default_factory=list)
    error: str = ""
    # 최종 발견 지도. 리포트가 이것으로 프레임을 그린다. 없으면 리포트가 궤적만으로
    # 지도를 성기게 복원하는데, 그러면 화면의 지도와 옆에 적힌 discovered_ratio 가
    # 서로를 부정한다 -- 증거로 쓸 수 없는 리포트가 된다.
    discovered_cells: list[int] = field(default_factory=list)
    # 셀별 최초 관측 step. 슬라이더가 발견 과정을 단계별로 재생하는 데 쓴다.
    first_seen_step: list[int] = field(default_factory=list)


def normalize_angle(angle: float) -> float:
    """(-pi, pi] 로 정규화."""
    wrapped = math.fmod(angle + math.pi, 2.0 * math.pi)
    if wrapped <= 0.0:
        wrapped += 2.0 * math.pi
    return wrapped - math.pi


def angle_difference(a: float, b: float) -> float:
    return normalize_angle(a - b)


def polygon_overlaps_cell(
    corners: Sequence[tuple[float, float]],
    cell_min_x: float,
    cell_min_y: float,
    cell_size: float,
) -> bool:
    """회전 사각형과 축정렬 셀 사각형의 겹침 (SAT).

    셀 중심 샘플링은 얇은 벽을 지나칠 수 있어 쓰지 않는다. 두 볼록 다각형의
    분리축 검사는 정확하고, 축 후보는 두 도형의 변 법선 4개뿐이다.
    """
    cell = (
        (cell_min_x, cell_min_y),
        (cell_min_x + cell_size, cell_min_y),
        (cell_min_x + cell_size, cell_min_y + cell_size),
        (cell_min_x, cell_min_y + cell_size),
    )
    for polygon in (corners, cell):
        count = len(polygon)
        for index in range(count):
            x0, y0 = polygon[index]
            x1, y1 = polygon[(index + 1) % count]
            axis_x, axis_y = -(y1 - y0), x1 - x0
            length = math.hypot(axis_x, axis_y)
            if length < 1e-12:
                continue
            axis_x /= length
            axis_y /= length
            a_lo = min(px * axis_x + py * axis_y for px, py in corners)
            a_hi = max(px * axis_x + py * axis_y for px, py in corners)
            b_lo = min(px * axis_x + py * axis_y for px, py in cell)
            b_hi = max(px * axis_x + py * axis_y for px, py in cell)
            if a_hi < b_lo or b_hi < a_lo:
                return False
    return True
