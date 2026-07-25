"""Frame-source abstractions for files, devices and OpenCV streams."""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

LOGGER = logging.getLogger(__name__)
_DEVICE_RE = re.compile(r"^[0-9]+$")


@dataclass(frozen=True, slots=True)
class FramePacket:
    frame: np.ndarray
    timestamp: float
    source_timestamp: float
    sequence: int
    frame_age_seconds: float


@dataclass(slots=True)
class SourceInfo:
    kind: str
    description: str
    width: int
    height: int
    reported_fps: float
    effective_read_fps: float = 0.0
    dropped_frames: int = 0
    connected: bool = True


class FrameSource(Protocol):
    info: SourceInfo

    def read(self) -> FramePacket | None: ...

    def close(self) -> None: ...


def parse_input_spec(value: str | int) -> int | str:
    if isinstance(value, int):
        return value
    stripped = value.strip()
    return int(stripped) if _DEVICE_RE.fullmatch(stripped) else value


def _valid_fps(value: float, fallback: float = 25.0) -> float:
    return float(value) if 1.0 <= float(value) <= 240.0 else fallback


class FileFrameSource:
    def __init__(self, path: str | Path, start_frame: int = 0):
        self.path = str(path)
        self._capture = cv2.VideoCapture(self.path)
        if not self._capture.isOpened():
            raise RuntimeError(f"Could not open video file: {self.path}")
        if start_frame > 0:
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        width = int(round(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
        height = int(round(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        reported_fps = _valid_fps(self._capture.get(cv2.CAP_PROP_FPS))
        self.info = SourceInfo("file", self.path, width, height, reported_fps)
        self._sequence = start_frame
        self._started_at = time.monotonic()
        self._read_count = 0

    def read(self) -> FramePacket | None:
        ok, frame = self._capture.read()
        if not ok:
            self.info.connected = False
            return None
        now = time.monotonic()
        source_ms = float(self._capture.get(cv2.CAP_PROP_POS_MSEC))
        source_timestamp = source_ms / 1000.0 if source_ms > 0 else self._sequence / self.info.reported_fps
        self._sequence += 1
        self._read_count += 1
        elapsed = now - self._started_at
        self.info.effective_read_fps = self._read_count / elapsed if elapsed > 0 else 0.0
        return FramePacket(frame, now, source_timestamp, self._sequence, 0.0)

    def close(self) -> None:
        self._capture.release()
        self.info.connected = False


class LatestFrameSource:
    """Low-latency source that stores only the newest live frame."""

    def __init__(
        self,
        source: int | str,
        kind: str,
        capture_width: int | None = None,
        capture_height: int | None = None,
        capture_fps: float | None = None,
        fallback_fps: float = 25.0,
        warmup_seconds: float = 0.0,
    ):
        self._capture = cv2.VideoCapture(source)
        if not self._capture.isOpened():
            raise RuntimeError(f"Could not open {kind} input: {source}")
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if capture_width:
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, int(capture_width))
        if capture_height:
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, int(capture_height))
        if capture_fps:
            self._capture.set(cv2.CAP_PROP_FPS, float(capture_fps))
        width = int(round(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
        height = int(round(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        reported_fps = _valid_fps(self._capture.get(cv2.CAP_PROP_FPS), fallback_fps)
        self.info = SourceInfo(kind, str(source), width, height, reported_fps)
        LOGGER.info(
            "%s opened: actual=%dx%d @ %.3f fps (requested=%sx%s @ %s)",
            kind,
            width,
            height,
            reported_fps,
            capture_width or "default",
            capture_height or "default",
            capture_fps or "default",
        )
        if capture_width and width != int(capture_width):
            LOGGER.warning("Capture width request %s was not accepted; actual is %s", capture_width, width)
        if capture_height and height != int(capture_height):
            LOGGER.warning("Capture height request %s was not accepted; actual is %s", capture_height, height)
        if capture_fps and abs(reported_fps - float(capture_fps)) > 0.5:
            LOGGER.warning("Capture FPS request %s was not accepted; actual is %.3f", capture_fps, reported_fps)

        self._latest: tuple[np.ndarray, float, int] | None = None
        self._last_delivered = -1
        self._sequence = 0
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._started_at = time.monotonic()
        self._successful_reads = 0
        self._thread = threading.Thread(target=self._reader, name=f"{kind}-reader", daemon=True)
        self._thread.start()
        if warmup_seconds > 0:
            time.sleep(warmup_seconds)

    def _reader(self) -> None:
        consecutive_failures = 0
        while not self._stop.is_set():
            ok, frame = self._capture.read()
            now = time.monotonic()
            if not ok:
                consecutive_failures += 1
                self.info.dropped_frames += 1
                self.info.connected = consecutive_failures < 30
                time.sleep(min(0.1, 0.005 * consecutive_failures))
                continue
            consecutive_failures = 0
            self.info.connected = True
            self._sequence += 1
            self._successful_reads += 1
            elapsed = now - self._started_at
            self.info.effective_read_fps = self._successful_reads / elapsed if elapsed > 0 else 0.0
            with self._condition:
                if self._latest is not None and self._last_delivered < self._latest[2]:
                    self.info.dropped_frames += 1
                self._latest = (frame, now, self._sequence)
                self._condition.notify_all()

    def read(self) -> FramePacket | None:
        deadline = time.monotonic() + max(0.1, 2.0 / self.info.reported_fps)
        with self._condition:
            while not self._stop.is_set():
                if self._latest is not None and self._latest[2] != self._last_delivered:
                    frame, captured_at, sequence = self._latest
                    self._last_delivered = sequence
                    now = time.monotonic()
                    return FramePacket(
                        frame.copy(),
                        now,
                        captured_at - self._started_at,
                        sequence,
                        max(0.0, now - captured_at),
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(timeout=remaining)
        return None

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        self._thread.join(timeout=1.0)
        self._capture.release()
        self.info.connected = False


class CaptureDeviceFrameSource(LatestFrameSource):
    def __init__(self, device_index: int, **kwargs: object):
        super().__init__(device_index, "capture-device", **kwargs)


class StreamFrameSource(LatestFrameSource):
    def __init__(self, url: str, **kwargs: object):
        super().__init__(url, "stream", **kwargs)


def open_frame_source(
    input_value: str | int,
    *,
    capture_width: int | None = None,
    capture_height: int | None = None,
    capture_fps: float | None = None,
    start_frame: int = 0,
    warmup_seconds: float = 0.0,
) -> FrameSource:
    parsed = parse_input_spec(input_value)
    if isinstance(parsed, int):
        return CaptureDeviceFrameSource(
            parsed,
            capture_width=capture_width,
            capture_height=capture_height,
            capture_fps=capture_fps,
            warmup_seconds=warmup_seconds,
        )
    if "://" in parsed:
        return StreamFrameSource(
            parsed,
            capture_width=capture_width,
            capture_height=capture_height,
            capture_fps=capture_fps,
            warmup_seconds=warmup_seconds,
        )
    return FileFrameSource(parsed, start_frame=start_frame)
