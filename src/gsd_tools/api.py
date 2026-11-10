"""Prompt-free public functions shared by CLI, notebooks and future web workers."""
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable
import math
import shutil
import subprocess

from PIL import Image

from .frames import normalize_frame, select_frames, suggest_fps, gif_duration_ms
from .settings import RenderSettings
from .rendering import trajectory, validate_input, resolve_output_path, make_viewport, render_frame


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


@dataclass(frozen=True)
class Mp4Result:
    path: Path
    source_frames: tuple[int, ...]
    fps: float
    duration_seconds: float
    size: tuple[int, int]


def validate_mp4_fps(fps: float) -> float:
    """Validate video playback FPS without GIF frame-delay quantization."""
    fps = float(fps)
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("FPS must be finite and greater than zero.")
    return fps


def require_ffmpeg() -> str:
    """Locate the external encoder before starting expensive rendering."""
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise RuntimeError("FFmpeg was not found on PATH. Install FFmpeg first (macOS: brew install ffmpeg).")
    return executable


def _render_sequence(pipeline, selected, settings, folder, progress):
    """Render chronological PNG frames with one fixed camera for GIF or MP4."""
    viewport = make_viewport(pipeline, settings, selected[-1])
    for index, frame in enumerate(selected):
        path = Path(folder) / f"{index:08d}.png"
        render_frame(viewport, frame, path, settings)
        if progress is not None:
            progress(index + 1, len(selected))
        yield path


def inspect_gsd(gsd_path: str | Path) -> TrajectoryInfo:
    with trajectory(gsd_path) as pipeline:
        return TrajectoryInfo(validate_input(gsd_path), pipeline.source.num_frames)


def render(gsd_path: str | Path, output_path: str | Path | None = None, *,
           frame: int = -1, settings: RenderSettings | None = None) -> Path:
    """Render a PNG; default to the last frame, Front view and radius 0.5.

    Output defaults to the input GSD folder. An explicit output can be a file
    or directory; relative paths are resolved against the working directory.
    """
    settings = settings or RenderSettings(view="front")
    source = validate_input(gsd_path)
    output = resolve_output_path(source, output_path, settings.view, ".png")
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
    Output defaults to the input GSD folder; an explicit output may be a file
    or directory.
    """
    settings = settings or RenderSettings(view="perspective")
    source = validate_input(gsd_path)
    output = resolve_output_path(source, output_path, settings.view, ".gif")
    if type(loop) is not int or not 0 <= loop <= 65535:
        raise ValueError("Loop must be an integer between 0 and 65535 (0 = forever).")
    with trajectory(source, settings) as pipeline:
        selected = select_frames(pipeline.source.num_frames, start, end, frames)
        requested_fps = float(suggest_fps(len(selected)) if fps is None else fps)
        duration_ms = gif_duration_ms(requested_fps)
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="gsd-tools-") as temp:
            images = []
            try:
                for path in _render_sequence(pipeline, selected, settings, temp, progress):
                    with Image.open(path) as image:
                        # Store compact indexed frames; do not accumulate RGB bitmaps.
                        images.append(image.convert("RGB").quantize(colors=256))
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


def mp4(gsd_path: str | Path, output_path: str | Path | None = None, *,
        start: int = 0, end: int = -1, frames: int | None = None,
        fps: float | None = None, crf: int = 18,
        settings: RenderSettings | None = None,
        progress: Callable[[int, int], None] | None = None) -> Mp4Result:
    """Render GSD frames and encode H.264/yuv420p MP4 using external FFmpeg.

    Defaults to Perspective and the input GSD folder. Odd image dimensions
    are padded with one white pixel to satisfy yuv420p requirements.
    Existing outputs are replaced only after successful encoding. Frames use
    uniform playback intervals rather than physical simulation timestamps.
    """
    settings = settings or RenderSettings(view="perspective")
    source = validate_input(gsd_path)
    output = resolve_output_path(source, output_path, settings.view, ".mp4")
    executable = require_ffmpeg()
    if type(crf) is not int or not 0 <= crf <= 51:
        raise ValueError("CRF must be an integer between 0 and 51 (lower = higher quality).")
    if fps is not None:
        fps = validate_mp4_fps(fps)
    with trajectory(source, settings) as pipeline:
        selected = select_frames(pipeline.source.num_frames, start, end, frames)
        fps = validate_mp4_fps(suggest_fps(len(selected)) if fps is None else fps)
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="gsd-tools-") as temp:
            for _ in _render_sequence(pipeline, selected, settings, temp, progress):
                pass
            # Encode beside the destination so the final replacement is atomic.
            with TemporaryDirectory(prefix=".gsd-tools-", dir=output.parent) as encoded_dir:
                encoded = Path(encoded_dir) / "video.mp4"
                command = [
                    executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                    "-framerate", str(fps), "-start_number", "0",
                    "-i", str(Path(temp) / "%08d.png"), "-frames:v", str(len(selected)),
                    "-an", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                    "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=white",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(encoded),
                ]
                try:
                    subprocess.run(command, check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as exc:
                    raise RuntimeError(f"FFmpeg encoding failed: {exc.stderr.strip()[-2000:]}") from exc
                if not encoded.is_file() or encoded.stat().st_size == 0:
                    raise RuntimeError("FFmpeg did not produce a valid output file.")
                encoded.replace(output)
    size = tuple(n + n % 2 for n in settings.size)
    return Mp4Result(output, selected, fps, len(selected) / fps, size)
