"""향후 ROS2 subscriber/TF listener가 호출할 framework-neutral 경계."""

from __future__ import annotations

import math

from localization.pose import PoseEstimate, PoseFrame, PoseSource


class RosPoseSourceAdapter:
    """ROS 메시지를 구독하거나 TF를 조회하지 않고 검증된 값을 모델로 변환한다."""

    @staticmethod
    def from_odom(
        *,
        x_m: float,
        y_m: float,
        heading_rad: float,
        timestamp: float,
        source: PoseSource = PoseSource.RF2O_ODOM,
    ) -> PoseEstimate:
        if source is not PoseSource.RF2O_ODOM:
            raise ValueError("odom input requires RF2O_ODOM source")
        return RosPoseSourceAdapter._build(
            x_m, y_m, heading_rad, PoseFrame.ODOM, source, timestamp
        )

    @staticmethod
    def from_map_to_base_link(
        *,
        x_m: float,
        y_m: float,
        heading_rad: float,
        timestamp: float,
        source: PoseSource,
    ) -> PoseEstimate:
        if source not in (PoseSource.SLAM_MAP, PoseSource.LOCALIZATION_MAP):
            raise ValueError("map input requires SLAM_MAP or LOCALIZATION_MAP")
        return RosPoseSourceAdapter._build(
            x_m, y_m, heading_rad, PoseFrame.MAP, source, timestamp
        )

    @staticmethod
    def _build(
        x_m: float,
        y_m: float,
        heading_rad: float,
        frame_id: PoseFrame,
        source: PoseSource,
        timestamp: float,
    ) -> PoseEstimate:
        values = (x_m, y_m, heading_rad, timestamp)
        valid = all(math.isfinite(value) for value in values) and timestamp >= 0
        return PoseEstimate(
            x_m,
            y_m,
            heading_rad,
            frame_id,
            source,
            valid,
            timestamp,
        )
