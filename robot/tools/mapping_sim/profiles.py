"""릴리스별 매핑 프로필. 값은 **실제 태그에서 읽은 것만** 쓴다.

각 값 옆에 출처를 적었다. 추측한 값은 없다. 두 태그를 직접 비교해 확인한
사실은 다음과 같다 (``git diff iot-v0.2.2..iot-v0.2.5``)::

    robot/config/ros/explore.params.yaml          두 태그 바이트 동일
    robot/config/ros/nav2.params.yaml.template    planner_server 섹션 차이 없음
    robot/src/aiot_robot/ros_config.py            인플레이션 0.25 -> 0.40,
                                                  mapping 페널티 3개가 명시 핀으로
                                                  추가되었으나 **수치는 템플릿
                                                  기본값과 동일**
    robot/patches/...frontier-recovery.patch      목표 yaw 규칙 변경 + frontier_free

따라서 매핑 동작에 영향을 주는 태그 간 차이는 정확히 두 개다:
**목표 yaw 규칙**과 **인플레이션 반경**. 나머지는 동일하다. 프로필을 이 두 축으로
구성한 것은 임의 선택이 아니라 diff 가 그렇게 나왔기 때문이다.
"""

from __future__ import annotations

from .contracts import (
    BlacklistMode,
    FrontierParams,
    GoalYawRule,
    InflationSpec,
    MergeMetric,
    MotionModel,
    PlannerParams,
    Profile,
    ProfileProvenance,
    RetryParams,
)


# explore.params.yaml 은 두 태그에서 동일하므로 공통 팩토리로 둔다.
# 값 출처: robot/config/ros/explore.params.yaml (iot-v0.2.2 == iot-v0.2.5)
_EXPLORE_SOURCE = "robot/config/ros/explore.params.yaml"
_ROSCFG_SOURCE = "robot/src/aiot_robot/ros_config.py"
_TEMPLATE_SOURCE = "robot/config/ros/nav2.params.yaml.template"
_PATCH_SOURCE = "robot/patches/m-explore-ros2-326cf8a-roki-frontier-recovery.patch"


def _shared_frontier(**overrides: object) -> FrontierParams:
    """explore.params.yaml 의 실제 값."""
    base = dict(
        min_frontier_size_m=0.35,     # explore.params.yaml: min_frontier_size
        potential_scale=0.5,          # explore.params.yaml: potential_scale
        gain_scale=3.0,               # explore.params.yaml: gain_scale
        approach_distance_m=0.25,     # explore.params.yaml: frontier_approach_distance
        clearance_aware_approach=False,
        required_clearance_m=None,
    )
    base.update(overrides)
    return FrontierParams(**base)  # type: ignore[arg-type]


def _shared_retry(**overrides: object) -> RetryParams:
    """explore.params.yaml + explore.cpp 패치의 실제 값.

    planner_period_sec 6.666 의 근거: upstream explore.cpp 가 타이머 주기를
    ``(uint16_t)(1000.0 / planner_frequency_)`` 로 만든다. planner_frequency
    0.15 -> 1000/0.15 = 6666.67 -> uint16_t 캐스트로 6666 ms.
    이 값은 2026-08-12 실측 로그로 확인했다 (쿨다운 경고 간격 6.62 s / 6.70 s).
    """
    base = dict(
        max_attempts=2,               # explore.params.yaml: frontier_max_attempts
        retry_delay_sec=15.0,         # explore.params.yaml: frontier_retry_delay
        merge_radius_cells=5,         # explore.cpp 패치: constexpr tolerance = 5
        merge_metric=MergeMetric.CHEBYSHEV,   # fabs(dx)<r && fabs(dy)<r
        blacklist_mode=BlacklistMode.COORDINATE_COOLDOWN,
        planner_period_sec=6.666,     # planner_frequency 0.15 (위 주석 참조)
        progress_timeout_sec=90.0,    # explore.params.yaml: progress_timeout
    )
    base.update(overrides)
    return RetryParams(**base)  # type: ignore[arg-type]


