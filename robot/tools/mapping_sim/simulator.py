"""탐사 루프. 정답 지도와 발견 지도를 분리한 채 종료까지 연속 재현한다.

이 파일이 재현하는 것은 explore_lite 패치 + Nav2 의 **상호작용**이다. 한 tick 은
다음 순서로 돈다::

    프론티어 검출 -> 후보 판정(블랙리스트/쿨다운/크기) -> 최선 후보 선택
    -> 접근점·목표 yaw 계산 -> 경로 사전검사 -> 목표 전송 -> 경로 추종
    -> 추종 중 관측으로 발견 지도 갱신 -> 다음 tick

종료 상태에서 COMPLETE 와 STALLED 를 섞지 않는 것이 이 시뮬레이터의 핵심 목적이다.
실제 시스템은 둘을 구분하지 못해 19% 완성된 지도를 "완료" 로 저장하고 있었다.
"""

from __future__ import annotations

import math
import random
import time
from collections import deque
from dataclasses import dataclass, replace
from typing import Sequence

from . import frontier as frontier_mod
from .contracts import (
    BlacklistMode,
    CandidateVerdict,
    CellState,
    FailureRecord,
    FrontierCandidate,
    GridSpec,
    LidarSpec,
    MergeMetric,
    PlannedPath,
    PlannerFlavor,
    PlannerParams,
    Pose,
    Profile,
    RobotSpec,
    RunMetrics,
    SimResult,
    StepRecord,
    TerminationState,
)
from .planner import PlannerBackend, default_backend
from .worldmodel import DiscoveredMap, GroundTruth


class StartPoseError(ValueError):
    """시작 자세가 쓸 수 없을 때. 후보를 함께 담아 던진다."""

    def __init__(self, message: str, candidates: Sequence[tuple[float, float]]):
        super().__init__(message)
        self.candidates = tuple(candidates)


@dataclass(frozen=True)
class SimSettings:
    max_steps: int = 2000
    max_sim_time_sec: float = 3600.0
    lidar: LidarSpec = LidarSpec()
    robot: RobotSpec = RobotSpec()
    seed: int = 0
    # 관측 간격. 이보다 많이 움직이면 다시 스캔한다.
    observe_interval_m: float = 0.05
    # 지도가 바뀌면 추종을 끊고 재계획할지. 실제 explore 는 goal_active_ 가드
    # 때문에 목표가 끝날 때까지 재계획하지 않으므로 기본은 False 다.
    replan_on_map_change: bool = False
    # 같은 (로봇 셀, 각도 bin, 선택 접근점) 이 이만큼 연속되면 LOOP.
    loop_window: int = 6
    # 실제 이동으로 인정하는 최소 순변위. 이보다 작으면 "움직이지 않은 성공".
    motion_epsilon_m: float = 0.05


