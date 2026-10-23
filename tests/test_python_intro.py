"""Native intro behavior, independent of clocks, user state and network."""
from dataclasses import replace

import pytest

from maxpane_dashboard.intro.settings import IntroConfig, Egg, load_config, palette
from maxpane_dashboard.intro.sequence import IntroSequence, LINES


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('intro must stay offline')
    monkeypatch.setattr('httpx.Client.send', fail)
    monkeypatch.setattr('httpx.AsyncClient.send', fail)


def model(**changes):
    clock = [0.0]
    seq = IntroSequence(replace(IntroConfig(), **changes), clock=lambda: clock[0])
    return seq, clock


def test_typewriter_pacing_blanks_and_final_prompt():
    seq, clock = model(typewriter_speed_ms=100)
    clock[0] = .1
    assert seq.typewriter_text() == ('W', LINES[0], True)
    clock[0] = 1.3
    assert seq.typewriter_text()[0] == 'Wake up, Pepe'
    clock[0] = 1.4
    assert seq.typewriter_text()[0] == 'Wake up, Pepe'
    clock[0] = 1.5
    assert seq.typewriter_text()[0] == 'Wake up, Pepe.'
    clock[0] = 2
    assert seq.typewriter_text()[0] == LINES[0]
    clock[0] = 3.2
    assert seq.typewriter_text()[0] == ''
    clock[0] = seq.typewriter_duration
    seq.tick()
    assert seq.stage == 'prompt'


def test_intro_greetings_use_pepe_and_swarm():
    assert LINES == ('Wake up, Pepe...', 'The Swarm has you...',
                     'Follow the white frog.', 'Lock in, Pepe.')


def test_yes_rain_reveal_hold_and_final_key():
    seq, clock = model()
    seq.enter('prompt')
    seq.key('y', 'y')
    assert seq.response == 'locking in...'
    clock[0] = .79; seq.tick()
    assert seq.stage == 'prompt'
    clock[0] = .8; seq.tick()
    assert seq.stage == 'rain'
    clock[0] += 7.5; seq.tick()
    assert seq.stage == 'logo'
    seq.key('x', 'x')
    assert seq.result is None
    clock[0] += 3
    seq.key('x', 'x')
    assert seq.result == 'dashboard'


@pytest.mark.parametrize('word,message,action', [
    ('', 'locking in...', 'rain'), ('n', 'Maybe next time, Pepe.', 'exit'),
    ('ngmi', 'Not with that attitude. Try again.', 'prompt'),
    ('gm', "gm Pepe. Let's go.", 'rain'),
    ('wat', 'There is no spoon. Try again.', 'prompt'),
])
def test_prompt_choices(word, message, action):
    seq, clock = model(); seq.enter('prompt')
    for char in word: seq.key(char, char)
    assert seq.response is None  # N must remain editable for ngmi.
    seq.key('enter')
    assert seq.response == message
    clock[0] = 1; seq.tick()
    assert seq.stage == action
    if action == 'prompt': assert seq.buffer == '' and seq.response is None


def test_custom_egg_precedence_bounds_and_releases():
    seq, clock = model(easter_eggs=(Egg('GM', 'Custom', 'exit'),))
    seq.enter('prompt')
    seq.key('y', 'y', kind='release')
    assert not seq.response
    for char in 'gm': seq.key(char, char)
    seq.key('enter'); assert seq.response == 'Custom'
    clock[0] = 1; seq.tick(); assert seq.result == 'exit'
    seq.enter('prompt')
    for _ in range(80): seq.key('x', '界')
    assert len(seq.buffer) == 64
    seq.key('backspace'); assert len(seq.buffer) == 63


@pytest.mark.parametrize('skip', ['any', 'esc', 'none', 'unknown'])
@pytest.mark.parametrize('stage', ['typewriter', 'prompt', 'rain', 'logo'])
def test_skip_and_unconditional_interrupt(skip, stage):
    seq, _ = model(skip_key=skip); seq.enter(stage)
    seq.key('escape')
    assert (seq.result == 'dashboard') == (skip in ('any', 'esc'))
    seq.enter(stage); seq.key('ctrl+c')
    assert seq.result == 'interrupt'


def test_any_key_skip_exempts_prompt_and_logo_hold():
    for stage in ('prompt', 'logo'):
        seq, _ = model(); seq.enter(stage); seq.key('g', 'g')
        assert seq.result is None
    seq, _ = model(); seq.key('a', 'a'); assert seq.result == 'dashboard'


def test_settings_and_color_fallback(tmp_path):
    path = tmp_path / 'config.toml'
    assert load_config(path) == IntroConfig()
    path.write_text('[intro]\nmode="always"\ncolor_scheme="custom"\n[intro.colors]\ntext="#123456"\nbackground="#€€"\n')
    config = load_config(path)
    assert config.should_show(True)
    assert palette(config)['text'] == '#123456' and palette(config)['background'] == '#1c1c1c'
    path.write_text('[intro]\nrain_duration_ms=-1\n')
    with pytest.raises(ValueError): load_config(path)
    path.write_text('[intro]\nenabled="yes"\n')
    with pytest.raises(ValueError): load_config(path)


@pytest.mark.parametrize('mode,enabled,seen,want', [
    ('never', True, False, False), ('always', True, True, True),
    ('always', False, False, False), ('first_run', True, False, True),
    ('first_run', True, True, False), ('unknown', True, True, False),
])
def test_visibility_policy(mode, enabled, seen, want):
    assert replace(IntroConfig(), mode=mode, enabled=enabled).should_show(seen) is want


@pytest.mark.parametrize('preview,mode,result,expected', [
    (True, 'first_run', 'dashboard', False), (True, 'never', 'dashboard', False),
    (False, 'first_run', 'dashboard', True), (False, 'always', 'dashboard', False),
    (False, 'unknown', 'dashboard', False), (False, 'first_run', 'exit', False),
    (False, 'first_run', 'interrupt', False),
])
def test_cli_seen_marker_only_on_normal_first_run_success(tmp_path, monkeypatch, preview, mode, result, expected):
    from maxpane_dashboard.intro import __main__ as cli
    monkeypatch.setattr(cli.Path, 'home', lambda: tmp_path)
    path = tmp_path / 'config.toml'
    path.write_text(f'[intro]\nmode="{mode}"\n')
    calls = []
    monkeypatch.setattr(cli.IntroApp, 'run', lambda self: calls.append(self) or result)
    code = cli.main(['--config', str(path)] + (['--preview'] if preview else []))
    assert len(calls) == 1
    assert code == {'dashboard': 0, 'exit': 1, 'interrupt': 130}[result]
    assert (tmp_path / '.maxpane/.intro_seen').exists() is expected


def test_cli_already_seen_skips_and_bad_config_warns(tmp_path, monkeypatch, capsys):
    from maxpane_dashboard.intro import __main__ as cli
    monkeypatch.setattr(cli.Path, 'home', lambda: tmp_path)
    state = tmp_path / '.maxpane'
    state.mkdir(); (state / '.intro_seen').touch()
    path = state / 'config.toml'
    path.write_text('[intro]\nenabled="wrong"\n')
    def fail(self): raise AssertionError('seen intro must not mount')
    monkeypatch.setattr(cli.IntroApp, 'run', fail)
    assert cli.main([]) == 0
    assert 'config' in capsys.readouterr().err.lower()
