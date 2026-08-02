"""FWAScreen -- the Fake World Assets gacha terminal as a Textual Screen.

Layout (the house pattern, identical in structure to ``screens/talismans.py``
lines 58-80 and ``screens/ttt.py``)::

    #title-bar          FWA · N positions · X ETH in core · fee Y ETH
    FWAHeroMetrics      PULL EV · PRICE · CROWN            (3 cards, height 7)
    #middle-row         FWAOddsBoard (3fr)     | #right-col (2fr)
                        FWAActivityFeed (3fr)    FWASparkline  (height auto)
                          -- one or the other,   FWASignals    (1fr)
                             toggled with `c`
    #separator
    #bottom-row         FWAChaseBoard (2fr) | FWASettlementTable (2fr)
    StatusBar

Three things about this screen are deliberate rather than incidental:

1. **``c`` toggles the odds board and the activity feed**, the same affordance
   Talismans and TTT use for their two mutually exclusive tables. The feed
   originally sat in the bottom row and took 3fr of 7, which left the chase
   board and the settlement table roughly 55 rendered columns each at a
   200-column terminal -- below what either needs for its full column set, so
   both wore a permanent ``‹ widen`` marker. Giving the bottom row to those two
   alone and letting the feed share the odds board's slot brought the width
   needed for a marker-free layout down from 198 columns to 172.

   Both widgets stay mounted and both are dispatched to on every refresh, so
   toggling is a visibility flip with no refetch. Creating the feed on demand
   would leave it blank for a beat after the first ``c``, which reads as a bug.

2. **Every widget update is individually guarded.** One widget raising must
   never cost the other six their refresh, so each dispatch is its own
   ``try``/``except`` with a ``logger.debug``. A failure of the *manager* is
   different in kind: nothing can be trusted, so only the ``StatusBar`` is
   touched (``last_updated_seconds_ago=999``) and the previous frame is left on
   screen rather than being half-overwritten.

3. **Degradation reaches the title bar.** ``degraded_sources`` has no home in
   the shared ``StatusBar`` API (:mod:`maxpane_dashboard.widgets.status_bar`
   exposes only ``last_updated_seconds_ago`` / ``error_count`` /
   ``poll_interval`` plus the game/theme/view labels), so it is appended to the
   title bar instead. Leaving it to the widgets alone would mean the operator
   has to notice *which* panels went quiet; PRD §9 wants the fact stated once,
   somewhere permanent. If ``StatusBar`` ever grows a ``set_degraded()``, this
   is the line to move.

Minimum terminal width: 172 columns
-----------------------------------

Measured against composited output, not estimated: at **172 columns** the last
``‹ widen`` marker (the signals panel's) goes away, in both views.
``__main__.FULL_LAYOUT_COLUMNS`` carries the number and a test renders this
screen at it.

It used to be 198. The bottom row was 3fr/2fr/2fr with the activity feed taking
the 3fr, so the chase board and settlement table got ~55 columns each -- the
feed needs 79 for its full line and those two need 54 and 55, and the row could
not satisfy all three until the terminal was very wide. Moving the feed into
the odds board's slot leaves the bottom row split evenly between two widgets
that each need ~55, which is why the requirement fell by 26 columns.

Below the threshold, **no widget drops a column silently**: each announces the
loss in its own title with a ``‹ widen`` marker naming what went
(``‹ widen: TOKEN``, ``‹ widen: COUNT``, ``‹ widen for amounts``). The chase
board's ``ODDS`` and ``JACKPOT`` and the settlement table's ``SHARE`` are the
last columns dropped, because they carry those widgets' entire point. A narrow
terminal therefore costs *fields*, never correctness — every number still on
screen is the same number it would be at 200 columns.

The screen is clock-free: every time-derived string (the emissions countdown,
the feed's "as of HH:MM", staleness) arrives already rendered in the payload.
Nothing here consults the wall clock, which is why the 2026-08-04T19:01:23Z
emissions stop can be tested in both its live and its ended state from fixed
fixtures.

The screen is written against the frozen ``FWA_DATA_KEYS`` /
``FWA_WIDGET_SIGNATURES`` contract, not against ``FWAManager``'s internals --
any object with an awaitable ``fetch_and_compute()`` returning that dict drives
it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.screens.refresh_guard import RefreshGuard
from maxpane_dashboard.widgets.fwa import (
    FWAActivityFeed,
    FWAChaseBoard,
    FWAHeroMetrics,
    FWAOddsBoard,
    FWASettlementTable,
    FWASignals,
    FWASparkline,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from maxpane_dashboard.data.fwa_manager import FWAManager

logger = logging.getLogger(__name__)

_EMDASH = "—"

#: Shown until the first payload lands.
INITIAL_TITLE = "FWA · Gacha Terminal · Ethereum Mainnet"

#: Sentinel staleness pushed to the StatusBar when the manager itself failed.
MANAGER_FAILURE_SECONDS = 999


# -- format helpers ----------------------------------------------------


def _num(value, default: float = 0.0) -> float:
    """Coerce to ``float``, falling back to ``default`` -- never raise.

    Exists because an all-``None`` payload (PRD §9) must still be able to drive
    ``StatusBar.update_data``, which does arithmetic on its arguments.
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
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _EMDASH


