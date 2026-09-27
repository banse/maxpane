"""pepepane -- the lean PEPEPANE entrypoint (spec §15 "Lean entrypoint", §4.3/§4.4, §12.1).

``pepepane`` is the product on both hosts (spec §16 #10: nothing is registered in the
``maxpane`` menu). It constructs **exactly one** manager (``SeatManager``), pushes
:class:`SeatScreen` directly -- no splash, no game menu -- and is the **only** caller of
``manager.start_tail()``, which it calls only when not ``--once`` (spec §4.3, §9). It
never imports ``app.py``, ``data.surf_manager``, ``data.curator_manager``, ``data.fwa_*``
or ``sybilkit`` (``tests/test_seat_cli_imports.py`` walks the AST). What it cannot
avoid: ``maxpane_dashboard/data/__init__.py`` eagerly imports the FrenPet/base manager
*modules* on any ``data.*`` import -- imported, never constructed, which is the line
between 142 and 371 MiB (fill7 §4; spec §15).

:data:`CSS_PATH` is the shared ``themes/minimal.tcss``, computed here from the
package path -- equal to ``app.CSS_PATH`` by a test, never by an import (spec §8, §15).

Configuration (spec §12.1): CLI flag > ``PEPEPANE_*`` env > ``~/.config/pepepane.toml``
``[pepepane]`` > ``config.get_seat()`` (seat only) > defaults. Env vars are
configuration, never secrets (MaxPane rule). ``--offline`` removes every API tier and
marks every broker plan ``offline: true``; ``--once`` prints the validated v2 document
and exits; ``--host fixture --fixture <dir>`` is the dev mode (spec §4.4). The two
argparse validators of ``__main__.py`` are restated here (plan deviation 9).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path

from textual.app import App
from textual.binding import Binding

import maxpane_dashboard
from maxpane_dashboard import __version__
from maxpane_dashboard.config import get_seat
from maxpane_dashboard.copy_action import CopyAddressMixin
from maxpane_dashboard.data.seat_api import SeatApiClient
from maxpane_dashboard.data.seat_broker_client import DockerUnitReader, LocalDockerBroker, SystemdUnitReader, UnixSocketBroker
from maxpane_dashboard.data.seat_manager import SeatManager, build_fixture_manager
from maxpane_dashboard.data.seat_models import validate_status_document
from maxpane_dashboard.data.seat_tail import JOURNAL_FIRST_RUN_SINCE, DockerLogsSource, JournaldSource, journal_since_arg
from maxpane_dashboard.explorer_action import ExplorerLinkMixin
from maxpane_dashboard.screens.seat import SeatScreen
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.status_bar import StatusBar

__all__ = [
    "CSS_PATH", "DEFAULTS", "DEFAULT_CONFIG", "ENV", "ENV_PREFIX", "EXIT_HOST", "EXIT_OK", "EXIT_REFUSED", "EXIT_USAGE", "HOSTS",
    "MIN_POLL_INTERVAL", "SeatApp", "build_manager", "build_parser", "main", "resolve_settings", "run_once",
]

logger = logging.getLogger(__name__)

#: The shared stylesheet -- the same path ``app.py:47`` computes, asserted equal by a test (spec §8, §15).
CSS_PATH = Path(maxpane_dashboard.__file__).parent / "themes" / "minimal.tcss"

ENV_PREFIX = "PEPEPANE_"
ENV = {
    "host": "PEPEPANE_HOST", "unit": "PEPEPANE_UNIT", "container": "PEPEPANE_CONTAINER", "broker": "PEPEPANE_BROKER",
    "seat": "PEPEPANE_SEAT", "agent": "PEPEPANE_AGENT", "offline": "PEPEPANE_OFFLINE", "config": "PEPEPANE_CONFIG",
}
DEFAULT_CONFIG = Path.home() / ".config" / "pepepane.toml"
HOSTS = ("systemd", "docker", "fixture")
DEFAULTS = {
    "host": "systemd", "unit": "imd-worker.service", "container": "imd-worker", "broker": "/run/imd-dash/broker.sock",
    "seat": None, "agent": None, "offline": False, "fixture": None,
}
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_REFUSED = 3
EXIT_HOST = 4
#: The same floor as ``__main__._MIN_POLL_INTERVAL``: below it Textual's timer breaks (LOW-3).
MIN_POLL_INTERVAL = 5
#: ``0`` = leave the terminal alone: the entrypoint runs over ssh on a VPS (plan deviation 9).
DEFAULT_FONT_SIZE = 0
THEME_NAMES = tuple(THEMES)


def _poll_interval(value: str) -> int:
    """Restates ``__main__._poll_interval`` (bound by a test): reject what breaks the refresh timer."""
    try:
        seconds = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid int value: {value!r}") from None
    if seconds < MIN_POLL_INTERVAL:
        raise argparse.ArgumentTypeError(
            f"must be at least {MIN_POLL_INTERVAL} seconds (got {seconds}); values below that stop the refresh timer instead of speeding it up"
        )
    return seconds


def _font_size(value: str) -> int:
    """Restates ``__main__._font_size`` (bound by a test): ``0`` or 6–72."""
    try:
        size = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid int value: {value!r}") from None
    if size < 0 or (0 < size < 6) or size > 72:
        raise argparse.ArgumentTypeError(f"must be 0 (leave the terminal alone) or 6-72 (got {size})")
    return size


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _version_text() -> str:
    return f"pepepane {__version__}\nPython {platform.python_version()} ({sys.executable})"


class _VersionAction(argparse.Action):
    """Print the version on stdout verbatim and exit 0 (the ``__main__`` reasoning: no reflow, never stderr)."""

    def __init__(self, option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, help=None):
        super().__init__(option_strings=option_strings, dest=dest, default=default, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        print(_version_text())
        parser.exit()


class SeatApp(CopyAddressMixin, ExplorerLinkMixin, App):
    """The one-screen app: themes registered, ``SeatScreen`` pushed, no splash, no menu."""

    CSS_PATH = CSS_PATH
    TITLE = "PEPEPANE"
    BINDINGS = [
        Binding("q", "quit", "Quit", show=False),
        Binding("t", "cycle_theme", "Theme", show=False),
    ]

    def __init__(self, manager, *, poll_interval: int = 5, theme: str = "minimal", **kwargs) -> None:
        super().__init__(**kwargs)
        # Use the injected manager (spec §15).
        self._manager = manager
        self._poll_interval = poll_interval
        self._initial_theme = theme if theme in THEMES else "minimal"

    def on_mount(self) -> None:
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = self._initial_theme
        self.push_screen(SeatScreen(self._manager, self._poll_interval, name="seat"))

    def action_cycle_theme(self) -> None:
        names = list(THEMES)
        index = names.index(self.theme) if self.theme in names else 0
        self.theme = names[(index + 1) % len(names)]
        try:
            self.screen.query_one(StatusBar).set_theme_name(self.theme)
        except Exception:  # noqa: BLE001 -- a modal without a status bar
            pass

    async def action_quit(self) -> None:
        try:
            await self._manager.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("seat manager did not close cleanly: %s", exc)
        self.exit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pepepane", description="PEPEPANE -- a local dashboard and control panel for one IdentityMD worker")
    parser.add_argument("-V", "--version", action=_VersionAction, help="Show the version and the interpreter running it, then exit")
    parser.add_argument("--host", choices=HOSTS, default=None, help="systemd (VPS), docker (Mac) or fixture (dev mode); default from env/config, else systemd")
    parser.add_argument("--unit", default=None, help="systemd unit (default imd-worker.service)")
    parser.add_argument("--container", default=None, help="docker container (default imd-worker)")
    parser.add_argument("--broker", default=None, help="broker socket path (default /run/imd-dash/broker.sock)")
    parser.add_argument("--seat", type=int, default=None, help="IDMD token id (else PEPEPANE_SEAT, config, ~/.maxpane/config.toml [seat] token_id)")
    parser.add_argument("--agent", type=int, default=None, help="ERC-8004 agent id, the --offline fallback for the SEAT box")
    parser.add_argument("--fixture", default=None, help="fixture case directory for --host fixture (tests/fixtures/seat/<case>/)")
    parser.add_argument("--offline", action="store_true", default=False, help="no api.imd.fun reads; every broker plan is local-only")
    parser.add_argument("--once", action="store_true", default=False, help="backfill, fetch once, print the status document v2 as JSON, exit")
    parser.add_argument("--backfill-api", action="store_true", default=False, help="seed the ledger from /seats/<id>?work=1000 once")
    parser.add_argument("--poll-interval", type=_poll_interval, default=MIN_POLL_INTERVAL, help=f"seconds between refreshes (default {MIN_POLL_INTERVAL}, minimum {MIN_POLL_INTERVAL})")
    parser.add_argument("--theme", default="minimal", choices=THEME_NAMES)
    parser.add_argument("--font-size", type=_font_size, default=DEFAULT_FONT_SIZE, help="terminal font size on launch (0 = leave it alone; iTerm2 only)")
    parser.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _read_config(path: Path) -> dict:
    """The ``[pepepane]`` table of *path*, or ``{}``: a hand-editable file is third-party input, never a crash."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    table = data.get("pepepane")
    return table if isinstance(table, dict) else {}


