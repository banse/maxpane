"""Frozen interface for the surf ("mission control") dashboard.

Boundaries only: this module imports nothing but the standard library.  No
client, no cache, no analytics, no Textual.  Every other surf module codes
against what is declared here.

Unit discipline (copied deliberately from ``fwa_models``): **models are
wei-native, the flat dict is the presentation boundary.**  ``*_wei`` fields are
``int``; the manager divides exactly once when it builds the flat dict, which is
why the dict carries ``imd_supply`` / ``value_eth`` while the models carry
``imd_supply_wei`` / ``value_wei``.

Naming discipline: **model fields mirror the chain, flat-dict keys mirror the
PRD.**  The getter is ``identityAllowed()`` so the field is ``identity_allowed``;
the hero key is ``gate_open``.  The full mapping is table-ised in
``surf_manager``; nothing here is renamed to match a widget.

Raw discipline: the client returns what it read.  ``ChannelTx`` has no ``kind``
and no ``text`` — the manager derives both through ``analytics/surf_signals``,
so the classifier and the UTF-8 decoder each have exactly one caller and one
test suite against hostile input (PRD §6 rule 4).  ``LogWindow`` carries raw log
rows for the same reason; the decoders live in ``surf_manager``.

``DevTx`` is the one deliberate exception, and the reason is right below it:
``counterparty``, ``counterparty_label`` and ``kind`` are declared **without
defaults**, so only the constructor site can fill them — and that site is the
client, which is the last place a row's provenance (whose page it came from)
still exists, and therefore the only place the address-poisoning sender filter
can run.  The manager derives ``counterparty_known`` from ``counterparty_label``
and nothing else.

Outage discipline: every field a read can fail to produce is ``… | None`` and
defaults to ``None``.  Nothing here defaults to ``0`` — a zero written into a
persisted supply series outlives the outage that produced it and fires a false
BURN signal (docs/surf_PRD.md §6.1).
"""

from __future__ import annotations

from dataclasses import dataclass

#: The four announcement-channel classifications (analytics/surf_signals.py
#: ``classify_channel_tx`` returns exactly one of these).
CHANNEL_KINDS: tuple[str, ...] = ("self", "reply", "action", "fund")

#: Signal states rendered by ``SurfSignals``.  ``None`` means "not evaluated".
SIGNAL_STATES: tuple[str, ...] = ("ok", "watch", "fired")


@dataclass(frozen=True, slots=True)
class NonceSet:
    """The three transaction counts read every refresh, in one batch.

    A leg that failed is ``None``; a leg that succeeded and is genuinely 0 is
    ``0``.  Signal code must never conflate the two.
    """

    announce: int | None
    dev: int | None
    ops: int | None
    block_number: int | None = None


@dataclass(frozen=True, slots=True)
class ChainState:
    """One batched round of ``eth_call`` getters — the PRD fast tier.

    Seven ``aggregate3`` sub-calls: ``positions()``, ``ownerOf()``,
    ``identityAllowed()``, ``totalSupply()``, ``slot0()``, ``name()``,
    ``symbol()``.  Every sub-call is ``allowFailure=True``, so one reverted view
    degrades one field to ``None`` rather than the round.

    ``lp_owner`` is the raw address from ``NFPM.ownerOf(LP_POSITION_ID)``; the
    manager compares it to ``OPS_WALLET`` to produce ``lp_owner_ok`` — the model
    does not editorialise, and "unread" must stay distinguishable from "someone
    else holds it".

    ``lp_imd_wei``/``lp_weth_wei`` are **derived, not returned**: the standard
    Uniswap v3 closed form over ``liquidity``, ``sqrtPriceX96`` and the position's
    ``tickLower``/``tickUpper``.  WP1.4 computes them because it is the only place
    the tick bounds exist — see the note above.  A ``0`` in either is a *real*
    zero (the price left that side of the range); ``None`` is a failed read.

    There is no ``identities_written``: the verified IdentityMD source has
    ``totalSupply`` and ``identityAllowed`` and no written-hash counter, so that
    number is ``NftStats.written``'s problem, not a getter's.

    ``lp_state``/``lp_position_count`` are the 2026-08-17 migration addition.
    The ops wallet withdrew and burned v3 position ``LP_POSITION_ID``, so
    ``positions()``/``ownerOf()`` now revert ``Invalid token ID`` — a revert is
    an *answer* ("this position does not exist"), never a failed read, so it is
    encoded as ``"gone"``, not collapsed into the same ``None`` a transport
    outage produces. ``"live"`` is the ordinary case (the call succeeded);
    ``None`` means no sub-call answered at all. ``lp_position_count`` is
    ``PositionManager.balanceOf(OPS_WALLET)`` on the v4 side and has a
    **representable zero** — 0 means the wallet genuinely holds no v4 position,
    a real value distinct from "we could not read it".
    """

    lp_liquidity: int | None
    lp_token0: str | None
    lp_token1: str | None
    lp_fee: int | None
    lp_tokens_owed0_wei: int | None
    lp_tokens_owed1_wei: int | None
    lp_imd_wei: int | None
    lp_weth_wei: int | None
    lp_owner: str | None
    identity_allowed: bool | None
    imd_supply_wei: int | None
    sqrt_price_x96: int | None
    pool_tick: int | None
    imd_name: str | None
    imd_symbol: str | None
    block_number: int | None = None
    lp_state: str | None = None  # "live" | "gone" | None
    lp_position_count: int | None = None


