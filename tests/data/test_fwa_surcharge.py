"""``surchargeBps`` must be read live, and never asserted against a guess.

The bug this closes, from a live log line::

    FWA sweep invariants FAILED -- refusing to publish derived numbers:
    acquisitionFee 109842658187088279 != onchain 104849810087675175

The ratio is ``1.0476190476`` on every sample -- exactly ``1.10 / 1.05``. The
owner moved ``surchargeBps`` from 1000 to 500 (the dashboard was *displaying*
``surcharge 1000→500`` in its own signals panel at the time) and the invariant
kept recomputing the fee at 10%.

The consequence was not a wrong number on screen -- the guard did its job and
withheld everything. It was a permanently stale odds board, a suppressed EV
card and an "invariant mismatch" banner **on a sweep that was correct**:
``totalWeight`` and ``weightedBackingTotal`` both matched on-chain exactly, and
the fee is derived from those two, so the fee check proves nothing about sweep
completeness that they do not already prove. It tests the surcharge constant
and nothing else.

Hence the two rules pinned here: read the value from ``ConfigSet`` key 13, and
when it has not been read, do not assert the fee at all.

No network: positions and aggregates are literals.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.analytics import fwa_ev
from maxpane_dashboard.data.fwa_client import check_sweep_invariants
from maxpane_dashboard.data.fwa_logs import CONFIG_KEY_SURCHARGE, latest_config_value
from maxpane_dashboard.data.fwa_models import Position

BACKINGS = [10**18, 3 * 10**18, 7 * 10**18]


def _positions() -> list[Position]:
    return [
        Position(
            listing_id=i + 1,
            collection="0x" + f"{i:02x}" * 20,
            token_id=i,
            depositor="0x" + "11" * 20,
            backing_wei=b,
            weight=fwa_ev.inverse_weight(b),
            status=1,
        )
        for i, b in enumerate(BACKINGS)
    ]


def _aggregates(surcharge_bps: int) -> dict:
    tw = fwa_ev.total_weight(BACKINGS)
    wbt = fwa_ev.weighted_backing_total(BACKINGS)
    return {
        "expected_count": len(BACKINGS),
        "total_weight_onchain": tw,
        "weighted_backing_total_onchain": wbt,
        "acquisition_fee_onchain": fwa_ev.acquisition_fee_wei(wbt, tw, surcharge_bps),
    }


# ---------------------------------------------------------------------------
# reading the value
# ---------------------------------------------------------------------------


def _config_log(key: int, value: int, block: int, tx: str = "") -> dict:
    return {
        "topics": [
            "0x" + "00" * 32,          # topic0 is not read by config_history
            "0x" + f"{key:064x}",
        ],
        "data": "0x" + f"{value:064x}",
        "block_number": block,
        "log_index": key,
        "tx_hash": tx or ("0x" + f"{block:064x}"),
        "transaction_hash": tx or ("0x" + f"{block:064x}"),
        "event": "ConfigSet",
        "key": key,
        "value": value,
        "name": "SURCHARGE_BPS" if key == CONFIG_KEY_SURCHARGE else f"key {key}",
    }


def _launch_write(surcharge: int, block: int = 100) -> list[dict]:
    """A realistic deploy-time bulk write.

    ``_infer_launch_block`` only recognises a launch write when the earliest
    block carries at least five logs from a *single* transaction -- so a
    one-event fixture never exercises launch filtering at all, and a test
    built on one silently proves nothing about it.
    """
    tx = "0x" + "ab" * 32
    keys = [2, 7, 10, 11, 12, CONFIG_KEY_SURCHARGE, 14, 15]
    return [
        _config_log(k, surcharge if k == CONFIG_KEY_SURCHARGE else 1, block, tx)
        for k in keys
    ]


def test_latest_value_wins() -> None:
    """1000 at launch, 500 later -- the live value is 500."""
    events = [
        _config_log(CONFIG_KEY_SURCHARGE, 1000, block=100),
        _config_log(CONFIG_KEY_SURCHARGE, 500, block=900),
    ]

    assert latest_config_value(events, CONFIG_KEY_SURCHARGE) == 500


def test_a_launch_only_write_still_counts() -> None:
    """The launch write is filtered from the drift *display*, not from state.

    A key nobody has touched since deployment still holds its launch value;
    excluding it here reports ``None`` for every untouched parameter, which
    then silently disables the fee check forever.

    Uses a *real* launch write -- five-plus logs, one tx, earliest block -- so
    the filter it is guarding against actually engages.
    """
    events = _launch_write(1000)
    from maxpane_dashboard.data.fwa_logs import config_history

    assert config_history(events) == [], "fixture is not a recognised launch write"
    assert latest_config_value(events, CONFIG_KEY_SURCHARGE) == 1000


def test_a_later_change_overrides_the_launch_write() -> None:
    """The production shape: 1000 written at deploy, 500 set later."""
    events = _launch_write(1000) + [
        _config_log(CONFIG_KEY_SURCHARGE, 500, block=900)
    ]

    assert latest_config_value(events, CONFIG_KEY_SURCHARGE) == 500


def test_the_default_is_not_read_not_a_number() -> None:
    """Calling without a surcharge must not silently assume one.

    This is the whole regression: the parameter used to default to the
    documented 1000, so every caller that forgot to pass it asserted the fee
    against a guess.
    """
    report = check_sweep_invariants(_positions(), **_aggregates(500))

    assert report["acquisition_fee_checked"] is False
    assert report["surcharge_bps_used"] is None
    assert report["invariants_ok"] is True


def test_an_unwritten_key_is_none_not_a_default() -> None:
    """"Never written" must stay distinguishable from a documented value."""
    events = [_config_log(99, 42, block=100)]

    assert latest_config_value(events, CONFIG_KEY_SURCHARGE) is None
    assert latest_config_value([], CONFIG_KEY_SURCHARGE) is None


# ---------------------------------------------------------------------------
# using it
# ---------------------------------------------------------------------------


def test_the_live_surcharge_makes_a_correct_sweep_pass() -> None:
    """500 bps on chain, 500 bps supplied -> invariants hold."""
    report = check_sweep_invariants(
        _positions(), **_aggregates(500), surcharge_bps=500
    )

    assert report["invariants_ok"] is True
    assert report["acquisition_fee_checked"] is True


def test_the_wrong_surcharge_is_caught_not_ignored() -> None:
    """The check must still bite when a value *is* supplied and disagrees.

    Otherwise the fix would be indistinguishable from deleting the assertion.
    """
    report = check_sweep_invariants(
        _positions(), **_aggregates(500), surcharge_bps=1000
    )

    assert report["invariants_ok"] is False
    assert any("acquisitionFee" in m for m in report["mismatches"])
    assert any("surchargeBps=1000" in m for m in report["mismatches"])


def test_the_exact_ratio_that_was_observed_live() -> None:
    """Reproduces the production symptom: computed == onchain * 1.10 / 1.05."""
    report = check_sweep_invariants(
        _positions(), **_aggregates(500), surcharge_bps=1000
    )

    computed = report["acquisition_fee_computed"]
    onchain = report["acquisition_fee_onchain"]

    # 1.10/1.05 exactly -- the signature that identified the cause. The wei-
    # exact identity `computed == onchain * 11000 // 10500` holds at the
    # production magnitudes seen in the log (~1.1e17) but not at this
    # fixture's, because each value carries its own pair of truncations.
    assert computed / onchain == pytest.approx(11 / 10.5, rel=1e-12)


def test_an_unread_surcharge_does_not_fail_a_good_sweep() -> None:
    """**The regression that mattered.**

    With no live value, the fee is recomputed for information but not
    asserted, so a complete and correct sweep publishes. Asserting it against
    the documented 1000 is what left the odds board stale for days on data
    that was fine.
    """
    report = check_sweep_invariants(
        _positions(), **_aggregates(500), surcharge_bps=None
    )

    assert report["invariants_ok"] is True, report["mismatches"]
    assert report["acquisition_fee_checked"] is False
    assert report["surcharge_bps_used"] is None


def test_an_unread_surcharge_still_asserts_everything_else() -> None:
    """Skipping the fee must not skip the checks that prove completeness.

    ``totalWeight`` and ``weightedBackingTotal`` are what detect a short
    sweep -- the free-list holes that once cost 263 positions silently.
    """
    aggregates = _aggregates(500)
    aggregates["total_weight_onchain"] += 1  # a sweep that missed a position

    report = check_sweep_invariants(
        _positions(), **aggregates, surcharge_bps=None
    )

    assert report["invariants_ok"] is False
    assert any("totalWeight" in m for m in report["mismatches"])


def test_a_short_sweep_is_caught_regardless_of_surcharge() -> None:
    """Count mismatch is independent of any parameter value."""
    aggregates = _aggregates(500)
    aggregates["expected_count"] = len(BACKINGS) + 5

    for surcharge in (None, 500, 1000):
        report = check_sweep_invariants(
            _positions(), **aggregates, surcharge_bps=surcharge
        )
        assert report["invariants_ok"] is False
        assert any("activeListingCount" in m for m in report["mismatches"])


@pytest.mark.parametrize("surcharge", [0, 250, 500, 1000, 2500])
def test_the_fee_tracks_whatever_the_chain_says(surcharge) -> None:
    """No value is privileged -- 1000 is not more 'correct' than 500."""
    report = check_sweep_invariants(
        _positions(), **_aggregates(surcharge), surcharge_bps=surcharge
    )

    assert report["invariants_ok"] is True


def test_the_two_floor_divisions_are_preserved() -> None:
    """Collapsing them changes the integer by up to a wei.

    The fee is ``(Σweighted // Σweight) * (BPS + s) // BPS`` -- two sequential
    truncations, not one expression.
    """
    tw = fwa_ev.total_weight(BACKINGS)
    wbt = fwa_ev.weighted_backing_total(BACKINGS)

    two_steps = fwa_ev.acquisition_fee_wei(wbt, tw, 500)
    collapsed = wbt * (10_000 + 500) // (tw * 10_000)

    assert two_steps == check_sweep_invariants(
        _positions(), **_aggregates(500), surcharge_bps=500
    )["acquisition_fee_computed"]
    # Two truncations can only lose value relative to one, never gain it, and
    # on this fixture they differ by a wei -- which is exactly why the check
    # must recompute the way the contract does rather than simplify.
    assert two_steps <= collapsed
    assert collapsed - two_steps == 1


# ---------------------------------------------------------------------------
# the EV rebate is sized from the same parameter
# ---------------------------------------------------------------------------


def test_the_rebate_is_sized_from_the_live_surcharge() -> None:
    """``rebate = surcharge slice of the fee x rebate_share``.

    The slice is ``fee * s / (BPS + s)`` -- about 1/11 of the fee at 1000 bps
    and 1/21 at 500. Sizing it with the stale default overstated the rebate
    1.91x and pushed the headline EV optimistic by the difference, which is
    the same class of bug as the invariant failure and was one call site away
    from it.
    """
    fee = 105_472_438_580_792_280

    assert fwa_ev.surcharge_wei(fee, 1000) / fwa_ev.surcharge_wei(fee, 500) == (
        pytest.approx(1.909, abs=1e-3)
    )


def test_an_unknown_surcharge_claims_no_rebate() -> None:
    """0 means "cannot size it", and yields no rebate rather than a guess.

    Erring pessimistic matches the EV band's lower bound; erring optimistic
    would advertise value that may not exist.
    """
    assert fwa_ev.surcharge_wei(105_472_438_580_792_280, 0) == 0
