#!/usr/bin/env python3
"""Export a still frame from a stitched 360 video for mask tuning."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a frame from a video as an image.")
    parser.add_argument("--input", required=True, help="Input video path or stream URL.")
    parser.add_argument("--output", default="renders/mask_reference.jpg", help="Output image path.")
    parser.add_argument("--frame", type=int, default=0, help="Frame number to export.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        print(f"ERROR: Could not open input: {args.input}")
        return 2

    if args.frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, args.frame)

    ok, frame = cap.read()
    cap.release()
    if not ok:
        print(f"ERROR: Could not read frame {args.frame}")
        return 3

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), frame)
    print(f"wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
