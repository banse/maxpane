"""The lifecycle and the fetch-to-widget dispatch every dashboard screen shares.

Fourteen screens inherit :class:`~maxpane_dashboard.screens.refresh_guard.RefreshGuard`
and ten of them are *the same five things hand-copied*: a constructor that
stores the manager, the poll interval and a timer slot; an ``on_screen_resume``
that fires the first refresh, starts the interval and primes the status bar; an
``on_screen_suspend`` that stops the timer; and a ``_do_refresh`` that fetches
once and then repeats, per panel::

    try:
        self.query_one(SomeWidget).update_data(
            a=data.get("a"),
            b=data.get("b", ""),
        )
    except Exception as exc:
        logger.debug("Failed to update SomeWidget: %s", exc)

**151 such blocks across the 14 screens** (counted on the tree, 2026-09-20).
Copied code does not stay copied, and the drift is measurable rather than
hypothetical:

* **Log levels diverged.** ``debug`` in most screens, ``warning`` in bakery and
  frenpet, ``error`` for a failed fetch in base/bakery/frenpet/frenpet_full.
  ``debug`` is *below* the app's handler level, so the majority of screens threw
  away exactly the lines the degradation convention exists to leave behind: a
  panel that cannot render is worth one line in ``~/.maxpane/maxpane.log``.
  This module logs every degraded step at ``warning``, once.
* **The failure path itself was not copied faithfully.** bakery and frenpet read
  ``self._data_manager._error_count`` *bare* inside the handler that runs when a
  fetch has already failed; a manager without that attribute turns a degraded
  refresh into an ``AttributeError`` raised out of the error handler. The other
  eight screens read it with ``getattr(..., 0)``. Here it is read once, with the
  default, so every screen degrades instead of two of them crashing.
* **A dropped panel is invisible.** A dispatch block that is deleted, or a
  widget renamed out of ``compose``, produces no failure anywhere: the screen
  simply stops updating that panel. There is nothing to assert against 151
  hand-typed blocks.

A subclass therefore declares *data*, not control flow: :attr:`DashboardScreen.PANELS`
is a tuple of ``(widget class, adapter)`` rows, where the adapter maps the
manager's flat dict to that widget's ``update_data`` keyword arguments —
:func:`keys` builds the adapter for the dominant ``data.get`` shape, and a panel
that computes gets a module-level function in its own screen. The rows are then
data a test can read:
``tests/screens/test_dashboard_screen.py::test_every_panel_row_names_a_mounted_widget_and_its_update_data_keywords``
mounts every subclass and checks each row against ``compose`` and against the
widget's real signature, so a mistyped key, a dropped row or a widget that is
not in ``compose`` reddens a named test instead of silently blanking a panel.

What stays per screen: ``compose`` (the layouts genuinely differ), ``on_mount``,
``action_toggle_view``, an ``_update_title`` body, and the one extra status-bar
line some screens prime (``_prime_status_bar``). What a screen must never
re-declare: the scheduling methods (they belong to ``RefreshGuard``), the
lifecycle handlers, or a hand-rolled dispatch block.
"""

from __future__ import annotations

import copy
import logging
from typing import Callable

from textual.binding import Binding
from textual.screen import Screen
from textual.widget import Widget

from maxpane_dashboard.screens.refresh_guard import RefreshGuard
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)

#: A panel adapter: the manager's flat payload in, one widget's ``update_data``
#: keyword arguments out.
Adapter = Callable[[dict], dict]


def keys(*names: str, **defaults: object) -> Adapter:
    """Build the adapter for the dominant dispatch shape: ``data.get`` per key.

    ``keys("a", "b", b="")`` is exactly ``a=data.get("a"), b=data.get("b", "")``
    — the block it replaces, default for default. Every keyword argument the
    panel receives is named in *names*; *defaults* only supplies the fallback
    for the ones that had one, so a key with no default reads as a plain
    ``data.get`` and a failed read arrives as ``None`` (never ``0``).

    A default naming a key that is not in *names* is a typo — ``faucet_opn=True``
    beside ``"faucet_open"`` would otherwise be silently ignored and the panel
    would quietly receive ``None`` — so it raises here, at import time of the
    screen that declared it.

    A mutable default (``top_pets=[]``) is **copied per call**, as the block it
    replaces built a fresh ``[]`` on every refresh. Handing every refresh the
    one list object the adapter was declared with would let a panel that
    appends to what it receives accumulate rows across refreshes (WP-B
    review M4).
    """
    unknown = sorted(set(defaults) - set(names))
    if unknown:
        raise ValueError(
            f"keys(): default(s) {unknown} name no key in {list(names)}; "
            "a default only supplies the fallback for a key that is listed"
        )

    def adapt(data: dict) -> dict:
        return {
            name: data[name] if name in data else copy.copy(defaults.get(name))
            for name in names
        }

    return adapt