class FailureLedger:
    """실패 후보 원장. 두 배제 방식을 모두 구현해 나란히 비교한다.

    현행(COORDINATE_COOLDOWN): explore.cpp 그대로. 체비셰프 5셀 상자로 병합하고
    시도횟수가 max_attempts 에 닿으면 **영구** 배제한다. clear() 가 없다.

    후보(MAP_REVISION_SOFT): 배제를 지도 개정에 묶는다. 지도가 바뀌면 그 실패는
    낡은 정보에 근거한 것이므로 시도횟수를 되돌려 재평가한다. 지도가 그대로면
    현행과 똑같이 동작하므로 무한 재시도가 되지 않는다.
    """

    def __init__(self, profile: Profile, resolution: float) -> None:
        self._retry = profile.retry
        self._resolution = resolution
        self._records: list[FailureRecord] = []
        self._reactivations = 0

    @property
    def radius_m(self) -> float:
        return self._retry.merge_radius_cells * self._resolution

    def _hit(self, x: float, y: float) -> int | None:
        radius = self.radius_m
        for index, record in enumerate(self._records):
            dx = abs(x - record.x)
            dy = abs(y - record.y)
            if self._retry.merge_metric is MergeMetric.CHEBYSHEV:
                inside = dx < radius and dy < radius
            else:
                inside = math.hypot(dx, dy) < radius
            if inside:
                return index
        return None

    def is_blacklisted(self, x: float, y: float) -> bool:
        index = self._hit(x, y)
        if index is None:
            return False
        return self._records[index].attempts >= self._retry.max_attempts

    def is_cooling(self, x: float, y: float, now: float) -> bool:
        index = self._hit(x, y)
        if index is None:
            return False
        record = self._records[index]
        return (
            record.attempts < self._retry.max_attempts
            and now < record.retry_after_sec
        )

    def earliest_retry_after(self, now: float) -> float | None:
        pending = [
            record.retry_after_sec
            for record in self._records
            if record.attempts < self._retry.max_attempts
            and record.retry_after_sec > now
        ]
        return min(pending) if pending else None

    def record(
        self,
        x: float,
        y: float,
        reason: str,
        now: float,
        map_revision: int,
        discovered: DiscoveredMap | None = None,
    ) -> FailureRecord:
        index = self._hit(x, y)
        retry_after = now + self._retry.retry_delay_sec
        # 실패 시점의 주변 FREE 셀 수를 기준선으로 남긴다. LOCAL_FREE_GROWTH 가
        # 이 값 대비 증가분을 보므로, 기준선을 갱신하지 않으면 한 번 자란 지도로
        # 계속 되살아난다.
        local_free = (
            self.count_local_free_cells(x, y, discovered)
            if discovered is not None
            else 0
        )
        if index is None:
            record = FailureRecord(
                x=x,
                y=y,
                attempts=1,
                retry_after_sec=retry_after,
                last_reason=reason,
                map_revision_at_failure=map_revision,
                local_free_cells=local_free,
            )
            self._records.append(record)
            return record
        previous = self._records[index]
        record = replace(
            previous,
            attempts=previous.attempts + 1,
            retry_after_sec=retry_after,
            last_reason=reason,
            map_revision_at_failure=map_revision,
            local_free_cells=local_free,
        )
        self._records[index] = record
        return record

    def count_local_free_cells(
        self, x: float, y: float, discovered: DiscoveredMap
    ) -> int:
        """(x, y) 중심 recheck_radius_m 원 안의 FREE 셀 수.

        explore.cpp 의 ``countLocalFreeCells`` 와 같다 -- 원형 마스크이고
        ``getCost(...) == FREE_SPACE`` 를 센다. explore 는 costmap_topic 이 raw
        ``map`` 이므로 인플레이션이 없는 발견 지도를 그대로 보는 것이 맞다.
        """
        spec = discovered.spec
        radius_cells = int(math.ceil(self._retry.recheck_radius_m / spec.resolution))
        if radius_cells <= 0:
            return 0
        center_col, center_row = spec.world_to_cell(x, y)
        if not spec.contains(center_col, center_row):
            return 0
        free_cells = 0
        for dy in range(-radius_cells, radius_cells + 1):
            for dx in range(-radius_cells, radius_cells + 1):
                if dx * dx + dy * dy > radius_cells * radius_cells:
                    continue
                col, row = center_col + dx, center_row + dy
                if not spec.contains(col, row):
                    continue
                if discovered.state_at_cell(col, row) is CellState.FREE:
                    free_cells += 1
        return free_cells

    def note_local_free_growth(self, discovered: DiscoveredMap) -> int:
        """v0.2.6 (7c9caee): 목표 주변 FREE 가 자란 실패만 되살린다.

        MAP_REVISION_SOFT 와 달리 지도 다른 곳의 변화로는 되돌아오지 않는다.
        되살릴 때 기준선(local_free_cells)을 새 값으로 갱신하므로, 같은 성장으로
        두 번 되살아나지 않는다 -- 그것이 무한 재시도를 막는 장치다.
        """
        if self._retry.blacklist_mode is not BlacklistMode.LOCAL_FREE_GROWTH:
            return 0
        reactivated = 0
        for index, record in enumerate(self._records):
            if record.attempts < self._retry.max_attempts:
                continue
            # a3d7d62: 되살릴 수 있는 횟수에 상한을 둔다. 없으면 반경 안 셀 수
            # (약 201)/12 = 약 16회까지 되살아나 stall 신호가 늦어진다.
            if record.reactivations >= self._retry.max_reactivations:
                continue
            free_cells = self.count_local_free_cells(record.x, record.y, discovered)
            if free_cells < record.local_free_cells + self._retry.recheck_min_free_cells:
                continue
            self._records[index] = replace(
                record,
                attempts=0,
                retry_after_sec=0.0,
                local_free_cells=free_cells,
                reactivations=record.reactivations + 1,
                reactivated_by_map_change=True,
            )
            reactivated += 1
        self._reactivations += reactivated
        return reactivated

    def note_map_revision(self, revision: int) -> int:
        """지도가 바뀌었다. soft 모드면 낡은 근거의 배제를 되돌린다."""
        if self._retry.blacklist_mode is not BlacklistMode.MAP_REVISION_SOFT:
            return 0
        reactivated = 0
        for index, record in enumerate(self._records):
            if record.map_revision_at_failure >= revision:
                continue
            if record.attempts == 0:
                continue
            self._records[index] = replace(
                record,
                attempts=0,
                retry_after_sec=0.0,
                map_revision_at_failure=revision,
                reactivated_by_map_change=True,
            )
            reactivated += 1
        self._reactivations += reactivated
        return reactivated

    @property
    def reactivations(self) -> int:
        return self._reactivations

    def permanently_excluded(self) -> int:
        return sum(
            1
            for record in self._records
            if record.attempts >= self._retry.max_attempts
        )

    def total_attempts(self) -> int:
        return sum(record.attempts for record in self._records)

    def snapshot(self) -> list[FailureRecord]:
        return list(self._records)


