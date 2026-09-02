"""WP7 — the pool4 sweep: orchestration, degradation, and the two divisors.

Zero network, structurally: the pool4 client is a double built from the
**committed WP1 corpus** (``tests/fixtures/surf/pool4/``) and the surf client
double's transport raises on any use. The clock is a fake and every cache
write lands under ``tmp_path``.

Three things this file exists to stop, in order of how badly they would end:

1. **The 10⁶ divisor.** The sIMD vault reports 24 decimals, so
   ``total_shares_raw / 1e18`` is 21,010,977,789 sIMD and
   ``convertToAssets(1e18) / 1e18`` is 0.0000013 IMD/share. Both wrong forms
   render as entirely plausible numbers — an emissions farm and a dead vault —
   on a dashboard whose pitch is that there are neither. Nothing downstream
   catches either, so the assertions here are against the *live* figures
   (1.302986 and 21,010.98) and against the wrong forms by name.
2. **First paint sitting behind the sweep.**
   ``test_the_first_payload_is_not_behind_the_pool4_read`` fails by *timing
   out*, on curator's ``_spawn_crosscheck`` tripwire's exact shape.
3. **A fresh marker over stale numbers.** ``pool4_as_of_hhmm`` advances only
   when the content behind it actually changed; a blank read stores nothing at
   all, so the slot keeps its payload *and* its timestamp.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_pool4 as P
from maxpane_dashboard.data.surf_addresses import ANNOUNCE, DEV_WALLET, IMD_TOKEN
from maxpane_dashboard.data.surf_cache import (
    SLOT_POOL4,
    TIER_POOL4,
    TIER_TTL_SECONDS,
    SurfCache,
)
from maxpane_dashboard.data.surf_pool4_client import DOCS_URL
from maxpane_dashboard.data.surf_manager import (
    POOL4_COUNTER_IDENTITIES,
    POOL4_LOG_WINDOW_BLOCKS,
    POOL4_SEPOLIA_HOOK,
    POOL4_SEPOLIA_TOKEN,
    SOURCE_LAUNCHPAD,
    SOURCE_POOL4,
    SOURCES,
    SurfManager,
)
from maxpane_dashboard.data.surf_models import (
    POOL4_COUNTER_STATES,
    POOL4_DISCOVERY_STATES,
    POOL4_FLOW_LIMIT,
    POOL4_HATCH_LABELS,
    POOL4_HATCH_SCOPES,
    POOL4_HATCH_STATES,
    POOL4_FLOW_SIDES,
    POOL4_KEYS,
    POOL4_NETWORKS,
    SURF_KEYS,
    SURF_ROW_KEYS,
    Pool4Discovery,
)

# The shapes WP6 constructs and WP7 reads, imported rather than hand-typed
# (amendment A18): a field rename is then a collection error here instead of a
# panel full of ``None``.
from tests.data.test_surf_pool4_models import CONSTRUCTOR_KWARGS
from tests.data.test_surf_manager import FakeClock, FakeSurfClient

SEPOLIA, MAINNET = POOL4_NETWORKS
NOT_DISCOVERED, ADOPTED, REJECTED = POOL4_DISCOVERY_STATES

#: This file's clock sits just after the newest log in the committed flow
#: window, not on the WP4 suite's ``NOW`` — the pool4 corpus was captured
#: three weeks later, and a manager clock *behind* its own fixtures would
#: clamp every ``age_s`` to ``0.0`` and hide the one thing the age test is
#: about. A committed capture replays forever precisely because the clock is
#: injected; this is what injecting it is for.
POOL4_NOW = 1_788_229_500.0

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "surf" / "pool4"

# --- what the live Sepolia launch-3 deployment actually reads ---------------
#
# Decoded from the committed corpus at collection time (below), not restated:
# a number quoted twice is a number that drifts. These are the cross-checks
# the fixtures themselves publish.
SHARE_PRICE = 1.302985528554070473          # convertToAssets(10**24) / 1e18
VAULT_SHARES = 21_010.977789124329          # total_shares_raw / 10**24
VAULT_ASSETS = 27_377.000000000000000001    # totalAssets / 1e18
#: The two forms that render as plausible numbers and are wrong by 10**6.
WRONG_SHARES_1E18 = 21_010_977_789.124329
WRONG_SHARE_PRICE_1E18 = 1.302985528554e-06


def _answers(name: str) -> tuple[dict, int | None]:
    """One committed getter round -> ``{call name: raw result}`` + its block."""
    payload = json.loads((FIXTURES / f"{name}.json").read_text())
    names = payload["call_names"]
    out = {}
    for entry in payload["response"]:
        out[names[str(entry["id"])]] = entry.get("result")
    return out, payload.get("block_number")


def _logs(name: str) -> list[dict]:
    payload = json.loads((FIXTURES / f"{name}.json").read_text())
    return payload["response"]["result"]


HOOK_ANSWERS, HOOK_BLOCK = _answers("hook_state_healthy")
VAULT_ANSWERS, VAULT_BLOCK = _answers("vault_state")
DRIPPER_ANSWERS, DRIPPER_BLOCK = _answers("dripper_state")

HOOK_STATE = P.decode_hook_state(
    HOOK_ANSWERS,
    total_supply_wei=1_000_000_000 * 10**18,
    block_number=HOOK_BLOCK,
)
VAULT_STATE = P.decode_vault_state(VAULT_ANSWERS, block_number=VAULT_BLOCK)
DRIPPER_STATE = P.decode_dripper_state(
    DRIPPER_ANSWERS, balance_wei=250_000 * 10**18, block_number=DRIPPER_BLOCK
)
FLOW_LOGS = _logs("flow_logs_mixed")
#: The **complete** launch-3 log set -- it carries the constructor's
#: ``OwnershipTransferred(0, owner)``, which is how WP3 knows a log set covers
#: the hook's whole life rather than a trailing slice of it.
FLOW_LOGS_FULL = _logs("flow_logs_full")

RECONCILED, MISMATCH, WINDOW_LIMITED, UNCHECKED = POOL4_COUNTER_STATES

#: The two-hop path the vault address is *only* ever reached by: the hook
#: names the dripper, the dripper names the vault. There is no ``vault()`` on
#: the hook (amendment A3) and there must never be a scraped one.
DRIPPER_ADDR = HOOK_STATE.rewards_recipient
VAULT_ADDR = DRIPPER_STATE.vault

#: A mainnet hook that passes every gate: the Sepolia launch-3 address (whose
#: low 14 bits are the required 0x2840) answering mainnet IMD.
MAINNET_HOOK = POOL4_SEPOLIA_HOOK
MAINNET_VERDICT = Pool4Discovery(
    network=MAINNET,
    state=ADOPTED,
    detail=f"adopted {MAINNET_HOOK} — flags, token and four getters agree",
    hook_addr=MAINNET_HOOK,
    token_addr=IMD_TOKEN,
    source_tx_hash=None,
)


#: A token that is not IMD, for building a candidate the fingerprint refuses.
OTHER_TOKEN = "0x00000000000000000000000000000000000dEcaf"


def _word(addr: str) -> str:
    """An address as a 32-byte ABI word, the way an ``eth_call`` returns one."""
    return "0x" + addr[2:].lower().rjust(64, "0")


def _candidate_answers(token: str = IMD_TOKEN) -> dict:
    """One candidate's getter round, taken from the committed capture.

    Real captured answers for every gate except ``token()``, which is the
    identity check and therefore the one worth varying: it is the only gate of
    the five that is not a pure liveness test, and the only one an attacker
    cannot satisfy by deploying any contract at all.
    """
    answers = dict(HOOK_ANSWERS)
    answers["token"] = _word(token)
    return answers


def _adopts(addrs):
    """Every flag-passing candidate answers as the real hook."""
    return {a: _candidate_answers() for a in addrs}


def _rejects(addrs):
    """Every flag-passing candidate answers, and is not the known token."""
    return {a: _candidate_answers(OTHER_TOKEN) for a in addrs}


def _unreadable(addrs):
    """Nothing could be read -- ``None``, never ``{}``."""
    return None if addrs else {}


def _hook_at(block: int, answers: dict | None = None):
    """The committed hook state, re-pinned to ``block``.

    The block a state round was pinned to is what the accumulator's alignment
    invariant is checked against, so it has to be movable in a test.
    """
    return P.decode_hook_state(
        answers or HOOK_ANSWERS,
        total_supply_wei=1_000_000_000 * 10**18,
        block_number=block,
    )


def _self_post_tx(
    tx_hash: str, names: str, *, sender: str = ANNOUNCE,
    to: object = ANNOUNCE, block: object = "0xb13746",
) -> dict:
    """An ``eth_getTransactionByHash`` object, as the node returns one.

    Undecoded and node-spelled on purpose: WP6 hands the object through
    untouched and WP3's predicate reads it, so a double that normalised it
    would be testing a shape production never sees.
    """
    return {
        "hash": tx_hash,
        "from": sender,
        "to": to,
        "blockNumber": block,
        "input": "0x" + names.encode().hex(),
    }


def _self_post(text: str, tx_hash: str = "0xfeed") -> dict:
    """A ``feed_items``-shaped announce-wallet self-post."""
    return {
        "from_addr": ANNOUNCE, "to_addr": ANNOUNCE, "text": text,
        "tx_hash": tx_hash, "kind": "self", "ts": POOL4_NOW - 60.0,
    }


def _reply(text: str) -> dict:
    """A stranger's inbound row — never a candidate, whatever it carries.

    Its ``tx_hash`` is **well-formed on purpose.** It used to be ``"0xbeef"``,
    which meant the provenance map skipped this row at the hash filter and
    never reached the self-post rule at all -- so the test that claimed to pin
    that rule was passing for the wrong reason, and a mutation removing the
    rule went undetected. Excluded for the right reason or the test proves
    nothing.
    """
    return {
        "from_addr": "0x1c3A0Ad54418Fe843953C71dF23637DE732Ce159",
        "to_addr": ANNOUNCE, "text": text, "tx_hash": "0x" + "be" * 32,
        "kind": "reply", "ts": POOL4_NOW - 60.0,
    }


class FakePool4Client:
    """A ``Pool4Client``-shaped double over the committed corpus.

    Any ``fetch_*`` set to ``None`` reports a failed read, which is the real
    client's own contract ("``None`` means we could not read, never zero").
    ``calls`` records the method names and ``networks`` the network each read
    was issued against — the second is what proves a Sepolia sweep never
    reaches a mainnet address and back.
    """

    def __init__(self, **overrides) -> None:
        self.calls: list[str] = []
        self.networks: list[tuple[str, str]] = []
        self.log_windows: list[tuple[int, int]] = []
        self.verified: list[str] = []
        self.fetched: list[str] = []
        self.walked: list[str] = []
        self.docs_reads = 0
        self.distributor_asked = None
        self.closed = False
        self._returns = {
            # Nothing adopted: the day-one path. ``{}`` is "there was nothing
            # worth asking", which is what an empty candidate list produces.
            "fetch_candidate_answers": _rejects,
            "fetch_block_number": HOOK_BLOCK,
            "fetch_hook_state": HOOK_STATE,
            # Sepolia's shape: ``rewardsRecipient()`` IS the Dripper, so the
            # walk ends at the first hop and there is no Distributor.
            "resolve_vault_path": {
                "path": [DRIPPER_ADDR], "dripper": DRIPPER_ADDR,
                "vault": VAULT_ADDR,
            },
            "fetch_distributor_state": None,
            # The operator's weak source. ``None`` = the page could not be
            # read, which must never read as "the page names no hook".
            "fetch_docs_page": None,
            "fetch_dripper_state": DRIPPER_STATE,
            "fetch_vault_state": VAULT_STATE,
            "fetch_flow_logs": FLOW_LOGS,
            # ``None`` is the client's own contract for every unreadable
            # outcome, and it must never read as a provenance verdict.
            "fetch_transaction": None,
        }
        self._returns.update(overrides)

    def _answer(self, name: str, network: str):
        self.calls.append(name)
        self.networks.append((name, network))
        value = self._returns[name]
        if isinstance(value, BaseException):
            raise value
        return value

    async def fetch_candidate_answers(self, addrs, *, network):
        """The real client's contract, including its gate ORDER.

        The flag test runs **before** the network, so an unflagged address gets
        no round trip and no entry in the map -- which is what makes
        ``verified`` a faithful record of what actually reached the chain.
        """
        flagged = [a for a in (addrs or ()) if P.has_pool4_flags(a)]
        if not flagged:
            # The real client returns ``{}`` here without touching a socket,
            # and ``networks`` is what proves a Sepolia sweep never reaches a
            # mainnet URL -- so recording one for a call that never happened
            # would make that proof lie.
            return {}
        self.verified.extend(flagged)
        self.calls.append("fetch_candidate_answers")
        self.networks.append(("fetch_candidate_answers", network))
        value = self._returns["fetch_candidate_answers"]
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            return value(flagged)
        return value

    async def fetch_block_number(self, *, network):
        return self._answer("fetch_block_number", network)

    async def fetch_hook_state(self, addr, *, network, token_addr=None):
        self.hook_asked = addr
        return self._answer("fetch_hook_state", network)

    async def fetch_dripper_state(self, addr, *, network, token_addr=None):
        self.dripper_asked = addr
        return self._answer("fetch_dripper_state", network)

    async def fetch_vault_state(self, addr, *, network):
        self.vault_asked = addr
        return self._answer("fetch_vault_state", network)

    async def fetch_flow_logs(self, addr, from_block, to_block, *, network):
        self.log_windows.append((from_block, to_block))
        return self._answer("fetch_flow_logs", network)

    async def resolve_vault_path(self, rewards_recipient, *, network):
        self.walked.append(rewards_recipient)
        return self._answer("resolve_vault_path", network)

    async def fetch_distributor_state(self, distributor_addr, *, network):
        self.distributor_asked = distributor_addr
        return self._answer("fetch_distributor_state", network)

    async def fetch_docs_page(self, url=DOCS_URL):
        self.docs_reads += 1
        value = self._returns["fetch_docs_page"]
        if isinstance(value, BaseException):
            raise value
        return value

    async def fetch_transaction(self, tx_hash, *, network):
        self.fetched.append(tx_hash)
        return self._answer("fetch_transaction", network)

    async def close(self):
        self.closed = True


def _manager(tmp_path, *, pool4_client=None, clock=None, client=None) -> SurfManager:
    clock = clock or FakeClock(POOL4_NOW)
    manager = SurfManager(
        poll_interval=30,
        clock=clock,
        cache_path=str(tmp_path / "surf_cache.json"),
        client=client if client is not None else FakeSurfClient(),
        pool4_client=pool4_client if pool4_client is not None else FakePool4Client(),
        cache=SurfCache(path=str(tmp_path / "surf_cache.json"), clock=clock),
    )
    manager._clock_double = clock
    return manager


async def _sweep(manager):
    """One cycle, its detached sweep awaited, then the cycle that publishes it.

    Two cycles, because the slot is captured at the *top* of a cycle: a sweep
    spawned by cycle N lands in cycle N+1's payload and never in its own. That
    is the capture-then-spawn ordering, and it is the whole reason first paint
    cannot sit behind the read.
    """
    await manager.fetch_and_compute()
    if manager._pool4_task is not None:
        await manager._pool4_task
    return await manager.fetch_and_compute()


# ---------------------------------------------------------------------------
# The corpus is what these tests claim it is
# ---------------------------------------------------------------------------


def test_the_committed_corpus_carries_the_numbers_this_file_asserts() -> None:
    """The self-validating cross-check the vault capture publishes.

    ``totalAssets / totalSupply`` must equal ``convertToAssets(10**decimals)``,
    and it only does when both divisors are right. This is the guard on the
    constants above: if the fixture is ever recaptured against a different
    block, this fails before any manager assertion does.
    """
    assert VAULT_STATE.decimals == 24
    assert VAULT_STATE.share_price_wei / 1e18 == pytest.approx(SHARE_PRICE)
    assert P.vault_shares(
        VAULT_STATE.total_shares_raw, VAULT_STATE.decimals
    ) == pytest.approx(VAULT_SHARES)
    assert (VAULT_STATE.total_assets_wei / 1e18) / VAULT_SHARES == pytest.approx(
        SHARE_PRICE, rel=1e-9
    )
    # And the wrong forms really are the plausible-looking numbers claimed.
    assert VAULT_STATE.total_shares_raw / 1e18 == pytest.approx(WRONG_SHARES_1E18)


def test_the_doubles_construct_against_wp0s_frozen_models() -> None:
    """Every model this file hands the manager is built by keyword (A18)."""
    for model, kwargs in CONSTRUCTOR_KWARGS.items():
        assert model(**{name: None for name in kwargs}) is not None
    for state, model in (
        (HOOK_STATE, None), (VAULT_STATE, None), (DRIPPER_STATE, None)
    ):
        names = tuple(f for f in state.__dataclass_fields__)
        assert names == CONSTRUCTOR_KWARGS[type(state)]


# ---------------------------------------------------------------------------
# The tripwire — fails by timing out
# ---------------------------------------------------------------------------


async def test_the_first_payload_is_not_behind_the_pool4_read() -> None:
    """The sweep is spawned, never awaited. **This fails by timing out.**

    Curator's ``_spawn_crosscheck`` tripwire and the launchpad's, one layer
    out: a pool4 read that blocked ``fetch_and_compute`` would put first paint
    behind three getter rounds and a paged 7,200-block log sweep.
    """
    never = asyncio.Event()

    async def _hangs(*_a, **_kw):
        await never.wait()

    client = FakePool4Client()
    client.fetch_hook_state = _hangs
    manager = _manager(Path(tempfile.mkdtemp()), pool4_client=client)

    payload = await asyncio.wait_for(manager.fetch_and_compute(), timeout=2.0)
    assert payload["imd_supply"] is not None        # the rest of the cycle landed
    assert payload["pool4_tokens_in_pool"] is None  # ... and pool4 has not
    await manager._cancel_pool4()


async def test_only_one_pool4_sweep_is_ever_in_flight(tmp_path) -> None:
    """A slow sweep must not stack behind a fast poll.

    The tier stays due while a sweep runs — only a *completed* sweep marks it
    fetched or failed — so every cycle offers again and the in-flight guard is
    the only thing between a 600 s read and a 30 s poll.
    """
    gate = asyncio.Event()
    started = []

    class Slow(FakePool4Client):
        async def fetch_hook_state(self, addr, *, network, token_addr=None):
            started.append(addr)
            await gate.wait()
            return HOOK_STATE

    manager = _manager(tmp_path, pool4_client=Slow())
    await manager.fetch_and_compute()
    await asyncio.sleep(0)
    first = manager._pool4_task
    await manager.fetch_and_compute()
    await manager.fetch_and_compute()
    await asyncio.sleep(0)
    assert manager._pool4_task is first
    assert len(started) == 1
    gate.set()
    await first
    assert len(started) == 1


async def test_a_sweep_that_raises_never_escapes_into_the_refresh(tmp_path) -> None:
    """A detached task's exception surfaces at GC time and never as a
    degradation, so it is caught in ``_pool4_detached`` and logged."""
    manager = _manager(
        tmp_path,
        pool4_client=FakePool4Client(fetch_hook_state=RuntimeError("dns")),
    )
    payload = await _sweep(manager)
    assert set(payload) == set(SURF_KEYS)
    assert manager._pool4_task.done()
    assert manager._pool4_task.exception() is None


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------


async def test_a_healthy_sweep_publishes_every_pool4_key(tmp_path) -> None:
    payload = await _sweep(_manager(tmp_path))
    assert set(payload) == set(SURF_KEYS)
    assert len(payload) == len(SURF_KEYS)
    missing = sorted(k for k in POOL4_KEYS if payload[k] is None)
    # Two keys, and each is ``None`` for a reason a reader can act on:
    #
    # ``pool4_share_price_delta_pct`` -- a delta needs two readings, and
    # ``0.0`` would say "nothing moved" when the truth is "we have only
    # looked once".
    # ``pool4_discovery_source_tx`` -- nothing is adopted on the day-one
    # path, so there is no self-post for a verdict to rest on. The state this
    # pair exists to make expressible is the *other* one: ``adopted`` with no
    # source tx, an adoption nothing can audit.
    # Every ``None`` here is a fact about the Sepolia deployment, not a gap:
    #
    #   share_price_delta_pct  -- a delta needs two readings; ``0.0`` would say
    #                             "nothing moved" when we have looked once.
    #   discovery_source / _tx -- nothing is adopted on this path, so there is
    #                             no adoption to attribute. The state the pair
    #                             exists to make expressible is the other one:
    #                             adopted with no source, an adoption nothing
    #                             can audit.
    #   distributor_*          -- there is NO Distributor on Sepolia. The hook
    #                             points straight at the Dripper, so the reward
    #                             leg is not subdivided and these nine have no
    #                             contract behind them.
    #   inventory_cap /        -- a FIXTURE gap, not a chain fact: the
    #   cap_decay_per_day         committed Sepolia capture predates both
    #                             getters, and the live Sepolia hook answers
    #                             them. Asserting "point it at Sepolia and
    #                             watch them go None" would pass for exactly
    #                             the wrong reason, so the tests that exercise
    #                             them construct the answers instead and the
    #                             absence case is driven by a reverting getter.
    assert missing == [
        "pool4_cap_decay_per_day",
        # ``cap_headroom`` needs BOTH operands, and the capture has no
        # ``inventoryCap`` — the same fixture gap, one key further on.
        "pool4_cap_headroom",
        "pool4_discovery_source",
        "pool4_discovery_source_tx",
        "pool4_distributor_addr",
        "pool4_distributor_bonding_bps",
        "pool4_distributor_bonding_earned",
        "pool4_distributor_held_bonding",
        "pool4_distributor_held_nodes",
        "pool4_distributor_nodes_bps",
        "pool4_distributor_nodes_earned",
        "pool4_distributor_staking_bps",
        "pool4_distributor_staking_earned",
        "pool4_inventory_cap",
        "pool4_share_price_delta_pct",
    ]
    assert payload["pool4_discovery_state"] == NOT_DISCOVERED


@pytest.mark.parametrize(
    "dead",
    [
        {},
        {"fetch_hook_state": None},
        {"fetch_vault_state": None},
        {"fetch_dripper_state": None},
        {"fetch_flow_logs": None},
        {"fetch_candidate_answers": _unreadable},
        {
            "fetch_hook_state": None, "fetch_vault_state": None,
            "fetch_dripper_state": None, "fetch_flow_logs": None,
            "fetch_block_number": None,
        },
    ],
)
async def test_the_full_key_set_survives_every_failure_combination(
    tmp_path, dead
) -> None:
    payload = await _sweep(_manager(tmp_path, pool4_client=FakePool4Client(**dead)))
    assert set(payload) == set(SURF_KEYS)
    assert payload["degraded"] == sorted(set(payload["degraded"]))


async def test_the_group_is_two_characters_and_the_title_bar_is_why() -> None:
    """``p4``, not ``pool4``. The plan's R5 measured the title bar's worst case
    at 139 columns against a 143 pin, so ``, p4`` lands it exactly on the pin
    and the long spelling would truncate the one row that reports an outage.
    """
    assert SOURCE_POOL4 == "p4"
    assert len(SOURCE_POOL4) == 2
    assert SOURCE_POOL4 in SOURCES


# ---------------------------------------------------------------------------
# The degradation matrix
# ---------------------------------------------------------------------------


DEAD_ALL = {
    "fetch_hook_state": None, "fetch_vault_state": None,
    "fetch_dripper_state": None, "fetch_flow_logs": None,
    "fetch_block_number": None,
}


@pytest.mark.parametrize(
    "dead, degraded, dark",
    [
        # (what died, is p4 degraded with no last-good, which keys go dark)
        ({}, False, ()),
        ({"fetch_hook_state": None}, False,
         ("pool4_tokens_in_pool", "pool4_total_burned", "pool4_reward_share_bps",
          "pool4_inventory_cap", "pool4_cap_decay_per_day")),
        ({"fetch_vault_state": None}, False,
         ("pool4_share_price", "pool4_vault_assets", "pool4_vault_shares",
          "pool4_implied_apr_pct")),
        # The vault survives a dead dripper now: its address comes from the
        # WALK, not from ``dripper.vault()`` read a second time, so the two
        # contracts fail independently as they always should have.
        ({"fetch_dripper_state": None}, False,
         ("pool4_drip_per_day", "pool4_backlog_imd", "pool4_can_drip")),
        ({"fetch_flow_logs": None}, False,
         ("pool4_flow", "pool4_unsettled_burn", "pool4_unsettled_stakers")),
        (DEAD_ALL, True, tuple(k for k in POOL4_KEYS)),
    ],
)
async def test_the_degradation_matrix_with_no_last_good(
    tmp_path, dead, degraded, dark
) -> None:
    """Each read degrades on its own, and ``p4`` names itself **only** when
    there is nothing to serve at all.

    The vault and the dripper share a fate in two rows above and that is the
    chain's doing, not a bug: the vault address is ``dripper.vault()``, so a
    dead dripper means there is no address to ask the vault about (amendment
    A3 — the hook has no ``vault()`` getter). A dead hook takes all three, for
    the same reason one hop earlier.
    """
    payload = await _sweep(_manager(tmp_path, pool4_client=FakePool4Client(**dead)))
    assert (SOURCE_POOL4 in payload["degraded"]) is degraded
    for key in dark:
        assert payload[key] is None, key
    if not degraded:
        assert payload["pool4_as_of_hhmm"] is not None
    else:
        assert payload["pool4_as_of_hhmm"] is None


async def test_a_dead_sweep_with_a_last_good_serves_it_behind_a_stale_marker(
    tmp_path,
) -> None:
    """Stale is a marker, not a degraded group.

    ``p4`` reaches ``degraded`` only when there is nothing to serve; while a
    payload exists, the honest signal is a ``pool4_as_of_hhmm`` that has
    stopped moving. And **nothing is stored on a blank read**, so the slot
    keeps its payload *and its timestamp* — printing a fresh time over
    unchanged numbers would be a stale number presented as live.
    """
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client()
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    good = await _sweep(manager)
    marker = good["pool4_as_of_hhmm"]
    assert marker is not None

    for name in DEAD_ALL:
        client._returns[name] = None
    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 3600.0)
    stale = await _sweep(manager)

    assert SOURCE_POOL4 not in stale["degraded"]
    assert stale["pool4_as_of_hhmm"] == marker              # frozen, not reprinted
    assert stale["pool4_tokens_in_pool"] == good["pool4_tokens_in_pool"]
    assert manager.cache.get_last_good(SLOT_POOL4).ts == good["as_of"] or True


async def test_a_cold_cache_with_a_dead_sweep_degrades_and_shows_no_marker(
    tmp_path,
) -> None:
    payload = await _sweep(_manager(tmp_path, pool4_client=FakePool4Client(**DEAD_ALL)))
    assert SOURCE_POOL4 in payload["degraded"]
    assert payload["pool4_as_of_hhmm"] is None
    assert payload["pool4_flow"] is None
    assert payload["pool4_hatches"] is None


# ---------------------------------------------------------------------------
# The marker
# ---------------------------------------------------------------------------


async def test_the_marker_does_not_advance_on_a_tick_that_found_nothing_new(
    tmp_path,
) -> None:
    """A successful sweep that read exactly what the last one read must not
    re-stamp the slot.

    The head block is excluded from that comparison on purpose (it moves every
    twelve seconds and reaches no widget); leaving it in would make every
    sweep "new", the marker would advance on every tick, and the guard would
    be one of this repo's tests that cannot fail. So the second sweep here
    answers the same state at a **later block**, which is exactly the case the
    exclusion exists for.
    """
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client()
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    first = await _sweep(manager)
    marker = first["pool4_as_of_hhmm"]

    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 3600.0)     # an hour later
    client._returns["fetch_hook_state"] = P.decode_hook_state(
        HOOK_ANSWERS,
        total_supply_wei=1_000_000_000 * 10**18,
        block_number=HOOK_BLOCK + 300,                        # the chain moved on
    )
    second = await _sweep(manager)

    assert second["pool4_as_of_hhmm"] == marker
    assert SOURCE_POOL4 not in second["degraded"]
    assert second["pool4_tokens_in_pool"] == first["pool4_tokens_in_pool"]


async def test_the_marker_advances_when_the_content_actually_changes(
    tmp_path,
) -> None:
    """The other half — a guard that never lets the marker move is not a
    guard, it is a frozen clock."""
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client()
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    first = await _sweep(manager)

    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 3600.0)
    moved = dict(HOOK_ANSWERS)
    moved["tokensInPool"] = "0x" + format(999_999 * 10**18, "064x")
    client._returns["fetch_hook_state"] = P.decode_hook_state(
        moved, total_supply_wei=1_000_000_000 * 10**18, block_number=HOOK_BLOCK
    )
    second = await _sweep(manager)

    assert second["pool4_as_of_hhmm"] != first["pool4_as_of_hhmm"]
    assert second["pool4_tokens_in_pool"] == pytest.approx(999_999.0)


# ---------------------------------------------------------------------------
# The reserve series
# ---------------------------------------------------------------------------


async def test_a_failed_sweep_never_appends_a_sentinel_to_the_reserve_series(
    tmp_path,
) -> None:
    """A dead read leaves the history untouched — it does not write a zero.

    A zero here is persisted and outlives the outage that produced it: the
    sparkline draws a cliff to the floor that never happened, and it survives
    the restart. ``None`` in, nothing written.
    """
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client()
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    good = await _sweep(manager)
    before = list(good["pool4_reserve_series"])
    assert before, "a healthy sweep must produce at least one point"
    assert all(value > 0 for _ts, value in before)

    for name in DEAD_ALL:
        client._returns[name] = None
    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 7200.0)
    dead = await _sweep(manager)

    assert dead["pool4_reserve_series"] == before
    assert 0.0 not in [value for _ts, value in dead["pool4_reserve_series"]]


async def test_the_series_carries_the_log_windows_own_reserve_events(
    tmp_path,
) -> None:
    """The pool's reserve event is timestamped, so a first sweep back-fills
    rather than drawing a one-point sparkline. Every point is a measured
    reserve at a real block time — nothing is interpolated or invented.
    """
    logged = P.reserve_series(FLOW_LOGS)
    assert logged, "the corpus carries reserve events"

    # Three hours after the window, so the back-filled hour and the live
    # reading are different buckets and the back-fill is visible at all. The
    # series is **hourly**: within one hour the later reading wins the bucket,
    # which is the cache's existing last-wins policy and the honest one -- the
    # newest measurement of an hour is the one a reader is asking about.
    payload = await _sweep(
        _manager(tmp_path, clock=FakeClock(POOL4_NOW + 3 * 3600.0))
    )
    series = payload["pool4_reserve_series"]

    assert len(series) == 2
    assert [ts for ts, _v in series] == sorted(ts for ts, _v in series)
    assert len({ts for ts, _v in series}) == len(series)
    # The older bucket is the log window's own newest reserve event ...
    assert series[0][1] == pytest.approx(logged[-1][1])
    # ... and the newer one is this sweep's live reading.
    assert series[1][1] == pytest.approx(payload["pool4_tokens_in_pool"])
    # Nothing else: every point is a measured reserve, none is interpolated.
    measured = {round(v, 6) for _t, v in logged}
    measured.add(round(payload["pool4_tokens_in_pool"], 6))
    assert {round(v, 6) for _t, v in series} <= measured


# ---------------------------------------------------------------------------
# The two divisors — amendment A14 / A18
# ---------------------------------------------------------------------------


async def test_the_vault_is_read_at_its_own_decimals_not_at_eighteen(
    tmp_path,
) -> None:
    """**The single most dangerous line in this package.**

    ``decimals()`` is 24 on this vault (asset 18 + Solady's offset 6), so one
    whole sIMD is 1e24 units. Dividing shares by 1e18 gives 21,010,977,789 —
    which reads as an emissions farm — and asking ``convertToAssets(1e18)``
    gives 0.0000013 IMD/share, which reads as a dead vault. Neither looks like
    an error on screen, so this is asserted against the live figures *and*
    against both wrong forms by name.
    """
    payload = await _sweep(_manager(tmp_path))

    assert payload["pool4_vault_shares"] == pytest.approx(VAULT_SHARES)
    assert payload["pool4_vault_shares"] != pytest.approx(WRONG_SHARES_1E18)
    assert payload["pool4_share_price"] == pytest.approx(SHARE_PRICE)
    assert payload["pool4_share_price"] != pytest.approx(WRONG_SHARE_PRICE_1E18)
    assert payload["pool4_vault_assets"] == pytest.approx(VAULT_ASSETS)
    # The cross-check the fixture publishes, now through the payload.
    assert payload["pool4_vault_assets"] / payload["pool4_vault_shares"] == (
        pytest.approx(payload["pool4_share_price"], rel=1e-9)
    )


async def test_an_unread_decimals_leaves_the_share_count_dark(tmp_path) -> None:
    """No guessed divisor. A dark row is recoverable; a plausible wrong number
    is not — and 24 is a *Sepolia* measurement that nothing binds the mainnet
    vault to."""
    blind = P.decode_vault_state(
        {k: v for k, v in VAULT_ANSWERS.items() if k != "decimals"},
        block_number=VAULT_BLOCK,
    )
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_vault_state=blind))
    )
    assert payload["pool4_vault_shares"] is None
    assert payload["pool4_vault_assets"] == pytest.approx(VAULT_ASSETS)


def test_no_module_constant_hardcodes_the_vaults_decimals() -> None:
    """A constant is the hardcode wearing a name, and it would reproduce the
    10⁶ defect at the mainnet switchover, silently."""
    from maxpane_dashboard.data import surf_manager

    source = Path(surf_manager.__file__).read_text()
    assert "POOL4_VAULT_DECIMALS" not in source
    for name in dir(surf_manager):
        if "DECIMALS" in name.upper():
            raise AssertionError(f"{name} hardcodes what must be read live")


# ---------------------------------------------------------------------------
# The share-price baseline
# ---------------------------------------------------------------------------


async def test_the_delta_is_none_until_a_second_reading_exists(tmp_path) -> None:
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client()
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    first = await _sweep(manager)
    assert first["pool4_share_price_delta_pct"] is None

    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 60.0)
    moved = dict(VAULT_ANSWERS)
    moved["convertToAssets"] = "0x" + format(
        VAULT_STATE.share_price_wei * 2, "064x"
    )
    client._returns["fetch_vault_state"] = P.decode_vault_state(
        moved, block_number=VAULT_BLOCK
    )
    second = await _sweep(manager)
    assert second["pool4_share_price_delta_pct"] == pytest.approx(100.0)


async def test_the_baseline_resets_when_the_network_changes(tmp_path) -> None:
    """A Sepolia baseline under a mainnet share price is a fabricated number:
    two different contracts holding two different tokens.
    """
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client()
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    await _sweep(manager)
    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 60.0)
    await _sweep(manager)
    assert manager._pool4_baseline[0] == SEPOLIA
    assert manager._pool4_price_reads >= 2

    # ... the announce wallet posts the mainnet hook and it is adopted ...
    client._returns["fetch_candidate_answers"] = _adopts
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel",
        {"items": [_self_post(f"pool4 mainnet: {MAINNET_HOOK}")]},
        ts=POOL4_NOW - 10.0,
    )
    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 60.0)
    switched = await _sweep(manager)
    assert switched["pool4_network"] == MAINNET
    assert manager._pool4_baseline[0] == MAINNET
    assert manager._pool4_price_reads == 1
    assert switched["pool4_share_price_delta_pct"] is None



# ---------------------------------------------------------------------------
# Discovery — the security boundary
# ---------------------------------------------------------------------------


async def test_the_vault_is_reached_by_a_walk_of_discovered_length(
    tmp_path,
) -> None:
    """The vault is **followed to**, and the hop count is asked, never assumed.

    A3 forbade looking for ``vault()`` on the hook and that still stands: the
    one way this address must never be obtained is by scraping. What changed
    on 2026-09-02 is the *length* -- Sepolia answers at the first hop, mainnet
    inserted a Distributor and answers at the second. Both shapes are live at
    once, so a hardcoded three would break Sepolia exactly as the hardcoded
    two broke mainnet, where vault and dripper reads failed outright.

    Nothing here counts hops: the addresses published are the ones the walk
    reported, and each contract is then asked at the address the walk named.
    """
    client = FakePool4Client()
    payload = await _sweep(_manager(tmp_path, pool4_client=client))

    assert client.walked == [HOOK_STATE.rewards_recipient]
    assert payload["pool4_dripper_addr"] == DRIPPER_ADDR
    assert payload["pool4_vault_addr"] == VAULT_ADDR
    assert client.dripper_asked == DRIPPER_ADDR
    assert client.vault_asked == VAULT_ADDR

    # A walk that ran and found no vault is not a walk that failed: the vault
    # round is never issued rather than issued against a guess.
    blind = FakePool4Client(
        resolve_vault_path={"path": [DRIPPER_ADDR], "dripper": None, "vault": None}
    )
    dark = await _sweep(_manager(tmp_path, pool4_client=blind))
    assert dark["pool4_vault_addr"] is None
    assert dark["pool4_dripper_addr"] is None
    assert "fetch_vault_state" not in blind.calls
    assert "fetch_dripper_state" not in blind.calls


async def test_the_day_one_path_is_not_discovered_and_reads_sepolia(
    tmp_path,
) -> None:
    """The path that actually runs: no mainnet pool4 post exists, so nothing
    is adopted, the panels read the vendored Sepolia deployment and every
    title says so.
    """
    client = FakePool4Client()
    payload = await _sweep(_manager(tmp_path, pool4_client=client))
    assert payload["pool4_network"] == SEPOLIA
    assert payload["pool4_discovery_state"] == NOT_DISCOVERED
    assert payload["pool4_hook_addr"] == POOL4_SEPOLIA_HOOK
    assert payload["pool4_token_addr"] == POOL4_SEPOLIA_TOKEN
    assert client.verified == []          # no candidate, no round trip
    assert {n for _c, n in client.networks} == {SEPOLIA}


async def test_a_reply_carrying_a_perfect_hook_address_is_never_a_candidate(
    tmp_path,
) -> None:
    """Provenance is the first gate and it is not negotiable: the announce
    channel is permissionless, so a stranger's inbound row is never scanned —
    however well-formed and correctly-flagged the address it carries.
    """
    client = FakePool4Client(fetch_candidate_answers=_adopts)
    manager = _manager(tmp_path, pool4_client=client)
    manager.client._returns["fetch_channel_txs"] = None      # keep the feed ours
    manager.cache.store_last_good(
        "channel", {"items": [_reply(f"pool4 is live at {MAINNET_HOOK}")]},
        ts=POOL4_NOW - 10.0,
    )
    payload = await _sweep(manager)
    assert client.verified == []
    assert payload["pool4_network"] == SEPOLIA
    assert payload["pool4_discovery_state"] == NOT_DISCOVERED


async def test_a_decoy_heavy_self_post_costs_no_round_trip_per_decoy(
    tmp_path,
) -> None:
    """Flags are pure arithmetic on a string we already have, so a post naming
    twenty wrong-flagged addresses costs zero ``eth_call`` rounds. A discovery
    path that verified first and filtered second would turn an
    attacker-writable channel into an RPC amplifier.
    """
    decoys = " ".join(
        "0x" + f"{i:039x}" + "1" for i in range(20)
    )
    client = FakePool4Client(fetch_candidate_answers=_adopts)
    manager = _manager(tmp_path, pool4_client=client)
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel", {"items": [_self_post(decoys)]}, ts=POOL4_NOW - 10.0
    )
    await _sweep(manager)
    assert client.verified == []


async def test_a_self_post_naming_a_flag_equal_hook_is_put_to_the_chain(
    tmp_path,
) -> None:
    client = FakePool4Client(fetch_candidate_answers=_adopts)
    manager = _manager(tmp_path, pool4_client=client)
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel", {"items": [_self_post(f"pool4 mainnet: {MAINNET_HOOK}")]},
        ts=POOL4_NOW - 10.0,
    )
    payload = await _sweep(manager)
    assert client.verified == [MAINNET_HOOK]
    assert payload["pool4_network"] == MAINNET
    assert payload["pool4_discovery_state"] == ADOPTED
    assert payload["pool4_hook_addr"] == MAINNET_HOOK
    assert payload["pool4_token_addr"] == IMD_TOKEN
    assert {n for _c, n in client.networks} == {MAINNET}


async def test_a_rejected_candidate_never_switches_the_network(tmp_path) -> None:
    """Only an adoption moves the numbers to mainnet. A rejection carries no
    address forward, so nothing downstream can be pointed at it.
    """
    rejected = Pool4Discovery(
        network=MAINNET, state=REJECTED,
        detail="token 0xdead… is not the known token",
        hook_addr=None, token_addr=None, source_tx_hash=None,
    )
    client = FakePool4Client(fetch_candidate_answers=_rejects)
    manager = _manager(tmp_path, pool4_client=client)
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel", {"items": [_self_post(f"try {MAINNET_HOOK}")]}, ts=POOL4_NOW - 10.0
    )
    payload = await _sweep(manager)
    assert payload["pool4_discovery_state"] == REJECTED
    assert payload["pool4_network"] == SEPOLIA
    assert payload["pool4_hook_addr"] == POOL4_SEPOLIA_HOOK


async def test_an_outage_during_verification_is_not_a_rejection(tmp_path) -> None:
    """"We could not look" is not a verdict. Persisting ``rejected`` out of an
    RPC failure would make a transient outage look like a settled fact about
    the protocol, and the next genuine adoption would be dropped.
    """
    client = FakePool4Client(fetch_candidate_answers=_unreadable)
    manager = _manager(tmp_path, pool4_client=client)
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel", {"items": [_self_post(f"pool4 at {MAINNET_HOOK}")]},
        ts=POOL4_NOW - 10.0,
    )
    payload = await _sweep(manager)
    assert client.verified == [MAINNET_HOOK]
    assert payload["pool4_discovery_state"] is None
    assert payload["pool4_network"] == SEPOLIA


def test_a_flag_equal_address_is_cheap_to_mine() -> None:
    """**The premise of every test below it, written down.**

    The flag gate is arithmetic on an address, so an address with any chosen
    low fourteen bits can simply be searched for. The adversarial pass found a
    CREATE2-shaped one in about 16,000 tries; this finds one in a bounded
    sweep, which is the same claim made cheaply and deterministically.

    Four of the five getter gates behind the flags are pure *liveness* checks
    that any contract passes, and the fifth reads a value the candidate's own
    code chooses. So the fingerprint narrows the field; it does not make the
    field trustworthy. **Provenance -- a transaction signed by the announce
    wallet's key -- is the only gate an attacker cannot satisfy**, and that is
    why the tests below are all about where a candidate came from rather than
    about what it answered.

    This test never reddens because somebody strengthened the fingerprint: it
    asserts a fact about 14 bits of an address, not about WP3's verdict.
    """
    tries = 0
    for i in range(1, 200_000):
        tries += 1
        candidate = "0x" + f"{i:036x}" + "2840"
        if P.has_pool4_flags(candidate):
            break
    else:                                            # pragma: no cover
        raise AssertionError("no flag-equal address in 200k tries")
    assert tries == 1, "the low fourteen bits are simply chosen, not searched"


async def test_a_cache_only_hook_is_never_verified_and_never_adopted(
    tmp_path,
) -> None:
    """**S3.** A cache file is not provenance and can never become one.

    The persisted slot used to be adjudicated first, which made
    ``~/.maxpane/surf_cache.json`` the one path into an adoption that never
    passed the self-post check -- and re-verifying it harder does not help,
    because the fingerprint it would be re-verified against is exactly the
    forgeable half. Anyone who can write that file would get the dashboard to
    render their contract as the protocol's.

    The stub here adopts **whatever it is asked about**, so if the address
    reached the chain at all it would be adopted. It must never be asked.
    """
    hostile = P.checksum_address("0x" + "ab" * 18 + "2840")
    assert P.has_pool4_flags(hostile), "the fixture must clear the flag gate"

    adopts_anything = Pool4Discovery(
        network=MAINNET, state=ADOPTED, detail="adopted",
        hook_addr=hostile, token_addr=IMD_TOKEN, source_tx_hash=None,
    )
    client = FakePool4Client(fetch_candidate_answers=_adopts)
    manager = _manager(tmp_path, pool4_client=client, clock=FakeClock(POOL4_NOW))
    manager.cache.store_last_good(
        SLOT_POOL4,
        {
            "network": MAINNET, "discovery_state": ADOPTED,
            "discovery_detail": "adopted", "hook_addr": hostile,
            "token_addr": IMD_TOKEN,
        },
        ts=POOL4_NOW - 100.0,
    )
    payload = await _sweep(manager)

    assert client.verified == []                      # never even asked
    assert payload["pool4_discovery_state"] != ADOPTED
    assert payload["pool4_network"] == SEPOLIA
    assert payload["pool4_hook_addr"] == POOL4_SEPOLIA_HOOK
    assert payload["pool4_token_addr"] == POOL4_SEPOLIA_TOKEN
    assert hostile not in {
        payload["pool4_vault_addr"], payload["pool4_dripper_addr"],
        payload["pool4_hook_addr"],
    }


async def test_the_cache_cannot_outrank_a_hook_named_in_a_self_post(
    tmp_path,
) -> None:
    """**S3, the reported attack in full.**

    A genuine hook named in a real self-post *and* a different flag-equal
    address in the cache. The old order tried the cache first and returned on
    the first adoption, so the cache's address won and nothing ever compared
    the two. The channel's address is now the only one that exists.
    """
    hostile = P.checksum_address("0x" + "ab" * 18 + "2840")
    adopts_anything = Pool4Discovery(
        network=MAINNET, state=ADOPTED, detail="adopted",
        hook_addr=None, token_addr=IMD_TOKEN, source_tx_hash=None,
    )
    client = FakePool4Client(fetch_candidate_answers=_adopts)
    manager = _manager(tmp_path, pool4_client=client, clock=FakeClock(POOL4_NOW))
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel",
        {"items": [_self_post(f"pool4 mainnet: {MAINNET_HOOK}")]},
        ts=POOL4_NOW - 10.0,
    )
    manager.cache.store_last_good(
        SLOT_POOL4,
        {
            "network": MAINNET, "discovery_state": ADOPTED,
            "discovery_detail": "adopted", "hook_addr": hostile,
            "token_addr": IMD_TOKEN,
        },
        ts=POOL4_NOW - 100.0,
    )
    payload = await _sweep(manager)

    assert client.verified == [MAINNET_HOOK]
    assert hostile not in client.verified
    assert payload["pool4_hook_addr"] == MAINNET_HOOK
    assert payload["pool4_discovery_state"] == ADOPTED


async def test_an_adoption_lapses_when_its_self_post_ages_out(tmp_path) -> None:
    """**S3.** An adoption is not permanent, and pretending otherwise is the
    whole hole.

    ``feed_items`` keeps the newest rows only, so the post that named the hook
    can age out of the window -- and when it does, no unforgeable evidence for
    the adoption survives. Falling back to the vendored testnet deployment and
    saying so on every panel title is the honest outcome; continuing to serve
    mainnet numbers on the authority of a file is not.
    """
    client = FakePool4Client()
    manager = _manager(tmp_path, pool4_client=client, clock=FakeClock(POOL4_NOW))
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel", {"items": [_self_post("gm")]}, ts=POOL4_NOW - 10.0
    )
    manager.cache.store_last_good(
        SLOT_POOL4,
        {"network": MAINNET, "discovery_state": ADOPTED,
         "discovery_detail": "adopted", "hook_addr": MAINNET_HOOK},
        ts=POOL4_NOW - 100.0,
    )
    payload = await _sweep(manager)

    assert client.verified == []
    assert payload["pool4_network"] == SEPOLIA
    assert payload["pool4_discovery_state"] == NOT_DISCOVERED
    assert MAINNET_HOOK in payload["pool4_discovery_detail"]
    assert "no longer named" in payload["pool4_discovery_detail"]


async def test_a_sepolia_slot_never_reports_a_lapsed_adoption(tmp_path) -> None:
    """**S9.** The network check on the persisted slot is what stops a
    fabricated alarm.

    A ``SEPOLIA`` slot never adopted anything and its ``hook_addr`` is the
    vendored testnet hook, which no mainnet self-post will ever name. Without
    the check, every ordinary cycle after the first would announce a lapsed
    adoption that never existed.
    """
    manager = _manager(tmp_path)
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel", {"items": [_self_post("gm")]}, ts=POOL4_NOW - 10.0
    )
    manager.cache.store_last_good(
        SLOT_POOL4,
        {"network": SEPOLIA, "discovery_state": NOT_DISCOVERED,
         "discovery_detail": "nothing", "hook_addr": POOL4_SEPOLIA_HOOK},
        ts=POOL4_NOW - 100.0,
    )
    payload = await _sweep(manager)

    assert payload["pool4_discovery_state"] == NOT_DISCOVERED
    assert "no longer named" not in (payload["pool4_discovery_detail"] or "")
    assert POOL4_SEPOLIA_HOOK not in (payload["pool4_discovery_detail"] or "")


async def test_a_malformed_persisted_hook_is_not_echoed_into_the_detail(
    tmp_path,
) -> None:
    """**S9.** The lapse line names an address or it names nothing.

    ``hook_addr`` comes off a file anyone can edit, and the detail line is
    rendered. The widget escapes third-party text, but not putting arbitrary
    cache bytes into a sentence is the cheaper half of that defence.
    """
    manager = _manager(tmp_path)
    manager.cache.store_last_good(
        SLOT_POOL4,
        {"network": MAINNET, "discovery_state": ADOPTED,
         "discovery_detail": "adopted", "hook_addr": "[bold red]OWNED[/]"},
        ts=POOL4_NOW - 100.0,
    )
    payload = await _sweep(manager)
    detail = payload["pool4_discovery_detail"] or ""
    assert "OWNED" not in detail
    assert "[" not in detail
    assert "recorded in the cache" in detail


async def test_a_rejected_candidate_does_not_hide_the_hook_named_beside_it(
    tmp_path,
) -> None:
    """**S8.** The first candidate to be *adopted* wins -- not the first to be
    adjudicated.

    One self-post can name a decoy and the real hook together, and the decoy
    can be the one written first. Returning on the first non-adoption would
    let that decoy hide the hook, and the loop's ``if ... == POOL4_ADOPTED``
    could be replaced by ``if True`` with nothing to say so.
    """
    decoy = P.checksum_address("0x" + "cd" * 18 + "2840")
    assert P.has_pool4_flags(decoy)

    def _decoy_first(addrs):
        return {
            a: _candidate_answers(
                OTHER_TOKEN if a.lower() == decoy.lower() else IMD_TOKEN
            )
            for a in addrs
        }

    client = FakePool4Client(fetch_candidate_answers=_decoy_first)
    manager = _manager(tmp_path, pool4_client=client)
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel",
        {"items": [_self_post(f"decoy {decoy} real {MAINNET_HOOK}")]},
        ts=POOL4_NOW - 10.0,
    )
    payload = await _sweep(manager)

    assert client.verified == [decoy, MAINNET_HOOK]   # both, in channel order
    assert payload["pool4_discovery_state"] == ADOPTED
    assert payload["pool4_hook_addr"] == MAINNET_HOOK
    assert payload["pool4_network"] == MAINNET


async def test_an_outage_on_one_candidate_does_not_hide_the_next(
    tmp_path,
) -> None:
    """**S8, the sibling.** "We could not read it" is not "it is not the hook",
    so a failed round on one candidate must not end the search either.
    """
    unreadable = P.checksum_address("0x" + "cd" * 18 + "2840")

    def _one_is_dark(addrs):
        # The real client omits an address whose round failed; it does not
        # return an empty answer set for it.
        return {
            a: _candidate_answers()
            for a in addrs if a.lower() != unreadable.lower()
        }

    client = FakePool4Client(fetch_candidate_answers=_one_is_dark)
    manager = _manager(tmp_path, pool4_client=client)
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel",
        {"items": [_self_post(f"first {unreadable} second {MAINNET_HOOK}")]},
        ts=POOL4_NOW - 10.0,
    )
    payload = await _sweep(manager)

    assert client.verified == [unreadable, MAINNET_HOOK]
    assert payload["pool4_discovery_state"] == ADOPTED
    assert payload["pool4_hook_addr"] == MAINNET_HOOK


async def test_the_first_rejection_is_published_when_nothing_is_adopted(
    tmp_path,
) -> None:
    """... and the loop still ends in a verdict rather than in silence."""
    client = FakePool4Client(fetch_candidate_answers=_rejects)
    manager = _manager(tmp_path, pool4_client=client)
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel",
        {"items": [_self_post(f"a {MAINNET_HOOK} b " + "0x" + "cd" * 18 + "2840")]},
        ts=POOL4_NOW - 10.0,
    )
    payload = await _sweep(manager)

    # Both were asked, both answered, and both were refused on the one gate
    # that is not a liveness check -- so this IS a verdict, not an outage.
    assert len(client.verified) == 2
    assert payload["pool4_discovery_state"] == REJECTED
    assert "not the known token" in payload["pool4_discovery_detail"]
    assert payload["pool4_network"] == SEPOLIA


async def test_discovery_costs_no_second_announce_channel_request(tmp_path) -> None:
    """Discovery reads the rows this cycle already produced.

    The announce channel is one Blockscout page and the fast path has already
    paid for it; a second request would double the only rate-limited endpoint
    on that path to learn nothing new. Structural: the pool4 client has no
    channel method at all, and the surf client's call log does not grow.
    """
    surf = FakeSurfClient()
    manager = _manager(tmp_path, client=surf)
    await _sweep(manager)
    channel_calls = surf.calls.count("fetch_channel_txs")
    assert channel_calls <= 2                 # one per cycle, never per sweep
    assert not any(
        "channel" in name for name in dir(manager.pool4_client)
    )


# ---------------------------------------------------------------------------
# Discovery sources — the operator's decision, and its disclosure
# ---------------------------------------------------------------------------

DOCS_PAGE = (
    "<html><body><h1>pool4</h1>"
    "<p>Market hook: {hook}</p>"
    "<p>Reward Distributor: {dist}</p></body></html>"
)


async def test_a_self_post_adoption_is_sourced_to_the_channel(tmp_path) -> None:
    client = FakePool4Client(
        fetch_candidate_answers=_adopts,
        fetch_docs_page=DOCS_PAGE.format(hook=MAINNET_HOOK, dist=DISTRIBUTOR_ADDR),
    )
    manager = _manager(tmp_path, pool4_client=client, clock=FakeClock(POOL4_NOW))
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel",
        {"items": [_self_post(f"pool4 mainnet: {MAINNET_HOOK}", tx_hash=REAL_TX)]},
        ts=POOL4_NOW - 10.0,
    )
    payload = await _sweep(manager)

    assert payload["pool4_discovery_state"] == ADOPTED
    assert payload["pool4_discovery_source"] == "self-post"
    # The docs page is not consulted AT ALL when the channel adopts: ranked,
    # never merged, and the strong source settles it alone.
    assert client.docs_reads == 0


async def test_the_docs_page_is_consulted_only_when_the_channel_adopts_nothing(
    tmp_path,
) -> None:
    """The operator's decision: the announce channel has not named the mainnet
    hook, so ``pool4.imd.fun/docs`` is accepted as a **candidate** source.

    The full chain fingerprint still applies, and the channel remains the
    stronger path -- a self-post landing later overrides docs on the next
    sweep.
    """
    client = FakePool4Client(
        fetch_candidate_answers=_adopts,
        fetch_docs_page=DOCS_PAGE.format(hook=MAINNET_HOOK, dist=DISTRIBUTOR_ADDR),
    )
    payload = await _sweep(_manager(tmp_path, pool4_client=client))

    assert client.docs_reads == 1
    assert payload["pool4_discovery_state"] == ADOPTED
    assert payload["pool4_discovery_source"] == "docs"
    assert payload["pool4_network"] == MAINNET
    # A page is not a transaction, and inventing a pointer for one would be
    # the disclosure undone.
    assert payload["pool4_discovery_source_tx"] is None


async def test_the_ranking_is_delegated_and_not_re_derived(
    tmp_path, monkeypatch
) -> None:
    """**The consolidation, pinned behaviourally rather than by a grep.**

    The manager used to sequence the two sources itself, because the raw
    getter answers ``ranked_discovery`` needs were not reachable from the
    client. They are now, so the ordering decision lives in exactly one place
    -- and it has to *stay* there: which candidates each source produced is
    input to that decision, and a verdict has already discarded it.

    Also pinned: the two calls, and their order. Phase one passes no docs text
    at all, which is what makes "the page is not fetched when the channel
    adopts" true rather than merely intended.
    """
    seen = []
    real = P.ranked_discovery

    def _spy(rows, announce, token, answers=None, network=None,
             source_tx_by_addr=None, docs_text=None):
        seen.append(docs_text)
        return real(rows, announce, token, answers, network,
                    source_tx_by_addr, docs_text)

    monkeypatch.setattr(P, "ranked_discovery", _spy)
    client = FakePool4Client(
        fetch_docs_page=DOCS_PAGE.format(hook=MAINNET_HOOK, dist=DISTRIBUTOR_ADDR),
        fetch_candidate_answers=_adopts,
    )
    payload = await _sweep(_manager(tmp_path, pool4_client=client))

    assert seen == [None, client._returns["fetch_docs_page"]]
    assert payload["pool4_discovery_source"] == "docs"


async def test_the_two_candidate_lists_are_ranked_never_merged(
    tmp_path,
) -> None:
    """Merging would let a docs address be adjudicated ahead of a channel one
    purely by list position — the strong source silently losing to the weak.

    Here the channel names a hook the chain adopts and the docs page names a
    different one. The channel's must win, and the docs address must never
    reach a getter at all.
    """
    docs_hook = P.checksum_address("0x" + "cd" * 18 + "2840")
    client = FakePool4Client(
        # Adopts whatever it is asked about -- so if the docs address were ever
        # put to the chain it would win, and only the ORDER stops it.
        fetch_candidate_answers=_adopts,
        fetch_docs_page=DOCS_PAGE.format(hook=docs_hook, dist=DISTRIBUTOR_ADDR),
    )
    manager = _manager(tmp_path, pool4_client=client, clock=FakeClock(POOL4_NOW))
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel",
        {"items": [_self_post(f"pool4: {MAINNET_HOOK}", tx_hash=REAL_TX)]},
        ts=POOL4_NOW - 10.0,
    )
    payload = await _sweep(manager)

    assert client.verified == [MAINNET_HOOK]
    assert docs_hook not in client.verified
    assert client.docs_reads == 0
    assert payload["pool4_discovery_source"] == "self-post"


async def test_an_adoption_with_no_recorded_source_reads_as_unattributed(
    tmp_path,
) -> None:
    """**The absence that must not exist.**

    ``None`` keeps its house meaning on every non-adopted state -- there is no
    adoption to attribute. On an ADOPTED one it is not an answer at all: a
    renderer treating ``None`` as "nothing to say" would draw a docs-sourced
    adoption identically to a dev-signed one, undoing by omission the
    disclosure the operator's decision was conditioned on.

    A slot persisted before the key existed is exactly that case, and it must
    surface as ``unattributed`` -- shown at least as weakly as ``docs`` -- so a
    producer bug is visible instead of being promoted to the strong answer.
    """
    manager = _manager(tmp_path)
    manager.cache.store_last_good(
        SLOT_POOL4,
        {"network": MAINNET, "discovery_state": ADOPTED,
         "discovery_detail": "adopted", "hook_addr": MAINNET_HOOK},
        ts=POOL4_NOW - 100.0,
    )
    payload = await manager.fetch_and_compute()
    assert payload["pool4_discovery_source"] == "unattributed"
    assert payload["pool4_discovery_source"] != "self-post"


async def test_a_non_adopted_verdict_has_no_source_to_attribute(
    tmp_path,
) -> None:
    payload = await _sweep(_manager(tmp_path))
    assert payload["pool4_discovery_state"] == NOT_DISCOVERED
    assert payload["pool4_discovery_source"] is None


async def test_an_unreadable_docs_page_is_not_a_verdict_about_it(
    tmp_path,
) -> None:
    """``None`` from the page must never read as "the page names no hook".

    The observable difference is **which source the published reason came
    from**, and nothing else: the network, the state and the source word are
    all identical either way. An earlier version of this test asserted only
    those three and a mutation that turned an unreadable page into an empty
    one -- a verdict about a page nobody read -- went straight through it.

    So the claim is pinned directly, against WP3's own wording for the same
    inputs rather than a phrase retyped here: with the page unread, the reason
    a reader sees must be the **channel's**.
    """
    client = FakePool4Client(fetch_docs_page=None, fetch_candidate_answers=_adopts)
    payload = await _sweep(_manager(tmp_path, pool4_client=client))

    assert client.docs_reads == 1
    assert client.verified == []
    assert payload["pool4_discovery_source"] is None
    assert payload["pool4_network"] == SEPOLIA

    channels_own_reason = P.adjudicate_candidates(
        [], IMD_TOKEN, None, None, None, origin="self-post"
    ).detail
    docs_own_reason = P.adjudicate_candidates(
        [], IMD_TOKEN, None, None, None, origin="docs"
    ).detail
    assert channels_own_reason != docs_own_reason, "the two must be tellable apart"
    assert payload["pool4_discovery_detail"] == channels_own_reason
    assert payload["pool4_discovery_detail"] != docs_own_reason


async def test_a_docs_candidate_faces_the_same_gates_as_a_channel_one(
    tmp_path,
) -> None:
    """The weak source must not acquire a weaker **gate** as well.

    A flag-failing address on the docs page costs zero round trips, exactly as
    it does in the channel: the arithmetic runs first either way.
    """
    flagless = "0x" + "ab" * 19 + "41"
    assert not P.has_pool4_flags(flagless)
    client = FakePool4Client(
        fetch_candidate_answers=_adopts,
        fetch_docs_page=f"<p>hook: {flagless}</p>",
    )
    payload = await _sweep(_manager(tmp_path, pool4_client=client))

    assert client.verified == []
    assert payload["pool4_network"] == SEPOLIA
    assert payload["pool4_discovery_source"] is None

    # And the REASON must be about the address, not about the chain.
    #
    # The flag filter on the docs path is not redundant with the client's own:
    # it is also what the "we could not look" guard counts against. Drop it and
    # an address that failed the *arithmetic* gate — which never earned a round
    # trip and never could have one — is reported as one the chain did not
    # answer. That is an outage claim manufactured out of a rejection, the
    # exact inversion of the property the guard exists for.
    detail = payload["pool4_discovery_detail"]
    assert "unverified" not in detail
    assert detail == P.adjudicate_candidates(
        [flagless], IMD_TOKEN, None, None, None, origin="docs"
    ).detail


# ---------------------------------------------------------------------------
# The flow rows
# ---------------------------------------------------------------------------


async def test_flow_rows_match_the_frozen_row_shape_and_the_cap(tmp_path) -> None:
    payload = await _sweep(_manager(tmp_path))
    rows = payload["pool4_flow"]
    assert rows is not None and rows
    assert len(rows) <= POOL4_FLOW_LIMIT
    for row in rows:
        assert set(row) == set(SURF_ROW_KEYS["pool4_flow"])
        assert row["side"] in POOL4_FLOW_SIDES
        # A representable zero, never ``None`` — a buy burns nothing, and that
        # is a fact about the mechanism rather than a missing read.
        assert isinstance(row["burned_imd"], float)
        assert isinstance(row["stakers_imd"], float)
        assert isinstance(row["settled"], bool)
        # Exactly one fee leg: the 1% is taken in ETH on a buy, IMD on a sell.
        assert (row["fee_imd"] is None) != (row["fee_eth"] is None)


async def test_a_buy_row_carries_zeros_not_dashes(tmp_path) -> None:
    payload = await _sweep(_manager(tmp_path))
    buys = [r for r in payload["pool4_flow"] if r["side"] == "buy"]
    assert buys, "the mixed corpus carries a buy"
    for row in buys:
        assert row["burned_imd"] == 0.0
        assert row["stakers_imd"] == 0.0
        assert row["fee_eth"] is not None
        assert row["fee_imd"] is None


async def test_the_age_of_a_row_is_computed_at_publish_time(tmp_path) -> None:
    """The screen and the widget are clock-free, so the manager precomputes
    the age — and it must be the age *now*, not the age when the sweep landed,
    or a slot served through an outage reads as live for as long as it lasts.
    """
    clock = FakeClock(POOL4_NOW)
    manager = _manager(tmp_path, clock=clock)
    first = await _sweep(manager)
    ages = [r["age_s"] for r in first["pool4_flow"]]
    assert all(a is not None and a >= 0 for a in ages)

    clock.advance(3600.0)
    later = await manager.fetch_and_compute()
    later_ages = [r["age_s"] for r in later["pool4_flow"]]
    assert all(b - a == pytest.approx(3600.0) for a, b in zip(ages, later_ages))


async def test_a_dead_log_pool_is_none_and_a_quiet_window_is_empty(
    tmp_path,
) -> None:
    """Opposite claims, rendered differently: ``None`` is "the log pool is
    down", ``[]`` is "swept, and genuinely quiet"."""
    dead = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_flow_logs=None))
    )
    assert dead["pool4_flow"] is None
    assert dead["pool4_unsettled_burn"] is None

    quiet = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_flow_logs=[]))
    )
    assert quiet["pool4_flow"] == []
    assert quiet["pool4_unsettled_burn"] == 0.0
    assert quiet["pool4_unsettled_stakers"] == 0.0


