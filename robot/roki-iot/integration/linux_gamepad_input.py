"""Linux joystick input for headless manual SLAM mapping.

The reader never opens Serial.  It translates a standard ``/dev/input/js*``
device into the same short, fail-safe motion pulses used by the manual drive
controller.  All button and axis indexes remain environment-configurable
because generic 2.4 GHz gamepads do not share one stable layout.
"""

from __future__ import annotations

import errno
import os
import select
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80
_EVENT = struct.Struct("<IhBB")
JS_EVENT_SIZE = _EVENT.size


@dataclass(frozen=True)
class GamepadSettings:
    device_path: str = "/dev/input/js0"
    steering_axis: int = 0
    throttle_axis: int = 1
    deadman_button: int = 4
    deadman_required: bool = True
    stop_button: int = 1
    finish_button_a: int = 6
    finish_button_b: int = 7
    deadzone: float = 0.35
    finish_hold_sec: float = 2.0
    loop_interval_sec: float = 0.05
    reconnect_interval_sec: float = 1.0
    # Linux js devices normally emit events only when a value changes.  A
    # positive lease is therefore an optional receiver-specific safety policy,
    # not a device-liveness check.  Zero keeps a held deadman/stick command
    # active while the device remains open; release, STOP and disconnect still
    # stop immediately.
    input_lease_sec: float = 0.0

    def __post_init__(self) -> None:
        if not self.device_path:
            raise ValueError("gamepad device_path is required")
        indexes = (
            self.steering_axis,
            self.throttle_axis,
            self.deadman_button,
            self.stop_button,
            self.finish_button_a,
            self.finish_button_b,
        )
        if any(index < 0 for index in indexes):
            raise ValueError("gamepad axis and button indexes must be non-negative")
        if not 0.0 < self.deadzone < 1.0:
            raise ValueError("gamepad deadzone must be between 0 and 1")
        if self.finish_hold_sec <= 0:
            raise ValueError("finish_hold_sec must be positive")
        if self.loop_interval_sec <= 0 or self.reconnect_interval_sec <= 0:
            raise ValueError("gamepad loop intervals must be positive")
        if self.input_lease_sec < 0:
            raise ValueError("gamepad input lease must not be negative")


@dataclass(frozen=True)
class JoystickEvent:
    value: int
    event_type: int
    number: int
    is_initial: bool = False

    @classmethod
    def decode(cls, raw: bytes) -> "JoystickEvent":
        if len(raw) != JS_EVENT_SIZE:
            raise ValueError("Linux joystick event must be exactly 8 bytes")
        _timestamp, value, event_type, number = _EVENT.unpack(raw)
        return cls(
            value,
            event_type & ~JS_EVENT_INIT,
            number,
            is_initial=bool(event_type & JS_EVENT_INIT),
        )