class DashboardScreen(RefreshGuard, Screen):
    """A polling dashboard screen: lifecycle here, panels declared as data.

    Subclass it, set :attr:`GAME_NAME`, :attr:`REFRESH_WORKER_NAME` and
    :attr:`PANELS`, write ``compose`` — and write no ``__init__``,
    ``on_screen_resume``, ``on_screen_suspend`` or ``_do_refresh``. A screen
    with extra state of its own (a view toggle) may keep an ``__init__`` that
    calls ``super().__init__(manager, poll_interval, name=name, **kwargs)``
    first and sets only that state.
    """

    #: The words the status bar shows for this dashboard, e.g.
    #: ``"onchain monsters"``. Also the subject of the refresh-failure log
    #: line. Every subclass sets it; the empty default is what the guard test
    #: (``test_every_polling_screen_uses_the_guard``) refuses.
    GAME_NAME: str = ""

    #: Worker name for the guarded refresh, set per screen (see
    #: :class:`~maxpane_dashboard.screens.refresh_guard.RefreshGuard`).
    #: Annotation only: the default stays RefreshGuard's single source, so the
    #: guard test's "must set its own" check keeps biting.
    REFRESH_WORKER_NAME: str

    #: The dispatch, as data: one ``(widget class, adapter)`` row per panel, in
    #: the order the screen updates them. The class is what ``query_one``
    #: resolves inside this screen; the adapter turns the manager's flat payload
    #: into that widget's ``update_data`` keyword arguments (:func:`keys` for the
    #: plain ``data.get`` shape, a module-level function where a panel computes).
    #: The status bar is NOT a row — :meth:`_do_refresh` always updates it last.
    PANELS: tuple[tuple[type[Widget], Adapter], ...] = ()

    #: ``r`` refreshes on every dashboard, and every subclass inherits it:
    #: Textual merges ``BINDINGS`` along the MRO (verified on Textual 8.1.1 --
    #: a subclass declaring only ``c`` answers to ``c`` *and* ``r``), so a
    #: screen with extra keys lists only those extra keys. ttt and talismans
    #: re-list ``r`` today; that is harmless, not required, and WP-B owns their
    #: lists.
    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    def __init__(
        self,
        manager,
        poll_interval: int = 30,
        name: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(name=name, **kwargs)
        self._data_manager = manager
        self._poll_interval = poll_interval
        self._refresh_timer = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_screen_resume(self) -> None:
        """Fill the screen, start the poll interval, prime the status bar."""
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            bar = self.query_one(StatusBar)
            bar.set_theme_name(self.app.theme)
            bar.set_game_name(self.GAME_NAME)
            self._prime_status_bar(bar)
        except Exception:
            # A harness may mount no StatusBar; a dashboard without a footer is
            # not a reason to refuse to render.
            pass

    def on_screen_suspend(self) -> None:
        """Stop polling when switching away."""
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _prime_status_bar(self, bar: StatusBar) -> None:
        """Hook: the one extra status-bar line a screen primes on resume.

        ``set_active_view`` (fwa, ttt, talismans) or ``set_key_hints`` (surf).
        Default no-op. Runs inside the resume handler's own ``try``, so a screen
        that raises here loses its extra line, not its refresh.
        """

    def _update_title(self, data: dict) -> None:
        """Hook: refresh the screen's own title bar from *data*. Default no-op.

        The body lives in the subclass; the containment lives here, so no screen
        has to remember the ``try/except`` around it again.
        """

    # ------------------------------------------------------------------
    # The refresh
    # ------------------------------------------------------------------

    async def _do_refresh(self) -> None:
        """Fetch once, then update the title, every panel and the status bar.

        Every step is contained on its own: one panel that cannot render never
        stops the next one, and never stops the status bar from saying when the
        data is from.
        """
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            logger.warning("%s refresh failed: %s", self.GAME_NAME, exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=999,
                    # getattr, not a bare read: this handler runs *because*
                    # something already failed, and a manager without the
                    # attribute must degrade, not raise out of the error path.
                    error_count=getattr(self._data_manager, "_error_count", 0),
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        try:
            self._update_title(data)
        except Exception as exc:
            logger.warning("Failed to update the title bar: %s", exc)

        for widget_class, adapt in self.PANELS:
            try:
                self.query_one(widget_class).update_data(**adapt(data))
            except Exception as exc:
                logger.warning("Failed to update %s: %s", widget_class.__name__, exc)

        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=data.get("last_updated_seconds_ago", 0),
                error_count=data.get("error_count", 0),
                poll_interval=data.get("poll_interval", self._poll_interval),
            )
        except Exception as exc:
            logger.warning("Failed to update StatusBar: %s", exc)