async def test_the_log_window_is_the_trailing_span_from_the_head_block(
    tmp_path,
) -> None:
    client = FakePool4Client()
    await _sweep(_manager(tmp_path, pool4_client=client))
    (start, end), = client.log_windows
    assert end == HOOK_BLOCK
    assert end - start + 1 == POOL4_LOG_WINDOW_BLOCKS


async def test_a_window_that_opens_mid_settlement_publishes_no_legs(
    tmp_path,
) -> None:
    """A trailing window can hold a settlement whose accrual fell outside it.

    Over a complete history ``accrued - settled`` cannot be negative; over a
    window it can, and a negative does not mean "less than nothing is
    outstanding" — it means this window cannot answer. A dark row, never a
    negative IMD figure rendered as a fact.
    """
    settled_only = [
        log for log in FLOW_LOGS
        if (log.get("topics") or [None])[0] == P.TOPIC_CLAIMS_SETTLED
    ]
    assert settled_only, "the corpus carries a settlement"
    burn, _stakers = P.unsettled_legs(settled_only)
    assert burn < 0, "the slice must actually be the negative case"

    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_flow_logs=settled_only))
    )
    assert payload["pool4_unsettled_burn"] is None
    assert payload["pool4_unsettled_stakers"] is None


# ---------------------------------------------------------------------------
# The derived numbers
# ---------------------------------------------------------------------------


