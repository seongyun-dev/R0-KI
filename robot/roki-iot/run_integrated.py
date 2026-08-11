#!/usr/bin/env python3
"""Production composition root for Robot MQTT, navigation, AI and telemetry."""

from __future__ import annotations

import argparse
import hmac
import importlib.util
import logging
import math
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
ROBOT_ROOT = PROJECT_ROOT.parent
FINAL_RUNTIME_ROOT = ROBOT_ROOT / "roki"
ROBOT_SRC_ROOT = ROBOT_ROOT / "src"

for path in (str(ROBOT_SRC_ROOT), str(FINAL_RUNTIME_ROOT), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _patrol_behavior_tree_xml() -> str:
    """Return the Patrol-only BT path without reusing the Mapping default."""

    configured = os.getenv("ROKI_NAV2_PATROL_BT_XML", "").strip()
    path = (
        Path(configured)
        if configured
        else ROBOT_ROOT
        / "config"
        / "ros"
        / "nav2_fixed_path_through_poses.xml"
    )
    if not path.is_absolute():
        raise RuntimeError("ROKI_NAV2_PATROL_BT_XML must be an absolute path")
    return path.as_posix()


def _build_final_components() -> tuple[Any, Any, Any]:
    """Build the sole ESP32 owner and read-only ROS sensor bridges."""

    final_root = str(FINAL_RUNTIME_ROOT)
    original_sys_path = list(sys.path)
    sys.path = [final_root, *(path for path in original_sys_path if path != final_root)]
    try:
        from scripts.run_runtime import (
            build_ros_lidar_health_bridge,
            build_ros_tf_pose_bridge,
            build_runtime,
        )

        runtime = build_runtime()
        pose_bridge = build_ros_tf_pose_bridge(runtime.state_store)
        lidar_health_bridge = build_ros_lidar_health_bridge(runtime.state_store)
    finally:
        sys.path = original_sys_path

    return runtime, pose_bridge, lidar_health_bridge


def _selected_route_path(route_path: str | Path | None = None) -> Path:
    return Path(
        route_path
        or os.getenv(
            "ROKI_ROUTE_FILE",
            "/var/lib/aiot/config/route.local.yaml",
        )
    )


def _validate_import_namespaces() -> None:
    """Ensure final-runtime and backend-compatibility packages coexist."""

    final_root = str(FINAL_RUNTIME_ROOT)
    original_sys_path = list(sys.path)
    preserved_state_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "state" or name.startswith("state.")
    }
    for name in preserved_state_modules:
        del sys.modules[name]
    sys.path = [final_root, *(path for path in original_sys_path if path != final_root)]
    try:
        from state.robot_state import RobotStateStore as FinalRobotStateStore
        from backend_state.robot_state_store import (
            RobotStateStore as BackendRobotStateStore,
        )
        from mqtt.client import MqttClient as FinalMqttClient
        from backend_mqtt.client import MqttClient as BackendMqttClient
        from integration.runtime_state_backend_adapter import FinalRuntimeService

        if (
            FinalRobotStateStore is BackendRobotStateStore
            or FinalMqttClient is BackendMqttClient
            or FinalRuntimeService is None
        ):
            raise RuntimeError("runtime import namespaces are not isolated")
    finally:
        sys.path = original_sys_path
        for name in tuple(sys.modules):
            if name == "state" or name.startswith("state."):
                del sys.modules[name]
        sys.modules.update(preserved_state_modules)


def _build_navigation_service(
    route_path: str | Path | None = None,
    *,
    encoder_limited: bool,
) -> Any:
    if encoder_limited:
        raise RuntimeError(
            "DEMO_NAV2_REQUIRED: encoder_limited is a straight-line diagnostic "
            "mode and cannot run the fixed-map demo patrol"
        )
    selected_path = _selected_route_path(route_path)
    if not selected_path.is_file():
        raise RuntimeError(f"waypoint route file is missing: {selected_path}")
    from navigation.route import load_route

    return _build_navigation_service_from_route(
        load_route(selected_path),
        encoder_limited=encoder_limited,
        route_path=selected_path,
    )


def _build_navigation_service_from_route(
    route: Any,
    *,
    encoder_limited: bool,
    route_path: Path | None = None,
) -> Any:
    """Validate either a local file route or a freshly fetched Backend route."""

    if encoder_limited:
        raise RuntimeError(
            "DEMO_NAV2_REQUIRED: encoder_limited is a straight-line diagnostic "
            "mode and cannot run the fixed-map demo patrol"
        )
    from navigation.map_metadata import (
        file_sha256,
        load_map_metadata,
        map_bundle_sha256,
        validate_route_bounds,
    )
    from navigation.route import RouteValidationError
    from navigation.service import WaypointNavigationService
    from aiot_robot.ros_config import nav2_xy_goal_tolerance

    xy_goal_tolerance_m = nav2_xy_goal_tolerance(os.environ)
    for waypoint in route.waypoints:
        if waypoint.acceptance_radius_m < xy_goal_tolerance_m:
            raise RouteValidationError(
                f"waypoint {waypoint.sequence} acceptance_radius_m "
                f"{waypoint.acceptance_radius_m:.3f} is below Nav2 "
                f"xy_goal_tolerance {xy_goal_tolerance_m:.3f}; Nav2 could "
                "stop before the mission advances"
            )
    raw_map_path = os.getenv("ROKI_MAP_YAML", "").strip()
    map_path = Path(raw_map_path)
    if not raw_map_path or not map_path.is_absolute() or not map_path.is_file():
        raise RuntimeError(
            "NAV2_MAP_MISSING: ROKI_MAP_YAML must be a readable absolute map YAML"
        )
    metadata = load_map_metadata(map_path)
    expected_map_id = _required_environment("ROKI_MAP_ID")
    expected_map_version = _required_positive_integer("ROKI_MAP_VERSION")
    if route.map_id != expected_map_id:
        raise RouteValidationError(
            f"route map_id {route.map_id!r} does not match ROKI_MAP_ID"
        )
    if route.map_version != expected_map_version:
        raise RouteValidationError(
            "route map_version does not match ROKI_MAP_VERSION"
        )
    expected_map_sha256 = _required_sha256("ROKI_MAP_SHA256")
    if not hmac.compare_digest(map_bundle_sha256(metadata), expected_map_sha256):
        raise RouteValidationError("map YAML/image SHA256 does not match deployment")
    if route_path is not None:
        expected_route_sha256 = _required_sha256("ROKI_ROUTE_SHA256")
        if not hmac.compare_digest(file_sha256(route_path), expected_route_sha256):
            raise RouteValidationError("route SHA256 does not match deployment")

    # Keep only deployment identity and coordinate sanity here.  Occupancy,
    # unknown-space and robot-footprint decisions belong to Nav2's live
    # costmaps, where current LiDAR data can be considered.  Static rejection
    # made a usable field map impossible to patrol and also incorrectly tied
    # every route to one preconfigured dock coordinate.
    validate_route_bounds(route, metadata)
    return WaypointNavigationService(route)


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"DEMO_CONFIG_MISSING: {name} must be set")
    return value


