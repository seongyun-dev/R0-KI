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

    def __call__(self, *args, **kwargs):
        self.calls += 1
        text = self.outputs.pop(0) if self.outputs else self.outputs_last()
        result = type("R", (), {})()
        result.stdout = text
        result.stderr = ""
        return result

    def outputs_last(self):
        return "active [3]"


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
        )

    def join_starter(self, supervisor):
        starter = supervisor._starter
        if starter is not None:
            starter.join(timeout=5.0)
            self.assertFalse(starter.is_alive())

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

        self.assertIn(signal.SIGINT, self.process.signals)
        self.assertFalse(supervisor.running)

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