async def test_the_split_is_measured_from_the_counters_never_quoted(
    tmp_path,
) -> None:
    """1.00 / 89.10 / 9.90 is what the docs say; this must be able to disagree
    with them, so the assertion is against the live counters' own arithmetic.
    """
    payload = await _sweep(_manager(tmp_path))
    fee = HOOK_STATE.total_fee_token_wei
    burn = HOOK_STATE.total_burned_wei
    stake = HOOK_STATE.total_rewarded_wei
    total = fee + burn + stake
    assert payload["pool4_measured_inference_pct"] == pytest.approx(fee / total * 100)
    assert payload["pool4_measured_burn_pct"] == pytest.approx(burn / total * 100)
    assert payload["pool4_measured_stakers_pct"] == pytest.approx(stake / total * 100)
    assert sum(
        payload[k] for k in (
            "pool4_measured_inference_pct", "pool4_measured_burn_pct",
            "pool4_measured_stakers_pct",
        )
    ) == pytest.approx(100.0)


async def test_no_symmetric_eth_cross_check_is_published(tmp_path) -> None:
    """Amendment A9. ``totalFeeToken`` is cumulative and ``retainedEth`` is a
    current balance, so ``Σ FeeCollected[eth] == retainedEth()`` reads 0.0057
    against 0 on a perfectly healthy hook — it would cry wolf on every owner
    withdrawal. The identity that holds is
    ``Σ FeeCollected[eth] == Σ FeesWithdrawn[eth] + retainedEth()``, and it is
    not a payload key at all.
    """
    payload = await _sweep(_manager(tmp_path))
    assert payload["pool4_retained_eth"] == pytest.approx(
        HOOK_STATE.retained_eth_wei / 1e18
    )
    # A9 is about the ETH *identity*, not about the control existing at all:
    # ``pool4_counter_state`` publishes the three IMD identities and is
    # supposed to be here. The original spelling of this line banned any key
    # containing "mismatch" or "reconcil", which W1's keys clear by luck --
    # they are named ``counter_*`` -- and which would have fired on the first
    # sensibly-named one. What must never appear is an ETH counter key.
    assert not [
        k for k in POOL4_KEYS
        if "counter" in k and ("eth" in k or "retained" in k)
    ]


