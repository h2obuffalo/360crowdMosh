# macOS setup

Use Python 3.10–3.13:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[live,dev]'
```

Grant camera permission to Terminal/Python, then test:

```bash
python scripts/offline_director.py --input 0 --input-mode flat --capture-width 1920 --capture-height 1080 --capture-fps 30 --diagnostics
```

For Mosh-Pro virtual output, install and initialise a `pyvirtualcam` backend such as OBS Virtual Camera, then add `--virtualcam`. Requested webcam formats are best-effort; use the logged actual resolution and FPS.
