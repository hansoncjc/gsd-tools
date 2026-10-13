"""Regression tests for terminal defaults, overrides and output destinations."""
from pathlib import Path
import pytest
from gsd_tools import cli
from gsd_tools.api import GifResult, TrajectoryInfo
from gsd_tools.frames import select_frames, gif_duration_ms
from gsd_tools.rendering import resolve_output_path


@pytest.fixture
def terminal(monkeypatch, tmp_path):
    source = tmp_path / 'input folder' / 'trajectory.gsd'
    source.parent.mkdir()
    source.touch()
    working = tmp_path / 'working folder'
    working.mkdir()
    monkeypatch.chdir(working)
    monkeypatch.setattr(cli.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(cli, 'inspect_gsd', lambda path: TrajectoryInfo(Path(path), 300))
    calls = []
    prompts = []

    def render_stub(path, output, **kwargs):
        calls.append(('render', path, output, kwargs))
        return output

    def gif_stub(path, output, **kwargs):
        calls.append(('gif', path, output, kwargs))
        frames = select_frames(300, kwargs['start'], kwargs['end'], kwargs['frames'])
        delay = gif_duration_ms(kwargs['fps'])
        return GifResult(output, frames, len(frames), kwargs['fps'], 1000 / delay,
                         delay, len(frames) * delay / 1000)

    monkeypatch.setattr(cli, 'render', render_stub)
    monkeypatch.setattr(cli, 'gif', gif_stub)

    def answer(values):
        entries = iter(values)

        def read(prompt):
            prompts.append(prompt)
            return next(entries)

        monkeypatch.setattr('builtins.input', read)

    return source, calls, prompts, answer


def test_render_enter_accepts_defaults_and_saves_beside_gsd(terminal):
    source, calls, prompts, answer = terminal
    answer([str(source)] + [''] * 6)
    assert cli.main(['render']) == 0
    command, path, output, kwargs = calls[0]
    assert output == source.parent / 'trajectory_front.png'
    assert kwargs['settings'].view == 'front'
    assert kwargs['settings'].radius == 0.5
    assert kwargs['settings'].color == '#6666FF'
    assert kwargs['settings'].size == (1200, 1200)
    assert kwargs['frame'] == -1
    assert any('View (front/perspective) [front]' in p for p in prompts)
    assert any('Sphere radius [0.5]' in p for p in prompts)


def test_render_interactive_overrides_and_invalid_input_retry(terminal, tmp_path, capsys):
    source, calls, prompts, answer = terminal
    destination = tmp_path / 'new output folder'
    answer(['left', 'perspective', '0', '', 'red', '320x280', '50', f'"{destination}"'])
    assert cli.main(['render', str(source)]) == 0
    _, _, output, kwargs = calls[0]
    assert kwargs['settings'].view == 'perspective'
    assert kwargs['settings'].radius == 0.5
    assert kwargs['settings'].color == 'red'
    assert kwargs['settings'].size == (320, 280)
    assert kwargs['frame'] == 50
    assert output == destination / 'trajectory_perspective.png'
    assert 'Invalid input' in capsys.readouterr().out


def test_explicit_flags_are_not_prompted_again(terminal, tmp_path):
    source, calls, prompts, answer = terminal
    answer([])
    output = tmp_path / 'custom.png'
    assert cli.main(['render', str(source), '--view', 'perspective', '--radius', '0.8',
                     '--color', 'red', '--size', '320', '280', '--frame', '10', '-o', str(output)]) == 0
    assert not prompts
    assert calls[0][2] == output
    assert calls[0][3]['settings'].radius == 0.8


def test_render_no_prompt_uses_defaults_in_a_terminal(terminal):
    source, calls, prompts, answer = terminal
    answer([])
    assert cli.main(['render', str(source), '--no-prompt']) == 0
    assert not prompts
    assert calls[0][2] == source.parent / 'trajectory_front.png'


def test_gif_enter_accepts_all_defaults(terminal):
    source, calls, prompts, answer = terminal
    answer([''] * 10)
    assert cli.main(['gif', str(source)]) == 0
    _, _, output, kwargs = calls[0]
    assert kwargs['settings'].view == 'perspective'
    assert kwargs['start'] == 0 and kwargs['end'] == -1
    assert kwargs['frames'] == 300
    assert kwargs['fps'] == 20
    assert kwargs['loop'] == 0
    assert output == source.parent / 'trajectory_perspective.gif'
    assert any('Playback FPS [20.0]' in p for p in prompts)


def test_gif_custom_frame_rate_and_output(terminal, tmp_path, capsys):
    source, calls, prompts, answer = terminal
    output = tmp_path / 'custom.gif'
    answer(['front', '', '', '', '', '', '3', '15', '', str(output)])
    assert cli.main(['gif', str(source)]) == 0
    _, _, actual_output, kwargs = calls[0]
    assert actual_output == output
    assert kwargs['frames'] == 3 and kwargs['fps'] == 15
    assert kwargs['settings'].view == 'front'
    assert 'actual FPS: 14.29' in capsys.readouterr().out


def test_noninteractive_defaults_never_prompt(terminal, monkeypatch):
    source, calls, prompts, answer = terminal
    monkeypatch.setattr(cli.sys.stdin, 'isatty', lambda: False)
    answer([])
    assert cli.main(['gif', str(source)]) == 0
    assert not prompts
    assert calls[0][2] == source.parent / 'trajectory_perspective.gif'


def test_output_file_and_directory_resolution(tmp_path):
    source = tmp_path / 'input' / 'trajectory.gsd'
    assert resolve_output_path(source, None, 'front', '.png') == source.parent / 'trajectory_front.png'
    folder = tmp_path / 'output.with.dots'
    folder.mkdir()
    assert resolve_output_path(source, folder, 'front', '.png') == folder / 'trajectory_front.png'
    assert resolve_output_path(source, tmp_path / 'new-folder', 'perspective', '.gif') == tmp_path / 'new-folder' / 'trajectory_perspective.gif'
    with pytest.raises(ValueError):
        resolve_output_path(source, tmp_path / 'wrong.jpg', 'front', '.png')
