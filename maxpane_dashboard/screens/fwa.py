"""FWAScreen -- PULLS and NETWORK views for Fake World Assets.

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
    FWANetworkHero     PLATFORM · TOKENOMICS · ECOSYSTEM   (hidden initially)
    #fwa-network-body VALUE FLOW / REGISTRY | DROPS / ACTIVITY
    StatusBar

Four contracts are deliberate:

1. ``e`` flips already-mounted PULLS and NETWORK bodies without fetching.
   ``c`` keeps its original odds/activity meaning in PULLS and does nothing in
   NETWORK; ``escape`` returns to PULLS without forgetting that sub-view.
2. Every widget update is independently guarded. One broken renderer cannot
   suppress the other panels; a manager failure leaves the previous frame and
   marks only the shared status bar.
3. Source degradation and integrity reach the active title. The shared
   :class:`StatusBar` remains unchanged and uses only its existing freshness,
   error, and active-view surfaces.
4. Geometry is measured in the real compositor. The app-wide PULLS pin remains
   143 columns; NETWORK's smallest complete fallback seam is 122 columns and
   its first non-scrolling height is 39 rows. Below those boundaries, whole
   fields are shed with ``‹ widen`` or the title advertises ``‹ taller``.

The screen is clock-free: every time-derived string (the emissions countdown,
the feed's "as of HH:MM", staleness) arrives already rendered in the payload.
Nothing here consults the wall clock, which is why the 2026-08-04T19:01:23Z
emissions stop can be tested in both its live and its ended state from fixed
fixtures.

The screen is written against the frozen PULLS and NETWORK presentation
contracts, not against manager internals.  Both bodies remain mounted and are
updated on every refresh; ``e`` only flips visibility, while ``c`` retains its
original odds/activity meaning inside PULLS and is a no-op inside NETWORK.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.data.fwa_ecosystem_models import (
    FWA_NETWORK_WIDGET_SIGNATURES,
)
from maxpane_dashboard.screens.refresh_guard import RefreshGuard
from maxpane_dashboard.widgets.fwa import (
    FWAActivityFeed,
    FWAChaseBoard,
    FWAEcosystemRegistry,
    FWAFlowRail,
    FWAHeroMetrics,
    FWAIRDropBoard,
    FWANetworkActivity,
    FWANetworkHero,
    FWAOddsBoard,
    FWASettlementTable,
    FWASignals,
    FWASparkline,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from maxpane_dashboard.data.fwa_composite_manager import FWACompositeManager

logger = logging.getLogger(__name__)

_EMDASH = "—"

#: Shown until the first payload lands.
INITIAL_TITLE = "FWA · Gacha Terminal · Ethereum Mainnet"

#: Sentinel staleness pushed to the StatusBar when the manager itself failed.
MANAGER_FAILURE_SECONDS = 999

#: First width where both NETWORK tables' smallest complete column tier fits
#: inside the real 3:2 columns, including padding and reserved scrollbar cells.
#: The application-wide pin remains 143, comfortably above this boundary.
FWA_NETWORK_FULL_LAYOUT_COLUMNS = 122

#: First terminal height at which the NETWORK body's two columns can show all
#: panels at their declared minimum heights.  Shorter terminals keep the same
#: data and scroll the columns; the title advertises ``‹ taller``.
FWA_NETWORK_FULL_LAYOUT_ROWS = 39

_NETWORK_WIDGET_CLASSES = {
    "FWANetworkHero": FWANetworkHero,
    "FWAFlowRail": FWAFlowRail,
    "FWAIRDropBoard": FWAIRDropBoard,
    "FWAEcosystemRegistry": FWAEcosystemRegistry,
    "FWANetworkActivity": FWANetworkActivity,
}


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


def _network_title_line(data: dict, *, short: bool = False) -> str:
    """Compose the one-row NETWORK provenance title without inventing state."""

    block = _fmt_int(data.get("network_state_block"))
    state = "n/a" if block == _EMDASH else f"#{block}"
    if data.get("network_state_stale") is True:
        chain = "CHAIN STALE"
    elif data.get("network_state_block") is not None:
        chain = "CHAIN LIVE"
    else:
        chain = "CHAIN N/A"

    line = "FWA NETWORK"
    if short:
        line += " · [yellow]‹ taller[/]"
    line += f" · state {state} · {chain}"
    head = _fmt_int(data.get("network_chain_head"))
    if head != _EMDASH and head != block:
        line += f" · head #{head}"
    degraded = data.get("network_degraded_sources")
    try:
        degraded_count = len([item for item in degraded or [] if str(item).strip()])
    except TypeError:
        degraded_count = 0
    if degraded_count:
        noun = "SOURCE" if degraded_count == 1 else "SOURCES"
        line += f" · [yellow]{degraded_count} {noun} STALE[/]"

    warnings = data.get("network_integrity_warning_count")
    try:
        warning_count = int(warnings) if warnings is not None else 0
    except (TypeError, ValueError, OverflowError):
        warning_count = 0
    if warning_count:
        line += f" · [yellow]{warning_count} INTEGRITY[/]"
    return line


class FWAScreen(RefreshGuard, Screen):
    """Fake World Assets dashboard with independent PULLS/NETWORK state."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("c", "toggle_view", "Odds/Activity", show=True),
        Binding("e", "toggle_mode", "PULLS/Network", show=True),
        Binding(
            "escape",
            "show_pulls",
            "Back to PULLS",
            show=False,
            priority=True,
        ),
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
    FWAScreen FWANetworkHero {
        height: 7;
        margin: 1 0 0 0;
    }
    FWAScreen FWANetworkHero > FWAHeroBox {
        padding: 0 1;
    }
    FWAScreen #fwa-network-body {
        width: 100%;
        height: 1fr;
        margin: 1 0 1 0;
    }
    FWAScreen #fwa-network-main {
        width: 3fr;
        height: 1fr;
        min-height: 26;
        padding: 0 1;
        overflow-y: auto;
        scrollbar-gutter: stable;
        scrollbar-size: 1 1;
    }
    FWAScreen #fwa-network-rail {
        width: 2fr;
        height: 1fr;
        min-height: 23;
        padding: 0 1;
        overflow-y: auto;
        scrollbar-gutter: stable;
        scrollbar-size: 1 1;
    }
    FWAScreen FWAFlowRail,
    FWAScreen FWAEcosystemRegistry,
    FWAScreen FWAIRDropBoard,
    FWAScreen FWANetworkActivity {
        width: 100%;
    }
    FWAScreen FWAEcosystemRegistry,
    FWAScreen FWANetworkActivity {
        margin: 1 0 0 0;
    }
    """

    def __init__(
        self,
        data_manager: "FWACompositeManager",
        poll_interval: int = 30,
        name: str = "fwa",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None
        self._mode: str = "pulls"
        #: Which widget owns the PULLS middle-left slot: "odds" or "activity".
        self._pulls_view: str = "odds"
        self._last_data: dict = {}

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

        network_hero = FWANetworkHero()
        network_hero.display = False
        yield network_hero

        network_body = Horizontal(id="fwa-network-body")
        network_body.display = False
        with network_body:
            with Vertical(id="fwa-network-main"):
                yield FWAFlowRail()
                yield FWAEcosystemRegistry()
            with Vertical(id="fwa-network-rail"):
                yield FWAIRDropBoard()
                yield FWANetworkActivity()

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
        if self._mode != "pulls":
            return
        self._pulls_view = "activity" if self._pulls_view == "odds" else "odds"
        showing_odds = self._pulls_view == "odds"
        try:
            self.query_one(FWAOddsBoard).display = showing_odds
            self.query_one(FWAActivityFeed).display = not showing_odds
        except Exception as exc:  # noqa: BLE001 -- a toggle must never crash
            logger.debug("FWA view toggle failed: %s", exc)
        try:
            self.query_one(StatusBar).set_active_view(self._status_view())
        except Exception:
            pass
        self._update_status_metrics()

    def _update_status_metrics(self) -> None:
        if not self._last_data:
            return
        data = self._last_data
        if self._mode == "network":
            age = data.get("network_last_updated_seconds_ago")
            errors = data.get("network_error_count")
            age_default = MANAGER_FAILURE_SECONDS
        else:
            age = data.get("last_updated_seconds_ago")
            errors = data.get("error_count")
            age_default = 0.0
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=_num(age, age_default),
                error_count=int(_num(errors, 0)),
                poll_interval=int(_num(data.get("poll_interval"), self._poll_interval)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to update FWA StatusBar: %s", exc)

    def action_toggle_mode(self) -> None:
        """Flip already-mounted PULLS and NETWORK bodies without fetching."""

        self._mode = "network" if self._mode == "pulls" else "pulls"
        self._apply_mode()

    def action_show_pulls(self) -> None:
        """Return from NETWORK; leave the remembered odds/activity slot intact."""

        if self._mode == "pulls":
            return
        self._mode = "pulls"
        self._apply_mode()

    def _apply_mode(self) -> None:
        showing_pulls = self._mode == "pulls"
        for selector in (
            "FWAHeroMetrics",
            "#middle-row",
            "#separator",
            "#bottom-row",
        ):
            try:
                self.query_one(selector).display = showing_pulls
            except Exception as exc:  # noqa: BLE001 -- mode switches never crash
                logger.debug("FWA mode toggle could not update %s: %s", selector, exc)
        for selector in ("FWANetworkHero", "#fwa-network-body"):
            try:
                self.query_one(selector).display = not showing_pulls
            except Exception as exc:  # noqa: BLE001
                logger.debug("FWA mode toggle could not update %s: %s", selector, exc)
        self._update_chrome()

    def _status_view(self) -> str:
        if self._mode == "network":
            return "network · e pulls"
        return f"pulls/{self._pulls_view} · e network"

    def _update_chrome(self) -> None:
        try:
            title = (
                _network_title_line(
                    self._last_data,
                    short=0 < self.size.height < FWA_NETWORK_FULL_LAYOUT_ROWS,
                )
                if self._mode == "network"
                else _title_line(self._last_data)
                if self._last_data
                else INITIAL_TITLE
            )
            self.query_one("#title-bar", Static).update(title)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to update FWA title chrome: %s", exc)
        try:
            self.query_one(StatusBar).set_active_view(self._status_view())
        except Exception:
            pass
        self._update_status_metrics()

    def on_resize(self, _event=None) -> None:
        if self._mode == "network":
            self._update_chrome()

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
            self.query_one(StatusBar).set_active_view(self._status_view())
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

        self._last_data = data
        self._update_chrome()

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
                sellback_signal=data.get("sellback_signal"),
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

        # NETWORK widgets are populated even while their body is hidden.  The
        # first ``e`` press therefore paints immediately and never triggers I/O.
        for name, widget_class in _NETWORK_WIDGET_CLASSES.items():
            signature = FWA_NETWORK_WIDGET_SIGNATURES[name]
            try:
                self.query_one(widget_class).update_data(
                    **{key: data.get(key) for key in signature}
                )
            except Exception as exc:  # noqa: BLE001 -- isolate every panel
                logger.debug("Failed to update %s: %s", name, exc)
