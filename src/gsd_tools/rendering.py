"""OVITO scene lifecycle, particle appearance, and the two supported cameras."""
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
import os

from .settings import (RenderSettings, parse_color, PERSPECTIVE_DIRECTION,
                       PERSPECTIVE_DISTANCE_SCALE, PERSPECTIVE_FOV)

_scene_lock = RLock()
_qt_app = None


def load_runtime():
    """Initialize Qt before OVITO; offscreen rendering also works on servers."""
    global _qt_app
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        _qt_app = QApplication.instance() or QApplication([])
        import ovito
    except ImportError as exc:
        raise RuntimeError("OVITO is unavailable. Install gsd-tools in an OVITO Python environment.") from exc
    return ovito


def validate_input(path: str | Path) -> Path:
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() != ".gsd":
        raise ValueError("Input must be a .gsd file.")
    if not path.is_file():
        raise FileNotFoundError(f"GSD file does not exist: {path}")
    return path


def validate_output(path: str | Path, suffix: str, input_path: Path) -> Path:
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() != suffix:
        raise ValueError(f"Output must have a {suffix} extension.")
    if path == input_path:
        raise ValueError("Output cannot replace the input trajectory.")
    return path


@contextmanager
def trajectory(path: str | Path, settings: RenderSettings | None = None):
    """Use an isolated scene and restore existing scene pipelines on exit.

    OVITO/Qt calls must run on the process main thread. Web jobs should use
    separate worker processes, not invoke this from request handler threads.
    """
    path = validate_input(path)
    with _scene_lock:
        ovito = load_runtime()
        from ovito.io import import_file
        from ovito.vis import ParticlesVis

        pipeline = import_file(str(path))
        if pipeline.source.num_frames < 1:
            raise ValueError("The trajectory contains no frames.")
        if settings is not None:
            rgb = parse_color(settings.color)

            def appearance(frame, data):
                if data.particles is None or data.particles.count == 0:
                    raise ValueError(f"Frame {frame} contains no particles to render.")
                particles = data.particles_
                particles.create_property("Color")[:] = rgb
                particles.create_property("Radius")[:] = settings.radius
                particles.vis.shape = ParticlesVis.Shape.Sphere
                # Ignore trajectory-specific ellipsoids, transparency and selection.
                for name in ("Aspherical Shape", "Superquadric Roundness", "Transparency", "Selection"):
                    if name in particles:
                        del particles[name]
                if "Particle Type" in particles:
                    prop = particles["Particle Type_"]
                    for particle_type in list(prop.types):
                        prop.make_mutable(particle_type).shape = ParticlesVis.Shape.Sphere
                if particles.bonds is not None:
                    particles.bonds.vis.enabled = False
                if data.cell is not None:
                    data.cell.vis.enabled = True
                    data.cell.vis.render_cell = True
                    data.cell.vis.rendering_color = rgb

            pipeline.modifiers.append(appearance)

        scene = ovito.scene
        previous = list(scene.pipelines)
        previous_frame = scene.anim.current_frame
        try:
            for existing in previous:
                existing.remove_from_scene()
            if settings is not None:
                pipeline.add_to_scene()
            yield pipeline
        finally:
            if pipeline in scene.pipelines:
                pipeline.remove_from_scene()
            for existing in previous:
                existing.add_to_scene()
            scene.anim.current_frame = previous_frame


def make_viewport(pipeline, settings: RenderSettings, reference_frame: int):
    """Fit once and keep the camera fixed; use the confirmed Perspective preset."""
    import numpy as np
    import ovito
    from ovito.vis import Viewport

    data = pipeline.compute(reference_frame)
    ovito.scene.anim.current_frame = reference_frame
    if settings.view == "front":
        viewport = Viewport(type=Viewport.Type.Front)
    else:
        viewport = Viewport(type=Viewport.Type.Perspective)
        viewport.camera_dir = PERSPECTIVE_DIRECTION
        viewport.camera_up = (0, 0, 1)
        viewport.fov = PERSPECTIVE_FOV
    viewport.zoom_all(size=settings.size)
    if settings.view == "perspective":
        if data.cell is not None:
            matrix = np.asarray(data.cell.matrix)
            center = matrix[:, 3] + matrix[:, :3].sum(axis=1) / 2
        else:
            positions = np.asarray(data.particles.positions)
            center = (positions.min(axis=0) + positions.max(axis=0)) / 2
        viewport.camera_pos = center + PERSPECTIVE_DISTANCE_SCALE * (np.asarray(viewport.camera_pos) - center)
    return viewport


def render_frame(viewport, frame: int, path: Path, settings: RenderSettings):
    from ovito.vis import TachyonRenderer
    viewport.render_image(filename=str(path), size=settings.size, frame=frame,
                          renderer=TachyonRenderer(), background=(1, 1, 1))