def _mapping_planner(**overrides: object) -> PlannerParams:
    """MappingGridBased 의 실제 파라미터.

    출처: nav2.params.yaml.template 의 planner_server.GridBased (두 태그 동일)
    + ros_config.py MODE_PROFILES["mapping"]["/planner_server"] 의 덮어쓰기.

    v0.2.2 는 change/non_straight/cost 를 MODE_PROFILES 에 두지 않고 템플릿
    기본값을 그대로 썼고, v0.2.5 는 같은 값을 명시적으로 핀했다. 즉 렌더 결과는
    두 태그에서 동일하다 -- 여기서 같은 숫자를 쓰는 것은 그 사실의 반영이다.
    """
    base = dict(
        motion_model=MotionModel.REEDS_SHEPP,  # MODE_PROFILES mapping
        tolerance_m=0.20,                      # template: tolerance
        allow_unknown=True,                    # template: allow_unknown
        angle_quantization_bins=64,            # template: angle_quantization_bins
        max_planning_time_sec=3.5,             # template: max_planning_time
        max_iterations=1_000_000,              # template: max_iterations
        reverse_penalty=2.0,                   # MODE_PROFILES mapping
        change_penalty=0.0,                    # template == MODE_PROFILES(v0.2.5)
        non_straight_penalty=1.2,              # template == MODE_PROFILES(v0.2.5)
        cost_penalty=2.0,                      # template == MODE_PROFILES(v0.2.5)
        retrospective_penalty=0.025,           # template: retrospective_penalty
    )
    base.update(overrides)
    return PlannerParams(**base)  # type: ignore[arg-type]


PROFILE_V022 = Profile(
    name="v0.2.2",
    provenance=ProfileProvenance(
        tag="iot-v0.2.2",
        commit="341b920",
        sources=(_EXPLORE_SOURCE, _ROSCFG_SOURCE, _TEMPLATE_SOURCE, _PATCH_SOURCE),
        notes=(
            "인플레이션 0.25 (ros_config.py: MEASURED_INFLATION_RADIUS_M)",
            "목표 yaw = atan2(approach - robot_pose) (패치 makePlan)",
            "frontier_free 개념 없음",
            "mapping 페널티는 MODE_PROFILES 에 없고 템플릿 기본값을 사용",
        ),
    ),
    frontier=_shared_frontier(),
    planner=_mapping_planner(),
    retry=_shared_retry(),
    inflation=InflationSpec(inflation_radius_m=0.25, cost_scaling_factor=3.0),
    goal_yaw_rule=GoalYawRule.BEARING_FROM_ROBOT,
    single_active_goal=True,
    await_cancel_before_new_goal=False,
    retry_with_alternate_approach=False,
)


PROFILE_V025 = Profile(
    name="v0.2.5",
    provenance=ProfileProvenance(
        tag="iot-v0.2.5",
        commit="af1478c",
        sources=(_EXPLORE_SOURCE, _ROSCFG_SOURCE, _TEMPLATE_SOURCE, _PATCH_SOURCE),
        notes=(
            "인플레이션 0.40 (ros_config.py: NAVIGATION_INFLATION_RADIUS_M)",
            "목표 yaw = atan2(frontier_free - approach) (패치 makePlan)",
            "frontier_free = 프론티어 시드에 맞닿은 FREE 셀",
            "mapping 페널티가 명시 핀이지만 수치는 v0.2.2 렌더 결과와 동일",
            "explore.params.yaml 은 v0.2.2 와 바이트 동일",
        ),
    ),
    frontier=_shared_frontier(),
    planner=_mapping_planner(),
    retry=_shared_retry(),
    inflation=InflationSpec(inflation_radius_m=0.40, cost_scaling_factor=3.0),
    goal_yaw_rule=GoalYawRule.APPROACH_TO_BOUNDARY,
    single_active_goal=True,
    await_cancel_before_new_goal=False,
    retry_with_alternate_approach=False,
)


