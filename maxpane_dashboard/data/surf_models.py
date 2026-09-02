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
    mcap_eth: float | None


@dataclass(frozen=True, slots=True)
class LaunchpadEvent:
    """One row of the launchpad activity feed.

    ``kind`` is a closed vocabulary the producer owns: ``"buy"``, ``"sell"``,
    ``"launch"``.  ``ticker`` is **attacker-chosen** (``launch(string,string)``
    is permissionless) and is carried raw here, escaped at render.

    ``eth`` is ``None`` on a launch and never ``0.0``: a launch has no swap
    size, and a zero would read and rank as a free trade.
    """

    kind: str
    ticker: str
    wallet: str
    eth: float | None
    age_s: float | None


@dataclass(frozen=True, slots=True)
class Burnkeeper:
    """One wallet that called ``bridgeToBaseBurnReceiver()`` on the live
    executor, with what it burned and what the bridge cost it.

    ``imd_burned`` has a **representable zero** and comes from
    ``TokensBridgedForBurn`` logs.  ``eth_paid`` is ``float | None`` because
    it comes from a *different* source (the executor's internal transactions)
    that can fail on its own: ``None`` means "we could not read the fee",
    never "the bridge was free", and it must never fall back to the
    transaction's ``value`` -- the contract refunds the surplus, and on live
    data that fallback overstates by up to 36x.
    """

    wallet: str
    imd_burned: float
    eth_paid: float | None
    burns: int


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
    activity: tuple[LaunchpadEvent, ...] | None = None
    burnkeepers: tuple[Burnkeeper, ...] | None = None


# ---------------------------------------------------------------------------
# pool4 — "protocol owned inference" (CappedBurnHook + sIMD + RewardDripper)
#
# The surf ``p`` body.  Research of record: docs/imd_pool4_mechanics.md; the
# frozen contract this section implements: docs/surf_pool4_contract.md.
#
# Two disciplines from the top of this module apply with unusual force here and
# are restated because pool4 is where they were most likely to be got wrong:
#
# 1. **Wei-native models, flat dict at the presentation boundary.**  The hook's
#    counters are uint256 IMD; the models carry ``total_burned_wei`` and the
#    manager divides exactly once into ``pool4_total_burned``.
# 2. **Model fields mirror the chain, flat-dict keys mirror the PRD.**  The
#    getter is ``tokensInPool()`` so the field is ``tokens_in_pool_wei``; the
#    payload key is ``pool4_tokens_in_pool``.  Nothing here is renamed to suit
#    a widget.
#
# The hook is **unverified source**: its interface is *recovered from bytecode
# selectors*, not read from a verified ABI.  Every hook field is therefore
# ``| None`` with no exception -- a getter that does not exist on the mainnet
# deployment answers nothing, and that is a routine outcome here rather than an
# incident.  ``Pool4VaultState`` and ``Pool4DripperState`` come from verified
# source and are still all-``None``-able for the ordinary transport reason.
# ---------------------------------------------------------------------------

#: The two networks a pool4 read can be about.  Closed vocabulary: every panel
#: title renders ``· <word>`` from it, and ``· —`` when the payload key is
#: ``None``.  ``None`` is "no sweep has ever completed", never a default word --
#: a testnet number under a MAINNET title is the single worst thing this view
#: can print, so the word is always read, never assumed.
POOL4_NETWORKS: tuple[str, ...] = ("SEPOLIA", "MAINNET")

#: The three discovery verdicts.  ``not-discovered`` is the day-one state and
#: the one that actually runs: no pool4 hook, vault or dripper existed on
#: mainnet when this was written, so the mainnet hook has to be *discovered*
#: from the announce channel rather than shipped hardcoded.
#:
#: ``adopted`` is a verdict about an **attacker-writable** channel, and the
#: only thing that makes it safe is **where the candidate came from**: a
#: transaction signed by the announce wallet's key.  That is the one gate
#: nobody can forge without the key.
#:
#: **The cache does not get a vote.**  A persisted ``adopted`` address is not a
#: candidate -- not tried first, not tried last, not re-verified (A27).  An
#: earlier design re-verified it on read and this comment used to promise that;
#: the promise was empty, because the thing it re-ran is forgeable (see
#: :class:`Pool4Discovery`).  Discovery starts from the channel every time, and
#: a state read back from disk is a *label on the last run*, never a nomination
#: for the next one.
POOL4_DISCOVERY_STATES: tuple[str, ...] = ("not-discovered", "adopted", "rejected")

#: The outcome of R1 control (c) -- the wei-exact reconciliation of the hook's
#: cumulative counters against the sum of its own logs.  This is the build's
#: central risk made visible: the hook interface was **recovered from bytecode
#: selectors**, the contract is unverified on mainnet too, and three event
#: signatures are still unresolved, so a wrong operand order in a decoder
#: currently surfaces as a confident wrong number with no signal anywhere.
#:
#: Four words, none a substring of another -- deliberately, on
#: ``SurfBurnPipeline._ready_word``'s precedent.  ``"reconciled"`` and
#: ``"mismatch"`` rather than ``"agree"``/``"disagree"``, because ``agree`` is a
#: substring of ``disagree`` and a widget testing ``"agree" in state`` would
#: render a mismatch as healthy:
#:
#: * ``reconciled``     -- every applicable identity holds **to the wei**, over
#:                         complete history.  The only good news this key gives.
#: * ``mismatch``       -- at least one does not.  ``pool4_counter_detail``
#:                         names which counter and by how much.
#: * ``window-limited`` -- the log sums cover a **trailing window**, not the
#:                         hook's full history, so the cumulative identities
#:                         cannot hold by construction.  Not an error, and not a
#:                         pass: the control did not run.
#: * ``unchecked``      -- the sweep failed or the counters are unread.  We
#:                         could not compute it, which is not the same as
#:                         nothing being wrong.
POOL4_COUNTER_STATES: tuple[str, ...] = (
    "reconciled", "mismatch", "window-limited", "unchecked",
)

