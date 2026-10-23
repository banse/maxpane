"""Native startup policy and launch routing, without a terminal or network."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest

from maxpane_dashboard.intro import startup


@pytest.fixture
def intro_env(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    state = tmp_path / '.maxpane'
    calls = []

    class FakeIntro:
        def __init__(self, config):
            calls.append(config)

        def run(self):
            return 'dashboard'

    monkeypatch.setattr(startup, 'IntroApp', FakeIntro)
    return state, calls


@pytest.mark.parametrize('mode', ['first_run', 'always'])
def test_normal_intro_runs_once_even_with_legacy_always(intro_env, mode):
    state, calls = intro_env
    state.mkdir()
    (state / 'config.toml').write_text(f'[intro]\nmode = "{mode}"\n')
    assert startup.run_intro() == 0
    assert (state / '.intro_seen').exists()
    assert startup.run_intro() == 0
    assert len(calls) == 1


@pytest.mark.parametrize('settings', ['enabled = false', 'mode = "never"'])
def test_disabled_normal_intro_can_be_forced(intro_env, settings):
    state, calls = intro_env
    state.mkdir()
    (state / 'config.toml').write_text(f'[intro]\n{settings}\n')
    assert startup.run_intro() == 0
    assert calls == []
    assert not (state / '.intro_seen').exists()
    assert startup.run_intro(force=True) == 0
    assert (state / '.intro_seen').exists()
    assert startup.run_intro(force=True) == 0
    assert len(calls) == 2


@pytest.mark.parametrize(('outcome', 'code'), [('exit', 1), ('interrupt', 130), (None, 1)])
def test_decline_and_interrupt_do_not_mark_seen(intro_env, monkeypatch, outcome, code):
    state, _ = intro_env
    monkeypatch.setattr(startup.IntroApp, 'run', lambda self: outcome)
    assert startup.run_intro() == code
    assert not state.exists()


def test_preview_never_changes_marker_and_honors_custom_config(intro_env, tmp_path):
    state, calls = intro_env
    config = tmp_path / 'preview.toml'
    config.write_text('[intro]\nenabled = false\ntypewriter_speed_ms = 80\n')
    assert startup.run_intro(preview=True, config_path=config, first_run_only=False) == 0
    assert calls[0].typewriter_speed_ms == 80
    assert not state.exists()


def test_invalid_config_falls_back_without_breaking_start(intro_env, capsys):
    state, calls = intro_env
    state.mkdir()
    (state / 'config.toml').write_text('[broken')
    assert startup.run_intro() == 0
    assert calls[0].typewriter_speed_ms == 45
    assert 'using defaults' in capsys.readouterr().err


def test_marker_write_failure_warns_but_allows_dashboard(intro_env, monkeypatch, capsys):
    def denied(self, *args, **kwargs):
        raise PermissionError('read-only profile')

    monkeypatch.setattr(Path, 'touch', denied)
    assert startup.run_intro() == 0
    assert 'could not be saved' in capsys.readouterr().err


@pytest.mark.parametrize(('intro_code', 'expected'), [(0, ['intro', 'app', 'run']), (1, ['intro']), (130, ['intro'])])
def test_cli_runs_intro_before_constructing_readers(tmp_path, monkeypatch, intro_code, expected):
    import maxpane_dashboard.__main__ as cli

    monkeypatch.setenv('HOME', str(tmp_path))
    events = []

    def intro(**kwargs):
        assert kwargs == {'force': True}
        events.append('intro')
        return intro_code

    class App:
        return_code = 0

        def __init__(self, **kwargs):
            events.append('app')

        def run(self):
            events.append('run')

    monkeypatch.setattr(cli, 'run_intro', intro)
    monkeypatch.setattr(cli, 'MaxPaneApp', App)
    monkeypatch.setattr(cli, '_maximize_terminal', lambda *args: None)
    monkeypatch.setattr(cli.logging, 'basicConfig', lambda **kwargs: None)
    monkeypatch.setattr(cli.sys, 'argv', ['maxpane', '--intro'])
    assert cli.main() == intro_code
    assert events == expected


@pytest.mark.parametrize('flag', ['--help', '--version', '-V'])
def test_cli_informational_flags_do_not_start_intro_or_write_state(tmp_path, monkeypatch, flag):
    import maxpane_dashboard.__main__ as cli

    def forbidden(*args, **kwargs):
        raise AssertionError('informational flag ran startup')

    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr(cli, 'run_intro', forbidden)
    monkeypatch.setattr(cli, 'MaxPaneApp', forbidden)
    monkeypatch.setattr(cli, '_maximize_terminal', forbidden)
    monkeypatch.setattr(cli.sys, 'argv', ['maxpane', flag])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert not (tmp_path / '.maxpane').exists()


@pytest.mark.parametrize('script', ['start-maxpane.sh', 'scripts/start.sh', 'scripts/launch.sh',
                                    'scripts/launch-maximized.sh', 'scripts/launch-iterm.sh'])
def test_launcher_forwards_help_without_terminal_or_pid_side_effects(tmp_path, script):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / 'scripts').mkdir()
    for relative in {script, 'scripts/start.sh'}:
        shutil.copy(root / relative, tmp_path / relative)
    bin_dir = tmp_path / '.venv' / 'bin'
    bin_dir.mkdir(parents=True)
    interpreter = bin_dir / 'python'
    interpreter.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    interpreter.chmod(0o755)
    (bin_dir / 'activate').write_text(f'export PATH="{bin_dir}:$PATH"\n')
    env = {**os.environ, 'HOME': str(tmp_path)}
    env.pop('TERM_PROGRAM', None)
    result = subprocess.run(['bash', str(tmp_path / script), '--help'], env=env,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert '\x1b' not in result.stdout
    assert result.stdout.splitlines()[-1] == '--help'
    assert not (tmp_path / 'data').exists()


def test_launcher_uses_python_even_when_old_rust_binary_exists(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / 'scripts').mkdir()
    shutil.copy(root / 'scripts/start.sh', tmp_path / 'scripts/start.sh')
    bin_dir = tmp_path / '.venv' / 'bin'
    bin_dir.mkdir(parents=True)
    interpreter = bin_dir / 'python'
    interpreter.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 17\n')
    interpreter.chmod(0o755)
    (bin_dir / 'activate').write_text(f'export PATH="{bin_dir}:$PATH"\n')
    rust = tmp_path / 'maxpane/target/release/maxpane'
    rust.parent.mkdir(parents=True)
    rust.write_text('#!/bin/sh\ntouch rust-was-run\nexit 99\n')
    rust.chmod(0o755)
    result = subprocess.run(['bash', str(tmp_path / 'scripts/start.sh'), '--intro'],
                            env={**os.environ, 'HOME': str(tmp_path)},
                            capture_output=True, text=True, check=False)
    assert result.returncode == 17
    assert result.stdout.splitlines()[-1] == '--intro'
    assert not (tmp_path / 'rust-was-run').exists()