def _fmt_eth(value, places: int = 4) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        out = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if out != out:
        return _EMDASH
    return f"{out:,.{places}f}"


def _fmt_degraded(sources) -> str:
    """``· degraded: logs, market`` -- or an empty string when all is well."""
    if not sources:
        return ""
    try:
        names = [str(s).strip() for s in sources if str(s).strip()]
    except TypeError:
        return ""
    if not names:
        return ""
    return " · degraded: " + ", ".join(names)


def _title_line(data: dict) -> str:
    """Compose the meta row.

    The first three fields are the mandated format. What follows is ordered by
    what must survive a narrow terminal: warnings before figures, because
    ``#title-bar`` is one row high and the tail is what gets clipped.

    ``current_block`` is deliberately absent -- the odds board already prints
    the block its sweep is pinned to, which is the honest "as of" for the only
    panel whose freshness can lag. ``invariants_ok`` is surfaced here as well
    as through ``odds_stale``: the manager sets both, and a mismatch is worth
    stating in words rather than leaving as a table's ``STALE`` tag.
    """
    line = (
        f"FWA · {_fmt_int(data.get('active_positions'))} positions · "
        f"{_fmt_eth(data.get('core_balance_eth'), 3)} ETH in core · "
        f"fee {_fmt_eth(data.get('acquisition_fee_eth'))} ETH"
    )

    if data.get("invariants_ok") is False:
        line += " · [yellow]⚠ invariant mismatch[/]"

    line += _fmt_degraded(data.get("degraded_sources"))

    revenue = data.get("cumulative_revenue_eth")
    if revenue is not None:
        line += f" · rev {_fmt_eth(revenue, 2)} ETH"
    take_rate = data.get("take_rate_pct")
    if take_rate is not None:
        line += f" · take {_fmt_eth(take_rate, 2)}%"

    return line


