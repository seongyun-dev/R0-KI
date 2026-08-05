from __future__ import annotations

import threading
import unittest

from integration.linux_gamepad_input import (
    GamepadSettings,
    GamepadState,
    JoystickEvent,
    JS_EVENT_AXIS,
    JS_EVENT_BUTTON,
    JS_EVENT_INIT,
    LinuxGamepadInput,
)


class GamepadStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 0.0
        self.settings = GamepadSettings(finish_hold_sec=2.0)
        self.state = GamepadState(self.settings, clock=lambda: self.now)

    def button(self, number: int, pressed: bool = True) -> None:
        self.state.update(
            JoystickEvent(1 if pressed else 0, JS_EVENT_BUTTON, number)
        )

    def axis(self, number: int, value: int) -> None:
        self.state.update(JoystickEvent(value, JS_EVENT_AXIS, number))

    def test_deadman_is_required_for_motion(self) -> None:
        self.axis(self.settings.throttle_axis, -32767)
        self.assertEqual(self.state.decision(), (None, None, True, False))

        self.button(self.settings.deadman_button)
        self.assertEqual(self.state.decision(), (None, "w", False, False))

    def test_deadman_can_be_disabled_for_field_rc_control(self) -> None:
        settings = GamepadSettings(deadman_required=False)
        state = GamepadState(settings)
        state.update(JoystickEvent(0, JS_EVENT_AXIS, settings.throttle_axis))
        state.update(JoystickEvent(-32767, JS_EVENT_AXIS, settings.throttle_axis))

        self.assertEqual(state.decision(), (None, "w", False, False))

    def test_axes_map_to_reverse_and_right_steering(self) -> None:
        self.button(self.settings.deadman_button)
        self.axis(self.settings.throttle_axis, 32767)
        self.axis(self.settings.steering_axis, 32767)
        self.assertEqual(self.state.decision(), ("d", "s", False, False))

    def test_stop_button_overrides_deadman_and_axes(self) -> None:
        self.button(self.settings.deadman_button)
        self.axis(self.settings.throttle_axis, -32767)
        self.button(self.settings.stop_button)
        self.assertEqual(self.state.decision(), (None, None, True, False))

    def test_finish_requires_two_button_hold(self) -> None:
        self.button(self.settings.finish_button_a)
        self.button(self.settings.finish_button_b)
        self.assertEqual(self.state.decision(), (None, None, True, False))
        self.now = 1.9
        self.assertEqual(self.state.decision(), (None, None, True, False))
        self.now = 2.0
        self.assertEqual(self.state.decision(), (None, None, True, True))
        self.assertEqual(self.state.decision(), (None, None, True, False))

    def test_init_events_cannot_restore_held_motion(self) -> None:
        self.state.update(
            JoystickEvent(
                1,
                JS_EVENT_BUTTON,
                self.settings.deadman_button,
                is_initial=True,
            )
        )
        self.state.update(
            JoystickEvent(
                -32767,
                JS_EVENT_AXIS,
                self.settings.throttle_axis,
                is_initial=True,
            )
        )

        self.assertEqual(self.state.decision(), (None, None, True, False))

        self.button(self.settings.deadman_button, False)
        self.axis(self.settings.throttle_axis, 0)
        self.button(self.settings.deadman_button)
        self.axis(self.settings.throttle_axis, -32767)
        self.assertEqual(self.state.decision(), (None, "w", False, False))

    def test_decode_preserves_init_flag(self) -> None:
        import struct

        raw = struct.pack(
            "<IhBB",
            1,
            1,
            JS_EVENT_BUTTON | JS_EVENT_INIT,
            self.settings.deadman_button,
        )

        event = JoystickEvent.decode(raw)

        self.assertEqual(event.event_type, JS_EVENT_BUTTON)
        self.assertTrue(event.is_initial)


