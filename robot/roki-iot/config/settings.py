"""
한바퀴 IoT 애플리케이션 설정 모듈.

이 파일은 다음 역할만 담당한다.

1. .env / 환경변수 읽기
2. MQTT 연결 설정 제공
3. 로봇별 MQTT 토픽 생성
4. 발행 주기 제공

센서값을 읽거나 MQTT 메시지를 발행하지 않는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# roki-iot/.env 를 프로젝트 루트 기준으로 로드한다.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")


def read_boolean_environment(
    name: str,
    default: bool,
) -> bool:
    """
    환경변수 문자열을 bool 값으로 변환한다.

    허용하는 true 값:
    - true
    - 1
    - yes
    - on
    """

    default_text = "true" if default else "false"
    value = os.getenv(name, default_text)

    return value.strip().lower() in {
        "true",
        "1",
        "yes",
        "on",
    }


@dataclass(frozen=True)
class AppSettings:
    """
    애플리케이션 실행 설정.

    frozen=True를 사용해 실행 중 설정값이
    실수로 변경되지 않도록 한다.
    """

    schema_version: int
    robot_key: str

    mqtt_host: str
    mqtt_port: int
    mqtt_username: str | None
    mqtt_password: str | None
    mqtt_use_tls: bool

    pose_publish_interval_seconds: float
    status_publish_interval_seconds: float

    pipeline_source_a: str
    pipeline_source_b: str
    pipeline_extra_args: str
    pipeline_start_grace_seconds: float
    pipeline_enabled: bool

    ai_required_for_patrol: bool
    lidar_required_for_patrol: bool
    service_token_file: str
    command_cache_file: str
    navigation_mode: str
    encoder_fallback_enabled: bool
    obstacle_clear_hold_seconds: float

    patrol_drive_speed_pwm: int
    patrol_steering_degrees: int

    def __post_init__(self) -> None:
        if not 1 <= self.schema_version <= 1:
            raise ValueError("SCHEMA_VERSION must be 1")
        if not 0 <= self.patrol_drive_speed_pwm <= 255:
            raise ValueError(
                "PATROL_DRIVE_SPEED_PWM must be between 0 and 255"
            )
        if not 60 <= self.patrol_steering_degrees <= 100:
            raise ValueError(
                "PATROL_STEERING_DEGREES must be between 60 and 100"
            )
        if self.navigation_mode not in {"auto", "nav2", "encoder_limited"}:
            raise ValueError(
                "ROKI_NAVIGATION_MODE must be auto, nav2 or encoder_limited"
            )
        if self.obstacle_clear_hold_seconds < 0:
            raise ValueError(
                "OBSTACLE_CLEAR_HOLD_SECONDS must be non-negative"
            )

    @property
    def mqtt_client_id(self) -> str:
        """Jetson MQTT 클라이언트 식별자를 반환한다."""

        return f"{self.robot_key}-jetson"

    @property
    def pose_topic(self) -> str:
        """로봇 Pose 발행 토픽을 반환한다."""

        return (
            "hanbakwi/v1/robots/"
            f"{self.robot_key}/pose"
        )

    @property
    def status_topic(self) -> str:
        """로봇 상태 발행 토픽을 반환한다."""

        return (
            "hanbakwi/v1/robots/"
            f"{self.robot_key}/status"
        )

    @property
    def command_topic(self) -> str:
        """로봇 명령 수신 토픽을 반환한다."""

        return (
            f"hanbakwi/v1/robots/{self.robot_key}/command"
        )

    @property
    def command_response_topic(self) -> str:
        """로봇 명령 응답 토픽을 반환한다."""

        return (
            f"hanbakwi/v1/robots/{self.robot_key}/command/ack"
        )


def load_settings() -> AppSettings:
    """
    환경변수에서 애플리케이션 설정을 생성한다.

    설정을 읽는 책임을 이 함수 한 곳으로 모아
    다른 모듈에서 os.getenv를 직접 호출하지 않게 한다.
    """

    return AppSettings(
        schema_version=int(
            os.getenv("SCHEMA_VERSION", "1")
        ),
        robot_key=os.getenv(
            "ROBOT_KEY",
            "ROKI-01",
        ),
        mqtt_host=os.getenv(
            "MQTT_HOST",
            "127.0.0.1",
        ),
        mqtt_port=int(
            os.getenv("MQTT_PORT", "1883")
        ),
        mqtt_username=os.getenv("MQTT_USERNAME"),
        mqtt_password=os.getenv("MQTT_PASSWORD"),
        mqtt_use_tls=read_boolean_environment(
            name="MQTT_USE_TLS",
            default=True,
        ),
        pose_publish_interval_seconds=float(
            os.getenv(
                "POSE_PUBLISH_INTERVAL_SECONDS",
                "1",
            )
        ),
        status_publish_interval_seconds=float(
            os.getenv(
                "STATUS_PUBLISH_INTERVAL_SECONDS",
                "5",
            )
        ),
        pipeline_source_a=os.getenv(
            "PIPELINE_SOURCE_A",
            "/dev/roki_camera_front",
        ),
        pipeline_source_b=os.getenv(
            "PIPELINE_SOURCE_B",
            "/dev/roki_camera_rear",
        ),
        pipeline_extra_args=os.getenv(
            "PIPELINE_EXTRA_ARGS",
            "",
        ),
        pipeline_start_grace_seconds=float(
            os.getenv(
                "PIPELINE_START_GRACE_SECONDS",
                "8",
            )
        ),
        pipeline_enabled=read_boolean_environment(
            name="PIPELINE_ENABLED",
            default=False,
        ),
        ai_required_for_patrol=read_boolean_environment(
            name="AIOT_AI_REQUIRED_FOR_PATROL",
            default=True,
        ),
        lidar_required_for_patrol=read_boolean_environment(
            name="AIOT_LIDAR_REQUIRED_FOR_PATROL",
            default=True,
        ),
        service_token_file=os.getenv(
            "AIOT_BACKEND_TOKEN_FILE",
            "/var/lib/aiot/secrets/robot-service-token",
        ),
        command_cache_file=os.getenv(
            "AIOT_COMMAND_CACHE_FILE",
            "/var/lib/aiot/state/command-cache.json",
        ),
        navigation_mode=os.getenv(
            "ROKI_NAVIGATION_MODE",
            "auto",
        ).strip().lower(),
        encoder_fallback_enabled=read_boolean_environment(
            name="ROKI_ENCODER_FALLBACK_ENABLED",
            default=True,
        ),
        obstacle_clear_hold_seconds=float(
            os.getenv("OBSTACLE_CLEAR_HOLD_SECONDS", "1.0")
        ),
        # PWM 45 is the lowest field-tested motion value. Steering 80 degrees
        # is the measured straight-ahead position.
        patrol_drive_speed_pwm=int(
            os.getenv(
                "PATROL_DRIVE_SPEED_PWM",
                "45",
            )
        ),
        patrol_steering_degrees=int(
            os.getenv(
                "PATROL_STEERING_DEGREES",
                "80",
            )
        ),
    )
