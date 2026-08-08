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

from dataclasses import dataclass, field

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
