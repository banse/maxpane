"""``pepepane`` -- the lean entrypoint (spec §15 "Lean entrypoint", §4.3/§4.4, §12.1 runtime configuration; contract §C.17).

Part 1 (Task 8.11): the app class, the shared stylesheet path, the parser and the settings
resolution. Part 2 (Task 8.12) appends ``build_manager``/``run_once``/``main``. No Textual app is
started except under ``run_test``; nothing touches ``~/.maxpane`` (HOME is a temp dir), the
network, a socket, Docker or ssh. Every CLI test passes ``env={}`` explicitly (contract §E).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from maxpane_dashboard import __version__, seat_cli
from maxpane_dashboard.screens.seat import SeatScreen
from tests.address_sweep.builders import _PayloadManager, _seat_payload


# -- the stylesheet decision (spec §8, §14, §15) ------------------------------------------------


def test_seat_app_css_path_equals_app_css_path():
    # a TEST may import app.py; seat_cli.py never does (tests/test_seat_cli_imports.py)
    from maxpane_dashboard.app import CSS_PATH as APP_CSS_PATH

    assert seat_cli.SeatApp.CSS_PATH == seat_cli.CSS_PATH == APP_CSS_PATH
    assert seat_cli.CSS_PATH.name == "minimal.tcss" and seat_cli.CSS_PATH.exists()
    assert seat_cli.SeatApp.TITLE == "PEPEPANE"


# -- the parser -------------------------------------------------------------------------------


def test_the_parser_has_every_contract_flag_with_its_default():
    args = seat_cli.build_parser().parse_args([])
    assert args.host is None and args.unit is None and args.container is None and args.broker is None
    assert args.seat is None and args.agent is None and args.fixture is None
    assert args.offline is False and args.once is False and args.backfill_api is False
    assert args.poll_interval == 5 and args.theme == "minimal" and args.font_size == 0 and args.log_level == "WARNING"
    full = seat_cli.build_parser().parse_args(["--host", "docker", "--unit", "u.service", "--container", "imd-w", "--broker", "/run/x.sock",
                                               "--seat", "420", "--agent", "50939", "--fixture", "tests/fixtures/seat/healthy",
                                               "--offline", "--once", "--backfill-api", "--poll-interval", "10", "--theme", "matrix", "--font-size", "17"])
    assert full.host == "docker" and full.seat == 420 and full.agent == 50939 and full.offline and full.once and full.backfill_api
    assert full.poll_interval == 10 and full.theme == "matrix" and full.font_size == 17


@pytest.mark.parametrize("argv", [["--host", "bogus"], ["--poll-interval", "4"], ["--poll-interval", "0"], ["--poll-interval", "-5"],
                                  ["--font-size", "5"], ["--font-size", "73"], ["--seat", "seven"], ["--theme", "neon"]])
def test_the_parser_rejects_bad_values_with_a_usage_error(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        seat_cli.build_parser().parse_args(argv)
    assert exc.value.code == seat_cli.EXIT_USAGE
    assert "usage:" in capsys.readouterr().err


def test_poll_interval_and_font_size_validators_match_main():
    # plan deviation 9: restated because importing __main__ would import app.py; bound here
    from maxpane_dashboard.__main__ import _font_size as main_font, _poll_interval as main_poll

    for value in ("0", "-1", "4", "5", "30", "x"):
        ours = main = None
        try:
            ours = seat_cli._poll_interval(value)
        except argparse.ArgumentTypeError:
            ours = "refused"
        try:
            main = main_poll(value)
        except argparse.ArgumentTypeError:
            main = "refused"
        assert ours == main, value
    for value in ("0", "5", "6", "17", "72", "73", "-1", "x"):
        ours = main = None
        try:
            ours = seat_cli._font_size(value)
        except argparse.ArgumentTypeError:
            ours = "refused"
        try:
            main = main_font(value)
        except argparse.ArgumentTypeError:
            main = "refused"
        assert ours == main, value
    assert seat_cli.MIN_POLL_INTERVAL == 5


def test_version_prints_the_running_build_and_interpreter(capsys):
    with pytest.raises(SystemExit) as exc:
        seat_cli.build_parser().parse_args(["-V"])
    assert exc.value.code == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"pepepane {__version__}" and out[1].startswith("Python ")


# -- settings: CLI > env > config file > config.get_seat() > defaults (spec §12.1) -----------------


def _args(**overrides) -> argparse.Namespace:
    args = seat_cli.build_parser().parse_args([])
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def test_resolve_settings_precedence(tmp_path, monkeypatch):
    config = tmp_path / "pepepane.toml"
    config.write_text('[pepepane]\nhost = "docker"\ncontainer = "imd-w"\nseat = 420\nagent = 50939\noffline = true\nbroker = "/run/file.sock"\n', encoding="utf-8")
    monkeypatch.setattr(seat_cli, "get_seat", lambda: 5)
    settings = seat_cli.resolve_settings(_args(agent=1), {"PEPEPANE_HOST": "systemd", "PEPEPANE_SEAT": "7"}, config)
    assert settings["host"] == "systemd", "env beats the file"
    assert settings["seat"] == 7 and settings["agent"] == 1, "env beats the file; the CLI beats both"
    assert settings["container"] == "imd-w" and settings["offline"] is True and settings["broker"] == "/run/file.sock", "the file beats the defaults"
    assert settings["unit"] == "imd-worker.service" and settings["poll_interval"] == 5 and settings["fixture"] is None
    bare = seat_cli.resolve_settings(_args(), {}, tmp_path / "missing.toml")
    assert bare["host"] == "systemd" and bare["seat"] == 5, "config.get_seat() is the last fallback for the seat only"
    assert bare["agent"] is None and bare["offline"] is False and bare["container"] == "imd-worker" and bare["broker"] == "/run/imd-dash/broker.sock"
    assert set(bare) == {"host", "unit", "container", "broker", "seat", "agent", "offline", "fixture", "poll_interval", "theme", "font_size", "once", "backfill_api", "log_level"}


def test_resolve_settings_validates_host_and_parses_bools(tmp_path, monkeypatch):
    monkeypatch.setattr(seat_cli, "get_seat", lambda: None)
    with pytest.raises(ValueError, match="host"):
        seat_cli.resolve_settings(_args(), {"PEPEPANE_HOST": "bogus"}, tmp_path / "none.toml")
    for word, expected in (("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("false", False), ("", False)):
        assert seat_cli.resolve_settings(_args(), {"PEPEPANE_OFFLINE": word}, tmp_path / "none.toml")["offline"] is expected, word
    assert seat_cli.resolve_settings(_args(offline=True), {"PEPEPANE_OFFLINE": "0"}, tmp_path / "none.toml")["offline"] is True, "the CLI flag wins"
    with pytest.raises(ValueError, match="PEPEPANE_SEAT"):
        seat_cli.resolve_settings(_args(), {"PEPEPANE_SEAT": "seven"}, tmp_path / "none.toml")
    broken = tmp_path / "broken.toml"
    broken.write_text("this is not toml = [", encoding="utf-8")
    assert seat_cli.resolve_settings(_args(), {}, broken)["host"] == "systemd", "a corrupt file is third-party input, never a crash"
    assert seat_cli.ENV == {"host": "PEPEPANE_HOST", "unit": "PEPEPANE_UNIT", "container": "PEPEPANE_CONTAINER", "broker": "PEPEPANE_BROKER",
                            "seat": "PEPEPANE_SEAT", "agent": "PEPEPANE_AGENT", "offline": "PEPEPANE_OFFLINE", "config": "PEPEPANE_CONFIG"}
    assert seat_cli.HOSTS == ("systemd", "docker", "fixture") and seat_cli.DEFAULT_CONFIG == Path.home() / ".config" / "pepepane.toml"


# -- the app: no splash, no menu, one screen -------------------------------------------------------


class _SpyManager(_PayloadManager):
    def __init__(self, payload: dict) -> None:
        super().__init__(payload)
        self.closed = 0
        self.tail_started = 0

    def start_tail(self) -> bool:
        self.tail_started += 1
        return True

    async def close(self) -> None:
        self.closed += 1


async def test_seat_app_pushes_the_seat_screen_directly_and_closes_the_manager_on_quit():
    manager = _SpyManager(_seat_payload())
    app = seat_cli.SeatApp(manager, poll_interval=5, theme="matrix")
    async with app.run_test(size=(170, 60)) as pilot:
        await pilot.pause()
        assert isinstance(pilot.app.screen, SeatScreen), type(pilot.app.screen)
        assert pilot.app.theme == "matrix"
        assert manager.tail_started == 0, "the app never starts the tail; seat_cli.main does (spec §4.3)"
        await pilot.press("t")
        await pilot.pause()
        assert pilot.app.theme != "matrix"
        await pilot.press("q")
        await pilot.pause()
    assert manager.closed == 1


def test_seat_app_constructs_no_manager_of_its_own():
    import inspect

    source = inspect.getsource(seat_cli.SeatApp.__init__)
    assert "Manager(" not in source and "build_manager" not in source
