# Live input notes

The first prototype is offline-first. Live input should be tested only after the motion director produces good reframed output from an existing stitched/equirectangular clip.

## What we need from live input

The script needs a video source that OpenCV can read as an equirectangular 360 frame:

```text
full stitched 360 frame, usually 2:1 aspect ratio
```

Good examples:

```text
3840x1920
5760x2880
2880x1440
1920x960
```

Bad examples for this prototype:

```text
single-lens webcam view
already flattened/non-360 camera view
phone-app reframed output only
```

## Insta360 consumer camera reality check

The ONE X2 / ONE R consumer workflow may not expose a clean raw 360 webcam device directly to Python. The likely live path is through the Insta360 phone app's live streaming feature.

The route to test later:

```text
Insta360 camera
  -> phone app
  -> live stream to custom/local RTMP endpoint
  -> local receiver/OBS/ffmpeg
  -> Python reads stream URL
  -> reframed virtual camera/file
  -> Mosh-Pro
```

## Candidate local RTMP receivers

### MediaMTX

Potentially the simplest modern test server.

Typical concept:

```text
phone app streams to rtmp://your-computer-ip/live/crowd360
Python reads rtmp://127.0.0.1/live/crowd360 or equivalent
```

### nginx-rtmp

Classic RTMP server route, but setup is more involved.

### OBS custom service

OBS can receive/handle streaming workflows, but for this project it may be more useful as a diagnostic tool than the main processing app.

## OpenCV stream test

Once you have a stream URL, try:

```bash
python scripts/offline_director.py \
  --input rtmp://127.0.0.1/live/crowd360 \
  --config configs/example.yaml \
  --preview
```

If OpenCV cannot open it, use ffmpeg to confirm the stream exists:

```bash
ffmpeg -i rtmp://127.0.0.1/live/crowd360 -f null -
```

## Live latency expectations

The first live RTMP path will probably have noticeable latency. That is acceptable for the first visuals-editor version because the crowd feed is being moshed and abstracted, not used for tight performer monitoring.

If latency becomes important later, test:

- lower stream resolution;
- lower GOP/keyframe interval;
- SRT/WebRTC routes;
- direct capture device paths;
- TouchDesigner or native GPU pipeline.

## What to verify first

Before integrating with Mosh-Pro, verify:

1. The input is truly 360/equirectangular.
2. The script can open the stream.
3. The preview reframes correctly.
4. Masked zones are ignored.
5. The output can be sent to virtual camera or rendered to file.