class FWAScreen(RefreshGuard, Screen):
    """Fake World Assets gacha-terminal dashboard.

    ``BINDINGS`` is ``r`` plus ``c`` -- the latter swaps the odds board and the
    activity feed in the middle-left slot (see the module docstring).
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("c", "toggle_view", "Odds/Activity", show=True),
    ]

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "fwa-refresh"

    # Structural fallback only. The registered ``fwa`` theme (WP-16) restates
    # these in ``themes/minimal.tcss`` and overrides them -- app stylesheet
    # rules always beat ``DEFAULT_CSS``. They live here so the screen is
    # reviewable and correctly proportioned on its own, under any theme that
    # has no FWA block.
    #
    # FWAHeroBox's padding is intentionally NOT restated here: it is set to
    # ``0 2`` in the widget's own ``DEFAULT_CSS`` and any theme rule that
    # raises it to ``1 2`` costs the hero cards their fourth line, i.e. the
    # PULL EV coverage badge (PRD §3). See ``widgets/fwa/__init__.py``.
    DEFAULT_CSS = """
    FWAScreen #title-bar {
        width: 100%;
        height: 1;
        text-align: center;
        content-align: center middle;
    }
    FWAScreen FWAHeroMetrics {
        padding: 0 1;
        margin: 1 0 0 0;
    }
    FWAScreen #middle-row {
        height: 1fr;
        margin: 1 0 0 0;
    }
    FWAScreen FWAOddsBoard {
        width: 3fr;
        padding: 0 1;
    }
    FWAScreen #right-col {
        width: 2fr;
        padding: 0 1;
    }
    FWAScreen FWASparkline {
        height: auto;
        content-align: center top;
    }
    FWAScreen FWASignals {
        height: 1fr;
        margin: 1 0 0 0;
        overflow-y: auto;
        content-align: center top;
    }
    FWAScreen #separator {
        width: 100%;
        height: 1;
        padding: 0 2;
    }
    FWAScreen #bottom-row {
        height: 1fr;
        margin: 0 0 1 0;
    }
    FWAScreen FWAActivityFeed {
        width: 3fr;
        padding: 0 1;
    }
    FWAScreen FWAChaseBoard {
        width: 2fr;
        padding: 0 1;
    }
    FWAScreen FWASettlementTable {
        width: 2fr;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        data_manager: "FWAManager",
        poll_interval: int = 30,
        name: str = "fwa",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None
        #: Which widget owns the wide middle-left slot: "odds" or "activity".
        self._active_view: str = "odds"

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(INITIAL_TITLE, id="title-bar")

        yield FWAHeroMetrics()

        with Horizontal(id="middle-row"):
            # Two views of the same slot, toggled with ``c``. The feed is
            # created hidden rather than created on demand so it keeps
            # receiving every refresh and is already populated when toggled to
            # -- an empty panel that fills in a beat later reads as a bug.
            yield FWAOddsBoard()
            feed = FWAActivityFeed()
            feed.display = False
            yield feed
            with Vertical(id="right-col"):
                yield FWASparkline()
                yield FWASignals()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            # Two panes, half the width each. The activity feed used to sit
            # here and took 3fr of 7, leaving these two ~55 columns apiece at a
            # 200-column terminal -- below what either needs for its full
            # column set. Sharing the row between them roughly doubles both.
            yield FWAChaseBoard()
            yield FWASettlementTable()

        yield StatusBar()

    # ------------------------------------------------------------------
    # Actions / bindings
    # ------------------------------------------------------------------

    def action_toggle_view(self) -> None:
        """Swap the odds board and the activity feed in the middle-left slot.

        Both widgets stay mounted and both keep being updated on every
        refresh, so toggling is a pure visibility flip -- no refetch, no
        repopulate, no empty frame.
        """
        self._active_view = "activity" if self._active_view == "odds" else "odds"
        showing_odds = self._active_view == "odds"
        try:
            self.query_one(FWAOddsBoard).display = showing_odds
            self.query_one(FWAActivityFeed).display = not showing_odds
        except Exception as exc:  # noqa: BLE001 -- a toggle must never crash
            logger.debug("FWA view toggle failed: %s", exc)
        try:
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass

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
            self.query_one(StatusBar).set_game_name("fwa")
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    # ------------------------------------------------------------------
    # Refresh flow
    # ------------------------------------------------------------------

    async def _do_refresh(self) -> None:
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            logger.debug("FWA refresh failed: %s", exc)
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
            logger.debug("FWA refresh returned %r, not a dict", type(data))
            return

        # Title bar
        try:
            self.query_one("#title-bar", Static).update(_title_line(data))
        except Exception as exc:
            logger.debug("Failed to update title bar: %s", exc)

        # Hero metrics -- PULL EV · PRICE · CROWN
        try:
            self.query_one(FWAHeroMetrics).update_data(
                pull_ev_best_eth=data.get("pull_ev_best_eth"),
                pull_ev_lower_eth=data.get("pull_ev_lower_eth"),
                ev_available=data.get("ev_available"),
                ev_collections_priced=data.get("ev_collections_priced"),
                ev_collections_total=data.get("ev_collections_total"),
                ev_weight_priced_pct=data.get("ev_weight_priced_pct"),
                ev_rebate_eth=data.get("ev_rebate_eth"),
                acquisition_fee_eth=data.get("acquisition_fee_eth"),
                vrf_fee_eth=data.get("vrf_fee_eth"),
                quote_total_eth=data.get("quote_total_eth"),
                price_available=data.get("price_available"),
                harmonic_mean_eth=data.get("harmonic_mean_eth"),
                arithmetic_mean_eth=data.get("arithmetic_mean_eth"),
                hm_am_gap_x=data.get("hm_am_gap_x"),
                crown_pot_eth=data.get("crown_pot_eth"),
                crown_pot_usd=data.get("crown_pot_usd"),
                crown_seize_eth=data.get("crown_seize_eth"),
                crown_holder=data.get("crown_holder"),
                crown_holder_name=data.get("crown_holder_name"),
                crown_vacant=data.get("crown_vacant"),
                crown_available=data.get("crown_available"),
            )
        except Exception as exc:
            logger.debug("Failed to update FWAHeroMetrics: %s", exc)

        # Odds board (middle-row left)
        try:
            self.query_one(FWAOddsBoard).update_data(
                collection_odds=data.get("collection_odds"),
                odds_available=data.get("odds_available"),
                odds_as_of_block=data.get("odds_as_of_block"),
                odds_stale=data.get("odds_stale"),
            )
        except Exception as exc:
            logger.debug("Failed to update FWAOddsBoard: %s", exc)

        # Sparkline (right-col top)
        try:
            self.query_one(FWASparkline).update_data(
                fwa_price_history=data.get("fwa_price_history"),
                fwa_price_usd=data.get("fwa_price_usd"),
                fwa_price_change_24h=data.get("fwa_price_change_24h"),
                spark_available=data.get("spark_available"),
            )
        except Exception as exc:
            logger.debug("Failed to update FWASparkline: %s", exc)

        # Signals (right-col bottom)
        try:
            self.query_one(FWASignals).update_data(
                pool_temp_signal=data.get("pool_temp_signal"),
                buy_gate_signal=data.get("buy_gate_signal"),
                emissions_signal=data.get("emissions_signal"),
                vrf_queue_signal=data.get("vrf_queue_signal"),
                param_drift_signal=data.get("param_drift_signal"),
            )
        except Exception as exc:
            logger.debug("Failed to update FWASignals: %s", exc)

        # Activity feed (bottom-row left)
        try:
            self.query_one(FWAActivityFeed).update_data(
                draw_events=data.get("draw_events"),
                feed_available=data.get("feed_available"),
                feed_unavailable_reason=data.get("feed_unavailable_reason"),
                feed_as_of_ts=data.get("feed_as_of_ts"),
            )
        except Exception as exc:
            logger.debug("Failed to update FWAActivityFeed: %s", exc)

        # Chase board (bottom-row centre)
        #
        # ``crown_listing_id`` is an optional extra outside the frozen
        # signature: when the manager supplies it, the row that is *also* the
        # crown position gets marked. It is passed through only when present,
        # so the board never claims a coincidence it was not told about.
        try:
            chase_kwargs = {
                "chase_positions": data.get("chase_positions"),
                "chase_available": data.get("chase_available"),
            }
            if "crown_listing_id" in data:
                chase_kwargs["crown_listing_id"] = data["crown_listing_id"]
            self.query_one(FWAChaseBoard).update_data(**chase_kwargs)
        except Exception as exc:
            logger.debug("Failed to update FWAChaseBoard: %s", exc)

        # Settlement + crown history (bottom-row right)
        try:
            self.query_one(FWASettlementTable).update_data(
                settlement_mix=data.get("settlement_mix"),
                crown_history=data.get("crown_history"),
                crown_sets_total=data.get("crown_sets_total"),
                crown_payouts_total=data.get("crown_payouts_total"),
                crown_paid_eth=data.get("crown_paid_eth"),
                settle_available=data.get("settle_available"),
                settle_as_of_ts=data.get("settle_as_of_ts"),
            )
        except Exception as exc:
            logger.debug("Failed to update FWASettlementTable: %s", exc)

        # Status bar. Values are coerced because an all-None payload is a
        # supported state (PRD §9) and StatusBar does arithmetic on these.
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=_num(
                    data.get("last_updated_seconds_ago"), 0.0
                ),
                error_count=int(_num(data.get("error_count"), 0)),
                poll_interval=int(_num(data.get("poll_interval"), self._poll_interval)),
            )
        except Exception as exc:
            logger.debug("Failed to update StatusBar: %s", exc)
