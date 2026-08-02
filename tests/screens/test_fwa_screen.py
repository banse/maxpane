"""Headless Textual tests for the FWA dashboard screen (WP-13).

A fake manager returns the frozen ``FWA_DATA_KEYS`` dict (no network), the
screen is pushed via ``App.run_test()``, and we assert:

* the screen mounts, composes all seven widgets and refreshes,
* **every** ``FWA_DATA_KEYS`` group reaches the widget that owns it -- checked
  mechanically against ``FWA_WIDGET_SIGNATURES`` rather than by eye, so a key
  added upstream cannot quietly go unrendered,
* a manager exception leaves the screen standing and only marks the StatusBar,
* an all-``None`` payload renders explicit unavailable states (PRD §9),
* the PULL EV coverage badge is **on screen** -- asserted against the
  compositor, not the widget's content string. A hero box with too little
  vertical room drops its last line silently, and that last line is the
  coverage badge; an EV number without it is what PRD §3 forbids. The same
  assertion is repeated with the real ``minimal.tcss`` loaded, so a theme rule
  that reintroduces ``padding: 1 2`` on ``FWAHeroBox`` fails here.

Zero network, and zero dependence on the wall clock: the 2026-08-04T19:01:23Z
emissions stop is exercised in both its *ended* (primary) and its *counting
down* state from fixed payloads, so these tests read the same before and after
that date.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from maxpane_dashboard.analytics import fwa_signals as _signals
from maxpane_dashboard.data.fwa_models import (
    FWA_DATA_KEYS,
    FWA_WIDGET_SIGNATURES,
)
from maxpane_dashboard.screens.fwa import FWAScreen
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

_THEMES = Path(__file__).resolve().parents[2] / "maxpane_dashboard" / "themes"
_TCSS = _THEMES / "minimal.tcss"

#: Keys the screen itself consumes rather than handing to a widget: the title
#: bar takes the first six, the StatusBar the last three. ``current_block`` is
#: deliberately not rendered -- the odds board prints ``odds_as_of_block``,
#: which is the block the only lag-prone panel is pinned to.
META_KEYS = frozenset(
    {
        "active_positions",
        "core_balance_eth",
        "cumulative_revenue_eth",
        "take_rate_pct",
        "current_block",
        "invariants_ok",
        "degraded_sources",
        "last_updated_seconds_ago",
        "error_count",
        "poll_interval",
    }
)

_WIDGET_CLASSES = {
    "FWAHeroMetrics": FWAHeroMetrics,
    "FWAOddsBoard": FWAOddsBoard,
    "FWASparkline": FWASparkline,
    "FWASignals": FWASignals,
    "FWAActivityFeed": FWAActivityFeed,
    "FWAChaseBoard": FWAChaseBoard,
    "FWASettlementTable": FWASettlementTable,
}

#: Fixed timestamps -- never ``time.time()``. See the module docstring.
_TS = 1_775_000_000
_BLOCK = 25_612_701

#: The emissions hard stop, as the two states the signal can be in. The ended
#: state is primary: it is what the dashboard will spend its life showing.
#:
#: Both are built by calling the **real** builder with a pinned clock rather
#: than hand-written (WP-20). The hand-written versions carried
#: ``"color": "green"`` and ``"indicator": "▲"`` -- neither of which
#: ``analytics/fwa_signals.py`` can emit: the colour vocabulary is
#: ``$success | $warning | $error | dim`` and the indicator is always ``●``.
#: A screen test whose payload the product cannot produce measures the fixture,
#: not the screen. The clock is injected on both sides of 2026-08-04T19:01:23Z,
#: so these still read identically before and after that instant.
_EMISSION_START = 1_784_574_083
_EMISSION_DURATION = 1_785_870_083 - _EMISSION_START  # stops 2026-08-04T19:01:23Z
_EMISSION_STOP = _EMISSION_START + _EMISSION_DURATION

EMISSIONS_ENDED_SIGNAL = _signals.emissions_signal(
    _EMISSION_STOP + 21 * 86_400, _EMISSION_START, _EMISSION_DURATION, 3
).model_dump()
EMISSIONS_LIVE_SIGNAL = _signals.emissions_signal(
    _EMISSION_STOP - (8 * 86_400 + 4 * 3_600), _EMISSION_START, _EMISSION_DURATION, 3
).model_dump()


def _sample_data() -> dict:
    """A representative full payload, plus the optional ``crown_listing_id``.

    ``crown_listing_id`` is outside the frozen signature and WP-12 is adding it
    to ``FWA_DATA_KEYS`` in parallel; it is included here so the screen is
    tested with it, and every test that needs the exact frozen key set derives
    it from ``FWA_DATA_KEYS`` instead of from this dict.
    """
    return {
        # -- hero: PULL EV ------------------------------------------------
        "pull_ev_best_eth": -0.0163,
        "pull_ev_lower_eth": -0.0871,
        "ev_available": True,
        "ev_collections_priced": 22,
        "ev_collections_total": 38,
        "ev_weight_priced_pct": 61.3,
        "ev_rebate_eth": 0.0042,
        # -- hero: PRICE ---------------------------------------------------
        "acquisition_fee_eth": 0.1247,
        "vrf_fee_eth": 0.0009,
        "quote_total_eth": 0.1256,
        "price_available": True,
        "harmonic_mean_eth": 0.1247,
        "arithmetic_mean_eth": 0.5002,
        "hm_am_gap_x": 4.01,
        # -- hero: CROWN ---------------------------------------------------
        "crown_pot_eth": 221.4,
        "crown_pot_usd": 812_300.0,
        "crown_seize_eth": 243.54,
        "crown_holder": "0x" + "ab" * 20,
        "crown_vacant": False,
        "crown_available": True,
        # -- odds board -----------------------------------------------------
        "collection_odds": [
            {
                "rank": 1,
                "address": "0x" + "11" * 20,
                "name": "Ten Thousand Tokens",
                "positions": 1847,
                "weight_share_pct": 49.0828,
                "eth_backed": 210.4409,
                "floor_eth": 0.0421,
                "floor_source": "coingecko",
                "eth_per_odds_point": 4.287,
                "floor_note": "",
            },
            {
                "rank": 2,
                "address": "0x" + "22" * 20,
                "name": "Art Blocks",
                "positions": 402,
                "weight_share_pct": 11.7431,
                "eth_backed": 88.12,
                "floor_eth": None,
                "floor_source": "suppressed",
                "eth_per_odds_point": None,
                "floor_note": "one contract hosts many collections",
            },
            {
                "rank": 3,
                "address": "0x" + "33" * 20,
                "name": "CryptoPunks",
                "positions": 3,
                "weight_share_pct": 0.0,
                "eth_backed": 137.1,
                "floor_eth": 42.5,
                "floor_source": "coingecko",
                "eth_per_odds_point": None,
                "floor_note": "",
            },
        ],
        "odds_available": True,
        "odds_as_of_block": _BLOCK,
        "odds_stale": False,
        # -- sparkline -------------------------------------------------------
        "fwa_price_history": [[_TS + i * 3600, 0.00042 + i * 1e-6] for i in range(100)],
        "fwa_price_usd": 0.00051,
        "fwa_price_change_24h": -3.42,
        "spark_available": True,
        # -- signals ---------------------------------------------------------
        # Built by the real builders, not by hand -- see EMISSIONS_*_SIGNAL
        # above. Every field here is one the product can actually emit.
        "pool_temp_signal": _signals.pool_temp_signal(
            seconds_since_last_request=4_000,
            token_share_bps=0,
            hot_gap=60,
            cold_gap=3_600,
        ).model_dump(),
        "buy_gate_signal": _signals.buy_gate_signal(False).model_dump(),
        "emissions_signal": EMISSIONS_ENDED_SIGNAL,
        "vrf_queue_signal": _signals.vrf_queue_signal(
            last_issued=100,
            next_to_process=100,
            pending=0,
            unsettled=0,
            unfulfilled_vrf=0,
            subscription_balance=10**18,
            minimum_buffer=10**17,
        ).model_dump(),
        "param_drift_signal": _signals.param_drift_signal(
            [{"key": 15, "value": 100, "block_number": 25_592_190, "ts": _TS}],
            {},
        ).model_dump(),
        # -- activity feed -----------------------------------------------------
        "draw_events": [
            {
                "ts": _TS - i * 600,
                "block_number": _BLOCK - i,
                "tx_hash": f"0x{i:064x}",
                "purchaser": f"0x{i:040x}",
                "collection": "0x" + "11" * 20,
                "collection_name": "Ten Thousand Tokens",
                "token_id": 1000 + i,
                "outcome": "bid_fwa",
                "outcome_label": "accepted bid · paid in $FWA",
                "amount_eth": 0.0421,
            }
            for i in range(6)
        ],
        "feed_available": True,
        "feed_unavailable_reason": None,
        "feed_as_of_ts": float(_TS),
        # -- chase board --------------------------------------------------------
        "chase_positions": [
            {
                "rank": 1,
                "listing_id": 56508,
                "collection": "0x" + "33" * 20,
                "collection_name": "CryptoPunks",
                "token_id": 4821,
                "backing_eth": 221.4,
                "odds_pct": 0.0000004,
                "expected_draws": 1_776_000.0,
                "jackpot_ratio": 1378.0,
                "sellback_eth": 188.19,
            },
            {
                "rank": 2,
                "listing_id": 51221,
                "collection": "0x" + "44" * 20,
                "collection_name": "Fidenza",
                "token_id": 313,
                "backing_eth": 64.0,
                "odds_pct": 0.0000014,
                "expected_draws": 512_000.0,
                "jackpot_ratio": 398.5,
                "sellback_eth": 54.4,
            },
        ],
        "chase_available": True,
        # The crown and the jackpot are the same listing at this block (PRD §5).
        "crown_listing_id": 56508,
        # -- settlement + crown --------------------------------------------------
        "settlement_mix": [
            {
                "outcome": "bid_fwa",
                "label": "accept bid · $FWA",
                "count": 7392,
                "share_pct": 73.92,
            },
            {
                "outcome": "bid_eth",
                "label": "accept bid · ETH",
                "count": 1384,
                "share_pct": 13.84,
            },
            {
                "outcome": "relist",
                "label": "relist",
                "count": 764,
                "share_pct": 7.64,
            },
            {
                "outcome": "kept",
                "label": "keep the NFT",
                "count": 460,
                "share_pct": 4.60,
            },
            {
                "outcome": "forced",
                "label": "force-finalized",
                "count": 0,
                "share_pct": 0.0,
            },
        ],
        "crown_history": [
            {
                "rank": i,
                "holder": f"0x{i:040x}",
                "reigns": 5 - i,
                "payout_eth": 12.5 - i,
                "last_block": _BLOCK - i * 1000,
                "last_ts": _TS - i * 86400,
            }
            for i in range(1, 5)
        ],
        "crown_sets_total": 41,
        "crown_payouts_total": 38,
        "crown_paid_eth": 214.77,
        "settle_available": True,
        "settle_as_of_ts": float(_TS),
        # -- meta -----------------------------------------------------------------
        "active_positions": 3867,
        "core_balance_eth": 483.201,
        "cumulative_revenue_eth": 720.688,
        "take_rate_pct": 8.8,
        "current_block": _BLOCK,
        "invariants_ok": True,
        "degraded_sources": [],
        "last_updated_seconds_ago": 2.0,
        "error_count": 0,
        "poll_interval": 30,
    }


def _frozen_payload(**overrides) -> dict:
    """Exactly ``FWA_DATA_KEYS`` (plus any explicit overrides).

    Derived from the frozen contract rather than from ``_sample_data`` so a key
    added upstream shows up here automatically -- as ``None`` if the sample has
    no value for it, which is a legal payload by contract.
    """
    sample = _sample_data()
    payload = {key: sample.get(key) for key in FWA_DATA_KEYS}
    # Optional extras the manager may also carry (WP-12's crown_listing_id).
    for extra in ("crown_listing_id",):
        if extra not in payload and extra in sample:
            payload[extra] = sample[extra]
    payload.update(overrides)
    return payload


def _all_none_payload() -> dict:
    """Every contract key present, every value ``None`` (PRD §9)."""
    return {key: None for key in FWA_DATA_KEYS}


class _FakeManager:
    """Stand-in for FWAManager that never touches the network."""

    def __init__(self, payload: dict | None = None, raises: bool = False) -> None:
        self._payload = payload if payload is not None else _frozen_payload()
        self._raises = raises
        self._error_count = 3
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        if self._raises:
            raise RuntimeError("all three pools are down")
        return dict(self._payload)

    async def close(self) -> None:
        pass


class _Harness(App):
    """Push a single FWAScreen for testing (no app stylesheet)."""

    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


class _ThemedHarness(_Harness):
    """Same, but with the real ``minimal.tcss`` loaded."""

    CSS_PATH = _TCSS


def _screen_text(app) -> str:
    """Composited screen text -- what a user would actually see.

    Reaching into the compositor is the only way to prove a line is *on screen*
    rather than merely present in a widget's content: a hero box with too
    little vertical room drops its last line silently.
    """
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _plain(widget) -> str:
    visual = widget.visual
    return getattr(visual, "plain", str(visual))


def _record_dispatches(screen) -> dict[str, list[dict]]:
    """Wrap every widget's ``update_data`` so we can see what it was handed."""
    calls: dict[str, list[dict]] = {name: [] for name in _WIDGET_CLASSES}

    def _wrap(name: str, original):
        def recorder(**kwargs):
            calls[name].append(kwargs)
            return original(**kwargs)

        return recorder

    for name, cls in _WIDGET_CLASSES.items():
        widget = screen.query_one(cls)
        widget.update_data = _wrap(name, widget.update_data)

    return calls


