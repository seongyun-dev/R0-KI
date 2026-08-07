from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from navigation.cmd_vel_adapter import AckermannCommandSettings
from navigation.route import parse_route
from navigation.ros_nav2_bridge import RosNav2Bridge, RosNav2BridgeSettings


class ManualTimer:
    def __init__(self, seconds, callback):
        self.seconds = seconds
        self.callback = callback
        self.started = False
        self.cancelled = False
        self.daemon = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire_even_if_cancelled(self):
        self.callback()


class DeadThread:
    def is_alive(self):
        return False


class FakePoseWithCovarianceStamped:
    def __init__(self):
        self.header = SimpleNamespace(frame_id=None, stamp=None)
        self.pose = SimpleNamespace(
            pose=SimpleNamespace(
                position=SimpleNamespace(x=0.0, y=0.0),
                orientation=SimpleNamespace(z=0.0, w=0.0),
            ),
            covariance=[0.0] * 36,
        )


def demo_route():
    return parse_route(
        {
            "schema_version": 1,
            "map_id": "demo-map",
            "map_version": 1,
            "route_id": "scan-dwell-test",
            "frame_id": "map",
            "waypoints": [
                {
                    "sequence": 1,
                    "name": "PASS",
                    "x": 1.0,
                    "y": 1.0,
                    "yaw_deg": 0.0,
                    "acceptance_radius_m": 0.2,
                    "action": "PASS",
                },
                {
                    "sequence": 2,
                    "name": "SCAN",
                    "x": 2.0,
                    "y": 1.0,
                    "yaw_deg": 0.0,
                    "acceptance_radius_m": 0.2,
                    "action": "SCAN",
                },
                {
                    "sequence": 3,
                    "name": "DESTINATION",
                    "x": 3.0,
                    "y": 1.0,
                    "yaw_deg": 0.0,
                    "acceptance_radius_m": 0.2,
                    "action": "DESTINATION",
                },
            ],
        }
    )


def reached(waypoint):
    return SimpleNamespace(
        mission_event=SimpleNamespace(
            event_type=SimpleNamespace(value="WAYPOINT_REACHED"),
            waypoint=waypoint,
        )
    )


