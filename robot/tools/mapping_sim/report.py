"""시뮬레이션 결과를 검토 가능한 산출물로 굽는다.

``report.html`` / ``summary.json`` / ``trace.jsonl`` / ``final-map.svg`` 네 개를 쓴다.

이 모듈이 지키는 규칙 세 가지 -- 전부 프로젝트 규약에서 나온 것이고, 편의를 위해
깨뜨리지 않는다.

1. **발견 지도를 정답 지도로 채우지 않는다.** ``ground_truth_cells`` 는 오직
   기본 숨김인 디버그 오버레이에만 쓰인다. 리포트가 정답 지도로 발견 지도를
   메우면 화면은 예뻐지지만 "무엇을 실제로 발견했는가" 라는 질문에 거짓으로
   답하게 되고, 두 지도 분리 불변식이 보고 단계에서 무너진다.

2. **근사를 실측이라 부르지 않는다.** ``RunMetrics.planner_flavor`` 가
   ``NAV2_ACTUAL`` 이 아니면 헤더에 경고 배너를 강제로 띄운다. 배너를 끄는
   옵션은 두지 않았다 -- 끌 수 있으면 결국 꺼진 채로 공유된다.

3. **없는 데이터를 만들지 않는다.** 정답 지도 길이가 격자와 다르거나 발견 지도
   원본이 없으면, 그 사실을 ``summary.json`` 의 ``warnings`` 와 리포트 화면에
   적는다. 조용히 그럴듯한 그림을 그리지 않는다.

발견 지도(DiscoveredMap)를 받는 경로
------------------------------------
``write_outputs`` 의 시그니처는 고정이고 ``SimResult`` / ``StepRecord`` 에는 격자를
담는 필드가 없다 (계약에 필드를 추가하지 않기로 했으므로 그대로 둔다). 그래서
발견 지도는 자유 딕셔너리인 ``run_metadata`` 를 통해 받는다::

    run_metadata["discovered_maps"] = {
        "v0.2.5": {
            "cells": [...],             # 길이 = width*height, CellState 값
            "first_seen_step": [...],   # (선택) 셀별 최초 관측 step, 미관측은 -1
        },
        # 또는 그냥 flat 리스트만: "v0.2.2": [...]
    }

``first_seen_step`` 이 있으면 슬라이더가 진짜 단계별 발견 과정을 재생한다. 없으면
최종 지도를 모든 step 에 그대로 보여주고 그 사실을 화면에 밝힌다.

키가 아예 없으면 **추적 기록만으로 부분 복원**한다: 경로 샘플의 ``cell_state`` (계획
시점의 발견 지도 상태) 와 실제 주행한 자세의 셀(FREE)뿐이다. 정답 지도를 참조하지
않으므로 지도는 성기지만, 성긴 것이 정직하다.

템플릿 규칙
-----------
HTML/CSS/JS 는 f-string 으로 만들지 않는다. CSS 의 ``{`` 가 f-string 을 깨뜨리는
사고가 이 파일에서 가장 잦았다. 템플릿 상수 + ``str.replace`` 만 쓴다.
"""

from __future__ import annotations

import html
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .contracts import (
    CIRCUMSCRIBED_RADIUS_M,
    DRIVE_SPEED_MPS,
    FOOTPRINT_LENGTH_M,
    FOOTPRINT_PADDING_M,
    FOOTPRINT_WIDTH_M,
    INSCRIBED_RADIUS_M,
    MAX_STEER_RAD,
    MIN_TURNING_RADIUS_M,
    WHEELBASE_M,
    CandidateVerdict,
    CellState,
    GridSpec,
    PlannerFlavor,
    Pose,
    RunMetrics,
    SimResult,
    StepRecord,
    TerminationState,
)


# 반환 딕셔너리의 키이자 실제 파일명. 호출자가 outputs["report.html"] 로 집는다.
REPORT_HTML = "report.html"
SUMMARY_JSON = "summary.json"
TRACE_JSONL = "trace.jsonl"
FINAL_MAP_SVG = "final-map.svg"

# run_metadata 에서 발견 지도 원본을 찾는 키 (모듈 docstring 참조).
DISCOVERED_MAP_KEY = "discovered_maps"

SUMMARY_SCHEMA = "roki.mapping_sim.summary/v1"

# HTML 인라인 JSON 은 좌표가 대부분이라 소수점을 자른다. 화면 픽셀보다 훨씬 촘촘한
# 자리수이므로 그림이 달라지지 않는다. trace.jsonl 은 증거 파일이라 자르지 않는다.
_HTML_FLOAT_DIGITS = 5

_APPROXIMATE_WARNING = (
    "이 결과는 자체 근사 플래너입니다. 실제 Nav2/Smac 결과가 아닙니다."
)

_VERDICT_STYLE: dict[str, tuple[str, str]] = {
    CandidateVerdict.SELECTED.value: ("#f5c542", "선택"),
    CandidateVerdict.BLACKLISTED.value: ("#e5484d", "영구 배제"),
    CandidateVerdict.COOLING_DOWN.value: ("#a855f7", "쿨다운 대기"),
    CandidateVerdict.TOO_SMALL.value: ("#8b98a5", "크기 미달"),
    CandidateVerdict.NO_APPROACH_CELL.value: ("#12a594", "접근점 없음"),
    CandidateVerdict.PATH_UNAVAILABLE.value: ("#f76b15", "경로 사전검사 실패"),
    CandidateVerdict.GOAL_IN_COLLISION.value: ("#d6409f", "목표 자세 충돌"),
    CandidateVerdict.NOT_EVALUATED.value: ("#5b6b7f", "미평가"),
}

_STATE_LABELS: dict[str, str] = {
    TerminationState.COMPLETE.value: "완료 (유효 프론티어 없음)",
    TerminationState.WAITING.value: "대기 (재시도 쿨다운)",
    TerminationState.STALLED.value: "교착 (후보 전부 실패·제외)",
    TerminationState.COLLISION.value: "충돌",
    TerminationState.LOOP.value: "루프",
    TerminationState.TIMEOUT.value: "시간 초과",
    TerminationState.FAILED.value: "실패",
}

_FLAVOR_LABELS: dict[str, str] = {
    PlannerFlavor.APPROXIMATE.value: "APPROXIMATE (자체 SE2 격자 탐색)",
    PlannerFlavor.NAV2_ACTUAL.value: "NAV2_ACTUAL (ComputePathToPose 실호출)",
}

# 캔버스와 SVG 가 공유하는 오버레이 색. 라이트/다크 양쪽에서 읽히는 채도를 골랐다.
_LAYER_COLORS: dict[str, str] = {
    "path": "#2f9be8",
    "path_unknown": "#e040fb",
    "path_reverse": "#ffb020",
    "travelled": "#22c55e",
    "start": "#3b82f6",
    "goal": "#f5c542",
    "robot": "#ff6b3d",
    "collision": "#e5484d",
    "cooldown": "#a855f7",
    "ground_truth": "rgba(229,72,77,0.38)",
}

_LAYER_LABELS: dict[str, str] = {
    "path": "계획 경로 (전진)",
    "path_unknown": "unknown 통과 구간",
    "path_reverse": "후진 구간",
    "travelled": "실제 이동 궤적",
    "start": "시작 자세",
    "goal": "선택 목표 + yaw",
    "robot": "로봇 footprint",
    "collision": "충돌 위치",
    "cooldown": "쿨다운·배제 후보 표식",
    "ground_truth": "정답 지도 (디버그 전용)",
}

_METRIC_LABELS: dict[str, str] = {
    "final_state": "종료 상태",
    "discovered_ratio": "발견 비율",
    "ground_truth_free_cells": "정답 자유 셀 수",
    "discovered_free_cells": "발견 자유 셀 수",
    "total_travel_m": "총 이동거리 (m)",
    "net_displacement_m": "순 변위 (m)",
    "goals_sent": "보낸 목표 수",
    "goals_succeeded_without_motion": "이동 없이 성공한 목표 수",
    "plan_successes": "계획 성공",
    "plan_failures": "계획 실패",
    "unknown_traverse_m": "unknown 통과 거리 (m)",
    "min_wall_clearance_m": "최소 벽 여유 (m)",
    "collisions": "충돌 횟수",
    "reverse_distance_m": "후진 거리 (m)",
    "reverse_ratio": "후진 비율",
    "direction_changes": "방향 전환 수",
    "stale_goal_retained_sec": "낡은 목표 유지 시간 (s)",
    "frontier_retries": "프론티어 재시도",
    "permanently_excluded": "영구 배제 후보 수",
    "compute_time_sec": "계산 시간 (s)",
    "steps": "step 수",
    "planner_flavor": "플래너 종류",
}

_PERCENT_METRICS = frozenset({"discovered_ratio", "reverse_ratio"})


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------


