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
This task (WP4.7) wires that composition end-to-end, but no ``fetch_*`` call
happens yet in :meth:`_cycle`, so today the three flags are always at their
"nothing wrong" default and contribute nothing observable — the wiring exists
so that whichever later WP4 task adds the ``fetch_channel_txs`` /
``fetch_dev_activity`` / ``fetch_recent_logs`` calls does not *also* have to
remember to fold these three into ``degraded``: the path already reaches them.
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

        # Divided exactly once, here, and reused everywhere below — the models
        # are wei-native and this dict is the presentation boundary (WP0.4).
        imd_supply = _tokens(_field(state, "imd_supply_wei"))

        # Folded in before anything else reads it: a burn is a *pair* of
        # successful supply reads, and ``record_supply`` refuses to conclude
        # anything from a ``None``.
        self.cache.record_supply(imd_supply, _opt_int(_field(state, "block_number")))

        data: dict[str, Any] = {
            "as_of": self.cache.newest_as_of(),
            "degraded": self._degraded(),
            "feed_nonce": _opt_int(_field(nonces, "announce")),
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
            # question. It is filled from `NftStats.written` in Task WP4.10.
            "imd_supply": imd_supply,
            "imd_burned_cum": self.cache.observed_burn_total(),
        }

        payload = self._finalise(data)

        # Sample *before* reading the series back, so this cycle's point is in
        # the sparkline the user is looking at rather than one refresh behind.
        # ``None`` leaves a series untouched — a dead source must never write a
        # sentinel into a history (CLAUDE.md).
        _safe_call(
            self.cache.sample_series,
            now,
            imd_supply=payload.get("imd_supply"),
            imd_price_usd=payload.get("imd_price_usd"),
            parity_pct=payload.get("parity_pct"),
        )
        payload["supply_series"] = self.cache.get_series(SERIES_IMD_SUPPLY)
        payload["price_series"] = self.cache.get_series(SERIES_IMD_PRICE_USD)

        self.save_cache()
        return payload

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

    def _hook_status(self, hooked_pools: Any) -> str | None:
        """"NOT LIVE" / "LAUNCHED" / ``None`` — the hero's frozen vocabulary.

        Takes the **already-decoded, already hook-filtered** v4 ``Initialize``
        rows for IMD (each with ``hooks != 0x0``) — the same shape
        ``analytics.surf_signals``' ``v4_hook_pools`` reading is built from
        (see its docstring: "all 19 live IMD v4 pools are third-party and
        hookless", filtered upstream). Raw ``LogWindow.v4_initializes`` log
        rows are undecoded on purpose (``surf_models.LogWindow``'s own
        docstring: "the decoders ... live in ``surf_manager``"), and that
        decode is a later WP4 task's job, not this scaffolding task's — so this
        method only turns "is there at least one confirmed hooked pool" into
        the two-word vocabulary the hero renders, and does not itself parse a
        raw log.

        Kept as a **named, tested-by-name method** now — rather than inlined
        into whichever later task first has real data to feed it — because
        ``widgets/surf/hero.py`` and its test suite already name
        ``SurfManager._hook_status`` and its exact vocabulary
        (``HOOK_NOT_LIVE``/``HOOK_LAUNCHED``) in their own docstrings; defining
        it here, correctly, now, is what stops that name or vocabulary from
        drifting before the decoder exists to call it.

        ``None`` means "the logs group was never read this cycle" — distinct
        from an empty sequence, which means "read, and confirmed empty": NOT
        LIVE is a real, confirmed answer (PRD §4), never a guess standing in
        for an outage.
        """
        if hooked_pools is None:
            return None
        try:
            return HOOK_LAUNCHED if len(hooked_pools) > 0 else HOOK_NOT_LIVE
        except TypeError:
            # Not sized (e.g. a bad type slipped through) — an unreadable
            # answer is not the same as a confirmed-empty one.
            return None

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