def unknown_path_length_m(path: PlannedPath) -> float:
    """경로가 UNKNOWN 칸을 통과하는 누적 길이.

    explore.cpp 의 ``pathCrossesUnsafeUnknown`` 과 같은 방식이다 -- 경로를
    해상도 절반 간격으로 샘플하고, UNKNOWN 칸에 놓인 샘플이 대표하는 구간
    길이를 더한다. 우리 플래너는 이미 그 간격으로 샘플을 만들어 두므로 샘플 간
    거리를 그대로 쓴다.

    구간 길이를 쓰는 것이 중요하다. 샘플 **개수**로 세면 해상도나 프리미티브
    길이가 바뀔 때 같은 경로가 다르게 판정된다.
    """
    total = 0.0
    previous = None
    for sample in path.samples:
        if previous is not None and sample.cell_state is CellState.UNKNOWN:
            total += math.hypot(
                sample.pose.x - previous.x, sample.pose.y - previous.y
            )
        previous = sample.pose
    return total


def path_crosses_unsafe_unknown(
    path: PlannedPath, params: PlannerParams
) -> bool:
    """a3d7d62: 점유 칸을 지나거나 UNKNOWN 통과가 허용치를 넘으면 거부.

    실제 구현은 점유 칸을 만나면 즉시 거부하므로 여기서도 같이 본다. 우리
    플래너는 애초에 점유 칸을 지나는 경로를 만들지 않지만, 판정을 한곳에 모아
    두면 나중에 플래너를 바꿔도 이 계약이 유지된다.
    """
    if path.occupied_cells > 0:
        return True
    limit = params.max_unknown_path_length_m
    if limit is None:
        return False
    return unknown_path_length_m(path) > limit


def validate_start_pose(
    ground_truth: GroundTruth, start: Pose, robot: RobotSpec
) -> None:
    """시작 자세가 못 쓸 자세면 FREE 후보를 보여주고 실패한다.

    임의로 다른 곳에서 시작하지 않는다 -- 조용히 옮기면 비교 결과가 무의미해진다.
    """
    spec = ground_truth.spec
    col, row = spec.world_to_cell(start.x, start.y)
    if not spec.contains(col, row):
        raise StartPoseError(
            f"시작 지점 ({start.x:.3f}, {start.y:.3f}) 이 지도 밖이다. "
            f"지도 범위: x {spec.origin_x:.3f}~"
            f"{spec.origin_x + spec.width * spec.resolution:.3f}, "
            f"y {spec.origin_y:.3f}~"
            f"{spec.origin_y + spec.height * spec.resolution:.3f}",
            ground_truth.free_start_candidates(robot),
        )
    state = ground_truth.state_at_cell(col, row)
    if state is not CellState.FREE:
        raise StartPoseError(
            f"시작 지점 ({start.x:.3f}, {start.y:.3f}) 의 셀이 {state.name} 이다. "
            "FREE 여야 한다.",
            ground_truth.free_start_candidates(robot),
        )
    if ground_truth.footprint_collides(start, robot):
        clearance = ground_truth.min_obstacle_distance(
            start.x, start.y, robot.circumscribed_radius_m * 2.0
        )
        raise StartPoseError(
            f"시작 지점 ({start.x:.3f}, {start.y:.3f}, "
            f"{math.degrees(start.yaw):.1f}deg) 에서 footprint 가 충돌한다. "
            f"최근접 장애물 {clearance:.3f} m, 필요한 여유 "
            f"{robot.inscribed_radius_m:.3f} m 이상.",
            ground_truth.free_start_candidates(robot),
        )


