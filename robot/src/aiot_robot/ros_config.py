"""Render field-calibrated Nav2 configuration without guessing measurements."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path, PurePosixPath
from string import Template
from typing import Mapping


FIELD_VARIABLES = (
    "ROKI_WHEELBASE_M",
    "ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG",
    "ROKI_INITIAL_POSE_X_M",
    "ROKI_INITIAL_POSE_Y_M",
    "ROKI_INITIAL_POSE_YAW_RAD",
)
DEFAULT_NAV2_XY_GOAL_TOLERANCE_M = 0.20

# 실측에서 정한 값이지 반지름에서 유도한 값이 아니다.
#
# 예전에는 ROKI_ROBOT_RADIUS_M(0.23) + 0.15 = 0.38 로 계산했다. 그런데 그
# 0.23 원형 근사가 바로 순찰이 벽 0.23 m 안에서 자기 셀을 치명으로 표시하던
# 원인이었고, 그래서 사각 footprint 로 교체했다. 계산의 전제가 사라졌는데
# 계산만 남아 있었다 -- 렌더된 0.38 은 곧바로 0.25 로 덮어써져 한 번도 쓰인
# 적이 없다. 유도를 지우고 실측값을 그대로 둔다.
MEASURED_INFLATION_RADIUS_M = 0.25


def missing_field_variables(environment: Mapping[str, str]) -> list[str]:
    return [name for name in FIELD_VARIABLES if not environment.get(name, "").strip()]


def build_nav2_values(environment: Mapping[str, str]) -> dict[str, str]:
    missing = missing_field_variables(environment)
    if missing:
        raise ValueError("missing field measurements: " + ", ".join(missing))

    wheelbase = _positive_float(environment, "ROKI_WHEELBASE_M")
    steering_angle = _positive_float(
        environment, "ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG"
    )
    if steering_angle >= 60:
        raise ValueError("ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG must be below 60")
    initial_pose_x = _finite_float(environment, "ROKI_INITIAL_POSE_X_M")
    initial_pose_y = _finite_float(environment, "ROKI_INITIAL_POSE_Y_M")
    initial_pose_yaw = _finite_float(
        environment, "ROKI_INITIAL_POSE_YAW_RAD"
    )
    if not -math.pi <= initial_pose_yaw <= math.pi:
        raise ValueError("ROKI_INITIAL_POSE_YAW_RAD must be within -pi..pi")
    desired_speed = _positive_float(
        environment, "ROKI_NAV2_DESIRED_LINEAR_SPEED_MPS", default="0.20"
    )
    maximum_speed = _positive_float(
        environment, "ROKI_MAXIMUM_LINEAR_SPEED_MPS", default="0.40"
    )
    if desired_speed > maximum_speed:
        raise ValueError(
            "ROKI_NAV2_DESIRED_LINEAR_SPEED_MPS must not exceed "
            "ROKI_MAXIMUM_LINEAR_SPEED_MPS"
        )
    xy_goal_tolerance = nav2_xy_goal_tolerance(environment)
    minimum_turning_radius = wheelbase / math.tan(math.radians(steering_angle))
    if not math.isfinite(minimum_turning_radius) or minimum_turning_radius <= 0:
        raise ValueError("calculated minimum turning radius is invalid")

    bt_xml_raw = environment.get(
        "ROKI_NAV2_BT_XML",
        "/opt/aiot/iot/current/robot/config/ros/nav2_fixed_path.xml",
    )
    through_poses_bt_xml_raw = environment.get(
        "ROKI_NAV2_THROUGH_POSES_BT_XML",
        "/opt/aiot/iot/current/robot/config/ros/"
        "nav2_fixed_path_through_poses.xml",
    )
    bt_paths = {
        "NAV2_BT_XML": ("ROKI_NAV2_BT_XML", bt_xml_raw),
        "NAV2_THROUGH_POSES_BT_XML": (
            "ROKI_NAV2_THROUGH_POSES_BT_XML",
            through_poses_bt_xml_raw,
        ),
    }
    rendered_bt_paths: dict[str, str] = {}
    for output_name, (environment_name, raw_path) in bt_paths.items():
        native_path = Path(raw_path)
        posix_path = PurePosixPath(raw_path)
        if not native_path.is_absolute() and not posix_path.is_absolute():
            raise ValueError(f"{environment_name} must be an absolute path")
        rendered_bt_paths[output_name] = (
            posix_path.as_posix()
            if posix_path.is_absolute()
            else native_path.as_posix()
        )
    return {
        "INFLATION_RADIUS_M": _number(MEASURED_INFLATION_RADIUS_M),
        "MINIMUM_TURNING_RADIUS_M": _number(minimum_turning_radius),
        "ANALYTIC_EXPANSION_MAX_LENGTH_M": _number(
            max(3.0, minimum_turning_radius * 5.0)
        ),
        "DESIRED_LINEAR_SPEED_MPS": _number(desired_speed),
        "MAXIMUM_LINEAR_SPEED_MPS": _number(maximum_speed),
        "XY_GOAL_TOLERANCE_M": _number(xy_goal_tolerance),
        "INITIAL_POSE_X_M": _number(initial_pose_x),
        "INITIAL_POSE_Y_M": _number(initial_pose_y),
        "INITIAL_POSE_YAW_RAD": _number(initial_pose_yaw),
        **rendered_bt_paths,
    }


def nav2_xy_goal_tolerance(environment: Mapping[str, str]) -> float:
    """Return the one tolerance shared by Nav2 and route preflight."""

    value = _positive_float(
        environment,
        "ROKI_NAV2_XY_GOAL_TOLERANCE_M",
        default=str(DEFAULT_NAV2_XY_GOAL_TOLERANCE_M),
    )
    if not 0.05 <= value <= 1.0:
        raise ValueError(
            "ROKI_NAV2_XY_GOAL_TOLERANCE_M must be within 0.05..1.0"
        )
    return value


# 운행마다 실제로 달라야 하는 파라미터. 나머지는 전부 공통이다.
#
# 예전에는 매핑용과 순찰용 설정 파일을 따로 렌더하고 모드를 바꿀 때 aiot-ros 를
# 재시작해 갈아 끼웠다. 두 모드가 서로 다른 노드 집합을 쓰던 시절의 구조다.
# 이제는 slam_toolbox 하나가 두 역할을 다 하므로 노드 집합이 같고, 코스트맵
# 모양도 같다(둘 다 slam_toolbox 의 /map 을 본다). 남은 차이가 이 넷뿐이라
# 파일을 두 벌 둘 이유가 없어졌다.
#
# 이 값들은 기동 시 렌더된 파일에 인스턴스별로 들어간다. 실행 중에 바꾸지 않는다.
#
# 2026-08-08 실측: /planner_server 에 SetParameters 를 하면 SmacPlannerHybrid 가
# 휴리스틱 테이블을 동기 재생성하며 노드를 23~29초 블록한다. lifecycle manager 의
# bond heartbeat 가 4초라 그 사이 Nav2 스택 전체가 내려가고, explore 는 비활성
# Nav2 에 목표를 보내지 않으므로 매핑이 한 발도 못 움직인다.
#
# 그래서 전환은 파라미터 변경이 아니라 인스턴스 선택이다 -- BT 가 goal 마다
# planner_id / goal_checker_id 로 고른다. 이 표는 이제 "무엇을 주입할까"가 아니라
# "렌더된 값이 맞는가"를 검증하는 기준이다.
MODE_PROFILES: dict[str, dict[str, dict[str, object]]] = {
    # 2026-08-08: 키를 실제 플러그인 인스턴스로 옮긴다.
    #
    # 예전에는 두 운행이 같은 GridBased 인스턴스 하나를 놓고 값을 주고받았고,
    # 그래서 전환이 SetParameters 였다. 지금은 planner_plugins 가
    # [GridBased, MappingGridBased, PatrolGridBased] 로 셋이고 BT 가 goal 마다
    # 골라 쓴다. 값은 기동 시 인스턴스별로 이미 올라와 있다(실측:
    # MappingGridBased=REEDS_SHEPP/1.3/False, PatrolGridBased=DUBIN/2.1/True).
    #
    # GridBased 는 더 이상 아무도 부르지 않는다. 거기를 가리키던 이 표가
    # 검증도 주입도 엉뚱한 인스턴스를 보게 만들고 있었다.
    "mapping": {
        "/planner_server": {
            # 탐사는 아직 지도에 없는 공간을 헤쳐야 하는 유일한 운행이다.
            # Dubin 경로는 전진으로만 휘므로 회전반경 0.34 m 로는 0.3~0.4 m
            # 옆 벽을 비켜 갈 전진 호가 없다. Reeds-Shepp 이 후진 구간을 준다.
            "MappingGridBased.motion_model_for_search": "REEDS_SHEPP",
            # 순찰용 2.1 은 탐사에서 과하다. 프론티어가 가깝고 축에서 크게
            # 벗어나 있을 때(실측 0.93 m, 121도) 유일한 해가 후진으로
            # 시작하는데, 2.1 에서는 탐색이 벽으로 쓸리는 전진 호만 골라
            # 결국 계획이 없었다. 1.0 보다는 높여 전진을 여전히 선호한다.
            "MappingGridBased.reverse_penalty": 1.3,
            # 재계획 사이에 장애물 확장을 재사용하는 최적화다. SLAM 이 지도를
            # 키우는 동안은 그 전제가 매초 깨지므로, 낡은 휴리스틱으로
            # 도달 가능한 목표를 포기한다.
            "MappingGridBased.cache_obstacle_heuristic": False,
        },
        "/controller_server": {
            # explore_lite 는 모든 프론티어 목표에 단위 쿼터니언을 찍는다
            # (explore.cpp: goal.pose.pose.orientation.w = 1) -- "0 rad 를 보고
            # 도착하라". 차동 로봇은 제자리에서 돌면 되지만 이 섀시는 Dubin
            # 경로를 비틀어야 하고, 그 곡률이 선속을 0 으로 조이면서 각속만
            # 남겨 Ackermann 어댑터가 거부해야 하는 제자리 회전을 만든다.
            # 탐사에서 도착 방위는 의미가 없으므로 풀어준다.
            "mapping_goal_checker.yaw_goal_tolerance": 3.15,
        },
    },
    "patrol": {
        "/planner_server": {
            # 순찰은 운전자가 그린 경로를 따라 이미 주행 가능한 공간을 간다.
            # 여기서 후진하면 보내진 웨이포인트에서 멀어진다.
            "PatrolGridBased.motion_model_for_search": "DUBIN",
            "PatrolGridBased.reverse_penalty": 2.1,
            # 지도가 고정되므로 확장 재사용이 성립한다.
            "PatrolGridBased.cache_obstacle_heuristic": True,
        },
        "/controller_server": {
            # 순찰은 도착 방위가 의미를 갖는다. 다음 구간의 시작 자세다.
            "patrol_goal_checker.yaw_goal_tolerance": 0.35,
        },
    },
}


def apply_slam_shape(rendered: str, environment: Mapping[str, str]) -> str:
    """두 운행이 공유하는 형태로 다듬는다.

    코스트맵과 섀시 물리는 모드에 따라 달라질 이유가 없다. 두 모드 모두
    slam_toolbox 가 발행하는 ``/map`` 을 보고, 회전반경과 PWM 하한은 하드웨어
    사실이다. 운행마다 달라야 하는 넷은 ``MODE_PROFILES`` 에 있다.
    """

    import yaml

    config = yaml.safe_load(rendered)
    # Nav2 설정이 아니면 다듬을 것이 없다. 토큰 치환만 확인하는 축소 템플릿이
    # 그런 경우다. 진짜 템플릿이 이 분기로 새면 아래 코스트맵/프로필 테스트가
    # 즉시 잡는다.
    if not isinstance(config, dict) or "global_costmap" not in config:
        return rendered

    global_costmap = config["global_costmap"]["global_costmap"]["ros__parameters"]
    # SLAM publishes /map continuously; follow it instead of a one-shot load.
    #
    # Static plus inflation only, which is what upstream Nav2 uses alongside SLAM.
    # A live obstacle_layer here was tried and removed: /map already encodes these
    # same scans with proper probabilistic ray-tracing, and on a non-rolling costmap
    # that grows with the map, a mark is only cleared when something re-observes it
    # inside raytrace_max_range. Everything the robot drove past kept its marks, so
    # exploration progressively walled itself in.
    global_costmap["plugins"] = ["static_layer", "inflation_layer"]
    global_costmap["static_layer"] = {
        "plugin": "nav2_costmap_2d::StaticLayer",
        "map_subscribe_transient_local": True,
        "subscribe_to_updates": True,
    }
    global_costmap.pop("obstacle_layer", None)
    # Unknown space must stay distinguishable so the explorer can still see where
    # the frontiers are. The planner is deliberately left free to route through it
    # (the template's allow_unknown stays true): during exploration the map is a
    # thin band of observed free space, and a car-like Dubin path needs roughly
    # twice the 0.34 m turning radius of clearance to curve at all. Forbidding
    # unknown cells makes every candidate path leave known space and fail, which
    # is what "GridBased: failed to create plan" was. Clearance is enforced where
    # it can actually be measured -- the local costmap and the LiDAR interlock.
    global_costmap["track_unknown_space"] = True
    global_costmap["rolling_window"] = False
    for key in ("width", "height"):
        global_costmap.pop(key, None)

    # 이 건물의 복도는 약 1.1 m 다. 스커트가 양쪽에서 0.38 m 씩 들어오면
    # 가운데 약 0.3 m 만 남는데, 그건 실측 회전반경 0.341 m 보다 좁다.
    # 축에서 벗어난 목표로 향하는 호가 들어갈 자리가 없어져 계획이 거부된다.
    #
    # 치명성은 이 값과 무관하다. Nav2 는 footprint 의 내접원(사각 차체
    # 0.35x0.25 에서 0.125 m)을 치명 반경으로 쓰고, inflation 은 그 바깥의
    # 비용 기울기일 뿐이다. 라이다 인터락도 그대로 살아 있다.
    #
    # ⚠️ 이 값은 매핑 디버깅에서 도출했고 순찰로는 아직 검증하지 않았다.
    # 회전반경과 복도 폭은 두 운행이 공유하는 물리 사실이라 같은 값이 맞다고
    # 보지만, 근거는 매핑 쪽에만 있다. 순찰 첫 완주 때 확인할 것.
    #
    # 값 자체는 템플릿이 MEASURED_INFLATION_RADIUS_M 로 이미 받는다. 여기서
    # 다시 쓰지 않는다 -- 같은 값을 두 곳에서 정하면 언젠가 어긋난다.

    # 두 운행의 값을 각자의 인스턴스에 함께 넣는다.
    #
    # 예전에는 매핑 값만 넣었다. 스택이 매핑 모드로 뜨고 순찰 값은 전환 시
    # 주입한다는 전제였기 때문이다. 그 주입이 Nav2 를 죽인다는 것이 실측으로
    # 확인돼(위 주석) 전환이 인스턴스 선택으로 바뀌었으므로, 이제는 둘 다
    # 기동 시점에 자리를 잡고 있어야 한다.
    #
    # 생애주기 관리자가 bond 끊김으로 스택을 복구하며 파일을 다시 읽어도
    # 두 프로필이 그대로 살아난다 -- 예전에는 그때 순찰 값이 사라졌다.
    for mode_profile in MODE_PROFILES.values():
        for node, overrides in mode_profile.items():
            section = (
                config["planner_server"]["ros__parameters"]
                if node == "/planner_server"
                else config["controller_server"]["ros__parameters"]
            )
            for dotted, value in overrides.items():
                head, _, tail = dotted.partition(".")
                section[head][tail] = value

    # The template forbids negative linear velocity, which is right for a DUBIN
    # route that must never retreat from the waypoint it was sent to. It silently
    # defeated the whole reverse setup. /cmd_vel is published by the
    # velocity smoother, not the controller, so a reverse command from the controller
    # arrived as linear.x clamped to 0 with angular.z intact -- which the Ackermann
    # adapter must refuse as an in-place rotation. Every IN_PLACE_ROTATION_REJECTED
    # was a reverse being flattened here.
    smoother = config["velocity_smoother"]["ros__parameters"]
    maximum_reverse = -float(smoother["max_velocity"][0])
    smoother["min_velocity"] = [maximum_reverse, 0.0, smoother["min_velocity"][2]]
    # A REEDS_SHEPP path alternates forward and reverse, and every reversal
    # walks linear.x through zero while the steering command is still live.
    # The Ackermann adapter must refuse that pair as an in-place rotation, so
    # the gate closed and the ramp restarted roughly every two seconds -- the
    # chassis oscillated in place instead of driving (measured 2026-08-07:
    # gate open +45, -45, +45 ... with IN_PLACE_ROTATION_REJECTED between
    # each). Collapsing near-zero linear to exactly zero removes the pair:
    # the adapter reads a clean STOP, the reversal completes, and the next
    # segment starts from a real speed. The threshold sits just under the
    # controller's own floor (regulated_linear_scaling_min_speed 0.05) so it
    # only catches the ramp crossing, never a legitimate cruise command.
    deadband = smoother.get("deadband_velocity") or [0.0, 0.0, 0.0]
    smoother["deadband_velocity"] = [0.049, deadband[1], deadband[2]]

    controller = config["controller_server"]["ros__parameters"]
    follow_path = controller["FollowPath"]
    # Measured floor, not a preference: the drive PWM cannot go below 45 without
    # stalling, and PWM 45 moves this chassis at 0.094 m/s (tape-measured 0.23 m
    # over 2.02 s, agreeing with TF to 2.6% and the encoders at 1470 ticks/m).
    # Letting the controller scale below that makes it believe it slowed down when
    # nothing changed, so it keeps adding steering instead -- which is how a tight
    # curve turns into a full-lock veer.
    # The floor the chassis can actually hold. Measured from rest, 1 s per step:
    # PWM 44 -> 0.074 m/s, 42 -> 0.059, 41 -> ~0.05, 40 -> 0.039, 38 -> 0.024,
    # 36 -> stalls. Below PWM 41 the two rear motors also diverge sharply (16% of
    # each other at 40, 58% at 38), so a slower floor would buy regulation range at
    # the cost of veering every time the controller slowed down. Asking for less
    # than this makes the controller believe it slowed when it did not, and it
    # answers by steering harder instead.
    follow_path["regulated_linear_scaling_min_speed"] = 0.05
    # Pure pursuit oscillates once the lookahead falls under the turning radius:
    # the carrot sits inside the tightest arc the chassis can draw, so it can never
    # be reached and the controller answers by steering harder. 0.34 m is the
    # measured radius, so keep the lookahead comfortably outside it.
    follow_path["min_lookahead_dist"] = 0.45
    follow_path["lookahead_dist"] = 0.50
    # Without this the controller drives forward along a reverse segment instead
    # of backing along it, so the Reeds-Shepp plan above would be worse than no
    # plan. Safe to pair only because use_rotate_to_heading is false; Nav2 rejects
    # the two together. The adapter already signs the drive PWM from linear.x, so
    # a negative command reaches the chassis as reverse.
    follow_path["allow_reversing"] = True

    bt = config["bt_navigator"]["ros__parameters"]
    mapping_bt = environment.get("ROKI_NAV2_MAPPING_BT_XML", "").strip()
    if mapping_bt:
        bt["default_nav_to_pose_bt_xml"] = mapping_bt

    return yaml.safe_dump(config, sort_keys=False, allow_unicode=True)


def render_nav2_config(
    template_path: Path,
    output_path: Path,
    environment: Mapping[str, str],
) -> dict[str, str]:
    values = build_nav2_values(environment)
    template = Template(template_path.read_text(encoding="utf-8"))
    rendered = apply_slam_shape(template.substitute(values), environment)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(rendered, encoding="utf-8")
        os.chmod(temporary, 0o640)
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return values


def _positive_float(
    environment: Mapping[str, str], name: str, *, default: str | None = None
) -> float:
    raw = environment.get(name, default or "")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return value


def _finite_float(environment: Mapping[str, str], name: str) -> float:
    raw = environment.get(name, "")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _number(value: float) -> str:
    rendered = f"{value:.6f}".rstrip("0").rstrip(".")
    # ROS 2 parameters are strongly typed. YAML scalars such as ``0`` are
    # integers, so AMCL rejects them for its double-valued initial pose even
    # though the source environment was parsed as a float. Keep every
    # rendered measurement explicitly floating-point.
    return rendered if "." in rendered else f"{rendered}.0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--software-only", action="store_true")
    args = parser.parse_args(argv)

    if args.software_only:
        print(
            json.dumps(
                {
                    "fieldReady": not missing_field_variables(os.environ),
                    "missingMeasurements": missing_field_variables(os.environ),
                    "template": args.template.as_posix(),
                },
                sort_keys=True,
            )
        )
        return 0
    if args.output is None:
        parser.error("--output is required unless --software-only is used")
    values = render_nav2_config(args.template, args.output, os.environ)
    print(json.dumps({"fieldReady": True, "values": values}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