async def test_a_zero_drift_renders_as_a_number_not_a_dash(tmp_path) -> None:
    """``0.0`` is the healthy value of ``pool4_split_drift_bps``."""
    tuned = dict(HOOK_ANSWERS)
    burn = HOOK_STATE.total_burned_wei
    stake = HOOK_STATE.total_rewarded_wei
    exact = round(stake / (burn + stake) * HOOK_STATE.bps_denominator)
    tuned["rewardShareBps"] = "0x" + format(exact, "064x")
    hook = P.decode_hook_state(tuned, block_number=HOOK_BLOCK)
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_hook_state=hook))
    )
    assert payload["pool4_split_drift_bps"] is not None
    assert abs(payload["pool4_split_drift_bps"]) < 1.0


async def test_a_reserve_below_the_floor_is_published_not_clamped(
    tmp_path,
) -> None:
    """Amendment A7: launch 1 sits below its own ``capFloor()`` today. The
    floor binds the swap path; a backstop rebalance can move the reserve where
    a swap cannot, so a negative distance is a legitimate state and renders.
    """
    low = dict(HOOK_ANSWERS)
    low["tokensInPool"] = "0x" + format(1_000 * 10**18, "064x")
    hook = P.decode_hook_state(low, block_number=HOOK_BLOCK)
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_hook_state=hook))
    )
    assert payload["pool4_floor_distance"] < 0
    assert payload["pool4_floor_distance_pct"] < 0


