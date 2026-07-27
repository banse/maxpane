"""Frozen interface for the Fake World Assets (FWA) "Gacha Terminal" dashboard.

This module is **boundaries only**. It imports nothing but ``pydantic`` and the
standard library — no client, no cache, no analytics, no Textual. Every other FWA
module codes against what is declared here, and nothing declared here may change
without an explicit contract amendment (see ``docs/fwa_implementation_plan.md``
§8.5 and risk R9).

It freezes three things:

1. **Ten frozen Pydantic models** — the typed shapes the data layer passes around.
2. :data:`FWA_DATA_KEYS` — every key ``FWAManager.fetch_and_compute()`` returns.
3. :data:`FWA_WIDGET_SIGNATURES` — the exact ``update_data()`` kwargs of the seven
   widgets, plus :data:`FWA_ROW_KEYS` for the list-of-dict payloads.


Unit discipline (non-negotiable)
--------------------------------

**Models are wei-native. The flat dict is the presentation boundary.**

* Every wei quantity on a model is an ``int``, declared as :data:`Wei`, which is a
  *strict* int — passing a ``float`` raises ``ValidationError`` rather than being
  silently truncated. There is no such thing as a fractional wei.
* Wei → ETH conversion happens exactly once, in the manager, when it builds the
  flat dict. That is why the models carry ``backing_wei`` / ``pot_wei`` /
  ``amount_wei`` while the flat-dict rows carry ``eth_backed`` / ``crown_pot_eth``
  / ``amount_eth``.
* ``floor_eth`` and the DexScreener/GeckoTerminal figures are the exception: they
  originate off-chain as decimal ETH/USD quotes and were never wei.

All models are ``frozen=True`` **and** ``extra="forbid"``: they cannot be mutated
after construction and cannot be constructed with a field that is not declared
here. The second half is what makes :class:`PullEV` structurally honest (below).


The four traps this contract encodes
------------------------------------

1. **Weight is INVERSE to backing.** ``weight = INVERSE_WEIGHT_NUMERATOR // backing``
   where ``INVERSE_WEIGHT_NUMERATOR == 1e36`` — verified against all 3,867 live
   positions with 0 mismatches. Cheap positions dominate the draw; rich positions
   are effectively unreachable (CryptoPunks: 137.10 ETH across 3 positions for
   **0.000%** of the weight). Any proportional-weighting assumption is wrong, and
   ``Position.weight`` is therefore never derived by multiplying anything.

2. **``settlementDiscountBps() == 8500`` is the purchaser PAYOUT rate, not a
   discount.** Accepting the standing bid pays the purchaser **85%** of the
   position's backing — it does not take 15% off anything. The name is an on-chain
   naming trap; do not invert it. In this codebase it is called
   ``purchaser_payout_bps`` and nowhere is 8500 described as a discount.

3. **``weighted_backing_total`` is neither wei nor ETH, and is never TVL.** It is
   ``Σ(weight × backing) ≈ active_listing_count × 1e36`` — a dimensionless
   accumulator used only inside the ``acquisitionFee()`` derivation. It is
   deliberately **absent from** :data:`FWA_DATA_KEYS` so no widget can render it.
   The only source for "ETH held by the protocol" is ``eth_getBalance(core)``,
   surfaced as ``core_balance_eth``.

4. **``PoolTemp.forced_share_bps`` is a SIGNED int256.** ``-1`` means "dynamic —
   the surcharge split is computed from the pool temperature". Any value ``>= 0``
   is an owner override pinning the split, and the UI must say so. Decoding it as
   an unsigned uint256 yields ``2**256 - 1``; that is a bug, not a huge share.


The EV band is structural, not a convention
-------------------------------------------

Keyless floor prices reach 26 of the 38 collections that hold live positions, but
the two largest weight buckets are unpriced, so those 26 carry only ~20% of the
draw weight (findings §13.14). A single confident EV number would therefore be a
lie that costs someone ETH. Both counters are measured per sweep, never assumed.

:class:`PullEV` has ``lower_eth`` and ``best_eth`` as *required* fields and, thanks
to ``extra="forbid"``, **cannot be given a ``point_eth`` / ``value_eth`` /
``ev_eth`` field at all** — not by a subclass edit, not by a well-meant kwarg. A
downstream agent is physically unable to render a single confident EV figure. The
coverage counters (``collections_priced`` / ``collections_total`` /
``weight_priced_pct``) are likewise required, so the badge can never go missing
while a number is on screen.


Naming deltas from the implementation-plan §8.5 draft
-----------------------------------------------------

The draft key names were indicative; the names below are final.

===========================  =====================================================
Draft                        Final
===========================  =====================================================
``pull_ev_best``             ``pull_ev_best_eth``      (unit made explicit)
``pull_ev_lower``            ``pull_ev_lower_eth``     (unit made explicit)
``ev_coverage_collections``  ``ev_collections_priced`` + ``ev_collections_total``
``ev_coverage_weight_pct``   ``ev_weight_priced_pct``  (matches ``PullEV`` field)
``eth_in_core``              ``core_balance_eth``      (``eth_getBalance(core)``)
===========================  =====================================================

Added since the draft: ``crown_vacant``, ``ev_rebate_eth``, ``chase_available``,
``feed_as_of_ts``, ``settle_as_of_ts``, ``crown_listing_id``. Removed: nothing —
plus ``weighted_backing_total`` was never a key and must not become one (trap 3).

``crown_listing_id`` was added in wave 3: the crown and the max-backing position
can be the same listing (they were at block 25612701), and ``FWAChaseBoard`` can
only flag that coincidence if it is told which listing wears the crown. It is a
data key but **not** a widget-signature kwarg — the board takes it as an optional
extra, so the frozen two-kwarg payload still renders and the note stays dark
without it.


Settlement outcomes
-------------------

``SettlementMix.outcome`` and ``DrawEvent.outcome`` use these five stable machine
keys; ``outcome_label`` carries the human string:

* ``"bid_fwa"``   — accept bid, paid in $FWA   (73.92% of all settlements)
* ``"bid_eth"``   — accept bid, paid in ETH    (13.84%)
* ``"relist"``    — purchaser becomes depositor (7.64%)
* ``"kept"``      — keep the NFT               (4.60%)
* ``"forced"``    — force-finalized            (0.00%)

~88% sell straight back. Almost nobody wants the art.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    # scalar aliases
    "Wei",
    "Weight",
    # models
    "Position",
    "CollectionOdds",
    "PullEV",
    "Crown",
    "PoolTemp",
    "ConfigParam",
    "SettlementMix",
    "FWASignal",
    "DrawEvent",
    "FWASnapshot",
    # the frozen contract
    "FWA_DATA_KEYS",
    "FWA_WIDGET_SIGNATURES",
    "FWA_ROW_KEYS",
    "FWA_SETTLEMENT_OUTCOMES",
    "INVERSE_WEIGHT_NUMERATOR",
]


# ---------------------------------------------------------------------------
# Scalar aliases
# ---------------------------------------------------------------------------

Wei = Annotated[int, Field(strict=True)]
"""A wei-denominated integer.

