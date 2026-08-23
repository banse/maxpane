"""WP4 — orchestration, tiering and degradation tests for :class:`SurfManager`.

Zero network: the client is a double whose transport raises on use, the clock is
a fake, and persistence points at ``tmp_path``. Nothing here sleeps.

The centre of gravity is degradation, because that is the deliverable: the
manager must return exactly ``SURF_KEYS`` under every combination of source
failures, must never let an exception escape, and — the correctness rule the
whole PRD hangs on — must never let a failed read move a baseline.
"""

from __future__ import annotations

import asyncio
import math
import tempfile
from pathlib import Path
from typing import Any

import pytest

from maxpane_dashboard.analytics import surf_signals
from maxpane_dashboard.data.surf_cache import (
    SERIES_IMD_PRICE_USD,
    SERIES_IMD_SUPPLY,
    SLOT_CHANNEL,
    SLOT_LAUNCHPAD,
    SLOT_LOGS,
    SLOT_NFT,
    TIER_LAUNCHPAD,
    SurfCache,
)
from maxpane_dashboard.data.surf_manager import (
    SOURCES,
    SOURCE_ACTIVITY,
    SOURCE_CHAIN,
    SOURCE_CHANNEL,
    SOURCE_LAUNCHPAD,
    SOURCE_LOGS,
    SOURCE_MARKET,
    SOURCE_NFT,
    SurfManager,
)
from maxpane_dashboard.data.surf_models import (
    SURF_KEYS,
    SURF_ROW_KEYS,
    ChainState,
    ChannelTx,
    DevTx,
    LaunchpadCoin,
    LaunchpadState,
    LogWindow,
    MarketSnapshot,
    NftStats,
    NonceSet,
    PoolV4State,
)
from maxpane_dashboard.data.surf_addresses import (
    ANNOUNCE,
    BURN_EXECUTOR_V1,
    DEV_WALLET,
    FWA_SPLITTER,
    IDENTITY_REGISTRY,
    IDMD_NFT,
    IMD_TOKEN,
    KNOWN_LABELS,
    NFPM,
    OPS_WALLET,
    POOL_MANAGER_V4,
    SEAPORT,
    TOPIC_IDENTITY_HASH_UPDATED,
    TOPIC_SEAPORT_ORDER_FULFILLED,
    TOPIC_TRANSFER,
    TOPIC_V4_INITIALIZE,
    WETH,
)

# --- live values, captured 2026-08-08 (tests/fixtures/surf/captures/) -------
#
# The models are wei-native (WP0.4); the *_WEI constants are what a double
# hands the manager, and the token figures are what the manager must publish
# after dividing exactly once.

IMD_SUPPLY_WEI = 2_376_731_868_679_000_000_000_000   # imd_token.json total_supply
IMD_SUPPLY = 2_376_731.868679                        # ... / 1e18
LP_IMD_WEI = 388_421_000_000_000_000_000_000
LP_WETH_WEI = 142_706_700_000_000_000_000

# DexScreener's **whole-pool** reserves (`liquidity.base` / `liquidity.quote`).
# These two are *constructed*, not captured — they are the only numbers in this
# block that are, and the construction is the point. The pool holds every
# position while the hero tracks 1167726 alone, so the pool pair must be the
# larger one; it is set here to ~2.32x the position, i.e. the tracked position
# is ~43% of the pool.
#
# They have to be *visibly* different or the discrimination they exist for
# cannot be written down. `LP_IMD_WEI / 1e18` is 388420.99999999994 in binary
# floating point, so the previous doubles (`pool_imd = 388_421.0`,
# `pool_weth = 142.7067`) matched `pytest.approx` of the hero's own legs at the
# default `rel=1e-6` — `test_wei_is_divided_exactly_once` was asserting
# `x == approx(y)` and `x != approx(y)` about the same pair of numbers and could
# never go green. Keep any edit clearly apart from the two `LP_*_WEI / 1e18`
# values, and never derive one pair from the other.
#
# `POOL_LIQ_USD` is DexScreener's own `liquidity.usd` field, captured
# independently of these two; nothing in WP4 reads the reserves at all
# (`_market_payload` omits them on purpose), so no test cross-checks the three.
POOL_IMD = 902_763.4
POOL_WETH = 331.6772

IMD_PRICE_USD = 0.7074                 # dexscreener_imd.json priceUsd
FP_PRICE_USD = 0.7274                  # dexscreener_fp.json, deepest Base pair
PARITY_PCT = -2.7495188342040167
VOL_24H_USD = 244_178.0
POOL_LIQ_USD = 548_701.21
CHANGE_24H = 30.89
ETH_USD = 1917.74                      # announce_eth_info.json exchange_rate
NFT_HOLDERS = 667                      # identity_counters.json
ANNOUNCE_NONCE = 14                    # 13 self-posts + the register() call
DEV_NONCE = 2350
OPS_NONCE = 38                         # ops_eth_txs.json: sent nonces 1..37 → account nonce 38
LP_LIQUIDITY = 1_234_567_890_123_456_789
BLOCK = 25_707_780

#: Mirrors ``surf_client.LOG_WINDOW_BLOCKS`` (2400, ≈8 h at 12 s blocks) as a
#: literal rather than an import: this module drives a *double*, and importing
#: the real client here would make the manager suite depend on the transport
#: layer it exists to stand in for. Only the arithmetic matters — a
#: ``LogWindow`` double needs some plausible ``from_block``.
LOG_WINDOW = 2400

#: Task 6 fix round 1 (controller finding 1): the five reading keys
#: ``_readings()`` feeds for Task 7's not-yet-registered detectors (DECOY
#: POOL, BURN READY, HOT COIN). Not in ``surf_signals.READING_KEYS`` — that
#: tuple is Task 7's own file to grow — so the "exactly WP2's contract" test
#: below names them itself rather than compare against an import that
#: doesn't know about them yet.
LAUNCHPAD_READING_KEYS = frozenset(
    {
        "decoy_pool_count",
        "decoy_newest_fee_bps",
        "burn_ready",
        "burn_accrued",
        "launchpad_swaps_by_coin",
    }
)


def _word(value: int) -> str:
    return f"{value & (2**256 - 1):064x}"


def _addr_word(addr: str) -> str:
    return addr[2:].lower().rjust(64, "0")


def _mint_log(
    to_addr: str,
    amount_wei: int,
    *,
    ts: float,
    tx: str,
    block: int = BLOCK,
    log_index: int = 0,
    stamped: bool = True,
) -> dict:
    """A raw ``Transfer(0x0 -> dev wallet)`` log, exactly as WP1 passes it through.

    ``stamped=False`` models the endpoints that omit ``blockTimestamp`` — drpc
    does, tenderly does not, and both are in the logs pool. That is the sweep
    where every row in the group ends up carrying the same observation clock,
    so ``(block, log_index)`` is the only thing left that orders them.
    """
    log = {
        "address": "0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7".lower(),
        "topics": [TOPIC_TRANSFER, "0x" + "0" * 64, "0x" + _addr_word(to_addr)],
        "data": "0x" + _word(amount_wei),
        "blockNumber": hex(block),
        "blockTimestamp": hex(int(ts)),
        "logIndex": hex(log_index),
        "transactionHash": tx,
    }
    if not stamped:
        del log["blockTimestamp"]
    return log


def _v4_init_log(hooks: str, *, ts: float, tx: str) -> dict:
    """A raw v4 ``Initialize`` log: hooks is the third word of ``data``.

    ``Initialize(id, currency0, currency1, fee, tickSpacing, hooks, sqrtPriceX96, tick)``
    — three indexed args, five in the payload.
    """
    return {
        "address": POOL_MANAGER_V4.lower(),
        "topics": [
            TOPIC_V4_INITIALIZE,
            "0x" + "11" * 32,
            "0x" + _addr_word("0x" + "00" * 20),
            "0x" + _addr_word("0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7"),
        ],
        "data": (
            "0x" + _word(10_000) + _word(200) + _addr_word(hooks)
            + _word(0) + _word(0)
        ),
        "blockNumber": hex(BLOCK),
        "blockTimestamp": hex(int(ts)),
        "transactionHash": tx,
    }


def _identity_log(token_id: int, *, ts: float, tx: str) -> dict:
    """A raw ``IdentityHashUpdated(uint256 indexed id, string, bool)`` log.

    Verified off ``captures/identity_contract.json`` (`source_code_head`): the
    id is **topics[1]**, and the payload is a dynamic ``(string, bool)`` that
    nobody needs to decode. Two logs for one id are one identity written.
    """
    return {
        "address": IDENTITY_REGISTRY.lower(),
        "topics": [TOPIC_IDENTITY_HASH_UPDATED, "0x" + _word(token_id)],
        "data": "0x" + _word(64) + _word(1) + _word(0),
        "blockNumber": hex(BLOCK),
        "blockTimestamp": hex(int(ts)),
        "transactionHash": tx,
    }


def _seaport_log(
    token_id: int,
    amounts: tuple[int, ...],
    *,
    ts: float,
    tx: str,
    offer_token: str = IDMD_NFT,
) -> dict:
    """A raw Seaport ``OrderFulfilled``, exactly as WP1.9 passes it through.

    ``OrderFulfilled(bytes32 orderHash, address indexed offerer, address
    indexed zone, address recipient, SpentItem[] offer,
    ReceivedItem[] consideration)`` — two indexed args, so ``data`` is
    ``orderHash | recipient | offset(offer) | offset(consideration)`` followed
    by the two arrays. ``SpentItem`` is 4 words
    ``(itemType, token, identifier, amount)``; ``ReceivedItem`` is those plus a
    ``recipient``. ``amounts`` are the **native** consideration legs — seller
    proceeds and marketplace fee — which is what a realized price is made of.
    """
    offer = [_word(2), _addr_word(offer_token), _word(token_id), _word(1)]
    consideration: list[str] = []
    for amount in amounts:
        consideration += [
            _word(0),                          # itemType NATIVE
            _addr_word("0x" + "00" * 20),
            _word(0),
            _word(amount),
            _addr_word(DEV_WALLET),
        ]
    offer_at = 4 * 32                          # after the four head words
    consideration_at = offer_at + 32 + len(offer) * 32
    return {
        "address": SEAPORT.lower(),
        "topics": [
            TOPIC_SEAPORT_ORDER_FULFILLED,
            "0x" + _addr_word(OPS_WALLET),     # offerer (the seller)
            "0x" + "0" * 64,                   # zone
        ],
        "data": "0x" + "".join(
            [
                _word(0),                      # orderHash — unread here
                _addr_word(DEV_WALLET),        # recipient
                _word(offer_at),
                _word(consideration_at),
                _word(1),                      # len(offer)
                *offer,
                _word(len(amounts)),           # len(consideration)
                *consideration,
            ]
        ),
        "blockNumber": hex(25_707_884),
        "blockTimestamp": hex(int(ts)),
        "transactionHash": tx,
    }


# The one real Seaport purchase in the captures: dev wallet,
# ``fulfillAvailableAdvancedOrders``, two orders in one transaction whose
# realized totals sum to the transaction's own ``value``.
SEAPORT_TX = "0x5b4d1b4416bbd7d466c9aca7ecd371252ba2ea38aa82aa6c186be35035eadad2"
SEAPORT_TS = 1_786_163_591.0                   # 2026-08-08T04:33:11Z
SEAPORT_TX_VALUE_WEI = 363_898_900_000_000_000


def _seaport_fill() -> tuple[dict, ...]:
    """Both ``OrderFulfilled`` logs of that transaction, raw."""
    return (
        _seaport_log(1751, (178_200_000_000_000_000, 1_800_000_000_000_000),
                     ts=SEAPORT_TS, tx=SEAPORT_TX),
        _seaport_log(354, (182_059_911_000_000_000, 1_838_989_000_000_000),
                     ts=SEAPORT_TS, tx=SEAPORT_TX),
    )


# Real channel calldata (announce_eth_txs.json — complete, not truncated).
SOON_HEX = "0x736f6f6e"                                   # "soon", nonce 0
REGISTER_HEX = (
    "0xf2c298be0000000000000000000000000000000000000000000000000000000000000020"
    "0000000000000000000000000000000000000000000000000000000000000035"
    "697066733a2f2f516d596a3962727053775a6f634a7772745a6e375835426f4e5550515"
    "54d77456171564e4654796764367a726133"
    "0000000000000000000000000000000000000000000000000000"
)
REGISTER_TS = 1_779_469_691.0                              # 2026-05-22T17:08:11Z
FUND_TS = 1_778_737_523.0                                  # 2026-05-14T05:45:23Z
NOW = 1_786_190_400.0                                      # 2026-08-08T12:00:00Z

#: The newest **self**-post in the default channel double — ten minutes before
#: the suite's clock, and that recency is load-bearing rather than cosmetic.
#:
#: `_channel_payload` makes this row's timestamp `last_ts`, `_readings` copies it
#: to `announce_last_ts`, WP2's `_detect_post` returns it as the detector's
#: `fired_ts`, and `build_signals` stores `fired["post"]["ts"] = min(ts, now)`.
#: A post older than `FIRED_TTL_S` (86400 s) therefore takes the *relaxation*
#: branch on the very cycle it is detected — "detected, but older than the TTL is
#: history, not news" — and renders `state="ok"` with a `last: …` detail instead
#: of FIRED. This constant used to be `1_779_000_000.0`, 83 days before `NOW`,
#: which made `"fired"` structurally unreachable in this suite: three WP4.11
#: tests asserted it and would all have failed, and no amount of manager work
#: could have fixed them. Keep any edit to this value inside the FIRED window.
SOON_TS = NOW - 600.0                                      # 2026-08-08T11:50:00Z

ERC8004 = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
REPLIER = "0x1c3A0Ad54418Fe843953C71dF23637DE732Ce159"


class FakeClock:
    def __init__(self, t: float = NOW) -> None:
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> float:
        self.t += float(seconds)
        return self.t


class DeadTransport:
    """Proves structurally that no test reaches the network."""

    async def aclose(self):
        return None

    async def post(self, *_a, **_k):     # pragma: no cover — must never be reached
        raise AssertionError("SURF manager tests must not touch the network")

    async def get(self, *_a, **_k):      # pragma: no cover
        raise AssertionError("SURF manager tests must not touch the network")


def test_the_doubles_construct_against_wp0s_frozen_models():
    """The cheapest possible guard on the thing that broke this plan once.

    Every helper below builds its model **by keyword**, so a WP0.4 rename is a
    `TypeError` here at collection. That matters more on the *consuming* side
    than on the producing one: WP4 reads models through `_field()`, and the
    earlier revision of this file read `state.lp_imd`, `state.identity_allowed`
    and `logs.identity_writes` off dataclasses that had no such fields. With a
    plain `getattr(..., None)` that is not an error at all — it is a hero panel
    that renders "unavailable" on a perfectly healthy chain, behind a green
    suite. Hence both halves: `_field()` raises on an unknown name, and this
    test proves the names the doubles use are real ones.
    """
    import dataclasses

    from tests.data.test_surf_models import CONSTRUCTOR_KWARGS

    for model, names in CONSTRUCTOR_KWARGS.items():
        assert tuple(f.name for f in dataclasses.fields(model)) == names

    # Constructing each double is the actual assertion — a TypeError here names
    # the field that moved.
    _chain_state()
    _channel_txs()
    _posted_channel_txs(NOW)
    _dev_tx()
    _market()
    _nft_stats()
    FakeSurfClient()

    # And every model *attribute* the manager reads must exist. `_field` raises
    # AttributeError on a typo, so this is the list that keeps it honest.
    reads = {
        ChainState: ("lp_liquidity", "lp_imd_wei", "lp_weth_wei", "lp_owner",
                     "identity_allowed", "imd_supply_wei", "block_number"),
        NonceSet: ("announce", "dev", "ops"),
        ChannelTx: ("tx_hash", "ts", "nonce", "from_addr", "to_addr",
                    "value_wei", "input_hex"),
        DevTx: ("tx_hash", "ts", "wallet_label", "from_addr", "counterparty",
                "counterparty_label", "value_wei", "kind"),
        MarketSnapshot: ("imd_price_usd", "imd_change_24h_pct", "imd_vol_24h_usd",
                         "pool_liquidity_usd", "pool_imd", "pool_weth",
                         "fp_price_usd", "eth_usd"),
        LogWindow: ("to_block", "bridge_mints", "identity_updates",
                    "v4_initializes", "seaport_sales"),
        NftStats: ("holders", "total_supply", "transfers_total", "transfers_24h",
                   "dev_holdings", "written", "floor_eth"),
    }
    for model, names in reads.items():
        declared = {f.name for f in dataclasses.fields(model)}
        assert not set(names) - declared, (
            f"{model.__name__}: WP4 reads {set(names) - declared}, which WP0 does "
            f"not declare — check for a flat-dict key used as a field name"
        )


