"""Orchestrator for the SURF "Surfboard" dashboard (WP4).

One coordination point between six independently failing source groups, three
refresh tiers and one frozen output contract. Exposes one public coroutine,
:meth:`SurfManager.fetch_and_compute`, which returns **exactly**
:data:`~maxpane_dashboard.data.surf_models.SURF_KEYS` — always, under every
failure combination, and without ever letting an exception escape.

Source groups and how they die
------------------------------

============  ==========================================  =====================
Group         Client call                                 Dies as
============  ==========================================  =====================
``chain``     ``fetch_nonces`` + ``fetch_chain_state``    state RPC pool down
``channel``   ``fetch_channel_txs``                       Blockscout down
``market``    ``fetch_market``                            GeckoTerminal/DexScreener
``logs``      ``fetch_recent_logs``                       logs RPC pool down
``nft``       ``fetch_nft_stats``                         Blockscout counters
``activity``  ``fetch_dev_activity``                      Blockscout tx pages
============  ==========================================  =====================

``chain`` is the one that matters most: the announce channel emits **no logs**, so
``eth_getTransactionCount`` is the only detector that exists for it. It therefore
runs on the fast tier every refresh and is never skipped.

Four rules this module exists to enforce
-----------------------------------------

1. **A failed read is ``None``, never ``0``.** Every reading handed to
   ``build_signals`` is either a real value or ``None``; the pure layer compares
   ``None`` against nothing. The false-BURN case (supply ``None`` -> 0 -> "2.37M
   burned!") has a dedicated regression test.
2. **Baselines advance only on successful reads** (PRD §3). The manager never
   writes a baseline itself: it hands the cache's baselines plus this cycle's
   readings to ``build_signals`` and stores back whatever comes out.
3. **No sentinel ever reaches a series.** ``sample_series`` is called with the
   assembled payload's values, which are ``None`` when unread.
4. **A permissionless event is not a claim until someone unforgeable made
   it.** Uniswap v4 ``initialize()`` is open to anyone, so an ``Initialize``
   log naming IMD with a non-zero hook costs a stranger one transaction's gas
   and says nothing about who sent it. The hooked-``Initialize`` attribution
   therefore acts only on a row whose enclosing transaction a dev wallet
   signed (``client.fetch_tx_senders`` → :meth:`_attribute_launches` →
   :meth:`_valid_launch`); a hooked row we could not attribute renders as an
   explicit unknown, never as a launch. The persisted ``hook_launch`` record
   holds that evidence and is re-validated on every read, so it is durable
   without being a latch — the previous ``hook_live = bool(hooked) or
   previously_live`` was an unconditional OR over third-party input, and one
   griefing transaction pinned the hero to LAUNCHED for the life of the cache
   file. (Fix round 12a, 2026-08-24: the hero's own ``hook_status`` flat key
   this attribution used to feed is gone — no widget rendered it — but
   ``v4_hook_pools``/the persisted ``hook_launch`` record stay wired, because
   ``analytics/surf_signals.py`` still advances a baseline off them.)
5. **"Not due to retry" is not "healthy."** :meth:`SurfCache.is_fresh` /
   ``tiers_due`` answer *whether to attempt a fetch*, and only that:
   ``mark_failed`` advances the same ``_tier_next_due`` clock ``mark_fetched``
   does, purely to space out retries, so a tier sitting out a failure's backoff
   window is indistinguishable from a tier that is genuinely fresh if you only
   ask ``is_fresh``. A task that decides whether *this cycle's* payload for a
   group is trustworthy must not use ``is_fresh``/``tiers_due`` for that
   question — it must either compare :meth:`SurfCache.last_fetch_ts` against
   the tier's own TTL (``surf_cache.TIER_TTL_SECONDS``), which only advances on
   a genuine success, or — the pattern this module already uses — track
   per-attempt success in ``_failed_groups``/``_note`` (below) and never clear
   an entry except on a successful attempt. ``_degraded`` is built that way on
   purpose: a group that failed two cycles ago and is not due to retry yet
   stays in ``_failed_groups`` and therefore stays reported as degraded, rather
   than reading as healthy because its tier happens to be "fresh" (backed off).

Live values are computed, never quoted: ``parity_pct`` is derived from the two
prices every cycle, and ``imd_burned_cum`` is accumulated from observed supply
decreases. The repo has measured a documented "constant" drift three days
running; the same rule applies here (PRD §6.2).

Where the client's three degradation signals live (read this before WP4.8+)
-----------------------------------------------------------------------------

:class:`~maxpane_dashboard.data.surf_client.SurfClient` exposes three booleans/
dict that appear in no WP4 brief — ``channel_truncated``, ``activity_truncated``
and ``log_group_failed`` — because reviews of the client package forced them in
after WP1 shipped. Each is reset to its "nothing wrong" value at the START of
the matching ``fetch_*`` call, so reading it right after that call reflects only
the attempt that just happened:

* ``client.channel_truncated`` (bool) -> the announce feed hit its page bound
  with more pages outstanding. Maps to :data:`SOURCE_CHANNEL`.
* ``client.activity_truncated`` (bool) -> the dev-wallet activity pages did the
  same. This is the one that matters most: those pages feed the NEW DEPLOY
  detector (``deploy_events``), so a silent truncation means the dashboard
  reports "nothing shipped" when something did. Maps to :data:`SOURCE_ACTIVITY`.
* ``client.log_group_failed`` (dict keyed by the four ``LogWindow`` field
  names) -> a per-group log-filter failure inside one otherwise-successful
  ``fetch_recent_logs()`` call. Without reading this, a failed bridge-mint
  filter is indistinguishable from "no mints" and BRIDGE STAGE reports
  all-clear during an outage. Any ``True`` value maps to :data:`SOURCE_LOGS`.

:meth:`SurfManager._client_degradation` reads all three (defensively —
``getattr`` with a default, because a client double that only implements the
seven ``fetch_*`` coroutines, as every WP4 test double so far does, need not
define them) and folds whatever they report into :meth:`_degraded`'s output.
WP4.7 wired that composition end-to-end before any ``fetch_*`` call reached it;
WP4.9 made ``channel_truncated`` and ``log_group_failed`` observable, by wiring
:meth:`_pool_channel`'s ``fetch_channel_txs`` and :meth:`_pool_logs`'s
``fetch_recent_logs`` into :meth:`_cycle`. WP4.10 is what finally makes
``activity_truncated`` observable too, by wiring :meth:`_pool_activity`'s
``fetch_dev_activity`` into :meth:`_cycle` — it is the flag that matters most,
because a silent truncation of the dev/ops tx pages is indistinguishable from
"nothing shipped" to the NEW DEPLOY detector.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
import time
from typing import Any

from maxpane_dashboard.analytics.surf_signals import (
    READING_KEYS,
    SIGNAL_NAMES,
    build_signals,
    classify_channel_tx,
    decode_utf8_calldata,
    parity_pct,
)
from maxpane_dashboard.data.safe_call import safe_call as _safe_call
from maxpane_dashboard.data import surf_pool4 as P
from maxpane_dashboard.data.surf_addresses import (
    ANNOUNCE,
    BURN_EXECUTOR_V1,
    DEV_WALLET,
    FWA_SPLITTER,
    IDMD_NFT,
    IMD_TOKEN,
    KNOWN_LABELS,
    NFPM,
    OPS_WALLET,
    POOL_V3,
    RELAY_DEPOSITORY,
    SEAPORT,
    UNIVERSAL_ROUTER,
    WETH,
    ZERO_ADDRESS,
)
from maxpane_dashboard.data.surf_cache import (
    DEFAULT_CACHE_PATH,
    SLOT_ACTIVITY,
    SLOT_CHAIN,
    SLOT_CHANNEL,
    SLOT_LAUNCHPAD,
    SLOT_LOGS,
    SLOT_MARKET,
    SLOT_NFT,
    SLOT_POOL4,
    SERIES_IMD_PRICE_USD,
    pool4_reserve_series_name,
    SERIES_IMD_SUPPLY,
    TIER_FAST,
    TIER_LAUNCHPAD,
    TIER_MEDIUM,
    TIER_POOL4,
    TIER_SLOW,
    SurfCache,
)
from maxpane_dashboard.data.surf_client import SurfClient
from maxpane_dashboard.data.surf_models import (
    POOL4_COUNTER_STATES,
    POOL4_DISCOVERY_SOURCES,
    POOL4_DISCOVERY_STATES,
    POOL4_FLOW_LIMIT,
    POOL4_NETWORKS,
    POOL4_REWARD_PATHS,
    SURF_KEYS,
    Pool4Discovery,
)
from maxpane_dashboard.data.surf_pool4_client import Pool4Client
from maxpane_dashboard.data.surf_v4 import price_eth_per_imd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source groups (PRD §5 meta: ``degraded`` is a list of these names)
# ---------------------------------------------------------------------------

SOURCE_CHAIN = "chain"
SOURCE_CHANNEL = "channel"
SOURCE_MARKET = "market"
SOURCE_LOGS = "logs"
SOURCE_NFT = "nft"
SOURCE_ACTIVITY = "activity"
#: The v4 pool / decoy scan / launchpad hook+factory+executor sweep (Task 6,
#: curator ``TIER_ANALYSIS`` precedent). Unlike the other six groups this one
#: is **never** noted through :meth:`SurfManager._note` on a per-attempt
#: basis: a sweep that ran and failed while a last-good payload is already on
#: hand is a stale ``launchpad_as_of_hhmm`` marker, not a degradation — only
#: "nothing to serve at all" (``GROUP_SLOT``'s own no-last-good clause below)
#: puts this name in :meth:`SurfManager._degraded`'s output.
#:
#: Spelled ``"pad"``, not ``"launchpad"`` (fix round 1, controller finding 2):
#: ``screens/surf.py``'s title bar renders every ``degraded`` member verbatim
#: on a ``height: 1`` ``Static`` with no ellipsis and no scrollbar, and
#: ``WORST_CASE_TITLE_COLUMNS`` is a *tight* measurement of that row —
#: appending the full word pushed the worst case past both that pin and
#: ``FULL_LAYOUT_COLUMNS``, silently truncating the one row that exists to
#: tell the reader something is down. This repo's standing rule is to shorten
#: the label rather than widen the layout (curator's own precedent). Do not
#: "improve" this back to the long form without re-measuring
#: ``WORST_CASE_TITLE_COLUMNS`` — that is the whole reason it is terse.
SOURCE_LAUNCHPAD = "pad"
#: The pool4 sweep (WP7), on ``SOURCE_LAUNCHPAD``'s terms exactly: never noted
#: per attempt, only "nothing to serve at all" reaches :meth:`_degraded`, and
#: otherwise a stale ``pool4_as_of_hhmm`` is the whole signal.
#:
#: **Two characters, deliberately, and for the reason spelled out above.** The
#: title bar renders every ``degraded`` member verbatim on a ``height: 1``
#: ``Static`` with no ellipsis; the plan's R5 measured that row's worst case at
#: 139 columns against a 143 pin, so ``, p4`` costs exactly four columns and
#: lands it *on* the pin with nothing to spare. ``"pool4"`` would overflow it
#: silently, truncating the one row whose job is to say something is down.
#: Do not lengthen this without re-measuring ``WORST_CASE_TITLE_COLUMNS``.
SOURCE_POOL4 = "p4"

SOURCES: tuple[str, ...] = (
    SOURCE_CHAIN,
    SOURCE_CHANNEL,
    SOURCE_MARKET,
    SOURCE_LOGS,
    SOURCE_NFT,
    SOURCE_ACTIVITY,
    SOURCE_LAUNCHPAD,
    SOURCE_POOL4,
)

#: group -> the cache slot holding its last-good payload.
GROUP_SLOT: dict[str, str] = {
    SOURCE_CHAIN: SLOT_CHAIN,
    SOURCE_CHANNEL: SLOT_CHANNEL,
    SOURCE_MARKET: SLOT_MARKET,
    SOURCE_LOGS: SLOT_LOGS,
    SOURCE_NFT: SLOT_NFT,
    SOURCE_ACTIVITY: SLOT_ACTIVITY,
    SOURCE_LAUNCHPAD: SLOT_LAUNCHPAD,
    SOURCE_POOL4: SLOT_POOL4,
}

# ---------------------------------------------------------------------------
# pool4 — the vocabularies, the vendored testnet addresses and the log window
# ---------------------------------------------------------------------------

#: Unpacked from the contract, never retyped (amendment A5). Five packages
#: share one spelling of ``"not-discovered"``; a sixth hand-typed one is how a
#: state word silently stops matching the widget that renders it.
POOL4_NETWORK_SEPOLIA, POOL4_NETWORK_MAINNET = POOL4_NETWORKS
POOL4_NOT_DISCOVERED, POOL4_ADOPTED, POOL4_REJECTED = POOL4_DISCOVERY_STATES
#: Ranked strongest first. ``unattributed`` is never *set* by this module -- it
#: is what ``discovery_source_word`` resolves an adoption with no recorded
#: source to, so a producer bug shows up on screen instead of being promoted to
#: the strong case.
POOL4_SOURCE_SELF_POST, POOL4_SOURCE_DOCS, POOL4_SOURCE_UNATTRIBUTED = (
    POOL4_DISCOVERY_SOURCES
)
#: What ``rewardsRecipient()`` points at, and therefore what the reward share
#: means. ``None`` is *unknown* and must never be read as ``direct``.
POOL4_PATH_DIRECT, POOL4_PATH_VIA_DISTRIBUTOR = POOL4_REWARD_PATHS

#: The Sepolia launch-3 deployment, **vendored** — the hook, and its own test
#: IMD. Not in ``surf_addresses``: that module is the mainnet vocabulary this
#: dashboard's other seven groups read, and a testnet address in it would be
#: one import away from being used as a mainnet one. They are parameters to
#: every ``Pool4Client`` call for the same reason the client refuses to hold
#: them as constants (its own docstring): the mainnet hook is *discovered*, and
#: a module-level address is either a testnet address shipped to mainnet
#: readers or a mainnet address nobody verified.
#:
#: Captured with the WP1 corpus (``tests/fixtures/surf/pool4/``,
#: ``hook_state_healthy.json`` — chain 11155111, block 11614022). Read live on
#: every sweep; nothing here is a documented number.
POOL4_SEPOLIA_HOOK = "0xa1B997A9861B2b8aC17B4c615089cCC2a5416840"
POOL4_SEPOLIA_TOKEN = "0xB37d54bC1F1d9271fc57D7E03192976baA39Cc82"

#: Blocks of hook logs one sweep asks for — ~24 h at 12 s, on both chains.
#: The client pages this in its own ``LOG_WINDOW_BLOCKS`` chunks; this is the
#: span, not the chunk. Wide enough that FLOW has rows on a quiet day and that
#: an accrual and the swap that settles it are almost always in the same
#: window; see ``_pool4_unsettled_legs`` for what happens when they are not.
POOL4_LOG_WINDOW_BLOCKS = 7_200

#: Unpacked from the contract, never retyped (A5).  Four words, none a
#: substring of another, and ``None`` is **not** one of them: ``None`` means
#: the control has never run, and every outcome of actually looking is a word.
POOL4_RECONCILED, POOL4_MISMATCH, POOL4_WINDOW_LIMITED, POOL4_UNCHECKED = (
    POOL4_COUNTER_STATES
)

#: The identities R1 control (c) publishes, named because **A9 excludes the
#: other two** and the exclusion is the whole point of naming them.
#:
#: ``sum_FeeCollected_eth == sum_FeesWithdrawn_eth + retainedEth()`` is real and
#: holds, but it is not published here: ``totalFeeToken`` is cumulative while
#: ``retainedEth`` is a current *balance*, and the symmetric form a reader
#: would expect cries wolf on every owner withdrawal.
#: ``totalBurned() == token.balanceOf(0xdEaD)`` is excluded for a different
#: reason -- nothing on this path reads that balance, so it is permanently
#: unread and including it would make the control permanently ``unchecked``.
#: See the report: reading it needs a leg on ``fetch_hook_state``'s batch,
#: which is WP6's file.
#:
#: These are WP3's own dict keys, restated here with
#: ``test_the_reconciliation_keys_this_module_reads_still_exist`` as the
#: tripwire: a rename there would otherwise silently select nothing and this
#: control would report ``unchecked`` forever while looking healthy.
POOL4_COUNTER_IDENTITIES: tuple[str, ...] = (
    "sum_FeeCollected_imd == totalFeeToken()",
    "sum_ClaimsSettled_0 == totalBurned()",
    "sum_ClaimsSettled_1 == totalRewarded()",
)

#: A transaction hash, and nothing else, may be cited as provenance.
#: ``source_tx_hash`` reaches this module from a Blockscout row and, on a later
#: read, from a cache file -- both third-party. The detail line it lands in is
#: escaped at render; refusing to put arbitrary bytes into a sentence in the
#: first place is the cheaper half of that defence.
_TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

#: Slot keys excluded from the "did anything actually change?" comparison that
#: gates ``pool4_as_of_hhmm``. The head block moves every twelve seconds and
#: reaches no widget, so leaving it in would make every sweep look like new
#: data and the marker would advance on every tick — a guard that cannot fail,
#: which is worse than no guard at all.
POOL4_VOLATILE_SLOT_KEYS: frozenset[str] = frozenset({"block_number"})

#: Rows handed to the widgets. The feed renders fewer at narrow tiers; the
#: surplus costs nothing and lets a screen change its mind without a manager change.
FEED_ITEM_LIMIT = 25
DEV_ACTIVITY_LIMIT = 25
NFT_SALES_LIMIT = 8

# NOTE: ``SIGNAL_NAMES`` is **imported** from ``analytics.surf_signals`` above
# and only re-exported in ``__all__`` for convenience. It is not restated here.
# WP2 derives it from its own ``_DETECTORS`` tuple, so a detector renamed or
# reordered there must reach ``_signal_keys`` — a local copy would keep reading
# WP0's spellings out of a dict keyed by WP2's, and all eighteen ``sig_*`` keys
# would become ``None`` in silence: ``_finalise`` only logs keys *outside*
# ``SURF_KEYS``, the full-key-set test still passes, and
# ``test_every_signal_contributes_three_keys`` would be comparing the manager
# against itself. This is the same failure as the ``READING_KEYS`` drift in
# open issue 2, and the same fix.

#: ``wallet_label`` -> the address that label must belong to. Used only for the
#: defence-in-depth re-check in ``_activity_rows``: WP1.6 owns the poisoning
#: filter, and this map is what lets the manager *assert* the rule held rather
#: than implement it a second time (a row labelled "dev" whose sender is not the
#: dev wallet cannot be that wallet's own tx).
DEV_WALLETS: dict[str, str] = {
    "dev": DEV_WALLET.lower(),
    "ops": OPS_WALLET.lower(),
}

#: The signers whose ``Initialize`` transaction makes a hooked v4 pool *the
#: dev's launch* rather than a stranger's. Derived from ``DEV_WALLETS`` above,
#: which is read from ``surf_addresses`` — the module that owns this vocabulary
#: — rather than restated, so a corrected address cannot come to mean two
#: different things in one repo.
LAUNCH_SIGNERS: frozenset[str] = frozenset(DEV_WALLETS.values())

#: ``LogWindow`` group name -> the ``SLOT_LOGS`` keys that group produces.
#:
#: This is the table that turns ``SurfClient.log_group_failed`` into an answer.
#: ``LogWindow``'s tuple fields default to ``()`` and cannot hold ``None``, so a
#: filter that died and a window that was genuinely empty arrive here
#: identically; the client's flag is the out-of-band channel that separates
#: them, and these are the keys it has to reach. Adding a key to the
#: ``SLOT_LOGS`` payload without adding it here means a failed filter silently
#: publishes an affirmative empty claim for it again.
LOG_GROUP_SLOT_KEYS: dict[str, tuple[str, ...]] = {
    "bridge_mints": ("bridge_mints",),
    "identity_updates": ("identity_writes",),
    "v4_initializes": ("v4_hook_pools", "hook_launch", "hook_unverified"),
    "seaport_sales": ("nft_last_sales",),
}

#: ``LOG_GROUP_SLOT_KEYS`` group -> the ``READING_KEYS`` entry it feeds. A group
#: that failed must reach ``build_signals`` as ``None``: ``[]``/``0`` is the
#: affirmative claim "read and held nothing", and that claim is what lets
#: BRIDGE STAGE report all-clear during an outage. ``seaport_sales`` is absent
#: on purpose — realized sales are a panel, not a detector.
LOG_GROUP_READING_KEYS: dict[str, str] = {
    "bridge_mints": "bridge_mints",
    "identity_updates": "identities_written",
    "v4_initializes": "v4_hook_pools",
}

#: Distinct ``Initialize`` transaction hashes whose signer the manager will
#: remember between cycles. Bounded because the memo is keyed by an
#: attacker-choosable value: anyone can emit a hooked ``Initialize`` for IMD,
#: and an unbounded memo would grow one entry per grief transaction for the
#: life of the process. Nineteen IMD v4 pools have ever existed, so this is
#: room for two orders of magnitude more than the chain has produced.
_SIGNER_MEMO_CAP = 256

# NOTE: the counterparty -> kind map that used to live here belongs to WP1.6,
# which fills ``DevTx.kind`` at construction. Keeping a copy here would be a
# second implementation of one vocabulary, and the two would drift the first
# time a contract is added to only one of them.

#: Wei per whole token / per ETH. The models are wei-native and this module is
#: the single place that divides (WP0.4).
WEI = 10**18


def _dget(state: Any, name: str) -> Any:
    """One decoded getter off the Distributor's plain dict, or ``None``.

    The Distributor has no WP0 model yet, so its client returns a dict keyed by
    getter name. Deliberately **not** ``_field``: that one raises on an unknown
    attribute so a model rename is loud, and a ``dict`` cannot give that
    guarantee -- a missing key here is an ordinary "this deployment does not
    have one", which is exactly the Sepolia case.
    """
    if not isinstance(state, dict):
        return None
    return state.get(name)


async def _none() -> None:
    """An already-finished "we had no address to ask" leg.

    Used where a ``gather`` has a leg that cannot run — the dripper round with
    no ``rewardsRecipient()`` behind it. Passing a coroutine that answers
    ``None`` keeps the gather's shape fixed, which is what lets the caller
    unpack its results positionally without a branch per leg.
    """
    return None


def _field(obj: Any, name: str) -> Any:
    """``obj.name``, or ``None`` when the whole read failed.

    Deliberately **not** ``getattr(obj, name, None)``. A model field that gets
    renamed must raise ``AttributeError`` here — loudly, in one place — instead
    of silently becoming ``None``, which this layer encodes as *outage*: every
    dependent key would go dark and every test would stay green. WP0.4 is the
    frozen field table; this helper is what makes drifting off it fail.
    """
    if obj is None:
        return None
    return getattr(obj, name)


#: The fields checked by :func:`_chain_state_empty`. Every one of WP0.4's
#: ``ChainState`` fields — deliberately the same tuple ``test_the_doubles_...``
#: pins as "the fields WP4 reads", so a WP0 rename that ``_field()`` would
#: already catch cannot silently narrow this check instead.
_CHAIN_STATE_FIELDS: tuple[str, ...] = (
    "lp_liquidity", "lp_imd_wei", "lp_weth_wei", "lp_owner",
    "identity_allowed", "imd_supply_wei", "block_number",
)


def _chain_state_empty(state: Any) -> bool:
    """``True`` when ``fetch_chain_state()`` returned an object with nothing in it.

    A batched ``eth_call`` round can come back as a real :class:`ChainState`
    (not ``None``) while every sub-call inside it failed client-side — a
    partial-batch decode failure that never raises. ``_pool_chain``'s ``ok``
    check used to read only ``state_res is not None``, so this shape passed as
    a healthy read: six hero keys (``lp_liquidity``, ``lp_imd``, ``lp_weth``,
    ``lp_owner_ok``, ``gate_open``, ``imd_supply``) rendered dashes with
    ``"chain"`` never entering ``degraded`` — a screen full of unexplained
    dashes, which is the one shape CLAUDE.md's degradation rule forbids. A
    state with even one field populated is a genuine partial read (the everyday
    case ``_pool_chain``'s docstring already documents) and is not touched by
    this check.
    """
    return state is not None and all(
        _field(state, name) is None for name in _CHAIN_STATE_FIELDS
    )


def _tokens(wei: Any) -> float | None:
    """Wei -> whole tokens, exactly once. ``None`` in, ``None`` out."""
    raw = _opt_int(wei)
    return None if raw is None else raw / WEI


def _hex_int(value: Any) -> int | None:
    """``int`` from a decimal *or* ``0x`` string — RPC payloads use both."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 16) if text.lower().startswith("0x") else int(text, 10)
        except ValueError:
            return None
    return _opt_int(value)


def _word_addr(data: Any, index: int) -> str:
    """The *index*-th 32-byte word of a log payload, read as an address.

    ``""`` when the payload is short or unparseable — never a zero address,
    which would read as "hookless" rather than "undecodable".
    """
    raw = str(data or "")
    raw = raw[2:] if raw.startswith("0x") else raw
    start = index * 64
    word = raw[start : start + 64]
    if len(word) != 64:
        return ""
    return "0x" + word[24:]


def _data_words(data: Any) -> list[str]:
    """A log payload split into whole 32-byte words, ``0x`` stripped.

    A trailing partial word is discarded rather than padded: a short payload is
    a *truncated* one, and inventing zeroes for the missing bytes is how a
    truncated Seaport order would decode into a confident, wrong price.
    """
    raw = str(data or "")
    raw = raw[2:] if raw.startswith("0x") else raw
    usable = len(raw) - len(raw) % 64
    return [raw[i : i + 64] for i in range(0, usable, 64)]


def _abi_array(words: list[str], head_index: int, stride: int) -> list[list[str]]:
    """The dynamic array whose 32-byte *offset* sits at ``words[head_index]``.

    Solidity encodes a dynamic array as an offset in the head and a
    ``length``-prefixed body at that offset, counted in **bytes** from the start
    of the payload — so the length word is at ``offset // 32``. Each element is
    ``stride`` words (4 for Seaport's ``SpentItem``, 5 for ``ReceivedItem``).

    Returns ``[]`` for a malformed head and stops early — never a partial
    element — when the payload runs out. Both are the "undecodable" answer, and
    the callers treat them as such rather than as an empty order.
    """
    if head_index >= len(words):
        return []
    offset = _hex_int("0x" + words[head_index])
    if offset is None or offset % 32 or offset // 32 >= len(words):
        return []
    start = offset // 32
    count = _hex_int("0x" + words[start]) or 0
    items: list[list[str]] = []
    for i in range(count):
        lo = start + 1 + i * stride
        if lo + stride > len(words):
            break
        items.append(words[lo : lo + stride])
    return items


def _log_ts(log: Any, now: float) -> float:
    """A log's block timestamp, or *now* as the first-seen time.

    Some of the keyless logs endpoints return ``blockTimestamp`` on the log
    object and some do not (drpc does not; tenderly does), and resolving a block
    header per log is a round trip per event on a pool that already rate-limits.
    Falling back to the observation clock is safe for WP2's detectors — they key
    on ``tx_hash`` first, so a re-observed row can never re-fire — but it does
    mean a FIRED age can read as "just now" for an event that landed a few
    minutes earlier. See Open issues.

    What the fallback does **not** give you is an ordering: a whole group
    stamped with one clock has no ``ts`` order at all. That is why every row
    carries :func:`_log_position` beside this stamp, and why WP2 orders on
    ``(ts, block, log_index)`` rather than on ``ts`` alone.
    """
    if isinstance(log, dict):
        stamp = _hex_int(log.get("blockTimestamp") or log.get("timestamp"))
        if stamp:
            return float(stamp)
    return float(now)


def _log_position(log: Any) -> dict[str, int | None]:
    """``{"block": …, "log_index": …}`` — a log's place in the chain's own order.

    The client preserves both fields verbatim and the decoders used to discard
    them, which left ``ts`` as the only ordering key over an event stream — and
    ``ts`` is not a total order over these rows. Two events in one block share a
    timestamp, and an endpoint that omits ``blockTimestamp`` makes every row in
    the sweep share one. ``None`` for either field when the endpoint did not
    send it; WP2 sorts those below a row that has one rather than ahead of it.
    """
    row = log if isinstance(log, dict) else {}
    return {
        "block": _hex_int(row.get("blockNumber")),
        "log_index": _hex_int(row.get("logIndex")),
    }


def _opt_float(value: Any) -> float | None:
    """``float`` or ``None`` — never a silent ``0``."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


#: The launchpad fields a completed read is expected to produce -- the
#: multicall's getters and the log sweep's aggregates together. All of them
#: ``None`` at once is not a launchpad with nothing in it; it is a launchpad
#: nobody could read.
_LAUNCHPAD_READ_FIELDS = (
    "coin_count",
    "imd_to_burn_wei",
    "executor_balance_wei",
    "min_bridge_wei",
    "creator_eth_owed_wei",
    "burned_total_wei",
    "swap_count",
    "trader_count",
    "launch_count",
    "new_24h",
    "creator_count",
)


def _launchpad_state_is_blank(state: Any) -> bool:
    """True when a launchpad state carries no reading at all.

    ``SurfClient.fetch_launchpad`` promises it always returns a state, and it
    keeps that promise on a total failure by returning one whose every field
    is ``None`` (``_failed_launchpad_sweep``). That is the honest shape for a
    *client* to return -- "we could not look" is exactly ``None``, never
    ``0`` -- but it must not be persisted over a slot that already holds real
    numbers, because ``SLOT_LAUNCHPAD``'s payload is what the hero's
    LAUNCHPAD and FLOW boxes and the whole ``l`` view render, behind this
    tier's own ``as of HH:MM``.

    A representable zero still counts as a reading: a launchpad with
    ``coin_count == 0`` is a fact, and this returns ``False`` for it. Only
    the total absence of every field is blank.
    """
    if state is None:
        return True
    return all(_field(state, name) is None for name in _LAUNCHPAD_READ_FIELDS)


class SurfManager:
    """Fetches SURF data across seven source groups and returns a flat dict."""

    def __init__(
        self,
        poll_interval: int = 30,
        *,
        clock: Any = time.time,
        cache_path: str = DEFAULT_CACHE_PATH,
        client: Any = None,
        cache: Any = None,
        pool4_client: Any = None,
    ) -> None:
        self.poll_interval = poll_interval
        self._clock = clock
        self._cache_path = str(cache_path)
        self.client = client if client is not None else SurfClient()
        #: pool4's own client, injected like ``client`` and for the same
        #: reason. It is a *second* client rather than an extension of
        #: ``SurfClient`` because pool4 reads two chains from four endpoint
        #: pools; see ``surf_pool4_client``'s docstring. A test that hands a
        #: ``SurfClient`` double and nothing here would otherwise get the real
        #: one and a live socket on the first sweep.
        self.pool4_client = (
            pool4_client if pool4_client is not None else Pool4Client()
        )
        self.cache = cache if cache is not None else SurfCache(
            path=self._cache_path, clock=clock
        )

        self._cycle_count = 0
        self._error_count = 0
        #: Groups whose most recent *attempt* failed. Cleared on success.
        self._failed_groups: set[str] = set()
        #: ``Initialize`` tx hash -> the wallet that signed it. In-memory only
        #: and never persisted: it is a cache of an answer, not a state the
        #: dashboard may restore and act on across restarts. Only successful
        #: lookups are remembered, so an RPC outage never freezes an
        #: attribution. Bounded by :data:`_SIGNER_MEMO_CAP`.
        self._launch_signer_memo: dict[str, str] = {}
        #: The in-flight detached launchpad sweep, or ``None``. Held so the
        #: task is never garbage-collected mid-flight and so :meth:`close` can
        #: cancel it before the client's sockets go. See :meth:`_spawn_launchpad`.
        self._launchpad_task: Any = None
        #: The in-flight detached pool4 sweep, or ``None``. Same contract.
        self._pool4_task: Any = None
        #: ``(network, share price)`` this session's ``pool4_share_price_delta_pct``
        #: is measured against, and the count of successful share-price reads
        #: since it was seeded.
        #:
        #: In memory only, never persisted: it is a *session* baseline, and a
        #: restored one would report a move that happened while the app was
        #: not running as a move the reader just watched. It is re-seeded
        #: whenever the network changes, because a Sepolia baseline under a
        #: mainnet share price is a fabricated number — the two vaults are
        #: different contracts holding different tokens.
        self._pool4_baseline: tuple[str | None, float] | None = None
        self._pool4_price_reads = 0

        try:
            self.cache.load()
        except Exception as exc:            # noqa: BLE001 — load is fail-soft; belt and braces
            logger.warning("SURF cache load failed: %s", exc)

    # -- lifecycle -----------------------------------------------------------

    def save_cache(self) -> None:
        try:
            self.cache.save()
        except Exception as exc:            # noqa: BLE001
            logger.warning("SURF cache save failed: %s", exc)

    async def close(self) -> None:
        """Stop the detached sweeps, persist the cache, close both clients.

        Never raises. Each sweep holds the client it reads through, so both
        are cancelled and awaited *first* — closing sockets out from under a
        task still mid-request is how a clean quit turns into a traceback on
        the way down (curator's ``close()`` precedent,
        ``_cancel_crosscheck``/``_cancel_analysis``).

        ``pool4_client.close()`` is guarded separately from ``client.close()``
        on purpose: one raising must not leave the other's sockets open, which
        a single ``try`` around both would do.
        """
        await self._cancel_launchpad()
        await self._cancel_pool4()
        self.save_cache()
        try:
            await self.client.close()
        except Exception as exc:            # noqa: BLE001
            logger.debug("closing the SURF client failed: %s", exc)
        try:
            closer = getattr(self.pool4_client, "close", None)
            if closer is not None:
                await closer()
        except Exception as exc:            # noqa: BLE001
            logger.debug("closing the pool4 client failed: %s", exc)

    # -- the chain group (fast tier) -----------------------------------------

    async def _pool_chain(self, now: float) -> dict[str, Any]:
        """Three nonces + the batched ``eth_call`` round. Never raises.

        Both reads are issued concurrently against the **same** state RPC pool
        and are judged together, so ``ok`` is ``True`` only when *both*
        answered. ``and``, not ``or``: the two calls fail independently and the
        realistic half-failure is the cheap one surviving — the provider answers
        ``eth_getTransactionCount`` and drops the batched ``eth_call`` round.
        Under ``or`` that cycle published ``lp_liquidity``, ``lp_imd``,
        ``lp_weth``, ``lp_owner_ok``, ``gate_open`` and ``imd_supply`` as
        ``None`` while ``degraded`` reported the chain group **healthy**: six
        dashes across the hero with nothing on screen to explain them, which is
        the one shape CLAUDE.md's degradation rule forbids.

        Flagging is all ``and`` changes. Whatever *did* come back is still read
        straight off the models in ``_cycle`` and still published, ``None``
        fields still render as unavailable, and a ``None`` can never advance a
        baseline downstream. What a half-failure does **not** do is overwrite
        the ``SLOT_CHAIN`` last-good with a half-empty payload or mark the fast
        tier fetched.

        WP4.12 adds one more shape to ``ok``: a ``state_res`` that is not
        ``None`` but is wholly empty (:func:`_chain_state_empty`) — a
        client-side partial-batch decode failure that never raises and never
        returns ``None`` either, so it looked exactly like a healthy read
        before this guard. A ``state_res`` with even one field populated is
        the ordinary half-failure above and is unaffected.
        """
        nonces_res, state_res = await asyncio.gather(
            self._guard(self.client.fetch_nonces, "fetch_nonces"),
            self._guard(self.client.fetch_chain_state, "fetch_chain_state"),
            return_exceptions=False,
        )
        ok = (
            nonces_res is not None
            and state_res is not None
            and not _chain_state_empty(state_res)
        )
        if ok:
            self.cache.store_last_good(
                SLOT_CHAIN,
                {
                    "block": _opt_int(_field(state_res, "block_number")),
                    "imd_supply": _tokens(_field(state_res, "imd_supply_wei")),
                    "announce_nonce": _opt_int(_field(nonces_res, "announce")),
                },
                ts=now,
            )
            self.cache.mark_fetched(TIER_FAST, now)
        else:
            self.cache.mark_failed(TIER_FAST, now)
        self._note(SOURCE_CHAIN, ok)
        return {"nonces": nonces_res, "state": state_res, "ok": ok}

    async def _guard(self, call: Any, name: str) -> Any:
        """Await ``call()``; a raise becomes ``None`` and is logged, never escapes."""
        try:
            return await call()
        except Exception as exc:            # noqa: BLE001 — clients document None on failure
            logger.warning("SURF %s raised: %s", name, exc)
            return None

    # -- the medium tier: market, logs, channel ------------------------------

    async def _pool_market(
        self, tiers: set[str], now: float, real_pool_id: str | None
    ) -> Any:
        """Fetch the market view when the medium tier is due. Never raises.

        ``real_pool_id`` (fix round 10a) is the live v4 pool id, threaded in
        from the launchpad slot ``_cycle`` already unpacked -- it is what
        lets ``SurfClient._pick_imd_pair`` tell the real pair from a decoy,
        and costs no extra request (it is a plain argument, not a fetch).

        The skip predicate is the tier's due-ness and **nothing else**. It used
        to read ``TIER_MEDIUM not in tiers and get_last_good(SLOT) is not
        None``, and every one of the five skip predicates in this module was
        written that way. The second conjunct means a group whose slot has
        never been populated is fetched on *every* poll no matter what
        ``mark_failed`` did to the tier clock — i.e. the failure backoff was
        bypassed entirely on a cold cache, which is exactly the state a fresh
        install is in when the upstream host is down or rate-limiting.

        It was never needed: a tier with no recorded ``next_due`` is already
        due (:meth:`SurfCache.is_fresh` returns ``False`` for an unset tier), so
        cycle 1 on a cold cache fetches on the tier check alone. All the
        conjunct did was disable the backoff on the path that needs it — this
        one hammered DexScreener, GeckoTerminal and CoinGecko every 30 s
        indefinitely, and ``_pool_nft``'s ~11 requests per call (each retried
        once by ``_get_json``) did the same to Blockscout. For a keyless tool
        installed by people who cannot register for anything, getting the
        user's IP blocked is a first-class failure.
        """
        if TIER_MEDIUM not in tiers:
            return None                     # skip, not a failure: no `_note` above
        snap = await self._guard(
            lambda: self.client.fetch_market(real_pool_id), "fetch_market"
        )
        self._note(SOURCE_MARKET, snap is not None)
        if snap is not None:
            self.cache.store_last_good(SLOT_MARKET, self._market_payload(snap), ts=now)
        return snap

    @staticmethod
    def _market_payload(snap: Any) -> dict[str, Any]:
        """The whole PRD §5 market view, scaled once and cached as one dict.

        **All six values, not just the two prices.** The slot is what `_cycle`
        falls back to on a skipped medium tier, so anything left out of it is a
        key that renders `--` on two refreshes out of three — while `_degraded`
        correctly says the market group is healthy, because a skip never reaches
        `_note`. Storing only `imd_price_usd`/`fp_price_usd` (as this method used
        to) blanked `imd_change_24h_pct`, `imd_vol_24h_usd`, `pool_liquidity_usd`
        and `eth_usd`, took `parity_pct` with them, and dropped this cycle's
        price and parity samples on the floor as well — `sample_series` treats a
        `None` as "nothing to record", which is right for an outage and wrong for
        a refresh that simply did not need to re-fetch.

        `pool_imd` / `pool_weth` are deliberately absent: they are DexScreener's
        whole-pool reserves and no `SURF_KEYS` entry reads them. The hero's LP
        legs come off `ChainState.lp_imd_wei` / `lp_weth_wei` (WP0.4, WP1.4).
        """
        return {
            "imd_price_usd": _opt_float(_field(snap, "imd_price_usd")),
            "imd_change_24h_pct": _opt_float(_field(snap, "imd_change_24h_pct")),
            "imd_vol_24h_usd": _opt_float(_field(snap, "imd_vol_24h_usd")),
            "pool_liquidity_usd": _opt_float(_field(snap, "pool_liquidity_usd")),
            "fp_price_usd": _opt_float(_field(snap, "fp_price_usd")),
            "eth_usd": _opt_float(_field(snap, "eth_usd")),
        }

    async def _pool_logs(self, tiers: set[str], now: float) -> Any:
        if TIER_MEDIUM not in tiers:
            return None
        window = await self._guard(self.client.fetch_recent_logs, "fetch_recent_logs")
        self._note(SOURCE_LOGS, window is not None)
        if window is not None:
            # Decoded **into WP2's row shapes** here, once, and cached that way:
            # `_readings` reads these back off the slot on every fast-only
            # refresh (Task WP4.11), so the detectors keep seeing a read window
            # rather than an outage between two medium ticks. All four groups
            # arrive raw; all four are decoded here and nowhere else.
            candidates = self._hooked_candidates(window, now)
            signers = await self._launch_signers(candidates)
            hooked, unattributed = self._attribute_launches(candidates, signers)
            previous = dict(
                getattr(self.cache.get_last_good(SLOT_LOGS), "payload", None) or {}
            )
            failed = self._log_group_failed()
            payload: dict[str, Any] = {
                "to_block": _opt_int(_field(window, "to_block")),
                "bridge_mints": self._bridge_rows(window, now),
                # "Hooked pools seen in THIS window, that a dev wallet
                # signed". `None` when the window held a hooked pool whose
                # signer we could not read: that is an unread attribution,
                # not an empty window, and `[]` here would seed WP2's v4
                # baseline with the claim that nothing happened.
                "v4_hook_pools": hooked if hooked or not unattributed else None,
                "hook_launch": self._launch_record(
                    hooked, previous.get("hook_launch")
                ),
                "hook_unverified": bool(unattributed),
                # Signal 3's detail line: writes seen *in this window*, not
                # the hero's lifetime "x/2000". Two different numbers with
                # one name — see the header's consequence 4.
                "identity_writes": self._identity_writes(window),
                # Realized sales belong to the logs group, not to the
                # Blockscout counters: they are on different tiers, and the
                # NFT panel must keep showing them through a slow-tier skip.
                "nft_last_sales": self._seaport_sale_rows(window, now),
            }
            # A group whose filter FAILED contributed nothing to the four
            # decoders above -- they saw `()`, which `LogWindow` cannot tell
            # from "read and held nothing" (its own docstring says so and
            # hands the resolution here). Writing their output would replace
            # this group's last-good rows with an affirmative empty claim, so
            # instead every key the failed group owns keeps the value we
            # already hold, or stays `None` when we have never held one.
            for group, keys in LOG_GROUP_SLOT_KEYS.items():
                if not failed.get(group):
                    continue
                for key in keys:
                    payload[key] = previous.get(key)
            # Persisted with the payload, because it is what tells `_readings`
            # which of these values may be handed to a detector as a reading
            # and which must arrive as `None`. It survives a fast-only cycle
            # for the same reason `_failed_groups` does: nothing re-read the
            # group, so nothing has re-earned the claim.
            payload["log_group_failed"] = failed
            self.cache.store_last_good(SLOT_LOGS, payload, ts=now)
        return window

    def _log_group_failed(self) -> dict[str, bool]:
        """Which of the four log filters failed inside this cycle's sweep.

        ``getattr`` with a default, exactly as :meth:`_client_degradation`
        documents: the real client always defines ``log_group_failed`` and
        resets it at the start of every ``fetch_recent_logs`` call, but a test
        double implementing only the ``fetch_*`` coroutines need not, and this
        manager must not crash on a client that is *less* chatty about its
        failures. An absent flag reads as "nothing reported failed", which is
        the same conclusion the code drew before the flag was wired anywhere.
        """
        flags = getattr(self.client, "log_group_failed", None)
        if not isinstance(flags, dict):
            return dict.fromkeys(LOG_GROUP_SLOT_KEYS, False)
        return {group: bool(flags.get(group)) for group in LOG_GROUP_SLOT_KEYS}

    async def _launch_signers(self, candidates: list[dict[str, Any]]) -> dict[str, str]:
        """``{tx_hash: signer}`` for the hooked ``Initialize`` rows, memoised.

        Costs nothing in the everyday case, because the everyday case is zero
        hooked rows: all nineteen IMD v4 pools that have ever existed are
        third-party and hookless. A row whose signer stays unreadable is simply
        absent from the result and stays a candidate for the next attempt —
        the memo only ever remembers answers, never failures, so a transient
        RPC outage cannot freeze an attribution.

        Every failure mode here — a client that never grew the method, a
        malformed answer, an exception — lands on the same conservative
        outcome: no attribution. That direction is deliberate. An unattributed
        hooked pool renders as an explicit unknown; a wrongly attributed one
        renders as a launch that did not happen.
        """
        wanted = {
            str(row.get("tx_hash") or "").lower()
            for row in candidates
            if row.get("tx_hash")
        }
        missing = sorted(wanted - set(self._launch_signer_memo))
        if missing:
            try:
                found = await self.client.fetch_tx_senders(missing)
            except Exception as exc:        # noqa: BLE001 — never a false launch
                logger.warning("SURF v4 initiator lookup failed: %s", exc)
                found = None
            if isinstance(found, dict):
                if len(self._launch_signer_memo) + len(found) > _SIGNER_MEMO_CAP:
                    self._launch_signer_memo.clear()
                for tx, signer in found.items():
                    address = str(signer or "").strip().lower()
                    if address:
                        self._launch_signer_memo[str(tx).strip().lower()] = address
        return {
            tx: self._launch_signer_memo[tx]
            for tx in wanted
            if tx in self._launch_signer_memo
        }

    @staticmethod
    def _attribute_launches(
        candidates: list[dict[str, Any]], signers: dict[str, str]
    ) -> tuple[list[dict[str, Any]], bool]:
        """Split hooked rows into ``(dev-signed rows, any unattributable?)``.

        Three outcomes per row and they are three different facts:

        * signed by a wallet in :data:`LAUNCH_SIGNERS` — the dev's launch;
        * signed by anyone else — a stranger's pool, dropped outright so it can
          neither reach the hero nor advance WP2's ``v4_tx`` baseline;
        * signer unread — neither claim is available, reported through the
          second return value so the hero can say so instead of guessing.
        """
        rows: list[dict[str, Any]] = []
        unattributed = False
        for row in candidates:
            signer = signers.get(str(row.get("tx_hash") or "").lower())
            if signer is None:
                unattributed = True
                continue
            if signer not in LAUNCH_SIGNERS:
                continue
            rows.append({**row, "initiator": signer})
        return rows, unattributed

    @classmethod
    def _launch_record(
        cls, rows: list[dict[str, Any]], previous: Any
    ) -> dict[str, Any] | None:
        """The verified launch to persist: the one we already hold, else this
        window's earliest dev-signed pool.

        This replaces the old ``hook_live = bool(hooked) or previously_live``
        latch. The difference is not cosmetic: that expression was an
        unconditional OR over unverified third-party input, so one griefing
        transaction pinned the hero to LAUNCHED for the life of the cache file
        and no code path could clear it. Here the stored value is the
        *evidence*, and it is re-validated by :meth:`_valid_launch` on every
        write and every read — so a record that stops naming a dev wallet stops
        producing a launch.

        The earliest row wins when a window holds several: a launch happens
        once, and the row that dates it is the first one.
        """
        held = cls._valid_launch(previous)
        if held is not None:
            return held
        verified = [row for row in rows if cls._valid_launch(row) is not None]
        if not verified:
            return None
        return dict(min(verified, key=lambda r: _opt_float(r.get("ts")) or 0.0))

    @staticmethod
    def _valid_launch(record: Any) -> dict[str, Any] | None:
        """The record if it still evidences a dev-signed hooked pool, else ``None``.

        Re-checked every time rather than trusted once, because this value is
        read back out of a JSON file on disk that a previous build, a hand
        edit, or a corrected address constant can leave inconsistent with the
        vocabulary the running code holds.
        """
        if not isinstance(record, dict):
            return None
        hooks = str(record.get("hooks") or "")
        if not hooks or (_hex_int(hooks) or 0) == 0:
            return None
        if not str(record.get("tx_hash") or ""):
            return None
        if str(record.get("initiator") or "").lower() not in LAUNCH_SIGNERS:
            return None
        return dict(record)

    # -- the slow tier: NFT counters and dev tx pages -------------------------

    async def _pool_nft(self, tiers: set[str], now: float) -> Any:
        """Blockscout's collection counters. No log window is in scope here.

        This coroutine runs *concurrently* with `_pool_logs`, so the realized
        sales genuinely do not exist yet: the slot is stored with counters only
        and `_cycle` folds the sales in from `SLOT_LOGS` afterwards. Reaching
        for a `window` here is a `NameError` on the first successful slow-tier
        fetch, and because `_guard` wraps only the *await*, it escapes past
        `_pool_nft` to `fetch_and_compute`'s outermost guard — turning every
        cycle that refreshes the NFT tier into a blank payload with
        ``degraded == list(SOURCES)``.
        """
        if TIER_SLOW not in tiers:
            return None
        stats = await self._guard(self.client.fetch_nft_stats, "fetch_nft_stats")
        self._note(SOURCE_NFT, stats is not None)
        if stats is not None:
            self.cache.store_last_good(SLOT_NFT, self._nft_payload(stats), ts=now)
        return stats

    async def _pool_activity(
        self, tiers: set[str], now: float, dev_nonce: int | None, ops_nonce: int | None
    ) -> Any:
        """The two dev tx pages — on the slow tier **or** on a nonce change.

        Mirrors :meth:`_pool_channel`, for the same reason: PRD §3 #4 reads
        "both dev nonces every refresh; Blockscout tx page **on change**". The
        nonces come off the fast tier, so a contract creation is *detectable*
        within 30 s; leaving the page on the 420 s tier would then sit on that
        detection for up to seven more minutes, which is the whole margin the
        detector exists to buy.

        The skip does **not** also require a populated slot. It used to, and
        that conjunct disabled the failure backoff on the one path that needs
        it — see :meth:`_pool_market`.

        Every ``return None`` is a skip and must not reach :meth:`_note`.
        """
        cached = self.cache.get_last_good(SLOT_ACTIVITY)
        payload = (cached.payload or {}) if cached is not None else {}
        moved = self._nonce_moved(payload.get("dev_nonce"), dev_nonce) or (
            self._nonce_moved(payload.get("ops_nonce"), ops_nonce)
        )
        if not moved and TIER_SLOW not in tiers:
            return None

        rows = await self._guard(self.client.fetch_dev_activity, "fetch_dev_activity")
        self._note(SOURCE_ACTIVITY, rows is not None)
        if rows is not None:
            self.cache.store_last_good(
                SLOT_ACTIVITY,
                {
                    "rows": await self._with_burn_amounts(self._activity_rows(rows)),
                    "dev_nonce": dev_nonce,
                    "ops_nonce": ops_nonce,
                },
                ts=now,
            )
        return rows

    async def _with_burn_amounts(
        self, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Attach the IMD each bridge-and-burn row actually sent.

        Only ``burn`` rows are asked about, so the read is bounded by how many
        of them are on screen -- three of sixty-three on the captured pages --
        and the client batches those into one POST and memoises the answers.

        A failure here costs the amount, never the row: the panel still has
        every field it had before, and the cell renders the ETH value as it
        always did. That is why this is not behind ``_guard``/``_note`` -- the
        activity group did not fail, and marking it degraded for a missing
        secondary figure would put a staleness marker on a panel that is
        entirely fresh.
        """
        wanted = [row["tx_hash"] for row in rows if row.get("kind") == "burn"]
        if not wanted:
            return rows
        try:
            amounts = await self.client.fetch_burn_amounts(wanted)
        except Exception as exc:            # noqa: BLE001 — secondary figure
            logger.warning("SURF burn amounts unread: %s", exc)
            return rows
        for row in rows:
            amount = amounts.get(row["tx_hash"])
            if amount is not None:
                row["imd_burned"] = _tokens(amount)
        return rows

    @staticmethod
    def _nonce_moved(seen: Any, current: int | None) -> bool:
        """``True`` only when both are known and they differ.

        An unreadable nonce is not a change: an outage must never *cause* a
        fetch storm, and it must never look like activity either.
        """
        previous = _opt_int(seen)
        return previous is not None and current is not None and previous != current

    @staticmethod
    def _nft_payload(stats: Any, sales: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Blockscout counters, plus the sales the **logs** group already decoded.

        The two sources are on different tiers on purpose: counters are
        slow-tier REST, sales are medium-tier logs. ``sales`` is therefore
        passed in already decoded (WP4.9's ``_seaport_sale_rows``, cached under
        ``SLOT_LOGS``) and defaults to ``None`` — this method never reaches for
        a log window, because when `_pool_nft` calls it there is not one.

        ``written`` is WP1.8's **lifetime** distinct-id count and is published
        under both flat names, ``nft_written`` and the hero's
        ``identities_written``. ``transfers_24h`` is the *rate* and is ``None``
        until WP1.8's window walk reaches the 24 h edge — never back-filled from
        the lifetime counter beside it, which is *available* and wrong.
        """
        return {
            "nft_holders": _opt_int(_field(stats, "holders")),
            "nft_transfers_24h": _opt_float(_field(stats, "transfers_24h")),
            "nft_dev_holdings": _opt_int(_field(stats, "dev_holdings")),
            "nft_written": _opt_int(_field(stats, "written")),
            "nft_last_sales": sales,
            # There is no keyless floor source. Never faked, never blank-by-accident.
            # WP0.4 pins ``NftStats.floor_eth`` to ``None`` for the same reason.
            "nft_floor": None,
        }

    @staticmethod
    def _activity_rows(rows: Any) -> list[dict[str, Any]]:
        """Re-check, flatten, scale, sort and cap.

        **WP1.6 owns the poisoning defence** — it filters on the sender and fills
        ``counterparty`` / ``counterparty_label`` / ``kind`` from ``KNOWN_LABELS``
        at construction, where the row's provenance still exists (see the
        ownership note in this file's header, and report the conflict if WP1's
        text still disagrees). This method therefore *reads* those three fields
        instead of deriving them: two implementations of one allowlist is how a
        lookalike eventually inherits its target's label.

        What stays here — and it doubles as the manager's half of the dust
        defence (CLAUDE.md / PRD §6.5): the widget's dust filter keys on the
        *rendered row shape* (``kind``/``value_eth``); this one keys on the
        *sender*, so it drops every dust row without ever inspecting a value —
        a poisoning transfer is inbound by construction, and rule 1 below drops
        every inbound row regardless of its wei amount. That is why the header
        can say "the manager never emits a dust row, because it never emits an
        inbound row at all": there is no falsy-vs-1-gwei distinction to get
        wrong here, because there is no value threshold in this method at all.

        1. **A cheap re-check of rule 1, as defence in depth.** A row whose
           ``from_addr`` is not the wallet its own ``wallet_label`` names cannot
           be one of that wallet's own txs, so it is dropped *and logged* — loud,
           because if it ever fires it is a WP1 bug and not a normal condition.
           This is an assertion about the rule, not a second copy of it.
        2. **``counterparty_known``**, the one derived value: a label the client
           resolved is a known counterparty, a ``None`` is not. The widget dims
           the unknowns without ever importing the address module.
        3. **wei→ETH**, once, at the presentation boundary.
        """
        out: list[dict[str, Any]] = []
        for row in rows or ():
            sender = str(_field(row, "from_addr") or "").lower()
            label_name = str(_field(row, "wallet_label") or "")
            expected = DEV_WALLETS.get(label_name)
            if expected is not None and sender != expected:
                logger.warning(
                    "SURF activity: %s row from %s is not the %s wallet — "
                    "WP1's sender filter let an inbound row through",
                    _field(row, "tx_hash"), sender, label_name,
                )
                continue
            counterparty_label = _field(row, "counterparty_label")
            out.append(
                {
                    "ts": _opt_float(_field(row, "ts")),
                    "wallet_label": label_name,
                    "kind": str(_field(row, "kind") or ""),
                    "counterparty": (
                        counterparty_label
                        if counterparty_label is not None
                        else str(_field(row, "counterparty") or "")
                    ),
                    "counterparty_known": counterparty_label is not None,
                    "value_eth": _tokens(_field(row, "value_wei")),
                    "tx_hash": str(_field(row, "tx_hash") or ""),
                    # Filled in by `_with_burn_amounts` once the receipts are
                    # read; the tx page it comes from carries no IMD figure.
                    "imd_burned": None,
                }
            )
        out.sort(key=lambda r: (r["ts"] is not None, r["ts"] or 0.0), reverse=True)
        return out[:DEV_ACTIVITY_LIMIT]

    async def _pool_channel(
        self, tiers: set[str], now: float, nonce: int | None
    ) -> Any:
        """Fetch the channel bodies on the medium tier, and *immediately* on a new post.

        The nonce is the cheap detector and it is read on the **fast** tier, every
        refresh; the bodies are a Blockscout page. Two rules, in this order:

        1. **A nonce change forces the fetch regardless of the medium tier.** PRD
           §11.1 wants the decoded text within one refresh interval of the tx
           landing. Checking ``TIER_MEDIUM`` first (as this method used to) meant
           a post detected on a 30 s fast-tier cycle waited for the 90 s tier
           before its body was pulled — the signal quoting text the payload did
           not have yet, up to three refreshes running.
        2. **Otherwise the page is fetched whenever the medium tier is due** —
           including on a cold cache, where this method used to fetch
           unconditionally and so bypassed the failure backoff (see
           :meth:`_pool_market`).

        There used to be a rule between those two: *an unchanged nonce skips
        the page*, on the reasoning that nothing was posted for 52 days over
        the real May-to-July gap. It is gone, because the announce nonce is
        blind to the half of this channel the feed exists to thread.

        ``eth_getTransactionCount`` counts the txs an account **sent**. Every
        inbound message — every question a reader writes to the channel, which
        is precisely what :func:`~maxpane_dashboard.analytics.surf_feed.build_threads`
        nests under the post it answers — leaves it untouched. Gated on the
        nonce, a reply reached the screen not when it was written but whenever
        the dev next posted.

        Worse, the gate could poison itself permanently. ``nonce`` here is this
        cycle's **fast-tier** read while ``rows`` is Blockscout's page, and the
        indexer publishes a tx some seconds after the nonce that produced it is
        readable. Store the two together on the wrong cycle and the payload
        claims to have seen a nonce whose tx is not on it — after which the
        cached nonce equals the live nonce on every later cycle, the fetch is
        skipped, and the one number that could have unstuck the slot is already
        recorded as seen. Measured live on 2026-08-24: the channel last-good
        was 46 hours old while every other tier had refreshed inside the last
        seven minutes, and two messages were missing from the feed entirely.

        The cost of dropping it is one Blockscout page per medium tier, which
        is what ``_pool_activity`` already spends on each of two other
        addresses.

        Every ``return None`` here is a *skip*, not a failure: it must not call
        :meth:`_note`, because a skipped group is not degraded and the feed keeps
        rendering its last-good rows without a staleness marker it has not earned.
        """
        cached = self.cache.get_last_good(SLOT_CHANNEL)
        seen = (cached.payload or {}).get("nonce") if cached is not None else None
        moved = nonce is not None and seen is not None and int(seen) != int(nonce)

        if not moved and TIER_MEDIUM not in tiers:
            return None                     # skip: tier not due (fresh, or backed off)

        rows = await self._guard(self.client.fetch_channel_txs, "fetch_channel_txs")
        self._note(SOURCE_CHANNEL, rows is not None)
        if rows is not None:
            self.cache.store_last_good(
                SLOT_CHANNEL, self._channel_payload(rows, nonce), ts=now
            )
        return rows

    def _channel_payload(self, rows: Any, nonce: int | None) -> dict[str, Any]:
        """The cached channel slot: what the feed renders *and* what POST reads.

        ``tx_count`` is the **unclipped** row count — ``feed_items`` is capped at
        :data:`FEED_ITEM_LIMIT`, so ``len(items)`` would saturate and silently
        stop being a tx count. ``last_text`` / ``last_ts`` are the newest
        *self*-post, which is what NEW POST quotes; a reply is not the dev posting.
        """
        items = self._feed_items(rows)
        selfs = [i for i in items if i.get("kind") == "self" and i.get("ts") is not None]
        newest = max(selfs, key=lambda i: i["ts"]) if selfs else None
        return {
            "nonce": nonce,
            "tx_count": len(list(rows or ())),
            "items": items,
            "last_text": (newest or {}).get("text"),
            "last_ts": (newest or {}).get("ts"),
        }

    def _bridge_rows(self, window: Any, now: float) -> list[dict[str, Any]]:
        """OFT mints as ``{ts, tx_hash, amount, to_label}`` (WP2's shape).

        ``Transfer(from, to, value)``: ``from``/``to`` are indexed, the amount is
        the whole payload. WP1 pre-filters to ``from == 0x0`` and ``to ∈ {dev,
        ops}``, so every row here is unambiguous staging — IMD has no mint
        function, and on 2026-08-07 the first of these landed 264 s before the
        LP add.
        """
        rows: list[dict[str, Any]] = []
        for log in _field(window, "bridge_mints") or ():
            topics = list((log or {}).get("topics") or ())
            to_addr = ("0x" + topics[2][-40:]).lower() if len(topics) > 2 else ""
            rows.append(
                {
                    "ts": _log_ts(log, now),
                    "tx_hash": str(log.get("transactionHash") or ""),
                    "amount": _tokens(_hex_int(log.get("data"))),
                    "to_label": KNOWN_LABELS.get(to_addr, ""),
                    **_log_position(log),
                }
            )
        return rows

    def _hooked_candidates(self, window: Any, now: float) -> list[dict[str, Any]]:
        """Hooked v4 ``Initialize`` rows as ``{ts, tx_hash, hooks}`` (WP2's shape).

        ``Initialize(id, currency0, currency1, fee, tickSpacing, hooks,
        sqrtPriceX96, tick)`` — three indexed args, so ``hooks`` is the third word
        of ``data``. Every one of the 19 existing IMD v4 pools is third-party and
        **hookless**, so the hookless rows are filtered out here: they can never
        be the launch and must never advance WP2's ``v4_tx`` baseline past a
        real one.

        A non-zero hooks address makes a row a **candidate**, not the launch.
        ``PoolManager.initialize()`` is permissionless and the event payload
        carries nothing about who called it, so this method deliberately stops
        one step short of a verdict; :meth:`_attribute_launches` supplies the
        part a stranger cannot forge.
        """
        rows: list[dict[str, Any]] = []
        for log in _field(window, "v4_initializes") or ():
            hooks = _word_addr((log or {}).get("data"), 2)
            # `_hex_int`, not `int(hooks, 16)`: the payload is third-party text
            # and a non-hex data word would raise out of `_pool_logs`, which
            # `_guard` does not cover — one bad row would blank all 48 keys.
            if not hooks or (_hex_int(hooks) or 0) == 0:
                continue
            rows.append(
                {
                    "ts": _log_ts(log, now),
                    "tx_hash": str((log or {}).get("transactionHash") or ""),
                    "hooks": hooks,
                    **_log_position(log),
                }
            )
        return rows

    @staticmethod
    def _eth_equivalent(items: list[list[str]]) -> float | None:
        """What the payment legs of one Seaport array are worth in ETH.

        ``None`` -- never ``0.0`` -- when any payment leg is in a token this
        dashboard cannot express in ether. That distinction is the whole bug
        this function was extracted for: summing only ``itemType == 0`` and
        calling the result a price rendered every WETH sale as ``0.000 ETH``,
        which reads as a free transfer rather than as an unpriceable one.

        WETH counts at 1:1 because it *is* ether, wrapped -- not a conversion
        and not a rate this would have to fetch. Anything else would need one,
        and there is no keyless source for it, so the row is refused rather
        than guessed. A mixed-currency order is refused for the same reason:
        a partial sum is a wrong price, not a rounded one.

        ``itemType`` 2 and 3 are the NFT legs. They are not payment and do not
        make an order unpriceable -- an accepted bid always carries one.
        """
        wei = 0
        for item in items:
            item_type = _hex_int("0x" + item[0])
            amount = _hex_int("0x" + item[3]) or 0
            if item_type == 0:                              # NATIVE
                wei += amount
            elif item_type == 1:                            # ERC20
                if _word_addr(item[1], 0).lower() != WETH.lower():
                    return None
                wei += amount
        return wei / WEI

    @staticmethod
    def _seaport_sale_rows(window: Any, now: float) -> list[dict[str, Any]]:
        """Realized IDMD sales as ``{ts, token_id, eth}`` — PRD §4's NFT panel.

        ``OrderFulfilled(bytes32 orderHash, address indexed offerer, address
        indexed zone, address recipient, SpentItem[] offer,
        ReceivedItem[] consideration)``. Two indexed args, so ``data`` opens
        with ``orderHash``, ``recipient`` and the two array *offsets*;
        ``SpentItem`` is 4 words ``(itemType, token, identifier, amount)`` and
        ``ReceivedItem`` is those plus a ``recipient``.

        **Seaport describes a matched trade from whichever side was
        fulfilled, and both sides are sales.** A *listing fill* puts the NFT
        in the ``offer`` and the payment in the ``consideration``. An
        *accepted bid* is the mirror image: the buyer's payment is the offer
        and the NFT comes back in the consideration. This used to require
        IDMD in the offer array and drop everything else, on the reasoning
        that the remainder was an order paid **in** IDMD — a purchase of
        something else. That reasoning describes a real shape, but the filter
        did not select it: what it actually dropped was every bid anyone had
        ever accepted. Measured 2026-08-25, one transaction alone
        (``0xb0538d32…``) carried five of them, invisible.

        So the NFT is looked for on both sides, and the price is read off
        whichever side it is *not* on. That price is an ETH-equivalent, not a
        native sum — see :meth:`_eth_equivalent`, and the ``0.000 ETH`` those
        seven sales rendered before it existed.

        **One trade can emit both logs, and then it is still one sale.** They
        are deduplicated on ``(tx_hash, token_id)`` and the *bid* side wins,
        because it carries what the buyer actually paid: on ``0xa3b58d42…``
        the bid says 0.243 and the listing says 0.24057, the difference being
        a marketplace fee whose leg lives only in the bid's own log. Keeping
        both would be worse than the zero this replaced — two prices for one
        NFT, each plausible.

        On the pinned native fill ``0x5b4d1b44…eadad2`` the two orders come to
        0.18 and 0.1838989 ETH and those sum to the transaction's own
        ``value`` of 363898900000000000 wei. That identity is the cheapest
        available proof this walk is right: get an offset wrong and the sum
        stops matching. It survives all of the above unchanged — two listing
        fills, two token ids, nothing to deduplicate.
        """
        # (tx_hash, token_id) -> (row, from_the_bid_side)
        best: dict[tuple[str, int], tuple[dict[str, Any], bool]] = {}
        for log in _field(window, "seaport_sales") or ():
            words = _data_words((log or {}).get("data"))
            offer = _abi_array(words, 2, 4)
            consideration = _abi_array(words, 3, 5)

            def _identity(items: list[list[str]]) -> int | None:
                return next(
                    (
                        _hex_int("0x" + item[2])
                        for item in items
                        if _word_addr(item[1], 0).lower() == IDMD_NFT.lower()
                    ),
                    None,
                )

            token_id = _identity(offer)
            from_bid = False
            paid_with = consideration
            if token_id is None:
                token_id = _identity(consideration)
                from_bid = True
                paid_with = offer
            if token_id is None:
                continue                # this order does not move an identity

            eth = SurfManager._eth_equivalent(paid_with)
            if eth is None:
                continue                # priced in something we cannot express

            key = (str((log or {}).get("transactionHash") or ""), token_id)
            row = {"ts": _log_ts(log, now), "token_id": token_id, "eth": eth}
            previous = best.get(key)
            if previous is None or (from_bid and not previous[1]):
                best[key] = (row, from_bid)

        rows = [row for row, _ in best.values()]
        rows.sort(key=lambda r: (r["ts"] is not None, r["ts"] or 0.0), reverse=True)
        return rows[:NFT_SALES_LIMIT]

    @staticmethod
    def _identity_writes(window: Any) -> int | None:
        """Distinct identities written **in the recent log window**.

        Not the hero's number, and the two must never be swapped (wp1.md open
        issue 9). ``NftStats.written`` is a *lifetime* count off Blockscout's
        registry log view — 1 of 2000, written 2026-05-14, months outside any
        window this app opens. This one answers "writes seen since breakfast"
        and is the only thing PRD §3 #3 asks the GATE row's detail to carry.

        Counted over distinct ``topics[1]``, never ``len(rows)``:
        ``IdentityHashUpdated(uint256 indexed id, string, bool)`` fires again
        when a holder replaces their hash, and that is one identity written.
        WP1 already filtered the group by topic0, so the id is topics[1] on
        every row here.
        """
        rows = _field(window, "identity_updates")
        if rows is None:
            # Unreachable through ``LogWindow`` -- the field is
            # ``tuple[dict, ...] = ()`` and no input can make it ``None``, as
            # its own docstring says. Kept because this method also runs
            # against a ``window`` double in tests, but it is NOT the filter's
            # failure guard: ``LOG_GROUP_SLOT_KEYS`` is, and it is what stops a
            # dead ``IdentityHashUpdated`` filter rendering "closed · 0 written".
            return None
        ids: set[str] = set()
        for row in rows:
            topics = list((row or {}).get("topics") or ())
            if len(topics) > 1 and topics[1]:
                ids.add(str(topics[1]).lower())
        return len(ids)

    def _feed_items(self, rows: Any) -> list[dict[str, Any]]:
        """Classify and decode the channel rows into widget-ready primitives.

        ``kind`` and ``text`` both come from the pure layer, so the classification
        rules and the UTF-8 decoder have exactly one implementation each; WP0.4's
        ``ChannelTx`` deliberately carries neither.

        ``label`` is what an outbound channel call *did* — Blockscout's decoded
        ``method`` when it has one, the 4-byte selector when it does not. NEW
        DEPLOY renders its ``action`` rows with it (Task WP4.11), and both halves
        are third-party-influenced strings escaped at the widget, never here.

        ``value_eth`` is what the row is *for* when it has neither: a plain
        value transfer has empty calldata by definition, so ``text`` is
        ``None`` and ``label`` is ``""``, and the amount is the only fact
        left. The widget falls back to it rather than rendering a badge
        beside a blank line. ``None`` and not ``0.0`` when ``value_wei`` will
        not read -- a zero-value post is the *normal* shape on this channel,
        so a sentinel zero here would be indistinguishable from the truth.

        ``to_addr`` (Task 1's ``SURF_ROW_KEYS["feed_items"]``, Task 3's own
        addition to this row) is threading's raw material: an ``answer``'s
        recipient is who asked the question it answers, and a later task nests
        the row under that question by matching on it. Three-state, same as
        ``_parse_channel_tx`` already documents for the field it comes from:
        ``None`` for a contract creation, never ``""``.
        """
        items: list[dict[str, Any]] = []
        for row in rows or ():
            from_addr = str(_field(row, "from_addr") or "")
            to_addr = str(_field(row, "to_addr") or "") or None
            input_hex = str(_field(row, "input_hex") or "")
            kind = _safe_call(
                classify_channel_tx,
                from_addr,
                to_addr or "",
                _opt_int(_field(row, "value_wei")) or 0,
                input_hex,
                # Tri-state, straight through: the classifier reclassifies on
                # `False` alone, so a page that did not state a status leaves
                # every row on its own shape.
                _field(row, "success"),
                default=None,
            )
            items.append(
                {
                    "ts": _opt_float(_field(row, "ts")),
                    "kind": kind,
                    "from_addr": from_addr,
                    "to_addr": to_addr,
                    "from_label": KNOWN_LABELS.get(from_addr.lower()),
                    "text": _safe_call(decode_utf8_calldata, input_hex, default=None),
                    "tx_hash": str(_field(row, "tx_hash") or ""),
                    "label": (
                        f"{_field(row, 'method')}()"
                        if _field(row, "method")
                        else (input_hex[:10] if len(input_hex) >= 10 else "")
                    ),
                    "value_eth": _tokens(_field(row, "value_wei")),
                }
            )
        items.sort(key=lambda i: (i["ts"] is not None, i["ts"] or 0.0), reverse=True)
        return items[:FEED_ITEM_LIMIT]

    # -- the launchpad tier: v4 pool, decoy scan, hook/factory/executor -------
    #
    # Its own tier (``TIER_LAUNCHPAD``, curator's ``TIER_ANALYSIS`` precedent)
    # and its own detached sweep: ``_spawn_launchpad`` schedules
    # ``_pool_launchpad`` and never awaits it, so first paint never sits behind
    # a 146-coin ``getLogs`` sweep. ``_cycle`` captures whatever this slot
    # already held *before* offering a new sweep — see ``_spawn_launchpad``'s
    # docstring for why that capture-then-spawn order, not "no ``await`` after
    # spawning", is what makes the read race-free regardless of how the event
    # loop happens to interleave this cycle's big ``gather`` with an in-flight
    # or freshly spawned sweep.

    def _spawn_launchpad(self, tiers: set[str], now: float) -> Any:
        """Start the v4/launchpad sweep **detached**; never wait for it.

        ``fetch_pool_v4`` + ``fetch_decoy_pool_count`` + ``fetch_launchpad``
        together are a handful of ``eth_call`` rounds plus three ``getLogs``
        sweeps over the launchpad's own (wide) window — far cheaper than
        curator's whole-history cross-check, but still enough that awaiting it
        in ``_cycle`` would put first paint behind it, which is exactly the
        tripwire this module's test suite pins by timeout rather than by
        assertion. ``TIER_LAUNCHPAD`` reads as immediately due on every fresh
        launch (tier due-marks are not persisted across restarts — see
        ``data/surf_cache.py``), so this is offered from the very first cycle,
        not only from later ones.

        One at a time: while a sweep is in flight the tier stays due (only a
        *completed* ``_pool_launchpad`` marks it fetched or failed), so every
        cycle offers again and the guard here is what keeps a slow read from
        stacking up behind a fast poll.
        """
        if TIER_LAUNCHPAD not in tiers:
            return None
        running = self._launchpad_task
        if running is not None and not running.done():
            logger.debug("SURF launchpad sweep still in flight; not starting another")
            return running
        self._launchpad_task = asyncio.ensure_future(
            self._launchpad_detached(tiers, now)
        )
        return self._launchpad_task

    async def _launchpad_detached(self, tiers: set[str], now: float) -> None:
        """``_pool_launchpad`` with nobody to raise at.

        A detached task's exception surfaces as an "exception was never
        retrieved" line at garbage-collection time and never as a
        degradation, so it is caught here and logged instead.
        ``CancelledError`` is re-raised: that one is :meth:`close` doing its
        job and must propagate so the cancellation actually completes.
        """
        try:
            await self._pool_launchpad(tiers, now)
        except asyncio.CancelledError:
            raise
        except Exception as exc:        # noqa: BLE001 — nobody awaits this task
            self._error_count += 1
            logger.warning("SURF launchpad sweep failed: %s", exc)

    async def _cancel_launchpad(self) -> None:
        """Stop an in-flight launchpad sweep and wait for it to actually be gone."""
        task = self._launchpad_task
        self._launchpad_task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
            logger.debug("SURF launchpad sweep stopped on close: %s", exc)

    async def _pool_launchpad(self, tiers: set[str], now: float) -> Any:
        """Read the v4 pool, the decoy scan and the launchpad getters+logs.

        Mirrors :meth:`_pool_nft`'s shape: a simple ``ok`` gate, never
        raising. ``fetch_pool_v4`` and ``fetch_launchpad`` never return bare
        ``None`` on their own (their own docstrings: "the pool is real, so
        there is no does-not-exist case, only 'we could not read it right
        now'") — a ``None`` here means :meth:`_guard` caught an actual
        exception, which is rare but not impossible, so ``ok`` still checks
        for it rather than assuming success.

        ``fetch_decoy_pool_count`` needs the *real* pool id ``fetch_pool_v4``
        resolves — telling a stranger's decoy from the real pool is the whole
        point of that call — so the two cannot be issued concurrently.
        ``fetch_launchpad`` is independent of both and runs alongside
        ``fetch_pool_v4``. A decoy-scan failure on its own does **not**
        invalidate the rest of the sweep: it degrades to ``None`` inside an
        otherwise-successful payload, the same granularity every other group
        in this module already uses (e.g. ``NftStats.transfers_24h`` beside a
        healthy ``holders``).

        Task 8: the cursor is read out of ``SLOT_LAUNCHPAD``'s own last-good
        payload **before** calling the client — the previous sweep's own
        cache write, never this cycle's, so a cursor is available from the
        very first sweep after a restart (last-good survives the process,
        this cycle's ``launchpad_state`` does not exist yet). It is handed to
        ``fetch_launchpad`` opaquely: this method does not know or check its
        shape, only that ``dict.get`` on a non-dict slot answers ``None``
        (a cold sweep), which is the same safe degradation
        ``_coerce_launchpad_resume`` gives a corrupt persisted one on the
        client side. Skipping this read (passing ``resume=None``
        unconditionally) does not fail loudly — every existing assertion
        about a *healthy* sweep still passes, because the client answers the
        same fixture either way — it just silently turns every sweep into a
        cold ~34k-block re-read forever; the round-trip test earns its keep
        by mutation, not by inspection.
        """
        if TIER_LAUNCHPAD not in tiers:
            return None
        prior_entry = self.cache.get_last_good(SLOT_LAUNCHPAD)
        prior_slot = prior_entry.payload if prior_entry is not None else None
        cursor = prior_slot.get("cursor") if isinstance(prior_slot, dict) else None
        pool_state, launchpad_state = await asyncio.gather(
            self._guard(self.client.fetch_pool_v4, "fetch_pool_v4"),
            self._guard(
                lambda: self.client.fetch_launchpad(resume=cursor),
                "fetch_launchpad",
            ),
        )
        real_pool_id = _field(pool_state, "pool_id")
        decoy_result = await self._guard(
            lambda: self.client.fetch_decoy_pool_count(real_pool_id),
            "fetch_decoy_pool_count",
        )
        decoy_count: int | None = None
        decoy_newest_fee_bps: int | None = None
        if isinstance(decoy_result, tuple) and len(decoy_result) == 2:
            decoy_count = decoy_result[0]
            newest = decoy_result[1]
            if isinstance(newest, dict):
                # Task 6 fix round 1: the newest decoy's own fee tier, fed to
                # Task 7's DECOY POOL detail line via `_readings`. Not a
                # `SURF_KEYS` entry — no widget renders it yet — so it is
                # cached here rather than surfaced through the flat payload.
                decoy_newest_fee_bps = _opt_int(newest.get("fee"))
        # ``fetch_launchpad`` never returns ``None`` -- it promises a state
        # and keeps that promise by returning an honestly all-``None`` one --
        # so ``launchpad_state is not None`` was true for a *total* sweep
        # failure too, and the all-``None`` payload then overwrote a good
        # last-good. The tier's whole design is the opposite of that: it
        # carries its own slower ``as of HH:MM`` clock (Task 9) precisely so
        # stale launchpad values can be shown honestly rather than discarded.
        #
        # This branch stopped being a one-panel concern on 2026-08-24: the
        # hero's LAUNCHPAD and FLOW boxes ride these keys now, so one failed
        # sweep blanked half the hero row rather than degrading one panel.
        # Nothing is stored on a blank read, so the slot keeps its previous
        # payload *and its previous timestamp* -- the marker goes stale, which
        # is the true statement, instead of a fresh marker over dashes.
        blank = _launchpad_state_is_blank(launchpad_state)
        ok = pool_state is not None and launchpad_state is not None and not blank
        if ok:
            self.cache.store_last_good(
                SLOT_LAUNCHPAD,
                self._launchpad_payload(
                    pool_state, decoy_count, decoy_newest_fee_bps, launchpad_state
                ),
                ts=now,
            )
            self.cache.mark_fetched(TIER_LAUNCHPAD, now)
        else:
            self.cache.mark_failed(TIER_LAUNCHPAD, now)
        return {
            "pool": pool_state,
            "decoy_count": decoy_count,
            "launchpad": launchpad_state,
            "ok": ok,
        }

    @staticmethod
    def _launchpad_payload(
        pool_state: Any,
        decoy_count: int | None,
        decoy_newest_fee_bps: int | None,
        launchpad_state: Any,
    ) -> dict[str, Any]:
        """The whole combined slot: pool, decoy scan, launchpad — one dict,
        one slot, one ``launchpad_as_of_hhmm`` marker for all of it.

        Wei-native (WP0's "models are wei-native, the flat dict is the
        presentation boundary"): ``_cycle`` divides exactly once when it reads
        this back. Keys mirror the source dataclasses' own field names
        (``coin_count``, not ``launchpad_coin_count``) rather than the flat
        ``SURF_KEYS`` vocabulary — this slot caches what the client returned,
        not the PRD's name for it; the mapping to flat names lives in
        ``_cycle`` alone, matching every other ``*_wei`` field in this
        module. ``total_real_imd_wei``/``burn_fee_bps``/``creator_fee_bps``
        are read off ``LaunchpadState`` by the client but have no
        ``SURF_KEYS`` home yet, so they are not cached here — nothing reads
        them. ``decoy_newest_fee_bps`` (fix round 1) is the same story:
        cached for Task 7's DECOY POOL detector to read via ``_readings``,
        no ``SURF_KEYS`` entry of its own. ``swaps_by_coin`` (fix round 2) is
        cached the same way, and deliberately *separate* from ``coins``
        below: ``coins`` is the render-capped row list this slot has always
        carried, ``swaps_by_coin`` is the **full** per-coin in-window swap
        count ``SurfClient.fetch_launchpad`` now also returns — the input
        Task 7's ``hot_coin_threshold`` takes a median over. Feeding it the
        capped list instead (as the fix-round-1 version of this method did)
        biases that median several times too high, because the cap keeps
        exactly the busiest coins and drops everything else — see
        ``LaunchpadState.swaps_by_coin``'s own docstring for the mechanism.
        ``sqrt_price_x96`` (fix round 10a) is cached the same way: the raw
        input to ``surf_v4.price_eth_per_imd``, which ``_cycle`` turns into
        the authoritative on-chain ``imd_price_usd`` and the market
        cross-check -- no ``SURF_KEYS`` entry of its own either, since the
        derived USD figures are what the payload actually publishes.
        ``PoolV4State.liquidity`` (fix round 12a) is no longer cached here at
        all: it fed only ``pool_liquidity_raw``, which came out of
        ``SURF_KEYS`` because no widget ever read it -- unlike the fields
        above, it has no other consumer to keep it alive for.

        Task 8 adds four more of the same shape. ``cursor`` is the odd one
        out among them -- an opaque ``dict | None`` this method never
        inspects, only stores, so :meth:`_pool_launchpad`'s *next* call can
        read it back off this same slot and hand it to ``fetch_launchpad``
        as ``resume``; drop this key and the sweep still renders correctly
        today and silently goes cold (re-reads the whole launchpad history)
        on every future poll, which is why the round-trip is asserted at
        the cache boundary and not inferred from a healthy payload.
        ``launch_count``/``new_24h``/``creator_count`` are plain aggregates,
        mirroring ``LaunchpadState``'s own field names like everything above
        them: ``launch_count`` is deliberately kept *separate* from
        ``coin_count`` (the factory's own claim) rather than merged into it
        -- ``_cycle`` publishes both under different flat keys so the two
        can be compared at render time, per Task 1's contract.
        """
        return {
            "pool_id": _field(pool_state, "pool_id"),
            "pool_fee": _opt_int(_field(pool_state, "lp_fee")),
            "pool_id_source": _field(pool_state, "pool_id_source"),
            "sqrt_price_x96": _opt_int(_field(pool_state, "sqrt_price_x96")),
            "decoy_pool_count": decoy_count,
            "decoy_newest_fee_bps": decoy_newest_fee_bps,
            "coin_count": _opt_int(_field(launchpad_state, "coin_count")),
            "imd_to_burn_wei": _opt_int(_field(launchpad_state, "imd_to_burn_wei")),
            "executor_balance_wei": _opt_int(
                _field(launchpad_state, "executor_balance_wei")
            ),
            "min_bridge_wei": _opt_int(_field(launchpad_state, "min_bridge_wei")),
            "bridge_amount_wei": _opt_int(
                _field(launchpad_state, "bridge_amount_wei")
            ),
            "creator_eth_owed_wei": _opt_int(
                _field(launchpad_state, "creator_eth_owed_wei")
            ),
            "burned_total_wei": _opt_int(_field(launchpad_state, "burned_total_wei")),
            "swap_count": _opt_int(_field(launchpad_state, "swap_count")),
            "trader_count": _opt_int(_field(launchpad_state, "trader_count")),
            # Final fix wave (I1): the {pool_id: ticker} label map that goes
            # with the pool-keyed `swaps_by_coin` below. Cached for the same
            # reason -- no `SURF_KEYS` home, one detector consumer -- and it
            # is a *label* map only: nothing joins on a ticker any more.
            "coin_tickers": _field(launchpad_state, "coin_tickers"),
            "coins": SurfManager._launchpad_coin_rows(
                SurfManager._coins_if_swept(launchpad_state)
            ),
            "swaps_by_coin": _field(launchpad_state, "swaps_by_coin"),
            "launch_count": _opt_int(_field(launchpad_state, "launch_count")),
            "new_24h": _opt_int(_field(launchpad_state, "new_24h")),
            "creator_count": _opt_int(_field(launchpad_state, "creator_count")),
            "cursor": _field(launchpad_state, "cursor"),
            "activity": SurfManager._launchpad_activity_rows(
                _field(launchpad_state, "activity")
            ),
            "burnkeepers": SurfManager._burnkeeper_rows(
                _field(launchpad_state, "burnkeepers")
            ),
        }

    @staticmethod
    def _coins_if_swept(launchpad_state: Any) -> Any:
        """``LaunchpadState.coins`` when the sweep behind it ran; else ``None``.

        **``coins`` is the one log-derived launchpad field with no failure
        shape of its own**, and that is why this exists. ``activity`` and
        ``burnkeepers`` are handed to the manager as ``None`` when the sweep
        failed, so their row-builders can answer ``None`` and their panels
        can say *unavailable*. ``coins`` cannot: the client does not read it
        off the sweep at all, it *derives* it by running
        ``analytics/surf_launchpad.rank_coins`` over the sweep's launch list
        — and ``_failed_launchpad_sweep``'s launch list is ``[]``, so a total
        log-pool outage arrives here as an empty tuple that is
        indistinguishable, by inspection of that field alone, from a
        launchpad nobody has launched a coin on.

        It matters because the two pools fail independently. The launchpad
        *getters* ride the STATE pool and all four log sweeps ride the LOGS
        pool ("state and logs need different endpoint pools" —
        ``surf_client``), so "logs down, state up" is an ordinary failure
        here, not a corner. ``coin_count`` survives it, so
        :func:`_launchpad_state_is_blank` is ``False``, the slot is written
        and its ``as of HH:MM`` marker is refreshed — and before this check
        existed, a good coin list was replaced by an empty one under a title
        asserting 146 coins, behind a marker that read live, while the two
        panels beside it correctly said *unavailable*. One outage, three
        panels, two different stories.

        ``launch_count`` is the signal because it is the *same sweep's* count
        of the *same* ``Launched`` events ``coins`` is ranked from
        (``len(merged)`` in ``SurfClient._launchpad_logs``), so it answers
        exactly the question being asked: was that population read at all?
        A genuinely empty launchpad answers ``0`` and its ``coins`` stay the
        representable ``()`` — 0 is a reading, per this module's own rule.
        Deliberately not ``swap_count`` or ``burned_total_wei``: those count
        a different event and a launch with no swap yet is a real thing.
        """
        if _field(launchpad_state, "launch_count") is None:
            return None
        return _field(launchpad_state, "coins")

    @staticmethod
    def _launchpad_coin_rows(coins: Any) -> list[dict[str, Any]] | None:
        """``LaunchpadCoin`` rows -> ``SURF_ROW_KEYS["launchpad_coins"]`` dicts.

        **``None`` in, ``None`` out**, exactly like its two siblings
        :meth:`_launchpad_activity_rows` / :meth:`_burnkeeper_rows` and like
        :meth:`_with_mcap_usd` downstream of it: ``for coin in coins or ()``
        turned "nobody could read the launchpad" into "the launchpad has no
        coins", and ``widgets/surf/launchpad.py`` renders those two
        differently on purpose (``None`` -> ``⚠ launchpad unavailable``,
        ``[]`` -> an empty, correctly-marked table). The caller that decides
        which of the two a sweep produced is :meth:`_coins_if_swept`; a
        ``None`` can also arrive from a replayed or hand-edited payload,
        which this method already treats as third-party input below.

        ``creator_known`` is **derived here**, not carried on ``LaunchpadCoin``
        (WP0's dataclass has no such field): the client's own ``rank_coins``
        input already computes it from :data:`KNOWN_LABELS`
        (``surf_client._label_for``) but the dataclass construction drops it
        on the floor, so it is re-derived from the raw ``creator`` address
        against the same allowlist — never a second, divergent implementation
        of "known", just the one ``KNOWN_LABELS`` lookup this module already
        uses for ``dev_activity``/``feed_items``.

        ``ticker``/``name`` are carried through **raw**: ``launch(string,
        string)`` is permissionless and both are attacker-chosen, escaped at
        the widget and never here (the same rule ``feed_items``' ``text`` and
        ``label`` follow).

        Task 7 widened the ranking window from an hour to a day and Task 1
        renamed the row shape to match: ``change_1h_pct``/``swaps_1h`` are
        gone, replaced by ``change_24h_pct`` (still ``float | None`` -- it is
        unmeasured, not zero, below two in-window priced swaps) and
        ``swaps_24h``/``swaps_all`` (both a representable ``int`` zero, never
        ``None``, per ``LaunchpadCoin``'s own docstring). ``_opt_int``/
        ``_opt_float`` are still applied rather than trusted raw: a
        hand-edited last-good payload replayed through ``_launchpad_coin_rows``
        on some future call site is exactly the kind of third-party input
        this module never trusts without coercing first.
        """
        if coins is None:
            return None
        rows: list[dict[str, Any]] = []
        for coin in coins:
            creator = str(_field(coin, "creator") or "")
            rows.append(
                {
                    "ticker": _field(coin, "ticker"),
                    "name": _field(coin, "name"),
                    "creator": creator,
                    "creator_known": KNOWN_LABELS.get(creator.lower()) is not None,
                    "age_s": _opt_float(_field(coin, "age_s")),
                    "price_eth": _opt_float(_field(coin, "price_eth")),
                    "mcap_eth": _opt_float(_field(coin, "mcap_eth")),
                    # Filled at assembly from the MARKET tier, never here:
                    # this row is what gets cached, and the cache slot is the
                    # launchpad tier's. See `_with_mcap_usd`.
                    "mcap_usd": None,
                    "change_24h_pct": _opt_float(_field(coin, "change_24h_pct")),
                    "swaps_24h": _opt_int(_field(coin, "swaps_24h")),
                    "swaps_all": _opt_int(_field(coin, "swaps_all")),
                    "imd_burned": _opt_float(_field(coin, "imd_burned")),
                }
            )
        return rows

    @staticmethod
    def _launchpad_activity_rows(events: Any) -> list[dict[str, Any]] | None:
        """`LaunchpadEvent`s -> `SURF_ROW_KEYS["launchpad_activity"]` dicts.

        `None` in, `None` out: a failed sweep is not an empty feed, and the
        panel says two different things about them.

        `ticker` rides through **raw** -- attacker-chosen, escaped at the
        widget, never here (`feed_items`' own rule). `wallet_known` is the
        one `KNOWN_LABELS` lookup this module already uses everywhere else.
        """
        if events is None:
            return None
        rows: list[dict[str, Any]] = []
        for event in events:
            wallet = str(_field(event, "wallet") or "")
            rows.append({
                "kind": str(_field(event, "kind") or ""),
                "ticker": _field(event, "ticker"),
                "wallet": wallet,
                "wallet_known": KNOWN_LABELS.get(wallet.lower()) is not None,
                "eth": _opt_float(_field(event, "eth")),
                "age_s": _opt_float(_field(event, "age_s")),
            })
        return rows

    @staticmethod
    def _burnkeeper_rows(keepers: Any) -> list[dict[str, Any]] | None:
        """`Burnkeeper`s -> `SURF_ROW_KEYS["launchpad_burnkeepers"]` dicts.

        `eth_paid` stays `float | None` through the coercion: `_opt_float`
        must not be allowed to turn an unread fee into a zero one.
        """
        if keepers is None:
            return None
        rows: list[dict[str, Any]] = []
        for keeper in keepers:
            wallet = str(_field(keeper, "wallet") or "")
            rows.append({
                "wallet": wallet,
                "wallet_known": KNOWN_LABELS.get(wallet.lower()) is not None,
                "imd_burned": _opt_float(_field(keeper, "imd_burned")),
                "eth_paid": _opt_float(_field(keeper, "eth_paid")),
                "burns": _opt_int(_field(keeper, "burns")),
            })
        return rows

    @staticmethod
    def _with_mcap_usd(rows: Any, eth_usd: Any) -> list[dict[str, Any]] | None:
        """Attach `mcap_usd` to cached coin rows, at payload assembly.

        **`None` in, `None` out** -- fix round 1's Critical. `rows is None`
        means the launchpad tier has never completed a sweep (a cold cache),
        which is a different fact from "swept and found zero coins"
        (`rows == []`). `widgets/surf/launchpad.py` renders the two
        differently (`None` -> `⚠ launchpad unavailable`, `[]` -> an empty,
        correctly-marked table), and this function sits between the cache
        slot and that widget, so it must preserve the distinction rather than
        flatten both into `[]` via `rows or ()`.

        **This is the one cross-tier value on this panel.** `mcap_eth` is the
        launchpad tier's own (a slow-tier price times a supply from a slow-
        tier log); `eth_usd` is the market tier's, and it is fresher. The
        multiplication happens here because this is the only place both are
        in hand, and it happens at *assembly* rather than in the cache so
        that no USD figure is ever persisted against the slow tier's
        timestamp.

        `eth_usd is None` (CoinGecko down) leaves `mcap_usd` `None` and the
        cell renders a dash. It never falls back to the ETH figure -- an ETH
        number under a `$` header is worse than no number. And it never
        renders 0: `eth_usd <= 0` is not a plausible reading (a live ETH
        price cannot be zero or negative) and is treated exactly like a
        missing one, rather than trusting a caller two layers away
        (`SurfClient`, which already rewrites a non-positive read to `None`)
        to keep this function's own promise for it.
        """
        if rows is None:
            return None
        usd = _opt_float(eth_usd)
        if usd is not None and usd <= 0:
            usd = None
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            mcap = _opt_float(row.get("mcap_eth"))
            out.append({
                **row,
                "mcap_usd": None if (usd is None or mcap is None) else mcap * usd,
            })
        return out

    @staticmethod
    def _pool_venue(lp_state: Any) -> str | None:
        """Which pool is currently live, derived from ``ChainState.lp_state``.

        ``"live"`` means the ops wallet's v3 NFPM position still answers, so
        v3 is still the venue; ``"gone"`` means it now reverts
        ``Invalid token ID`` — the migration happened, so v4 is live.
        ``None`` (no sub-call answered) stays an honest unknown rather than a
        guess either way.
        """
        if lp_state == "live":
            return "v3"
        if lp_state == "gone":
            return "v4"
        return None

    # -- signals -------------------------------------------------------------

    def _readings(
        self,
        data: dict[str, Any],
        nonces: Any,
        channel: dict[str, Any],
        activity_rows: list[dict[str, Any]],
        launchpad_slot: dict[str, Any] | None = None,
        launchpad_ts: float | None = None,
        state: Any = None,
    ) -> dict[str, Any]:
        """This cycle's values for the nine detectors, keyed by ``READING_KEYS``
        plus the five Task 7 will need that ``READING_KEYS`` does not name yet.

        Built as ``dict.fromkeys(READING_KEYS)`` and filled in place, so a key WP2
        adds arrives here as an explicit ``None`` instead of as a detector that
        quietly never fires again.

        Four rules the body encodes:

        1. **Unread is ``None`` — never ``0``, ``[]`` or ``False``.** An empty list
           is the opposite claim ("the window was read and held nothing"), and it
           is the only thing that lets BRIDGE STAGE and BURN reach ``ok`` at all.
        2. **The three chain scalars are taken off the assembled payload**, not
           re-read off the model, so the hero panel and the detectors cannot
           disagree about liquidity, the gate or the supply, and the wei->token
           division stays at exactly one site (`_tokens`, Task WP4.7).
           `identities_written` is the deliberate exception and reads off the
           **log slot** instead: it is the one reading whose flat-key namesake
           is a *different number* — see the block comment below.
        3. **Event rows and the channel page come off last-good, not off this
           cycle's fetch results.** The logs group is medium tier, so on a
           fast-only refresh ``fetch_recent_logs`` was never called — and reading
           its ``None`` as an outage would blank BRIDGE STAGE and LP MIGRATION
           every 30 s. That is a lie about the source where the truth is only a
           refresh rate. The slot's as-of marker already carries the staleness
           (CLAUDE.md: serve last-good behind an ``as of`` marker), and re-serving
           rows cannot re-fire anything — WP2 keys events on ``(tx, ts)``. The
           caller passes ``channel`` for the same reason, already resolved to
           fresh-or-last-good by ``_cycle``.
        4. **A post body is only quoted under the nonce it was read at.** See the
           comment below; this one is load-bearing for the FIRED age.
        5. **Fix round 1 (controller finding 1):** ``decoy_pool_count``,
           ``decoy_newest_fee_bps``, ``burn_ready``, ``burn_accrued`` and
           ``launchpad_swaps_by_coin`` are fed here for the three detectors
           Task 7 (``analytics/surf_signals.py``, not this file) adds —
           DECOY POOL, BURN READY, HOT COIN. They are **not yet** in
           ``READING_KEYS``: that tuple is Task 7's own file to grow, and
           this method assigning extra keys beyond ``dict.fromkeys(READING_KEYS)``
           is harmless — ``build_signals`` reads whatever dict it is handed,
           key by key, with no membership check against ``READING_KEYS``
           anywhere. Left unfed, those three detectors would watch nothing
           forever the moment Task 7 registers them, a defect that would ship
           green (every existing test passes; nothing asserts these three
           signals ever leave ``None``) and be invisible without reading this
           method. The first three are read straight off ``data`` — the
           manager's own already-assembled flat payload — for the same reason
           rule 2 above gives: the hero, the launchpad panel and this detector
           input must not be able to disagree.
        """
        logs = dict(getattr(self.cache.get_last_good(SLOT_LOGS), "payload", None) or {})
        channel = channel or {}
        # The same list `_cycle` renders the feed from — unpacked here rather than
        # passed as a sixth argument, so the rows the panel shows and the rows the
        # detectors read can never be two different lists. `None`, not `[]`, when
        # `channel` itself is falsy: `_deploy_events` needs to tell "the channel
        # page has never answered" apart from "it answered and held nothing", and
        # collapsing that here would erase the distinction before it gets there.
        feed_items = list(channel.get("items") or ()) if channel else None
        read: dict[str, Any] = dict.fromkeys(READING_KEYS)

        # -- fast tier: three nonces, every refresh, the whole early edge -----
        read["announce_nonce"] = data.get("feed_nonce")
        read["dev_nonce"] = _opt_int(_field(nonces, "dev"))
        read["ops_nonce"] = _opt_int(_field(nonces, "ops"))

        # -- fast tier: the batched chain read, via the payload ---------------
        read["lp_liquidity"] = data.get("lp_liquidity")
        read["gate_open"] = data.get("gate_open")
        read["imd_supply"] = data.get("imd_supply")
        # -- final fix wave (C2): LP MOVE's actual subject -------------------
        # The one chain scalar read off the MODEL rather than off the payload,
        # and rule 2's reasoning is why: it is not in `SURF_KEYS` at all (fix
        # round 12a removed the flat key -- no widget renders it), so there is
        # no panel for a detector to disagree with. Skipping this wiring is
        # exactly what left `_detect_lp` pointed at `lp_liquidity`, i.e. at
        # `NFPM.positions()` on the v3 position the dev BURNED on 2026-08-17:
        # that call reverts, the reading is `None` forever, and the row could
        # never fire. `PositionManager.balanceOf(OPS_WALLET)` already rides in
        # the same `aggregate3` (`surf_client.py`), so this costs no request.
        read["lp_position_count"] = _opt_int(_field(state, "lp_position_count"))

        # -- the GATE detail's write count is the WINDOW count ----------------
        # Not `data["identities_written"]`, which is the hero's *lifetime*
        # number off `NftStats.written` (1 of 2000, written 2026-05-14 — months
        # outside any log window this app opens). WP2 documents this reading as
        # "distinct tokens in IdentityHashUpdated logs" and PRD §3 #3 makes the
        # log count the detector's detail source; wp1.md open issue 9 assigns
        # the window count here and the lifetime count to the hero, precisely
        # because they are different facts. Feed the lifetime number in and
        # `_detect_gate`'s `written > base_written` WATCH branch — "the gate
        # opened and closed between two polls" — can never be reached.
        read["identities_written"] = logs.get("identity_writes")

        # -- the channel page, as `_channel_payload` stored it -----------------
        # ``tx_count`` counts posts AND replies (21 today against nonce 14), which
        # is the only thing that moves when somebody *else* writes to the channel.
        read["channel_tx_count"] = _opt_int(channel.get("tx_count"))
        # The body we hold belongs to *this* nonce only if the page was read at
        # it. `_pool_channel` fetches on the same cycle the nonce moves, so the
        # pair is normally matched -- but the nonce comes from an RPC and the page
        # from Blockscout, and either can be the one that is down. Quoting an
        # older post under a newer nonce would misquote it and -- worse -- date
        # the FIRED row to the previous post; across the real 52-day May-to-July
        # silence that timestamp is past FIRED_TTL_S, so brand-new news would
        # render as relaxed history. ``None`` here loses nothing: `build_signals`
        # falls back to ``now``, which is when we actually saw it.
        if read["announce_nonce"] is not None and _opt_int(
            channel.get("nonce")
        ) == read["announce_nonce"]:
            # Raw third-party text: escaped at the widget, never here.
            read["announce_last_text"] = channel.get("last_text")
            read["announce_last_ts"] = _opt_float(channel.get("last_ts"))

        # NEW REPLY's stream. Deliberately *not* behind the nonce guard above:
        # that guard exists because ``last_text`` and the live nonce come from
        # two different sources and can disagree about which post is newest.
        # These rows carry their own ``ts``, ``tx_hash`` and body from the one
        # page, so there is no pair to mismatch -- an older page just yields an
        # older newest row, which the baseline already knows about.
        #
        # ``None`` when the channel has never answered, ``[]`` when it answered
        # and held no replies: only the second may seed a baseline, and the
        # difference is what stops a cold cache reporting the whole history as
        # breaking news.
        read["channel_threads"] = (
            None
            if feed_items is None
            else [
                item
                for item in feed_items
                if isinstance(item, dict)
                and item.get("kind") in ("reply", "answer")
                and item.get("ts") is not None
            ]
        )

        # -- the log window (medium tier, served from last-good) --------------
        read["bridge_mints"] = logs.get("bridge_mints")
        read["v4_hook_pools"] = logs.get("v4_hook_pools")

        # -- a log group whose FILTER died is unread, whatever the slot holds --
        # Last after every log-derived reading is assigned, so nothing can
        # re-fill one of these behind it. `_pool_logs` keeps a failed group's
        # last-good rows so the panels can still render them behind the slot's
        # as-of marker -- but last-good is not a reading. Handing it to a
        # detector either re-seeds a baseline off stale rows or, for an empty
        # group, makes the affirmative claim "read and held nothing", and that
        # claim is exactly what let BRIDGE STAGE render `ok · no mints in
        # window` through a dead bridge-mint filter -- the earliest of the six
        # detectors reporting all-clear out of a read that failed.
        for group, reading_key in LOG_GROUP_READING_KEYS.items():
            if (logs.get("log_group_failed") or {}).get(group):
                read[reading_key] = None

        # -- the dev tx pages (slow tier, or a nonce change) ------------------
        # ``[]`` once the group has answered even once, ``None`` before that:
        # "no deploys in the pages we have" and "we have no pages" are different
        # facts and only the first may seed a baseline.
        activity_read = self.cache.get_last_good(SLOT_ACTIVITY) is not None
        if activity_read:
            # PRD §3 #6's precursor half, "BurnExecutor tx seen": an outbound
            # call to the executor, which is what `_activity_rows` labels
            # ``burn``. The IMD amount is not on a tx page (the ETH value is the
            # OFT fee, and passing *that* as an IMD amount would be a lie), so
            # the row carries ``amount: None`` and WP2 renders "? IMD ->
            # BurnExecutor". BURN still FIREs on the verified supply drop; this
            # is the earlier WATCH.
            read["burn_transfers"] = [
                {"ts": row.get("ts"), "tx_hash": row.get("tx_hash"), "amount": None}
                for row in activity_rows or ()
                if row.get("kind") == "burn"
            ]

        # -- NEW DEPLOY reads two streams, and only one is the tx pages -------
        # Extracted to `_deploy_events` (Task 3) so a manager-level test can
        # drive it directly with a synthetic `answer` item — the false
        # positive it fixed (an `answer` entering this stream labelled with
        # its own first four calldata bytes) is otherwise invisible from
        # here, since the feed panel never renders `label`. See that method's
        # docstring for the two-stream, two-gate story.
        read["deploy_events"] = self._deploy_events(
            feed_items, activity_rows, activity_read
        )

        # -- fix round 1: the five Task 7 reading keys (see rule 5 above) -----
        slot = launchpad_slot if isinstance(launchpad_slot, dict) else {}
        read["decoy_pool_count"] = data.get("decoy_pool_count")
        read["decoy_newest_fee_bps"] = slot.get("decoy_newest_fee_bps")
        read["burn_ready"] = data.get("burn_ready")
        read["burn_accrued"] = data.get("burn_accrued")
        read["burn_bridgeable"] = data.get("burn_bridgeable")
        read["launchpad_swaps_by_coin"] = self._swaps_by_coin(
            slot.get("swaps_by_coin")
        )
        read["launchpad_coin_tickers"] = self._coin_tickers(slot.get("coin_tickers"))
        # -- final fix wave (C1): WHEN that distribution was read -------------
        # ``SLOT_LAUNCHPAD``'s own ``LastGood.ts``, passed in by ``_cycle``
        # from the entry it already unpacked. This is the only reading here
        # that is a fact about the *slot* rather than about the chain, and it
        # exists because ``launchpad_swaps_by_coin`` is a **windowed**
        # statistic served from a last-good slot that never expires: without
        # it HOT COIN cannot tell "40 swaps this hour" from "40 swaps in an
        # hour that ended yesterday", and reported the second as the first
        # through a total outage. ``None`` before the sweep has ever landed,
        # which the detector reads as "cannot be shown to be current" and
        # renders unknown -- the failing-safe direction.
        read["launchpad_swaps_ts"] = (
            float(launchpad_ts) if isinstance(launchpad_ts, (int, float)) else None
        )
        return read

    @staticmethod
    def _deploy_events(
        feed_items: list[dict[str, Any]] | None,
        activity_rows: list[dict[str, Any]] | None,
        activity_read: bool,
    ) -> list[dict[str, Any]] | None:
        """NEW DEPLOY's event stream: dev-wallet deploys plus channel actions.

        PRD §3 #4: "new tx with ``created_contract``, **or** announce-EOA
        outbound *contract call*". The second never appears in
        ``fetch_dev_activity`` — that fetches the two dev wallets' pages, and
        the announce EOA is neither of them — so it has to come off the
        channel page, where ``classify_channel_tx`` already labels it
        ``action``. The ERC-8004 registration at channel nonce 4 is the PRD's
        own worked example of the shape, and without the second stream below
        it would not fire.

        ``answer`` rows are excluded by the ``kind == "action"`` filter, and
        that exclusion is the point of Task 3, not incidental to it: before
        ``answer`` existed, the channel's own authenticated replies were
        classified ``action`` too and entered here labelled with the first
        four bytes of their own calldata — a reply beginning "Yes the goal
        is…" fired this detector under the label ``0x59657320``, the ASCII
        for "Yes ". The filter needed no change; ``answer`` rows simply
        stopped matching it the moment ``classify_channel_tx`` learned the
        kind.

        ``feed_items`` carries a distinction ``_readings`` used to spell with
        two separate checks (``channel and activity_read``): ``None`` means
        the channel page has never answered, a list — even ``[]`` — means it
        has. Only the second may extend or sort ``events``: extending it from
        ``None`` would be the same lie ``[]`` vs ``None`` always is in this
        file, "the deploy window was read and held nothing", and that claim
        seeds WP2's ``deploy_tx``/``deploy_ts`` baselines — a channel page
        answering while Blockscout's tx pages are down must not seed that
        baseline on the tx-page source's behalf. ``activity_read`` gates both
        streams: the first directly (only a successful read of the tx pages
        may report deploys as ``[]`` instead of ``None``), and the second
        again so a channel-only cycle cannot make that claim through the
        merge either.
        """
        events: list[dict[str, Any]] | None = None
        if activity_read:
            events = [
                {
                    "ts": row.get("ts"),
                    "tx_hash": row.get("tx_hash"),
                    "kind": "deploy",
                    "label": row.get("counterparty"),
                    "wallet_label": row.get("wallet_label"),
                }
                for row in activity_rows or ()
                if row.get("kind") == "deploy"
            ]
        if feed_items is not None and activity_read:
            events = [
                *(events or []),
                *(
                    {
                        "ts": item.get("ts"),
                        "tx_hash": item.get("tx_hash"),
                        "kind": "action",
                        # Blockscout's decoded method name when it has one, the
                        # 4-byte selector when it does not. WP2 prints it
                        # verbatim: "action register() · announce".
                        "label": item.get("label") or "",
                        "wallet_label": "announce",
                    }
                    for item in feed_items or ()
                    if item.get("kind") == "action"
                ),
            ]
            # Newest first, so `_newest` and the row order agree. Two streams on
            # two cadences share one `(deploy_tx, deploy_ts)` baseline pair, and
            # WP2 reports only the newest row — so a channel `action` can still
            # bury an older tx-page `deploy` here. That is a WP2 contract
            # question, not this method's; see Open issue 12.
            events.sort(
                key=lambda e: (e["ts"] is not None, e["ts"] or 0.0), reverse=True
            )
        return events

    @staticmethod
    def _swaps_by_coin(value: Any) -> dict[str, int] | None:
        """The full per-coin in-window swap distribution, validated off
        whatever the slot holds — HOT COIN's (Task 7) own input.

        **Fix round 2.** The fix-round-1 version of this method derived a
        ``{ticker: swaps_1h}`` map from ``launchpad_coins``, the
        ``LAUNCHPAD_RENDER_LIMIT``-capped row list this slot has always
        carried — and that was the bug: ``hot_coin_threshold`` takes the
        *median* of active coins, and the median of only the busiest 20 runs
        several times higher than the median of the full population (a
        threshold near 24 instead of near the floor of 5, measured against a
        real-shaped distribution). The cap is about how many rows the panel
        draws; it was never meant to also decide how many coins the
        statistic sees. This method now reads the **full** distribution
        ``SurfClient.fetch_launchpad`` returns as ``LaunchpadState
        .swaps_by_coin`` and ``_launchpad_payload`` caches unmodified under
        the same key — no derivation from the capped rows any more.

        ``None`` when the slot has never held one at all: a cache file
        persisted before this fix, or a client double that predates the
        field, both look like "unread" and both get the honest ``None``
        rather than a guess reconstructed from a differently-scoped number
        (CLAUDE.md: a failed read is ``None``, never a stand-in claim).
        Malformed entries (a non-``dict`` value, or a per-coin count that is
        not a plain ``int``) are dropped individually rather than discarding
        the whole map — the same per-point tolerance ``series_points
        .coerce_points`` uses for a persisted history.
        """
        if not isinstance(value, dict):
            return None
        out: dict[str, int] = {}
        for pool_id, swaps in value.items():
            if isinstance(swaps, int) and not isinstance(swaps, bool):
                out[str(pool_id)] = swaps
        return out

    @staticmethod
    def _coin_tickers(value: Any) -> dict[str, str] | None:
        """``{pool_id: ticker}`` off whatever the slot holds — the LABEL map.

        Final fix wave (I1). ``swaps_by_coin`` is keyed by ``pool_id``
        because ``LaunchpadFactory.launch(string,string)`` is permissionless
        and two coins can carry the same ticker; this map is what lets HOT
        COIN still *name* the coin it is talking about, and it decides
        nothing. The tickers stay raw — attacker-chosen strings are bounded
        and filtered at the point of display (``surf_signals._safe_ticker``),
        never sanitised here, so the one filter has one caller.

        ``None`` when the slot has never held one (a cache file persisted
        before this fix, or a client double predating the field): the honest
        "unread" rather than a guess. Malformed entries are dropped
        individually, the same per-point tolerance ``_swaps_by_coin`` uses.
        """
        if not isinstance(value, dict):
            return None
        return {
            str(pool_id): ticker
            for pool_id, ticker in value.items()
            if isinstance(ticker, str)
        }

    # -- the pool4 tier: discovery, hook/dripper/vault, flow logs ------------
    #
    # WP7 of docs/surf_pool4_implementation_plan.md, built on ``_spawn_launchpad``
    # / ``_launchpad_detached`` / ``_pool_launchpad`` / ``_launchpad_payload``
    # rather than beside them: same detached-sweep shape, same capture-then-spawn
    # ordering, same "nothing is stored on a blank read" last-good rule, same
    # wei-native slot with ``_cycle`` as the one place that divides.
    #
    # Three things are pool4's own and are the ones to read carefully:
    #
    # 1. **Discovery runs off the channel rows this cycle already produced.**
    #    No new announce-channel request exists on this path, and a persisted
    #    adopted address is re-verified against the chain on every read rather
    #    than trusted — a cache file is third-party input exactly as the
    #    announce post was.
    # 2. **The network is a property of the numbers, not a setting.** Until a
    #    mainnet hook is adopted the panels read the vendored Sepolia
    #    deployment and every title says ``SEPOLIA``. Adoption switches the
    #    word, the reserve series and the share-price baseline together, in
    #    one payload.
    # 3. **The marker moves only when the content does.** See
    #    :meth:`_pool4_content`.

    def _spawn_pool4(self, tiers: set[str], now: float, rows: Any) -> Any:
        """Start the pool4 sweep **detached**; never wait for it.

        Discovery plus three getter rounds plus a paged log window over a
        24 h span is far more than first paint may sit behind, so this is
        ``ensure_future`` and nothing awaits it — ``_pool_launchpad``'s rule,
        and the tripwire for it fails by *timing out* rather than by
        assertion.

        ``rows`` is the channel feed this cycle already built, handed in
        rather than re-fetched: the announce channel is one Blockscout page
        and it has already been read (or served from last-good) by the time
        this is offered. A second request for it would double the only
        rate-limited endpoint on the fast path in order to learn nothing new.

        One at a time: while a sweep is in flight ``TIER_POOL4`` stays due
        (only a *completed* :meth:`_pool_pool4` marks it fetched or failed),
        so every cycle offers again and this guard is what keeps a slow sweep
        from stacking behind a 30 s poll.
        """
        if TIER_POOL4 not in tiers:
            return None
        running = self._pool4_task
        if running is not None and not running.done():
            logger.debug("SURF pool4 sweep still in flight; not starting another")
            return running
        self._pool4_task = asyncio.ensure_future(
            self._pool4_detached(tiers, now, rows)
        )
        return self._pool4_task

    async def _pool4_detached(self, tiers: set[str], now: float, rows: Any) -> None:
        """``_pool_pool4`` with nobody to raise at.

        A detached task's exception surfaces as an "exception was never
        retrieved" line at garbage-collection time and never as a
        degradation, so it is caught here. ``CancelledError`` is re-raised:
        that one is :meth:`close` doing its job.
        """
        try:
            await self._pool_pool4(tiers, now, rows)
        except asyncio.CancelledError:
            raise
        except Exception as exc:            # noqa: BLE001 — nobody awaits this task
            self._error_count += 1
            logger.warning("SURF pool4 sweep failed: %s", exc)

    async def _cancel_pool4(self) -> None:
        """Stop an in-flight pool4 sweep and wait for it to actually be gone."""
        task = self._pool4_task
        self._pool4_task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
            logger.debug("SURF pool4 sweep stopped on close: %s", exc)

    async def _pool_pool4(self, tiers: set[str], now: float, rows: Any) -> Any:
        """One pool4 sweep: adjudicate, read three contracts, sweep the logs.

        The order is forced by the chain, not chosen: the vault address is two
        hops out (``hook.rewardsRecipient()`` -> RewardDripper ->
        ``dripper.vault()`` — amendment A3, there is no ``vault()`` on the
        hook), so the dripper round cannot start before the hook round has
        answered and the vault round cannot start before the dripper's has.
        The log sweep needs only the head block, so it runs alongside the
        dripper round rather than after it.

        Every read degrades on its own. A dead vault costs the four VAULT keys
        and nothing else; a dead log pool costs FLOW and the unsettled legs and
        leaves every getter-derived number standing. That granularity is the
        point of the sweep being one slot with per-field ``None``s rather than
        four slots.
        """
        if TIER_POOL4 not in tiers:
            return None
        prior_entry = self.cache.get_last_good(SLOT_POOL4)
        prior = getattr(prior_entry, "payload", None)
        prior = prior if isinstance(prior, dict) else {}

        discovery, discovery_source = await self._pool4_discovery(rows, prior)
        adopted = (
            _field(discovery, "state") == POOL4_ADOPTED
            and _field(discovery, "hook_addr")
        )
        if adopted:
            network = POOL4_NETWORK_MAINNET
            hook_addr = _field(discovery, "hook_addr")
            token_addr = IMD_TOKEN
        else:
            network = POOL4_NETWORK_SEPOLIA
            hook_addr = POOL4_SEPOLIA_HOOK
            token_addr = POOL4_SEPOLIA_TOKEN

        client = self.pool4_client
        hook = await self._guard(
            lambda: client.fetch_hook_state(
                hook_addr, network=network, token_addr=token_addr
            ),
            "pool4 fetch_hook_state",
        )

        # ---- the walk to the vault, whose LENGTH IS DISCOVERED --------------
        #
        # A3 forbade looking for ``vault()`` on the hook and that still stands:
        # the vault is reached by following the chain, never scraped. What
        # changed on 2026-09-02 is the number of links. Sepolia answers
        # ``vault()`` at the first hop; mainnet inserted a Distributor, so it
        # is hook -> Distributor -> Dripper -> vault. Both shapes are live
        # **simultaneously**, so a hardcoded three would break Sepolia exactly
        # as the hardcoded two broke mainnet -- vault and dripper reads failed
        # outright there until this landed. Nothing here counts hops:
        # ``resolve_vault_path`` asks each node what it is and follows the
        # answer, and this method reads the addresses out of its result.
        recipient = _field(hook, "rewards_recipient")
        head_block = _field(hook, "block_number")
        path, log_read = await asyncio.gather(
            self._guard(
                lambda: client.resolve_vault_path(recipient, network=network),
                "pool4 resolve_vault_path",
            ) if recipient else _none(),
            self._pool4_logs(hook_addr, head_block, network),
        )
        logs, from_block, to_block = log_read

        dripper_addr = (path or {}).get("dripper")
        vault_addr = (path or {}).get("vault")
        distributor_addr = self._pool4_distributor_addr(path)

        # Three independent contracts, three independent reads: a dead
        # Distributor costs the nine distributor keys and nothing else.
        dripper, vault, distributor = await asyncio.gather(
            self._guard(
                lambda: client.fetch_dripper_state(
                    dripper_addr, network=network, token_addr=token_addr
                ),
                "pool4 fetch_dripper_state",
            ) if dripper_addr else _none(),
            self._guard(
                lambda: client.fetch_vault_state(vault_addr, network=network),
                "pool4 fetch_vault_state",
            ) if vault_addr else _none(),
            self._guard(
                lambda: client.fetch_distributor_state(
                    distributor_addr, network=network
                ),
                "pool4 fetch_distributor_state",
            ) if distributor_addr else _none(),
        )

        # The running counter total, folded before the payload is built so the
        # control can be reconciled against it. Held in the cache rather than
        # in the slot: it must advance on a sweep whose payload did not change,
        # and it must stay out of that slot's content comparison entirely.
        accumulator = self._pool4_accumulate(network, logs, from_block, to_block)

        payload = self._pool4_payload(
            discovery=discovery,
            discovery_source=discovery_source,
            network=network,
            hook_addr=hook_addr,
            token_addr=token_addr,
            dripper_addr=dripper_addr,
            vault_addr=vault_addr,
            distributor_addr=distributor_addr,
            path=path,
            hook=hook,
            dripper=dripper,
            vault=vault,
            distributor=distributor,
            logs=logs,
            accumulator=accumulator,
        )

        # Nothing is stored on a blank read, so the slot keeps its previous
        # payload *and its previous timestamp*: the marker goes stale, which is
        # the true statement, rather than a fresh time printed over dashes.
        # ``_launchpad_payload``'s own rule, and the reason it exists.
        if self._pool4_read_is_blank(hook, dripper, vault, logs, distributor):
            self.cache.mark_failed(TIER_POOL4, now)
            return {"ok": False, "network": network, "payload": None}

        # The share-price baseline is seeded from a *successful* read only, and
        # re-seeded when the network changes.
        self._pool4_note_share_price(network, payload.get("share_price_wei"))

        # The reserve history: the log window's own timestamped reserve events
        # first (back-fill), then this sweep's reading at ``now``. Both are
        # measured reserves; neither is a sentinel, and a failed read folds
        # nothing at all rather than a zero.
        _safe_call(
            self.cache.fold_pool4_reserve_history,
            P.reserve_series(logs),
            network=network,
        )
        _safe_call(
            self.cache.sample_pool4_reserve,
            now,
            _tokens(payload.get("tokens_in_pool_wei")),
            network=network,
        )

        changed = self._pool4_content(payload) != self._pool4_content(prior)
        if changed:
            self.cache.store_last_good(SLOT_POOL4, payload, ts=now)
        else:
            # A successful sweep that read exactly what the last one read.
            # The tier is satisfied — this is not a failure and must not take
            # the failure backoff — but the ``as of`` marker stays where it
            # was, because it names when these values were *first* seen and
            # nothing about them is newer than that.
            logger.debug("SURF pool4 sweep found nothing new; marker left alone")
        self.cache.mark_fetched(TIER_POOL4, now)
        return {"ok": True, "network": network, "payload": payload, "changed": changed}

    async def _pool4_logs(
        self, hook_addr: str, head_block: Any, network: str
    ) -> tuple[Any, int | None, int | None]:
        """The hook's logs over the trailing :data:`POOL4_LOG_WINDOW_BLOCKS`.

        ``None`` — never ``[]`` — when the head block is unknown: a window
        nobody could locate is a failed read, and ``[]`` is the affirmative
        claim "swept, and genuinely quiet" that makes FLOW render an empty
        table instead of an unavailable one.

        Returns ``(logs, from_block, to_block)``. The bounds are not
        decoration: the counter accumulator's **continuity** invariant is
        checked against them, and a window whose bounds are unknown cannot be
        folded into a running total at all.

        ``to_block`` is the block the hook's own state round was pinned to,
        which is what makes the accumulator's **alignment** invariant hold by
        construction: the sums cover ``[genesis, to_block]`` and the counters
        were read at that same block. Falling back to ``fetch_block_number``
        breaks that on purpose -- the counters then came from a block this
        method cannot name, so the control reports ``window-limited`` rather
        than reconciling two different moments.
        """
        pinned = _opt_int(head_block)
        head = pinned
        if head is None:
            head = _opt_int(
                await self._guard(
                    lambda: self.pool4_client.fetch_block_number(network=network),
                    "pool4 fetch_block_number",
                )
            )
        if head is None:
            return None, None, None
        start = max(0, head - POOL4_LOG_WINDOW_BLOCKS + 1)
        logs = await self._guard(
            lambda: self.pool4_client.fetch_flow_logs(
                hook_addr, start, head, network=network
            ),
            "pool4 fetch_flow_logs",
        )
        # Only a window that ends where the state round was pinned may be
        # accumulated; an unpinned one is returned with no bounds so
        # ``accumulate_counters`` refuses it rather than silently mis-aligning.
        if pinned is None:
            return logs, None, None
        return logs, start, head

    async def _pool4_discovery(self, rows: Any, prior: dict[str, Any]) -> Any:
        """Adjudicate mainnet from the announce channel, and **only** from it.

        **This is the security boundary, and the one thing to understand about
        it is that the fingerprint is FORGEABLE and provenance is not.**

        The flag gate is arithmetic on an address, and an address with any
        chosen low fourteen bits is mineable: the adversarial pass found a
        CREATE2-shaped one ending ``0x2840`` in about 16,000 tries, which is
        seconds of work. Of the five getter gates behind it, four
        (``rewardShareBps``, ``BPS_DENOMINATOR``, ``burnSink``,
        ``poolManager``) only check that *something answered* — any contract
        passes them — and the fifth, ``token()``, returns whatever the
        candidate's own code chooses to return. A hostile contract that
        answers the real mainnet IMD to ``token()`` and four zero words to the
        rest is adopted, and the pass proved it.

        So the **self-post check is the only gate an attacker cannot satisfy**:
        it requires a transaction signed by the announce wallet's key. Every
        other gate narrows the field; this one is what makes the field
        trustworthy. It follows that a candidate may only ever come from
        ``candidate_addresses`` over this cycle's channel rows, and that is
        now the only place this method gets one.

        **The persisted slot nominates nothing.** It used to be tried first,
        which made a cache file the one path into an adoption that never
        passed provenance — anyone who could write ``~/.maxpane/surf_cache.json``
        got a full adoption, including over a genuine hook named in a real
        self-post, because the loop returned on the first adoption and nothing
        compared the two. The fix is not to re-verify it harder: re-verifying
        cannot help, because the fingerprint it would be re-verified against is
        exactly the forgeable half. Its only remaining job is
        :meth:`_pool4_lapsed_adoption`.

        A **corroborate-then-prefer** variant was considered and rejected:
        adopting the persisted address only when the channel *also* names it is
        equally safe, but it changes nothing about safety (a corroborated
        address is a channel address either way) while breaking a legitimate
        migration — if the dev announces a *new* hook, preferring the stored
        one pins the dashboard to the old contract for as long as the cache
        survives. Channel order already answers this: ``feed_items`` is
        newest-first, so the most recently announced hook is the first
        candidate, which is the plan's own "first flag-equal candidate to be
        adopted wins".

        Everything before the getter round is pure arithmetic on strings this
        cycle already has, so a self-post naming twenty decoys costs zero round
        trips rather than twenty. Nothing here re-derives the mask, re-orders
        the gates or second-guesses a rejection: WP3 owns the verdict.

        Two outcomes are deliberately *not* verdicts:

        * **"We could not look."** When every candidate's round failed this
          returns ``state=None`` — discovery has not run — rather than the
          ``rejected`` a null answer set would manufacture. Persisting a
          rejection out of an outage would make a transient RPC failure look
          like a settled fact about the protocol.
        * **A rejection does not end the search.** Each candidate is
          adjudicated on its own and the *first adopted* one wins; the first
          rejection is only published when nothing was adopted. Returning on
          the first non-adoption would let one decoy in a post hide the real
          hook named beside it.
        """
        # Only the flag-passing candidates are asked about; everything before
        # the network is arithmetic on strings this cycle already has, so a
        # self-post naming twenty decoys costs zero round trips. Which of them
        # gets adjudicated, and in what order, is ``ranked_discovery``'s call
        # from the rows -- not this list's.
        candidates = P.flagged_candidates(
            P.triaged_candidates(P.candidate_addresses(rows, ANNOUNCE))
        )
        # The transaction each candidate was named in. ``Pool4Client.verify_hook``
        # adjudicates one address and has no rows to look it up in, so it
        # returns ``source_tx_hash=None`` and this is where the pointer is put
        # back -- WP3's own ``discovery_verdict`` already does the same thing
        # from its ``source_tx_by_addr`` parameter, which is why that parameter
        # exists.
        source_tx = self._pool4_source_tx_by_addr(rows)
        lapsed = self._pool4_lapsed_adoption(prior, candidates)
        if lapsed is not None:
            logger.info(
                "SURF pool4: the adopted hook %s is no longer named by any "
                "self-post — falling back to the vendored testnet deployment",
                lapsed,
            )

        # ---- adjudication, ranked by WP3 ------------------------------------
        #
        # The ranking is **not** re-derived here. ``ranked_discovery`` needs to
        # know which candidates each source produced *before* anything is
        # adjudicated -- a verdict has already discarded that -- so it takes the
        # raw getter answers and this method's only job is to fetch them.
        #
        # Two calls rather than one, and the reason is a round trip rather than
        # a rule: passing ``docs_text`` up front would fetch the docs page on
        # every sweep, including the ones where the channel adopts and the page
        # is never consulted. Phase one is channel-only; phase two happens only
        # if phase one adopted nothing, and re-adjudicates the channel from the
        # same answers (pure, same result) before docs gets its turn.
        answers = await self._pool4_candidate_answers(candidates)
        verdict, source = P.ranked_discovery(
            rows, ANNOUNCE, IMD_TOKEN, answers, None, source_tx, docs_text=None
        )
        if _field(verdict, "state") == POOL4_ADOPTED:
            return self._pool4_with_source_tx(verdict, source_tx), source

        asked = list(candidates)
        docs_text = await self._guard(
            # Wrapped in a lambda like every other call here: ``self.client.name``
            # is evaluated at the call site, so a client without the method
            # raises OUTSIDE ``_guard``'s try and takes the whole sweep down.
            lambda: self.pool4_client.fetch_docs_page(), "pool4 fetch_docs_page"
        )
        if docs_text:
            # The operator's decision, and its cost stated once: the docs site
            # becomes a trusted input. Anyone who can change that page can name
            # a hook, and the fingerprint alone will not stop them -- a
            # ``0x2840``-shaped address mines in about 20,000 tries, four of the
            # five getters are pure liveness checks and ``token()`` is the
            # candidate's own choice. **The mitigation is disclosure, not
            # prevention**: an adoption from here carries ``docs`` as its
            # source, so weaker provenance identifies itself instead of hiding
            # behind the same word as a dev-signed post.
            docs_candidates = P.flagged_candidates(
                P.triaged_candidates(P.docs_candidate_addresses(docs_text))
            )
            asked += docs_candidates
            docs_answers = await self._pool4_candidate_answers(docs_candidates)
            answers = {**(answers or {}), **(docs_answers or {})}
            verdict, source = P.ranked_discovery(
                rows, ANNOUNCE, IMD_TOKEN, answers, None, source_tx,
                docs_text=docs_text,
            )
            if _field(verdict, "state") == POOL4_ADOPTED:
                return self._pool4_with_source_tx(verdict, source_tx), source

        # ---- "we could not look" is still not a verdict ---------------------
        #
        # The one property the local ranking existed to protect, kept. A
        # candidate that got no answers is adjudicated against an empty map and
        # comes back ``rejected`` -- "token unread — the candidate answered
        # nothing" -- which would turn a transient RPC failure into a settled
        # fact about the protocol and drop the next genuine adoption.
        #
        # The test is deliberately the strict one: a non-adoption is only
        # published as a verdict when **every** flag-passing candidate actually
        # answered. A rejection is a claim about the whole candidate set, and a
        # set that was partly unreadable cannot support it.
        unread = [a for a in asked if a not in (answers or {})]
        if unread:
            verdict = Pool4Discovery(
                network=None,
                state=None,
                detail=(
                    f"{len(unread)} candidate(s) unverified — the chain did "
                    "not answer"
                ),
            )

        # Nothing in this cycle's window was adopted. If a previous adoption is
        # no longer named there, this is where it is either re-established from
        # the chain or allowed to lapse -- after the window has had its say, so
        # a freshly announced hook always outranks a remembered one.
        if lapsed is not None:
            reestablished = await self._pool4_reestablish(prior, lapsed)
            if reestablished is not None:
                # A re-established adoption keeps the source it was adopted
                # under: the transaction that proves it is a self-post, and
                # calling it anything weaker would under-report provenance the
                # chain just confirmed.
                return reestablished, POOL4_SOURCE_SELF_POST

        if lapsed is None:
            return verdict, None
        # The lapsed case is a fact only this module can know, and WP3's "no
        # hook-shaped address" line would be true while hiding the thing the
        # reader most needs to be told.
        return Pool4Discovery(
            network=None,
            state=_field(verdict, "state"),
            detail=(
                f"the adopted hook {lapsed} is no longer named by any "
                "self-post — reading the vendored testnet deployment"
            ),
        ), None

    async def _pool4_candidate_answers(self, candidates: Any) -> dict | None:
        """The raw getter round per candidate — **evidence, never a verdict**.

        This is the whole of the manager's part in adjudication now. WP3 owns
        the ranking and the fingerprint; WP6 owns the round trip and the flag
        gate that runs before it; this fetches and hands over.

        Nothing in the returned map is an adoption. Four of the five getters
        are pure liveness checks any deployed contract passes and ``token()``
        is a value the candidate's own contract chooses, so an entry means only
        "this address answered". The authority behind an adoption is
        provenance, upstream of here.

        ``{}`` is "there was nothing worth asking"; ``None`` is "nothing could
        be read". Both are passed through unchanged -- the caller needs to tell
        them apart, because only one of them makes a rejection unsafe to
        publish.
        """
        return await self._guard(
            lambda: self.pool4_client.fetch_candidate_answers(
                list(candidates or ()), network=POOL4_NETWORK_MAINNET
            ),
            "pool4 fetch_candidate_answers",
        )

    @staticmethod
    def _pool4_with_source_tx(verdict: Any, source_tx: dict[str, str]) -> Any:
        """Attach the self-post an adoption rests on, when there is one.

        ``ranked_discovery`` fills ``source_tx_hash`` from the map it was given,
        so this only covers the case where it could not -- and a docs adoption
        deliberately has none: a page is not a transaction, and inventing a
        pointer for one would be the disclosure undone.
        """
        if _field(verdict, "source_tx_hash") is not None:
            return verdict
        addr = _field(verdict, "hook_addr")
        if not isinstance(addr, str):
            return verdict
        found = source_tx.get(addr.lower())
        if found is None:
            return verdict
        return dataclasses.replace(verdict, source_tx_hash=found)

    async def _pool4_reestablish(
        self, prior: dict[str, Any], lapsed: str
    ) -> Any:
        """Re-prove a lapsed adoption from the chain, or let it go (S15).

        The channel window keeps 25 rows against a channel running at ~2.55
        days a post, so about **64 days** after a hook is announced its
        self-post ages out and a genuine adoption lapses to Sepolia. Fetching
        the remembered transaction is what lets provenance outlive the window.

        **The trust boundary, and it is the whole of this method.** The cache
        may supply **a transaction hash and nothing else**. Every question that
        decides -- is this a self-post, does its calldata name this address --
        is recomputed by WP3's predicate from the *fetched transaction*. The
        stored address is passed as ``expected_addr``, which is the **claim
        under test**, never a credential: nothing but the fetched object can
        make that predicate return ``True``. A cache that supplied a hash *and*
        an address, where the address was believed because the hash resolved,
        would be A27's persisted-adoption bypass wearing a new hat.

        **Could-not-read and answered-no are different, and only one lapses.**

        * ``fetch_transaction`` -> ``None``: we could not look. A bad RPC
          minute must not drop a good adoption, so the adoption is **held** and
          the next cycle asks again. The client already collapses every
          unreadable outcome -- an unknown hash, a pruned node, a wrong chain,
          a hash-identity mismatch -- into that one ``None``, precisely so an
          outage cannot be read as an attack.
        * the predicate answers ``False``: that is a real finding about a real
          transaction, and the adoption **lapses**.

        Holding is not free and is deliberately bounded: it keeps serving
        mainnet numbers on an adoption whose provenance could not be re-proved
        *this cycle*. It is the correct trade against dropping a good adoption
        on a transient failure, and it self-corrects on the first cycle that
        gets an answer either way.

        ``None`` is returned when there is nothing to try -- no remembered
        hash, or one that is not a hash -- and the caller lapses.
        """
        source_tx = self._pool4_source_tx(prior.get("discovery_source_tx"))
        hook_addr = prior.get("hook_addr")
        if source_tx is None or not isinstance(hook_addr, str):
            return None

        tx = await self._guard(
            lambda: self.pool4_client.fetch_transaction(
                source_tx, network=POOL4_NETWORK_MAINNET
            ),
            "pool4 fetch_transaction",
        )
        if tx is None:
            logger.info(
                "SURF pool4: could not read the cited self-post %s — holding "
                "the adoption of %s rather than dropping it on a failed read",
                source_tx, lapsed,
            )
            return Pool4Discovery(
                network=POOL4_NETWORK_MAINNET,
                state=POOL4_ADOPTED,
                detail=(
                    "the cited self-post could not be read this cycle — the "
                    "adoption is held, not re-proved"
                ),
                hook_addr=hook_addr,
                token_addr=IMD_TOKEN,
                source_tx_hash=source_tx,
            )

        proved, why = _safe_call(
            P.reestablish_provenance,
            tx, ANNOUNCE, hook_addr, source_tx,
            default=(False, "the provenance check could not be run"),
        )
        if not proved:
            logger.warning(
                "SURF pool4: the cited self-post %s does not re-establish %s "
                "(%s) — lapsing to the vendored testnet deployment",
                source_tx, hook_addr, why,
            )
            return None
        return Pool4Discovery(
            network=POOL4_NETWORK_MAINNET,
            state=POOL4_ADOPTED,
            detail=why,
            hook_addr=hook_addr,
            token_addr=IMD_TOKEN,
            source_tx_hash=source_tx,
        )

    @staticmethod
    def _pool4_lapsed_adoption(prior: dict[str, Any], candidates: Any) -> str | None:
        """The stored mainnet hook the channel no longer names, or ``None``.

        The persisted slot's **only** remaining role. An adoption is not
        permanent: ``feed_items`` holds the newest
        :data:`FEED_ITEM_LIMIT` rows, so the self-post that named the hook can
        age out of the window, and when it does there is no longer any
        unforgeable evidence for the adoption. The honest outcome is to fall
        back to the vendored testnet deployment and say so on every panel
        title — not to keep serving mainnet numbers on the authority of a file.

        The network check is what keeps this from crying wolf: a slot whose
        network is ``SEPOLIA`` never adopted anything, and its ``hook_addr`` is
        the vendored testnet hook, so reporting *that* as a lapsed adoption
        would fabricate an alarm on every ordinary cycle.

        The address is echoed into a rendered detail line, so it is passed
        through ``checksum_address`` first and dropped for a generic phrase if
        it is not an address at all. The widget escapes third-party text
        anyway; not putting arbitrary cache-file bytes into a sentence in the
        first place is the cheaper half of that defence.
        """
        addr = prior.get("hook_addr")
        if prior.get("network") != POOL4_NETWORK_MAINNET:
            return None
        if not isinstance(addr, str):
            return None
        if addr.lower() in {str(c).lower() for c in (candidates or ())}:
            return None
        return P.checksum_address(addr) or "recorded in the cache"

    def _pool4_note_share_price(self, network: str, share_price_wei: Any) -> None:
        """Seed or re-seed the session's share-price baseline.

        Called only from a successful sweep. A network change resets it to the
        new reading and resets the count with it, so the first mainnet payload
        publishes ``None`` rather than a percentage measured against a Sepolia
        vault — a number that would look entirely ordinary and mean nothing.
        """
        price = _tokens(share_price_wei)
        if price is None or price <= 0:
            return
        baseline = self._pool4_baseline
        if baseline is None or baseline[0] != network:
            self._pool4_baseline = (network, price)
            self._pool4_price_reads = 1
            return
        self._pool4_price_reads += 1

    def _pool4_share_price_delta_pct(
        self, network: Any, price: float | None
    ) -> float | None:
        """The published delta, or ``None`` until a *second* reading exists.

        ``0.0`` is a real answer — "we looked twice and it did not move" — and
        must never stand in for "we have only looked once", which is what
        seeding the baseline from the reading it is compared against would
        produce on every cold start.
        """
        baseline = self._pool4_baseline
        if baseline is None or price is None or self._pool4_price_reads < 2:
            return None
        if baseline[0] != network:
            return None
        return P.share_price_delta_pct(price, baseline[1])

    @staticmethod
    def _pool4_read_is_blank(
        hook: Any, dripper: Any, vault: Any, logs: Any, distributor: Any = None
    ) -> bool:
        """True when a sweep produced no chain reading at all.

        ``logs`` counts as a reading when it is a list, ``[]`` included: a
        swept-and-quiet window is an answer about the world. Each state counts
        when at least one of its fields answered — the clients return a model
        with per-field ``None``s, so "not ``None``" alone would call a wholly
        reverting contract a successful read.

        The discovery verdict is deliberately *not* a reading here. It is real
        information, but a slot written on discovery alone would refresh the
        ``as of`` marker over a panel of dashes, which is the one outcome the
        marker exists to prevent. With nothing to serve, ``p4`` degrades and
        says so instead.
        """
        if isinstance(logs, list):
            return False
        for state in (hook, dripper, vault, distributor):
            if state is None:
                continue
            if isinstance(state, dict):
                # The Distributor has no WP0 model yet, so its client hands
                # back a plain dict of decoded getters. ``block_number`` rides
                # along on every round and is not a reading of the contract:
                # counting it would make a wholly-reverting Distributor look
                # like a successful read.
                if any(
                    value is not None
                    for key, value in state.items()
                    if key != "block_number"
                ):
                    return False
                continue
            fields = getattr(state, "__dataclass_fields__", None) or {}
            if any(getattr(state, name, None) is not None for name in fields):
                return False
        return True

    @staticmethod
    def _pool4_content(payload: Any) -> dict[str, Any]:
        """The part of a slot payload a change in ``as of`` would be about.

        The head block is excluded because it moves every twelve seconds and
        reaches no widget: comparing it would make every sweep "new", the
        marker would advance on every tick, and the guard would be one of this
        repo's tests-that-cannot-fail. Everything else *is* content — including
        the discovery detail, which is a sentence a reader acts on.
        """
        if not isinstance(payload, dict):
            return {}
        return {
            key: value
            for key, value in payload.items()
            if key not in POOL4_VOLATILE_SLOT_KEYS
        }

    @staticmethod
    def _pool4_distributor_addr(path: Any) -> str | None:
        """The Reward Distributor, read out of the walk. ``None`` on Sepolia.

        **Derived from the chain's own answer, never from a hop count.** The
        walk visits ``rewardsRecipient()`` first and stops at whichever node
        answered ``vault()`` -- and ``vault()`` lives on the RewardDripper and
        nowhere else. So the Distributor is exactly "the node the hook points
        at, when that node is not itself the Dripper": on Sepolia those are the
        same address and this is ``None``, on mainnet they differ and this is
        the Distributor.

        ``None`` when the walk found no dripper at all, which is the honest
        answer -- with no end of the path identified, nothing can be said about
        which node was the middle of it.
        """
        if not isinstance(path, dict):
            return None
        hops = path.get("path")
        dripper = path.get("dripper")
        if not isinstance(hops, list) or not hops or not isinstance(dripper, str):
            return None
        first = hops[0]
        if not isinstance(first, str) or first.lower() == dripper.lower():
            return None
        return first

    @staticmethod
    def _pool4_cap_decay(raw: Any) -> float | None:
        """Whole IMD per day, with the disabled case rendered as a real zero.

        Three answers and all three are distinct, which is the whole reason
        this is not a bare division:

        * ``None`` -- unread. The getter is absent or the round failed.
        * ``0.0`` -- **the ratchet is off.** Sepolia answers ``uint128`` max
          here, which the mainnet record reads as *no decay*. Dividing it by
          1e18 would put 340,282,366,920,938,463,463 IMD/day on the panel: a
          decay that would zero a 472M IMD cap instantly, i.e. the exact
          opposite of what the value means. A representable zero says "we
          looked and it does not decay", which is true and is a different
          claim from ``None``.
        * a number -- the live rate, read and never assumed.

        **The threshold is WP3's** (:func:`~surf_pool4.is_no_decay`), not a
        magnitude compared here. Where the boundary sits is a fact about the
        contract's vocabulary and belongs beside the selectors: notably
        ``uint64`` max is deliberately *not* caught, because it is 18.4
        IMD/day -- an entirely plausible rate that a greedier test would
        silently turn into "no decay", which is the opposite error and the
        harder one to notice.
        """
        value = _opt_int(raw)
        disabled = P.is_no_decay(value)
        if disabled is None:
            return None
        if disabled:
            return 0.0
        return _tokens(value)

    @staticmethod
    def _pool4_cap_headroom(
        *, inventory_cap_wei: Any, reserve_wei: Any
    ) -> float | None:
        """``inventoryCap - tokensInPool``, whole IMD. **NOTE THE OPERAND ORDER.**

        How much inventory can still arrive before the ceiling binds. On
        mainnet the cap decays at 1,000 IMD/day, so this is a countdown as much
        as a quantity: 94.68 IMD of headroom against that rate is a cap that
        binds in about two hours. A reader looking at ``inventoryCap`` and
        ``tokensInPool`` side by side on a compact formatter sees ``5.3K`` and
        ``5.2K`` and cannot tell that from a pool with a week of slack.

        **The sign trap, which is the whole reason this is a named function
        with keyword-only parameters.** Its sibling one section down is
        ``floor_distance = reserve - floor``. This one is ``cap - reserve``:
        the operands are in the *opposite* order, so that both read **positive
        when healthy** -- the floor is below the reserve, the ceiling is above
        it. Writing the ceiling by analogy with the floor, which is the natural
        thing to do when they sit next to each other, produces
        ``reserve - cap`` and renders a **binding cap as slack of the same
        magnitude**. That is precisely the reading this key exists to prevent.
        The parameters are keyword-only so a positional swap is a ``TypeError``
        rather than a sign error.

        **Wei in, divided once at the end**, and that is load-bearing rather
        than habit. The two operands are within one part in 10^8 of each other
        on a live pool; at Sepolia's 472M IMD scale one float64 step is about
        909,495 wei, so subtracting the two *published* floats annihilates any
        headroom below a millionth of an IMD and returns a confident ``0.0``.
        Subtracting in integer wei and dividing once keeps a 12-wei gap as
        ``1.2e-17`` -- A20's rule that anything checked on these values belongs
        in wei-space and not in floats.

        A negative is **real and must render**: it means inventory sits above
        the cap. Nothing here clamps, on ``floor_distance``'s A7 precedent,
        where a reserve below its own floor is likewise a legitimate state.
        ``None`` when either operand is unread -- a headroom computed against
        a number nobody read is not a weaker answer, it is a wrong one.
        """
        cap = _opt_int(inventory_cap_wei)
        reserve = _opt_int(reserve_wei)
        if cap is None or reserve is None:
            return None
        return (cap - reserve) / WEI

    @staticmethod
    def _pool4_reward_path(hook: Any, path: Any) -> str | None:
        """``direct`` / ``via-distributor`` / ``None`` — **the shape of the path**.

        This is what the reward share *means*, and it exists because an address
        cannot carry it. ``pool4_distributor_addr`` is ``None`` both when there
        is no Distributor and when the getter that would have named one failed,
        and those two are **three times apart on the headline percentage**: all
        of ``totalRewarded()`` reaches stakers under ``direct``, and 30% of it
        does under ``via-distributor``.

        The hook's getters are batched per-field, so "the counters answered and
        ``rewardsRecipient()`` did not" is a routine payload rather than a
        corner. Reading absence-of-address as absence-of-Distributor would
        label mainnet's 15% as the staker share in exactly that payload — which
        is the defect this module shipped until the word existed, because it
        branched on the address.

        ``None`` is *unknown*, and it is returned for every case where the
        chain did not actually settle the shape: the recipient unread, the walk
        unread, or a walk that ran and never reached a vault. A word is only
        published when an answer was read.
        """
        if _field(hook, "rewards_recipient") is None:
            return None
        if not isinstance(path, dict):
            return None
        hops = path.get("path")
        dripper = path.get("dripper")
        if not isinstance(hops, list) or not hops or not isinstance(dripper, str):
            # The walk ran but never identified the end of the path, so which
            # node was the middle of it is not established either.
            return None
        first = hops[0]
        if not isinstance(first, str):
            return None
        return (
            POOL4_PATH_DIRECT if first.lower() == dripper.lower()
            else POOL4_PATH_VIA_DISTRIBUTOR
        )

    @staticmethod
    def _pool4_bonding_bps(
        staking_bps: Any, nodes_bps: Any, bps_denominator: Any
    ) -> int | None:
        """``BPS_DENOMINATOR - stakingBps - nftBps``. **Derived, never read.**

        Bonding has no getter: it is the remainder, measured at 4000 today.
        The number is published; a ``bonding_derived`` flag is not, because a
        flag that can only ever be ``True`` is a constant dressed as data.

        It goes ``None`` whenever **either** input does -- ``split_drift_bps``'
        rule -- because a remainder computed from a number nobody read is not a
        weaker answer, it is a wrong one. And nothing here falls back to 4000:
        the split has already moved once (``rewardShareBps`` 1000 -> 1500 the
        day mainnet shipped), so a hardcoded remainder is a number that goes
        stale in silence.
        """
        parts = (_opt_int(staking_bps), _opt_int(nodes_bps), _opt_int(bps_denominator))
        if any(p is None for p in parts):
            return None
        staking, nodes, denominator = parts
        remainder = denominator - staking - nodes    # type: ignore[operator]
        return remainder if remainder >= 0 else None

    def _pool4_accumulate(
        self, network: str, logs: Any, from_block: Any, to_block: Any
    ) -> dict[str, Any] | None:
        """Fold this window into ``network``'s running counter total (S17).

        The identities are cumulative counters against a sum of **all** logs,
        while the sweep reads a trailing window -- so from about a day after
        deployment every check would be ``window-limited`` for ever and the
        control would detect nothing. Carrying the sums forward is the fix, on
        the ``LaunchpadState.cursor`` precedent: a total cannot be recovered
        from its newest addend.

        **Both invariants are WP3's and both are checkable.** This method
        supplies the inputs they are checked against and stores the result; it
        does not decide either:

        * **Continuity** -- seeded at the genesis marker, and every window
          thereafter satisfying ``from_block <= cursor + 1``. A gap
          **discards** the accumulator rather than patching it, because a total
          short by a missed sweep is indistinguishable from one short by a
          decoder bug, and a total that says ``reconciled`` when it means
          ``probably`` is worse than no total at all. Overlapping re-sweeps are
          idempotent; a failed sweep advances nothing and loses nothing.
        * **Alignment** -- ``cursor_block == at_block`` exactly, where
          ``at_block`` is the block the hook's counters were read at. This
          holds here **by construction** rather than by luck: ``_pool4_logs``
          sweeps to the same block the state round was pinned to. A cursor
          behind the counters makes the sums short and -- because continuity
          certifies the evidence complete -- that reads as a **mismatch**, a
          false alarm on every tick where a swap lands between the two reads.

        Kept per network for the reserve series' reason: a total accumulated on
        Sepolia reconciled against mainnet counters is not a weaker check, it
        is a wrong one.

        ``None`` is returned for an unrecognised network, and the control then
        falls back to single-window behaviour -- honest ``window-limited``,
        never a fabricated pass.
        """
        prior = self.cache.get_pool4_accumulator(network)
        if prior is None and pool4_reserve_series_name(network) is None:
            return None
        folded = _safe_call(
            P.accumulate_counters,
            prior if prior is not None else P.empty_accumulator(),
            logs,
            from_block,
            to_block,
            default=None,
        )
        if not isinstance(folded, dict):
            return prior
        _safe_call(self.cache.set_pool4_accumulator, network, folded)
        # An **unseeded** accumulator is not handed to the control: it is
        # stored (so a discarded one is genuinely cleared) but the control
        # falls back to single-window behaviour, which is what WP3's own
        # "the caller falls back until a sweep containing genesis reseeds it"
        # means. Passing one anyway is not merely pointless -- it is wrong
        # twice over. Its zeroed sums read as "we counted nothing" rather than
        # "we could not count", so a dead log read would report
        # ``window-limited`` instead of ``unchecked``; and its window reason
        # names the block the counters were read at, which moves every twelve
        # seconds, so ``counter_detail`` would change on every tick and the
        # ``as of`` marker would advance for ever.
        if folded.get("genesis_block") is None:
            return None
        return folded

    @staticmethod
    def _pool4_counter_check(
        logs: Any, hook: Any, accumulator: Any = None
    ) -> tuple[str, str | None]:
        """R1 control (c): does the hook agree with its own logs? ``(state, detail)``.

        **This build's central risk made visible.** The hook interface was
        recovered from bytecode selectors, the contract is unverified, and
        three event signatures are still unresolved -- so a wrong operand order
        in a decoder currently surfaces as a *confident wrong number* with no
        signal anywhere. This is the only thing on the pool4 path that would
        say so.

        ``None`` is not one of the outcomes this returns. It is reserved for
        "the control has never run", which is what an absent slot key leaves
        behind, and it is the one convention that must not be reused here: a
        control whose silence reads as *all clear* reports a clean bill of
        health for a check that did not happen. Every outcome of actually
        looking is a word.

        **The arithmetic and the precedence are WP3's, deliberately.** This
        method neither compares sums nor decides which outcome outranks which:
        ``reconcile_counters`` runs the identities and ``counter_verdict``
        folds them, so one module owns both the numbers and the judgement about
        them. In particular **window-limitedness is not inferred here**. The
        honest question is "do these sums cover the hook's whole life?", and
        that module answers it positively, from the constructor's
        ``OwnershipTransferred(0, owner)`` in the log set -- a birth
        certificate -- rather than from arithmetic on
        :data:`POOL4_LOG_WINDOW_BLOCKS` and a block number, which is what this
        method did in its first draft and which would have gone wrong the first
        time anyone changed the window. The consequence is worth stating
        plainly: while the window still reaches the hook's first block this can
        say ``reconciled``, and once the hook is older than the window it
        settles at ``window-limited`` permanently. That is the true state of
        the evidence, not a failure, and reaching ``reconciled`` in steady
        state needs the sums accumulated forward from deployment (the
        ``LaunchpadState.cursor`` precedent -- a total cannot be recovered from
        its newest addend). It is not built here and it is not faked.

        **What this module does own is *which* identities are published**, and
        that is an A9 decision rather than an arithmetic one.
        :data:`POOL4_COUNTER_IDENTITIES` is the filter, and the filtering is
        load-bearing in both directions: the ETH identity must not be folded in
        (the symmetric form a reader expects cries wolf on every owner
        withdrawal), and ``totalBurned() == balanceOf(0xdEaD)`` must not be
        either, because nothing on this path reads that balance -- and since
        ``unchecked`` outranks ``reconciled``, folding one permanently unread
        identity in would pin this control at ``unchecked`` forever, which is a
        control that can never say anything at all.

        An identity that has gone missing from the report is ``unchecked``, not
        quietly dropped: two identities folded where three were meant is a
        weaker control wearing the same word.
        """
        report = _safe_call(
            P.reconcile_counters, logs, hook, accumulator=accumulator, default=None
        )
        if not isinstance(report, dict):
            return POOL4_UNCHECKED, "the reconciliation could not be computed"

        published = {
            name: report[name]
            for name in POOL4_COUNTER_IDENTITIES
            if isinstance(report.get(name), dict)
        }
        if len(published) != len(POOL4_COUNTER_IDENTITIES):
            missing = len(POOL4_COUNTER_IDENTITIES) - len(published)
            return (
                POOL4_UNCHECKED,
                f"{missing} of {len(POOL4_COUNTER_IDENTITIES)} identities "
                "were not reported",
            )

        verdict = _safe_call(P.counter_verdict, published, default=(None, None))
        state, detail = (
            verdict if isinstance(verdict, tuple) and len(verdict) == 2
            else (None, None)
        )
        if state not in POOL4_COUNTER_STATES:
            return POOL4_UNCHECKED, "the reconciliation returned no verdict"
        return state, detail if isinstance(detail, str) else None

    @staticmethod
    def _pool4_source_tx_by_addr(rows: Any) -> dict[str, str]:
        """``{address: the self-post transaction that named it}``.

        The provenance pointer, and after A27 the **only** thing an adoption
        actually rests on: every other artifact in the chain of trust is
        forgeable, and what is not forgeable is that one transaction carried
        the announce wallet's signature.

        Built with :func:`~surf_pool4.candidate_addresses` one row at a time,
        so the provenance rule is applied by the function that owns it rather
        than approximated here -- a row that is not a self-post yields no
        entry, whatever it carries. First spelling wins, matching the order
        that function already promises.

        The hash it records is a **pointer to a credential, not a credential**.
        Nothing here, and nothing downstream, may treat a stored hash as
        evidence: re-establishing an adoption from one means re-reading that
        transaction from the chain and re-checking the signer, which this
        build does not do.
        """
        out: dict[str, str] = {}
        for row in rows or ():
            if not isinstance(row, dict):
                continue
            tx_hash = row.get("tx_hash")
            if not isinstance(tx_hash, str) or not _TX_HASH_RE.match(tx_hash):
                continue
            for addr in P.candidate_addresses([row], ANNOUNCE):
                out.setdefault(addr.lower(), tx_hash)
        return out

    @staticmethod
    def _pool4_source_tx(source_tx: Any) -> str | None:
        """The self-post hash a verdict rests on, re-validated. ``None`` if not one.

        **Its own key, not an appendix to the detail line**, and the slot has
        always said why three lines above where it is stored: the detail is
        WP3's sentence and this is a pointer to a credential, so a later reader
        must be able to tell them apart. Appending it merged exactly the two
        things that comment keeps separate, and made a rendered sentence the
        only place an auditor could find the hash -- on a rail panel that
        truncates.

        Separating them is also what makes the pair *expressive*. The row that
        matters is ``state == "adopted"`` with ``source_tx is None``: **an
        adoption nothing can audit.** Merged into prose that state is a missing
        suffix nobody can query; as two keys it is a condition a widget or a
        test can name.

        Re-checked on every publish rather than once on the way in. This value
        comes back out of ``~/.maxpane/`` and is third-party by exactly the
        argument that makes any cache file third-party -- a version that never
        validated it, or a hand edit, must not get a free pass on render.
        """
        if isinstance(source_tx, str) and _TX_HASH_RE.match(source_tx):
            return source_tx
        return None

    @staticmethod
    def _pool4_unsettled_legs(logs: Any) -> tuple[float | None, float | None]:
        """``(unsettled burn, unsettled stakers)`` — or ``(None, None)``.

        WP3 sums accruals minus settlements across the window; over a
        *complete* history that difference cannot be negative, because nothing
        settles what was never accrued. Over a **trailing window** it can be:
        an accrual just before the window opened, settled by a swap just
        inside it, leaves the settlement with no accrual to pair against.

        A negative therefore does not mean "less than nothing is outstanding",
        it means this window cannot answer the question — so it is ``None``, a
        dark row, rather than a negative IMD figure rendered as a fact. A real
        ``0.0`` (settled up to date) is untouched and still renders as a number.
        """
        burn, stakers = P.unsettled_legs(logs)
        if burn is None or stakers is None:
            return None, None
        if burn < 0 or stakers < 0:
            logger.debug(
                "SURF pool4 unsettled legs are negative (%s / %s) — the window "
                "opened mid-settlement, so they are published as unread",
                burn, stakers,
            )
            return None, None
        return burn, stakers

    @staticmethod
    def _pool4_flow_rows(logs: Any) -> list[dict[str, Any]] | None:
        """``SURF_ROW_KEYS["pool4_flow"]`` rows, newest first, capped.

        ``None`` in, ``None`` out: "the log pool is down" and "nothing traded"
        are opposite claims and the FLOW panel renders them differently.

        ``burned_imd`` / ``stakers_imd`` are plain floats and are ``0.0`` on a
        buy — a representable zero, never ``None``. ``age_s`` is filled in by
        ``_cycle`` from ``ts``: this method is clock-free, which is the only
        reason a committed capture replays forever.

        The cap is :data:`POOL4_FLOW_LIMIT`, **imported from the contract**
        rather than declared beside ``FEED_ITEM_LIMIT`` (amendment A4) —
        ``SurfPool4Flow`` codes against the same constant, so one number.
        """
        if logs is None:
            return None
        events = P.decode_flow_events(logs)
        rows: list[dict[str, Any]] = []
        for event in events[:POOL4_FLOW_LIMIT]:
            rows.append(
                {
                    "ts": _opt_float(_field(event, "ts")),
                    "age_s": None,          # filled by ``_cycle``; the model is clock-free
                    "side": _field(event, "side"),
                    "size_imd": _tokens(_field(event, "size_wei")),
                    "burned_imd": _tokens(_field(event, "burned_wei")) or 0.0,
                    "stakers_imd": _tokens(_field(event, "stakers_wei")) or 0.0,
                    "fee_imd": _tokens(_field(event, "fee_token_wei")),
                    "fee_eth": _tokens(_field(event, "fee_eth_wei")),
                    "settled": bool(_field(event, "settled")),
                    "tx_hash": _field(event, "tx_hash"),
                }
            )
        return rows

    @staticmethod
    def _pool4_hatch_rows(
        hook: Any, dripper: Any, vault: Any, dripper_addr: Any,
        distributor: Any = None, distributor_addr: Any = None,
    ) -> list[dict[str, Any]] | None:
        """``SURF_ROW_KEYS["pool4_hatches"]`` — one row per owner-held lever.

        ``None`` when nothing was read at all; otherwise the full list, with
        an ``"unknown"`` state on every lever whose contract did not answer.
        ``[]`` is never emitted: the BOND row always exists, because "the bond
        the site advertises is not a contract we can see" is itself the answer
        a reader came for.

        ``addr_known`` is a :data:`KNOWN_LABELS` hit and nothing else — no
        prefix match, no fallback. The burn sink ``0x…dEaD`` is deliberately
        *not* in that allowlist, so it renders as an address rather than as a
        name this repo never assigned it.
        """
        if hook is None and dripper is None and vault is None and distributor is None:
            return None

        def known(addr: Any) -> bool:
            return isinstance(addr, str) and addr.lower() in KNOWN_LABELS

        def ownership(owner: Any) -> str:
            if owner is None:
                return "unknown"
            return (
                "renounced"
                if str(owner).lower() == ZERO_ADDRESS.lower()
                else "live"
            )

        def flag(value: Any, on: str, off: str) -> str:
            if value is None:
                return "unknown"
            return on if value else off

        # Is a bonding reserve actually readable on this deployment? Read, not
        # assumed: the Distributor is mainnet-only today, so on Sepolia there
        # is no bonding leg at all and no reserve to describe.
        bonding_reserve = (
            distributor_addr is not None
            and _dget(distributor, "heldBonding") is not None
        )
        vault_owner = _field(vault, "owner")
        hook_owner = _field(hook, "owner")
        dripper_owner = _field(dripper, "owner")
        burn_sink = _field(hook, "burn_sink")
        vault_live = ownership(vault_owner) == "live"

        rows: list[dict[str, Any]] = [
            {
                "scope": "vault", "label": "owner",
                "state": ownership(vault_owner),
                "detail": None,
                "addr": vault_owner if vault_owner else None,
                "addr_known": known(vault_owner),
            },
            {
                "scope": "vault", "label": "paused",
                "state": flag(_field(vault, "paused"), "paused", "open"),
                "detail": "setPaused stops every entry point",
                "addr": None, "addr_known": False,
            },
            {
                "scope": "vault", "label": "rescue",
                "state": (
                    "unknown" if vault_owner is None
                    else ("open" if vault_live else "closed")
                ),
                "detail": "rescueERC20 can move the staked IMD while the owner is live",
                "addr": None, "addr_known": False,
            },
            {
                "scope": "dripper", "label": "owner",
                "state": ownership(dripper_owner),
                "detail": None,
                "addr": dripper_owner if dripper_owner else None,
                "addr_known": known(dripper_owner),
            },
            {
                "scope": "dripper", "label": "rewards",
                "state": "live" if dripper_addr else "unknown",
                "detail": None,
                "addr": dripper_addr if dripper_addr else None,
                "addr_known": known(dripper_addr),
            },
            {
                # The Distributor sits between the hook and the Dripper on
                # mainnet, and its owner holds ``setDripper`` and
                # ``emergencyWithdraw`` -- it can re-point the entire rewards
                # path, so it belongs on the trust surface beside the other
                # three. On Sepolia there is no Distributor and this row says
                # ``absent``, which is a fact about the deployment rather than
                # a failed read.
                "scope": "distributor", "label": "owner",
                "state": (
                    "absent" if not distributor_addr
                    else ownership(_dget(distributor, "owner"))
                ),
                "detail": "setDripper can re-point the whole rewards path",
                "addr": _dget(distributor, "owner") or None,
                "addr_known": known(_dget(distributor, "owner")),
            },
            {
                "scope": "distributor", "label": "rewards",
                "state": "live" if distributor_addr else "absent",
                "detail": None,
                "addr": distributor_addr if distributor_addr else None,
                "addr_known": known(distributor_addr),
            },
            {
                "scope": "hook", "label": "owner",
                "state": ownership(hook_owner),
                "detail": None,
                "addr": hook_owner if hook_owner else None,
                "addr_known": known(hook_owner),
            },
            {
                "scope": "hook", "label": "market",
                "state": flag(_field(hook, "market_open"), "open", "closed"),
                "detail": None, "addr": None, "addr_known": False,
            },
            {
                "scope": "hook", "label": "rebalance",
                "state": flag(_field(hook, "rebalance_enabled"), "open", "closed"),
                "detail": "the backstop re-centre is permissionless while open",
                "addr": None, "addr_known": False,
            },
            {
                "scope": "hook", "label": "burn sink",
                "state": "live" if burn_sink else "unknown",
                "detail": None,
                "addr": burn_sink if burn_sink else None,
                "addr_known": known(burn_sink),
            },
            {
                # **Three facts, and only the middle one used to reach the
                # screen.** The bonding SHARE is live (the remainder of the
                # reward split); the bonding RESERVE is live and readable
                # (``heldBonding`` on the Distributor); the bond MARKET is not
                # -- it opens at $4 per IMD.
                #
                # This row said ``no bond contract is named by the hook``,
                # which was true of the hook and was the right sentence when
                # no deployed contract carried a bond. After the launch it
                # reads as "bonding does not exist" while 6% of every retired
                # batch accrues to a reserve we already read.
                #
                # ``closed`` is the state word that says the market is shut
                # without saying the programme is absent, and the detail is
                # SEVENTEEN CELLS because that is what the hatch grid's last
                # column gives a row with no address. "reserve accruing ·
                # market opens at $4" truncates to "reserve accruing…" and the
                # market's closure -- the whole point -- never reaches the
                # screen. Shorten the value, not the pin.
                "scope": "bond", "label": "deployed",
                "state": "closed" if bonding_reserve else "absent",
                "detail": (
                    "reserve, opens $4" if bonding_reserve
                    # No Distributor on this deployment, so there is no bonding
                    # leg to have a reserve. Claiming one would be the same
                    # class of error one chain over.
                    else "no bonding leg"
                ),
                "addr": None, "addr_known": False,
            },
        ]
        return rows

    def _pool4_payload(
        self,
        *,
        discovery: Any,
        discovery_source: Any = None,
        network: str,
        hook_addr: Any,
        token_addr: Any,
        dripper_addr: Any,
        vault_addr: Any,
        hook: Any,
        dripper: Any,
        vault: Any,
        logs: Any,
        accumulator: Any = None,
        distributor_addr: Any = None,
        distributor: Any = None,
        path: Any = None,
    ) -> dict[str, Any]:
        """The whole combined slot — discovery, three contracts, the flow window.

        **Wei-native**, like ``_launchpad_payload``: ``_cycle`` divides exactly
        once when it reads this back, and no ``_wei`` field exists in the flat
        payload. The three exceptions are named and are not oversights:
        ``unsettled_burn`` / ``unsettled_stakers`` (WP3's function already
        returns whole IMD, and re-multiplying to store them would be inventing
        precision) and the two row lists, which are the presentation shapes the
        widgets take.

        ``backstop_centred`` is derived **here**, not published raw: amendment
        A19 keeps the tick bounds model-internal, because ``centred`` /
        ``drifted`` / ``unknown`` is the decision-relevant fact and raw bounds
        on a rail panel are noise. It is the reason ``POOL4_KEYS`` stays at 45.

        ``share_price_wei`` is ``convertToAssets(10 ** decimals)`` and
        ``total_shares_raw`` divides by ``10 ** decimals``, **never 1e18** —
        the sIMD vault reports 24 decimals (asset 18 + Solady's offset 6).
        ``decimals`` is stored beside them, read from the chain, so the
        divisor travels with the numbers it applies to and no constant can
        drift away from the vault it describes.
        """
        unsettled_burn, unsettled_stakers = self._pool4_unsettled_legs(logs)
        counter_state, counter_detail = self._pool4_counter_check(
            logs, hook, accumulator
        )
        return {
            # ---- discovery ------------------------------------------------
            "network": network,
            "discovery_state": _field(discovery, "state"),
            "discovery_detail": _field(discovery, "detail"),
            # The self-post an adoption rests on. Kept beside the verdict and
            # never merged into it: the detail is WP3's sentence, this is a
            # pointer to a credential, and a later reader must be able to tell
            # them apart. Persisting it makes re-establishment *possible*, not
            # safe -- doing it would mean re-reading this transaction from the
            # chain and re-checking the signer, which nothing here does.
            "discovery_source_tx": _field(discovery, "source_tx_hash"),
            # Which candidate source the adoption came from. Stored raw; the
            # ``unattributed`` resolution happens at publish time so a slot
            # written before this key existed still discloses correctly.
            "discovery_source": discovery_source,
            "hook_addr": hook_addr,
            "token_addr": token_addr,
            "vault_addr": vault_addr,
            "dripper_addr": dripper_addr,
            # ---- the hook (wei-native) ------------------------------------
            "reward_share_bps": _opt_int(_field(hook, "reward_share_bps")),
            "bps_denominator": _opt_int(_field(hook, "bps_denominator")),
            "total_burned_wei": _opt_int(_field(hook, "total_burned_wei")),
            "total_rewarded_wei": _opt_int(_field(hook, "total_rewarded_wei")),
            "total_fee_token_wei": _opt_int(_field(hook, "total_fee_token_wei")),
            "retained_eth_wei": _opt_int(_field(hook, "retained_eth_wei")),
            "last_claim_block": _opt_int(_field(hook, "last_claim_block")),
            "tokens_in_pool_wei": _opt_int(_field(hook, "tokens_in_pool_wei")),
            "cap_floor_wei": _opt_int(_field(hook, "cap_floor_wei")),
            # Present on BOTH chains -- the difference is the value, not the
            # presence (the mainnet doc's own correction). A test written as
            # "point it at Sepolia and watch these go None" would pass for the
            # wrong reason; the absence case needs a getter made to revert.
            "inventory_cap_wei": _opt_int(_field(hook, "inventory_cap_wei")),
            "cap_decay_per_day_wei": _opt_int(
                _field(hook, "cap_decay_tokens_per_day_wei")
            ),
            "eth_in_pool_wei": _opt_int(_field(hook, "eth_in_pool_wei")),
            "total_supply_wei": _opt_int(_field(hook, "total_supply_wei")),
            "position_liquidity": _opt_int(_field(hook, "position_liquidity")),
            "current_tick": _opt_int(_field(hook, "current_tick")),
            "ref_tick": _opt_int(_field(hook, "ref_tick")),
            "backstop_centred": P.backstop_centred(
                _field(hook, "backstop_tick_lower"),
                _field(hook, "ref_tick"),
                _field(hook, "tick_spacing"),
            ),
            # ---- the vault ------------------------------------------------
            # ---- the Reward Distributor (mainnet only, today) --------------
            #
            # ``nft`` on the chain is ``nodes`` in the payload, and this is the
            # single translation point. That is the module's stated naming
            # discipline rather than a slip -- *model fields mirror the chain,
            # flat-dict keys mirror the docs* -- the same split that makes
            # ``identityAllowed()`` the key ``gate_open``. The project's
            # documentation calls them nodes: the NFT-holding compute daemons.
            # Both sides are pinned, so neither is a typo to "fix".
            "distributor_addr": distributor_addr,
            # The *shape* of the reward path. Stored beside the address and
            # never derived from it downstream: absence-of-address is not
            # absence-of-Distributor, and mistaking the two overstates the
            # staker share by 3x.
            "reward_path": self._pool4_reward_path(hook, path),
            "distributor_staking_bps": _opt_int(_dget(distributor, "stakingBps")),
            "distributor_nodes_bps": _opt_int(_dget(distributor, "nftBps")),
            "distributor_staking_earned_wei": _opt_int(
                _dget(distributor, "stakingEarned")
            ),
            "distributor_nodes_earned_wei": _opt_int(_dget(distributor, "nftEarned")),
            "distributor_bonding_earned_wei": _opt_int(
                _dget(distributor, "bondingEarned")
            ),
            "distributor_held_nodes_wei": _opt_int(_dget(distributor, "heldNft")),
            "distributor_held_bonding_wei": _opt_int(
                _dget(distributor, "heldBonding")
            ),
            "distributor_owner": _dget(distributor, "owner"),
            "vault_decimals": _opt_int(_field(vault, "decimals")),
            "share_price_wei": _opt_int(_field(vault, "share_price_wei")),
            "total_assets_wei": _opt_int(_field(vault, "total_assets_wei")),
            "total_shares_raw": _opt_int(_field(vault, "total_shares_raw")),
            # ---- the dripper ----------------------------------------------
            "drip_rate_per_second_wei": _opt_int(
                _field(dripper, "drip_rate_per_second_wei")
            ),
            "drippable_wei": _opt_int(_field(dripper, "drippable_wei")),
            "can_drip": self._opt_bool(_field(dripper, "can_drip")),
            "backlog_wei": _opt_int(_field(dripper, "balance_wei")),
            # ---- R1 control (c): the hook against its own logs ------------
            "counter_state": counter_state,
            "counter_detail": counter_detail,
            # ---- the flow window ------------------------------------------
            "flow": self._pool4_flow_rows(logs),
            "unsettled_burn": unsettled_burn,
            "unsettled_stakers": unsettled_stakers,
            # ---- the levers -----------------------------------------------
            "hatches": self._pool4_hatch_rows(
                hook, dripper, vault, dripper_addr, distributor, distributor_addr
            ),
            # ---- bookkeeping (excluded from the content comparison) --------
            "block_number": _opt_int(_field(hook, "block_number")),
        }

    def _pool4_keys(
        self, slot: dict[str, Any], entry: Any, now: float
    ) -> dict[str, Any]:
        """The 45 ``POOL4_KEYS``, off one captured slot. The presentation boundary.

        Every division by 1e18 on the pool4 path happens here and nowhere else,
        and every derived number comes from WP3's pure functions rather than
        from arithmetic written a second time in this module.

        The two divisors that are **not** 1e18 are the dangerous ones and they
        are the reason this method reads the way it does:

        * ``pool4_vault_shares`` is ``total_shares_raw / 10 ** decimals`` via
          ``surf_pool4.vault_shares``. On the live 24-decimal vault the
          habitual ``/ 1e18`` gives 21,010,977,789 sIMD — a number that reads
          as an emissions farm, on a dashboard whose whole pitch is that there
          are no emissions.
        * ``pool4_share_price`` divides ``convertToAssets(10 ** decimals)`` by
          1e18 because its *result* is an IMD amount. Asking the vault for
          ``convertToAssets(1e18)`` instead — a millionth of a share — answers
          0.0000013 IMD/share, which reads as a dead vault.

        Neither wrong form looks like an error on screen, so nothing downstream
        would catch either. ``decimals`` is read from the chain and carried in
        the slot; there is no constant here to hardcode it with.
        """
        share_price = _tokens(slot.get("share_price_wei"))
        vault_assets = _tokens(slot.get("total_assets_wei"))
        drip_rate = _tokens(slot.get("drip_rate_per_second_wei"))
        drip_per_day = None if drip_rate is None else drip_rate * 86_400.0
        backlog_imd = _tokens(slot.get("backlog_wei"))
        network = slot.get("network")
        burned_wei = slot.get("total_burned_wei")
        rewarded_wei = slot.get("total_rewarded_wei")
        fee_wei = slot.get("total_fee_token_wei")
        reserve_wei = slot.get("tokens_in_pool_wei")
        floor_wei = slot.get("cap_floor_wei")
        # ``measured_split``'s third element is the WHOLE reward share, not the
        # staker leg: ``totalRewarded()`` is everything handed to
        # ``rewardsRecipient()``, and the hook's counters cannot see past it.
        # On mainnet that recipient is the Distributor, which splits it three
        # ways -- so publishing this number as the staker share overstates it
        # by more than three times (15% rendered where 4.5% is true), and it
        # would render as an entirely plausible figure.
        inference_pct, burn_pct, reward_pct = P.measured_split(
            fee_wei, burned_wei, rewarded_wei
        )
        staking_bps = slot.get("distributor_staking_bps")
        nodes_bps = slot.get("distributor_nodes_bps")
        bonding_bps = self._pool4_bonding_bps(
            staking_bps, nodes_bps, slot.get("bps_denominator")
        )
        # **Branch on the path WORD, never on the address.**
        # ``distributor_addr`` is ``None`` both when there is no Distributor and
        # when the getter that would have named one failed, and those two are
        # three times apart on this number. This module branched on the address
        # until ``pool4_reward_path`` existed, which meant a routine payload --
        # counters answered, ``rewardsRecipient()`` did not -- published
        # mainnet's whole 15% reward share as the staker share.
        reward_path = slot.get("reward_path")
        if reward_path == POOL4_PATH_VIA_DISTRIBUTOR:
            # The reward leg is subdivided; only its staking part belongs under
            # a "stakers" label.
            stakers_pct, _bonding_pct, _nodes_pct = P.reward_leg_split(
                reward_pct, staking_bps, nodes_bps, slot.get("bps_denominator")
            )
        elif reward_path == POOL4_PATH_DIRECT:
            # ``rewardsRecipient()`` is the Dripper itself, so the whole reward
            # leg reaches the vault and the two ARE the same number. Publishing
            # ``None`` here would blank a figure that is correct on every
            # Sepolia read.
            stakers_pct = reward_pct
        else:
            # Unknown path. Neither answer can be stood behind, and guessing
            # the wrong one is a 3x error on the headline percentage.
            stakers_pct = None
        liquidity = slot.get("position_liquidity")

        return {
            "pool4_network": network if network in POOL4_NETWORKS else None,
            "pool4_as_of_hhmm": (
                entry.as_of_hhmm() if entry is not None else None
            ),
            "pool4_discovery_state": (
                slot.get("discovery_state")
                if slot.get("discovery_state") in POOL4_DISCOVERY_STATES
                else None
            ),
            "pool4_discovery_detail": slot.get("discovery_detail"),
            "pool4_discovery_source_tx": self._pool4_source_tx(
                slot.get("discovery_source_tx")
            ),
            # ``None`` keeps its house meaning -- no adoption to attribute --
            # on every non-adopted state. On an ADOPTED one it is not an answer
            # at all: a renderer treating ``None`` as "nothing to say" would
            # draw a docs-sourced adoption identically to a dev-signed one,
            # undoing by omission the disclosure the operator's decision was
            # conditioned on. WP3 owns that rule; this calls it rather than
            # restating it, including for a slot persisted before the key
            # existed, which resolves to ``unattributed`` and is visible.
            "pool4_discovery_source": P.discovery_source_word(
                slot.get("discovery_source"), slot.get("discovery_state")
            ),
            "pool4_hook_addr": slot.get("hook_addr"),
            "pool4_token_addr": slot.get("token_addr"),
            "pool4_vault_addr": slot.get("vault_addr"),
            "pool4_dripper_addr": slot.get("dripper_addr"),
            # ---- THE SPLIT ------------------------------------------------
            "pool4_measured_inference_pct": inference_pct,
            "pool4_measured_burn_pct": burn_pct,
            "pool4_measured_stakers_pct": stakers_pct,
            # ---- the Reward Distributor ------------------------------------
            "pool4_reward_path": (
                reward_path if reward_path in POOL4_REWARD_PATHS else None
            ),
            "pool4_distributor_addr": slot.get("distributor_addr"),
            "pool4_distributor_staking_bps": _opt_int(staking_bps),
            "pool4_distributor_nodes_bps": _opt_int(nodes_bps),
            "pool4_distributor_bonding_bps": bonding_bps,
            "pool4_distributor_staking_earned": _tokens(
                slot.get("distributor_staking_earned_wei")
            ),
            "pool4_distributor_nodes_earned": _tokens(
                slot.get("distributor_nodes_earned_wei")
            ),
            "pool4_distributor_bonding_earned": _tokens(
                slot.get("distributor_bonding_earned_wei")
            ),
            "pool4_distributor_held_nodes": _tokens(
                slot.get("distributor_held_nodes_wei")
            ),
            "pool4_distributor_held_bonding": _tokens(
                slot.get("distributor_held_bonding_wei")
            ),
            "pool4_reward_share_bps": _opt_int(slot.get("reward_share_bps")),
            "pool4_bps_denominator": _opt_int(slot.get("bps_denominator")),
            "pool4_split_drift_bps": P.split_drift_bps(
                burned_wei, rewarded_wei,
                slot.get("reward_share_bps"), slot.get("bps_denominator"),
            ),
            "pool4_total_burned": _tokens(burned_wei),
            "pool4_total_rewarded": _tokens(rewarded_wei),
            "pool4_total_fee_token": _tokens(fee_wei),
            "pool4_retained_eth": _tokens(slot.get("retained_eth_wei")),
            "pool4_last_claim_block": _opt_int(slot.get("last_claim_block")),
            "pool4_unsettled_burn": _opt_float(slot.get("unsettled_burn")),
            "pool4_unsettled_stakers": _opt_float(slot.get("unsettled_stakers")),
            # R1 control (c). ``None`` only when the slot has never held a
            # sweep -- never as a way of saying the identities held.
            "pool4_counter_state": (
                slot.get("counter_state")
                if slot.get("counter_state") in POOL4_COUNTER_STATES
                else None
            ),
            "pool4_counter_detail": slot.get("counter_detail"),
            # ---- THE RATCHET ----------------------------------------------
            "pool4_tokens_in_pool": _tokens(reserve_wei),
            "pool4_cap_floor": _tokens(floor_wei),
            "pool4_inventory_cap": _tokens(slot.get("inventory_cap_wei")),
            # cap - reserve. NOT reserve - cap: see the operand-order note on
            # the helper. Passed by keyword so a swap cannot be silent.
            "pool4_cap_headroom": self._pool4_cap_headroom(
                inventory_cap_wei=slot.get("inventory_cap_wei"),
                reserve_wei=reserve_wei,
            ),
            "pool4_cap_decay_per_day": self._pool4_cap_decay(
                slot.get("cap_decay_per_day_wei")
            ),
            "pool4_floor_distance": P.floor_distance(reserve_wei, floor_wei),
            "pool4_floor_distance_pct": P.floor_distance_pct(reserve_wei, floor_wei),
            "pool4_burned_supply_pct": P.burned_supply_pct(
                burned_wei, slot.get("total_supply_wei")
            ),
            "pool4_total_supply": _tokens(slot.get("total_supply_wei")),
            "pool4_reserve_series": self.cache.get_pool4_reserve_series(network),
            "pool4_eth_in_pool": _tokens(slot.get("eth_in_pool_wei")),
            # Raw ``uint128`` L: not an amount of any token, so it is never
            # divided — but the contract types it ``float``, and a widget that
            # formats it as one must not be handed an int on one refresh and a
            # float on the next.
            "pool4_position_liquidity": (
                None if liquidity is None else float(liquidity)
            ),
            "pool4_current_tick": _opt_int(slot.get("current_tick")),
            "pool4_ref_tick": _opt_int(slot.get("ref_tick")),
            "pool4_backstop_centred": self._opt_bool(slot.get("backstop_centred")),
            # ---- sIMD VAULT -----------------------------------------------
            "pool4_share_price": share_price,
            "pool4_share_price_delta_pct": self._pool4_share_price_delta_pct(
                network, share_price
            ),
            "pool4_vault_assets": vault_assets,
            "pool4_vault_shares": P.vault_shares(
                slot.get("total_shares_raw"), slot.get("vault_decimals")
            ),
            "pool4_drip_per_day": drip_per_day,
            "pool4_drippable": _tokens(slot.get("drippable_wei")),
            "pool4_can_drip": self._opt_bool(slot.get("can_drip")),
            "pool4_backlog_imd": backlog_imd,
            "pool4_backlog_days": P.backlog_days(backlog_imd, drip_per_day),
            "pool4_implied_apr_pct": P.implied_apr_pct(drip_per_day, vault_assets),
            # ---- the two row keys -----------------------------------------
            "pool4_flow": self._pool4_aged_flow(slot.get("flow"), now),
            "pool4_hatches": slot.get("hatches"),
        }

    @staticmethod
    def _pool4_aged_flow(rows: Any, now: float) -> list[dict[str, Any]] | None:
        """Fill each row's ``age_s`` from its ``ts`` at publish time.

        ``None`` in, ``None`` out. The age is computed here rather than stored
        because a cached row's age is a function of *now*, not of the sweep:
        a slot served from last-good through an outage would otherwise report
        the age it had when it landed and read as live for as long as the
        outage lasted. The widget and the screen stay clock-free.
        """
        if rows is None:
            return None
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ts = _opt_float(row.get("ts"))
            out.append(
                dict(
                    row,
                    age_s=None if ts is None else max(0.0, float(now) - ts),
                )
            )
        return out

    def _signal_keys(self, readings: dict[str, Any], now: float) -> dict[str, Any]:
        """Run ``build_signals`` and expand its result into the 18 ``sig_*`` keys."""
        baselines = self.cache.get_baselines()
        result = _safe_call(
            build_signals, baselines, readings, now, default=None
        )
        if not isinstance(result, tuple) or len(result) != 2:
            logger.warning("build_signals returned %r — leaving the baselines alone", result)
            return {}
        signals, advanced = result
        if isinstance(advanced, dict):
            self.cache.set_baselines(advanced, now=now)
        out: dict[str, Any] = {}
        for name in SIGNAL_NAMES:
            out[f"sig_{name}_state"] = (signals or {}).get(f"sig_{name}_state")
            out[f"sig_{name}_detail"] = (signals or {}).get(f"sig_{name}_detail")
            out[f"sig_{name}_age_s"] = _opt_float(
                (signals or {}).get(f"sig_{name}_age_s")
            )
        return out

    # -- public API ----------------------------------------------------------

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Run one refresh cycle and return the flat dashboard dict.

        **No exception escapes**: a total failure still returns the full key set
        with every value ``None`` and ``degraded`` naming what died, because a
        widget can render an explicit unavailable state but cannot render a
        traceback.
        """
        try:
            return await self._cycle()
        except Exception as exc:            # noqa: BLE001 — the outermost guard
            self._error_count += 1
            logger.exception("SURF refresh cycle failed outright: %s", exc)
            payload = self._blank_payload()
            payload["degraded"] = list(SOURCES)
            return payload

    # -- the cycle -----------------------------------------------------------

    async def _cycle(self) -> dict[str, Any]:
        now = float(self._clock())
        self._cycle_count += 1
        tiers = set(self.cache.tiers_due(now))

        chain = await self._pool_chain(now)
        state = chain.get("state")
        nonces = chain.get("nonces")
        announce_nonce = _opt_int(_field(nonces, "announce"))

        # Divided exactly once, here, and reused everywhere below — the models
        # are wei-native and this dict is the presentation boundary (WP0.4).
        imd_supply = _tokens(_field(state, "imd_supply_wei"))

        # Folded in before anything else reads it: a burn is a *pair* of
        # successful supply reads, and ``record_supply`` refuses to conclude
        # anything from a ``None``.
        self.cache.record_supply(imd_supply, _opt_int(_field(state, "block_number")))

        dev_nonce = _opt_int(_field(nonces, "dev"))
        ops_nonce = _opt_int(_field(nonces, "ops"))

        # Captured now, as a plain local snapshot, *before* offering this
        # cycle's own sweep: whatever ``_spawn_launchpad`` schedules below can
        # only ever update ``self.cache.last_good`` itself, never mutate this
        # already-extracted value, so this payload reads whatever the slot
        # held going into this cycle — never a sweep this same cycle just
        # spawned, no matter how the event loop interleaves it with the
        # ``gather`` a few lines down. See ``_spawn_launchpad``'s docstring.
        launchpad_entry = self.cache.get_last_good(SLOT_LAUNCHPAD)
        # Built here, ahead of the gather, rather than beside `market_payload`
        # below (fix round 10a): `_pool_market` now needs `real_pool_id` to
        # tell the live v4 pair from a decoy, so the slot has to be unpacked
        # before it is handed in, not after. `{}` on a cold cache or a sweep
        # that has never produced a payload: every `.get()` below then
        # answers `None`, the honest "not yet run" state rather than a guess.
        launchpad_slot: dict[str, Any] = (
            dict(launchpad_entry.payload)
            if launchpad_entry is not None and isinstance(launchpad_entry.payload, dict)
            else {}
        )
        real_pool_id = launchpad_slot.get("pool_id")
        self._spawn_launchpad(tiers, now)

        # The pool4 slot is captured here for ``launchpad_entry``'s reason and
        # it is the same race: whatever ``_spawn_pool4`` schedules below can
        # only update ``self.cache.last_good``, never this already-extracted
        # value, so this payload publishes what the slot held going *into* this
        # cycle no matter how the loop interleaves the sweep with the gather.
        # The spawn itself has to wait until the channel rows exist — discovery
        # reads them and must not cost a second request for the announce page —
        # so the capture and the spawn are deliberately far apart.
        pool4_entry = self.cache.get_last_good(SLOT_POOL4)
        pool4_slot: dict[str, Any] = (
            dict(pool4_entry.payload)
            if pool4_entry is not None and isinstance(pool4_entry.payload, dict)
            else {}
        )

        market, logs, channel, nft, activity = await asyncio.gather(
            self._pool_market(tiers, now, real_pool_id),
            self._pool_logs(tiers, now),
            self._pool_channel(tiers, now, announce_nonce),
            self._pool_nft(tiers, now),
            self._pool_activity(tiers, now, dev_nonce, ops_nonce),
        )
        # A tier's clock is moved by the tier's *own* work, never by a
        # nonce-forced fetch: a channel or tx-page pull triggered off the fast
        # tier must not push the market and the log window another 90/420 s out.
        # A due tier that produced nothing takes the failure backoff instead of
        # being retried on every refresh.
        if TIER_MEDIUM in tiers:
            if market is not None or logs is not None:
                self.cache.mark_fetched(TIER_MEDIUM, now)
            else:
                self.cache.mark_failed(TIER_MEDIUM, now)
        if TIER_SLOW in tiers:
            if nft is not None:
                self.cache.mark_fetched(TIER_SLOW, now)
            else:
                self.cache.mark_failed(TIER_SLOW, now)

        # The sales live in the *logs* slot, decoded once by `_pool_logs`. They
        # are read back from there on every cycle — including a fast-only one,
        # where `logs` is `None` because the medium tier was skipped — so a
        # skipped or cached NFT tier can neither blank them nor serve a copy
        # that is staler than the window they came from.
        logs_payload = dict(
            getattr(self.cache.get_last_good(SLOT_LOGS), "payload", None) or {}
        )
        sales = logs_payload.get("nft_last_sales")

        nft_payload = (
            self._nft_payload(nft, sales) if nft is not None
            else dict(getattr(self.cache.get_last_good(SLOT_NFT), "payload", None) or {})
        )
        nft_payload["nft_last_sales"] = sales

        # `None` and `[]` are opposite claims about the tx pages, and the widget
        # renders them differently ("activity unavailable" vs "no recent
        # activity"). `[]` is only allowed once the group has actually answered:
        # a cold cache plus a dead Blockscout is `None`.
        #
        # Read back from ``SLOT_ACTIVITY`` rather than re-running
        # ``_activity_rows(activity)`` here: unlike ``_nft_payload``/
        # ``_channel_payload`` (pure re-shapers, safe to call twice),
        # ``_activity_rows`` *logs* on every dropped poisoning row, and
        # ``_pool_activity`` already called it once and stored the result
        # before this line runs (the ``gather`` above only returns once every
        # coroutine, including ``_pool_activity``, has finished). Calling it
        # again here would double every "is not the wallet" warning for a
        # spoof row still in the client's page — the same row logged twice
        # for one cycle is not "loud", it is misleading.
        activity_cached = getattr(
            self.cache.get_last_good(SLOT_ACTIVITY), "payload", None
        )
        activity_rows = (
            list((activity_cached or {}).get("rows") or [])
            if activity_cached is not None
            else None
        )

        # This cycle's channel slot: fresh when we fetched, last-good otherwise.
        # Both shapes are the same dict, so the POST detector reads one thing.
        channel_payload = (
            self._channel_payload(channel, announce_nonce)
            if channel is not None
            else dict(
                getattr(self.cache.get_last_good(SLOT_CHANNEL), "payload", None) or {}
            )
        )
        # `None` when the channel has never been read (cold cache + dead
        # Blockscout), `[]` when it was read and held nothing. WP3's feed
        # widget branches on exactly that: `[]` renders "no posts in window"
        # with the unavailable banner absent, so publishing `[]` for an outage
        # would have the screen state that the dev has not posted.
        raw_items = channel_payload.get("items")
        feed_items = list(raw_items) if raw_items is not None else None

        # Offered here, at the first point the channel rows exist, and never
        # awaited: pool4 discovery reads the announce channel this cycle has
        # already paid for. Spawning it earlier would mean either a second
        # request for that page or a sweep that adjudicates against nothing.
        self._spawn_pool4(tiers, now, feed_items)

        # This cycle's market view: fresh when we fetched, last-good otherwise —
        # the same resolution `channel_payload` gets above and `nft_payload` /
        # `activity_rows` get in Task WP4.10. Reading the seven keys off `market`
        # instead (as this block used to) publishes `None` for all of them on
        # every *skipped* medium tier, which with a 30 s poll and a 90 s TTL is
        # two refreshes in three: the whole market panel goes to `--`/`$ --` and
        # the title bar to `SURF · IMD — · parity —`, while `degraded` says the
        # group is healthy — correctly, because a skip never reaches `_note`. A
        # dark panel with nothing flagging it is the one outcome CLAUDE.md's
        # degradation rule forbids. `fresh_market` stays separate because the
        # sparklines may not be fed the fallback; see the sampling call below.
        fresh_market = self._market_payload(market) if market is not None else None
        market_payload = (
            fresh_market
            if fresh_market is not None
            else dict(
                getattr(self.cache.get_last_good(SLOT_MARKET), "payload", None) or {}
            )
        )
        dex_imd_price = market_payload.get("imd_price_usd")
        fp_price = market_payload.get("fp_price_usd")

        # Fix round 10a: the authoritative price is the on-chain extsload
        # read, not DexScreener's -- a third-party aggregator's number is a
        # cross-check now, never the number of record. `sqrt_price_x96`
        # comes off the same `launchpad_slot` snapshot `real_pool_id` above
        # already unpacked, so this costs no extra request either.
        chain_price_usd = None
        sqrt_price_x96 = launchpad_slot.get("sqrt_price_x96")
        eth_usd = market_payload.get("eth_usd")
        if sqrt_price_x96 is not None and eth_usd is not None:
            eth_per_imd = price_eth_per_imd(sqrt_price_x96)
            if eth_per_imd is not None:
                chain_price_usd = eth_per_imd * eth_usd
        # Falls back to the (now correctly v4-matched) DexScreener price only
        # while the chain read is unavailable -- a cold cache before the
        # launchpad sweep's first landing, typically one or two poll cycles,
        # never the full 600 s TTL. Blanking the market panel's headline
        # price on every fresh launch for a source that is merely "not yet
        # due" is a worse outcome than a graceful, honestly-labelled
        # cross-check taking over for a cycle or two.
        imd_price = chain_price_usd if chain_price_usd is not None else dex_imd_price
        # "A missing source is not agreement" -- `None` unless BOTH read.
        # Signed, not absolute: a disagreement is information about
        # direction as well as magnitude, and this repo does not average,
        # clamp or hide it.
        price_source_disagreement_pct = None
        if (
            dex_imd_price is not None
            and chain_price_usd is not None
            and chain_price_usd != 0
        ):
            price_source_disagreement_pct = (
                (dex_imd_price - chain_price_usd) / chain_price_usd * 100.0
            )

        burn_accrued = _tokens(launchpad_slot.get("imd_to_burn_wei"))
        burn_min_bridge = _tokens(launchpad_slot.get("min_bridge_wei"))
        # BURN READY is the executor's own answer, not a comparison we make.
        #
        # This used to be `burn_accrued >= max(burn_min_bridge, 1)`, and it
        # reported READY minutes after a burn. Every part of it was wrong.
        # `imdToBurn` is the *hook's* accrual and the bridge does not spend
        # it -- `bridgeToBaseBurnReceiver` clamps to the *executor's*
        # `tokenBalance()`. `minBridgeAmount()` is genuinely `0` on chain, so
        # the comparison was vacuous and the `max(..., 1)` floor standing in
        # for it was a whole IMD with no on-chain basis at all -- which LP
        # fees re-accrue past within minutes of a burn (CLAUDE.md: read
        # values live, never hardcode a documented one). And even a funded
        # executor can fail, because the OFT strips shared-decimal dust and
        # enforces its own minimum, so `amountSentLD` can round to zero.
        #
        # `previewBridge()` applies all of that in the contract and answers
        # zero rather than reverting, so `> 0` is exactly "a burn is callable
        # right now". Still tri-state: `None` is a failed read, and the row
        # must render "cannot tell" for it rather than NOT READY.
        bridge_amount = _tokens(launchpad_slot.get("bridge_amount_wei"))
        burn_ready = None if bridge_amount is None else bridge_amount > 0

        data: dict[str, Any] = {
            "as_of": self.cache.newest_as_of(),
            "degraded": self._degraded(),
            "feed_nonce": announce_nonce,
            "lp_liquidity": _opt_int(_field(state, "lp_liquidity")),
            # WP1.4 derives these from liquidity + sqrtPrice + the position's tick
            # bounds; the bounds exist nowhere downstream, which is why the client
            # owns the math and the manager only scales it.
            "lp_imd": _tokens(_field(state, "lp_imd_wei")),
            "lp_weth": _tokens(_field(state, "lp_weth_wei")),
            "lp_owner_ok": self._owner_ok(_field(state, "lp_owner")),
            "gate_open": self._opt_bool(_field(state, "identity_allowed")),
            # `identities_written` is NOT set here. `ChainState` has no such
            # field (WP0.4 dropped it — the registry has no getter), and the
            # ~8 h `LogWindow.identity_updates` count answers a different
            # question. It is filled from `NftStats.written` below.
            "imd_supply": imd_supply,
            "imd_burned_cum": self.cache.observed_burn_total(),
            "eth_usd": market_payload.get("eth_usd"),
            "imd_price_usd": imd_price,
            "imd_change_24h_pct": market_payload.get("imd_change_24h_pct"),
            "imd_vol_24h_usd": market_payload.get("imd_vol_24h_usd"),
            "pool_liquidity_usd": market_payload.get("pool_liquidity_usd"),
            "price_source_disagreement_pct": price_source_disagreement_pct,
            "fp_price_usd": fp_price,
            # The one implementation, imported from analytics/ — never a copy.
            # IMD is FP bridged 1:1, so the spread is a real arbitrage/health
            # metric and it moves with every bridge tx (PRD §6.2).
            "parity_pct": parity_pct(imd_price, fp_price),
            "feed_items": feed_items,
            "feed_last_post_age_s": self._last_post_age(feed_items or [], now),
            "nft_holders": nft_payload.get("nft_holders"),
            "nft_transfers_24h": nft_payload.get("nft_transfers_24h"),
            "nft_dev_holdings": nft_payload.get("nft_dev_holdings"),
            "nft_written": nft_payload.get("nft_written"),
            # One number, one producer (`NftStats.written`, WP1.8): the hero and
            # the NFT panel must never be able to disagree about it, so they are
            # the same expression rather than two reads.
            "identities_written": nft_payload.get("nft_written"),
            "nft_last_sales": nft_payload.get("nft_last_sales"),
            "nft_floor": None,
            "dev_activity": activity_rows,
            # ---- pool (v3 -> v4 migration) — off the fast-tier chain read,
            # so it never waits on the launchpad sweep --------------------
            # `state.lp_position_count` is deliberately not published here
            # any more (fix round 12a: no widget ever read it). The client
            # still fetches it -- ChainState.lp_position_count and the
            # PositionManager.balanceOf(OPS_WALLET) leg behind it are kept,
            # available for a future owner-sanity signal without re-adding
            # the multicall leg; see the task report for the reasoning.
            "pool_venue": self._pool_venue(_field(state, "lp_state")),
            "lp_state": _field(state, "lp_state"),
            # ---- the rest of the pool group, plus burn executor and the
            # launchpad panels — all off the launchpad slot captured above,
            # never this cycle's own (detached, not-yet-landed) sweep -------
            "pool_fee_bps": launchpad_slot.get("pool_fee"),
            "pool_id_source": launchpad_slot.get("pool_id_source"),
            "decoy_pool_count": launchpad_slot.get("decoy_pool_count"),
            "burn_accrued": burn_accrued,
            "burn_staged": _tokens(launchpad_slot.get("executor_balance_wei")),
            "burn_ready": burn_ready,
            "burn_min_bridge": burn_min_bridge,
            "burn_bridgeable": bridge_amount,
            "launchpad_coin_count": launchpad_slot.get("coin_count"),
            # Task 8: the sweep's own population reads, deliberately published
            # alongside `launchpad_coin_count` (the factory's claim) rather
            # than reconciled with it here -- the two agree on a healthy full
            # sweep and every way of disagreeing (a cursor mid-catch-up, a
            # truncated provider page, a too-late first block) is a render-
            # time comparison, per `LaunchpadState`'s own docstring.
            "launchpad_launch_count": launchpad_slot.get("launch_count"),
            "launchpad_new_24h": launchpad_slot.get("new_24h"),
            "launchpad_creator_count": launchpad_slot.get("creator_count"),
            "launchpad_swap_count": launchpad_slot.get("swap_count"),
            "launchpad_trader_count": launchpad_slot.get("trader_count"),
            "launchpad_burned_total": _tokens(launchpad_slot.get("burned_total_wei")),
            "launchpad_creator_eth_owed": _tokens(
                launchpad_slot.get("creator_eth_owed_wei")
            ),
            "launchpad_coins": self._with_mcap_usd(
                launchpad_slot.get("coins"), eth_usd
            ),
            "launchpad_activity": launchpad_slot.get("activity"),
            "launchpad_burnkeepers": launchpad_slot.get("burnkeepers"),
            "launchpad_as_of_hhmm": (
                launchpad_entry.as_of_hhmm() if launchpad_entry is not None else None
            ),
        }

        # ---- pool4 (detached sweep, its own slower "as of") ----------------
        # One contiguous block off the slot captured above, never this cycle's
        # own not-yet-landed sweep. ``_pool4_keys`` is the only place the pool4
        # path divides by 1e18, and the only place it divides by 10**decimals.
        data.update(self._pool4_keys(pool4_slot, pool4_entry, now))

        data.update(
            self._signal_keys(
                self._readings(
                    data,
                    nonces,
                    channel_payload,
                    activity_rows,
                    launchpad_slot,
                    launchpad_ts=(
                        launchpad_entry.ts if launchpad_entry is not None else None
                    ),
                    state=state,
                ),
                now,
            )
        )

        payload = self._finalise(data)

        # Sample *before* reading the series back, so this cycle's point is in
        # the sparkline the user is looking at rather than one refresh behind.
        # ``None`` leaves a series untouched — a dead source must never write a
        # sentinel into a history (CLAUDE.md).
        _safe_call(
            self.cache.sample_series,
            now,
            imd_supply=payload.get("imd_supply"),
            # Fresh-only. `None` on a skipped or failed medium tier, and that
            # costs nothing on the skip path: the tier is due every 90 s while
            # the buckets are hourly, so the bucket the user is looking at is
            # filled by the next real read either way.
            imd_price_usd=(fresh_market or {}).get("imd_price_usd"),
            parity_pct=parity_pct(
                (fresh_market or {}).get("imd_price_usd"),
                (fresh_market or {}).get("fp_price_usd"),
            ),
        )
        payload["supply_series"] = self.cache.get_series(SERIES_IMD_SUPPLY)
        payload["price_series"] = self.cache.get_series(SERIES_IMD_PRICE_USD)

        self.save_cache()
        return payload

    @staticmethod
    def _last_post_age(items: list[dict[str, Any]], now: float) -> float | None:
        """Age of the newest **self**-post. Replies are not the dev posting."""
        stamps = [
            i["ts"] for i in items if i.get("kind") == "self" and i.get("ts") is not None
        ]
        return None if not stamps else max(0.0, float(now) - max(stamps))

    @staticmethod
    def _opt_bool(value: Any) -> bool | None:
        return None if value is None else bool(value)

    @staticmethod
    def _owner_ok(owner: Any) -> bool | None:
        """``None`` = unread, ``False`` = someone other than frenpet.eth holds it.

        PRD §4 wants this as a sanity flag on the hero, and the two are not the
        same fact: conflating them would make a dead RPC read as a stolen LP.
        """
        if owner is None:
            return None
        return str(owner).lower() == OPS_WALLET.lower()

    # -- degradation ---------------------------------------------------------

    def _note(self, group: str, ok: bool) -> None:
        if ok:
            self._failed_groups.discard(group)
        else:
            self._failed_groups.add(group)
            self._error_count += 1

    def _client_degradation(self) -> set[str]:
        """Source groups the client's own truncation/failure flags implicate.

        Reads :attr:`SurfClient.channel_truncated`, ``.activity_truncated`` and
        ``.log_group_failed`` — see the module docstring section on where
        these live. ``getattr(..., default)`` throughout: these three exist on
        the real :class:`~maxpane_dashboard.data.surf_client.SurfClient` but a
        test double that implements only the seven ``fetch_*`` coroutines
        (every WP4 manager-test double so far) need not define them, and this
        method must not raise just because one is absent — that would turn a
        client that is *more* honest about outages into a manager that crashes
        on it.

        Reset to their "nothing wrong" values at the START of each matching
        ``fetch_*`` call on the client, so — once a later task actually calls
        those coroutines — reading them right after reflects only this cycle's
        attempt, never a previous one.
        """
        out: set[str] = set()
        client = self.client
        if getattr(client, "channel_truncated", False):
            out.add(SOURCE_CHANNEL)
        if getattr(client, "activity_truncated", False):
            out.add(SOURCE_ACTIVITY)
        log_group_failed = getattr(client, "log_group_failed", None)
        if isinstance(log_group_failed, dict) and any(log_group_failed.values()):
            out.add(SOURCE_LOGS)
        return out

    def _degraded(self) -> list[str]:
        """Groups the screen must not present as live.

        A group is degraded when its last attempt failed **or** it has never
        produced a payload — the second clause is what keeps a group that failed
        two cycles ago, and is not due again, from reading as healthy — **or**
        the client's own per-call truncation/failure flags say this cycle's read
        was incomplete (:meth:`_client_degradation`; see the module docstring).
        """
        out = set(self._failed_groups)
        for group, slot in GROUP_SLOT.items():
            if self.cache.get_last_good(slot) is None:
                out.add(group)
        out |= self._client_degradation()
        return sorted(out)

    # -- contract enforcement ------------------------------------------------

    def _finalise(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return exactly :data:`SURF_KEYS`, no more and no less."""
        out = self._blank_payload()
        for key, value in data.items():
            if key in out:
                out[key] = value
            else:
                logger.error(
                    "SurfManager produced %r, which is not in SURF_KEYS — dropped", key
                )
        return out

    def _blank_payload(self) -> dict[str, Any]:
        """Every key present, every source down, nothing invented.

        The three **source-backed** list keys — ``feed_items``,
        ``dev_activity``, ``nft_last_sales`` — stay ``None`` here, from
        ``dict.fromkeys``. WP3 froze the opposite pair of meanings and its
        widgets act on them: *a ``None`` list means "source dead", an empty list
        means "genuinely nothing"*, so ``feed_items=[]`` renders "no posts in
        window" with ``UNAVAILABLE_LINE`` deliberately absent, and
        ``dev_activity=[]`` renders "no recent activity". Seeding ``[]`` on a
        blank payload would make a dead Blockscout assert that the channel is
        quiet and the dev wallets idle — a stale-source-presented-as-fact, which
        is what CLAUDE.md's "a dead source degrades to an explicit unavailable
        state" and "a failed read is ``None``, never ``0``" both forbid.

        ``supply_series`` / ``price_series`` are different and stay ``[]``: they
        are *this cache's* history, not a source's answer, and an empty history
        is a fact about the install rather than about the network.
        """
        payload: dict[str, Any] = dict.fromkeys(SURF_KEYS)
        payload.update(
            {
                "degraded": [],
                "supply_series": [],
                "price_series": [],
                "nft_floor": None,     # PRD §4: always None in v1, explicitly
            }
        )
        return payload


__all__ = [
    "DEV_ACTIVITY_LIMIT",
    "FEED_ITEM_LIMIT",
    "GROUP_SLOT",
    "NFT_SALES_LIMIT",
    "SIGNAL_NAMES",      # re-export of analytics.surf_signals.SIGNAL_NAMES
    "SOURCES",
    "SOURCE_ACTIVITY",
    "SOURCE_CHAIN",
    "SOURCE_CHANNEL",
    "SOURCE_LOGS",
    "SOURCE_MARKET",
    "SOURCE_NFT",
    "SOURCE_POOL4",
    "POOL4_LOG_WINDOW_BLOCKS",
    "POOL4_SEPOLIA_HOOK",
    "POOL4_SEPOLIA_TOKEN",
    "SurfManager",
]
