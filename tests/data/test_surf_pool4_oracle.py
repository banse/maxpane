"""WP8 -- cross-check our pool4 math against an independent implementation.

The ``pool4hook-research`` skill is a second reader of this protocol, written
by its own author against the same chain. Agreement between two independent
implementations is a far stronger check than any self-consistency test: it is
how the ``0x840`` / ``0x2840`` flag error would have been caught on day one.

``tests/fixtures/surf/pool4/oracle_25955365.json`` is **evidence**. Never
regenerate it to make a test pass.
"""

import json
from pathlib import Path

import pytest

from maxpane_dashboard.analytics.surf_pool4_depth import (
    MAX_TICK,
    depth_rows,
    eth_between,
)

ORACLE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "surf"
    / "pool4"
    / "oracle_25955365.json"
)


def _load_oracle() -> dict:
    return json.loads(ORACLE.read_text(encoding="utf-8"))


def test_our_depth_ladder_agrees_with_the_independent_reader():
    """Two implementations, one protocol. Tolerance is 1% because the oracle
    rounds for display; a disagreement wider than that is a real defect in one
    of them and this test does not care which.

    Rows are matched **by ``move_pct``, never by position**: the oracle's
    ladder has nine rungs (1/2/5/10/20/30/50/75/90) and ours has five, so the
    plan's draft ``zip(ours, oracle["sell_side"])`` would have compared our
    -5% against the oracle's -2% and passed or failed for a reason that is not
    the claim. Reported as a finding.

    -1% is excluded and named: we compute 0.12 ETH against the oracle's 0.11,
    a second-decimal display rounding on the smallest rung (0.005 ETH is 4.5%
    of 0.11). It is checked below at its own coarser tolerance rather than
    quietly dropped.
    """
    oracle = _load_oracle()
    ours = depth_rows(
        tick=oracle["tick"],
        position_liquidity=float(oracle["position_liquidity"]),
        band_lower_tick=oracle["backstop_lower"],
        band_liquidity=float(oracle["backstop_liquidity"]),
    )
    assert ours is not None

    by_move = {int(r["move_pct"]): r for r in oracle["sell_side"]}
    compared = 0
    for row in ours:
        ref = by_move.get(int(row["move_pct"]))
        if ref is None:
            continue
        rel = 0.05 if int(row["move_pct"]) == 1 else 0.01
        assert row["eth_paid"] == pytest.approx(ref["hook_total_eth"], rel=rel), (
            f"-{row['move_pct']}%: ours {row['eth_paid']:.4f} ETH vs oracle "
            f"{ref['hook_total_eth']} ETH"
        )
        compared += 1
    assert compared == len(ours), "every rung of our ladder must have an oracle row"


def test_our_backstop_principal_matches_the_value_the_chain_reports():
    """``eth_between(band, lower, MAX_TICK)`` is the single-sided ETH the
    backstop band holds -- which the hook itself exposes as
    ``backstopPrincipal``. This is the strongest agreement available here:
    it is not the oracle's arithmetic being reproduced, it is the chain's own
    number, and the two implementations reach it independently.
    """
    oracle = _load_oracle()
    ours = eth_between(
        float(oracle["backstop_liquidity"]), oracle["backstop_lower"], MAX_TICK
    )
    assert ours == pytest.approx(oracle["backstop_principal_eth"], rel=1e-6)


def test_the_oracle_fixture_still_carries_the_inputs_the_ladder_needs():
    """A fixture silently trimmed to its rows would leave the cross-check
    above comparing our ladder against inputs it invented."""
    oracle = _load_oracle()
    for key in (
        "block",
        "tick",
        "position_liquidity",
        "backstop_lower",
        "backstop_liquidity",
        "backstop_principal_eth",
        "sell_side",
    ):
        assert key in oracle, key
    assert oracle["block"] == 25955365
    assert oracle["sell_side"], "the ladder rows were parsed from the skill's table"
