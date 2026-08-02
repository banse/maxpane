"""Headless Textual tests for FWA widgets A (WP-10).

Covers ``FWAHeroMetrics``, ``FWAOddsBoard`` and ``FWASparkline``.  WP-11's
widgets (signals, activity feed, chase board, settlement table) live in
``test_fwa_widgets_b.py``.

Each widget is mounted in a tiny ``App`` via ``App.run_test()`` and
``update_data()`` is exercised three ways -- no args, an all-``None``
payload, and a representative full payload -- none of which may raise.
On top of that we assert the honesty rules the PRD makes mandatory:

* the Pull EV band never renders a number without its coverage badge,
* the EV sign is carried by a glyph and not by colour alone,
* a vacant crown renders ``vacant`` and never ``0``,
* an unpriced collection is marked unpriced and never shown as ``0``,
* the harmonic/arithmetic gap is whatever the payload says at this
  block -- the widget has no constant to fall back on,
* a short price history degrades rather than being padded with invented
  low candles.

Zero network. Text assertions read ``Static.visual.plain``, i.e. the
*rendered* text with markup stripped -- so a glyph asserted here is real
text on screen, not a colour tag.
"""

from __future__ import annotations

import inspect

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from maxpane_dashboard.data.fwa_models import FWA_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fwa.fwa_hero_metrics import FWAHeroMetrics
from maxpane_dashboard.widgets.fwa.fwa_odds_board import FWAOddsBoard
from maxpane_dashboard.widgets.fwa.fwa_sparkline import FWASparkline


