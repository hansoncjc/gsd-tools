"""GSD snapshots and animations backed by OVITO."""
from .api import GifResult, TrajectoryInfo, gif, inspect_gsd, render
from .settings import RenderSettings

__version__ = "0.1.0"
__all__ = ["gif", "render", "inspect_gsd", "RenderSettings", "GifResult", "TrajectoryInfo"]