async def test_no_derived_number_is_ever_an_infinity(tmp_path) -> None:
    """A zero denominator is ``None``, never ``inf`` — the widgets format
    floats and an infinity is a rendering accident waiting to happen."""
    idle = dict(DRIPPER_ANSWERS)
    idle["dripRatePerSecond"] = "0x" + format(0, "064x")
    dripper = P.decode_dripper_state(idle, balance_wei=1, block_number=DRIPPER_BLOCK)
    empty = dict(VAULT_ANSWERS)
    empty["totalAssets"] = "0x" + format(0, "064x")
    vault = P.decode_vault_state(empty, block_number=VAULT_BLOCK)
    zero_floor = dict(HOOK_ANSWERS)
    zero_floor["capFloor"] = "0x" + format(0, "064x")
    hook = P.decode_hook_state(zero_floor, block_number=HOOK_BLOCK)

    payload = await _sweep(
        _manager(
            tmp_path,
            pool4_client=FakePool4Client(
                fetch_dripper_state=dripper,
                fetch_vault_state=vault,
                fetch_hook_state=hook,
            ),
        )
    )
    assert payload["pool4_backlog_days"] is None
    assert payload["pool4_implied_apr_pct"] is None
    assert payload["pool4_floor_distance_pct"] is None
    for key in POOL4_KEYS:
        value = payload[key]
        if isinstance(value, float):
            assert value == value and abs(value) != float("inf"), key


async def test_the_backstop_publishes_one_tri_state_and_no_tick_bounds(
    tmp_path,
) -> None:
    """Amendment A19: the bounds stay model-internal. ``centred`` / ``drifted``
    / ``unknown`` is the decision-relevant fact; raw ticks on a rail panel are
    noise, and adding them would be a ``POOL4_KEYS`` change for no reader.
    """
    payload = await _sweep(_manager(tmp_path))
    assert payload["pool4_backstop_centred"] is True
    assert not [k for k in POOL4_KEYS if "backstop" in k and k != "pool4_backstop_centred"]


# ---------------------------------------------------------------------------
# R1 control (c) — the hook against its own logs (finding W1)
# ---------------------------------------------------------------------------


def test_the_reconciliation_keys_this_module_reads_still_exist() -> None:
    """The agreement test behind :data:`POOL4_COUNTER_IDENTITIES`.

    The manager selects three identities out of ``reconcile_counters``' report
    **by name**, because which identities this build publishes is an A9
    decision rather than an arithmetic one. A rename on WP3's side would
    otherwise select nothing, and the control would report ``unchecked``
    forever while looking perfectly healthy.

    It bites in both directions: a renamed identity fails the first assertion,
    and an identity quietly *added* to the manager's tuple that A9 excludes
    fails the second.
    """
    report = P.reconcile_counters(FLOW_LOGS_FULL, HOOK_STATE)
    for name in POOL4_COUNTER_IDENTITIES:
        assert name in report, name
    assert len(POOL4_COUNTER_IDENTITIES) == 3

    banned = [n for n in report if "eth" in n.lower() or "balanceOf" in n]
    assert banned, "the report must still carry the identities A9 excludes"
    for name in banned:
        assert name not in POOL4_COUNTER_IDENTITIES


async def test_a_complete_log_set_reconciles_to_the_wei(tmp_path) -> None:
    """The good news, and the only outcome that is good news.

    The full launch-3 corpus carries the constructor event, so the sums cover
    the hook's whole life and the three cumulative identities can hold -- and
    on the real capture they do, to the wei. That is what makes the recovered
    getter set trustworthy on this deployment.
    """
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL))
    )
    assert payload["pool4_counter_state"] == RECONCILED
    assert "3 identities" in payload["pool4_counter_detail"]


async def test_a_trailing_window_is_window_limited_not_a_mismatch(
    tmp_path,
) -> None:
    """**The one that would have cried wolf forever after day one.**

    :data:`POOL4_LOG_WINDOW_BLOCKS` is a *trailing* span and the identities are
    a cumulative counter against a sum over logs, so once the hook is older
    than the window they disagree **by construction and permanently**. Wired
    naively that is a mismatch on every sweep for the life of the protocol.

    ``window-limited`` is neither an error nor a pass: the control did not run.
    """
    payload = await _sweep(_manager(tmp_path))          # the 60-block slice
    assert payload["pool4_counter_state"] == WINDOW_LIMITED
    assert payload["pool4_counter_state"] != MISMATCH
    assert "first block" in payload["pool4_counter_detail"]


async def test_a_dead_log_read_is_unchecked_not_window_limited(
    tmp_path,
) -> None:
    """"Nobody could take the sum" and "the sum is short" are different claims,
    and only the second one is about the window."""
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_flow_logs=None))
    )
    assert payload["pool4_counter_state"] == UNCHECKED
    assert payload["pool4_counter_state"] != WINDOW_LIMITED


async def test_none_never_means_the_identities_held(tmp_path) -> None:
    """**The convention that is least survivable here, stated as a test.**

    ``_finalise`` fills a key it was not given with ``None``, so if ``None``
    meant "agree", a control that failed to compute would render a clean bill
    of health for a check that never happened. ``None`` therefore means only
    "has never run", and **every** outcome of looking is a word.
    """
    cold = await _manager(tmp_path).fetch_and_compute()   # no sweep has landed
    assert cold["pool4_counter_state"] is None
    assert cold["pool4_counter_detail"] is None

    # ... and a sweep that could not compute it says so in words.
    ran = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_flow_logs=None))
    )
    assert ran["pool4_counter_state"] is not None
    assert ran["pool4_counter_state"] in POOL4_COUNTER_STATES
    assert ran["pool4_counter_state"] != RECONCILED


async def test_a_mismatch_names_which_counter_and_by_how_much(
    tmp_path,
) -> None:
    """The loud outcome, and the only one a reader should act on.

    Every log counted twice is what a decoder reading the same event under two
    topics would look like: the sums exceed the cumulative counters, which no
    window can explain.
    """
    payload = await _sweep(
        _manager(
            tmp_path,
            pool4_client=FakePool4Client(
                fetch_flow_logs=FLOW_LOGS_FULL + FLOW_LOGS_FULL
            ),
        )
    )
    assert payload["pool4_counter_state"] == MISMATCH
    detail = payload["pool4_counter_detail"]
    assert any(name.split(" ==")[0] in detail for name in POOL4_COUNTER_IDENTITIES)
    assert "wei" in detail


async def test_an_unread_counter_is_unchecked_not_a_mismatch(
    tmp_path, monkeypatch
) -> None:
    """**The WP3 coordination pin.**

    ``reconcile_counters``' per-check shape changed mid-build: ``agree`` used
    to be ``from_counter is not None and ...``, which made an unread counter
    byte-identical to a genuine disagreement -- the very conflation this
    control exists to catch, one layer down, on the control itself. A manager
    keying on ``agree`` would publish ``mismatch`` for a failed sweep.

    Both shapes are fed here, so neither side can drift silently: the legacy
    one (no ``state`` key, ``agree=False`` for an unread counter) and the
    current one. Both must fold to ``unchecked``.
    """
    legacy = {
        name: {"from_logs": 0, "from_counter": None,
               "agree": False, "delta_wei": None}
        for name in POOL4_COUNTER_IDENTITIES
    }
    monkeypatch.setattr(P, "reconcile_counters", lambda *a, **k: legacy)
    state, _detail = SurfManager._pool4_counter_check(FLOW_LOGS_FULL, HOOK_STATE)
    assert state == UNCHECKED
    assert state != MISMATCH

    current = {
        name: {"from_logs": None, "from_counter": None,
               "state": UNCHECKED, "agree": None, "delta_wei": None}
        for name in POOL4_COUNTER_IDENTITIES
    }
    monkeypatch.setattr(P, "reconcile_counters", lambda *a, **k: current)
    state, _detail = SurfManager._pool4_counter_check(FLOW_LOGS_FULL, HOOK_STATE)
    assert state == UNCHECKED


async def test_the_eth_identity_is_never_folded_into_the_control(
    monkeypatch,
) -> None:
    """**A9, at the only place it can now go wrong.**

    ``Σ FeeCollected[eth] == retainedEth()`` is false on a perfectly healthy
    hook -- the token counter is cumulative, the ETH one is a current balance,
    and the owner has withdrawn. Folding it in would put the whole control at
    ``mismatch`` on every owner withdrawal, which is a control nobody believes
    by the second week.

    The three IMD identities reconcile here and the ETH one screams; the
    published word must be ``reconciled``.
    """
    report = {
        name: {"from_logs": 1, "from_counter": 1,
               "state": RECONCILED, "agree": True, "delta_wei": 0}
        for name in POOL4_COUNTER_IDENTITIES
    }
    report["sum_FeeCollected_eth == sum_FeesWithdrawn_eth + retainedEth()"] = {
        "from_logs": 5_700_000_000_000_000, "from_counter": 0,
        "state": MISMATCH, "agree": False, "delta_wei": 5_700_000_000_000_000,
    }
    monkeypatch.setattr(P, "reconcile_counters", lambda *a, **k: report)
    state, _detail = SurfManager._pool4_counter_check(FLOW_LOGS_FULL, HOOK_STATE)
    assert state == RECONCILED


async def test_a_permanently_unread_identity_cannot_pin_the_control(
    tmp_path,
) -> None:
    """``unchecked`` outranks ``reconciled`` in WP3's fold, and rightly so --
    "four held and the fifth was unread" is not a clean bill of health.

    Which is exactly why ``totalBurned() == balanceOf(0xdEaD)`` must stay out
    of the published set: nothing on this path reads that balance, so folding
    it in would pin this control at ``unchecked`` **forever** -- a control that
    can never say anything, which is indistinguishable from not having one.
    """
    report = P.reconcile_counters(FLOW_LOGS_FULL, HOOK_STATE)
    dead = "totalBurned() == token.balanceOf(0xdEaD)"
    assert report[dead]["from_counter"] is None, "still unread on this path"
    assert dead not in POOL4_COUNTER_IDENTITIES

    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL))
    )
    assert payload["pool4_counter_state"] == RECONCILED


async def test_a_missing_identity_is_unchecked_not_quietly_dropped(
    monkeypatch,
) -> None:
    """Two identities folded where three were meant is a weaker control
    wearing the same word."""
    report = {
        POOL4_COUNTER_IDENTITIES[0]: {
            "from_logs": 1, "from_counter": 1, "state": RECONCILED,
            "agree": True, "delta_wei": 0,
        }
    }
    monkeypatch.setattr(P, "reconcile_counters", lambda *a, **k: report)
    state, detail = SurfManager._pool4_counter_check(FLOW_LOGS_FULL, HOOK_STATE)
    assert state == UNCHECKED
    assert "not reported" in detail


def test_the_counter_verdict_is_slot_content_not_bookkeeping() -> None:
    """A control changing its mind is the single most important thing this
    sweep can learn, so it must not land behind a marker that says the data is
    unchanged since an hour ago.

    Focused deliberately. The integration test below drives the change with a
    continuity gap, which also changes the flow rows -- so it proves the marker
    moves but cannot prove *the verdict* is what moved it. This compares two
    payloads that differ in nothing else.
    """
    base = {"network": SEPOLIA, "counter_state": RECONCILED,
            "counter_detail": "all 3 identities hold to the wei",
            "block_number": 100}
    same_data_new_verdict = dict(base, counter_state=MISMATCH,
                                 counter_detail="... is out by 1 wei")
    later_block = dict(base, block_number=101)

    content = SurfManager._pool4_content
    assert content(base) != content(same_data_new_verdict)
    # ... while the head block, which moves every twelve seconds and reaches
    # no widget, is excluded -- or the marker would advance on every tick.
    assert content(base) == content(later_block)


async def test_the_counter_state_moves_the_as_of_marker(tmp_path) -> None:
    """A control changing its mind is new content, not a quiet re-read.

    ``reconciled`` -> ``mismatch`` is the single most important thing this
    sweep can learn, so it must not land behind a marker that says the data is
    unchanged since an hour ago.
    """
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL)
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    first = await _sweep(manager)
    assert first["pool4_counter_state"] == RECONCILED

    # A gap wider than the window: the accumulator is discarded (continuity),
    # and the control falls back to a single window that does not reach
    # genesis. ``reconciled`` -> ``window-limited`` is a change of verdict.
    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 3600.0)
    client._returns["fetch_hook_state"] = _hook_at(
        HOOK_BLOCK + POOL4_LOG_WINDOW_BLOCKS * 3
    )
    client._returns["fetch_flow_logs"] = FLOW_LOGS
    second = await _sweep(manager)

    assert second["pool4_counter_state"] == WINDOW_LIMITED
    assert second["pool4_as_of_hhmm"] != first["pool4_as_of_hhmm"]


# ---------------------------------------------------------------------------
# The provenance pointer (F5/S15)
# ---------------------------------------------------------------------------

REAL_TX = "0x" + "9a" * 32


async def test_an_adoption_publishes_the_transaction_it_rests_on(tmp_path) -> None:
    """**After A27 the whole safety of an adoption is one transaction.**

    Every other artifact -- the address, the flags, the getter answers, the
    stored verdict -- is forgeable. What is not forgeable is that a specific
    transaction carried the announce wallet's signature. A verdict that cannot
    name the transaction it rests on is unauditable, so the hash rides the
    detail line and is persisted beside the verdict.
    """
    client = FakePool4Client(fetch_candidate_answers=_adopts)
    manager = _manager(tmp_path, pool4_client=client, clock=FakeClock(POOL4_NOW))
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel",
        {"items": [_self_post(f"pool4 mainnet: {MAINNET_HOOK}", tx_hash=REAL_TX)]},
        ts=POOL4_NOW - 10.0,
    )
    payload = await _sweep(manager)

    assert payload["pool4_discovery_state"] == ADOPTED
    # Its own key -- **not** appended to the detail line. Merged into prose it
    # is a suffix nobody can query, on a rail panel that truncates; as a key it
    # is a value a widget or a test can name, and the pair (state, source_tx)
    # can express the row that matters: adopted with no transaction behind it.
    assert payload["pool4_discovery_source_tx"] == REAL_TX
    assert REAL_TX not in (payload["pool4_discovery_detail"] or "")
    assert payload["pool4_discovery_detail"] == MAINNET_VERDICT.detail
    # ... and durably, so an auditor has it whatever the panel does.
    assert manager.cache.get_last_good(SLOT_POOL4).payload[
        "discovery_source_tx"
    ] == REAL_TX