def _classify(
    candidates: list[FrontierCandidate], ledger: FailureLedger, now: float
) -> list[FrontierCandidate]:
    """블랙리스트·쿨다운 판정을 후보에 반영한다. 정렬은 바꾸지 않는다."""
    judged: list[FrontierCandidate] = []
    for candidate in candidates:
        if candidate.verdict is not CandidateVerdict.NOT_EVALUATED:
            judged.append(candidate)
            continue
        if candidate.approach is None:
            judged.append(
                replace(candidate, verdict=CandidateVerdict.NO_APPROACH_CELL)
            )
            continue
        ax, ay = candidate.approach
        if ledger.is_blacklisted(ax, ay):
            judged.append(
                replace(candidate, verdict=CandidateVerdict.BLACKLISTED)
            )
            continue
        if ledger.is_cooling(ax, ay, now):
            judged.append(
                replace(candidate, verdict=CandidateVerdict.COOLING_DOWN)
            )
            continue
        judged.append(candidate)
    return judged


def _first_selectable(candidates: Sequence[FrontierCandidate]) -> int | None:
    for index, candidate in enumerate(candidates):
        if candidate.verdict is CandidateVerdict.NOT_EVALUATED:
            return index
    return None


def _terminal_state_when_nothing_selectable(
    candidates: Sequence[FrontierCandidate], ledger: FailureLedger, now: float
) -> tuple[TerminationState, str]:
    """선택할 후보가 없을 때의 종료 상태.

    COMPLETE 는 **프론티어 셀이 하나도 없을 때만** 쓴다. 크기 미달로 버려진
    프론티어가 남아 있으면 STALLED 다 -- 그게 실제로 지도를 미완성으로 남기는
    조건이고, min_frontier_size 0.35 가 개구부를 버리는 문제를 그대로 드러낸다.
    """
    if not candidates:
        return TerminationState.COMPLETE, "프론티어 셀이 없다"
    if ledger.earliest_retry_after(now) is not None:
        return TerminationState.WAITING, "모든 후보가 쿨다운 중"
    only_too_small = all(
        candidate.verdict is CandidateVerdict.TOO_SMALL
        for candidate in candidates
    )
    if only_too_small:
        return (
            TerminationState.STALLED,
            f"프론티어 {len(candidates)}개가 모두 min_frontier_size 미달로 "
            "버려졌다 (지도가 완성된 것이 아니다)",
        )
    reasons: dict[str, int] = {}
    for candidate in candidates:
        reasons[candidate.verdict.value] = reasons.get(candidate.verdict.value, 0) + 1
    detail = ", ".join(f"{name}={count}" for name, count in sorted(reasons.items()))
    return (
        TerminationState.STALLED,
        f"프론티어는 남아 있으나 선택 가능한 후보가 없다 ({detail})",
    )