# -- package exports ---------------------------------------------------


def test_widget_package_exports_all_seven():
    """``from maxpane_dashboard.widgets.fwa import *`` resolves all seven."""
    import maxpane_dashboard.widgets.fwa as pkg

    for name in FWA_WIDGET_SIGNATURES:
        assert name in pkg.__all__, f"{name} missing from widgets.fwa.__all__"
        assert getattr(pkg, name) is _WIDGET_CLASSES[name]


def test_bindings_are_refresh_and_the_view_toggle():
    """``c`` swaps the odds board and the activity feed in one slot.

    The feed used to occupy 3fr of the bottom row, which left the chase board
    and the settlement table ~55 columns each at a 200-column terminal --
    under what either needs for its full column set. Sharing the middle-left
    slot with the odds board instead gives the bottom row to those two alone.
    """
    keys = {binding.key for binding in FWAScreen.BINDINGS}
    assert keys == {"r", "c"}


# -- mount / refresh ----------------------------------------------------


async def test_screen_mounts_and_refreshes():
    manager = _FakeManager()
    screen = FWAScreen(manager, poll_interval=30, name="fwa")
    app = _Harness(screen)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()

        # All seven widgets composed, in their canonical slots.
        for cls in _WIDGET_CLASSES.values():
            screen.query_one(cls)
        assert screen.query_one("#middle-row").children
        assert screen.query_one("#right-col").children
        assert len(screen.query_one("#bottom-row").children) == 2

        await screen._do_refresh()
        await pilot.pause()
        assert manager.calls >= 1

        text = _screen_text(app)
        assert "FWA · 3,867 positions" in text
        assert "ETH in core" in text
        assert "ODDS BOARD" in text
        assert "CHASE BOARD" in text
        assert "SETTLEMENT & CROWN" in text