def write_outputs(
    results: list[SimResult],
    ground_truth_cells: dict[str, list[int]],
    grid_spec: GridSpec,
    output_dir: Path,
    run_metadata: dict,
) -> dict[str, Path]:
    """report.html / summary.json / trace.jsonl / final-map.svg 를 쓰고 경로를 돌려준다.

    반환 딕셔너리의 키는 파일명 그대로다 (``REPORT_HTML`` 등 모듈 상수와 동일).
    ``ground_truth_cells`` 는 profile_name -> flat CellState 값이고, 평탄화 순서는
    ``GridSpec.index`` 와 같다 (row 0 = 아래쪽, index = row * width + col).
    """

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    cell_count = max(0, grid_spec.width * grid_spec.height)
    warnings: list[str] = []
    prepared = [
        _prepare_profile(
            result, grid_spec, cell_count, ground_truth_cells, run_metadata, warnings
        )
        for result in results
    ]
    if not prepared:
        warnings.append("결과가 비어 있다 (프로필 0개). 지표와 지도는 렌더할 것이 없다.")
    geometry = _robot_geometry()

    summary_path = directory / SUMMARY_JSON
    trace_path = directory / TRACE_JSONL
    svg_path = directory / FINAL_MAP_SVG
    html_path = directory / REPORT_HTML

    _write_text(
        summary_path,
        _build_summary(prepared, grid_spec, run_metadata, generated_at, warnings),
    )
    _write_trace(trace_path, prepared)
    _write_text(
        svg_path, _build_svg(prepared, grid_spec, geometry, generated_at)
    )
    _write_text(
        html_path,
        _build_html(
            prepared, grid_spec, geometry, run_metadata, generated_at, warnings
        ),
    )
    return {
        REPORT_HTML: html_path,
        SUMMARY_JSON: summary_path,
        TRACE_JSONL: trace_path,
        FINAL_MAP_SVG: svg_path,
    }


# ---------------------------------------------------------------------------
# 직렬화
# ---------------------------------------------------------------------------


def _jsonable(value: Any, float_digits: int | None = None) -> Any:
    """dataclass·Enum·Pose 를 JSON 자료형으로. inf/nan 은 None 이 된다.

    inf 를 그대로 두면 파이썬 json 이 ``Infinity`` 를 내놓고, 그건 유효한 JSON 이
    아니라서 브라우저의 ``JSON.parse`` 가 통째로 실패한다. ``RunMetrics``
    ``min_wall_clearance_m`` 의 기본값이 정확히 ``inf`` 이므로 실제로 터진다.
    """

    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Pose):
        return {
            "x": _jsonable(value.x, float_digits),
            "y": _jsonable(value.y, float_digits),
            "yaw": _jsonable(value.yaw, float_digits),
        }
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value if float_digits is None else round(value, float_digits)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            entry.name: _jsonable(getattr(value, entry.name), float_digits)
            for entry in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item, float_digits) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item, float_digits) for item in value]
    return str(value)


def _cell_value(value: Any) -> int:
    """CellState 든 정수든 하나의 정수로. 지도 배열은 이 형태만 다룬다."""

    if isinstance(value, CellState):
        return value.value
    return int(value)


def _rle(cells: Sequence[int]) -> list[list[int]]:
    """[[값, 반복수], ...]. 셀 5만 개를 인라인 JSON 에 넣으려면 이 압축이 필요하다."""

    runs: list[list[int]] = []
    for raw in cells:
        value = _cell_value(raw)
        if runs and runs[-1][0] == value:
            runs[-1][1] += 1
        else:
            runs.append([value, 1])
    return runs


def _write_text(path: Path, text: str) -> None:
    # newline="\n" 고정: 호스트가 Windows 라 기본값이면 CRLF 가 섞여 들어간다.
    with path.open("w", encoding="utf-8", newline="\n") as sink:
        sink.write(text)


# ---------------------------------------------------------------------------
# 프로필별 준비 (지도 해석)
# ---------------------------------------------------------------------------


def _prepare_profile(
    result: SimResult,
    grid: GridSpec,
    cell_count: int,
    ground_truth_cells: Mapping[str, Sequence[int]] | None,
    run_metadata: Mapping[str, Any] | None,
    warnings: list[str],
) -> dict[str, Any]:
    name = result.profile_name
    truth = (ground_truth_cells or {}).get(name)
    ground: list[int] | None = None
    if truth is None:
        warnings.append(f"{name}: 정답 지도가 없어 디버그 오버레이를 비활성화했다")
    elif len(truth) != cell_count:
        warnings.append(
            f"{name}: 정답 지도 길이 {len(truth)} 가 격자 {cell_count} 와 달라 무시했다"
        )
    else:
        ground = [_cell_value(value) for value in truth]

    base, deltas, source = _resolve_discovered(result, grid, cell_count, run_metadata)
    final = list(base) if base is not None else [CellState.UNKNOWN.value] * cell_count
    for delta in deltas:
        for index, value in delta:
            if 0 <= index < cell_count:
                final[index] = value
    return {
        "result": result,
        "name": name,
        "ground": ground,
        "base": base,
        "deltas": deltas,
        "source": source,
        "final": final,
    }


def _resolve_discovered(
    result: SimResult,
    grid: GridSpec,
    cell_count: int,
    run_metadata: Mapping[str, Any] | None,
) -> tuple[list[int] | None, list[list[list[int]]], str]:
    """(기저 지도, step 별 증분, 출처 설명) 을 만든다.

    출처 설명을 반환값에 포함시킨 이유: 복원 지도인지 원본인지 화면에 반드시 적어야
    하고, 그 판단은 여기서만 알 수 있다.
    """

    step_count = len(result.steps)
    provided = (run_metadata or {}).get(DISCOVERED_MAP_KEY)
    payload = provided.get(result.profile_name) if isinstance(provided, Mapping) else None

    cells: Sequence[Any] | None = None
    first_seen: Sequence[Any] | None = None
    if isinstance(payload, Mapping):
        raw_cells = payload.get("cells")
        if isinstance(raw_cells, Sequence) and not isinstance(raw_cells, (str, bytes)):
            cells = raw_cells
        raw_seen = payload.get("first_seen_step")
        if isinstance(raw_seen, Sequence) and not isinstance(raw_seen, (str, bytes)):
            first_seen = raw_seen
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        cells = payload

    if cells is not None and len(cells) == cell_count:
        values = [_cell_value(value) for value in cells]
        if first_seen is not None and len(first_seen) == cell_count and step_count:
            return (
                None,
                _deltas_from_first_seen(values, first_seen, step_count),
                "제공된 발견 지도 (셀별 최초 관측 step 으로 단계 재생)",
            )
        return (
            values,
            [[] for _ in range(step_count)],
            "제공된 최종 발견 지도 (단계별 증분 정보 없음 -- 모든 step 에 같은 지도)",
        )

    if cells is not None:
        return (
            None,
            _deltas_from_trace(result, grid),
            f"발견 지도 길이 {len(cells)} 가 격자 {cell_count} 와 달라 무시하고 "
            "추적 기록으로 부분 복원했다",
        )
    return (
        None,
        _deltas_from_trace(result, grid),
        "추적 기록 기반 부분 복원 (발견 지도 원본 미제공). 경로 샘플의 지도 상태와 "
        "실제 주행 셀만 표시된다",
    )


def _deltas_from_first_seen(
    cells: Sequence[int], first_seen: Sequence[Any], step_count: int
) -> list[list[list[int]]]:
    deltas: list[list[list[int]]] = [[] for _ in range(step_count)]
    for index, raw in enumerate(first_seen):
        if raw is None:
            continue
        try:
            step = int(raw)
        except (TypeError, ValueError):
            continue
        if step < 0:
            continue
        deltas[min(step, step_count - 1)].append([index, cells[index]])
    return deltas


def _deltas_from_trace(result: SimResult, grid: GridSpec) -> list[list[list[int]]]:
    """추적 기록만으로 발견 지도를 복원한다. 정답 지도는 절대 보지 않는다.

    쓸 수 있는 증거는 두 가지뿐이다. (1) 경로 샘플의 ``cell_state`` -- 계획 시점의
    발견 지도 값이므로 그 자체로 발견 지도의 관측이다. (2) 실제 주행한 자세의 셀 --
    로봇이 지나간 칸은 발견 지도에서 FREE 다. 프론티어 클러스터 셀은 UNKNOWN 이므로
    지도를 채우는 데 쓸 수 없고, 별도 오버레이로만 그린다.
    """

    unknown = CellState.UNKNOWN.value
    free = CellState.FREE.value
    snapshot: dict[int, int] = {}
    deltas: list[list[list[int]]] = []
    for record in result.steps:
        pending: dict[int, int] = {}
        if record.path is not None:
            for sample in record.path.samples:
                index = _cell_index(grid, sample.pose.x, sample.pose.y)
                if index is not None:
                    pending[index] = _cell_value(sample.cell_state)
        # 주행은 계획보다 나중이므로 계획 시점 값을 덮는다.
        for pose in record.travelled:
            index = _cell_index(grid, pose.x, pose.y)
            if index is not None:
                pending[index] = free
        delta = [
            [index, value]
            for index, value in sorted(pending.items())
            if snapshot.get(index, unknown) != value
        ]
        for index, value in delta:
            snapshot[index] = value
        deltas.append(delta)
    return deltas


