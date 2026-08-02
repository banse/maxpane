"""Accessibility guardrails for the FWA dashboard (WP-19).

Everything here is measured against **composited output** --
``Screen._compositor.render_strips()`` -- rather than against source markup.
That distinction is the whole point of this file: the defect it locks down was
a colour that reached the pixel as something other than what the source said.

Three separate markup dialects reach the FWA screen and they do *not* accept
the same tokens. Getting this wrong is silent in two of the three cases:

===================  ==========================  ==========================
Surface              ``[green]`` resolves to     ``[$success]``
===================  ==========================  ==========================
``Static``/Content   CSS name table -> #008000   theme variable, per theme
``RichLog``          ANSI theme -> #98e024       **raises MarkupError**
``DataTable`` cell   ANSI theme -> #98e024       **raises MarkupError**
===================  ==========================  ==========================

``#008000``'s contrast peaks at 4.09:1 against pure black, so in Content markup
``green`` fails WCAG 1.4.3 (4.5:1) on *every* background that can exist -- no
palette can rescue it. In a ``RichLog`` the same tag is fine (7.18-10.57 across
the ten themes) but ``red`` is not (#f4005f, 2.76-4.07). So the correct token
depends on the surface, and each is asserted where it belongs.

Zero network access.
"""

from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.analytics import fwa_signals as sig
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.fwa.fwa_chase_board import _GOLD as CHASE_GOLD
from maxpane_dashboard.widgets.fwa.fwa_hero_metrics import (
    CROWN_GOLD,
    FWAHeroBox,
    FWAHeroMetrics,
    _ev_sign,
)
from maxpane_dashboard.widgets.fwa.fwa_signals import FWASignals
from maxpane_dashboard.widgets.fwa.fwa_sparkline import _fmt_change

pytestmark = pytest.mark.asyncio

#: Textual's CSS name table values for the names this dashboard must not use in
#: ``Static``/Content markup. Asserted as *rendered* colours, so a future
#: ``[green]`` reintroduced anywhere upstream is caught by its pixel value.
CSS_GREEN = "#008000"
CSS_RED = "#ff0000"

#: WCAG 2.2 AA, 1.4.3 Contrast (Minimum), normal text.
AA = 4.5

#: Four registered themes declare an ``error`` that cannot reach 4.5:1 on their
#: own surface: matrix #ff0040 (3.81), minimal #e64c3c (4.14), bakery #e5719a
#: (4.43) and frenpet #e57272 (4.43); bakery's ``success`` is #1b96ca (3.87).
#: Those are deliberate brand palettes shared by all nine dashboards, so they
#: are not FWA's to change -- and the EV sign carries a ``▲``/``▼`` glyph plus
#: an explicit ``+``/``-`` regardless, so no information is lost. What FWA
#: *must* guarantee is that it never drops below the 3:1 floor and never falls
#: back to the CSS names, which is what this constant encodes.
AA_LARGE = 3.0


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class _Harness(App):
    """Mount one widget under a chosen registered theme."""

    def __init__(self, widget, theme: str = "fwa") -> None:
        super().__init__()
        self._widget = widget
        self._theme_name = theme

    def compose(self):
        yield self._widget

    def on_mount(self) -> None:
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = self._theme_name


def _srgb(channel: float) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _srgb(r) + 0.7152 * _srgb(g) + 0.0722 * _srgb(b)


