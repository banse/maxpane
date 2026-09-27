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


# ---------------------------------------------------------------------------
# Task 8.12 -- build_manager, run_once, main
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402

HEALTHY_CASE = Path(__file__).resolve().parent / "fixtures" / "seat" / "healthy"


class _Recorder:
    """Stands in for a source/broker/reader class: records its construction, does nothing."""

    made: list[tuple[str, tuple, dict]] = []

    def __init__(self, *args, **kwargs) -> None:
        _Recorder.made.append((type(self).__name__, args, kwargs))


def _recorder(name: str):
    return type(name, (_Recorder,), {})


def _settings(**overrides) -> dict:
    base = {"host": "systemd", "unit": "imd-worker.service", "container": "imd-worker", "broker": "/run/imd-dash/broker.sock", "seat": 7, "agent": 51075,
            "offline": False, "fixture": None, "poll_interval": 5, "theme": "minimal", "font_size": 0, "once": False, "backfill_api": False, "log_level": "WARNING"}
    base.update(overrides)
    return base


@pytest.fixture
def recorders(monkeypatch):
    _Recorder.made = []
    for name in ("JournaldSource", "DockerLogsSource", "UnixSocketBroker", "LocalDockerBroker", "SystemdUnitReader", "DockerUnitReader", "SeatApiClient"):
        monkeypatch.setattr(seat_cli, name, _recorder(name))
    managers: list[dict] = []

    class _FakeSeatManager:
        def __init__(self, **kwargs) -> None:
            managers.append(kwargs)
            self.kwargs = kwargs
            self.tail_started = 0
            self.closed = 0

        def start_tail(self) -> bool:
            self.tail_started += 1
            return True

        async def backfill(self, *, api: bool = False) -> dict:
            self.backfilled = api
            return {}

        async def fetch_and_compute(self) -> dict:
            self.fetched = getattr(self, "fetched", 0) + 1
            return {}

        async def settle(self) -> None:
            self.settled = getattr(self, "settled", 0) + 1

        def document(self) -> dict:
            return json.loads((Path(__file__).resolve().parent / "fixtures" / "seat" / "status" / "status_v2_healthy.json").read_text(encoding="utf-8"))

        async def close(self) -> None:
            self.closed += 1

    monkeypatch.setattr(seat_cli, "SeatManager", _FakeSeatManager)
    return managers


def test_build_manager_wires_the_systemd_host(recorders):
    manager = seat_cli.build_manager(_settings())
    names = [name for name, _a, _k in _Recorder.made]
    assert names == ["SeatApiClient", "UnixSocketBroker", "SystemdUnitReader"], names
    broker = next(k for n, a, k in _Recorder.made if n == "UnixSocketBroker")
    assert broker == {"offline": False} and next(a for n, a, k in _Recorder.made if n == "UnixSocketBroker") == ("/run/imd-dash/broker.sock",)
    kwargs = manager.kwargs
    assert kwargs["host"] == "systemd" and kwargs["unit"] == "imd-worker.service" and kwargs["container"] is None
    assert kwargs["seat"] == 7 and kwargs["agent"] == 51075 and kwargs["offline"] is False and kwargs["poll_interval"] == 5
    assert callable(kwargs["tail"]), "the tail is a factory the manager calls with its TailState"

    class _State:
        cursor = "s=abc;i=1"
        last_ts_utc = None
        watermark_ts = None

    kwargs["tail"](_State())
    journald = next((a, k) for n, a, k in _Recorder.made if n == "JournaldSource")
    assert journald == (("imd-worker.service",), {"cursor": "s=abc;i=1", "since": None})
    _State.cursor = None
    kwargs["tail"](_State())
    assert _Recorder.made[-1][2] == {"cursor": None, "since": seat_cli.JOURNAL_FIRST_RUN_SINCE}
    # spec §5.1/§9: a vacuumed cursor is cleared and lastTsUtc kept -> the next attach is `--since <lastTsUtc>`
    _State.last_ts_utc = "2026-09-24T04:12:00.000Z"
    kwargs["tail"](_State())
    assert _Recorder.made[-1][2] == {"cursor": None, "since": "2026-09-24 04:12:00 UTC"}


