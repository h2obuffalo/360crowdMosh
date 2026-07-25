"""Geometry-specific output renderers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

from .config import DirectorConfig


def wrap_degrees(angle: float) -> float:
    return ((angle + 180.0) % 360.0) - 180.0


def shortest_yaw_delta(current: float, target: float) -> float:
    return wrap_degrees(target - current)


def lerp_angle_degrees(current: float, target: float, amount: float) -> float:
    return wrap_degrees(current + shortest_yaw_delta(current, target) * amount)


@lru_cache(maxsize=96)
def _camera_rays(
    width: int, height: int, fov_degrees: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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
    """Render one perspective view from a stitched equirectangular source."""
    src_h, src_w = frame_bgr.shape[:2]
    x, y, z = _camera_rays(out_width, out_height, round(float(fov_degrees), 4))
    yaw = math.radians(yaw_degrees)
    pitch = math.radians(pitch_degrees)

    cosy, siny = math.cos(yaw), math.sin(yaw)
    x1 = x * cosy + z * siny
    y1 = y
    z1 = -x * siny + z * cosy

    cosp, sinp = math.cos(pitch), math.sin(pitch)
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


@dataclass(frozen=True, slots=True)
class CropRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height


def calculate_flat_crop(
    source_width: int,
    source_height: int,
    output_width: int,
    output_height: int,
    center_x: float,
    center_y: float,
    crop_width_fraction: float,
    aspect_mode: str = "crop",
) -> CropRect:
    """Calculate a bounded source crop without stretching.

    In crop mode the largest output-aspect rectangle is the wide shot. In
    letterbox mode the wide shot is the whole source and the selected crop keeps
    the source aspect before being fitted into the output canvas.
    """
    if min(source_width, source_height, output_width, output_height) <= 0:
        raise ValueError("source and output dimensions must be positive")
    if not 0 < crop_width_fraction <= 1:
        raise ValueError("crop_width_fraction must be in (0, 1]")
    if aspect_mode not in {"crop", "letterbox"}:
        raise ValueError("aspect_mode must be crop or letterbox")

    output_aspect = output_width / float(output_height)
    source_aspect = source_width / float(source_height)
    if aspect_mode == "crop":
        if source_aspect >= output_aspect:
            max_height = source_height
            max_width = int(round(max_height * output_aspect))
        else:
            max_width = source_width
            max_height = int(round(max_width / output_aspect))
        crop_width = max(2, int(round(max_width * crop_width_fraction)))
        crop_height = max(2, int(round(crop_width / output_aspect)))
        if crop_height > max_height:
            crop_height = max_height
            crop_width = max(2, int(round(crop_height * output_aspect)))
    else:
        crop_width = max(2, int(round(source_width * crop_width_fraction)))
        crop_height = max(2, int(round(source_height * crop_width_fraction)))

    crop_width = min(source_width, crop_width)
    crop_height = min(source_height, crop_height)
    half_w = crop_width / 2.0
    half_h = crop_height / 2.0
    center_px = min(source_width - half_w, max(half_w, center_x * source_width))
    center_py = min(source_height - half_h, max(half_h, center_y * source_height))
    x = int(round(center_px - half_w))
    y = int(round(center_py - half_h))
    x = min(source_width - crop_width, max(0, x))
    y = min(source_height - crop_height, max(0, y))
    return CropRect(x=x, y=y, width=crop_width, height=crop_height)


class EquirectangularRenderer:
    def __init__(self, config: DirectorConfig):
        self.config = config

    def render(self, frame_bgr: np.ndarray, state: object) -> np.ndarray:
        return equirectangular_to_perspective(
            frame_bgr,
            yaw_degrees=float(getattr(state, "yaw_degrees")),
            pitch_degrees=float(getattr(state, "pitch_degrees")),
            fov_degrees=float(getattr(state, "fov_degrees")),
            out_width=int(self.config.output_width),
            out_height=int(self.config.output_height),
        )


class FlatCropRenderer:
    def __init__(self, config: DirectorConfig):
        self.config = config
        self.last_crop: CropRect | None = None

    def crop_for_state(self, frame_bgr: np.ndarray, state: object) -> CropRect:
        source_height, source_width = frame_bgr.shape[:2]
        return calculate_flat_crop(
            source_width,
            source_height,
            int(self.config.output_width),
            int(self.config.output_height),
            float(getattr(state, "center_x")),
            float(getattr(state, "center_y")),
            float(getattr(state, "crop_width_fraction")),
            self.config.flat_aspect_mode,
        )

    def render(self, frame_bgr: np.ndarray, state: object) -> np.ndarray:
        crop_rect = self.crop_for_state(frame_bgr, state)
        self.last_crop = crop_rect
        crop = frame_bgr[crop_rect.y : crop_rect.y2, crop_rect.x : crop_rect.x2]
        output_size = (int(self.config.output_width), int(self.config.output_height))
        if self.config.flat_aspect_mode == "crop":
            return cv2.resize(crop, output_size, interpolation=cv2.INTER_LINEAR)

        output = np.zeros(
            (int(self.config.output_height), int(self.config.output_width), 3),
            dtype=frame_bgr.dtype,
        )
        scale = min(
            self.config.output_width / float(crop_rect.width),
            self.config.output_height / float(crop_rect.height),
        )
        fitted_width = max(1, int(round(crop_rect.width * scale)))
        fitted_height = max(1, int(round(crop_rect.height * scale)))
        fitted = cv2.resize(crop, (fitted_width, fitted_height), interpolation=cv2.INTER_LINEAR)
        x = (self.config.output_width - fitted_width) // 2
        y = (self.config.output_height - fitted_height) // 2
        output[y : y + fitted_height, x : x + fitted_width] = fitted
        return output
