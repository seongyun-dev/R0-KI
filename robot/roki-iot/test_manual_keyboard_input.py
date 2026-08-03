from __future__ import annotations

import unittest
from unittest.mock import Mock

from integration.manual_keyboard_input import ManualKeyboardInput


class ManualKeyboardInputTest(unittest.TestCase):
    def test_background_service_without_tty_fails_before_thread_start(self) -> None:
        controller = Mock()
        stream = Mock()
        stream.isatty.return_value = False
        keyboard = ManualKeyboardInput(controller, input_stream=stream)

        with self.assertRaisesRegex(RuntimeError, "foreground TTY"):
            keyboard.start()


if __name__ == "__main__":
    unittest.main()
