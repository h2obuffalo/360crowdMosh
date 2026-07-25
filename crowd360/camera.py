"""Time-based virtual camera controllers for both source geometries."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import DirectorConfig
from .geometry import normalized_to_pitch, normalized_to_yaw
from .rendering import calculate_flat_crop, shortest_yaw_delta, wrap_degrees
from .targeting import CameraTarget


def _smooth_capped(delta: float, dt: float, time_constant: float, max_speed: float) -> float:
    if dt <= 0:
        return 0.0
    alpha = 1.0 - math.exp(-dt / max(1e-6, time_constant))
    wanted = delta * alpha
    limit = abs(max_speed) * dt
    return max(-limit, min(limit, wanted))


@dataclass(slots=True)
class EquirectangularCameraState:
    yaw_degrees: float
    pitch_degrees: float
    fov_degrees: float


class EquirectangularCameraController:
    def __init__(self, config: DirectorConfig):
        self.config = config
        self.state = EquirectangularCameraState(
            yaw_degrees=config.equirectangular_home_yaw_degrees,
            pitch_degrees=config.equirectangular_home_pitch_degrees,
            fov_degrees=config.equirectangular_home_fov_degrees,
        )

    @property
    def normalized_position(self) -> tuple[float, float]:
        x = ((self.state.yaw_degrees + 180.0) % 360.0) / 360.0
        y = (90.0 - self.state.pitch_degrees) / 180.0
        return x, min(1.0, max(0.0, y))

    def update(self, target: CameraTarget, dt: float) -> EquirectangularCameraState:
        target_yaw = normalized_to_yaw(target.center_x)
        target_pitch = min(
            self.config.pitch_max_degrees,
            max(self.config.pitch_min_degrees, normalized_to_pitch(target.center_y)),
        )
        target_fov = min(
            self.config.equirectangular_max_fov_degrees,
            max(self.config.equirectangular_min_fov_degrees, target.framing),
        )
        if target.hard_cut:
            self.state.yaw_degrees = target_yaw
            self.state.pitch_degrees = target_pitch
            self.state.fov_degrees = target_fov
            return self.state

        yaw_delta = shortest_yaw_delta(self.state.yaw_degrees, target_yaw)
        pitch_delta = target_pitch - self.state.pitch_degrees
        fov_delta = target_fov - self.state.fov_degrees
        if abs(yaw_delta) >= self.config.movement_deadband * 360.0:
            self.state.yaw_degrees = wrap_degrees(
                self.state.yaw_degrees
                + _smooth_capped(
                    yaw_delta,
                    dt,
                    self.config.smoothing_time_seconds,
                    self.config.equirectangular_max_pan_degrees_per_second,
                )
            )
        if abs(pitch_delta) >= self.config.movement_deadband * 180.0:
            self.state.pitch_degrees += _smooth_capped(
                pitch_delta,
                dt,
                self.config.smoothing_time_seconds,
                self.config.equirectangular_max_pitch_degrees_per_second,
            )
        if abs(fov_delta) >= self.config.zoom_deadband:
            self.state.fov_degrees += _smooth_capped(
                fov_delta,
                dt,
                self.config.smoothing_time_seconds,
                self.config.zoom_change_per_second
                * (
                    self.config.equirectangular_max_fov_degrees
                    - self.config.equirectangular_min_fov_degrees
                ),
            )
        self.state.pitch_degrees = min(
            self.config.pitch_max_degrees,
            max(self.config.pitch_min_degrees, self.state.pitch_degrees),
        )
        self.state.fov_degrees = min(
            self.config.equirectangular_max_fov_degrees,
            max(self.config.equirectangular_min_fov_degrees, self.state.fov_degrees),
        )
        return self.state


@dataclass(slots=True)
class FlatCameraState:
    center_x: float
    center_y: float
    crop_width_fraction: float


class FlatCameraController:
    def __init__(self, config: DirectorConfig):
        self.config = config
        self.state = FlatCameraState(
            center_x=config.flat_home_center_x,
            center_y=config.flat_home_center_y,
            crop_width_fraction=config.flat_wide_crop_width_fraction,
        )

    @property
    def normalized_position(self) -> tuple[float, float]:
        return self.state.center_x, self.state.center_y

    def update(
        self,
        target: CameraTarget,
        dt: float,
        source_width: int,
        source_height: int,
    ) -> FlatCameraState:
        target_crop = min(
            1.0,
            max(self.config.flat_min_crop_width_fraction, target.framing),
        )
        safe_x, safe_y = self._clamp_center(
            target.center_x,
            target.center_y,
            target_crop,
            source_width,
            source_height,
        )
        if target.hard_cut:
            self.state.center_x = safe_x
            self.state.center_y = safe_y
            self.state.crop_width_fraction = target_crop
            return self.state

        dx = safe_x - self.state.center_x
        dy = safe_y - self.state.center_y
        dz = target_crop - self.state.crop_width_fraction
        if abs(dx) >= self.config.movement_deadband:
            self.state.center_x += _smooth_capped(
                dx,
                dt,
                self.config.smoothing_time_seconds,
                self.config.flat_max_pan_normalized_per_second,
            )
        if abs(dy) >= self.config.movement_deadband:
            self.state.center_y += _smooth_capped(
                dy,
                dt,
                self.config.smoothing_time_seconds,
                self.config.flat_max_tilt_normalized_per_second,
            )
        if abs(dz) >= self.config.zoom_deadband:
            self.state.crop_width_fraction += _smooth_capped(
                dz,
                dt,
                self.config.smoothing_time_seconds,
                self.config.zoom_change_per_second,
            )
        self.state.crop_width_fraction = min(
            1.0,
            max(
                self.config.flat_min_crop_width_fraction,
                self.state.crop_width_fraction,
            ),
        )
        self.state.center_x, self.state.center_y = self._clamp_center(
            self.state.center_x,
            self.state.center_y,
            self.state.crop_width_fraction,
            source_width,
            source_height,
        )
        return self.state

    def _clamp_center(
        self,
        center_x: float,
        center_y: float,
        crop_width_fraction: float,
        source_width: int,
        source_height: int,
    ) -> tuple[float, float]:
        rect = calculate_flat_crop(
            source_width,
            source_height,
            self.config.output_width,
            self.config.output_height,
            0.5,
            0.5,
            crop_width_fraction,
            self.config.flat_aspect_mode,
        )
        half_x = rect.width / (2.0 * source_width)
        half_y = rect.height / (2.0 * source_height)
        return (
            min(1.0 - half_x, max(half_x, center_x)),
            min(1.0 - half_y, max(half_y, center_y)),
        )
