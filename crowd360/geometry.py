"""Input geometry detection and normalized coordinate helpers."""

from __future__ import annotations

import math
from typing import Literal

InputMode = Literal["auto", "equirectangular", "flat"]
ResolvedInputMode = Literal["equirectangular", "flat"]


def detect_input_mode(width: int, height: int, requested: InputMode = "auto") -> ResolvedInputMode:
    """Resolve geometry conservatively from frame dimensions."""
    if requested in ("equirectangular", "flat"):
        return requested
    if requested != "auto":
        raise ValueError("requested input mode must be auto, equirectangular or flat")
    if width <= 0 or height <= 0:
        raise ValueError("frame dimensions must be positive")
    ratio = width / float(height)
    return "equirectangular" if 1.85 <= ratio <= 2.15 else "flat"


def circular_delta(a: float, b: float) -> float:
    return ((b - a + 0.5) % 1.0) - 0.5


def circular_distance(a: float, b: float) -> float:
    return abs(circular_delta(a, b))


def normalized_to_yaw(x: float) -> float:
    return ((x % 1.0) * 360.0) - 180.0


def yaw_to_normalized(yaw_degrees: float) -> float:
    return ((yaw_degrees + 180.0) % 360.0) / 360.0


def normalized_to_pitch(y: float) -> float:
    return 90.0 - min(1.0, max(0.0, y)) * 180.0


def pitch_to_normalized(pitch_degrees: float) -> float:
    return min(1.0, max(0.0, (90.0 - pitch_degrees) / 180.0))


def region_distance(mode: ResolvedInputMode, current_x: float, current_y: float, target_x: float, target_y: float) -> float:
    dx = circular_distance(current_x, target_x) if mode == "equirectangular" else abs(target_x - current_x)
    return math.hypot(dx, target_y - current_y)
