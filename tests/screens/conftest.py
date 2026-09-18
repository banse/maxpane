"""Markers for the expensive tier.

Everything under ``tests/screens`` composites a whole dashboard through the
Textual compositor (0.3-1.3 s a case) and is marked ``screen``; the
integer size sweeps inside it -- the tests that certify a layout pin by
walking widths or heights -- are additionally marked ``sweep``.  The
markers are declared in ``pyproject.toml``; ``-m 'not screen'`` is the fast
tier and ``-m 'not sweep'`` skips only the pin certifications (see
``CLAUDE.md`` "Tests" and the terminal-layout skill).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

#: This hook receives the WHOLE session's items, not only this directory's
#: (pytest calls ``pytest_collection_modifyitems`` from every conftest with
#: the full list), so the marker is applied by path.
_SCREENS = Path(__file__).resolve().parent

#: A test is a sweep when its *function name* says it walks a size band.
#: The names are the repo's own vocabulary for pin certification -- see the
#: sweep sites in test_surf_screen.py, test_surf_swarm_layout.py,
#: test_surf_pool4_market_layout.py and test_ttt_address_icon_layout.py.
_SWEEP_NAME = re.compile(
    r"_is_whole_from_|_at_every_height|clips_without_saying_so|"
    r"scrolls_at_or_above_the_pin|loses_a_row"
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if not Path(str(item.path)).resolve().is_relative_to(_SCREENS):
            continue
        item.add_marker(pytest.mark.screen)
        if _SWEEP_NAME.search(item.originalname or item.name):
            item.add_marker(pytest.mark.sweep)
