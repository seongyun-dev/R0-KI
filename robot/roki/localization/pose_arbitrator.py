"""운영 MQTT에 노출할 map Pose 선택 정책."""

from __future__ import annotations

from localization.pose import PoseEstimate, PoseFrame, PoseSource


class PoseArbitrator:
    MAP_SOURCES = frozenset(
        (PoseSource.SLAM_MAP, PoseSource.LOCALIZATION_MAP)
    )

    def __init__(self, map_pose_timeout_sec: float | None) -> None:
        if map_pose_timeout_sec is not None and map_pose_timeout_sec <= 0:
            raise ValueError("map_pose_timeout_sec must be positive or None")
        self._map_pose_timeout_sec = map_pose_timeout_sec

    def select(
        self,
        *,
        map_pose: PoseEstimate | None,
        odom_pose: PoseEstimate | None,
        now: float,
    ) -> PoseEstimate | None:
        """Odom은 내부 보관만 하며 운영 최종 Pose로 선택하지 않는다."""

        del odom_pose
        timeout = self._map_pose_timeout_sec
        if map_pose is None or timeout is None:
            return None
        if not map_pose.valid or map_pose.frame_id is not PoseFrame.MAP:
            return None
        if map_pose.source not in self.MAP_SOURCES:
            return None
        age = now - map_pose.timestamp
        if age < 0 or age > timeout:
            return None
        return map_pose
