"""WP6 — the manager wiring behind the ``4`` POOL4 MARKET body.

Zero network, structurally: every client here is a double over the **committed**
corpus in ``tests/fixtures/surf/pool4/``, the surf client double's transport
raises on any use, the clock is a fake and every cache write lands under
``tmp_path``.

What this file exists to stop, in order of how badly it would end:

1. **First paint sitting behind the staker sweep.** The sIMD ``Transfer`` fold
   is a multi-minute walk over eight weeks of log history, paged.
   ``test_the_first_payload_is_not_behind_the_staker_sweep`` fails by *timing
   out*, which is the point: there is no assertion that can observe "did not
   block" after the fact.
2. **A ninth degraded group.** ``p4`` is the eighth name and CLAUDE.md records
   that the eighth is what took the worst-case title row to exactly the pinned
   width. The staker sweep gets no name of its own; it serves last-good behind
   its own stale marker and folds into ``p4`` only with nothing at all to
   serve.
3. **Two ticks read a block apart.** The whole reason the venue gap is
   derivable. The research skill reported it three ways that did not agree, and
   the cure is one batch — so this file asserts the manager makes *one* call
   for both venues and derives the gap from that call's own pair, never from
   the hook getter round's ``current_tick``.
4. **A backstop with two states.** ``deployed`` / ``"none"`` / ``None`` are
   three different facts and the middle one has no representable value of its
   own, which is the curator rail defect verbatim.

Every expected figure below is either published by a committed capture as its
own cross-check (``dripped_total_wei``, ``total_supply_shares_wei``,
``total_assets_imd_wei``, ``window_seconds``) or produced by the independent
oracle (``oracle_25955365.json``). Nothing is asserted against a number this
module computed.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from maxpane_dashboard.analytics import surf_pool4_depth as pool4_depth
from maxpane_dashboard.data import surf_pool4_market as mk
from maxpane_dashboard.data.surf_cache import (
    SLOT_POOL4,
    SLOT_POOL4_STAKERS,
    TIER_FAILURE_BACKOFF_SECONDS,
    TIER_POOL4,
    TIER_POOL4_STAKERS,
    TIER_TTL_SECONDS,
)
from maxpane_dashboard.data.surf_manager import (
    POOL4_DRIP_WINDOW_BLOCKS,
    POOL4_STAKERS_LIMIT,
    POOL4_STAKERS_WINDOW_BLOCKS,
    POOL4_TOPIC_DRIPPED,
    SOURCES,
    SurfManager,
)
from maxpane_dashboard.data.surf_models import (
    POOL4_BACKSTOP_STATES,
    POOL4_STAKERS_KEYS,
    POOL4_VENUE_WORDS,
    SURF_ROW_KEYS,
    PoolV4State,
)

# The whole `p` body's harness, reused rather than rebuilt: the corpus, the
# doubles and the two-cycle sweep helper are the same ones, and a second copy
# of them is a second thing to keep in step with the client's contract.
from tests.data.test_surf_manager_pool4 import (
    DRIPPER_ADDR,
    FLOW_LOGS,
    HOOK_ANSWERS,
    HOOK_BLOCK,
    HOOK_STATE,
    POOL4_NOW,
    VAULT_ADDR,
    VAULT_ASSETS,
    VAULT_STATE,
    FakePool4Client,
    _hook_at,
    _manager,
)
from tests.data.test_surf_manager import FakeClock

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "surf" / "pool4"

DEPLOYED, NO_BAND = POOL4_BACKSTOP_STATES
HERE, REFERENCE = POOL4_VENUE_WORDS

#: 365 days, the window WP3's fold annualises on. Restated here rather than
#: imported from the private ``_YEAR_SECONDS`` so the expectation below is an
#: independent arithmetic statement and not the fold quoting itself.
YEAR_SECONDS = 365 * 24 * 3600


def _capture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


DRIPPED = _capture("dripped_logs_7d")
TRANSFERS_FULL = _capture("simd_transfers_full")
TRANSFERS_PARTIAL = _capture("simd_transfers_partial")
ORACLE = _capture("oracle_25955365")

DRIPPED_LOGS = DRIPPED["response"]["result"]
TRANSFER_LOGS = TRANSFERS_FULL["response"]["result"]
TRANSFER_LOGS_PARTIAL = TRANSFERS_PARTIAL["response"]["result"]

#: The capture's own cross-checks, read off the file rather than retyped.
DRIPPED_IMD = DRIPPED["dripped_total_wei"] / 1e18
DRIPPED_WINDOW_SECONDS = DRIPPED["window_seconds"]
SHARE_SUPPLY_UNITS = TRANSFERS_FULL["total_supply_shares_wei"]
VAULT_ASSETS_MAINNET = TRANSFERS_FULL["total_assets_imd_wei"] / 1e18

#: The hook pool's live tick and the hookless reference pool's, from the
#: independent oracle. One block, both venues — which is the only way this
#: comparison means anything.
HOOK_TICK = ORACLE["tick"]
REFERENCE_TICK = ORACLE["reference_tick"]
HOOK_FEE = ORACLE["hook_lp_fee_bps"]
REFERENCE_FEE = ORACLE["reference_lp_fee_bps"]
REFERENCE_BLOCK = ORACLE["block"]


def _slot0(tick: int, fee: int, source: str = "hook") -> PoolV4State:
    return PoolV4State(
        pool_id="0x" + "11" * 32,
        sqrt_price_x96=None,
        tick=tick,
        lp_fee=fee,
        liquidity=1,
        pool_id_source=source,
    )


def _reference_answer(
    hook_tick: int = HOOK_TICK,
    reference_tick: int = REFERENCE_TICK,
    reference_fee: int = REFERENCE_FEE,
) -> dict:
    """What ``fetch_reference_slot0`` returns: both venues, one block."""
    return {
        "hook": _slot0(hook_tick, HOOK_FEE),
        "reference": _slot0(reference_tick, reference_fee, source="pinned"),
        "block_number": REFERENCE_BLOCK,
    }


class MarketPool4Client(FakePool4Client):
    """The `p` body's double plus the two reads the `4` body added.

    ``fetch_flow_logs`` dispatches on the **address** here, which the parent
    does not need to: three different contracts' log histories now ride that
    one method (the hook's flow window, the dripper's delivery window, the
    share token's whole life), and a double that answered the same list to all
    three would let the manager sweep the wrong contract and still pass.
    """

    def __init__(self, **overrides) -> None:
        self.reference_calls: list[tuple[str, str]] = []
        self.log_reads: list[tuple[str, int, int]] = []
        by_addr = overrides.pop("logs_by_addr", None)
        super().__init__(**overrides)
        self._returns.setdefault("fetch_reference_slot0", _reference_answer())
        self._logs_by_addr = by_addr if by_addr is not None else {
            str(HOOK_STATE.token or "").lower(): FLOW_LOGS,
            str(DRIPPER_ADDR).lower(): DRIPPED_LOGS,
            str(VAULT_ADDR).lower(): TRANSFER_LOGS,
        }

    async def fetch_reference_slot0(
        self, pool_id, reference_pool_id=None, *, network, pool_manager
    ):
        self.reference_calls.append((pool_id, pool_manager))
        return self._answer("fetch_reference_slot0", network)

    async def fetch_flow_logs(self, addr, from_block, to_block, *, network):
        self.log_windows.append((from_block, to_block))
        self.log_reads.append((str(addr).lower(), from_block, to_block))
        # ``in``, not ``.get() is not None``: ``None`` is the client's own
        # contract for a failed read, so a double that treated it as "no
        # override set" could not express the failure case at all -- and the
        # test that thought it was expressing it would pass on the healthy
        # path instead.
        key = "fetch_flow_logs_" + str(addr).lower()
        if key in self._returns:
            override = self._returns[key]
            if isinstance(override, BaseException):
                raise override
            return override
        if str(addr).lower() in self._logs_by_addr:
            return self._logs_by_addr[str(addr).lower()]
        return self._answer("fetch_flow_logs", network)


def _market_manager(tmp_path, *, pool4_client=None, clock=None) -> SurfManager:
    clock = clock or FakeClock(POOL4_NOW)
    return _manager(
        tmp_path,
        pool4_client=pool4_client if pool4_client is not None else MarketPool4Client(),
        clock=clock,
    )


async def _sweep_pool4(manager) -> dict:
    """One cycle, its detached pool4 sweep awaited, then the publishing cycle."""
    await manager.fetch_and_compute()
    if manager._pool4_task is not None:
        await manager._pool4_task
    if manager._pool4_stakers_task is not None:
        await manager._pool4_stakers_task
    return await manager.fetch_and_compute()


async def _sweep_stakers(manager) -> dict:
    """Drive a staker sweep to completion and publish it.

    Three cycles, not two, and the clock move in the middle is the reason: the
    staker sweep needs the *pool4* slot to have named a vault before it has
    anything to walk, so its first offer always lands on an empty slot and
    takes the failure backoff. That is production's own cold-start sequence,
    not a quirk of the harness.
    """
    await _sweep_pool4(manager)
    manager._clock_double.advance(TIER_FAILURE_BACKOFF_SECONDS[TIER_POOL4_STAKERS] + 1)
    await manager.fetch_and_compute()
    if manager._pool4_stakers_task is not None:
        await manager._pool4_stakers_task
    return await manager.fetch_and_compute()


# ---------------------------------------------------------------------------
# The tripwire — fails by TIMING OUT
# ---------------------------------------------------------------------------


async def test_the_first_payload_is_not_behind_the_staker_sweep() -> None:
    """The sweep is spawned, never awaited. **This fails by timing out.**

    ``_spawn_pool4``'s contract one tier further out, and the stakes are higher
    here: eight weeks of ``Transfer`` history paged in 2,400-block chunks is
    minutes of round trips, and a ``fetch_and_compute`` that waited on it would
    leave the dashboard blank for all of them. There is no assertion that can
    observe "did not block" after the fact, so the timeout *is* the test.

    The pool4 slot is primed first so the assertions can tell the two sweeps
    apart: the rest of the pool4 body must be on screen while the staker panel
    is still ``None``.
    """
    never = asyncio.Event()

    async def _hangs(*_a, **_kw):
        await never.wait()

    tmp_path = Path(tempfile.mkdtemp())
    client = MarketPool4Client()
    manager = _market_manager(tmp_path, pool4_client=client)
    await _sweep_pool4(manager)

    client._returns["fetch_flow_logs_" + str(VAULT_ADDR).lower()] = None
    client.fetch_block_number = _hangs
    manager._clock_double.advance(TIER_FAILURE_BACKOFF_SECONDS[TIER_POOL4_STAKERS] + 1)

    payload = await asyncio.wait_for(manager.fetch_and_compute(), timeout=2.0)
    assert payload["pool4_current_tick"] is not None   # the `p` body landed
    assert payload["pool4_stakers"] is None            # ... and this has not
    await manager._cancel_pool4_stakers()
    await manager._cancel_pool4()


async def test_only_one_staker_sweep_is_ever_in_flight(tmp_path) -> None:
    """A multi-minute walk must not stack behind a 30 s poll.

    The tier stays due while a sweep runs — only a *completed* sweep marks it
    fetched or failed — so every cycle offers again and the in-flight guard is
    the only thing between the two.
    """
    gate = asyncio.Event()
    started: list[int] = []

    class Slow(MarketPool4Client):
        async def fetch_flow_logs(self, addr, from_block, to_block, *, network):
            if str(addr).lower() == str(VAULT_ADDR).lower():
                started.append(1)
                await gate.wait()
            return await super().fetch_flow_logs(
                addr, from_block, to_block, network=network
            )

    manager = _market_manager(tmp_path, pool4_client=Slow())
    await _sweep_pool4(manager)
    manager._clock_double.advance(TIER_FAILURE_BACKOFF_SECONDS[TIER_POOL4_STAKERS] + 1)
    for _ in range(4):
        await manager.fetch_and_compute()
        await asyncio.sleep(0)
    assert started == [1]
    gate.set()
    await manager._cancel_pool4_stakers()
    await manager._cancel_pool4()


# ---------------------------------------------------------------------------
# Both ticks, one block
# ---------------------------------------------------------------------------


async def test_both_ticks_come_from_the_same_block(tmp_path) -> None:
    """PRD 8.3: the gap is a difference, not a disagreement.

    One call for both venues, and the manager must never fall back to reading
    the two pools separately — two ticks a block apart in a thin pool
    manufacture a percent of gap out of nothing, which is how one research tool
    reported +1.5% and +0.2% for the same pair inside five minutes.
    """
    client = MarketPool4Client()
    manager = _market_manager(tmp_path, pool4_client=client)
    await _sweep_pool4(manager)

    assert len(client.reference_calls) == 1
    asked_pool_id, asked_manager = client.reference_calls[0]
    assert asked_pool_id == HOOK_STATE.pool_id
    assert asked_manager == HOOK_STATE.pool_manager
    assert "fetch_pool_slot0" not in client.calls


async def test_the_gap_is_derived_from_the_batch_pair_not_from_current_tick(
    tmp_path,
) -> None:
    """The substitution that would look right and be wrong.

    ``pool4_current_tick`` comes off the hook's *getter* round — a different
    call at a different block. Pairing it with the reference tick is the
    cross-block comparison PRD 8.3 exists to settle, and it is invisible on a
    healthy chain because the two ticks are usually equal. So they are made
    unequal here: the batch's hook tick is the oracle's, the getter round's is
    the Sepolia corpus's, and only one of the two produces the oracle's gap.
    """
    client = MarketPool4Client()
    manager = _market_manager(tmp_path, pool4_client=client)
    payload = await _sweep_pool4(manager)

    assert payload["pool4_current_tick"] == HOOK_STATE.current_tick
    assert payload["pool4_current_tick"] != HOOK_TICK      # the two really differ
    assert payload["pool4_reference_pool_tick"] == REFERENCE_TICK
    assert payload["pool4_venue_gap_pct"] == pytest.approx(
        mk.venue_gap_pct(hook_tick=HOOK_TICK, reference_tick=REFERENCE_TICK)
    )


async def test_the_reference_tick_is_not_the_hooks_own_lagged_tick(tmp_path) -> None:
    """PRD 7.1's naming trap, asserted rather than described.

    ``pool4_ref_tick`` already exists and means the hook's internal
    anti-manipulation tick. Two things called "ref tick" in one payload is how
    a wrong number renders confidently.
    """
    payload = await _sweep_pool4(_market_manager(tmp_path))
    assert payload["pool4_ref_tick"] == HOOK_STATE.ref_tick
    assert payload["pool4_reference_pool_tick"] == REFERENCE_TICK
    assert payload["pool4_ref_tick"] != payload["pool4_reference_pool_tick"]


async def test_the_cheaper_venue_stays_silent_below_the_two_fees(tmp_path) -> None:
    """PRD 8.3. ``None`` is the expected answer, not a fold that never ran.

    The live pair is 1% against 1%, so nothing under a 2% gap is arbitrageable
    and naming a venue over it tells a reader to lose the spread. The oracle's
    own pair is 1 tick apart — 0.01% — which is exactly the case this must
    refuse.
    """
    payload = await _sweep_pool4(_market_manager(tmp_path))
    assert abs(payload["pool4_venue_gap_pct"]) < 1.0
    assert payload["pool4_cheaper_venue"] is None


async def test_a_gap_above_the_two_fees_names_the_reference_pool(tmp_path) -> None:
    """And the silence above is a threshold, not a hardcoded ``None``."""
    client = MarketPool4Client(
        fetch_reference_slot0=_reference_answer(reference_tick=HOOK_TICK + 5_000)
    )
    payload = await _sweep_pool4(_market_manager(tmp_path, pool4_client=client))
    assert payload["pool4_venue_gap_pct"] > 2.0
    assert payload["pool4_cheaper_venue"] == REFERENCE
    assert payload["pool4_cheaper_venue"] in POOL4_VENUE_WORDS


async def test_an_unreadable_reference_costs_four_keys_and_nothing_else(
    tmp_path,
) -> None:
    """A dead cross-venue read must not blind the body it sits in."""
    client = MarketPool4Client(fetch_reference_slot0=None)
    payload = await _sweep_pool4(_market_manager(tmp_path, pool4_client=client))
    assert payload["pool4_reference_pool_tick"] is None
    assert payload["pool4_venue_gap_pct"] is None
    assert payload["pool4_cheaper_venue"] is None
    assert payload["pool4_current_tick"] is not None
    assert payload["pool4_vault_assets"] is not None


# ---------------------------------------------------------------------------
# The USD price
# ---------------------------------------------------------------------------


async def test_the_usd_price_is_the_hook_tick_times_the_market_eth_price(
    tmp_path,
) -> None:
    """USD per IMD, from the pool's own tick and the ETH price already read.

    The orientation is the half that is easy to get backwards: the pool prices
    IMD **per ETH**, so IMD's own price is ETH's divided by that ratio. Upside
    down it renders a plausible number rather than an error, which is why the
    conversion is called from ``analytics/surf_pool4_depth`` rather than
    written a second time.
    """
    payload = await _sweep_pool4(_market_manager(tmp_path))
    eth_usd = payload["eth_usd"]
    assert eth_usd is not None
    imd_per_eth = pool4_depth.sqrt_ratio(payload["pool4_current_tick"]) ** 2
    assert payload["pool4_price_usd"] == pytest.approx(eth_usd / imd_per_eth)
    # The wrong orientation is the number to be sure we did not publish.
    assert payload["pool4_price_usd"] != pytest.approx(eth_usd * imd_per_eth)


async def test_the_usd_price_is_none_rather_than_zero_without_an_eth_price(
    tmp_path,
) -> None:
    """A failed read is ``None``, never ``0`` — and ``0`` is a *price*."""
    manager = _market_manager(tmp_path)
    payload = await _sweep_pool4(manager)
    slot = dict(manager.cache.get_last_good(SLOT_POOL4).payload)
    entry = manager.cache.get_last_good(SLOT_POOL4)
    assert payload["pool4_price_usd"] is not None
    keys = manager._pool4_keys(slot, entry, POOL4_NOW, eth_usd=None)
    assert keys["pool4_price_usd"] is None


# ---------------------------------------------------------------------------
# The backstop band — three states, never two
# ---------------------------------------------------------------------------


async def test_a_deployed_band_publishes_its_tick_liquidity_and_eth(
    tmp_path,
) -> None:
    """And its ETH agrees with the independent oracle's own figure.

    The band is single-sided ETH from its lower tick to the top of the range.
    ``eth_between`` is cross-checked against ``pool4hook-research``'s
    ``backstop_principal_eth`` at block 25955365 — a second implementation of
    this protocol's math by its own author — so this asserts the manager
    reaches that implementation rather than a private copy of it.
    """
    hook = _hook_at(HOOK_BLOCK)
    payload = await _sweep_pool4(_market_manager(tmp_path))

    assert payload["pool4_backstop_state"] == DEPLOYED
    assert payload["pool4_backstop_lower_tick"] == hook.backstop_tick_lower
    assert payload["pool4_backstop_liquidity"] == hook.backstop_liquidity
    assert payload["pool4_backstop_eth"] == pytest.approx(
        pool4_depth.eth_between(
            float(hook.backstop_liquidity),
            hook.backstop_tick_lower,
            pool4_depth.MAX_TICK,
        )
    )
    # Raw ``uint128`` L, never scaled: a divided one is 1e18 times too small
    # and reads as a band with no depth at all.
    assert payload["pool4_backstop_liquidity"] > 1e21


def test_the_oracle_agrees_with_the_bands_eth_conversion() -> None:
    """The cross-check the test above leans on, stated on its own.

    If this fails the fixture was recaptured against a different block and the
    assertion above stops meaning what it claims.
    """
    assert pool4_depth.eth_between(
        float(ORACLE["backstop_liquidity"]),
        ORACLE["backstop_lower"],
        pool4_depth.MAX_TICK,
    ) == pytest.approx(ORACLE["backstop_principal_eth"], rel=1e-9)


async def test_a_band_with_no_liquidity_is_none_the_word_not_none_the_absence(
    tmp_path,
) -> None:
    """**The middle state.** We looked, and there is no band.

    This is the curator rail defect's exact shape: a real negative with no
    representable value of its own renders identically to "we could not look",
    so the panel reads confident and green through an outage. The word is what
    separates them.

    The three numbers go to ``None`` rather than to ``0`` here, and that is not
    the rule inverted: a band that does not exist has no lower tick, and the
    getter's ``0`` is a *real tick* near one IMD per ETH — publishing it would
    draw a band at a price nobody deployed one at.
    """
    answers = dict(HOOK_ANSWERS)
    answers["backstop"] = "0x" + "00" * 96
    client = MarketPool4Client(fetch_hook_state=_hook_at(HOOK_BLOCK, answers))
    payload = await _sweep_pool4(_market_manager(tmp_path, pool4_client=client))

    assert payload["pool4_backstop_state"] == NO_BAND
    assert payload["pool4_backstop_state"] is not None
    assert payload["pool4_backstop_lower_tick"] is None
    assert payload["pool4_backstop_liquidity"] is None
    assert payload["pool4_backstop_eth"] is None


async def test_an_unread_band_is_none_the_absence_not_the_word(tmp_path) -> None:
    """The third state: the getter did not answer at all.

    ``"none"`` would claim we looked. An ``eth_call`` to an address with no
    code returns ``"0x"`` and no error, so "the call did not fail" is not "the
    getter answered" — which is why this case has to be distinguishable at all.
    """
    answers = dict(HOOK_ANSWERS)
    answers["backstop"] = "0x"
    client = MarketPool4Client(fetch_hook_state=_hook_at(HOOK_BLOCK, answers))
    payload = await _sweep_pool4(_market_manager(tmp_path, pool4_client=client))

    assert payload["pool4_backstop_state"] is None
    assert payload["pool4_backstop_lower_tick"] is None
    assert payload["pool4_backstop_eth"] is None


async def test_the_three_backstop_outcomes_are_three_distinct_answers(
    tmp_path,
) -> None:
    """Stated once, mechanically: no two of the three may look alike.

    A test per branch can pass while two branches publish the same thing;
    this is the one that fails if a future edit collapses the middle.
    """
    seen = []
    for backstop in ("0x", "0x" + "00" * 96, HOOK_ANSWERS["backstop"]):
        answers = dict(HOOK_ANSWERS)
        answers["backstop"] = backstop
        client = MarketPool4Client(fetch_hook_state=_hook_at(HOOK_BLOCK, answers))
        payload = await _sweep_pool4(
            _market_manager(Path(tempfile.mkdtemp()), pool4_client=client)
        )
        seen.append(
            (
                payload["pool4_backstop_state"],
                payload["pool4_backstop_lower_tick"],
                payload["pool4_backstop_eth"],
            )
        )
    assert len({state for state, _, _ in seen}) == 3
    assert seen[0][0] is None and seen[1][0] == NO_BAND and seen[2][0] == DEPLOYED


# ---------------------------------------------------------------------------
# The realised trailing return
# ---------------------------------------------------------------------------


async def test_the_trailing_return_is_what_arrived_not_what_was_promised(
    tmp_path,
) -> None:
    """PRD 8.1, against the capture's own published totals.

    ``dripped_total_wei`` and ``window_seconds`` are recorded by the capture
    itself — the second read off the two boundary **block headers**, which this
    manager has no call available to read. So this is a genuine cross-check of
    both halves at once: the sum against a number the capture computed, and the
    span against a measurement taken a different way entirely.
    """
    payload = await _sweep_pool4(_market_manager(tmp_path))
    expected = (
        DRIPPED_IMD / VAULT_ASSETS * (YEAR_SECONDS / DRIPPED_WINDOW_SECONDS) * 100.0
    )
    assert payload["pool4_trailing_return_pct"] == pytest.approx(expected, rel=0.01)


async def test_the_trailing_return_is_not_the_delivery_cap(tmp_path) -> None:
    """Two different numbers, and the panel shows the measured one.

    ``pool4_implied_apr_pct`` is ``dripRatePerSecond`` annualised — a ceiling
    on how fast rewards *can* reach the vault, which the vault panel already
    refuses to call APR. A window under that cap must produce the smaller
    figure, and it must not silently inherit the cap's key.
    """
    payload = await _sweep_pool4(_market_manager(tmp_path))
    assert payload["pool4_implied_apr_pct"] is not None
    assert payload["pool4_trailing_return_pct"] is not None
    assert payload["pool4_trailing_return_pct"] != payload["pool4_implied_apr_pct"]


async def test_only_the_vaults_leg_of_each_delivery_is_counted(tmp_path) -> None:
    """The event's second word is the keeper's cut and never reaches the vault.

    Summing both words overstates what stakers received — by 0.3% on this
    window, which is small enough to look like rounding and is the reason this
    is asserted rather than eyeballed. The capture's ``operand_proof``
    reconciles each word against its own ``Transfer`` in the same receipt.
    """
    manager = _market_manager(tmp_path)
    await _sweep_pool4(manager)
    slot = manager.cache.get_last_good(SLOT_POOL4).payload
    assert slot["dripped_imd"] == pytest.approx(DRIPPED_IMD)
    both_words = (
        DRIPPED["dripped_total_wei"] + DRIPPED["keeper_rewards_total_wei"]
    ) / 1e18
    assert slot["dripped_imd"] != pytest.approx(both_words)


async def test_the_delivery_window_spans_seven_days_of_blocks(tmp_path) -> None:
    """The window asked for, and the span measured out of it.

    The block count is nominal; the seconds are measured, because annualising
    a short window as though it had been seven days overstates the return in
    the flattering direction.
    """
    client = MarketPool4Client()
    manager = _market_manager(tmp_path, pool4_client=client)
    await _sweep_pool4(manager)

    reads = [r for r in client.log_reads if r[0] == str(DRIPPER_ADDR).lower()]
    assert len(reads) == 1
    _addr, from_block, to_block = reads[0]
    assert to_block - from_block + 1 == POOL4_DRIP_WINDOW_BLOCKS

    slot = manager.cache.get_last_good(SLOT_POOL4).payload
    assert slot["drip_window_seconds"] == pytest.approx(
        DRIPPED_WINDOW_SECONDS, rel=0.01
    )


async def test_a_quiet_window_is_a_real_zero_once_a_block_time_is_known(
    tmp_path,
) -> None:
    """Zero delivered is a fact, and it must not render as a dash.

    The return is lumpy by construction — trims only happen when sells exceed
    headroom — so a quiet stretch is the *expected* reading, not a failure.
    The span it is annualised over comes from the previous sweep's measurement,
    because a window with no events cannot measure its own block time.
    """
    client = MarketPool4Client()
    manager = _market_manager(tmp_path, pool4_client=client)
    await _sweep_pool4(manager)

    client._returns["fetch_flow_logs_" + str(DRIPPER_ADDR).lower()] = []
    manager._clock_double.advance(TIER_TTL_SECONDS[TIER_POOL4] + 1)
    payload = await _sweep_pool4(manager)

    slot = manager.cache.get_last_good(SLOT_POOL4).payload
    assert slot["dripped_imd"] == 0.0
    assert slot["drip_window_seconds"] is not None
    assert payload["pool4_trailing_return_pct"] == 0.0


async def test_an_unread_delivery_window_is_none_not_zero(tmp_path) -> None:
    """"We could not look" and "nothing arrived" are opposite claims."""
    client = MarketPool4Client()
    client._returns["fetch_flow_logs_" + str(DRIPPER_ADDR).lower()] = None
    payload = await _sweep_pool4(_market_manager(tmp_path, pool4_client=client))
    assert payload["pool4_trailing_return_pct"] is None
    assert payload["pool4_vault_assets"] is not None


def test_a_window_too_quiet_to_measure_its_own_block_time_reports_no_span() -> None:
    """And it reports it as ``None``, never by assuming twelve seconds.

    A hardcoded cadence would agree with mainnet today and skew every return
    on any chain that disagrees — and it would be indistinguishable from a
    measured one, which is what makes it worth refusing outright.
    """
    one = [log for log in DRIPPED_LOGS[:1]]
    window = SurfManager._pool4_drip_window(one, 1_000, 51_400, None)
    assert window["window_seconds"] is None
    assert window["seconds_per_block"] is None
    assert window["dripped_imd"] > 0.0


def test_the_block_time_is_measured_rather_than_assumed() -> None:
    """Against the capture's own header-read span.

    ``window_seconds`` in the fixture came from two block **headers**; this
    comes from the logs' own timestamps. Two independent routes to the same
    number is the whole claim.
    """
    window = SurfManager._pool4_drip_window(
        DRIPPED_LOGS, DRIPPED["from_block"], DRIPPED["to_block"], None
    )
    assert window["window_seconds"] == pytest.approx(
        DRIPPED_WINDOW_SECONDS, rel=0.001
    )
    assert window["dripped_imd"] == pytest.approx(DRIPPED_IMD)


def test_a_delivery_topic_that_is_not_the_dripped_one_is_not_counted() -> None:
    """The topic is a literal with no recovered pre-image and it must bite.

    A guessed signature string hashes to a topic0 that matches no log, and the
    panel then goes quiet rather than red. So the filter is asserted from both
    sides: the real topic sums, and a neighbouring one contributes nothing.
    """
    assert POOL4_TOPIC_DRIPPED.startswith("0x") and len(POOL4_TOPIC_DRIPPED) == 66
    foreign = [
        dict(log, topics=["0x" + "ab" * 32] + list(log["topics"][1:]))
        for log in DRIPPED_LOGS
    ]
    window = SurfManager._pool4_drip_window(
        foreign, DRIPPED["from_block"], DRIPPED["to_block"], None
    )
    assert window["dripped_imd"] == 0.0


# ---------------------------------------------------------------------------
# The staker sweep
# ---------------------------------------------------------------------------


async def test_the_fold_reproduces_the_share_tokens_own_total_supply(
    tmp_path,
) -> None:
    """The strongest check available on a holder fold, and it is independent.

    Every balance summed must equal ``totalSupply()`` — a number the capture
    read from the contract, not from these logs. A dropped log, a debit applied
    before its credit, a mis-decoded value word: all three break this identity,
    and none of them is visible in a leaderboard that merely looks plausible.
    """
    manager = _market_manager(tmp_path)
    await _sweep_stakers(manager)
    rows = SurfManager._pool4_share_transfers(TRANSFER_LOGS)
    balances = mk.fold_share_transfers(rows, complete=True)
    assert sum(balances.values()) == SHARE_SUPPLY_UNITS


async def test_the_leaderboard_lands_with_its_count_and_concentration(
    tmp_path,
) -> None:
    """PRD 6.1. Ranking is not the point; concentration is."""
    manager = _market_manager(tmp_path)
    payload = await _sweep_stakers(manager)

    assert payload["pool4_stakers"] is not None
    assert len(payload["pool4_stakers"]) == POOL4_STAKERS_LIMIT
    assert payload["pool4_staker_count"] > POOL4_STAKERS_LIMIT
    assert payload["pool4_staker_top3_pct"] is not None
    assert 0.0 < payload["pool4_staker_top3_pct"] < 100.0
    assert payload["pool4_stakers_as_of_hhmm"] is not None


async def test_every_staker_row_carries_exactly_the_frozen_row_shape(
    tmp_path,
) -> None:
    """C2: ``address``, not ``addr``. The producer's spelling is the contract.

    The row shape was specified two ways — this key's own comment said
    ``rank/addr/imd/pct`` while ``staker_rows`` emitted ``address`` — and a
    widget reading the losing spelling paints a blank column, which looks like
    a data outage rather than like a bug.
    """
    payload = await _sweep_stakers(_market_manager(tmp_path))
    declared = set(SURF_ROW_KEYS["pool4_stakers"])
    assert "address" in declared and "addr" not in declared
    for row in payload["pool4_stakers"]:
        assert set(row) == declared


async def test_the_rows_are_priced_in_imd_and_not_in_raw_shares(tmp_path) -> None:
    """CLAUDE.md's decimals rule, at the one place it can go wrong here.

    The vault reports ``decimals()`` of 24, so a balance unit is 10^24 of a
    share. Handing ``staker_rows`` the whole-share price scales every row by
    1e24 — a plausible, enormous number rather than an error. The whole
    leaderboard summed must come back to the vault's own ``totalAssets()``.
    """
    manager = _market_manager(tmp_path)
    payload = await _sweep_stakers(manager)

    per_unit = SurfManager._pool4_share_price_per_unit(
        VAULT_STATE.share_price_wei, VAULT_STATE.decimals
    )
    assert per_unit == pytest.approx(
        (VAULT_STATE.share_price_wei / 1e18) / 10 ** VAULT_STATE.decimals
    )
    # The whole vault, reconstructed from the rows' own percentages.
    top = payload["pool4_stakers"][0]
    implied_vault_imd = top["imd"] / (top["pct"] / 100.0)
    assert implied_vault_imd == pytest.approx(
        SHARE_SUPPLY_UNITS * per_unit, rel=1e-9
    )
    # And the wrong divisor really is the plausible-looking number.
    assert top["imd"] * 10 ** VAULT_STATE.decimals > 1e20


def test_the_share_price_a_row_takes_is_per_unit_not_per_whole_share() -> None:
    """Stated on its own, because both forms render and only one is right."""
    whole = VAULT_STATE.share_price_wei / 1e18
    per_unit = SurfManager._pool4_share_price_per_unit(
        VAULT_STATE.share_price_wei, VAULT_STATE.decimals
    )
    assert per_unit != pytest.approx(whole)
    assert per_unit * 10 ** VAULT_STATE.decimals == pytest.approx(whole)
    assert SurfManager._pool4_share_price_per_unit(None, 24) is None
    assert SurfManager._pool4_share_price_per_unit(10**18, None) is None


def test_a_truncated_sweep_is_refused_the_concentration_figure() -> None:
    """PRD 7.4, against the capture that exists solely to drive it.

    The partial fixture's own first log also sits a few blocks inside its
    window, so a "did the window open before the first event" heuristic calls
    it complete — it was the first rule written here and it did. What actually
    separates the two captures is that eleven of the truncated one's holders
    send out more than they were seen receiving, which is a *proof* that the
    shares came from before the window.
    """
    full = SurfManager._pool4_share_transfers(TRANSFER_LOGS)
    partial = SurfManager._pool4_share_transfers(TRANSFER_LOGS_PARTIAL)
    assert SurfManager._pool4_sweep_is_complete(
        full, TRANSFER_LOGS, TRANSFERS_FULL["from_block"]
    )
    assert not SurfManager._pool4_sweep_is_complete(
        partial, TRANSFER_LOGS_PARTIAL, TRANSFERS_PARTIAL["from_block"]
    )
    rows = mk.staker_rows(
        mk.fold_share_transfers(partial, complete=False), share_price=1e-24
    )
    assert mk.top_n_pct(rows, 3, complete=False) is None


def test_an_empty_window_is_never_called_complete() -> None:
    """Zero logs over a bounded range says nothing about the range before it."""
    assert not SurfManager._pool4_sweep_is_complete([], [], 1_000)


async def test_a_truncated_sweep_still_ranks_but_publishes_no_top_three(
    tmp_path,
) -> None:
    """End to end: the rows survive, the concentration figure does not."""
    client = MarketPool4Client()
    client._returns["fetch_flow_logs_" + str(VAULT_ADDR).lower()] = (
        TRANSFER_LOGS_PARTIAL
    )
    payload = await _sweep_stakers(_market_manager(tmp_path, pool4_client=client))
    assert payload["pool4_stakers"]
    assert payload["pool4_staker_top3_pct"] is None


async def test_the_sweep_walks_the_vault_and_asks_for_its_whole_history(
    tmp_path,
) -> None:
    """The share token *is* the vault, reached only by the chain's own walk.

    The address comes off the pool4 slot rather than from a second discovery:
    repeating that walk would be a second chance for the two sweeps to disagree
    about which vault they describe.
    """
    client = MarketPool4Client()
    manager = _market_manager(tmp_path, pool4_client=client)
    await _sweep_stakers(manager)

    reads = [r for r in client.log_reads if r[0] == str(VAULT_ADDR).lower()]
    assert len(reads) == 1
    _addr, from_block, to_block = reads[0]
    assert to_block - from_block + 1 == POOL4_STAKERS_WINDOW_BLOCKS


async def test_the_sweep_does_nothing_at_all_before_a_vault_is_named(
    tmp_path,
) -> None:
    """A cold start has no vault to walk, and must not guess one."""
    client = MarketPool4Client()
    manager = _market_manager(tmp_path, pool4_client=client)
    await manager.fetch_and_compute()
    if manager._pool4_stakers_task is not None:
        await manager._pool4_stakers_task
    assert not [r for r in client.log_reads if r[0] == str(VAULT_ADDR).lower()]
    assert manager.cache.get_last_good(SLOT_POOL4_STAKERS) is None
    await manager._cancel_pool4()


# ---------------------------------------------------------------------------
# The marker, and the degraded group that must not grow a ninth member
# ---------------------------------------------------------------------------


async def test_the_stakers_marker_does_not_advance_on_a_tick_that_found_nothing(
    tmp_path,
) -> None:
    """A fresh time beside days-old data is a stale number presented as live.

    Curator's analysis-marker rule, PRD 7.2. The sweep below runs twice over
    an identical corpus, which is what a real re-sweep of an unchanged vault
    looks like; the marker must name when these balances were *first* seen.
    """
    manager = _market_manager(tmp_path)
    first = await _sweep_stakers(manager)
    first_ts = manager.cache.get_last_good(SLOT_POOL4_STAKERS).ts

    manager._clock_double.advance(TIER_TTL_SECONDS[TIER_POOL4_STAKERS] + 1)
    await manager.fetch_and_compute()
    if manager._pool4_stakers_task is not None:
        await manager._pool4_stakers_task
    second = await manager.fetch_and_compute()

    assert manager.cache.get_last_good(SLOT_POOL4_STAKERS).ts == first_ts
    assert (
        second["pool4_stakers_as_of_hhmm"] == first["pool4_stakers_as_of_hhmm"]
    )
    assert second["pool4_stakers"] == first["pool4_stakers"]


async def test_the_stakers_marker_does_advance_when_the_fold_actually_moves(
    tmp_path,
) -> None:
    """The guard above has to be able to fail, or it is not a guard."""
    client = MarketPool4Client()
    manager = _market_manager(tmp_path, pool4_client=client)
    first = await _sweep_stakers(manager)
    first_ts = manager.cache.get_last_good(SLOT_POOL4_STAKERS).ts

    client._returns["fetch_flow_logs_" + str(VAULT_ADDR).lower()] = (
        TRANSFER_LOGS_PARTIAL
    )
    manager._clock_double.advance(TIER_TTL_SECONDS[TIER_POOL4_STAKERS] + 1)
    await manager.fetch_and_compute()
    if manager._pool4_stakers_task is not None:
        await manager._pool4_stakers_task
    second = await manager.fetch_and_compute()

    assert manager.cache.get_last_good(SLOT_POOL4_STAKERS).ts > first_ts
    assert second["pool4_stakers"] != first["pool4_stakers"]


async def test_a_failed_sweep_serves_last_good_and_adds_no_ninth_degraded_group(
    tmp_path,
) -> None:
    """PRD 7.3. ``p4`` is the eighth name and there is no room for a ninth.

    CLAUDE.md records that the eighth is what took the worst-case title row to
    exactly the pinned width, so a group of this sweep's own would silently
    truncate the one row whose job is to say something is down. A failed sweep
    with a last-good on hand is not a degradation at all: the stale marker is
    the whole signal.
    """
    client = MarketPool4Client()
    manager = _market_manager(tmp_path, pool4_client=client)
    good = await _sweep_stakers(manager)

    client._returns["fetch_flow_logs_" + str(VAULT_ADDR).lower()] = RuntimeError(
        "log endpoint is down"
    )
    manager._clock_double.advance(TIER_TTL_SECONDS[TIER_POOL4_STAKERS] + 1)
    await manager.fetch_and_compute()
    if manager._pool4_stakers_task is not None:
        await manager._pool4_stakers_task
    payload = await manager.fetch_and_compute()

    assert payload["pool4_stakers"] == good["pool4_stakers"]
    assert len(set(payload["degraded"])) <= 8
    assert len(SOURCES) == 8
    assert "pool4_stakers" not in payload["degraded"]
    assert set(payload["degraded"]) <= set(SOURCES)


async def test_a_sweep_with_nothing_to_serve_names_no_group_at_all(
    tmp_path,
) -> None:
    """The other half of PRD 7.3, and the half that was written out.

    The PRD says the staker sweep "folds into ``p4`` only when it has nothing
    at all to serve". The ``only`` is honoured absolutely — no ninth name, ever
    — and the fold itself is **not implemented**, deliberately: below is the
    case that decided it. ``p4`` is healthy, seven pool4 panels are live and
    dated, and one log endpoint is refusing the share token. Naming ``p4``
    there tells the reader those seven panels are down, and a false degradation
    is not the safe direction of an honest one.

    The signal is not lost: ``pool4_stakers`` is ``None`` and the panel's own
    unavailable state renders — the curator-rail rule satisfied at the widget,
    which is where "can the widget tell?" is answered. The manager's own
    no-last-good clause still degrades ``p4`` when there is nothing anywhere,
    which is the only way this sweep can be empty on a cold cache anyway: it
    reads its vault address out of ``SLOT_POOL4``.

    Recorded as a named deviation rather than a silent one.
    """
    client = MarketPool4Client()
    client._returns["fetch_flow_logs_" + str(VAULT_ADDR).lower()] = RuntimeError(
        "log endpoint is down"
    )
    manager = _market_manager(tmp_path, pool4_client=client)
    await _sweep_pool4(manager)
    manager._clock_double.advance(TIER_FAILURE_BACKOFF_SECONDS[TIER_POOL4_STAKERS] + 1)
    await manager.fetch_and_compute()
    if manager._pool4_stakers_task is not None:
        await manager._pool4_stakers_task
    payload = await manager.fetch_and_compute()

    assert manager.cache.get_last_good(SLOT_POOL4_STAKERS) is None
    assert payload["pool4_stakers"] is None
    assert payload["pool4_stakers_as_of_hhmm"] is None
    # The seven healthy panels are not slandered, and no ninth name appears.
    assert "p4" not in payload["degraded"]
    assert payload["pool4_current_tick"] is not None
    assert set(payload["degraded"]) <= set(SOURCES)


async def test_a_total_outage_still_degrades_p4(tmp_path) -> None:
    """And the rule above is not "this sweep can never say anything".

    With nothing in either slot there is nothing to serve anywhere, and ``p4``
    names itself through the manager's existing no-last-good clause.
    """
    client = MarketPool4Client(
        fetch_hook_state=None,
        fetch_vault_state=None,
        fetch_dripper_state=None,
        fetch_flow_logs=None,
    )
    client._returns["fetch_flow_logs_" + str(VAULT_ADDR).lower()] = None
    client._returns["fetch_flow_logs_" + str(DRIPPER_ADDR).lower()] = None
    payload = await _sweep_stakers(_market_manager(tmp_path, pool4_client=client))
    assert payload["pool4_stakers"] is None
    assert "p4" in payload["degraded"]


async def test_the_two_markers_run_on_two_clocks(tmp_path) -> None:
    """PRD 7.2: the staker panel may not hide behind ``pool4_as_of_hhmm``.

    They are separate slots written by separate sweeps on separate tiers, and
    the one thing a shared marker would guarantee is that a half-hour-old
    leaderboard sits under a one-minute-old timestamp.
    """
    manager = _market_manager(tmp_path)
    await _sweep_stakers(manager)
    assert (
        manager.cache.get_last_good(SLOT_POOL4).ts
        != manager.cache.get_last_good(SLOT_POOL4_STAKERS).ts
    )
    assert TIER_TTL_SECONDS[TIER_POOL4_STAKERS] > TIER_TTL_SECONDS[TIER_POOL4]


async def test_the_four_staker_keys_are_exactly_what_the_contract_froze(
    tmp_path,
) -> None:
    """A fixed count is itself the tripwire — ``CURATOR_ANALYSIS_KEYS``'s shape."""
    payload = await _sweep_stakers(_market_manager(tmp_path))
    assert len(POOL4_STAKERS_KEYS) == 4
    for key in POOL4_STAKERS_KEYS:
        assert key in payload


# ---------------------------------------------------------------------------
# Structural: nothing here touches the network
# ---------------------------------------------------------------------------


async def test_no_test_in_this_file_can_reach_the_network(tmp_path) -> None:
    """The surf client double's transport raises on any use, and is unused."""
    manager = _market_manager(tmp_path)
    await _sweep_stakers(manager)
    assert manager.client.http.__class__.__name__ == "DeadTransport"
    await manager.close()
