"""Standalone native intro. Does not launch a dashboard or invoke Rust."""
import argparse
from pathlib import Path
from .startup import run_intro


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true', help='always show; never write the seen marker')
    parser.add_argument('--config', type=Path, help='TOML settings (default: ~/.maxpane/config.toml)')
    args = parser.parse_args(argv)
    return run_intro(preview=args.preview, config_path=args.config, first_run_only=False)


if __name__ == '__main__':
    raise SystemExit(main())
