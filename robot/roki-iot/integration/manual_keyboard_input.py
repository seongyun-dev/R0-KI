"""TTY keyboard input for the explicit manual patrol demo mode."""

from __future__ import annotations

import os
import select
import sys
import threading
from typing import Any, TextIO

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - deployment target is Linux
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]


class ManualKeyboardInput:
    """Forward keys to a controller without ever opening the Serial device."""

    def __init__(
        self,
        controller: Any,
        *,
        loop_interval_sec: float = 0.02,
        input_stream: TextIO = sys.stdin,
    ) -> None:
        if loop_interval_sec <= 0:
            raise ValueError("keyboard loop interval must be positive")
        self._controller = controller
        self._loop_interval_sec = loop_interval_sec
        self._input_stream = input_stream
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        if not self._input_stream.isatty():
            raise RuntimeError("manual keyboard mode requires a foreground TTY")
        if termios is None or tty is None:
            raise RuntimeError("manual keyboard mode requires a POSIX terminal")
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="manual-keyboard",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._controller.active:
            self._controller.deactivate()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._thread = None

    def _run(self) -> None:
        assert termios is not None and tty is not None
        fd = self._input_stream.fileno()
        original_attributes = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            print(
                "[MANUAL] MQTT START 후 W/A/S/D 조작, "
                "Space/Q=즉시 정지, 순찰 종료는 프론트 STOP"
            )
            while not self._stop_event.is_set():
                readable, _, _ = select.select(
                    [self._input_stream],
                    [],
                    [],
                    self._loop_interval_sec,
                )
                if readable:
                    key = os.read(fd, 1).decode("utf-8", errors="ignore")
                    if key == "":
                        break
                    action = self._controller.handle_key(key)
                    if action != "IGNORED":
                        print(f"[MANUAL] key={key!r} action={action}")
                result = self._controller.tick()
                if result is not None:
                    print(f"[MANUAL] action={result}")
        except (EOFError, KeyboardInterrupt):
            pass
        finally:
            if self._controller.active:
                self._controller.deactivate()
            termios.tcsetattr(fd, termios.TCSADRAIN, original_attributes)
