"""Continuous motion/activity analysis in normalized source coordinates."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Iterable

import cv2
import numpy as np

from .config import DirectorConfig, Rect
from .geometry import ResolvedInputMode


@dataclass(frozen=True, slots=True)
class ActivityRegion:
    x: float
    y: float
    width: float
    height: float
    center_x: float
    center_y: float
    score: float
    moving_fraction: float


@dataclass(slots=True)
class ActivitySnapshot:
    heatmap: np.ndarray
    motion_mask: np.ndarray
    regions: list[ActivityRegion] = field(default_factory=list)
    global_flash: bool = False
    confidence_scale: float = 1.0
    timestamp: float = 0.0
    processing_ms: float = 0.0
    skipped_analysis_frames: int = 0


class ActivityAnalyser:
    """Analyse each source once, independently of target evaluation.

    The analyser owns reusable CLAHE/morphology objects and stores a decaying
    activity heatmap. Coordinates exposed by regions are normalized against the
    original source geometry, so the selector can be shared by flat and 360
    inputs.
    """

    def __init__(self, config: DirectorConfig, mode: ResolvedInputMode):
        self.config = config
        self.mode = mode
        self._previous_gray: np.ndarray | None = None
        self._heatmap = np.zeros(
            (int(config.analysis_height), int(config.analysis_width)), dtype=np.float32
        )
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self._kernel = np.ones((3, 3), dtype=np.uint8)
        self._last_analysis_at: float | None = None
        self._flash_until = 0.0
        self._skipped = 0
        self.last_snapshot = ActivitySnapshot(
            heatmap=self._heatmap.copy(),
            motion_mask=np.zeros_like(self._heatmap, dtype=np.uint8),
        )

    def due(self, timestamp: float) -> bool:
        if self._last_analysis_at is None:
            return True
        return timestamp - self._last_analysis_at >= (1.0 / self.config.analysis_fps) - 1e-9

    def process_if_due(self, frame_bgr: np.ndarray, timestamp: float) -> ActivitySnapshot:
        if not self.due(timestamp):
            self._skipped += 1
            self.last_snapshot.skipped_analysis_frames = self._skipped
            return self.last_snapshot
        return self.update(frame_bgr, timestamp)

    def update(self, frame_bgr: np.ndarray, timestamp: float) -> ActivitySnapshot:
        started = time.perf_counter()
        if frame_bgr.ndim != 3 or frame_bgr.shape[2] < 3:
            raise ValueError("ActivityAnalyser expects a BGR colour frame")
        resized = cv2.resize(
            frame_bgr,
            (int(self.config.analysis_width), int(self.config.analysis_height)),
            interpolation=cv2.INTER_AREA,
        )
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        if self.config.contrast_boost:
            gray = self._clahe.apply(gray)
        if self.config.brightness_floor > 0:
            gray = gray.copy()
            gray[gray < int(self.config.brightness_floor)] = 0

        previous_at = self._last_analysis_at
        dt = 0.0 if previous_at is None else max(0.0, timestamp - previous_at)
        self._last_analysis_at = timestamp
        decay = 0.0 if previous_at is None else math.exp(-dt / self.config.motion_decay_seconds)
        self._heatmap *= decay

        if self._previous_gray is None:
            motion = np.zeros_like(gray, dtype=np.uint8)
            global_flash = False
            confidence_scale = 1.0
        else:
            signed = gray.astype(np.int16) - self._previous_gray.astype(np.int16)
            raw_diff = np.abs(signed)
            raw_changed_fraction = float(
                np.count_nonzero(raw_diff >= self.config.motion_threshold)
            ) / float(raw_diff.size)

            # A lighting change is mostly a common-mode signal. Remove the
            # median signed shift before thresholding local residual movement.
            global_shift = float(np.median(signed))
            residual = np.abs(signed.astype(np.float32) - global_shift)
            motion = np.where(residual >= self.config.motion_threshold, 255, 0).astype(np.uint8)
            motion = cv2.morphologyEx(motion, cv2.MORPH_OPEN, self._kernel)
            motion = self._remove_small_components(motion)

            global_flash = raw_changed_fraction >= self.config.global_flash_fraction
            if global_flash:
                self._flash_until = max(
                    self._flash_until,
                    timestamp + self.config.global_flash_recovery_seconds,
                )
            confidence_scale = (
                self.config.global_flash_confidence_scale
                if timestamp < self._flash_until
                else 1.0
            )

        self._previous_gray = gray
        mask = build_ignore_mask(
            gray.shape[1], gray.shape[0], self.config.ignored_rects, self.mode
        )
        motion[mask == 0] = 0

        instant = motion.astype(np.float32) / 255.0 * 100.0
        if timestamp < self._flash_until:
            instant *= self.config.global_flash_confidence_scale
        self._heatmap = np.maximum(self._heatmap, instant)
        self._heatmap[mask == 0] = 0.0

        regions = self._score_regions(self._heatmap, motion)
        snapshot = ActivitySnapshot(
            heatmap=self._heatmap.copy(),
            motion_mask=motion,
            regions=regions,
            global_flash=global_flash,
            confidence_scale=confidence_scale,
            timestamp=timestamp,
            processing_ms=(time.perf_counter() - started) * 1000.0,
            skipped_analysis_frames=self._skipped,
        )
        self.last_snapshot = snapshot
        return snapshot

    def _remove_small_components(self, motion: np.ndarray) -> np.ndarray:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(motion, connectivity=8)
        minimum = max(
            2,
            int(round(motion.size * self.config.minimum_motion_region_fraction)),
        )
        cleaned = np.zeros_like(motion)
        for label in range(1, count):
            if int(stats[label, cv2.CC_STAT_AREA]) >= minimum:
                cleaned[labels == label] = 255
        return cleaned

    def _score_regions(
        self, heatmap: np.ndarray, motion: np.ndarray
    ) -> list[ActivityRegion]:
        rows = int(self.config.candidate_rows)
        columns = int(self.config.candidate_columns)
        region_width = (1.75 / columns) if self.mode == "equirectangular" else (1.5 / columns)
        region_height = min(1.0, 1.5 / rows)
        regions: list[ActivityRegion] = []

        for row in range(rows):
            center_y = (row + 0.5) / rows
            y = max(0.0, min(1.0 - region_height, center_y - region_height / 2.0))
            for column in range(columns):
                center_x = (column + 0.5) / columns
                x = center_x - region_width / 2.0
                if self.mode == "equirectangular":
                    x %= 1.0
                else:
                    x = max(0.0, min(1.0 - region_width, x))
                heat_values = extract_normalized_region(
                    heatmap, x, y, region_width, region_height, self.mode
                )
                motion_values = extract_normalized_region(
                    motion, x, y, region_width, region_height, self.mode
                )
                if heat_values.size == 0:
                    continue
                moving_fraction = float(np.count_nonzero(motion_values)) / float(
                    motion_values.size
                )
                # The upper percentile rewards a coherent moving group while the
                # mean stops a single noisy pixel from becoming a target.
                score = (
                    0.65 * float(np.percentile(heat_values, 85))
                    + 0.35 * float(np.mean(heat_values))
                ) * max(0.15, min(1.0, moving_fraction * 8.0))
                weighted_x, weighted_y = activity_centroid(
                    heat_values, x, y, region_width, region_height, self.mode
                )
                regions.append(
                    ActivityRegion(
                        x=x,
                        y=y,
                        width=region_width,
                        height=region_height,
                        center_x=weighted_x,
                        center_y=weighted_y,
                        score=score,
                        moving_fraction=moving_fraction,
                    )
                )
        regions.sort(key=lambda item: item.score, reverse=True)
        return regions


def build_ignore_mask(
    width: int,
    height: int,
    rectangles: Iterable[Rect],
    mode: ResolvedInputMode,
) -> np.ndarray:
    mask = np.full((height, width), 255, dtype=np.uint8)
    for x, y, rect_width, rect_height in rectangles:
        y0 = max(0, min(height, int(math.floor(y * height))))
        y1 = max(y0, min(height, int(math.ceil((y + rect_height) * height))))
        x0 = max(0, min(width, int(math.floor(x * width))))
        x1_normalized = x + rect_width
        if mode == "equirectangular" and x1_normalized > 1.0:
            right_end = width
            wrap_end = max(0, min(width, int(math.ceil((x1_normalized - 1.0) * width))))
            mask[y0:y1, x0:right_end] = 0
            mask[y0:y1, 0:wrap_end] = 0
        else:
            x1 = max(x0, min(width, int(math.ceil(min(1.0, x1_normalized) * width))))
            mask[y0:y1, x0:x1] = 0
    return mask


def extract_normalized_region(
    image: np.ndarray,
    x: float,
    y: float,
    width: float,
    height: float,
    mode: ResolvedInputMode,
) -> np.ndarray:
    image_height, image_width = image.shape[:2]
    y0 = max(0, min(image_height, int(math.floor(y * image_height))))
    y1 = max(y0 + 1, min(image_height, int(math.ceil((y + height) * image_height))))
    x %= 1.0 if mode == "equirectangular" else 1.0
    x0 = max(0, min(image_width, int(math.floor(x * image_width))))
    x_end = x + width
    if mode == "equirectangular" and x_end > 1.0:
        wrap_end = max(1, min(image_width, int(math.ceil((x_end - 1.0) * image_width))))
        return np.concatenate((image[y0:y1, x0:image_width], image[y0:y1, 0:wrap_end]), axis=1)
    x1 = max(x0 + 1, min(image_width, int(math.ceil(min(1.0, x_end) * image_width))))
    return image[y0:y1, x0:x1]


def activity_centroid(
    values: np.ndarray,
    x: float,
    y: float,
    width: float,
    height: float,
    mode: ResolvedInputMode,
) -> tuple[float, float]:
    weights = values.astype(np.float64)
    total = float(weights.sum())
    if total <= 1e-9:
        return ((x + width / 2.0) % 1.0, min(1.0, y + height / 2.0))
    local_y, local_x = np.indices(values.shape, dtype=np.float64)
    local_x = (local_x + 0.5) / max(1, values.shape[1])
    local_y = (local_y + 0.5) / max(1, values.shape[0])
    center_x = x + float((local_x * weights).sum() / total) * width
    center_y = y + float((local_y * weights).sum() / total) * height
    if mode == "equirectangular":
        center_x %= 1.0
    else:
        center_x = min(1.0, max(0.0, center_x))
    return center_x, min(1.0, max(0.0, center_y))