#: What ``rewardsRecipient()`` points at -- the shape of the reward path, and
#: therefore **what the reward share actually means**.
#:
#: * ``direct``          -- the recipient is the Dripper.  The reward share IS
#:                          the staker share; ``totalRewarded()`` all reaches
#:                          stakers.  Sepolia's shape.
#: * ``via-distributor`` -- the recipient is a Reward Distributor that
#:                          subdivides the share three ways.  The staker share
#:                          is a *fraction* of ``totalRewarded()``.  Mainnet's.
#:
#: ``None`` means the path is **unknown** -- ``rewardsRecipient()`` was not
#: read -- and a panel must then annotate nothing rather than guess a leg.
#:
#: **This exists because an address cannot carry it.**
#: ``pool4_distributor_addr`` is ``None`` both when there is no Distributor and
#: when the getter that would have named one failed, and those two are three
#: times apart on the headline percentage: 15% of gross reaches stakers under
#: ``direct``, 4.5% under ``via-distributor``.  The hook's getters are batched
#: with ``allowFailure=True`` -- one reverted view degrades one field, not the
#: round -- so "counters answered, ``rewardsRecipient()`` did not" is a routine
#: payload, not a corner case.  A panel reading absence-of-address as
#: absence-of-Distributor would label mainnet's 15% as the staker share in
#: exactly that payload.  Same family as ``POOL4_COUNTER_STATES``: the healthy
#: reading has to be a *word*, because ``None`` is what an omission produces.
POOL4_REWARD_PATHS: tuple[str, ...] = ("direct", "via-distributor")

#: Where an adopted hook's address came from, **ordered strongest first**.
#: This exists because the operator accepted a second candidate source on
#: 2026-09-02, and the mitigation for that decision is *disclosure rather than
#: prevention*: an adoption must say which source it came from, so weaker
#: provenance identifies itself instead of hiding behind the same word as a
#: dev-signed post.
#:
#: * ``self-post``    -- a transaction signed by the announce wallet's key.
#:                       **Unforgeable**, and still the stronger path: it
#:                       overrides ``docs`` whenever a self-post lands.
#: * ``docs``         -- the project's own server-rendered documentation page.
#:                       A **trusted input, not a signed one**: anyone who can
#:                       change that page can name a hook, and the chain
#:                       fingerprint alone will not stop them (A27 -- a
#:                       correctly-shaped address mines in ~20,000 tries, four
#:                       of the five getters are pure liveness checks, and
#:                       ``token()`` is the candidate's own choice).
#: * ``unattributed`` -- adopted, but the producer did not record a source.
#:                       It exists so that a producer bug is **visible**
#:                       instead of rendering as the strong case, and it must
#:                       be shown at least as weakly as ``docs``.
#:
#: ``None`` means there is no adoption to attribute -- read it against
#: ``pool4_discovery_state``, exactly as ``pool4_discovery_source_tx`` is read.
#: ``None`` must **never** render as ``self-post``: absence is not provenance,
#: and this is the one key where mistaking it for the strong answer relaunches
#: the whole problem A27 closed.
POOL4_DISCOVERY_SOURCES: tuple[str, ...] = ("self-post", "docs", "unattributed")

#: The two sides a flow row can have.  Producer-owned and closed: the widget
#: sizes its ``side`` cell to the widest member exactly, so a third member is a
#: layout change, not a data change.
#:
#: The asymmetry is the mechanism, not a quirk: on a **buy** the 1% fee is taken
#: in ETH and nothing burns, on a **sell** it is taken in IMD and 89.1% of the
#: remainder is destroyed.  Buys are not deflationary; sells are.
POOL4_FLOW_SIDES: tuple[str, ...] = ("buy", "sell")

#: ``scope`` on a hatches row -- which contract the hatch belongs to.
#: ``distributor`` joined on 2026-09-02: mainnet routes ``rewardsRecipient()``
#: to a Reward Distributor that has no Sepolia counterpart, and it carries a
#: live ``owner()`` with ``emergencyWithdraw`` and ``setDripper`` -- a trust
#: surface that did not exist before and that this panel exists to disclose.
POOL4_HATCH_SCOPES: tuple[str, ...] = (
    "vault", "dripper", "distributor", "hook", "bond",
)

#: ``label`` on a hatches row -- which hatch it is.
#: ``dripper`` is the distributor's ``setDripper(address)`` power -- the
#: ability to re-point the rewards path at a different contract. ``rescue``
#: covers ``emergencyWithdraw`` on the distributor as well as ``rescueERC20``
#: on the vault; they are the same shape of hatch and share one word.
POOL4_HATCH_LABELS: tuple[str, ...] = (
    "owner", "paused", "rescue", "market", "rebalance", "burn sink",
    "rewards", "dripper", "deployed",
)

#: ``state`` on a hatches row.  ``unknown`` is a first-class member and is not
#: interchangeable with the row being absent: "we looked and could not tell"
#: has to render differently from "there is no such hatch" (``absent``), which
#: is what the BOND row says while no bond contract is deployed anywhere a
#: reader could check.
POOL4_HATCH_STATES: tuple[str, ...] = (
    "live", "renounced", "paused", "open", "closed", "absent", "unknown",
)

#: Flow rows handed to ``SurfPool4Flow``.  Mirrors ``FEED_ITEM_LIMIT`` and the
#: rest of that family in ``surf_manager``; it lives here rather than there
#: because ``surf_manager`` is owned by a different work package in this build
#: and the cap is part of the frozen contract the widget codes against.
POOL4_FLOW_LIMIT = 25


