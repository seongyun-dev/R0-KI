"""ExploreSupervisor: the explorer lives and dies with the mapping session."""

from __future__ import annotations

import signal
import threading
import unittest

from integration.explore_supervisor import ExploreSupervisor


class FakeProcess:
    def __init__(self, pid: int = 4321) -> None:
        self.pid = pid
        self.signals: list[int] = []
        self.exited = threading.Event()

    def poll(self):
        return 0 if self.exited.is_set() else None

    def wait(self, timeout=None):
        if not self.exited.wait(timeout=timeout):
            raise TimeoutError("process still running")
        return 0

    def send_signal(self, signum):
        self.signals.append(signum)
        self.exited.set()


class FakeRun:
    """Scripted `ros2 lifecycle get` outputs, one per call."""

    def __init__(self, outputs) -> None:
        self.outputs = list(outputs)
        self.calls = 0
        self.argvs = []

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if args:
            self.argvs.append(list(args[0]))
        text = self.outputs.pop(0) if self.outputs else self.outputs_last()
        result = type("R", (), {})()
        result.stdout = text
        result.stderr = ""
        return result

    def outputs_last(self):
        return "active [3]"


class FakeMonitor:
    def __init__(self, on_status) -> None:
        self.on_status = on_status
        self.started = False
        self.pause_requests = 0
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def request_pause(self, timeout_sec=1.0) -> bool:
        self.pause_requests += 1
        self.on_status("exploration_paused")
        return True

    def stop(self) -> None:
        self.stopped = True

    def emit(self, status: str) -> None:
        self.on_status(status)


class ExploreSupervisorTest(unittest.TestCase):
    def build(self, run_outputs, process=None):
        self.process = process or FakeProcess()
        self.popen_calls = []
        self.clock = [0.0]

        def fake_popen(argv, **kwargs):
            self.popen_calls.append((argv, kwargs))
            return self.process

        def fake_monotonic():
            return self.clock[0]

        def fake_sleep(seconds):
            self.clock[0] += seconds

        def fake_monitor_factory(on_status):
            self.monitor = FakeMonitor(on_status)
            return self.monitor

        return ExploreSupervisor(
            explore_setup_file="/opt/explore/setup.bash",
            params_file="/opt/robot/config/ros/explore.params.yaml",
            nav2_wait_timeout_sec=30.0,
            nav2_poll_interval_sec=1.0,
            terminate_grace_sec=0.1,
            popen=fake_popen,
            run=FakeRun(run_outputs),
            monotonic=fake_monotonic,
            sleep=fake_sleep,
            monitor_factory=fake_monitor_factory,
        )

    def join_starter(self, supervisor):
        starter = supervisor._starter
        if starter is not None:
            starter.join(timeout=5.0)
            self.assertFalse(starter.is_alive())

    def test_readiness_probe_bypasses_the_ros_daemon(self):
        """데몬 그래프는 aiot-ros 재시작을 넘어 살아남아 낡은 답을 준다.

        2026-08-07 22:00 현장: `ros2 lifecycle get /bt_navigator` 가
        "Node not found" 를 돌려주는 동안 같은 노드가
        `ros2 node list --no-daemon` 에는 active 로 보였다. 폴링으로는
        복구되지 않는다 -- 재시도마다 같은 캐시를 물어보기 때문이다.
        그 결과 매핑 세션이 explore 없이 조용히 진행됐다.
        """

        supervisor = self.build(["active [3]"])
        supervisor.start(7)
        self.join_starter(supervisor)

        self.assertTrue(supervisor._run.argvs, "준비 판정이 호출되지 않았다")
        argv = supervisor._run.argvs[0]
        self.assertEqual(argv[:3], ["ros2", "lifecycle", "get"])
        self.assertIn("--no-daemon", argv)

    def test_spawns_only_after_bt_navigator_is_active(self):
        supervisor = self.build(["inactive [2]", "inactive [2]", "active [3]"])
        supervisor.start(7)
        self.join_starter(supervisor)

        self.assertEqual(len(self.popen_calls), 1)
        argv, kwargs = self.popen_calls[0]
        self.assertEqual(argv[0], "bash")
        self.assertIn("explore_lite", argv[2])
        self.assertIn("explore.params.yaml", argv[2])
        # A fresh process group is what lets stop() kill the whole ros2 tree.
        self.assertTrue(kwargs.get("start_new_session"))

    def test_never_spawns_when_nav2_stays_inactive(self):
        supervisor = self.build(["inactive [2]"] * 100)
        supervisor.start(7)
        self.join_starter(supervisor)

        self.assertEqual(self.popen_calls, [])

    def test_stop_during_wait_cancels_the_spawn(self):
        gate = threading.Event()

        def blocking_run(*args, **kwargs):
            gate.wait(timeout=5.0)
            result = type("R", (), {})()
            result.stdout = "active [3]"
            result.stderr = ""
            return result

        supervisor = ExploreSupervisor(
            explore_setup_file="/opt/explore/setup.bash",
            params_file="/opt/params.yaml",
            popen=lambda *a, **k: self.fail("must not spawn after stop"),
            run=blocking_run,
        )
        supervisor.start(7)
        supervisor._stop_requested.set()
        gate.set()
        self.join_starter(supervisor)

    def test_stop_signals_the_process(self):
        supervisor = self.build(["active [3]"])
        supervisor.start(7)
        self.join_starter(supervisor)
        self.assertTrue(supervisor.running)

        supervisor.stop("finish")

        self.assertEqual(self.monitor.pause_requests, 1)
        self.assertTrue(self.monitor.stopped)
        self.assertIn(signal.SIGINT, self.process.signals)
        self.assertFalse(supervisor.running)

    def test_tracks_return_to_origin_status(self):
        supervisor = self.build(["active [3]"])
        supervisor.start(7)
        self.join_starter(supervisor)

        self.monitor.emit("returning_to_origin")
        self.assertEqual(supervisor.status, "returning_to_origin")
        self.monitor.emit("returned_to_origin")
        self.assertEqual(supervisor.status, "returned_to_origin")

        supervisor.stop("finish")

    def test_stop_without_start_is_a_no_op(self):
        supervisor = self.build(["active [3]"])
        supervisor.stop("shutdown")
        self.assertEqual(self.popen_calls, [])

    def test_second_start_is_ignored_while_running(self):
        supervisor = self.build(["active [3]", "active [3]"])
        supervisor.start(7)
        self.join_starter(supervisor)
        supervisor.start(7)
        self.join_starter(supervisor)
        self.assertEqual(len(self.popen_calls), 1)

    def test_from_environment_requires_the_autonomy_flag(self):
        self.assertIsNone(
            ExploreSupervisor.from_environment({"AIOT_MAPPING_AUTONOMOUS": ""})
        )
        self.assertIsNone(ExploreSupervisor.from_environment({}))
        supervisor = ExploreSupervisor.from_environment(
            {
                "AIOT_MAPPING_AUTONOMOUS": "true",
                "AIOT_EXPLORE_SETUP_FILE": "/opt/explore/setup.bash",
                "AIOT_EXPLORE_PARAMS_FILE": "/opt/params.yaml",
            }
        )
        self.assertIsNotNone(supervisor)


if __name__ == "__main__":
    unittest.main()