Strict on purpose: ``Position(backing_wei=1e18)`` raises rather than quietly
accepting a float that has already lost precision. There are no fractional wei,
and 1e18-scale values exceed float64's exact-integer range anyway.
"""

Weight = Annotated[int, Field(strict=True)]
"""A 1e36-scaled inverse draw weight (``1e36 // backing_wei``).

Dimensionless — not wei, not ETH. Strict for the same reason as :data:`Wei`:
a float here silently destroys the bit-exactness the fee derivation depends on.
"""

INVERSE_WEIGHT_NUMERATOR = 10**36
"""``weight = INVERSE_WEIGHT_NUMERATOR // backing_wei``. Read live where it matters;
this constant exists so the *rule* is greppable, never as a substitute for chain data.
"""

FWA_SETTLEMENT_OUTCOMES: tuple[str, ...] = (
    "bid_fwa",
    "bid_eth",
    "relist",
    "kept",
    "forced",
)
"""Stable machine keys for the five settlement outcomes (see module docstring)."""


_FROZEN = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------------------
# Models — PRD §6's seven
# ---------------------------------------------------------------------------


class Position(BaseModel):
    """One live listing: an NFT deposited with committed ETH backing.

    Mirrors the on-chain ``listings(uint256)`` flat 11-tuple plus its id. The tuple
    is all-static-types, head-only encoded, 352 bytes — the Talismans dynamic-tuple
    decode trap does not apply, but the decode is still fixture-asserted (PRD §7
    rule 10).

    * ``weight`` is **inverse**: ``1e36 // backing_wei``. Never proportional.
    * ``backing_wei`` is the on-chain ``value`` field — mutable via
      ``updateBacking()``, so a cached ``Position`` goes stale. Positions are only
      ever valid at the block they were swept at and are never merged across
      blocks (PRD §7 rule 8, plan risk R4).
    * ``fee_share`` is **1 for every position** — fees split *equally*, backing buys
      duration, not share size. ``feeShareTotal() == activeListingCount()`` is a
      free runtime invariant.
    * ``allocatee`` is ``None`` while unallocated (on-chain ``address(0)``). The
      zero address is normalised away here so no widget can render it.
    * ``slot`` is 1-indexed and **non-contiguous** — the free list leaves permanent
      holes, which is why sweeps count non-zero ids instead of scanning ``1..n``
      (plan risk R5).
    * ``status`` is the raw ``uint8``; ``1`` is Active empirically. Labels come from
      ``fwa_enums``; unknown values render ``status N``.
    """

    model_config = _FROZEN

    listing_id: int
    collection: str                    # lowercased 0x address of the NFT contract
    depositor: str                     # lowercased 0x address
    allocatee: str | None = None       # None == unallocated (on-chain address(0))
    token_id: int
    weight: Weight                     # 1e36 // backing_wei — INVERSE
    backing_wei: Wei                   # on-chain `value`, mutable via updateBacking()
    fee_share: int = 1                 # always 1; fees split equally
    fee_debt: Wei = 0
    slot: int = 0                      # 1-indexed, non-contiguous (free-list holes)
    allocated_at: int = 0              # uint64 unix seconds; 0 == never allocated
    status: int = 0                    # raw uint8; 1 == Active


class CollectionOdds(BaseModel):
    """One row of the odds board: a collection's aggregated draw exposure.

    This is where the protocol's central tension is legible — ``weight_share_pct``
    is driven by how *cheap* a collection's positions are, so TTT sits at ~49.08%
    while CryptoPunks hold 137.10 ETH for 0.000%.

    * ``weight`` is the summed inverse weight of the collection's positions.
    * ``backing_wei`` is the summed backing. The manager converts it to the flat
      dict's ``eth_backed``.
    * ``floor_eth`` is ``None`` whenever no keyless floor exists (16 of 38
      collections) **or** the floor is suppressed. ``floor_source`` says which,
      so a widget never has to guess from ``None``:
      ``"coingecko"`` | ``"opensea"`` | ``"cached"`` | ``"missing"`` | ``"suppressed"``.
    * ``floor_note`` carries the reason text, e.g. Art Blocks'
      ``"multi-collection contract — floor not meaningful"``. One contract hosting
      many collections has no single floor; a per-contract number there is simply
      false, so it is never rendered.
    * ``eth_per_odds_point`` is ``None`` when the floor is unknown.
    """

    model_config = _FROZEN

    address: str                       # lowercased 0x NFT contract address
    name: str                          # onchain name(), never the docs page
    positions: int
    weight: Weight                     # summed inverse weight
    weight_share_pct: float            # 0.0-100.0
    backing_wei: Wei                   # summed backing (wei -> eth_backed at the boundary)
    floor_eth: float | None = None     # off-chain decimal ETH quote, never wei
    floor_source: str = "missing"      # coingecko|opensea|cached|missing|suppressed
    eth_per_odds_point: float | None = None
    floor_note: str = ""


class PullEV(BaseModel):
    """The flagship metric, rendered as an honest band — never as a point.

    ``EV = Σ pᵢ · max(0.85 · backingᵢ, floorᵢ) − acquisitionFee + rebateShare · surcharge``
    with ``pᵢ = (1e36 / backingᵢ) / totalWeight``.

    * ``lower_eth`` counts every unknown floor as ``0``. Strictly pessimistic and
      therefore incapable of misleading anyone into a purchase.
    * ``best_eth`` excludes unknown floors from the ``max()`` instead of zeroing
      them. Optimistic, and only meaningful next to the coverage counters.
    * ``lower_eth <= best_eth`` always; the band collapses when coverage is total.
    * ``fee_eth`` is the acquisition fee subtracted; ``rebate_eth`` is the
      pool-temperature-dependent $FWA surcharge share routed back to the purchaser.

    **There is deliberately no ``point_eth`` / ``value_eth`` / ``ev_eth`` field, and
    ``extra="forbid"`` makes adding one at a call site impossible.** Because floors
    are missing for 16 of 38 collections — including the two largest weight buckets
    — a single confident number here would tell someone to spend ETH on an estimate
    a third of which is fabricated. The band is enforced by the type, not by
    discipline (plan risk R13).
    """

    model_config = _FROZEN

    lower_eth: float                   # unknown floors zeroed — pessimistic bound
    best_eth: float                    # unknown floors excluded — optimistic bound
    fee_eth: float                     # acquisition fee subtracted from the EV
    rebate_eth: float                  # $FWA surcharge share routed back to purchaser
    collections_priced: int            # e.g. 22
    collections_total: int             # e.g. 38
    weight_priced_pct: float           # share of draw weight that has a floor


class Crown(BaseModel):
    """The single-holder "top deposit" crown — not a leaderboard.

    Exactly one listing holds it at a time. Taking it requires depositing at least
    ``(BPS + threshold_bps) / BPS`` times the incumbent's backing (live: 110%),
    which is what ``seize_wei`` reports.

    * ``vacant`` is authoritative. When it is ``True`` the widget renders
      ``vacant``, never ``0`` — a zero pot and an empty throne are different states.
    * ``share_bps`` is the crown tithe, **live 100 bps** even though the docs say
      500. It changed at block 25592190 (``ConfigSet key=15``). Read it live; never
      hardcode either value (PRD §7 rule 6).
    * ``depositor`` is the incumbent holder's address, ``None`` when vacant.
    """

    model_config = _FROZEN

    listing_id: int                    # 0 == vacant
    depositor: str | None = None       # incumbent crown holder; None when vacant
    pot_wei: Wei = 0
    seize_wei: Wei = 0                 # (BPS + threshold_bps)/BPS x incumbent backing
    threshold_bps: int = 0             # live 1000 -> 110% takeover
    share_bps: int = 0                 # crown tithe; live 100, docs say 500
    vacant: bool = True


class PoolTemp(BaseModel):
    """Pool temperature: which way the 10% surcharge is currently flowing.

    The surcharge split is a function of ``seconds_since_last_request``: at
    ``<= hot_gap`` it all goes to depositors, at ``>= cold_gap`` it all comes back
    to the purchaser as a $FWA allowance, with a ramp between. On a cold pool the
    effective price is materially lower — publicly observable, directly exploitable,
    and surfaced nowhere else.

    * ``token_share_bps`` is the **live** ``tokenShareBps(gap)`` read. Its linearity
      is unconfirmed, so it is read, never recomputed. ``None`` means the read
      failed; ``share_estimated=True`` means the value came from the documented ramp
      as a fallback and must be labelled as an estimate.
    * ``forced_share_bps`` is a **signed int256**. ``-1`` means dynamic (the normal
      case). Anything ``>= 0`` is an owner override that pins the split regardless
      of temperature, and the UI must say the dial is overridden. Decoding this
      unsigned gives ``2**256 - 1``, which is a decode bug, not a large share.
    * ``hot_gap`` / ``cold_gap`` are the live ramp endpoints in seconds (documented
      60 / 3600). The documented pair may appear as a static label only, never as a
      computed prediction.
    """

    model_config = _FROZEN

    seconds_since_last_request: int
    token_share_bps: int | None = None  # live purchaser share; None == read failed
    hot_gap: int = 0                    # seconds; live read, docs say 60
    cold_gap: int = 0                   # seconds; live read, docs say 3600
    forced_share_bps: int = -1          # SIGNED int256; -1 == dynamic
    share_estimated: bool = False       # True == token_share_bps came from the ramp


class ConfigParam(BaseModel):
    """One protocol parameter, resolved from ``ConfigSet`` history.

    Only six ``ConfigSet`` events exist in the protocol's entire history, so the
    whole parameter-drift widget is driven by one topic filter.

    ``is_drift`` compares the live value against the last on-chain ``ConfigSet`` —
    **never** against a documented value (PRD §7 rule 6). The owner is a plain EOA
    with no multisig or timelock and has already moved the crown tithe 500 → 100
    bps mid-flight, which is exactly why nothing here is hardcoded.
    """

    model_config = _FROZEN

    key: int                           # on-chain config key, e.g. 15
    name: str                          # resolved label, e.g. "TOP_LISTING_SHARE_BPS"
    value: int                         # live value
    block_number: int                  # block of the ConfigSet that last set it
    is_drift: bool = False             # live != last ConfigSet


class SettlementMix(BaseModel):
    """One row of the settlement-outcome mix — the protocol's most revealing stat.

    ``outcome`` is one of :data:`FWA_SETTLEMENT_OUTCOMES`; ``label`` is the human
    string. ~88% of purchasers sell straight back rather than keep the NFT.
    ``share_pct`` values across the five rows sum to 100.0.
    """

    model_config = _FROZEN

    outcome: str                       # one of FWA_SETTLEMENT_OUTCOMES
    label: str = ""                    # human string, e.g. "Accept bid, paid in $FWA"
    count: int = 0
    share_pct: float = 0.0


# ---------------------------------------------------------------------------
# Models — the three plumbing shapes the Talismans/TTT convention requires
# ---------------------------------------------------------------------------


class FWASignal(BaseModel):
    """One row of the Signals panel.

    Identical *shape* to ``TalismanSignal`` / ``TTTSignal`` so the shared
    ``_fmt_signal`` widget helper works unchanged -- but **not** the same colour
    vocabulary.

    ``color`` is restricted to :data:`~maxpane_dashboard.analytics.fwa_signals.SIGNAL_COLORS`
    = ``"$success" | "$warning" | "$error" | "dim"``: the **theme variables**,
    never the CSS colour names ``green`` / ``yellow`` / ``red``. Textual resolves
    content markup through the CSS name table, where ``green`` is ``#008000`` --
    4.09:1 against pure black, so it fails WCAG AA against *every* possible
    background and no palette can rescue it. The ``$`` forms resolve per theme
    and measure 10.39:1 and 6.82:1 under ``fwa``.

    This paragraph used to say ``"green" | "yellow" | "red" | "dim"``, which was
    true until WP-19 moved the vocabulary and stale afterwards. Three separate
    work packages then hand-wrote signal fixtures in the old vocabulary and went
    green while testing values the product cannot emit; the frozen contract
    saying so was how they got there. ``tests/test_fwa_guardrails.py::
    test_no_named_fixture_carries_a_field_the_product_cannot_emit`` now catches
    the fixture, and this docstring is the other half of the fix.

    Colour is never the sole carrier of meaning: ``value_str`` must also spell the
    state out in words or a glyph, so every row survives greyscale and
    colour-blind viewing (PRD §11).
    """

    model_config = _FROZEN

    label: str
    value_str: str
    indicator: str                     # always "●" — see analytics.fwa_signals.INDICATOR
    color: str                         # "$success" | "$warning" | "$error" | "dim"


class DrawEvent(BaseModel):
    """One activity-feed line: a VRF draw and the settlement choice made after it.

    Pairs ``AcquisitionRequested`` / ``NFTAllocated`` with the settlement event that
    followed. ``outcome`` is one of :data:`FWA_SETTLEMENT_OUTCOMES` and
    ``outcome_label`` is the words shown on screen — the feed colours by outcome but
    also spells it out.

    ``amount_wei`` is the ETH the purchaser received or paid for that settlement
    (0 when the outcome carries no ETH leg, e.g. paid in $FWA). ``collection`` is
    the address; ``collection_name`` is the display name and may be ``None`` before
    the registry resolves it.
    """

    model_config = _FROZEN

    ts: int                            # unix seconds
    block_number: int
    tx_hash: str
    purchaser: str                     # lowercased 0x address
    collection: str                    # lowercased 0x address
    collection_name: str | None = None
    token_id: int | None = None
    outcome: str = ""                  # one of FWA_SETTLEMENT_OUTCOMES
    outcome_label: str = ""            # human string rendered in the feed
    amount_wei: Wei = 0                # -> amount_eth at the presentation boundary


class FWASnapshot(BaseModel):
    """Everything one poll cycle produced, before it is flattened for the widgets.

    ``block_number`` is the **pinned** sweep block. Every position in ``positions``
    and every aggregate derived from them belongs to that one block; results are
    never merged across blocks (PRD §7 rule 11).

    ``invariants_ok`` is the runtime aggregate check — ``Σ(1e36//value) ==
    totalWeight()``, ``Σ(weight*value) == weightedBackingTotal()`` and the bit-exact
    ``acquisitionFee()`` reproduction. When it is ``False`` the odds board and EV
    render *stale*, never wrong: a partial sweep that produces a plausible total is
    a defect, not a degraded state.

    ``weighted_backing_total`` is carried here for the invariant check only. It is
    ``Σ(weight × backing) ≈ count × 1e36`` — **neither wei nor ETH, and never TVL**.
    It is intentionally absent from :data:`FWA_DATA_KEYS` so it cannot reach a
    widget. For value held, use ``core_balance_wei`` (``eth_getBalance(core)``).

    Sequence fields are tuples rather than lists so a shared snapshot is immutable
    all the way down, not just at the attribute level.
    """

    model_config = _FROZEN

    fetched_at: float                  # unix seconds, wall clock
    block_number: int = 0              # pinned sweep block; 0 == unknown

    # Position-derived (all pinned to block_number)
    positions: tuple[Position, ...] = ()
    collection_odds: tuple[CollectionOdds, ...] = ()
    pull_ev: PullEV | None = None

    # Hot-tier state
    crown: Crown | None = None
    pool_temp: PoolTemp | None = None
    params: tuple[ConfigParam, ...] = ()

    # Log-derived
    settlement_mix: tuple[SettlementMix, ...] = ()
    draw_events: tuple[DrawEvent, ...] = ()

    # Signals
    pool_temp_signal: FWASignal | None = None
    buy_gate_signal: FWASignal | None = None
    emissions_signal: FWASignal | None = None
    vrf_queue_signal: FWASignal | None = None
    param_drift_signal: FWASignal | None = None

    # Scalars (wei-native; converted at the presentation boundary)
    active_positions: int = 0
    core_balance_wei: Wei = 0          # eth_getBalance(core) — the ONLY value-held source
    acquisition_fee_wei: Wei = 0
    vrf_fee_wei: Wei = 0
    quote_total_wei: Wei = 0
    cumulative_revenue_wei: Wei = 0
    total_weight: Weight = 0
    weighted_backing_total: Weight = 0  # NOT wei, NOT ETH, NEVER TVL — invariant only

    # Health
    invariants_ok: bool = True
    degraded_sources: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# The flat-dict contract
# ---------------------------------------------------------------------------

FWA_DATA_KEYS: tuple[str, ...] = (
    # ---- hero: FWAHeroMetrics ------------------------------------------------
    # PULL EV card — a band plus its coverage badge. The badge keys are as
    # mandatory as the value keys: no EV number may render without them.
    "pull_ev_best_eth",            # float | None — unknown floors excluded
    "pull_ev_lower_eth",           # float | None — unknown floors zeroed
    "ev_available",                # bool
    "ev_collections_priced",       # int  (22)
    "ev_collections_total",        # int  (38)
    "ev_weight_priced_pct",        # float
    "ev_rebate_eth",               # float | None — $FWA surcharge share to purchaser
    # PRICE card — live quote plus the harmonic/arithmetic gap that IS the protocol
    "acquisition_fee_eth",         # float | None
    "vrf_fee_eth",                 # float | None — as returned; never a computed guess
    "quote_total_eth",             # float | None — the returned tuple, never a sum
    "price_available",             # bool
    "harmonic_mean_eth",           # float | None — what a pull costs you
    "arithmetic_mean_eth",         # float | None — what the pool holds
    "hm_am_gap_x",                 # float | None — a LIVE ratio, never a constant
    # CROWN card — gold is used here and nowhere else
    "crown_pot_eth",               # float | None
    "crown_pot_usd",               # float | None — None when no USD source
    "crown_seize_eth",             # float | None — 1.10 x incumbent backing
    "crown_holder",                # str | None
    "crown_vacant",                # bool — render "vacant", never 0
    "crown_available",             # bool

    # ---- odds board: FWAOddsBoard -------------------------------------------
    "collection_odds",             # list[dict] — FWA_ROW_KEYS["collection_odds"]
    "odds_available",              # bool
    "odds_as_of_block",            # int | None — the pinned sweep block
    "odds_stale",                  # bool — invariant mismatch or cached sweep

    # ---- sparkline: FWASparkline --------------------------------------------
    "fwa_price_history",           # list[[ts, close]] — hourly, up to 100 candles
    "fwa_price_usd",               # float | None
    "fwa_price_change_24h",        # float | None — percent
    "spark_available",             # bool

    # ---- signals: FWASignals -------------------------------------------------
    # Each is an FWASignal dump ({label, value_str, indicator, color}) or None.
    "pool_temp_signal",
    "buy_gate_signal",
    "emissions_signal",            # normally "emissions ended" — never a negative countdown
    "vrf_queue_signal",
    "param_drift_signal",

    # ---- activity feed: FWAActivityFeed --------------------------------------
    "draw_events",                 # list[dict] — FWA_ROW_KEYS["draw_events"]
    "feed_available",              # bool — False renders "logs unavailable — activity paused"
    "feed_unavailable_reason",     # str | None
    "feed_as_of_ts",               # float | None — for the "as of HH:MM" header

    # ---- chase board: FWAChaseBoard ------------------------------------------
    "chase_positions",             # list[dict] — FWA_ROW_KEYS["chase_positions"]
    "chase_available",             # bool
    # The crown's listing id, so the board can flag the crown/jackpot
    # coincidence (PRD §5). Deliberately *not* in FWA_WIDGET_SIGNATURES: it is an
    # optional extra kwarg on ``FWAChaseBoard.update_data`` with a ``None``
    # default, so the frozen two-kwarg payload still renders and the note simply
    # stays dark. ``None`` when the crown is vacant or unreadable.
    "crown_listing_id",            # int | None

    # ---- settlement table: FWASettlementTable --------------------------------
    "settlement_mix",              # list[dict] — FWA_ROW_KEYS["settlement_mix"]
    "crown_history",               # list[dict] — FWA_ROW_KEYS["crown_history"]
    "crown_sets_total",            # int | None — deduped TopListingSet count
    "crown_payouts_total",         # int | None
    "crown_paid_eth",              # float | None
    "settle_available",            # bool
    "settle_as_of_ts",             # float | None — for the "as of HH:MM" header

    # ---- meta: title bar + StatusBar ----------------------------------------
    "active_positions",            # int
    "core_balance_eth",            # float | None — eth_getBalance(core). NOT weighted_backing_total.
    "cumulative_revenue_eth",      # float | None — Splitter totalReceived()
    "take_rate_pct",               # float | None
    "current_block",               # int
    "invariants_ok",               # bool — False => odds_stale, render stale not wrong
    "degraded_sources",            # list[str] — e.g. ["logs"]
    "last_updated_seconds_ago",    # float
    "error_count",                 # int
    "poll_interval",               # int
)
"""Every key ``FWAManager.fetch_and_compute()`` returns — exactly, always.

Under *every* failure combination the manager returns this full key set; a dead
source changes values and flips an ``*_available`` flag, it never removes a key.
That is what lets a widget render an explicit unavailable state instead of
inferring one from ``None``.

``weighted_backing_total`` is absent by design (module docstring, trap 3).
"""


FWA_WIDGET_SIGNATURES: dict[str, tuple[str, ...]] = {
    "FWAHeroMetrics": (
        "pull_ev_best_eth",
        "pull_ev_lower_eth",
        "ev_available",
        "ev_collections_priced",
        "ev_collections_total",
        "ev_weight_priced_pct",
        "ev_rebate_eth",
        "acquisition_fee_eth",
        "vrf_fee_eth",
        "quote_total_eth",
        "price_available",
        "harmonic_mean_eth",
        "arithmetic_mean_eth",
        "hm_am_gap_x",
        "crown_pot_eth",
        "crown_pot_usd",
        "crown_seize_eth",
        "crown_holder",
        "crown_vacant",
        "crown_available",
    ),
    "FWAOddsBoard": (
        "collection_odds",
        "odds_available",
        "odds_as_of_block",
        "odds_stale",
    ),
    "FWASparkline": (
        "fwa_price_history",
        "fwa_price_usd",
        "fwa_price_change_24h",
        "spark_available",
    ),
    "FWASignals": (
        "pool_temp_signal",
        "buy_gate_signal",
        "emissions_signal",
        "vrf_queue_signal",
        "param_drift_signal",
    ),
    "FWAActivityFeed": (
        "draw_events",
        "feed_available",
        "feed_unavailable_reason",
        "feed_as_of_ts",
    ),
    "FWAChaseBoard": (
        "chase_positions",
        "chase_available",
    ),
    "FWASettlementTable": (
        "settlement_mix",
        "crown_history",
        "crown_sets_total",
        "crown_payouts_total",
        "crown_paid_eth",
        "settle_available",
        "settle_as_of_ts",
    ),
}
"""The exact ``update_data()`` kwarg names of the seven PRD §5 widgets.

Every kwarg is keyword-only with a ``None``/empty default, so ``update_data()``,
``update_data(**{k: None for k in sig})`` and a full payload all render without
raising — the three cases ``tests/widgets/test_fwa_widgets.py`` drives.

Widgets take **primitives only** (``str``/``int``/``float``/``bool``/``dict``/
``list[dict]``) and import nothing from this module — the project rule. This table
is how the widget WPs and the manager WP stay in agreement while being written
concurrently, and it is asserted mechanically rather than reviewed by eye.

The meta keys are not listed here: they go to the shared ``StatusBar``
(``last_updated_seconds_ago``, ``error_count``, ``poll_interval``) and to the
screen's title bar.
"""


FWA_ROW_KEYS: dict[str, tuple[str, ...]] = {
    "collection_odds": (
        "rank",                   # int, 1-based, sorted by weight_share_pct desc
        "address",                # str
        "name",                   # str
        "positions",              # int
        "weight_share_pct",       # float — TTT 49.08 ... Punks 0.000
        "eth_backed",             # float — from CollectionOdds.backing_wei
        "floor_eth",              # float | None
        "floor_source",           # str — coingecko|opensea|cached|missing|suppressed
        "eth_per_odds_point",     # float | None
        "floor_note",             # str — e.g. the Art Blocks suppression note
    ),
    "draw_events": (
        "ts",                     # int, unix seconds
        "block_number",           # int
        "tx_hash",                # str
        "purchaser",              # str
        "collection",             # str — address
        "collection_name",        # str | None — display name
        "token_id",               # int | None
        "outcome",                # str — one of FWA_SETTLEMENT_OUTCOMES
        "outcome_label",          # str — spelled out, not colour-only
        "amount_eth",             # float — from DrawEvent.amount_wei
    ),
    "chase_positions": (
        "rank",                   # int, 1-based, richest backing first
        "listing_id",             # int
        "collection",             # str — address
        "collection_name",        # str | None
        "token_id",               # int | None
        "backing_eth",            # float — up to 221 ETH
        "odds_pct",               # float — render 3 decimals, "0.000%" never "0"
        "expected_draws",         # float | None — pulls until this position is hit
        "jackpot_ratio",          # float | None — up to 1378x
        "sellback_eth",           # float | None — 0.85 x backing
    ),
    "settlement_mix": (
        "outcome",                # str — one of FWA_SETTLEMENT_OUTCOMES
        "label",                  # str — human string
        "count",                  # int
        "share_pct",              # float — the five rows sum to 100.0
    ),
    "crown_history": (
        "rank",                   # int, 1-based
        "holder",                 # str — one wallet currently holds 4 reigns
        "reigns",                 # int — deduped TopListingSet count for this holder
        "payout_eth",             # float — settled crown payouts
        "last_block",             # int | None
        "last_ts",                # int | None
    ),
}
"""Key sets for the ``list[dict]`` payloads in :data:`FWA_DATA_KEYS`.

Widgets cannot import the models, so these rows are the only shared vocabulary
between the manager and the tables that render them. Frozen here for the same
reason as the widget signatures: seven agents write against them concurrently.

``fwa_price_history`` is the one sequence payload that is *not* a list of dicts —
it is ``list[[ts, close]]`` pairs, matching the existing sparkline helpers.
"""