def _cell_index(grid: GridSpec, x: float, y: float) -> int | None:
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    column, row = grid.world_to_cell(x, y)
    if not grid.contains(column, row):
        return None
    return grid.index(column, row)


def _robot_geometry() -> dict[str, float]:
    """footprint 를 그릴 치수. contracts.py 의 실측 상수를 그대로 쓴다.

    ``RobotSpec`` 을 인자로 받지 않는 이유: 호출부(mapping_replay_simulator.py)가
    ``RobotSpec()`` 을 기본값으로 만들고, 그 기본값이 바로 이 상수들이다. 즉 지금은
    같은 숫자다. 나중에 기본값이 아닌 RobotSpec 으로 시뮬레이션하게 되면 그 치수를
    여기로 넘겨야 한다 -- 안 넘기면 리포트가 그리는 footprint 만 조용히 틀려진다.
    """

    return {
        "length_m": FOOTPRINT_LENGTH_M,
        "width_m": FOOTPRINT_WIDTH_M,
        "padding_m": FOOTPRINT_PADDING_M,
    }


def _footprint_corners(
    x: float, y: float, yaw: float, geometry: Mapping[str, float]
) -> list[tuple[float, float]]:
    half_length = geometry["length_m"] / 2.0 + geometry["padding_m"]
    half_width = geometry["width_m"] / 2.0 + geometry["padding_m"]
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    local = (
        (half_length, half_width),
        (half_length, -half_width),
        (-half_length, -half_width),
        (-half_length, half_width),
    )
    return [
        (x + lx * cos_yaw - ly * sin_yaw, y + lx * sin_yaw + ly * cos_yaw)
        for lx, ly in local
    ]


# ---------------------------------------------------------------------------
# summary.json
# ---------------------------------------------------------------------------


def _public_metadata(run_metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """run_metadata 를 JSON 화한다. 발견 지도 원본은 크기 때문에 뺀다."""

    cleaned: dict[str, Any] = {}
    for key, value in (run_metadata or {}).items():
        if key == DISCOVERED_MAP_KEY:
            cleaned[str(key)] = (
                "<생략: 발견 지도 원본은 report.html / final-map.svg 로 렌더된다>"
            )
            continue
        cleaned[str(key)] = _jsonable(value)
    return cleaned


def _measured_constants() -> dict[str, float]:
    """contracts.py 의 실측 상수를 그대로 옮긴다 (여기서 다시 정의하지 않는다)."""

    return {
        "footprint_length_m": FOOTPRINT_LENGTH_M,
        "footprint_width_m": FOOTPRINT_WIDTH_M,
        "wheelbase_m": WHEELBASE_M,
        "max_steer_deg": math.degrees(MAX_STEER_RAD),
        "min_turning_radius_m": MIN_TURNING_RADIUS_M,
        "drive_speed_mps": DRIVE_SPEED_MPS,
        "footprint_padding_m": FOOTPRINT_PADDING_M,
        "inscribed_radius_m": INSCRIBED_RADIUS_M,
        "circumscribed_radius_m": CIRCUMSCRIBED_RADIUS_M,
    }


def _build_summary(
    prepared: list[dict[str, Any]],
    grid: GridSpec,
    run_metadata: Mapping[str, Any] | None,
    generated_at: str,
    warnings: list[str],
) -> str:
    profiles = []
    for entry in prepared:
        result: SimResult = entry["result"]
        profiles.append(
            {
                "profile_name": result.profile_name,
                "map_yaml": result.map_yaml,
                "start_pose": _jsonable(result.start_pose),
                "error": result.error,
                "steps_recorded": len(result.steps),
                "discovered_map_source": entry["source"],
                "ground_truth_available": entry["ground"] is not None,
                "metrics": _jsonable(result.metrics),
            }
        )
    payload = {
        "schema": SUMMARY_SCHEMA,
        "generated_at": generated_at,
        "planner_flavor_notice": (
            _APPROXIMATE_WARNING if _has_approximate(prepared) else ""
        ),
        "grid": _jsonable(grid),
        "measured_constants": _measured_constants(),
        "run_metadata": _public_metadata(run_metadata),
        "warnings": list(warnings),
        "profiles": profiles,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def _has_approximate(prepared: list[dict[str, Any]]) -> bool:
    for entry in prepared:
        metrics: RunMetrics = entry["result"].metrics
        if metrics.planner_flavor != PlannerFlavor.NAV2_ACTUAL.value:
            return True
    return False


# ---------------------------------------------------------------------------
# trace.jsonl
# ---------------------------------------------------------------------------


def _write_trace(path: Path, prepared: list[dict[str, Any]]) -> None:
    """StepRecord 한 개당 한 줄. 프로필 이름을 매 줄에 붙인다.

    한 줄씩 흘려 쓴다: 수천 step 짜리 실행에서 전체를 문자열로 모으면 메모리를
    두 배로 먹고 이 파일은 증거라 잘라낼 수도 없다.
    """

    with path.open("w", encoding="utf-8", newline="\n") as sink:
        for entry in prepared:
            result: SimResult = entry["result"]
            for record in result.steps:
                sink.write(json.dumps(
                    _trace_line(result.profile_name, record),
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ))
                sink.write("\n")


def _trace_line(profile_name: str, record: StepRecord) -> dict[str, Any]:
    line: dict[str, Any] = {"profile": profile_name}
    line.update(_jsonable(record))
    return line


# ---------------------------------------------------------------------------
# final-map.svg
# ---------------------------------------------------------------------------


_SVG_STYLE = r"""
.bg{fill:#f4f6f8}
.unk{fill:#c9d0d6}
.free{fill:#ffffff}
.occ{fill:#101418}
.frame{fill:none;stroke:#98a4b0;stroke-width:1}
.txt{fill:#12161a;font:13px system-ui,-apple-system,'Malgun Gothic',sans-serif}
.sub{fill:#5b6b7f;font:11px system-ui,-apple-system,'Malgun Gothic',sans-serif}
.hdr{fill:#12161a;font:600 16px system-ui,-apple-system,'Malgun Gothic',sans-serif}
.warn{fill:#8a5200;font:600 13px system-ui,-apple-system,'Malgun Gothic',sans-serif}
@media (prefers-color-scheme:dark){
.bg{fill:#0d1116}
.unk{fill:#4c565f}
.free{fill:#dde4ea}
.occ{fill:#04060a}
.frame{stroke:#3a444e}
.txt{fill:#e6edf3}
.sub{fill:#9aa7b4}
.hdr{fill:#e6edf3}
.warn{fill:#ffd479}
}
"""


def _n(value: float) -> str:
    """SVG 좌표 문자열. 소수 둘째 자리면 렌더에 충분하고 파일이 훨씬 작아진다."""

    if not math.isfinite(value):
        return "0"
    text = f"{value:.2f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _build_svg(
    prepared: list[dict[str, Any]],
    grid: GridSpec,
    geometry: Mapping[str, float],
    generated_at: str,
) -> str:
    margin = 16.0
    header = 58.0
    caption = 74.0
    gap = 24.0
    span = max(1, max(grid.width, grid.height))
    cell = max(1.0, min(6.0, 560.0 / span))
    panel_w = grid.width * cell
    panel_h = grid.height * cell
    columns = max(1, len(prepared))
    total_w = margin * 2 + columns * panel_w + (columns - 1) * gap
    total_h = margin * 2 + header + panel_h + caption

    parts: list[str] = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="'
        + _n(total_w)
        + '" height="'
        + _n(total_h)
        + '" viewBox="0 0 '
        + _n(total_w)
        + " "
        + _n(total_h)
        + '">'
    )
    parts.append("<style>" + _SVG_STYLE + "</style>")
    parts.append(
        '<rect class="bg" x="0" y="0" width="'
        + _n(total_w)
        + '" height="'
        + _n(total_h)
        + '"/>'
    )
    parts.append(
        '<text class="hdr" x="'
        + _n(margin)
        + '" y="'
        + _n(margin + 16)
        + '">최종 발견 지도와 실제 이동 궤적</text>'
    )
    parts.append(
        '<text class="sub" x="'
        + _n(margin)
        + '" y="'
        + _n(margin + 34)
        + '">'
        + _xml(
            f"생성 {generated_at} / 격자 {grid.width}x{grid.height} @ "
            f"{grid.resolution:.3f} m / 정답 지도는 포함하지 않는다"
        )
        + "</text>"
    )
    if _has_approximate(prepared):
        parts.append(
            '<text class="warn" x="'
            + _n(margin)
            + '" y="'
            + _n(margin + 52)
            + '">'
            + _xml(_APPROXIMATE_WARNING)
            + "</text>"
        )

    if not prepared:
        parts.append(
            '<text class="txt" x="'
            + _n(margin)
            + '" y="'
            + _n(margin + header + 24)
            + '">렌더할 결과가 없다</text>'
        )
        parts.append("</svg>")
        return "\n".join(parts) + "\n"

    for column, entry in enumerate(prepared):
        origin_x = margin + column * (panel_w + gap)
        origin_y = margin + header
        parts.append(
            '<g transform="translate('
            + _n(origin_x)
            + ","
            + _n(origin_y)
            + ')">'
        )
        parts.extend(_svg_panel(entry, grid, geometry, cell, panel_w, panel_h))
        parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _svg_panel(
    entry: dict[str, Any],
    grid: GridSpec,
    geometry: Mapping[str, float],
    cell: float,
    panel_w: float,
    panel_h: float,
) -> list[str]:
    result: SimResult = entry["result"]
    metrics: RunMetrics = result.metrics
    cells: list[int] = entry["final"]
    occupied = CellState.OCCUPIED.value
    free = CellState.FREE.value

    def to_x(x: float) -> float:
        return (x - grid.origin_x) / grid.resolution * cell

    def to_y(y: float) -> float:
        return panel_h - (y - grid.origin_y) / grid.resolution * cell

    parts: list[str] = []
    # UNKNOWN 을 배경 한 장으로 깔고 나머지만 그린다. 미탐사가 대부분이라
    # 여기서 rect 수가 한 자릿수 배로 줄어든다.
    parts.append(
        '<rect class="unk" x="0" y="0" width="'
        + _n(panel_w)
        + '" height="'
        + _n(panel_h)
        + '"/>'
    )
    for row, column, run, value in _row_runs(cells, grid, {CellState.UNKNOWN.value}):
        style = "free" if value == free else ("occ" if value == occupied else "unk")
        parts.append(
            '<rect class="'
            + style
            + '" x="'
            + _n(column * cell)
            + '" y="'
            + _n(panel_h - (row + 1) * cell)
            + '" width="'
            + _n(run * cell)
            + '" height="'
            + _n(cell)
            + '"/>'
        )
    parts.append(
        '<rect class="frame" x="0.5" y="0.5" width="'
        + _n(max(1.0, panel_w - 1.0))
        + '" height="'
        + _n(max(1.0, panel_h - 1.0))
        + '"/>'
    )

    points: list[str] = [
        _n(to_x(result.start_pose.x)) + "," + _n(to_y(result.start_pose.y))
    ]
    last_pose = result.start_pose
    for record in result.steps:
        for pose in record.travelled:
            points.append(_n(to_x(pose.x)) + "," + _n(to_y(pose.y)))
            last_pose = pose
    if len(points) > 1:
        parts.append(
            '<polyline fill="none" stroke="'
            + _LAYER_COLORS["travelled"]
            + '" stroke-width="2" stroke-linejoin="round" points="'
            + " ".join(points)
            + '"/>'
        )
    parts.append(
        '<circle cx="'
        + _n(to_x(result.start_pose.x))
        + '" cy="'
        + _n(to_y(result.start_pose.y))
        + '" r="4" fill="'
        + _LAYER_COLORS["start"]
        + '"/>'
    )
    corners = _footprint_corners(
        last_pose.x, last_pose.y, last_pose.yaw, geometry
    )
    parts.append(
        '<polygon fill="none" stroke="'
        + _LAYER_COLORS["robot"]
        + '" stroke-width="2" points="'
        + " ".join(_n(to_x(cx)) + "," + _n(to_y(cy)) for cx, cy in corners)
        + '"/>'
    )
    for record in result.steps:
        if record.state is not TerminationState.COLLISION:
            continue
        cx, cy = to_x(record.pose.x), to_y(record.pose.y)
        parts.append(
            '<path stroke="'
            + _LAYER_COLORS["collision"]
            + '" stroke-width="2.5" d="M'
            + _n(cx - 6)
            + " "
            + _n(cy - 6)
            + "L"
            + _n(cx + 6)
            + " "
            + _n(cy + 6)
            + "M"
            + _n(cx + 6)
            + " "
            + _n(cy - 6)
            + "L"
            + _n(cx - 6)
            + " "
            + _n(cy + 6)
            + '"/>'
        )

    lines = [
        f"{result.profile_name} -- {_state_label(metrics.final_state)}",
        f"발견 {metrics.discovered_ratio * 100:.1f}% / 이동 {metrics.total_travel_m:.2f} m"
        f" / 충돌 {metrics.collisions} / step {metrics.steps}",
        _FLAVOR_LABELS.get(metrics.planner_flavor, metrics.planner_flavor),
        "발견 지도 출처: " + str(entry["source"]),
    ]
    baseline = panel_h + 20.0
    parts.append(
        '<text class="txt" x="0" y="' + _n(baseline) + '">' + _xml(lines[0]) + "</text>"
    )
    for index, text in enumerate(lines[1:]):
        parts.append(
            '<text class="sub" x="0" y="'
            + _n(baseline + 16.0 * (index + 1))
            + '">'
            + _xml(text)
            + "</text>"
        )
    return parts


