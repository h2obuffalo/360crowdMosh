from __future__ import annotations

import numpy as np
import pytest

from crowd360.camera import EquirectangularCameraController, FlatCameraController
from crowd360.config import DirectorConfig
from crowd360.geometry import detect_input_mode
from crowd360.rendering import (
    FlatCropRenderer,
    calculate_flat_crop,
    equirectangular_to_perspective,
    lerp_angle_degrees,
    shortest_yaw_delta,
)
from crowd360.sources import parse_input_spec
from crowd360.targeting import CameraTarget


def longitude_frame(width: int = 720, height: int = 360) -> np.ndarray:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 0] = np.arange(width, dtype=np.uint32)[None, :] * 255 // (width - 1)
    frame[:, :, 1] = 80
    frame[:, :, 2] = 160
    return frame


@pytest.mark.parametrize(
    ("yaw", "expected_x"),
    [(0.0, 0.5), (90.0, 0.75), (-90.0, 0.25)],
)
def test_perspective_rendering_cardinal_yaws(yaw: float, expected_x: float) -> None:
    frame = longitude_frame()
    rendered = equirectangular_to_perspective(frame, yaw, 0.0, 50.0, 101, 51)
    observed = rendered[25, 50, 0] / 255.0
    assert observed == pytest.approx(expected_x, abs=0.03)


def test_perspective_rendering_across_longitude_seam() -> None:
    frame = longitude_frame()
    left = equirectangular_to_perspective(frame, 179.0, 0.0, 30.0, 80, 40)
    right = equirectangular_to_perspective(frame, -179.0, 0.0, 30.0, 80, 40)
    # Both views straddle the same physical seam and should remain populated.
    assert left.mean() > 20
    assert right.mean() > 20
    assert np.mean(np.abs(left.astype(np.int16) - right.astype(np.int16))) < 20


def test_shortest_path_yaw_interpolation() -> None:
    assert shortest_yaw_delta(179.0, -179.0) == pytest.approx(2.0)
    assert shortest_yaw_delta(-179.0, 179.0) == pytest.approx(-2.0)
    assert abs(lerp_angle_degrees(179.0, -179.0, 0.5)) == pytest.approx(180.0)


def test_flat_crop_wide_medium_close() -> None:
    widths = [
        calculate_flat_crop(1920, 1080, 1280, 720, 0.5, 0.5, zoom).width
        for zoom in (1.0, 0.72, 0.5)
    ]
    assert widths[0] > widths[1] > widths[2]
    assert widths == [1920, 1382, 960]


@pytest.mark.parametrize("center_x,center_y", [(0.0, 0.0), (1.0, 1.0), (-2.0, 4.0)])
def test_flat_crop_never_exceeds_source(center_x: float, center_y: float) -> None:
    crop = calculate_flat_crop(1920, 1080, 1280, 720, center_x, center_y, 0.5)
    assert 0 <= crop.x < 1920
    assert 0 <= crop.y < 1080
    assert crop.x2 <= 1920
    assert crop.y2 <= 1080


def test_flat_crop_matches_output_aspect() -> None:
    crop = calculate_flat_crop(1440, 1080, 1280, 720, 0.5, 0.5, 1.0)
    assert crop.width / crop.height == pytest.approx(16 / 9, rel=0.002)
    assert crop.height < 1080  # 4:3 source is cropped vertically, not stretched.


def test_flat_renderer_does_not_apply_spherical_distortion() -> None:
    config = DirectorConfig(output_width=160, output_height=90).validate()
    renderer = FlatCropRenderer(config)
    frame = np.random.default_rng(4).integers(0, 256, (90, 160, 3), dtype=np.uint8)
    state = type("State", (), {"center_x": 0.5, "center_y": 0.5, "crop_width_fraction": 1.0})()
    output = renderer.render(frame, state)
    assert np.array_equal(output, frame)


def test_letterbox_preserves_source_aspect() -> None:
    config = DirectorConfig(
        output_width=160,
        output_height=90,
        flat_aspect_mode="letterbox",
    ).validate()
    renderer = FlatCropRenderer(config)
    frame = np.full((120, 160, 3), 200, dtype=np.uint8)  # 4:3
    state = type("State", (), {"center_x": 0.5, "center_y": 0.5, "crop_width_fraction": 1.0})()
    output = renderer.render(frame, state)
    assert output.shape == (90, 160, 3)
    assert output[:, 20:140].mean() > 150
    assert output[:, :15].mean() < 10
    assert output[:, 145:].mean() < 10


def test_geometry_detection_and_override() -> None:
    assert detect_input_mode(3840, 1920, "auto") == "equirectangular"
    assert detect_input_mode(1920, 1080, "auto") == "flat"
    assert detect_input_mode(1440, 1080, "auto") == "flat"
    assert detect_input_mode(1920, 1080, "equirectangular") == "equirectangular"
    assert detect_input_mode(3840, 1920, "flat") == "flat"


def test_camera_device_index_parsing() -> None:
    assert parse_input_spec("0") == 0
    assert parse_input_spec(" 12 ") == 12
    assert parse_input_spec("video0.mp4") == "video0.mp4"
    assert parse_input_spec("rtsp://camera/0") == "rtsp://camera/0"


def test_camera_motion_is_time_based_across_frame_rates() -> None:
    config = DirectorConfig(smoothing_time_seconds=0.5).validate()
    target = CameraTarget(0.8, 0.65, 0.5, 10.0)
    states = []
    for fps in (25, 60):
        controller = FlatCameraController(config)
        for _ in range(fps):
            controller.update(target, 1.0 / fps, 1920, 1080)
        states.append(controller.state)
    assert states[0].center_x == pytest.approx(states[1].center_x, abs=0.01)
    assert states[0].center_y == pytest.approx(states[1].center_y, abs=0.01)
    assert states[0].crop_width_fraction == pytest.approx(states[1].crop_width_fraction, abs=0.01)


def test_equirectangular_controller_uses_shortest_path() -> None:
    config = DirectorConfig(
        equirectangular_home_yaw_degrees=179.0,
        equirectangular_max_pan_degrees_per_second=20.0,
        movement_deadband=0.0,
    ).validate()
    controller = EquirectangularCameraController(config)
    target_x = ((-179.0 + 180.0) % 360.0) / 360.0
    controller.update(CameraTarget(target_x, 0.5, 72.0, 5.0), 0.1)
    assert controller.state.yaw_degrees > 179.0 or controller.state.yaw_degrees < -179.0