def _chain_state(**overrides) -> ChainState:
    """A WP0.4 ``ChainState``, keyword-for-keyword. Wei in, tokens out later.

    Every key here is a real field of the frozen dataclass, so a rename in WP0.4
    makes this helper raise ``TypeError`` at collection — which is the point.
    Note what is *absent*: there is no ``identities_written`` — the registry
    exposes no written-hash getter, so WP0.4 dropped the field and the number
    lives on ``NftStats.written`` instead (WP1.8, and this file's header
    consequence 4). And ``lp_imd_wei``/``lp_weth_wei`` are present but are
    *derived* by WP1.4 from the tick bounds, so a double that sets them is
    standing in for that derivation, not for a getter.
    """
    fields = {
        "lp_liquidity": LP_LIQUIDITY,
        "lp_token0": WETH,
        "lp_token1": IMD_TOKEN,
        "lp_fee": 10_000,
        "lp_tokens_owed0_wei": 7_345_000_000_000_000_000,
        "lp_tokens_owed1_wei": 30_784_000_000_000_000_000_000,
        "lp_imd_wei": LP_IMD_WEI,
        "lp_weth_wei": LP_WETH_WEI,
        "lp_owner": OPS_WALLET,
        "identity_allowed": False,          # gate closed since 2026-05-14
        "imd_supply_wei": IMD_SUPPLY_WEI,
        "sqrt_price_x96": 4_181_066_022_637_632_195_530_919_936,
        "pool_tick": -3466,
        "imd_name": "Identity.md",
        "imd_symbol": "IMD",
        "block_number": BLOCK,
    }
    fields.update(overrides)
    return ChainState(**fields)


def _channel_txs() -> list[ChannelTx]:
    """The four real channel shapes.

    ``ChannelTx`` has **no** ``kind``/``text`` field: the client returns the row
    as read and the manager classifies it through the pure layer.  So every
    assertion downstream about a kind or a message body is an assertion about
    ``classify_channel_tx`` / ``decode_utf8_calldata`` running for real on the
    ``input_hex`` carried here.
    """
    return [
        ChannelTx(tx_hash="0x" + "a1" * 32, ts=SOON_TS, nonce=0,
                  from_addr=ANNOUNCE, to_addr=ANNOUNCE, value_wei=0,
                  input_hex=SOON_HEX),
        ChannelTx(tx_hash="0x" + "a2" * 32, ts=REGISTER_TS, nonce=4,
                  from_addr=ANNOUNCE, to_addr=ERC8004, value_wei=0,
                  input_hex=REGISTER_HEX, method="register"),
        ChannelTx(tx_hash="0x" + "a3" * 32, ts=FUND_TS, nonce=2266,
                  from_addr=DEV_WALLET, to_addr=ANNOUNCE,
                  value_wei=54_000_000_000_000_000, input_hex="0x"),
        ChannelTx(tx_hash="0x" + "a4" * 32, ts=SOON_TS + 60.0, nonce=0,
                  from_addr=REPLIER, to_addr=ANNOUNCE, value_wei=0,
                  input_hex="0x686579"),                          # "hey"
    ]


def _posted_channel_txs(ts: float, *, tx: str = "0x" + "a9" * 32) -> list[ChannelTx]:
    """The channel page as it looks *after* a new self-post lands at ``ts``.

    A test that bumps the announce nonce but keeps handing back the *old*
    ``_channel_txs()`` page is not exercising a new post — it is exercising a
    stale page, which is a different scenario with its own test
    (``test_a_stale_page_never_quotes_an_old_body_under_a_new_nonce``, where the
    page read *fails*). The difference is visible in exactly one number and it is
    the number PRD §3 sells: the FIRED row is dated to ``announce_last_ts``, so a
    page that still holds only the previous post dates brand-new news to that
    post's timestamp instead of to the post that just landed.

    ``nonce`` is the nonce this tx *consumed*, so a page whose newest row is
    ``ANNOUNCE_NONCE`` belongs to an account nonce of ``ANNOUNCE_NONCE + 1`` —
    which is what the callers set on their ``NonceSet``.
    """
    return [
        ChannelTx(tx_hash=tx, ts=float(ts), nonce=ANNOUNCE_NONCE,
                  from_addr=ANNOUNCE, to_addr=ANNOUNCE, value_wei=0,
                  input_hex=SOON_HEX),
        *_channel_txs(),
    ]


def _market(**overrides) -> MarketSnapshot:
    """A WP0.4 ``MarketSnapshot``, keyword-for-keyword.

    ``pool_imd``/``pool_weth`` are DexScreener's **whole-pool reserves across
    every position**, kept for the market panel's cross-check only. They are
    *not* the hero's LP legs: those are ``ChainState.lp_imd_wei`` /
    ``lp_weth_wei`` for position 1167726 alone, which WP1.4 derives from the
    position's tick bounds precisely so the whole-pool numbers are never
    substituted (WP0.4, WP1.4, and this file's header table). Neither
    ``pool_*`` value is ever divided — they are already whole tokens, so
    scaling them would be a second division of something that was never wei.

    ``POOL_IMD``/``POOL_WETH`` are therefore the *larger* pair, and they have
    to be visibly larger for this double to be worth anything: these fields
    exist here only so ``test_wei_is_divided_exactly_once`` can assert
    ``data["lp_imd"] != pytest.approx(POOL_IMD)`` and
    ``data["lp_weth"] != pytest.approx(POOL_WETH)``. This double used to carry
    ``388_421.0``/``142.7067`` — the position's own legs to the last digit — so
    those two assertions were structurally unsatisfiable and the discrimination
    the docstring claimed was one the numbers denied. See the constants.

    ``indexer_name`` is DexScreener's (current) — GeckoTerminal's stale
    "Vibe Coins" never reaches a model, so there is no staleness flag to set.
    """
    fields = {
        "imd_price_usd": IMD_PRICE_USD,
        "imd_price_usd_gecko": IMD_PRICE_USD,
        "imd_change_24h_pct": CHANGE_24H,
        "imd_vol_24h_usd": VOL_24H_USD,
        "pool_liquidity_usd": POOL_LIQ_USD,
        "pool_imd": POOL_IMD,
        "pool_weth": POOL_WETH,
        "fp_price_usd": FP_PRICE_USD,
        "fdv_usd": 1_284_000.0,
        "eth_usd": ETH_USD,
        "indexer_name": "Identity.md",
        "indexer_symbol": "IMD",
        "sources_agree": True,
    }
    fields.update(overrides)
    return MarketSnapshot(**fields)


def _dev_tx(**overrides) -> DevTx:
    """A WP0.4 ``DevTx`` as WP1.6 hands it over: already filtered and labelled.

    The real 2026-08-07 33-ETH LP add.  ``counterparty_label`` is populated
    because the client fills it from ``KNOWN_LABELS``; the manager turns it into
    the ``counterparty_known`` boolean and scales the wei.  Tests that care about
    an *unknown* counterparty override ``counterparty_label=None`` — that is the
    poisoning-relevant shape, and it must render dimmed, never trusted.
    """
    fields = {
        "tx_hash": "0x" + "b1" * 32,
        "ts": NOW - 3600.0,
        "wallet_label": "ops",
        "from_addr": OPS_WALLET,
        "to_addr": NFPM,
        "counterparty": NFPM,
        "counterparty_label": "NFPM",
        "value_wei": 33_252_659_725_872_729_307,
        "method": "multicall",
        "kind": "lp",
        "created_contract": None,
    }
    fields.update(overrides)
    return DevTx(**fields)


def _nft_stats(**overrides) -> NftStats:
    """A WP0.4 ``NftStats`` as WP1.8 hands it over — the live 2026-08-08 values.

    ``written=1`` is the real chain: one identity of 2000 has a hash, set
    2026-05-14. WP1.8 derives it with ``_count_identities_written()`` over the
    registry's **lifetime** Blockscout log view, counted across distinct
    ``topics[1]``, so it is a genuine producer and both ``identities_written``
    and ``nft_written`` read it. Tests that want the unavailable state override
    ``written=None`` — never ``0``, which would claim nobody has written one.

    ``transfers_24h`` stays ``None`` here: it is the *rate*, and WP1.8 answers
    ``None`` rather than a lower bound when its page walk does not reach the
    24 h edge (wp1.md open issue 12). ``floor_eth`` is pinned ``None`` for good.
    """
    fields = {
        "holders": NFT_HOLDERS,
        "total_supply": 2000,
        "transfers_total": 7411,          # lifetime counter, not a daily rate
        "dev_holdings": 3,
        "transfers_24h": None,
        "written": 1,
    }
    fields.update(overrides)
    return NftStats(**fields)


#: A plausible v4 pool id (bytes32). Never the real one — this is a double.
POOL_ID = "0x" + "c0" * 32


def _pool_v4_state(**overrides) -> PoolV4State:
    """A WP0.4 ``PoolV4State``, keyword-for-keyword. Resolves through the hook
    by default; a test wanting the fallback path overrides
    ``pool_id_source="fallback"``.

    ``sqrt_price_x96`` (fix round 10a) is chosen, not copied from
    ``_chain_state``'s v3 slot0 value: it is reverse-solved so
    ``surf_v4.price_eth_per_imd(sqrt) * ETH_USD == IMD_PRICE_USD`` exactly,
    so the default double represents one coherent world where the on-chain
    price (now authoritative) and the market fixtures' DexScreener price
    agree -- a test that wants a genuine chain/market disagreement overrides
    ``sqrt_price_x96`` explicitly instead of inheriting an accidental one.
    """
    fields = {
        "pool_id": POOL_ID,
        "sqrt_price_x96": 4_125_170_652_482_305_403_204_344_479_744,
        "tick": -3466,
        "lp_fee": 10_000,
        "liquidity": 987_654_321_098_765,
        "pool_id_source": "hook",
    }
    fields.update(overrides)
    return PoolV4State(**fields)


def _launchpad_coin(**overrides) -> LaunchpadCoin:
    """A WP0.4 ``LaunchpadCoin``. ``creator`` defaults to an address with no
    ``KNOWN_LABELS`` entry — a test wanting the known-creator branch overrides
    ``creator=DEV_WALLET``.
    """
    fields = {
        "ticker": "ICE",
        "name": "Icecream",
        "creator": "0x" + "c1" * 20,
        "age_s": 3_600.0,
        "price_eth": 0.000123,
        "change_1h_pct": 7.2727,
        "swaps_1h": 5,
        "imd_burned": 0.42,
    }
    fields.update(overrides)
    return LaunchpadCoin(**fields)


def _launchpad_state(**overrides) -> LaunchpadState:
    """A WP0.4 ``LaunchpadState``, keyword-for-keyword.

    ``coin_count`` is deliberately **not** 146 — the tripwire's own "a
    146-coin sweep" and the stale-seed regression test's literal ``146`` both
    need a default that cannot be confused with either by coincidence.

    ``swaps_by_coin`` (fix round 2) carries the default ``coins`` row's own
    ``swaps_1h`` (``ICE: 5``, off ``_launchpad_coin``'s default) plus five
    quieter coins that never reach the render-capped ``coins`` tuple — which
    is exactly what the field is for: the FULL in-window population, not the
    capped slice.

    **Six** active coins, not one (final fix wave, C1). The one-coin default
    sat below ``surf_launchpad.HOT_MIN_ACTIVE`` (5), so
    ``hot_coin_threshold`` returned ``None`` and HOT COIN answered "hour too
    thin to judge" whatever the detector did — which meant
    ``test_no_signal_fires_and_no_baseline_moves_under_a_total_outage``, the
    flagship outage invariant, passed **vacuously** for that detector and
    never noticed it firing off a day-old last-good slot. With six coins the
    hour is judgeable and ICE (5) clears the bar (median 1 -> floor 5), so
    the invariant now actually bites HOT COIN.
    """
    fields = {
        "coin_count": 12,
        "imd_to_burn_wei": round(15.06 * 10**18),
        "total_real_imd_wei": round(500_000 * 10**18),
        "burn_fee_bps": 50,
        "creator_fee_bps": 50,
        "creator_eth_owed_wei": round(0.25 * 10**18),
        "executor_balance_wei": round(3.0 * 10**18),
        "min_bridge_wei": round(10.0 * 10**18),
        "coins": (_launchpad_coin(),),
        "swap_count": 25,
        "trader_count": 12,
        "burned_total_wei": round(90.0 * 10**18),
        "swaps_by_coin": {"ICE": 5, "AAA": 1, "BBB": 1, "CCC": 2, "DDD": 1, "EEE": 2},
    }
    fields.update(overrides)
    return LaunchpadState(**fields)


class FakeSurfClient:
    """A SurfClient-shaped double. Any method set to ``None`` reports failure."""

    def __init__(self, **overrides) -> None:
        self.http = DeadTransport()
        self.calls: list[str] = []
        self.closed = False
        self._returns = {
            "fetch_nonces": NonceSet(
                announce=ANNOUNCE_NONCE, dev=DEV_NONCE, ops=OPS_NONCE,
                block_number=BLOCK,
            ),
            "fetch_chain_state": _chain_state(),
            "fetch_channel_txs": _channel_txs(),
            "fetch_dev_activity": [_dev_tx()],
            "fetch_market": _market(),
            # All four groups are **raw** log dicts — WP1.9 hands them over
            # verbatim and WP4.9 owns every decoder (wp1.md, *Decode
            # ownership*). ``seaport_sales`` is not the exception it was once
            # written as: it arrives with `topics`/`data` like the other three.
            "fetch_recent_logs": LogWindow(
                from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
                bridge_mints=(), identity_updates=(), v4_initializes=(),
                seaport_sales=_seaport_fill(),
            ),
            "fetch_nft_stats": _nft_stats(),
            # ``{tx_hash: signer}`` for the transactions the state pool could
            # read. **Empty by default, and that is the honest default**: a
            # double that answered "the dev sent it" for every hash would make
            # the v4-launch corroboration structurally unfalsifiable, which is
            # the exact shape of the defect it exists to close. A test that
            # wants a launch attributed says whose it is.
            "fetch_tx_senders": {},
            "fetch_pool_v4": _pool_v4_state(),
            "fetch_launchpad": _launchpad_state(),
            # ``(count, newest_row)`` — the real client's shape. The newest
            # row is ``None`` here because no manager key reads it; only the
            # count reaches ``SURF_KEYS`` (``decoy_pool_count``).
            "fetch_decoy_pool_count": (4, None),
        }
        self._returns.update(overrides)

    async def _answer(self, name: str):
        self.calls.append(name)
        value = self._returns[name]
        if isinstance(value, BaseException):
            raise value
        return value

    async def fetch_tx_senders(self, tx_hashes):
        """The real client's contract: a hash it could not read is ABSENT."""
        table = await self._answer("fetch_tx_senders")
        table = {str(k).lower(): str(v).lower() for k, v in (table or {}).items()}
        return {
            tx: table[tx]
            for tx in {str(h or "").lower() for h in tx_hashes or ()}
            if tx in table
        }

    async def fetch_nonces(self):        return await self._answer("fetch_nonces")
    async def fetch_chain_state(self):   return await self._answer("fetch_chain_state")
    async def fetch_channel_txs(self):   return await self._answer("fetch_channel_txs")
    async def fetch_dev_activity(self):  return await self._answer("fetch_dev_activity")
    async def fetch_market(self, real_pool_id=None):
        return await self._answer("fetch_market")
    async def fetch_recent_logs(self):   return await self._answer("fetch_recent_logs")
    async def fetch_nft_stats(self):     return await self._answer("fetch_nft_stats")
    async def fetch_pool_v4(self):       return await self._answer("fetch_pool_v4")
    async def fetch_launchpad(self):     return await self._answer("fetch_launchpad")

    async def fetch_decoy_pool_count(self, real_pool_id):
        """Ignores ``real_pool_id`` — the double just answers the fixed pair."""
        return await self._answer("fetch_decoy_pool_count")

    async def close(self):
        self.closed = True


def _manager(tmp_path, *, client=None, clock=None, **kwargs) -> SurfManager:
    clock = clock or FakeClock()
    manager = SurfManager(
        poll_interval=30,
        clock=clock,
        cache_path=str(tmp_path / "surf_cache.json"),
        client=client if client is not None else FakeSurfClient(),
        cache=SurfCache(path=str(tmp_path / "surf_cache.json"), clock=clock),
        **kwargs,
    )
    manager._clock_double = clock
    return manager


@pytest.fixture
def manager(tmp_path):
    return _manager(tmp_path)


def _manager_with(**method_overrides) -> SurfManager:
    """A healthy manager whose client has the given coroutine(s) replaced.

    No ``tmp_path`` fixture: used by tests (the Task 6 tripwire and its
    siblings) that take no fixture parameters of their own, mirroring
    curator's equivalent helper. Owns a throwaway cache directory instead.
    """
    client = FakeSurfClient()
    for name, coro in method_overrides.items():
        setattr(client, name, coro)
    return _manager(Path(tempfile.mkdtemp()), client=client)


def _manager_with_last_good(
    slot: str, payload: Any, *, at: float = 0.0
) -> SurfManager:
    """A manager whose cache already holds ``payload`` as ``slot``'s last-good,
    stamped at ``at`` — or, when ``payload`` is ``None``, a cache that has
    never populated ``slot`` at all (the "nothing to serve" case).
    """
    manager = _manager_with()
    if payload is not None:
        manager.cache.store_last_good(slot, payload, ts=at)
    return manager


# ---------------------------------------------------------------------------
# The frozen contract
# ---------------------------------------------------------------------------


async def test_returns_exactly_surf_keys(manager):
    data = await manager.fetch_and_compute()
    assert set(data) == set(SURF_KEYS)
    assert len(data) == len(SURF_KEYS)