class _Harness(App):
    """Mount a single widget instance so we can drive ``update_data``."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _plain(widget, selector: str) -> str:
    """Rendered text of a child ``Static``, markup stripped."""
    child = widget.query_one(selector, Static)
    visual = child.visual
    return getattr(visual, "plain", str(visual))


def _screen_text(app) -> str:
    """Composited screen text -- what a user would actually see.

    Reaching into the compositor is the only way to prove a line is *on
    screen* rather than merely present in the widget's content: a hero box
    with too little vertical room drops its last line silently, which is
    precisely how a Pull EV number could end up rendered without its
    coverage badge.
    """
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _sig_names(func) -> tuple[str, ...]:
    return tuple(
        name
        for name, param in inspect.signature(func).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    )


def _odds_rows(count: int = 38) -> list[dict]:
    """A realistic odds payload: TTT on top, Punks rich but unreachable.

    Shares are the 6-dp values the manager produces; they sum to slightly
    over 100 by design and nothing here asserts otherwise (PRD §5).
    """
    rows = [
        {
            "rank": 1,
            "address": "0x" + "11" * 20,
            "name": "Ten Thousand Tokens",
            "positions": 1847,
            "weight_share_pct": 49.082800,
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
            "weight_share_pct": 11.204311,
            "eth_backed": 88.1200,
            "floor_eth": None,
            "floor_source": "suppressed",
            "eth_per_odds_point": None,
            "floor_note": "multi-collection contract — floor not meaningful",
        },
        {
            "rank": 3,
            "address": "0x" + "33" * 20,
            "name": "Unpriced Thing",
            "positions": 51,
            "weight_share_pct": 3.771002,
            "eth_backed": 12.5000,
            "floor_eth": None,
            "floor_source": "missing",
            "eth_per_odds_point": None,
            "floor_note": "",
        },
    ]
    for i in range(4, count):
        rows.append(
            {
                "rank": i,
                "address": f"0x{i:040x}",
                "name": f"Collection {i}",
                "positions": max(1, 40 - i),
                "weight_share_pct": round(3.0 - i * 0.07, 6),
                "eth_backed": 5.0 + i,
                "floor_eth": 0.1 + i / 100,
                "floor_source": "coingecko",
                "eth_per_odds_point": 1.5 + i,
                "floor_note": "",
            }
        )
    # CryptoPunks last: 137 ETH of backing for 0.000% of the draw.
    rows.append(
        {
            "rank": count,
            "address": "0x" + "99" * 20,
            "name": "CryptoPunks",
            "positions": 3,
            "weight_share_pct": 0.00023,
            "eth_backed": 137.1000,
            "floor_eth": 42.5,
            "floor_source": "coingecko",
            "eth_per_odds_point": 596086.9,
            "floor_note": "",
        }
    )
    return rows[:count]


_FULL_HERO = {
    "pull_ev_best_eth": -0.024311,
    "pull_ev_lower_eth": -0.116876,
    "ev_available": True,
    "ev_collections_priced": 22,
    "ev_collections_total": 38,
    "ev_weight_priced_pct": 61.4,
    "ev_rebate_eth": 0.0,
    "acquisition_fee_eth": 0.116876,
    "vrf_fee_eth": 0.00104,
    "quote_total_eth": 0.117916,
    "price_available": True,
    "harmonic_mean_eth": 0.106251,
    "arithmetic_mean_eth": 0.370878,
    "hm_am_gap_x": 3.4906,
    "crown_pot_eth": 12.3456,
    "crown_pot_usd": 41230.0,
    "crown_seize_eth": 243.1,
    "crown_holder": "0xabcdef0123456789abcdef0123456789abcdef01",
    "crown_vacant": False,
    "crown_available": True,
}


# ---------------------------------------------------------------------
# contract conformance
# ---------------------------------------------------------------------


def test_update_data_kwargs_match_frozen_signatures():
    """Every kwarg name matches ``FWA_WIDGET_SIGNATURES`` exactly."""
    for cls in (FWAHeroMetrics, FWAOddsBoard, FWASparkline):
        expected = FWA_WIDGET_SIGNATURES[cls.__name__]
        assert _sig_names(cls.update_data) == expected, cls.__name__


def test_widget_modules_import_no_data_layer():
    """Widgets take primitives only -- no models, client or analytics."""
    import ast

    import maxpane_dashboard.widgets.fwa.fwa_hero_metrics as hero
    import maxpane_dashboard.widgets.fwa.fwa_odds_board as odds
    import maxpane_dashboard.widgets.fwa.fwa_sparkline as spark

    for module in (hero, odds, spark):
        tree = ast.parse(inspect.getsource(module))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        for name in imported:
            assert "maxpane_dashboard.data" not in name, (module.__name__, name)
            assert "analytics" not in name, (module.__name__, name)
            assert "fwa_client" not in name, (module.__name__, name)


# ---------------------------------------------------------------------
# hero metrics
# ---------------------------------------------------------------------


async def test_hero_no_args_and_all_none_render_dashes():
    widget = FWAHeroMetrics()
    async with _Harness(widget).run_test():
        widget.update_data()
        widget.update_data(
            **{k: None for k in FWA_WIDGET_SIGNATURES["FWAHeroMetrics"]}
        )
        for box_id in ("#fwa-hero-ev", "#fwa-hero-price", "#fwa-hero-crown"):
            text = _plain(widget, box_id)
            assert "Loading" not in text
            assert "—" in text or "--" in text


async def test_hero_renders_band_and_coverage():
    widget = FWAHeroMetrics()
    async with _Harness(widget).run_test():
        widget.update_data(**_FULL_HERO)
        text = _plain(widget, "#fwa-hero-ev")
        # Best estimate and lower bound are both on screen ...
        assert "-0.0243" in text
        assert "lower" in text and "-0.1169" in text
        # ... with the coverage badge underneath.
        assert "22/38" in text
        assert "of weight priced" in text
        # And no single confident point value anywhere.
        assert "point" not in text.lower()


async def test_hero_never_shows_ev_without_coverage_badge():
    """An EV number may never appear without its coverage badge."""
    variants = [
        _FULL_HERO,
        {**_FULL_HERO, "pull_ev_best_eth": 0.0813, "ev_available": None},
        {**_FULL_HERO, "pull_ev_best_eth": 0.0},
        # coverage counters missing -> badge degrades, but is still there
        {
            **_FULL_HERO,
            "ev_collections_priced": None,
            "ev_collections_total": None,
            "ev_weight_priced_pct": None,
        },
        {**_FULL_HERO, "pull_ev_lower_eth": None, "ev_rebate_eth": 0.0021},
    ]
    widget = FWAHeroMetrics()
    async with _Harness(widget).run_test():
        for payload in variants:
            widget.update_data(**payload)
            text = _plain(widget, "#fwa-hero-ev")
            assert "of weight priced" in text, payload

        # ... and when there is no EV at all, say so explicitly.
        widget.update_data(**{**_FULL_HERO, "ev_available": False})
        text = _plain(widget, "#fwa-hero-ev")
        assert "insufficient data" in text
        assert "—" in text


async def test_hero_coverage_badge_reads_zero_coverage_and_no_pool_differently():
    """Zero coverage is a fact; a zero total is a missing reading (WP-20).

    Two states that used to render as confident zeros:

    * **Zero coverage, live pool** -- ``0/3 · 0.0% of weight priced``. This is
      correct and stays. The keyless floor sources cover none of the three
      collections, and the EV beside it is still meaningful: at zero coverage
      ``best_eth`` degrades to the sell-back-minus-fee expectation, which is
      computed entirely from on-chain backing and does not depend on a floor at
      all. The badge is the disclosure that makes it readable, so the number
      keeps its place.
    * **Zero total, dead chain** -- ``0/0 · 0.0%`` claimed that none of a pool's
      weight was priced when no pool had been read. That now renders as dashes,
      the same as any other missing reading.
    """
    widget = FWAHeroMetrics()
    async with _Harness(widget).run_test():
        # Live pool, nothing priced: real denominator, real 0.0%.
        widget.update_data(
            **{
                **_FULL_HERO,
                "ev_collections_priced": 0,
                "ev_collections_total": 3,
                "ev_weight_priced_pct": 0.0,
            }
        )
        text = _plain(widget, "#fwa-hero-ev")
        assert "0/3 · 0.0% of weight priced" in text, text
        assert "-0.0243" in text, "the sell-back expectation still renders"

        # Dead chain: no pool was read, so there is no coverage to report.
        widget.update_data(
            **{
                **_FULL_HERO,
                "ev_available": False,
                "ev_collections_priced": 0,
                "ev_collections_total": 0,
                "ev_weight_priced_pct": 0.0,
            }
        )
        text = _plain(widget, "#fwa-hero-ev")
        assert "0/0" not in text, (
            "a zero total is a missing reading, not a priced-nothing pool: " + text
        )
        assert "--/-- · --% of weight priced" in text, text
        assert "of weight priced" in text, "the badge is never dropped (PRD §3)"


async def test_hero_coverage_badge_is_visible_on_screen():
    """The badge must survive layout, not just live in the content string.

    Four lines in a 7-high card only fit while the vertical padding is 0;
    ``padding: 1 2`` would clip the badge off the bottom (see the note on
    ``FWAHeroMetrics.DEFAULT_CSS``).
    """
    widget = FWAHeroMetrics()
    app = _Harness(widget)
    async with app.run_test(size=(140, 12)) as pilot:
        widget.update_data(**_FULL_HERO)
        await pilot.pause()
        screen = _screen_text(app)
        assert "-0.0243" in screen
        assert "of weight priced" in screen
        assert "to seize" in screen


async def test_hero_ev_sign_has_glyph_not_only_color():
    """Sign survives greyscale: a glyph plus an explicit +/- (PRD §11)."""
    widget = FWAHeroMetrics()
    async with _Harness(widget).run_test():
        widget.update_data(**{**_FULL_HERO, "pull_ev_best_eth": 0.0813})
        up = _plain(widget, "#fwa-hero-ev")
        assert "▲" in up
        assert "+0.0813" in up

        widget.update_data(**{**_FULL_HERO, "pull_ev_best_eth": -0.0243})
        down = _plain(widget, "#fwa-hero-ev")
        assert "▼" in down
        assert "-0.0243" in down

        assert up != down


async def test_hero_crown_vacant_renders_vacant_not_zero():
    widget = FWAHeroMetrics()
    async with _Harness(widget).run_test():
        widget.update_data(
            **{
                **_FULL_HERO,
                "crown_vacant": True,
                "crown_pot_eth": 0.0,
                "crown_pot_usd": None,
                "crown_holder": None,
            }
        )
        text = _plain(widget, "#fwa-hero-crown")
        assert "vacant" in text
        assert "0.000" not in text

        # occupied crown: pot in ETH and USD, plus the seize price
        widget.update_data(**_FULL_HERO)
        text = _plain(widget, "#fwa-hero-crown")
        assert "12.346" in text
        assert "$41,230" in text
        assert "to seize" in text and "243.100" in text

        # unavailable crown is explicit, not a zero pot
        widget.update_data(**{**_FULL_HERO, "crown_available": False})
        assert "crown unavailable" in _plain(widget, "#fwa-hero-crown")


async def test_hero_price_gap_is_live_never_hardcoded():
    widget = FWAHeroMetrics()
    async with _Harness(widget).run_test():
        widget.update_data(**_FULL_HERO)
        first = _plain(widget, "#fwa-hero-price")
        assert "0.1169" in first          # live acquisition fee
        assert "3.49×" in first           # the gap as measured right now

        # a different block, a different gap -- nothing is pinned
        widget.update_data(
            **{
                **_FULL_HERO,
                "harmonic_mean_eth": 0.123874,
                "arithmetic_mean_eth": 0.481327,
                "hm_am_gap_x": 3.885,
            }
        )
        second = _plain(widget, "#fwa-hero-price")
        assert "3.88×" in second
        assert "3.49×" not in second

        # gap absent from the payload -> computed from the two live means
        widget.update_data(**{**_FULL_HERO, "hm_am_gap_x": None})
        assert "3.49×" in _plain(widget, "#fwa-hero-price")

        # no means at all -> no invented multiple
        widget.update_data(
            **{
                **_FULL_HERO,
                "harmonic_mean_eth": None,
                "arithmetic_mean_eth": None,
                "hm_am_gap_x": None,
            }
        )
        assert "×" not in _plain(widget, "#fwa-hero-price")


async def test_hero_vrf_leg_only_when_tuple_says_nonzero():
    widget = FWAHeroMetrics()
    async with _Harness(widget).run_test():
        widget.update_data(**_FULL_HERO)
        assert "vrf 0.0010" in _plain(widget, "#fwa-hero-price")

        widget.update_data(**{**_FULL_HERO, "vrf_fee_eth": 0.0})
        assert "vrf" not in _plain(widget, "#fwa-hero-price")

        widget.update_data(**{**_FULL_HERO, "vrf_fee_eth": None})
        assert "vrf" not in _plain(widget, "#fwa-hero-price")

        widget.update_data(**{**_FULL_HERO, "price_available": False})
        assert "quote unavailable" in _plain(widget, "#fwa-hero-price")


# ---------------------------------------------------------------------
# odds board
# ---------------------------------------------------------------------


async def test_odds_board_no_args_and_all_none():
    widget = FWAOddsBoard()
    async with _Harness(widget).run_test():
        widget.update_data()
        table = widget.query_one(DataTable)
        assert table.row_count == 1  # "No data"
        widget.update_data(
            **{k: None for k in FWA_WIDGET_SIGNATURES["FWAOddsBoard"]}
        )
        assert table.row_count == 1


async def test_odds_board_row_count_and_sort():
    widget = FWAOddsBoard()
    async with _Harness(widget).run_test():
        rows = _odds_rows(38)
        # hand them over unsorted -- the board sorts by weight share desc
        shuffled = rows[5:] + rows[:5]
        widget.update_data(
            collection_odds=shuffled,
            odds_available=True,
            odds_as_of_block=25621114,
            odds_stale=False,
        )
        table = widget.query_one(DataTable)
        assert table.row_count == 38

        first = [str(c) for c in table.get_row_at(0)]
        last = [str(c) for c in table.get_row_at(37)]
        assert "Ten Thousand" in first[1]  # truncated to the column
        assert "49.083%" in first[3]
        # the tension: rich collection, no odds
        assert "CryptoPunks" in last[1]
        assert "0.000%" in last[3]
        assert "137.10" in last[4]

        # shares descend all the way down
        shares = [
            float(str(table.get_row_at(i)[3]).replace("[bold]", "")
                  .replace("[/]", "").rstrip("%"))
            for i in range(table.row_count)
        ]
        assert shares == sorted(shares, reverse=True)

        meta = _plain(widget, "#fwa-odds-title")
        assert "38 collections" in meta
        assert "25,621,114" in meta


async def test_odds_board_missing_floor_renders_dash():
    widget = FWAOddsBoard()
    async with _Harness(widget).run_test():
        widget.update_data(
            collection_odds=_odds_rows(38), odds_available=True
        )
        table = widget.query_one(DataTable)
        row = [str(c) for c in table.get_row_at(2)]  # "Unpriced Thing"
        assert "Unpriced Thing" in row[1]
        assert row[5] == "—"          # floor, not 0
        assert "0" not in row[5]
        assert row[6] == "—"          # eth per odds point, not 0


async def test_odds_board_suppressed_floor_renders_note():
    widget = FWAOddsBoard()
    async with _Harness(widget).run_test():
        widget.update_data(
            collection_odds=_odds_rows(38), odds_available=True
        )
        table = widget.query_one(DataTable)
        row = [str(c) for c in table.get_row_at(1)]  # "Art Blocks"
        assert "n/a*" in row[5]
        # The note explaining the `*` is the lowest-priority part of the title
        # and is dropped first when the panel is narrow, so it is asserted
        # against the text the widget builds rather than against a rendering
        # at whatever width this harness happens to use.
        title = widget._title_for(38, None, False, "multi-collection contract")
        assert "multi-collection" in title
        assert title.startswith("ODDS BOARD")


async def test_odds_board_unavailable_and_stale_states():
    widget = FWAOddsBoard()
    async with _Harness(widget).run_test():
        widget.update_data(collection_odds=[], odds_available=False)
        table = widget.query_one(DataTable)
        assert table.row_count == 1
        assert "unavailable" in str(table.get_row_at(0)[1])
        assert "odds unavailable" in _plain(widget, "#fwa-odds-title")

        widget.update_data(
            collection_odds=_odds_rows(5),
            odds_available=True,
            odds_as_of_block=25621114,
            odds_stale=True,
        )
        assert "STALE" in _plain(widget, "#fwa-odds-title")


async def test_odds_board_tolerates_malformed_rows():
    widget = FWAOddsBoard()
    async with _Harness(widget).run_test():
        widget.update_data(
            collection_odds=[
                None,
                "not a dict",
                {},
                {"name": None, "address": None, "weight_share_pct": None},
                {"name": "Ok", "weight_share_pct": 1.0, "eth_backed": "n/a"},
            ],
            odds_available=True,
        )
        table = widget.query_one(DataTable)
        assert table.row_count == 3


# ---------------------------------------------------------------------
# sparkline
# ---------------------------------------------------------------------


async def test_sparkline_no_args_and_all_none():
    widget = FWASparkline()
    async with _Harness(widget).run_test():
        widget.update_data()
        widget.update_data(
            **{k: None for k in FWA_WIDGET_SIGNATURES["FWASparkline"]}
        )
        assert "waiting for data" in _plain(widget, "#fwa-spark-price")


async def test_sparkline_short_series_waiting():
    widget = FWASparkline()
    async with _Harness(widget).run_test():
        widget.update_data(fwa_price_history=[])
        assert "waiting for data" in _plain(widget, "#fwa-spark-price")

        widget.update_data(
            fwa_price_history=[[1_760_000_000, 0.00012]],
            fwa_price_usd=0.00012,
        )
        text = _plain(widget, "#fwa-spark-price")
        assert "waiting for data" in text
        assert "$0.00012000" in text


async def test_sparkline_degrades_when_history_shorter_than_window():
    """Fewer candles than the bar width: pad with space, never with ▁."""
    widget = FWASparkline()
    async with _Harness(widget).run_test():
        points = [[1_760_000_000 + i * 3600, 0.0001 + i * 1e-6] for i in range(6)]
        widget.update_data(
            fwa_price_history=points,
            fwa_price_usd=0.000105,
            fwa_price_change_24h=4.21,
        )
        bar = _plain(widget, "#fwa-spark-price")
        # exactly the six real candles are drawn; the rest is blank
        assert bar.count("▁") == 1          # the series' own minimum
        assert "  " in bar
        meta = _plain(widget, "#fwa-spark-meta")
        assert "6 candles" in meta
        assert "short history" in meta
        assert "▲" in meta and "+4.21%" in meta


async def test_sparkline_full_history_and_change_sign():
    widget = FWASparkline()
    async with _Harness(widget).run_test():
        # ~100 hourly candles, i.e. the whole life of the v4 pool
        points = [
            [1_760_000_000 + i * 3600, 0.0001 + (i % 17) * 2e-6]
            for i in range(100)
        ]
        widget.update_data(
            fwa_price_history=points,
            fwa_price_usd=0.00013,
            fwa_price_change_24h=-3.1,
            spark_available=True,
        )
        bar = _plain(widget, "#fwa-spark-price")
        assert "$0.00013000" in bar
        meta = _plain(widget, "#fwa-spark-meta")
        assert "100 candles" in meta
        assert "4.2d" in meta
        assert "short history" not in meta
        assert "▼" in meta and "-3.10%" in meta


async def test_sparkline_unavailable_state():
    widget = FWASparkline()
    async with _Harness(widget).run_test():
        widget.update_data(
            fwa_price_history=None,
            fwa_price_usd=None,
            fwa_price_change_24h=None,
            spark_available=False,
        )
        assert "price feed unavailable" in _plain(widget, "#fwa-spark-price")
        assert "no market data" in _plain(widget, "#fwa-spark-meta")