def _row_runs(
    cells: Sequence[int], grid: GridSpec, skip: set[int]
) -> list[tuple[int, int, int, int]]:
    """행 단위 런렝스 (row, col_start, run, value). 셀별 rect 를 피하는 유일한 이유."""

    runs: list[tuple[int, int, int, int]] = []
    for row in range(grid.height):
        base = row * grid.width
        column = 0
        while column < grid.width:
            value = cells[base + column]
            run = 1
            while column + run < grid.width and cells[base + column + run] == value:
                run += 1
            if value not in skip:
                runs.append((row, column, run, value))
            column += run
    return runs


def _xml(text: str) -> str:
    return html.escape(str(text), quote=True)


def _state_label(value: str) -> str:
    return _STATE_LABELS.get(value, value) + f" [{value}]"


# ---------------------------------------------------------------------------
# report.html
# ---------------------------------------------------------------------------


_STYLE_CSS = r"""
:root{
  color-scheme: light dark;
  --bg:#f5f7f9; --panel:#ffffff; --panel-2:#eef2f6; --fg:#11161b; --muted:#5b6b7f;
  --border:#d5dde5; --accent:#0b62d6; --accent-fg:#ffffff;
  --warn-bg:#fff3d4; --warn-fg:#7a4b00; --warn-border:#e0a72b;
  --bad:#b4232a;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#0c1015; --panel:#141a21; --panel-2:#1b232c; --fg:#e6edf3; --muted:#9aa7b4;
    --border:#28323c; --accent:#5aa2ff; --accent-fg:#08111c;
    --warn-bg:#3a2a06; --warn-fg:#ffd479; --warn-border:#8a6a12;
    --bad:#ff8b8b;
  }
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--fg);
  font:14px/1.55 system-ui,-apple-system,'Malgun Gothic','Apple SD Gothic Neo',sans-serif;
}
.wrap{max-width:1500px; margin:0 auto; padding:20px 18px 64px}
h1{font-size:21px; margin:0 0 4px}
h2{font-size:16px; margin:28px 0 10px}
.muted{color:var(--muted)}
.sub{color:var(--muted); margin:0 0 14px; font-size:13px}
.banner{
  border:1px solid var(--warn-border); background:var(--warn-bg); color:var(--warn-fg);
  border-radius:8px; padding:12px 14px; margin:12px 0 18px; font-weight:600;
}
.banner .detail{font-weight:400; font-size:12.5px; margin-top:4px}
.card{
  background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:14px;
}
.tabs{display:flex; flex-wrap:wrap; gap:8px; margin:0 0 12px}
.tab{
  cursor:pointer; border:1px solid var(--border); background:var(--panel);
  color:var(--fg); border-radius:999px; padding:6px 14px; font:inherit; font-size:13px;
}
.tab[aria-selected="true"]{background:var(--accent); color:var(--accent-fg); border-color:transparent}
.stage{display:flex; flex-wrap:wrap; gap:14px; align-items:flex-start}
.stage .view-col{flex:1 1 620px; min-width:320px}
.stage .side-col{flex:1 1 360px; min-width:300px}
canvas{
  width:100%; height:auto; display:block; border:1px solid var(--border);
  border-radius:8px; background:var(--panel-2);
}
.controls{display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:10px}
button{
  cursor:pointer; font:inherit; font-size:13px; color:var(--fg); background:var(--panel);
  border:1px solid var(--border); border-radius:6px; padding:6px 12px;
}
button:hover{border-color:var(--accent)}
select{font:inherit; font-size:13px; padding:5px 6px; border-radius:6px;
  border:1px solid var(--border); background:var(--panel); color:var(--fg)}
input[type=range]{flex:1 1 220px; min-width:160px; accent-color:var(--accent)}
.step-label{font-variant-numeric:tabular-nums; font-size:13px; color:var(--muted); min-width:120px}
.toggles{display:flex; flex-wrap:wrap; gap:12px; margin-top:10px; font-size:13px}
.toggles label{display:inline-flex; gap:6px; align-items:center; cursor:pointer}
.debug{color:var(--bad); font-weight:600}
.kv{display:grid; grid-template-columns:auto 1fr; gap:4px 12px; font-size:13px; margin:0}
.kv dt{color:var(--muted)}
.kv dd{margin:0; word-break:break-all}
.table-wrap{overflow-x:auto; -webkit-overflow-scrolling:touch;
  border:1px solid var(--border); border-radius:10px; background:var(--panel)}
table{border-collapse:collapse; width:100%; font-size:13px}
th,td{border-bottom:1px solid var(--border); padding:7px 10px; text-align:left;
  white-space:nowrap; vertical-align:top}
thead th{background:var(--panel-2); position:sticky; top:0}
tbody tr:last-child th,tbody tr:last-child td{border-bottom:none}
td.num{text-align:right; font-variant-numeric:tabular-nums}
.legend{display:flex; flex-wrap:wrap; gap:10px 18px; list-style:none; padding:0; margin:0;
  font-size:13px}
.legend li{display:flex; align-items:center; gap:7px}
.sw{width:14px; height:14px; border-radius:3px; border:1px solid var(--border); flex:0 0 auto}
pre{background:var(--panel); border:1px solid var(--border); border-radius:10px;
  padding:12px; overflow-x:auto; font-size:12.5px; margin:0}
.warnlist{margin:0; padding-left:18px; font-size:13px; color:var(--bad)}
.footnote{color:var(--muted); font-size:12.5px; margin-top:10px}
"""


