"""Validated configuration for the crowd camera director."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

Rect = tuple[float, float, float, float]
VALID_INPUT_MODES = {"auto", "equirectangular", "flat"}
VALID_ASPECT_MODES = {"crop", "letterbox"}
VALID_NO_MOTION_BEHAVIOURS = {"hold", "home", "slow_roam"}


@dataclass(slots=True)
class DirectorConfig:
    input_mode: str = "auto"
    flat_aspect_mode: str = "crop"
    output_width: int = 1280
    output_height: int = 720
    output_fps: float | None = None
    analysis_width: int = 320
    analysis_height: int = 180
    analysis_fps: float = 10.0
    target_evaluation_fps: float = 5.0
    motion_decay_seconds: float = 1.5
    motion_threshold: float = 12.0
    brightness_floor: int = 8
    contrast_boost: bool = True
    minimum_motion_region_fraction: float = 0.0007
    global_flash_fraction: float = 0.55
    global_flash_confidence_scale: float = 0.12
    global_flash_recovery_seconds: float = 0.6
    ignored_rects: list[Rect] = field(default_factory=list)
    candidate_columns: int = 12
    candidate_rows: int = 4
    minimum_activity_score: float = 1.5
    current_shot_bias: float = 0.20
    hysteresis: float = 0.12
    target_switch_margin: float = 0.25
    travel_penalty: float = 0.20
    target_cooldown_seconds: float = 5.0
    hold_seconds_min: float = 2.0
    hold_seconds_max: float = 7.0
    minimum_target_movement: float = 0.05
    hard_cuts: bool = False
    no_motion_behavior: str = "hold"
    smoothing_time_seconds: float = 0.6
    movement_deadband: float = 0.012
    zoom_deadband: float = 0.01
    zoom_change_per_second: float = 0.8
    zoom_from_activity: bool = True
    medium_activity_score: float = 4.0
    close_activity_score: float = 10.0
    equirectangular_home_yaw_degrees: float = 0.0
    equirectangular_home_pitch_degres: float = -5.0
    equirectangular_home_fov_degrees: float = 72.0
    equirectangular_wide_fov_degrees: float = 92.0
    equirectangular_medium_fov_degrees: float = 68.0
    equirectangular_close_fov_degrees: float = 48.0
    equirectangular_min_fov_degrees: float = 42.0
    equirectangular_max_fov_degrees: float = 95.0
    pitch_min_degrees: float = -25.0
    pitch_max_degrees: float = 18.0
    equirectangular_max_pan_degrees_per_second: float = 100.0
    equirectangular_max_pitch_degrees_per_second: float = 50.0
    flat_home_center_x: float = 0.5
    flat_home_center_y: float = 0.5
    flat_wide_crop_width_fraction: float = 1.0
    flat_medium_crop_width_fraction: float = 0.72
    flat_close_crop_width_fraction: float = 0.50
    flat_min_crop_width_fraction: float = 0.50
    flat_max_pan_normalized_per_second: float = 0.40
    flat_max_tilt_normalized_per_second: float = 0.30
    slow_roam_period_seconds: float = 24.0
    slow_roam_amplitude: float = 0.08
    random_seed: int | None = 7

    def validate(self) -> "DirectorConfig":
        if self.input_mode not in VALID_INPUT_MODES:
            raise ValueError(f"input_mode must be one of {sorted(VALID_INPUT_MODES)}")
        if self.flat_aspect_mode not in VALID_ASPECT_MODES:
            raise ValueError(f"flat_aspect_mode must be one of {sorted(VALID_ASPECT_MODES)}")
        if self.no_motion_behavior not in VALID_NO_MOTION_BEHAVIOURS:
            raise ValueError(f"no_motion_behavior must be one of {sorted(VALID_NO_MOTION_BEHAVIOURS)}")
        for name in ("output_width","output_height","analysis_width","analysis_height","analysis_fps","target_evaluation_fps","motion_decay_seconds","smoothing_time_seconds","hold_seconds_max","candidate_columns","candidate_rows"):
            if float(getattr(self,name)) <= 0: raise ValueError(f"{name} must be greater than zero")
        if self.output_fps is not None and self.output_fps <= 0: raise ValueError("output_fps must be greater than zero when set")
        if self.hold_seconds_min < 0 or self.hold_seconds_min > self.hold_seconds_max: raise ValueError("hold_seconds_min must be between zero and hold_seconds_max")
        if not 0 < self.flat_min_crop_width_fraction <= 1: raise ValueError("flat_min_crop_width_fraction must be in (0, 1]")
        self.ignored_rects = validate_rectangles(self.ignored_rects)
        return self


LEGACY_MIGRATIONS: dict[str, str] = {"output_fov_degrees":"equirectangular_home_fov_degrees","min_fov_degrees":"equirectangular_min_fov_degrees","max_fov_degrees":"equirectangular_max_fov_degrees","zoom_from_motion":"zoom_from_activity"}

def validate_rectangles(value):
    rects=[]
    if not value: return rects
    for index,item in enumerate(value):
        if not isinstance(item,Sequence) or isinstance(item,(str,bytes)) or len(item)!=4:
            raise ValueError(f"ignored_rects[{index}] must contain exactly [x, y, width, height]")
        try: x,y,width,height=(float(part) for part in item)
        except (TypeError,ValueError) as exc: raise ValueError(f"ignored_rects[{index}] contains a non-numeric value") from exc
        if not 0.0<=x<1.0 or not 0.0<=y<=1.0 or not 0.0<width<=1.0 or height<=0 or y+height>1.0+1e-9:
            raise ValueError(f"ignored_rects[{index}] is out of normalized bounds")
        rects.append((x,y,width,height))
    return rects

def _migrate_legacy(data):
    migrated=dict(data)
    for old,new in LEGACY_MIGRATIONS.items():
        if old in migrated and new not in migrated: migrated[new]=migrated.pop(old); warnings.warn(f"Configuration key '{old}' is deprecated; use '{new}'",DeprecationWarning,stacklevel=3)
    fps=float(migrated.get("output_fps") or 25.0)
    for old,new in (("hold_frames_min","hold_seconds_min"),("hold_frames_max","hold_seconds_max")):
        if old in migrated and new not in migrated: migrated[new]=float(migrated.pop(old))/fps; warnings.warn(f"{old} was migrated to {new}",DeprecationWarning,stacklevel=3)
    for obsolete in ("scan_sectors","scan_pitch_degrees","scan_fov_degrees","scan_width","scan_height","smoothing","top_candidate_count","hard_cut_probability"):
        if obsolete in migrated: migrated.pop(obsolete); warnings.warn(f"Configuration key '{obsolete}' is obsolete and was ignored",DeprecationWarning,stacklevel=3)
    return migrated

def config_from_mapping(data):
    values=_migrate_legacy(dict(data or {}))
    allowed={i.name for i in fields(DirectorConfig)}
    unknown=sorted(set(values)-allowed)
    if unknown: raise ValueError(f"Unknown config key(s): {', '.join(unknown)}")
    if "ignored_rects" in values: values["ignored_rects"]=validate_rectangles(values["ignored_rects"])
    return DirectorConfig(**values).validate()

def load_config(path):
    if path is None: return DirectorConfig().validate()
    p=Path(path)
    if not p.exists(): raise ValueError(f"Configuration file does not exist: {p}")
    data=yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data,Mapping): raise ValueError("Configuration root must be a YAML mapping")
    return config_from_mapping(data)
