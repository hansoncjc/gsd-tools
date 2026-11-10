"""GSD snapshots and animations backed by OVITO."""
from .api import GifResult, Mp4Result, TrajectoryInfo, gif, mp4, inspect_gsd, render
from .settings import RenderSettings

__version__ = "0.1.0"
__all__ = ["gif", "mp4", "render", "inspect_gsd", "RenderSettings", "GifResult", "Mp4Result", "TrajectoryInfo"]