_SCRIPT_JS = r"""
(function () {
  "use strict";

  var node = document.getElementById("sim-data");
  var canvas = document.getElementById("view");
  if (!node || !canvas || !canvas.getContext) { return; }
  var DATA = JSON.parse(node.textContent);
  var ctx = canvas.getContext("2d");
  var G = DATA.grid;
  var SIZE = Math.max(0, G.width * G.height);
  var CS = DATA.cell_states;
  var LAYER = DATA.colors;
  var ROBOT = DATA.robot;
  var VERDICTS = DATA.verdicts;
  var STATE_LABELS = DATA.states;

  var PALETTES = {
    light: {
      bg: "#e9edf1", unknown: "#c9d0d6", free: "#ffffff", occupied: "#101418",
      hud: "#101418", hudBg: "rgba(255,255,255,0.82)"
    },
    dark: {
      bg: "#0e1216", unknown: "#4c565f", free: "#dde4ea", occupied: "#04060a",
      hud: "#e8eef4", hudBg: "rgba(6,10,14,0.78)"
    }
  };

  var slider = document.getElementById("slider");
  var stepLabel = document.getElementById("step-label");
  var statusBox = document.getElementById("status");
  var candBox = document.getElementById("candidates");
  var playBtn = document.getElementById("play");
  var speedSel = document.getElementById("speed");
  var toggles = {
    truth: document.getElementById("t-truth"),
    frontier: document.getElementById("t-frontier"),
    path: document.getElementById("t-path"),
    travel: document.getElementById("t-travel"),
    robot: document.getElementById("t-robot")
  };

  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  function palette() { return (media && media.matches) ? PALETTES.dark : PALETTES.light; }

  var scale = Math.min(960 / Math.max(1, G.width), 720 / Math.max(1, G.height));
  canvas.width = Math.max(1, Math.round(G.width * scale));
  canvas.height = Math.max(1, Math.round(G.height * scale));

  function px(x) { return (x - G.origin_x) / G.resolution * scale; }
  function py(y) { return canvas.height - (y - G.origin_y) / G.resolution * scale; }

  function decodeRle(rle) {
    var arr = new Int16Array(SIZE);
    if (SIZE) { arr.fill(CS.unknown); }
    if (!rle || !rle.length) { return arr; }
    var k = 0, i, j, value, count;
    for (i = 0; i < rle.length && k < SIZE; i++) {
      value = rle[i][0];
      count = rle[i][1];
      for (j = 0; j < count && k < SIZE; j++) { arr[k] = value; k++; }
    }
    return arr;
  }

  var views = {};
  var order = [];
  for (var pi = 0; pi < DATA.profiles.length; pi++) {
    var prof = DATA.profiles[pi];
    views[prof.name] = {
      profile: prof, base: null, gt: null, map: null, applied: -1, step: 0
    };
    order.push(prof.name);
  }
  var active = order.length ? order[0] : null;
  var timer = null;

  function current() { return active ? views[active] : null; }

  function ensureBase(st) {
    if (st.base !== null) { return; }
    st.base = decodeRle(st.profile.discovered_base_rle);
    var gt = st.profile.ground_truth_rle;
    st.gt = (gt && gt.length) ? decodeRle(gt) : null;
  }

  function stepCount(st) { return st.profile.steps.length; }

  function seek(target) {
    var st = current();
    if (!st) { return; }
    ensureBase(st);
    var last = stepCount(st) - 1;
    if (target > last) { target = last; }
    if (target < 0) { target = 0; }
    if (st.map === null || target < st.applied) {
      st.map = st.base.slice();
      st.applied = -1;
    }
    while (st.applied < target && st.applied < last) {
      st.applied += 1;
      var delta = st.profile.steps[st.applied].map_delta;
      if (delta) {
        for (var i = 0; i < delta.length; i++) { st.map[delta[i][0]] = delta[i][1]; }
      }
    }
    st.step = target;
    syncControls(st);
    render();
  }

  function syncControls(st) {
    var count = stepCount(st);
    slider.min = 0;
    slider.max = Math.max(0, count - 1);
    slider.disabled = count <= 1;
    slider.value = st.step;
    stepLabel.textContent = count
      ? ("step " + (st.step + 1) + " / " + count)
      : "step 기록 없음";
  }

  function esc(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function num(value, digits) {
    if (value === null || value === undefined || typeof value !== "number") { return "-"; }
    return value.toFixed(digits);
  }

  function record(st) {
    return stepCount(st) ? st.profile.steps[st.step] : null;
  }

  function cellRect(column, row, run) {
    var x0 = Math.floor(column * scale);
    var x1 = Math.ceil((column + run) * scale);
    var y0 = canvas.height - Math.ceil((row + 1) * scale);
    var y1 = canvas.height - Math.floor(row * scale);
    return [x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0)];
  }

  function drawCells(arr, pal, truthMode) {
    if (!arr) { return; }
    for (var row = 0; row < G.height; row++) {
      var base = row * G.width;
      var column = 0;
      while (column < G.width) {
        var value = arr[base + column];
        var run = 1;
        while (column + run < G.width && arr[base + column + run] === value) { run++; }
        var paint = null;
        if (truthMode) {
          if (value === CS.occupied) { paint = LAYER.ground_truth; }
        } else if (value === CS.occupied) {
          paint = pal.occupied;
        } else if (value === CS.free) {
          paint = pal.free;
        } else {
          paint = pal.unknown;
        }
        if (paint) {
          var r = cellRect(column, row, run);
          ctx.fillStyle = paint;
          ctx.fillRect(r[0], r[1], r[2], r[3]);
        }
        column += run;
      }
    }
  }

  function drawClusters(rec) {
    var list = rec.candidates || [];
    for (var i = 0; i < list.length; i++) {
      var cand = list[i];
      var style = VERDICTS[cand.verdict] || { color: "#888888", label: cand.verdict };
      var selected = cand.verdict === "selected";
      ctx.globalAlpha = selected ? 1.0 : 0.68;
      ctx.fillStyle = style.color;
      var cells = cand.cluster_cells || [];
      for (var j = 0; j < cells.length; j++) {
        var r = cellRect(cells[j][0], cells[j][1], 1);
        ctx.fillRect(r[0], r[1], r[2], r[3]);
      }
      ctx.globalAlpha = 1.0;
      if (selected && cells.length) {
        var sx = 0, sy = 0;
        for (j = 0; j < cells.length; j++) { sx += cells[j][0]; sy += cells[j][1]; }
        var cx = (sx / cells.length + 0.5) * scale;
        var cy = canvas.height - (sy / cells.length + 0.5) * scale;
        ctx.strokeStyle = style.color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(cx, cy, Math.max(9, scale * 3), 0, Math.PI * 2);
        ctx.stroke();
      }
    }
  }

  function drawRetryMarkers(rec) {
    var list = rec.candidates || [];
    for (var i = 0; i < list.length; i++) {
      var cand = list[i];
      if (cand.verdict !== "cooling_down" && cand.verdict !== "blacklisted") { continue; }
      var spot = cand.approach;
      var mx, my;
      if (spot) {
        mx = px(spot[0]);
        my = py(spot[1]);
      } else if (cand.cluster_cells && cand.cluster_cells.length) {
        mx = (cand.cluster_cells[0][0] + 0.5) * scale;
        my = canvas.height - (cand.cluster_cells[0][1] + 0.5) * scale;
      } else {
        continue;
      }
      ctx.strokeStyle = cand.verdict === "cooling_down" ? LAYER.cooldown : LAYER.collision;
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.arc(mx, my, 9, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  function drawPath(rec) {
    var path = rec.path;
    if (!path || !path.samples || path.samples.length < 2) { return; }
    for (var i = 1; i < path.samples.length; i++) {
      var a = path.samples[i - 1], b = path.samples[i];
      var unknown = (a.cell_state === CS.unknown) || (b.cell_state === CS.unknown);
      ctx.beginPath();
      ctx.moveTo(px(a.pose.x), py(a.pose.y));
      ctx.lineTo(px(b.pose.x), py(b.pose.y));
      ctx.lineWidth = unknown ? 4.5 : 2.5;
      ctx.strokeStyle = unknown ? LAYER.path_unknown : (b.reverse ? LAYER.path_reverse : LAYER.path);
      ctx.setLineDash(b.reverse ? [7, 4] : []);
      ctx.stroke();
    }
    ctx.setLineDash([]);
  }

  function drawTravelled(st) {
    var started = false;
    ctx.beginPath();
    var start = st.profile.start_pose;
    if (start) { ctx.moveTo(px(start.x), py(start.y)); started = true; }
    for (var i = 0; i <= st.step && i < stepCount(st); i++) {
      var poses = st.profile.steps[i].travelled || [];
      for (var j = 0; j < poses.length; j++) {
        var X = px(poses[j].x), Y = py(poses[j].y);
        if (!started) { ctx.moveTo(X, Y); started = true; } else { ctx.lineTo(X, Y); }
      }
    }
    if (started) {
      ctx.strokeStyle = LAYER.travelled;
      ctx.lineWidth = 3;
      ctx.lineJoin = "round";
      ctx.stroke();
    }
    if (start) {
      ctx.fillStyle = LAYER.start;
      ctx.beginPath();
      ctx.arc(px(start.x), py(start.y), 5, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function drawCollisions(st) {
    for (var i = 0; i <= st.step && i < stepCount(st); i++) {
      var rec = st.profile.steps[i];
      if (rec.state !== "COLLISION") { continue; }
      var cx = px(rec.pose.x), cy = py(rec.pose.y);
      ctx.strokeStyle = LAYER.collision;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(cx - 8, cy - 8); ctx.lineTo(cx + 8, cy + 8);
      ctx.moveTo(cx + 8, cy - 8); ctx.lineTo(cx - 8, cy + 8);
      ctx.stroke();
    }
  }

  function arrow(x0, y0, x1, y1, color, width) {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
    var ang = Math.atan2(y1 - y0, x1 - x0);
    var head = Math.max(7, width * 3.2);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x1 - head * Math.cos(ang - 0.45), y1 - head * Math.sin(ang - 0.45));
    ctx.lineTo(x1 - head * Math.cos(ang + 0.45), y1 - head * Math.sin(ang + 0.45));
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
  }

  function selectedCandidate(rec) {
    var list = rec.candidates || [];
    for (var i = 0; i < list.length; i++) {
      if (rec.selected_id && list[i].candidate_id === rec.selected_id) { return list[i]; }
    }
    for (i = 0; i < list.length; i++) {
      if (list[i].verdict === "selected") { return list[i]; }
    }
    return null;
  }

  function drawGoal(rec) {
    var cand = selectedCandidate(rec);
    if (!cand || !cand.approach) { return; }
    var gx = px(cand.approach[0]), gy = py(cand.approach[1]);
    ctx.strokeStyle = LAYER.goal;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(gx, gy, 7, 0, Math.PI * 2);
    ctx.stroke();
    if (typeof cand.goal_yaw === "number") {
      var reach = 0.35 / G.resolution * scale;
      arrow(gx, gy,
        gx + reach * Math.cos(cand.goal_yaw),
        gy - reach * Math.sin(cand.goal_yaw),
        LAYER.goal, 2.5);
    }
  }

  function drawRobot(pose) {
    var hl = ROBOT.length_m / 2 + ROBOT.padding_m;
    var hw = ROBOT.width_m / 2 + ROBOT.padding_m;
    var c = Math.cos(pose.yaw), s = Math.sin(pose.yaw);
    var local = [[hl, hw], [hl, -hw], [-hl, -hw], [-hl, hw]];
    ctx.beginPath();
    for (var i = 0; i < local.length; i++) {
      var X = px(pose.x + local[i][0] * c - local[i][1] * s);
      var Y = py(pose.y + local[i][0] * s + local[i][1] * c);
      if (i === 0) { ctx.moveTo(X, Y); } else { ctx.lineTo(X, Y); }
    }
    ctx.closePath();
    ctx.strokeStyle = LAYER.robot;
    ctx.lineWidth = 2.5;
    ctx.stroke();
    var nose = 0.22 / G.resolution * scale;
    arrow(px(pose.x), py(pose.y),
      px(pose.x) + nose * Math.cos(pose.yaw),
      py(pose.y) - nose * Math.sin(pose.yaw),
      LAYER.robot, 2);
  }

  function drawHud(st, rec, pal) {
    var lines = [];
    lines.push(st.profile.name + " | " + (stepCount(st)
      ? ("step " + (st.step + 1) + " / " + stepCount(st)) : "step 없음"));
    if (rec) {
      lines.push("coverage " + num((rec.discovered_ratio || 0) * 100, 1) + "% | known "
        + (rec.known_cells || 0) + " 셀 | t=" + num(rec.sim_time_sec, 1) + " s");
      lines.push("상태 " + (rec.state ? (STATE_LABELS[rec.state] || rec.state) : "진행 중"));
    }
    if (toggles.truth && toggles.truth.checked) { lines.push("정답 지도 오버레이 ON (디버그)"); }
    ctx.font = "13px system-ui,-apple-system,'Malgun Gothic',sans-serif";
    var width = 0;
    for (var i = 0; i < lines.length; i++) {
      width = Math.max(width, ctx.measureText(lines[i]).width);
    }
    ctx.fillStyle = pal.hudBg;
    ctx.fillRect(8, 8, width + 18, lines.length * 18 + 12);
    ctx.fillStyle = pal.hud;
    for (i = 0; i < lines.length; i++) { ctx.fillText(lines[i], 17, 27 + i * 18); }
  }

  function render() {
    var st = current();
    if (!st) { return; }
    ensureBase(st);
    if (st.map === null) { seek(st.step); return; }
    var pal = palette();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1.0;
    ctx.fillStyle = pal.bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    drawCells(st.map, pal, false);
    if (toggles.truth && toggles.truth.checked && st.gt) { drawCells(st.gt, pal, true); }
    var rec = record(st);
    if (toggles.travel && toggles.travel.checked) { drawTravelled(st); }
    if (rec) {
      if (toggles.frontier && toggles.frontier.checked) { drawClusters(rec); drawRetryMarkers(rec); }
      if (toggles.path && toggles.path.checked) { drawPath(rec); }
      drawGoal(rec);
      if (toggles.robot && toggles.robot.checked) { drawRobot(rec.pose); }
    }
    drawCollisions(st);
    drawHud(st, rec, pal);
    updateSide(st, rec);
  }

  function updateSide(st, rec) {
    var rows = [];
    rows.push(["프로필", esc(st.profile.name)]);
    rows.push(["지도", esc(st.profile.map_yaml)]);
    rows.push(["플래너", esc(st.profile.flavor_label)]);
    rows.push(["발견 지도 출처", esc(st.profile.discovered_source)]);
    rows.push(["정답 지도", st.gt ? "있음 (디버그 토글)" : "없음"]);
    var summary = st.profile.metrics;
    if (summary) {
      rows.push(["최종 결과", esc(STATE_LABELS[summary.final_state] || summary.final_state)
        + " / 발견 " + num((summary.discovered_ratio || 0) * 100, 1) + "% / 이동 "
        + num(summary.total_travel_m, 2) + " m / 충돌 " + summary.collisions]);
    }
    if (st.profile.error) { rows.push(["오류", esc(st.profile.error)]); }
    if (rec) {
      rows.push(["상태", esc(rec.state ? (STATE_LABELS[rec.state] || rec.state) : "진행 중")]);
      rows.push(["coverage", num((rec.discovered_ratio || 0) * 100, 2) + " %"]);
      rows.push(["known 셀", String(rec.known_cells || 0)]);
      rows.push(["sim 시간", num(rec.sim_time_sec, 2) + " s"]);
      rows.push(["map revision", String(rec.map_revision)]);
      rows.push(["로봇 자세", num(rec.pose.x, 3) + ", " + num(rec.pose.y, 3) + " / "
        + num(rec.pose.yaw * 180 / Math.PI, 1) + " deg"]);
      rows.push(["선택 후보", esc(rec.selected_id || "없음")]);
      if (rec.path) {
        rows.push(["경로", num(rec.path.length_m, 2) + " m / 후진 "
          + num(rec.path.reverse_length_m, 2) + " m / 전환 " + rec.path.direction_changes
          + " / unknown " + rec.path.unknown_cells + " 셀"]);
      }
      if (rec.note) { rows.push(["비고", esc(rec.note)]); }
      var events = rec.goal_events || [];
      if (events.length) {
        var text = [];
        for (var e = 0; e < events.length; e++) {
          text.push(num(events[e][0], 2) + "s " + esc(events[e][1]));
        }
        rows.push(["목표 이벤트", text.join("<br>")]);
      }
    }
    var parts = ["<dl class='kv'>"];
    for (var i = 0; i < rows.length; i++) {
      parts.push("<dt>" + rows[i][0] + "</dt><dd>" + rows[i][1] + "</dd>");
    }
    parts.push("</dl>");
    statusBox.innerHTML = parts.join("");

    var body = [];
    var list = rec ? (rec.candidates || []) : [];
    for (i = 0; i < list.length; i++) {
      var cand = list[i];
      var style = VERDICTS[cand.verdict] || { color: "#888888", label: cand.verdict };
      body.push("<tr>"
        + "<td><span class='sw' style='background:" + style.color + "'></span> "
        + esc(cand.candidate_id) + "</td>"
        + "<td>" + esc(style.label) + "</td>"
        + "<td class='num'>" + num(cand.size_m, 2) + "</td>"
        + "<td class='num'>" + num(cand.min_distance_m, 2) + "</td>"
        + "<td class='num'>" + num(cand.cost, 3) + "</td>"
        + "<td class='num'>" + (cand.approach
            ? (num(cand.approach[0], 2) + ", " + num(cand.approach[1], 2)) : "-") + "</td>"
        + "<td class='num'>" + (typeof cand.goal_yaw === "number"
            ? num(cand.goal_yaw * 180 / Math.PI, 1) : "-") + "</td>"
        + "<td class='num'>" + num(cand.approach_clearance_m, 3) + "</td>"
        + "<td>" + esc(cand.reject_detail) + "</td>"
        + "</tr>");
    }
    if (!body.length) { body.push("<tr><td colspan='9'>이 step 의 후보 기록이 없다</td></tr>"); }
    candBox.innerHTML = body.join("");
  }

  function stop() {
    if (timer !== null) { window.clearInterval(timer); timer = null; }
    playBtn.textContent = "재생";
    playBtn.setAttribute("aria-pressed", "false");
  }

  function play() {
    var st = current();
    if (!st || stepCount(st) <= 1) { return; }
    stop();
    var period = parseInt(speedSel.value, 10);
    if (!period || period < 16) { period = 200; }
    playBtn.textContent = "일시정지";
    playBtn.setAttribute("aria-pressed", "true");
    timer = window.setInterval(function () {
      var view = current();
      if (!view) { stop(); return; }
      if (view.step + 1 >= stepCount(view)) { stop(); return; }
      seek(view.step + 1);
    }, period);
  }

  playBtn.addEventListener("click", function () {
    if (timer === null) { play(); } else { stop(); }
  });
  document.getElementById("prev").addEventListener("click", function () {
    stop();
    var st = current();
    if (st) { seek(st.step - 1); }
  });
  document.getElementById("next").addEventListener("click", function () {
    stop();
    var st = current();
    if (st) { seek(st.step + 1); }
  });
  document.getElementById("first").addEventListener("click", function () {
    stop();
    seek(0);
  });
  document.getElementById("last").addEventListener("click", function () {
    stop();
    var st = current();
    if (st) { seek(stepCount(st) - 1); }
  });
  slider.addEventListener("input", function () {
    stop();
    seek(parseInt(slider.value, 10) || 0);
  });
  speedSel.addEventListener("change", function () {
    if (timer !== null) { play(); }
  });
  Object.keys(toggles).forEach(function (key) {
    if (toggles[key]) { toggles[key].addEventListener("change", render); }
  });
  var tabs = document.querySelectorAll(".tab");
  Array.prototype.forEach.call(tabs, function (tab) {
    tab.addEventListener("click", function () {
      var name = tab.getAttribute("data-profile");
      if (!name || !views[name]) { return; }
      stop();
      active = name;
      Array.prototype.forEach.call(tabs, function (other) {
        other.setAttribute("aria-selected", other === tab ? "true" : "false");
      });
      seek(views[name].step);
    });
  });
  document.addEventListener("keydown", function (event) {
    var st = current();
    if (!st) { return; }
    // 슬라이더·체크박스·버튼에 포커스가 있을 때는 가로채지 않는다. 그러지 않으면
    // 슬라이더 화살표가 두 칸씩 움직이고 스페이스로 체크박스를 켤 수 없다.
    var tag = event.target && event.target.tagName ? event.target.tagName : "";
    if (tag === "INPUT" || tag === "SELECT" || tag === "BUTTON" || tag === "TEXTAREA") { return; }
    if (event.key === "ArrowLeft") { stop(); seek(st.step - 1); event.preventDefault(); }
    else if (event.key === "ArrowRight") { stop(); seek(st.step + 1); event.preventDefault(); }
    else if (event.key === " ") {
      if (timer === null) { play(); } else { stop(); }
      event.preventDefault();
    }
  });
  if (media) {
    if (media.addEventListener) { media.addEventListener("change", render); }
    else if (media.addListener) { media.addListener(render); }
  }

  if (active) { seek(0); }
})();
"""


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>매핑 리플레이 리포트</title>
<style>__STYLE__</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>매핑 리플레이 시뮬레이터 리포트</h1>
  <p class="sub">__SUBTITLE__</p>
  __BANNER__
  __WARNINGS__