def contrast(fg: str, bg: str) -> float:
    """WCAG 2.x relative-contrast ratio between two ``#rrggbb`` colours."""
    a, b = _luminance(fg), _luminance(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def composited(app, needle: str) -> tuple[str, str] | None:
    """``(fg, bg)`` of the first painted segment containing ``needle``.

    Reads the compositor, so it returns the colour that actually reached the
    screen -- markup resolution, theme, CSS and layout all already applied.
    """
    for strip in app.screen._compositor.render_strips():
        for segment in strip:
            if needle not in segment.text:
                continue
            style = segment.style
            if not style or not style.color or not style.bgcolor:
                continue
            return (
                style.color.get_truecolor().hex,
                style.bgcolor.get_truecolor().hex,
            )
    return None


_HERO = {
    "pull_ev_best_eth": -0.0243,
    "pull_ev_lower_eth": -0.0410,
    # WP-20: these four were ``pull_ev_available`` / ``priced_collections`` /
    # ``total_collections`` / ``priced_weight_pct`` -- none of which
    # ``FWAHeroMetrics.update_data`` accepts, so all four were swallowed by
    # ``**_kwargs`` and the coverage badge was measured as ``--/-- · --%``
    # rather than as the real ``22/38 · 61.3%``. Names taken from
    # ``FWA_WIDGET_SIGNATURES["FWAHeroMetrics"]``.
    "ev_available": True,
    "ev_collections_priced": 22,
    "ev_collections_total": 38,
    "ev_weight_priced_pct": 61.3,
    "acquisition_fee_eth": 0.037,
    "vrf_fee_eth": 0.0006,
    "quote_total_eth": 0.0376,
    "price_available": True,
    "crown_pot_eth": 3.221,
    "crown_seize_eth": 0.221,
    "crown_holder": "0x1234567890abcdef1234567890abcdef12345678",
    "crown_vacant": False,
    "crown_available": True,
}


def test_contrast_helper_matches_the_published_reference_values():
    """Guard the ruler before trusting anything measured with it.

    Both are quoted in W3C's own material: white on black is exactly 21:1, and
    #008000 against pure black -- the ceiling this whole file is about -- is
    4.09:1.
    """
    assert contrast("#ffffff", "#000000") == pytest.approx(21.0, abs=0.01)
    assert contrast(CSS_GREEN, "#000000") == pytest.approx(4.09, abs=0.01)
    assert contrast(CSS_GREEN, "#000000") < AA


# ---------------------------------------------------------------------------
# The vocabulary: theme variables, never CSS colour names
# ---------------------------------------------------------------------------


def test_signal_vocabulary_is_theme_variables():
    assert sig.SIGNAL_COLORS == {"$success", "$warning", "$error", "dim"}
    assert sig.SIGNAL_GOOD == "$success"
    assert sig.SIGNAL_WARN == "$warning"
    assert sig.SIGNAL_BAD == "$error"
    for colour in sig.SIGNAL_COLORS - {sig.SIGNAL_MUTED}:
        assert colour.startswith("$"), colour


def test_ev_sign_and_change_use_theme_variables():
    assert _ev_sign(1.0) == ("▲", "$success")
    assert _ev_sign(-1.0) == ("▼", "$error")
    assert "$success" in _fmt_change(3.4)
    assert "$error" in _fmt_change(-3.4)
    for value in (3.4, -3.4, 0.0, None, "x"):
        rendered = _fmt_change(value)
        assert "[green]" not in rendered
        assert "[red]" not in rendered


# ---------------------------------------------------------------------------
# Colour is never the sole carrier (PRD §11)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "glyph", "sign"),
    [(0.0813, "▲", "+0.0813"), (-0.0813, "▼", "-0.0813")],
)
async def test_ev_carries_glyph_and_sign_not_only_colour(value, glyph, sign):
    """Strip every style and the sign must still be readable."""
    widget = FWAHeroMetrics()
    app = _Harness(widget)
    async with app.run_test(size=(140, 12)) as pilot:
        widget.update_data(**{**_HERO, "pull_ev_best_eth": value})
        await pilot.pause()
        plain = "\n".join(
            "".join(s.text for s in strip)
            for strip in app.screen._compositor.render_strips()
        )
        assert glyph in plain
        assert sign in plain
        # The uncertainty must never be separated from the number it qualifies.
        assert "of weight priced" in plain


@pytest.mark.parametrize(
    ("builder", "words"),
    [
        (lambda: sig.buy_gate_signal(False), ("GATED", "no outside buys")),
        (lambda: sig.buy_gate_signal(True), ("OPEN", "outside buys enabled")),
        (
            lambda: sig.pool_temp_signal(10, 0, hot_gap=60, cold_gap=3600),
            ("HOT", "depositors"),
        ),
        (
            lambda: sig.pool_temp_signal(9000, 10_000, hot_gap=60, cold_gap=3600),
            ("COLD", "YOU"),
        ),
        (lambda: sig.buy_gate_signal(None), ("unavailable",)),
    ],
)
async def test_signal_rows_spell_their_state_out(builder, words):
    """Every colour-coded signal row survives with colour removed."""
    widget = FWASignals()
    app = _Harness(widget)
    async with app.run_test(size=(90, 10)) as pilot:
        row = builder().model_dump()
        widget.update_data(
            pool_temp_signal=row,
            buy_gate_signal=row,
            emissions_signal=row,
            vrf_queue_signal=row,
            param_drift_signal=row,
        )
        await pilot.pause()
        plain = "\n".join(
            "".join(s.text for s in strip)
            for strip in app.screen._compositor.render_strips()
        )
        for word in words:
            assert word in plain, f"{word!r} missing from {plain!r}"