def _int_or_none(value: object, name: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {value!r}") from None


def resolve_settings(args: argparse.Namespace, env: Mapping[str, str], config_path: Path) -> dict:
    """CLI > env > config file > ``config.get_seat()`` (seat only) > :data:`DEFAULTS`. Raises ``ValueError`` on a bad value."""
    config_override = env.get(ENV["config"])
    file_values = _read_config(Path(config_override) if config_override else config_path)
    settings: dict = {}
    for key in ("host", "unit", "container", "broker", "fixture"):
        cli = getattr(args, key, None)
        value = cli if cli is not None else env.get(ENV.get(key, ""), None) if key in ENV else None
        if value is None:
            value = file_values.get(key)
        if value is None:
            value = DEFAULTS[key]
        settings[key] = str(value) if value is not None else None
    for key in ("seat", "agent"):
        cli = getattr(args, key, None)
        value = cli if cli is not None else _int_or_none(env.get(ENV[key]), ENV[key])
        if value is None:
            value = _int_or_none(file_values.get(key), key)
        settings[key] = value
    if settings["seat"] is None:
        settings["seat"] = get_seat()
    offline = bool(getattr(args, "offline", False))
    if not offline and ENV["offline"] in env:
        offline = _truthy(env[ENV["offline"]])
    if not offline and "offline" in file_values and getattr(args, "offline", False) is False and ENV["offline"] not in env:
        offline = file_values.get("offline") is True or _truthy(file_values.get("offline"))
    settings["offline"] = offline
    if settings["host"] not in HOSTS:
        raise ValueError(f"host must be one of {HOSTS}, got {settings['host']!r}")
    settings["poll_interval"] = getattr(args, "poll_interval", MIN_POLL_INTERVAL)
    settings["theme"] = getattr(args, "theme", "minimal")
    settings["font_size"] = getattr(args, "font_size", DEFAULT_FONT_SIZE)
    settings["once"] = bool(getattr(args, "once", False))
    settings["backfill_api"] = bool(getattr(args, "backfill_api", False))
    settings["log_level"] = getattr(args, "log_level", "WARNING")
    return settings