async def test_screen_dispatches_every_data_key():
    """Every ``FWA_DATA_KEYS`` group reaches the widget that owns it."""
    manager = _FakeManager()
    screen = FWAScreen(manager, poll_interval=30, name="fwa")
    app = _Harness(screen)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        calls = _record_dispatches(screen)
        await screen._do_refresh()
        await pilot.pause()

        dispatched: set[str] = set()
        for name, signature in FWA_WIDGET_SIGNATURES.items():
            assert calls[name], f"{name}.update_data was never called"
            kwargs = calls[name][-1]
            # Exactly the frozen signature -- plus, for the chase board only,
            # the optional crown_listing_id extra.
            allowed = set(signature)
            if name == "FWAChaseBoard":
                allowed |= {"crown_listing_id"}
            assert set(kwargs) <= allowed, f"{name} got unexpected kwargs"
            assert set(signature) <= set(kwargs), f"{name} missing frozen kwargs"
            dispatched |= set(kwargs)

        # Nothing in the contract goes unrendered: it is either a widget kwarg
        # or a meta key the screen itself consumes.
        unconsumed = set(FWA_DATA_KEYS) - dispatched - META_KEYS
        assert not unconsumed, f"contract keys reach no widget: {sorted(unconsumed)}"

        # ...and the meta keys really are on screen.
        text = _screen_text(app)
        assert "3,867 positions" in text          # active_positions
        assert "483.201 ETH in core" in text      # core_balance_eth
        assert "fee 0.1247 ETH" in text           # acquisition_fee_eth
        assert "rev 720.69 ETH" in text           # cumulative_revenue_eth
        assert "take 8.80%" in text               # take_rate_pct
        assert "30s poll" in text                 # poll_interval
        assert "updated 2s ago" in text           # last_updated_seconds_ago


