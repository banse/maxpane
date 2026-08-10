"""SurfScreen -- the surfsurf.eth Surfboard as a Textual Screen.

Layout: three content rows, every widget on screen at once::

    #title-bar         SURF · IMD $x.xx · parity ±x.x% · feed #N (age)
    #hero-row          SurfHero (full width, four boxes)
    #middle-row        SurfFeed (7fr)   | #surf-right-rail (6fr)
                                        |   SurfSignals     (auto, +1 margin)
                                        |   SurfDevActivity (1fr)
    #separator
    #bottom-row        SurfMarket (7fr) | SurfNft (6fr)
    StatusBar

Both rows below the hero are split 7:6 on the same seam, so the two rows
read as one grid rather than two unrelated bands.

**The seam is a measurement.** It was 3:2 until 2026-08-10. The left
column's binding panel is ``SurfFeed`` (81 columns before it breaks a post),
the right column's is ``SurfDevActivity`` (71 columns of rail before it
sheds a field), so the narrowest terminal serving both is 81 + 71 = 152 --
but only a seam near 81:71 collects it. 3:2 hands the feed 0.60 W against
the 0.538 it needs, so the rail reached 71 only at 176: 24 columns of waste,
and past the ~169 a laptop gets at the 17 pt ``__main__`` forces on launch,
i.e. the full layout was unreachable at the app's own font size. Every
candidate seam was swept over the real screen (5:3 187 · 3:2 176 · 7:5 169 ·
4:3 164 · 6:5 155 · 7:6 152 · 1:1 162); 152 is the floor, four seams reach
it, 7:6 is the simplest. The table and both pins live in
``tests/screens/test_surf_screen.py``.

**Nothing is hidden.** Until 2026-08-10 the announce feed and the
dev-activity panel shared the middle-left slot and ``c`` swapped them, which
meant half the dashboard's content was off screen at any moment and the
status bar had to carry a ``view:`` word to say which half. The activity
panel moved into the rail under the signals, the market moved down beside
the NFT panel, and the key, its action, the status-bar indicator and their
tests went with the slot they served. The market did not cost the bottom
row a single row on the way: ``SurfNft`` is the taller of the two (its
last-sales block runs to four lines), so an ``auto`` row sized to the NFT
panel already had room for the market's seven.

``SurfSignals`` is ``auto`` (a title, a spacer and six detector rows) with a
one-row bottom margin, and ``SurfDevActivity`` takes the rest of the rail at
``1fr``, floored by ``ACTIVITY_MIN_HEIGHT``. That margin is the blank line
between the two rail panels: they sat flush and read as one block. A margin
rather than a spacer widget -- nothing to compose, nothing to query, and it
collapses into the rail's scroll extent like any other row, so ``TALLER_HINT``
keeps accounting for it. It costs the rail exactly one row: the marker now
lights at 36 rows instead of 35, and the first genuinely-lost activity row
moved 33 -> 34 with it, so the marker still leads the loss by two. That floor is what keeps the rail's
``overflow-y: auto`` honest: a ``1fr`` child cannot overflow its scroll
container -- it shrinks -- so without a floor the activity panel would shed
one row per terminal row down to a bare title with no scrollbar, no marker
and no other trace anywhere on screen. That is exactly what ``SurfMarket``
did from this same rail until 2026-08-09, and it is the reason the floor is
declared rather than left to Textual.

The hero was half a row wide until 2026-08-09 and shared it with the
signals panel. Two things were wrong with that. Its four boxes had to
share a ``3fr`` half, which left each of them 13 content columns on a
139-column terminal -- narrow enough that the box copy had to shed whole
fields to fit (see ``widgets/surf/hero.py``), and the ``full`` tier was
unreachable below ~220 columns, i.e. on no terminal anybody owns. And the
row was pinned at ``height: 10`` for a ``height: 7`` widget, so three rows
under the boxes were reserved and blank on every launch. Full width buys
each box ~26 columns at the same 139, which reaches the ``full`` tier, and
the row now sizes to its content.

**Every row but the middle one sizes to its content**, and the middle row
alone carries ``1fr``. That is what makes a tall terminal grow the feed
instead of stranding whitespace: previously ``#bottom-row`` also carried
``1fr`` and took half the slack for a panel with eight lines in it, which
left roughly a fifth of the screen empty above the status bar.

Deliberate choices, in the FWA screen's terms (see screens/fwa.py, whose
docstring carries the full rationale):

1. **Every widget update is individually guarded** -- one widget raising must
   never cost the other five their refresh. A *manager* failure touches only
   the StatusBar and leaves the previous frame standing.
2. **Degradation reaches the title bar** (``· degraded: …``), because the
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
from textual.containers import Horizontal, Vertical
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

#: Shown until the first payload lands -- and, on the degraded path where the
#: manager raises, for good: ``_title_line`` is what replaces it and that code
#: is never reached. The name here must therefore be the name the game-select
#: menu uses (``screens/game_select.GAMES``), which is asserted by
#: ``test_the_initial_title_names_the_dashboard_the_menu_names``. It was not:
#: the rename to "Surfboard" reached the menu, the README and CLAUDE.md and
#: stopped here, so the one surface a user reads *inside* the dashboard kept
#: the old name.
INITIAL_TITLE = "SURF · Surfboard · Ethereum Mainnet"

#: The row-wise counterpart of the widgets' ``‹ widen``: the right rail holds
#: more than this terminal's height can show, so some of SIGNALS / DEV
#: ACTIVITY is scrolled off. It rides the **title bar** rather than a panel
#: title because a panel title is itself the first thing a short rail loses --
#: when the market was still in this rail, 143x31 composited the ``IMD
#: MARKET`` heading alone and 143x30 not even that. Row 0 cannot be pushed off
#: by anything.
#:
#: It lights at or below **36** rows and is dark from 37 up. It was 35/36
#: until 2026-08-10, when the one-row margin under ``SurfSignals`` -- the
#: blank line separating the rail's two panels -- made the rail's content one
#: row taller. Nothing else about the threshold moved: the first genuinely
#: lost activity row went 33 -> 34 in the same step, so the marker still leads
#: the first real loss by two rows, which is the property that matters.
#: Below 20 rows the bottom row goes off the end of a screen that has itself
#: started scrolling; the marker is already lit long before that, so nothing
#: is ever lost in silence.
#:
#: Riding row 0 is necessary but not sufficient: that row is one line of a
#: *wrapping* ``Static``, so its own tail is silently dropped rather than
#: ellipsised. ``_title_line`` therefore puts this marker ahead of both
#: warnings -- see its docstring for why it, of the three, is the one that
#: has to survive.
TALLER_HINT = "‹ taller"

#: Sentinel staleness pushed to the StatusBar when the manager itself failed.
MANAGER_FAILURE_SECONDS = 999

#: The rail's floor for ``SurfDevActivity``: a title, a spacer and five rows
#: -- the same seven rows ``SurfMarket`` occupied here until it moved to the
#: bottom row, which is why the height at which ``TALLER_HINT`` lights did not
#: move then. (It moved one row later, when the signals panel gained its
#: separating margin: 35 -> 36. This floor is unchanged.)
#: A ``1fr`` child shrinks instead of overflowing its scroll
#: container, so this floor is the only thing that turns "the rail is too
#: short" into an overflow the screen can see and advertise; without it the
#: panel silently thins to its title. **Restated as ``min-height`` in both
#: stylesheets** -- CSS cannot read a Python constant, so
#: ``test_the_activity_floor_is_the_same_number_in_both_stylesheets`` pins the
#: three copies together.
ACTIVITY_MIN_HEIGHT = 7

#: Measured against composited output, not estimated -- see tests.
#:
#: Reconciled to the measured **152** on 2026-08-10, re-swept column by column
#: before the constant moved: 151 lights exactly one marker (the activity
#: panel's), 152 lights none, and nothing above it lights one either. The
#: number is quoted by ``__main__.FULL_LAYOUT_COLUMNS``, the ``--font-size``
#: help text, the README width table and CLAUDE.md, and all five now agree.
#: ``tests/screens/test_surf_screen.MEASURED_FULL_LAYOUT_COLUMNS`` holds the
#: same number as an **independent literal** and pins it to the real screen in
#: both directions; keep it a separate literal, because a test that aliased it
#: to this constant would compare a number against itself and pin nothing.
#: A documented width *above* the measured one is merely generous -- one
#: *below* it would clip, which is what
#: ``test_the_documented_width_still_covers_the_measured_one`` forbids.
#:
#: The history, because the number has moved three times in three days. It
#: was 135
#: while ``SurfDevActivity`` had a ``3fr`` slot of its own (shared with the
#: feed, behind a ``c`` swap that no longer exists). The three-row restructure
#: traded that slot for a share of the right rail and the number went to 176 --
#: not because the panel needs 176 columns, but because a **3:2** seam gives
#: the rail only ``0.4 * W`` and the rail needs 71. Re-seaming to **7:6** hands
#: the feed exactly the 0.538 it needs and the rail the rest, and 81 + 71 = 152
#: falls out -- so the number came back **down**, 176 -> 152, without hiding
#: anything. The whole seam sweep is in the screen docstring and, with the
#: losing candidates, in the test module.
#:
#: 152 is inside the ~169 columns a laptop gets at the forced 17 pt, which was
#: the point of re-seaming: at 176 the full layout was unreachable at the
#: font size the app itself picks, and ``--font-size 12`` was the only way in.
#:
#: The measured number deliberately EXCLUDES posts carrying an inherently
#: unbreakable token (a URL glued to a raw tx hash, e.g. by a trailing
#: period with no space -- the real nonce-13 capture's link is 91 columns).
#: SurfFeed correctly truncates such a token and lights its own ``‹ widen``;
#: *this particular capture* clears at 216 (194 before the re-seam, the feed
#: being narrower now), and the next real post linking a transaction
#: reproduces the shape at whatever width its own token needs. A fixture
#: containing one therefore cannot be what "full layout" is measured against
#: -- see ``test_a_linked_post_advertises_widen_at_the_full_layout_width``.
#: Do not raise this toward 216 to silence a linked post's marker: that
#: marker is correct, and 216 is a "full layout" nobody could reach.
SURF_FULL_LAYOUT_COLUMNS = 152


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


def _title_line(data: dict, row_hint: bool = False) -> str:
    """Compose the meta row (PRD §4).

    Ordered by what must survive a narrow terminal, because ``#title-bar`` is
    ``height: 1`` around a wrapping ``Static``: everything past the first
    line reaches no pixel at all -- no ``…``, no scrollbar, no trace. The tail
    of this string is not "clipped", it is *gone*, so the order here is the
    only priority mechanism the row has. Parity renders with the em-dash
    fallback rather than a zero: a dead market source must never read as
    perfect parity.

    ``row_hint`` -- the height counterpart of a widget's ``‹ widen`` -- comes
    **first**, ahead of both warnings. It used to sit after the degraded list,
    which meant the one advertisement on this screen with no second home was
    lost exactly when a source was also down: three degraded groups plus the
    LP warning ran the line to 118 columns, and at 100 the wrap fell inside
    the list. The warnings are each mirrored inside a panel (the LP flag is
    the hero's ``OWNER CHANGED`` box; a degraded group is that panel's own
    unavailable state), and nothing anywhere else says a row went off the
    bottom of the rail -- so if exactly one of the three has to survive a
    narrow terminal, it is this one. The version tail stays last: the
    StatusBar carries the version too.
    """
    feed_age = _fmt_age(data.get("feed_last_post_age_s"))
    line = (
        f"SURF · IMD {_fmt_usd(data.get('imd_price_usd'))} · "
        f"parity {_fmt_signed_pct(data.get('parity_pct'))} · "
        f"feed #{_fmt_int(data.get('feed_nonce'))} ({feed_age})"
    )

    if row_hint:
        line += f" · [yellow]{TALLER_HINT}[/]"

    if data.get("lp_owner_ok") is False:
        line += " · [yellow]⚠ LP owner changed[/]"

    line += _fmt_degraded(data.get("degraded"))
    # Plain, unmarked version tail: the StatusBar already carries the dim
    # version, and markup here would only complicate every assertion on the
    # end of this string.
    line += f" · v{__version__}"
    return line


class SurfScreen(RefreshGuard, Screen):
    """surfsurf.eth Surfboard dashboard."""

    #: No ``c``: the swap it drove died with the shared slot (see the module
    #: docstring). A key that hides half the screen has nothing to offer a
    #: layout whose whole point is that nothing is hidden.
    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "surf-refresh"

    # Structural fallback only. WP6 restates these in themes/minimal.tcss
    # (one owner) the way the FWA block does, app-stylesheet rules then beat
    # DEFAULT_CSS. They live here so the screen is reviewable and correctly
    # proportioned on its own, under any theme that has no surf block. The
    # two copies must stay in agreement -- edit both or neither.
    #
    # `#hero-row` is `height: auto` and carries NO vertical padding. SurfHero
    # is a height-7 widget whose boxes hold five content lines inside a
    # height-7 frame; one row of vertical padding here clips the bottom
    # border off the screen, which is the FWA hero-clipping bug. `auto` also
    # replaces the old `height: 10`, whose three spare rows were the dead
    # space above the feed.
    #
    # `#middle-row` is the ONLY `1fr` row on the screen, so every row a
    # taller terminal adds lands in the feed and the activity panel.
    # `#bottom-row` is `auto`: the market's seven rows and the NFT panel's
    # eight are content, not slack, and a `1fr` here used to hand them half
    # the screen's spare rows.
    #
    # Inside the rail SurfSignals is `auto` -- a title, a spacer and six
    # detector rows, exactly 8 -- plus a one-row bottom margin, the blank line
    # that stops the two rail panels reading as one block. A margin, not a
    # spacer widget: nothing to compose or query, and it collapses into the
    # rail's scroll extent like any other row, so `TALLER_HINT` still accounts
    # for it (that marker moved 35 -> 36 rows, and the first real loss 33 ->
    # 34, so it still leads the loss by two).
    # SurfDevActivity takes the remainder at
    # `1fr` with a `min-height` floor. The floor is the load-bearing part: a
    # `1fr` child cannot overflow its scroll container, it shrinks, so
    # without one the activity panel would shed a row per terminal row down
    # to a bare title with no scrollbar, no marker and no trace on screen.
    # SurfMarket did precisely that from this rail until 2026-08-09.
    # With the floor the rail's content height is a constant
    # 8 + ACTIVITY_MIN_HEIGHT, which is what makes the overflow, the
    # scrollbar and the title bar's `‹ taller` fire on the same terminal row.
    #
    # Vertical padding on SurfSignals costs the sixth detector row -- BURN --
    # while the panel still looks complete. tests/test_surf_registration.py
    # asserts all six reach the compositor.
    #
    # The rail scrolls (`overflow-y: auto`, at the stylesheet-wide
    # `scrollbar-size: 1 1`) as the short-terminal guard. Scrolling is the
    # *affordance* -- nothing is dropped, it is all still reachable. The
    # *advertisement* is `TALLER_HINT` on the title bar, because a one-cell
    # scrollbar in a gutter names nothing, and at very short heights Textual
    # paints it outside the rail's own rectangle.
    #
    # Both rows below the hero split 7:6 on the same seam: SurfFeed/SurfMarket
    # take `7fr`, the rail/SurfNft `6fr`. Measured, not chosen -- the feed
    # needs 81 columns for an unbroken post and the rail 71 before the
    # activity panel sheds a field, so 152 is the floor and only a seam near
    # 81:71 collects it. This was 3:2 until 2026-08-10, which over-fed the
    # left column and pushed the full layout to 176. Equal shares are wrong in
    # the other direction: 1:1 starves the feed and costs 162.
    DEFAULT_CSS = """
    SurfScreen #title-bar {
        width: 100%;
        height: 1;
        text-align: center;
        content-align: center middle;
    }
    SurfScreen #hero-row {
        height: auto;
        margin: 1 0 0 0;
    }
    SurfScreen SurfHero {
        width: 1fr;
        padding: 0 1;
    }
    SurfScreen #middle-row {
        height: 1fr;
        margin: 1 0 0 0;
    }
    SurfScreen SurfFeed {
        width: 7fr;
        padding: 0 1;
    }
    SurfScreen #surf-right-rail {
        width: 6fr;
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }
    SurfScreen SurfSignals {
        width: 1fr;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    SurfScreen SurfDevActivity {
        width: 1fr;
        height: 1fr;
        min-height: 7;
        padding: 0 1;
    }
    SurfScreen #separator {
        width: 100%;
        height: 1;
        padding: 0 2;
    }
    SurfScreen #bottom-row {
        height: auto;
        margin: 0 0 1 0;
    }
    SurfScreen SurfMarket {
        width: 7fr;
        height: auto;
        padding: 0 1;
    }
    SurfScreen SurfNft {
        width: 6fr;
        height: auto;
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
        #: Last payload the title bar was built from, kept so a resize can
        #: rebuild the line with (or without) the row marker at no cost and
        #: without a refetch. ``None`` until the first payload lands, which
        #: is also the degraded-manager state -- see ``_render_title``.
        self._title_data: dict | None = None

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(INITIAL_TITLE, id="title-bar")

        with Horizontal(id="hero-row"):
            yield SurfHero()

        with Horizontal(id="middle-row"):
            yield SurfFeed()
            # The right rail: the six detectors on top, the dev wallets'
            # transactions underneath. Both are permanently visible -- the
            # activity panel used to live in the feed's slot behind a ``c``
            # swap and was composed hidden.
            with Vertical(id="surf-right-rail"):
                yield SurfSignals()
                yield SurfDevActivity()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield SurfMarket()
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
            # No set_active_view: no slot on this screen has two views, so a
            # `view:` word on the shared bar would name something that does
            # not exist.
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def on_resize(self, _event=None) -> None:
        """Keep the row marker honest when the terminal changes height.

        Deferred to after the next refresh: the ``Resize`` message arrives
        before the rail has been re-laid-out, so reading its scroll state
        here would answer for the *previous* height and the marker would
        lag one resize behind -- lit on a terminal that now fits, dark on
        one that no longer does. Both are worse than no marker.
        """
        self.call_after_refresh(self._render_title)

    def _rail_is_cut(self) -> bool:
        """Does the right rail hold more than this height can show?

        ``show_vertical_scrollbar`` is the rail's own answer to that question
        and is what the layout already turns the loss into; asking it rather
        than re-deriving the arithmetic keeps the marker and the scrollbar
        from ever disagreeing.
        """
        try:
            return bool(self.query_one("#surf-right-rail").show_vertical_scrollbar)
        except Exception:  # noqa: BLE001 -- not composed yet, or torn down
            return False

    def _render_title(self) -> None:
        """(Re)compose the title bar from the last payload plus the marker."""
        cut = self._rail_is_cut()
        if self._title_data is None:
            # No payload yet -- or the manager raised and there never will
            # be one. INITIAL_TITLE carries no version tail, so the marker
            # simply goes on the end.
            line = INITIAL_TITLE + (f" · [yellow]{TALLER_HINT}[/]" if cut else "")
        else:
            line = _title_line(self._title_data, row_hint=cut)
        try:
            self.query_one("#title-bar", Static).update(line)
        except Exception as exc:  # noqa: BLE001 -- a title must never crash
            logger.debug("Failed to update title bar: %s", exc)

    # ------------------------------------------------------------------
    # Refresh flow
    # ------------------------------------------------------------------

    async def _do_refresh(self) -> None:
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            # Belt and braces: WP4's SurfManager.fetch_and_compute() never
            # raises -- it guarantees the full SURF_KEYS dict with None
            # values under every failure combination. This branch covers a
            # mis-wired manager or a future manager edit that breaks that
            # guarantee, not the specified outage path (see
            # test_screen_survives_all_none_payload for the real one).
            logger.debug("surf refresh failed: %s", exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=MANAGER_FAILURE_SECONDS,
                    error_count=getattr(self._data_manager, "_error_count", 0),
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        if not isinstance(data, dict):  # defensive: a broken manager contract
            logger.debug("surf refresh returned %r, not a dict", type(data))
            return

        # Title bar. The payload is kept so a later resize can re-compose
        # this same line with or without the row marker, without refetching.
        self._title_data = data
        self._render_title()

        # Hero (the full-width top row)
        try:
            self.query_one(SurfHero).update_data(
                hook_status=data.get("hook_status"),
                lp_liquidity=data.get("lp_liquidity"),
                lp_imd=data.get("lp_imd"),
                lp_weth=data.get("lp_weth"),
                lp_owner_ok=data.get("lp_owner_ok"),
                gate_open=data.get("gate_open"),
                identities_written=data.get("identities_written"),
                imd_supply=data.get("imd_supply"),
                imd_burned_cum=data.get("imd_burned_cum"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfHero: %s", exc)

        # Signals (right rail, top) -- the six detectors
        try:
            self.query_one(SurfSignals).update_data(
                sig_post_state=data.get("sig_post_state"),
                sig_post_detail=data.get("sig_post_detail"),
                sig_post_age_s=data.get("sig_post_age_s"),
                sig_lp_state=data.get("sig_lp_state"),
                sig_lp_detail=data.get("sig_lp_detail"),
                sig_lp_age_s=data.get("sig_lp_age_s"),
                sig_gate_state=data.get("sig_gate_state"),
                sig_gate_detail=data.get("sig_gate_detail"),
                sig_gate_age_s=data.get("sig_gate_age_s"),
                sig_deploy_state=data.get("sig_deploy_state"),
                sig_deploy_detail=data.get("sig_deploy_detail"),
                sig_deploy_age_s=data.get("sig_deploy_age_s"),
                sig_bridge_state=data.get("sig_bridge_state"),
                sig_bridge_detail=data.get("sig_bridge_detail"),
                sig_bridge_age_s=data.get("sig_bridge_age_s"),
                sig_burn_state=data.get("sig_burn_state"),
                sig_burn_detail=data.get("sig_burn_detail"),
                sig_burn_age_s=data.get("sig_burn_age_s"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfSignals: %s", exc)

        # Announce feed (middle row, left)
        try:
            self.query_one(SurfFeed).update_data(
                feed_items=data.get("feed_items"),
                feed_nonce=data.get("feed_nonce"),
                feed_last_post_age_s=data.get("feed_last_post_age_s"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfFeed: %s", exc)

        # Dev activity (middle row, right rail, under the signals)
        try:
            self.query_one(SurfDevActivity).update_data(
                dev_activity=data.get("dev_activity"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfDevActivity: %s", exc)

        # Market (bottom row, left)
        try:
            self.query_one(SurfMarket).update_data(
                imd_price_usd=data.get("imd_price_usd"),
                imd_change_24h_pct=data.get("imd_change_24h_pct"),
                imd_vol_24h_usd=data.get("imd_vol_24h_usd"),
                pool_liquidity_usd=data.get("pool_liquidity_usd"),
                fp_price_usd=data.get("fp_price_usd"),
                parity_pct=data.get("parity_pct"),
                supply_series=data.get("supply_series"),
                price_series=data.get("price_series"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfMarket: %s", exc)

        # NFT (bottom row, right)
        try:
            self.query_one(SurfNft).update_data(
                nft_holders=data.get("nft_holders"),
                nft_transfers_24h=data.get("nft_transfers_24h"),
                nft_dev_holdings=data.get("nft_dev_holdings"),
                nft_written=data.get("nft_written"),
                nft_last_sales=data.get("nft_last_sales"),
                nft_floor=data.get("nft_floor"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfNft: %s", exc)

        # Status bar. A refresh that reaches this line just fetched, so the
        # staleness is honestly 0 without consulting any clock; ``as_of`` is
        # the *payload's* fetch instant and stays inside the widgets' strings.
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=0.0,
                error_count=int(_num(getattr(self._data_manager, "_error_count", 0))),
                poll_interval=self._poll_interval,
            )
        except Exception as exc:
            logger.debug("Failed to update StatusBar: %s", exc)