async def test_every_source_group_is_named(manager):
    assert SOURCES == (
        SOURCE_CHAIN, SOURCE_CHANNEL, SOURCE_MARKET,
        SOURCE_LOGS, SOURCE_NFT, SOURCE_ACTIVITY, SOURCE_LAUNCHPAD,
    )


async def test_close_persists_the_cache_and_closes_the_client(tmp_path):
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client)
    await m.fetch_and_compute()
    await m.close()
    assert client.closed is True
    assert (tmp_path / "surf_cache.json").exists()


# ---------------------------------------------------------------------------
# Fast tier — the chain group
# ---------------------------------------------------------------------------


async def test_hero_values_come_straight_off_the_chain_read(manager):
    data = await manager.fetch_and_compute()
    assert data["lp_liquidity"] == LP_LIQUIDITY
    assert data["lp_imd"] == pytest.approx(LP_IMD_WEI / 1e18)
    assert data["lp_weth"] == pytest.approx(LP_WETH_WEI / 1e18)
    assert data["lp_owner_ok"] is True             # ownerOf(1167726) == frenpet.eth
    assert data["gate_open"] is False              # ChainState.identity_allowed
    assert data["imd_supply"] == pytest.approx(IMD_SUPPLY)
    assert data["feed_nonce"] == ANNOUNCE_NONCE
    # The hero's other number, `identities_written`, is deliberately NOT here:
    # `ChainState` has no such getter, so it rides in on the slow tier off
    # `NftStats.written`. Task WP4.10 asserts it.


async def test_a_wrong_lp_owner_is_flagged_not_hidden(tmp_path):
    client = FakeSurfClient(fetch_chain_state=_chain_state(lp_owner="0x" + "de" * 20))
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["lp_owner_ok"] is False


async def test_an_unknown_lp_owner_is_none_not_false(tmp_path):
    """``None`` is 'we could not read it'; ``False`` is 'someone else owns it'."""
    client = FakeSurfClient(
        fetch_chain_state=_chain_state(
            identity_allowed=None, imd_supply_wei=None, lp_liquidity=None,
            lp_imd_wei=None, lp_weth_wei=None, lp_owner=None,
        )
    )
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["lp_owner_ok"] is None
    assert data["gate_open"] is None
    assert data["imd_supply"] is None


async def test_wei_is_divided_exactly_once(tmp_path):
    """WP0.4's models are wei-native; this flat dict is the presentation boundary."""
    data = await _manager(tmp_path).fetch_and_compute()
    assert data["imd_supply"] == pytest.approx(IMD_SUPPLY_WEI / 1e18)
    assert data["lp_imd"] == pytest.approx(LP_IMD_WEI / 1e18)
    assert data["lp_weth"] == pytest.approx(LP_WETH_WEI / 1e18)
    # MarketSnapshot.pool_* is the whole pool, not this position — it must not be
    # what the hero shows, and it is not divided either way. Both halves are
    # asserted because a hero fed from the market snapshot would show whichever
    # leg the writer reached for first.
    assert data["lp_imd"] != pytest.approx(POOL_IMD)
    assert data["lp_weth"] != pytest.approx(POOL_WETH)
    # And the two pairs really are distinguishable — the point the old doubles
    # missed. `LP_IMD_WEI / 1e18` is 388420.99999999994, so a `pool_imd` of
    # 388_421.0 satisfies `pytest.approx` at the default rel=1e-6 and the two
    # assertions above become mutually exclusive with the two before them.
    assert LP_IMD_WEI / 1e18 != pytest.approx(POOL_IMD)
    assert LP_WETH_WEI / 1e18 != pytest.approx(POOL_WETH)
    # lp_liquidity is a raw uint128, not a token amount: it must NOT be divided.
    assert data["lp_liquidity"] == LP_LIQUIDITY


async def test_burned_cum_is_zero_after_one_read_then_accumulates(tmp_path):
    """Day one on a healthy RPC: ``0.0``, meaning "observed nothing yet".

    Note what this is *not*: an all-time total.  ~58,849 IMD had already been
    burned before this cache existed (PRD §1) and no keyless source can hand
    it to us, so ``0.0`` here is a statement about the observation window
    only.  WP3.2's hero renders it as words rather than the digit ``0`` for
    that reason -- if that rendering contract ever loosens, this key starts
    lying on every fresh install.
    """
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client)

    first = await m.fetch_and_compute()
    assert first["imd_burned_cum"] == 0.0        # one read: honestly zero observed

    client._returns["fetch_chain_state"] = _chain_state(
        block_number=BLOCK + 100,
        imd_supply_wei=IMD_SUPPLY_WEI - 15_745 * 10**18,
    )
    second = await m.fetch_and_compute()
    assert second["imd_burned_cum"] == pytest.approx(15_745.0)
    assert second["imd_supply"] == pytest.approx(2_360_986.868679)


async def test_a_chain_outage_is_flagged_and_invents_nothing(tmp_path):
    """The 'only the chain group' half of this lands in WP4.10, once six exist."""
    client = FakeSurfClient(fetch_nonces=None, fetch_chain_state=None)
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert SOURCE_CHAIN in data["degraded"]
    assert data["imd_supply"] is None
    assert data["feed_nonce"] is None
    assert data["lp_liquidity"] is None
    # Cold start + dead chain group: never read a supply, so there is nothing
    # to report -- ``None`` (unavailable), not ``0.0`` ("watched, saw nothing").
    assert data["imd_burned_cum"] is None


async def test_a_raising_client_call_is_a_degradation_not_a_crash(tmp_path):
    client = FakeSurfClient(fetch_chain_state=RuntimeError("publicnode 521"))
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert set(data) == set(SURF_KEYS)
    assert SOURCE_CHAIN in data["degraded"]


# ---------------------------------------------------------------------------
# Medium tier — market, logs, channel
# ---------------------------------------------------------------------------


async def test_parity_is_computed_live_never_quoted(manager):
    data = await manager.fetch_and_compute()
    assert data["imd_price_usd"] == pytest.approx(IMD_PRICE_USD)
    assert data["fp_price_usd"] == pytest.approx(FP_PRICE_USD)
    assert data["parity_pct"] == pytest.approx(PARITY_PCT)
    assert data["imd_vol_24h_usd"] == pytest.approx(VOL_24H_USD)
    assert data["pool_liquidity_usd"] == pytest.approx(POOL_LIQ_USD)
    assert data["imd_change_24h_pct"] == pytest.approx(CHANGE_24H)
    assert data["eth_usd"] == pytest.approx(ETH_USD)


async def test_parity_comes_from_the_pure_layer_not_a_local_copy(manager):
    """The math lives in ``analytics/surf_signals.parity_pct`` and nowhere else."""
    import inspect

    from maxpane_dashboard.analytics import surf_signals
    from maxpane_dashboard.data import surf_manager as sm

    assert sm.parity_pct is surf_signals.parity_pct
    source = inspect.getsource(sm)
    assert "_parity" not in source, "parity math was re-implemented in data/"


async def test_parity_is_none_when_either_leg_is_missing(tmp_path):
    client = FakeSurfClient(
        fetch_market=_market(
            imd_change_24h_pct=None, imd_vol_24h_usd=None,
            pool_liquidity_usd=None, pool_imd=None, pool_weth=None,
            fp_price_usd=None, eth_usd=None,
        )
    )
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["parity_pct"] is None


async def test_the_feed_is_classified_and_decoded_by_the_pure_layer(manager):
    data = await manager.fetch_and_compute()
    kinds = {item["tx_hash"]: item["kind"] for item in data["feed_items"]}
    assert kinds["0x" + "a1" * 32] == "self"     # from == to == channel
    assert kinds["0x" + "a2" * 32] == "action"   # channel -> ERC-8004 register()
    assert kinds["0x" + "a3" * 32] == "fund"     # dev wallet -> channel, 0.054 ETH
    assert kinds["0x" + "a4" * 32] == "reply"    # anyone else

    texts = {item["tx_hash"]: item["text"] for item in data["feed_items"]}
    assert texts["0x" + "a1" * 32] == "soon"
    assert texts["0x" + "a2" * 32] is None       # register() calldata is not UTF-8
    assert texts["0x" + "a4" * 32] == "hey"

    # Newest first, and the known-label map names the channel.
    assert data["feed_items"][0]["ts"] >= data["feed_items"][-1]["ts"]
    labels = {i["tx_hash"]: i["from_label"] for i in data["feed_items"]}
    assert labels["0x" + "a1" * 32] == KNOWN_LABELS[ANNOUNCE.lower()]
    assert labels["0x" + "a4" * 32] is None      # unknown senders stay unlabelled


async def test_last_post_age_counts_self_posts_only(manager):
    """A community reply is not the dev posting (PRD §6.4)."""
    data = await manager.fetch_and_compute()
    # a1 is the only self-post; a2 is an action, a3 a fund, a4 a community reply.
    assert data["feed_last_post_age_s"] == pytest.approx(NOW - SOON_TS)


async def test_channel_bodies_are_fetched_only_when_the_nonce_moves(tmp_path):
    clock = FakeClock()
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client, clock=clock)

    await m.fetch_and_compute()
    assert client.calls.count("fetch_channel_txs") == 1

    clock.advance(600.0)                      # medium tier is due again
    await m.fetch_and_compute()
    assert client.calls.count("fetch_channel_txs") == 1   # nonce unchanged: skipped

    client._returns["fetch_nonces"] = NonceSet(
        announce=ANNOUNCE_NONCE + 1, dev=DEV_NONCE, ops=OPS_NONCE
    )
    clock.advance(600.0)
    await m.fetch_and_compute()
    assert client.calls.count("fetch_channel_txs") == 2   # a new post: fetched


async def test_a_new_post_reaches_the_feed_in_the_cycle_that_detects_it(tmp_path):
    """PRD §11.1: decoded text within *one* refresh interval of the tx landing.

    The nonce is read on the fast tier every 30 s, so a nonce change must force
    the body fetch immediately.  Gating the bodies behind the 90 s medium TTL
    would let the signal fire up to three refreshes before the text it quotes
    exists — the exact opposite of the job this dashboard has.
    """
    clock = FakeClock()
    client = FakeSurfClient(fetch_channel_txs=[])       # channel read as empty
    m = _manager(tmp_path, client=client, clock=clock)

    first = await m.fetch_and_compute()
    assert first["feed_items"] == []
    assert client.calls.count("fetch_channel_txs") == 1

    # One poll interval later — the medium tier is NOT due — a post lands.
    client._returns["fetch_nonces"] = NonceSet(
        announce=ANNOUNCE_NONCE + 1, dev=DEV_NONCE, ops=OPS_NONCE
    )
    client._returns["fetch_channel_txs"] = _channel_txs()
    clock.advance(30.0)
    second = await m.fetch_and_compute()

    assert client.calls.count("fetch_channel_txs") == 2
    assert len(second["feed_items"]) == 4                # same cycle, not the next
    # The signal half of this — FIRED and the decoded body in the *same* cycle —
    # is asserted in Task WP4.11 once build_signals is wired.


async def test_a_skipped_channel_fetch_is_not_a_degradation(tmp_path):
    clock = FakeClock()
    m = _manager(tmp_path, clock=clock)
    await m.fetch_and_compute()
    clock.advance(600.0)
    data = await m.fetch_and_compute()
    assert SOURCE_CHANNEL not in data["degraded"]
    assert len(data["feed_items"]) == 4         # served from last-good


async def test_the_medium_tier_is_skipped_while_fresh(tmp_path):
    clock = FakeClock()
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client, clock=clock)

    await m.fetch_and_compute()
    before = client.calls.count("fetch_market")
    clock.advance(30.0)                          # inside the 90 s medium TTL
    await m.fetch_and_compute()
    assert client.calls.count("fetch_market") == before
    assert client.calls.count("fetch_nonces") == 2       # fast tier always runs


async def test_a_skipped_medium_tier_still_renders_the_whole_market_panel(tmp_path):
    """A skip is not an outage, and the panel must not go dark for one.

    This is the other half of ``test_the_medium_tier_is_skipped_while_fresh``,
    and it is the half that bites: counting calls proves the tier was skipped and
    says nothing about what the payload then contains. With the shipped defaults
    (``--poll-interval`` 30 s, ``TIER_TTL_SECONDS[TIER_MEDIUM] = 90.0``) the
    medium tier is due on one refresh in three, so a `_cycle` that reads the
    seven market keys off `_pool_market`'s return value publishes `None` for all
    of them **two refreshes out of three** — `--` / `$ --` / `parity —` on a
    healthy chain — while `degraded` correctly omits ``market``, because a skip
    never reaches `_note`. Nothing else in this suite can see it: every other
    market assertion runs a single cycle in which every tier is due.
    """
    clock = FakeClock()
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client, clock=clock)

    await m.fetch_and_compute()
    clock.advance(30.0)                          # inside the 90 s medium TTL
    second = await m.fetch_and_compute()

    assert client.calls.count("fetch_market") == 1     # the tier really was skipped
    assert second["imd_price_usd"] == pytest.approx(IMD_PRICE_USD)
    assert second["fp_price_usd"] == pytest.approx(FP_PRICE_USD)
    assert second["parity_pct"] == pytest.approx(PARITY_PCT)
    assert second["imd_change_24h_pct"] == pytest.approx(CHANGE_24H)
    assert second["imd_vol_24h_usd"] == pytest.approx(VOL_24H_USD)
    assert second["pool_liquidity_usd"] == pytest.approx(POOL_LIQ_USD)
    assert second["eth_usd"] == pytest.approx(ETH_USD)
    assert SOURCE_MARKET not in second["degraded"]


#: The transaction that emits a hooked ``Initialize`` in the tests below, and
#: the wallet that signed it. Both matter: v4 ``initialize()`` is
#: permissionless, so the log alone says only that *somebody* paid gas, and the
#: signer is the part of it a stranger cannot forge.
LAUNCH_TX = "0x" + "a5" * 32
STRANGER = "0x" + "ee" * 20


def _hook_launch_status(m) -> str | None:
    """Mirrors the removed ``SurfManager._hook_status()`` exactly, against
    the persisted ``hook_launch``/``hook_unverified`` ``SLOT_LOGS`` fields.

    Fix round 12a removed the flat ``hook_status`` ``SURF_KEYS`` entry (no
    widget ever read it) and the method that computed it, but not the
    attribution machinery underneath (``_attribute_launches``/
    ``_valid_launch``/the persisted ``hook_launch`` record): those still
    write into ``SLOT_LOGS`` and ``analytics/surf_signals.py`` still advances
    a baseline off ``v4_hook_pools``. This helper is what lets the tests
    below -- particularly "a stranger cannot launch the hook for the price
    of gas", a security regression, not a rendering one -- keep asserting
    against that live mechanism directly instead of through the dead key.
    """
    entry = m.cache.get_last_good(SLOT_LOGS)
    if entry is None or not isinstance(entry.payload, dict):
        return None
    if SurfManager._valid_launch(entry.payload.get("hook_launch")) is not None:
        return "LAUNCHED"
    if entry.payload.get("hook_unverified"):
        return None
    return "NOT LIVE"


async def test_hook_status_reads_not_live_until_a_hooked_initialize_appears(tmp_path):
    client = FakeSurfClient(fetch_tx_senders={LAUNCH_TX: DEV_WALLET})
    m = _manager(tmp_path, client=client)
    await m.fetch_and_compute()
    assert _hook_launch_status(m) == "NOT LIVE"

    client._returns["fetch_recent_logs"] = LogWindow(
        from_block=BLOCK - 5_000,
        to_block=BLOCK + 10,
        bridge_mints=(),
        identity_updates=(),
        v4_initializes=(
            _v4_init_log("0x" + "ab" * 20, ts=NOW - 120.0, tx=LAUNCH_TX),
        ),
        seaport_sales=(),
    )
    m._clock_double.advance(600.0)
    await m.fetch_and_compute()
    assert _hook_launch_status(m) == "LAUNCHED"


async def test_a_stranger_can_not_launch_the_hook_for_the_price_of_gas(tmp_path):
    """Uniswap v4 ``initialize()`` is permissionless — the merge blocker.

    The client's filter accepts any ``Initialize`` from the PoolManager naming
    IMD in either currency, and a hook address only has to carry valid
    permission bits. So one transaction from any EOA used to produce
    ``hook_status: LAUNCHED`` and ``sig_lp: fired | V4 LAUNCH`` — permanently,
    because the flag was latched into the persisted cache and no code path
    could ever clear it.

    Every other failure in this layer degrades to an explicit unavailable
    state. This one manufactured a confident, permanent, adversarially-chosen
    *positive* on the single event PRD §1/§7 says the dashboard exists to
    catch. A pool a stranger created is not the dev's launch, and the signature
    on the enclosing transaction is what says so.
    """
    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
            bridge_mints=(), identity_updates=(), seaport_sales=(),
            v4_initializes=(
                _v4_init_log("0x" + "de" * 20, ts=NOW - 120.0, tx=LAUNCH_TX),
            ),
        ),
        fetch_tx_senders={LAUNCH_TX: STRANGER},
    )
    m = _manager(tmp_path, client=client, clock=FakeClock())
    data = await m.fetch_and_compute()

    assert _hook_launch_status(m) == "NOT LIVE"
    assert data["sig_lp_state"] != "fired"
    assert "V4 LAUNCH" not in (data["sig_lp_detail"] or "")
    # ...and it is still not the dev's launch 150 days and many clean windows
    # later, which is where the old latch made it permanent.
    client._returns["fetch_recent_logs"] = LogWindow(
        from_block=BLOCK, to_block=BLOCK + LOG_WINDOW,
        bridge_mints=(), identity_updates=(), v4_initializes=(), seaport_sales=(),
    )
    m._clock_double.advance(150 * 86400.0)
    later = await m.fetch_and_compute()
    assert _hook_launch_status(m) == "NOT LIVE"
    assert later["sig_lp_state"] != "fired"