# ---------------------------------------------------------------------------
# Measured contrast, every registered theme
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("theme_name", sorted(THEMES))
@pytest.mark.parametrize(
    ("ev", "needle"), [(0.0813, "▲ +0.0813"), (-0.0813, "▼ -0.0813")]
)
async def test_ev_sign_never_resolves_to_a_css_colour_name(theme_name, ev, needle):
    """The regression itself, asserted as pixels under all ten themes."""
    widget = FWAHeroMetrics()
    app = _Harness(widget, theme=theme_name)
    async with app.run_test(size=(140, 12)) as pilot:
        widget.update_data(**{**_HERO, "pull_ev_best_eth": ev})
        await pilot.pause()
        measured = composited(app, needle)
        assert measured is not None, f"{needle!r} was never painted"
        fg, bg = measured
        assert fg.lower() not in {CSS_GREEN, CSS_RED}, (
            f"{theme_name}: EV sign fell back to the CSS name table ({fg})"
        )
        ratio = contrast(fg, bg)
        assert ratio >= AA_LARGE, (
            f"{theme_name}: EV sign {fg} on {bg} = {ratio:.2f}, below {AA_LARGE}"
        )


@pytest.mark.parametrize("theme_name", sorted(THEMES))
async def test_crown_gold_passes_aa_under_every_theme(theme_name):
    """Gold has no fallback -- it is the crown's only colour, so it must pass."""
    widget = FWAHeroMetrics()
    app = _Harness(widget, theme=theme_name)
    async with app.run_test(size=(140, 12)) as pilot:
        widget.update_data(**_HERO)
        await pilot.pause()
        measured = composited(app, "3.221")
        assert measured is not None
        fg, bg = measured
        assert fg.lower() == CROWN_GOLD
        ratio = contrast(fg, bg)
        assert ratio >= AA, f"{theme_name}: crown gold {fg} on {bg} = {ratio:.2f}"


def test_gold_has_exactly_one_value():
    """One semantic, one hex.

    The hero tile and the chase board each used to carry their own gold
    (``#f0c040`` and ``#d4af37``), so "the crown colour" had two definitions
    that were free to drift. Both passed contrast; only one is the value the
    ``fwa`` theme declares as ``fwa-crown-gold``.
    """
    assert CROWN_GOLD == "#f0c040"
    assert CHASE_GOLD == CROWN_GOLD
    assert THEMES["fwa"].variables["fwa-crown-gold"] == CROWN_GOLD


async def test_gold_reaches_the_pixel_only_on_the_crown():
    """Exclusivity asserted where it is claimed -- on screen, not in a comment.

    Gold is the crown's only signal, so anything else wearing it dilutes the
    one tile that has no other cue. The palette's nearest neighbour to gold is
    ``fwa-pool-warm`` #f2842f, a Manhattan 79 away, which is close enough that
    "nobody else uses gold" has to be a measured claim rather than a habit.
    """
    widget = FWAHeroMetrics()
    app = _Harness(widget)
    async with app.run_test(size=(140, 12)) as pilot:
        widget.update_data(**_HERO)
        await pilot.pause()
        wearing_gold = [
            segment.text.strip()
            for strip in app.screen._compositor.render_strips()
            for segment in strip
            if segment.style
            and segment.style.color
            and segment.style.color.get_truecolor().hex == CROWN_GOLD
            and segment.text.strip()
        ]
        assert wearing_gold, "the crown pot was not painted gold at all"
        # The crown pot is the only gold thing; the tile's other three lines
        # (title, holder, seize price) are dim.
        assert wearing_gold == ["3.221"], wearing_gold


# ---------------------------------------------------------------------------
# Layout guarantees that carry meaning
# ---------------------------------------------------------------------------


