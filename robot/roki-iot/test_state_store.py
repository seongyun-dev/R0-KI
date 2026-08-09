from pprint import pprint

from backend_state.models import (
    HardwareState,
    ObstacleState,
    PoseState,
)
from backend_state.robot_state_store import RobotStateStore


def main() -> None:
    store = RobotStateStore()

    store.update_hardware(
        HardwareState(
            battery=82.5,
            motor="NORMAL",
            line_sensor="NORMAL",
        )
    )

    store.update_robot_state("PATROLLING")
    store.update_camera_status("NORMAL")
    store.update_lidar_status("NORMAL")

    store.update_pose(
        PoseState(
            x=3.42,
            y=7.18,
            heading=92.5,
        )
    )

    store.update_obstacle(
        ObstacleState(
            status="STOP",
            direction="FRONT",
            reason_message="전방 근접 장애물 감지",
        )
    )

    snapshot = store.get_snapshot()

    print("\n===== ROBOT STATE SNAPSHOT =====")
    pprint(snapshot)

    print("\n===== CHECK =====")
    print(f"state: {snapshot.status.state}")
    print(f"battery: {snapshot.status.battery}")
    print(f"motor: {snapshot.status.motor}")
    print(f"camera: {snapshot.status.camera}")
    print(f"lidar: {snapshot.status.lidar}")
    print(f"line_sensor: {snapshot.status.line_sensor}")
    print(f"obstacle: {snapshot.status.obstacle}")
    print(f"pose: {snapshot.pose}")


if __name__ == "__main__":
    main()
