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

import csv
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.screens.wallet_input import WalletInputScreen

from maxpane_dashboard import __version__
from maxpane_dashboard.data.curator_models import CURATOR_ROW_KEYS, PHASES
from maxpane_dashboard.screens.refresh_guard import RefreshGuard
from maxpane_dashboard.widgets.curator import (
    CuratorActivity,
    CuratorClosestCalls,
    CuratorWalletLadder,
    CuratorWalletNext,
    CuratorWalletStanding,
    CuratorWalletTarget,
    CuratorWalletAddress,
    CuratorWalletHero,
    CuratorCleanList,
    CuratorClusters,
    CuratorHero,
    CuratorLeaderboard,
    CuratorCleanedList,
    CuratorOperators,
    CuratorRawList,
    CuratorSegments,
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
#: Body ids use ids rather than classes because several views hold repeated
#: widget shapes and each visibility target must stay unambiguous.
DASHBOARD_BODY_ID = "curator-dashboard-body"
WALLET_BODY_ID = "curator-wallet-body"
#: The `f` view's body — OPERATORS over SEGMENTS over CLEANED LIST.
ANALYSIS_BODY_ID = "curator-analysis-body"
#: The `l` view's body -- THE RAW LIST beside THE CLEANED LIST.
LIST_BODY_ID = "curator-list-body"
#: The wallet body's own hero, which swaps with it.
WALLET_HERO_ID = "curator-wallet-hero"

#: The four modes: game, reader standing, linked-wallet analysis, and the two
#: complete record lists. A fifth spelling is a silent fallback arm.
#:
#: `analysis` and `list` keep the **dashboard** hero on screen: the doomsday
#: clock never leaves, so `_show_mode` hides it only for `wallet`.
MODE_DASHBOARD = "dashboard"
MODE_WALLET = "wallet"
MODE_ANALYSIS = "analysis"
MODE_LIST = "list"
MODES = (MODE_DASHBOARD, MODE_WALLET, MODE_ANALYSIS, MODE_LIST)

#: Where the `e` export lands, relative to the (injectable) home directory —
#: the cleaned list as JSON rows plus a CSV of the same rows.  A TUI cannot
#: hand a file to the reader, so it writes to disk and names the path.
CLEAN_LIST_BASENAME = "curator_clean_list"
LISTS_BASENAME = "curator_lists"

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
#:
#: **The 2026-08-18 `f` view did not move it.**  The analysis body's own
#: first-clean width is **137** at both sweep heights — one column inside
#: this pin — and its binding panel is ``CuratorOperators`` (the 82-column
#: evidence cell), pinned by
#: ``test_the_analysis_binding_panel_is_the_operators_table`` rather than by
#: this sentence.  The `y` view still clears at exactly 138 with the wallet
#: rail's gutter reserved, measured against a **clean-linkage** payload: a
#: *linked* reader's evidence line legitimately exceeds the rail's share and
#: lights ``‹ widen`` here at any width (the surf announce-feed precedent),
#: which is correct and must never be silenced by raising this constant.
#:
#: The `l` body's separate composited sweep clears every column at **141** and
#: advertises its shed NAME column at 140 and below. It therefore does not
#: alter this dashboard-layout pin and remains inside the app-wide 143.
CURATOR_FULL_LAYOUT_COLUMNS = 138

#: The three flat-dict keys the screen renders itself -- the title bar's
#: freshness and health markers.  Exactly ``curator_signals.MANAGER_OWNED_KEYS``.
#:
#: "Never dispatched to a widget" was true of all three until ``degraded``
#: also had to reach ``CuratorSignals``: two of its rows are ``None`` both when
#: the chain is quiet and when the logs pool is down, and only this key tells
#: those apart (see that widget's ``LOGS_GROUP``).  It is a *both*, not a move
#: -- the title bar still renders it -- and the totality test below is a
#: containment, so meta and dispatched may overlap.  ``as_of``/``as_of_hhmm``
#: reach no widget.  The agreement with the analytics layer is
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
        "whale_ens", "last_saved_ens",
        "phase", "settled", "settled_hour", "sig_settled_state",
        "sig_at_risk_state", "first_judged_hour", "hour_needed_eth",
        "hour_seconds_left", "last_saved_hour", "last_saved_wallet",
        "last_saved_age_s", "whale_amount_eth", "whale_wallet", "whale_age_s",
        "clusters_count", "flagged_points_share_pct", "forced_eth",
        "rescued_total_eth", "you_rank", "you_points", "you_credit_eth",
        "you_required_next_eth", "you_marginal_points",
        # The one META_KEYS entry a widget receives, and the only one it needs:
        # HOUR SAVED and WHALE are ``None`` both when the chain is quiet and
        # when the logs pool is down, so without this they rendered a green
        # ``none yet`` / ``none this hour`` off a refresh that could not look --
        # while FARM, fed by the same group, said ``-- unknown``.  FARM can tell
        # them apart because ``clusters_count == 0`` is representable and
        # "no whale" is not.  See ``widgets/curator/signals.LOGS_GROUP``.
        "degraded",
    ),
    "CuratorActivity": ("activity_rows",),
    "CuratorClosestCalls": (
        "closest_call_rows", "first_judged_hour", "grace_ends_utc",
    ),
    "CuratorClusters": (
        "cluster_rows", "clusters_count", "flagged_points_share_pct",
    ),
    # -- the `y` wallet view --------------------------------------------------
    "CuratorWalletHero": (
        "you_rank", "you_points", "you_credit_eth", "you_weight_share_pct",
        "you_required_next_eth", "you_marginal_points", "you_next_send_passes",
        "contributors_total",
    ),
    "CuratorWalletAddress": ("you_address", "you_ens"),
    "CuratorWalletLadder": ("you_ladder_rows", "you_address"),
    # The last four are the `f` build's additions (WP5's hand-off, pasted
    # verbatim): the linked line and the clean rank beside the raw one.
    "CuratorWalletStanding": (
        "you_rank", "you_points", "you_credit_eth", "you_weight_eth",
        "you_tx_count", "you_weight_share_pct", "you_first_hour",
        "you_joined_utc", "contributors_total",
        "you_linked_state", "you_linked_reasons",
        "you_linked_group_size", "you_clean_rank",
    ),
    "CuratorWalletNext": ("you_required_next_eth", "you_credit_eth"),
    "CuratorWalletTarget": (
        "you_marginal_points", "you_rank", "you_next_rank",
        "you_next_rank_needs_eth", "you_next_send_passes",
    ),
    # -- the `f` analysis view (WP0's routing table, ANALYSIS_KEY_ROUTING) ----
    # `flagged_points_share_pct` is REUSED (PRD §7): Tier A feeds the FARM
    # rail row from it today, and the OPERATORS summary renders the same
    # number — one key, two panels, never two keys for one quantity.
    # `clean_list_export_path` is deliberately NOT here (ruling R4): the
    # export receipt is screen-supplied through `mark_exported`, like
    # `mark_pending`, because it is a keypress's result and not manager data.
    "CuratorOperators": (
        "operator_rows", "operators_count", "flagged_points_share_pct",
        "analysis_as_of_hhmm",
    ),
    "CuratorSegments": ("segment_rows", "analysis_as_of_hhmm"),
    # `points_total` is the R14 amendment: the population total at the same
    # analysis snapshot, so the panel can render PRD §5.3's "total vs clean".
    "CuratorCleanList": (
        "clean_list_rows", "clean_points", "clean_contributors",
        "points_total", "you_clean_rank", "analysis_as_of_hhmm",
    ),
    # -- the `l` raw/clean record view ---------------------------------------
    "CuratorRawList": ("leaderboard_rows",),
    "CuratorCleanedList": ("clean_list_rows", "analysis_as_of_hhmm"),
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


