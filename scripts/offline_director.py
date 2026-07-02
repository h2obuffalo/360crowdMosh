#!/usr/bin/env python3
"""Offline/virtual-camera 360 crowd director prototype.

Example:
    python scripts/offline_director.py \
        --input input/test_360.mp4 \
        --output renders/test_reframe.mp4 \
        --config configs/example.yaml \
        --preview
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# Allow running from repo root without installing as a package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from crowd360.config import load_config
from crowd360.motion_tracker import MotionCrowdDirector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-reframe stitched 360 footage toward active crowd motion.")
    parser.add_argument("--input", required=True, help="Input stitched/equirectangular 360 video path or stream URL.")
    parser.add_argument("--output", help="Optional output video path. Omit if only using --virtualcam.")
    parser.add_argument("--config", default="configs/example.yaml", help="YAML config path.")
    parser.add_argument("--preview", action="store_true", help="Show live preview windows.")
    parser.add_argument("--virtualcam", action="store_true", help="Send reframed frames to the first available virtual camera.")
    parser.add_argument("--max-frames", type=int, default=0, help="Optional limit for testing. 0 means no limit.")
    parser.add_argument("--start-frame", type=int, default=0, help="Seek to frame before processing.")
    return parser.parse_args()


def open_writer(path: Optional[str], fps: float, width: int, height: int) -> Optional[cv2.VideoWriter]:
    if not path:
        return None
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Could not open output writer: {path}")
    return writer


def open_virtualcam(enabled: bool, width: int, height: int, fps: float):
    if not enabled:
        return None
    try:
        import pyvirtualcam
    except ImportError as exc:
        raise RuntimeError("pyvirtualcam is not installed. Run: pip install -r requirements.txt") from exc

    return pyvirtualcam.Camera(width=width, height=height, fps=fps)


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)

    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        print(f"ERROR: Could not open input: {args.input}", file=sys.stderr)
        return 2

    input_fps = cap.get(cv2.CAP_PROP_FPS)
    fps = float(cfg.output_fps or input_fps or 25.0)
    if fps <= 1.0 or fps > 240.0:
        fps = 25.0

    if args.start_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, args.start_frame)

    director = MotionCrowdDirector(cfg)
    writer = open_writer(args.output, fps, int(cfg.output_width), int(cfg.output_height))
    cam = open_virtualcam(args.virtualcam, int(cfg.output_width), int(cfg.output_height), fps)

    if cam is not None:
        print(f"Using virtual camera: {cam.device}")

    frame_idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            target = director.update(frame)
            output = director.render_output(frame)

            if writer is not None:
                writer.write(output)

            if cam is not None:
                # pyvirtualcam expects RGB.
                cam.send(cv2.cvtColor(output, cv2.COLOR_BGR2RGB))
                cam.sleep_until_next_frame()

            if args.preview:
                preview = output.copy()
                cv2.putText(
                    preview,
                    f"yaw={target.yaw:6.1f} pitch={target.pitch:5.1f} fov={target.fov:5.1f} score={target.score:5.2f}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow("360 Crowd Mosh - reframed", preview)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break

            frame_idx += 1
            if args.max_frames and frame_idx >= args.max_frames:
                break

            if frame_idx % 100 == 0:
                print(f"processed {frame_idx} frames")
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        if cam is not None:
            cam.close()
        if args.preview:
            cv2.destroyAllWindows()

    print(f"done: processed {frame_idx} frames")
    if args.output:
        print(f"wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
