"""F3 test-only widget (see ``test_address_icons_everywhere.py``'s
``test_the_main_sweep_catches_a_shortened_address_the_old_value_only_excuse_missed``).

A minimal widget whose module genuinely imports the address helper's own
icon-producing entry point (``address_text``), so ``_hash_only_module`` on
this module correctly reports "not hash-only" -- the exact provenance a real
production widget capable of building icons has, e.g. ``widgets/surf/
swarm_launches.py``. Kept in its own file, not the test module itself,
because the test module already imports ``ADDRESS_RE``/``PROSE_ADDRESS_RE``
(not the icon-producing names) and must stay a *hash-only-eligible* import
surface for other tests in that file to reason about accurately.

This widget never calls ``address_text``: that is the point. It reproduces,
live, the exact defect F3 describes -- a widget *capable* of an icon that
paints a bare, un-iconized shortened address window instead, whose digits
happen to match some unrelated hash's own window elsewhere in the served
payload.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from maxpane_dashboard.widgets.address import address_text  # noqa: F401 -- see module docstring


class BareShortenedAddress(Static):
    """Paints exactly the text it is given, with no icon."""

    def __init__(self, shown: str) -> None:
        super().__init__(Text(shown))
