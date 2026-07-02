# 360 Crowd Mosh

Prototype tool for turning stitched 360 footage into an auto-reframed live/recorded feed for Mosh-Pro.

The goal is not to make a full VJ app. The goal is to make a small "virtual camera operator" that watches a 360 audience/crowd feed, avoids obvious bad zones such as ceiling/projector walls, chooses active crowd regions, and outputs a normal 16:9 video feed that Mosh-Pro can treat as a file or webcam.

## Project concept

```text
Insta360 ONE X2 / ONE R / stitched 360 file
        -> equirectangular 360 video frame
        -> motion scan + optional person detection later
        -> random/smoothed audience target selection
        -> normal reframed 16:9 crop
        -> video file or virtual webcam
        -> Mosh-Pro webcam/file input
        -> data mosh / optical flow / MIDI / BPM / export
```

The first prototype is deliberately offline-first because you already have dim stitched footage. Once that works, live input can be swapped in via RTMP/OBS/capture.

## Current status

This repo contains a first-draft Python prototype:

- reads a stitched/equirectangular 360 video file;
- scans multiple yaw sectors around the audience band;
- scores regions by motion energy;
- ignores configurable no-track zones;
- randomly chooses among active regions;
- smooths yaw/pitch/FOV toward the chosen target;
- writes a normal reframed output video;
- can optionally send frames to a virtual webcam if `pyvirtualcam` and OBS virtual camera are set up.

It does **not** yet do true person detection. That is intentional. For dim dancefloor footage, motion-directed reframing is the best first test before adding YOLO/person tracking.

## Platform recommendation

Start on the MacBook.

Reasons:

- Mosh-Pro supports macOS and Windows.
- OBS Studio has a macOS virtual camera.
- `pyvirtualcam` supports macOS through OBS virtual camera.
- Offline video processing avoids the harder Insta360 live-stream/capture problem at first.

Use Windows later if:

- the MacBook struggles with performance;
- OBS virtual camera routing into Mosh-Pro is unreliable;
- you want Spout-based workflows, GPU-heavy YOLO, or Resolume-style routing.

## Quick start: offline render

```bash
git clone https://github.com/h2obuffalo/360crowdMosh.git
cd 360crowdMosh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/offline_director.py \
  --input /path/to/stitched_360_video.mp4 \
  --output renders/crowd_reframe_test.mp4 \
  --config configs/example.yaml \
  --preview
```

The output file can then be loaded into Mosh-Pro as normal video input.

## Quick start: virtual webcam test

One-time macOS setup:

1. Install OBS Studio.
2. Open OBS.
3. Click **Start Virtual Camera** once.
4. Click **Stop Virtual Camera**.
5. Close OBS.

Then run:

```bash
source .venv/bin/activate
python scripts/offline_director.py \
  --input /path/to/stitched_360_video.mp4 \
  --config configs/example.yaml \
  --virtualcam \
  --preview
```

Then in Mosh-Pro, choose the OBS virtual camera as a webcam input.

Important: OBS virtual camera is usually a single shared virtual camera. If Python is writing to it, do not also expect OBS to read it and output the same virtual camera again. For the first test, send Python directly to Mosh-Pro.

## Manual setup checklist

See:

- [Mac setup](docs/SETUP_MAC.md)
- [Windows setup](docs/SETUP_WINDOWS.md)
- [Prototype roadmap](docs/ROADMAP.md)

## Tracking strategy

The first tracker does this:

1. Divide the 360 image into virtual looking directions.
2. Render each direction as a small normal perspective crop.
3. Measure frame-to-frame motion energy.
4. Penalize masked/excluded areas.
5. Pick randomly from the top active sectors.
6. Smooth the camera view toward the target.

This is better than raw person detection for version 1 because dim footage, strobe lighting, projections, and datapath feedback may confuse object detectors. Motion plus masks should be enough to prove the idea.

## Avoiding ceilings, projectors, and meta-feedback

The config file supports:

- audience pitch band;
- ignored equirectangular rectangles;
- target hold time;
- smoothness;
- FOV/zoom;
- hard-cut probability.

For projections/screens, add mask rectangles in `configs/example.yaml` so they do not dominate the motion score.

## Later live path

```text
Insta360 phone app live 360 stream
        -> local RTMP server / OBS / ffmpeg input
        -> this app reads stream URL
        -> auto-reframed virtual camera
        -> Mosh-Pro
```

Likely next pieces:

- local RTMP ingest notes;
- mask painting UI;
- MIDI/OSC controls;
- YOLO person detector pass;
- TouchDesigner/OBS routing recipes;
- NDI/Syphon/Spout alternatives.

## Safety/privacy note

This is designed for abstracting the crowd into visual material, but it is still camera-based audience capture. For real events, use signage/consent appropriate to the venue/project, and avoid storing identifiable footage unless everyone involved has agreed.