async def test_screen_survives_manager_exception():
    """The screen stands; only the StatusBar is marked."""
    manager = _FakeManager(raises=True)
    screen = FWAScreen(manager, poll_interval=30, name="fwa")
    app = _Harness(screen)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await screen._do_refresh()   # must not raise
        await pilot.pause()

        status = screen.query_one(StatusBar).query_one("#status-left")
        rendered = _plain(status)
        assert "updated 999s ago" in rendered
        assert "3 errors" in rendered  # manager's _error_count is surfaced

        # The title bar was not half-overwritten with a broken frame.
        assert "Gacha Terminal" in _plain(screen.query_one("#title-bar"))
        # Every widget is still mounted and rendering.
        text = _screen_text(app)
        assert "ODDS BOARD" in text
        assert "SETTLEMENT & CROWN" in text


async def test_screen_survives_all_none_payload():
    """PRD §9: an all-``None`` payload renders explicit unavailable states."""
    manager = _FakeManager(payload=_all_none_payload())
    screen = FWAScreen(manager, poll_interval=30, name="fwa")
    app = _Harness(screen)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await screen._do_refresh()   # must not raise
        await pilot.pause()

        text = _screen_text(app)
        # Title bar degrades to em-dashes rather than inventing zeros.
        assert "FWA · — positions" in text
        # Widgets state that they have nothing, rather than going blank.
        assert "insufficient data" in text     # PULL EV
        assert "no collections" in text        # odds board
        assert "No draws" in text or "unavailable" in text  # feed
        # A dead payload never claims a healthy poll.
        assert "0s poll" in text or "poll" in text


