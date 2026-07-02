"""Equirectangular 360 -> perspective reframe helpers.

This keeps the maths local and dependency-light so the first prototype can run
from ordinary stitched 360 files without a specialist 360 SDK.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Tuple

import cv2
import numpy as np


def wrap_degrees(angle: float) -> float:
    """Wrap angle to [-180, 180)."""
    return ((angle + 180.0) % 360.0) - 180.0


def lerp_angle_degrees(current: float, target: float, amount: float) -> float:
    """Shortest-path angular interpolation in degrees."""
    delta = wrap_degrees(target - current)
    return wrap_degrees(current + delta * amount)


@lru_cache(maxsize=64)
def _camera_rays(width: int, height: int, fov_degrees: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build normalized camera rays for a perspective viewport.

    The FOV is horizontal. Vertical FOV is derived from aspect ratio.
    """
    hfov = math.radians(fov_degrees)
    aspect = height / float(width)
    vfov = 2.0 * math.atan(math.tan(hfov / 2.0) * aspect)

    xs = np.linspace(-math.tan(hfov / 2.0), math.tan(hfov / 2.0), width, dtype=np.float32)
    ys = np.linspace(math.tan(vfov / 2.0), -math.tan(vfov / 2.0), height, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)
    zv = np.ones_like(xv, dtype=np.float32)

    norm = np.sqrt(xv * xv + yv * yv + zv * zv)
    return xv / norm, yv / norm, zv / norm


def equirectangular_to_perspective(
    frame_bgr: np.ndarray,
    yaw_degrees: float,
    pitch_degrees: float,
    fov_degrees: float,
    out_width: int,
    out_height: int,
) -> np.ndarray:
    """Render a perspective view from an equirectangular 360 frame.

    yaw_degrees: horizontal look direction. 0 is the centre of the equirectangular frame.
    pitch_degrees: vertical look direction. Positive looks up.
    fov_degrees: horizontal field of view. Smaller means more zoomed in.
    """
    src_h, src_w = frame_bgr.shape[:2]
    x, y, z = _camera_rays(out_width, out_height, float(fov_degrees))

    yaw = math.radians(yaw_degrees)
    pitch = math.radians(pitch_degrees)

    # Rotate around Y for yaw.
    cosy = math.cos(yaw)
    siny = math.sin(yaw)
    x1 = x * cosy + z * siny
    y1 = y
    z1 = -x * siny + z * cosy

    # Rotate around X for pitch.
    cosp = math.cos(pitch)
    sinp = math.sin(pitch)
    x2 = x1
    y2 = y1 * cosp - z1 * sinp
    z2 = y1 * sinp + z1 * cosp

    lon = np.arctan2(x2, z2)
    lat = np.arctan2(y2, np.sqrt(x2 * x2 + z2 * z2))

    map_x = ((lon + math.pi) / (2.0 * math.pi) * src_w).astype(np.float32)
    map_y = ((math.pi / 2.0 - lat) / math.pi * src_h).astype(np.float32)

    return cv2.remap(
        frame_bgr,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_WRAP,
    )
