# gsd-tools

Generate PNG snapshots and animated GIFs from GSD trajectories. Both commands share the same OVITO rendering code, which can also be called from notebooks and future web workers.

## Installation

Requires Python 3.10+, OVITO, Pillow, and NumPy. Install in a dedicated Python environment:

```bash
python -m pip install -e .
```

If the environment already has all required dependencies, use `python -m pip install -e . --no-deps`. Follow the [official OVITO installation instructions](https://www.ovito.org/manual/python/introduction/installation.html) to choose the appropriate pip or conda installation method.

After installation, run either `gsd-tools` or `python -m gsd_tools`.

## Shared parameters

| Parameter | Default | Description |
|---|---|---|
| `gsd_path` | Required | Input GSD file. Quote paths containing spaces. If omitted in an interactive terminal, the program prompts for the path |
| `--view` | render: `front`; gif: `perspective` | Only `front` and `perspective` are supported |
| `--radius` | `0.5` | Sphere radius in simulation coordinate units; must be greater than zero |
| `--color` | `#6666FF` | Shared particle and simulation box outline color; accepts a hexadecimal value or color name |
| `--size WIDTH HEIGHT` | `1200 1200` | Output size in pixels; uses a fixed canvas without cropping white margins |
| `-o / --output` | Input GSD folder | Accepts an output file or directory. Defaults to `<GSD_stem>_<view>.png` or `.gif`; an existing output with the same name is overwritten |
| `--no-prompt` | Disabled | Use defaults for omitted options without interactive prompts; supported by both commands |

`blue` and `ovito-blue` are aliases for `#6666FF`, the blue `(0.4, 0.4, 1.0)` in the local OVITO 3.15.4 default particle-type palette. Using a fixed color keeps the appearance consistent across file types, chemical element types, and user settings.

Rendering uses a white background and opaque spheres. Bonds are hidden, and the simulation box outline is visible. `front` uses OVITO's default Front direction. `perspective` uses the agreed initial oblique view:

- `camera_dir = (-90, 120, -100)`, equivalent to the unit vector `(-0.499230, 0.665640, -0.554700)`.
- `camera_up = (0, 0, 1)`, keeping the z-axis upright.
- `fov = 35°`.
- After `zoom_all(size=...)`, the camera's distance from the box center is multiplied by **1.1**. If no simulation box is present, the center of the particle bounds is used instead.

## Interactive defaults

In a terminal, both commands prompt for each option that was not supplied on the command line. Every optional prompt shows its default in brackets: press Enter to accept it, or enter a different value. Options supplied explicitly, such as `--view perspective`, are used directly without prompting again.

For example, running `gsd-tools render` displays:

```text
GSD path:
GSD total frames: 300
View (front/perspective) [front]:
Sphere radius [0.5]:
Particle and box color [#6666FF]:
Image size (width height) [1200 1200]:
Frame index (-1 = last) [-1]:
Output file or directory [/path/to/trajectory_front.png]:
```

The default output is beside the input GSD file. You can enter a full output filename or an output directory; directories use the generated filename. Existing directories, paths without a suffix, and paths ending in a slash are treated as directories. Relative output paths are resolved against the current working directory. Invalid option values are reported and prompted again.

Use `--no-prompt` to skip all prompts and use defaults for omitted options. Noninteractive execution also skips prompts; the GSD path must be supplied in both cases.

```bash
gsd-tools render "/path/to/trajectory.gsd" --no-prompt
gsd-tools gif "/path/to/trajectory.gsd" --frames 100 --fps 10 --no-prompt
```

## PNG snapshots: render

Defaults to the last frame and the Front view. Frame indices start at 0; `-1` selects the last frame.

```bash
gsd-tools render "/path/to/trajectory.gsd"
gsd-tools render "/path/to/trajectory.gsd" --view perspective -o snapshot.png
gsd-tools render "/path/to/trajectory.gsd" --frame 100 --radius 0.8 --color '#2E8B57' -o frame100.png
```

## Animations: gif

Defaults to all frames and the Perspective view. The program reads and displays the total GSD frame count. In an interactive terminal, omitted options are prompted with defaults: view, radius, color, image size, starting and ending frames, output frame count, playback FPS, loop count, and output path. Press Enter to use all available frames and accept the recommended FPS, or enter custom values.

```bash
gsd-tools gif "/path/to/trajectory.gsd"
gsd-tools gif "/path/to/trajectory.gsd" --frames 100 --fps 10 -o animation.gif
gsd-tools gif "/path/to/trajectory.gsd" --view front --start 50 --end 299 --frames 60 --color '#6666FF' --fps 15 -o front.gif
gsd-tools gif "/path/to/trajectory.gsd" --frames 100 --no-prompt -o animation.gif
```

| GIF parameter | Default | Description |
|---|---|---|
| `--frames` | All frames in the selected range | Number of output frames, sampled uniformly with both endpoints included; a count of 1 selects the final frame in the range |
| `--start` | `0` | Inclusive starting frame |
| `--end` | `-1` | Inclusive ending frame |
| `--fps` | Automatic recommendation | Playback rate; changing it does not change the selected source frames |
| `--loop` | `0` | GIF repeat count; 0 means repeat forever |
| `--no-prompt` | Disabled | Skip all interactive prompts; useful for batch scripts |

The recommendation is `clamp(round(output_frame_count / 10), 5, 20)`, aiming for a playback duration of about 10 seconds. GIF frame delays have a resolution of 10 ms, so a custom FPS is converted to the nearest representable delay. For example, 15 FPS becomes 70 ms per frame, or approximately 14.286 FPS. The program reports the requested rate, the actual rate, and the final playback duration.

GIF rendering uses one fixed camera and identical canvas dimensions for every frame. Sampling follows source frame indices rather than physical simulation time; even if source time intervals vary, playback uses uniform frame delays. Pillow may combine consecutive identical images and accumulate their delays, so the program reports both the rendered and encoded frame counts.

Automatic framing uses the agreed `zoom_all` procedure. In OVITO 3.15, this method fits the camera to the bounds of the first source frame. If the box changes size substantially during the trajectory, the fixed camera may not cover every later frame. The initial implementation is intended primarily for simulations with a fixed box.

## Python API

```python
from gsd_tools import RenderSettings, inspect_gsd, render, gif

info = inspect_gsd("trajectory.gsd")
print(info.total_frames)

settings = RenderSettings(view="perspective", radius=0.5, color="#6666FF")
render("trajectory.gsd", "snapshot.png", settings=settings)
result = gif("trajectory.gsd", "animation.gif", frames=100, fps=10, settings=settings)
print(result.actual_fps, result.duration_seconds)
```

The Python API does not prompt for input. When `output_path` is omitted, output is saved beside the input GSD file. An explicit output may be a file or directory. OVITO/Qt tasks must run on the process's main thread; a future web application should execute rendering jobs in separate worker processes. Each rendering call temporarily isolates the OVITO scene and restores existing pipelines on completion or failure.

## Validation

```bash
python -m pip install -e '.[test]'
python -m pytest
GSD_TOOLS_TEST_FILE="/path/to/trajectory.gsd" python -m pytest
```

Without `GSD_TOOLS_TEST_FILE`, tests that render an actual trajectory are skipped. When it is set, the tests check PNG views, colors, radius changes, scene restoration, GIF playback duration, and default output placement. Terminal interaction tests also cover accepting defaults with Enter, overriding values, retrying invalid input, and skipping prompts for explicit flags or batch execution.
