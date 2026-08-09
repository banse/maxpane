"""SurfScreen -- surfsurf.eth Mission Control as a Textual Screen.

Layout (the house pattern; structurally the FWA screen with the hero split
into two side-by-side widgets)::

    #title-bar      SURF · IMD $x.xx · parity ±x.x% · feed #N (age)
    #hero-row       SurfHero (3fr)   | SurfSignals (2fr)
    #middle-row     SurfFeed (3fr)     | SurfMarket (2fr)
                    SurfDevActivity (3fr)
                      -- one or the other, toggled with `c`
    #separator
    #bottom-row     SurfNft (full width)
    StatusBar

Deliberate choices, in the FWA screen's terms (see screens/fwa.py, whose
docstring carries the full rationale):

1. **``c`` toggles the announce feed and the dev-activity table** in the
   middle-left slot. Both stay mounted and both are dispatched to on every
   refresh, so toggling is a visibility flip with no refetch and no blank
   first frame.
2. **Every widget update is individually guarded** -- one widget raising must
   never cost the other five their refresh. A *manager* failure touches only
   the StatusBar and leaves the previous frame standing.
3. **Degradation reaches the title bar** (``· degraded: …``), because the
   shared StatusBar API has no ``set_degraded()``.

The screen is clock-free: every time-derived string (``feed_last_post_age_s``,
per-signal ages) arrives pre-computed in the payload. Nothing here consults
the wall clock, so any captured instant replays forever in tests.

Written against the frozen ``SURF_KEYS`` contract, not against
``SurfManager``'s internals -- any object with an awaitable
``fetch_and_compute()`` returning that dict drives it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard import __version__
from maxpane_dashboard.screens.refresh_guard import RefreshGuard
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surf import (
    SurfDevActivity,
    SurfFeed,
    SurfHero,
    SurfMarket,
    SurfNft,
    SurfSignals,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from maxpane_dashboard.data.surf_manager import SurfManager

logger = logging.getLogger(__name__)

_EMDASH = "—"

#: Shown until the first payload lands.
INITIAL_TITLE = "SURF · Mission Control · Ethereum Mainnet"

#: Sentinel staleness pushed to the StatusBar when the manager itself failed.
MANAGER_FAILURE_SECONDS = 999

#: Measured in Task WP5.5 (provisional: the FWA number until then).
SURF_FULL_LAYOUT_COLUMNS = 143


# -- format helpers ----------------------------------------------------


def _num(value, default: float = 0.0) -> float:
    """Coerce to ``float``, falling back to ``default`` — never raise."""
    if value is None or isinstance(value, bool):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out:  # NaN
        return default
    return out


def _fmt_int(value) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _EMDASH


def _fmt_usd(value) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        out = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if out != out:
        return _EMDASH
    return f"${out:,.2f}"


def _fmt_signed_pct(value) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        out = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if out != out:
        return _EMDASH
    return f"{out:+.1f}%"


def _fmt_age(value) -> str:
    """``42s`` / ``17m`` / ``23h`` / ``3d`` — or an em-dash for ``None``.

    90 is the seconds/minutes boundary and 90 min the minutes/hours boundary
    (``5400.0`` renders ``90m``); 36 h is the hours/days boundary — the same
    tiers the sparkline axis uses.
    """
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if seconds != seconds or seconds < 0:
        return _EMDASH
    if seconds < 90:
        return f"{int(seconds)}s"
    if seconds <= 90 * 60:
        return f"{int(seconds // 60)}m"
    if seconds < 36 * 3600:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def _fmt_degraded(sources) -> str:
    """``· degraded: logs, market`` — or an empty string when all is well.

    Only ``None``/``[]`` (or anything else falsy) genuinely mean "nothing is
    degraded" and may render empty. Every other input must render
    *something* visibly wrong, even if it is a shape the manager should
    never actually produce: a bare ``except: return ""`` here would let a
    malformed ``degraded`` value collapse the title bar to the healthy line
    on the single most prominent row of the screen, which is the exact
    failure this whole project exists to prevent.
    """
    if not sources:
        return ""

    # A bare string is one group name, not a sequence of one-letter groups
    # (``"logs"`` iterates to ``"l", "o", "g", "s"`` otherwise).
    if isinstance(sources, (str, bytes)):
        sources = [sources]

    try:
        names = [str(s).strip() for s in sources if str(s).strip()]
    except TypeError:
        # Truthy but not iterable (an int, a float, ...) -- an unexpected
        # shape the manager never emits today, but "unreachable today" is
        # not a reason to fail toward looking healthy.
        return " · degraded: ?"

    if not names:
        return " · degraded: ?"
    return " · degraded: " + ", ".join(names)


def _title_line(data: dict) -> str:
    """Compose the meta row (PRD §4).

    Ordered by what must survive a narrow terminal: warnings before the
    version tail, because ``#title-bar`` is one row high and the tail is what
    gets clipped. Parity renders with the em-dash fallback rather than a
    zero: a dead market source must never read as perfect parity.
    """
    feed_age = _fmt_age(data.get("feed_last_post_age_s"))
    line = (
        f"SURF · IMD {_fmt_usd(data.get('imd_price_usd'))} · "
        f"parity {_fmt_signed_pct(data.get('parity_pct'))} · "
        f"feed #{_fmt_int(data.get('feed_nonce'))} ({feed_age})"
    )

    if data.get("lp_owner_ok") is False:
        line += " · [yellow]⚠ LP owner changed[/]"

    line += _fmt_degraded(data.get("degraded"))
    # Plain, unmarked version tail: the StatusBar already carries the dim
    # version, and markup here would only complicate every assertion on the
    # end of this string.
    line += f" · v{__version__}"
    return line


class SurfScreen(RefreshGuard, Screen):
    """surfsurf.eth Mission Control dashboard."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("c", "toggle_view", "Feed/Activity", show=True),
    ]

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "surf-refresh"

    # Structural fallback only. WP6 restates these in themes/minimal.tcss
    # (one owner) the way the FWA block does, app-stylesheet rules then beat
    # DEFAULT_CSS. They live here so the screen is reviewable and correctly
    # proportioned on its own, under any theme that has no surf block.
    #
    # #hero-row is height 10: SurfSignals renders six detector rows plus a
    # title inside a border. Any theme rule that adds vertical padding here
    # drops the sixth row -- the BURN detector -- which is exactly the FWA
    # coverage-badge clipping bug. The compositor test pins all six rows.
    DEFAULT_CSS = """
    SurfScreen #title-bar {
        width: 100%;
        height: 1;
        text-align: center;
        content-align: center middle;
    }
    SurfScreen #hero-row {
        height: 10;
        margin: 1 0 0 0;
    }
    SurfScreen SurfHero {
        width: 3fr;
        padding: 0 1;
    }
    SurfScreen SurfSignals {
        width: 2fr;
        padding: 0 1;
    }
    SurfScreen #middle-row {
        height: 1fr;
        margin: 1 0 0 0;
    }
    SurfScreen SurfFeed {
        width: 3fr;
        padding: 0 1;
    }
    SurfScreen SurfDevActivity {
        width: 3fr;
        padding: 0 1;
    }
    SurfScreen SurfMarket {
        width: 2fr;
        padding: 0 1;
    }
    SurfScreen #separator {
        width: 100%;
        height: 1;
        padding: 0 2;
    }
    SurfScreen #bottom-row {
        height: 1fr;
        margin: 0 0 1 0;
    }
    SurfScreen SurfNft {
        width: 1fr;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        data_manager: "SurfManager",
        poll_interval: int = 30,
        name: str = "surf",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None
        #: Which widget owns the middle-left slot: "feed" or "activity".
        self._active_view: str = "feed"

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(INITIAL_TITLE, id="title-bar")

        with Horizontal(id="hero-row"):
            yield SurfHero()
            yield SurfSignals()

        with Horizontal(id="middle-row"):
            # Two views of one slot, toggled with ``c``. The activity table
            # is created hidden rather than on demand so it keeps receiving
            # every refresh and is already populated when toggled to.
            yield SurfFeed()
            activity = SurfDevActivity()
            activity.display = False
            yield activity
            yield SurfMarket()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield SurfNft()

        yield StatusBar()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_screen_resume(self) -> None:
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("surf")
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    # ------------------------------------------------------------------
    # Refresh flow (Task WP5.3 fills this in)
    # ------------------------------------------------------------------

    async def _do_refresh(self) -> None:
        await self._data_manager.fetch_and_compute()
