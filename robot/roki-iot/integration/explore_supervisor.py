"""Own the frontier explorer's lifetime from the mapping session.

explore_lite has no enable/disable API, and it permanently blacklists any
frontier whose goal fails. Launched together with the ROS stack it therefore
runs against a closed motion gate whenever no mapping session is active,
blacklists every frontier within minutes and stops itself for good ("All
frontiers traversed") -- after which only a service restart could revive it.
That is why mapping only ever worked when someone restarted aiot-ros by hand
right after opening a session.

Owning the process here makes its lifetime equal to the session's: it is
spawned once the session is accepted and the motion gate is open, and it is
terminated when the session finishes, aborts or shuts down. Every session gets
a fresh explorer and therefore a fresh blacklist.

The spawn also replaces the old fixed ``sleep 12`` ordering hack in
run-ros.sh: it waits until Nav2's bt_navigator lifecycle reports ``active``
before launching, because a goal sent during activation is rejected and its
frontier is blacklisted for no reason.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


def _environment_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


class ExploreStatusMonitor:
    """Observe explore_lite's return trip and cancel its goal before shutdown.

    A private ROS context is intentional.  The integrated runtime already owns
    several ROS nodes and executors; shutting this monitor down must never shut
    down their shared default context.
    """

    def __init__(
        self,
        on_status: Any,
        *,
        status_topic: str = "/explore/status",
        resume_topic: str = "/explore/resume",
    ) -> None:
        self._on_status = on_status
        self._status_topic = status_topic
        self._resume_topic = resume_topic
        self._context: Any = None
        self._executor: Any = None
        self._node: Any = None
        self._pause_publisher: Any = None
        self._bool_type: Any = None
        self._thread: threading.Thread | None = None
        self._paused = threading.Event()

    def start(self) -> None:
        import rclpy
        from explore_lite_msgs.msg import ExploreStatus
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from std_msgs.msg import Bool

        context = Context()
        rclpy.init(args=None, context=context)
        node = rclpy.create_node("aiot_explore_status_monitor", context=context)
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)
        self._context = context
        self._executor = executor
        self._node = node
        self._bool_type = Bool
        self._pause_publisher = node.create_publisher(Bool, self._resume_topic, 10)
        node.create_subscription(
            ExploreStatus,
            self._status_topic,
            self._status_callback,
            10,
        )
        self._thread = threading.Thread(
            target=executor.spin,
            name="ros-explore-status-monitor",
            daemon=True,
        )
        self._thread.start()

    def request_pause(self, timeout_sec: float = 1.0) -> bool:
        """Ask explore_lite to cancel every Nav2 goal before it is killed."""

        if self._pause_publisher is None or self._bool_type is None:
            return False
        self._paused.clear()
        message = self._bool_type()
        message.data = False
        deadline = time.monotonic() + max(0.0, timeout_sec)
        while time.monotonic() < deadline:
            self._pause_publisher.publish(message)
            if self._paused.wait(timeout=0.1):
                return True
        return self._paused.is_set()

    def stop(self) -> None:
        if self._executor is not None:
            self._executor.shutdown()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)
        if self._node is not None:
            self._node.destroy_node()
        if self._context is not None:
            try:
                self._context.shutdown()
            except Exception:
                pass
        self._context = None
        self._executor = None
        self._node = None
        self._pause_publisher = None
        self._thread = None

    def _status_callback(self, message: Any) -> None:
        status = str(getattr(message, "status", "")).strip()
        if status == "exploration_paused":
            self._paused.set()
        if status:
            self._on_status(status)


class ExploreSupervisor:
    def __init__(
        self,
        *,
        explore_setup_file: str,
        params_file: str,
        bt_navigator_node: str = "/bt_navigator",
        nav2_wait_timeout_sec: float = 120.0,
        nav2_poll_interval_sec: float = 3.0,
        terminate_grace_sec: float = 5.0,
        cancel_settle_sec: float = 0.25,
        popen: Any = subprocess.Popen,
        run: Any = subprocess.run,
        monotonic: Any = time.monotonic,
        sleep: Any = time.sleep,
        monitor_factory: Any = ExploreStatusMonitor,
    ) -> None:
        if not explore_setup_file or not params_file:
            raise ValueError("explore setup and params files are required")
        if nav2_wait_timeout_sec <= 0 or nav2_poll_interval_sec <= 0:
            raise ValueError("nav2 wait settings must be positive")
        self._explore_setup_file = explore_setup_file
        self._params_file = params_file
        self._bt_navigator_node = bt_navigator_node
        self._nav2_wait_timeout_sec = nav2_wait_timeout_sec
        self._nav2_poll_interval_sec = nav2_poll_interval_sec
        self._terminate_grace_sec = terminate_grace_sec
        self._cancel_settle_sec = cancel_settle_sec
        self._popen = popen
        self._run = run
        self._monotonic = monotonic
        self._sleep = sleep
        self._monitor_factory = monitor_factory
        self._lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._process: Any | None = None
        self._starter: threading.Thread | None = None
        self._monitor: Any | None = None
        self._status: str | None = None

    @classmethod
    def from_environment(
        cls, environ: Any = None
    ) -> "ExploreSupervisor | None":
        """Build from robot.env/ros.env; None when autonomy is not enabled."""

        environ = os.environ if environ is None else environ
        if not _environment_enabled(environ.get("AIOT_MAPPING_AUTONOMOUS")):
            return None
        robot_root = Path(__file__).resolve().parents[2]
        params_file = environ.get("AIOT_EXPLORE_PARAMS_FILE", "").strip() or str(
            robot_root / "config" / "ros" / "explore.params.yaml"
        )
        setup_file = environ.get("AIOT_EXPLORE_SETUP_FILE", "").strip() or (
            "/home/e103/explore_ws/install/setup.bash"
        )
        return cls(explore_setup_file=setup_file, params_file=params_file)

    @property
    def running(self) -> bool:
        with self._lock:
            process = self._process
        return process is not None and process.poll() is None

    @property
    def status(self) -> str | None:
        with self._lock:
            return self._status

    def start(self, mapping_session_id: int) -> None:
        """Spawn the explorer once Nav2 is active. Never blocks the caller."""

        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return
            if self._starter is not None and self._starter.is_alive():
                return
            self._stop_requested.clear()
            starter = threading.Thread(
                target=self._start_worker,
                args=(mapping_session_id,),
                name="explore-supervisor-start",
                daemon=True,
            )
            self._starter = starter
        starter.start()

    def stop(self, reason: str) -> None:
        """Terminate the explorer process group; idempotent."""

        self._stop_requested.set()
        starter = self._starter
        if starter is not None and starter is not threading.current_thread():
            starter.join(timeout=1.0)
        with self._lock:
            process = self._process
            self._process = None
            monitor = self._monitor
            self._monitor = None
        try:
            # Killing the action client does not guarantee that Nav2 cancels
            # the goal it accepted.  Pause while the node is still spinning so
            # STOP_MAPPING/abort cannot leave a return goal alive for the next
            # mapping session.
            if monitor is not None and process is not None and process.poll() is None:
                acknowledged = monitor.request_pause()
                print(
                    "[MAPPING] explore pause requested "
                    f"reason={reason} acknowledged={str(acknowledged).lower()}"
                )
                if acknowledged:
                    self._sleep(self._cancel_settle_sec)
            if process is None or process.poll() is not None:
                return
            self._signal_group(process, signal.SIGINT)
            if self._wait(process, self._terminate_grace_sec):
                print(f"[MAPPING] explore stopped reason={reason}")
                return
            self._signal_group(process, signal.SIGTERM)
            if self._wait(process, 3.0):
                print(f"[MAPPING] explore terminated reason={reason}")
                return
            self._signal_group(process, signal.SIGKILL)
            process.wait()
            print(f"[MAPPING] explore killed reason={reason}")
        finally:
            if monitor is not None:
                monitor.stop()

    def _start_worker(self, mapping_session_id: int) -> None:
        if not self._wait_for_bt_navigator_active():
            if not self._stop_requested.is_set():
                print(
                    "[MAPPING] explore not started "
                    "reason=NAV2_NOT_ACTIVE "
                    f"mappingSessionId={mapping_session_id}"
                )
            return
        if self._stop_requested.is_set():
            return
        monitor = self._monitor_factory(self._on_status)
        try:
            monitor.start()
        except Exception as exc:
            try:
                monitor.stop()
            except Exception:
                pass
            print(
                "[MAPPING] explore not started "
                "reason=STATUS_MONITOR_FAILED "
                f"mappingSessionId={mapping_session_id} "
                f"type={type(exc).__name__}"
            )
            return
        command = (
            "set -e; "
            f". {self._shell_quote(self._explore_setup_file)}; "
            "exec ros2 run explore_lite explore --ros-args "
            f"--params-file {self._shell_quote(self._params_file)}"
        )
        try:
            with self._lock:
                if self._stop_requested.is_set():
                    monitor.stop()
                    return
                self._monitor = monitor
                self._status = None
                self._process = self._popen(
                    ["bash", "-c", command],
                    start_new_session=True,
                )
        except Exception:
            with self._lock:
                self._monitor = None
                self._process = None
            monitor.stop()
            raise
        print(
            "[MAPPING] explore started "
            f"mappingSessionId={mapping_session_id} "
            f"pid={self._process.pid}"
        )

    def _on_status(self, status: str) -> None:
        with self._lock:
            self._status = status
        print(f"[MAPPING] explore status={status}")

    def _wait_for_bt_navigator_active(self) -> bool:
        deadline = self._monotonic() + self._nav2_wait_timeout_sec
        while not self._stop_requested.is_set():
            try:
                result = self._run(
                    # --no-daemon is not optional. The ROS daemon caches a
                    # graph that survives an aiot-ros restart, so after a mode
                    # switch it answers "Node not found" for a bt_navigator
                    # that is demonstrably in `ros2 node list --no-daemon`.
                    # Polling cannot recover from that: every retry asks the
                    # same stale cache, the deadline expires, and the session
                    # silently runs without explore (NAV2_NOT_ACTIVE).
                    # Observed 2026-08-07 22:00, mapping session 9.
                    [
                        "ros2",
                        "lifecycle",
                        "get",
                        "--no-daemon",
                        self._bt_navigator_node,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10.0,
                )
                output = (result.stdout or "") + (result.stderr or "")
            except Exception:
                output = ""
            if "active" in output and "inactive" not in output:
                return True
            if self._monotonic() >= deadline:
                return False
            self._sleep(self._nav2_poll_interval_sec)
        return False

    def _wait(self, process: Any, timeout: float) -> bool:
        try:
            process.wait(timeout=timeout)
            return True
        except Exception:
            return False

    def _signal_group(self, process: Any, signum: int) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signum)
        except (AttributeError, ProcessLookupError, PermissionError, OSError):
            try:
                process.send_signal(signum)
            except Exception:
                pass

    @staticmethod
    def _shell_quote(value: str) -> str:
        return "'" + value.replace("'", "'\\''") + "'"
