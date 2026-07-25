"""Diagnostic source/activity/output preview rendering."""

from __future__ import annotations

import cv2
import numpy as np

from .activity import ActivitySnapshot
from .config import DirectorConfig
from .director import DirectorFrame
from .geometry import ResolvedInputMode
from .rendering import CropRect
from .sources import SourceInfo


def _draw_wrapped_rect(
    image: np.ndarray,
    x: float,
    y: float,
    width: float,
    height: float,
    colour: tuple[int, int, int],
    thickness: int,
) -> None:
    image_height, image_width = image.shape[:2]
    y0 = int(y * image_height)
    y1 = int(min(1.0, y + height) * image_height)
    x0 = int((x % 1.0) * image_width)
    x_end = x + width
    if x_end <= 1.0:
        cv2.rectangle(image, (x0, y0), (int(x_end * image_width), y1), colour, thickness)
    else:
        cv2.rectangle(image, (x0, y0), (image_width - 1, y1), colour, thickness)
        cv2.rectangle(image, (0, y0), (int((x_end - 1.0) * image_width), y1), colour, thickness)


def draw_source_overlay(
    source: np.ndarray,
    config: DirectorConfig,
    mode: ResolvedInputMode,
    result: DirectorFrame,
    crop: CropRect | None,
) -> np.ndarray:
    overlay = source.copy()
    for rect in config.ignored_rects:
        x, y, width, height = rect
        if mode == "equirectangular":
            _draw_wrapped_rect(overlay, x, y, width, height, (80, 80, 255), 2)
        else:
            h, w = overlay.shape[:2]
            cv2.rectangle(
                overlay,
                (int(x * w), int(y * h)),
                (int(min(1.0, x + width) * w), int((y + height) * h)),
                (80, 80, 255),
                2,
            )
    for region in result.snapshot.regions[:12]:
        colour = (0, 255, 255) if region.score >= config.minimum_activity_score else (100, 100, 100)
        _draw_wrapped_rect(
            overlay,
            region.x,
            region.y,
            region.width,
            region.height,
            colour,
            1,
        )
        cv2.putText(
            overlay,
            f"{region.score:.1f}",
            (int(region.center_x * overlay.shape[1]), int(region.center_y * overlay.shape[0])),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            colour,
            1,
            cv2.LINE_AA,
        )
    target = result.decision.selected
    cv2.circle(
        overlay,
        (int(target.center_x * overlay.shape[1]), int(target.center_y * overlay.shape[0])),
        10,
        (0, 255, 0),
        2,
    )
    if mode == "flat" and crop is not None:
        cv2.rectangle(
            overlay,
            (crop.x, crop.y),
            (crop.x2, crop.y2),
            (255, 0, 255),
            3,
        )
    elif mode == "equirectangular":
        state = result.camera_state
        viewport_width = float(getattr(state, "fov_degrees")) / 360.0
        viewport_height = min(1.0, viewport_width * overlay.shape[1] / overlay.shape[0] * 0.5)
        center_x = ((float(getattr(state, "yaw_degrees")) + 180.0) % 360.0) / 360.0
        center_y = (90.0 - float(getattr(state, "pitch_degrees"))) / 180.0
        _draw_wrapped_rect(
            overlay,
            (center_x - viewport_width / 2.0) % 1.0,
            max(0.0, center_y - viewport_height / 2.0),
            viewport_width,
            viewport_height,
            (255, 0, 255),
            3,
        )
    return overlay


def render_diagnostics(
    source: np.ndarray,
    result: DirectorFrame,
    config: DirectorConfig,
    mode: ResolvedInputMode,
    source_info: SourceInfo,
    crop: CropRect | None = None,
    output_fps: float = 0.0,
) -> np.ndarray:
    source_panel = draw_source_overlay(source, config, mode, result, crop)
    heat = np.clip(result.snapshot.heatmap * 2.55, 0, 255).astype(np.uint8)
    heat = cv2.applyColorMap(heat, cv2.COLORMAP_INFERNO)
    heat = cv2.resize(heat, (source_panel.shape[1], source_panel.shape[0]))
    output_panel = cv2.resize(result.output, (source_panel.shape[1], source_panel.shape[0]))
    tiled = np.hstack((source_panel, heat, output_panel))
    lines = [
        f"mode={mode} target={result.decision.reason} score={result.decision.selected.score:.2f}",
        f"source={source_info.width}x{source_info.height} reported={source_info.reported_fps:.2f} read={source_info.effective_read_fps:.2f} output={output_fps:.2f}",
        f"analysis={config.analysis_fps:.1f}fps process={result.processing_ms:.1f}ms skipped={result.snapshot.skipped_analysis_frames} dropped={source_info.dropped_frames}",
        f"global-flash={'YES' if result.snapshot.global_flash else 'no'} confidence={result.snapshot.confidence_scale:.2f} connected={source_info.connected}",
    ]
    for index, line in enumerate(lines):
        cv2.putText(
            tiled,
            line,
            (12, 25 + index * 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return tiled
