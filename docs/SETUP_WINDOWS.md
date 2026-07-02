# Windows setup

Use Windows if the MacBook struggles, if Mosh-Pro camera routing is easier there, or if the next step needs heavier GPU acceleration/person detection.

## 1. Install basics

Install:

- Python 3.12 from <https://www.python.org/downloads/windows/>
- OBS Studio from <https://obsproject.com/>
- Mosh-Pro from <https://moshpro.app/>
- Git for Windows from <https://git-scm.com/download/win>

Optional later:

- Unity Capture or another second virtual camera if you need Python -> virtual camera -> OBS -> virtual camera -> Mosh-Pro routing.
- NDI tools if you want network video routing.

## 2. Clone and install dependencies

In PowerShell:

```powershell
git clone https://github.com/h2obuffalo/360crowdMosh.git
cd 360crowdMosh
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks the venv activation script:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then re-run:

```powershell
.\.venv\Scripts\Activate.ps1
```

## 3. Offline render

```powershell
mkdir input
mkdir renders
copy C:\path\to\stitched_360_file.mp4 input\test_360.mp4

python scripts\offline_director.py `
  --input input\test_360.mp4 `
  --output renders\reframe_test.mp4 `
  --config configs\example.yaml `
  --preview
```

Load `renders\reframe_test.mp4` into Mosh-Pro.

## 4. Virtual camera

OBS includes a built-in virtual camera on Windows.

One-time OBS setup:

1. Open OBS.
2. Click **Start Virtual Camera**.
3. Click **Stop Virtual Camera**.
4. Quit OBS.

Then:

```powershell
python scripts\offline_director.py `
  --input input\test_360.mp4 `
  --config configs\example.yaml `
  --virtualcam `
  --preview
```

Open Mosh-Pro and select the OBS virtual camera as the webcam source.

## Windows routing note

The OBS virtual camera is normally a single shared camera. If Python writes to it, OBS cannot also safely use that same camera as input and output. For more complex routing, use a second virtual camera such as Unity Capture, or avoid virtual cameras and use file/NDI/Spout workflows later.

## GPU/person detection later

Windows may be the stronger target for the later YOLO/person detector phase because CUDA GPU setup is usually more useful on the Windows desktop than on the MacBook. The current prototype intentionally avoids that dependency.