class GamepadState:
    """Pure state machine used by the device reader and unit tests."""

    def __init__(
        self,
        settings: GamepadSettings,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._axes: dict[int, float] = {}
        self._buttons: dict[int, bool] = {}
        self._finish_started: float | None = None
        self._finish_emitted = False
        self._armed = False

    def reset(self) -> None:
        self._axes.clear()
        self._buttons.clear()
        self._finish_started = None
        self._finish_emitted = False
        self._armed = False

    def disarm(self) -> None:
        """Require a neutral, released control state before motion resumes."""

        self._armed = False
        self._finish_started = None
        self._finish_emitted = False

    def update(self, event: JoystickEvent) -> None:
        safe_before_update = self._safe_to_arm()
        if event.event_type == JS_EVENT_AXIS:
            divisor = 32767.0 if event.value >= 0 else 32768.0
            self._axes[event.number] = max(-1.0, min(1.0, event.value / divisor))
        elif event.event_type == JS_EVENT_BUTTON:
            self._buttons[event.number] = event.value != 0
        if not event.is_initial and not self._armed:
            self._armed = safe_before_update or self._safe_to_arm()

    def decision(self) -> tuple[str | None, str | None, bool, bool]:
        """Return steering key, drive key, stop request and finish request."""

        if not self._armed:
            return None, None, True, False

        finish_pressed = self._button(self._settings.finish_button_a) and self._button(
            self._settings.finish_button_b
        )
        now = self._clock()
        finish = False
        if finish_pressed:
            if self._finish_started is None:
                self._finish_started = now
            elif (
                not self._finish_emitted
                and now - self._finish_started >= self._settings.finish_hold_sec
            ):
                self._finish_emitted = True
                finish = True
            return None, None, True, finish
        self._finish_started = None
        self._finish_emitted = False

        if self._button(self._settings.stop_button):
            return None, None, True, False
        if (
            self._settings.deadman_required
            and not self._button(self._settings.deadman_button)
        ):
            return None, None, True, False

        steering_value = self._axes.get(self._settings.steering_axis, 0.0)
        throttle_value = self._axes.get(self._settings.throttle_axis, 0.0)
        steering = None
        drive = None
        if steering_value <= -self._settings.deadzone:
            steering = "a"
        elif steering_value >= self._settings.deadzone:
            steering = "d"
        if throttle_value <= -self._settings.deadzone:
            drive = "w"
        elif throttle_value >= self._settings.deadzone:
            drive = "s"
        return steering, drive, drive is None and steering is None, False

    def _button(self, number: int) -> bool:
        return self._buttons.get(number, False)

    @property
    def finish_pressed(self) -> bool:
        return self._button(self._settings.finish_button_a) and self._button(
            self._settings.finish_button_b
        )

    def _safe_to_arm(self) -> bool:
        if any(
            self._button(number)
            for number in (
                self._settings.deadman_button,
                self._settings.stop_button,
                self._settings.finish_button_a,
                self._settings.finish_button_b,
            )
        ):
            return False
        return all(
            abs(self._axes.get(number, 0.0)) < self._settings.deadzone
            for number in (
                self._settings.steering_axis,
                self._settings.throttle_axis,
            )
        )


class LinuxGamepadInput:
    """Reconnectable Linux joystick reader with an optional deadman switch."""

    def __init__(
        self,
        controller: Any,
        *,
        settings: GamepadSettings,
        finish_callback: Callable[[], None],
        opener: Callable[[str, int], int] = os.open,
        reader: Callable[[int, int], bytes] = os.read,
        closer: Callable[[int], None] = os.close,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._controller = controller
        self._settings = settings
        self._finish_callback = finish_callback
        self._opener = opener
        self._reader = reader
        self._closer = closer
        self._clock = clock
        self._state = GamepadState(settings, clock=clock)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._file_descriptor: int | None = None
        self._command_active = False
        self._last_input_at: float | None = None
        self._diagnostic_lock = threading.Lock()
        self._last_decision: str | None = None
        self._last_decision_at: float | None = None

    @property
    def device_path(self) -> Path:
        return Path(self._settings.device_path)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        try:
            descriptor = self._open()
        except OSError as exc:
            raise RuntimeError(
                f"mapping gamepad is unavailable: {self._settings.device_path}"
            ) from exc
        self._file_descriptor = descriptor
        self._state.reset()
        self._command_active = False
        self._last_input_at = None
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="mapping-gamepad",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._safe_stop()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None

    def diagnostic_snapshot(self) -> dict[str, object]:
        """Return read-only liveness/input context without affecting control."""

        now = self._clock()
        with self._diagnostic_lock:
            decision = self._last_decision
            decision_at = self._last_decision_at
        thread = self._thread
        return {
            "gamepadDeviceOpen": self._file_descriptor is not None,
            "gamepadThreadAlive": thread is not None and thread.is_alive(),
            "lastGamepadDecision": decision or "unavailable",
            "lastGamepadDecisionAgoMs": (
                None
                if decision_at is None
                else round(max(0.0, (now - decision_at) * 1000.0), 3)
            ),
        }

    def _open(self) -> int:
        return self._opener(
            self._settings.device_path,
            os.O_RDONLY | os.O_NONBLOCK,
        )

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                if self._file_descriptor is None:
                    if self._stop_event.wait(self._settings.reconnect_interval_sec):
                        break
                    try:
                        self._file_descriptor = self._open()
                        self._state.reset()
                        self._last_input_at = None
                        print(f"[MAPPING] gamepad reconnected path={self.device_path}")
                    except OSError:
                        continue
                try:
                    self._read_available_events(self._file_descriptor)
                    self._apply_decision()
                except OSError as exc:
                    if exc.errno not in {
                        errno.EAGAIN,
                        errno.EWOULDBLOCK,
                        errno.ENODEV,
                        errno.EIO,
                        errno.EBADF,
                    }:
                        raise
                    if exc.errno not in {errno.EAGAIN, errno.EWOULDBLOCK}:
                        print("[MAPPING] gamepad disconnected; motion stopped")
                        self._close_device()
                        self._state.reset()
                        self._last_input_at = None
                        self._safe_stop()
                self._stop_event.wait(self._settings.loop_interval_sec)
        finally:
            self._safe_stop()
            self._close_device()

    def _read_available_events(self, descriptor: int) -> None:
        readable, _, _ = select.select([descriptor], [], [], 0)
        if not readable:
            return
        while True:
            try:
                raw = self._reader(descriptor, JS_EVENT_SIZE)
            except BlockingIOError:
                return
            if raw == b"":
                raise OSError(errno.ENODEV, "gamepad disconnected")
            self._accept_event(JoystickEvent.decode(raw))

    def _accept_event(self, event: JoystickEvent) -> None:
        self._state.update(event)
        if not event.is_initial:
            self._last_input_at = self._clock()

    def _apply_decision(self) -> None:
        lease_enabled = self._settings.input_lease_sec > 0
        lease_expired = (
            self._last_input_at is None
            or self._clock() - self._last_input_at
            > self._settings.input_lease_sec
        )
        if lease_enabled and lease_expired and not self._state.finish_pressed:
            self._state.disarm()
            if self._command_active:
                self._record_decision("LEASE_STOP")
            self._safe_stop()
            self._controller.tick()
            return
        steering, drive, stop, finish = self._state.decision()
        if stop:
            if self._command_active:
                self._record_decision("STOP")
            self._safe_stop()
        else:
            decisions: list[str] = []
            if steering is not None:
                self._controller.handle_key(steering)
                self._command_active = True
                decisions.append(steering.upper())
            if drive is not None:
                self._controller.handle_key(drive)
                self._command_active = True
                decisions.append(drive.upper())
            if decisions:
                self._record_decision("+".join(decisions))
        result = self._controller.tick()
        if result is not None:
            self._command_active = False
        if finish:
            self._record_decision("FINISH")
            self._stop_event.set()
            threading.Thread(
                target=self._finish_callback,
                name="mapping-finish-request",
                daemon=True,
            ).start()

    def _safe_stop(self) -> None:
        # A released deadman is evaluated every loop.  Emit one STOP on the
        # transition instead of flooding the ESP32 while the stick is idle.
        if self._command_active:
            self._controller.handle_key(" ")
        self._command_active = False

    def _record_decision(self, decision: str) -> None:
        now = self._clock()
        with self._diagnostic_lock:
            self._last_decision = decision
            self._last_decision_at = now

    def _close_device(self) -> None:
        descriptor = self._file_descriptor
        self._file_descriptor = None
        if descriptor is None:
            return
        try:
            self._closer(descriptor)
        except OSError:
            pass
