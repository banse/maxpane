"""The one app-level action every copy icon calls (PRD §4)."""

from __future__ import annotations

from maxpane_dashboard import clipboard
from maxpane_dashboard.widgets.address import is_address
from maxpane_dashboard.widgets.status_bar import StatusBar


class CopyAddressMixin:
    """Mixed into ``MaxPaneApp`` ahead of ``App``."""

    #: How long the outcome stays in the status bar.
    COPY_MESSAGE_S: float = 3.0

    async def action_copy_address(self, address: str) -> None:
        # Validated again here: the icon's meta is not the only way to invoke
        # an action, and an unvalidated value must never reach a subprocess.
        if not is_address(address):
            self._post_copy_message(clipboard.UNAVAILABLE, None)
            return
        outcome = await clipboard.copy_text(address, osc52=self.copy_to_clipboard)
        self._post_copy_message(outcome, address)

    def _post_copy_message(self, outcome: str, address: str | None) -> None:
        bars = self.screen.query(StatusBar)
        if not bars:
            return  # splash, game select and the wallet prompt have no status bar
        bar = bars.first()
        message = clipboard.copy_message(outcome, address)
        token = object()
        self._copy_message_token = token
        bar.set_message(message)

        def _clear() -> None:
            # Only our own, and only if still on display: an ENS fetch or an
            # export that posted since keeps its message (CLAUDE.md ownership).
            if getattr(self, "_copy_message_token", None) is token and bar.message == message:
                bar.set_message("")

        self.set_timer(self.COPY_MESSAGE_S, _clear)
