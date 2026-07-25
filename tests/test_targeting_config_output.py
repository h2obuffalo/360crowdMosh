from __future__ import annotations

import warnings

import numpy as np
import pytest

from crowd360.activity import ActivityRegion, ActivitySnapshot
from crowd360.config import DirectorConfig, config_from_mapping
from crowd360.output import TimestampResampler
from crowd360.targeting import TargetSelector


def region(x: float, score: float, y: float = 0.5) -> ActivityRegion:
    return ActivityRegion(x, 0.25, 0.2, 0.5, x, y, score, 0.2)


def snapshot(*regions: ActivityRegion) -> ActivitySnapshot:
    return ActivitySnapshot(
        heatmap=np.zeros((10, 10), dtype=np.float32),
        motion_mask=np.zeros((10, 10), dtype=np.uint8),
        regions=list(regions),
        timestamp=0.0,
    )


def test_hysteresis_prevents_unnecessary_switch() -> None:
    config = DirectorConfig(
        hold_seconds_min=0.0,
        hold_seconds_max=10.0,
        hysteresis=0.2,
        target_switch_margin=0.5,
        travel_penalty=0.0,
        target_cooldown_seconds=0.0,
        current_shot_bias=0.0,
    ).validate()
    selector = TargetSelector(config, "flat")
    first = selector.evaluate(snapshot(region(0.25, 8.0)), 0.0, 0.5, 0.5)
    assert first.switched
    second = selector.evaluate(
        snapshot(region(0.25, 8.0), region(0.75, 8.8)), 1.0, 0.25, 0.5
    )
    assert not second.switched
    assert second.reason == "hysteresis-margin"


def test_cooldown_prevents_bouncing_to_recent_target() -> None:
    config = DirectorConfig(
        hold_seconds_min=0.0,
        hold_seconds_max=1.0,
        hysteresis=0.0,
        target_switch_margin=0.0,
        travel_penalty=0.0,
        target_cooldown_seconds=10.0,
        minimum_target_movement=0.05,
    ).validate()
    selector = TargetSelector(config, "flat")
    selector.evaluate(snapshot(region(0.2, 8.0)), 0.0, 0.5, 0.5)
    switched = selector.evaluate(snapshot(region(0.8, 9.0)), 1.1, 0.2, 0.5)
    assert switched.switched
    bounce = selector.evaluate(snapshot(region(0.2, 20.0)), 1.5, 0.8, 0.5)
    assert not bounce.switched
    assert bounce.reason == "recent-target-cooldown"


@pytest.mark.parametrize("mode", ["flat", "equirectangular"])
def test_no_motion_home_fallback(mode: str) -> None:
    config = DirectorConfig(no_motion_behavior="home").validate()
    selector = TargetSelector(config, mode)  # type: ignore[arg-type]
    decision = selector.evaluate(snapshot(), 0.0, 0.1, 0.8)
    assert decision.selected.fallback
    if mode == "flat":
        assert decision.selected.center_x == pytest.approx(config.flat_home_center_x)
        assert decision.selected.framing == pytest.approx(config.flat_wide_crop_width_fraction)
    else:
        assert decision.selected.framing == pytest.approx(config.equirectangular_home_fov_degrees)


def test_invalid_configuration_has_clear_error() -> None:
    with pytest.raises(ValueError, match="input_mode"):
        config_from_mapping({"input_mode": "sphere"})
    with pytest.raises(ValueError, match=r"ignored_rects\[0\]"):
        config_from_mapping({"ignored_rects": [[0.2, 0.3, 0.4]]})
    with pytest.raises(ValueError, match="Unknown config key"):
        config_from_mapping({"made_up": 3})


def test_legacy_frame_configuration_is_migrated() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = config_from_mapping(
            {"hold_frames_min": 50, "hold_frames_max": 175, "output_fps": 25}
        )
    assert config.hold_seconds_min == pytest.approx(2.0)
    assert config.hold_seconds_max == pytest.approx(7.0)
    assert caught


def test_offline_resampling_retains_duration() -> None:
    source_fps = 30.0
    output_fps = 25.0
    duration = 2.0
    timestamps = [index / source_fps for index in range(int(duration * source_fps))]
    resampler = TimestampResampler(output_fps)
    count = sum(resampler.emit_count(timestamp) for timestamp in timestamps)
    count += resampler.flush_count(duration)
    assert count == int(duration * output_fps)
    assert count / output_fps == pytest.approx(duration)
