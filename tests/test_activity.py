import numpy as np
from crowd360.activity import ActivityAnalyser, build_ignore_mask
from crowd360.config import DirectorConfig


def moving_frame():
    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    frame[50:130, 210:300] = 255
    return frame


def analyse(config, mode="flat"):
    analyser = ActivityAnalyser(config, mode)
    analyser.update(np.zeros((180, 320, 3), dtype=np.uint8), 0.0)
    return analyser.update(moving_frame(), 0.1)


def test_motion_scores_above_static_regions():
    snap = analyse(DirectorConfig(contrast_boost=False, motion_threshold=5).validate())
    assert snap.regions[0].score > 1.5
    assert snap.regions[0].center_x > 0.6
    assert snap.regions[-1].score == 0


def test_masked_motion_is_ignored():
    config = DirectorConfig(contrast_boost=False, motion_threshold=5, ignored_rects=[(0.6, 0.2, 0.4, 0.6)]).validate()
    snap = analyse(config)
    assert np.count_nonzero(snap.motion_mask) == 0


def test_partial_mask_overlap_only_suppresses_overlap():
    full = analyse(DirectorConfig(contrast_boost=False, motion_threshold=5).validate())
    partial = analyse(DirectorConfig(contrast_boost=False, motion_threshold=5, ignored_rects=[(0.65, 0.0, 0.15, 1.0)]).validate())
    assert 0 < np.count_nonzero(partial.motion_mask) < np.count_nonzero(full.motion_mask)


def test_seam_crossing_mask_wraps():
    mask = build_ignore_mask(100, 50, [(0.9, 0.2, 0.2, 0.4)], "equirectangular")
    assert np.all(mask[10:30, 90:] == 0)
    assert np.all(mask[10:30, :10] == 0)


def test_global_flash_is_suppressed():
    config = DirectorConfig(contrast_boost=False, motion_threshold=5, global_flash_fraction=0.5).validate()
    analyser = ActivityAnalyser(config, "flat")
    analyser.update(np.zeros((180, 320, 3), dtype=np.uint8), 0.0)
    snap = analyser.update(np.full((180, 320, 3), 255, dtype=np.uint8), 0.1)
    assert snap.global_flash
    assert np.count_nonzero(snap.motion_mask) == 0