@dataclass(frozen=True, slots=True)
class Pool4HookState:
    """One batched ``eth_call`` round over the hook's recovered getter set.

    **Unverified source.**  Every name below is transcribed from a bytecode
    selector, not from a published ABI, so a field being ``None`` on the
    mainnet deployment means "this getter did not answer" and is an ordinary
    outcome -- the client degrades field by field and never drops the round.

    ``position_liquidity`` is deliberately **not** ``_wei``-suffixed: Uniswap's
    ``L`` is a raw ``uint128`` in the pool's own units and is not an amount of
    anything, so dividing it by 1e18 would be meaningless.  It reaches the flat
    dict unchanged as ``pool4_position_liquidity``.  ``eth_in_pool_wei`` and
    ``tokens_in_pool_wei`` beside it *are* amounts and are divided exactly once.

    ``cap_floor_wei`` is ``capFloor()``, the reserve level the ratchet is not
    supposed to cross.  Its meaning is **inferred from behaviour, not proven**
    (docs/surf_pool4_implementation_plan.md §5 R2) and it is owner-settable, so
    it is labelled *observed* on screen and never as a guarantee.  This model
    holds the number; it does not hold that claim.

    ``market_open`` and ``rebalance_enabled`` are tri-state ``bool | None``:
    ``None`` must never render as either confident answer.

    ``backstop()`` returns **three words and is therefore three fields**:
    ``(int24 lower, int24 upper, uint128 liquidity)``, 96 bytes, no ETH word
    (amendment A15 -- the fourth operand in the mechanics doc's earlier draft
    came from the *event* ``0xe3966151…``, not from the getter, and a decoder
    expecting four reads past the answer).

    Three fields rather than one delimited ``"lower,upper,liquidity"`` string,
    and rather than a ``tuple[int, int, int]``, for three reasons:

    1. **It is this module's existing shape for a multi-word getter.**
       ``positions()`` is already flattened into ``ChainState.lp_liquidity`` /
       ``lp_token0`` / ``lp_token1`` / ``lp_fee`` / ``lp_tokens_owed0_wei`` /
       ``lp_tokens_owed1_wei``. A second convention for the same job is how a
       reader learns to check which one applies.
    2. **Outage discipline is per field here.** A tuple or a string is
       all-or-nothing: one unreadable word forces the whole backstop to
       ``None``, and "we read the bounds but not the liquidity" has nowhere to
       live. Three ``| None`` fields degrade independently, which is the
       granularity the rest of this module already promises.
    3. **A delimited string makes every consumer a parser.** ``pool4_backstop_centred``
       is derived from the bounds against ``current_tick``; deriving it from a
       string means a ``split(",")`` and an ``int()`` per consumer, each with
       its own behaviour on a malformed value -- and the value comes off an
       *unverified* contract, so malformed is a real case, not a hypothetical.

    ``backstop_liquidity`` is deliberately **not** ``_wei``-suffixed, for
    ``position_liquidity``'s reason: it is a raw ``uint128`` ``L``, not an
    amount of any token.

    ``vault`` is **absent on purpose**.  The recovered interface names
    ``rewardsRecipient()`` (the dripper) and ``backstop()`` and no vault, so the
    vault address is one hop further out -- ``Pool4DripperState.vault`` -- and
    putting a ``vault`` field here would invite a producer to fill it by
    scraping a page, which is the one way the address must never be obtained.

    ``bps_denominator`` and ``reward_share_bps`` are the *claimed* split.  The
    measured split is computed from the counters below and the two are compared
    rather than reconciled: ``pool4_split_drift_bps`` is the difference, and
    ``0.0`` is its healthy value and a real number, never a dash.
    """

    #: --- state -----------------------------------------------------------
    token: str | None
    pool_manager: str | None
    pool_id: str | None
    owner: str | None
    burn_sink: str | None
    rewards_recipient: str | None
    backstop_tick_lower: int | None
    backstop_tick_upper: int | None
    backstop_liquidity: int | None
    market_open: bool | None
    rebalance_enabled: bool | None
    #: --- config ----------------------------------------------------------
    bps_denominator: int | None
    reward_share_bps: int | None
    lp_fee: int | None
    cap_floor_wei: int | None
    #: ``inventoryCap()`` and ``capDecayTokensPerDay()``.  Neither is in any
    #: public signature database; the selectors were computed from the
    #: documentation's own vocabulary and confirmed present in the bytecode,
    #: and they live in WP3's ``data/surf_pool4.py`` under the A8 rule -- one
    #: authority per constant, and this module is not it.
    #:
    #: **Both chains answer both getters** (D13, measured by WP6).  An earlier
    #: version of this comment said they were mainnet-only and that Sepolia had
    #: neither; that was an assumption, never measured, and it was wrong.  The
    #: difference is the *value*, not the presence::
    #:
    #:                            Sepolia               Mainnet
    #:     capDecayTokensPerDay   2**128-1 (no decay)   1,000 IMD/day
    #:     inventoryCap           472,569,750.77 IMD    5,413.26 IMD
    #:     tokensInPool           472,569,750.77 IMD    5,413.26 IMD
    #:
    #: Two consequences worth carrying:
    #:
    #: 1. **The absence case cannot be driven by pointing at Sepolia.**  A test
    #:    written as "aim it at Sepolia and watch these go ``None``" passes for
    #:    the wrong reason.  Absence has to come from a getter made to revert,
    #:    which is what a differently-built future hook actually looks like.
    #:    ``None`` therefore keeps its ordinary meaning here -- unread, or a
    #:    hook without the getter -- and neither is an incident.
    #: 2. **``2**128-1`` is a sentinel, not a rate.**  Divided into whole IMD it
    #:    is ~3.4e20 per day, which is not a number any panel should print.  It
    #:    means *no decay*, and the producer owns turning it into that word --
    #:    see the note on ``pool4_cap_decay_per_day``.
    #:
    #: ``inventoryCap`` minus ``tokensInPool`` is published as
    #: ``pool4_cap_headroom``.  It was refused twice and those refusals are now
    #: **superseded, not wrong**:
    #:
    #: * *"the difference is unrepresentable in float"* -- built on a 12-wei
    #:   sample taken minutes after an event and mistaken for a property.  The
    #:   measured mainnet gap is 94.68 IMD, ~1.0e14 ulps at that magnitude,
    #:   where the 12-wei case was 1.3e-5 ulps.  One of those subtracts cleanly
    #:   and one is not representable at all.
    #: * *"the divergent state has never been observed"* -- self-sealing.  The
    #:   only deployment that could show it is Sepolia, whose cap cannot move
    #:   *because* its decay is the no-decay sentinel.  The state was explained
    #:   away by the very special case that prevented it.
    #: * *"both operands are already published"* -- proves too much.
    #:   ``pool4_floor_distance`` is ``reserve - floor`` and both of *its*
    #:   operands are published keys too.  The contract already decided this
    #:   shape belongs in the manager, so refusing the ceiling half on a ground
    #:   that equally condemns the floor half is not a distinction.
    #:
    #: What survives is weaker than it looked: the absolute form has no division
    #: hazard (there is no ``_pct`` sibling and none is asked for) and the
    #: comparison stays derivable downstream.  Those were reasons it was *cheap*
    #: to omit, never reasons it was wrong to publish.
    inventory_cap_wei: int | None
    cap_decay_tokens_per_day_wei: int | None
    keeper_reward_wei: int | None
    #: --- position --------------------------------------------------------
    tick_spacing: int | None
    tick_lower: int | None
    tick_upper: int | None
    ref_tick: int | None
    current_tick: int | None
    current_sqrt_price_x96: int | None
    position_liquidity: int | None
    eth_in_pool_wei: int | None
    tokens_in_pool_wei: int | None
    #: --- counters --------------------------------------------------------
    total_burned_wei: int | None
    total_rewarded_wei: int | None
    total_fee_token_wei: int | None
    retained_eth_wei: int | None
    last_claim_block: int | None
    #: --- the token's own supply, read off ``token()``, not off the hook ---
    total_supply_wei: int | None = None
    block_number: int | None = None


