import unittest

from control.motion_controller import MotionState
from safety.safety_controller import SafetyDecision
from serial_comm.protocol import (
    HardwareStatus,
    LineSensorStatus,
    MotorStatus,
    Odometry,
)
from state.robot_state import ObstacleState, PoseState, RobotStateStore


class RobotStateStoreTest(unittest.TestCase):
    def test_runtime_and_mqtt_views_share_one_store(self) -> None:
        store = RobotStateStore(map_pose_timeout_sec=1.0, clock=lambda: 10.0)
        hardware = HardwareStatus(
            battery_percent=74.5,
            motor=MotorStatus.NORMAL,
            line_sensor=LineSensorStatus.NORMAL,
        )
        odometry = Odometry(1, 100, 10, 11)
        motion = MotionState(10, 11, -1, None, None, None, None, None, None)

        store.update_hardware_status(hardware)
        store.update_odometry(odometry, motion)
        store.update_safety(SafetyDecision(True, "NONE"))
        store.update_robot_state("PATROLLING")
        store.update_camera_status("NORMAL")
        store.update_lidar_status("NORMAL")
        store.update_obstacle(ObstacleState("STOP", "FRONT", "blocked"))
        store.update_pose(PoseState(1.0, 2.0, 90.0))

        self.assertIs(store.snapshot().hardware_status, hardware)
        self.assertIs(store.snapshot().odometry, odometry)
        self.assertEqual(store.get_status().battery, 74.5)
        self.assertEqual(store.get_status().state, "PATROLLING")
        self.assertEqual(store.get_status().camera, "NORMAL")
        self.assertEqual(store.get_status().lidar, "NORMAL")
        self.assertEqual(store.get_status().obstacle.status, "STOP")
        self.assertEqual(store.get_pose(), PoseState(1.0, 2.0, 90.0))
        self.assertTrue(store.has_status_changed())

        store.mark_status_published()

        self.assertFalse(store.has_status_changed())

    def test_connection_reset_only_disconnects_esp32_fields(self) -> None:
        store = RobotStateStore()
        store.update_hardware_status(
            HardwareStatus(
                80.0,
                MotorStatus.NORMAL,
                LineSensorStatus.NORMAL,
            )
        )
        store.update_robot_state("PATROLLING")
        store.update_camera_status("NORMAL")

        store.reset_connection()

        self.assertIsNone(store.snapshot().hardware_status)
        status = store.get_status()
        self.assertIsNone(status.battery)
        self.assertEqual(status.motor, "DISCONNECTED")
        self.assertEqual(status.line_sensor, "DISCONNECTED")
        self.assertEqual(status.state, "PATROLLING")
        self.assertEqual(status.camera, "NORMAL")


if __name__ == "__main__":
    unittest.main()
