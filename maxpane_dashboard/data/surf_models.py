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

#: The five announcement-channel classifications (analytics/surf_signals.py
#: ``classify_channel_tx`` returns exactly one of these).
#:
#: ``answer`` is the announcement wallet replying to a ``reply``: per 0xTXT
#: (``0x/packages/protocol/src/surf.ts``) a `surf -> X` zero-value tx carrying
#: UTF-8 is a `legacy-reply`, not a contract call. Folding it into ``action``
#: is what detached the dev's answers from the questions they answer -- a
#: reader could see a question in the feed and never see it get answered,
#: because the answer rendered identically to an unrelated contract call.
CHANNEL_KINDS: tuple[str, ...] = (
    "self", "reply", "answer", "action", "fund", "failed",
)

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

    ``success`` is the receipt's own verdict, and it is **tri-state**:
    ``True``/``False`` when the page said so, ``None`` when it did not.
    ``None`` is not ``False`` — an unstated status must never turn a real
    message into a failure — which is the same rule every numeric reading in
    this file follows, applied to a boolean. It is carried rather than acted
    on here: ``classify_channel_tx`` is where a reverted tx stops being the
    thing it tried to be.
    """

    tx_hash: str
    ts: float
    nonce: int | None
    from_addr: str
    to_addr: str | None
    value_wei: int
    input_hex: str
    method: str | None = None
    success: bool | None = None


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
    #: The receipt's own verdict, tri-state exactly as ``ChannelTx.success``
    #: is: ``None`` means the page did not say and must never be read as a
    #: failure. Unlike ``ChannelTx``, ``kind`` here is assigned by the client
    #: (``_classify_dev_kind``), so the receipt is both carried and acted on
    #: in the same layer -- a reverted tx is ``failed`` whatever address it
    #: was sent to, and the destination only names a tx that happened.
    success: bool | None = None


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

    Fix round 10a (v3->v4 repoint) added a ``legacy_pool_liquidity_usd``
    field carrying the superseded v3 pool's own liquidity apart from the
    live ``pool_liquidity_usd`` above. Task 2 (2026-08-23) removed it: the
    v3 pool was drained on 2026-08-17 and its LP position burned, so that
    number had stopped being a second opinion on the live pool's and become
    a number about a pool that no longer exists.
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

    ``swaps_24h`` is the ranking key and ``swaps_all`` the tiebreak (fix
    round 2's ``swaps_1h``/hour window undercounted a coin that traded
    heavily on day one and then went quiet -- a day-long window is what the
    PRD's LAUNCHPAD COINS table actually sorts by). Both are plain ``int``
    with a **representable zero**: a coin that has never traded really has
    ``0`` swaps, in either window, and that is a fact worth ranking on, not
    a failed read to hide. ``change_24h_pct`` stays ``float | None`` because
    it genuinely can fail to exist: it is ``None`` when fewer than two
    in-window swaps carry a usable price to diff -- *"no measurable move"
    is not the claim "a flat day"*, and collapsing the two would let a coin
    with one swap (or none) rank as unchanged instead of unmeasured.
    """

    ticker: str
    name: str
    creator: str
    age_s: float | None
    price_eth: float | None
    change_24h_pct: float | None
    swaps_24h: int
    swaps_all: int
    imd_burned: float | None