@dataclass(frozen=True, slots=True)
class Pool4VaultState:
    """``StakedIMD`` (sIMD) -- Solady ``ERC4626`` + ``Ownable``, verified source.

    No emissions and no rebase: reward IMD is transferred in, ``totalAssets``
    rises and every share is worth more, so there is no claim step and no
    per-holder accrual for this model to carry.

    **This vault is not an 18-decimal token, and that is the single most
    dangerous fact in this class** (amendment A14, verified live).  Solady's
    ``ERC4626`` reports ``asset decimals + _decimalsOffset()``, and
    ``StakedIMD._decimalsOffset()`` is 6, so ``decimals()`` returns **24**.
    One whole ``sIMD`` is ``1e24`` units, not ``1e18``.

    Both halves of the habitual ``/ 1e18`` are wrong by a factor of a million,
    and **both wrong forms render as entirely plausible numbers**, which is why
    nothing downstream would catch them::

        convertToAssets(1e18) / 1e18 = 0.000001302985528554   # reads as a dead vault
        convertToAssets(1e24) / 1e18 = 1.302985528554         # pool4_share_price
        total_shares / 1e18 = 21,010,977,789.12 sIMD          # reads as an emissions farm
        total_shares / 1e24 =         21,010.98 sIMD          # pool4_vault_shares

    Cross-check: ``total_assets`` 27,377.00 / 21,010.98 = 1.302986.

    Two consequences are wired into the field list below rather than left to a
    reader's care:

    * ``decimals`` is **read from the chain, never assumed to be 24.**  The
      mainnet vault does not exist yet and nothing binds its
      ``_decimalsOffset()`` to Sepolia's.  A constant 24 would reproduce this
      exact defect at the switchover, silently and plausibly -- which is the
      house rule "read values live, never hardcode a documented one" in its
      most literal form.  The divisor for shares is ``10 ** decimals``, and it
      is ``None``-guarded like every other read.
    * ``total_shares_raw`` does **not** end ``_wei``, and that asymmetry is
      deliberate.  Everything suffixed ``_wei`` in this module divides by
      ``1e18``; shares do not.  Two adjacent ``_wei`` fields with two different
      divisors is precisely the habit-trap that produced A14, so the share
      count is spelled differently on purpose and there is no symmetry to lean
      on.

    ``share_price_wei`` is ``convertToAssets(10 ** decimals)`` -- assets per
    **one whole share**, the raw answer rather than a ratio.  It keeps the
    ``_wei`` suffix correctly: its result is an *asset* amount (18-decimal
    IMD), so the manager divides it by ``1e18`` exactly once into
    ``pool4_share_price``.  It is read rather than derived from
    ``total_assets_wei / total_shares_raw`` because the decimals offset makes
    those two quantities not directly divisible, and the contract's own
    conversion is the only correct one.

    ``owner`` and ``paused`` are the trust surface the source states plainly:
    while the owner has not renounced, ``setPaused`` stops every entry point and
    ``rescueERC20`` can move the staked IMD itself -- the source comment calls
    it "a deliberate 'move funds to safety in a worst case' hatch, not a
    trustless design".  Whether the *mainnet* owner has renounced is a live read
    the dashboard shows, never an assumption, which is why ``owner`` is a raw
    address here and the renounced/live wording is derived downstream.
    """

    name: str | None
    symbol: str | None
    #: ``decimals()`` -- 24 on Sepolia (18 asset + 6 offset). READ, never
    #: assumed; ``10 ** decimals`` is the divisor for ``total_shares_raw`` and
    #: the argument to ``convertToAssets``.
    decimals: int | None
    asset: str | None
    owner: str | None
    paused: bool | None
    #: 18-decimal IMD, like every other ``_wei`` field here.
    total_assets_wei: int | None
    #: Raw ``totalSupply()`` in share units -- divide by ``10 ** decimals``,
    #: NOT by ``1e18``. Named ``_raw`` rather than ``_wei`` so the difference
    #: is visible at every call site.
    total_shares_raw: int | None
    share_price_wei: int | None
    block_number: int | None = None


@dataclass(frozen=True, slots=True)
class Pool4DripperState:
    """``RewardDripper`` -- verified source.  Holds the lumpy reward share and
    releases ``min(rate x min(elapsed, maxCatchup), balance)``.

    ``balance_wei`` is the dripper's own IMD balance -- the **backlog**, the
    thing that makes this panel worth drawing.  Idle time beyond
    ``max_catchup_seconds`` is forfeited rather than banked, so one ``drip()``
    after a long quiet spell can never dump the buffer, and the vault's yield is
    therefore **rate-limited, not flow-limited**: sIMD APR is a function of
    ``drip_rate_per_second_wei`` and vault TVL and never of what the pool
    earned.  ``pool4_backlog_days`` is that sentence as a number.

    ``drippable_wei`` and ``can_drip`` are the contract's own answers about
    *right now* and both have a representable zero/``False``: "nothing is
    drippable this instant" is a real answer, distinct from ``None``.

    ``vault`` is where the vault address comes from -- ``vault()`` on this
    contract.  **How many hops away this contract is depends on the network,
    and that is the one mainnet change that is not self-adapting:**

    * Sepolia: ``hook.rewardsRecipient()`` -> Dripper -> ``dripper.vault()``.
    * Mainnet: ``hook.rewardsRecipient()`` -> **Distributor** ->
      ``distributor.dripper()`` -> Dripper -> ``dripper.vault()``.

    A two-hop reader calls ``vault()`` on the Distributor, which has no such
    method, and the vault and dripper reads then fail outright.  The hop count
    must be discovered from what each address answers, never assumed from the
    Sepolia shape.

    It is read off chain and never scraped from a page.  That is unchanged and
    is *not* softened by the operator's 2026-09-02 decision to accept the
    documentation page as a **candidate address source** for discovery: a
    candidate is an address the chain fingerprint then interrogates, whereas
    scraping a value would be taking the page's word for a number no one
    checked.  The first is a nomination, the second is a fabrication.
    """

    vault: str | None
    token: str | None
    owner: str | None
    drip_rate_per_second_wei: int | None
    max_catchup_seconds: int | None
    min_drip_amount_wei: int | None
    keeper_reward_wei: int | None
    drippable_wei: int | None
    can_drip: bool | None
    balance_wei: int | None
    block_number: int | None = None


