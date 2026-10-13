"""Prompt-free public functions shared by CLI, notebooks and future web workers."""
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from PIL import Image

from .frames import normalize_frame, select_frames, suggest_fps, gif_duration_ms
from .settings import RenderSettings
from .rendering import trajectory, validate_input, validate_output, make_viewport, render_frame


@dataclass(frozen=True)
class TrajectoryInfo:
    path: Path
    total_frames: int


@dataclass(frozen=True)
class GifResult:
    path: Path
    source_frames: tuple[int, ...]
    encoded_frames: int
    requested_fps: float
    actual_fps: float
    frame_duration_ms: int
    duration_seconds: float


def inspect_gsd(gsd_path: str | Path) -> TrajectoryInfo:
    with trajectory(gsd_path) as pipeline:
        return TrajectoryInfo(validate_input(gsd_path), pipeline.source.num_frames)


def render(gsd_path: str | Path, output_path: str | Path | None = None, *,
           frame: int = -1, settings: RenderSettings | None = None) -> Path:
    """Render a PNG; default to the last frame, Front view and radius 0.5."""
    settings = settings or RenderSettings(view="front")
    source = validate_input(gsd_path)
    output = validate_output(output_path or Path.cwd() / f"{source.stem}_{settings.view}.png", ".png", source)
    with trajectory(source, settings) as pipeline:
        frame = normalize_frame(frame, pipeline.source.num_frames)
        viewport = make_viewport(pipeline, settings, frame)
        output.parent.mkdir(parents=True, exist_ok=True)
        render_frame(viewport, frame, output, settings)
    return output


def gif(gsd_path: str | Path, output_path: str | Path | None = None, *,
        start: int = 0, end: int = -1, frames: int | None = None,
        fps: float | None = None, loop: int = 0,
        settings: RenderSettings | None = None,
        progress: Callable[[int, int], None] | None = None) -> GifResult:
    """Render selected GSD frames to a GIF using one fixed camera and canvas.

    Equal frame delays represent equal *frame-index* intervals, not physical
    simulation time. Consecutive identical images may be coalesced by Pillow.
    """
    settings = settings or RenderSettings(view="perspective")
    source = validate_input(gsd_path)
    output = validate_output(output_path or Path.cwd() / f"{source.stem}_{settings.view}.gif", ".gif", source)
    if type(loop) is not int or not 0 <= loop <= 65535:
        raise ValueError("Loop must be an integer between 0 and 65535 (0 = forever).")
    with trajectory(source, settings) as pipeline:
        selected = select_frames(pipeline.source.num_frames, start, end, frames)
        requested_fps = float(suggest_fps(len(selected)) if fps is None else fps)
        duration_ms = gif_duration_ms(requested_fps)
        viewport = make_viewport(pipeline, settings, selected[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="gsd-tools-") as temp:
            images = []
            try:
                for i, frame in enumerate(selected):
                    path = Path(temp) / f"{i:08d}.png"
                    render_frame(viewport, frame, path, settings)
                    with Image.open(path) as image:
                        # Store compact indexed frames; do not accumulate RGB bitmaps.
                        images.append(image.convert("RGB").quantize(colors=256))
                    if progress is not None:
                        progress(i + 1, len(selected))
                images[0].save(output, format="GIF", save_all=True, append_images=images[1:],
                               duration=duration_ms, loop=loop, disposal=2, optimize=False)
            finally:
                for image in images:
                    image.close()
    with Image.open(output) as image:
        encoded_frames = image.n_frames
        total_duration = 0
        for i in range(encoded_frames):
            image.seek(i)
            total_duration += image.info.get("duration", 0)
    return GifResult(output, selected, encoded_frames, requested_fps, 1000 / duration_ms,
                     duration_ms, total_duration / 1000)
