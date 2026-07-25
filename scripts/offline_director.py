#!/usr/bin/env python3
"""Run the crowd director on a file, capture device, or OpenCV stream."""
from __future__ import annotations
import argparse, logging, sys
from pathlib import Path
from typing import Any
import cv2
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from crowd360.config import load_config
from crowd360.diagnostics import render_diagnostics
from crowd360.director import MotionCrowdDirector
from crowd360.geometry import detect_input_mode
from crowd360.output import TimestampResampler
from crowd360.rendering import FlatCropRenderer
from crowd360.sources import open_frame_source
LOG=logging.getLogger("crowd360")

def arguments(argv=None):
 p=argparse.ArgumentParser(description="Motion-directed 16:9 output from flat or stitched 360 video")
 p.add_argument("--input",required=True,help="File, OpenCV URL, or device index such as 0")
 p.add_argument("--input-mode",choices=("auto","equirectangular","flat"))
 p.add_argument("--output"); p.add_argument("--output-fps",type=float)
 p.add_argument("--config",default="configs/example.yaml")
 p.add_argument("--flat-aspect-mode",choices=("crop","letterbox"))
 p.add_argument("--capture-width",type=int); p.add_argument("--capture-height",type=int)
 p.add_argument("--capture-fps",type=float); p.add_argument("--capture-warmup-seconds",type=float,default=0)
 p.add_argument("--preview",action="store_true"); p.add_argument("--diagnostics",action="store_true")
 p.add_argument("--virtualcam",action="store_true"); p.add_argument("--max-frames",type=int,default=0)
 p.add_argument("--start-frame",type=int,default=0); p.add_argument("--log-level",default="INFO")
 return p.parse_args(argv)

def writer(path,fps,w,h):
 if not path:return None
 target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
 out=cv2.VideoWriter(str(target),cv2.VideoWriter_fourcc(*"mp4v"),fps,(w,h))
 if not out.isOpened(): raise RuntimeError(f"Could not open output writer: {path}")
 return out

def virtualcam(enabled,w,h,fps)->Any|None:
 if not enabled:return None
 try: import pyvirtualcam
 except ImportError as exc: raise RuntimeError("Install the project live extra for --virtualcam") from exc
 return pyvirtualcam.Camera(width=w,height=h,fps=fps)

def main(argv=None):
 a=arguments(argv); logging.basicConfig(level=getattr(logging,a.log_level.upper()),format="%(levelname)s %(name)s: %(message)s")
 try:
  c=load_config(a.config)
  if a.input_mode:c.input_mode=a.input_mode
  if a.flat_aspect_mode:c.flat_aspect_mode=a.flat_aspect_mode
  if a.output_fps:c.output_fps=a.output_fps
  c.validate()
  source=open_frame_source(a.input,capture_width=a.capture_width,capture_height=a.capture_height,capture_fps=a.capture_fps,start_frame=a.start_frame,warmup_seconds=a.capture_warmup_seconds)
 except (RuntimeError,ValueError) as exc: LOG.error("%s",exc); return 2
 out=cam=None; processed=written=0; last_output=last_timestamp=None
 try:
  packet=source.read()
  if packet is None: raise RuntimeError("Input opened but produced no frame")
  h,w=packet.frame.shape[:2]; mode=detect_input_mode(w,h,c.input_mode)
  LOG.info("Input geometry: %s (requested=%s, frame=%dx%d)",mode,c.input_mode,w,h)
  fps=float(c.output_fps or source.info.reported_fps or 25); fps=fps if 1<=fps<=240 else 25
  out=writer(a.output,fps,c.output_width,c.output_height); cam=virtualcam(a.virtualcam,c.output_width,c.output_height,fps)
  director=MotionCrowdDirector(c,mode); resampler=TimestampResampler(fps) if c.output_fps else None
  while packet is not None:
   result=director.update(packet.frame,packet.source_timestamp,1/source.info.reported_fps)
   last_output,last_timestamp=result.output,packet.source_timestamp
   count=resampler.emit_count(packet.source_timestamp) if resampler else 1
   if out:
    for _ in range(count): out.write(result.output); written+=1
   if cam: cam.send(cv2.cvtColor(result.output,cv2.COLOR_BGR2RGB)); cam.sleep_until_next_frame()
   if a.diagnostics:
    crop=director.renderer.last_crop if isinstance(director.renderer,FlatCropRenderer) else None
    cv2.imshow("Crowd camera diagnostics",render_diagnostics(packet.frame,result,c,mode,source.info,crop=crop,output_fps=fps))
   elif a.preview: cv2.imshow("Crowd camera output",result.output)
   if (a.preview or a.diagnostics) and cv2.waitKey(1)&0xff in (27,ord("q")): break
   processed+=1
   if a.max_frames and processed>=a.max_frames: break
   packet=source.read()
  if out and resampler and last_output is not None and last_timestamp is not None:
   for _ in range(resampler.flush_count(last_timestamp+1/source.info.reported_fps)): out.write(last_output); written+=1
  LOG.info("Done: processed=%d, wrote=%d",processed,written); return 0
 except (RuntimeError,ValueError) as exc: LOG.error("%s",exc); return 2
 finally:
  source.close()
  if out: out.release()
  if cam: cam.close()
  if a.preview or a.diagnostics: cv2.destroyAllWindows()
if __name__=="__main__": raise SystemExit(main())
