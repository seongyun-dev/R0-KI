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
    "ROKI_ROBOT_RADIUS_M",
    "ROKI_INITIAL_POSE_X_M",
    "ROKI_INITIAL_POSE_Y_M",
    "ROKI_INITIAL_POSE_YAW_RAD",
)
DEFAULT_NAV2_XY_GOAL_TOLERANCE_M = 0.20


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
    robot_radius = _positive_float(environment, "ROKI_ROBOT_RADIUS_M")
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
        "ROBOT_RADIUS_M": _number(robot_radius),
        "INFLATION_RADIUS_M": _number(robot_radius + 0.15),
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


def apply_mapping_overrides(rendered: str, environment: Mapping[str, str]) -> str:
    """Turn the patrol Nav2 config into the mapping-mode variant.

    Patrol deliberately keeps the stored map out of the global costmap: there the
    map is localization evidence and the live LiDAR owns obstacle decisions.
    Exploration needs the opposite -- the planner must see the map that SLAM is
    still growing so it can route through known free space toward a frontier and
    refuse to cut through unexplored cells.

    Only the differences live here so the two configurations cannot drift apart.
    """

    import yaml

    config = yaml.safe_load(rendered)

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

    # The template inflates robot_radius + 0.15 = 0.38 m, which suits an open floor.
    # Here the mapped corridor measures about 1.1 m across, so a 0.38 m skirt on each
    # wall leaves roughly 0.3 m of un-penalised centre -- less than the 0.34 m turning
    # radius, so no arc toward an off-axis frontier fits and every plan is refused.
    # Lethality is untouched: it still comes from the 0.23 m footprint, and the LiDAR
    # interlock still stops the chassis on approach. This only stops the planner from
    # treating the whole room as expensive.
    for scope in ("global_costmap", "local_costmap"):
        layer = config[scope][scope]["ros__parameters"]["inflation_layer"]
        layer["inflation_radius"] = 0.25

    planner = config["planner_server"]["ros__parameters"]["GridBased"]
    # Exploration is the one mode that has to maneuver through space it has not
    # mapped yet. A Dubin path can only curve forward, so with 0.34 m of turning
    # radius a wall 0.3-0.4 m to one side leaves no forward arc that clears it --
    # that is what "RegulatedPurePursuitController detected collision ahead" was.
    # Reeds-Shepp adds reverse segments, and the template's reverse_penalty keeps
    # them short and last-resort. Patrol stays on DUBIN: it follows an operator's
    # route through space already known to be drivable, and reversing there would
    # move the robot away from the waypoint it was sent to.
    planner["motion_model_for_search"] = "REEDS_SHEPP"
    # The template's 2.1 is tuned for patrol, where reversing means leaving the
    # waypoint you were sent to. During exploration a frontier is often close and
    # far off-axis -- 0.93 m at 121 deg was observed live -- and the only path that
    # fits a 0.34 m turning radius in a room this size starts by backing up. At 2.1
    # the search kept preferring forward arcs that swept into the wall, so no plan
    # existed at all. Still above 1.0 so forward stays preferred when it works.
    planner["reverse_penalty"] = 1.3
    # Upstream documents this as safe only when the costmap is largely static: it
    # reuses the obstacle dynamic-programming expansion between replans. While SLAM
    # is still growing the map that assumption is false every second, so the search
    # runs against a stale heuristic and gives up on goals that are reachable.
    planner["cache_obstacle_heuristic"] = False

    # The template forbids negative linear velocity, which is right for patrol: that
    # mode plans with DUBIN and must never retreat from the waypoint it was sent to.
    # Here it silently defeated the whole reverse setup. /cmd_vel is published by the
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
    # explore_lite stamps every frontier goal with an identity quaternion, i.e.
    # "arrive facing 0 rad" (explore.cpp: goal.pose.pose.orientation.w = 1).
    # A differential robot just pivots on arrival, but this chassis would have to
    # contort a Dubin path to hit that heading, and the resulting curvature makes
    # the controller throttle linear velocity to zero while still commanding yaw
    # -- an in-place rotation the Ackermann adapter must refuse. Arrival heading
    # carries no meaning for exploration, so free it.
    controller["general_goal_checker"]["yaw_goal_tolerance"] = 3.15
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
    *,
    mapping: bool = False,
) -> dict[str, str]:
    values = build_nav2_values(environment)
    template = Template(template_path.read_text(encoding="utf-8"))
    rendered = template.substitute(values)
    if mapping:
        rendered = apply_mapping_overrides(rendered, environment)
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
    parser.add_argument(
        "--mapping",
        action="store_true",
        help="render the mapping-mode variant that follows the live SLAM map",
    )
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
    values = render_nav2_config(
        args.template, args.output, os.environ, mapping=args.mapping
    )
    print(
        json.dumps(
            {"fieldReady": True, "mapping": args.mapping, "values": values},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
