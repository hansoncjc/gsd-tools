"""Trajectory frame selection and GIF playback timing."""
import math


def normalize_frame(frame: int, total_frames: int) -> int:
    if total_frames < 1:
        raise ValueError("The trajectory contains no frames.")
    if type(frame) is not int:
        raise ValueError("Frame indices must be integers.")
    index = frame + total_frames if frame < 0 else frame
    if not 0 <= index < total_frames:
        raise ValueError(f"Frame {frame} is outside the trajectory ({total_frames} frames).")
    return index


def select_frames(total_frames: int, start: int = 0, end: int = -1,
                  count: int | None = None) -> tuple[int, ...]:
    """Inclusive range; uniformly sample count frames including both endpoints.

    For count=1, select the final frame in the chosen range.
    """
    start = normalize_frame(start, total_frames)
    end = normalize_frame(end, total_frames)
    if start > end:
        raise ValueError("Start frame must not be after end frame.")
    available = end - start + 1
    if count is None:
        return tuple(range(start, end + 1))
    if type(count) is not int or not 1 <= count <= available:
        raise ValueError(f"Output frame count must be between 1 and {available}.")
    if count == 1:
        return (end,)
    return tuple(start + round(i * (available - 1) / (count - 1)) for i in range(count))


def suggest_fps(frame_count: int) -> int:
    """Aim for about ten seconds, clamped to 5–20 FPS."""
    if frame_count < 1:
        raise ValueError("At least one frame is required.")
    return max(5, min(20, round(frame_count / 10)))


def gif_duration_ms(fps: float) -> int:
    """Round to GIF's 10 ms timing units and return the actual frame delay."""
    if not math.isfinite(fps) or not 0 < fps <= 100:
        raise ValueError("FPS must be finite, greater than zero, and at most 100.")
    duration = max(1, round(100 / fps)) * 10
    if duration > 655350:
        raise ValueError("FPS is too low for a GIF frame delay (maximum 655.35 s).")
    return duration
