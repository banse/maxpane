"""WP4 — the sIMD share fold and the concentration it answers.

Pure fold; no I/O. The two committed corpora are real ``eth_getLogs`` captures
of the mainnet vault's share token — one complete, one deliberately truncated,
which is the only way the ``None`` concentration guard can be driven by data
rather than by a flag a test set for itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_pool4_market as mk

ZERO = "0x" + "00" * 20
A, B, C, D = ("0x" + c * 40 for c in "abcd")

FIXTURES = Path(__file__).parent.parent / "fixtures" / "surf" / "pool4"

TRANSFER_TOPIC0 = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)


def load(name: str):
    with open(FIXTURES / f"{name}.json") as fh:
        return json.load(fh)


def _xfer(frm, to, value):
    return {"from": frm, "to": to, "value": value}


def _corpus(name: str) -> list[dict]:
    """The captured logs, decoded to the fold's input shape.

    Decoded here rather than stored pre-decoded: the fixture is the response
    the chain sent, and a fixture that already holds ``{from, to, value}`` is a
    fixture somebody transcribed.
    """
    fx = load(name)
    rows = []
    for log in fx["response"]["result"]:
        assert log["topics"][0].lower() == TRANSFER_TOPIC0
        rows.append(_xfer(
            "0x" + log["topics"][1][-40:],
            "0x" + log["topics"][2][-40:],
            int(log["data"], 16),
        ))
    return rows


# ---------------------------------------------------------------------------
# The fold — the plan's six tests
# ---------------------------------------------------------------------------


def test_a_mint_credits_and_a_burn_debits():
    bal = mk.fold_share_transfers(
        [_xfer(ZERO, A, 100), _xfer(ZERO, B, 50), _xfer(A, ZERO, 30)], complete=True
    )
    assert bal == {A: 70, B: 50}


def test_a_holder_who_leaves_entirely_is_dropped_not_kept_at_zero():
    """A zero-balance row would rank an address that holds nothing."""
    bal = mk.fold_share_transfers(
        [_xfer(ZERO, A, 100), _xfer(A, B, 100)], complete=True
    )
    assert A not in bal
    assert bal == {B: 100}


def test_rows_convert_shares_to_imd_and_carry_a_share_of_vault():
    rows = mk.staker_rows({A: 600, B: 400}, share_price=2.0)
    assert rows[0] == {
        "rank": 1, "address": A, "imd": 1200.0, "pct": 60.0,
    }
    assert rows[1]["rank"] == 2 and rows[1]["pct"] == pytest.approx(40.0)


def test_top_three_is_none_on_an_incomplete_fold():
    """PRD 7.4. A partial sweep ranking a subset would understate
    concentration -- the exact direction that makes a risk look smaller than
    it is. None (the dash), never a number computed from part of the data.
    This is `clean_routed_eth`'s guard verbatim.
    """
    rows = mk.staker_rows({A: 600, B: 300, C: 100}, share_price=1.0)
    assert mk.top_n_pct(rows, 3, complete=True) == pytest.approx(100.0)
    assert mk.top_n_pct(rows, 3, complete=False) is None


def test_an_incomplete_fold_is_flagged_rather_than_silently_returned():
    bal = mk.fold_share_transfers([_xfer(ZERO, A, 100)], complete=False)
    assert bal.complete is False
    assert mk.fold_share_transfers([_xfer(ZERO, A, 100)], complete=True).complete is True


def test_an_unread_share_price_gives_no_rows_rather_than_raw_shares():
    """Rendering share counts where IMD is promised is a unit error a reader
    cannot see -- 21 billion 'shares' against 21,010 real ones is the
    decimals-offset trap one layer up."""
    assert mk.staker_rows({A: 600}, share_price=None) is None


# ---------------------------------------------------------------------------
# Edges the plan's six do not reach
# ---------------------------------------------------------------------------


def test_a_transfer_between_two_holders_moves_shares_and_mints_nothing():
    """The fold's total must be conserved by an ordinary transfer, or a
    concentration percentage is computed against a denominator that moved."""
    bal = mk.fold_share_transfers(
        [_xfer(ZERO, A, 1000), _xfer(A, B, 400)], complete=True
    )
    assert bal == {A: 600, B: 400}
    assert sum(bal.values()) == 1000


def test_the_limit_caps_the_rows_but_never_the_denominator():
    """The percentages must be shares of the whole vault, not of the page. A
    denominator built from the top twenty makes every leaderboard add to 100%
    and hides exactly the dispersion the panel exists to show."""
    balances = {f"0x{i:040x}": 1 for i in range(1, 51)}
    rows = mk.staker_rows(balances, share_price=1.0, limit=20)
    assert len(rows) == 20
    assert sum(r["pct"] for r in rows) == pytest.approx(40.0)


def test_an_empty_fold_gives_no_rows_and_no_concentration():
    assert mk.staker_rows(mk.fold_share_transfers([], complete=True),
                          share_price=1.0) is None
    assert mk.top_n_pct(None, 3, complete=True) is None
    assert mk.top_n_pct([], 3, complete=True) is None


def test_top_n_asks_for_more_holders_than_exist_without_inventing_any():
    rows = mk.staker_rows({A: 600, B: 400}, share_price=1.0)
    assert mk.top_n_pct(rows, 3, complete=True) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# The committed corpora
# ---------------------------------------------------------------------------


def test_the_full_corpus_folds_to_a_vault_that_reconciles_with_total_supply():
    """Two independent readings of the same fact: the folded balances sum to
    what ``totalSupply()`` reported at the same head. A fold that dropped
    mints, double-counted burns or mishandled a self-transfer would not.
    """
    fx = load("simd_transfers_full")
    balances = mk.fold_share_transfers(_corpus("simd_transfers_full"),
                                       complete=fx["complete"])
    assert balances.complete is True
    assert sum(balances.values()) == fx["total_supply_shares_wei"]
    assert all(v > 0 for v in balances.values())


def test_the_full_corpus_is_complete_by_measurement_and_not_by_assertion():
    fx = load("simd_transfers_full")
    assert fx["completeness_measured"]["same_log_count"] is True
    assert fx["completeness_measured"]["wider_from_block"] < fx["first_log_block"]
    assert fx["synthetic"] is False


def test_the_real_vault_has_a_concentration_and_the_partial_capture_has_none():
    """The guard driven by data rather than by a flag the test chose.

    Both corpora are real captures of the same token. The full one ranks and
    answers; the truncated one folds to a *different*, smaller vault and is
    refused -- and the refusal is what stops a two-day window from being read
    as the whole holder set.
    """
    full = load("simd_transfers_full")
    share_price = full["share_price_wei_per_whole_share"] / 1e18

    whole = mk.fold_share_transfers(_corpus("simd_transfers_full"),
                                    complete=full["complete"])
    rows = mk.staker_rows(whole, share_price=share_price)
    top3 = mk.top_n_pct(rows, 3, complete=whole.complete)
    assert top3 is not None and 0.0 < top3 <= 100.0

    partial_fx = load("simd_transfers_partial")
    part = mk.fold_share_transfers(_corpus("simd_transfers_partial"),
                                   complete=partial_fx["complete"])
    part_rows = mk.staker_rows(part, share_price=share_price)
    assert mk.top_n_pct(part_rows, 3, complete=part.complete) is None
    assert sum(part.values()) != sum(whole.values()), (
        "the truncated corpus folds to the same vault as the full one -- it "
        "has stopped being incomplete and no longer tests the guard"
    )


def test_the_corpus_share_price_is_one_whole_share_not_one_ether():
    """CLAUDE.md's decimals rule, pinned in the fixture that carries the
    number: the vault reports 24 decimals, so one whole share is 1e24 and the
    read must have asked ``convertToAssets(10 ** decimals())``."""
    fx = load("simd_transfers_full")
    assert fx["share_decimals"] == 24
    call = fx["side_reads"][0]["params"][0]["data"]
    assert call.startswith("0x07a2d13a")
    assert int(call[10:], 16) == 10 ** fx["share_decimals"]


def test_the_share_price_the_rows_take_is_per_balance_unit_not_per_whole_share():
    """The unit seam, driven by the real vault rather than argued about.

    ``staker_rows`` multiplies a balance by a price, so the price must be IMD
    **per balance unit**. Balances are folded in raw token units and this vault
    reports 24 decimals, so the per-unit price is the whole-share price divided
    by ``10 ** 24``. Handing it the whole-share price instead inflates every
    row by that factor -- and the test does not take that on faith: folded with
    the per-unit price the whole holder set sums to the vault's own
    ``totalAssets()``, and with the whole-share price it sums to something
    ~1e24 times the vault, which is the decimals-offset trap wearing a
    different hat.
    """
    fx = load("simd_transfers_full")
    balances = mk.fold_share_transfers(_corpus("simd_transfers_full"),
                                       complete=fx["complete"])
    whole_share_price = fx["share_price_wei_per_whole_share"] / 1e18
    per_unit = whole_share_price / 10 ** fx["share_decimals"]

    every = mk.staker_rows(balances, share_price=per_unit, limit=len(balances))
    assert sum(r["imd"] for r in every) == pytest.approx(
        fx["total_assets_imd_wei"] / 1e18, rel=1e-9
    )

    wrong = mk.staker_rows(balances, share_price=whole_share_price,
                           limit=len(balances))
    assert sum(r["imd"] for r in wrong) > sum(r["imd"] for r in every) * 1e20
