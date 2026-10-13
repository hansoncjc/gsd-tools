import math
import pytest
from gsd_tools.frames import select_frames, suggest_fps, gif_duration_ms
from gsd_tools.settings import RenderSettings, parse_color
from gsd_tools.cli import main


def test_sampling_preserves_endpoints_and_order():
    selected = select_frames(300, count=100)
    assert len(selected) == 100
    assert selected[0] == 0 and selected[-1] == 299
    assert len(set(selected)) == 100
    assert all(a < b for a, b in zip(selected, selected[1:]))
    assert select_frames(300, 50, 100, 1) == (100,)
    assert select_frames(300, -3, -1) == (297, 298, 299)


@pytest.mark.parametrize('kwargs', [dict(count=0), dict(count=301), dict(start=100, end=50), dict(end=300)])
def test_invalid_sampling_rejected(kwargs):
    with pytest.raises(ValueError):
        select_frames(300, **kwargs)


def test_timing_exposes_actual_gif_rate():
    assert suggest_fps(100) == 10
    assert suggest_fps(300) == 20
    assert gif_duration_ms(15) == 70
    assert gif_duration_ms(20) == 50
    for fps in [0, -1, math.nan, math.inf, 101, 0.0001]:
        with pytest.raises(ValueError):
            gif_duration_ms(fps)


def test_invalid_appearance_rejected():
    assert parse_color('blue') == parse_color('#6666FF')
    for kwargs in [dict(view='left'), dict(radius=0), dict(radius=math.nan),
                   dict(color='invalid'), dict(size=(0, 760))]:
        with pytest.raises(ValueError):
            RenderSettings(**kwargs)


def test_cli_missing_input_and_unsupported_view(capsys):
    with pytest.raises(SystemExit) as exc:
        main(['render', 'trajectory.gsd', '--view', 'left'])
    assert exc.value.code == 2
    assert main(['render', '/file/does/not/exist.gsd']) == 1
    assert 'does not exist' in capsys.readouterr().err
