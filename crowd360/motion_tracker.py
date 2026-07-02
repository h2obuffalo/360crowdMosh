"""Motion-based crowd target selection for stitched 360 video."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Sequence, Tuple

import cv2
import numpy as np

from .config import DirectorConfig, Rect
from .reframe import equirectangular_to_perspective, lerp_angle_degrees, wrap_degrees


@dataclass
class Target:
    yaw: float
    pitch: float
    fov: float
    score: float


class MotionCrowdDirector:
    """Chooses reframing targets by scanning equirectangular footage for motion.

    This deliberately avoids full person detection for the first prototype. It is
    more likely to survive dim, noisy, strobing dancefloor footage and gives us
    a useful baseline before adding YOLO/person tracking.
    """

    def __init__(self, config: DirectorConfig):
        self.config = config
        self.rng = random.Random(config.random_seed)
        self.prev_sector_gray: List[np.ndarray | None] = [None] * config.scan_sectors
        self.motion_memory: List[float] = [0.0] * config.scan_sectors

        self.current_yaw = 0.0
        self.current_pitch = config.scan_pitch_degrees
        self.current_fov = config.output_fov_degrees
        self.target = Target(0.0, config.scan_pitch_degrees, config.output_fov_degrees, 0.0)
        self.frames_until_retarget = 0

    def update(self, frame_bgr: np.ndarray) -> Target:
        """Update target selection from the latest 360 frame."""
        if self.frames_until_retarget <= 0:
            candidates = self._scan_candidates(frame_bgr)
            self.target = self._choose_target(candidates)
            self.frames_until_retarget = self.rng.randint(
                int(self.config.hold_frames_min), int(self.config.hold_frames_max)
            )
        else:
            self.frames_until_retarget -= 1
            if self.rng.random() < float(self.config.hard_cut_probability) / max(1, self.frames_until_retarget):
                candidates = self._scan_candidates(frame_bgr)
                self.target = self._choose_target(candidates)
                self.frames_until_retarget = self.rng.randint(
                    int(self.config.hold_frames_min), int(self.config.hold_frames_max)
                )

        smooth = float(self.config.smoothing)
        self.current_yaw = lerp_angle_degrees(self.current_yaw, self.target.yaw, smooth)
        self.current_pitch += (self.target.pitch - self.current_pitch) * smooth
        self.current_fov += (self.target.fov - self.current_fov) * smooth
        self.current_pitch = float(np.clip(self.current_pitch, self.config.pitch_min_degrees, self.config.pitch_max_degrees))
        self.current_fov = float(np.clip(self.current_fov, self.config.min_fov_degrees, self.config.max_fov_degrees))

        return Target(self.current_yaw, self.current_pitch, self.current_fov, self.target.score)

    def render_output(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Render the current directed viewport."""
        return equirectangular_to_perspective(
            frame_bgr,
            yaw_degrees=self.current_yaw,
            pitch_degrees=self.current_pitch,
            fov_degrees=self.current_fov,
            out_width=int(self.config.output_width),
            out_height=int(self.config.output_height),
        )

    def _scan_candidates(self, frame_bgr: np.ndarray) -> List[Target]:
        candidates: List[Target] = []
        for sector_idx in range(int(self.config.scan_sectors)):
            yaw = -180.0 + (360.0 * sector_idx / float(self.config.scan_sectors))
            yaw = wrap_degrees(yaw)
            crop = equirectangular_to_perspective(
                frame_bgr,
                yaw_degrees=yaw,
                pitch_degrees=float(self.config.scan_pitch_degrees),
                fov_degrees=float(self.config.scan_fov_degrees),
                out_width=int(self.config.scan_width),
                out_height=int(self.config.scan_height),
            )
            score = self._motion_score(sector_idx, crop)
            score *= self._mask_penalty_for_yaw(yaw, self.config.ignored_rects)

            # Dim footage can produce noisy false positives. Decay but retain
            # recent motion so a single strobe frame does not fully dominate.
            self.motion_memory[sector_idx] = (
                float(self.config.motion_decay) * self.motion_memory[sector_idx]
                + (1.0 - float(self.config.motion_decay)) * score
            )
            combined_score = max(score, self.motion_memory[sector_idx])

            if combined_score > 0:
                fov = float(self.config.output_fov_degrees)
                if self.config.zoom_from_motion:
                    # More motion -> tighter shot, bounded by min/max FOV.
                    zoom_strength = min(1.0, combined_score / 60.0)
                    fov = self.config.max_fov_degrees + (
                        self.config.min_fov_degrees - self.config.max_fov_degrees
                    ) * zoom_strength
                candidates.append(Target(yaw, float(self.config.scan_pitch_degrees), fov, combined_score))
        return candidates

    def _motion_score(self, sector_idx: int, crop_bgr: np.ndarray) -> float:
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        if self.config.contrast_boost:
            # Helps dim dancefloor footage without needing a heavy denoiser.
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)

        # Suppress near-black noise.
        gray = np.where(gray < int(self.config.brightness_floor), 0, gray).astype(np.uint8)

        prev = self.prev_sector_gray[sector_idx]
        self.prev_sector_gray[sector_idx] = gray
        if prev is None:
            return 0.0

        diff = cv2.absdiff(gray, prev)
        _, thresh = cv2.threshold(diff, int(self.config.motion_threshold), 255, cv2.THRESH_BINARY)
        # Morph close reduces isolated compression/noise speckles.
        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        motion_pixels = float(np.count_nonzero(thresh))
        total_pixels = float(thresh.shape[0] * thresh.shape[1])
        return 100.0 * motion_pixels / max(1.0, total_pixels)

    def _choose_target(self, candidates: Sequence[Target]) -> Target:
        if not candidates:
            return Target(self.current_yaw, self.current_pitch, self.current_fov, 0.0)

        ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
        top_n = max(1, int(self.config.top_candidate_count))
        shortlist = ranked[:top_n]

        # Weighted random choice keeps the shot alive without simply acting like CCTV.
        weights = [max(0.01, c.score) for c in shortlist]
        return self.rng.choices(shortlist, weights=weights, k=1)[0]

    @staticmethod
    def _mask_penalty_for_yaw(yaw: float, rects: Sequence[Rect]) -> float:
        """Return 0..1 penalty for ignored rects near this yaw.

        Rects are normalized in equirectangular coordinates. This version uses a
        simple yaw overlap test; a later mask-paint UI can make this more exact.
        """
        if not rects:
            return 1.0
        x_norm = ((yaw + 180.0) % 360.0) / 360.0
        penalty = 1.0
        for x, _y, w, _h in rects:
            x2 = x + w
            if x <= x_norm <= x2:
                penalty *= 0.05
        return penalty
