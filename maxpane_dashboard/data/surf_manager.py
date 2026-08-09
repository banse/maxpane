"""Orchestrator for the SURF "Mission Control" dashboard (WP4).

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
4. **"Not due to retry" is not "healthy."** :meth:`SurfCache.is_fresh` /
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
    BURN_EXECUTOR,
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
    SLOT_LOGS,
    SLOT_MARKET,
    SLOT_NFT,
    SERIES_IMD_PRICE_USD,
    SERIES_IMD_SUPPLY,
    TIER_FAST,
    TIER_MEDIUM,
    TIER_SLOW,
    SurfCache,
)
from maxpane_dashboard.data.surf_client import SurfClient
from maxpane_dashboard.data.surf_models import SURF_KEYS

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

SOURCES: tuple[str, ...] = (
    SOURCE_CHAIN,
    SOURCE_CHANNEL,
    SOURCE_MARKET,
    SOURCE_LOGS,
    SOURCE_NFT,
    SOURCE_ACTIVITY,
)

#: group -> the cache slot holding its last-good payload.
GROUP_SLOT: dict[str, str] = {
    SOURCE_CHAIN: SLOT_CHAIN,
    SOURCE_CHANNEL: SLOT_CHANNEL,
    SOURCE_MARKET: SLOT_MARKET,
    SOURCE_LOGS: SLOT_LOGS,
    SOURCE_NFT: SLOT_NFT,
    SOURCE_ACTIVITY: SLOT_ACTIVITY,
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

# NOTE: the counterparty -> kind map that used to live here belongs to WP1.6,
# which fills ``DevTx.kind`` at construction. Keeping a copy here would be a
# second implementation of one vocabulary, and the two would drift the first
# time a contract is added to only one of them.

#: Wei per whole token / per ETH. The models are wei-native and this module is
#: the single place that divides (WP0.4).
WEI = 10**18

#: The hero's v4-hook vocabulary (PRD §4, WP0's ``SURF_KEYS`` comment).
#: Spelled to match ``widgets/surf/hero.py``'s ``HOOK_NOT_LIVE``/``HOOK_LAUNCHED``
#: **exactly**, but deliberately not imported from there: widgets never import
#: from ``data/``/``analytics/`` and this module must not import from
#: ``widgets/`` either (CLAUDE.md's one-directional data flow), so the two
#: string pairs are independently frozen literals on both sides rather than a
#: shared import. A prior reviewer found a sibling widget branching on a
#: lowercase/snake vocabulary ("not_live"/"launched") that the manager never
#: actually emitted — these constants exist so that mistake cannot repeat here.
HOOK_NOT_LIVE = "NOT LIVE"
HOOK_LAUNCHED = "LAUNCHED"


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
    object and some do not, and resolving a block header per log is a round trip
    per event on a pool that already rate-limits. Falling back to the observation
    clock is safe for WP2's detectors — they key on ``tx_hash`` first, so a
    re-observed row can never re-fire — but it does mean a FIRED age can read as
    "just now" for an event that landed a few minutes earlier. See Open issues.
    """
    if isinstance(log, dict):
        stamp = _hex_int(log.get("blockTimestamp") or log.get("timestamp"))
        if stamp:
            return float(stamp)
    return float(now)


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
    """Fetches SURF data across six source groups and returns a flat dict."""

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
        """Persist the cache and close the client. Never raises."""
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
        """
        nonces_res, state_res = await asyncio.gather(
            self._guard(self.client.fetch_nonces, "fetch_nonces"),
            self._guard(self.client.fetch_chain_state, "fetch_chain_state"),
            return_exceptions=False,
        )
        ok = nonces_res is not None and state_res is not None
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

    async def _pool_market(self, tiers: set[str], now: float) -> Any:
        if TIER_MEDIUM not in tiers and self.cache.get_last_good(SLOT_MARKET) is not None:
            return None                     # skip, not a failure: no `_note` above
        snap = await self._guard(self.client.fetch_market, "fetch_market")
        self._note(SOURCE_MARKET, snap is not None)
        if snap is not None:
            self.cache.store_last_good(SLOT_MARKET, self._market_payload(snap), ts=now)
        return snap

    @staticmethod
    def _market_payload(snap: Any) -> dict[str, Any]:
        """The whole PRD §5 market view, scaled once and cached as one dict.

        **All seven values, not just the two prices.** The slot is what `_cycle`
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
        if TIER_MEDIUM not in tiers and self.cache.get_last_good(SLOT_LOGS) is not None:
            return None
        window = await self._guard(self.client.fetch_recent_logs, "fetch_recent_logs")
        self._note(SOURCE_LOGS, window is not None)
        if window is not None:
            # Decoded **into WP2's row shapes** here, once, and cached that way:
            # `_readings` reads these back off the slot on every fast-only
            # refresh (Task WP4.11), so the detectors keep seeing a read window
            # rather than an outage between two medium ticks. All four groups
            # arrive raw; all four are decoded here and nowhere else.
            hooked = self._hook_pool_rows(window, now)
            # `hook_live` is **latched**, and that is not a convenience.
            # `hooked` is only what the *current* ~8 h window shows
            # (`LOG_WINDOW_BLOCKS = 2400`) and this slot is replaced wholesale on
            # every successful medium-tier read, so a `hook_live` derived from
            # the window alone flips the hero back from LAUNCHED to NOT LIVE
            # about eight hours after the launch — on a perfectly healthy chain,
            # for the single event PRD §1/§7 says this dashboard exists to catch.
            # A v4 pool initialization is irreversible, so that is a *wrong*
            # value, not a stale one, and no as-of marker makes it honest.
            # `v4_hook_pools` is deliberately **not** latched: it is the panel's
            # row list and must keep meaning "seen in this window".
            previously_live = bool(
                (
                    getattr(self.cache.get_last_good(SLOT_LOGS), "payload", None) or {}
                ).get("hook_live")
            )
            self.cache.store_last_good(
                SLOT_LOGS,
                {
                    "to_block": _opt_int(_field(window, "to_block")),
                    "bridge_mints": self._bridge_rows(window, now),
                    "v4_hook_pools": hooked,
                    "hook_live": bool(hooked) or previously_live,
                    # Signal 3's detail line: writes seen *in this window*, not
                    # the hero's lifetime "x/2000". Two different numbers with
                    # one name — see the header's consequence 4.
                    "identity_writes": self._identity_writes(window),
                    # Realized sales belong to the logs group, not to the
                    # Blockscout counters: they are on different tiers, and the
                    # NFT panel must keep showing them through a slow-tier skip.
                    "nft_last_sales": self._seaport_sale_rows(window, now),
                },
                ts=now,
            )
        return window

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
        if TIER_SLOW not in tiers and self.cache.get_last_good(SLOT_NFT) is not None:
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

        Every ``return None`` is a skip and must not reach :meth:`_note`.
        """
        cached = self.cache.get_last_good(SLOT_ACTIVITY)
        payload = (cached.payload or {}) if cached is not None else {}
        moved = self._nonce_moved(payload.get("dev_nonce"), dev_nonce) or (
            self._nonce_moved(payload.get("ops_nonce"), ops_nonce)
        )
        if not moved and TIER_SLOW not in tiers and cached is not None:
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

        Every ``return None`` here is a *skip*, not a failure: it must not call
        :meth:`_note`, because a skipped group is not degraded and the feed keeps
        rendering its last-good rows without a staleness marker it has not earned.
        """
        cached = self.cache.get_last_good(SLOT_CHANNEL)
        seen = (cached.payload or {}).get("nonce") if cached is not None else None
        moved = nonce is not None and seen is not None and int(seen) != int(nonce)

        if not moved and cached is not None:
            if seen is not None and nonce is not None:
                return None                 # skip: nothing new was posted
            if TIER_MEDIUM not in tiers:
                return None                 # skip: nonce unreadable, tier fresh

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
                }
            )
        return rows

    def _hook_pool_rows(self, window: Any, now: float) -> list[dict[str, Any]]:
        """Hooked v4 ``Initialize`` rows as ``{ts, tx_hash, hooks}`` (WP2's shape).

        ``Initialize(id, currency0, currency1, fee, tickSpacing, hooks,
        sqrtPriceX96, tick)`` — three indexed args, so ``hooks`` is the third word
        of ``data``. Every one of the 19 existing IMD v4 pools is third-party and
        **hookless**, so a non-zero hooks address *is* the launch signal (PRD §3,
        signal 2); the hookless rows are filtered out here so they can never
        advance WP2's ``v4_tx`` baseline past a real one.
        """
        rows: list[dict[str, Any]] = []
        for log in _field(window, "v4_initializes") or ():
            hooks = _word_addr(log.get("data"), 2)
            if not hooks or int(hooks, 16) == 0:
                continue
            rows.append(
                {
                    "ts": _log_ts(log, now),
                    "tx_hash": str(log.get("transactionHash") or ""),
                    "hooks": hooks,
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
            return None                     # the filter failed; not "no writes"
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
        """
        items: list[dict[str, Any]] = []
        for row in rows or ():
            from_addr = str(_field(row, "from_addr") or "")
            input_hex = str(_field(row, "input_hex") or "")
            kind = _safe_call(
                classify_channel_tx,
                from_addr,
                str(_field(row, "to_addr") or ""),
                _opt_int(_field(row, "value_wei")) or 0,
                input_hex,
                default=None,
            )
            items.append(
                {
                    "ts": _opt_float(_field(row, "ts")),
                    "kind": kind,
                    "from_addr": from_addr,
                    "from_label": KNOWN_LABELS.get(from_addr.lower()),
                    "text": _safe_call(decode_utf8_calldata, input_hex, default=None),
                    "tx_hash": str(_field(row, "tx_hash") or ""),
                    "label": (
                        f"{_field(row, 'method')}()"
                        if _field(row, "method")
                        else (input_hex[:10] if len(input_hex) >= 10 else "")
                    ),
                }
            )
        items.sort(key=lambda i: (i["ts"] is not None, i["ts"] or 0.0), reverse=True)
        return items[:FEED_ITEM_LIMIT]

    # -- signals -------------------------------------------------------------

    def _readings(
        self,
        data: dict[str, Any],
        nonces: Any,
        channel: dict[str, Any],
        activity_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """This cycle's values for the six detectors, keyed by ``READING_KEYS``.

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
        """
        logs = dict(getattr(self.cache.get_last_good(SLOT_LOGS), "payload", None) or {})
        channel = channel or {}
        # The same list `_cycle` renders the feed from — unpacked here rather than
        # passed as a sixth argument, so the rows the panel shows and the rows the
        # detectors read can never be two different lists.
        feed_items = list(channel.get("items") or ())
        read: dict[str, Any] = dict.fromkeys(READING_KEYS)

        # -- fast tier: three nonces, every refresh, the whole early edge -----
        read["announce_nonce"] = data.get("feed_nonce")
        read["dev_nonce"] = _opt_int(_field(nonces, "dev"))
        read["ops_nonce"] = _opt_int(_field(nonces, "ops"))

        # -- fast tier: the batched chain read, via the payload ---------------
        read["lp_liquidity"] = data.get("lp_liquidity")
        read["gate_open"] = data.get("gate_open")
        read["imd_supply"] = data.get("imd_supply")

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
        # PRD §3 #4: "new tx with ``created_contract``, **or** announce-EOA
        # outbound *contract call*". The second never appears in
        # ``fetch_dev_activity`` -- that fetches the two dev wallets' pages, and
        # the announce EOA is neither of them -- so it has to come off the
        # channel page, where `classify_channel_tx` already labels it ``action``.
        # The ERC-8004 registration at channel nonce 4 is the PRD's own worked
        # example of the shape, and without this branch it would not fire.
        #
        # The channel branch is gated on `activity_read` as well as on
        # `channel`, and that is load-bearing: `[]` is a claim that "the deploy
        # window was read and held nothing", and it seeds WP2's `deploy_tx` /
        # `deploy_ts` baselines. One source may not make that claim on the
        # other's behalf — a channel page answering while Blockscout's tx pages
        # are down would seed the baseline before the tx-page source has ever
        # produced a row, and the first real deploy would then be measured
        # against a baseline it never contributed to.
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
        if channel and activity_read:
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
            # question, not a WP4 one; see Open issue 12.
            events.sort(
                key=lambda e: (e["ts"] is not None, e["ts"] or 0.0), reverse=True
            )
        read["deploy_events"] = events
        return read

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

        market, logs, channel, nft, activity = await asyncio.gather(
            self._pool_market(tiers, now),
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
        imd_price = market_payload.get("imd_price_usd")
        fp_price = market_payload.get("fp_price_usd")

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
            "fp_price_usd": fp_price,
            # The one implementation, imported from analytics/ — never a copy.
            # IMD is FP bridged 1:1, so the spread is a real arbitrage/health
            # metric and it moves with every bridge tx (PRD §6.2).
            "parity_pct": parity_pct(imd_price, fp_price),
            "feed_items": feed_items,
            "feed_last_post_age_s": self._last_post_age(feed_items or [], now),
            "hook_status": self._hook_status(),
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
        }

        data.update(
            self._signal_keys(
                self._readings(data, nonces, channel_payload, activity_rows), now
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

    # -- hero: v4 hook status --------------------------------------------------

    def _hook_status(self) -> str | None:
        """``"LAUNCHED"`` / ``"NOT LIVE"`` / ``None`` when the logs pool never answered.

        Reads the **latched** ``hook_live`` written by ``_pool_logs``, never
        ``v4_hook_pools`` — those rows fall out of the ~8 h log window and a
        launch does not. ``None`` means "the logs group has never produced a
        payload" — distinct from a confirmed-empty window, which is a real
        answer (PRD §4), never a guess standing in for an outage.
        """
        entry = self.cache.get_last_good(SLOT_LOGS)
        if entry is None or not isinstance(entry.payload, dict):
            return None
        return HOOK_LAUNCHED if entry.payload.get("hook_live") else HOOK_NOT_LIVE

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
    "HOOK_LAUNCHED",
    "HOOK_NOT_LIVE",
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