</header>

<section aria-label="프로필 선택">
  <div class="tabs" role="tablist">__TABS__</div>
</section>

<section class="stage">
  <div class="view-col card">
    <canvas id="view" width="900" height="700" role="img"
      aria-label="발견 지도와 로봇 상태 리플레이"></canvas>
    <div class="controls">
      <button id="first" type="button">처음</button>
      <button id="prev" type="button">이전</button>
      <button id="play" type="button" aria-pressed="false">재생</button>
      <button id="next" type="button">다음</button>
      <button id="last" type="button">마지막</button>
      <input id="slider" type="range" min="0" max="0" value="0" step="1"
        aria-label="step 슬라이더">
      <span class="step-label" id="step-label">step -</span>
      <select id="speed" aria-label="재생 속도">
        <option value="400">0.5x</option>
        <option value="200" selected>1x</option>
        <option value="100">2x</option>
        <option value="50">4x</option>
      </select>
    </div>
    <div class="toggles">
      <label><input type="checkbox" id="t-frontier" checked> 프론티어 후보</label>
      <label><input type="checkbox" id="t-path" checked> 계획 경로</label>
      <label><input type="checkbox" id="t-travel" checked> 이동 궤적</label>
      <label><input type="checkbox" id="t-robot" checked> footprint</label>
      <label><input type="checkbox" id="t-truth">
        <span class="debug">정답 지도 (디버그)</span></label>
    </div>
    <p class="footnote">방향키로 step 이동, 스페이스로 재생·정지.
      정답 지도는 기본 숨김이며 디버그 토글로만 보인다 -- 알고리즘은 이 지도를 보지 않는다.</p>
  </div>
  <div class="side-col">
    <div class="card" id="status">-</div>
    <h2>이 step 의 프론티어 후보</h2>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>후보</th><th>판정</th><th>크기 m</th><th>최소거리 m</th><th>비용</th>
          <th>접근점</th><th>goal yaw °</th><th>여유 m</th><th>사유</th>
        </tr></thead>
        <tbody id="candidates"></tbody>
      </table>
    </div>
  </div>
