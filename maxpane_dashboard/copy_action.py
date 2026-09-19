"""The one app-level copy path: the ``⧉`` icon and Textual's own text selection (PRD §4)."""

from __future__ import annotations

from textual import events
from textual.app import App

from maxpane_dashboard import clipboard
from maxpane_dashboard.widgets.address import is_address
from maxpane_dashboard.widgets.status_bar import StatusBar


class CopyAddressMixin:
    """Mixed into ``MaxPaneApp`` ahead of ``App``.

    Two entry points, one clipboard path (``clipboard.copy_text``: native tool
    first, OSC 52 second, the status bar says which):

    * :meth:`action_copy_address` -- the ``⧉`` glyph's ``@click`` action;
    * :meth:`copy_to_clipboard` -- Textual's own entry point, reached by
      ``ctrl+c`` / ``super+c`` after a drag (``Screen.action_copy_text``) and,
      through :meth:`on_text_selected`, by releasing the mouse after a drag.
      Textual owns the mouse, so the terminal never has a selection of its own
      and Cmd+C copied nothing; ``App.copy_to_clipboard`` alone writes OSC 52,
      which Apple Terminal ignores.

    Textual selects text in ``Static``-based panels, ``Log`` and ``Markdown``.
    ``DataTable`` opts out (``ALLOW_SELECT = False``); ``RichLog`` highlights
    a drag but ``Widget.get_selection`` yields nothing for it because its
    render is a ``Panel``, not a ``Text`` (Textual 8.1.1).  Leaderboards and
    feeds therefore keep the icon as their copy path -- and a ``RichLog``
    subclass that ever renders a ``Text`` starts copying feed lines.
    """

    #: How long the outcome stays in the status bar.
    COPY_MESSAGE_S: float = 3.0

    async def action_copy_address(self, address: str) -> None:
        # Validated again here: the icon's meta is not the only way to invoke
        # an action, and an unvalidated value must never reach a subprocess.
        if not is_address(address):
            self._post_copy_message(clipboard.UNAVAILABLE, None)
            return
        outcome = await clipboard.copy_text(address, osc52=self._write_osc52)
        self._post_copy_message(outcome, address)

    def copy_to_clipboard(self, text: str) -> None:
        """Textual's copy entry point, rerouted through the native-first path.

        ``Screen.action_copy_text`` calls this synchronously, and the native
        tool is a subprocess, so the copy runs in a worker; the status bar
        gets the outcome when it is known.
        """
        if not text:
            return
        self.run_worker(
            self._copy_selection(text),
            name="copy-selection",
            group="copy-selection",
            exclusive=True,
            exit_on_error=False,
        )

    def on_text_selected(self, event: events.TextSelected) -> None:
        """Select-to-copy: the screen posts this on every mouse-up."""
        text = self.screen.get_selected_text()
        if text:
            self.copy_to_clipboard(text)

    async def _copy_selection(self, text: str) -> None:
        outcome = await clipboard.copy_text(text, osc52=self._write_osc52)
        self._post_copy_message(outcome, None)

    def _write_osc52(self, text: str) -> None:
        # The *base* implementation, on purpose: ``self.copy_to_clipboard`` is
        # the override above, and using it as the fallback of the path it
        # wraps would start a second copy for every one that misses pbcopy.
        App.copy_to_clipboard(self, text)

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
