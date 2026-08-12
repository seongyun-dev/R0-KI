#!/usr/bin/env python3
"""자율 매핑을 저장된 지도 위에서 종료까지 연속 재현하는 오프라인 시뮬레이터.

실물 로봇·ROS·MQTT·시리얼을 전혀 쓰지 않는다. 운영 코드는 읽기만 한다.

기본 플래너는 Nav2 SmacPlannerHybrid 가 **아니라** 같은 비용식을 쓰는 자체 SE2
격자 탐색이다. 그래서 모든 산출물에 APPROXIMATE 가 표시된다. 실제 Nav2 결과가
필요하면 ROS 환경에서 ``--planner-backend nav2`` 를 쓴다.

사용 예::

    python robot/tools/mapping_replay_simulator.py \\
      --map C:/workspace/iot/artifacts/mapping-review-20260812/map-13-v1-cf6a97edfc6c/map.yaml \\
      --profiles v0.2.2,v0.2.5,v0.2.6-candidate \\
      --start-x 0.0 --start-y 0.0 --start-yaw-deg 0 \\
      --max-steps 2000 \\
      --output C:/workspace/iot/artifacts/mapping-simulator/run-001
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    # robot/ 를 경로에 넣어 `tools.mapping_sim` 으로 import 되게 한다.
    sys.path.insert(0, str(_HERE.parent))

from tools.mapping_sim import profiles as profiles_mod  # noqa: E402
from tools.mapping_sim.contracts import (  # noqa: E402
    LidarSpec,
    PlannerFlavor,
    Pose,
    RobotSpec,
)
from tools.mapping_sim.report import write_outputs  # noqa: E402
from tools.mapping_sim.simulator import (  # noqa: E402
    SimSettings,
    StartPoseError,
    run,
)
from tools.mapping_sim.worldmodel import GroundTruth  # noqa: E402


def _git(*args: str) -> str:
    """저장소 상태를 metadata 에 남긴다. 실패해도 실행은 계속한다."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(_HERE.parent.parent),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "(git 조회 실패)"
    return completed.stdout.strip() or "(없음)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mapping_replay_simulator",
        description="자율 매핑을 저장 지도 위에서 종료까지 연속 재현한다",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--map", required=True, help="ROS map.yaml 경로 (정답 지도로 쓴다)"
    )
    parser.add_argument(
        "--profiles",
        default="v0.2.2,v0.2.5",
        help="쉼표로 구분한 프로필. 사용 가능: "
        + ", ".join(sorted(profiles_mod.BUILTIN_PROFILES)),
    )
    parser.add_argument("--start-x", type=float, required=True)
    parser.add_argument("--start-y", type=float, required=True)
    parser.add_argument("--start-yaw-deg", type=float, default=0.0)
    parser.add_argument("--max-steps", type=int, default=2000)
    parser.add_argument("--max-sim-time-sec", type=float, default=3600.0)
    parser.add_argument("--output", required=True, help="산출물 디렉터리")

    sensor = parser.add_argument_group("가상 LiDAR")
    sensor.add_argument("--lidar-range", type=float, default=8.0)
    sensor.add_argument("--lidar-min-range", type=float, default=0.20)
    sensor.add_argument("--lidar-angle-step-deg", type=float, default=1.0)
    sensor.add_argument(
        "--lidar-noise",
        type=float,
        default=0.0,
        help="거리 노이즈 표준편차 [m]. 0 이면 완전 결정론적 (기본)",
    )
    sensor.add_argument("--seed", type=int, default=0)

    behaviour = parser.add_argument_group("동작")
    behaviour.add_argument(
        "--planner-backend",
        choices=("approximate", "nav2"),
        default="approximate",
        help="approximate = 자체 근사 (기본). nav2 = ComputePathToPose 실호출 "
        "(ROS 환경 필요, 없으면 실패한다. 자동 폴백하지 않는다)",
    )
    behaviour.add_argument(
        "--replan-on-map-change",
        action="store_true",
        help="지도가 바뀌면 추종을 끊고 재계획한다. 실제 explore 는 goal_active_ "
        "가드 때문에 그러지 않으므로 기본은 꺼져 있다",
    )
    behaviour.add_argument("--observe-interval-m", type=float, default=0.05)
    behaviour.add_argument("--loop-window", type=int, default=6)
    return parser


