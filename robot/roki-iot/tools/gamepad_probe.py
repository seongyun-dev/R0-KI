#!/usr/bin/env python3
"""Print Linux joystick axis/button numbers without touching Robot hardware."""

from __future__ import annotations

import argparse
import os
import select

from integration.linux_gamepad_input import (
    JS_EVENT_AXIS,
    JS_EVENT_BUTTON,
    JS_EVENT_SIZE,
    JoystickEvent,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="read-only /dev/input/js* event probe; Ctrl-C exits"
    )
    parser.add_argument("--device", default="/dev/input/js0")
    args = parser.parse_args()

    descriptor = os.open(args.device, os.O_RDONLY | os.O_NONBLOCK)
    print(f"reading {args.device}; no Serial or motor command will be sent")
    try:
        while True:
            readable, _, _ = select.select([descriptor], [], [], 1.0)
            if not readable:
                continue
            raw = os.read(descriptor, JS_EVENT_SIZE)
            if raw == b"":
                raise RuntimeError("gamepad disconnected")
            event = JoystickEvent.decode(raw)
            if event.event_type == JS_EVENT_AXIS:
                divisor = 32767.0 if event.value >= 0 else 32768.0
                print(
                    f"axis number={event.number} "
                    f"value={event.value / divisor:+.3f}"
                )
            elif event.event_type == JS_EVENT_BUTTON:
                print(
                    f"button number={event.number} "
                    f"pressed={event.value != 0}"
                )
    except KeyboardInterrupt:
        return 0
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
