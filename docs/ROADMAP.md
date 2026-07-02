# Prototype roadmap

## Phase 0: repo seed

Done in this first draft:

- Mac-first offline prototype plan.
- Python/OpenCV equirectangular reframe helper.
- Motion-based crowd region selection.
- Configurable no-track rectangles.
- Offline MP4 output.
- Optional virtual camera output.
- Setup notes for macOS and Windows.

## Phase 1: prove the visual concept with existing stitched footage

Goal: get one dim 360 clip producing a usable Mosh-Pro source.

Manual steps:

1. Put a stitched 360 clip in `input/` locally.
2. Run `scripts/offline_director.py` with `--preview`.
3. Tune `configs/example.yaml`:
   - masks for ceiling/floor;
   - masks for projector walls/screens;
   - scan pitch;
   - hold time;
   - FOV/zoom;
   - motion threshold.
4. Export a reframed MP4.
5. Load the MP4 into Mosh-Pro.
6. Try Mosh-Pro Data-Mosh, Optical-Flow, Feedback, Pixel Sort, Hard Glitch, and MIDI modulation.

Acceptance test:

- The exported video mostly looks at crowd/dance movement rather than ceiling, floor, screens, or projectors.
- Random target switching feels intentional enough to be visually useful after Mosh-Pro effects.

## Phase 2: improve setup UX

Add:

- still-frame export command;
- simple mask visualizer;
- maybe a click/drag mask editor;
- diagnostic overlay showing sector scores;
- side-by-side preview: flattened 360 source + selected output crop.

Acceptance test:

- You can tune masks without guessing normalized coordinates by hand.

## Phase 3: live input test

Potential routes:

```text
Insta360 app 360 live stream -> RTMP server -> Python OpenCV input
OBS media/source capture -> virtual/file/NDI -> Python input
HDMI/capture path if a camera/player can output equirectangular video
```

For live 360 from Insta360 consumer cameras, likely manual setup still involves the phone app starting a live stream. This repo should document the working route once tested.

Acceptance test:

- Python script reads a live equirectangular source and outputs a reframed live feed.

## Phase 4: Mosh-Pro live routing

Test routes:

1. Python -> OBS virtual camera -> Mosh-Pro webcam input.
2. Python -> file export -> Mosh-Pro file input.
3. Python -> OBS/NDI/Syphon/Spout style route if webcam is too limiting.

Acceptance test:

- Mosh-Pro receives the reframed view reliably with acceptable latency.

## Phase 5: MIDI/OSC control

Add controls for:

- freeze current target;
- force new random target;
- randomness;
- motion sensitivity;
- zoom/FOV;
- smoothness;
- hard-cut probability;
- mask enable/disable;
- output clarity vs chaos gate.

Potential libraries:

- `python-osc` for OSC;
- `mido` + `python-rtmidi` for MIDI.

Acceptance test:

- A hardware controller or TouchOSC can change the direction/zoom/randomness live.

## Phase 6: person detector layer

Add optional YOLO or MediaPipe layer after the motion baseline works.

Proposed logic:

```text
motion scan finds active sectors
        -> person detector validates likely people/groups
        -> director randomly chooses from valid moving human regions
```

Do not start here. The motion-only system is cheaper, faster, and more tolerant of dark footage.

Acceptance test:

- Person detector improves crowd selection without locking onto screens, lights, or projections.

## Phase 7: installation/live-show mode

Add:

- persistent show config;
- OSC/MIDI mappings file;
- startup script;
- crash-safe fallback to slow random panning;
- logging of dropped frames and FPS;
- optional black/idle output if no motion is found.

Acceptance test:

- The system can run during a show without constant babysitting.
