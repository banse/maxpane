"""CuratorScreen -- THE LIST, the WhitelistCurator survival watch, as a Screen.

Layout (the canonical slot grid, ``screens/talismans.py`` lines 62-84 with the
FWA ``c`` swap grafted onto the bottom-right slot)::

    #title-bar     THE LIST · hour N · GRACE/JUDGED/SETTLED · as of HH:MM
                   [· ⚠ logs, state] · vX.Y.Z
    #hero-row      CuratorHero (full width, 3 boxes + the EOA subtitle)   auto
    #middle-row    CuratorLeaderboard (3fr) | #curator-right-rail (5fr)     1fr
                                            |   CuratorSparklines
                                            |   CuratorSignals
    #separator
    #bottom-row    CuratorActivity (5fr) | CuratorClosestCalls (3fr)       auto
                                         | CuratorClusters (3fr, hidden)
                                           -- one or the other, key ``c``
    StatusBar

Five things here are deliberate rather than incidental.

1. **The screen is clock-free.**  Every time-derived string -- the grace
   countdown, the hour clock, the whale's age, ``lived 1 d 4 h`` -- arrives
   already computed in the payload, because ``analytics/curator_signals``
   takes ``now_ts`` as an argument and this module takes nothing.  That is why
   the 2026-08-17T00:03:22Z capture replays forever, and why
   ``test_the_screen_reads_no_clock_of_its_own`` can pin it with a source
   scan.

2. **``c`` swaps CLOSEST CALLS and FAN-OUT PATTERNS in the bottom-right slot**,
   the affordance FWA, TTT and Talismans use for two mutually exclusive tables.
   The default is *phase-aware*: CLUSTERS while the game is in grace (or while
   the phase is unknown), CLOSEST CALLS once an hour has actually been judged.
   A CLOSEST CALLS panel opened during grace shows ``no judged hours yet`` for
   the dashboard's entire first day; the clusters table has data from the first
   deposit.  The default stops applying the moment the reader presses ``c``
   (:attr:`CuratorScreen._user_chose_view`) -- a panel that snaps back while
   you are reading it is worse than a suboptimal default.

   Both tables stay mounted and both are dispatched to on every refresh, so
   toggling is a visibility flip with no refetch and no blank first frame.

3. **Every widget update is individually guarded.**  One widget raising must
   never cost the other six their refresh, so each dispatch is its own
   ``try``/``except``.  A failure of the *manager* is different in kind:
   nothing can be trusted, so only the ``StatusBar`` is touched
   (``last_updated_seconds_ago=999``) and the previous frame is left standing
   rather than half-overwritten.  Note that this is **not** the documented
   outage path: ``CuratorManager.fetch_and_compute`` never raises and returns
   the full contract with every value ``None`` instead
   (``test_no_exception_escapes_when_every_call_raises``).  The ``except`` here
   models a mis-wired manager, not a dead RPC.

4. **Degradation reaches the title bar**, behind the house warning glyph, with
   the failing groups named verbatim -- the shared ``StatusBar`` exposes only
   ``last_updated_seconds_ago`` / ``error_count`` / ``poll_interval`` and has no
   ``set_degraded()``.  Leaving it to the widgets alone would make the reader
   work out *which* panels went quiet from the panels themselves.

5. **A settled contract renders an archive, not a fault** (PRD §11).  The
   phase word stays ``SETTLED`` through a total outage -- the settlement latch
   lives in the manager and beats the live read -- and what moves instead is
   the ``as of HH:MM`` marker.  Nothing on this screen turns ``SETTLED`` into
   an error state, and the title bar carries no ``ERROR`` / ``no data`` copy
   for it.

Minimum terminal width: 138 columns
-----------------------------------

Measured against composited output over **three phases x two ``c`` views**,
column by column, not estimated (:data:`CURATOR_FULL_LAYOUT_COLUMNS`).  The
last panel asking for a column at 137 is ``CuratorSignals``, the seven-row
rail, and it is the panel this layout's seams were cut around --
``tests/screens/test_curator_screen.py`` pins that fact with
``_panels_asking_for_width`` rather than leaving it to this paragraph, because
on the surf screen the same claim changed hands three times in prose with no
test that could contradict it.

**Both seams are measurements.**  ``#middle-row`` splits 3:5 and
``#bottom-row`` 5:3, and neither is the ratio the plan sketched (3:2 and 1:1).
Measured on this screen, in **content** columns, the four panels that can bind
need ``CuratorLeaderboard`` 48, ``CuratorSignals`` 84, ``CuratorActivity`` 77
and ``CuratorClusters`` 45; adding each slot's own ``padding: 0 1`` -- and the
rail's reserved scrollbar gutter -- makes the arithmetic floors 137 for the
middle row and 126 for the bottom one, and only a seam near each pair's own
ratio collects them.  The sketched 3:2 middle seam would have handed the rail
0.40 W against the 0.63 it needs -- past **180** columns, with the YOU row
silently amputating its ``next ≥`` tail the whole way down.  A 1:1 bottom row
costs the activity feed its full line until 158.

The middle seam was re-swept ratio by ratio -- and swept **again** when the
gutter was reserved, because every one of these numbers is a column wider with
it.  3:5 is **one column off optimum, on purpose**: 10:17, 7:12, 13:22 and
17:29 all reach 137 while 3:5 reaches 138, 4:7 also costs 138, 5:8 costs 140,
1:2 costs 150 and 1:1 costs 173.  One column buys nothing a reader sees -- the
app-wide number is FWA's 143 either way -- and it is not worth an odd seam.
Re-sweep before re-seaming, and only when one of those four panel needs moves.

143 clears every layout here with 5 columns to spare, so
``__main__.FULL_LAYOUT_COLUMNS`` does not move: FWA's 143 stays the binder.
Below 138 nothing clips dark -- each panel names the columns it shed with a
``‹ widen`` marker in its own title, and the marker is the point.  It is never
silenced by raising a constant.

**138, not 137, and the extra column is the rail's scrollbar gutter.**  The
first pin here was 137, swept at one terminal height (48 rows) -- and the
width of this layout was a function of the *height* it was measured at.
``#curator-right-rail`` scrolls, its content is a constant 14 rows, and below
42 rows the scrollbar engaged and took a column off ``CuratorSignals``, the
binding panel: 137 cleared on a 48-row terminal and lit ``‹ widen`` on a
40-row one.  The gutter is now **reserved** (``scrollbar-gutter: stable``), so
the rail's inner width no longer moves with the terminal's height and the
number is one column larger at *every* height rather than right at one of
them.  ``test_the_measured_width_holds_at_a_short_terminal_too`` sweeps both a
tall and a short terminal, so the constant can never again be calibrated
against one generous window.

Minimum terminal height, and how the loss is advertised
-------------------------------------------------------

The rail needs **14 rows** -- a four-row sparkline panel, the one-row margin
under it, and a nine-row signal panel (title, spacer, seven detector rows) --
and gets them from a 42-row terminal.  Below that it scrolls, and scrolling
alone names nothing: a one-cell scrollbar in a reserved gutter says which
*panel* is short in neither words nor rows, and the rows it hides go from the
bottom -- YOU first, then FORCED ETH, then FARM.  So the title bar advertises
it with :data:`TALLER_HINT`, the height counterpart of a widget's
``‹ widen``, exactly as ``screens/surf.py`` does for the same rail construct.
The marker is driven off the rail's own ``show_vertical_scrollbar`` rather
than re-derived arithmetic, so the scrollbar and the marker can never
disagree, and it is re-rendered from ``on_resize`` (deferred with
``call_after_refresh``, because the ``Resize`` message arrives before the rail
has been re-laid-out and reading it early answers for the previous height).
``test_the_taller_hint_lights_exactly_when_the_rail_scrolls`` pins the row it
lights at in both directions.

**``CuratorSignals`` needs 84 content columns here while
``widgets/curator/signals.SIGNALS_FULL_WIDTH`` publishes 82.**  Not a
contradiction and not a defect: that number is data-dependent (it is the YOU
row's, and the YOU row's width is a function of the reader's own credit), and
this screen measures it against the *widest real wallet in the capture* --
rank 1, ``490.90 credit`` / ``next ≥ 491.00 ETH``, which prints two columns
wider than the four-figure wallet WP4 measured.  Reported to WP4 as a
measurement note, not as a change request.

The screen is written against the frozen ``CURATOR_KEYS`` contract, not against
``CuratorManager``'s internals: any object with an awaitable
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
from maxpane_dashboard.data.curator_models import PHASES
from maxpane_dashboard.screens.refresh_guard import RefreshGuard
from maxpane_dashboard.widgets.curator import (
    CuratorActivity,
    CuratorClosestCalls,
    CuratorClusters,
    CuratorHero,
    CuratorLeaderboard,
    CuratorSignals,
    CuratorSparklines,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from maxpane_dashboard.data.curator_manager import CuratorManager

logger = logging.getLogger(__name__)

_EMDASH = "—"

#: Shown until the first payload lands.
INITIAL_TITLE = "THE LIST · WhitelistCurator · Ethereum Mainnet"

#: Sentinel staleness pushed to the StatusBar when the manager itself failed.
MANAGER_FAILURE_SECONDS = 999

#: The height counterpart of a widget's ``‹ widen``: the right rail holds more
#: rows than this terminal can show, so its last detector rows -- YOU first --
#: are only reachable by scrolling.
#:
#: The rail's content is a constant 14 rows and it gets them from a **42**-row
#: terminal; at 41 the scrollbar engages and YOU goes below the fold.  A
#: one-cell scrollbar in a gutter names neither the panel nor the loss, which
#: is why ``screens/surf.py`` grew the same marker for the same rail construct
#: -- and at very short heights Textual paints that scrollbar outside the
#: rail's own rectangle, so it is not even reliably *visible*.
#:
#: ``_title_line`` puts it ahead of the degraded list and the version tail:
#: ``#title-bar`` is one row that wraps out of existence rather than
#: ellipsising, a degraded group is mirrored inside each panel's own
#: unavailable state, the version is mirrored by the StatusBar three rows
#: down, and **nothing anywhere else says a row went off the bottom of the
#: rail**.  Of the three tail fields it is the one that has to survive.
TALLER_HINT = "‹ taller"

#: The two occupants of the bottom-right slot, as :attr:`CuratorScreen._active_view`
#: spells them.  Not the widget class names: the StatusBar renders this word.
VIEW_CLUSTERS = "clusters"
VIEW_CLOSEST = "closest"

#: ids for the swap pair, so ``minimal.tcss`` (WP7) can place them by id and the
#: toggle can query them without importing the classes twice.
CLOSEST_ID = "curator-closest-calls"
CLUSTERS_ID = "curator-clusters"

#: The full-layout width, **measured** by rendering this screen column by
#: column in all three phases and both ``c`` views -- never estimated.  See the
#: module docstring for which panel is the last one asking for a column, and
#: ``tests/screens/test_curator_screen.py`` for the sweep that produced it.
#:
#: It stays at or under ``__main__.FULL_LAYOUT_COLUMNS`` (FWA's 143) by
#: *shedding columns with a marker*, never by raising the app-wide constant;
#: ``test_curator_fits_inside_the_documented_app_width`` is the tripwire.
#:
#: **Swept at two terminal heights, not one.**  This was 137 for as long as it
#: was measured only on a 48-row terminal: the rail's scrollbar used to eat a
#: column off the binding panel below 42 rows, so the pinned number was true
#: for a tall window and false for a short one.  The gutter is reserved now
#: (see ``DEFAULT_CSS`` and the module docstring) and the sweep carries the
#: height dimension with it.
CURATOR_FULL_LAYOUT_COLUMNS = 138

#: The three flat-dict keys the screen consumes itself and never dispatches to
#: a widget.  Exactly ``curator_signals.MANAGER_OWNED_KEYS``; the agreement is
#: asserted rather than assumed.  ``phase`` and ``settled`` are deliberately
#: *not* here -- the title bar reads them **and** the hero and the rail are
#: dispatched them, which is why the dispatch test asserts containment plus
#: totality instead of a partition.
META_KEYS: tuple[str, ...] = ("degraded", "as_of_hhmm", "as_of")

#: The keyword sets each widget's ``update_data`` takes, hand-typed rather than
#: introspected.  Deriving them from ``inspect.signature`` would make
#: ``test_the_dispatch_map_matches_the_widgets_own_signatures`` compare a
#: constant with itself and it could never fail again -- the redundancy-plus-
#: agreement-test pattern CLAUDE.md documents for ``_GAME_CYCLE``.
#:
#: ``you_address`` is the one entry that is not a ``CURATOR_KEYS`` key: the
#: screen supplies the configured wallet so the reader's own row can be
#: emphasised, and it is the only screen-supplied kwarg on this dashboard.
#: ``hourly_threshold_eth`` and ``first_judged_hour`` are **not** screen-derived
#: -- they are read live off the ``once`` tier and dispatched like any other
#: key, because ``ethNeededThisHour()`` answers 0 through all of grace and on
#: any already-safe judged hour, so ``hour_fed + hour_needed`` does not
#: reconstruct the threshold.
WIDGET_SIGNATURES: dict[str, tuple[str, ...]] = {
    "CuratorHero": (
        "phase", "current_hour", "grace_seconds_left", "grace_ends_utc",
        "hour_fed_eth", "hour_needed_eth", "hour_seconds_left",
        "hourly_threshold_eth", "settled_hour", "settled_at_ts",
        "settled_observed_at", "lived_desc", "early_multiplier_x",
        "points_per_eth_now", "survival_streak_hours",
        "closest_call_margin_eth", "closest_call_hour", "contributors_total",
        "deposits_total", "volume_routed_eth", "top_points",
    ),
    "CuratorLeaderboard": ("leaderboard_rows", "you_address"),
    "CuratorSparklines": (
        "volume_series", "contributors_series", "hourly_threshold_eth",
    ),
    "CuratorSignals": (
        "phase", "settled", "settled_hour", "sig_settled_state",
        "sig_at_risk_state", "first_judged_hour", "hour_needed_eth",
        "hour_seconds_left", "last_saved_hour", "last_saved_wallet",
        "last_saved_age_s", "whale_amount_eth", "whale_wallet", "whale_age_s",
        "clusters_count", "flagged_points_share_pct", "forced_eth",
        "rescued_total_eth", "you_rank", "you_points", "you_credit_eth",
        "you_required_next_eth", "you_marginal_points",
    ),
    "CuratorActivity": ("activity_rows",),
    "CuratorClosestCalls": (
        "closest_call_rows", "first_judged_hour", "grace_ends_utc",
    ),
    "CuratorClusters": (
        "cluster_rows", "clusters_count", "flagged_points_share_pct",
    ),
}

#: The one kwarg above that the manager does not produce.
SCREEN_SUPPLIED: frozenset[str] = frozenset({"you_address"})


# -- format helpers ----------------------------------------------------


def _num(value, default: float = 0.0) -> float:
    """Coerce to ``float``, falling back to ``default`` -- never raise.

    Exists because an all-``None`` payload is a supported state and
    ``StatusBar.update_data`` does arithmetic on its arguments.
    """
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
    """``2,291`` -- or an em dash.  A failed read is never a zero."""
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _EMDASH


def _phase_word(phase) -> str:
    """``GRACE`` / ``JUDGED`` / ``SETTLED``, or ``phase —`` for unknown.

    ``None`` is what a failed ``isSettled()`` read produces and it is **not**
    grace: naming a phase we could not read would be a guess about whether the
    game is still alive, printed in the one place a reader looks first.

    The unknown form carries the word ``phase`` because a bare em dash between
    two other ``·``-separated fields says nothing about *what* is unknown --
    and this row already carries one em dash for the hour.
    """
    text = str(phase or "").strip().lower()
    return text.upper() if text in PHASES else f"phase {_EMDASH}"


def _fmt_degraded(sources) -> str:
    """`` · ⚠ logs, state`` -- or an empty string when every source answered.

    The glyph rides in front of the list rather than the word ``degraded: ``
    (nine columns on a row that cannot ellipsise), and the groups render
    verbatim because they are ``CURATOR_DEGRADED_GROUPS``.
    """
    if not sources:
        return ""
    try:
        names = [str(s).strip() for s in sources if str(s).strip()]
    except TypeError:
        return ""
    if not names:
        return ""
    return " · ⚠ " + ", ".join(names)


def _title_line(data: dict, row_hint: bool = False) -> str:
    """Compose the meta row (PRD §4).

    ``THE LIST · hour N · PHASE · as of HH:MM [· ‹ taller] [· ⚠ groups] ·
    vX.Y.Z``

    Ordered by what must survive a narrow terminal, because ``#title-bar`` is
    a ``height: 1`` ``Static`` that **wraps out of existence** rather than
    ellipsising: everything past the first row reaches no pixel at all, with
    no ``…`` and no trace.  So the warning precedes the version tail, and the
    version tail -- the one field on this row that is also rendered by the
    StatusBar three rows down -- is the first thing lost.

    ``row_hint`` (:data:`TALLER_HINT`) comes ahead of *both*: it is the only
    advertisement on this screen with no second home, while every degraded
    group is mirrored by its own panel's unavailable state.  It is written in
    plain text rather than surf's ``[yellow]`` markup because nothing else on
    this line carries markup, and a plain line is one a test can compare
    against composited output character for character.

    Nothing here is an alarm about settlement.  A settled contract is the
    product's terminal state, so the phase word simply reads ``SETTLED`` and
    the freshness marker is what moves under an outage; ``ERROR`` / ``no data``
    copy would turn an archive into a fault (PRD §11).
    """
    line = (
        f"THE LIST · hour {_fmt_int(data.get('current_hour'))} · "
        f"{_phase_word(data.get('phase'))}"
    )

    as_of = data.get("as_of_hhmm")
    line += f" · as of {as_of}" if as_of else f" · as of {_EMDASH}"

    if row_hint:
        line += f" · {TALLER_HINT}"

    line += _fmt_degraded(data.get("degraded"))
    line += f" · v{__version__}"
    return line


def _default_view(phase) -> str:
    """Which table owns the bottom-right slot before the reader says otherwise.

    CLUSTERS until an hour has actually been judged, then CLOSEST CALLS.  An
    unknown phase picks CLUSTERS too: it is the one of the two that has rows
    from the first deposit onwards, so an unknown phase costs the reader a
    populated table rather than an empty one.
    """
    text = str(phase or "").strip().lower()
    return VIEW_CLOSEST if text in ("judged", "settled") else VIEW_CLUSTERS


class CuratorScreen(RefreshGuard, Screen):
    """THE LIST -- WhitelistCurator survival watch (Ethereum mainnet).

    ``BINDINGS`` is ``r`` plus ``c``; the latter swaps CLOSEST CALLS and
    FAN-OUT PATTERNS in the bottom-right slot (see the module docstring).
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("c", "toggle_view", "Calls/Patterns", show=True),
    ]

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "curator-refresh"

    # Structural fallback only.  WP7 restates this block in
    # ``themes/minimal.tcss`` (one owner) the way the FWA and surf blocks are
    # restated; app-stylesheet rules then beat ``DEFAULT_CSS``.  It lives here
    # so the screen is reviewable and correctly proportioned on its own, under
    # any theme that has no curator block.  The two copies must stay in
    # agreement -- edit both or neither.
    #
    # `#hero-row` is `height: auto` and carries NO vertical padding.
    # ``CuratorHero`` is a height-8 widget: three height-7 boxes over the
    # one-row EOA subtitle.  A single row of vertical padding here clips the
    # subtitle -- or the boxes' bottom border -- off the screen, which is the
    # FWA hero coverage-badge bug exactly.
    #
    # `#curator-right-rail` carries no vertical padding for the same reason
    # one step further down: the rail holds a **seven**-row signal panel whose
    # last row is YOU, and a fixed-height column loses its last row first.
    # It scrolls (`overflow-y: auto`) as the short-terminal guard -- scrolling
    # is the affordance, nothing is unreachable -- and the *advertisement* is
    # `TALLER_HINT` on the title bar, because a one-cell scrollbar names
    # nothing and Textual paints it outside the rail's rectangle at very short
    # heights.
    #
    # `scrollbar-gutter: stable` is load-bearing, not cosmetic. Without it the
    # scrollbar takes its column out of `CuratorSignals` -- the panel that
    # binds the full-layout width -- only on terminals under 42 rows, so this
    # layout's *width* requirement moved with its *height* and the pinned
    # number was true at 48 rows and one column short at 40. Reserving the
    # gutter spends that column at every height instead of at one of them.
    #
    # The two seams are measured, not chosen.  `#middle-row` is 3:5 because
    # ``CuratorLeaderboard`` needs 48 content columns and ``CuratorSignals``
    # needs 84 against the widest real wallet in the capture; with each slot's
    # own `padding: 0 1` and the rail's reserved gutter that sums to 137, and
    # only a seam near 50:87 collects it.  `#bottom-row` is 5:3 because ``CuratorActivity`` needs 77 and the
    # wider of the two swap tables (``CuratorClusters``) needs 45; floor 126,
    # comfortably inside the middle row's.  The column-by-column sweep and the
    # seam-by-seam sweep behind both are in
    # ``tests/screens/test_curator_screen.py``; re-sweep before re-seaming, and
    # only when one of those four panel needs moves.
    #
    # `#middle-row` and `#bottom-row` are BOTH `1fr`, and the second one is a
    # WP7 correction to this comment rather than a preference.  Every
    # measurement in this file was taken under `themes/minimal.tcss`, whose
    # shared `#bottom-row { height: 1fr }` (line 126) outranks DEFAULT_CSS the
    # way an app stylesheet always does -- so `auto` here was never what
    # rendered, and restating `auto` in the curator block made it render for
    # the first time: `CuratorActivity` is `height: auto` over a full deposit
    # window, so the row grew to 47 rows, starved `#middle-row` to 1, and
    # SIGNALS and YOU stopped reaching the compositor entirely (a screen
    # scrollbar then ate two columns and the width sweep "passed" at 136 with
    # the whole rail gone).  `1fr` in both copies is the geometry that was
    # actually measured; the two slots inside each row stay `auto` and size to
    # their own content.
    DEFAULT_CSS = """
    CuratorScreen #title-bar {
        width: 100%;
        height: 1;
        text-align: center;
        content-align: center middle;
    }
    CuratorScreen #hero-row {
        height: auto;
        margin: 1 0 0 0;
    }
    CuratorScreen CuratorHero {
        width: 1fr;
        padding: 0 1;
    }
    CuratorScreen #middle-row {
        height: 1fr;
        margin: 1 0 0 0;
    }
    CuratorScreen CuratorLeaderboard {
        width: 3fr;
        padding: 0 1;
    }
    CuratorScreen #curator-right-rail {
        width: 5fr;
        height: 1fr;
        overflow-y: auto;
        scrollbar-gutter: stable;
        scrollbar-size: 1 1;
    }
    CuratorScreen CuratorSparklines {
        width: 1fr;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    CuratorScreen CuratorSignals {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    CuratorScreen #separator {
        width: 100%;
        height: 1;
        padding: 0 2;
    }
    CuratorScreen #bottom-row {
        height: 1fr;
        margin: 0 0 1 0;
    }
    CuratorScreen CuratorActivity {
        width: 5fr;
        height: auto;
        padding: 0 1;
    }
    CuratorScreen CuratorClosestCalls {
        width: 3fr;
        height: auto;
        padding: 0 1;
    }
    CuratorScreen CuratorClusters {
        width: 3fr;
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        data_manager: "CuratorManager",
        poll_interval: int = 30,
        name: str = "curator",
        wallet: str | None = None,
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None
        #: The wallet the leaderboard emphasises.  Passed in by the app from
        #: ``--wallet`` / ``MAXPANE_WALLET``; the screen never reads the
        #: environment itself, so two screens in one process can watch two
        #: wallets and a test drives it without patching anything.
        self._wallet = wallet or None
        #: Which table owns the bottom-right slot: ``VIEW_CLUSTERS`` or
        #: ``VIEW_CLOSEST``.  Starts on the unknown-phase default, which is
        #: also the grace default, so the first frame is never an empty table.
        self._active_view: str = _default_view(None)
        #: True once the reader has pressed ``c``.  From then on the
        #: phase-aware default stops applying: a panel that snaps back while
        #: you are reading it is worse than a suboptimal default.
        self._user_chose_view: bool = False
        #: The last payload the title bar was composed from, kept so
        #: :meth:`_render_title` can re-compose the same line with a different
        #: ``‹ taller`` state when only the terminal's height changed.
        #: ``None`` until the first refresh lands.
        self._title_data: dict | None = None

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(INITIAL_TITLE, id="title-bar")

        with Horizontal(id="hero-row"):
            yield CuratorHero()

        with Horizontal(id="middle-row"):
            yield CuratorLeaderboard()
            with Vertical(id="curator-right-rail"):
                yield CuratorSparklines()
                yield CuratorSignals()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield CuratorActivity()
            # Both swap tables live in the layout and both are dispatched to on
            # every refresh; one is hidden at a time.  Creating one on demand
            # would leave it blank for a beat after the first ``c``, which
            # reads as a bug.
            yield CuratorClosestCalls(id=CLOSEST_ID)
            yield CuratorClusters(id=CLUSTERS_ID)

        yield StatusBar()

    def on_mount(self) -> None:
        self._show_active_view()

    # ------------------------------------------------------------------
    # Actions / bindings
    # ------------------------------------------------------------------

    def _show_active_view(self) -> None:
        """Apply :attr:`_active_view` to the two swap widgets' visibility."""
        showing_closest = self._active_view == VIEW_CLOSEST
        try:
            self.query_one(f"#{CLOSEST_ID}").display = showing_closest
            self.query_one(f"#{CLUSTERS_ID}").display = not showing_closest
        except Exception as exc:  # noqa: BLE001 -- a toggle must never crash
            logger.debug("Curator view toggle failed: %s", exc)
        try:
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass

    def action_toggle_view(self) -> None:
        """Swap CLOSEST CALLS and FAN-OUT PATTERNS in the bottom-right slot.

        Also the moment the phase-aware default stops applying: after this the
        choice is the reader's, across every later phase change.
        """
        self._active_view = (
            VIEW_CLUSTERS if self._active_view == VIEW_CLOSEST else VIEW_CLOSEST
        )
        self._user_chose_view = True
        self._show_active_view()

    def _apply_phase_default(self, phase) -> None:
        """Move the slot to the phase's default -- unless the reader has chosen.

        Called from ``_do_refresh`` only, and gated on
        :attr:`_user_chose_view`; running it unconditionally is what makes a
        panel snap back under the reader's hands when the game crosses out of
        grace.
        """
        if self._user_chose_view:
            return
        wanted = _default_view(phase)
        if wanted != self._active_view:
            self._active_view = wanted
        self._show_active_view()

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
            self.query_one(StatusBar).set_game_name("curator")
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def on_resize(self, _event=None) -> None:
        """Keep the ``‹ taller`` marker honest when the terminal is resized.

        Deferred to after the next refresh: the ``Resize`` message arrives
        *before* the rail has been re-laid-out, so reading its scroll state
        here would answer for the previous height and the marker would lag one
        resize behind -- lit on a terminal that now fits, dark on one that no
        longer does.  Both are worse than no marker at all.
        """
        self.call_after_refresh(self._render_title)

    def _rail_is_cut(self) -> bool:
        """Does the right rail hold more rows than this height can show?

        ``show_vertical_scrollbar`` is the rail's own answer, and it is what
        the layout already turns the loss into; asking it rather than
        re-deriving the arithmetic keeps the marker and the scrollbar from
        ever disagreeing.
        """
        try:
            return bool(
                self.query_one("#curator-right-rail").show_vertical_scrollbar
            )
        except Exception:  # noqa: BLE001 -- not composed yet, or torn down
            return False

    def _render_title(self) -> None:
        """(Re)compose the title bar from the last payload plus the marker."""
        cut = self._rail_is_cut()
        if self._title_data is None:
            # No payload yet -- or the manager raised and there never will be
            # one.  The marker simply goes on the end here; there is no
            # degraded list and no version tail on this line for it to have to
            # precede.
            line = INITIAL_TITLE + (f" · {TALLER_HINT}" if cut else "")
        else:
            line = _title_line(self._title_data, row_hint=cut)
        try:
            self.query_one("#title-bar", Static).update(line)
        except Exception as exc:  # noqa: BLE001 -- a title must never crash
            logger.debug("Failed to update title bar: %s", exc)

    # ------------------------------------------------------------------
    # Refresh flow
    # ------------------------------------------------------------------

    def _dispatch(self, widget_cls, data: dict) -> None:
        """Hand one widget exactly the kwargs :data:`WIDGET_SIGNATURES` names.

        One ``try``/``except`` per widget: a malformed value costs its own
        panel a frame, never the other six.  ``data.get`` rather than
        ``data[...]`` so a manager that has not implemented a key yet degrades
        one field instead of the whole screen -- the widgets already render an
        explicit unavailable state for ``None``.
        """
        name = widget_cls.__name__
        kwargs = {
            key: (self._wallet if key == "you_address" else data.get(key))
            for key in WIDGET_SIGNATURES[name]
        }
        try:
            self.query_one(widget_cls).update_data(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to update %s: %s", name, exc)

    async def _do_refresh(self) -> None:
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            # NOT the documented outage path -- see the module docstring.
            logger.debug("Curator refresh failed: %s", exc)
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
            logger.debug("Curator refresh returned %r, not a dict", type(data))
            return

        # Title bar.  Composed through ``_render_title`` so the payload and
        # the ``‹ taller`` marker are always read together: a refresh that
        # wrote the line itself would drop a marker a resize had just lit.
        self._title_data = data
        self._render_title()

        # The swap slot's phase-aware default, before the tables are filled so
        # the frame the reader sees is already the right one.
        try:
            self._apply_phase_default(data.get("phase"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to apply the phase default: %s", exc)

        for widget_cls in (
            CuratorHero,
            CuratorLeaderboard,
            CuratorSparklines,
            CuratorSignals,
            CuratorActivity,
            CuratorClosestCalls,
            CuratorClusters,
        ):
            self._dispatch(widget_cls, data)

        # Status bar.  ``last_updated_seconds_ago`` is the age of the *cycle*,
        # which has just completed -- the age of the *data* is the title bar's
        # ``as of HH:MM``, which the manager fills from its newest successful
        # read and which is what freezes under an outage.  The values are
        # coerced because an all-``None`` payload is a supported state and this
        # widget does arithmetic on them.
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=_num(
                    data.get("last_updated_seconds_ago"), 0.0
                ),
                error_count=int(
                    _num(getattr(self._data_manager, "_error_count", 0), 0)
                ),
                poll_interval=int(_num(self._poll_interval, 30)),
            )
        except Exception as exc:
            logger.debug("Failed to update StatusBar: %s", exc)
