# macOS setup

Mac is the recommended first route for this prototype because the first test uses stitched video files, Mosh-Pro supports macOS, and OBS virtual camera can be used as the bridge into Mosh-Pro.

## 1. Install basics

Install Homebrew if needed, then:

```bash
brew install python@3.12 ffmpeg
```

Install OBS Studio from <https://obsproject.com/>.

Install Mosh-Pro from <https://moshpro.app/>.

## 2. Clone and install Python dependencies

```bash
git clone https://github.com/h2obuffalo/360crowdMosh.git
cd 360crowdMosh
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Put test footage somewhere local

Do not commit footage to the repo. Suggested local folder:

```bash
mkdir -p input renders
cp /path/to/your/stiched_360_file.mp4 input/test_360.mp4
```

## 4. Run an offline render first

```bash
source .venv/bin/activate
python scripts/offline_director.py \
  --input input/test_360.mp4 \
  --output renders/reframe_test.mp4 \
  --config configs/example.yaml \
  --preview
```

Press `q` or Escape to quit the preview.

Load `renders/reframe_test.mp4` into Mosh-Pro as a normal video file.

## 5. Tune masks

Open one frame from the 360 video in any image viewer/editor, or export a still with ffmpeg:

```bash
ffmpeg -i input/test_360.mp4 -frames:v 1 renders/first_frame.jpg
```

The equirectangular image coordinates are normalized:

```text
x: 0.0 left edge, 1.0 right edge
y: 0.0 top/ceiling, 1.0 bottom/floor
```

Edit `configs/example.yaml` and add `ignored_rects` for:

- projector walls;
- screens;
- DJ laptop;
- mirrored surfaces;
- ceiling lights;
- areas where the projected output feed appears.

Example:

```yaml
ignored_rects:
  - [0.0, 0.0, 1.0, 0.18]    # ceiling
  - [0.0, 0.88, 1.0, 0.12]   # floor
  - [0.62, 0.28, 0.12, 0.28] # projection screen
```

## 6. Virtual camera into Mosh-Pro

One-time OBS setup:

1. Open OBS.
2. Click **Start Virtual Camera**.
3. Click **Stop Virtual Camera**.
4. Quit OBS.

Then run:

```bash
source .venv/bin/activate
python scripts/offline_director.py \
  --input input/test_360.mp4 \
  --config configs/example.yaml \
  --virtualcam \
  --preview
```

Open Mosh-Pro and select the OBS virtual camera as the webcam input.

## Known macOS caveat

OBS virtual camera is usually a single shared virtual camera. For the first test, route:

```text
Python -> OBS virtual camera -> Mosh-Pro
```

Do not try to simultaneously route:

```text
Python -> OBS virtual camera -> OBS -> OBS virtual camera -> Mosh-Pro
```

That loop usually needs a second virtual camera system or a different route such as Syphon/NDI later.

## Performance tips

If the MacBook struggles:

- reduce `scan_sectors` from 24 to 12 or 16;
- reduce `scan_width` / `scan_height`;
- render to 960x540 before 1280x720;
- disable `--preview`;
- do offline file export instead of virtual camera.
