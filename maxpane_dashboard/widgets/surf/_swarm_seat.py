"""Re-export shim: the seat-state words live in ``widgets/seat_words.py`` since 2026-09-26.

Hoisted so the PEPEPANE dashboard shares ``NODE_TITLES``, ``seat_token`` and the
honest count forms without importing from ``widgets/surf/`` (rules/widgets.md:
hoist, never re-declare). Every surf body and test keeps this import path;
nothing is declared here.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.seat_words import *  # noqa: F401,F403
from maxpane_dashboard.widgets.seat_words import (  # noqa: F401
    _forms,
    _num,
    _reading,
    _whole,
)
from maxpane_dashboard.widgets.seat_words import __all__  # noqa: F401