async def test_an_unattributable_hooked_pool_is_unknown_never_launched(tmp_path):
    """The signer read failed, so we do not know whose pool this is.

    An explicit unknown (``None`` — the hero's unavailable state) is the honest
    answer and the only one that is not a guess. Publishing LAUNCHED would let
    an outage on *our* side decide the headline; publishing NOT LIVE would
    swallow a real launch. Neither is a claim this cycle earned.
    """
    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
            bridge_mints=(), identity_updates=(), seaport_sales=(),
            v4_initializes=(
                _v4_init_log("0x" + "ab" * 20, ts=NOW - 120.0, tx=LAUNCH_TX),
            ),
        ),
        fetch_tx_senders={},          # the state pool could not read the tx
    )
    m = _manager(tmp_path, client=client)
    data = await m.fetch_and_compute()
    assert _hook_launch_status(m) is None
    assert data["sig_lp_state"] != "fired"


async def test_a_persisted_launch_that_no_longer_names_a_dev_wallet_is_dropped(tmp_path):
    """The launch record is re-validated on every read — it is not a latch.

    A cache file written by an older build (whose ``hook_live`` was an
    unconditional boolean), hand-edited, or carried across a correction to the
    dev-wallet vocabulary can assert a launch that its own evidence does not
    support. The hero must return to NOT LIVE, because a state this
    consequential has to be able to stop being true when the evidence stops
    supporting it.
    """
    clock = FakeClock()
    m = _manager(tmp_path, client=FakeSurfClient(), clock=clock)
    m.cache.store_last_good(
        SLOT_LOGS,
        {
            "to_block": BLOCK,
            "bridge_mints": [],
            "v4_hook_pools": [],
            "hook_launch": {
                "ts": NOW - 3600.0, "tx_hash": LAUNCH_TX,
                "hooks": "0x" + "ab" * 20, "initiator": STRANGER,
            },
            "identity_writes": 0,
            "nft_last_sales": [],
        },
        ts=NOW - 3600.0,
    )
    assert _hook_launch_status(m) == "NOT LIVE"

    clock.advance(600.0)
    await m.fetch_and_compute()
    assert _hook_launch_status(m) == "NOT LIVE"
    # ...and the unusable record is gone from the slot rather than lying dormant.
    assert m.cache.get_last_good(SLOT_LOGS).payload.get("hook_launch") is None


async def test_a_launch_is_never_un_launched_when_the_log_window_moves_past_it(tmp_path):
    """``Initialize`` is irreversible; the ~8 h log window is not.

    ``LOG_WINDOW_BLOCKS`` is 2400 blocks (≈8 h at 12 s), and `_pool_logs`
    replaces `SLOT_LOGS` wholesale on every successful medium-tier read. So a
    launch derived from the current window alone flips the hero back from
    LAUNCHED to NOT LIVE roughly eight hours after the launch, on a perfectly
    healthy chain, for the one event PRD §1/§7 says this dashboard exists to
    catch. That is a wrong value rather than a stale one — no `as of` marker
    redeems it — so `_pool_logs` persists the verified launch record while
    leaving `v4_hook_pools` as the current window's rows.

    Persistence, not permanence: the record is only ever written from a
    dev-signed ``Initialize`` and is re-validated against that same vocabulary
    every time it is read (see
    ``..._that_no_longer_names_a_dev_wallet_is_dropped``).

    The cycle above (`..._until_a_hooked_initialize_appears`) cannot see this: it
    asserts LAUNCHED on the cycle that reads the log and never runs a later one.
    """
    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
            bridge_mints=(), identity_updates=(), seaport_sales=(),
            v4_initializes=(
                _v4_init_log("0x" + "ab" * 20, ts=NOW - 120.0, tx=LAUNCH_TX),
            ),
        ),
        fetch_tx_senders={LAUNCH_TX: OPS_WALLET},
    )
    m = _manager(tmp_path, client=client)
    await m.fetch_and_compute()
    assert _hook_launch_status(m) == "LAUNCHED"

    # The pool is still there — the window has simply moved past its Initialize.
    client._returns["fetch_recent_logs"] = LogWindow(
        from_block=BLOCK, to_block=BLOCK + LOG_WINDOW,
        bridge_mints=(), identity_updates=(), v4_initializes=(), seaport_sales=(),
    )
    m._clock_double.advance(600.0)
    await m.fetch_and_compute()

    assert _hook_launch_status(m) == "LAUNCHED"
    # ...and the *rows* still mean "seen in this window", so the panel does not
    # claim a pool was initialized in a window that did not contain it.
    assert m.cache.get_last_good(SLOT_LOGS).payload["v4_hook_pools"] == []


async def test_a_hookless_third_party_pool_does_not_launch_the_hook(tmp_path):
    """All 19 existing IMD v4 pools are third-party and hookless."""
    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - 5_000, to_block=BLOCK, bridge_mints=(),
            identity_updates=(),
            v4_initializes=(
                _v4_init_log("0x" + "00" * 20, ts=NOW - 120.0, tx="0x" + "b0" * 32),
            ),
            seaport_sales=(),
        )
    )
    m = _manager(tmp_path, client=client)
    await m.fetch_and_compute()
    assert _hook_launch_status(m) == "NOT LIVE"


async def test_hook_status_is_none_when_the_logs_pool_never_answered(tmp_path):
    client = FakeSurfClient(fetch_recent_logs=None)
    m = _manager(tmp_path, client=client)
    data = await m.fetch_and_compute()
    assert _hook_launch_status(m) is None
    assert SOURCE_LOGS in data["degraded"]


async def test_log_rows_are_decoded_into_wp2s_shapes_and_cached_that_way(tmp_path):
    """The 2026-08-07 staging mint, decoded once and stored in WP2's row shape.

    WP1 hands raw rows over (its own ratchet test bans `_word_addr`/`_log_ts`
    from the client), so the amount word, the ``to`` topic and the block
    timestamp are decoded here — and cached decoded, because `_readings` reads
    the slot back on every fast-only refresh.
    """
    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - 5_000, to_block=BLOCK,
            bridge_mints=(
                _mint_log(OPS_WALLET, 10_000 * 10**18, ts=1_786_076_339.0,
                          tx="0x17084b1bfc998a457416c1ba9689f50ca04efc6e1"
                             "60b7e28d4c75dc89bcea85c"),
            ),
            identity_updates=(
                _identity_log(1751, ts=NOW - 600.0, tx="0x" + "e1" * 32),
                # The same holder replacing their hash: ONE identity written,
                # two logs. `len(rows)` here is the wrong number (wp1.md #9).
                _identity_log(1751, ts=NOW - 300.0, tx="0x" + "e2" * 32),
            ),
            v4_initializes=(
                _v4_init_log("0x" + "ab" * 20, ts=NOW - 120.0, tx=LAUNCH_TX),
            ),
            seaport_sales=(),
        ),
        fetch_tx_senders={LAUNCH_TX: DEV_WALLET},
    )
    m = _manager(tmp_path, client=client)
    await m.fetch_and_compute()
    cached = m.cache.get_last_good(SLOT_LOGS).payload

    mint = cached["bridge_mints"][0]
    assert mint["amount"] == pytest.approx(10_000.0)      # the data word / 1e18
    assert mint["to_label"] == KNOWN_LABELS[OPS_WALLET.lower()]
    assert mint["ts"] == pytest.approx(1_786_076_339.0)   # blockTimestamp, not now
    assert mint["tx_hash"].startswith("0x17084b1b")

    assert cached["v4_hook_pools"][0]["hooks"] == "0x" + "ab" * 20
    # The stored launch is the *evidence*, not a boolean: the signer is what
    # separates the dev's launch from a stranger's transaction, so it has to
    # survive into the file that the next process re-validates.
    assert cached["hook_launch"]["initiator"] == DEV_WALLET.lower()
    assert cached["hook_launch"]["tx_hash"] == LAUNCH_TX
    assert cached["hook_unverified"] is False

    assert cached["identity_writes"] == 1                 # distinct ids, not rows
    assert cached["nft_last_sales"] == []                 # read, and empty


async def test_seaport_sales_are_decoded_from_the_raw_order_logs(tmp_path):
    """The real 2026-08-08 fill, walked out of raw ``OrderFulfilled`` payloads.

    ``LogWindow.seaport_sales`` arrives **raw** like the other three groups
    (wp1.md, *Decode ownership*), so the offer/consideration walk is WP4's. The
    proof it is right is arithmetic rather than a hand-typed expectation: the
    two realized totals of tx ``0x5b4d1b44…eadad2`` sum to that transaction's
    own ``value``, ``363898900000000000`` wei. Miss an array offset or count
    only the seller's leg and the identity stops holding.
    """
    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
            bridge_mints=(), identity_updates=(), v4_initializes=(),
            seaport_sales=(
                *_seaport_fill(),
                # An OrderFulfilled for a *different* collection. WP1's
                # pre-filter is a substring match on the payload, so any order
                # that merely mentions IDMD anywhere reaches us; only the offer
                # side makes it a sale of an identity.
                _seaport_log(7, (1_000,), ts=SEAPORT_TS - 60.0,
                             tx="0x" + "f0" * 32,
                             offer_token="0x" + "be" * 20),
            ),
        )
    )
    m = _manager(tmp_path, client=client)
    await m.fetch_and_compute()
    sales = m.cache.get_last_good(SLOT_LOGS).payload["nft_last_sales"]

    assert [row["token_id"] for row in sales] == [1751, 354]
    assert sales[0]["eth"] == pytest.approx(0.18)
    assert sales[1]["eth"] == pytest.approx(0.1838989)
    assert all(row["ts"] == pytest.approx(SEAPORT_TS) for row in sales)
    assert sum(row["eth"] for row in sales) == pytest.approx(
        SEAPORT_TX_VALUE_WEI / 1e18
    )


# ---------------------------------------------------------------------------
# Medium tier — the real Initialize fixture (2026-08-09 controller capture)
# ---------------------------------------------------------------------------
#
# ``tests/fixtures/surf/manager/v4_initialize_real.json`` is a real
# ``eth_getLogs`` response for a v4 PoolManager ``Initialize`` event
# involving IMD, captured live to settle where the ``hooks`` field sits in
# the payload (data word index 2 — see the file's own ``_meta``). The pool
# it describes is hookless (``hooks == 0x0``); no hooked IMD v4 pool exists
# on chain yet, so the LAUNCHED case below is a synthetic row built by
# flipping only the hooks word of this same real payload, keeping every
# other word (fee, tickSpacing, sqrtPriceX96, tick) exactly as captured.


def _real_v4_initialize_log() -> dict:
    import json
    from pathlib import Path

    path = (
        Path(__file__).resolve().parent.parent
        / "fixtures" / "surf" / "manager" / "v4_initialize_real.json"
    )
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload["logs"][0]


def test_the_real_initialize_log_confirms_hooks_is_data_word_index_2():
    """Ground truth, not an assumption: hooks decodes to the zero address here.

    ``_v4_init_log`` (this file's own synthetic builder, used by every other
    hook test) already places ``hooks`` at word index 2 — this test is what
    justifies that placement against a payload nobody in this plan hand-built.
    """
    from maxpane_dashboard.data.surf_manager import _word_addr

    log = _real_v4_initialize_log()
    hooks = _word_addr(log["data"], 2)
    assert hooks == "0x" + "00" * 20


async def test_a_real_hookless_pool_does_not_launch_the_hook(tmp_path):
    """The one real ``Initialize`` this token has ever emitted: hookless."""
    real_log = _real_v4_initialize_log()
    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - 5_000, to_block=BLOCK, bridge_mints=(),
            identity_updates=(), seaport_sales=(),
            v4_initializes=(real_log,),
        )
    )
    m = _manager(tmp_path, client=client)
    await m.fetch_and_compute()
    assert _hook_launch_status(m) == "NOT LIVE"


async def test_a_hooked_pool_shaped_like_the_real_capture_launches_the_hook(tmp_path):
    """A synthetic hooked row, built by flipping only the real payload's hooks word.

    Every other word — fee, tickSpacing, sqrtPriceX96, tick — stays exactly as
    captured on 2026-08-09; only the hooks word (data index 2) changes. This is
    the "hooked case with the real payload's shape" the task calls for, since no
    hooked IMD v4 pool exists on chain to capture directly.
    """
    real_log = _real_v4_initialize_log()
    raw = real_log["data"]
    prefix = raw[: 2 + 64 * 2]                      # 0x + fee + tickSpacing
    suffix = raw[2 + 64 * 3 :]                       # sqrtPriceX96 + tick
    hooked_data = prefix + _addr_word("0x" + "ab" * 20) + suffix
    hooked_log = dict(real_log, data=hooked_data)

    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - 5_000, to_block=BLOCK, bridge_mints=(),
            identity_updates=(), seaport_sales=(),
            v4_initializes=(hooked_log,),
        ),
        fetch_tx_senders={hooked_log["transactionHash"]: DEV_WALLET},
    )
    m = _manager(tmp_path, client=client)
    await m.fetch_and_compute()
    assert _hook_launch_status(m) == "LAUNCHED"


# ---------------------------------------------------------------------------
# The client's own degradation flags, wired for the first time by this task
# ---------------------------------------------------------------------------
#
# ``SurfClient.channel_truncated`` and ``.log_group_failed`` exist on the real
# client (WP1.5, WP1.9) and ``_client_degradation`` has read them since WP4.7 —
# but nothing called ``fetch_channel_txs``/``fetch_recent_logs`` before this
# task, so the two flags never moved off their "nothing wrong" defaults in any
# manager cycle. These two tests are what proves the wiring, not just the
# reading, is in place: a double that reports truncation/failure the way the
# real client would (an attribute set on the object the manager actually
# calls) must show up in ``degraded``.


async def test_a_truncated_channel_page_reaches_degraded_now_that_it_is_fetched(
    tmp_path,
):
    """WP1.5's page-bound truncation flag, read right after the call this task adds."""
    client = FakeSurfClient()
    client.channel_truncated = True        # as the real client leaves it mid-page
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert SOURCE_CHANNEL in data["degraded"]


def _group_failure(**failed: bool) -> dict[str, bool]:
    """``SurfClient.log_group_failed`` with the named groups reporting failure."""
    flags = dict.fromkeys(
        ("bridge_mints", "identity_updates", "v4_initializes", "seaport_sales"),
        False,
    )
    flags.update(failed)
    return flags


async def test_a_failed_log_group_reaches_degraded_even_on_an_otherwise_ok_window(
    tmp_path,
):
    """The exact failure this product exists to prevent: an empty ``bridge_mints``
    that is a *filter failure*, not "no mints", flagged even though the rest of
    the sweep answered fine and the hook-launch attribution still reads a real
    value.

    This test used to stop at ``degraded`` — which its own docstring promised
    more than. ``degraded`` was the *only* place ``log_group_failed`` reached,
    so the bug it names was fully present with it green, and wiring the flag
    into ``_readings`` would have left it green too: it could not tell the two
    apart. The detector assertion below is the half that bites, because
    ``sig_bridge`` is what a user reads as "nothing is staging".
    """
    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
            bridge_mints=(), identity_updates=(), v4_initializes=(),
            seaport_sales=(),
        )
    )
    client.log_group_failed = _group_failure(bridge_mints=True)
    m = _manager(tmp_path, client=client)
    data = await m.fetch_and_compute()
    assert SOURCE_LOGS in data["degraded"]
    # The rest of the sweep is trustworthy — a per-group failure must not sink
    # a hero value that a different group answered cleanly.
    assert _hook_launch_status(m) == "NOT LIVE"
    # ...and the failed group is unavailable, NOT an affirmative all-clear.
    assert data["sig_bridge_state"] is None
    assert data["sig_bridge_detail"] == "bridge logs unavailable"


async def test_a_bridge_filter_that_dies_after_a_good_window_stops_claiming_all_clear(
    tmp_path,
):
    """``_detect_bridge``'s unavailable branch was unreachable in production.

    ``read["bridge_mints"]`` is ``logs.get("bridge_mints")`` and ``_pool_logs``
    always wrote that key, so it was ``None`` only before the logs group had
    *ever* succeeded. After one success a bridge-filter outage could never
    again produce the unavailable state — it produced ``ok · no mints in
    window``, an affirmative claim about the earliest of the six detectors,
    made out of a read that failed. ``tests/analytics`` pins the ``None``
    branch; nothing pinned that the manager can reach it.
    """
    clock = FakeClock()
    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
            bridge_mints=(), identity_updates=(), v4_initializes=(),
            seaport_sales=(),
        )
    )
    m = _manager(tmp_path, client=client, clock=clock)
    first = await m.fetch_and_compute()
    assert first["sig_bridge_state"] == "ok"          # read, and held nothing
    assert first["sig_bridge_detail"] == "no mints in window"

    client.log_group_failed = _group_failure(bridge_mints=True)
    clock.advance(120.0)                               # the medium tier is due
    second = await m.fetch_and_compute()
    assert second["sig_bridge_state"] is None
    assert second["sig_bridge_detail"] == "bridge logs unavailable"


