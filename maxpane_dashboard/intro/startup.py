"""Intro policy shared by normal startup and the standalone preview."""
from pathlib import Path
import sys

from .settings import IntroConfig, load_config
from .view import IntroApp


def run_intro(*, force: bool = False, preview: bool = False,
              config_path: Path | None = None) -> int:
    """Run before constructing dashboard readers; return a process exit code.

    Only a literal yes suppresses the greeting on later launches. Rain and logo
    still run each time; previews never persist the confirmation.
    """
    state = Path.home() / '.maxpane'
    try:
        config = load_config(config_path or state / 'config.toml')
    except (OSError, ValueError) as exc:
        print(f'Intro config could not be read; using defaults: {exc}', file=sys.stderr)
        config = IntroConfig()
    marker = state / '.intro_accepted'
    automatic = config.enabled and config.mode != 'never'
    if not (force or preview or automatic):
        return 0

    def accept():
        try:
            state.mkdir(parents=True, exist_ok=True)
            marker.touch()
        except OSError as exc:
            print(f'Intro confirmation could not be saved: {exc}', file=sys.stderr)

    start_at = 'typewriter' if force or preview or not marker.exists() else 'rain'
    result = IntroApp(config, start_at=start_at, on_accept=None if preview else accept).run()
    return {'dashboard': 0, 'exit': 1, 'interrupt': 130}.get(result, 1)
