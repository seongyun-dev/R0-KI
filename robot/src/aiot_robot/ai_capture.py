"""Validated capture settings for the external dual-camera AI pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CaptureSettings:
    width: int = 640
    height: int = 480
    fps: float = 30.0
    fourcc: str = "MJPG"
    buffer_size: int = 1

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1:
            raise ValueError("capture width and height must be positive")
        if self.fps <= 0:
            raise ValueError("capture fps must be positive")
        if len(self.fourcc) != 4 or not self.fourcc.isalnum():
            raise ValueError("capture fourcc must contain four alphanumeric characters")
        if self.buffer_size < 1:
            raise ValueError("capture buffer size must be positive")


def configure_capture(
    capture: Any,
    cv2_module: Any,
    settings: CaptureSettings,
) -> dict[str, float]:
    """Apply a deterministic format and reject a camera that ignores it.

    The external model code owns the ``VideoCapture`` object.  This function
    changes only capture properties after the pipeline opens the device; it does
    not open a second camera handle or modify the AI checkout.
    """

    fourcc = cv2_module.VideoWriter_fourcc(*settings.fourcc)
    requested = (
        (cv2_module.CAP_PROP_FOURCC, float(fourcc)),
        (cv2_module.CAP_PROP_FRAME_WIDTH, float(settings.width)),
        (cv2_module.CAP_PROP_FRAME_HEIGHT, float(settings.height)),
        (cv2_module.CAP_PROP_FPS, float(settings.fps)),
        (cv2_module.CAP_PROP_BUFFERSIZE, float(settings.buffer_size)),
    )
    for property_id, value in requested:
        capture.set(property_id, value)

    actual = {
        "width": float(capture.get(cv2_module.CAP_PROP_FRAME_WIDTH)),
        "height": float(capture.get(cv2_module.CAP_PROP_FRAME_HEIGHT)),
        "fps": float(capture.get(cv2_module.CAP_PROP_FPS)),
    }
    if round(actual["width"]) != settings.width:
        raise RuntimeError(
            f"camera width mismatch: requested={settings.width} "
            f"actual={actual['width']:.3f}"
        )
    if round(actual["height"]) != settings.height:
        raise RuntimeError(
            f"camera height mismatch: requested={settings.height} "
            f"actual={actual['height']:.3f}"
        )
    # Some V4L2/OpenCV combinations return 0 when FPS querying is unsupported.
    if actual["fps"] > 0 and abs(actual["fps"] - settings.fps) > 0.5:
        raise RuntimeError(
            f"camera fps mismatch: requested={settings.fps:.3f} "
            f"actual={actual['fps']:.3f}"
        )
    return actual