class LinuxGamepadInputTest(unittest.TestCase):
    def test_diagnostic_snapshot_tracks_latest_motion_decision(self) -> None:
        class FakeController:
            def handle_key(self, _key: str) -> None:
                pass

            def tick(self):
                return None

        now = 1.0
        settings = GamepadSettings()
        gamepad = LinuxGamepadInput(
            FakeController(),
            settings=settings,
            finish_callback=lambda: None,
            clock=lambda: now,
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(1, JS_EVENT_BUTTON, settings.deadman_button)
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(-32767, JS_EVENT_AXIS, settings.throttle_axis)
        )
        gamepad._apply_decision()  # type: ignore[attr-defined]
        now = 1.25

        snapshot = gamepad.diagnostic_snapshot()

        self.assertEqual(snapshot["lastGamepadDecision"], "W")
        self.assertEqual(snapshot["lastGamepadDecisionAgoMs"], 250.0)
        self.assertFalse(snapshot["gamepadDeviceOpen"])
        self.assertFalse(snapshot["gamepadThreadAlive"])

    def test_default_holds_command_while_device_remains_connected(self) -> None:
        class FakeController:
            def __init__(self) -> None:
                self.keys: list[str] = []

            def handle_key(self, key: str) -> None:
                self.keys.append(key)

            def tick(self):
                return None

        now = 0.0
        controller = FakeController()
        settings = GamepadSettings()
        gamepad = LinuxGamepadInput(
            controller,
            settings=settings,
            finish_callback=lambda: None,
            clock=lambda: now,
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(1, JS_EVENT_BUTTON, settings.deadman_button)
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(-32767, JS_EVENT_AXIS, settings.throttle_axis)
        )

        gamepad._apply_decision()  # type: ignore[attr-defined]
        now = 1.0
        gamepad._apply_decision()  # type: ignore[attr-defined]
        now = 30.0
        gamepad._apply_decision()  # type: ignore[attr-defined]

        self.assertEqual(settings.input_lease_sec, 0.0)
        self.assertEqual(controller.keys, ["w", "w", "w"])

    def test_deadman_release_emits_only_one_stop(self) -> None:
        class FakeController:
            active = True

            def __init__(self) -> None:
                self.keys: list[str] = []

            def handle_key(self, key: str) -> None:
                self.keys.append(key)

            def tick(self):
                return None

        controller = FakeController()
        settings = GamepadSettings()
        gamepad = LinuxGamepadInput(
            controller,
            settings=settings,
            finish_callback=lambda: None,
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(1, JS_EVENT_BUTTON, settings.deadman_button)
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(-32767, JS_EVENT_AXIS, settings.throttle_axis)
        )
        gamepad._apply_decision()  # type: ignore[attr-defined]
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(0, JS_EVENT_BUTTON, settings.deadman_button)
        )
        gamepad._apply_decision()  # type: ignore[attr-defined]
        gamepad._apply_decision()  # type: ignore[attr-defined]

        self.assertEqual(controller.keys, ["w", " "])

    def test_silent_input_expires_motion_and_requires_rearming(self) -> None:
        class FakeController:
            def __init__(self) -> None:
                self.keys: list[str] = []

            def handle_key(self, key: str) -> None:
                self.keys.append(key)

            def tick(self):
                return None

        now = 0.0
        controller = FakeController()
        settings = GamepadSettings(input_lease_sec=0.2)
        gamepad = LinuxGamepadInput(
            controller,
            settings=settings,
            finish_callback=lambda: None,
            clock=lambda: now,
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(1, JS_EVENT_BUTTON, settings.deadman_button)
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(-32767, JS_EVENT_AXIS, settings.throttle_axis)
        )
        gamepad._apply_decision()  # type: ignore[attr-defined]

        now = 0.21
        gamepad._apply_decision()  # type: ignore[attr-defined]
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(-32767, JS_EVENT_AXIS, settings.throttle_axis)
        )
        gamepad._apply_decision()  # type: ignore[attr-defined]

        self.assertEqual(controller.keys, ["w", " "])

        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(0, JS_EVENT_BUTTON, settings.deadman_button)
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(0, JS_EVENT_AXIS, settings.throttle_axis)
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(1, JS_EVENT_BUTTON, settings.deadman_button)
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(-32767, JS_EVENT_AXIS, settings.throttle_axis)
        )
        gamepad._apply_decision()  # type: ignore[attr-defined]

        self.assertEqual(controller.keys, ["w", " ", "w"])

    def test_finish_callback_runs_outside_the_reader_thread(self) -> None:
        class FakeController:
            def handle_key(self, _key: str) -> None:
                pass

            def tick(self):
                return None

        now = 0.0
        callback_completed = threading.Event()
        callback_threads: list[str] = []

        def finish() -> None:
            callback_threads.append(threading.current_thread().name)
            callback_completed.set()

        settings = GamepadSettings(finish_hold_sec=0.1, input_lease_sec=0.05)
        gamepad = LinuxGamepadInput(
            FakeController(),
            settings=settings,
            finish_callback=finish,
            clock=lambda: now,
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(1, JS_EVENT_BUTTON, settings.finish_button_a)
        )
        gamepad._accept_event(  # type: ignore[attr-defined]
            JoystickEvent(1, JS_EVENT_BUTTON, settings.finish_button_b)
        )
        gamepad._apply_decision()  # type: ignore[attr-defined]
        now = 0.1
        gamepad._apply_decision()  # type: ignore[attr-defined]

        self.assertTrue(callback_completed.wait(timeout=1.0))
        self.assertEqual(callback_threads, ["mapping-finish-request"])


if __name__ == "__main__":
    unittest.main()