async def test_all_none_payload_still_shows_ev_coverage_badge():
    """No EV number is on screen, but the badge frame still is (PRD §3)."""
    manager = _FakeManager(payload=_all_none_payload())
    screen = FWAScreen(manager, poll_interval=30, name="fwa")
    app = _Harness(screen)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        assert "of weight priced" in _screen_text(app)


# -- the clipping trap --------------------------------------------------


async def test_ev_coverage_badge_reaches_the_compositor():
    """The badge must be *on screen*, not merely in the widget's content."""
    manager = _FakeManager()
    screen = FWAScreen(manager, poll_interval=30, name="fwa")
    app = _Harness(screen)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        text = _screen_text(app)
        assert "22/38 · 61.3% of weight priced" in text
        # The EV number and its coverage are inseparable: if one is visible so
        # is the other.
        assert "-0.0163" in text


async def test_ev_coverage_badge_survives_the_real_stylesheet():
    """Same assertion with ``minimal.tcss`` loaded.

    ``FWAHeroBox`` is ``height: 7`` with a border, leaving four content rows
    for four lines. Any theme rule that gives it ``padding: 1 2`` (as the
    Talismans block does, and as WP-16's brief currently reads) drops the
    fourth line -- the coverage badge -- and this test is where that shows up.
    """
    manager = _FakeManager()
    screen = FWAScreen(manager, poll_interval=30, name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        assert "of weight priced" in _screen_text(app)


# -- optional crown_listing_id (WP-12, in flight) -----------------------


async def test_chase_board_gets_crown_listing_id_when_present():
    manager = _FakeManager(payload=_frozen_payload(crown_listing_id=56508))
    screen = FWAScreen(manager, poll_interval=30, name="fwa")
    app = _Harness(screen)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        calls = _record_dispatches(screen)
        await screen._do_refresh()
        await pilot.pause()
        assert calls["FWAChaseBoard"][-1]["crown_listing_id"] == 56508
        assert "crown and chase" in _screen_text(app)


async def test_screen_tolerates_missing_crown_listing_id():
    """The key is not in the frozen contract yet; its absence must be fine."""
    payload = _frozen_payload()
    payload.pop("crown_listing_id", None)
    manager = _FakeManager(payload=payload)
    screen = FWAScreen(manager, poll_interval=30, name="fwa")
    app = _Harness(screen)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        calls = _record_dispatches(screen)
        await screen._do_refresh()   # must not raise
        await pilot.pause()
        assert "crown_listing_id" not in calls["FWAChaseBoard"][-1]
        # Nothing is claimed about the coincidence either way.
        assert "crown and chase" not in _screen_text(app)


# -- degradation is rendered, not swallowed -----------------------------


async def test_degraded_sources_and_invariant_break_reach_the_title_bar():
    manager = _FakeManager(
        payload=_frozen_payload(
            degraded_sources=["logs", "market"],
            invariants_ok=False,
            odds_stale=True,
        )
    )
    screen = FWAScreen(manager, poll_interval=30, name="fwa")
    app = _Harness(screen)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        text = _screen_text(app)
        assert "degraded: logs, market" in text
        assert "invariant mismatch" in text
        # The odds board says stale rather than pretending to be live.
        assert "STALE" in text


# -- the emissions stop, from fixtures only -----------------------------


async def test_emissions_state_is_data_driven_not_wall_clock():
    """Both sides of 2026-08-04T19:01:23Z, neither derived from ``now``."""
    for signal, expected in (
        (EMISSIONS_ENDED_SIGNAL, "emissions ended · 21d ago"),  # the primary case
        (EMISSIONS_LIVE_SIGNAL, "emissions live · 8d 4h left"),
    ):
        manager = _FakeManager(payload=_frozen_payload(emissions_signal=signal))
        screen = FWAScreen(manager, poll_interval=30, name="fwa")
        app = _Harness(screen)
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            await screen._do_refresh()
            await pilot.pause()
            assert expected in _screen_text(app)


# -- lifecycle -----------------------------------------------------------


async def test_screen_resume_sets_status_bar_labels_and_starts_timer():
    manager = _FakeManager()
    screen = FWAScreen(manager, poll_interval=30, name="fwa")
    app = _Harness(screen)
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        status = screen.query_one(StatusBar)
        assert status._game_name == "fwa"
        assert status._theme_name == app.theme
        assert screen._refresh_timer is not None

        screen.on_screen_suspend()
        assert screen._refresh_timer is None


# -- the odds / activity toggle -----------------------------------------


async def test_c_swaps_the_odds_board_and_the_activity_feed():
    """One slot, two views, mutually exclusive at every step."""
    screen = FWAScreen(_FakeManager(), poll_interval=30, name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        text = _screen_text(app)
        assert "ODDS BOARD" in text and "ACTIVITY" not in text
        assert screen._active_view == "odds"

        await pilot.press("c")
        await pilot.pause()
        text = _screen_text(app)
        assert "ACTIVITY" in text and "ODDS BOARD" not in text
        assert screen._active_view == "activity"

        await pilot.press("c")
        await pilot.pause()
        text = _screen_text(app)
        assert "ODDS BOARD" in text and "ACTIVITY" not in text
        assert screen._active_view == "odds"


async def test_the_bottom_row_is_unaffected_by_the_toggle():
    """The chase board and settlement table are always on screen.

    They are the reason the feed moved; a toggle that hid one of them would
    have defeated the change.
    """
    screen = FWAScreen(_FakeManager(), poll_interval=30, name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        for _ in range(3):
            text = _screen_text(app)
            assert "CHASE BOARD" in text
            assert "SETTLEMENT" in text
            await pilot.press("c")
            await pilot.pause()


async def test_the_hidden_view_still_receives_updates():
    """Both widgets are mounted and dispatched to, whichever is showing.

    Creating the feed on demand would leave it empty for a beat after the
    first toggle, which reads as a bug. This asserts the feed has content
    *before* it is ever shown.
    """
    screen = FWAScreen(_FakeManager(), poll_interval=30, name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        calls = _record_dispatches(screen)
        await screen._do_refresh()
        await pilot.pause()

        assert calls["FWAActivityFeed"], "the hidden feed was never updated"
        assert calls["FWAOddsBoard"]

        # and it renders immediately on the very first toggle
        await pilot.press("c")
        await pilot.pause()
        assert "ACTIVITY" in _screen_text(app)


async def test_the_toggle_survives_a_missing_widget():
    """A toggle must never take the screen down.

    Guarded because the view flip runs outside the refresh path's per-widget
    try/except.
    """
    screen = FWAScreen(_FakeManager(), poll_interval=30, name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        screen.query_one(FWAOddsBoard).remove()
        await pilot.pause()

        screen.action_toggle_view()  # must not raise
        await pilot.pause()

        assert screen._active_view == "activity"


async def test_the_status_bar_names_the_active_view():
    """Same affordance Talismans and TTT use, so `c` is discoverable."""
    screen = FWAScreen(_FakeManager(), poll_interval=30, name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        seen = []
        bar = screen.query_one(StatusBar)
        original = bar.set_active_view
        bar.set_active_view = lambda v: (seen.append(v), original(v))[1]

        screen.action_toggle_view()
        await pilot.pause()

        assert seen == ["activity"]


async def test_both_views_get_the_identical_slot():
    """The toggle must not resize the panel underneath it.

    The feed's ``width: 3fr`` against ``#right-col``'s ``2fr`` is the odds
    board's own ratio, which is the whole reason moving the feed between rows
    needed no stylesheet change. Give either widget a different width and the
    layout jumps on every ``c`` press -- so this measures both under the real
    stylesheet rather than trusting the numbers to stay equal.
    """
    screen = FWAScreen(_FakeManager(), poll_interval=30, name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        odds_size = screen.query_one(FWAOddsBoard).size

        await pilot.press("c")
        await pilot.pause()
        feed_size = screen.query_one(FWAActivityFeed).size

        assert (feed_size.width, feed_size.height) == (odds_size.width, odds_size.height), (
            f"feed occupies {feed_size} where the odds board occupied "
            f"{odds_size} -- the panel resizes on every toggle"
        )
        assert feed_size.height > 1, "the feed collapsed instead of filling the row"
