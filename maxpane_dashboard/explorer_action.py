"""The one app-level path from a linked address to its public explorer page.

Refactor programme 2026-09, Branch 4. ``widgets/address.py`` gives a shown
address (or ``hash_text`` a transaction hash) an OSC 8 hyperlink **and** the
``@click`` action ``app.open_explorer(name, kind, value)``; this mixin runs
that action.

Read-only, keyless: the only thing it does is hand a URL it built itself to
``App.open_url`` (Textual -> ``webbrowser.open``), which opens the page in the
user's browser. The app makes no request, signs nothing, sends nothing.
"""

from __future__ import annotations

from maxpane_dashboard.status_message import MESSAGE_S, post_status_message
from maxpane_dashboard.widgets.explorer import EXPLORERS, Explorer, is_valid, url_for

__all__ = ["ExplorerLinkMixin", "UNAVAILABLE", "explorer_message"]

UNAVAILABLE = "explorer unavailable"


def explorer_message(explorer: Explorer | None) -> str:
    """The status-bar sentence: ``opened etherscan`` or :data:`UNAVAILABLE`.

    Plain words only -- the name comes from the allowlist, never from the
    action string -- because ``StatusBar.set_message`` wraps it in markup.
    """
    return f"opened {explorer.name}" if explorer is not None else UNAVAILABLE


class ExplorerLinkMixin:
    """Mixed into ``MaxPaneApp`` ahead of ``App``: ``action_open_explorer``."""

    #: How long the outcome stays in the status bar.
    EXPLORER_MESSAGE_S: float = MESSAGE_S

    def action_open_explorer(self, name: object, kind: object, value: object) -> None:
        # Validated again here, on all three parts: a link's meta is not the
        # only way to invoke an action. The URL is rebuilt from the parts that
        # passed (widgets/explorer.url_for) and never taken from any text.
        explorer = EXPLORERS.get(name) if isinstance(name, str) else None
        if explorer is None or not is_valid(explorer, kind, value):
            post_status_message(self, explorer_message(None), seconds=self.EXPLORER_MESSAGE_S)
            return
        try:
            self.open_url(url_for(explorer, kind, value))
        except Exception:  # noqa: BLE001 -- no browser is "could not open", never a crash
            post_status_message(self, explorer_message(None), seconds=self.EXPLORER_MESSAGE_S)
            return
        post_status_message(self, explorer_message(explorer), seconds=self.EXPLORER_MESSAGE_S)