def _atomic_write(
    directory: Path,
    writes: tuple[tuple[Path, Callable[[Path], None]], ...],
) -> None:
    """Write every same-directory temporary before replacing a destination."""
    directory.mkdir(parents=True, exist_ok=True)
    pending = tuple(
        (path, path.with_name(f"{path.name}.tmp"), writer)
        for path, writer in writes
    )
    try:
        for _path, temporary, writer in pending:
            writer(temporary)
        for path, temporary, _writer in pending:
            os.replace(temporary, path)
    except Exception:
        for _path, temporary, _writer in pending:
            try:
                temporary.unlink()
            except OSError:
                pass
        raise


def _write_clean_list(directory: Path, rows: list) -> Path:
    """Write ``rows`` as ``curator_clean_list.json`` + ``.csv`` in *directory*.

    The JSON is the ``clean_list_rows`` payload verbatim -- the shape the
    contract froze, so a consumer script reads the same rows the panel shows.
    An **empty list is a real record** (M1): the sweep ran and nobody
    survives it, and that is exactly the state a consumer most needs to see.
    The CSV's header is ``CURATOR_ROW_KEYS["clean_list_rows"]``, imported
    rather than retyped.  Returns the JSON path (the one the panel names).

    **Atomic against the files already on disk.**  Both files are written to
    temp names in the *same* directory and ``os.replace``d into place only
    once both writes completed, so a failed RE-export can never truncate a
    previously good export in place -- writing the real names directly is a
    corruption window exactly as wide as the write, and the panel's receipt
    would keep naming the mangled file as saved. On failure, temporary files
    are removed and no destination is ever truncated in place.
    """
    columns = CURATOR_ROW_KEYS["clean_list_rows"]
    json_path = directory / f"{CLEAN_LIST_BASENAME}.json"
    csv_path = directory / f"{CLEAN_LIST_BASENAME}.csv"

    def write_json(path: Path) -> None:
        path.write_text(json.dumps(rows, indent=1), encoding="utf-8")

    def write_csv(path: Path) -> None:
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=columns, extrasaction="ignore"
            )
            writer.writeheader()
            for row in rows:
                if isinstance(row, dict):
                    writer.writerow({key: row.get(key) for key in columns})

    _atomic_write(directory, ((json_path, write_json), (csv_path, write_csv)))
    return json_path