@dataclass(frozen=True, slots=True)
class ChannelTx:
    """One announcement-channel transaction, **raw**.

    No ``kind`` and no ``text``: the channel is permissionless and
    attacker-writable, so classification and UTF-8 decoding are pure functions in
    ``analytics/surf_signals`` where they are table-tested against hostile input.
    ``input_hex`` is what makes that possible and is never dropped — the manager
    calls ``classify_channel_tx(from_addr, to_addr, value_wei, input_hex)`` and
    ``decode_utf8_calldata(input_hex)``.

    ``method`` is Blockscout's decoded method name when it has one, else
    ``None`` — a hint for the feed, never the classification.
    """

    tx_hash: str
    ts: float
    nonce: int | None
    from_addr: str
    to_addr: str | None
    value_wei: int
    input_hex: str
    method: str | None = None


@dataclass(frozen=True, slots=True)
class DevTx:
    """One dev-wallet transaction for the activity feed, filtered and labelled.

    ``counterparty_label`` is ``None`` for anything outside
    ``surf_addresses.KNOWN_LABELS`` — an allowlist, never a heuristic, so a
    lookalike cannot inherit its target's label no matter how many leading hex
    characters it matches.  The widget renders those dimmed and truncated.

    Rows are only ever built where the *sender* is a dev wallet, so a poisoning
    dust transfer can never manufacture one (PRD §6.5).  That is a
    **construction invariant**, not a downstream filter: ``wallet_label`` records
    whose page the row came from, and that provenance only exists inside the
    client, which is why WP1.6 owns the check.

    The manager still derives ``counterparty_known`` (= ``counterparty_label is
    not None``) and scales ``value_wei`` to ETH for display.
    """

    tx_hash: str
    ts: float
    wallet_label: str
    from_addr: str
    to_addr: str | None
    counterparty: str
    counterparty_label: str | None
    value_wei: int
    method: str | None
    kind: str
    created_contract: str | None = None


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Cross-checked market view.  DexScreener displays, GeckoTerminal checks.

    ``indexer_name``/``indexer_symbol`` are **DexScreener's**, which are current.
    GeckoTerminal still serves "Vibe Coins" (two renames behind) — its numbers
    are welcome and its strings are barred at the client, which is why no
    ``*_stale`` flag needs to exist here.  The onchain name/symbol the dashboard
    actually renders are ``ChainState.imd_name``/``imd_symbol``.

    ``sources_agree`` is ``None`` unless *both* sources answered: two prices that
    were never compared are not two prices that disagreed.
    """

    imd_price_usd: float | None
    imd_price_usd_gecko: float | None
    imd_change_24h_pct: float | None
    imd_vol_24h_usd: float | None
    pool_liquidity_usd: float | None
    pool_imd: float | None
    pool_weth: float | None
    fp_price_usd: float | None
    fdv_usd: float | None
    eth_usd: float | None
    indexer_name: str | None
    indexer_symbol: str | None
    sources_agree: bool | None = None


@dataclass(frozen=True, slots=True)
class LogWindow:
    """A recent-window ``eth_getLogs`` sweep across the logs RPC pool.

    Per group, ``()`` means the group was read and held nothing **or** that this
    one filter failed: these fields are frozen tuples and cannot hold ``None``,
    so a single failed group degrades to ``()`` and the failure is reported
    through the manager's ``degraded`` list — never through the tuple.  Do not
    write ``if window.bridge_mints is None``; no input can reach that branch.
    Only a sweep where *every* group failed returns ``None`` instead of a
    ``LogWindow``, because collapsing a dead logs pool into a quiet chain would
    hide exactly the state the launch signals are watching for.

    Groups carry the **raw** log rows the endpoint returned — ``topics`` (full
    list, order intact), ``data`` (untruncated), ``blockNumber``,
    ``blockTimestamp`` when the endpoint sends it, and ``transactionHash`` — all
    preserved, never normalised, pruned or re-keyed.  The decoders that turn
    those into ``ts`` / ``hooks`` / ``amount`` / ``token_id`` live in
    ``surf_manager`` (WP4); WP1.9b is the hand-over guard that fails if the
    client drops any of the fields those decoders index.
    """

    from_block: int | None
    to_block: int | None
    bridge_mints: tuple[dict, ...] = ()
    identity_updates: tuple[dict, ...] = ()
    v4_initializes: tuple[dict, ...] = ()
    seaport_sales: tuple[dict, ...] = ()


@dataclass(frozen=True, slots=True)
class NftStats:
    """IDMD collection stats from Blockscout counters + one ``balanceOf``.

    ``transfers_total`` is the lifetime counter Blockscout serves (7,411 on
    2026-08-08).  ``transfers_24h`` is the *rate* the PRD hero asks for; it is a
    separate field so the lifetime number can never be rendered as a daily one,
    and WP1.8's ``_count_transfers_24h()`` derives it by walking
    ``/tokens/{IDMD}/transfers`` newest-first until a row falls outside the
    window.  ``written`` (identities with a hash set — 1 of 2000) is WP1.8's
    ``_count_identities_written()``: distinct ``topics[1]`` over
    ``/addresses/{IDENTITY_REGISTRY}/logs``, lifetime, keyless.  Both answer
    ``None`` when their page budget runs out before the answer is complete — a
    lower bound printed as a rate or a total is a wrong number.

    ``floor_eth`` is the one deferred field, and it is pinned to ``None`` for
    good: OpenSea is keyed and Cloudflare-gated and no other keyless source
    exists, so the widget renders ``n/a — no keyless source``.  Never populate
    any of the three from an indexer guess — and specifically, never populate
    ``written`` from ``len(LogWindow.identity_updates)``, which counts an
    eight-hour window and not the collection (see open issue 9).

    Realized sales are **not** here: they are decoded from
    ``LogWindow.seaport_sales`` on the medium tier.
    """

    holders: int | None
    total_supply: int | None
    transfers_total: int | None
    dev_holdings: int | None
    transfers_24h: float | None = None
    written: int | None = None
    floor_eth: None = None


@dataclass(frozen=True, slots=True)
class PoolV4State:
    """One ``extsload`` round against the live IMD/ETH v4 pool.

    v4 has no ``slot0()``; state is read out of ``PoolManager._pools`` by
    computing the mapping slot.  Every field is ``None`` on a failed read --
    the pool is real, so there is no "does not exist" case here.

    ``pool_id_source`` is ``"hook"`` when ``LaunchpadHook.imdEthPoolId()``
    answered and ``"fallback"`` when the vendored constant was used.  It is
    recorded rather than inferred because the panel has to be able to say so:
    37 decoy pools mean "which pool is this" is a question with a wrong answer.
    """

    pool_id: str | None
    sqrt_price_x96: int | None
    tick: int | None
    lp_fee: int | None
    liquidity: int | None
    pool_id_source: str  # "hook" | "fallback"


@dataclass(frozen=True, slots=True)
class LaunchpadCoin:
    """One launched coin, ranked from logs.

    ``ticker`` and ``name`` are **attacker-chosen**: ``launch(string,string)``
    is permissionless.  They are carried raw here and escaped at render.
    """

    ticker: str
    name: str
    creator: str
    age_s: float | None
    price_eth: float | None
    change_1h_pct: float | None
    swaps_1h: int
    imd_burned: float | None


@dataclass(frozen=True, slots=True)
class LaunchpadState:
    """The launchpad tier's payload: getters plus log aggregates.

    ``imd_to_burn_wei`` and ``executor_balance_wei`` have a **representable
    zero** -- 0 means "we looked and nothing has accrued" and must stay
    distinguishable from ``None``, which means the read failed.

    ``swaps_by_coin`` (fix round 2, 2026-08-24) is the **full** per-coin
    in-window swap count -- every coin with at least one swap in the hour,
    not the ``LAUNCHPAD_RENDER_LIMIT``-capped slice ``coins`` carries. The
    two serve different callers on purpose: ``coins`` is how many rows the
    panel draws, ``swaps_by_coin`` is the input
    ``analytics/surf_launchpad.hot_coin_threshold`` takes a *median* over --
    and a median taken over only the render-capped top 20 runs several times
    too high (the busiest coins are exactly the ones the cap keeps), so HOT
    COIN would almost never fire if it read the capped list instead. Costs
    no extra request: it is counted from the same ``CurveSwap`` sweep
    ``coins``/``swap_count``/``trader_count`` already read. ``None`` only
    when that sweep failed outright (mirrors ``all_swaps`` in
    ``SurfClient._launchpad_logs``); a swept-but-quiet hour is the
    representable ``{}``.
    """

    coin_count: int | None
    imd_to_burn_wei: int | None
    total_real_imd_wei: int | None
    burn_fee_bps: int | None
    creator_fee_bps: int | None
    creator_eth_owed_wei: int | None
    executor_balance_wei: int | None
    min_bridge_wei: int | None
    coins: tuple[LaunchpadCoin, ...]
    swap_count: int | None
    trader_count: int | None
    burned_total_wei: int | None
    swaps_by_coin: dict[str, int] | None


#: Every key ``SurfManager.fetch_and_compute()`` returns — the parallel-agent
#: interface, frozen by docs/surf_PRD.md §5.  Every numeric is ``float|int|None``
#: and ``None`` renders as the widget's unavailable state, never as 0.
SURF_KEYS: tuple[str, ...] = (
    # ---- meta ---------------------------------------------------------------
    "as_of",                 # float — epoch of the sweep that produced this dict
    "degraded",              # list[str] — source-group names currently failing
    "eth_usd",               # float | None — CoinGecko via data/price.py
    # ---- feed ---------------------------------------------------------------
    "feed_nonce",            # int | None — eth_getTransactionCount(ANNOUNCE)
    "feed_last_post_age_s",  # float | None
    "feed_items",            # list[dict] — SURF_ROW_KEYS["feed_items"]
    # ---- signals: six detectors, state/detail/age each ----------------------
    "sig_post_state",        # "ok" | "watch" | "fired" | None
    "sig_post_detail",       # str
    "sig_post_age_s",        # float | None
    "sig_lp_state",
    "sig_lp_detail",
    "sig_lp_age_s",
    "sig_gate_state",
    "sig_gate_detail",
    "sig_gate_age_s",
    "sig_deploy_state",
    "sig_deploy_detail",
    "sig_deploy_age_s",
    "sig_bridge_state",
    "sig_bridge_detail",
    "sig_bridge_age_s",
    "sig_burn_state",
    "sig_burn_detail",
    "sig_burn_age_s",
    # ---- hero ---------------------------------------------------------------
    "hook_status",           # str — "NOT LIVE" until an Initialize with hooks!=0
    "lp_liquidity",          # float | None — raw v3 L, rendered abbreviated
    "lp_imd",                # float | None — IMD side, whole tokens
    "lp_weth",                # float | None — WETH side, whole tokens
    "lp_owner_ok",            # bool | None — ownerOf(1167726) == OPS_WALLET
    "gate_open",              # bool | None — IdentityRegistry.identityAllowed()
    "identities_written",     # int | None — 1 of 2000 on 2026-08-08
    "imd_supply",             # float | None — whole IMD, never 0 on failure
    "imd_burned_cum",         # float | None — cumulative, from the burn ledger
    # ---- pool (v3 -> v4 migration) -------------------------------------------
    "pool_venue",             # "v3" | "v4" | None — which pool is currently live
    "pool_fee_bps",           # int | None — the live pool's LP fee, in bps
    "pool_liquidity_raw",     # int | None — raw v4 liquidity (PoolV4State.liquidity)
    "pool_id_source",         # "hook" | "fallback" | None — see PoolV4State
    "decoy_pool_count",       # int | None — other ETH/IMD v4 pools seen (37 known)
    "lp_state",               # "live" | "gone" | None — ops wallet's v4 position
    "lp_position_count",      # int | None — PositionManager.balanceOf(OPS_WALLET)
    # ---- burn executor (v1 -> v2) --------------------------------------------
    "burn_accrued",           # float | None — IMD accrued for burn, whole tokens
    "burn_staged",            # float | None — IMD balance sitting at BURN_EXECUTOR_V2
    "burn_ready",             # bool | None — None unless both accrued & min_bridge read
    "burn_min_bridge",        # float | None — BurnExecutor.minBridgeAmount(), whole IMD
    # ---- market -------------------------------------------------------------
    "imd_price_usd",
    "imd_change_24h_pct",
    "imd_vol_24h_usd",
    "pool_liquidity_usd",
    "fp_price_usd",
    "parity_pct",             # float | None — (imd/fp - 1) * 100, computed live
    "supply_series",          # list[[ts, supply]] — burns step it down
    "price_series",           # list[[ts, price_usd]]
    # ---- nft ----------------------------------------------------------------
    "nft_holders",
    "nft_transfers_24h",
    "nft_dev_holdings",
    "nft_written",
    "nft_last_sales",        # list[dict] — SURF_ROW_KEYS["nft_last_sales"]
    "nft_floor",              # always None in v1 — explicit unavailable state
    # ---- activity -----------------------------------------------------------
    "dev_activity",           # list[dict] — SURF_ROW_KEYS["dev_activity"]
    # ---- launchpad (detached sweep, its own slower "as of") -----------------
    "launchpad_coin_count",         # int | None — LaunchpadFactory.coinCount()
    "launchpad_swap_count",         # int | None — CurveSwap logs seen this sweep
    "launchpad_trader_count",       # int | None — distinct swap senders
    "launchpad_burned_total",       # float | None — cumulative from ImdBurned logs
    "launchpad_creator_eth_owed",   # float | None — LaunchpadHook.totalCreatorEthOwed()
    "launchpad_coins",              # list[dict] — SURF_ROW_KEYS["launchpad_coins"]
    "launchpad_as_of_hhmm",         # str | None — slower tier's own staleness marker
    # ---- signals: three new detectors, state/detail/age each ----------------
    "sig_decoy_state",
    "sig_decoy_detail",
    "sig_decoy_age_s",
    "sig_burnready_state",
    "sig_burnready_detail",
    "sig_burnready_age_s",
    "sig_hot_state",
    "sig_hot_detail",
    "sig_hot_age_s",
)

#: Row shapes for the list-of-dict payloads.  Widgets index these keys
#: directly, so adding one is a contract change, not an implementation detail.
SURF_ROW_KEYS: dict[str, tuple[str, ...]] = {
    "feed_items": ("ts", "kind", "from_addr", "from_label", "text", "tx_hash"),
    "nft_last_sales": ("ts", "token_id", "eth"),
    "dev_activity": (
        "ts",
        "wallet_label",
        "kind",
        "counterparty",
        "counterparty_known",
        "value_eth",
        "tx_hash",
    ),
    "launchpad_coins": (
        "ticker",
        "name",
        "creator",
        "creator_known",
        "age_s",
        "price_eth",
        "change_1h_pct",
        "swaps_1h",
        "imd_burned",
    ),
}
