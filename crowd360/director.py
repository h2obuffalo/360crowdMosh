"""High-level orchestration of analysis, selection, movement and rendering."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .activity import ActivityAnalyser, ActivitySnapshot
from .camera import (
    EquirectangularCameraController,
    EquirectangularCameraState,
    FlatCameraController,
    FlatCameraState,
)
from .config import DirectorConfig
from .geometry import ResolvedInputMode
from .rendering import EquirectangularRenderer, FlatCropRenderer
from .targeting import CameraTarget, SelectionDecision, TargetSelector


@dataclass(slots=True)
class DirectorFrame:
    output: np.ndarray
    snapshot: ActivitySnapshot
    decision: SelectionDecision
    camera_state: EquirectangularCameraState | FlatCameraState
    processing_ms: float


class MotionCrowdDirector:
    """Shared director with geometry-specific controllers and renderers."""

    def __init__(self, config: DirectorConfig, input_mode: ResolvedInputMode):
        self.config = config.validate()
        self.input_mode = input_mode
        self.analyser = ActivityAnalyser(config, input_mode)
        self.selector = TargetSelector(config, input_mode)
        if input_mode == "equirectangular":
            self.camera = EquirectangularCameraController(config)
            self.renderer = EquirectangularRenderer(config)
        else:
            self.camera = FlatCameraController(config)
            self.renderer = FlatCropRenderer(config)
        self._last_frame_timestamp: float | None = None
        self._last_target_evaluation: float | None = None
        self._decision: SelectionDecision | None = None

    def update(
        self,
        frame_bgr: np.ndarray,
        timestamp: float,
        fallback_dt: float = 1.0 / 25.0,
    ) -> DirectorFrame:
        started = time.perf_counter()
        snapshot = self.analyser.process_if_due(frame_bgr, timestamp)
        dt = (
            fallback_dt
            if self._last_frame_timestamp is None
            else max(1e-6, timestamp - self._last_frame_timestamp)
        )
        self._last_frame_timestamp = timestamp
        camera_x, camera_y = self.camera.normalized_position
        evaluation_due = (
            self._last_target_evaluation is None
            or timestamp - self._last_target_evaluation
            >= (1.0 / self.config.target_evaluation_fps) - 1e-9
        )
        if evaluation_due:
            self._decision = self.selector.evaluate(
                snapshot, timestamp, camera_x, camera_y
            )
            self._last_target_evaluation = timestamp
        if self._decision is None:
            self._decision = self.selector.evaluate(
                snapshot, timestamp, camera_x, camera_y
            )
        target = self._decision.selected

        if self.input_mode == "equirectangular":
            state = self.camera.update(target, dt)  # type: ignore[arg-type]
        else:
            source_height, source_width = frame_bgr.shape[:2]
            state = self.camera.update(  # type: ignore[union-attr]
                target,
                dt,
                source_width,
                source_height,
            )
        output = self.renderer.render(frame_bgr, state)
        return DirectorFrame(
            output=output,
            snapshot=snapshot,
            decision=self._decision,
            camera_state=state,
            processing_ms=(time.perf_counter() - started) * 1000.0,
        )

    @property
    def current_target(self) -> CameraTarget | None:
        return self.selector.current