@dataclass(frozen=True, slots=True)
class Pool4DistributorState:
    """The Reward Distributor -- **mainnet only, no Sepolia counterpart**.

    On Sepolia ``hook.rewardsRecipient()`` was the Dripper.  On mainnet it is
    this contract, which splits the reward share three ways before the staking
    leg reaches the Dripper at all.  That is why the vault is **three hops
    away** on mainnet and two on Sepolia -- see :class:`Pool4DripperState`.

    Recovered interface: ``stakingBps() nftBps() dripper() asset() owner()
    distribute() stakingEarned() bondingEarned() nftEarned() heldBonding()
    heldNft() setDripper(address) emergencyWithdraw(address)``.

    **There is no ``bonding_bps`` field, and that absence is the point.**
    Bonding has no getter: it is the *remainder*,
    ``BPS_DENOMINATOR - stakingBps - nftBps``.  This model carries what the
    client read and nothing else, so the derivation lives in the manager, is
    published as ``pool4_distributor_bonding_bps``, and is **labelled derived
    on screen** -- the ``cap_floor``/*observed* precedent.  A field here would
    be a number with no getter behind it, which is how a hardcoded ``4000``
    gets typed in and then goes stale in silence the day the split moves.  The
    honest signature of a derived value is that it goes ``None`` whenever
    *either* input does, exactly like ``pool4_split_drift_bps``.

    **``nft`` here is ``nodes`` in the payload**, and that is the module's
    stated naming discipline rather than a slip: *model fields mirror the
    chain, flat-dict keys mirror the docs* -- the same split that makes
    ``identityAllowed()`` the field ``identity_allowed`` and the key
    ``gate_open``.  The chain says ``nftBps()``/``nftEarned()``/``heldNft()``;
    the project's documentation calls them **nodes**, the NFT-holding compute
    daemons.  The manager's mapping table is the single translation point.

    ``held_bonding_wei``/``held_nft_wei`` are IMD sitting here awaiting
    ``distribute()``, and both have a **representable zero** -- 0 means
    distributed up to date.  There is deliberately no ``held_staking``: the
    staking leg is forwarded onward rather than held, and inventing a field for
    a getter that does not exist would invite a producer to fill it with a
    plausible zero.
    """

    staking_bps: int | None
    nft_bps: int | None
    dripper: str | None
    asset: str | None
    owner: str | None
    staking_earned_wei: int | None
    bonding_earned_wei: int | None
    nft_earned_wei: int | None
    held_bonding_wei: int | None
    held_nft_wei: int | None
    block_number: int | None = None


@dataclass(frozen=True, slots=True)
class Pool4FlowEvent:
    """One swap's worth of hook activity, wire-level.

    Sourced from the hook's own logs -- ``FeeCollected``, ``ClaimsSettled`` and
    the accrual topic whose pre-image was not found -- joined per transaction.

    ``burned_wei`` and ``stakers_wei`` are ``int``, **not** ``int | None``, and
    that is the load-bearing decision in this class.  A buy has no burn leg and
    no staker leg, and that is a *representable zero*: ``0`` renders as
    ``0.00``.  ``None`` is reserved one level up, for ``pool4_flow`` itself
    being ``None`` -- the whole-panel unavailable state.  Collapsing the two is
    the FARM/HOUR-SAVED defect this repo already shipped once, where a panel
    read confident and green straight through an outage.

    ``fee_token_wei`` and ``fee_eth_wei`` are the two legs of ``FeeCollected``
    and are genuinely exclusive: the 1% is taken in ETH on a buy and in IMD on a
    sell, so exactly one of them is a number on a well-formed row and ``None``
    on the other means "the fee was not taken in this currency", not "unread".

    ``settled`` is ``False`` for an accrual that ``ClaimsSettled`` has not paid
    out yet.  Settlement is opportunistic -- it rides the next swap, and
    ``settleClaims()`` is the permissionless way to force it -- so an unsettled
    row is an ordinary steady-state row, never an error.

    ``size_wei`` is IMD in on a sell and IMD out on a buy; it is one field
    because the ``side`` beside it already says which.  There is no ``age_s``:
    the model is clock-free and the manager precomputes the age, so a committed
    capture replays forever.
    """

    tx_hash: str | None
    ts: float | None
    block_number: int | None
    side: str | None
    size_wei: int | None
    burned_wei: int
    stakers_wei: int
    fee_token_wei: int | None
    fee_eth_wei: int | None
    settled: bool


