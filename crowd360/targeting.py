"""Geometry-aware target selection with confidence, hysteresis and cooldown."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .activity import ActivityRegion, ActivitySnapshot
from .config import DirectorConfig
from .geometry import (
    ResolvedInputMode,
    pitch_to_normalized,
    region_distance,
    yaw_to_normalized,
)


@dataclass(frozen=True, slots=True)
class CameraTarget:
    center_x: float
    center_y: float
    framing: float
    score: float
    region: ActivityRegion | None = None
    fallback: bool = False
    hard_cut: bool = False


@dataclass(slots=True)
class SelectionDecision:
    selected: CameraTarget
    proposed: CameraTarget | None
    switched: bool
    reason: str


class TargetSelector:
    def __init__(self, config: DirectorConfig, mode: ResolvedInputMode):
        self.config = config
        self.mode = mode
        self.current: CameraTarget | None = None
        self.last_switch_at: float | None = None
        self._recent: dict[tuple[int, int], float] = {}

    def evaluate(
        self,
        snapshot: ActivitySnapshot,
        timestamp: float,
        camera_x: float,
        camera_y: float,
    ) -> SelectionDecision:
        eligible = [
            region
            for region in snapshot.regions
            if region.score * snapshot.confidence_scale >= self.config.minimum_activity_score
        ]
        if not eligible:
            fallback = self._fallback(timestamp, camera_x, camera_y)
            switched = self._is_meaningful_change(self.current, fallback)
            if switched and fallback is not self.current:
                self._commit(fallback, timestamp)
            elif self.current is None:
                self.current = fallback
            return SelectionDecision(
                selected=self.current or fallback,
                proposed=fallback,
                switched=switched,
                reason=f"no-motion:{self.config.no_motion_behavior}",
            )

        proposed_region = max(
            eligible,
            key=lambda region: self._effective_score(region, timestamp, camera_x, camera_y),
        )
        proposed = self._target_for_region(proposed_region)

        if self.current is None or self.current.fallback:
            self._commit(proposed, timestamp)
            return SelectionDecision(proposed, proposed, True, "initial-active-target")

        elapsed = timestamp - (self.last_switch_at if self.last_switch_at is not None else timestamp)
        current_region_score = self._score_near_current(eligible)
        movement = region_distance(
            self.mode,
            self.current.center_x,
            self.current.center_y,
            proposed.center_x,
            proposed.center_y,
        )

        if movement < self.config.minimum_target_movement:
            refreshed = CameraTarget(
                center_x=self.current.center_x,
                center_y=self.current.center_y,
                framing=proposed.framing,
                score=max(self.current.score, proposed.score),
                region=proposed.region,
            )
            self.current = refreshed
            return SelectionDecision(refreshed, proposed, False, "movement-below-threshold")

        if elapsed < self.config.hold_seconds_min:
            return SelectionDecision(self.current, proposed, False, "minimum-shot-duration")

        forced = elapsed >= self.config.hold_seconds_max
        key = self._region_key(proposed.center_x, proposed.center_y)
        last_used = self._recent.get(key)
        if (
            not forced
            and last_used is not None
            and timestamp - last_used < self.config.target_cooldown_seconds
        ):
            return SelectionDecision(self.current, proposed, False, "recent-target-cooldown")

        required = (
            current_region_score * (1.0 + self.config.hysteresis)
            + self.config.target_switch_margin
        )
        candidate_effective = self._effective_score(
            proposed_region, timestamp, camera_x, camera_y
        )
        if not forced and candidate_effective < required:
            return SelectionDecision(self.current, proposed, False, "hysteresis-margin")

        hard_cut = bool(self.config.hard_cuts and forced)
        proposed = CameraTarget(
            center_x=proposed.center_x,
            center_y=proposed.center_y,
            framing=proposed.framing,
            score=proposed.score,
            region=proposed.region,
            hard_cut=hard_cut,
        )
        self._commit(proposed, timestamp)
        return SelectionDecision(
            proposed,
            proposed,
            True,
            "maximum-shot-duration" if forced else "better-active-target",
        )

    def _effective_score(
        self,
        region: ActivityRegion,
        timestamp: float,
        camera_x: float,
        camera_y: float,
    ) -> float:
        distance = region_distance(
            self.mode, camera_x, camera_y, region.center_x, region.center_y
        )
        score = region.score - self.config.travel_penalty * distance * max(
            self.config.minimum_activity_score, region.score
        )
        if self.current is not None:
            current_distance = region_distance(
                self.mode,
                self.current.center_x,
                self.current.center_y,
                region.center_x,
                region.center_y,
            )
            if current_distance < self.config.minimum_target_movement:
                score += self.config.current_shot_bias * max(1.0, region.score)
        key = self._region_key(region.center_x, region.center_y)
        last_used = self._recent.get(key)
        if last_used is not None:
            age = timestamp - last_used
            if age < self.config.target_cooldown_seconds:
                score *= max(0.05, age / self.config.target_cooldown_seconds)
        return score

    def _score_near_current(self, regions: list[ActivityRegion]) -> float:
        assert self.current is not None
        nearest = min(
            regions,
            key=lambda region: region_distance(
                self.mode,
                self.current.center_x,
                self.current.center_y,
                region.center_x,
                region.center_y,
            ),
        )
        distance = region_distance(
            self.mode,
            self.current.center_x,
            self.current.center_y,
            nearest.center_x,
            nearest.center_y,
        )
        if distance > max(0.2, self.config.minimum_target_movement * 2.0):
            return max(self.config.minimum_activity_score, self.current.score)
        return nearest.score + self.config.current_shot_bias * max(1.0, nearest.score)

    def _target_for_region(self, region: ActivityRegion) -> CameraTarget:
        framing = self._framing_for_score(region.score)
        return CameraTarget(
            center_x=region.center_x % 1.0 if self.mode == "equirectangular" else min(1.0, max(0.0, region.center_x)),
            center_y=min(1.0, max(0.0, region.center_y)),
            framing=framing,
            score=region.score,
            region=region,
        )

    def _framing_for_score(self, score: float) -> float:
        if self.mode == "equirectangular":
            wide = self.config.equirectangular_wide_fov_degrees
            medium = self.config.equirectangular_medium_fov_degrees
            close = self.config.equirectangular_close_fov_degrees
        else:
            wide = self.config.flat_wide_crop_width_fraction
            medium = self.config.flat_medium_crop_width_fraction
            close = self.config.flat_close_crop_width_fraction
        if not self.config.zoom_from_activity:
            return medium
        if score >= self.config.close_activity_score:
            return close
        if score >= self.config.medium_activity_score:
            return medium
        return wide

    def _fallback(self, timestamp: float, camera_x: float, camera_y: float) -> CameraTarget:
        if self.config.no_motion_behavior == "hold" and self.current is not None:
            return self.current
        if self.mode == "equirectangular":
            home_x = yaw_to_normalized(self.config.equirectangular_home_yaw_degrees)
            home_y = pitch_to_normalized(self.config.equirectangular_home_pitch_degrees)
            framing = self.config.equirectangular_home_fov_degrees
        else:
            home_x = self.config.flat_home_center_x
            home_y = self.config.flat_home_center_y
            framing = self.config.flat_wide_crop_width_fraction
        if self.config.no_motion_behavior == "hold":
            home_x, home_y = camera_x, camera_y
        elif self.config.no_motion_behavior == "slow_roam":
            phase = 2.0 * math.pi * timestamp / self.config.slow_roam_period_seconds
            home_x += math.sin(phase) * self.config.slow_roam_amplitude
            home_y += math.sin(phase * 0.5) * self.config.slow_roam_amplitude * 0.35
            if self.mode == "equirectangular":
                home_x %= 1.0
            else:
                home_x = min(1.0, max(0.0, home_x))
            home_y = min(1.0, max(0.0, home_y))
        return CameraTarget(home_x, home_y, framing, 0.0, fallback=True)

    def _commit(self, target: CameraTarget, timestamp: float) -> None:
        if self.current is not None and not self.current.fallback:
            self._recent[self._region_key(self.current.center_x, self.current.center_y)] = timestamp
        self.current = target
        self.last_switch_at = timestamp

    def _is_meaningful_change(
        self, current: CameraTarget | None, target: CameraTarget
    ) -> bool:
        if current is None:
            return True
        return region_distance(
            self.mode,
            current.center_x,
            current.center_y,
            target.center_x,
            target.center_y,
        ) >= self.config.minimum_target_movement

    def _region_key(self, x: float, y: float) -> tuple[int, int]:
        return (
            int((x % 1.0) * self.config.candidate_columns),
            int(min(0.999999, max(0.0, y)) * self.config.candidate_rows),
        )
