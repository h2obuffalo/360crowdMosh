"""Configuration loading for 360 Crowd Mosh."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import yaml

Rect = Tuple[float, float, float, float]


@dataclass
class DirectorConfig:
    output_width: int = 1280
    output_height: int = 720
    output_fps: float | None = None

    scan_sectors: int = 24
    scan_pitch_degrees: float = -5.0
    scan_fov_degrees: float = 55.0
    scan_width: int = 256
    scan_height: int = 144

    output_fov_degrees: float = 70.0
    min_fov_degrees: float = 45.0
    max_fov_degrees: float = 95.0
    zoom_from_motion: bool = True

    hold_frames_min: int = 60
    hold_frames_max: int = 180
    smoothing: float = 0.04
    top_candidate_count: int = 6
    hard_cut_probability: float = 0.03
    random_seed: int | None = 7

    motion_threshold: float = 10.0
    brightness_floor: int = 8
    contrast_boost: bool = True
    motion_decay: float = 0.8

    pitch_min_degrees: float = -25.0
    pitch_max_degrees: float = 18.0

    # Equirectangular normalized rectangles: [x, y, w, h], values 0..1.
    # Use these to exclude screens, projector walls, ceiling strips, DJ laptops, etc.
    ignored_rects: List[Rect] = field(default_factory=list)


def _as_rects(value: Any) -> List[Rect]:
    rects: List[Rect] = []
    if not value:
        return rects
    for item in value:
        if len(item) != 4:
            raise ValueError(f"Ignored rect must have four values: {item}")
        rects.append(tuple(float(v) for v in item))
    return rects


def load_config(path: str | None) -> DirectorConfig:
    """Load YAML config, falling back to defaults if path is None."""
    cfg = DirectorConfig()
    if not path:
        return cfg

    with open(path, "r", encoding="utf-8") as handle:
        data: Dict[str, Any] = yaml.safe_load(handle) or {}

    for key, value in data.items():
        if key == "ignored_rects":
            setattr(cfg, key, _as_rects(value))
        elif hasattr(cfg, key):
            setattr(cfg, key, value)
        else:
            raise ValueError(f"Unknown config key: {key}")
    return cfg