def run(
    profile: Profile,
    ground_truth: GroundTruth,
    start: Pose,
    settings: SimSettings,
    backend: PlannerBackend | None = None,
) -> SimResult:
    """한 프로필로 탐사를 종료까지 돌린다."""

    robot = settings.robot
    validate_start_pose(ground_truth, start, robot)

    planner = backend if backend is not None else default_backend()
    rng = (
        random.Random(settings.seed)
        if settings.lidar.range_noise_m > 0.0
        else None
    )

    spec = ground_truth.spec
    discovered = DiscoveredMap(spec)
    ledger = FailureLedger(profile, spec.resolution)
    metrics = RunMetrics(
        ground_truth_free_cells=ground_truth.free_cell_count(),
        planner_flavor=getattr(planner, "flavor", PlannerFlavor.APPROXIMATE).value,
    )
    result = SimResult(
        profile_name=profile.name,
        map_yaml="",
        start_pose=start,
        metrics=metrics,
    )

    pose = start
    sim_time = 0.0
    signatures: deque[tuple[int, int, int, int, int]] = deque(
        maxlen=settings.loop_window
    )

    def observe(at: Pose) -> bool:
        revealed = ground_truth.raycast(at, settings.lidar, rng)
        changed = discovered.reveal(revealed)
        if changed:
            ledger.note_map_revision(discovered.revision)
            ledger.note_local_free_growth(discovered)
        return changed

    discovered.mark_step(0)

    observe(pose)
    metrics.min_wall_clearance_m = ground_truth.min_obstacle_distance(
        pose.x, pose.y, robot.circumscribed_radius_m * 3.0
    )

    terminal: TerminationState | None = None
    step = 0

    while step < settings.max_steps:
        step += 1
        discovered.mark_step(step)
        record = StepRecord(
            step=step,
            sim_time_sec=sim_time,
            map_revision=discovered.revision,
            pose=pose,
            state=None,
            discovered_ratio=_discovered_ratio(discovered, metrics),
            known_cells=discovered.known_cell_count(),
        )

        if sim_time > settings.max_sim_time_sec:
            terminal = TerminationState.TIMEOUT
            record.state = terminal
            record.note = f"시뮬레이션 시간 {sim_time:.1f}s 초과"
            result.steps.append(record)
            break

        candidates = frontier_mod.detect(
            discovered, pose, profile.frontier, robot, profile.goal_yaw_rule
        )
        candidates = _classify(candidates, ledger, sim_time)
        pick = _first_selectable(candidates)

        if pick is None:
            state, note = _terminal_state_when_nothing_selectable(
                candidates, ledger, sim_time
            )
            record.candidates = candidates
            record.note = note
            if state is TerminationState.WAITING:
                record.state = TerminationState.WAITING
                result.steps.append(record)
                next_retry = ledger.earliest_retry_after(sim_time)
                # 쿨다운이 풀리는 시각을 지나는 **첫 계획 tick** 으로 건너뛴다.
                # explore 는 임의 시각이 아니라 타이머 tick 에서만 재계획한다.
                period = profile.retry.planner_period_sec
                if next_retry is None:
                    sim_time += period
                else:
                    ticks = math.ceil((next_retry - sim_time) / period)
                    sim_time += max(1, ticks) * period
                continue
            terminal = state
            record.state = terminal
            result.steps.append(record)
            break

        chosen = candidates[pick]
        assert chosen.approach is not None and chosen.goal_yaw is not None
        goal = Pose(chosen.approach[0], chosen.approach[1], chosen.goal_yaw)

        attempted: list[tuple[float, float]] = []
        path: PlannedPath | None = None
        plan_started = time.monotonic()
        while True:
            attempted.append((goal.x, goal.y))
            path = planner.plan(
                discovered, pose, goal, profile.planner, profile.inflation, robot
            )
            # a3d7d62: 경로가 나와도 UNKNOWN 통과가 허용치를 넘으면 거부한다.
            # 플래너는 allow_unknown 으로 탐사적으로 두고, 실행 가능한 경로인지는
            # 오버레이가 따로 판정하는 구조다.
            if path is not None and path_crosses_unsafe_unknown(
                path, profile.planner
            ):
                metrics.plan_rejected_unknown += 1
                unknown_reject = True
                path = None
            else:
                unknown_reject = False
            if path is not None:
                break
            metrics.plan_failures += 1
            # "경로가 없다" 와 "파이썬 backend 가 예산을 소진했다" 를 구분해 기록한다.
            # 후자는 시뮬레이터의 한계이고 실물 Nav2(C++)라면 성공했을 수 있으므로,
            # 뭉개면 프로필 비교가 조용히 오염된다.
            timed_out = bool(getattr(planner, "last_timeout", False))
            if unknown_reject:
                reason = "path_crosses_unknown"
            elif timed_out:
                reason = "planner_budget_exhausted"
            else:
                reason = "path_unavailable"
            if timed_out and not unknown_reject:
                metrics.plan_budget_exhausted += 1
            failure = ledger.record(
                goal.x, goal.y, reason, sim_time, discovered.revision, discovered
            )
            metrics.frontier_retries += 1
            if not profile.retry_with_alternate_approach:
                break
            alternates = frontier_mod.alternate_approaches(
                discovered,
                chosen,
                robot,
                profile.frontier,
                profile.goal_yaw_rule,
                attempted,
            )
            if not alternates:
                break
            (ax, ay), yaw, _clearance = alternates[0]
            goal = Pose(ax, ay, yaw)
        metrics.compute_time_sec += time.monotonic() - plan_started

        candidates[pick] = replace(
            chosen,
            verdict=(
                CandidateVerdict.SELECTED
                if path is not None
                else (
                    CandidateVerdict.PATH_CROSSES_UNKNOWN
                    if unknown_reject
                    else CandidateVerdict.PATH_UNAVAILABLE
                )
            ),
            approach=(goal.x, goal.y),
            goal_yaw=goal.yaw,
            reject_detail=(
                ""
                if path is not None
                else (
                    "UNKNOWN 통과 초과" if unknown_reject else "사전검사 실패"
                )
            ),
        )
        record.candidates = candidates

        if path is None:
            record.note = (
                f"경로 사전검사 실패. 시도 {ledger.total_attempts()}회, "
                f"영구 배제 {ledger.permanently_excluded()}개"
            )
            record.state = None
            result.steps.append(record)
            sim_time += profile.retry.planner_period_sec
            continue

        metrics.plan_successes += 1
        metrics.goals_sent += 1
        record.selected_id = chosen.candidate_id
        record.path = path
        record.goal_events.append((sim_time, "goal_accepted"))

        outcome = _follow(
            path=path,
            pose=pose,
            profile=profile,
            settings=settings,
            ground_truth=ground_truth,
            discovered=discovered,
            metrics=metrics,
            record=record,
            sim_time=sim_time,
            observe=observe,
        )
        pose = outcome.pose
        sim_time = outcome.sim_time
        record.travelled = outcome.trail

        if outcome.collided:
            terminal = TerminationState.COLLISION
            record.state = terminal
            record.note = (
                f"정답 지도의 점유 셀과 footprint 충돌: {outcome.collision_pose}"
            )
            metrics.collisions += 1
            result.steps.append(record)
            break

        if outcome.net_displacement_m < settings.motion_epsilon_m:
            metrics.goals_succeeded_without_motion += 1
            record.note = (
                f"목표를 성공으로 처리했으나 순변위 "
                f"{outcome.net_displacement_m:.3f} m (임계 "
                f"{settings.motion_epsilon_m:.3f} m)"
            )
        record.goal_events.append((sim_time, "goal_finished"))
        record.discovered_ratio = _discovered_ratio(discovered, metrics)
        record.known_cells = discovered.known_cell_count()

        signature = (
            *spec.world_to_cell(pose.x, pose.y),
            int(round(pose.yaw / (math.pi / 18.0))),
            *spec.world_to_cell(goal.x, goal.y),
        )
        signatures.append(signature)
        if (
            len(signatures) == signatures.maxlen
            and len(set(signatures)) == 1
        ):
            terminal = TerminationState.LOOP
            record.state = terminal
            record.note = (
                f"동일한 (자세, 목표) 조합이 {settings.loop_window}회 반복됐다"
            )
            result.steps.append(record)
            break

        result.steps.append(record)
        sim_time += profile.retry.planner_period_sec

    if terminal is None:
        terminal = TerminationState.TIMEOUT
        if result.steps:
            result.steps[-1].note += " / 최대 step 도달"

    metrics.final_state = terminal.value
    metrics.steps = step
    metrics.discovered_ratio = _discovered_ratio(discovered, metrics)
    metrics.discovered_free_cells = discovered.free_cell_count()
    metrics.net_displacement_m = math.hypot(pose.x - start.x, pose.y - start.y)
    metrics.permanently_excluded = ledger.permanently_excluded()
    metrics.failures_reactivated = ledger.reactivations
    if metrics.total_travel_m > 0.0:
        metrics.reverse_ratio = metrics.reverse_distance_m / metrics.total_travel_m
    if math.isinf(metrics.min_wall_clearance_m):
        metrics.min_wall_clearance_m = 0.0
    result.discovered_cells = discovered.flat_states()
    result.first_seen_step = discovered.first_seen_steps()
    return result


