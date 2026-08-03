#!/usr/bin/env python3
"""RO-KI 운영 headless Runtime 진입점."""

from __future__ import annotations

import logging
import signal
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from common.config_loader import (
    load_robot_config,
    load_lidar_config,
    load_runtime_config,
    load_safety_config,
    load_serial_config,
)
from control.motion_controller import MotionController, MotionControllerSettings
from mission.mission_controller import MissionController
from localization.encoder_pose_estimator import (
    EncoderPoseEstimator,
    EncoderPoseEstimatorSettings,
)
from localization.ros_tf_pose_bridge import (
    RosTfPoseBridge,
    RosTfPoseBridgeSettings,
)
from runtime.robot_runtime import RobotRuntime, RuntimeSettings
from safety.safety_controller import SafetyController, SafetySettings
from safety.obstacle_guard import (
    FrontObstacleDetector,
    ObstacleDetectorSettings,
)
from sensors.ros_lidar_health_bridge import (
    RosLidarHealthBridge,
    RosLidarHealthSettings,
)
from serial_comm.protocol import ProtocolSettings
from serial_comm.serial_bridge import SerialBridge, SerialBridgeSettings
from state.robot_state import RobotStateStore


def _required(
    values: dict[str, object],
    key: str,
    config_name: str,
) -> object:
    if key not in values:
        raise ValueError(
            f"필수 설정이 없습니다: {config_name}.{key}"
        )
    return values[key]


def _positive_milliseconds_to_seconds(
    values: dict[str, object],
    key: str,
    config_name: str,
) -> float:
    raw_value = _required(values, key, config_name)
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise ValueError(
            f"{config_name}.{key}는 양수 millisecond 숫자여야 합니다"
        )
    milliseconds = float(raw_value)
    if milliseconds <= 0:
        raise ValueError(
            f"{config_name}.{key}는 0보다 커야 합니다"
        )
    return milliseconds / 1000.0


def build_safety_settings(
    safety_config: dict[str, object],
) -> SafetySettings:
    raw_safety = _required(safety_config, "safety", "safety.yaml")
    if not isinstance(raw_safety, dict):
        raise ValueError("safety.yaml.safety는 객체여야 합니다")
    low_battery = _required(
        raw_safety,
        "low_battery_percent",
        "safety.yaml.safety",
    )
    if (
        low_battery is not None
        and (
            isinstance(low_battery, bool)
            or not isinstance(low_battery, (int, float))
        )
    ):
        raise ValueError(
            "safety.yaml.safety.low_battery_percent는 "
            "0..100 숫자 또는 null이어야 합니다"
        )
    low_battery_percent = (
        None if low_battery is None else float(low_battery)
    )
    return SafetySettings(
        odometry_timeout_sec=_positive_milliseconds_to_seconds(
            raw_safety,
            "odometry_timeout_ms",
            "safety.yaml.safety",
        ),
        hardware_status_timeout_sec=_positive_milliseconds_to_seconds(
            raw_safety,
            "hardware_status_timeout_ms",
            "safety.yaml.safety",
        ),
        low_battery_percent=low_battery_percent,
    )


def build_localization_settings(
    robot_config: dict[str, object],
) -> RosTfPoseBridgeSettings:
    raw = _required(robot_config, "localization", "robot.yaml")
    if not isinstance(raw, dict):
        raise ValueError("robot.yaml.localization must be an object")

    def positive_number(key: str) -> float:
        value = _required(raw, key, "robot.yaml.localization")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"robot.yaml.localization.{key} must be a positive number"
            )
        result = float(value)
        if result <= 0:
            raise ValueError(
                f"robot.yaml.localization.{key} must be positive"
            )
        return result

    return RosTfPoseBridgeSettings(
        map_frame=str(_required(raw, "map_frame", "robot.yaml.localization")),
        base_frame=str(_required(raw, "base_frame", "robot.yaml.localization")),
        map_pose_timeout_sec=positive_number("map_pose_timeout_sec"),
        tf_poll_interval_sec=positive_number("tf_poll_interval_sec"),
    )