class RosNav2BridgeTest(unittest.TestCase):
    def test_start_never_overwrites_localization(self) -> None:
        """START_PATROL must not teleport AMCL to the route's waypoint 1.

        Localization is seeded once at startup with the dock pose and owned by
        scan matching afterwards. The route is a set of goals, not a statement
        of where the robot is.
        """

        sleeps = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6),
                initial_pose_settle_sec=1.0,
            ),
            motion_sink=lambda _command: None,
            sleep=sleeps.append,
        )
        publisher = Mock()
        bridge.is_ready = Mock(return_value=(True, "READY"))
        bridge._initial_pose_type = FakePoseWithCovarianceStamped
        bridge._initial_pose_publisher = publisher
        bridge._node = SimpleNamespace(
            get_clock=lambda: SimpleNamespace(
                now=lambda: SimpleNamespace(to_msg=lambda: "stamp")
            )
        )
        bridge._send_sequence = Mock()
        route = demo_route()
        first_event = SimpleNamespace(
            mission_event=SimpleNamespace(waypoint=route.waypoints[0])
        )

        bridge.start_patrol(route=route, first_event=first_event)

        publisher.publish.assert_not_called()
        self.assertEqual(sleeps, [])
        # Waypoint 1 stays the externally confirmed anchor; navigation begins
        # when the outer service reports it reached and sequence 2 dispatches.
        bridge._send_sequence.assert_not_called()

    def test_start_waits_for_first_post_anchor_goal_acceptance(self) -> None:
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6),
                initial_pose_settle_sec=1.0,
            ),
            motion_sink=lambda _command: None,
            sleep=lambda _seconds: None,
        )
        bridge.is_ready = Mock(return_value=(True, "READY"))
        bridge._initial_pose_type = FakePoseWithCovarianceStamped
        bridge._initial_pose_publisher = Mock()
        bridge._node = SimpleNamespace(
            get_clock=lambda: SimpleNamespace(
                now=lambda: SimpleNamespace(to_msg=lambda: "stamp")
            )
        )

        def accept_first_goal(_sequence):
            handle = Mock()
            handle.accepted = True
            result_future = Mock()
            handle.get_result_async.return_value = result_future
            response = Mock()
            response.result.return_value = handle
            bridge._on_goal_response(response, bridge._goal_generation)

        bridge._send_sequence = accept_first_goal
        route = demo_route()
        first_event = SimpleNamespace(
            mission_event=SimpleNamespace(waypoint=route.waypoints[0])
        )

        bridge.start_patrol(route=route, first_event=first_event)
        bridge.on_navigation_event(reached(route.waypoints[0]))
        bridge.wait_for_first_goal_acceptance()

        self.assertIsNotNone(bridge._goal_handle)
        self.assertTrue(bridge._first_goal_event.is_set())
        self.assertEqual(bridge._current_sequence, 2)

    def test_rejected_first_post_anchor_goal_fails_start(self) -> None:
        commands = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6),
                initial_pose_settle_sec=1.0,
            ),
            motion_sink=commands.append,
            sleep=lambda _seconds: None,
        )
        bridge.is_ready = Mock(return_value=(True, "READY"))
        bridge._initial_pose_type = FakePoseWithCovarianceStamped
        bridge._initial_pose_publisher = Mock()
        bridge._node = SimpleNamespace(
            get_clock=lambda: SimpleNamespace(
                now=lambda: SimpleNamespace(to_msg=lambda: "stamp")
            )
        )

        def reject_first_goal(_sequence):
            handle = Mock()
            handle.accepted = False
            response = Mock()
            response.result.return_value = handle
            bridge._on_goal_response(response, bridge._goal_generation)

        bridge._send_sequence = reject_first_goal
        route = demo_route()
        first_event = SimpleNamespace(
            mission_event=SimpleNamespace(waypoint=route.waypoints[0])
        )

        bridge.start_patrol(route=route, first_event=first_event)
        bridge.on_navigation_event(reached(route.waypoints[0]))
        with self.assertRaisesRegex(RuntimeError, "NAV2_GOAL_REJECTED"):
            bridge.wait_for_first_goal_acceptance()

        self.assertTrue(commands[-1].stopped)
        self.assertEqual(commands[-1].stop_reason, "NAV2_GOAL_REJECTED")

    def test_cmd_vel_uses_calibrated_adapter_without_serial_ownership(self) -> None:
        commands = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                ackermann=AckermannCommandSettings(
                    wheelbase_m=0.24,
                    maximum_road_wheel_angle_deg=25,
                    minimum_drive_pwm=45,
                    maximum_drive_pwm=51,
                )
            ),
            motion_sink=commands.append,
        )

        command = bridge.record_cmd_vel(0.2, 0.2)

        self.assertEqual(commands, [command])
        self.assertGreater(command.speed_pwm, 0)
        self.assertLess(command.steering_deg, 80)
        self.assertFalse(hasattr(bridge, "_serial"))

    def test_uncalibrated_turn_is_stopped(self) -> None:
        commands = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                ackermann=AckermannCommandSettings(None, None)
            ),
            motion_sink=commands.append,
        )
        command = bridge.record_cmd_vel(0.2, 0.3)
        self.assertTrue(command.stopped)
        self.assertEqual(command.stop_reason, "STEERING_NOT_CALIBRATED")

    def test_pass_advances_immediately_but_scan_waits_before_next_goal(self) -> None:
        commands = []
        timers = []
        scan_contexts = []

        def timer_factory(seconds, callback):
            timer = ManualTimer(seconds, callback)
            timers.append(timer)
            return timer

        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6),
                scan_dwell_sec=4.0,
            ),
            motion_sink=commands.append,
            scan_context_sink=scan_contexts.append,
            timer_factory=timer_factory,
        )
        route = demo_route()
        bridge._route = route
        bridge._current_sequence = 1
        bridge._send_sequence = Mock()

        bridge.on_navigation_event(reached(route.waypoints[0]))
        bridge._send_sequence.assert_called_once_with(2)
        bridge._send_sequence.reset_mock()

        active_handle = Mock()
        bridge._goal_handle = active_handle
        bridge.on_navigation_event(reached(route.waypoints[1]))
        bridge._send_sequence.assert_not_called()
        active_handle.cancel_goal_async.assert_called_once_with()
        self.assertEqual(commands[-1].stop_reason, "SCAN_DWELL")
        self.assertEqual(timers[-1].seconds, 4.0)
        self.assertTrue(timers[-1].started)
        self.assertTrue(timers[-1].daemon)
        self.assertIs(scan_contexts[-1], route.waypoints[1])

        blocked = bridge.record_cmd_vel(0.2, 0.0)
        self.assertTrue(blocked.stopped)
        self.assertEqual(blocked.stop_reason, "SCAN_DWELL")

        timers[-1].fire_even_if_cancelled()
        self.assertIsNone(scan_contexts[-1])
        bridge._send_sequence.assert_called_once_with(3)
        self.assertEqual(bridge._current_sequence, 3)

    def test_pause_stop_and_failure_cancel_scan_dwell(self) -> None:
        for operation in ("pause", "stop", "fail"):
            with self.subTest(operation=operation):
                timers = []
                failures = []
                scan_contexts = []

                def timer_factory(seconds, callback):
                    del seconds
                    timer = ManualTimer(3.0, callback)
                    timers.append(timer)
                    return timer

                bridge = RosNav2Bridge(
                    settings=RosNav2BridgeSettings(
                        AckermannCommandSettings(0.124, 8.6)
                    ),
                    motion_sink=lambda _command: None,
                    failure_sink=failures.append,
                    scan_context_sink=scan_contexts.append,
                    timer_factory=timer_factory,
                )
                route = demo_route()
                bridge._route = route
                bridge._current_sequence = 2
                bridge._send_sequence = Mock()
                bridge.on_navigation_event(reached(route.waypoints[1]))
                timer = timers[-1]
                active_handle = Mock()
                bridge._goal_handle = active_handle

                if operation == "pause":
                    bridge.pause_patrol()
                elif operation == "stop":
                    bridge.stop_patrol()
                else:
                    bridge._fail("TEST_FAILURE")

                self.assertTrue(timer.cancelled)
                active_handle.cancel_goal_async.assert_called_once_with()
                timer.fire_even_if_cancelled()
                bridge._send_sequence.assert_not_called()
                if operation == "pause":
                    self.assertIsNone(scan_contexts[-1])
                    bridge.resume_patrol()
                    self.assertEqual(len(timers), 2)
                    self.assertTrue(timers[-1].started)
                    self.assertIs(scan_contexts[-1], route.waypoints[1])
                    timers[-1].fire_even_if_cancelled()
                    self.assertIsNone(scan_contexts[-1])
                    bridge._send_sequence.assert_called_once_with(3)
                else:
                    self.assertIsNone(scan_contexts[-1])
                if operation == "fail":
                    self.assertEqual(failures, ["TEST_FAILURE"])

    def test_null_yaw_uses_route_direction_instead_of_zero_default(self) -> None:
        route = parse_route(
            {
                "schema_version": 1,
                "map_id": "demo-map",
                "map_version": 1,
                "route_id": "nullable-yaw",
                "frame_id": "map",
                "waypoints": [
                    {
                        "sequence": 1,
                        "name": "PASS",
                        "x": 1.0,
                        "y": 1.0,
                        "yaw_deg": None,
                        "acceptance_radius_m": 0.2,
                        "action": "PASS",
                    },
                    {
                        "sequence": 2,
                        "name": "DESTINATION",
                        "x": 1.0,
                        "y": 2.0,
                        "yaw_deg": None,
                        "acceptance_radius_m": 0.2,
                        "action": "DESTINATION",
                    },
                ],
            }
        )
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6)
            ),
            motion_sink=lambda _command: None,
        )

        self.assertIsNone(route.waypoints[0].yaw_deg)
        self.assertAlmostEqual(bridge._resolve_goal_yaw_deg(route, 1), 90.0)
        self.assertAlmostEqual(bridge._resolve_goal_yaw_deg(route, 2), 90.0)

    def test_single_null_yaw_uses_current_localization_heading(self) -> None:
        route = parse_route(
            {
                "schema_version": 1,
                "map_id": "demo-map",
                "map_version": 1,
                "route_id": "single-null-yaw",
                "frame_id": "map",
                "waypoints": [
                    {
                        "sequence": 1,
                        "name": "DESTINATION",
                        "x": 1.0,
                        "y": 1.0,
                        "yaw_deg": None,
                        "acceptance_radius_m": 0.2,
                        "action": "DESTINATION",
                    }
                ],
            }
        )
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6)
            ),
            motion_sink=lambda _command: None,
            heading_source=lambda: 37.5,
        )

        self.assertEqual(bridge._resolve_goal_yaw_deg(route, 1), 37.5)

    def test_stale_goal_callbacks_cannot_restart_scan_motion_or_fail_patrol(self) -> None:
        failures = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6)
            ),
            motion_sink=lambda _command: None,
            failure_sink=failures.append,
        )
        bridge._route = demo_route()
        bridge._current_sequence = 2
        bridge._pending_scan = (2, 3)
        bridge._cmd_vel_hold_reason = "SCAN_DWELL"
        bridge._goal_generation = 5

        stale_handle = Mock()
        stale_handle.accepted = True
        response = Mock()
        response.result.return_value = stale_handle
        bridge._on_goal_response(response, 4)

        stale_handle.cancel_goal_async.assert_called_once_with()
        stale_handle.get_result_async.assert_not_called()
        stale_result = Mock()
        stale_result.result.return_value = SimpleNamespace(status=6)
        bridge._on_goal_result(stale_result, 4)
        self.assertEqual(failures, [])

        command = bridge.record_cmd_vel(0.2, 0.0)
        self.assertTrue(command.stopped)
        self.assertEqual(command.stop_reason, "SCAN_DWELL")

    def test_nav2_abort_holds_for_obstacle_and_resumes_same_waypoint(
        self,
    ) -> None:
        failures = []
        obstacles = []
        commands = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6)
            ),
            motion_sink=commands.append,
            failure_sink=failures.append,
            obstacle_sink=obstacles.append,
        )
        bridge._route = demo_route()
        bridge._current_sequence = 2
        bridge._goal_generation = 2
        bridge._send_sequence = Mock()
        result = Mock()
        result.result.return_value = SimpleNamespace(status=6)

        bridge._on_goal_result(result, 2)

        # An abort must not end the patrol: no failure is reported and the
        # route/sequence survive so the same waypoint can be retried.
        self.assertEqual(failures, [])
        self.assertEqual(obstacles, ["OBSTACLE"])
        self.assertIsNotNone(bridge._route)
        self.assertEqual(bridge._current_sequence, 2)
        self.assertTrue(bridge._paused)
        self.assertEqual(bridge._cmd_vel_hold_reason, "OBSTACLE")
        self.assertTrue(commands[-1].stopped)
        self.assertEqual(commands[-1].stop_reason, "OBSTACLE")
        bridge._send_sequence.assert_not_called()

        # Once the obstacle clears the runtime resumes the very same waypoint.
        bridge.resume_patrol()
        bridge._send_sequence.assert_called_once_with(2)
        self.assertFalse(bridge._paused)

    def test_repeated_nav2_aborts_eventually_fail_closed(self) -> None:
        failures = []
        obstacles = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6),
                goal_abort_retry_limit=2,
            ),
            motion_sink=lambda _command: None,
            failure_sink=failures.append,
            obstacle_sink=obstacles.append,
        )
        bridge._route = demo_route()
        bridge._current_sequence = 2
        bridge._send_sequence = Mock()

        def abort_once() -> None:
            bridge._goal_generation += 1
            bridge._paused = False
            result = Mock()
            result.result.return_value = SimpleNamespace(status=6)
            bridge._on_goal_result(result, bridge._goal_generation)

        abort_once()
        abort_once()
        self.assertEqual(failures, [])
        self.assertEqual(len(obstacles), 2)

        # A blockage that never clears must not hold the patrol open forever.
        abort_once()
        self.assertEqual(len(obstacles), 2)
        self.assertEqual(len(failures), 1)
        self.assertTrue(
            failures[0].startswith("NAV2_GOAL_ABORT_UNRECOVERABLE")
        )
        self.assertIsNone(bridge._route)

    def test_waypoint_progress_restores_abort_retry_budget(self) -> None:
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6)
            ),
            motion_sink=lambda _command: None,
        )
        route = demo_route()
        bridge._route = route
        bridge._current_sequence = 1
        bridge._goal_aborts_at_sequence = 2
        bridge._send_sequence = Mock()

        bridge.on_navigation_event(reached(route.waypoints[0]))

        self.assertEqual(bridge._current_sequence, 2)
        self.assertEqual(bridge._goal_aborts_at_sequence, 0)

    def test_succeeded_goal_restores_abort_retry_budget(self) -> None:
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6)
            ),
            motion_sink=lambda _command: None,
        )
        bridge._route = demo_route()
        bridge._current_sequence = 2
        bridge._goal_generation = 2
        bridge._goal_aborts_at_sequence = 2
        result = Mock()
        result.result.return_value = SimpleNamespace(status=4)

        bridge._on_goal_result(result, 2)

        self.assertEqual(bridge._goal_aborts_at_sequence, 0)

    def test_current_goal_cancel_fails_closed(self) -> None:
        failures = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6)
            ),
            motion_sink=lambda _command: None,
            failure_sink=failures.append,
        )
        bridge._route = demo_route()
        bridge._goal_generation = 2
        result = Mock()
        result.result.return_value = SimpleNamespace(status=5)

        bridge._on_goal_result(result, 2)

        self.assertEqual(failures, ["NAV2_GOAL_STATUS_5"])
        self.assertEqual(bridge._cmd_vel_hold_reason, "NAV2_GOAL_STATUS_5")

    def test_cancel_rpc_failure_cannot_suppress_physical_stop(self) -> None:
        commands = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6)
            ),
            motion_sink=commands.append,
        )
        handle = Mock()
        handle.cancel_goal_async.side_effect = RuntimeError("ROS unavailable")
        bridge._goal_handle = handle
        bridge._route = demo_route()

        bridge.stop_patrol()

        self.assertTrue(commands[-1].stopped)
        self.assertEqual(commands[-1].stop_reason, "NAV2_PATROL_STOPPED")

    def test_scan_dwell_range_is_fail_closed(self) -> None:
        for seconds in (0.0, 60.1, float("nan")):
            with self.subTest(seconds=seconds):
                with self.assertRaisesRegex(ValueError, "scan_dwell_sec"):
                    RosNav2BridgeSettings(
                        AckermannCommandSettings(0.124, 8.6),
                        scan_dwell_sec=seconds,
                    )

    def test_first_goal_accept_timeout_range_is_fail_closed(self) -> None:
        for seconds in (0.0, 15.1, float("nan")):
            with self.subTest(seconds=seconds):
                with self.assertRaisesRegex(
                    ValueError, "first_goal_accept_timeout_sec"
                ):
                    RosNav2BridgeSettings(
                        AckermannCommandSettings(0.124, 8.6),
                        first_goal_accept_timeout_sec=seconds,
                    )

    def test_active_goal_cmd_vel_freshness_timeout_fails_patrol(self) -> None:
        now = [0.0]
        commands = []
        failures = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6),
                cmd_vel_timeout_sec=0.5,
            ),
            motion_sink=commands.append,
            failure_sink=failures.append,
            clock=lambda: now[0],
        )
        handle = Mock()
        bridge._route = demo_route()
        bridge._current_sequence = 1
        bridge._goal_handle = handle
        bridge._cmd_vel_hold_reason = None
        bridge._last_cmd_vel_at = 0.0

        now[0] = 0.2
        bridge.record_cmd_vel(0.2, 0.0)
        now[0] = 0.69
        self.assertTrue(bridge.check_health())
        now[0] = 0.71
        self.assertFalse(bridge.check_health())

        self.assertEqual(failures, ["NAV2_CMD_VEL_TIMEOUT"])
        self.assertTrue(commands[-1].stopped)
        self.assertEqual(commands[-1].stop_reason, "NAV2_CMD_VEL_TIMEOUT")
        handle.cancel_goal_async.assert_called_once_with()
        self.assertIsNone(bridge._route)
        self.assertTrue(bridge.check_health())
        self.assertEqual(failures, ["NAV2_CMD_VEL_TIMEOUT"])

    def test_cmd_vel_timeout_is_disarmed_in_non_driving_states(self) -> None:
        scenarios = (
            ("GOAL_PENDING", False, None, None, "NAV2_GOAL_PENDING"),
            ("SCAN", False, Mock(), (2, 3), "SCAN_DWELL"),
            ("PAUSED", True, None, None, "OBSTACLE"),
            ("STOPPED", False, None, None, "NAV2_PATROL_STOPPED"),
        )
        for name, paused, handle, pending_scan, hold_reason in scenarios:
            with self.subTest(name=name):
                failures = []
                bridge = RosNav2Bridge(
                    settings=RosNav2BridgeSettings(
                        AckermannCommandSettings(0.124, 8.6),
                        cmd_vel_timeout_sec=0.5,
                    ),
                    motion_sink=lambda _command: None,
                    failure_sink=failures.append,
                    clock=lambda: 10.0,
                )
                bridge._route = None if name == "STOPPED" else demo_route()
                bridge._paused = paused
                bridge._goal_handle = handle
                bridge._pending_scan = pending_scan
                bridge._cmd_vel_hold_reason = hold_reason
                bridge._last_cmd_vel_at = 0.0

                self.assertTrue(bridge.check_health())
                self.assertEqual(failures, [])

    def test_dead_bridge_thread_fails_active_goal(self) -> None:
        failures = []
        commands = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                AckermannCommandSettings(0.124, 8.6)
            ),
            motion_sink=commands.append,
            failure_sink=failures.append,
        )
        handle = Mock()
        bridge._route = demo_route()
        bridge._current_sequence = 1
        bridge._goal_handle = handle
        bridge._cmd_vel_hold_reason = None
        bridge._last_cmd_vel_at = bridge._clock()
        bridge._thread_started = True
        bridge._thread = DeadThread()

        self.assertFalse(bridge.check_health())

        self.assertEqual(failures, ["NAV2_BRIDGE_THREAD_DEAD"])
        self.assertEqual(commands[-1].stop_reason, "NAV2_BRIDGE_THREAD_DEAD")
        handle.cancel_goal_async.assert_called_once_with()

    def test_bridge_thread_exit_does_not_fail_stopped_or_paused_patrol(self) -> None:
        for state in ("STOPPED", "PAUSED"):
            with self.subTest(state=state):
                failures = []
                bridge = RosNav2Bridge(
                    settings=RosNav2BridgeSettings(
                        AckermannCommandSettings(0.124, 8.6)
                    ),
                    motion_sink=lambda _command: None,
                    failure_sink=failures.append,
                )
                if state == "PAUSED":
                    bridge._route = demo_route()
                    bridge._paused = True
                bridge._rclpy = SimpleNamespace(ok=lambda: False)

                bridge._spin()

                self.assertEqual(failures, [])

    def test_cmd_vel_timeout_range_is_fail_closed(self) -> None:
        for seconds in (0.1, 5.1, float("nan")):
            with self.subTest(seconds=seconds):
                with self.assertRaisesRegex(ValueError, "cmd_vel_timeout_sec"):
                    RosNav2BridgeSettings(
                        AckermannCommandSettings(0.124, 8.6),
                        cmd_vel_timeout_sec=seconds,
                    )


if __name__ == "__main__":
    unittest.main()