@dataclass
class _FollowOutcome:
    pose: Pose
    sim_time: float
    trail: list[Pose]
    collided: bool
    collision_pose: Pose | None
    net_displacement_m: float


def _follow(
    *,
    path: PlannedPath,
    pose: Pose,
    profile: Profile,
    settings: SimSettings,
    ground_truth: GroundTruth,
    discovered: DiscoveredMap,
    metrics: RunMetrics,
    record: StepRecord,
    sim_time: float,
    observe,
) -> _FollowOutcome:
    """계획 경로를 따라 실제로 움직인다. 충돌은 **정답 지도** 로만 판정한다."""

    robot = settings.robot
    start_pose = pose
    trail: list[Pose] = [pose]
    since_observation = 0.0
    metrics.direction_changes += path.direction_changes

    previous = pose
    for sample in path.samples:
        segment = math.hypot(sample.pose.x - previous.x, sample.pose.y - previous.y)
        metrics.total_travel_m += segment
        if sample.reverse:
            metrics.reverse_distance_m += segment
        if sample.cell_state is CellState.UNKNOWN:
            metrics.unknown_traverse_m += segment
        sim_time += segment / max(robot.speed_mps, 1e-9)
        previous = sample.pose

        if ground_truth.footprint_collides(sample.pose, robot):
            trail.append(sample.pose)
            return _FollowOutcome(
                pose=sample.pose,
                sim_time=sim_time,
                trail=trail,
                collided=True,
                collision_pose=sample.pose,
                net_displacement_m=math.hypot(
                    sample.pose.x - start_pose.x, sample.pose.y - start_pose.y
                ),
            )

        clearance = ground_truth.min_obstacle_distance(
            sample.pose.x, sample.pose.y, robot.circumscribed_radius_m * 3.0
        )
        metrics.min_wall_clearance_m = min(metrics.min_wall_clearance_m, clearance)

        trail.append(sample.pose)
        since_observation += segment
        if since_observation >= settings.observe_interval_m:
            since_observation = 0.0
            changed = observe(sample.pose)
            if changed and settings.replan_on_map_change:
                record.goal_events.append((sim_time, "replan_on_map_change"))
                break
            if changed and profile.retarget_while_active:
                # upstream 대조군: 여기서 갈아탄다. 취소 완료를 기다리지 않으므로
                # 이전 목표가 cancel_latency_sec 동안 살아 있는 것으로 계상한다.
                # 패치 주석의 주장(선점이 ABORT 로 오인돼 재시도 예산을 먹는다) 을
                # 그대로 모델링한다.
                if not profile.await_cancel_before_new_goal:
                    metrics.stale_goal_retained_sec += profile.cancel_latency_sec
                record.goal_events.append((sim_time, "preempted_by_retarget"))
                break

    return _FollowOutcome(
        pose=previous,
        sim_time=sim_time,
        trail=trail,
        collided=False,
        collision_pose=None,
        net_displacement_m=math.hypot(
            previous.x - start_pose.x, previous.y - start_pose.y
        ),
    )


def _discovered_ratio(discovered: DiscoveredMap, metrics: RunMetrics) -> float:
    """정답 지도의 FREE 셀 중 몇 %를 발견했는가.

    분모를 전체 셀이 아니라 정답 FREE 셀로 둔다. 지도 bbox 의 대부분은 벽 바깥의
    UNKNOWN 이라 전체 셀 기준 비율은 의미가 없다.
    """
    if metrics.ground_truth_free_cells <= 0:
        return 0.0
    return discovered.free_cell_count() / metrics.ground_truth_free_cells
