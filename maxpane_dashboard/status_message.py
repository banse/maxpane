"""The one status-bar poster the app-level mixins share (PRD §4, Branch 4).

``copy_action.CopyAddressMixin`` and ``explorer_action.ExplorerLinkMixin``
each report an outcome in the centred footer message. One poster, so the
ownership rule lives in one place: the message clears itself after
:data:`MESSAGE_S`, **and only if it is still the message on display** -- an
ENS fetch, an export or a later copy that posted since keeps its own message.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.status_bar import StatusBar

__all__ = ["MESSAGE_S", "post_status_message"]

#: How long an outcome stays in the status bar.
MESSAGE_S: float = 3.0


def post_status_message(app, message: str, *, seconds: float = MESSAGE_S) -> None:
    """Show ``message`` in the current screen's status bar for ``seconds``.

    ``message`` is plain words and validated hex only: ``StatusBar.set_message``
    wraps it in markup, so nothing third-party may reach it. A screen without a
    status bar (splash, game select, the wallet prompt) shows nothing.
    """
    bars = app.screen.query(StatusBar)
    if not bars:
        return
    bar = bars.first()
    token = object()
    app._status_message_token = token
    bar.set_message(message)

    def _clear() -> None:
        # Only our own, and only if still on display (CLAUDE.md ownership).
        if getattr(app, "_status_message_token", None) is token and bar.message == message:
            bar.set_message("")

    app.set_timer(seconds, _clear)
