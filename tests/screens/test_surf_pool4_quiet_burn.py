"""POOL4 FLOW and BURN & SUPPLY on a burning-OFF market, composited.

The 2026-09-14 live defect, from a screenshot: POOL4 FLOW read ``no pool4
swaps yet`` and BURN & SUPPLY ``no flow observed`` while the hook pool had
218 swaps in 24 hours.  The market had headroom under its cap, so no sell
trimmed and the cap never ratcheted, and the flow decoder named swaps from
exactly those two events.

These tests drive the manager's own row builders over the committed
quiet-burn capture (``mainnet_flow_logs_quiet_burn`` + its PoolManager
``Swap`` sibling) and read what reaches the **compositor** in both bodies:
``SurfPool4Flow`` is mounted in ``p`` and in ``4``, and a fix that reached one
instance would be half a fix.  The last test is the control: the retired
decoder's answer on this window, ``[]``, painted, which proves the assertions
above it can fail.

No network: the manager is ``test_surf_screen``'s ``_FakeManager`` over a
payload, and the rows come from static methods over committed fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path

from maxpane_dashboard.data.surf_manager import SurfManager
from maxpane_dashboard.screens.surf import POOL4_BODY_ID, POOL4_USER_BODY_ID
from maxpane_dashboard.widgets.surf import SurfPool4Flow, SurfPool4UBurn
from maxpane_dashboard.widgets.surf import pool4_flow as flow_mod
from maxpane_dashboard.widgets.surf import pool4u_burn as burn_mod
from tests.screens.test_surf_screen import (
    _mainnet_pool4_payload,
    _region_text,
    _surf_app,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "surf" / "pool4"

#: Comfortably larger than any pin, as the market-screen tests use: this file
#: is about whether rows reach a pixel, not about the layout pin.
_SIZE = (150, 50)


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _quiet_burn_flow() -> list[dict]:
    """``pool4_flow`` exactly as the manager publishes it for this window."""
    swaps_fx = _fixture("mainnet_flow_swaps_quiet_burn")
    rows = SurfManager._pool4_flow_rows(
        swaps_fx["response"]["result"],
        _fixture("mainnet_flow_logs_quiet_burn")["response"]["result"],
    )
    return SurfManager._pool4_aged_flow(
        rows, float(swaps_fx["to_block_timestamp"]) + 60.0
    )


async def _painted(flow) -> tuple[str, str, str]:
    """Composited text of POOL4 FLOW in ``p``, then in ``4``, then BURN & SUPPLY."""
    payload = _mainnet_pool4_payload(pool4_flow=flow)
    async with _surf_app(payload).run_test(size=_SIZE) as pilot:
        screen = pilot.app.screen
        await screen._do_refresh()
        await pilot.pause()

        await pilot.press("p")
        await pilot.pause()
        await pilot.pause()
        auditor = screen.query_one(f"#{POOL4_BODY_ID}")
        assert auditor.display is True
        p_flow = _region_text(pilot.app, auditor.query_one(SurfPool4Flow))

        await pilot.press("4")
        await pilot.pause()
        await pilot.pause()
        market = screen.query_one(f"#{POOL4_USER_BODY_ID}")
        assert market.display is True
        m_flow = _region_text(pilot.app, market.query_one(SurfPool4Flow))
        burn = _region_text(pilot.app, market.query_one(SurfPool4UBurn))
    return p_flow, m_flow, burn


def _row_lines(text: str) -> list[str]:
    words = tuple(flow_mod.SIDE_WORDS.values())
    return [line for line in text.splitlines() if any(w in line for w in words)]


def test_the_payload_under_test_is_the_quiet_burn_window() -> None:
    flow = _quiet_burn_flow()
    assert flow and all(r["burned_imd"] == 0.0 for r in flow)
    assert {r["side"] for r in flow} == {"buy", "sell"}


async def test_pool4_flow_paints_rows_in_both_bodies_on_a_quiet_burn_market() -> None:
    p_flow, m_flow, _burn = await _painted(_quiet_burn_flow())
    for body, text in (("p", p_flow), ("4", m_flow)):
        assert flow_mod.EMPTY_LINE not in text, f"{body}: {text}"
        assert flow_mod.UNAVAILABLE_LINE not in text, f"{body}: {text}"
        rows = _row_lines(text)
        assert rows, f"{body} body painted no BUY/SELL row:\n{text}"
    assert "BUY" in p_flow + m_flow and "SELL" in p_flow + m_flow


async def test_burn_and_supply_reads_the_flow_on_a_quiet_burn_market() -> None:
    _p, _m, burn = await _painted(_quiet_burn_flow())
    assert "BURN & SUPPLY" in burn, burn
    assert burn_mod.EMPTY_LINE not in burn, burn
    assert burn_mod.UNAVAILABLE_LINE not in burn, burn


async def test_the_retired_answer_on_this_window_is_what_the_screenshot_showed() -> None:
    """The control.  ``[]`` is what the companion-event decoder made of these
    36 swaps; painted, it is the owner's screenshot -- which is what makes the
    three absence assertions above capable of failing."""
    p_flow, m_flow, burn = await _painted([])
    assert flow_mod.EMPTY_LINE in p_flow
    assert flow_mod.EMPTY_LINE in m_flow
    assert burn_mod.EMPTY_LINE in burn
    assert not _row_lines(p_flow) and not _row_lines(m_flow)
