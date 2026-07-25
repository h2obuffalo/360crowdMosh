# 360 Crowd Mosh

A focused motion-directed virtual camera for Mosh-Pro. It accepts stitched equirectangular 360° footage or normal flat video from a USB webcam, capture card, file, or OpenCV-compatible stream, and produces a normal configurable output frame (1280×720 by default).

The project deliberately does not add person detection, identity tracking, a VJ interface, or a video server.

## Input geometry

`--input-mode` and `input_mode` accept `auto`, `equirectangular`, and `flat`. Auto detection uses actual frame dimensions: frames close to 2:1 are treated as likely stitched equirectangular footage; common 16:9, 4:3, and similar frames are flat. Explicit CLI selection overrides configuration and detection.

The runtime is split into `FrameSource`, `ActivityAnalyser`, `TargetSelector`, geometry-specific `CameraController`, and geometry-specific `OutputRenderer` components. Activity is analysed once in normalized source coordinates, independently of target changes.

### Flat sources

Flat frames never enter spherical projection. The virtual camera moves an aspect-correct crop using normalized centre X/Y and crop-width fraction. Pan and tilt are digital cropping, not physical movement. Zoom reduces source coverage and may require upscaling. A 1080p webcam has limited reframing room when output is also 1080p; 4K provides materially more digital pan/zoom freedom. `flat_min_crop_width_fraction` defaults to `0.5`.

`flat_aspect_mode: crop` fills the output without stretching. `letterbox` preserves the selected source aspect and adds bars.

### Equirectangular sources

The source heatmap is analysed once. Masks, candidates, and targets may cross the longitude seam. The selected view is rendered once through the perspective projector, with shortest-path yaw movement and configured pitch/FOV limits.

## Installation

Supported Python: 3.10–3.13.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[live,dev]'
```

## Commands

Standard 1080p webcam (numeric input is a device index, not a filename):

```bash
python scripts/offline_director.py \
  --input 0 --input-mode flat \
  --capture-width 1920 --capture-height 1080 --capture-fps 30 \
  --virtualcam --preview
```

Flat video file:

```bash
python scripts/offline_director.py \
  --input input/crowd_camera.mp4 --input-mode flat \
  --output renders/flat_directed.mp4 \
  --config configs/flat_example.yaml --diagnostics
```

Stitched 360° file:

```bash
python scripts/offline_director.py \
  --input input/crowd_360.mp4 --input-mode equirectangular \
  --output renders/reframe_360.mp4 \
  --config configs/equirectangular_example.yaml --diagnostics
```

The original file command remains valid; ordinary 2:1 footage is normally auto-detected:

```bash
python scripts/offline_director.py \
  --input input/test_360.mp4 \
  --output renders/reframe_test.mp4 \
  --config configs/example.yaml --preview
```

## Activity, masks, and directing

Analysis runs at `analysis_fps` on a smaller image while output renders from the original frame. The analyser removes median global brightness shift, filters small connected components, applies ignored rectangles directly to motion pixels, and decays activity using elapsed seconds. A configurable global-flash detector temporarily lowers confidence after strobes.

Masks are normalized `[x, y, width, height]`. In equirectangular mode `x + width > 1` wraps across the seam.

Target selection uses minimum confidence, current-shot bias, hysteresis, switch margin, travel penalty, cooldown, minimum/maximum shot duration, and minimum meaningful movement. `no_motion_behavior` accepts `hold`, `home`, and `slow_roam`; stable `hold` is the default.

Camera motion uses elapsed time, speed limits, smoothing, deadbands, smooth arrival, separate position/zoom control, and optional hard cuts.

## Diagnostics and FPS

`--diagnostics` displays source, masks, candidates and scores, heatmap, selected crop or approximate 360 viewport, target reason/confidence, flash warning, source/analysis/output rates, processing time, skipped analysis frames, dropped live frames, and source state.

Source FPS is preserved by default. When `--output-fps` is set, file output is resampled from source timestamps so duration remains correct. Live inputs retain only the latest frame to prevent latency queues.

Capture width/height/FPS requests are best-effort; actual values are logged with warnings when a device does not accept them.

## Migration

Legacy frame-count hold settings and common old FOV/motion-decay keys are migrated with deprecation warnings where conversion is unambiguous. Old perspective-sector scan settings are ignored with warnings because analysis no longer renders multiple views.

## Tests and performance

```bash
pytest -q
python -m compileall -q crowd360 scripts tests
ruff check .
mypy crowd360
```

Tests use synthetic frames and require no physical camera. For an 8 GB M1 MacBook Pro, start near 320×180 analysis at 8–12 FPS; lower analysis rate before output rate. No neural-network or GPU dependency is introduced.