def _write_lists(directory: Path, raw: list, clean: list) -> Path:
    """Atomically write the raw and cleaned rows as one JSON record."""
    path = directory / f"{LISTS_BASENAME}.json"

    def write_json(temporary: Path) -> None:
        temporary.write_text(
            json.dumps({"raw": raw, "clean": clean}, indent=1),
            encoding="utf-8",
        )

    _atomic_write(directory, ((path, write_json),))
    return path


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

    Eight bindings: ``r`` refresh; ``c`` swaps CLOSEST CALLS and FAN-OUT
    PATTERNS in the bottom-right slot (see the module docstring); ``w`` sets
    the wallet; ``y`` swaps the body for the reader's own standing; ``f``
    swaps it for the linked-wallet analysis, with the doomsday clock left in
    place; ``l`` opens the raw/clean record lists; ``e`` exports inside ``f``
    or ``l``; ``esc`` backs out of a secondary view, one-way.
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("c", "toggle_view", "Calls/Patterns", show=True),
        Binding("w", "set_wallet", "Wallet", show=True),
        Binding("y", "toggle_mode", "You", show=True),
        Binding("f", "toggle_analysis", "Linked", show=True),
        Binding("l", "toggle_list", "Lists", show=True),
        # Only acts in MODE_ANALYSIS or MODE_LIST, so it remains a no-op on the
        # dashboard and wallet view -- the `esc` rule's shape.
        Binding("e", "export_clean_list", "Export", show=False),
        Binding("escape", "back_to_dashboard", "Back", show=False),
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
    /* The `y` view.  Both bodies claim the same `1fr` so the hero above them
       never moves on the toggle; the two facts panels are `auto` and size to
       their own lines.  Restated in minimal.tcss, and
       test_the_stylesheet_block_and_default_css_describe_one_layout compares
       the two copies rule by rule. */
    CuratorScreen #curator-dashboard-body {
        height: 1fr;
        width: 100%;
    }
    CuratorScreen #curator-wallet-body {
        height: 1fr;
        width: 100%;
    }
    /* `margin: 1 0 0 0` is `#middle-row`'s, so the blank line under the hero's
       EOA subtitle is the same on every body and their first titles sit on
       the same row. */
    CuratorScreen #wallet-top-row {
        height: 1fr;
        margin: 1 0 0 0;
    }
    CuratorScreen CuratorWalletHero {
        width: 100%;
        height: 8;
    }
    /* The rail scrolls below its measured minimum height (WALLET_MIN_HEIGHT
       in the screen suite) instead of dropping WHERE IT GETS YOU dark -- the
       FWA coverage-badge hazard on the reader's own panels -- and the
       `‹ taller` marker on the title bar is the advertisement, exactly as it
       is for the dashboard's own rail.  The gutter is reserved for the same
       reason as there: an unreserved one takes its column out of the rail's
       panels only on short terminals, which made the `y` view's *width*
       requirement a function of its *height*. */
    CuratorScreen #curator-wallet-rail {
        width: 2fr;
        height: 100%;
        overflow-y: auto;
        scrollbar-gutter: stable;
        scrollbar-size: 1 1;
    }
    CuratorScreen CuratorWalletLadder {
        width: 3fr;
        height: 100%;
        margin: 0 0 1 0;
        padding: 0 1;
    }
    /* In the rail: full width, sized to their own lines, one blank row between
       panels so the three do not read as one block. */
    CuratorScreen CuratorWalletAddress {
        width: 100%;
        height: auto;
        margin: 0 0 2 0;
        padding: 0 1;
    }
    CuratorScreen CuratorWalletStanding {
        width: 100%;
        height: auto;
        margin: 0 0 2 0;
        padding: 0 1;
    }
    CuratorScreen CuratorWalletNext {
        width: 100%;
        height: auto;
        margin: 0 0 2 0;
        padding: 0 1;
    }
    CuratorScreen CuratorWalletTarget {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    /* The `f` view.  Three full-width panels stacked -- measured (WP4.7):
       SEGMENTS' full tier alone needs 111 columns (a 33-column label beside
       a 56-column detail), so no two of these panels fit side by side inside
       the app-wide 143, and stacking is what lets every panel reach its full
       tier at the screen's own 138.  The body claims the same `1fr` as its
       two siblings so the hero -- which stays on screen in this mode --
       never moves on the toggle.

       Rows are the scarce dimension here: three panels of title + note +
       header + capped rows total 37 rows, so the whole body first fits a
       48-row terminal (ANALYSIS_MIN_HEIGHT in the screen suite).  Below
       that it scrolls -- nothing is unreachable -- and the advertisement is
       the title bar's `‹ taller`, driven off this body's own scrollbar.
       The gutter is reserved for the by-now-standard reason: without it the
       scrollbar takes its column out of the widest panel only on short
       terminals, and the *width* pin becomes a function of *height*. */
    CuratorScreen #curator-analysis-body {
        height: 1fr;
        width: 100%;
        overflow-y: auto;
        scrollbar-gutter: stable;
        scrollbar-size: 1 1;
    }
    /* `margin: 1 0 1 0` on the first panel: the top row is `#middle-row`'s
       own blank line under the hero, so every body's first title lands
       on the same row; the bottom row is the gap to SEGMENTS. */
    CuratorScreen CuratorOperators {
        width: 100%;
        height: auto;
        margin: 1 0 1 0;
        padding: 0 1;
    }
    CuratorScreen CuratorSegments {
        width: 100%;
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
    }
    CuratorScreen CuratorCleanList {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    /* The `l` view. Its two 100-row tables grow naturally inside one scrolling
       body, so every row remains reachable and short terminals are announced
       by the same title-bar marker as the `f` body. */
    CuratorScreen #curator-list-body {
        height: 1fr;
        width: 100%;
        overflow-y: auto;
        scrollbar-gutter: stable;
        scrollbar-size: 1 1;
    }
    CuratorScreen #curator-lists-row {
        width: 100%;
        height: auto;
        margin: 1 0 0 0;
    }
    CuratorScreen CuratorRawList {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    CuratorScreen CuratorCleanedList {
        width: 1fr;
        height: auto;
        padding: 0 1;
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
        export_dir: str | Path | None = None,
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None
        #: Where the `e` export writes.  Injectable for the same reason the
        #: cache path is (tests must never touch the developer's ~/.maxpane);
        #: ``None`` means the house directory, resolved at keypress time.
        self._export_dir = Path(export_dir) if export_dir is not None else None
        #: The wallet the leaderboard emphasises.  Passed in by the app from
        #: ``--wallet`` / ``MAXPANE_WALLET``; the screen never reads the
        #: environment itself, so two screens in one process can watch two
        #: wallets and a test drives it without patching anything.
        self._wallet = wallet or None
        #: Which table owns the bottom-right slot: ``VIEW_CLUSTERS`` or
        #: ``VIEW_CLOSEST``.  Starts on the unknown-phase default, which is
        #: also the grace default, so the first frame is never an empty table.
        self._active_view: str = _default_view(None)
        #: Which body is on screen: MODE_DASHBOARD or MODE_WALLET.  The hero and
        #: the title bar belong to neither and are always visible.
        self._mode: str = MODE_DASHBOARD
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
            # Both possible heroes are composed once. Wallet mode uses its own;
            # dashboard, analysis, and list modes share the doomsday clock.
            yield CuratorHero()
            yield CuratorWalletHero(id=WALLET_HERO_ID)

        # Every body is composed once and all but one are hidden, for the same
        # reason the two swap tables are: a body built on demand is blank for a
        # beat after the keypress, which reads as a bug. The title bar sits
        # above every body; only `y` swaps to the wallet hero.
        with Vertical(id=DASHBOARD_BODY_ID):
            with Horizontal(id="middle-row"):
                yield CuratorLeaderboard()
                with Vertical(id="curator-right-rail"):
                    yield CuratorSparklines()
                    yield CuratorSignals()

            yield Static("─" * 300, id="separator")

            with Horizontal(id="bottom-row"):
                yield CuratorActivity()
                # Both swap tables live in the layout and both are dispatched to
                # on every refresh; one is hidden at a time.  Creating one on
                # demand would leave it blank for a beat after the first ``c``,
                # which reads as a bug.
                yield CuratorClosestCalls(id=CLOSEST_ID)
                yield CuratorClusters(id=CLUSTERS_ID)

        with Vertical(id=WALLET_BODY_ID):
            with Horizontal(id="wallet-top-row"):
                yield CuratorWalletLadder()
                # The three facts panels stack in one rail beside the ladder:
                # they are read top to bottom as one thought -- where you
                # stand, what the next send must be, what it gets you -- and
                # the ladder is the tall thing they are read against.
                with Vertical(id="curator-wallet-rail"):
                    yield CuratorWalletAddress()
                    yield CuratorWalletStanding()
                    yield CuratorWalletNext()
                    yield CuratorWalletTarget()

        # The `f` view (PRD §5): the linked-wallet analysis, stacked so every
        # panel reaches its full tier at the screen's measured width.  Same
        # composed-once-shown-by-display contract as the other bodies,
        # and the dashboard hero above stays visible in this mode -- the
        # doomsday clock never leaves the screen.
        with Vertical(id=ANALYSIS_BODY_ID):
            yield CuratorOperators()
            yield CuratorSegments()
            yield CuratorCleanList()

        with Vertical(id=LIST_BODY_ID):
            with Horizontal(id="curator-lists-row"):
                yield CuratorRawList()
                yield CuratorCleanedList()

        yield StatusBar()

    #: The four view keys this screen names in the status bar. `tab switch`
    #: survives beside them at the measured width; `updated Ns ago` does not,
    #: and the title bar's `as of HH:MM` is the freshness marker that matters
    #: (it freezes under an outage, where the cycle age keeps counting).
    #: `e` is deliberately not here: it only acts inside `f` and `l`, and the
    #: relevant cleaned panel is where its result appears.
    #:
    #: The fourth key cannot grow the line: the third already pushed the
    #: worst-case (`4 errors` present) to the measured 138-column edge.  The
    #: compact spelling below remains 27 visible columns, the old hint's cost.
    KEY_HINTS = (
        "[dim]c[/] [dim]·[/] [dim]y[/] me [dim]·[/] "
        "[dim]f[/] link [dim]·[/] [dim]l[/] lists"
    )

    def on_mount(self) -> None:
        self._show_active_view()
        self._show_mode()
        try:
            self.query_one(StatusBar).set_key_hints(self.KEY_HINTS)
        except Exception as exc:  # noqa: BLE001 -- a hint is never load-bearing
            logger.debug("Could not set the curator key hints: %s", exc)

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

    def _show_mode(self) -> None:
        """Apply :attr:`_mode` to the four bodies' visibility.

        Exactly one body is displayed. Wallet mode swaps in its own hero;
        analysis and list mode keep the **dashboard** doomsday clock.
        """
        wallet = self._mode == MODE_WALLET
        analysis = self._mode == MODE_ANALYSIS
        lists = self._mode == MODE_LIST
        try:
            self.query_one(f"#{DASHBOARD_BODY_ID}").display = (
                not wallet and not analysis and not lists
            )
            self.query_one(f"#{WALLET_BODY_ID}").display = wallet
            self.query_one(f"#{ANALYSIS_BODY_ID}").display = analysis
            self.query_one(f"#{LIST_BODY_ID}").display = lists
            self.query_one(CuratorHero).display = not wallet
            self.query_one(f"#{WALLET_HERO_ID}").display = wallet
        except Exception as exc:  # noqa: BLE001 -- a toggle must never crash
            logger.debug("Curator mode toggle failed: %s", exc)
        # The `‹ taller` marker is about whichever body is now showing, so it
        # must be re-read -- deferred, exactly like `on_resize`, because the
        # newly displayed body has not been laid out when this returns.
        self.call_after_refresh(self._render_title)

    def action_toggle_mode(self) -> None:
        """``y`` -- swap the body between the game and the reader's own standing.

        The hero row stays put in both, so the doomsday clock never leaves the
        screen: this view is for deciding what to send, and that decision is
        worthless without the clock it is racing.

        **With no wallet configured this asks for one first.**  Every panel over
        there is about a wallet, so the view would otherwise open as six panels
        of ``--`` and leave the reader to guess that a *different* key is what
        they wanted.  Entering an address opens the view they asked for;
        escaping leaves them where they were.
        """
        if self._mode == MODE_WALLET:
            self._mode = MODE_DASHBOARD
            self._show_mode()
            return
        if self._wallet is None:
            self.app.push_screen(
                WalletInputScreen(),
                callback=lambda address: self._wallet_entered(
                    address, then_show_wallet=True
                ),
            )
            return
        self._mode = MODE_WALLET
        self._show_mode()

    def action_toggle_analysis(self) -> None:
        """``f`` -- swap the body for the linked-wallet analysis, or back.

        Mirrors :meth:`action_toggle_mode`, minus the wallet gate: the
        OPERATORS and SEGMENTS panels are about the population, so the view
        is worth opening with no wallet configured -- only the CLEANED LIST's
        "you" line needs one, and it degrades to its own instruction.
        """
        self._mode = (
            MODE_DASHBOARD if self._mode == MODE_ANALYSIS else MODE_ANALYSIS
        )
        self._show_mode()

    def action_toggle_list(self) -> None:
        """``l`` -- swap the body for the raw and cleaned record lists."""
        self._mode = MODE_DASHBOARD if self._mode == MODE_LIST else MODE_LIST
        self._show_mode()

    def action_export_clean_list(self) -> None:
        """``e`` -- export the active analysis or record-list view.

        Analysis mode retains its JSON + CSV cleaned-list export. List mode
        writes one JSON object containing both existing row arrays. Dashboard
        and wallet modes are no-ops. A ``None`` list is never written; an empty
        list is a real record and is written.

        A failed write is *told to the reader*, on the panel, not to the log
        alone -- and it replaces any earlier ``saved →`` receipt, whose
        freshness would otherwise be a lie about the keypress that just
        failed. Both writers use :func:`_atomic_write`, so a destination is
        never opened and truncated in place.
        """
        if self._mode == MODE_LIST:
            payload = self._title_data or {}
            raw = payload.get("leaderboard_rows")
            clean = payload.get("clean_list_rows")
            if not isinstance(raw, list) or not isinstance(clean, list):
                logger.debug("List export skipped: one or both lists unavailable")
                return
            directory = self._export_dir or Path.home() / ".maxpane"
            try:
                json_path = _write_lists(directory, raw, clean)
            except Exception as exc:  # noqa: BLE001 -- visible, never fatal
                logger.debug("List export failed: %s", exc)
                try:
                    self.query_one(CuratorCleanedList).mark_export_failed()
                except Exception as inner:  # noqa: BLE001
                    logger.debug("Could not show the list export failure: %s", inner)
                self.call_after_refresh(self._render_title)
                return
            try:
                self.query_one(CuratorCleanedList).mark_exported(str(json_path))
            except Exception as exc:  # noqa: BLE001 -- the file exists either way
                logger.debug("Could not show the list export path: %s", exc)
            self.call_after_refresh(self._render_title)
            return

        if self._mode != MODE_ANALYSIS:
            return
        rows = (self._title_data or {}).get("clean_list_rows")
        if not isinstance(rows, list):
            logger.debug("Clean-list export skipped: nothing analyzed yet")
            return
        directory = self._export_dir or Path.home() / ".maxpane"
        try:
            json_path = _write_clean_list(directory, rows)
        except Exception as exc:  # noqa: BLE001 -- a failed write must not crash
            logger.debug("Clean-list export failed: %s", exc)
            try:
                self.query_one(CuratorCleanList).mark_export_failed()
            except Exception as inner:  # noqa: BLE001
                logger.debug("Could not show the export failure: %s", inner)
            return
        try:
            self.query_one(CuratorCleanList).mark_exported(str(json_path))
        except Exception as exc:  # noqa: BLE001 -- the file is written either way
            logger.debug("Could not show the export path: %s", exc)

    def action_back_to_dashboard(self) -> None:
        """``esc`` -- one-way, back to the game from any secondary view. A no-op
        when already there, so the key never swallows an escape the reader
        meant for something else."""
        if self._mode != MODE_DASHBOARD:
            self._mode = MODE_DASHBOARD
            self._show_mode()

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

    def action_set_wallet(self) -> None:
        """``w`` -- prompt for the wallet the YOU row is about.

        The YOU row is the only actionable number on this screen and it is dark
        until somebody names an address, so the screen offers the prompt rather
        than only naming an environment variable it cannot set.
        ``WalletInputScreen`` validates the address and persists it to
        ``~/.maxpane/config.toml``, so the choice outlives the process and every
        wallet-scoped dashboard picks it up on the next launch.
        """
        self.app.push_screen(WalletInputScreen(), callback=self._wallet_entered)

    def _wallet_entered(
        self, address: str | None, *, then_show_wallet: bool = False
    ) -> None:
        """Callback from ``WalletInputScreen``: ``None`` means escape.

        Both halves have to move or the keypress lies: the **manager** owns the
        six YOU reads (and the stale state a switch invalidates -- see
        ``CuratorManager.set_wallet``), while the **screen** owns
        ``you_address``, which is what the leaderboard emphasises and what the
        rail prints.  Only then is a refresh worth spending: unchanged means the
        reader re-typed the address they already had.

        ``then_show_wallet`` is the ``y``-with-no-wallet path: the reader asked
        for the wallet view and was asked for an address on the way, so landing
        back on the dashboard would be answering a question they did not ask.
        An escape still leaves them where they were.
        """
        if not address:
            return
        moved = self._data_manager.set_wallet(address)
        self._wallet = address or None
        # Paint the address NOW rather than at the end of the next cycle.  The
        # YOU numbers cannot arrive until the fast tier re-reads, but the
        # *address* is known the instant it is typed, and a panel that still
        # says "press w to set one" right after you set one reads as a keypress
        # that did not work.
        try:
            # Not through `_dispatch`: the stale payload's `you_ens` is None for
            # the *previous* wallet, and rendering that as "no ENS record" is a
            # confident negative about a lookup that has not happened yet.
            self.query_one(CuratorWalletAddress).mark_pending(self._wallet)
        except Exception as exc:  # noqa: BLE001 -- a repaint is never load-bearing
            logger.debug("Could not repaint the wallet panel: %s", exc)
        if self._title_data is not None:
            for widget_cls in (CuratorWalletLadder, CuratorLeaderboard):
                self._dispatch(widget_cls, self._title_data)
        if then_show_wallet:
            self._mode = MODE_WALLET
            self._show_mode()
        if moved:
            self.action_refresh()

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
        """Does the showing body's scroll container exceed this height?

        ``show_vertical_scrollbar`` is the container's own answer, and it is
        what the layout already turns the loss into; asking it rather than
        re-deriving the arithmetic keeps the marker and the scrollbar from
        ever disagreeing. Which container matters depends on the mode, and the
        marker must describe the one the reader is looking at.
        """
        container_id = {
            MODE_DASHBOARD: "curator-right-rail",
            MODE_WALLET: "curator-wallet-rail",
            MODE_ANALYSIS: ANALYSIS_BODY_ID,
            MODE_LIST: LIST_BODY_ID,
        }.get(self._mode, "curator-right-rail")
        try:
            return bool(
                self.query_one(f"#{container_id}").show_vertical_scrollbar
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
            # Dispatched whether or not `y` is showing them, exactly like the
            # two swap tables: a body that starts rendering only when it
            # becomes visible is blank for a beat after the keypress.
            CuratorWalletHero,
            CuratorWalletAddress,
            CuratorWalletLadder,
            CuratorWalletStanding,
            CuratorWalletNext,
            CuratorWalletTarget,
            # The `f` view's three panels, dispatched hidden for the same
            # reason again -- and because "not yet analyzed" (`None` in every
            # analysis key) is a payload state they render explicitly.
            CuratorOperators,
            CuratorSegments,
            CuratorCleanList,
            # The `l` view is also dispatched hidden so it paints complete on
            # the first keypress without another read or refresh cycle.
            CuratorRawList,
            CuratorCleanedList,
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