# v0.2.6 후보는 **아직 태그가 아니다.** 2026-08-12 실측 진단에서 나온 수정안을
# 설정으로 표현한 것이고, 시뮬레이터로 비교하기 위한 가설이다. 실물 검증 전에는
# 릴리스로 취급하지 말 것.
PROFILE_V026_CANDIDATE = Profile(
    name="v0.2.6-candidate",
    provenance=ProfileProvenance(
        tag="(태그 없음 - 후보)",
        commit="(미커밋 - 가설)",
        sources=(
            "2026-08-12 젯슨 실측 (mappingSessionId=9, explore pid=37846)",
            _EXPLORE_SOURCE,
            _PATCH_SOURCE,
        ),
        notes=(
            "v0.2.5 기준에서 세 가지만 바꾼다",
            "1) 접근점을 clearance 로 고른다 (footprint 가 들어갈 수 있는 첫 셀)",
            "2) 사전검사 실패 시 다른 접근점으로 재시도한다",
            "3) 실패 병합을 체비셰프 0.25 m 상자 -> 유클리드 inscribed 0.135 m",
            "4) 지도 개정 기반 soft blacklist (좌표 영구 배제 대신 재평가)",
            "실측 근거: 목표 (1.373,0.137) 은 최근접 점유셀 0.180 m 로 "
            "inscribed 0.135 와 circumscribed 0.229 사이 -- yaw -90 도에서만 충돌. "
            "목표 (1.485,-2.940) 은 0.063 m 로 어떤 자세에서도 충돌.",
        ),
    ),
    frontier=_shared_frontier(
        clearance_aware_approach=True,
        required_clearance_m=None,   # None -> circumscribed 를 쓴다 (자세 무관 안전)
    ),
    planner=_mapping_planner(),
    retry=_shared_retry(
        merge_metric=MergeMetric.EUCLIDEAN,
        merge_radius_cells=3,                       # 0.135 m / 0.05 = 2.7 -> 3
        blacklist_mode=BlacklistMode.MAP_REVISION_SOFT,
    ),
    inflation=InflationSpec(inflation_radius_m=0.40, cost_scaling_factor=3.0),
    goal_yaw_rule=GoalYawRule.APPROACH_TO_BOUNDARY_LONG_BASELINE,
    single_active_goal=True,
    await_cancel_before_new_goal=True,
    retry_with_alternate_approach=True,
)


# 패치 **이전** upstream explore_lite 동작. 태그가 아니라 대조군이다.
#
# 패치가 `same_goal && goal_active_` 를 `goal_active_` 로 바꾼 이유를 주석에
# 이렇게 적어 두었다: "Retargeting on every map update preempts the old
# NavigateToPose goal; Humble cannot distinguish that preemption from a real
# ABORT and would consume the old frontier's retry budget."
# 그 주장이 실제로 얼마나 손해인지 재려면 대조군이 필요하다.
PROFILE_UPSTREAM_RETARGET = Profile(
    name="upstream-retarget",
    provenance=ProfileProvenance(
        tag="(태그 아님 - 대조군)",
        commit="326cf8a (m-explore-ros2 base, 패치 미적용 조건)",
        sources=(_PATCH_SOURCE,),
        notes=(
            "v0.2.5 와 모든 값이 같고 retarget_while_active 만 True",
            "패치가 제거한 upstream 동작: 매 지도 갱신마다 최선 후보로 갈아탄다",
            "취소 완료를 기다리지 않으므로 stale_goal_retained_sec 가 누적된다",
            "이 프로필은 릴리스가 아니다. 패치 주석의 주장을 검증하기 위한 대조군이다",
        ),
    ),
    frontier=_shared_frontier(),
    planner=_mapping_planner(),
    retry=_shared_retry(),
    inflation=InflationSpec(inflation_radius_m=0.40, cost_scaling_factor=3.0),
    goal_yaw_rule=GoalYawRule.APPROACH_TO_BOUNDARY,
    single_active_goal=True,
    retarget_while_active=True,
    await_cancel_before_new_goal=False,
    retry_with_alternate_approach=False,
)


BUILTIN_PROFILES: dict[str, Profile] = {
    PROFILE_V022.name: PROFILE_V022,
    PROFILE_V025.name: PROFILE_V025,
    PROFILE_V026_CANDIDATE.name: PROFILE_V026_CANDIDATE,
    PROFILE_UPSTREAM_RETARGET.name: PROFILE_UPSTREAM_RETARGET,
}


def resolve(names: str) -> list[Profile]:
    """"v0.2.2,v0.2.5" 같은 CLI 문자열을 프로필 목록으로."""
    resolved: list[Profile] = []
    for raw in names.split(","):
        key = raw.strip()
        if not key:
            continue
        if key not in BUILTIN_PROFILES:
            available = ", ".join(sorted(BUILTIN_PROFILES))
            raise KeyError(f"알 수 없는 프로필 {key!r}. 사용 가능: {available}")
        resolved.append(BUILTIN_PROFILES[key])
    if not resolved:
        raise KeyError("프로필을 하나 이상 지정해야 한다")
    return resolved