@dataclass(frozen=True, slots=True)
class Pool4Discovery:
    """The verdict on where pool4 lives -- and a **security boundary**.

    The mainnet hook is not shipped hardcoded because it did not exist when
    this was written.  It is discovered from the announce channel, which is
    permissionless and attacker-writable, so this class records the outcome of
    two gates and never merely an address:

    * **provenance -- the only unforgeable one** -- candidates come from
      announce-wallet *self-posts* only (``from_addr == to_addr == ANNOUNCE``).
      A reply or an inbound tx from a stranger carrying a plausible address
      yields no candidate at all.  Forging this costs the announce wallet's
      private key; forging anything else below costs a few seconds of CPU.
    * **fingerprint** -- the candidate's v4 permission bits must equal the
      required mask exactly (equality, never a subset test: a subset admits a
      hook that does not gate pool initialisation, and one that sets a
      RETURNS_DELTA bit, both materially different contracts), and its
      ``token()`` must be the known mainnet IMD.

      **The mask is WP3's, in ``data/surf_pool4.py``, and its value is fixed
      by amendment A8.  This docstring deliberately does not restate it, and a
      test asserts that it does not.**  An earlier draft of this paragraph
      named the bits and named the wrong ones, because it read the hook
      address's *tail* as the permission field.  The tail is a **mined vanity
      string**; the field is the low fourteen bits, and they are not the same
      -- reading one for the other drops a permission.  A gate built from that
      wording **rejects the real hook, so pool4 would never be discovered on
      any chain**.

      Two authorities for one constant is how the wrong one survives, so there
      is one: A8, which also records ``getHookPermissions()`` agreeing with
      each address's own low fourteen bits across all three Sepolia launches --
      the contract asked directly, rather than arithmetic done on an address.

    ``state`` is one of :data:`POOL4_DISCOVERY_STATES` and ``detail`` names the
    *first* gate a candidate failed -- one line of pattern language, third-party
    derived, escaped at render.  The curator ``pattern_language()`` precedent
    applies **here**, to this string: text read back from a persisted payload is
    third-party input and is re-checked before it is rendered.  It used to be
    cited two paragraphs down as grounds for re-verifying a stored *address*,
    which is a different claim it never supported -- sanitising text you must
    display is not the same as admitting an address to a security decision.

    ``hook_addr`` is populated on ``adopted`` and is ``None`` otherwise; a
    ``rejected`` verdict deliberately does not carry the address forward, so no
    downstream read can be pointed at it by a stale field.

    **The fingerprint narrows the field; it does not make a candidate
    trustworthy.**  It is forgeable by construction and two packages measured
    that independently: an address with the right permission bits was mined in
    ~16,000 tries by the security pass and in **20,141 tries, in under a
    second**, by WP3.  Four of the five getters it checks are pure liveness --
    any contract that answers at all passes them -- and ``token()`` is a value
    the candidate's own contract chooses.  A mined address in front of a
    contract that returns the real mainnet IMD and nothing else is adopted.  So
    the fingerprint's job is to reject *mistakes and lookalikes*, and the thing
    standing between this field and an attacker is the signature on the
    self-post, nothing else.

    **Nothing is ever adopted from storage** (amendment A27).  A persisted
    address is not in the candidate set at all -- not tried first, not tried
    last, not re-verified -- and discovery re-runs from the channel every time.
    This paragraph used to promise the opposite -- that a hand-edited cache
    entry was re-checked before use and therefore safe.  That promise held only
    against the committed fixture, whose flag word is all zeros; against anyone
    actually trying, the re-check returned ``adopted``.  The re-verification helper was
    deleted rather than documented, because a reassuring sentence attached to a
    defence a demo defeats in twenty seconds is worse than no sentence -- it is
    what someone finds when they grep for the cache-file protection.

    The known pressure on this, named so it can be refused on its merits: the
    self-post can age out of the channel window (~64 days measured), and
    discovery then loses a genuinely adopted hook.  **The fix is to read more
    channel history, or to re-establish provenance from the chain via
    ``source_tx_hash`` -- never to re-nominate from storage**, which would trade
    a paging bug for the provenance bypass A27 closed.

    ``source_tx_hash`` is the self-post the candidate came from, and after A27
    it is **the only pointer to the only evidence**: provenance is the sole
    unforgeable gate, so the transaction that carries the signature is the one
    artifact an adoption can be checked against by hand.

    Who fills it, and when:

    * **The discovery layer populates it on every verdict that had a
      candidate** -- adopted, rejected and the no-flagged-candidate case alike
      -- because a rejection is worth citing too.  It is ``None`` only when no
      candidate existed at all, or when the read never got that far.
    * **The manager persists it beside the verdict and publishes it as
      ``pool4_discovery_source_tx`` -- its own key, never appended to
      ``pool4_discovery_detail``.**  An earlier version merged the two, and the
      merge is what guaranteed the citation would be lost: a 66-character hash
      on the tail of a ~94-character sentence is the first thing any fitting
      pass drops, and after A27 the tail is the load-bearing half.  Truncating
      it deletes the only unforgeable evidence and keeps the address, which the
      reader could already see four lines below.  Two keys let the renderer give
      the citation its own line at a width it controls.

    **``None`` means no citation is available, and what that means is read
    against ``state``** -- the pair is always published together, so no second
    key is needed to disambiguate:

    * ``not-discovered`` + ``None`` -- nothing to cite yet.  Expected.
    * ``rejected`` + a hash -- the rejection cites the post it judged.
    * ``adopted`` + a hash -- the audit trail exists; this is the healthy case.
    * ``adopted`` + ``None`` -- **an adoption nothing can audit.**  It is the
      one combination worth surfacing, and it is expressible precisely because
      the two keys are separate.

    It is also the **only A27-compatible answer to S15**: the self-post ages out
    of the channel window at ~64 days, and when it does, discovery loses a
    genuinely adopted hook.  The two available fixes are to read more channel
    history (unbounded, and it grows forever) or to re-establish provenance from
    this hash (constant cost -- a transaction does not age out).  Re-nominating
    from storage is not a third option; that is the bypass A27 closed.

    **Persisting the hash makes re-establishment possible, not safe.**  A
    re-establishment must re-read that transaction *from the chain* and re-check
    the signer.  Trusting the stored address because a hash sits next to it is
    A27's bypass wearing a new hat, and the hash is not a credential -- it is a
    pointer to one.
    """

    network: str | None
    state: str | None
    detail: str | None = None
    hook_addr: str | None = None
    token_addr: str | None = None
    source_tx_hash: str | None = None


