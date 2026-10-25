"""The two POOL4 entry points dispatch independent burn evidence."""
import pytest

from maxpane_dashboard.widgets.surf import SurfPool4Split, SurfPool4UBurn, SurfPool4USignals
from tests.screens.test_surf_screen import _mainnet_pool4_payload, _region_text, _surf_app
from tests.widgets.test_surf_pool4_pipeline import pipeline
from maxpane_dashboard.screens.surf import (
    SURF_POOL4_FULL_LAYOUT_COLUMNS, SURF_POOL4_FULL_LAYOUT_ROWS,
    SURF_POOL4_USER_FULL_LAYOUT_COLUMNS, SURF_POOL4_USER_FULL_LAYOUT_ROWS,
)
from tests.screens.test_surf_pool4_screen import _pool4_app, _pool4_hatch_payload
from tests.screens.test_surf_pool4_market_layout import _layout_payload


@pytest.mark.asyncio
@pytest.mark.parametrize("key, cls", [("4", SurfPool4UBurn), ("e", SurfPool4Split)])
async def test_pipeline_reaches_both_pool4_views_at_owner_size(key, cls):
    data = _mainnet_pool4_payload(pool4_burn_pipeline=pipeline())
    async with _surf_app(payload=data).run_test(size=(149, 45)) as pilot:
        await pilot.press(key)
        await pilot.pause()
        widget = pilot.app.screen.query_one(cls)
        painted = _region_text(pilot.app, widget)
        assert all(value in painted for value in ("29.95 IMD", "159.56 IMD", "84.05 IMD")), painted
        assert "executor-wide" in painted and "Base burned" in painted
        if key == "4":
            signals = pilot.app.screen.query_one(SurfPool4USignals)
            assert signals.region.bottom <= signals.parent.region.bottom
            assert not signals.parent.show_vertical_scrollbar


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["ok", "empty", "partial", "wide"])
@pytest.mark.parametrize("key, cls, size", [
    ("4", SurfPool4UBurn, (SURF_POOL4_USER_FULL_LAYOUT_COLUMNS, SURF_POOL4_USER_FULL_LAYOUT_ROWS)),
    ("e", SurfPool4Split, (SURF_POOL4_FULL_LAYOUT_COLUMNS, SURF_POOL4_FULL_LAYOUT_ROWS)),
])
async def test_pipeline_states_fit_at_both_full_layout_pins(key, cls, size, state):
    data = _mainnet_pool4_payload(pool4_burn_pipeline=pipeline(state),
                                 pool4_hatches=_pool4_hatch_payload(12)["pool4_hatches"])
    app = _pool4_app(data) if key == "e" else _surf_app(_layout_payload(data))
    async with app.run_test(size=size) as pilot:
        await pilot.press(key)
        await pilot.pause()
        widget = pilot.app.screen.query_one(cls)
        painted = _region_text(pilot.app, widget)
        assert all(label in painted for label in ("queued", "Base burned", "executor-wide"))
        assert "…" not in painted and "‹" not in painted
        assert not widget.parent.show_vertical_scrollbar
