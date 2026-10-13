"""Shared appearance and camera settings, independent of OVITO initialization."""
from dataclasses import dataclass
import math
from PIL import ImageColor

# Blue entry in the local OVITO 3.15.4 default particle-type palette.
DEFAULT_BLUE = "#6666FF"
PERSPECTIVE_DIRECTION = (-90.0, 120.0, -100.0)
PERSPECTIVE_DISTANCE_SCALE = 1.1
PERSPECTIVE_FOV = math.radians(35)


def parse_color(value: str) -> tuple[float, float, float]:
    """Accept #RRGGBB or a Pillow/CSS color name; 'blue' means OVITO blue."""
    if not isinstance(value, str):
        raise ValueError("Color must be a name or a #RRGGBB string.")
    value = value.strip()
    if value.lower() in {"blue", "ovito-blue"}:
        value = DEFAULT_BLUE
    try:
        rgb = ImageColor.getrgb(value)
    except ValueError as exc:
        raise ValueError(f"Invalid color {value!r}; use a name or #RRGGBB.") from exc
    if len(rgb) != 3:
        raise ValueError("Use an opaque RGB color; transparency is not supported.")
    return tuple(channel / 255 for channel in rgb)


@dataclass(frozen=True)
class RenderSettings:
    view: str = "perspective"
    radius: float = 0.5
    color: str = DEFAULT_BLUE
    size: tuple[int, int] = (1200, 1200)

    def __post_init__(self):
        if self.view not in {"perspective", "front"}:
            raise ValueError("View must be 'perspective' or 'front'.")
        if not math.isfinite(self.radius) or self.radius <= 0:
            raise ValueError("Radius must be finite and greater than zero.")
        parse_color(self.color)
        if len(self.size) != 2 or any(type(n) is not int or n <= 0 for n in self.size):
            raise ValueError("Image size must be two positive integers (width, height).")
