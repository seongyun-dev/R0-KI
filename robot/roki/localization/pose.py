"""Backend payload와 분리된 내부 Pose 모델."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PoseFrame(str, Enum):
    ODOM = "odom"
    MAP = "map"


class PoseSource(str, Enum):
    ENCODER_ODOM = "ENCODER_ODOM"
    RF2O_ODOM = "RF2O_ODOM"
    SLAM_MAP = "SLAM_MAP"
    LOCALIZATION_MAP = "LOCALIZATION_MAP"


@dataclass(frozen=True)
class PoseEstimate:
    """내부 계산용 SI 단위 Pose. heading은 radian이다."""

    x_m: float
    y_m: float
    heading_rad: float
    frame_id: PoseFrame
    source: PoseSource
    valid: bool
    timestamp: float