def build_runtime() -> RobotRuntime:
    robot = load_robot_config()
    serial_config = load_serial_config()
    safety_config = load_safety_config()
    runtime_config = load_runtime_config()
    control = robot["control"]
    odometry = robot["odometry"]
    serial_values = serial_config["serial"]
    device = serial_config["device"]
    runtime_values = runtime_config["runtime"]

    protocol = ProtocolSettings(
        speed_min=-int(control["speed_max"]),
        speed_max=int(control["speed_max"]),
        steering_min_deg=int(control["servo_min_deg"]),
        steering_max_deg=int(control["servo_max_deg"]),
        steering_center_deg=int(control["servo_center_deg"]),
    )
    bridge = SerialBridge(
        SerialBridgeSettings(
            port=str(serial_values["port"]),
            baudrate=int(serial_values["baudrate"]),
            read_timeout_sec=float(serial_values["timeout_sec"]),
            reconnect_interval_sec=float(serial_values["reconnect_interval_sec"]),
            allowed_port_prefixes=tuple(device["allowed_port_prefixes"]),
            preferred_vid=device["preferred_vid"],
            preferred_pid=device["preferred_pid"],
        )
    )
    motion = MotionController(
        MotionControllerSettings(
            wheel_diameter_m=float(odometry["wheel_diameter_m"]),
            encoder_ticks_per_revolution=odometry[
                "encoder_ticks_per_revolution"
            ],
            speed_min=control["speed_min"],
            speed_max=int(control["speed_max"]),
            speed_ramp_per_update=control["speed_ramp_per_update"],
            straight_correction_kp_deg_per_tick=control[
                "straight_correction_kp_deg_per_tick"
            ],
            maximum_straight_correction_deg=control[
                "maximum_straight_correction_deg"
            ],
            steering_center_deg=int(control["servo_center_deg"]),
            steering_min_deg=int(control["servo_min_deg"]),
            steering_max_deg=int(control["servo_max_deg"]),
        )
    )
    mission = MissionController(protocol.steering_center_deg)
    safety = SafetyController(build_safety_settings(safety_config))
    localization = build_localization_settings(robot)
    state_store = RobotStateStore(
        map_pose_timeout_sec=localization.map_pose_timeout_sec
    )
    return RobotRuntime(
        bridge=bridge,
        protocol_settings=protocol,
        mission=mission,
        motion=motion,
        safety=safety,
        state_store=state_store,
        encoder_pose_estimator=EncoderPoseEstimator(
            EncoderPoseEstimatorSettings(
                steering_center_command=protocol.steering_center_deg,
                # TODO(calibration): wheelbase와 command별 실제 wheel angle을
                # 실측하기 전에는 회전 odometry를 활성화하지 않는다.
                wheelbase_m=None,
                steering_angle_rad_by_command=None,
            )
        ),
        settings=RuntimeSettings(
            disconnected_poll_sec=float(
                runtime_values["disconnected_poll_sec"]
            )
        ),
    )


def build_ros_tf_pose_bridge(state_store: RobotStateStore) -> RosTfPoseBridge:
    """운영 config를 사용해 기존 Store에 연결되는 TF Bridge를 만든다."""

    settings = build_localization_settings(load_robot_config())
    return RosTfPoseBridge(state_store=state_store, settings=settings)


def build_ros_lidar_health_bridge(
    state_store: RobotStateStore,
) -> RosLidarHealthBridge:
    """기존 lidar config로 /scan freshness monitor를 생성한다."""

    config = load_lidar_config()
    raw = _required(config, "lidar", "lidar.yaml")
    if not isinstance(raw, dict):
        raise ValueError("lidar.yaml.lidar must be an object")
    timeout = _required(raw, "scan_timeout_sec", "lidar.yaml.lidar")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError(
            "lidar.yaml.lidar.scan_timeout_sec must be a positive number"
        )
    raw_obstacle = _required(config, "obstacle", "lidar.yaml")
    if not isinstance(raw_obstacle, dict):
        raise ValueError("lidar.yaml.obstacle must be an object")

    def obstacle_number(key: str) -> float:
        value = _required(raw_obstacle, key, "lidar.yaml.obstacle")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"lidar.yaml.obstacle.{key} must be a number"
            )
        return float(value)

    return RosLidarHealthBridge(
        state_store=state_store,
        settings=RosLidarHealthSettings(
            scan_topic=str(_required(raw, "scan_topic", "lidar.yaml.lidar")),
            scan_timeout_sec=float(timeout),
        ),
        obstacle_detector=FrontObstacleDetector(
            ObstacleDetectorSettings(
                front_angle_deg=obstacle_number("front_angle_deg"),
                stop_distance_m=obstacle_number("stop_distance_m"),
                clear_distance_m=obstacle_number("clear_distance_m"),
            )
        ),
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    runtime = build_runtime()

    def stop_handler(signum: int, _frame: object) -> None:
        logging.getLogger(__name__).info(
            "Signal received: %s", signal.Signals(signum).name
        )
        runtime.request_stop()

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    try:
        runtime.run_forever()
        return 0
    except Exception:
        logging.getLogger(__name__).exception("Runtime failed")
        runtime.request_stop()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
