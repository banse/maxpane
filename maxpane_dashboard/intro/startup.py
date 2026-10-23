"""Intro policy shared by normal startup and the standalone preview."""
from pathlib import Path
import sys

from .settings import IntroConfig, load_config
from .view import IntroApp


def run_intro(*, force: bool = False, preview: bool = False,
              config_path: Path | None = None, first_run_only: bool = True) -> int:
    """Run before constructing dashboard readers; return a process exit code.

    Normal MaxPane startup is once per profile, even with a legacy ``always``
    config. The standalone runner retains its explicit configured policy.
    """
    state = Path.home() / '.maxpane'
    try:
        config = load_config(config_path or state / 'config.toml')
    except (OSError, ValueError) as exc:
        print(f'Intro config could not be read; using defaults: {exc}', file=sys.stderr)
        config = IntroConfig()
    marker = state / '.intro_seen'
    seen = marker.exists()
    automatic = config.should_show(seen) and (not first_run_only or not seen)
    if not (force or preview or automatic):
        return 0
    result = IntroApp(config).run()
    if result == 'dashboard' and not preview and (first_run_only or config.mode == 'first_run'):
        try:
            state.mkdir(parents=True, exist_ok=True)
            marker.touch()
        except OSError as exc:
            print(f'Intro seen marker could not be saved: {exc}', file=sys.stderr)
    return {'dashboard': 0, 'exit': 1, 'interrupt': 130}.get(result, 1)
