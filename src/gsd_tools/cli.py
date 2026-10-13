"""Local CLI. Interactive prompts stay outside the rendering API."""
import argparse
import sys

from .api import gif, inspect_gsd, render
from .frames import select_frames, suggest_fps, gif_duration_ms
from .settings import DEFAULT_BLUE, RenderSettings


def build_parser():
    parser = argparse.ArgumentParser(prog="gsd-tools", description="Render GSD snapshots and GIFs with OVITO.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command, description, default_view in [
        ("render", "Render one GSD frame as a PNG.", "front"),
        ("gif", "Render a GSD trajectory as a GIF.", "perspective"),
    ]:
        sub = subcommands.add_parser(command, help=description, description=description)
        sub.add_argument("gsd_path", nargs="?", help="Input .gsd file; prompted if omitted in a terminal.")
        sub.add_argument("-o", "--output", help="Output path (default: current directory).")
        sub.add_argument("--view", choices=["perspective", "front"], default=default_view,
                         help=f"Camera preset (default: {default_view}).")
        sub.add_argument("--radius", type=float, default=0.5, help="Sphere radius in simulation units (default: 0.5).")
        sub.add_argument("--color", default=DEFAULT_BLUE, help="Particle and box color: name or '#RRGGBB' (default: #6666FF).")
        sub.add_argument("--size", type=int, nargs=2, metavar=("WIDTH", "HEIGHT"), default=(900, 760))
        if command == "render":
            sub.add_argument("--frame", type=int, default=-1, help="Zero-based frame index; -1 means last frame (default).")
        else:
            sub.add_argument("--start", type=int, default=0, help="Inclusive starting frame (default: 0).")
            sub.add_argument("--end", type=int, default=-1, help="Inclusive ending frame (default: -1 = last).")
            sub.add_argument("--frames", type=int, help="Number of uniformly sampled output frames (default: all).")
            sub.add_argument("--fps", type=float, help="Playback FPS; suggested automatically when omitted.")
            sub.add_argument("--loop", type=int, default=0, help="GIF repeats; 0 = forever (default).")
            sub.add_argument("--no-prompt", action="store_true", help="Use suggested FPS without asking (for scripts).")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    interactive = sys.stdin.isatty()
    try:
        if args.gsd_path is None:
            if not interactive or getattr(args, "no_prompt", False):
                parser.error("Please provide the GSD file path.")
            args.gsd_path = input("GSD path: ").strip().strip("\"'")
        settings = RenderSettings(view=args.view, radius=args.radius, color=args.color, size=tuple(args.size))
        if args.command == "render":
            output = render(args.gsd_path, args.output, frame=args.frame, settings=settings)
            print(f"Saved PNG: {output}")
            return 0

        info = inspect_gsd(args.gsd_path)
        print(f"GSD total frames: {info.total_frames}")
        if args.frames is None and interactive and not args.no_prompt:
            available = len(select_frames(info.total_frames, args.start, args.end))
            entered = input(f"Output frame count [{available}]: ").strip()
            if entered:
                args.frames = int(entered)
        selected = select_frames(info.total_frames, args.start, args.end, args.frames)
        recommended = suggest_fps(len(selected))
        print(f"Output frames: {len(selected)}; source range: {selected[0]}–{selected[-1]}")
        print(f"Suggested FPS: {recommended} (aim: about 10 s, limited to 5–20 FPS)")
        fps = args.fps
        if fps is None and interactive and not args.no_prompt:
            entered = input(f"Playback FPS [{recommended}]: ").strip()
            fps = float(entered) if entered else float(recommended)
        if fps is None:
            fps = float(recommended)
        duration_ms = gif_duration_ms(fps)
        print(f"Requested FPS: {fps:g}; actual FPS: {1000 / duration_ms:.4g}; "
              f"estimated duration: {len(selected) * duration_ms / 1000:.2f} s")

        def progress(done, total):
            if done == 1 or done == total or done % max(1, total // 20) == 0:
                print(f"Rendered {done}/{total} frames", flush=True)

        result = gif(args.gsd_path, args.output, start=args.start, end=args.end,
                     frames=args.frames, fps=fps, loop=args.loop, settings=settings, progress=progress)
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