async def test_a_failed_seaport_filter_serves_last_good_sales_not_an_empty_list(
    tmp_path,
):
    """A partial failure must not destroy the other groups' last-good.

    ``_pool_logs`` replaced ``SLOT_LOGS`` wholesale, so one dead filter wrote
    ``[]`` over rows that were read successfully minutes earlier — and ``[]``
    is this manager's own contract for *genuinely nothing*, which is what the
    NFT panel renders as "no realized sales". CLAUDE.md's rule for a dead
    source is last-good behind an ``as of`` marker, and ``degraded`` already
    carries the marker's other half.
    """
    clock = FakeClock()
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client, clock=clock)
    first = await m.fetch_and_compute()
    assert [row["token_id"] for row in first["nft_last_sales"]] == [1751, 354]

    client._returns["fetch_recent_logs"] = LogWindow(
        from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
        bridge_mints=(), identity_updates=(), v4_initializes=(), seaport_sales=(),
    )
    client.log_group_failed = _group_failure(seaport_sales=True)
    clock.advance(120.0)
    second = await m.fetch_and_compute()

    assert [row["token_id"] for row in second["nft_last_sales"]] == [1751, 354]
    assert SOURCE_LOGS in second["degraded"]


async def test_a_new_mint_is_not_invisible_when_the_endpoint_omits_blocktimestamp(
    tmp_path,
):
    """End to end, through the decoder that produces the ambiguity.

    ``_log_ts`` falls back to the observation clock when the endpoint sends no
    ``blockTimestamp``, so every row of that sweep carries one identical stamp.
    ``_newest``'s ``max`` then returned the FIRST maximal row — the oldest, in
    the ascending order ``eth_getLogs`` serves — which is exactly the row the
    baseline already holds, so a genuinely new mint sitting behind it was
    invisible. It surfaced hours later, when the old row rolled out of the
    window, and fired then: the wrong event at the wrong time on the detector
    the PRD sells as the earliest of the six.

    Every log fixture in this file carries an explicit ``blockTimestamp``; this
    one deliberately does not, because that is where the bug lives.
    """
    clock = FakeClock()
    seen = _mint_log(OPS_WALLET, 10_000 * 10**18, ts=0.0, tx="0x" + "c1" * 32,
                     block=BLOCK, log_index=4, stamped=False)
    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
            bridge_mints=(seen,), identity_updates=(), v4_initializes=(),
            seaport_sales=(),
        )
    )
    m = _manager(tmp_path, client=client, clock=clock)
    first = await m.fetch_and_compute()
    assert first["sig_bridge_state"] == "ok"        # first sweep seeds, never news

    fresh = _mint_log(OPS_WALLET, 25_000 * 10**18, ts=0.0, tx="0x" + "c2" * 32,
                      block=BLOCK + 3, log_index=1, stamped=False)
    client._returns["fetch_recent_logs"] = LogWindow(
        from_block=BLOCK - LOG_WINDOW, to_block=BLOCK + 3,
        bridge_mints=(seen, fresh),                 # ascending, new row last
        identity_updates=(), v4_initializes=(), seaport_sales=(),
    )
    clock.advance(120.0)
    second = await m.fetch_and_compute()

    assert second["sig_bridge_state"] == "fired"
    assert "25,000" in second["sig_bridge_detail"]


async def test_a_failed_identity_filter_is_unavailable_not_zero_writes(tmp_path):
    """``_identity_writes`` guarded a branch its own model cannot reach.

    ``LogWindow.identity_updates`` is ``tuple[dict, ...] = ()`` and can never
    be ``None``, so ``if rows is None: return None  # the filter failed`` was a
    comment describing a protection that was not there: a dead
    ``IdentityHashUpdated`` filter yielded ``0`` and the GATE row rendered
    ``closed · 0 written`` — a count, made up, about a registry nobody read.

    Two cycles, and the first one has to succeed: with a cold slot the failed
    group has no last-good to carry forward and lands on ``None`` anyway, so a
    one-cycle version of this test passes against a manager that never reads
    ``log_group_failed`` at all.
    """
    clock = FakeClock()
    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
            bridge_mints=(), v4_initializes=(), seaport_sales=(),
            identity_updates=(
                _identity_log(1751, ts=NOW - 600.0, tx="0x" + "e1" * 32),
            ),
        )
    )
    m = _manager(tmp_path, client=client, clock=clock)
    first = await m.fetch_and_compute()
    assert "1 written" in first["sig_gate_detail"]

    client._returns["fetch_recent_logs"] = LogWindow(
        from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
        bridge_mints=(), identity_updates=(), v4_initializes=(), seaport_sales=(),
    )
    client.log_group_failed = _group_failure(identity_updates=True)
    clock.advance(120.0)
    second = await m.fetch_and_compute()
    # Neither a stale count presented as live nor a fabricated zero.
    assert "written" not in (second["sig_gate_detail"] or "")
    assert SOURCE_LOGS in second["degraded"]


# ---------------------------------------------------------------------------
# Slow tier — NFT and dev activity
# ---------------------------------------------------------------------------


async def test_nft_stats_reach_the_payload_and_the_floor_stays_none(manager):
    data = await manager.fetch_and_compute()
    assert data["nft_holders"] == NFT_HOLDERS
    assert data["nft_dev_holdings"] == 3
    # One number, one producer: WP1.8's lifetime distinct-id count over the
    # registry's Blockscout log view. Both flat keys read `NftStats.written` —
    # the hero's "x/2000" and the NFT panel's "written" are the same fact, and
    # neither may be back-filled from `len(LogWindow.identity_updates)`, which
    # counts an eight-hour window and would render 0/2000 on a chain whose real
    # answer is 1/2000 (wp1.md open issues 9 and 11).
    assert data["identities_written"] == 1
    assert data["nft_written"] == 1
    # `transfers_24h` is a *rate*; Blockscout serves a lifetime 7,411 and WP1.8
    # answers `None` rather than a lower bound when its page walk cannot reach
    # the 24 h edge. Asserting `is None` here is what stops someone "fixing" it
    # later with the lifetime counter, which is the wrong number closest to hand.
    assert data["nft_transfers_24h"] is None
    # Sales come off the log window, not off the Blockscout counters — decoded
    # from raw `OrderFulfilled` payloads in WP4.9.
    assert [row["token_id"] for row in data["nft_last_sales"]] == [1751, 354]
    assert data["nft_last_sales"][0]["eth"] == pytest.approx(0.18)
    # PRD §4: there is no keyless floor source; it renders an explicit n/a.
    assert data["nft_floor"] is None


async def test_an_unreadable_written_count_is_none_never_zero(tmp_path):
    """``0`` would say "nobody has written an identity". One person has.

    ``None`` is the only honest answer when WP1.8's page walk is truncated or
    Blockscout is down, and WP3.2's hero renders it as a dash rather than as
    ``0/2000`` — which would read as a fact about the collection.
    """
    client = FakeSurfClient(fetch_nft_stats=_nft_stats(written=None))
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["identities_written"] is None
    assert data["nft_written"] is None
    assert data["nft_holders"] == NFT_HOLDERS      # the rest of the group survives


async def test_dev_activity_is_newest_first_and_capped(tmp_path):
    from maxpane_dashboard.data.surf_manager import DEV_ACTIVITY_LIMIT

    rows = [
        _dev_tx(tx_hash=f"0x{i:064x}", ts=float(NOW - i * 60), wallet_label="dev",
                from_addr=DEV_WALLET, to_addr=FWA_SPLITTER, method="claim",
                counterparty=FWA_SPLITTER,
                counterparty_label=KNOWN_LABELS[FWA_SPLITTER.lower()],
                kind="FWA claim", value_wei=10_000_000_000_000_000)
        for i in range(DEV_ACTIVITY_LIMIT + 10)
    ]
    client = FakeSurfClient(fetch_dev_activity=list(reversed(rows)))
    data = await _manager(tmp_path, client=client).fetch_and_compute()

    assert len(data["dev_activity"]) == DEV_ACTIVITY_LIMIT
    stamps = [row["ts"] for row in data["dev_activity"]]
    assert stamps == sorted(stamps, reverse=True)
    assert data["dev_activity"][0] == {
        "ts": float(NOW), "wallet_label": "dev", "kind": "FWA claim",
        "counterparty": KNOWN_LABELS[FWA_SPLITTER.lower()],
        "counterparty_known": True,
        "value_eth": pytest.approx(0.01), "tx_hash": "0x" + "0" * 64,
    }


async def test_the_four_live_poisoning_rows_never_reach_the_feed(tmp_path, caplog):
    """PRD §6.5, against the real thing, one layer late.

    These four 1-gwei sends are in ``captures/ops_eth_txs.json`` today: inbound
    from addresses that share a 6-char prefix and a 4-char suffix with the two
    real LP-fee sinks.  WP1.6 is supposed to have dropped them already; here they
    arrive anyway, labelled ``ops`` with a sender that is not the ops wallet —
    the shape a regression in WP1's filter would produce.  The manager drops them
    and says so, because a truncated render of a lookalike is indistinguishable
    from the real one: the row must not exist rather than be rendered carefully.
    """
    poison = [
        _dev_tx(tx_hash="0x2ad89153afba05142769ad7855c49084bbc185b23e40d77ba46859336d0529ed",
                ts=1_785_903_359.0, wallet_label="ops",
                from_addr="0x61CCFD5d33F0F27a2cd5aCb558d9281b110DF14e",
                to_addr=OPS_WALLET, method=None, value_wei=1_000_000_000),
        _dev_tx(tx_hash="0xe81febd42dc8671210bc65ff6a1604f7c5e44b8fb640e208a0f66183f95a5b73",
                ts=1_785_464_471.0, wallet_label="ops",
                from_addr="0x61CCFD5d33F0F27a2cd5aCb558d9281b110DF14e",
                to_addr=OPS_WALLET, method=None, value_wei=1_000_000_000),
        _dev_tx(tx_hash="0x3f51f2eae061d3b10582fb545952524a1401a23ce6879c56c85cc5803adec605",
                ts=1_780_746_731.0, wallet_label="ops",
                from_addr="0xF30875988B99489ac71EC2F5069DE0dD80B70eE6",
                to_addr=OPS_WALLET, method=None, value_wei=1_000_000_000),
        _dev_tx(tx_hash="0x78dde33315dcd41e262c26d86f75fb3cfaa03f973cc5f20b976da6d50cf743d7",
                ts=1_780_746_503.0, wallet_label="ops",
                from_addr="0xF3083828702C1989710CECA517412071c2f60Ee6",
                to_addr=OPS_WALLET, method=None, value_wei=1_000_000_000),
    ]
    real = _dev_tx()                       # the 2026-08-07 LP add, outbound
    client = FakeSurfClient(fetch_dev_activity=[*poison, real])
    with caplog.at_level("WARNING"):
        data = await _manager(tmp_path, client=client).fetch_and_compute()

    assert [row["tx_hash"] for row in data["dev_activity"]] == [real.tx_hash]
    # Loud, not silent: if this ever fires in production it is a WP1 regression.
    assert caplog.text.count("is not the ops wallet") == 4
    # And the spoof senders are not in the allowlist, which is why no layer of
    # this can ever hand one of them a label.
    for row in poison:
        assert row.from_addr.lower() not in KNOWN_LABELS


async def test_an_unknown_counterparty_is_never_marked_known(tmp_path):
    """0x61CC704c… is a real, unlabelled LP-fee destination — dimmed, not trusted.

    ``counterparty_known`` is the one value this layer derives, and it derives it
    from the *absence* of a label rather than from any property of the address:
    an allowlist miss is the only thing that can produce it.
    """
    unknown = "0x61CC704c7A5B7071c7B3f4Cc09A9CBC86373f14E"
    client = FakeSurfClient(
        fetch_dev_activity=[
            _dev_tx(from_addr=OPS_WALLET, to_addr=unknown, counterparty=unknown,
                    counterparty_label=None, kind="transfer", method=None,
                    value_wei=300_000_000_000_000_000)
        ]
    )
    row = (await _manager(tmp_path, client=client).fetch_and_compute())["dev_activity"][0]
    assert row["counterparty_known"] is False
    assert row["counterparty"] == unknown       # the raw address, for the dim render
    assert row["value_eth"] == pytest.approx(0.3)


async def test_the_slow_tier_is_skipped_while_fresh(tmp_path):
    clock = FakeClock()
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client, clock=clock)

    await m.fetch_and_compute()
    clock.advance(120.0)                         # medium due, slow not
    await m.fetch_and_compute()
    assert client.calls.count("fetch_nft_stats") == 1
    assert client.calls.count("fetch_market") == 2

    clock.advance(400.0)
    await m.fetch_and_compute()
    assert client.calls.count("fetch_nft_stats") == 2


async def test_a_dev_nonce_bump_pulls_the_tx_page_inside_the_slow_window(tmp_path):
    """PRD §3 #4: 'both dev nonces every refresh; Blockscout tx page **on change**'.

    Waiting for the 420 s tier would surface a contract creation up to seven
    minutes late.  The NFT counters, which nothing detects on, stay on the tier.
    """
    clock = FakeClock()
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client, clock=clock)

    await m.fetch_and_compute()
    assert client.calls.count("fetch_dev_activity") == 1

    clock.advance(30.0)                          # one poll; slow tier not due
    await m.fetch_and_compute()
    assert client.calls.count("fetch_dev_activity") == 1   # nothing moved: skipped

    client._returns["fetch_nonces"] = NonceSet(
        announce=ANNOUNCE_NONCE, dev=DEV_NONCE + 1, ops=OPS_NONCE, block_number=BLOCK
    )
    clock.advance(30.0)
    await m.fetch_and_compute()
    assert client.calls.count("fetch_dev_activity") == 2   # exactly one extra
    assert client.calls.count("fetch_nft_stats") == 1      # still tier-gated

    clock.advance(30.0)                          # same nonce again: no third call
    await m.fetch_and_compute()
    assert client.calls.count("fetch_dev_activity") == 2


async def test_an_nft_outage_leaves_the_rest_of_the_screen_alone(tmp_path):
    """A dead source hands back ``None``, and specifically not ``[]``.

    WP3 froze the pair of meanings and its widgets branch on them: ``[]``
    renders "no recent activity" with the unavailable banner deliberately
    *absent*. Publishing ``[]`` for a Blockscout outage would make the screen
    assert the dev wallets were quiet — a dead source presented as a fact, which
    is the one thing CLAUDE.md's degradation rule forbids.
    """
    client = FakeSurfClient(fetch_nft_stats=None, fetch_dev_activity=None)
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert SOURCE_NFT in data["degraded"]
    assert SOURCE_ACTIVITY in data["degraded"]
    assert SOURCE_MARKET not in data["degraded"]
    assert data["nft_holders"] is None
    assert data["dev_activity"] is None
    assert data["imd_price_usd"] == pytest.approx(IMD_PRICE_USD)


async def test_a_read_but_empty_page_is_an_empty_list_not_none(tmp_path):
    """The other half of the same contract — and the reason it is not free.

    ``fetch_dev_activity`` answering ``[]`` is data: the pages were read and
    held nothing. That must reach the widget as ``[]`` so it renders "no recent
    activity" rather than the outage banner, and it must reach WP2 as ``[]`` so
    the deploy baseline can seed (see
    ``test_the_first_deploy_after_an_empty_page_still_fires``).
    """
    client = FakeSurfClient(fetch_dev_activity=[], fetch_channel_txs=[])
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["dev_activity"] == []
    assert data["feed_items"] == []
    assert SOURCE_ACTIVITY not in data["degraded"]


# All six groups exist now, so a healthy cycle can finally assert the full shape.


async def test_a_healthy_cycle_reports_nothing_degraded(manager):
    data = await manager.fetch_and_compute()
    # `launchpad` is the one group that can never be healthy on a single cold
    # cycle: its sweep is detached (Task 6) and cannot land inside the cycle
    # that spawned it, so a brand-new cache always shows it here alongside
    # whatever else genuinely failed -- nothing failed here, so it is alone.
    assert data["degraded"] == [SOURCE_LAUNCHPAD]
    assert data["as_of"] == pytest.approx(NOW)
    # This cycle's sample is already in the sparkline, not one refresh behind.
    assert data["supply_series"] == [[1_786_190_400.0, pytest.approx(IMD_SUPPLY)]]
    assert data["price_series"] == [[1_786_190_400.0, pytest.approx(IMD_PRICE_USD)]]


async def test_a_chain_outage_degrades_only_the_chain_group(tmp_path):
    """...of the five groups a single cold cycle can actually finish reading.
    ``launchpad`` rides along here too, but for an unrelated reason (Task 6:
    its detached sweep never lands inside the cycle that spawned it) — see
    ``test_a_healthy_cycle_reports_nothing_degraded`` for that one in isolation.
    """
    client = FakeSurfClient(fetch_nonces=None, fetch_chain_state=None)
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["degraded"] == [SOURCE_CHAIN, SOURCE_LAUNCHPAD]
    assert data["imd_price_usd"] == pytest.approx(IMD_PRICE_USD)
    assert data["nft_holders"] == NFT_HOLDERS
    assert data["imd_supply"] is None


