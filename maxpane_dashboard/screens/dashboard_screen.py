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

import asyncio
import copy
import logging
from typing import Callable

from textual.binding import Binding
from textual import events, on
from textual.screen import Screen
from textual.widget import Widget

from maxpane_dashboard.data.reader import ReaderHandle
from maxpane_dashboard.screens.refresh_guard import RefreshGuard, _join
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.card_inner import LoadingCard

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

    #: Static documentation still loads on entry and manual refresh, without polling.
    POLL_DATA: bool = True

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
        self._loading_timer = None
        self._card_loading_frame = 0
        self._background_loading = False
        self._loading_projection = False
        self._projection_due = False
        self._entry_refresh = False
        self._view_snapshots = {}
        self._scope_active = False
        self._reads_ready = False
        self._entry_snapshot = None
        self._reader_revision = -1

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_screen_resume(self) -> None:
        """Fill the screen, start the poll interval, prime the status bar."""
        previous = getattr(self.app, '_dashboard_owner', None)
        if previous is not None and previous is not self and previous._scope_active:
            # Textual can resume the parent before the popped child unmounts.
            previous._stop_view()
        self.app._dashboard_owner = self
        self._activate_view()
        self._do_initial_refresh()
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
        if self.POLL_DATA and not isinstance(self._data_manager, ReaderHandle):
            self._refresh_timer = self.set_interval(
                self._poll_interval, self._schedule_refresh
            )
        if self._loading_timer is None:
            self._loading_timer = self.set_interval(0.2, self._tick_loading)
        self.call_after_refresh(self._tick_loading)
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
        """End ownership of reads while retaining the displayed/cache values."""
        self._stop_view()

    @on(events.Unmount)
    def _unmount_dashboard(self) -> None:
        self._stop_view()

    def _stop_view(self) -> None:
        if self._scope_active and not isinstance(self._data_manager, ReaderHandle):
            retired = getattr(self.app, '_retired_dashboards', [])
            if self not in retired:
                retired.append(self)
            self.app._retired_dashboards = retired
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None
        if self._loading_timer:
            self._loading_timer.stop()
            self._loading_timer = None
        self.cancel_refresh()
        setter = getattr(self._data_manager, 'set_active_view', None)
        if setter is not None and self._scope_active:
            setter(None)
        self._scope_active = False
        self._reads_ready = False
        self._background_loading = self._loading_projection = self._projection_due = False
        self._set_loading(False)

    def _loading_view(self):
        return getattr(self, '_mode', None) or self.GAME_NAME

    def _activate_view(self):
        self._reads_ready = False
        setter = getattr(self._data_manager, 'set_active_view', None)
        if setter is not None:
            setter(self._loading_view())
        self._scope_active = True
        self._entry_refresh = True

    def restart_view(self):
        """Native body switches have the same boundary as screen navigation."""
        self.cancel_refresh()
        self._background_loading = self._loading_projection = self._projection_due = False
        self._activate_view()
        if self._refresh_timer is not None:
            self._refresh_timer.reset()
        self.start_refresh()
        self._tick_loading()

    @property
    def loading_suffix(self):
        """Compatibility for title composers; loading lives in the footer."""
        return ''

    def _set_loading(self, busy):
        for bar in self.query(StatusBar):
            bar.set_loading(busy)
        self._card_loading_frame = (self._card_loading_frame + 1) % 8 if busy else 0
        for card in self.query(LoadingCard):
            card.set_card_loading(busy and self.is_current and card.is_on_screen and card.visible,
                                  self._card_loading_frame)

    def _reads_pending(self):
        loading = getattr(self._data_manager, 'is_loading', None)
        return bool(loading(self._loading_view())) if callable(loading) else False

    def _tick_loading(self):
        if not self.is_current:
            return
        if isinstance(self._data_manager, ReaderHandle):
            # Local metadata only: acquisition and expensive projection belong
            # to the reader's independent clock, not this animation timer.
            if self._reader_revision != self._data_manager.revision and not self._refresh_in_flight:
                self._loading_projection = True
                self.start_refresh()
            self._set_loading(self._reads_pending())
            return
        background = self._reads_pending()
        if self._background_loading and not background:
            self._projection_due = True
        if self._projection_due and not self._refresh_in_flight:
            self._projection_due = False
            self._loading_projection = True
            self.start_refresh()
        self._background_loading = background
        self._set_loading(self._refresh_in_flight or background)

    def _snapshot_data(self):
        getter = getattr(self._data_manager, 'get_snapshot', None)
        if callable(getter):
            return getter()
        return self._view_snapshots.get(self._loading_view())

    async def _guarded_refresh(self, generation=None):
        try:
            if isinstance(self._data_manager, ReaderHandle):
                self._entry_refresh = False
                self._reads_ready = True
                # The reader owns cancellation/drain barriers. A UI worker only
                # reads its published snapshot and must not wait behind I/O.
                await super()._guarded_refresh(generation)
                return
            if self._entry_refresh:
                self._entry_refresh = False
                self._entry_snapshot = self._snapshot_data()
                if self._entry_snapshot is not None:
                    self._loading_projection = True
                    await self._do_refresh()
                self._loading_projection = False
            # Ownership crosses Screen instances as well as native body swaps.
            retired = list(getattr(self.app, '_retired_dashboards', []))
            for screen in dict.fromkeys([*retired, self]):
                workers = tuple(getattr(screen, '_retired_refreshes', []))
                for worker in workers:
                    await _join(worker)
                screen._retired_refreshes = [w for w in getattr(screen, '_retired_refreshes', [])
                                            if w not in workers]
                drain = getattr(screen._data_manager, 'drain_reads', None)
                if callable(drain):
                    await drain()
            if generation is not None and generation != self._refresh_generation:
                raise asyncio.CancelledError('retired dashboard handoff')
            pending = getattr(self.app, '_retired_dashboards', [])
            self.app._retired_dashboards = [screen for screen in pending if screen not in retired]
            self._reads_ready = True
            await super()._guarded_refresh(generation)
        finally:
            if generation is None or generation == self._refresh_generation:
                self._refresh_in_flight = False
                if self.is_current:
                    self._background_loading |= self._reads_pending()
                    self.call_after_refresh(self._tick_loading)

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

    async def _fetch_data(self) -> dict:
        """Fetch the payload; snapshot screens may supply a cheaper projection."""
        if isinstance(self._data_manager, ReaderHandle):
            # Read revision first: a racing publication can cause an extra
            # paint, but can never mark an older snapshot as the newest one.
            revision = self._data_manager.revision
            if self._loading_projection:
                self._loading_projection = False
                data = self._snapshot_data()
            else:
                data = await self._fetch_live_data()
            self._reader_revision = revision
            return data or {}
        if self._loading_projection:
            self._loading_projection = False
            data = self._entry_snapshot if self._entry_snapshot is not None else self._snapshot_data()
            self._entry_snapshot = None
            return data or {}
        generation, view = self._refresh_generation, self._loading_view()
        data = await self._fetch_live_data()
        if generation != self._refresh_generation or view != self._loading_view():
            raise asyncio.CancelledError('view changed during refresh')
        self._view_snapshots[view] = copy.deepcopy(data)
        return data

    async def _fetch_live_data(self):
        return await self._data_manager.fetch_and_compute()

    async def _do_refresh(self) -> None:
        """Fetch once, then update the title, every panel and the status bar.

        Every step is contained on its own: one panel that cannot render never
        stops the next one, and never stops the status bar from saying when the
        data is from.
        """
        try:
            data = await self._fetch_data()
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