def test_build_manager_wires_the_docker_host_and_offline_drops_the_api(recorders):
    manager = seat_cli.build_manager(_settings(host="docker", offline=True, container="imd-w"))
    names = [name for name, _a, _k in _Recorder.made]
    assert "SeatApiClient" not in names and names == ["LocalDockerBroker", "DockerUnitReader"], names
    broker_args, broker_kwargs = next((a, k) for n, a, k in _Recorder.made if n == "LocalDockerBroker")
    assert broker_args == ("imd-w",) and broker_kwargs["offline"] is True and broker_kwargs["audit_path"].name == "seat_audit.jsonl"
    # spec §11 gate step (b): the in-process Mac broker makes the fresh standing read, which needs the seat
    assert broker_kwargs["seat"] == 7
    assert "tail_lines" not in broker_kwargs, "the Mac broker reads its own docker logs tail (deviation 17)"
    assert manager.kwargs["host"] == "docker" and manager.kwargs["container"] == "imd-w" and manager.kwargs["unit"] is None and manager.kwargs["api"] is None

    class _State:
        cursor = None
        watermark_ts = "2026-09-26T03:40:11.000Z"

    manager.kwargs["tail"](_State())
    assert _Recorder.made[-1][:1] == ("DockerLogsSource",) and _Recorder.made[-1][2] == {"watermark_ts": "2026-09-26T03:40:11.000Z"}


def test_build_manager_hands_the_fixture_host_to_build_fixture_manager(monkeypatch, recorders):
    calls = []
    monkeypatch.setattr(seat_cli, "build_fixture_manager", lambda case_dir, **kw: calls.append((case_dir, kw)) or "fixture-manager")
    out = seat_cli.build_manager(_settings(host="fixture", fixture=str(HEALTHY_CASE), offline=True))
    assert out == "fixture-manager" and calls == [(HEALTHY_CASE, {"offline": True, "seat": 7, "agent": 51075, "poll_interval": 5})]
    assert _Recorder.made == [] and recorders == [], "the fixture host constructs no real source, broker, reader or api"


def test_run_once_prints_the_validated_v2_document_or_refuses(recorders):
    manager = seat_cli.build_manager(_settings())
    code, text = seat_cli.run_once(manager)
    assert code == seat_cli.EXIT_OK
    doc = json.loads(text)
    assert doc["schemaVersion"] == 2 and doc["seat"]["tokenId"] == 7 and manager.closed == 1 and manager.backfilled is False
    # the tiers are detached tasks: fetch, settle (await them), fetch again, so --once carries broker and API data
    assert manager.fetched == 2 and manager.settled == 1
    manager = seat_cli.build_manager(_settings())
    manager.document = lambda: {"schemaVersion": 1, "generatedAtUtc": "x"}
    code, text = seat_cli.run_once(manager, backfill_api=True)
    assert code == seat_cli.EXIT_REFUSED and json.loads(text) == {"refused": "wrong_schema", "detail": "schemaVersion=1"} and manager.backfilled is True


def test_run_once_against_the_real_fixture_manager(tmp_path, monkeypatch):
    # spec §4.4: the fixture host touches no host, no Docker, no network -- so the real manager may run here
    if not HEALTHY_CASE.is_dir():
        pytest.skip("WP7's healthy fixture case is not committed yet")
    monkeypatch.setenv("HOME", str(tmp_path))
    manager = seat_cli.build_fixture_manager(HEALTHY_CASE, offline=True, seat=7, agent=51075, poll_interval=5)
    code, text = seat_cli.run_once(manager)
    assert code == seat_cli.EXIT_OK
    doc = json.loads(text)
    assert doc["schemaVersion"] == 2 and "standing" not in doc.get("sources", {}), "--offline removes the API sources"


