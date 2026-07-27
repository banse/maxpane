"""HIGH-1 companion: the stale-catalog fallback must be visible on screen.

Ranking from the hardcoded table is an acceptable degradation when the live
``agent.json`` catalog cannot be used -- ranking from it *without saying so* is
not, because the fallback's costs and durations are season-old and the user has
no way to tell them from live ones.

Assertions read composited screen text, so a marker asserted here is real text
a user would see rather than a string that never reaches a pixel.  Zero network.
"""

from __future__ import annotations

from textual.app import App, ComposeResult

from maxpane_dashboard.analytics.ev import (
    CATALOG_SOURCE_FALLBACK,
    CATALOG_SOURCE_LIVE,
)
from maxpane_dashboard.widgets.ev_table import EVTable

_BOOSTS = [("Ad Campaign", -2711.5), ("Cleanup Crew", -6000.0)]
_ATTACKS = [("Recipe Sabotage", 0.0087), ("Supplier Strike", 0.0069)]


class _Harness(App):
    def __init__(self, widget: EVTable) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _screen_text(app: App) -> str:
    strips = app.screen._compositor.render_strips()
    return "\n".join(strip.text for strip in strips)


async def _render(catalog_source: str | None) -> str:
    widget = EVTable()
    app = _Harness(widget)
    async with app.run_test(size=(120, 12)):
        if catalog_source is None:
            widget.update_data(boost_rankings=_BOOSTS, attack_rankings=_ATTACKS)
        else:
            widget.update_data(
                boost_rankings=_BOOSTS,
                attack_rankings=_ATTACKS,
                catalog_source=catalog_source,
            )
        await app.workers.wait_for_complete()
        return _screen_text(app)


async def test_live_catalog_renders_no_warning() -> None:
    text = await _render(CATALOG_SOURCE_LIVE)
    assert "BEST PLAYS" in text
    assert "STALE" not in text.upper()


async def test_fallback_catalog_is_labelled_on_screen() -> None:
    text = await _render(CATALOG_SOURCE_FALLBACK)
    assert "STALE CATALOG" in text.upper()
    # the rankings still render -- a labelled estimate beats a blank panel
    assert "Ad Campaign" in text


async def test_marker_clears_when_live_data_returns() -> None:
    widget = EVTable()
    app = _Harness(widget)
    async with app.run_test(size=(120, 12)):
        widget.update_data(_BOOSTS, _ATTACKS, CATALOG_SOURCE_FALLBACK)
        await app.workers.wait_for_complete()
        assert "STALE CATALOG" in _screen_text(app).upper()

        widget.update_data(_BOOSTS, _ATTACKS, CATALOG_SOURCE_LIVE)
        await app.workers.wait_for_complete()
        assert "STALE" not in _screen_text(app).upper()


async def test_default_call_does_not_crash() -> None:
    """Older call sites pass two arguments; they must keep working."""
    text = await _render(None)
    assert "BEST PLAYS" in text
