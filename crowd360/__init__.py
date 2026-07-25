"""Motion-directed virtual crowd camera for flat and equirectangular video."""

from .config import DirectorConfig, load_config
from .director import MotionCrowdDirector
from .geometry import detect_input_mode

__all__ = ["DirectorConfig", "MotionCrowdDirector", "detect_input_mode", "load_config"]
