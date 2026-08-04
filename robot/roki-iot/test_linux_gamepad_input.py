from __future__ import annotations

import unittest

from integration.linux_gamepad_input import (
    GamepadSettings,
    GamepadState,
    JoystickEvent,
    JS_EVENT_AXIS,
    JS_EVENT_BUTTON,
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


class LinuxGamepadInputTest(unittest.TestCase):
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
        gamepad._state.update(  # type: ignore[attr-defined]
            JoystickEvent(1, JS_EVENT_BUTTON, settings.deadman_button)
        )
        gamepad._state.update(  # type: ignore[attr-defined]
            JoystickEvent(-32767, JS_EVENT_AXIS, settings.throttle_axis)
        )
        gamepad._apply_decision()  # type: ignore[attr-defined]
        gamepad._state.update(  # type: ignore[attr-defined]
            JoystickEvent(0, JS_EVENT_BUTTON, settings.deadman_button)
        )
        gamepad._apply_decision()  # type: ignore[attr-defined]
        gamepad._apply_decision()  # type: ignore[attr-defined]

        self.assertEqual(controller.keys, ["w", " "])


if __name__ == "__main__":
    unittest.main()