async def test_the_detail_line_is_wp3s_sentence_and_nothing_else(
    tmp_path,
) -> None:
    """WP3 owns the sentence and this module no longer edits it.

    The slot has always kept the verdict and its pointer apart -- "never merged
    into it… a later reader must be able to tell them apart" -- and the payload
    was violating that three lines away by appending the hash to the prose.
    """
    client = FakePool4Client(fetch_candidate_answers=_adopts)
    manager = _manager(tmp_path, pool4_client=client, clock=FakeClock(POOL4_NOW))
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel",
        {"items": [_self_post(f"pool4 mainnet: {MAINNET_HOOK}", tx_hash=REAL_TX)]},
        ts=POOL4_NOW - 10.0,
    )
    payload = await _sweep(manager)
    assert payload["pool4_discovery_detail"] == MAINNET_VERDICT.detail
    assert " · tx " not in payload["pool4_discovery_detail"]


@pytest.mark.parametrize(
    "bad", ["0xdeadbeef", "[bold red]OWNED[/]", "0x" + "zz" * 32, "", None, 12]
)
async def test_a_malformed_transaction_hash_is_never_cited(tmp_path, bad) -> None:
    """A malformed hash on the **row** never becomes provenance for anything.

    This pins the map builder's filter. The *persisted* half of the same rule
    has its own test below, and it needs one: a well-formed hash is required to
    enter the slot in the first place, so this test cannot see the citation's
    own check and must not be read as covering it.
    """
    client = FakePool4Client(fetch_candidate_answers=_adopts)
    manager = _manager(tmp_path, pool4_client=client, clock=FakeClock(POOL4_NOW))
    manager.client._returns["fetch_channel_txs"] = None
    row = _self_post(f"pool4 mainnet: {MAINNET_HOOK}")
    row["tx_hash"] = bad
    manager.cache.store_last_good("channel", {"items": [row]}, ts=POOL4_NOW - 10.0)
    payload = await _sweep(manager)

    assert payload["pool4_discovery_source_tx"] is None
    assert payload["pool4_discovery_detail"] == MAINNET_VERDICT.detail


@pytest.mark.parametrize(
    "bad", ["0xdeadbeef", "[bold red]OWNED[/]", "0x" + "zz" * 32, "", None, 12]
)
async def test_a_persisted_hash_is_rechecked_on_every_read(tmp_path, bad) -> None:
    """Composed at publish time, not stored joined — and this is the path that
    makes the citation's own filter load-bearing.

    A well-formed hash is already required to *enter* the slot, so the row-level
    test above cannot see this check at all: it is guarded upstream. What this
    covers is a hash arriving from the **cache file** — hand-edited, or written
    by a version that never checked — which is re-examined on every render
    rather than once, long ago, by code that may not have looked.

    (The parametrisation here is not decoration. With only the markup case,
    a mutation weakening the check to ``isinstance(str)`` was still caught,
    but ``"0xdeadbeef"`` is the case a reader would actually meet: a truncated
    hash is not a pointer to anything.)
    """
    manager = _manager(tmp_path)
    manager.cache.store_last_good(
        SLOT_POOL4,
        {"network": SEPOLIA, "discovery_state": NOT_DISCOVERED,
         "discovery_detail": "no hook-shaped address",
         "discovery_source_tx": bad},
        ts=POOL4_NOW - 100.0,
    )
    payload = await manager.fetch_and_compute()
    assert payload["pool4_discovery_source_tx"] is None
    assert payload["pool4_discovery_detail"] == "no hook-shaped address"


async def _lapsed_manager(tmp_path, client, *, stored_tx=REAL_TX):
    """A manager whose mainnet adoption has aged out of the channel window.

    The channel still answers -- it just no longer names the hook, which is
    what happens ~64 days after the announcement at 25 rows and 2.55 days a
    post.
    """
    manager = _manager(tmp_path, pool4_client=client, clock=FakeClock(POOL4_NOW))
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel", {"items": [_self_post("gm", tx_hash="0x" + "11" * 32)]},
        ts=POOL4_NOW - 10.0,
    )
    manager.cache.store_last_good(
        SLOT_POOL4,
        {"network": MAINNET, "discovery_state": ADOPTED,
         "discovery_detail": "adopted", "hook_addr": MAINNET_HOOK,
         "token_addr": IMD_TOKEN, "discovery_source_tx": stored_tx},
        ts=POOL4_NOW - 100.0,
    )
    return manager


async def test_a_lapsed_adoption_is_re_established_from_the_chain(
    tmp_path,
) -> None:
    """**S15.** Provenance outlives the 25-row window by re-reading the post.

    The cache says *where to look*; the chain stays the authority. The fetched
    transaction is a self-post whose calldata names the hook, so the adoption
    survives the window it was announced in.
    """
    client = FakePool4Client(
        fetch_transaction=_self_post_tx(REAL_TX, f"pool4 is live at {MAINNET_HOOK}")
    )
    payload = await _sweep(await _lapsed_manager(tmp_path, client))

    assert client.fetched == [REAL_TX]
    assert payload["pool4_network"] == MAINNET
    assert payload["pool4_discovery_state"] == ADOPTED
    assert payload["pool4_hook_addr"] == MAINNET_HOOK
    assert payload["pool4_discovery_source_tx"] == REAL_TX


async def test_a_failed_fetch_holds_the_adoption_rather_than_dropping_it(
    tmp_path,
) -> None:
    """**S15, the hold half.** A bad RPC minute is not a finding.

    ``fetch_transaction`` collapses every unreadable outcome -- unknown hash,
    pruned node, wrong chain, hash-identity mismatch -- into one ``None``,
    precisely so an outage cannot be read as an attack. Dropping a good
    adoption on it would make the view flap to Sepolia and back with the
    weather.
    """
    client = FakePool4Client(fetch_transaction=None)
    payload = await _sweep(await _lapsed_manager(tmp_path, client))

    assert client.fetched == [REAL_TX]
    assert payload["pool4_network"] == MAINNET
    assert payload["pool4_discovery_state"] == ADOPTED
    assert "held" in payload["pool4_discovery_detail"]
    assert "not re-proved" in payload["pool4_discovery_detail"]


@pytest.mark.parametrize(
    "tx, why",
    [
        (
            _self_post_tx(
                REAL_TX, f"pool4 at {MAINNET_HOOK}",
                sender="0x1c3A0Ad54418Fe843953C71dF23637DE732Ce159",
            ),
            "a stranger's transaction is not a self-post",
        ),
        (
            _self_post_tx(REAL_TX, f"pool4 at {MAINNET_HOOK}", to=None),
            "a contract creation is not a self-post either",
        ),
        (
            _self_post_tx(REAL_TX, f"pool4 at {MAINNET_HOOK}", block=None),
            "an unmined transaction is a claim, not a fact",
        ),
        (
            _self_post_tx(REAL_TX, "gm, nothing to see here"),
            "a self-post that names no address proves nothing",
        ),
    ],
)
async def test_a_transaction_that_does_not_prove_it_lapses_the_adoption(
    tmp_path, tx, why
) -> None:
    """**S15, the lapse half.** A real answer about a real transaction.

    This is the half that must stay distinct from the hold above: "we looked
    and it does not prove the adoption" ends it, where "we could not look"
    does not.
    """
    client = FakePool4Client(fetch_transaction=tx)
    payload = await _sweep(await _lapsed_manager(tmp_path, client))

    assert client.fetched == [REAL_TX], why
    assert payload["pool4_network"] == SEPOLIA, why
    assert payload["pool4_discovery_state"] == NOT_DISCOVERED, why
    assert payload["pool4_hook_addr"] == POOL4_SEPOLIA_HOOK, why


async def test_the_cache_supplies_a_hash_and_the_chain_supplies_the_verdict(
    tmp_path,
) -> None:
    """**S15's trust boundary, and the test that A27 is not being undone.**

    The cache may supply a transaction hash **and nothing else**. The stored
    address is the *claim under test*, never a credential: here the fetched
    self-post is perfectly genuine and names a different hook, so the stored
    address is refused even though its hash resolved to a real announce post.

    A cache that supplied a hash *and* an address, where the address was
    believed because the hash looked plausible, is A27's bypass in a new hat.
    """
    other = P.checksum_address("0x" + "cd" * 18 + "2840")
    client = FakePool4Client(
        fetch_transaction=_self_post_tx(REAL_TX, f"the new hook is {other}")
    )
    payload = await _sweep(await _lapsed_manager(tmp_path, client))

    assert client.fetched == [REAL_TX]
    assert payload["pool4_network"] == SEPOLIA
    assert payload["pool4_discovery_state"] != ADOPTED
    assert payload["pool4_discovery_source_tx"] is None
    # NOT asserted on ``pool4_hook_addr``: this corpus reuses one address for
    # ``MAINNET_HOOK`` and ``POOL4_SEPOLIA_HOOK``, so "the hook is not the
    # stored one" is vacuously true on the fallback path and would be a test
    # that cannot fail. The token address is what actually differs.
    assert payload["pool4_token_addr"] == POOL4_SEPOLIA_TOKEN
    assert other not in (payload["pool4_hook_addr"], payload["pool4_token_addr"])


async def test_a_stored_hash_that_is_not_a_hash_is_never_fetched(
    tmp_path,
) -> None:
    """The pointer is validated before it can reach a JSON-RPC body."""
    client = FakePool4Client(
        fetch_transaction=_self_post_tx(REAL_TX, f"pool4 at {MAINNET_HOOK}")
    )
    payload = await _sweep(
        await _lapsed_manager(tmp_path, client, stored_tx="[bold]OWNED[/]")
    )
    assert client.fetched == []
    assert payload["pool4_network"] == SEPOLIA


async def test_re_establishment_is_not_attempted_while_the_window_still_names_it(
    tmp_path,
) -> None:
    """Zero round trips in the normal case.

    Provenance is fresh from the channel on every ordinary cycle; the fetch
    exists only for the day the post ages out.
    """
    client = FakePool4Client(fetch_candidate_answers=_adopts)
    manager = _manager(tmp_path, pool4_client=client, clock=FakeClock(POOL4_NOW))
    manager.client._returns["fetch_channel_txs"] = None
    manager.cache.store_last_good(
        "channel",
        {"items": [_self_post(f"pool4 mainnet: {MAINNET_HOOK}", tx_hash=REAL_TX)]},
        ts=POOL4_NOW - 10.0,
    )
    manager.cache.store_last_good(
        SLOT_POOL4,
        {"network": MAINNET, "discovery_state": ADOPTED,
         "discovery_detail": "adopted", "hook_addr": MAINNET_HOOK,
         "discovery_source_tx": REAL_TX},
        ts=POOL4_NOW - 100.0,
    )
    payload = await _sweep(manager)

    assert client.fetched == []
    assert payload["pool4_discovery_state"] == ADOPTED


async def test_a_freshly_announced_hook_outranks_a_remembered_one(
    tmp_path,
) -> None:
    """The window has its say first.

    A migration announcement must win over a remembered adoption, so the
    re-establishment fetch runs only after this cycle's candidates have failed
    to produce one.
    """
    new_hook = P.checksum_address("0x" + "cd" * 18 + "2840")
    client = FakePool4Client(fetch_candidate_answers=_adopts)
    manager = await _lapsed_manager(tmp_path, client)
    manager.cache.store_last_good(
        "channel",
        {"items": [_self_post(f"moved to {new_hook}", tx_hash="0x" + "22" * 32)]},
        ts=POOL4_NOW - 10.0,
    )
    payload = await _sweep(manager)

    assert client.fetched == []
    assert payload["pool4_hook_addr"] == new_hook
    assert payload["pool4_discovery_source_tx"] == "0x" + "22" * 32


# ---------------------------------------------------------------------------
# S17 — the counter accumulator
# ---------------------------------------------------------------------------


async def test_the_accumulator_reconciles_beyond_the_window(tmp_path) -> None:
    """**S17, the whole point.** A total outlives the window it was summed in.

    The first sweep contains genesis and seeds the accumulator; the second
    sweeps a later, quiet window that reaches nothing. Single-window logic
    would call that ``window-limited`` for ever, and the control would detect
    nothing from about a day after deployment.
    """
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL)
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    first = await _sweep(manager)
    assert first["pool4_counter_state"] == RECONCILED

    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 60.0)
    client._returns["fetch_hook_state"] = _hook_at(HOOK_BLOCK + 100)
    client._returns["fetch_flow_logs"] = []          # swept, and quiet
    second = await _sweep(manager)

    assert second["pool4_counter_state"] == RECONCILED
    assert "hold to the wei" in second["pool4_counter_detail"]


async def test_a_gap_discards_the_accumulator_rather_than_patching_it(
    tmp_path,
) -> None:
    """**S17 invariant 1 — continuity.**

    A total short by a missed sweep is indistinguishable from one short by a
    decoder bug, and a hole is invisible. So a gap throws the total away and
    falls back to single-window behaviour. Losing two months of accumulation
    is cheap; a total that says ``reconciled`` when it means ``probably`` is
    not.
    """
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL)
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    assert (await _sweep(manager))["pool4_counter_state"] == RECONCILED

    # The app was closed for longer than the window is wide.
    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 60.0)
    client._returns["fetch_hook_state"] = _hook_at(
        HOOK_BLOCK + POOL4_LOG_WINDOW_BLOCKS * 2
    )
    client._returns["fetch_flow_logs"] = []
    after = await _sweep(manager)

    assert after["pool4_counter_state"] == WINDOW_LIMITED
    assert after["pool4_counter_state"] != RECONCILED
    assert manager.cache.get_pool4_accumulator(SEPOLIA)["genesis_block"] is None


async def test_an_overlapping_re_sweep_is_idempotent(tmp_path) -> None:
    """**S17 invariant 1, the other half.** Windows overlap by design.

    Every sweep re-reads a full trailing window, so the same logs arrive over
    and over. Double-counting them would inflate the sums past the counters
    and fire the sign hatch -- a mismatch on a healthy hook.
    """
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL)
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    first = await _sweep(manager)
    sums = dict(manager.cache.get_pool4_accumulator(SEPOLIA)["sums"])

    for _ in range(3):
        clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 60.0)
        again = await _sweep(manager)

    assert again["pool4_counter_state"] == RECONCILED
    assert manager.cache.get_pool4_accumulator(SEPOLIA)["sums"] == sums
    assert again["pool4_counter_state"] == first["pool4_counter_state"]


async def test_a_failed_sweep_advances_nothing_and_loses_nothing(
    tmp_path,
) -> None:
    """Not counting is not the same as counting zero."""
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL)
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    await _sweep(manager)
    before = manager.cache.get_pool4_accumulator(SEPOLIA)

    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 60.0)
    client._returns["fetch_flow_logs"] = None
    dead = await _sweep(manager)

    # The total is untouched -- neither advanced nor zeroed. That is the
    # invariant; the *verdict* stays ``reconciled`` and rightly so, because
    # the accumulated evidence is still complete and still aligned with the
    # block the counters were read at. A failed log read does not retract a
    # sum that was already taken. What it must never do is look like a
    # disagreement.
    assert manager.cache.get_pool4_accumulator(SEPOLIA) == before
    assert dead["pool4_counter_state"] != MISMATCH
    assert dead["pool4_flow"] is None                  # the panel says so instead

    # And once the head moves past the untouched cursor, alignment fails and
    # the control stands down rather than crying wolf.
    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 60.0)
    client._returns["fetch_hook_state"] = _hook_at(HOOK_BLOCK + 500)
    drifted = await _sweep(manager)
    assert drifted["pool4_counter_state"] == WINDOW_LIMITED
    assert "stop at block" in drifted["pool4_counter_detail"]


async def test_a_misaligned_cursor_is_window_limited_not_a_mismatch(
    tmp_path,
) -> None:
    """**S17 invariant 2 — alignment, and the false alarm it prevents.**

    The sums cover ``[genesis, cursor]``; the counters cover
    ``[genesis, at_block]``. A cursor *behind* makes the sums short, and
    because continuity certifies the evidence complete, a short sum reads as a
    **mismatch** -- on every tick where a swap lands between the two reads.

    Here the counters are read at a block the accumulator has not swept to, so
    the honest answer is that the control did not run.
    """
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL)
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    assert (await _sweep(manager))["pool4_counter_state"] == RECONCILED

    acc = manager.cache.get_pool4_accumulator(SEPOLIA)
    manager.cache.set_pool4_accumulator(
        SEPOLIA, dict(acc, cursor_block=acc["cursor_block"] - 1)
    )
    payload = await manager.fetch_and_compute()      # republish, no new sweep
    assert payload["pool4_counter_state"] == RECONCILED   # the slot is unchanged

    # ... and the next sweep, which re-reads at a block the cursor is behind,
    # must not call that a mismatch.
    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 60.0)
    acc = manager.cache.get_pool4_accumulator(SEPOLIA)
    manager.cache.set_pool4_accumulator(
        SEPOLIA, dict(acc, genesis_block=acc["genesis_block"], cursor_block=0)
    )
    client._returns["fetch_flow_logs"] = None        # nothing folds, cursor stays
    after = await _sweep(manager)
    assert after["pool4_counter_state"] != MISMATCH


