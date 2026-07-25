"""Compatibility facade for the original prototype API."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .config import DirectorConfig
from .director import MotionCrowdDirector as CoreMotionCrowdDirector
from .geometry import ResolvedInputMode


@dataclass(frozen=True, slots=True)
class Target:
    yaw: float
    pitch: float
    fov: float
    score: float


class MotionCrowdDirector:
    """Preserve ``update``/``render_output`` while using the new architecture."""

    def __init__(
        self,
        config: DirectorConfig,
        input_mode: ResolvedInputMode = "equirectangular",
    ):
        self.config = config
        self.input_mode = input_mode
        self._core = CoreMotionCrowdDirector(config, input_mode)
        self._last_result = None
        self._timestamp = 0.0

    def update(self, frame_bgr: np.ndarray, timestamp: float | None = None) -> Target:
        if timestamp is None:
            timestamp = self._timestamp
            self._timestamp += 1.0 / float(self.config.output_fps or 25.0)
        self._last_result = self._core.update(frame_bgr, timestamp)
        state = self._last_result.camera_state
        if self.input_mode == "equirectangular":
            return Target(
                float(getattr(state, "yaw_degrees")),
                float(getattr(state, "pitch_degrees")),
                float(getattr(state, "fov_degrees")),
                self._last_result.decision.selected.score,
            )
        return Target(
            float(getattr(state, "center_x")),
            float(getattr(state, "center_y")),
            float(getattr(state, "crop_width_fraction")),
            self._last_result.decision.selected.score,
        )

    def render_output(self, frame_bgr: np.ndarray) -> np.ndarray:
        if self._last_result is None:
            self.update(frame_bgr, time.monotonic())
        assert self._last_result is not None
        return self._last_result.output
