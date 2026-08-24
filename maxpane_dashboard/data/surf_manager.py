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
import logging
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
from maxpane_dashboard.data.surf_addresses import (
    ANNOUNCE,
    BURN_EXECUTOR_V1,
    DEV_WALLET,
    FWA_SPLITTER,
    IDMD_NFT,
    KNOWN_LABELS,
    NFPM,
    OPS_WALLET,
    POOL_V3,
    RELAY_DEPOSITORY,
    SEAPORT,
    UNIVERSAL_ROUTER,
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
    SERIES_IMD_PRICE_USD,
    SERIES_IMD_SUPPLY,
    TIER_FAST,
    TIER_LAUNCHPAD,
    TIER_MEDIUM,
    TIER_SLOW,
    SurfCache,
)
from maxpane_dashboard.data.surf_client import SurfClient
from maxpane_dashboard.data.surf_models import SURF_KEYS
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

SOURCES: tuple[str, ...] = (
    SOURCE_CHAIN,
    SOURCE_CHANNEL,
    SOURCE_MARKET,
    SOURCE_LOGS,
    SOURCE_NFT,
    SOURCE_ACTIVITY,
    SOURCE_LAUNCHPAD,
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
}

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
    ) -> None:
        self.poll_interval = poll_interval
        self._clock = clock
        self._cache_path = str(cache_path)
        self.client = client if client is not None else SurfClient()
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
        """Stop the detached launchpad sweep, persist the cache, close the client.

        Never raises. The sweep holds the same client the rest of this
        manager uses, so it is cancelled and awaited *first* — closing
        sockets out from under a task still mid-request is how a clean quit
        turns into a traceback on the way down (curator's ``close()``
        precedent, ``_cancel_crosscheck``/``_cancel_analysis``).
        """
        await self._cancel_launchpad()
        self.save_cache()
        try:
            await self.client.close()
        except Exception as exc:            # noqa: BLE001
            logger.debug("closing the SURF client failed: %s", exc)

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
                    "rows": self._activity_rows(rows),
                    "dev_nonce": dev_nonce,
                    "ops_nonce": ops_nonce,
                },
                ts=now,
            )
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
                }
            )
        out.sort(key=lambda r: (r["ts"] is not None, r["ts"] or 0.0), reverse=True)
        return out[:DEV_ACTIVITY_LIMIT]

    async def _pool_channel(
        self, tiers: set[str], now: float, nonce: int | None
    ) -> Any:
        """Fetch the channel bodies when the announce nonce moved — *whenever* it moved.

        The nonce is the cheap detector and it is read on the **fast** tier, every
        refresh; the bodies are a Blockscout page. Two rules, in this order:

        1. **A nonce change forces the fetch regardless of the medium tier.** PRD
           §11.1 wants the decoded text within one refresh interval of the tx
           landing. Checking ``TIER_MEDIUM`` first (as this method used to) meant
           a post detected on a 30 s fast-tier cycle waited for the 90 s tier
           before its body was pulled — the signal quoting text the payload did
           not have yet, up to three refreshes running.
        2. **An unchanged nonce skips the page**, even when the medium tier is
           due: nothing was posted for 52 days over the real May-to-July gap.
        3. **A tier that is not due skips the page** — including on a cold
           cache, where this method used to fetch unconditionally and so
           bypassed the failure backoff (see :meth:`_pool_market`). Rule 1
           still overrides: a nonce change forces the fetch either way.

        Every ``return None`` here is a *skip*, not a failure: it must not call
        :meth:`_note`, because a skipped group is not degraded and the feed keeps
        rendering its last-good rows without a staleness marker it has not earned.
        """
        cached = self.cache.get_last_good(SLOT_CHANNEL)
        seen = (cached.payload or {}).get("nonce") if cached is not None else None
        moved = nonce is not None and seen is not None and int(seen) != int(nonce)

        if not moved:
            if cached is not None and seen is not None and nonce is not None:
                return None                 # skip: nothing new was posted
            if TIER_MEDIUM not in tiers:
                return None                 # skip: tier not due (fresh, or backed off)

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
    def _seaport_sale_rows(window: Any, now: float) -> list[dict[str, Any]]:
        """Realized IDMD sales as ``{ts, token_id, eth}`` — PRD §4's NFT panel.

        ``OrderFulfilled(bytes32 orderHash, address indexed offerer, address
        indexed zone, address recipient, SpentItem[] offer,
        ReceivedItem[] consideration)``. Two indexed args, so ``data`` opens
        with ``orderHash``, ``recipient`` and the two array *offsets*;
        ``SpentItem`` is 4 words ``(itemType, token, identifier, amount)`` and
        ``ReceivedItem`` is those plus a ``recipient``.

        A row survives only when the **offer** side is the IDMD contract. WP1's
        pre-filter only checks that the payload mentions IDMD *anywhere*, which
        also matches an order paid **in** IDMD — that is a purchase of something
        else and must not appear as a sale of an identity.

        The realized price is the sum of the **native** consideration legs:
        seller proceeds plus the marketplace fee, because both were paid. On the
        pinned fill ``0x5b4d1b44…eadad2`` the two orders come to 0.18 and
        0.1838989 ETH and those sum to the transaction's own ``value`` of
        363898900000000000 wei. That identity is the cheapest available proof
        this walk is right: get an offset wrong and the sum stops matching.
        """
        rows: list[dict[str, Any]] = []
        for log in _field(window, "seaport_sales") or ():
            words = _data_words((log or {}).get("data"))
            offer = _abi_array(words, 2, 4)
            consideration = _abi_array(words, 3, 5)
            token_id = next(
                (
                    _hex_int("0x" + item[2])
                    for item in offer
                    if _word_addr(item[1], 0).lower() == IDMD_NFT.lower()
                ),
                None,
            )
            if token_id is None:
                continue                    # paid in IDMD, not a sale of one
            wei = 0
            for item in consideration:
                if _hex_int("0x" + item[0]) == 0:        # itemType NATIVE
                    wei += _hex_int("0x" + item[3]) or 0
            rows.append(
                {
                    "ts": _log_ts(log, now),
                    "token_id": token_id,
                    "eth": wei / WEI,
                }
            )
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
        ok = pool_state is not None and launchpad_state is not None
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
            "coins": SurfManager._launchpad_coin_rows(_field(launchpad_state, "coins")),
            "swaps_by_coin": _field(launchpad_state, "swaps_by_coin"),
            "launch_count": _opt_int(_field(launchpad_state, "launch_count")),
            "new_24h": _opt_int(_field(launchpad_state, "new_24h")),
            "creator_count": _opt_int(_field(launchpad_state, "creator_count")),
            "cursor": _field(launchpad_state, "cursor"),
        }

    @staticmethod
    def _launchpad_coin_rows(coins: Any) -> list[dict[str, Any]]:
        """``LaunchpadCoin`` rows -> ``SURF_ROW_KEYS["launchpad_coins"]`` dicts.

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
        rows: list[dict[str, Any]] = []
        for coin in coins or ():
            creator = str(_field(coin, "creator") or "")
            rows.append(
                {
                    "ticker": _field(coin, "ticker"),
                    "name": _field(coin, "name"),
                    "creator": creator,
                    "creator_known": KNOWN_LABELS.get(creator.lower()) is not None,
                    "age_s": _opt_float(_field(coin, "age_s")),
                    "price_eth": _opt_float(_field(coin, "price_eth")),
                    "change_24h_pct": _opt_float(_field(coin, "change_24h_pct")),
                    "swaps_24h": _opt_int(_field(coin, "swaps_24h")),
                    "swaps_all": _opt_int(_field(coin, "swaps_all")),
                    "imd_burned": _opt_float(_field(coin, "imd_burned")),
                }
            )
        return rows

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
        # Tri-state on purpose (Task 6 brief): "we cannot tell" is not "not
        # ready". `None` unless *both* legs were actually read this-or-a-prior
        # sweep; only then does it become a real `True`/`False`.
        burn_ready = (
            None
            if burn_accrued is None or burn_min_bridge is None
            else burn_accrued >= max(burn_min_bridge, 1)
        )

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
            "launchpad_coins": launchpad_slot.get("coins"),
            "launchpad_as_of_hhmm": (
                launchpad_entry.as_of_hhmm() if launchpad_entry is not None else None
            ),
        }

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
    "SurfManager",
]
