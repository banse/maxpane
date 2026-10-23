"""Preview the complete native intro without changing normal startup or seen state.

Run: .venv/bin/python scripts/python_intro.py
Reads ~/.maxpane/config.toml; --config PATH selects another settings file.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxpane_dashboard.intro.__main__ import main


if __name__ == '__main__':
    raise SystemExit(main(['--preview', *sys.argv[1:]]))