# ---------------------------------------------------------------------------
# Signals — driven through the real analytics/surf_signals.py, not a double
# ---------------------------------------------------------------------------

# Both come from WP2, and `SIGNAL_NAMES` deliberately does **not** come from
# the manager: WP2 derives it from `_DETECTORS`, so importing it from there is
# what makes this suite assert against the real registry instead of against the
# manager's own copy of it. A local copy in `data/` would keep `_signal_keys`
# reading WP0's spellings out of a dict keyed by WP2's — eighteen `sig_*` keys
# silently `None`, and `test_every_signal_contributes_three_keys` comparing the
# manager against itself and passing.
from maxpane_dashboard.analytics.surf_signals import (   # noqa: E402
    FIRED_TTL_S,
    SIGNAL_NAMES,
)


async def test_every_signal_contributes_three_keys(manager):
    data = await manager.fetch_and_compute()
    for name in SIGNAL_NAMES:
        assert f"sig_{name}_state" in data
        assert f"sig_{name}_detail" in data
        assert f"sig_{name}_age_s" in data
    assert data["sig_post_state"] in ("ok", "watch", "fired", None)


async def test_a_new_post_fires_within_one_cycle(tmp_path):
    clock = FakeClock()
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client, clock=clock)

    first = await m.fetch_and_compute()
    assert first["sig_post_state"] != "fired"     # the first read only baselines

    client._returns["fetch_nonces"] = NonceSet(
        announce=ANNOUNCE_NONCE + 1, dev=DEV_NONCE, ops=OPS_NONCE
    )
    clock.advance(30.0)
    # The page that nonce belongs to, carrying the post that just landed. The
    # FIRED age asserted below is `now - announce_last_ts`, so handing back the
    # unchanged `_channel_txs()` page here would date brand-new news to the
    # *previous* post — 600 s old in this fixture — and the assertion would be
    # pinning the wrong fact while still saying "fired".
    client._returns["fetch_channel_txs"] = _posted_channel_txs(clock.t)
    second = await m.fetch_and_compute()
    assert second["sig_post_state"] == "fired"
    assert second["sig_post_age_s"] == pytest.approx(0.0, abs=1.0)

    # Baselines advance immediately, so the *same* post never re-fires...
    clock.advance(30.0)
    third = await m.fetch_and_compute()
    assert third["sig_post_state"] == "fired"     # ...but the display persists 24 h
    assert third["sig_post_age_s"] == pytest.approx(30.0, abs=1.0)


async def test_a_fired_display_relaxes_after_its_ttl(tmp_path):
    clock = FakeClock()
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client, clock=clock)
    await m.fetch_and_compute()
    client._returns["fetch_nonces"] = NonceSet(
        announce=ANNOUNCE_NONCE + 1, dev=DEV_NONCE, ops=OPS_NONCE
    )
    clock.advance(30.0)
    # Dated to the fire moment, so the advance below is exactly one TTL past the
    # event rather than one TTL past the event plus the fixture post's own age.
    client._returns["fetch_channel_txs"] = _posted_channel_txs(clock.t)
    await m.fetch_and_compute()

    clock.advance(FIRED_TTL_S + 60.0)
    relaxed = await m.fetch_and_compute()
    assert relaxed["sig_post_state"] == "ok"
    assert "last" in (relaxed["sig_post_detail"] or "")


async def test_a_restart_neither_resurrects_nor_loses_a_fired_signal(tmp_path):
    clock = FakeClock()
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client, clock=clock)
    await m.fetch_and_compute()
    client._returns["fetch_nonces"] = NonceSet(
        announce=ANNOUNCE_NONCE + 1, dev=DEV_NONCE, ops=OPS_NONCE
    )
    clock.advance(30.0)
    # The post that fires is the one dated *now*, so the age below is the two
    # hours the process was down and nothing else.
    client._returns["fetch_channel_txs"] = _posted_channel_txs(clock.t)
    await m.fetch_and_compute()
    fire_ts = clock.t                      # the exact instant the post fired
    await m.close()

    clock.advance(7_200.0)                 # two hours later, fresh process
    restarted = _manager(tmp_path, client=FakeSurfClient(
        fetch_nonces=NonceSet(announce=ANNOUNCE_NONCE + 1, dev=DEV_NONCE, ops=OPS_NONCE)
    ), clock=clock)
    data = await restarted.fetch_and_compute()

    assert data["sig_post_state"] == "fired"                     # not lost
    assert data["sig_post_age_s"] == pytest.approx(7_200.0, abs=2.0)   # real age
    # The nonce baseline came back too, so the same post did not fire again.
    assert restarted.cache.get_baselines()["announce_nonce"] == ANNOUNCE_NONCE + 1

    # The LITERAL "fired" key, never the imported `BASELINE_FIRED_KEY` constant.
    # A reviewer proved a real coverage gap here: `SurfCache._sanitise_baselines`
    # (write side) and `SurfCache.get_baselines` (read side) both key off that
    # one symbol, so a spelling regression that renames it moves both sides
    # together and no test would ever notice — monkey-patching the constant to
    # "fired_at" and then calling with the literal "fired" silently dropped the
    # whole FIRED store while every existing cache test stayed green. Pinning
    # the literal here, at the manager/cache seam and through a real
    # `build_signals` round trip, is what closes that gap.
    fired = restarted.cache.get_baselines()["fired"]
    assert fired["post"]["ts"] == pytest.approx(fire_ts)
    assert fired["post"]["detail"]


async def test_baselines_are_stored_back_every_cycle(tmp_path):
    m = _manager(tmp_path)
    await m.fetch_and_compute()
    baselines = m.cache.get_baselines()
    assert baselines["announce_nonce"] == ANNOUNCE_NONCE
    assert baselines["imd_supply"] == pytest.approx(IMD_SUPPLY)
    assert baselines["gate_open"] is False


def test_the_readings_dict_is_exactly_wp2s_contract(tmp_path):
    """A misspelled reading key is an invisible outage, not a failure.

    ``build_signals`` treats *absent* and *``None``* identically, so spelling
    ``identity_writes`` where WP2 froze ``identities_written`` raises nothing,
    logs nothing and reddens nothing — it just turns the GATE detail off for
    good. This assertion is the only thing in either package that catches it,
    which is why it compares against the imported tuple and never a literal.
    """
    m = _manager(tmp_path)
    readings = m._readings({}, None, {}, [])
    assert set(readings) == set(surf_signals.READING_KEYS) | LAUNCHPAD_READING_KEYS
    # Cold cache, nothing read: nothing may claim it was. No 0, no [], no False.
    assert set(readings.values()) == {None}


async def test_a_read_but_empty_window_is_data_not_an_outage(manager):
    """``[]`` and ``None`` are opposite claims — only ``[]`` can reach ``ok``."""
    data = await manager.fetch_and_compute()
    channel = manager.cache.get_last_good(SLOT_CHANNEL).payload
    readings = manager._readings(
        data,
        NonceSet(announce=ANNOUNCE_NONCE, dev=DEV_NONCE, ops=OPS_NONCE),
        channel,
        data["dev_activity"],
    )
    assert readings["bridge_mints"] == []       # the window was read; it was empty
    assert readings["v4_hook_pools"] == []
    assert readings["burn_transfers"] == []     # the pages held no BurnExecutor call
    assert data["sig_bridge_state"] == "ok"     # reachable only through that []

    # The ops LP row is not a deploy — but the channel's ERC-8004 register()
    # call is an `action`, the second shape PRD §3 #4 names.
    assert [e["kind"] for e in readings["deploy_events"]] == ["action"]
    assert readings["deploy_events"][0]["tx_hash"] == "0x" + "a2" * 32
    assert readings["deploy_events"][0]["wallet_label"] == "announce"

    # The channel page count, not the feed render cap, and the newest self-post.
    assert readings["channel_tx_count"] == 4
    assert readings["announce_last_text"] == "soon"
    assert readings["announce_last_ts"] == pytest.approx(SOON_TS)


async def test_a_channel_action_never_claims_the_tx_pages_were_read(tmp_path):
    """`[]` is a claim about a source, and one source may not make it for another.

    `deploy_events` merges two streams that fail independently: the dev tx
    pages and the announce channel page. If the channel answers while the tx
    pages are down, an unguarded merge turns `None` ("we have no pages") into
    `[]` ("we read the pages and there were no deploys") — and `[]` seeds WP2's
    `deploy_tx`/`deploy_ts`. The first real deploy would then be measured
    against a baseline the tx-page source never contributed to.
    """
    client = FakeSurfClient(fetch_dev_activity=None)      # tx pages dead
    m = _manager(tmp_path, client=client)
    data = await m.fetch_and_compute()
    channel = m.cache.get_last_good(SLOT_CHANNEL).payload
    readings = m._readings(data, None, channel, data["dev_activity"])

    assert channel["items"], "the channel page itself was read fine"
    assert readings["deploy_events"] is None
    assert SOURCE_ACTIVITY in data["degraded"]


async def test_an_older_deploy_and_a_newer_action_both_reach_the_detector(tmp_path):
    """Both streams are carried, newest first — and one of them is not reported.

    A contract creation at T+0 on the slow tier and a channel `action` at
    T+100 on the medium tier are two different events on two cadences. WP4
    hands both to WP2 in one list, ordered, so nothing is dropped on the way.

    **Known limitation, Open issue 12:** WP2's `_fresh_event` reports only the
    *newest* row of a stream and refuses anything with `ts <= base["deploy_ts"]`,
    which is right for one chronological stream and wrong for two. So the row
    below is carried but never reported, and the fix is to split
    `deploy_events` into two `READING_KEYS` entries with their own baseline
    pairs — a WP2 contract change, raised with that file's owner rather than
    worked around here. This test pins what WP4 can guarantee today and goes
    green the moment WP2 splits the key.
    """
    clock = FakeClock()
    client = FakeSurfClient(fetch_dev_activity=[], fetch_channel_txs=[])
    m = _manager(tmp_path, client=client, clock=clock)
    await m.fetch_and_compute()

    client._returns["fetch_dev_activity"] = [
        _dev_tx(tx_hash="0x" + "d2" * 32, ts=NOW, wallet_label="dev",
                from_addr=DEV_WALLET, to_addr=None, method=None, value_wei=0,
                counterparty="0x" + "ce" * 20, counterparty_label=None,
                kind="deploy", created_contract="0x" + "ce" * 20),
    ]
    client._returns["fetch_channel_txs"] = [
        ChannelTx(tx_hash="0x" + "a2" * 32, ts=NOW + 100.0, nonce=4,
                  from_addr=ANNOUNCE, to_addr=ERC8004, value_wei=0,
                  input_hex=REGISTER_HEX, method="register"),
    ]
    client._returns["fetch_nonces"] = NonceSet(
        announce=ANNOUNCE_NONCE + 1, dev=DEV_NONCE + 1, ops=OPS_NONCE,
        block_number=BLOCK,
    )
    clock.advance(30.0)
    data = await m.fetch_and_compute()
    channel = m.cache.get_last_good(SLOT_CHANNEL).payload
    readings = m._readings(data, client._returns["fetch_nonces"], channel,
                           data["dev_activity"])

    assert [e["kind"] for e in readings["deploy_events"]] == ["action", "deploy"]
    assert readings["deploy_events"][1]["tx_hash"] == "0x" + "d2" * 32
    assert data["sig_deploy_state"] == "fired"


async def test_the_gate_detail_reads_the_window_and_the_hero_reads_the_lifetime(tmp_path):
    """Two counts, one name, and only one of them is the hero's (wp1.md #9).

    `NftStats.written` is a **lifetime** count over the registry's whole log
    history — 1 of 2000, written 2026-05-14, months outside any `eth_getLogs`
    window this app opens. WP2's `identities_written` *reading* is the other
    one: distinct ids seen in the recent window, which PRD §3 #3 makes signal
    3's detail line. Cross them and both break silently — the hero renders
    `0/2000` on a chain whose real answer is `1/2000`, and `_detect_gate`'s
    `written > base_written` WATCH branch becomes unreachable.
    """
    client = FakeSurfClient(
        fetch_nft_stats=_nft_stats(written=1),
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
            bridge_mints=(), v4_initializes=(), seaport_sales=(),
            identity_updates=(
                _identity_log(1751, ts=NOW - 600.0, tx="0x" + "e1" * 32),
                # Same id, replaced hash: one identity written, two logs.
                _identity_log(1751, ts=NOW - 300.0, tx="0x" + "e2" * 32),
                _identity_log(354, ts=NOW - 120.0, tx="0x" + "e3" * 32),
            ),
        ),
    )
    m = _manager(tmp_path, client=client)
    data = await m.fetch_and_compute()
    readings = m._readings(data, None, {}, data["dev_activity"])

    assert data["identities_written"] == 1      # lifetime, NftStats.written
    assert data["nft_written"] == 1
    assert readings["identities_written"] == 2  # distinct ids in the window
    assert "2 written" in (data["sig_gate_detail"] or "")


async def test_a_stale_page_never_quotes_an_old_body_under_a_new_nonce(tmp_path):
    """Blockscout down while the RPC is up: the nonce moved, the page did not.

    ``_pool_channel`` fetches the bodies on the same cycle the nonce moves, so the
    pair is normally matched — but the two live on different hosts and the page
    read is the one that fails. Without this guard the FIRED row for the brand-new
    post carries the *previous* post's text and timestamp, and across the real
    52-day May-to-July silence that timestamp is older than ``FIRED_TTL_S``: the
    news would render as relaxed history and the quote would be the wrong post.
    """
    clock = FakeClock()
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client, clock=clock)
    await m.fetch_and_compute()

    client._returns["fetch_nonces"] = NonceSet(
        announce=ANNOUNCE_NONCE + 1, dev=DEV_NONCE, ops=OPS_NONCE
    )
    client._returns["fetch_channel_txs"] = None      # the page read fails
    clock.advance(30.0)
    data = await m.fetch_and_compute()

    channel = m.cache.get_last_good(SLOT_CHANNEL).payload   # still the old page
    readings = m._readings(
        data, client._returns["fetch_nonces"], channel, data["dev_activity"]
    )
    assert readings["announce_nonce"] == ANNOUNCE_NONCE + 1
    assert readings["announce_last_text"] is None     # not the previous body
    assert readings["announce_last_ts"] is None
    assert SOURCE_CHANNEL in data["degraded"]
    # The nonce alone still fires it, and dates it to now rather than to May.
    assert data["sig_post_state"] == "fired"
    assert data["sig_post_age_s"] == pytest.approx(0.0, abs=1.0)


async def test_a_contract_creation_reaches_the_deploy_detector(tmp_path):
    """The row shape NEW DEPLOY exists for (PRD §3 #4), end to end.

    ``_activity_rows`` must flatten a ``created_contract`` tx as
    ``kind == "deploy"``: WP2 selects deploy rows *by kind*, so a row flattened
    under any other spelling is a deploy the panel never reports — silently, with
    every other test still green. This is the assertion that pins the vocabulary
    the two tasks share.
    """
    client = FakeSurfClient(fetch_dev_activity=[
        _dev_tx(tx_hash="0x" + "cc" * 32, ts=NOW - 60.0, wallet_label="dev",
                from_addr=DEV_WALLET, to_addr=None, value_wei=0, method=None,
                counterparty="0x" + "de" * 20, counterparty_label=None,
                kind="deploy", created_contract="0x" + "de" * 20),
    ])
    m = _manager(tmp_path, client=client)
    data = await m.fetch_and_compute()
    readings = m._readings(data, None, {}, data["dev_activity"])

    assert [row["tx_hash"] for row in readings["deploy_events"]] == ["0x" + "cc" * 32]
    assert readings["deploy_events"][0]["kind"] == "deploy"
    # The label is the flattened row's counterparty — the created contract for a
    # deploy. Asserted against the row rather than against a literal, so this test
    # pins the *hand-off* between the two tasks and not WP4.10's labelling rule.
    assert (
        readings["deploy_events"][0]["label"] == data["dev_activity"][0]["counterparty"]
    )
    assert "de" in readings["deploy_events"][0]["label"]   # the contract, not ""


