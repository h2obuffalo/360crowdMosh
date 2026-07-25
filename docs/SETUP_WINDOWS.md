# Windows setup

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e "[live,dev]"
```

Test a capture device:

```powershell
python scripts/offline_director.py --input 0 --input-mode flat --capture-width 1920 --capture-height 1080 --capture-fps 30 --diagnostics
```

Try another numeric index when device zero is not the intended camera. Install a `pyvirtualcam` backend such as OBS Virtual Camera before using `--virtualcam`.
