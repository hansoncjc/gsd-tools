"""MP4 encoder error handling and actual H.264 output validation."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from fractions import Fraction
import pytest
from gsd_tools import api, cli, RenderSettings


def test_missing_ffmpeg_fails_before_rendering(monkeypatch, tmp_path):
    source = tmp_path / 'input.gsd'
    source.touch()
    monkeypatch.setattr(api.shutil, 'which', lambda name: None)
    with pytest.raises(RuntimeError, match='FFmpeg was not found'):
        api.mp4(source)
    assert not list(tmp_path.glob('*.mp4'))


@pytest.mark.parametrize('fps', [0, -1, math.nan, math.inf])
def test_invalid_video_fps(fps):
    with pytest.raises(ValueError):
        api.validate_mp4_fps(fps)


def test_mp4_interactive_defaults(monkeypatch, tmp_path):
    source = tmp_path / 'input.gsd'
    source.touch()
    monkeypatch.setattr(cli.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(cli, 'require_ffmpeg', lambda: 'ffmpeg')
    monkeypatch.setattr(cli, 'inspect_gsd', lambda path: api.TrajectoryInfo(path, 300))
    prompts = []
    calls = []

    def read(prompt):
        prompts.append(prompt)
        return ''

    def encode(path, output, **kwargs):
        calls.append((output, kwargs))
        return api.Mp4Result(output, tuple(range(300)), kwargs['fps'], 15, (1200, 1200))

    monkeypatch.setattr('builtins.input', read)
    monkeypatch.setattr(cli, 'mp4', encode)
    assert cli.main(['mp4', str(source)]) == 0
    assert calls[0][0] == source.parent / 'input_perspective.mp4'
    assert calls[0][1]['settings'].size == (1200, 1200)
    assert calls[0][1]['fps'] == 20
    assert calls[0][1]['crf'] == 18
    assert any('CRF' in prompt for prompt in prompts)
    assert not any('Loop' in prompt for prompt in prompts)


def test_failed_encode_preserves_existing_output(monkeypatch, tmp_path):
    from contextlib import contextmanager
    source = tmp_path / 'input.gsd'
    source.touch()
    output = tmp_path / 'existing.mp4'
    output.write_bytes(b'original video')
    monkeypatch.setattr(api, 'require_ffmpeg', lambda: 'ffmpeg')

    @contextmanager
    def trajectory(*args):
        class Pipeline:
            class source:
                num_frames = 2
        yield Pipeline()

    monkeypatch.setattr(api, 'trajectory', trajectory)
    monkeypatch.setattr(api, '_render_sequence', lambda *args: iter(()))

    def fail(command, **kwargs):
        Path(command[-1]).write_bytes(b'partial video')
        raise subprocess.CalledProcessError(1, command, stderr='encoder unavailable')

    monkeypatch.setattr(api.subprocess, 'run', fail)
    with pytest.raises(RuntimeError, match='encoder unavailable'):
        api.mp4(source, output, frames=2)
    assert output.read_bytes() == b'original video'
    assert not list(tmp_path.glob('.gsd-tools-*'))


@pytest.mark.parametrize('view,size,fps', [('front', (320, 280), 15), ('perspective', (321, 281), 12.5)])
def test_actual_h264_frame_rate_size_and_duration(tmp_path, monkeypatch, view, size, fps):
    source = os.environ.get('GSD_TOOLS_TEST_FILE')
    if not source or not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('Requires a GSD fixture, FFmpeg, and ffprobe.')
    folder = tmp_path / 'input with spaces'
    folder.mkdir()
    copied = folder / 'test.gsd'
    shutil.copy2(source, copied)
    working = tmp_path / 'working'
    working.mkdir()
    monkeypatch.chdir(working)
    progress = []
    result = api.mp4(copied, frames=3, fps=fps, settings=RenderSettings(view=view, size=size),
                     progress=lambda done, total: progress.append((done, total)))
    assert result.path == folder / f'test_{view}.mp4'
    assert result.source_frames == (0, 150, 299)
    assert progress == [(1, 3), (2, 3), (3, 3)]
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                            '-show_streams', '-of', 'json', str(result.path)],
                           check=True, capture_output=True, text=True)
    stream = json.loads(probe.stdout)['streams'][0]
    assert stream['codec_name'] == 'h264'
    assert stream['pix_fmt'] == 'yuv420p'
    assert (stream['width'], stream['height']) == result.size
    assert result.size == tuple(n + n % 2 for n in size)
    assert int(stream['nb_frames']) == 3
    assert float(Fraction(stream['avg_frame_rate'])) == pytest.approx(fps)
    assert float(stream['duration']) == pytest.approx(3 / fps, abs=0.0001)