async def test_the_first_deploy_after_an_empty_page_still_fires(tmp_path):
    """A successful-but-empty read must seed the baseline, or event #1 is lost.

    ``[]`` seeds ``deploy_tx``/``deploy_ts`` and ``None`` does not (WP2's
    ``_advance``), so encoding "read the pages, found no deploys" as ``None``
    costs exactly one event: the first one ever — which on a fresh install is
    the one the user installed this for. It is a *silent* loss:
    ``_fresh_event`` returns ``None`` against an unseeded baseline while
    ``_advance`` records the row, so the next deploy fires and nobody notices
    the first never did.
    """
    clock = FakeClock()
    client = FakeSurfClient(fetch_dev_activity=[], fetch_channel_txs=[])
    m = _manager(tmp_path, client=client, clock=clock)

    first = await m.fetch_and_compute()
    assert first["sig_deploy_state"] == "ok"          # read, empty, baseline seeded
    assert m.cache.get_baselines()["deploy_tx"] == ""

    client._returns["fetch_dev_activity"] = [
        _dev_tx(tx_hash="0x" + "d1" * 32, ts=NOW + 100.0, wallet_label="dev",
                from_addr=DEV_WALLET, to_addr=None, method=None, value_wei=0,
                counterparty="0x" + "cd" * 20, counterparty_label=None,
                kind="deploy", created_contract="0x" + "cd" * 20),
    ]
    client._returns["fetch_nonces"] = NonceSet(
        announce=ANNOUNCE_NONCE, dev=DEV_NONCE + 1, ops=OPS_NONCE, block_number=BLOCK
    )
    clock.advance(30.0)
    second = await m.fetch_and_compute()

    assert second["sig_deploy_state"] == "fired"
    assert "new contract" in (second["sig_deploy_detail"] or "")


async def test_an_announce_channel_action_fires_new_deploy(tmp_path):
    """The ERC-8004 registration shape — PRD §3 #4's own worked example.

    It lands on the **channel** page, never on a dev-wallet tx page: the announce
    EOA is not one of the two wallets ``fetch_dev_activity`` pages. A
    ``deploy_events`` list built only from activity rows can therefore never see
    it, and NEW DEPLOY would sit at ``ok`` through the exact event it was
    specified for.
    """
    clock = FakeClock()
    client = FakeSurfClient(fetch_channel_txs=[], fetch_dev_activity=[])
    m = _manager(tmp_path, client=client, clock=clock)
    await m.fetch_and_compute()

    client._returns["fetch_channel_txs"] = [
        ChannelTx(tx_hash="0x" + "a2" * 32, ts=NOW + 60.0, nonce=4,
                  from_addr=ANNOUNCE, to_addr=ERC8004, value_wei=0,
                  input_hex=REGISTER_HEX, method="register"),
    ]
    client._returns["fetch_nonces"] = NonceSet(
        announce=ANNOUNCE_NONCE + 1, dev=DEV_NONCE, ops=OPS_NONCE, block_number=BLOCK
    )
    clock.advance(30.0)
    data = await m.fetch_and_compute()

    assert data["sig_deploy_state"] == "fired"
    assert "action register()" in (data["sig_deploy_detail"] or "")
    assert "announce" in (data["sig_deploy_detail"] or "")


async def test_a_burn_executor_call_is_the_burn_precursor(tmp_path):
    """PRD §3 #6's "BurnExecutor tx seen" half, from the dev tx page.

    ``bridgeToBaseBurnReceiver`` to ``0x2EC59BEd…`` is a real, keyless row (three
    of them in the captures, 2026-07-31 and 2026-08-05). The IMD amount is *not*
    on that page — the ETH value is the OFT fee, 3.05e-5 ETH — so the row carries
    ``amount: None`` rather than a number wrong by nine orders of magnitude.
    """
    clock = FakeClock()
    client = FakeSurfClient(fetch_dev_activity=[], fetch_channel_txs=[])
    m = _manager(tmp_path, client=client, clock=clock)
    await m.fetch_and_compute()

    client._returns["fetch_dev_activity"] = [
        _dev_tx(tx_hash="0xcfb8f6e2c733742615519cfc5596a6524daabb1efe0e628ee10da5b00f24964c",
                ts=NOW + 60.0, wallet_label="dev", from_addr=DEV_WALLET,
                to_addr=BURN_EXECUTOR_V1, method="bridgeToBaseBurnReceiver",
                counterparty=BURN_EXECUTOR_V1,
                counterparty_label=KNOWN_LABELS[BURN_EXECUTOR_V1.lower()],
                kind="burn", value_wei=30_466_501_051_555),
    ]
    client._returns["fetch_nonces"] = NonceSet(
        announce=ANNOUNCE_NONCE, dev=DEV_NONCE + 1, ops=OPS_NONCE, block_number=BLOCK
    )
    clock.advance(30.0)
    data = await m.fetch_and_compute()

    assert data["dev_activity"][0]["kind"] == "burn"
    assert data["sig_burn_state"] == "watch"        # supply flat, executor called
    assert "BurnExecutor" in (data["sig_burn_detail"] or "")


async def test_the_post_body_lands_in_the_same_cycle_the_signal_fires(tmp_path):
    """PRD §11.1 end to end: FIRED *and* the decoded text, one refresh interval.

    The bug this pins is the tier gate: with the medium-tier check ahead of the
    nonce check, the signal fired on the fast tier and the body arrived up to
    three refreshes later, so the FIRED row quoted nothing and the feed still
    showed the previous post.
    """
    clock = FakeClock()
    client = FakeSurfClient(fetch_channel_txs=[])
    m = _manager(tmp_path, client=client, clock=clock)
    first = await m.fetch_and_compute()
    assert first["feed_items"] == []

    client._returns["fetch_nonces"] = NonceSet(
        announce=ANNOUNCE_NONCE + 1, dev=DEV_NONCE, ops=OPS_NONCE, block_number=BLOCK
    )
    client._returns["fetch_channel_txs"] = _channel_txs()
    clock.advance(30.0)                      # ONE poll interval; medium not due
    second = await m.fetch_and_compute()

    assert second["sig_post_state"] == "fired"
    assert len(second["feed_items"]) == 4
    assert '"soon"' in (second["sig_post_detail"] or "")


# ---------------------------------------------------------------------------
# Full outage — PRD §11.3
# ---------------------------------------------------------------------------


def _dead_client() -> FakeSurfClient:
    """Every source returns ``None``: total, honest outage."""
    return FakeSurfClient(
        fetch_nonces=None, fetch_chain_state=None, fetch_channel_txs=None,
        fetch_dev_activity=None, fetch_market=None, fetch_recent_logs=None,
        fetch_nft_stats=None, fetch_pool_v4=None, fetch_launchpad=None,
        fetch_decoy_pool_count=None,
    )


async def test_a_total_outage_returns_the_full_key_set_with_nothing_invented(tmp_path):
    data = await _manager(tmp_path, client=_dead_client()).fetch_and_compute()

    assert set(data) == set(SURF_KEYS)
    assert data["degraded"] == sorted(SOURCES)
    for key in (
        "eth_usd", "imd_price_usd", "imd_change_24h_pct", "imd_vol_24h_usd",
        "pool_liquidity_usd", "fp_price_usd", "parity_pct", "imd_supply",
        "lp_liquidity", "lp_imd", "lp_weth", "lp_owner_ok", "gate_open",
        "identities_written", "imd_burned_cum", "feed_nonce",
        "feed_last_post_age_s", "nft_holders", "nft_transfers_24h",
        "nft_dev_holdings", "nft_written", "nft_floor", "as_of",
        # The three source-backed lists are `None` too, and that is the whole
        # point of WP3's contract: `[]` would render "no posts in window" / "no
        # recent activity" / "no sales in window" — three confident statements
        # about a chain nobody could reach. WP6's `DeadSourcesManager` builds
        # `{key: None for key in SURF_KEYS}`, so it is an accurate double of
        # exactly this payload.
        "feed_items", "dev_activity", "nft_last_sales",
    ):
        assert data[key] is None, f"{key} should be None under a total outage"
    # The two series are this cache's own history, not a source's answer, so an
    # empty one is a fact about the install rather than about the network.
    for key in ("supply_series", "price_series"):
        assert data[key] == []


async def test_no_signal_fires_and_no_baseline_moves_under_a_total_outage(tmp_path):
    """Test-isolation fix (Task 6, post-Task-7): cycle 1 *spawns* the
    detached launchpad sweep but cannot see its own result -- Task 6's whole
    point is that the sweep can never land inside the cycle that started it.
    A ``before`` snapshot taken right after cycle 1 is therefore taken
    mid-flight: the sweep lands afterwards, in the background, and only the
    *next* cycle's ``_readings()`` actually reads it and lets ``_advance()``
    fold a scalar like ``burn_ready`` into the baselines. Comparing that
    snapshot against a later cycle's baselines was comparing across "an
    outage plus a sweep landing", not across an outage -- ``burn_ready`` was
    the first baseline scalar whose source (Task 7) survives an outage, so
    it is the first to expose the gap.

    The fix is to let the sweep settle *and* let one more healthy cycle fold
    it into the baselines before the snapshot is taken -- explicitly
    awaiting the task, never a sleep, so this stays exactly as deterministic
    as every other test in this suite.
    """
    clock = FakeClock()
    m = _manager(tmp_path, client=FakeSurfClient(), clock=clock)
    await m.fetch_and_compute()                      # cycle 1: spawns the sweep
    if m._launchpad_task is not None:
        await asyncio.wait_for(m._launchpad_task, timeout=2.0)  # let it land
    await m.fetch_and_compute()                      # cycle 2: folds it into baselines
    before = m.cache.get_baselines()                 # now a genuine "established" snapshot

    m.client = _dead_client()
    clock.advance(120.0)
    data = await m.fetch_and_compute()

    assert m.cache.get_baselines() == before
    for name in SIGNAL_NAMES:
        assert data[f"sig_{name}_state"] != "fired"


async def test_an_outage_never_writes_a_sentinel_into_a_series(tmp_path):
    clock = FakeClock()
    m = _manager(tmp_path, client=FakeSurfClient(), clock=clock)
    await m.fetch_and_compute()
    healthy_supply = m.cache.get_series(SERIES_IMD_SUPPLY)
    healthy_price = m.cache.get_series(SERIES_IMD_PRICE_USD)

    m.client = _dead_client()
    clock.advance(7_200.0)                            # two fresh hour buckets
    await m.fetch_and_compute()
    clock.advance(3_600.0)
    await m.fetch_and_compute()

    assert m.cache.get_series(SERIES_IMD_SUPPLY) == healthy_supply
    assert m.cache.get_series(SERIES_IMD_PRICE_USD) == healthy_price


async def test_an_outage_can_never_produce_a_burn(tmp_path):
    """The false-BURN regression named in PRD §6.1."""
    clock = FakeClock()
    m = _manager(tmp_path, client=FakeSurfClient(), clock=clock)
    await m.fetch_and_compute()

    m.client = _dead_client()
    clock.advance(120.0)
    data = await m.fetch_and_compute()

    assert data["sig_burn_state"] != "fired"
    # A good read happened before the outage, so the observation window is
    # open and the honest answer is 0.0 -- unlike the cold start in
    # ``test_a_total_outage_returns_the_full_key_set_with_nothing_invented``,
    # where the same key must be ``None``. The outage moves it neither way.
    assert data["imd_burned_cum"] == 0.0
    assert m.cache.last_supply == pytest.approx(IMD_SUPPLY)


async def test_an_outage_after_a_good_read_serves_last_good_behind_an_as_of(tmp_path):
    clock = FakeClock()
    m = _manager(tmp_path, client=FakeSurfClient(), clock=clock)
    await m.fetch_and_compute()
    good_at = clock.t

    m.client = _dead_client()
    clock.advance(600.0)
    data = await m.fetch_and_compute()

    # The feed keeps rendering, but the header can say how old it is.
    assert len(data["feed_items"]) == 4
    assert data["as_of"] == pytest.approx(good_at)
    assert m.cache.age_of(SLOT_CHANNEL) == pytest.approx(600.0)
    assert SOURCE_CHANNEL in data["degraded"]


async def test_a_recovered_group_stops_being_degraded(tmp_path):
    clock = FakeClock()
    client = FakeSurfClient(fetch_market=None)
    m = _manager(tmp_path, client=client, clock=clock)
    first = await m.fetch_and_compute()
    assert SOURCE_MARKET in first["degraded"]

    client._returns["fetch_market"] = _market()
    clock.advance(120.0)
    second = await m.fetch_and_compute()
    assert SOURCE_MARKET not in second["degraded"]


async def test_no_exception_escapes_when_every_call_raises(tmp_path):
    boom = FakeSurfClient(
        fetch_nonces=RuntimeError("dns"), fetch_chain_state=RuntimeError("dns"),
        fetch_channel_txs=RuntimeError("dns"), fetch_dev_activity=RuntimeError("dns"),
        fetch_market=RuntimeError("dns"), fetch_recent_logs=RuntimeError("dns"),
        fetch_nft_stats=RuntimeError("dns"), fetch_pool_v4=RuntimeError("dns"),
        fetch_launchpad=RuntimeError("dns"), fetch_decoy_pool_count=RuntimeError("dns"),
    )
    data = await _manager(tmp_path, client=boom).fetch_and_compute()
    assert set(data) == set(SURF_KEYS)
    assert data["degraded"] == sorted(SOURCES)


async def test_the_manager_never_reaches_the_network_in_these_tests(manager):
    """Structural, per CLAUDE.md: the injected transport raises on any use."""
    await manager.fetch_and_compute()
    with pytest.raises(AssertionError):
        await manager.client.http.post("https://ethereum-rpc.publicnode.com")


# ---------------------------------------------------------------------------
# Review findings folded into WP4.12 (not in the brief; see the task report)
# ---------------------------------------------------------------------------


async def test_a_wholly_none_chain_state_degrades_the_chain_group(tmp_path):
    """A ``fetch_chain_state()`` that succeeds structurally (hands back a
    ``ChainState``, not ``None``) while every sub-field reads back ``None`` is a
    client-side partial-batch failure, not a healthy read. Left unguarded,
    ``ok`` stayed ``True`` in ``_pool_chain`` because it only checked
    ``state_res is not None`` — so six hero keys rendered dashes with no
    ``degraded`` entry to explain them, exactly the "screen full of dashes,
    nothing invented" gap this task exists to close.
    """
    client = FakeSurfClient(
        fetch_chain_state=_chain_state(
            lp_liquidity=None, lp_imd_wei=None, lp_weth_wei=None, lp_owner=None,
            identity_allowed=None, imd_supply_wei=None, block_number=None,
        )
    )
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert SOURCE_CHAIN in data["degraded"]
    assert data["lp_liquidity"] is None
    assert data["gate_open"] is None
    assert data["imd_supply"] is None
    assert data["imd_burned_cum"] is None       # cold start: nothing observed yet


async def test_a_half_empty_chain_state_is_not_penalised(tmp_path):
    """The wholly-``None`` guard must not overreach: a real partial read (some
    fields populated, some not — the everyday half-failure this dashboard is
    built to tolerate) is still an honest, healthy read and must not be flagged
    degraded on top of the per-field ``None``s already rendering as unavailable.
    """
    client = FakeSurfClient(
        fetch_chain_state=_chain_state(lp_owner=None, identity_allowed=None)
    )
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert SOURCE_CHAIN not in data["degraded"]
    assert data["lp_owner_ok"] is None
    assert data["gate_open"] is None
    assert data["imd_supply"] == pytest.approx(IMD_SUPPLY)   # the rest still reads


#: One poll cadence, spelled once. `_manager` builds every manager with
#: ``poll_interval=30`` and the backoff arithmetic below is derived from it
#: rather than counted by hand.
POLL_INTERVAL = 30.0


async def test_a_cold_cache_does_not_bypass_the_failure_backoff(tmp_path):
    """A fresh install against a rate-limiting host used to fetch on every poll.

    Every skip predicate read ``if TIER_X not in tiers and
    self.cache.get_last_good(SLOT) is not None: return None``. The second
    conjunct means a group whose slot has never been populated is fetched every
    refresh no matter what ``mark_failed`` did to the tier clock — and that is
    exactly the state a fresh install is in when the upstream host is down or
    rate-limiting. The multiplier is what makes it matter: one
    ``fetch_nft_stats`` is up to 11 upstream requests and ``_get_json`` retries
    each failure once, so a dead Blockscout cost roughly 40 requests to one
    already-rate-limiting host every 30 s, indefinitely. For a keyless tool
    installed with ``pipx`` by people who cannot register for anything, getting
    the user's IP blocked is a first-class failure.

    The cold cache never needed the second conjunct: a tier with no recorded
    ``next_due`` is *already* due, so cycle 1 fetches either way. All the
    conjunct ever did was disable the backoff on the one path that needs it.

    Counts are derived from ``TIER_FAILURE_BACKOFF_SECONDS``, not typed in, so
    a change to a backoff constant reaches this test as a change and not as a
    silent pass.
    """
    from maxpane_dashboard.data.surf_cache import (
        TIER_FAILURE_BACKOFF_SECONDS, TIER_MEDIUM, TIER_SLOW,
    )

    polls = 10
    span = polls * POLL_INTERVAL
    clock = FakeClock()
    client = _dead_client()
    m = _manager(tmp_path, client=client, clock=clock)
    for _ in range(polls):
        await m.fetch_and_compute()
        clock.advance(POLL_INTERVAL)

    medium = math.ceil(span / TIER_FAILURE_BACKOFF_SECONDS[TIER_MEDIUM])
    slow = math.ceil(span / TIER_FAILURE_BACKOFF_SECONDS[TIER_SLOW])
    assert client.calls.count("fetch_market") == medium
    assert client.calls.count("fetch_recent_logs") == medium
    assert client.calls.count("fetch_channel_txs") == medium
    assert client.calls.count("fetch_nft_stats") == slow
    assert client.calls.count("fetch_dev_activity") == slow

    # The fast tier is deliberately untouched: the announce channel emits no
    # logs, so `eth_getTransactionCount` is the only detector that exists for
    # it and it runs every refresh by design. Its 15 s backoff is shorter than
    # the poll interval anyway, so it could not skip a cycle if it tried.
    assert client.calls.count("fetch_nonces") == polls
    assert client.calls.count("fetch_chain_state") == polls

    # And a skipped group is still reported — it has never produced a payload.
    assert (await m.fetch_and_compute())["degraded"] == sorted(SOURCES)


