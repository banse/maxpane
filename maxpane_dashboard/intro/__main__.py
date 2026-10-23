"""Standalone native intro. Does not launch a dashboard or invoke Rust."""
import argparse
from pathlib import Path
import sys

from .settings import IntroConfig, load_config
from .view import IntroApp


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true', help='always show; never write the seen marker')
    parser.add_argument('--config', type=Path, help='TOML settings (default: ~/.maxpane/config.toml)')
    args = parser.parse_args(argv)
    state = Path.home() / '.maxpane'
    try:
        config = load_config(args.config or state / 'config.toml')
    except (OSError, ValueError) as exc:
        print(f'Intro config could not be read; using defaults: {exc}', file=sys.stderr)
        config = IntroConfig()
    marker = state / '.intro_seen'
    if not args.preview and not config.should_show(marker.exists()):
        return 0
    result = IntroApp(config).run()
    if result == 'dashboard' and not args.preview and config.mode == 'first_run':
        try:
            state.mkdir(parents=True, exist_ok=True)
            marker.touch()
        except OSError as exc:
            print(f'Intro seen marker could not be saved: {exc}', file=sys.stderr)
    return {'dashboard': 0, 'exit': 1, 'interrupt': 130}.get(result, 1)


if __name__ == '__main__':
    raise SystemExit(main())