def _make_backend(choice: str):
    if choice == "approximate":
        from tools.mapping_sim.planner import default_backend

        return default_backend()
    from tools.mapping_sim.planner import Nav2ActionPlanner

    # 실패하면 그대로 예외를 올린다. 근사 플래너로 조용히 내려가면 결과를
    # 실제 Nav2 결과로 오해하게 되므로 절대 폴백하지 않는다.
    return Nav2ActionPlanner()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    map_yaml = Path(args.map).expanduser()
    if not map_yaml.is_file():
        print(f"지도 YAML 이 없다: {map_yaml}", file=sys.stderr)
        return 2

    try:
        selected = profiles_mod.resolve(args.profiles)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        ground_truth = GroundTruth.from_map_yaml(map_yaml)
    except Exception as exc:  # 지도 오류는 사용자 입력 오류다
        print(f"지도를 읽을 수 없다: {exc}", file=sys.stderr)
        return 2

    robot = RobotSpec()
    lidar = LidarSpec(
        max_range_m=args.lidar_range,
        min_range_m=args.lidar_min_range,
        angle_increment_deg=args.lidar_angle_step_deg,
        range_noise_m=args.lidar_noise,
    )
    settings = SimSettings(
        max_steps=args.max_steps,
        max_sim_time_sec=args.max_sim_time_sec,
        lidar=lidar,
        robot=robot,
        seed=args.seed,
        observe_interval_m=args.observe_interval_m,
        replan_on_map_change=args.replan_on_map_change,
        loop_window=args.loop_window,
    )
    start = Pose(args.start_x, args.start_y, math.radians(args.start_yaw_deg))

    try:
        backend = _make_backend(args.planner_backend)
    except RuntimeError as exc:
        print(f"플래너 backend 를 만들 수 없다: {exc}", file=sys.stderr)
        return 2

    flavor = getattr(backend, "flavor", PlannerFlavor.APPROXIMATE)
    if flavor is PlannerFlavor.APPROXIMATE:
        print(
            "[APPROXIMATE] 이 실행은 자체 근사 플래너를 쓴다. "
            "실제 Nav2/Smac 결과가 아니다.",
            file=sys.stderr,
        )

    results = []
    for profile in selected:
        try:
            result = run(profile, ground_truth, start, settings, backend)
        except StartPoseError as exc:
            print(f"시작 자세를 쓸 수 없다: {exc}", file=sys.stderr)
            if exc.candidates:
                print("\n가능한 FREE 시작점 후보:", file=sys.stderr)
                for cx, cy in exc.candidates:
                    print(
                        f"  --start-x {cx:.3f} --start-y {cy:.3f}", file=sys.stderr
                    )
            else:
                print(
                    "  (이 지도에는 footprint 가 들어갈 FREE 셀이 없다)",
                    file=sys.stderr,
                )
            return 3
        result.map_yaml = str(map_yaml)
        results.append(result)
        print(
            f"{profile.name:>18}  {result.metrics.final_state:<9} "
            f"발견 {result.metrics.discovered_ratio * 100:5.1f}%  "
            f"이동 {result.metrics.total_travel_m:6.2f} m  "
            f"목표 {result.metrics.goals_sent:3d}  "
            f"계획실패 {result.metrics.plan_failures:3d}  "
            f"영구배제 {result.metrics.permanently_excluded:2d}  "
            f"step {result.metrics.steps}"
        )

    output_dir = Path(args.output).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    run_metadata = {
        "생성도구": "robot/tools/mapping_replay_simulator.py",
        "플래너종류": flavor.value,
        "근사여부경고": (
            "이 결과는 자체 근사 플래너입니다. 실제 Nav2/Smac 결과가 아닙니다."
            if flavor is PlannerFlavor.APPROXIMATE
            else "ComputePathToPose 실호출 결과입니다."
        ),
        "지도": str(map_yaml),
        "지도해상도": ground_truth.spec.resolution,
        "지도크기": [ground_truth.spec.width, ground_truth.spec.height],
        "시작자세": {
            "x": start.x,
            "y": start.y,
            "yaw_deg": args.start_yaw_deg,
        },
        "git": {
            "브랜치": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "커밋": _git("rev-parse", "--short=7", "HEAD"),
            "기준태그": "iot-v0.2.5 (af1478c)",
        },
        "로봇실측값": {
            "footprint_m": [robot.length_m, robot.width_m],
            "wheelbase_m": robot.wheelbase_m,
            "min_turning_radius_m": robot.min_turning_radius_m,
            "speed_mps": robot.speed_mps,
            "footprint_padding_m": robot.padding_m,
            "inscribed_radius_m": round(robot.inscribed_radius_m, 4),
            "circumscribed_radius_m": round(robot.circumscribed_radius_m, 4),
            "출처": "CLAUDE.md B-7 (줄자 검증) 및 robot/config/robot.env.example",
        },
        "라이다": {
            "max_range_m": lidar.max_range_m,
            "min_range_m": lidar.min_range_m,
            "angle_increment_deg": lidar.angle_increment_deg,
            "range_noise_m": lidar.range_noise_m,
            "beam_count": lidar.beam_count,
            "결정론적": lidar.range_noise_m == 0.0,
        },
        "프로필": {
            profile.name: {
                "태그": profile.provenance.tag,
                "커밋": profile.provenance.commit,
                "출처파일": list(profile.provenance.sources),
                "비고": list(profile.provenance.notes),
                "설정": {
                    "goal_yaw_rule": profile.goal_yaw_rule.value,
                    "inflation_radius_m": profile.inflation.inflation_radius_m,
                    "cost_scaling_factor": profile.inflation.cost_scaling_factor,
                    "motion_model": profile.planner.motion_model.value,
                    "allow_unknown": profile.planner.allow_unknown,
                    "tolerance_m": profile.planner.tolerance_m,
                    "reverse_penalty": profile.planner.reverse_penalty,
                    "change_penalty": profile.planner.change_penalty,
                    "non_straight_penalty": profile.planner.non_straight_penalty,
                    "cost_penalty": profile.planner.cost_penalty,
                    "min_frontier_size_m": profile.frontier.min_frontier_size_m,
                    "potential_scale": profile.frontier.potential_scale,
                    "gain_scale": profile.frontier.gain_scale,
                    "approach_distance_m": profile.frontier.approach_distance_m,
                    "clearance_aware_approach": (
                        profile.frontier.clearance_aware_approach
                    ),
                    "max_attempts": profile.retry.max_attempts,
                    "retry_delay_sec": profile.retry.retry_delay_sec,
                    "merge_metric": profile.retry.merge_metric.value,
                    "merge_radius_cells": profile.retry.merge_radius_cells,
                    "blacklist_mode": profile.retry.blacklist_mode.value,
                    "planner_period_sec": profile.retry.planner_period_sec,
                    "retarget_while_active": profile.retarget_while_active,
                    "await_cancel_before_new_goal": (
                        profile.await_cancel_before_new_goal
                    ),
                    "retry_with_alternate_approach": (
                        profile.retry_with_alternate_approach
                    ),
                },
            }
            for profile in selected
        },
    }

    # 리포트가 궤적으로 지도를 복원하지 않도록 실제 발견 지도를 넘긴다. 복원본은
    # 성겨서 화면의 지도와 옆에 적힌 discovered_ratio 가 서로를 부정한다.
    run_metadata["discovered_maps"] = {
        result.profile_name: {
            "cells": result.discovered_cells,
            "first_seen_step": result.first_seen_step,
        }
        for result in results
        if result.discovered_cells
    }

    written = write_outputs(
        results=results,
        ground_truth_cells={
            profile.name: ground_truth.flat_states() for profile in selected
        },
        grid_spec=ground_truth.spec,
        output_dir=output_dir,
        run_metadata=run_metadata,
    )
    print("\n산출물:")
    for name, path in written.items():
        print(f"  {name:<14} {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