async def test_a_backed_off_group_stays_degraded_through_the_retry_window(tmp_path):
    """Review point: ``mark_failed`` advances the retry clock, not
    ``last_fetch_ts`` — a tier sitting out a failure's backoff window answers
    ``is_fresh``/``tiers_due`` exactly like a tier that just succeeded. The
    manager must not use that question to decide whether this cycle's payload
    is trustworthy; ``_failed_groups`` must keep the group degraded through a
    skip cycle inside the backoff window, and the served value must be the
    honestly-stale last-good, never blanked and never silently "live".

    This one opens with a **successful** cycle, so it proves the warm-cache
    path only — which is the path that already worked. The cold-cache path its
    docstring used to imply is
    ``test_a_cold_cache_does_not_bypass_the_failure_backoff`` above, and it was
    broken for every one of the five skip predicates.
    """
    clock = FakeClock()
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client, clock=clock)
    await m.fetch_and_compute()                      # establishes a good NFT read

    client._returns["fetch_nft_stats"] = None
    clock.advance(420.0)                              # the slow tier is due
    failed = await m.fetch_and_compute()
    assert SOURCE_NFT in failed["degraded"]
    assert client.calls.count("fetch_nft_stats") == 2

    clock.advance(60.0)                               # inside the 120 s backoff
    skipped = await m.fetch_and_compute()
    assert client.calls.count("fetch_nft_stats") == 2  # backed off, not retried
    assert SOURCE_NFT in skipped["degraded"]            # still degraded, not "fresh"
    assert skipped["nft_holders"] == NFT_HOLDERS        # stale last-good, served honestly
    assert m.cache.age_of(SLOT_NFT) == pytest.approx(480.0)


async def test_a_client_flagged_partial_failure_names_only_that_group(tmp_path):
    """Review point: a partial outage — one group down, five healthy — must
    name only the failed group. ``activity_truncated`` is one of the three
    client-side flags folded into ``_degraded`` outside the ``fetch_*``
    None/exception path, so it is the one most at risk of leaking into groups
    it has nothing to do with.
    """
    client = FakeSurfClient()
    client.activity_truncated = True
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    # `launchpad` rides along on cold start: the detached sweep this cycle
    # offers cannot land inside the cycle that spawned it (Task 6), so a
    # brand-new cache always shows it alongside whatever else is down.
    assert data["degraded"] == [SOURCE_ACTIVITY, SOURCE_LAUNCHPAD]


# ---------------------------------------------------------------------------
# Task 6 — the launchpad tier: v4 pool, decoy scan, hook/factory/executor,
# wired as a detached sweep off its own TIER_LAUNCHPAD.
# ---------------------------------------------------------------------------


async def test_the_first_payload_is_not_behind_the_launchpad_read() -> None:
    """The sweep is spawned, never awaited.  This fails by timing out.

    Modelled on curator's ``_spawn_crosscheck`` tripwire: a launchpad read
    that blocks ``fetch_and_compute`` would push first paint behind a
    146-coin sweep.
    """
    never = asyncio.Event()

    async def _hangs(*_a, **_kw):
        await never.wait()

    manager = _manager_with(fetch_launchpad=_hangs)
    payload = await asyncio.wait_for(manager.fetch_and_compute(), timeout=2.0)
    assert payload["imd_supply"] is not None
    assert payload["launchpad_coin_count"] is None


async def test_a_failed_sweep_serves_last_good_behind_as_of() -> None:
    """Stale is a marker, not a degraded group -- degradation is for nothing
    to serve at all.

    Checked against ``SOURCE_LAUNCHPAD``, not the literal ``"launchpad"``
    the brief originally spelled this assertion with: fix round 1 (controller
    finding 2) renders this group as ``"pad"`` to keep the title bar's
    worst-case width inside its pin, and the group's *identity* -- "is this
    group degraded" -- is what this test is actually about.
    """
    manager = _manager_with_last_good(SLOT_LAUNCHPAD, {"coin_count": 146}, at=1000.0)
    payload = await manager.fetch_and_compute()
    assert payload["launchpad_coin_count"] == 146
    assert payload["launchpad_as_of_hhmm"] is not None
    assert SOURCE_LAUNCHPAD not in payload["degraded"]


async def test_a_failed_sweep_with_nothing_to_serve_degrades() -> None:
    manager = _manager_with_last_good(SLOT_LAUNCHPAD, None)
    payload = await manager.fetch_and_compute()
    assert SOURCE_LAUNCHPAD in payload["degraded"]


async def test_a_healthy_launchpad_sweep_populates_every_payload_key() -> None:
    """One populated slot -> every Task 1 key reads off it, correctly mapped
    and correctly scaled — the wei->token division happens exactly once, in
    ``_cycle``, never inside the cached slot itself."""
    coin = _launchpad_coin(creator=DEV_WALLET)          # a KNOWN_LABELS hit
    slot_payload = {
        "pool_id": POOL_ID,
        "pool_fee": 10_000,
        "pool_id_source": "hook",
        "decoy_pool_count": 4,
        "coin_count": 12,
        "imd_to_burn_wei": round(15.06 * 10**18),
        "executor_balance_wei": round(3.0 * 10**18),
        "min_bridge_wei": round(10.0 * 10**18),
        "creator_eth_owed_wei": round(0.25 * 10**18),
        "burned_total_wei": round(90.0 * 10**18),
        "swap_count": 25,
        "trader_count": 12,
        "coins": [
            {
                "ticker": coin.ticker, "name": coin.name, "creator": coin.creator,
                "creator_known": True, "age_s": coin.age_s,
                "price_eth": coin.price_eth, "change_1h_pct": coin.change_1h_pct,
                "swaps_1h": coin.swaps_1h, "imd_burned": coin.imd_burned,
            }
        ],
    }
    manager = _manager_with_last_good(SLOT_LAUNCHPAD, slot_payload, at=NOW - 30.0)
    payload = await manager.fetch_and_compute()

    assert payload["pool_fee_bps"] == 10_000
    assert payload["pool_id_source"] == "hook"
    assert payload["decoy_pool_count"] == 4
    assert payload["launchpad_coin_count"] == 12
    assert payload["launchpad_swap_count"] == 25
    assert payload["launchpad_trader_count"] == 12
    assert payload["burn_accrued"] == pytest.approx(15.06)
    assert payload["burn_staged"] == pytest.approx(3.0)
    assert payload["burn_min_bridge"] == pytest.approx(10.0)
    assert payload["burn_ready"] is True                 # 15.06 >= max(10.0, 1)
    assert payload["launchpad_creator_eth_owed"] == pytest.approx(0.25)
    assert payload["launchpad_burned_total"] == pytest.approx(90.0)
    assert payload["launchpad_as_of_hhmm"] is not None
    row = payload["launchpad_coins"][0]
    assert set(row) == set(SURF_ROW_KEYS["launchpad_coins"])
    assert row["ticker"] == "ICE"
    assert row["creator_known"] is True                  # DEV_WALLET is labelled


async def test_burn_ready_is_none_not_false_when_either_leg_is_unread() -> None:
    """The Task 6 tri-state rule: "we cannot tell" is not "not ready"."""
    only_accrued = {"imd_to_burn_wei": round(5.0 * 10**18)}   # no min_bridge_wei
    manager = _manager_with_last_good(SLOT_LAUNCHPAD, only_accrued, at=NOW)
    payload = await manager.fetch_and_compute()
    assert payload["burn_accrued"] == pytest.approx(5.0)
    assert payload["burn_min_bridge"] is None
    assert payload["burn_ready"] is None

    only_min_bridge = {"min_bridge_wei": round(2.0 * 10**18)}  # no imd_to_burn_wei
    manager2 = _manager_with_last_good(SLOT_LAUNCHPAD, only_min_bridge, at=NOW)
    payload2 = await manager2.fetch_and_compute()
    assert payload2["burn_accrued"] is None
    assert payload2["burn_ready"] is None


async def test_burn_ready_is_false_when_accrued_is_below_the_floor() -> None:
    """``max(min_bridge, 1)``: a zero ``min_bridge`` still needs at least one
    whole IMD accrued before bridging is "ready", not "any accrual at all"."""
    slot_payload = {
        "imd_to_burn_wei": round(0.5 * 10**18),
        "min_bridge_wei": 0,
    }
    manager = _manager_with_last_good(SLOT_LAUNCHPAD, slot_payload, at=NOW)
    payload = await manager.fetch_and_compute()
    assert payload["burn_accrued"] == pytest.approx(0.5)
    assert payload["burn_min_bridge"] == 0.0
    assert payload["burn_ready"] is False


async def test_representable_zeros_survive_as_zero_not_none() -> None:
    """A genuine on-chain zero must never collapse into "unread"."""
    slot_payload = {
        "decoy_pool_count": 0,
        "coin_count": 0,
        "swap_count": 0,
        "trader_count": 0,
        "burned_total_wei": 0,
        "coins": [],
    }
    manager = _manager_with_last_good(SLOT_LAUNCHPAD, slot_payload, at=NOW)
    payload = await manager.fetch_and_compute()
    assert payload["decoy_pool_count"] == 0
    assert payload["launchpad_coin_count"] == 0
    assert payload["launchpad_swap_count"] == 0
    assert payload["launchpad_trader_count"] == 0
    assert payload["launchpad_burned_total"] == 0.0
    assert payload["launchpad_coins"] == []
    # A cold-start `lp_position_count` still separates "0 positions, read" from
    # "we could not read it" -- exercised directly against `_chain_state`.


async def test_lp_state_passes_through_the_chain_read(tmp_path) -> None:
    """``lp_state`` rides the fast tier (``ChainState``), never the launchpad
    slot -- it must be available the very first cycle, unlike everything else
    this task wires.

    ``lp_position_count`` used to be asserted here too; fix round 12a
    dropped it from ``SURF_KEYS`` (no widget ever read it) and from this
    payload, though ``ChainState.lp_position_count`` itself -- and the
    ``PositionManager.balanceOf(OPS_WALLET)`` read behind it -- are kept
    (see the task report). ``tests/data/test_surf_client.py`` still covers
    that field's own construction directly; there is nothing left for this
    manager-level test to prove about it now that nothing downstream reads it.
    """
    client = FakeSurfClient(fetch_chain_state=_chain_state(lp_state="gone"))
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["lp_state"] == "gone"
    assert data["pool_venue"] == "v4"
    assert "lp_position_count" not in data


async def test_pool_venue_reads_v3_while_the_v3_position_still_answers(
    tmp_path,
) -> None:
    client = FakeSurfClient(fetch_chain_state=_chain_state(lp_state="live"))
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["pool_venue"] == "v3"


async def test_pool_venue_is_none_when_neither_sub_call_answered(tmp_path) -> None:
    client = FakeSurfClient(fetch_chain_state=_chain_state(lp_state=None))
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["pool_venue"] is None
    assert data["lp_state"] is None


async def test_a_decoy_scan_failure_does_not_blank_the_rest_of_the_sweep(
    tmp_path,
) -> None:
    """A decoy-count read that failed on its own must not invalidate the
    pool/launchpad data the same sweep otherwise read cleanly.

    Two cycles, and the task explicitly awaited in between: the sweep
    spawned by cycle 1 is never visible to cycle 1's *own* payload (Task 6's
    whole point), so this reads it back on cycle 2, once it has genuinely
    landed -- not by luck of how the event loop happened to interleave it.
    """
    client = FakeSurfClient(fetch_decoy_pool_count=None)
    m = _manager(tmp_path, client=client)
    await m.fetch_and_compute()
    await asyncio.wait_for(m._launchpad_task, timeout=2.0)
    data = await m.fetch_and_compute()
    assert data["decoy_pool_count"] is None
    assert data["pool_id_source"] == "hook"
    assert data["launchpad_coin_count"] == 12


async def test_a_launchpad_outage_degrades_only_the_launchpad_group(
    tmp_path,
) -> None:
    client = FakeSurfClient(fetch_pool_v4=None, fetch_launchpad=None)
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["degraded"] == [SOURCE_LAUNCHPAD]
    assert data["imd_supply"] is not None                # the rest is untouched


async def test_close_cancels_an_in_flight_launchpad_sweep() -> None:
    """Quitting mid-sweep must not leak the task or crash on the way out."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def _blocking(*_a, **_kw):
        started.set()
        await release.wait()
        return _launchpad_state()

    m = _manager_with(fetch_launchpad=_blocking)
    await m.fetch_and_compute()
    await asyncio.wait_for(started.wait(), timeout=2.0)
    task = m._launchpad_task
    assert task is not None and not task.done()

    release.set()
    await asyncio.wait_for(m.close(), timeout=2.0)
    assert task.done()
    assert m._launchpad_task is None


# ---------------------------------------------------------------------------
# Task 6 fix round 1 (controller finding 1) — the five reading keys Task 7's
# not-yet-registered detectors (DECOY POOL, BURN READY, HOT COIN) will need.
# ---------------------------------------------------------------------------


def test_readings_feed_the_three_future_detectors_off_the_launchpad_slot(
    tmp_path,
) -> None:
    """The three keys already flat-published (`decoy_pool_count`,
    `burn_ready`, `burn_accrued`) come off `data`; the two that aren't
    `SURF_KEYS` entries (`decoy_newest_fee_bps`, `launchpad_swaps_by_coin`)
    come off the raw slot dict passed alongside it.

    Fix round 2: `launchpad_swaps_by_coin` reads the slot's own
    `swaps_by_coin` key -- the FULL population `SurfClient.fetch_launchpad`
    now returns -- never derived from the render-capped `coins` rows, which
    is deliberately given a *different* (and smaller) distribution here to
    prove the two are not conflated.
    """
    slot_payload = {
        "decoy_pool_count": 4,
        "decoy_newest_fee_bps": 98_000,
        "coins": [
            {"ticker": "ICE", "swaps_1h": 9},
        ],
        "swaps_by_coin": {"ICE": 9, "FIRE": 2, "QUIET": 1},
    }
    m = _manager(tmp_path)
    data = {"decoy_pool_count": 4, "burn_ready": True, "burn_accrued": 15.06}
    readings = m._readings(data, None, {}, [], slot_payload)
    assert readings["decoy_pool_count"] == 4
    assert readings["decoy_newest_fee_bps"] == 98_000
    assert readings["burn_ready"] is True
    assert readings["burn_accrued"] == pytest.approx(15.06)
    assert readings["launchpad_swaps_by_coin"] == {"ICE": 9, "FIRE": 2, "QUIET": 1}


def test_swaps_by_coin_is_none_only_when_never_fetched(tmp_path) -> None:
    """``None`` (unread) and ``{}`` (read, genuinely nothing) are different
    claims, exactly as everywhere else in this module.

    Fix round 2: this now validates the slot's own ``swaps_by_coin`` dict
    directly (the full population `SurfClient.fetch_launchpad` returns),
    not a derivation from ``launchpad_coins`` rows -- there is no list
    shape to parse here any more.
    """
    m = _manager(tmp_path)
    assert m._swaps_by_coin(None) is None
    assert m._swaps_by_coin("not a dict") is None       # malformed slot value
    assert m._swaps_by_coin({}) == {}
    assert m._swaps_by_coin({"ICE": 3, "FIRE": 1}) == {"ICE": 3, "FIRE": 1}
    # A malformed entry (a non-int count, or a bool masquerading as one) is
    # dropped individually, not crashed on or coerced into a lie.
    assert m._swaps_by_coin({"ICE": 3, "BAD": None, "WORSE": True}) == {"ICE": 3}


async def test_the_launchpad_sweep_captures_the_newest_decoys_own_fee(
    tmp_path,
) -> None:
    """``decoy_newest_fee_bps`` is threaded from the client's
    ``(count, newest)`` return into the slot, for ``_readings`` to read back
    and feed DECOY POOL's detail line (Task 7)."""
    client = FakeSurfClient(
        fetch_decoy_pool_count=(3, {"fee": 98_000, "pool_id": "0x" + "d1" * 32})
    )
    m = _manager(tmp_path, client=client)
    await m.fetch_and_compute()
    await asyncio.wait_for(m._launchpad_task, timeout=2.0)
    entry = m.cache.get_last_good(SLOT_LAUNCHPAD)
    assert entry.payload["decoy_newest_fee_bps"] == 98_000


async def test_a_missing_newest_decoy_row_leaves_the_fee_unread(tmp_path) -> None:
    """No decoys at all (``(0, None)``) must not fabricate a fee tier."""
    client = FakeSurfClient(fetch_decoy_pool_count=(0, None))
    m = _manager(tmp_path, client=client)
    await m.fetch_and_compute()
    await asyncio.wait_for(m._launchpad_task, timeout=2.0)
    entry = m.cache.get_last_good(SLOT_LAUNCHPAD)
    assert entry.payload["decoy_pool_count"] == 0
    assert entry.payload["decoy_newest_fee_bps"] is None