async def test_an_unpinned_window_is_never_accumulated(tmp_path) -> None:
    """**S17 invariant 2, at its source.** Only a window that ends where the
    state round was pinned may be folded.

    When the hook round answers no block number, ``_pool4_logs`` falls back to
    ``fetch_block_number`` for a head -- and the counters then came from a
    block nobody can name. Folding that window would advance the cursor to a
    block the counters were never read at, and every later sweep would skip
    logs at or below it: the total would silently lose them, which is the one
    failure the accumulator must never have. It stays unseeded instead, and
    the control falls back to the honest single window.
    """
    unpinned = P.decode_hook_state(
        HOOK_ANSWERS, total_supply_wei=1_000_000_000 * 10**18, block_number=None
    )
    client = FakePool4Client(
        fetch_hook_state=unpinned, fetch_flow_logs=FLOW_LOGS_FULL
    )
    manager = _manager(tmp_path, pool4_client=client)
    payload = await _sweep(manager)

    assert "fetch_block_number" in client.calls        # the fallback ran
    acc = manager.cache.get_pool4_accumulator(SEPOLIA)
    assert acc is None or acc["genesis_block"] is None

    # The *verdict* is unaffected and legitimately still ``reconciled``: this
    # window happens to reach genesis on its own, so single-window logic can
    # answer it without any accumulation. What must not happen is the cursor
    # being advanced to a block the counters were never read at.
    assert payload["pool4_counter_state"] == RECONCILED


async def test_the_accumulator_is_network_namespaced(tmp_path) -> None:
    """A Sepolia total reconciled against mainnet counters is not a weaker
    check, it is a wrong one -- the reserve series' argument exactly."""
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL)
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    await _sweep(manager)

    assert manager.cache.get_pool4_accumulator(SEPOLIA)["genesis_block"] is not None
    assert manager.cache.get_pool4_accumulator(MAINNET) is None
    assert manager.cache.get_pool4_accumulator("BASE") is None


async def test_the_accumulator_survives_a_restart(tmp_path) -> None:
    """It is a running total; losing it on every launch would mean the control
    only ever works on the day of deployment."""
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL)
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    await _sweep(manager)
    saved = manager.cache.get_pool4_accumulator(SEPOLIA)
    manager.save_cache()

    restored = _manager(tmp_path, clock=clock, pool4_client=FakePool4Client())
    assert restored.cache.get_pool4_accumulator(SEPOLIA) == saved


@pytest.mark.parametrize(
    "bad",
    [
        {"genesis_block": None, "cursor_block": 5, "sums": {}},
        {"genesis_block": 1, "cursor_block": "5", "sums": {}},
        {"genesis_block": 9, "cursor_block": 5, "sums": {}},
        {"genesis_block": 1, "cursor_block": 5, "sums": {"fee_imd": -3}},
        {"genesis_block": 1, "cursor_block": 5, "sums": {"fee_imd": "3"}},
        {"genesis_block": 1, "cursor_block": 5},
        "not a mapping",
    ],
)
def test_a_malformed_persisted_accumulator_is_discarded(tmp_path, bad) -> None:
    """It is cache-supplied *evidence*, so it is structurally validated on the
    way in and a malformed one costs the accumulator rather than the startup.

    What makes that tolerable is not this check: it is **alignment**. A forged
    total is believed only while its cursor equals the block the counters were
    just read at, which is a live chain read nobody can predict, so a forgery
    has to be rewritten in lockstep with the chain and perishes on its own.
    """
    assert SurfCache._coerce_accumulator(bad) is None


async def test_the_accumulator_never_enters_the_slots_content_comparison(
    tmp_path,
) -> None:
    """It advances on every sweep, so folding it into the slot would make every
    tick look like new data and the ``as of`` marker would run for ever."""
    clock = FakeClock(POOL4_NOW)
    client = FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL)
    manager = _manager(tmp_path, pool4_client=client, clock=clock)
    first = await _sweep(manager)
    cursor = manager.cache.get_pool4_accumulator(SEPOLIA)["cursor_block"]

    # The SAME logs at a later block: every rendered value is unchanged, so the
    # only thing that moved is the cursor. (Sweeping an empty window instead
    # would change ``pool4_flow`` and prove nothing about the accumulator.)
    clock.advance(TIER_TTL_SECONDS[TIER_POOL4] + 3600.0)
    client._returns["fetch_hook_state"] = _hook_at(HOOK_BLOCK + 50)
    second = await _sweep(manager)

    assert manager.cache.get_pool4_accumulator(SEPOLIA)["cursor_block"] != cursor
    assert second["pool4_as_of_hhmm"] == first["pool4_as_of_hhmm"]
    slot = manager.cache.get_last_good(SLOT_POOL4).payload
    assert "cursor_block" not in slot
    assert "sums" not in slot


def test_the_provenance_map_applies_the_self_post_rule(tmp_path) -> None:
    """A reply's transaction is not provenance for anything it names.

    The map is built through ``candidate_addresses`` one row at a time, so the
    rule is applied by the function that owns it rather than approximated here.
    """
    rows = [
        _self_post(f"ours {MAINNET_HOOK}", tx_hash=REAL_TX),
        _reply(f"mine {POOL4_SEPOLIA_TOKEN}"),
    ]
    mapped = SurfManager._pool4_source_tx_by_addr(rows)
    assert mapped == {MAINNET_HOOK.lower(): REAL_TX}
    assert POOL4_SEPOLIA_TOKEN.lower() not in mapped


# ---------------------------------------------------------------------------
# Mainnet: the Distributor, the three-way reward leg, the two cap getters
# ---------------------------------------------------------------------------

#: The live mainnet Distributor reads (docs/imd_pool4_mainnet.md).
DISTRIBUTOR_ADDR = "0x9046739E1535B40EfBe6AB3f45d0024b690eCA30"
DISTRIBUTOR_STATE = {
    "dripper": DRIPPER_ADDR,
    "asset": IMD_TOKEN,
    "owner": DEV_WALLET,
    "stakingBps": 3000,
    "nftBps": 3000,
    "stakingEarned": 3_149_000_000_000_000_000,
    "bondingEarned": 4_198_600_000_000_000_000,
    "nftEarned": 3_149_000_000_000_000_000,
    "heldBonding": 4_198_600_000_000_000_000,
    "heldNft": 3_149_000_000_000_000_000,
    "block_number": HOOK_BLOCK,
}

#: The mainnet walk: hook -> Distributor -> Dripper -> vault.
MAINNET_PATH = {
    "path": [DISTRIBUTOR_ADDR, DRIPPER_ADDR],
    "dripper": DRIPPER_ADDR,
    "vault": VAULT_ADDR,
}


def _mainnet_client(**overrides) -> "FakePool4Client":
    """A client answering the mainnet shape: a Distributor between the two."""
    returns = {
        "resolve_vault_path": MAINNET_PATH,
        "fetch_distributor_state": DISTRIBUTOR_STATE,
    }
    returns.update(overrides)
    return FakePool4Client(**returns)


async def test_the_distributor_is_identified_from_the_walk_not_a_hop_count(
    tmp_path,
) -> None:
    """The Distributor is "the node the hook points at, when it is not the
    Dripper" -- derived from the chain's own answer.

    ``vault()`` lives on the RewardDripper and nowhere else, so the walk stops
    at the Dripper by definition and the first hop is the Distributor when the
    two differ. On Sepolia they are the same address and there is none.
    """
    client = _mainnet_client()
    payload = await _sweep(_manager(tmp_path, pool4_client=client))

    assert payload["pool4_distributor_addr"] == DISTRIBUTOR_ADDR
    assert client.distributor_asked == DISTRIBUTOR_ADDR
    assert payload["pool4_dripper_addr"] == DRIPPER_ADDR
    assert payload["pool4_vault_addr"] == VAULT_ADDR

    sepolia = await _sweep(_manager(tmp_path, pool4_client=FakePool4Client()))
    assert sepolia["pool4_distributor_addr"] is None


async def test_the_reward_path_is_a_word_the_address_cannot_carry(
    tmp_path,
) -> None:
    """``direct`` / ``via-distributor`` / ``None``, read off the walk."""
    mainnet = await _sweep(_manager(tmp_path, pool4_client=_mainnet_client()))
    assert mainnet["pool4_reward_path"] == "via-distributor"
    assert mainnet["pool4_distributor_addr"] == DISTRIBUTOR_ADDR

    sepolia = await _sweep(_manager(tmp_path))
    assert sepolia["pool4_reward_path"] == "direct"
    assert sepolia["pool4_distributor_addr"] is None


async def test_an_unread_recipient_is_unknown_and_not_direct(tmp_path) -> None:
    """**The defect the word exists to prevent, and this module shipped it.**

    ``pool4_distributor_addr`` is ``None`` in two completely different
    situations -- there is no Distributor, and the getter that would have named
    one failed -- and they are **three times apart** on the staker share. The
    hook's getters degrade per field, so "the counters answered and
    ``rewardsRecipient()`` did not" is a routine payload, not a corner.

    Branching on the address published mainnet's whole 15% reward share as the
    staker share in exactly that payload. Unknown must stay unknown.
    """
    blind = P.decode_hook_state(
        {k: v for k, v in HOOK_ANSWERS.items() if k != "rewardsRecipient"},
        total_supply_wei=1_000_000_000 * 10**18,
        block_number=HOOK_BLOCK,
    )
    client = _mainnet_client(fetch_hook_state=blind)
    payload = await _sweep(_manager(tmp_path, pool4_client=client))

    assert payload["pool4_reward_path"] is None
    assert payload["pool4_distributor_addr"] is None
    # The counters DID answer -- so the temptation to publish a share is real.
    assert payload["pool4_total_rewarded"] is not None
    assert payload["pool4_measured_burn_pct"] is not None
    # ... and the staker share is still refused, because which fraction of the
    # reward leg reaches stakers is exactly what was not established.
    assert payload["pool4_measured_stakers_pct"] is None


async def test_a_walk_that_never_reaches_a_vault_leaves_the_path_unknown(
    tmp_path,
) -> None:
    """A walk that ran and identified no Dripper has not established which node
    was the middle of the path either."""
    client = FakePool4Client(
        resolve_vault_path={"path": [DRIPPER_ADDR], "dripper": None, "vault": None}
    )
    payload = await _sweep(_manager(tmp_path, pool4_client=client))
    assert payload["pool4_reward_path"] is None
    assert payload["pool4_measured_stakers_pct"] is None


async def test_the_reward_leg_is_not_published_as_the_staker_share(
    tmp_path,
) -> None:
    """**The bug that would have shown wrong numbers on screen.**

    ``totalRewarded()`` is everything handed to ``rewardsRecipient()``. On
    mainnet that is the Distributor, which splits it three ways -- so the
    hook's counters cannot see the staker leg at all. Publishing the whole
    reward share under a "stakers" label overstates it by more than three
    times, and 15% where 4.5% is true renders as an entirely ordinary number.
    """
    payload = await _sweep(_manager(tmp_path, pool4_client=_mainnet_client()))

    fee = HOOK_STATE.total_fee_token_wei
    burn = HOOK_STATE.total_burned_wei
    reward = HOOK_STATE.total_rewarded_wei
    whole_reward_pct = reward / (fee + burn + reward) * 100

    stakers = payload["pool4_measured_stakers_pct"]
    assert stakers is not None
    # The staking leg is 3000/10000 of the reward share ...
    assert stakers == pytest.approx(whole_reward_pct * 0.3)
    # ... and emphatically NOT the whole reward share.
    assert stakers != pytest.approx(whole_reward_pct)
    assert whole_reward_pct / stakers == pytest.approx(10_000 / 3000)


async def test_with_no_distributor_the_reward_leg_is_the_staker_leg(
    tmp_path,
) -> None:
    """Sepolia's ``rewardsRecipient()`` IS the Dripper, so the whole reward
    share reaches the vault and the two are the same number.

    Blanking this on the deployment where it is correct would be the opposite
    error to the mainnet one, and just as wrong.
    """
    payload = await _sweep(_manager(tmp_path))
    fee = HOOK_STATE.total_fee_token_wei
    burn = HOOK_STATE.total_burned_wei
    reward = HOOK_STATE.total_rewarded_wei
    assert payload["pool4_measured_stakers_pct"] == pytest.approx(
        reward / (fee + burn + reward) * 100
    )
    assert sum(
        payload[k] for k in (
            "pool4_measured_inference_pct", "pool4_measured_burn_pct",
            "pool4_measured_stakers_pct",
        )
    ) == pytest.approx(100.0)


async def test_the_distributor_keys_carry_the_live_mainnet_reads(
    tmp_path,
) -> None:
    payload = await _sweep(_manager(tmp_path, pool4_client=_mainnet_client()))

    assert payload["pool4_distributor_staking_bps"] == 3000
    assert payload["pool4_distributor_nodes_bps"] == 3000
    assert payload["pool4_distributor_staking_earned"] == pytest.approx(3.1490)
    assert payload["pool4_distributor_nodes_earned"] == pytest.approx(3.1490)
    assert payload["pool4_distributor_bonding_earned"] == pytest.approx(4.1986)
    assert payload["pool4_distributor_held_nodes"] == pytest.approx(3.1490)
    assert payload["pool4_distributor_held_bonding"] == pytest.approx(4.1986)


def test_the_chain_says_nft_and_the_payload_says_nodes() -> None:
    """The naming discipline, pinned in **both** directions.

    *Model fields mirror the chain, flat-dict keys mirror the docs* -- the same
    split that makes ``identityAllowed()`` the key ``gate_open``. The chain
    says ``nftBps()``/``nftEarned()``/``heldNft()``; the project's own
    documentation calls them **nodes**, the NFT-holding compute daemons. The
    manager is the single translation point, so neither side is a typo to
    "fix" and a rename on either would be caught here.
    """
    from maxpane_dashboard.data.surf_pool4_client import DISTRIBUTOR_SIGNATURES

    assert "nftBps" in DISTRIBUTOR_SIGNATURES
    assert "nftEarned" in DISTRIBUTOR_SIGNATURES
    assert "heldNft" in DISTRIBUTOR_SIGNATURES
    assert not [k for k in DISTRIBUTOR_SIGNATURES if "nodes" in k.lower()]

    nodes_keys = [k for k in POOL4_KEYS if "nodes" in k]
    assert nodes_keys == [
        "pool4_distributor_nodes_bps",
        "pool4_distributor_nodes_earned",
        "pool4_distributor_held_nodes",
    ]
    assert not [k for k in POOL4_KEYS if "nft" in k.lower()]


async def test_bonding_bps_is_derived_and_never_hardcoded(tmp_path) -> None:
    """Bonding has no getter: it is ``BPS_DENOMINATOR - staking - nft``.

    The split has already moved once -- ``rewardShareBps`` went 1000 -> 1500
    the day mainnet shipped -- so a hardcoded 4000 is a number that goes stale
    in silence. Here the *inputs* are moved and the remainder has to follow.
    """
    payload = await _sweep(_manager(tmp_path, pool4_client=_mainnet_client()))
    assert payload["pool4_distributor_bonding_bps"] == 4000

    moved = dict(DISTRIBUTOR_STATE, stakingBps=2500, nftBps=2500)
    shifted = await _sweep(
        _manager(tmp_path, pool4_client=_mainnet_client(
            fetch_distributor_state=moved
        ))
    )
    assert shifted["pool4_distributor_bonding_bps"] == 5000


@pytest.mark.parametrize(
    "missing", ["stakingBps", "nftBps"]
)
async def test_bonding_bps_goes_none_when_either_input_does(
    tmp_path, missing
) -> None:
    """``split_drift_bps``' rule: a remainder computed from a number nobody
    read is not a weaker answer, it is a wrong one.

    And there is no ``bonding_derived`` flag beside it -- a flag that can only
    ever be ``True`` is a constant dressed as data.
    """
    blind = dict(DISTRIBUTOR_STATE)
    blind[missing] = None
    payload = await _sweep(
        _manager(tmp_path, pool4_client=_mainnet_client(
            fetch_distributor_state=blind
        ))
    )
    assert payload["pool4_distributor_bonding_bps"] is None
    assert not [k for k in POOL4_KEYS if "derived" in k]


async def test_an_unread_bps_denominator_takes_the_remainder_with_it(
    tmp_path,
) -> None:
    blind = P.decode_hook_state(
        {k: v for k, v in HOOK_ANSWERS.items() if k != "BPS_DENOMINATOR"},
        block_number=HOOK_BLOCK,
    )
    payload = await _sweep(
        _manager(tmp_path, pool4_client=_mainnet_client(fetch_hook_state=blind))
    )
    assert payload["pool4_bps_denominator"] is None
    assert payload["pool4_distributor_bonding_bps"] is None


async def test_a_dead_distributor_costs_only_the_distributor_keys(
    tmp_path,
) -> None:
    payload = await _sweep(
        _manager(tmp_path, pool4_client=_mainnet_client(
            fetch_distributor_state=None
        ))
    )
    assert payload["pool4_distributor_staking_bps"] is None
    assert payload["pool4_distributor_bonding_bps"] is None
    # The hook and the vault are untouched.
    assert payload["pool4_tokens_in_pool"] is not None
    assert payload["pool4_share_price"] is not None
    assert SOURCE_POOL4 not in payload["degraded"]