async def test_hero_box_padding_is_never_1_2():
    """``padding: 1 2`` clips PULL EV's coverage badge off the card.

    That leaves a confident EV number with its uncertainty removed, which PRD
    §3 forbids outright -- so the padding is asserted as a *computed* style,
    not merely as a comment, and the badge is confirmed on the compositor.
    """
    widget = FWAHeroMetrics()
    app = _Harness(widget)
    async with app.run_test(size=(140, 12)) as pilot:
        widget.update_data(**_HERO)
        await pilot.pause()
        boxes = list(app.screen.query(FWAHeroBox))
        assert boxes, "no hero boxes composed"
        for box in boxes:
            padding = box.styles.padding
            assert (padding.top, padding.bottom) == (0, 0), (
                f"{box.id}: vertical padding is {padding}, must be 0"
            )
            assert (padding.left, padding.right) == (2, 2), (
                f"{box.id}: horizontal padding is {padding}, expected 0 2"
            )
        plain = "\n".join(
            "".join(s.text for s in strip)
            for strip in app.screen._compositor.render_strips()
        )
        assert "of weight priced" in plain


# 30 is comfortably below the longest row and 200/240 comfortably above.
# The clipping width was 54 while the gated row carried the long footnote;
# shortening that row moved the boundary, and a threshold pinned to the old
# number went red as a failure. What is under test is the *rule* -- marker iff
# clipped -- so the widths only have to sit either side of it.
@pytest.mark.parametrize(
    ("width", "expect_marker"), [(200, False), (240, False), (30, True)]
)
async def test_widen_marker_only_appears_when_a_row_is_clipped(width, expect_marker):
    """A marker that is always on trains the operator to ignore it.

    ``_GATE_WORDS`` was missing ``"gated"``, so a correctly-read closed gate got
    ``· state unknown`` appended, which pushed the row past the panel width and
    lit the marker during entirely healthy operation.
    """
    widget = FWASignals()
    app = _Harness(widget)
    async with app.run_test(size=(width, 10)) as pilot:
        widget.update_data(
            pool_temp_signal=sig.pool_temp_signal(
                9000, 10_000, hot_gap=60, cold_gap=3600
            ).model_dump(),
            buy_gate_signal=sig.buy_gate_signal(False).model_dump(),
            emissions_signal=sig.emissions_signal(
                sig.DOCUMENTED_EMISSION_STOP + 86_400,
                sig.DOCUMENTED_EMISSION_START,
                sig.DOCUMENTED_EMISSION_DURATION,
            ).model_dump(),
            vrf_queue_signal=sig.vrf_queue_signal(1000, 985).model_dump(),
            param_drift_signal=sig.param_drift_signal(None).model_dump(),
        )
        await pilot.pause()
        plain = "\n".join(
            "".join(s.text for s in strip)
            for strip in app.screen._compositor.render_strips()
        )
        assert ("‹ widen" in plain) is expect_marker, plain


# ---------------------------------------------------------------------------
# Surface-appropriate markup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("theme_name", sorted(THEMES))
async def test_muted_containers_do_not_also_dim_their_content(theme_name):
    """``color: $text-muted`` and ``[dim]`` compound; one of them is enough.

    Textual applies the markup style *on top* of the CSS one, so a ``[dim]``
    span inside a Static that is already ``$text-muted`` is muted twice. On the
    FWA screen that measured 3.71:1 under ``fwa`` and 3.36 under ``bakery`` --
    below WCAG 1.4.3 -- against 6.5:1 for ``$text-muted`` alone, and it bought
    no visual separation because the container was already providing it. The
    offenders were the odds-board meta line, its footnote, and the activity /
    settlement staleness stamps.
    """
    from maxpane_dashboard.widgets.fwa.fwa_odds_board import FWAOddsBoard

    widget = FWAOddsBoard()
    app = _Harness(widget, theme=theme_name)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(
            collection_odds=[
                {
                    "collection": "0x" + "ab" * 20,
                    "collection_name": "Nakamigos",
                    "odds_pct": 3.2,
                    "weight_pct": 4.1,
                    "floor_eth": 0.11,
                }
            ],
            odds_available=True,
            odds_as_of_block=25_612_701,
            odds_stale=False,
        )
        await pilot.pause()
        measured = composited(app, "block")
        assert measured is not None, "the odds-board meta line was never painted"
        fg, bg = measured
        ratio = contrast(fg, bg)
        assert ratio >= AA, (
            f"{theme_name}: odds meta {fg} on {bg} = {ratio:.2f} -- "
            "a [dim] span inside a $text-muted container has come back"
        )


