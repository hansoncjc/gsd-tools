"""Local CLI with Enter-to-accept defaults and prompt-free batch operation."""
import argparse
import math
import sys

from .api import gif, inspect_gsd, render
from .frames import normalize_frame, select_frames, suggest_fps, gif_duration_ms
from .rendering import validate_input, resolve_output_path
from .settings import DEFAULT_BLUE, RenderSettings, parse_color


def build_parser():
    parser = argparse.ArgumentParser(prog="gsd-tools", description="Render GSD snapshots and GIFs with OVITO.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command, description, default_view in [
        ("render", "Render one GSD frame as a PNG.", "front"),
        ("gif", "Render a GSD trajectory as a GIF.", "perspective"),
    ]:
        sub = subcommands.add_parser(command, help=description, description=description)
        sub.set_defaults(default_view=default_view)
        sub.add_argument("gsd_path", nargs="?", help="Input .gsd file; prompted if omitted in a terminal.")
        sub.add_argument("-o", "--output", help="Output file or directory (default: input GSD folder).")
        sub.add_argument("--view", choices=["perspective", "front"],
                         help=f"Camera preset (default: {default_view}).")
        sub.add_argument("--radius", type=float, help="Sphere radius in simulation units (default: 0.5).")
        sub.add_argument("--color", help="Particle and box color: name or '#RRGGBB' (default: #6666FF).")
        sub.add_argument("--size", type=int, nargs=2, metavar=("WIDTH", "HEIGHT"),
                         help="Output dimensions (default: 1200 1200).")
        sub.add_argument("--no-prompt", action="store_true",
                         help="Use defaults for omitted options without interactive prompts.")
        if command == "render":
            sub.add_argument("--frame", type=int, help="Zero-based frame index; -1 means last frame (default).")
        else:
            sub.add_argument("--start", type=int, help="Inclusive starting frame (default: 0).")
            sub.add_argument("--end", type=int, help="Inclusive ending frame (default: -1 = last).")
            sub.add_argument("--frames", type=int, help="Number of uniformly sampled output frames (default: all).")
            sub.add_argument("--fps", type=float, help="Playback FPS; suggested automatically when omitted.")
            sub.add_argument("--loop", type=int, help="GIF repeats; 0 = forever (default).")
    return parser


def prompt_option(value, label, default, convert, interactive):
    """Prompt only for omitted options, retrying invalid input without losing defaults."""
    if value is not None:
        return value
    if not interactive:
        return default
    displayed = " ".join(map(str, default)) if isinstance(default, tuple) else str(default)
    while True:
        entered = input(f"{label} [{displayed}]: ").strip()
        if not entered:
            return default
        try:
            return convert(entered)
        except (ValueError, OSError) as exc:
            print(f"Invalid input: {exc}")


def parse_view(value):
    value = value.lower()
    if value not in {"front", "perspective"}:
        raise ValueError("Choose 'front' or 'perspective'.")
    return value


def parse_radius(value):
    radius = float(value)
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("Radius must be finite and greater than zero.")
    return radius


def parse_size(value):
    dimensions = tuple(int(n) for n in value.lower().replace("x", " ").split())
    if len(dimensions) != 2 or any(n <= 0 for n in dimensions):
        raise ValueError("Enter two positive dimensions, such as '1200 1200'.")
    return dimensions


def parse_color_option(value):
    parse_color(value)
    return value


def parse_loop(value):
    loop = int(value)
    if not 0 <= loop <= 65535:
        raise ValueError("Loop must be between 0 and 65535 (0 = forever).")
    return loop


def clean_path(value):
    return value.strip().strip("\"'")


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    interactive = sys.stdin.isatty() and not args.no_prompt
    try:
        if args.gsd_path is None:
            if not interactive:
                parser.error("Please provide the GSD file path.")
            args.gsd_path = clean_path(input("GSD path: "))
        source = validate_input(args.gsd_path)
        info = inspect_gsd(source)
        print(f"GSD total frames: {info.total_frames}")
        view = prompt_option(args.view, "View (front/perspective)", args.default_view, parse_view, interactive)
        radius = prompt_option(args.radius, "Sphere radius", 0.5, parse_radius, interactive)
        color = prompt_option(args.color, "Particle and box color", DEFAULT_BLUE, parse_color_option, interactive)
        size = prompt_option(args.size, "Image size (width height)", (1200, 1200), parse_size, interactive)
        settings = RenderSettings(view=view, radius=radius, color=color, size=tuple(size))

        if args.command == "render":
            frame = prompt_option(args.frame, "Frame index (-1 = last)", -1,
                                  lambda value: normalize_frame(int(value), info.total_frames), interactive)
        else:
            start = prompt_option(args.start, "Start frame", 0,
                                  lambda value: normalize_frame(int(value), info.total_frames), interactive)

            def parse_end(value):
                end = int(value)
                select_frames(info.total_frames, start, end)
                return end

            end = prompt_option(args.end, "End frame (-1 = last)", -1, parse_end, interactive)
            available = len(select_frames(info.total_frames, start, end))

            def parse_count(value):
                count = int(value)
                select_frames(info.total_frames, start, end, count)
                return count

            count = prompt_option(args.frames, "Output frame count", available, parse_count, interactive)
            selected = select_frames(info.total_frames, start, end, count)
            recommended = suggest_fps(len(selected))
            print(f"Output frames: {len(selected)}; source range: {selected[0]}–{selected[-1]}")
            print(f"Suggested FPS: {recommended} (aim: about 10 s, limited to 5–20 FPS)")

            def parse_fps(value):
                fps = float(value)
                gif_duration_ms(fps)
                return fps

            fps = prompt_option(args.fps, "Playback FPS", float(recommended), parse_fps, interactive)
            duration_ms = gif_duration_ms(fps)
            print(f"Requested FPS: {fps:g}; actual FPS: {1000 / duration_ms:.4g}; "
                  f"estimated duration: {len(selected) * duration_ms / 1000:.2f} s")
            loop = prompt_option(args.loop, "Loop (0 = forever)", 0, parse_loop, interactive)

        suffix = ".png" if args.command == "render" else ".gif"
        default_output = resolve_output_path(source, None, view, suffix)
        output = prompt_option(args.output, "Output file or directory", default_output,
                               lambda value: resolve_output_path(source, clean_path(value), view, suffix),
                               interactive)
        output = resolve_output_path(source, output, view, suffix)
        if args.command == "render":
            result = render(source, output, frame=frame, settings=settings)
            print(f"Saved PNG: {result}")
            return 0

        def progress(done, total):
            if done == 1 or done == total or done % max(1, total // 20) == 0:
                print(f"Rendered {done}/{total} frames", flush=True)

        result = gif(source, output, start=start, end=end, frames=count, fps=fps,
                     loop=loop, settings=settings, progress=progress)
        print(f"Saved GIF: {result.path}")
        print(f"Rendered frames: {len(result.source_frames)}; encoded frames: {result.encoded_frames}; "
              f"playback duration: {result.duration_seconds:.2f} s")
        return 0
    except (ValueError, OSError, RuntimeError, EOFError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
