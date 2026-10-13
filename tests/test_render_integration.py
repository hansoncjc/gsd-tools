"""Actual OVITO rendering tests, enabled using a supplied GSD fixture."""
import os
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from gsd_tools import RenderSettings, gif, inspect_gsd, render
from gsd_tools.rendering import load_runtime


@pytest.fixture
def source():
    path = os.environ.get('GSD_TOOLS_TEST_FILE')
    if not path:
        pytest.skip('Set GSD_TOOLS_TEST_FILE to run actual OVITO rendering tests.')
    return Path(path)


def nonwhite_bounds(path):
    with Image.open(path) as image:
        rgb = np.asarray(image.convert('RGB'), dtype=np.int16)
    ys, xs = np.where(np.any(rgb < 240, axis=2))
    return rgb, (xs.min(), ys.min(), xs.max(), ys.max())


def test_actual_views_color_radius_and_scene_restoration(source, tmp_path):
    ovito = load_runtime()
    from ovito.io import import_file
    existing = import_file(str(source))
    existing.add_to_scene()
    try:
        before = list(ovito.scene.pipelines)
        previous_frame = ovito.scene.anim.current_frame
        settings = RenderSettings(view='perspective', size=(480, 400))
        persp = render(source, tmp_path / 'perspective.png', settings=settings)
        rgb, bounds = nonwhite_bounds(persp)
        assert rgb.shape == (400, 480, 3)
        assert bounds[0] > 0 and bounds[1] > 0 and bounds[2] < 479 and bounds[3] < 399
        assert np.any((rgb[:, :, 2] > rgb[:, :, 0] + 10) & (rgb[:, :, 0] < 200))
        assert list(ovito.scene.pipelines) == before
        assert ovito.scene.anim.current_frame == previous_frame

        front = render(source, tmp_path / 'front.png', settings=RenderSettings(view='front', size=(480, 400)))
        with Image.open(front) as image:
            assert not np.array_equal(rgb, np.asarray(image))

        small = render(source, tmp_path / 'small.png', settings=RenderSettings(view='front', color='red', radius=0.5, size=(480, 400)))
        large = render(source, tmp_path / 'large.png', settings=RenderSettings(view='front', color='red', radius=1.0, size=(480, 400)))
        a, _ = nonwhite_bounds(small)
        b, _ = nonwhite_bounds(large)
        red_a = (a[:, :, 0] > a[:, :, 1] + 10) & (a[:, :, 1] < 200)
        red_b = (b[:, :, 0] > b[:, :, 1] + 10) & (b[:, :, 1] < 200)
        assert red_b.sum() > red_a.sum()

        with pytest.raises(ValueError):
            render(source, tmp_path / 'bad.png', frame=inspect_gsd(source).total_frames)
        assert list(ovito.scene.pipelines) == before
    finally:
        existing.remove_from_scene()


def test_actual_gif_frame_count_and_timing(source, tmp_path):
    info = inspect_gsd(source)
    count = min(3, info.total_frames)
    result = gif(source, tmp_path / 'test.gif', frames=count, fps=15,
                 settings=RenderSettings(view='front', size=(320, 280)))
    assert len(result.source_frames) == count
    assert result.source_frames[-1] == info.total_frames - 1
    assert result.frame_duration_ms == 70
    assert result.duration_seconds == pytest.approx(count * 0.07)
    with Image.open(result.path) as image:
        assert image.size == (320, 280)
        assert image.info['loop'] == 0
        assert image.n_frames == result.encoded_frames
        assert 1 <= image.n_frames <= count


def test_api_default_outputs_are_in_the_input_folder(source, tmp_path, monkeypatch):
    import shutil
    source_folder = tmp_path / 'input'
    source_folder.mkdir()
    copied_source = source_folder / source.name
    shutil.copy2(source, copied_source)
    working_folder = tmp_path / 'working'
    working_folder.mkdir()
    monkeypatch.chdir(working_folder)
    png = render(copied_source, settings=RenderSettings(view='front', size=(320, 280)))
    animation = gif(copied_source, frames=2, fps=10,
                    settings=RenderSettings(view='perspective', size=(320, 280)))
    assert png.parent == source_folder
    assert animation.path.parent == source_folder
    assert png.is_file() and animation.path.is_file()
    assert not list(working_folder.iterdir())