</section>

<section>
  <h2>범례</h2>
  <div class="card">__LEGEND__</div>
</section>

<section>
  <h2>비교 지표</h2>
  <div class="table-wrap">__METRICS_TABLE__</div>
</section>

<section>
  <h2>실측 상수</h2>
  <div class="table-wrap">__CONSTANTS_TABLE__</div>
</section>

<section>
  <h2>실행 정보 (run_metadata)</h2>
  <pre>__META_JSON__</pre>
</section>
</div>
<script type="application/json" id="sim-data">__DATA_JSON__</script>
<script>__SCRIPT__</script>
</body>
</html>
"""


def _build_html(
    prepared: list[dict[str, Any]],
    grid: GridSpec,
    geometry: Mapping[str, float],
    run_metadata: Mapping[str, Any] | None,
    generated_at: str,
    warnings: list[str],
) -> str:
    names = ", ".join(entry["name"] for entry in prepared) or "없음"
    subtitle = (
        f"생성 {generated_at} · 프로필 {names} · 격자 {grid.width}x{grid.height} @ "
        f"{grid.resolution:.3f} m · 원점 ({grid.origin_x:.3f}, {grid.origin_y:.3f})"
    )
    data_json = json.dumps(
        _html_payload(prepared, grid, geometry, generated_at),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    # </script> 가 데이터 안에 있으면 스크립트 요소가 조기 종료된다. JSON 에서 '<' 는
    # 문자열 안에만 나올 수 있고 '\/' 는 유효한 JSON 이스케이프이므로 안전하다.
    data_json = data_json.replace("</", "<\\/")

    document = _HTML_TEMPLATE
    document = document.replace("__STYLE__", _STYLE_CSS)
    document = document.replace("__SCRIPT__", _SCRIPT_JS)
    document = document.replace("__SUBTITLE__", html.escape(subtitle))
    document = document.replace("__BANNER__", _banner_html(prepared))
    document = document.replace("__WARNINGS__", _warnings_html(warnings))
    document = document.replace("__TABS__", _tabs_html(prepared))
    document = document.replace("__LEGEND__", _legend_html())
    document = document.replace("__METRICS_TABLE__", _metrics_table_html(prepared))
    document = document.replace("__CONSTANTS_TABLE__", _constants_table_html())
    document = document.replace(
        "__META_JSON__",
        html.escape(
            json.dumps(
                _public_metadata(run_metadata),
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
        ),
    )
    # 데이터는 항상 마지막에 넣는다. 먼저 넣으면 데이터에 우연히 들어 있는
    # __TOKEN__ 문자열이 이후 replace 에 잡혀 JSON 이 깨진다.
    return document.replace("__DATA_JSON__", data_json)


def _html_payload(
    prepared: list[dict[str, Any]],
    grid: GridSpec,
    geometry: Mapping[str, float],
    generated_at: str,
) -> dict[str, Any]:
    profiles = []
    for entry in prepared:
        result: SimResult = entry["result"]
        steps = []
        for index, record in enumerate(result.steps):
            payload = _jsonable(record, _HTML_FLOAT_DIGITS)
            # map_delta 는 StepRecord 필드가 아니라 렌더용 부가 정보다. trace.jsonl
            # 에는 넣지 않는다 (그쪽은 계약 그대로여야 한다).
            payload["map_delta"] = (
                entry["deltas"][index] if index < len(entry["deltas"]) else []
            )
            steps.append(payload)
        profiles.append(
            {
                "name": result.profile_name,
                "map_yaml": result.map_yaml,
                "start_pose": _jsonable(result.start_pose, _HTML_FLOAT_DIGITS),
                "error": result.error,
                "flavor_label": _FLAVOR_LABELS.get(
                    result.metrics.planner_flavor, result.metrics.planner_flavor
                ),
                "discovered_source": entry["source"],
                "metrics": _jsonable(result.metrics, _HTML_FLOAT_DIGITS),
                "ground_truth_rle": _rle(entry["ground"]) if entry["ground"] else [],
                "discovered_base_rle": _rle(entry["base"]) if entry["base"] else [],
                "steps": steps,
            }
        )
    return {
        "generated_at": generated_at,
        "grid": {
            "width": grid.width,
            "height": grid.height,
            "resolution": grid.resolution,
            "origin_x": grid.origin_x,
            "origin_y": grid.origin_y,
        },
        "cell_states": {
            "unknown": CellState.UNKNOWN.value,
            "free": CellState.FREE.value,
            "occupied": CellState.OCCUPIED.value,
        },
        "robot": dict(geometry),
        "colors": dict(_LAYER_COLORS),
        "verdicts": {
            member.value: {
                "color": _VERDICT_STYLE.get(member.value, ("#888888", ""))[0],
                "label": _VERDICT_STYLE.get(member.value, ("", member.value))[1]
                or member.value,
            }
            for member in CandidateVerdict
        },
        "states": {
            member.value: _STATE_LABELS.get(member.value, member.value)
            for member in TerminationState
        },
        "profiles": profiles,
    }


def _banner_html(prepared: list[dict[str, Any]]) -> str:
    if not _has_approximate(prepared):
        return ""
    approximate = [
        entry["name"]
        for entry in prepared
        if entry["result"].metrics.planner_flavor != PlannerFlavor.NAV2_ACTUAL.value
    ]
    detail = (
        "해당 프로필: "
        + html.escape(", ".join(approximate))
        + " — 경로·비용·소요시간은 같은 비용식을 쓰는 자체 SE2 격자 탐색의 결과이며, "
        "Nav2 SmacPlannerHybrid 를 호출한 값이 아니다."
    )
    return (
        '<div class="banner" role="alert">'
        + html.escape(_APPROXIMATE_WARNING)
        + '<div class="detail">'
        + detail
        + "</div></div>"
    )


def _warnings_html(warnings: list[str]) -> str:
    if not warnings:
        return ""
    items = "".join("<li>" + html.escape(text) + "</li>" for text in warnings)
    return '<ul class="warnlist">' + items + "</ul>"


def _tabs_html(prepared: list[dict[str, Any]]) -> str:
    if not prepared:
        return '<span class="muted">표시할 프로필이 없다</span>'
    buttons = []
    for index, entry in enumerate(prepared):
        name = html.escape(entry["name"])
        buttons.append(
            '<button class="tab" type="button" role="tab" data-profile="'
            + name
            + '" aria-selected="'
            + ("true" if index == 0 else "false")
            + '">'
            + name
            + "</button>"
        )
    return "".join(buttons)


def _legend_html() -> str:
    items = []
    for value, (color, label) in _VERDICT_STYLE.items():
        items.append(
            "<li><span class=\"sw\" style=\"background:"
            + color
            + '"></span>'
            + html.escape(label)
            + ' <span class="muted">('
            + html.escape(value)
            + ")</span></li>"
        )
    for key, color in _LAYER_COLORS.items():
        items.append(
            "<li><span class=\"sw\" style=\"background:"
            + color
            + '"></span>'
            + html.escape(_LAYER_LABELS.get(key, key))
            + "</li>"
        )
    return '<ul class="legend">' + "".join(items) + "</ul>"


def _format_metric(name: str, value: Any) -> str:
    if value is None:
        return "측정 없음"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, float):
        text = f"{value:.3f}"
        if name in _PERCENT_METRICS:
            text += f" ({value * 100.0:.1f}%)"
        return text
    if name == "final_state":
        return _state_label(str(value))
    if name == "planner_flavor":
        return _FLAVOR_LABELS.get(str(value), str(value))
    return str(value)


def _metrics_table_html(prepared: list[dict[str, Any]]) -> str:
    if not prepared:
        return "<table><tbody><tr><td>결과 없음</td></tr></tbody></table>"
    header = ["<tr><th>지표</th>"]
    for entry in prepared:
        header.append("<th>" + html.escape(entry["name"]) + "</th>")
    header.append("</tr>")

    rows: list[str] = []
    for label, getter in (
        ("지도 YAML", lambda item: item["result"].map_yaml),
        (
            "시작 자세",
            lambda item: (
                f"{item['result'].start_pose.x:.3f}, {item['result'].start_pose.y:.3f} / "
                f"{math.degrees(item['result'].start_pose.yaw):.1f}°"
            ),
        ),
        ("발견 지도 출처", lambda item: item["source"]),
        ("오류", lambda item: item["result"].error or "없음"),
    ):
        cells = "".join(
            "<td>" + html.escape(str(getter(entry))) + "</td>" for entry in prepared
        )
        rows.append("<tr><th>" + html.escape(label) + "</th>" + cells + "</tr>")

    # fields(RunMetrics) 를 순회한다: 8절 지표가 계약에 추가되면 표에 자동으로 따라온다.
    for entry_field in fields(RunMetrics):
        label = _METRIC_LABELS.get(entry_field.name, entry_field.name)
        values: list[str] = []
        for item in prepared:
            raw = getattr(item["result"].metrics, entry_field.name)
            values.append(
                '<td class="num">'
                + html.escape(_format_metric(entry_field.name, _jsonable(raw)))
                + "</td>"
            )
        rows.append(
            "<tr><th>"
            + html.escape(label)
            + ' <span class="muted">'
            + html.escape(entry_field.name)
            + "</span></th>"
            + "".join(values)
            + "</tr>"
        )
    return (
        "<table><thead>"
        + "".join(header)
        + "</thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _constants_table_html() -> str:
    labels = {
        "footprint_length_m": "차체 길이 (m)",
        "footprint_width_m": "차체 폭 (m)",
        "wheelbase_m": "축간거리 (m)",
        "max_steer_deg": "최대 조향각 (°)",
        "min_turning_radius_m": "최소 회전반경 (m)",
        "drive_speed_mps": "주행 속도 (m/s)",
        "footprint_padding_m": "footprint padding (m)",
        "inscribed_radius_m": "inscribed 반경 (m)",
        "circumscribed_radius_m": "circumscribed 반경 (m)",
    }
    rows = []
    for key, value in _measured_constants().items():
        rows.append(
            "<tr><th>"
            + html.escape(labels.get(key, key))
            + '</th><td class="num">'
            + f"{value:.4f}"
            + "</td></tr>"
        )
    return (
        "<table><thead><tr><th>항목</th><th>값</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        + "<!-- 출처: robot/tools/mapping_sim/contracts.py 의 실측 상수 -->"
    )