def test_no_theme_variable_is_handed_to_a_rich_parsing_surface():
    """``$``-variables are Textual *Content* markup only.

    Rich -- which is what ``RichLog.write`` and ``DataTable`` cells parse --
    does not know them, so ``[$warning]x[/]`` raises ``MarkupError`` instead of
    degrading. Only string literals are inspected: the prose explaining this
    rule necessarily quotes the tokens it forbids.
    """
    import ast
    import inspect

    from maxpane_dashboard.widgets.fwa import fwa_activity_feed, fwa_chase_board

    for module in (fwa_activity_feed, fwa_chase_board):
        tree = ast.parse(inspect.getsource(module))
        literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        # f-strings decompose into Constant parts, so `[$warning]` survives as
        # its own literal and is still caught.
        for text in literals:
            for token in ("[$success]", "[$error]", "[$warning]", "[$"):
                assert token not in text, (
                    f"{module.__name__} hands {token!r} to a Rich-parsed surface"
                )


def test_rich_rejects_theme_variables_but_accepts_what_the_feed_sends():
    """The rule above, demonstrated rather than asserted from memory."""
    from rich.errors import MarkupError
    from rich.text import Text

    from maxpane_dashboard.widgets.fwa.fwa_activity_feed import UNAVAILABLE_LINE

    with pytest.raises(MarkupError):
        Text.from_markup("[$warning]x[/]")

    rendered = Text.from_markup(f"[yellow]⚠ {UNAVAILABLE_LINE}[/]")
    assert UNAVAILABLE_LINE in rendered.plain
    assert "⚠" in rendered.plain


@pytest.mark.parametrize("theme_name", sorted(THEMES))
async def test_degraded_paths_render_without_raising_under_every_theme(theme_name):
    """Degraded must not mean crashed, and must not mean invisible.

    The Rich/Content split above is silent until the degraded branch runs,
    because that is the only branch these two widgets colour at all.
    """
    from maxpane_dashboard.widgets.fwa.fwa_activity_feed import (
        UNAVAILABLE_LINE,
        FWAActivityFeed,
    )
    from maxpane_dashboard.widgets.fwa.fwa_settlement_table import (
        UNAVAILABLE_TEXT,
        FWASettlementTable,
    )

    for widget_cls, kwargs, needle in (
        (
            FWAActivityFeed,
            {"draw_events": [], "feed_available": False},
            UNAVAILABLE_LINE,
        ),
        (
            FWASettlementTable,
            {"settlement_mix": [], "crown_history": [], "settle_available": False},
            UNAVAILABLE_TEXT,
        ),
    ):
        widget = widget_cls()
        app = _Harness(widget, theme=theme_name)
        async with app.run_test(size=(90, 16)) as pilot:
            widget.update_data(**kwargs)
            await pilot.pause()
            # Measure the cell, not the row cursor painted over it. Textual's
            # DataTable cursor replaces *both* colours with $primary-on-light,
            # which under `bakery` is #e1f1f8 on #1b96ca = 2.90:1 -- a real but
            # pre-existing, app-wide DataTable/theme issue that would otherwise
            # mask whether this widget's own choice is sound. Reported to the
            # palette owner rather than silently absorbed here.
            for table in widget.query(DataTable):
                table.cursor_type = "none"
            await pilot.pause()
            painted = [
                (
                    segment.text.strip(),
                    segment.style.color.get_truecolor().hex,
                    segment.style.bgcolor.get_truecolor().hex,
                )
                for strip in app.screen._compositor.render_strips()
                for segment in strip
                if segment.style
                and segment.style.color
                and segment.style.bgcolor
                and "⚠" in segment.text
            ]
            plain = "\n".join(
                "".join(s.text for s in strip)
                for strip in app.screen._compositor.render_strips()
            )
            assert needle[:18] in plain, f"{widget_cls.__name__}/{theme_name}"
            assert painted, f"{widget_cls.__name__}/{theme_name}: no ⚠ painted"
            for text, fg, bg in painted:
                ratio = contrast(fg, bg)
                assert ratio >= AA, (
                    f"{widget_cls.__name__}/{theme_name}: {text!r} "
                    f"{fg} on {bg} = {ratio:.2f}"
                )
