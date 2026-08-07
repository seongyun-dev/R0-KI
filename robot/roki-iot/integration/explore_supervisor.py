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
        popen: Any = subprocess.Popen,
        run: Any = subprocess.run,
        monotonic: Any = time.monotonic,
        sleep: Any = time.sleep,
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
        self._popen = popen
        self._run = run
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._process: Any | None = None
        self._starter: threading.Thread | None = None

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
        command = (
            "set -e; "
            f". {self._shell_quote(self._explore_setup_file)}; "
            "exec ros2 run explore_lite explore --ros-args "
            f"--params-file {self._shell_quote(self._params_file)}"
        )
        with self._lock:
            if self._stop_requested.is_set():
                return
            self._process = self._popen(
                ["bash", "-c", command],
                start_new_session=True,
            )
        print(
            "[MAPPING] explore started "
            f"mappingSessionId={mapping_session_id} "
            f"pid={self._process.pid}"
        )

    def _wait_for_bt_navigator_active(self) -> bool:
        deadline = self._monotonic() + self._nav2_wait_timeout_sec
        while not self._stop_requested.is_set():
            try:
                result = self._run(
                    ["ros2", "lifecycle", "get", self._bt_navigator_node],
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
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.send_signal(signum)
            except Exception:
                pass

    @staticmethod
    def _shell_quote(value: str) -> str:
        return "'" + value.replace("'", "'\\''") + "'"
