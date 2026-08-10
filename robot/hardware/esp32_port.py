#!/usr/bin/env python3
"""Resolve the ESP32 serial device without confusing it with the LiDAR.

The assembled robot has two CP2102 devices whose factory serial number is
``0001``.  Linux therefore cannot provide a unique ``/dev/serial/by-id``
symlink for them.  Production uses the udev-created ``/dev/roki_esp32`` alias;
an explicit CLI path or ``ESP32_PORT`` may override it for diagnostics.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

from serial.tools import list_ports


ESP32_ALIAS = "/dev/roki_esp32"
CP2102_BY_ID_GLOB = (
    "/dev/serial/by-id/"
    "usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_*-if00-port0"
)
CP2102_VID = 0x10C4
CP2102_PID = 0xEA60


class Esp32PortError(RuntimeError):
    """Raised when the ESP32 serial device cannot be selected safely."""


def _existing(path: str) -> str | None:
    return path if Path(path).exists() else None


def resolve_esp32_port(explicit_port: str | None = None) -> str:
    """Return a safe ESP32 port or fail closed when identity is ambiguous."""

    configured = explicit_port or os.getenv("ESP32_PORT")
    if configured:
        if selected := _existing(configured):
            return selected
        raise Esp32PortError(f"Configured ESP32 port does not exist: {configured}")

    if selected := _existing(ESP32_ALIAS):
        return selected

    cp2102_ports = sorted(
        port.device
        for port in list_ports.comports()
        if port.vid == CP2102_VID and port.pid == CP2102_PID
    )
    if len(cp2102_ports) > 1:
        raise Esp32PortError(
            "Multiple indistinguishable CP2102 devices are connected: "
            f"{cp2102_ports}. Install the RO-KI udev aliases or pass "
            "--port/ESP32_PORT explicitly; refusing to guess."
        )

    by_id_matches = sorted(glob.glob(CP2102_BY_ID_GLOB))
    if len(cp2102_ports) == 1 and len(by_id_matches) == 1:
        return by_id_matches[0]
    if len(cp2102_ports) == 1:
        return cp2102_ports[0]

    raise Esp32PortError(
        "ESP32 was not found. Expected /dev/roki_esp32 or one CP2102 device."
    )