def _required_positive_integer(name: str) -> int:
    raw = _required_environment(name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"DEMO_CONFIG_INVALID: {name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"DEMO_CONFIG_INVALID: {name} must be positive")
    return value


def _required_sha256(name: str) -> str:
    value = _required_environment(name).lower()
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RuntimeError(f"DEMO_CONFIG_INVALID: {name} must be a SHA256 hex digest")
    return value


def _navigation_mode(settings: Any) -> str:
    mode = settings.navigation_mode
    if mode != "nav2":
        raise RuntimeError(
            "DEMO_NAV2_REQUIRED: set ROKI_NAVIGATION_MODE=nav2; automatic "
            "encoder_limited fallback is disabled for the fixed-map demo"
        )
    from aiot_robot.ros_config import build_nav2_values

    try:
        build_nav2_values(os.environ)
    except ValueError as exc:
        raise RuntimeError(f"NAV2_FIELD_CONFIG_INVALID: {exc}") from exc
    if importlib.util.find_spec("nav2_msgs") is None:
        raise RuntimeError("NAV2_PACKAGE_MISSING: nav2_msgs is not installed")
    return "nav2"


def _build_nav2_driver(
    service_holder: dict[str, Any],
    mapping_sink_holder: dict[str, Any] | None = None,
) -> Any:
    from navigation.cmd_vel_adapter import AckermannCommandSettings
    from navigation.ros_nav2_bridge import RosNav2Bridge, RosNav2BridgeSettings

    wheelbase = os.getenv("ROKI_WHEELBASE_M")
    maximum_angle = os.getenv("ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG")
    if not wheelbase or not maximum_angle:
        raise RuntimeError(
            "Nav2 mode requires ROKI_WHEELBASE_M and "
            "ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG"
        )
    settings = RosNav2BridgeSettings(
        ackermann=AckermannCommandSettings(
            wheelbase_m=float(wheelbase),
            maximum_road_wheel_angle_deg=float(maximum_angle),
            maximum_linear_speed_mps=float(
                os.getenv("ROKI_MAXIMUM_LINEAR_SPEED_MPS", "0.4")
            ),
            minimum_drive_pwm=int(os.getenv("PATROL_DRIVE_SPEED_PWM", "45")),
            maximum_drive_pwm=int(os.getenv("ROKI_MAXIMUM_DRIVE_PWM", "51")),
            steering_left_deg=40,
            steering_center_deg=80,
            steering_right_deg=120,
        ),
        patrol_behavior_tree_xml=_patrol_behavior_tree_xml(),
        cmd_vel_topic=os.getenv("ROKI_CMD_VEL_TOPIC", "/cmd_vel"),
        navigate_action=os.getenv(
            "ROKI_NAVIGATE_ACTION", "/navigate_through_poses"
        ),
        map_frame=os.getenv("ROKI_MAP_FRAME", "map"),
        scan_dwell_sec=float(os.getenv("ROKI_SCAN_DWELL_SECONDS", "3.0")),
        cmd_vel_timeout_sec=float(
            os.getenv("ROKI_NAV2_CMD_VEL_TIMEOUT_SECONDS", "3.0")
        ),
        goal_abort_retry_limit=int(
            os.getenv("ROKI_NAV2_GOAL_ABORT_RETRY_LIMIT", "3")
        ),
    )
    def route_motion(command: Any) -> None:
        """실행 중인 운행에 따라 cmd_vel 을 알맞은 게이트로 보낸다.

        예전에는 부팅 시점의 AIOT_ROS_MODE 가 이걸 정했다. 매핑 모드면 순찰
        내비게이션 자체를 만들지 않았고, 그래서 브리지가 하나뿐이라 라우팅이
        필요 없었다. 이제 두 운행이 같은 스택을 쓰므로 브리지도 하나이고,
        어느 게이트로 갈지는 실행 중에 정해야 한다.
        (2026-08-08 실기: 이 라우팅이 없어 매핑 중 cmd_vel 이 순찰 게이트로
        가서 활성 순찰이 없다는 이유로 전부 MOTION_INTERLOCK 이 됐다.
        10분에 2,530건, 게이트 개방 0회.)
        """

        mapping_sink = (mapping_sink_holder or {}).get("sink")
        authorised = mapping_sink is not None and mapping_sink.mapping_authorised()
        # 결정이 바뀔 때만 한 줄. cmd_vel 은 20Hz 라 매번 찍으면 로그가 묻힌다.
        if route_motion.__dict__.get("last") != authorised:
            route_motion.__dict__["last"] = authorised
            print(
                "[MOTION ROUTE] "
                + ("mapping" if authorised else "patrol")
                + f" sink={'yes' if mapping_sink is not None else 'MISSING'}"
            )
        # 전이 로그만으로는 "콜백이 안 온다" 와 "콜백은 오는데 값이 0 이다" 를
        # 구분할 수 없다. 2026-08-08 현장에서 정확히 그 둘 사이에서 막혔다:
        # /cmd_vel 은 흐르는데 미션은 100% 비활성이었고, 라우터는 전이가 없어
        # 조용했다. 주기 집계는 호출 자체가 없으면 아무것도 찍지 않으므로
        # 침묵이 곧 "콜백 없음" 이라는 답이 된다.
        state = route_motion.__dict__
        state["calls"] = state.get("calls", 0) + 1
        if authorised:
            state["auth"] = state.get("auth", 0) + 1
        speed = int(getattr(command, "speed_pwm", 0))
        if speed == 0:
            state["zero"] = state.get("zero", 0) + 1
        elif speed < 0:
            state["reverse"] = state.get("reverse", 0) + 1
        else:
            state["forward"] = state.get("forward", 0) + 1
        # 조향 최소/최대를 남긴다. 2026-08-08 매핑이 4초 주행 뒤 펌웨어의
        # ESP32_INVALID_CONTROL 로 중단됐는데, 저널에는 게이트 전이 한 줄
        # (steering=67) 밖에 없어서 어느 값이 거부됐는지 알 수 없었다.
        # 펌웨어 소스의 허용 범위는 60..100 인데 CLAUDE.md B-7/B-8 의 실측은
        # 40/120 이 ACK 됐다고 기록한다 -- 둘 중 무엇이 실제인지 값을 봐야
        # 정해진다. 정지 명령(0)은 중립을 싣고 오므로 세지 않는다.
        if speed != 0:
            steering = int(getattr(command, "steering_deg", 0))
            low = state.get("steer_min")
            high = state.get("steer_max")
            state["steer_min"] = steering if low is None else min(low, steering)
            state["steer_max"] = steering if high is None else max(high, steering)
        now = time.monotonic()
        started = state.get("at")
        if started is None:
            state["at"] = now
        elif now - started >= 5.0:
            state["at"] = now
            print(
                f"[ROUTE CENSUS] {now - started:.0f}s "
                f"calls={state.get('calls', 0)} auth={state.get('auth', 0)} "
                f"fwd={state.get('forward', 0)} rev={state.get('reverse', 0)} "
                f"zero={state.get('zero', 0)} "
                f"steer={state.get('steer_min')}..{state.get('steer_max')} "
                f"last_speed={speed} last_reason={getattr(command, 'stop_reason', None)}",
                flush=True,
            )
            for key in ("calls", "auth", "forward", "reverse", "zero"):
                state[key] = 0
            state["steer_min"] = None
            state["steer_max"] = None
        if authorised:
            mapping_sink(command)
            return
        service_holder["service"].apply_motion_command(command)

    def mapping_holds_motion_authority() -> bool:
        """매핑 세션이 스스로 주행 권한을 갖는가.

        브리지의 cmd_vel 홀드는 순찰 생애주기 개념이라 순찰 goal 수락으로만
        풀린다. 자율 매핑의 goal 은 프론티어 탐색기가 보내므로 그 해제 경로가
        돌지 않고, stop_patrol 이 걸어둔 홀드가 영구히 남아 모든 명령을 0 으로
        만든다. 매핑 세션은 순찰과 무관한 별도의 주행 권한이므로 여기서 그렇게
        답한다. 라우터가 쓰는 것과 같은 판단이라 둘이 어긋날 수 없다.
        """

        mapping_sink = (mapping_sink_holder or {}).get("sink")
        return mapping_sink is not None and mapping_sink.mapping_authorised()

    return RosNav2Bridge(
        settings=settings,
        motion_sink=route_motion,
        failure_sink=lambda reason: service_holder["service"].fail_patrol(reason),
        obstacle_sink=lambda reason: service_holder["service"].pause_patrol(reason),
        scan_context_sink=lambda waypoint: service_holder[
            "service"
        ].update_scan_context(waypoint),
        external_motion_authority=mapping_holds_motion_authority,
    )


def build_mapping_motion_sink(
    runtime: Any, mapping_runtime_holder: dict[str, Any]
) -> Any:
    """매핑 세션이 살아 있는 동안만 섀시를 여는 게이트.

    브리지와 분리해 둔다. 지도가 이미 있으면 순찰 브리지가 cmd_vel 을
    구독하므로 매핑 전용 브리지를 또 만들면 두 구독자가 같은 명령을 놓고
    서로 정지시킨다. 그때는 브리지 없이 이 싱크만 순찰 브리지의 라우터에
    넘긴다.
    """

    from integration.mapping_motion_sink import MappingMotionSink

    return MappingMotionSink(
        runtime,
        lambda: mapping_runtime_holder.get("mapping"),
        stop_reporter=lambda reason: print(f"[MAPPING] motion stop reason={reason}"),
    )


def _build_mapping_nav2_bridge(
    runtime: Any, mapping_runtime_holder: dict[str, Any]
) -> Any:
    """Subscribe to Nav2 ``cmd_vel`` so the frontier explorer can drive mapping.

    Only the cmd_vel-to-ESP32 half of the bridge is wanted here: goals come from
    explore_lite over its own Nav2 action client, never from this process. The
    bridge therefore gets a mapping-session motion sink and no failure sink, and
    ``start_patrol`` is never called on it.
    """

    from navigation.ros_nav2_bridge import RosNav2Bridge, RosNav2BridgeSettings
    from navigation.cmd_vel_adapter import AckermannCommandSettings

    wheelbase = os.getenv("ROKI_WHEELBASE_M", "").strip()
    maximum_angle = os.getenv("ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG", "").strip()
    if not wheelbase or not maximum_angle:
        raise RuntimeError(
            "AUTONOMOUS_MAPPING_FIELD_CONFIG_MISSING: ROKI_WHEELBASE_M and "
            "ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG are required"
        )
    sink = build_mapping_motion_sink(runtime, mapping_runtime_holder)
    return RosNav2Bridge(
        settings=RosNav2BridgeSettings(
            ackermann=AckermannCommandSettings(
                wheelbase_m=float(wheelbase),
                maximum_road_wheel_angle_deg=float(maximum_angle),
                maximum_linear_speed_mps=float(
                    os.getenv("ROKI_MAXIMUM_LINEAR_SPEED_MPS", "0.4")
                ),
                minimum_drive_pwm=int(os.getenv("PATROL_DRIVE_SPEED_PWM", "45")),
                maximum_drive_pwm=int(os.getenv("ROKI_MAXIMUM_DRIVE_PWM", "51")),
                steering_left_deg=40,
                steering_center_deg=80,
                steering_right_deg=120,
            ),
            cmd_vel_topic=os.getenv("ROKI_CMD_VEL_TOPIC", "/cmd_vel"),
            navigate_action=os.getenv(
                "ROKI_NAVIGATE_ACTION", "/navigate_through_poses"
            ),
            map_frame=os.getenv("ROKI_MAP_FRAME", "map"),
        ),
        motion_sink=sink,
    )


def _build_manual_demo_components(runtime: Any) -> tuple[Any, Any]:
    """Build the temporary TTY demo without creating another Serial owner."""

    from control.manual_drive_controller import (
        ManualDriveController,
        ManualDriveSettings,
    )
    from integration.manual_keyboard_input import ManualKeyboardInput

    settings = ManualDriveSettings(
        forward_target_pwm=int(os.getenv("ROKI_MANUAL_FORWARD_PWM", "45")),
        reverse_target_pwm=int(os.getenv("ROKI_MANUAL_REVERSE_PWM", "40")),
        drive_pulse_sec=float(os.getenv("ROKI_MANUAL_DRIVE_PULSE_SEC", "0.2")),
        steering_center_deg=int(os.getenv("ROKI_MANUAL_STEERING_CENTER_DEG", "80")),
        steering_min_deg=int(os.getenv("ROKI_MANUAL_STEERING_MIN_DEG", "70")),
        steering_max_deg=int(os.getenv("ROKI_MANUAL_STEERING_MAX_DEG", "90")),
        steering_step_deg=int(os.getenv("ROKI_MANUAL_STEERING_STEP_DEG", "2")),
        steering_pulse_sec=float(
            os.getenv("ROKI_MANUAL_STEERING_PULSE_SEC", "0.5")
        ),
    )
    controller = ManualDriveController(
        runtime=runtime,
        state_store=runtime.state_store,
        settings=settings,
    )
    return controller, ManualKeyboardInput(
        controller,
        loop_interval_sec=float(
            os.getenv("ROKI_MANUAL_KEYBOARD_LOOP_SEC", "0.02")
        ),
    )


def _environment_enabled(name: str, default: bool = True) -> bool:
    value = os.getenv(name, "true" if default else "false")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _active_map_directory() -> Path | None:
    """활성 지도 디렉터리. 프로세스 환경이 아니라 env 파일에서 읽는다.

    매핑이 끝나면 ``map_activation`` 이 ``current-map.env`` 를 갱신하지만,
    이미 떠 있는 프로세스의 ``os.environ`` 은 부팅 시점 값 그대로다. 방금 그린
    지도로 순찰하려면 파일을 다시 읽어야 한다 -- 안 읽으면 이전 지도의
    포즈그래프를 적재하고, 로봇은 있지도 않은 벽 사이에서 위치추정을 한다.

    파일이 없거나 깨졌으면 부팅 시 환경으로 물러난다. 둘 다 없으면 활성 지도가
    없는 것이 맞다.
    """

    map_yaml = _active_map_environment().get("ROKI_MAP_YAML", "").strip()
    if not map_yaml:
        return None
    return Path(map_yaml).parent


def _active_map_environment() -> dict[str, str]:
    """current-map.env 의 ROKI_MAP_* 을 읽는다. 없는 키는 부팅 env 로 메운다."""

    import json

    environment_file = Path(
        os.getenv("AIOT_ACTIVE_MAP_ENV_FILE", "/var/lib/aiot/config/current-map.env")
    )
    values: dict[str, str] = {}
    try:
        for line in environment_file.read_text(encoding="utf-8").splitlines():
            name, separator, raw = line.partition("=")
            name = name.strip()
            if not separator or not name.startswith("ROKI_MAP_"):
                continue
            # map_activation 이 json.dumps 로 적는다. 따옴표를 벗긴다.
            try:
                values[name] = str(json.loads(raw.strip()))
            except ValueError:
                values[name] = raw.strip().strip('"')
    except (OSError, UnicodeError):
        values = {}
    for name in ("ROKI_MAP_YAML", "ROKI_MAP_ID", "ROKI_MAP_VERSION"):
        if not values.get(name):
            fallback = os.getenv(name, "").strip()
            if fallback:
                values[name] = fallback
    return values


def _patrol_start_anchor(route: Any) -> tuple[float, float, float, str] | None:
    """Return waypoint 1 and its route-facing yaw in map coordinates."""

    waypoints = tuple(getattr(route, "waypoints", ()) or ())
    if not waypoints:
        return None
    first = waypoints[0]
    explicit_yaw = getattr(first, "yaw_deg", None)
    if explicit_yaw is not None:
        return (
            float(first.x),
            float(first.y),
            math.radians(float(explicit_yaw)),
            "WAYPOINT_YAW",
        )
    if len(waypoints) < 2:
        return None
    second = waypoints[1]
    delta_x = float(second.x) - float(first.x)
    delta_y = float(second.y) - float(first.y)
    if math.hypot(delta_x, delta_y) <= 1e-6:
        return None
    return (
        float(first.x),
        float(first.y),
        math.atan2(delta_y, delta_x),
        "ROUTE_GEOMETRY",
    )


def _prepare_patrol_localization(
    mapping_runtime: Any,
    route: Any | None = None,
    *,
    require_start_anchor: bool = False,
) -> tuple[bool, str]:
    """포즈그래프를 적재하고 위치추정이 실제로 붙을 때까지 기다린다.

    예전에는 여기서 스캔을 끊었다 다시 이었다. 그 게이팅은 걷어냈다 --
    slam 이 라이다를 직접 구독하므로 끊을 수 있는 것이 없고, 끊으면 map
    프레임이 사라져 Nav2 와 pose 가 함께 죽는다(slam_toolbox.yaml 주석).

    남은 것은 관측이다. ``deserialize_map`` 은 빈 응답이라 성공/실패를
    알려주지 않으므로, 적재 이후의 새 스캔과 그에 이어진 map->odom 을 직접
    확인해야 순찰이 지도 없이 출발하는 것을 막을 수 있다.
    """

    slam = getattr(mapping_runtime, "slam_session", None)
    localization = getattr(mapping_runtime, "localization", None)
    if localization is None:
        return True, "LOCALIZATION_HANDOVER_UNAVAILABLE"
    directory = _active_map_directory()
    if directory is None:
        return False, "ACTIVE_MAP_MISSING"
    marker = slam.marker() if slam is not None else None
    ready, reason = localization.ensure_patrol(str(directory / "posegraph"))
    if not ready or slam is None:
        return ready, reason

    try:
        timeout_sec = float(os.getenv("AIOT_PATROL_LOCALIZATION_TIMEOUT_SEC", "30"))
        deadline = time.monotonic() + timeout_sec
        if not slam.wait_for_localization_ready(marker, timeout_sec=timeout_sec):
            return False, "LOCALIZATION_NOT_READY"
    except Exception as exc:
        print(f"[SLAM] patrol localization wait failed type={type(exc).__name__}")
        return False, "LOCALIZATION_NOT_READY"

    if not require_start_anchor:
        return True, reason

    anchor = _patrol_start_anchor(route)
    if anchor is None:
        return False, "START_ANCHOR_INVALID"
    anchor_x, anchor_y, anchor_yaw, yaw_source = anchor
    remaining = deadline - time.monotonic()
    initialpose_timeout = min(
        remaining,
        float(os.getenv("AIOT_INITIALPOSE_TIMEOUT_SEC", "10")),
    )
    if initialpose_timeout <= 0:
        return False, "INITIALPOSE_TIMEOUT"
    print(
        "[INITIALPOSE] start anchor "
        f"x={anchor_x:.3f} y={anchor_y:.3f} "
        f"yawDeg={math.degrees(anchor_yaw):.1f} source={yaw_source}"
    )
    try:
        return slam.relocalize(
            x=anchor_x,
            y=anchor_y,
            yaw_rad=anchor_yaw,
            timeout_sec=initialpose_timeout,
            position_tolerance_m=float(
                os.getenv("AIOT_INITIALPOSE_POSITION_TOLERANCE_M", "0.25")
            ),
            yaw_tolerance_rad=math.radians(
                float(os.getenv("AIOT_INITIALPOSE_YAW_TOLERANCE_DEG", "30"))
            ),
        )
    except Exception as exc:
        print(f"[INITIALPOSE] failed type={type(exc).__name__}")
        return False, "INITIALPOSE_FAILED"


def _no_active_map() -> bool:
    """아직 지도가 없으면 순찰 경로를 검증할 대상이 없다.

    예전에는 AIOT_ROS_MODE 로 판단했다. 그 변수는 "지금 어느 노드 집합이
    떠 있는가"를 뜻했고, 매핑 모드에는 순찰 경로가 없으니 검증을 미뤘다.
    이제 두 운행이 같은 노드 집합으로 돌아 그 변수가 사라졌지만, 판단의
    실질은 그대로다 -- 활성 지도가 없으면 순찰할 경로도 없다.
    지도가 활성화되면 map_activation 이 ROKI_MAP_YAML 을 기록한다.
    """

    return not os.getenv("ROKI_MAP_YAML", "").strip()


class _NoOpMappingInput:
    """No-op mapping input used when the optional gamepad is disabled."""

    device_path = Path("disabled")

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    @staticmethod
    def diagnostic_snapshot() -> dict[str, object]:
        return {
            "gamepadDeviceOpen": False,
            "gamepadThreadAlive": False,
            "lastGamepadDecision": "DISABLED",
            "lastGamepadDecisionAgoMs": None,
        }


# Compatibility for the already-deployed focused test name.
_DisabledMappingInput = _NoOpMappingInput


def _legacy_mapping_only_selected(settings: Any, route_path: Path) -> bool:
    """Preserve the pre-route mapping bootstrap used before Nav2 is configured."""

    return settings.navigation_mode == "encoder_limited" and not route_path.is_file()


def _require_legacy_route_when_mapping_disabled(
    settings: Any, route_path: Path
) -> None:
    if settings.navigation_mode == "encoder_limited" and not route_path.is_file():
        raise RuntimeError(f"waypoint route file is missing: {route_path}")


def _navigation_config_source() -> str:
    source = os.getenv("AIOT_NAVIGATION_CONFIG_SOURCE", "backend").strip().lower()
    if source not in {"backend", "local"}:
        raise RuntimeError(
            "NAVIGATION_CONFIG_SOURCE_INVALID: "
            "AIOT_NAVIGATION_CONFIG_SOURCE must be backend or local"
        )
    return source


def _event_delivery_owner() -> str:
    owner = os.getenv("AIOT_EVENT_DELIVERY_OWNER", "robot").strip().lower()
    if owner != "robot":
        raise RuntimeError(
            "EVENT_DELIVERY_OWNER_INVALID: AIOT_EVENT_DELIVERY_OWNER must be robot"
        )
    return owner


def _current_navigation_identity() -> Any:
    """지금 활성인 지도의 (mapId, mapVersion). 매 조회마다 파일에서 읽는다."""

    from aiot_robot.navigation_config import NavigationConfigIdentity

    values = _active_map_environment()
    map_id = values.get("ROKI_MAP_ID", "").strip()
    raw_version = values.get("ROKI_MAP_VERSION", "").strip()
    if not map_id or not raw_version:
        raise RuntimeError("ACTIVE_MAP_IDENTITY_MISSING")
    try:
        map_version = int(raw_version)
    except ValueError as exc:
        raise RuntimeError("ACTIVE_MAP_IDENTITY_INVALID") from exc
    if map_version <= 0:
        raise RuntimeError("ACTIVE_MAP_IDENTITY_INVALID")
    return NavigationConfigIdentity(map_id=map_id, map_version=map_version)


def _build_backend_navigation_provider(settings: Any) -> Any:
    """Build a deferred Robot-token client; no network is used until START."""

    from aiot_robot.backend_client import BackendConfig, RobotBackendClient
    from aiot_robot.navigation_config import (
        BackendNavigationConfigProvider,
        NavigationConfigIdentity,
    )

    token_file = Path(settings.service_token_file)

    def backend_factory() -> Any:
        token = os.getenv("AIOT_BACKEND_ACCESS_TOKEN", "").strip()
        if not token:
            try:
                token = token_file.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise RuntimeError("backend token is unavailable") from exc
        if not token:
            raise RuntimeError("backend token is unavailable")
        return RobotBackendClient(
            BackendConfig(
                base_url=_required_environment("AIOT_BACKEND_BASE_URL"),
                access_token=token,
                timeout_seconds=float(os.getenv("AIOT_BACKEND_TIMEOUT_SEC", "10")),
            )
        )

    return BackendNavigationConfigProvider(
        backend_factory=backend_factory,
        navigation_factory=lambda route: _build_navigation_service_from_route(
            route,
            encoder_limited=False,
        ),
        # 부팅 시 값으로 고정하지 않는다. 매핑이 끝나면 map_activation 이
        # current-map.env 를 갱신하지만 이 프로세스의 os.environ 은 그대로다.
        # 2026-08-08 14:00 실기: 런타임이 v32 를 들고 있는데 백엔드 경로가
        # 방금 만든 v34 를 가리켜 START_PATROL 이 NAVIGATION_MAP_MISMATCH 로
        # 거부됐다. 매핑 직후 그 지도로 순찰하는 것이 시연 흐름 전체다.
        identity=_current_navigation_identity,
        default_acceptance_radius_m=float(
            os.getenv("ROKI_WAYPOINT_ACCEPTANCE_RADIUS_M", "0.30")
        ),
        map_metadata_validator=_validate_backend_map_metadata_against_local,
    )


def _validate_backend_map_metadata_against_local(map_config: Any) -> None:
    """Bind Backend pixel/world metadata to the exact local Nav2 map bundle."""

    from aiot_robot.navigation_config import NavigationConfigError
    from navigation.map_metadata import load_map_metadata

    raw_map_path = os.getenv("ROKI_MAP_YAML", "").strip()
    map_path = Path(raw_map_path)
    if not raw_map_path or not map_path.is_absolute() or not map_path.is_file():
        raise NavigationConfigError("NAVIGATION_MAP_METADATA_MISMATCH")
    try:
        local = load_map_metadata(map_path)
        # Backend DECIMAL scales intentionally round the uploaded ROS YAML:
        # resolution(6,4), origin x/y(10,3), yaw(6,2). Accept at most one
        # half-unit in the stored scale, plus floating-point epsilon.
        numeric_pairs = (
            ("resolution", local.resolution_m, 5e-5 + 1e-12),
            ("originX", local.origin_x, 5e-4 + 1e-12),
            ("originY", local.origin_y, 5e-4 + 1e-12),
            ("originYaw", local.origin_yaw_rad, 5e-3 + 1e-12),
        )
        for key, local_value, absolute_tolerance in numeric_pairs:
            if not math.isclose(
                float(map_config[key]),
                float(local_value),
                rel_tol=0.0,
                abs_tol=absolute_tolerance,
            ):
                raise NavigationConfigError(
                    "NAVIGATION_MAP_METADATA_MISMATCH"
                )
        if (
            int(map_config["width"]) != local.width_px
            or int(map_config["height"]) != local.height_px
        ):
            raise NavigationConfigError("NAVIGATION_MAP_METADATA_MISMATCH")
    except NavigationConfigError:
        raise
    except Exception as exc:
        raise NavigationConfigError(
            "NAVIGATION_MAP_METADATA_MISMATCH"
        ) from exc


def _build_mapping_runtime(
    runtime: Any,
    runtime_service: Any,
    state_store: Any,
    settings: Any,
) -> Any:
    """Build a dormant gamepad mapper; the device opens only on START_MAPPING."""

    from aiot_robot.mapping_artifacts import MapExportSettings, SlamMapExporter
    from control.manual_drive_controller import (
        ManualDriveController,
        ManualDriveSettings,
    )
    from integration.linux_gamepad_input import GamepadSettings, LinuxGamepadInput
    from integration.localization_mode import (
        DockPose,
        LocalizationModeController,
        RosLocalizationModeTransport,
    )
    from integration.map_activation import (
        CurrentMapActivator,
        MapActivationSettings,
    )
    from integration.mapping_runtime import (
        ManualMappingRuntime,
        MappingRuntimeSettings,
    )
    from integration.slam_session_control import RosSlamSessionControl

    drive_controller = ManualDriveController(
        runtime=runtime,
        state_store=state_store,
        settings=ManualDriveSettings(
            forward_target_pwm=int(os.getenv("ROKI_MAPPING_FORWARD_PWM", "45")),
            reverse_target_pwm=int(os.getenv("ROKI_MAPPING_REVERSE_PWM", "45")),
            drive_pulse_sec=float(os.getenv("ROKI_MAPPING_DRIVE_PULSE_SEC", "0.2")),
            steering_center_deg=int(
                os.getenv("ROKI_MAPPING_STEERING_CENTER_DEG", "80")
            ),
            steering_min_deg=int(os.getenv("ROKI_MAPPING_STEERING_MIN_DEG", "60")),
            steering_max_deg=int(os.getenv("ROKI_MAPPING_STEERING_MAX_DEG", "100")),
            steering_step_deg=int(os.getenv("ROKI_MAPPING_STEERING_STEP_DEG", "2")),
            steering_pulse_sec=float(
                os.getenv("ROKI_MAPPING_STEERING_PULSE_SEC", "0.2")
            ),
            # LiDAR obstacles are map input in this explicit manual mode. The
            # operator and deadman switch own motion; runtime hardware safety
            # and ESP32 watchdog remain enforced below this controller.
            require_clear_path=False,
        ),
    )
    gamepad_settings = GamepadSettings(
        device_path=os.getenv("ROKI_MAPPING_GAMEPAD_DEVICE", "/dev/input/js0"),
        steering_axis=int(os.getenv("ROKI_MAPPING_GAMEPAD_STEERING_AXIS", "0")),
        throttle_axis=int(os.getenv("ROKI_MAPPING_GAMEPAD_THROTTLE_AXIS", "1")),
        deadman_button=int(os.getenv("ROKI_MAPPING_GAMEPAD_DEADMAN_BUTTON", "4")),
        deadman_required=_environment_enabled(
            "ROKI_MAPPING_GAMEPAD_DEADMAN_REQUIRED",
            True,
        ),
        stop_button=int(os.getenv("ROKI_MAPPING_GAMEPAD_STOP_BUTTON", "1")),
        finish_button_a=int(os.getenv("ROKI_MAPPING_GAMEPAD_FINISH_BUTTON_A", "6")),
        finish_button_b=int(os.getenv("ROKI_MAPPING_GAMEPAD_FINISH_BUTTON_B", "7")),
        deadzone=float(os.getenv("ROKI_MAPPING_GAMEPAD_DEADZONE", "0.35")),
        finish_hold_sec=float(os.getenv("ROKI_MAPPING_FINISH_HOLD_SEC", "2.0")),
        loop_interval_sec=float(os.getenv("ROKI_MAPPING_GAMEPAD_LOOP_SEC", "0.05")),
        reconnect_interval_sec=float(
            os.getenv("ROKI_MAPPING_GAMEPAD_RECONNECT_SEC", "1.0")
        ),
        input_lease_sec=float(
            os.getenv("ROKI_MAPPING_GAMEPAD_INPUT_LEASE_SEC", "0")
        ),
    )
    holder: dict[str, Any] = {}
    if _environment_enabled("AIOT_MAPPING_GAMEPAD_ENABLED", True):
        gamepad_input = LinuxGamepadInput(
            drive_controller,
            settings=gamepad_settings,
            finish_callback=lambda: holder["mapping"].finish(),
        )
    else:
        gamepad_input = _NoOpMappingInput()
    # 매핑<->순찰 전환. 예전에는 env 파일에 모드를 적고 서비스를 재시작했다.
    # 이제 slam_toolbox 서비스 호출이라 프로세스가 살아 있는 채로 바뀐다.
    localization_transport = RosLocalizationModeTransport()
    localization_transport.start()
    localization_controller = LocalizationModeController(
        localization_transport,
        # 포즈그래프를 불러올 때 줄 초기 추정값. 규약은 웨이포인트 1 = 도킹
        # 지점 = 매핑 시작점 = map (0,0,0) 이다. 이 값들은 전에 AMCL 의
        # set_initial_pose 로 갔는데, AMCL 이 사라지면서 갈 곳을 잃었다가
        # 여기로 온다 -- 용도는 처음부터 "도킹 지점이 어디인가"였다.
        dock_pose=DockPose(
            x=float(os.getenv("ROKI_INITIAL_POSE_X_M", "0") or 0),
            y=float(os.getenv("ROKI_INITIAL_POSE_Y_M", "0") or 0),
            theta=float(os.getenv("ROKI_INITIAL_POSE_YAW_RAD", "0") or 0),
        ),
        report=print,
    )

    slam_session = RosSlamSessionControl(
        reset_service=os.getenv("AIOT_SLAM_RESET_SERVICE", "/slam_toolbox/reset"),
        # slam 이 실제로 소비하는 토픽을 관측한다. 이름에 SLAM_SCAN 을 남기면
        # 다음 사람이 /slam_scan 을 넣을 유인이 생기는데, 그 토픽은 이제
        # 아무도 발행하지 않는다 -- 넣는 순간 first_scan_after() 가 영원히
        # None 이 되어 wait_for_fresh_map 과 wait_for_localization_ready 가
        # 조용히 항상 실패한다.
        scan_topic=os.getenv("AIOT_SLAM_OBSERVE_SCAN_TOPIC", "/scan"),
        map_topic=os.getenv("AIOT_SLAM_MAP_TOPIC", "/map"),
        map_frame=os.getenv("AIOT_SLAM_MAP_FRAME", "map"),
        odom_frame=os.getenv("AIOT_SLAM_ODOM_FRAME", "odom"),
        discovery_timeout_sec=float(
            os.getenv("AIOT_SLAM_SESSION_DISCOVERY_TIMEOUT_SEC", "15")
        ),
        service_timeout_sec=float(
            os.getenv("AIOT_SLAM_SESSION_SERVICE_TIMEOUT_SEC", "15")
        ),
    )
    mapping_runtime = ManualMappingRuntime(
        runtime_service=runtime_service,
        state_store=state_store,
        drive_controller=drive_controller,
        gamepad_input=gamepad_input,
        map_exporter=SlamMapExporter(
            MapExportSettings(
                Path(os.getenv("AIOT_MAPPING_OUTPUT_DIR", "/var/lib/aiot/maps")),
                timeout_seconds=float(
                    os.getenv("AIOT_MAPPING_EXPORT_TIMEOUT_SEC", "30")
                ),
                serialize_pose_graph=_environment_enabled(
                    "AIOT_MAPPING_SERIALIZE_POSE_GRAPH", True
                ),
            )
        ),
        map_activator=CurrentMapActivator(
            MapActivationSettings(
                maps_directory=Path(
                    os.getenv(
                        "AIOT_ACTIVE_MAP_DIR",
                        "/var/lib/aiot/maps/active",
                    )
                ),
                environment_file=Path(
                    os.getenv(
                        "AIOT_ACTIVE_MAP_ENV_FILE",
                        "/var/lib/aiot/config/current-map.env",
                    )
                ),
            )
        ),
        localization=localization_controller,
        slam_session=slam_session,
        settings=MappingRuntimeSettings(
            backend_base_url=os.getenv(
                "AIOT_BACKEND_BASE_URL", "https://i15e103.p.ssafy.io"
            ),
            backend_token_file=Path(settings.service_token_file),
            backend_timeout_sec=float(os.getenv("AIOT_BACKEND_TIMEOUT_SEC", "10")),
            upload_retry_initial_sec=float(
                os.getenv("AIOT_MAPPING_UPLOAD_RETRY_INITIAL_SEC", "2")
            ),
            upload_retry_max_sec=float(
                os.getenv("AIOT_MAPPING_UPLOAD_RETRY_MAX_SEC", "30")
            ),
            fresh_map_timeout_sec=float(
                os.getenv("AIOT_MAPPING_FRESH_MAP_TIMEOUT_SEC", "30")
            ),
        ),
    )
    holder["mapping"] = mapping_runtime
    return mapping_runtime


def _build_mapping_visualizer(mapping_runtime: Any) -> Any:
    """Build an optional read-only view of the existing mapping lifecycle."""

    from aiot_robot.mapping_visualizer import (
        MappingVisualizer,
        MappingVisualizerSettings,
    )

    settings = MappingVisualizerSettings(
        bind=os.getenv("AIOT_MAPPING_MJPEG_BIND", "127.0.0.1"),
        port=int(os.getenv("AIOT_MAPPING_MJPEG_PORT", "8091")),
        output_size_px=int(os.getenv("AIOT_MAPPING_MJPEG_SIZE_PX", "800")),
        maximum_fps=float(os.getenv("AIOT_MAPPING_MJPEG_MAX_FPS", "4")),
        jpeg_quality=int(os.getenv("AIOT_MAPPING_MJPEG_QUALITY", "75")),
        inactive_fps=float(os.getenv("AIOT_MAPPING_MJPEG_INACTIVE_FPS", "1")),
        map_topic=os.getenv("AIOT_MAPPING_MAP_TOPIC", "/map"),
        scan_topic=os.getenv("AIOT_MAPPING_SCAN_TOPIC", "/scan"),
        map_frame=os.getenv("ROKI_MAP_FRAME", "map"),
        robot_frame=os.getenv("ROKI_BASE_FRAME", "base_link"),
    )
    return MappingVisualizer(
        mapping_active=lambda: bool(mapping_runtime.motion_active),
        settings=settings,
    )


def create_integrated_application(
    *,
    final_runtime: Any | None = None,
    pose_bridge: Any | None = None,
    lidar_health_bridge: Any | None = None,
    start_serial_runtime: bool = True,
    navigation_service: Any | None = None,
    navigation_provider: Any | None = None,
    local_navigation_fallback_enabled: bool = False,
    navigation_mode: str = "encoder_limited",
    operational_ai: bool = False,
    ai_controller: Any | None = None,
    event_worker: Any | None = None,
    deployment_guard: Any | None = None,
    manual_demo: bool = False,
    manual_controller: Any | None = None,
    keyboard_input: Any | None = None,
    mapping_runtime: Any | None = None,
    allow_legacy_direct_patrol: bool = True,
) -> Any:
    """Compose all production components around exactly one RobotRuntime."""

    build_default_runtime = final_runtime is None
    if final_runtime is None:
        runtime, default_pose_bridge, default_lidar_bridge = _build_final_components()
        pose_bridge = pose_bridge or default_pose_bridge
        lidar_health_bridge = lidar_health_bridge or default_lidar_bridge
    else:
        runtime = final_runtime

    from aiot_robot.deployment_guard import PatrolDeploymentGuard
    from aiot_robot.event_delivery import DetectionRecorder, EventDeliveryWorker
    from aiot_robot.outbox import DetectionOutbox
    from backend_config.settings import load_settings
    from integration.runtime_state_backend_adapter import FinalRuntimeService
    from backend_mqtt.client import MqttClient
    from backend_mqtt.command_handler import PatrolCommandHandler
    from backend_mqtt.publisher import RokiPublisherApplication
    from pipeline.patrol_pipeline import PatrolPipelineRunner

    settings = load_settings()
    state_store = runtime.state_store
    manual_enabled = (
        manual_demo
        or manual_controller is not None
        or keyboard_input is not None
    )
    if not manual_enabled and navigation_service is not None and navigation_mode != "nav2":
        raise RuntimeError(
            "DEMO_NAV2_REQUIRED: fixed-map navigation cannot use encoder progress"
        )
    if (
        not manual_enabled
        and navigation_mode == "nav2"
        and navigation_service is None
        and navigation_provider is None
    ):
        raise RuntimeError("NAV2_ROUTE_REQUIRED: validated navigation service is missing")
    if manual_demo and manual_controller is None and keyboard_input is None:
        manual_controller, keyboard_input = _build_manual_demo_components(runtime)
    service_holder: dict[str, Any] = {}
    # 매핑 세션은 순찰과 같은 cmd_vel 스트림을 쓴다. 어느 게이트로 보낼지는
    # 실행 중에 정해지므로, 순찰 브리지의 라우터가 이 홀더를 통해 매핑 싱크를
    # 찾는다. 매핑 런타임은 아래에서 만들어지므로 지연 해석이다.
    mapping_runtime_holder: dict[str, Any] = {}
    mapping_sink_holder: dict[str, Any] = {}
    navigation_driver = (
        _build_nav2_driver(service_holder, mapping_sink_holder)
        if (
            navigation_mode == "nav2"
            and not manual_enabled
            and (navigation_service is not None or navigation_provider is not None)
        )
        else None
    )
    # Autonomous mapping has no route and therefore no patrol to authorise
    # motion, but Nav2 is still driving: the frontier explorer supplies the
    # goals. Build the same cmd_vel bridge and route its output through the
    # mapping-session gate instead of the patrol gate. The mapping runtime is
    # created further down, so the gate resolves it lazily.
    if not manual_enabled and _environment_enabled("AIOT_MAPPING_AUTONOMOUS", False):
        mapping_sink_holder["sink"] = build_mapping_motion_sink(
            runtime, mapping_runtime_holder
        )
    # 순찰 브리지가 없을 때만 매핑 전용 브리지를 만든다. 아직 지도가 없어
    # 순찰 내비게이션이 성립하지 않는 첫 매핑이 그런 경우다. 순찰 브리지가
    # 있으면 그쪽 라우터가 위 싱크로 보내므로 구독자를 둘로 만들지 않는다 --
    # 둘이면 같은 cmd_vel 을 놓고 서로 정지시킨다.
    mapping_motion_bridge = (
        _build_mapping_nav2_bridge(runtime, mapping_runtime_holder)
        if (
            navigation_driver is None
            and not manual_enabled
            and _environment_enabled("AIOT_MAPPING_AUTONOMOUS", False)
        )
        else None
    )
    runtime_service = FinalRuntimeService(
        runtime,
        patrol_drive_speed_pwm=settings.patrol_drive_speed_pwm,
        patrol_steering_degrees=settings.patrol_steering_degrees,
        navigation_service=None if manual_enabled else navigation_service,
        navigation_provider=None if manual_enabled else navigation_provider,
        local_navigation_fallback_enabled=(
            False if manual_enabled else local_navigation_fallback_enabled
        ),
        navigation_start_x_m=float(os.getenv("ROKI_ROUTE_START_X_M", "1.0")),
        navigation_start_y_m=float(os.getenv("ROKI_ROUTE_START_Y_M", "2.5")),
        navigation_maximum_travel_m=float(
            os.getenv("ROKI_ROUTE_MAXIMUM_TRAVEL_M", "0.70")
        ),
        encoder_fallback_enabled=settings.encoder_fallback_enabled,
        navigation_driver=navigation_driver,
        deployment_guard=deployment_guard
        or PatrolDeploymentGuard(
            os.getenv(
                "AIOT_PATROL_DEPLOY_LOCK_FILE",
                "/var/lib/aiot/state/patrol-deploy.lock",
            )
        ),
        manual_controller=manual_controller,
        keyboard_input=keyboard_input,
        allow_legacy_direct_patrol=allow_legacy_direct_patrol,
    )
    service_holder["service"] = runtime_service
    if mapping_runtime is None and build_default_runtime:
        mapping_runtime = _build_mapping_runtime(
            runtime,
            runtime_service,
            state_store,
            settings,
        )
    if mapping_runtime is not None:
        runtime_service.set_mapping_runtime(mapping_runtime)
        mapping_runtime_holder["mapping"] = mapping_runtime
    if lidar_health_bridge is not None:
        set_obstacle_activity_check = getattr(
            lidar_health_bridge,
            "set_obstacle_activity_check",
            None,
        )
        if callable(set_obstacle_activity_check):
            set_obstacle_activity_check(
                runtime_service.is_obstacle_detection_active
            )
        # obstacle_sink(pause)의 대칭짝. Nav2는 장애물 abort 시 순찰을 이쪽에
        # 넘기고 clear-detect 루프가 돌려주기를 기다리는데(RosNav2Bridge.
        # _hold_for_obstacle) 그 호출자가 없어서 _paused가 영구히 True로 남고
        # 이후 모든 cmd_vel이 MOTION_INTERLOCK으로 버려졌다.
        set_obstacle_clear_sink = getattr(
            lidar_health_bridge,
            "set_obstacle_clear_sink",
            None,
        )
        if callable(set_obstacle_clear_sink):
            set_obstacle_clear_sink(runtime_service.resume_patrol)

    runtime_components: list[Any] = []
    readiness_checks: list[Any] = []
    slam_session = getattr(mapping_runtime, "slam_session", None)
    if slam_session is not None:
        runtime_components.append(slam_session)
    if mapping_motion_bridge is not None:
        # Started and stopped with the rest of the runtime so the cmd_vel
        # subscription exists for the whole mapping session.
        runtime_components.append(mapping_motion_bridge)
    if (
        mapping_runtime is not None
        and _environment_enabled("AIOT_MAPPING_MJPEG_ENABLED", False)
    ):
        runtime_components.append(_build_mapping_visualizer(mapping_runtime))
    if operational_ai:
        from aiot_robot.runtime_ai import RosAiCoordinator

        outbox = DetectionOutbox(
            os.getenv("AIOT_EVENT_OUTBOX_DIR", "/var/lib/aiot/outbox")
        )
        emergency_stop_enabled = _environment_enabled(
            "AIOT_EMERGENCY_STOP_ENABLED", False
        )

        def emergency_stop(event: Any) -> None:
            stopped = runtime_service.pause_patrol("AI_EMERGENCY")
            print(
                "[AI EMERGENCY] stop requested "
                f"eventId={getattr(event, 'event_id', None)} "
                f"confidence={getattr(event, 'confidence', None)} "
                f"applied={stopped}"
            )

        recorder = DetectionRecorder(
            outbox,
            state_store,
            vehicle_range_source=lidar_health_bridge,
            camera_yaw_deg=float(
                os.getenv(
                    "AIOT_DETECTION_CAMERA_YAW_DEG",
                    os.getenv("AIOT_VEHICLE_CAMERA_YAW_DEG", "0"),
                )
            ),
            camera_horizontal_fov_deg=float(
                os.getenv("AIOT_DETECTION_CAMERA_HORIZONTAL_FOV_DEG", "48")
            ),
            lidar_forward_center_angle_deg=float(
                os.getenv(
                    "AIOT_LIDAR_FORWARD_CENTER_ANGLE_DEG",
                    os.getenv("AIOT_VEHICLE_LIDAR_CENTER_ANGLE_DEG", "0"),
                )
            ),
            emergency_stop_sink=(
                emergency_stop if emergency_stop_enabled else None
            ),
        )
        runtime_service.set_scan_context_listener(recorder.set_scan_context)
        ai_controller = ai_controller or RosAiCoordinator(recorder, state_store)
        event_worker = event_worker or EventDeliveryWorker(
            outbox,
            token_file=settings.service_token_file,
        )
        runtime_components.extend((ai_controller, event_worker))
        readiness_checks.append(event_worker.readiness_for_new_patrol)
    elif ai_controller is not None:
        runtime_components.append(ai_controller)
    if event_worker is not None and event_worker not in runtime_components:
        runtime_components.append(event_worker)
        readiness_checks.append(event_worker.readiness_for_new_patrol)

    mqtt_client = MqttClient(settings)
    pipeline_runner = PatrolPipelineRunner(
        source_a=settings.pipeline_source_a,
        source_b=settings.pipeline_source_b,
        extra_args=settings.pipeline_extra_args,
        start_grace_seconds=settings.pipeline_start_grace_seconds,
    )
    def prepare_patrol_localization() -> tuple[bool, str]:
        """순찰 시작 직전에 활성 지도의 포즈그래프가 적재돼 있음을 보장한다.

        매핑 완료 시점의 인계는 실패할 수 있고, 재부팅한 뒤에는 아예 일어나지
        않는다 -- 그 부팅에는 매핑이 없었으므로 부르는 쪽이 없다. 그래서
        지금까지는 재부팅 뒤 바로 순찰하면 slam_toolbox 가 빈 매핑 상태로
        남았고, 순찰은 지도 없이 출발했다.

        디렉터리를 env 파일에서 다시 읽는 것도 같은 이유다. 방금 그린 지도는
        current-map.env 에만 있고 이 프로세스의 os.environ 에는 없다.
        """

        return _prepare_patrol_localization(
            mapping_runtime,
            runtime_service.navigation_route,
            require_start_anchor=navigation_driver is not None,
        )

    command_handler = PatrolCommandHandler(
        settings=settings,
        mqtt_client=mqtt_client,
        serial_reader=runtime_service,
        state_store=state_store,
        pipeline_runner=pipeline_runner,
        pipeline_enabled=False,
        ai_controller=ai_controller,
        mapping_runtime=mapping_runtime,
        readiness_checks=readiness_checks,
        localization_preparer=prepare_patrol_localization,
    )
    if mapping_runtime is not None:
        mapping_runtime.set_failure_listener(command_handler.on_runtime_failure)
    application = RokiPublisherApplication(
        settings=settings,
        serial_reader=runtime_service,
        state_store=state_store,
        mqtt_client=mqtt_client,
        command_handler=command_handler,
        pipeline_runner=pipeline_runner,
        pose_source=pose_bridge,
        lidar_health_source=lidar_health_bridge,
        # A fresh AMCL/TF pose is useful while IDLE too: the dashboard must
        # reflect the robot at the marked dock before START_PATROL.  The pose
        # bridge already rejects missing or stale transforms, so patrol state
        # is not an additional validity condition.
        # 매핑 중에는 백엔드로 가는 장애물 알림만 비운다. 그리는 중인 벽이
        # 순찰 위험 알림이 되면 안 되기 때문이다. 젯슨 내부의 실제 스캔과
        # 인터락은 그대로 살아 있다.
        #
        # 예전에는 AIOT_ROS_MODE 도 함께 봤다. 그 변수는 부팅 시 어느 노드
        # 집합이 떴는지를 뜻했으므로, 세션이 없어도 매핑 스택이면 알림이
        # 꺼졌다. 이제 두 운행이 같은 스택을 쓰니 그 대리 판단이 성립하지
        # 않고, 판단 기준은 실제 세션 하나로 충분하다.
        obstacle_alert_activity_check=lambda: not (
            mapping_runtime is not None and mapping_runtime.active
        ),
        runtime_components=tuple(runtime_components),
        start_serial_reader=start_serial_runtime,
    )
    command_handler.set_flush_telemetry(application.publish_now)
    runtime_service.set_destination_listener(command_handler.on_destination_reached)
    runtime_service.set_fault_listener(command_handler.on_runtime_failure)
    return application


def preflight(route_path: str | Path | None = None) -> dict[str, Any]:
    """Validate configuration without MQTT, ROS nodes or serial access."""

    from backend_config.settings import load_settings

    _validate_import_namespaces()
    settings = load_settings()
    selected_route = _selected_route_path(route_path)
    mapping_available = True
    mapping_requested = _no_active_map()
    legacy_mapping_only = _legacy_mapping_only_selected(settings, selected_route)
    config_source = _navigation_config_source()
    local_fallback = _environment_enabled(
        "AIOT_NAVIGATION_LOCAL_FALLBACK_ENABLED", False
    )
    navigation = None
    if mapping_requested or legacy_mapping_only:
        mode = "mapping"
    elif config_source == "local":
        if not selected_route.is_file():
            raise RuntimeError(f"waypoint route file is missing: {selected_route}")
        mode = _navigation_mode(settings)
        navigation = _build_navigation_service(
            selected_route,
            encoder_limited=mode == "encoder_limited",
        )
    else:
        _require_legacy_route_when_mapping_disabled(settings, selected_route)
        mode = _navigation_mode(settings)
        _build_backend_navigation_provider(settings)
        if local_fallback:
            if not selected_route.is_file():
                raise RuntimeError(
                    "LOCAL_ROUTE_FALLBACK_MISSING: "
                    f"waypoint route file is missing: {selected_route}"
                )
            navigation = _build_navigation_service(
                selected_route,
                encoder_limited=False,
            )
    if mode == "nav2":
        holder: dict[str, Any] = {"service": None}
        _build_nav2_driver(holder)
    return {
        "robotKey": settings.robot_key,
        "navigationMode": mode,
        "routeConfigured": navigation is not None,
        "routeId": navigation.route.route_id if navigation is not None else None,
        "waypoints": len(navigation.route.waypoints) if navigation is not None else 0,
        "mapValidated": navigation is not None,
        "mappingAvailable": mapping_available,
        "mappingModeRequested": mapping_requested,
        "legacyMappingOnlySelected": legacy_mapping_only,
        "navigationConfigSource": config_source,
        "localRouteFallbackEnabled": local_fallback,
        "navigationProviderConfigured": (
            config_source == "backend" and mode != "mapping"
        ),
        "backendNavigationFetchDeferred": (
            config_source == "backend" and mode != "mapping"
        ),
        "localMapSafetyValidationDeferred": (
            config_source == "backend" and navigation is None and mode != "mapping"
        ),
        "aiRequired": settings.ai_required_for_patrol,
        "lidarRequired": settings.lidar_required_for_patrol,
        "eventDeliveryOwner": _event_delivery_owner(),
        "serialAccessed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pose-only",
        action="store_true",
        help="start telemetry without opening the ESP32 serial port",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate config and route without opening MQTT, ROS or serial",
    )
    parser.add_argument(
        "--manual-keyboard",
        action="store_true",
        help=(
            "temporary foreground demo: MQTT START enables AI, then "
            "W/A/S/D controls short motion pulses"
        ),
    )
    parser.add_argument("--route", default=None)
    args = parser.parse_args(argv)
    if args.manual_keyboard and args.pose_only:
        parser.error("--manual-keyboard cannot be combined with --pose-only")
    if args.manual_keyboard and args.check:
        parser.error("--manual-keyboard cannot be combined with --check")
    if args.manual_keyboard and not sys.stdin.isatty():
        parser.error("--manual-keyboard requires a foreground TTY")
    if args.check:
        import json

        print(json.dumps(preflight(args.route), sort_keys=True))
        return 0

    from backend_config.settings import load_settings

    settings = load_settings()
    mode = "manual" if args.manual_keyboard else "mapping"
    navigation = None
    navigation_provider = None
    local_navigation_fallback_enabled = False
    _event_delivery_owner()
    if not args.manual_keyboard:
        selected_route = _selected_route_path(args.route)
        if _no_active_map() or _legacy_mapping_only_selected(
            settings, selected_route
        ):
            logging.getLogger(__name__).info(
                "Mapping-only mode selected; patrol route validation is deferred"
            )
        elif _navigation_config_source() == "local":
            if not selected_route.is_file():
                raise RuntimeError(f"waypoint route file is missing: {selected_route}")
            mode = _navigation_mode(settings)
            navigation = _build_navigation_service(
                selected_route,
                encoder_limited=mode == "encoder_limited",
            )
        else:
            _require_legacy_route_when_mapping_disabled(settings, selected_route)
            mode = _navigation_mode(settings)
            navigation_provider = _build_backend_navigation_provider(settings)
            local_navigation_fallback_enabled = _environment_enabled(
                "AIOT_NAVIGATION_LOCAL_FALLBACK_ENABLED", False
            )
            if local_navigation_fallback_enabled:
                if not selected_route.is_file():
                    raise RuntimeError(
                        "LOCAL_ROUTE_FALLBACK_MISSING: "
                        f"waypoint route file is missing: {selected_route}"
                    )
                navigation = _build_navigation_service(
                    selected_route,
                    encoder_limited=False,
                )
    application = create_integrated_application(
        start_serial_runtime=not args.pose_only,
        navigation_service=navigation,
        navigation_provider=navigation_provider,
        local_navigation_fallback_enabled=local_navigation_fallback_enabled,
        navigation_mode=mode,
        operational_ai=True,
        manual_demo=args.manual_keyboard,
        allow_legacy_direct_patrol=False,
    )

    def stop_handler(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    try:
        application.start()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        logging.getLogger(__name__).exception("Integrated Robot runtime failed")
        return 1
    finally:
        application.stop()


if __name__ == "__main__":
    raise SystemExit(main())