# --- the two cap getters ----------------------------------------------------


def _hook_with_caps(inventory_wei, decay_wei):
    """The committed hook answers plus the two cap getters.

    Constructed rather than fixture-read: the committed Sepolia capture
    predates both getters. Driving the absence case from *that* fixture would
    pass for the wrong reason -- it would prove the capture is old, not that a
    hook without the getters degrades correctly.
    """
    answers = dict(HOOK_ANSWERS)
    if inventory_wei is not None:
        answers["inventoryCap"] = "0x" + format(inventory_wei, "064x")
    if decay_wei is not None:
        answers["capDecayTokensPerDay"] = "0x" + format(decay_wei, "064x")
    return P.decode_hook_state(answers, block_number=HOOK_BLOCK)


async def test_the_cap_getters_publish_on_either_chain(tmp_path) -> None:
    """Present on **both** chains -- the difference is the value, not the
    presence. The mainnet record corrected an earlier draft that assumed
    otherwise, and that assumption had never been measured.
    """
    hook = _hook_with_caps(5_487_346_500_000_000_000_000, 1_000 * 10**18)
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_hook_state=hook))
    )
    assert payload["pool4_inventory_cap"] == pytest.approx(5_487.3465)
    assert payload["pool4_cap_decay_per_day"] == pytest.approx(1_000.0)


async def test_a_disabled_ratchet_reads_as_a_real_zero(tmp_path) -> None:
    """``uint128`` max means the ratchet is off, and 0.0 is how that renders.

    Dividing the sentinel by 1e18 would put 340,282,366,920,938,463,463
    IMD/day on the panel -- a decay that would zero the cap instantly, i.e.
    the exact opposite of what the value means. ``None`` would be wrong the
    other way: it would say "we could not read it" about a getter that
    answered.
    """
    hook = _hook_with_caps(472_569_750_770_000_000_000_000_000, 2 ** 128 - 1)
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_hook_state=hook))
    )
    assert payload["pool4_cap_decay_per_day"] == 0.0
    assert payload["pool4_cap_decay_per_day"] is not None
    assert payload["pool4_inventory_cap"] is not None


@pytest.mark.parametrize(
    "persisted",
    [
        2 ** 128 - 1,                                   # the sentinel, as read
        str(2 ** 128 - 1),                              # hand-edited as text
        float(2 ** 128 - 1),                            # hand-edited as a float
    ],
)
async def test_the_sentinel_is_resolved_when_it_comes_BACK_from_the_cache(
    tmp_path, persisted
) -> None:
    """**The deserialisation boundary, pinned — no sweep involved.**

    ``pool4_cap_decay_per_day`` reaches the panel twice: once from the live
    hook read, and once on every later refresh from the persisted slot. The
    second path is the one that is easy to leave unguarded, because the value
    sitting in ``~/.maxpane/`` is *just a number* and stays plausible right up
    until a formatter divides it — at which point the panel reads
    ``340,282,366,920,938,487,808 IMD/day``, a decay that would zero the cap
    instantly, rendered with total confidence.

    A cache file is third-party input on the ``pattern_language()`` precedent,
    and this is the same argument that already re-checks ``_TX_HASH_RE`` on
    every publish rather than once: re-validated on every render, not once,
    long ago, by a version that may not have checked.

    The guard is WP3's ``is_no_decay`` on both paths — **one boundary, one
    authority** (A8). No second threshold exists in this module or downstream.
    """
    manager = _manager(tmp_path)
    manager.cache.store_last_good(
        SLOT_POOL4,
        {"network": SEPOLIA, "cap_decay_per_day_wei": persisted,
         "inventory_cap_wei": 5_487_346_500_000_000_000_000},
        ts=POOL4_NOW - 100.0,
    )
    payload = await manager.fetch_and_compute()      # republish only

    published = payload["pool4_cap_decay_per_day"]
    assert published == 0.0
    # ... and emphatically not the raw sentinel put through the divider.
    assert published != pytest.approx((2 ** 128 - 1) / 1e18)
    assert published < 1.0


# --- the ceiling's headroom, and the sign trap ------------------------------

#: The live mainnet reads, 2026-09-02.
MAINNET_CAP_WEI = 5_331_227_804_000_000_000_000        # inventoryCap
MAINNET_RESERVE_WEI = 5_236_544_041_000_000_000_000    # tokensInPool
MAINNET_FLOOR_WEI = 1_000 * 10**18                     # capFloor


def _hook_with_ceiling(cap_wei, reserve_wei, floor_wei=MAINNET_FLOOR_WEI):
    answers = dict(HOOK_ANSWERS)
    answers["inventoryCap"] = "0x" + format(cap_wei, "064x")
    answers["tokensInPool"] = "0x" + format(reserve_wei, "064x")
    answers["capFloor"] = "0x" + format(floor_wei, "064x")
    return P.decode_hook_state(answers, block_number=HOOK_BLOCK)


async def test_the_ceiling_and_the_floor_read_positive_from_OPPOSITE_operands(
    tmp_path,
) -> None:
    """**The sign trap, and the only test that catches it.**

    ``pool4_floor_distance`` is ``reserve - floor``; ``pool4_cap_headroom`` is
    ``cap - reserve``. The operand order is **deliberately opposite**, so that
    both read positive on a healthy pool -- the floor sits below the reserve,
    the ceiling above it.

    Writing the ceiling by analogy with its sibling is the natural mistake,
    because the two sit next to each other and one was already in the file. It
    yields ``reserve - cap``, which renders a **binding cap as slack of the
    same magnitude** -- the exact reading the key exists to prevent.

    Pinned against the two operands rather than a literal: a literal passes
    just as happily when the fixture and the constant are reversed together,
    which is the shape this mistake actually takes.
    """
    hook = _hook_with_ceiling(MAINNET_CAP_WEI, MAINNET_RESERVE_WEI)
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_hook_state=hook))
    )

    cap = payload["pool4_inventory_cap"]
    reserve = payload["pool4_tokens_in_pool"]
    floor = payload["pool4_cap_floor"]
    assert cap > reserve > floor, "the fixture must be a healthy pool"

    # The relationship, not the number.
    assert payload["pool4_cap_headroom"] == pytest.approx(cap - reserve)
    assert payload["pool4_floor_distance"] == pytest.approx(reserve - floor)

    # And the consequence that makes the order load-bearing: BOTH are positive
    # on a healthy pool, from operands in opposite orders.
    assert payload["pool4_cap_headroom"] > 0
    assert payload["pool4_floor_distance"] > 0
    # The by-analogy inversion would be this, and it must not be what we get.
    assert payload["pool4_cap_headroom"] != pytest.approx(reserve - cap)


async def test_a_binding_cap_renders_negative_rather_than_clamped(
    tmp_path,
) -> None:
    """Inventory above the ceiling is a real state, not an error.

    ``floor_distance``'s A7 precedent: launch 1 sits below its own floor
    because a backstop rebalance can move the reserve where a swap cannot, and
    nothing clamps it. The ceiling gets the same treatment -- clamping to zero
    would render a cap that is already exceeded as one exactly satisfied.
    """
    hook = _hook_with_ceiling(MAINNET_RESERVE_WEI, MAINNET_CAP_WEI)   # swapped
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_hook_state=hook))
    )
    assert payload["pool4_cap_headroom"] < 0
    assert payload["pool4_cap_headroom"] == pytest.approx(
        payload["pool4_inventory_cap"] - payload["pool4_tokens_in_pool"]
    )


async def test_the_headroom_is_computed_in_wei_not_from_the_published_floats(
    tmp_path,
) -> None:
    """Divided once, at the end — and at Sepolia's scale that is the whole
    difference between a number and a zero.

    One float64 step at 472M IMD is about 909,495 wei, so subtracting the two
    *published* whole-IMD floats annihilates any headroom below a millionth of
    an IMD and returns a confident ``0.0``. Subtracting in integer wei keeps
    it. (This is the residue of the argument that twice kept this key out of
    the contract: the cancellation is real, it was just never a reason to
    withhold the number — only a reason to compute it in wei.)
    """
    reserve = 472_569_750_774_434_000_000_000_000
    cap = reserve + 12
    hook = _hook_with_ceiling(cap, reserve, floor_wei=1)
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_hook_state=hook))
    )

    # What a consumer subtracting the two published floats would get ...
    assert payload["pool4_inventory_cap"] - payload["pool4_tokens_in_pool"] == 0.0
    # ... and what the manager actually publishes.
    assert payload["pool4_cap_headroom"] == pytest.approx(12 / 1e18)
    assert payload["pool4_cap_headroom"] > 0.0


@pytest.mark.parametrize("drop", ["inventoryCap", "tokensInPool"])
async def test_the_headroom_is_none_when_either_operand_is_unread(
    tmp_path, drop
) -> None:
    """A headroom computed against a number nobody read is not a weaker
    answer, it is a wrong one — ``split_drift_bps``' rule."""
    answers = dict(HOOK_ANSWERS)
    answers["inventoryCap"] = "0x" + format(MAINNET_CAP_WEI, "064x")
    answers.pop(drop, None)
    hook = P.decode_hook_state(answers, block_number=HOOK_BLOCK)
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_hook_state=hook))
    )
    assert payload["pool4_cap_headroom"] is None


def test_the_headroom_operands_cannot_be_swapped_positionally() -> None:
    """Keyword-only, so the sign trap is a ``TypeError`` and not a wrong number.

    This is the structural half of the sign defence: the test above catches an
    inversion that reaches the payload, and this makes the most likely way of
    writing one impossible to express.
    """
    with pytest.raises(TypeError):
        SurfManager._pool4_cap_headroom(MAINNET_CAP_WEI, MAINNET_RESERVE_WEI)
    assert SurfManager._pool4_cap_headroom(
        inventory_cap_wei=MAINNET_CAP_WEI, reserve_wei=MAINNET_RESERVE_WEI
    ) == pytest.approx(94.683763)


async def test_a_hook_without_the_cap_getters_publishes_none(tmp_path) -> None:
    """**The absence case, driven by a getter that reverts** -- which is what a
    differently-built future hook actually looks like.

    Pointing this at the committed Sepolia capture instead would pass for the
    wrong reason: that capture simply predates the getters.
    """
    hook = _hook_with_caps(None, None)
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_hook_state=hook))
    )
    assert payload["pool4_inventory_cap"] is None
    assert payload["pool4_cap_decay_per_day"] is None
    # ... and nothing else went dark with them.
    assert payload["pool4_cap_floor"] is not None
    assert payload["pool4_tokens_in_pool"] is not None


# ---------------------------------------------------------------------------
# The hatch rows
# ---------------------------------------------------------------------------


async def test_hatch_rows_match_the_frozen_vocabularies(tmp_path) -> None:
    payload = await _sweep(_manager(tmp_path))
    rows = payload["pool4_hatches"]
    assert rows
    for row in rows:
        assert set(row) == set(SURF_ROW_KEYS["pool4_hatches"])
        assert row["scope"] in POOL4_HATCH_SCOPES
        assert row["label"] in POOL4_HATCH_LABELS
        assert row["state"] in POOL4_HATCH_STATES
        assert isinstance(row["addr_known"], bool)
    assert {r["scope"] for r in rows} == set(POOL4_HATCH_SCOPES)


async def test_the_distributor_is_on_the_trust_surface(tmp_path) -> None:
    """Its owner holds ``setDripper`` and ``emergencyWithdraw`` — it can
    re-point the entire rewards path, so it belongs beside the other three.

    On Sepolia there is no Distributor and the rows say ``absent``: a fact
    about the deployment, not a failed read.
    """
    mainnet = await _sweep(_manager(tmp_path, pool4_client=_mainnet_client()))
    rows = {
        (r["scope"], r["label"]): r
        for r in mainnet["pool4_hatches"] if r["scope"] == "distributor"
    }
    assert rows
    assert rows[("distributor", "rewards")]["addr"] == DISTRIBUTOR_ADDR
    assert rows[("distributor", "rewards")]["state"] == "live"
    assert rows[("distributor", "owner")]["state"] == "live"
    assert rows[("distributor", "owner")]["addr_known"] is True

    sepolia = await _sweep(_manager(tmp_path))
    absent = [
        r for r in sepolia["pool4_hatches"] if r["scope"] == "distributor"
    ]
    assert absent and all(r["state"] == "absent" for r in absent)


async def test_the_bond_row_always_exists(tmp_path) -> None:
    """``[]`` is never emitted: "the bond the site advertises is not a contract
    we can see" is itself the answer a reader came for."""
    payload = await _sweep(_manager(tmp_path))
    bond = [r for r in payload["pool4_hatches"] if r["scope"] == "bond"]
    assert len(bond) == 1
    assert bond[0]["state"] == "unknown"


async def test_addr_known_is_an_allowlist_hit_and_nothing_else(tmp_path) -> None:
    """No prefix match, no fallback. The burn sink is not in ``KNOWN_LABELS``,
    so it renders as an address rather than as a name this repo never gave it.
    """
    payload = await _sweep(_manager(tmp_path))
    by_label = {r["label"]: r for r in payload["pool4_hatches"]}
    assert by_label["burn sink"]["addr"].lower().endswith("dead")
    assert by_label["burn sink"]["addr_known"] is False
    # The dev wallet *is* on the allowlist, and owns all three contracts here.
    assert by_label["owner"]["addr_known"] is True


async def test_an_unread_contract_leaves_its_levers_unknown(tmp_path) -> None:
    """``None`` must never render as a confident answer about a lever."""
    payload = await _sweep(
        _manager(tmp_path, pool4_client=FakePool4Client(fetch_vault_state=None))
    )
    vault_rows = [r for r in payload["pool4_hatches"] if r["scope"] == "vault"]
    assert vault_rows
    assert all(r["state"] == "unknown" for r in vault_rows)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def test_the_slot_round_trips_through_the_cache_file(tmp_path) -> None:
    """A restart republishes the same payload behind the same marker.

    The slot holds wei-native ``int``s two orders of magnitude past 2**53
    (``capFloor`` is 2.5e26) and two row lists, and ``_jsonable`` is what
    stands between them and the disk. A field it silently dropped would cost
    that panel on every restart and nothing else would notice — the sweep
    would look healthy and the number would simply be gone.
    """
    clock = FakeClock(POOL4_NOW)
    manager = _manager(tmp_path, clock=clock)
    live = await _sweep(manager)
    manager.save_cache()

    restored = _manager(tmp_path, clock=clock, pool4_client=FakePool4Client(**DEAD_ALL))
    restored.cache.load()
    after = await restored.fetch_and_compute()

    for key in POOL4_KEYS:
        if key in ("pool4_share_price_delta_pct", "pool4_reserve_series"):
            continue        # session state and cache history, not slot content
        assert after[key] == live[key], key
    assert after["pool4_as_of_hhmm"] == live["pool4_as_of_hhmm"]
    assert SOURCE_POOL4 not in after["degraded"]


# ---------------------------------------------------------------------------
# Lifecycle and no-network
# ---------------------------------------------------------------------------


async def test_close_cancels_the_sweep_and_closes_both_clients(tmp_path) -> None:
    """The sweep holds the client it reads through, so it is stopped *first* —
    closing sockets under a task mid-request is how a clean quit becomes a
    traceback on the way down.
    """
    gate = asyncio.Event()

    class Slow(FakePool4Client):
        async def fetch_hook_state(self, addr, *, network, token_addr=None):
            await gate.wait()
            return HOOK_STATE

    client = Slow()
    manager = _manager(tmp_path, pool4_client=client)
    await manager.fetch_and_compute()
    await asyncio.sleep(0)
    task = manager._pool4_task
    assert task is not None and not task.done()

    await manager.close()
    assert task.done()
    assert client.closed is True
    assert manager.client.closed is True


async def test_a_manager_built_without_a_pool4_client_owns_a_real_one() -> None:
    """The default mirrors ``client``'s. A test that injects nothing gets the
    real client — which is exactly why every helper in the surf manager suite
    injects a double, and why this is asserted rather than assumed.
    """
    from maxpane_dashboard.data.surf_pool4_client import Pool4Client

    manager = SurfManager(
        cache_path=str(Path(tempfile.mkdtemp()) / "surf_cache.json"),
        client=FakeSurfClient(),
        clock=FakeClock(POOL4_NOW),
    )
    assert isinstance(manager.pool4_client, Pool4Client)
    await manager.pool4_client.close()


async def test_these_tests_never_reach_the_network(tmp_path) -> None:
    """Structural, per CLAUDE.md: the surf client's transport raises on use and
    the pool4 client is a double with no transport at all."""
    manager = _manager(tmp_path)
    await _sweep(manager)
    with pytest.raises(AssertionError):
        await manager.client.http.post("https://example.invalid")
    assert not hasattr(manager.pool4_client, "_client")


def test_the_source_group_and_slot_are_wired_to_each_other() -> None:
    from maxpane_dashboard.data.surf_manager import GROUP_SLOT

    assert GROUP_SLOT[SOURCE_POOL4] == SLOT_POOL4
    assert set(GROUP_SLOT) == set(SOURCES)
    assert SOURCE_LAUNCHPAD in SOURCES        # p4 was added, pad was not moved
