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


def render_nav2_config(
    template_path: Path,
    output_path: Path,
    environment: Mapping[str, str],
) -> dict[str, str]:
    values = build_nav2_values(environment)
    template = Template(template_path.read_text(encoding="utf-8"))
    rendered = template.substitute(values)
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