#: The pool4 block of :data:`SURF_KEYS`, declared separately because five work
#: packages code against it in parallel and a tuple they can all import is what
#: makes a rename a collection error instead of a silent ``None`` panel.
#:
#: **62 keys: 60 scalars plus the two list keys.**  (43 + 2 at the freeze;
#: ``pool4_counter_state`` and ``pool4_counter_detail`` joined with finding W1,
#: which wired R1 control (c) rather than retiring it; then
#: ``pool4_discovery_source_tx``, which stopped the citation being merged into
#: a sentence that truncates.  Twelve more landed with the mainnet deployment
#: on 2026-09-02: the Distributor's three-way split (nine), the ratchet's
#: ceiling half (two), and ``pool4_discovery_source`` (one).  Then
#: ``pool4_reward_path``, because the Distributor's *presence* is a fact no
#: address can state -- see :data:`POOL4_REWARD_PATHS`.  Then
#: ``pool4_cap_headroom``, on evidence that retired the grounds it had twice
#: been refused on.)  ``pool4_flow`` and
#: ``pool4_hatches`` are members here as well as in :data:`SURF_ROW_KEYS`,
#: exactly as ``feed_items`` and ``launchpad_coins`` are -- the row-shape dict
#: describes the shape of a row, it does not excuse the key from the payload
#: contract, and ``test_row_key_sets_match_the_prd`` asserts the containment.
#:
#: Order is the order the panels render in, and it is the order these are
#: spliced into ``SURF_KEYS``: discovery/addresses, THE SPLIT, THE RATCHET,
#: sIMD VAULT, then the two row payloads.
POOL4_KEYS: tuple[str, ...] = (
    # ---- network, discovery and addresses (SurfPool4Hatches, + every title) --
    "pool4_network",            # str | None — POOL4_NETWORKS; None = never swept
    "pool4_as_of_hhmm",         # str | None — this tier's own slower clock
    "pool4_discovery_state",    # str | None — POOL4_DISCOVERY_STATES
    "pool4_discovery_detail",   # str | None — pattern language; escaped at render
    # The self-post an adoption rests on, published BESIDE the detail and never
    # merged into it. Appending it to the sentence is what guaranteed it fell
    # off: after A27 the citation is the only unforgeable evidence in the
    # design, so any tail-truncation deletes the evidence and keeps the address
    # the reader could already see four lines below.
    "pool4_discovery_source_tx",  # str | None — pointer, not credential
    # WHICH source nominated the adopted address. Disclosure is the whole
    # mitigation for accepting a second, weaker candidate source, so this is
    # never optional on an adoption and None must never render as "self-post".
    "pool4_discovery_source",     # str | None — POOL4_DISCOVERY_SOURCES
    "pool4_hook_addr",          # str | None — adopted (mainnet) or vendored (sepolia)
    "pool4_token_addr",         # str | None — IMD on the active network
    "pool4_vault_addr",         # str | None — read off chain, never scraped
    # On mainnet ``rewardsRecipient()`` is the Distributor and the Dripper is a
    # hop further on; on Sepolia there is no Distributor and this is None. The
    # hop count is discovered from what each address answers, never assumed.
    # ``None`` here is ambiguous ON PURPOSE and must not be read as topology:
    # it is both "no Distributor" and "rewardsRecipient() unread". The fact a
    # panel needs is ``pool4_reward_path`` beside it, which has a word for
    # "unknown" that an address cannot express.
    "pool4_distributor_addr",   # str | None — the address, when one was read
    "pool4_reward_path",        # str | None — POOL4_REWARD_PATHS; None = unknown
    "pool4_dripper_addr",       # str | None — distributor.dripper(), or the hook's
    # ---- THE SPLIT (SurfPool4Split) -----------------------------------------
    "pool4_measured_inference_pct",  # float | None — from live counters, never quoted
    "pool4_measured_burn_pct",       # float | None — ditto
    "pool4_measured_stakers_pct",    # float | None — ditto
    "pool4_reward_share_bps",        # int | None — rewardShareBps(), the *claimed* share
    "pool4_bps_denominator",         # int | None — BPS_DENOMINATOR()
    "pool4_split_drift_bps",         # float | None — measured minus claimed; 0.0 is healthy
    "pool4_total_burned",            # float | None — whole IMD
    "pool4_total_rewarded",          # float | None — whole IMD
    "pool4_total_fee_token",         # float | None — whole IMD
    "pool4_retained_eth",            # float | None — whole ETH
    "pool4_last_claim_block",        # int | None
    "pool4_unsettled_burn",          # float | None — accrued-but-unsettled; 0.0 = settled
    "pool4_unsettled_stakers",       # float | None — ditto, staker leg
    # R1 control (c). ``None`` = the check has never run, exactly like every
    # other key here; a *word* is the only thing that ever means "we looked".
    "pool4_counter_state",           # str | None — POOL4_COUNTER_STATES
    "pool4_counter_detail",          # str | None — which counter, by how much
    # ---- the Reward Distributor's three-way split (mainnet only) ----------
    # ``nodes`` is the chain's ``nft``: model fields mirror the chain, payload
    # keys mirror the docs (the identityAllowed -> gate_open precedent).
    # Every one of these is None on a deployment with no distributor, which is
    # a real answer about the topology, not a failed read.
    "pool4_distributor_staking_bps",     # int | None — stakingBps()
    "pool4_distributor_nodes_bps",       # int | None — nftBps()
    # DERIVED remainder: denominator − staking − nodes. No getter exists for
    # it. None whenever either input is unread; labelled derived on screen.
    "pool4_distributor_bonding_bps",     # int | None
    "pool4_distributor_staking_earned",  # float | None — whole IMD, cumulative
    "pool4_distributor_nodes_earned",    # float | None — whole IMD, cumulative
    "pool4_distributor_bonding_earned",  # float | None — whole IMD, cumulative
    # Awaiting distribute(). 0.0 = distributed up to date, a representable
    # zero. There is no held_staking: that leg is forwarded, not held.
    "pool4_distributor_held_nodes",      # float | None — whole IMD
    "pool4_distributor_held_bonding",    # float | None — whole IMD
    # ---- THE RATCHET (SurfPool4Ratchet) -------------------------------------
    "pool4_tokens_in_pool",     # float | None — the reserve, whole IMD
    "pool4_cap_floor",          # float | None — observed, labelled inferred
    # The ceiling half of the ratchet. The docs describe buys as lowering the
    # inventory cap, and it currently sits ON the inventory -- on BOTH chains
    # (D13), so it tracks the reserve rather than binding it today.
    "pool4_inventory_cap",      # float | None — whole IMD
    # cap − reserve. NOTE THE OPERAND ORDER: floor_distance is reserve − floor,
    # this is the mirror, so both are positive when healthy. Writing it as
    # "reserve − X" by analogy inverts the sign and renders a binding cap as
    # slack. A negative is real (inventory above the cap) and renders.
    "pool4_cap_headroom",       # float | None — whole IMD
    # A rate of 2**128-1 wei/day is the "no decay" sentinel Sepolia carries,
    # not a number: ~3.4e20 whole IMD/day. The producer resolves it to the
    # unavailable/no-decay state; a panel must never print it. None stays the
    # ordinary failed read.
    #
    # PRE-IDENTIFIED FOLLOW-UP, recorded so nobody re-derives it: "binds in
    # days" is pool4_cap_headroom / this rate, and it is the more actionable
    # form -- 94.68 IMD over 1,000/day is the cap binding in ~2.3 hours. It is
    # NOT a key: no panel has asked for one, and inventing it now is exactly
    # the surface-by-symmetry this contract refuses. Its hazard is worse than
    # backlog_days' zero denominator, though, so it is named here rather than
    # left to be discovered: on the sentinel, 94.68 / 3.4e20 is ~2.8e-19 days,
    # which reads as *binds now* when the truth is *never binds*. That is a
    # sign-of-meaning inversion, not a missing value, so whoever builds it must
    # resolve the sentinel BEFORE dividing rather than guard against zero.
    "pool4_cap_decay_per_day",  # float | None — whole IMD per day
    "pool4_floor_distance",     # float | None — reserve − floor; a negative is real
    "pool4_floor_distance_pct", # float | None — None on a 0/unread floor, never an infinity
    "pool4_burned_supply_pct",  # float | None — total_burned / total_supply * 100
    "pool4_total_supply",       # float | None — whole IMD
    "pool4_reserve_series",     # list[list[float]] | None — [[ts, imd], …]; [] = swept empty
    "pool4_eth_in_pool",        # float | None — whole ETH
    "pool4_position_liquidity", # float | None — raw uint128 L, not an amount
    "pool4_current_tick",       # int | None
    "pool4_ref_tick",           # int | None
    "pool4_backstop_centred",   # bool | None — tri-state; None is neither answer
    # ---- sIMD VAULT (SurfPool4Vault) ----------------------------------------
    "pool4_share_price",           # float | None — convertToAssets(1e18) / 1e18
    "pool4_share_price_delta_pct", # float | None — None until a second reading exists
    "pool4_vault_assets",          # float | None — TVL, whole IMD
    "pool4_vault_shares",          # float | None — whole sIMD
    "pool4_drip_per_day",          # float | None — dripRatePerSecond() * 86400
    "pool4_drippable",             # float | None — whole IMD
    "pool4_can_drip",              # bool | None — tri-state
    "pool4_backlog_imd",           # float | None — the dripper's own IMD balance
    "pool4_backlog_days",          # float | None — None on a 0/unread rate, never an infinity
    "pool4_implied_apr_pct",       # float | None — from drip rate and TVL only, never fee flow
    # ---- the two row payloads -----------------------------------------------
    "pool4_flow",       # list[dict] | None — SURF_ROW_KEYS["pool4_flow"]
    "pool4_hatches",    # list[dict] | None — SURF_ROW_KEYS["pool4_hatches"]
)


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
    "launchpad_activity",     # list[dict] | None — None means the sweep failed
    "launchpad_burnkeepers",  # list[dict] | None
    "launchpad_as_of_hhmm",         # str | None — slower tier's own staleness marker
    # ---- pool4 (detached sweep, its own slower "as of") ---------------------
    # One contiguous block, unpacked from POOL4_KEYS above rather than retyped:
    # five work packages import that tuple, and a hand-copied second spelling
    # here is exactly the drift the splice is meant to make impossible.
    *POOL4_KEYS,
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
        "mcap_eth",
        "mcap_usd",
        "change_24h_pct",
        "swaps_24h",
        "swaps_all",
        "imd_burned",
    ),
    "launchpad_activity": (
        "kind",          # "buy" | "sell" | "launch" -- closed, producer-owned
        "ticker",        # str  -- attacker-chosen, raw here, escaped at render
        "wallet",        # str  -- trader on a swap, creator on a launch
        "wallet_known",  # bool -- KNOWN_LABELS allowlist, never a blocklist
        "eth",           # float | None -- swap size; None on a launch
        "age_s",         # float | None
    ),
    "launchpad_burnkeepers": (
        "wallet",
        "wallet_known",
        "imd_burned",    # float -- representable zero, from logs
        "eth_paid",      # float | None -- LayerZero nativeFee; None if unread
        "burns",         # int   -- call count
    ),
    # ``burned_imd``/``stakers_imd`` are ``float`` and NOT ``float | None``:
    # a buy has neither leg and that is a representable ``0.0``. ``None`` is
    # reserved for ``pool4_flow`` itself, the whole-panel unavailable state.
    # Rendering the two the same way is the FARM/HOUR-SAVED defect this repo
    # already shipped once -- a panel that read confident and green through an
    # outage -- and it is the most likely way this row ships wrong.
    #
    # ``fee_imd``/``fee_eth`` are exclusive rather than redundant: the 1% is
    # taken in ETH on a buy and in IMD on a sell, so ``None`` on one of them
    # means "not taken in this currency", never "unread".
    #
    # ``age_s`` is precomputed by the manager. The screen and the widget are
    # clock-free, so a committed capture replays forever.
    "pool4_flow": (
        "ts",           # float | None -- epoch
        "age_s",        # float | None -- precomputed; the widget never reads a clock
        "side",         # str   -- POOL4_FLOW_SIDES, closed, producer-owned
        "size_imd",     # float | None -- IMD in on a sell, IMD out on a buy
        "burned_imd",   # float -- ClaimsSettled[0]; 0.0 on a buy, never None
        "stakers_imd",  # float -- ClaimsSettled[1]; same rule
        "fee_imd",      # float | None -- FeeCollected IMD leg; None when taken in ETH
        "fee_eth",      # float | None -- FeeCollected ETH leg; None when taken in IMD
        "settled",      # bool  -- False = accrued, ClaimsSettled has not paid it yet
        "tx_hash",      # str | None
    ),
    # ``pool4_hatches`` is ``None`` when unread; ``[]`` is never emitted,
    # because the BOND row always exists -- no bond contract is deployed
    # anywhere a reader can check, and the panel has to say so rather than
    # omit the row and let its absence read as "nothing to report".
    #
    # ``addr_known`` is the ``KNOWN_LABELS`` allowlist and nothing else: never
    # a blocklist, never a fallback, never a prefix match. An address that is
    # merely address-shaped is not known.
    "pool4_hatches": (
        "scope",       # str  -- POOL4_HATCH_SCOPES
        "label",       # str  -- POOL4_HATCH_LABELS
        "state",       # str  -- POOL4_HATCH_STATES
        "detail",      # str | None -- third-party derived; escaped at render
        "addr",        # str | None -- rendered through _fmt.long_addr
        "addr_known",  # bool -- KNOWN_LABELS allowlist only
    ),
}