def test_main_constructs_exactly_one_manager_and_starts_the_tail_only_when_not_once(monkeypatch, recorders, capsys):
    ran: list[dict] = []

    class _StubApp:
        def __init__(self, manager, *, poll_interval, theme, **kwargs) -> None:
            ran.append({"manager": manager, "poll_interval": poll_interval, "theme": theme})

        def run(self) -> None:
            ran[-1]["ran"] = True

    monkeypatch.setattr(seat_cli, "SeatApp", _StubApp)
    monkeypatch.setattr(seat_cli, "_configure_logging", lambda level: None)
    monkeypatch.setattr(seat_cli, "_apply_font_size", lambda size: None)
    monkeypatch.setattr(seat_cli, "get_seat", lambda: None)
    monkeypatch.setattr(seat_cli, "DEFAULT_CONFIG", Path("/nonexistent/pepepane.toml"))
    monkeypatch.setattr(seat_cli.os, "environ", {})
    code = seat_cli.main(["--host", "systemd", "--seat", "7", "--theme", "matrix", "--poll-interval", "10"])
    assert code == seat_cli.EXIT_OK and len(recorders) == 1
    manager = ran[0]["manager"]
    assert manager.tail_started == 1 and ran[0]["ran"] is True and ran[0]["poll_interval"] == 10 and ran[0]["theme"] == "matrix"
    recorders.clear()
    ran.clear()
    code = seat_cli.main(["--host", "systemd", "--seat", "7", "--once"])
    out = capsys.readouterr().out
    assert code == seat_cli.EXIT_OK and len(recorders) == 1 and ran == [], "--once never builds the app"
    assert json.loads(out)["schemaVersion"] == 2


def test_start_tail_is_called_only_by_seat_cli_and_not_under_once(monkeypatch, recorders):
    # spec §4.3/§9: the ONLY call site is main(), and never under --once
    monkeypatch.setattr(seat_cli, "SeatApp", type("StubApp", (), {"__init__": lambda self, m, **k: None, "run": lambda self: None}))
    monkeypatch.setattr(seat_cli, "_configure_logging", lambda level: None)
    monkeypatch.setattr(seat_cli, "_apply_font_size", lambda size: None)
    monkeypatch.setattr(seat_cli, "get_seat", lambda: None)
    monkeypatch.setattr(seat_cli, "DEFAULT_CONFIG", Path("/nonexistent/pepepane.toml"))
    monkeypatch.setattr(seat_cli.os, "environ", {})
    started: list[int] = []
    made = []

    class _Counting:
        def __init__(self, **kwargs) -> None:
            made.append(self)

        def start_tail(self) -> bool:
            started.append(1)
            return True

        async def backfill(self, *, api=False):
            return {}

        async def fetch_and_compute(self):
            return {}

        async def settle(self):
            pass

        def document(self):
            return json.loads((Path(__file__).resolve().parent / "fixtures" / "seat" / "status" / "status_v2_healthy.json").read_text(encoding="utf-8"))

        async def close(self):
            pass

    monkeypatch.setattr(seat_cli, "SeatManager", _Counting)
    assert seat_cli.main(["--host", "systemd", "--seat", "7", "--once", "--offline"]) == seat_cli.EXIT_OK
    assert started == [] and len(made) == 1
    assert seat_cli.main(["--host", "systemd", "--seat", "7", "--offline"]) == seat_cli.EXIT_OK
    assert started == [1] and len(made) == 2


def test_main_refuses_a_fixture_host_without_a_directory(monkeypatch, capsys):
    monkeypatch.setattr(seat_cli, "get_seat", lambda: None)
    monkeypatch.setattr(seat_cli, "DEFAULT_CONFIG", Path("/nonexistent/pepepane.toml"))
    monkeypatch.setattr(seat_cli.os, "environ", {})
    assert seat_cli.main(["--host", "fixture"]) == seat_cli.EXIT_HOST
    assert seat_cli.main(["--host", "fixture", "--fixture", "/nonexistent/case"]) == seat_cli.EXIT_HOST
    assert "--fixture" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        seat_cli.main(["--host", "bogus"])
    assert exc.value.code == seat_cli.EXIT_USAGE
