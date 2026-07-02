# Tools and routing notes

## Required for first offline test

### Python 3.12

Runs the prototype scripts.

### OpenCV / NumPy / PyYAML

Installed from `requirements.txt`.

Used for:

- reading stitched 360 video files;
- equirectangular-to-perspective remapping;
- motion scoring;
- MP4 export;
- preview windows.

### Mosh-Pro

Target visuals editor. For this project, Mosh-Pro is the final creative stage: it receives either a rendered MP4 or a virtual webcam feed from this tool.

Useful Mosh-Pro effects to test first:

- Data-Mosh;
- Optical-Flow;
- Feedback;
- Hard Glitch;
- Pixel Sort;
- Luma-Mesh;
- Transform;
- MIDI modulation and BPM timing.

## Required for virtual camera test

### OBS Studio

Used only to provide a virtual camera device at first.

First test route:

```text
Python script -> OBS virtual camera -> Mosh-Pro webcam input
```

One-time setup:

1. Open OBS.
2. Start Virtual Camera.
3. Stop Virtual Camera.
4. Quit OBS.

### pyvirtualcam

Python package that sends frames to the virtual camera. It still needs a real virtual camera backend installed first, which is why OBS is part of the setup.

## Optional / later tools

### ffmpeg

Useful for:

- extracting still frames for mask tuning;
- transcoding awkward camera files;
- testing stream URLs;
- generating image sequences.

Example:

```bash
ffmpeg -i input/test_360.mp4 -frames:v 1 renders/first_frame.jpg
```

### Local RTMP server

Potential live path for Insta360 app streaming:

```text
Insta360 camera -> phone app live stream -> local RTMP server -> Python/OBS input
```

Candidates to test later:

- OBS custom RTMP/service route;
- nginx with RTMP module;
- MediaMTX;
- ffmpeg as a receiver/relay.

### NDI

Useful if webcam routing is too restrictive, especially between machines.

Possible future route:

```text
Python/OBS -> NDI -> Mosh/OBS/TouchDesigner/Resolume-compatible receiver
```

### Syphon / Spout

Mosh-Pro can output Syphon on macOS and Spout on Windows. For this project, that is more useful after Mosh-Pro, not necessarily before it.

Possible route:

```text
Python -> Mosh-Pro -> Syphon/Spout output -> OBS/TouchDesigner/MadMapper/Resolume
```

### TouchDesigner

Useful if we decide the project should become more visual/interactive than the Python prototype:

```text
360 input -> TouchDesigner reproject/reframe -> optical flow/person tracking -> Mosh-Pro or direct projection
```

For now, Python is simpler and easier to keep in the repo.

## Current best route

For your current stitched footage:

```text
stitched 360 MP4 -> Python offline_director.py -> reframed MP4 -> Mosh-Pro
```

Then:

```text
stitched 360 MP4 -> Python offline_director.py --virtualcam -> Mosh-Pro webcam input
```

Then later:

```text
Insta360 live stream -> local RTMP -> Python offline_director.py/input URL -> Mosh-Pro
```
