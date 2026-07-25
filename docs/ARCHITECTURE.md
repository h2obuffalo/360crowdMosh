# Architecture

Every source frame is acquired and rendered. At the configured analysis interval, `ActivityAnalyser` updates one normalized source-space heatmap. At the target-evaluation interval, `TargetSelector` compares candidates with the held shot. Every output frame, the geometry-specific camera controller advances using elapsed time and one renderer produces the final view.

`FileFrameSource` preserves source timestamps. Capture-device and stream sources keep one latest-frame slot so latency cannot grow through a queue.

`EquirectangularRenderer` performs one `cv2.remap` for the selected yaw/pitch/FOV. `FlatCropRenderer` slices the original image, clamps the crop inside physical bounds, and resizes or letterboxes without spherical remapping.
