from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"


def load_yaml(filename: str) -> dict[str, Any]:
    """
    roki/config 디렉터리의 YAML 파일을 읽어 dict로 반환한다.
    """
    path = CONFIG_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise ValueError(f"YAML 최상위 구조는 객체여야 합니다: {path}")

    return data


def load_robot_config() -> dict[str, Any]:
    return load_yaml("robot.yaml")


def load_serial_config() -> dict[str, Any]:
    return load_yaml("serial.yaml")


def load_mqtt_config() -> dict[str, Any]:
    return load_yaml("mqtt.yaml")


def load_lidar_config() -> dict[str, Any]:
    return load_yaml("lidar.yaml")


def load_ai_config() -> dict[str, Any]:
    return load_yaml("ai.yaml")


def load_safety_config() -> dict[str, Any]:
    return load_yaml("safety.yaml")


def load_runtime_config() -> dict[str, Any]:
    return load_yaml("runtime.yaml")