@dataclass(frozen=True, slots=True)
class LaunchpadState:
    """The launchpad tier's payload: getters plus log aggregates.

    ``imd_to_burn_wei`` and ``executor_balance_wei`` have a **representable
    zero** -- 0 means "we looked and nothing has accrued" and must stay
    distinguishable from ``None``, which means the read failed.

    ``swaps_by_coin`` (fix round 2, 2026-08-24; window widened hour -> 24 h
    by this plan's Task 1) is the **full** per-coin in-window swap count --
    every coin with at least one swap in the 24 h window, not the
    ``LAUNCHPAD_RENDER_LIMIT``-capped slice ``coins`` carries. The
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

    **``swaps_by_coin`` is keyed by ``pool_id``, the coin's identity — never
    by its ticker** (final fix wave, I1), and ``coin_tickers`` is the
    companion ``{pool_id: ticker}`` map that exists only so a row can be
    *labelled*. ``LaunchpadFactory.launch(string,string)`` is permissionless
    and unpriced beyond gas, so a ticker is an attacker-chosen display string
    that two coins can share; joining on it merged their swap buckets, which
    both shrank the population ``hot_coin_threshold`` takes a median over and
    let a coin clear the bar on a stranger's volume. ``coin_tickers`` carries
    the raw ticker: escaping is the render layer's job, never this one's.

    ``launch_count`` is what the log sweep actually found (a count of
    ``Launched`` events over however much history the sweep has covered so
    far); ``coin_count`` above is what ``LaunchpadFactory.coinCount()``
    claims. They are two different reads of the same population and are
    deliberately never reconciled into one number here — when a resumable
    sweep is mid-catch-up the two *will* disagree, and the panel has to be
    able to say so (`launch_count of coin_count launched`) rather than
    silently ranking whatever subset the sweep has reached so far as if it
    were the whole population. ``new_24h`` is the same sweep's count of
    ``Launched`` events inside the last day, and ``creator_count`` the
    distinct-creator count over its **full** history, not the render-capped
    ``coins`` slice. All three are ``int | None`` with a representable
    zero -- 0 launches, 0 today, 0 distinct creators are all real answers a
    swept-but-quiet history can give, distinct from the sweep never having
    completed a pass at all.

    ``cursor`` is the launchpad sweep's own resumable position, on the
    ``SLOT_CLUSTERS`` precedent from curator's linked-wallet analysis: an
    append-only log sweep that re-fetched its whole history every tick would
    never catch up as the history grows, so the slot persists
    ``{"last_block": int, "launches": {pool_id: {...}}, "swaps_all":
    {pool_id: int}}`` **plus the three accumulators the lifetime aggregates
    above need** -- ``traders`` (a sorted address list), ``burn_by_coin``
    (``{pool_id: wei}``) and ``burned_total_wei`` -- and each sweep resumes
    from ``last_block`` instead of block zero.

    Those three are not bookkeeping. ``swap_count`` falls out of
    ``swaps_all`` for free, but ``trader_count``, ``burned_total_wei`` and
    each coin's ``imd_burned`` have no additive shortcut from an
    interval-sized delta: a cardinality cannot be deduplicated after the
    fact, and a total cannot be recovered from its newest addend. A cursor
    that dropped them would keep rendering the same labels over numbers that
    had quietly become "since the last tick" -- the exact defect class the
    cursor was introduced to remove. The 24 h swap slice is the one thing
    deliberately NOT in here: a window cannot be accumulated forward at all
    (yesterday's swap has to *leave* the day), so ``SurfClient`` re-reads it
    every sweep instead.

    ``None`` means "no sweep has ever completed a pass" -- not "the history
    is empty" -- and it is the manager's job to keep serving last-good
    ``coins``/``launch_count``/etc. behind an ``as of`` marker while a cursor
    is still ``None`` or stale, never to block first paint on it. It is
    always a ``dict`` or ``None`` even when a persisted payload was
    unreadable: ``SurfClient`` coerces a non-dict to ``None`` rather than
    passing it through, so ``payload["cursor"]["last_block"]`` cannot be
    handed a string.
    """

    coin_count: int | None
    imd_to_burn_wei: int | None
    total_real_imd_wei: int | None
    burn_fee_bps: int | None
    creator_fee_bps: int | None
    creator_eth_owed_wei: int | None
    executor_balance_wei: int | None
    min_bridge_wei: int | None
    #: ``BurnExecutor.previewBridge()``'s first word, ``amountToSend``: what a
    #: bridge-and-burn call would move **right now**, already clamped to the
    #: executor's balance, the OFT's limits and its shared-decimal dust, and
    #: to ``minBridgeAmount``. Zero is a real answer -- "nothing is
    #: bridgeable" -- and ``None`` is a failed read, the usual split. This is
    #: what ``burn_ready`` is derived from; the accrual in the *hook*
    #: (``imd_to_burn_wei``) is a different contract's number and the bridge
    #: does not spend it.
    bridge_amount_wei: int | None
    coins: tuple[LaunchpadCoin, ...]
    swap_count: int | None
    trader_count: int | None
    burned_total_wei: int | None
    swaps_by_coin: dict[str, int] | None
    coin_tickers: dict[str, str] | None = None
    launch_count: int | None = None
    new_24h: int | None = None
    creator_count: int | None = None
    cursor: dict | None = None


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
    # ---- signals: ten detectors, state/detail/age each ----------------------
    "sig_post_state",        # "ok" | "watch" | "fired" | None
    "sig_post_detail",       # str
    "sig_post_age_s",        # float | None
    # NEW REPLY (2026-08-24): a reply or an answer landed on the channel.
    # The feed collapses a post's replies behind a toggle, so without this
    # row a thread can grow with nothing on screen to say so.
    "sig_thread_state",
    "sig_thread_detail",
    "sig_thread_age_s",
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
    # `hook_status` removed 2026-08-24 (fix round 12a): no widget ever
    # rendered it after the HOOK hero card was dropped. The attribution
    # machinery it used to read (`hook_launch`, `v4_hook_pools`) is
    # unaffected -- analytics/surf_signals.py still advances a baseline
    # off it.
    # Raw v3 L off `NFPM.positions(LP_POSITION_ID)`. **Reads `None` forever**:
    # the ops wallet burned that position on 2026-08-17 and the call reverts.
    # Nothing renders it (the hero's LP box went to POOL/LP/BURN/SUPPLY in
    # Task 8) and, since the final fix wave's C2, no detector reads it either
    # -- `_detect_lp` watches `lp_position_count` on the v4 side. Kept in the
    # contract rather than removed, deliberately and late; do not re-describe
    # it as feeding anything.
    "lp_liquidity",          # float | None — raw v3 L, no consumer
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
    # `pool_liquidity_raw` removed 2026-08-24 (fix round 12a): zero
    # references anywhere; `pool_liquidity_usd` is the one the hero renders.
    "pool_id_source",         # "hook" | "fallback" | None — see PoolV4State
    "decoy_pool_count",       # int | None — other ETH/IMD v4 pools seen (37 known)
    "lp_state",               # "live" | "gone" | None — ops wallet's v4 position
    # `lp_position_count` removed 2026-08-24 (fix round 12a): zero
    # references anywhere. `ChainState.lp_position_count` (the model field,
    # PositionManager.balanceOf(OPS_WALLET)) is kept regardless — see
    # surf_manager.py's task-12a report for why.
    # ---- burn executor (v1 -> v2) --------------------------------------------
    "burn_accrued",           # float | None — IMD accrued for burn, whole tokens
    "burn_staged",            # float | None — IMD balance sitting at BURN_EXECUTOR_V2
    "burn_ready",             # bool | None — None unless both accrued & min_bridge read
    "burn_min_bridge",
    # What ``previewBridge()`` says a burn would send right now: the
    # quantity behind ``burn_ready``, and the one the BURN box headlines.
    # ``burn_accrued`` is a different contract's balance and moves the
    # opposite way -- a sweep empties the hook and fills the executor.
    "burn_bridgeable",        # float | None — BurnExecutor.minBridgeAmount(), whole IMD
    # ---- market -------------------------------------------------------------
    "imd_price_usd",           # float | None — on-chain (extsload) when available,
                                # else DexScreener/Gecko; see surf_manager._cycle
    "imd_change_24h_pct",
    "imd_vol_24h_usd",
    "pool_liquidity_usd",      # float | None — the LIVE v4 pool, matched by pool id
    "price_source_disagreement_pct",  # float | None — dex vs chain price, % of chain
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
    "launchpad_launch_count",       # int | None — Launched events swept, vs coin_count
    "launchpad_new_24h",            # int | None — Launched events in the last 24h
    "launchpad_creator_count",      # int | None — distinct creators, full history
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
    # ``label`` is what an outbound call *did* -- the decoded method name, or
    # the 4-byte selector when Blockscout has no ABI for it. It has been
    # emitted since Task WP4.11 and went four releases *undeclared*, which is
    # the reason ``value_eth`` could be specified by a brief and simply not
    # exist in the payload: nothing compared the two lists until
    # ``test_every_feed_row_key_is_declared_in_the_contract``.
    #
    # ``value_eth`` is whole ETH (``value_wei / 1e18``), ``None`` when the
    # value could not be read -- never ``0``, which is a real amount on a
    # channel where almost every tx is a zero-value calldata post. It is the
    # last thing a row has to say when it has no ``text`` and no decoded
    # ``label``: the channel's own funding tx (0.054 ETH, ``input: 0x``) is
    # exactly that shape on chain and rendered its badge followed by a blank
    # line until the feed had this field to fall back on.
    "feed_items": (
        "ts", "kind", "from_addr", "to_addr", "from_label", "text", "tx_hash",
        "label", "value_eth",
    ),
    "nft_last_sales": ("ts", "token_id", "eth"),
    "dev_activity": (
        "ts",
        "wallet_label",
        "kind",
        "counterparty",
        "counterparty_known",
        "value_eth",
        "tx_hash",
        # IMD sent by a bridge-and-burn, from the tx's own logs. ``None`` on
        # every other kind, and on a burn whose receipt we could not read --
        # the row's ETH value is the LayerZero fee, never the burn.
        "imd_burned",
    ),
    "launchpad_coins": (
        "ticker",
        "name",
        "creator",
        "creator_known",
        "age_s",
        "price_eth",
        "change_24h_pct",
        "swaps_24h",
        "swaps_all",
        "imd_burned",
    ),
}
