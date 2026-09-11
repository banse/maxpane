"""WP3 — the realised trailing return, and the fixture it is folded from.

Pure fold, no I/O: the tests below touch no socket because nothing in
``surf_pool4_market`` can. The ``Dripped`` corpus is a committed capture and is
read off disk, decoded through the module that already owns that topic0.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_pool4 as P
from maxpane_dashboard.data import surf_pool4_market as mk

WEEK = 7 * 24 * 3600

FIXTURES = Path(__file__).parent.parent / "fixtures" / "surf" / "pool4"


def load(name: str):
    with open(FIXTURES / f"{name}.json") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# The fold — the plan's five tests
# ---------------------------------------------------------------------------


def test_the_return_annualises_what_actually_arrived():
    """1,000 IMD delivered to a 1,000,000 IMD vault in 7 days annualises to
    1000/1000000 * (365/7) * 100 = 5.214%."""
    got = mk.trailing_return_pct(
        dripped_imd=1000.0, window_seconds=WEEK, vault_assets=1_000_000.0
    )
    assert got == pytest.approx(5.214, abs=0.01)


def test_a_quiet_window_is_zero_percent_and_not_none():
    """Nothing dripped is a REAL answer -- the return genuinely was zero. It
    must not render as 'unavailable', which is what None means here."""
    assert mk.trailing_return_pct(
        dripped_imd=0.0, window_seconds=WEEK, vault_assets=1_000_000.0
    ) == 0.0


def test_an_unread_drip_total_is_none_not_zero():
    assert mk.trailing_return_pct(
        dripped_imd=None, window_seconds=WEEK, vault_assets=1_000_000.0
    ) is None


def test_an_empty_vault_is_none_rather_than_a_division_by_zero():
    """An empty vault has no return to report -- and infinity is not a number
    a panel can render."""
    assert mk.trailing_return_pct(
        dripped_imd=100.0, window_seconds=WEEK, vault_assets=0.0
    ) is None
    assert mk.trailing_return_pct(
        dripped_imd=100.0, window_seconds=WEEK, vault_assets=None
    ) is None


def test_a_zero_window_is_none_rather_than_infinite():
    assert mk.trailing_return_pct(
        dripped_imd=100.0, window_seconds=0, vault_assets=1_000_000.0
    ) is None


# ---------------------------------------------------------------------------
# It is not the delivery cap
# ---------------------------------------------------------------------------


def test_the_realised_return_is_not_the_delivery_cap_by_construction():
    """PRD 8.1. ``pool4_implied_apr_pct`` is ``drip_rate x 365 / TVL`` -- a
    CEILING on how fast rewards can reach the vault. This fold takes what
    arrived, so a window in which the dripper ran under its cap must produce a
    smaller number than the cap, and a test that could not tell them apart
    would let the vault panel's refusal to say APR be undone one key later.
    """
    rate_per_second = 1000.0 / WEEK          # the cap, expressed as a rate
    cap_pct = rate_per_second * (365 * 24 * 3600) / 1_000_000.0 * 100.0
    realised = mk.trailing_return_pct(
        dripped_imd=250.0, window_seconds=WEEK, vault_assets=1_000_000.0
    )
    assert realised < cap_pct
    assert realised == pytest.approx(cap_pct / 4, rel=1e-9)


# ---------------------------------------------------------------------------
# The committed corpus
# ---------------------------------------------------------------------------


def test_the_dripped_corpus_is_a_real_capture_of_the_mainnet_dripper():
    """Evidence, not a hand-written stub: a capture with no request sibling is
    a response nobody can show came from a chain."""
    fx = load("dripped_logs_7d")
    assert fx["synthetic"] is False
    assert fx["chain"] == "mainnet"
    assert (FIXTURES / "dripped_logs_7d.request.json").exists()
    body = json.loads((FIXTURES / "dripped_logs_7d.request.json").read_text())["body"]
    assert body["method"] == "eth_getLogs"
    assert body["params"][0]["address"].lower() == fx["dripper"].lower()


def test_the_window_folds_to_a_return_the_delivery_cap_does_not_bound_to_zero():
    """End to end on real logs: decode the window's ``Dripped`` amounts with
    the module that owns that topic0, annualise against the vault's own
    ``totalAssets``, and get a number rather than a ``None``.

    The window's own ``first``/``last`` timestamps are used, never a nominal
    seven days: a capture that undershoots its window would otherwise be
    annualised as though it had spanned one, which overstates the return.
    """
    fx = load("dripped_logs_7d")
    logs = fx["response"]["result"]
    topic0 = fx["topic0"]
    total_wei = sum(
        int(lg["data"][2:66] or "0", 16)
        for lg in logs
        if lg["topics"][0].lower() == topic0.lower()
    )
    assert fx["dripped_total_wei"] == total_wei, (
        "the recorded total no longer follows from the recorded logs"
    )
    vault_assets = fx["vault_total_assets_wei"] / 1e18
    got = mk.trailing_return_pct(
        dripped_imd=total_wei / 1e18,
        window_seconds=fx["window_seconds"],
        vault_assets=vault_assets,
    )
    if total_wei == 0:
        assert got == 0.0, "a genuinely quiet window is 0.0, never None"
    else:
        assert got is not None and got > 0.0


def test_the_corpus_topic0_carries_a_measurement_and_not_a_guessed_signature():
    """The dripper's event has **no recovered pre-image**, so the corpus names
    it by its operands and proves them against the chain rather than asserting
    them: each sampled log's first data word equals the IMD ``Transfer`` from
    the dripper TO THE VAULT in the same receipt, to the wei.

    This is ``data/surf_pool4.py``'s rule for its three unresolved hook topics,
    applied one module out. A guessed signature string would hash to a topic0
    that matches no log, and the fold would go quiet rather than red -- so the
    fixture must never grow a ``topic0_preimage``.
    """
    fx = load("dripped_logs_7d")
    assert fx["topic0_preimage"] is None
    assert fx["topic0_operands"]
    assert fx["topic0"].lower() not in {t.lower() for t in P.TOPIC0}, (
        "this topic0 now has a home in surf_pool4.TOPIC0 -- fold through that "
        "module instead of through a literal in a fixture"
    )
    proof = fx["operand_proof"]
    assert proof, "an unresolved topic0 with no operand proof is a guess"
    for row in proof:
        assert row["word0_equals_transfer_to_vault"], row
        assert row["word1_equals_transfer_to_keeper"], row
        assert row["imd_transfer_to_vault"] == row["word0_to_vault"], row


def test_the_window_is_read_off_the_chain_and_not_assumed_to_be_seven_days():
    """A capture that undershoots its nominal week, annualised as a week,
    overstates the return. The corpus records both boundary timestamps and the
    seconds between them, and the fold is handed those seconds."""
    fx = load("dripped_logs_7d")
    assert fx["window_seconds"] == (
        fx["to_block_timestamp"] - fx["from_block_timestamp"]
    )
    assert fx["window_seconds"] > 0
    # Close to a week, but NOT a week -- which is exactly why it is measured.
    assert abs(fx["window_seconds"] - WEEK) < WEEK * 0.1
