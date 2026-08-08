# WP4 — SURF cache + manager

**Goal:** build `data/surf_cache.py` (tiered TTLs, last-good with as-of markers, three
validated series, persisted signal baselines, observed-burn accumulator) and
`data/surf_manager.py` (tier-composed client fetches → `build_signals` → exactly the
frozen `SURF_KEYS` flat dict, with a per-source-group degraded list), so every widget
work package has one honest data contract to build against.

**Dependencies:** WP0 (`data/surf_addresses.py`, `data/surf_models.py`), WP1
(`data/surf_client.py`), WP2 (`analytics/surf_signals.py`). Nothing in WP4 may be started
before `SURF_KEYS` and the seven model dataclasses exist — every manager test asserts
against them.

**Owner note:** WP4 owns `maxpane_dashboard/data/surf_cache.py`,
`maxpane_dashboard/data/surf_manager.py`, `tests/data/test_surf_cache.py` and
`tests/data/test_surf_manager.py` — and nothing else. It does **not** touch `app.py`,
`__main__.py`, `screens/game_select.py` or `themes/minimal.tcss` (WP6's files), and it
does not edit `surf_client.py`, `surf_models.py` or `surf_signals.py`. Defects found in
those files get **reported to the plan owner, never fixed here** (CLAUDE.md, *Working
with agents*).

---

## Interfaces this package consumes (freeze check before Task WP4.1)

Run this first; if any import fails, stop and report — do not stub the missing module.

```bash
cd /Library/Vibes/autopull && .venv/bin/python -c "
import dataclasses
from maxpane_dashboard.data.surf_models import (
    SURF_KEYS, NonceSet, ChainState, ChannelTx, DevTx, MarketSnapshot, LogWindow, NftStats)
from maxpane_dashboard.data.surf_addresses import (
    ANNOUNCE, DEV_WALLET, OPS_WALLET, IMD_TOKEN, ERC8004_REGISTRY, KNOWN_LABELS,
    BURN_EXECUTOR, NFPM, POOL_V3, FWA_SPLITTER, RELAY_DEPOSITORY, SEAPORT,
    UNIVERSAL_ROUTER)
from maxpane_dashboard.analytics.surf_signals import (
    build_signals, classify_channel_tx, decode_utf8_calldata, parity_pct,
    READING_KEYS, SIGNAL_NAMES, FIRED_TTL_S)
print(len(SURF_KEYS), 'keys'); print(len(READING_KEYS), 'readings'); print(FIRED_TTL_S)
print(SIGNAL_NAMES)   # WP2 derives it from _DETECTORS; WP4 re-exports, never retypes
for model in (NonceSet, ChainState, ChannelTx, DevTx, MarketSnapshot, LogWindow, NftStats):
    print(model.__name__, [f.name for f in dataclasses.fields(model)])
"
```

Then diff that output against the table below rather than trusting either. WP0.4 also
exports the same lists as `tests/data/test_surf_models.CONSTRUCTOR_KWARGS`, and Task WP4.7
asserts WP4's doubles construct against them — so a rename lands as a collection error in
this suite instead of as a dark hero panel:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -c "
import dataclasses
from tests.data.test_surf_models import CONSTRUCTOR_KWARGS
for model, names in CONSTRUCTOR_KWARGS.items():
    assert tuple(f.name for f in dataclasses.fields(model)) == names, model.__name__
print('model vocabulary agrees')
"
```

**The field table below is WP0.4's, quoted verbatim — it is the one freeze.** The last
line of the command above prints the real field lists; if any name differs from this
table, **stop and report it as a WP0/WP1 defect** rather than adapting WP4 to a third
spelling. Do not paraphrase, and in particular do not reach for a *flat-dict* key: WP4's
own output is named `lp_imd`, `imd_supply`, `gate_open`, `value_eth`, `block` — none of
which is a model field, and every one of which `_field()` will now reject loudly.

| Model | Field names WP4 reads (WP0.4 verbatim) |
|---|---|
| `NonceSet` | `announce`, `dev`, `ops`, `block_number` — each `int \| None` |
| `ChainState` | `lp_liquidity`, `lp_imd_wei`, `lp_weth_wei`, `lp_owner`, `identity_allowed`, `imd_supply_wei`, `block_number` |
| `ChannelTx` | `tx_hash`, `ts`, `nonce`, `from_addr`, `to_addr`, `value_wei`, `input_hex` |
| `DevTx` | `tx_hash`, `ts`, `wallet_label`, `from_addr`, `to_addr`, `counterparty`, `counterparty_label`, `value_wei`, `method`, `kind`, `created_contract` |
| `MarketSnapshot` | `imd_price_usd`, `imd_change_24h_pct`, `imd_vol_24h_usd`, `pool_liquidity_usd`, `pool_imd`, `pool_weth`, `fp_price_usd`, `eth_usd` |
| `LogWindow` | `to_block`, `bridge_mints`, `identity_updates`, `v4_initializes`, `seaport_sales` |
| `NftStats` | `holders`, `total_supply`, `transfers_total`, `transfers_24h`, `dev_holdings`, `written`, `floor_eth` |

Four consequences of quoting WP0.4 rather than paraphrasing it:

1. **Models are wei-native; the flat dict is the presentation boundary.** `imd_supply_wei`,
   `lp_imd_wei`, `lp_weth_wei` and `DevTx.value_wei` are `int` wei. The manager divides
   **exactly once**, in `_tokens()` / `_eth()`, when it builds `imd_supply`, `lp_imd`,
   `lp_weth` and `value_eth`.

   `MarketSnapshot.pool_imd` / `pool_weth` are a *different* number and are **not** the
   hero's LP legs: they are DexScreener's whole-pool reserves across every position, while
   the hero tracks position 1167726 alone. They are already whole tokens, so dividing them
   would be a second division of something that was never wei.
2. **Model names mirror the chain; flat keys mirror the PRD, and the two differ on
   purpose.** The getter is `identityAllowed()`, so the field is
   `ChainState.identity_allowed` and the hero key is `gate_open`. This mapping is the whole
   table below — write it once, in `_cycle`, and never reach for the flat name on a model.

   | flat key | comes from |
   |---|---|
   | `gate_open` | `ChainState.identity_allowed` |
   | `imd_supply` | `ChainState.imd_supply_wei` ÷ 1e18 |
   | `lp_liquidity` | `ChainState.lp_liquidity` (raw `L`, unscaled) |
   | `lp_owner_ok` | `ChainState.lp_owner` == `OPS_WALLET` |
   | `lp_imd` / `lp_weth` | `ChainState.lp_imd_wei` / `lp_weth_wei` ÷ 1e18 |
   | `identities_written` / `nft_written` | `NftStats.written` — one number, one producer (WP1.8) |
   | `nft_transfers_24h` | `NftStats.transfers_24h` |
   | `value_eth` | `DevTx.value_wei` ÷ 1e18 |
   | `counterparty_known` | `DevTx.counterparty_label is not None` |
   | `nft_last_sales` | `LogWindow.seaport_sales` (**raw** — decoded in WP4.9) |

3. **`getattr(obj, "<field>", None)` is banned for model fields.** It turns a renamed
   field into a silent `None`, which this data layer encodes as *outage* — the exact
   failure this table exists to prevent. Use the `_field()` helper (Task WP4.7): it
   returns `None` when the whole read failed and raises `AttributeError` when the *name*
   is wrong. This is not a style rule. An earlier revision of this plan read
   `getattr(state, "lp_imd", None)`, `getattr(state, "identity_allowed", None)` and
   `getattr(logs, "identity_writes", None)` against a `ChainState`/`LogWindow` that had no
   such fields; the whole hero would have rendered as an outage on a healthy chain, with
   every test green, because a default swallowed the typo.
4. **`identities_written` is two different numbers wearing one name, and WP4 must keep
   them apart.** The *flat key* `identities_written` (and its twin `nft_written`) is a
   **lifetime** count: distinct ids that ever appear in an `IdentityHashUpdated` log,
   which WP1.8's `_count_identities_written()` walks off Blockscout's
   `/addresses/{IDENTITY_REGISTRY}/logs` and returns as `NftStats.written` — 1 of 2000,
   written 2026-05-14. Both flat keys read that one field; `ChainState` has no such
   getter, so there is nothing else to read (WP0.4's `ChainState` docstring says so).

   WP2's *reading* of the same name is the other number: distinct `topics[1]` over
   `LogWindow.identity_updates`, a ~2,400-block (≈8 h) window — "written since
   breakfast", which is signal 3's detail line (PRD §3 #3: "`IdentityHashUpdated` log
   count ↑ → detail"). WP4.9 counts it and WP4.11 feeds it to `build_signals`; wp1.md
   open issue 9 assigns exactly that split. Cross them and both halves break silently:
   the hero renders `0/2000` on a chain whose real answer is `1/2000`, and
   `_detect_gate`'s `written > base_written` WATCH branch — "the gate opened and closed
   between two polls" — becomes unreachable. Never `len(rows)` for either: a holder
   replacing their hash fires the event twice for one identity.

### Ownership: the address-poisoning defence — WP1 fills the fields, WP4 re-checks

**Unresolved across packages; flagged for the orchestrator, implemented defensively here.**
WP1.6 and this file were both revised to "settle" this question and settled it in opposite
directions: WP1's *Decode ownership* table assigns the sender filter, the `KNOWN_LABELS`
lookup and the `kind` derivation to `fetch_dev_activity`, and the paragraph this replaces
assigned all three to `_activity_rows`. Two owners is the same failure as none — one of
them will be deleted as redundant by whoever reads it second.

The frozen model decides the split, and it decides it in WP1's favour: WP0.4's `DevTx`
carries `counterparty`, `counterparty_label` and `kind`, so **WP1 fills them** — a
constructor cannot leave a non-default field unset, and a double that pre-labels nothing
would be testing a client that cannot exist. WP4 therefore **reads** those three fields
rather than deriving them, and `counterparty_known` is the one thing it still computes
(`counterparty_label is not None`).

WP4 keeps the sender check as **defence in depth**, not as the owner of the rule: a row
whose `from_addr` is not the wallet named by its own `wallet_label` is dropped in
`_activity_rows` with a warning log. It costs one comparison, it cannot mask a WP1 bug
(the log makes it loud), and unlike a duplicated *label* lookup it is not a second
implementation of a rule — it is an assertion about one. If the orchestrator moves
ownership to WP4 instead, the change here is to derive the three fields rather than read
them, and `DevTx` loses them in WP0.4; do not do both.

WP3 keeps its `kind == "dust"` drop rule as defence in depth; after this change the
manager never emits a `dust` row, because it never emits an inbound row at all.

`ChannelTx` **must** carry the raw `input_hex`: WP4 derives `kind` through
`classify_channel_tx` and `text` through `decode_utf8_calldata`, so those two pure
functions have exactly one caller and the manager integration test exercises them for
real.

### The readings contract is WP2's `READING_KEYS`, not a paraphrase of it

`SurfManager._readings()` returns `dict.fromkeys(surf_signals.READING_KEYS)` updated in
place, and a test asserts `set(readings) == set(READING_KEYS)`. WP2 encodes *absent or
`None`* as outage, so a key WP4 forgets is not a loud failure — it is a detector that
silently never fires. All fourteen keys are filled in Task WP4.11.

---

### Task WP4.1: Cache scaffolding — refresh tiers on an injected clock

**Files:**
- Create: `/Library/Vibes/autopull/maxpane_dashboard/data/surf_cache.py`
- Test: `/Library/Vibes/autopull/tests/data/test_surf_cache.py`

**Interfaces:**
- Consumes: nothing yet (stdlib only).
- Produces: `DEFAULT_CACHE_PATH: str`, `TIER_FAST/TIER_MEDIUM/TIER_SLOW: str`,
  `TIERS: tuple[str, ...]`, `TIER_TTL_SECONDS: dict[str, float]`,
  `TIER_FAILURE_BACKOFF_SECONDS: dict[str, float]`,
  `SurfCache(path: str = DEFAULT_CACHE_PATH, clock: Callable[[], float] = time.time)`,
  `SurfCache.is_fresh(tier, now=None) -> bool`, `.is_due(tier, now=None) -> bool`,
  `.tiers_due(now=None) -> tuple[str, ...]`, `.mark_fetched(tier, now=None) -> None`,
  `.mark_failed(tier, now=None, retry_after=None) -> None`,
  `.seconds_until_due(tier, now=None) -> float`.

- [ ] **Write the failing test.** Create `tests/data/test_surf_cache.py`:

```python
"""Tests for the SURF tiered cache and its persistence layer (WP4).

Everything runs offline against a fake clock and ``tmp_path``: no network, no
sleeping, no dependence on wall-clock time.
"""

from __future__ import annotations

import json
import math

import pytest

from maxpane_dashboard.data.surf_cache import (
    DEFAULT_CACHE_PATH,
    TIER_FAST,
    TIER_MEDIUM,
    TIER_SLOW,
    TIERS,
    TIER_TTL_SECONDS,
    SurfCache,
)


class FakeClock:
    """Monotonic-by-hand clock so TTL tests never sleep."""

    def __init__(self, t: float = 1_786_190_400.0) -> None:   # 2026-08-08T12:00:00Z
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> float:
        self.t += float(seconds)
        return self.t


def _cache(tmp_path, clock=None) -> SurfCache:
    return SurfCache(path=str(tmp_path / "surf_cache.json"), clock=clock or FakeClock())


# ---------------------------------------------------------------------------
# Refresh tiers (PRD §5)
# ---------------------------------------------------------------------------


def test_tier_ttls_match_the_prd(tmp_path):
    """fast is due every refresh; medium 90 s; slow 420 s."""
    clock = FakeClock()
    c = _cache(tmp_path, clock)

    assert TIERS == (TIER_FAST, TIER_MEDIUM, TIER_SLOW)
    assert TIER_TTL_SECONDS[TIER_FAST] == 0.0
    assert 60.0 <= TIER_TTL_SECONDS[TIER_MEDIUM] <= 120.0
    assert 300.0 <= TIER_TTL_SECONDS[TIER_SLOW] <= 600.0

    # Nothing fetched yet: everything is due.
    assert set(c.tiers_due()) == set(TIERS)

    for tier in TIERS:
        c.mark_fetched(tier)
    # fast has a zero TTL by design — the announce nonce is the whole edge.
    assert c.tiers_due() == (TIER_FAST,)

    clock.advance(TIER_TTL_SECONDS[TIER_MEDIUM])
    assert TIER_MEDIUM in c.tiers_due()
    assert TIER_SLOW not in c.tiers_due()

    clock.advance(TIER_TTL_SECONDS[TIER_SLOW])
    assert set(c.tiers_due()) == set(TIERS)


def test_failed_tier_backs_off_instead_of_hammering(tmp_path):
    clock = FakeClock()
    c = _cache(tmp_path, clock)

    c.mark_failed(TIER_MEDIUM)
    assert TIER_MEDIUM not in c.tiers_due()      # spaced, not immediate
    assert c.seconds_until_due(TIER_MEDIUM) > 0.0

    clock.advance(60.0)
    assert TIER_MEDIUM in c.tiers_due()
    # A failure never counts as a fetch.
    assert c.last_fetch_ts(TIER_MEDIUM) is None


def test_explicit_now_overrides_the_injected_clock(tmp_path):
    """Every time-taking method accepts ``now=`` (CLAUDE.md: inject the clock)."""
    clock = FakeClock()
    c = _cache(tmp_path, clock)
    c.mark_fetched(TIER_SLOW, now=1_000.0)
    assert c.is_fresh(TIER_SLOW, now=1_100.0) is True
    assert c.is_fresh(TIER_SLOW, now=1_000.0 + TIER_TTL_SECONDS[TIER_SLOW]) is False


def test_unknown_tier_raises(tmp_path):
    c = _cache(tmp_path)
    with pytest.raises(ValueError):
        c.mark_fetched("hourly")


def test_default_cache_path_is_the_maxpane_convention():
    assert DEFAULT_CACHE_PATH.endswith("/.maxpane/surf_cache.json")
```

- [ ] **Run it and watch it fail.** `.venv/bin/python -m pytest tests/data/test_surf_cache.py -v`
      → `ModuleNotFoundError: No module named 'maxpane_dashboard.data.surf_cache'`
      (collection error, 0 tests run).

- [ ] **Minimal implementation.** Create `maxpane_dashboard/data/surf_cache.py`:

```python
"""Tiered cache, last-good snapshots, series and signal baselines for SURF (WP4).

This module owns *when* :class:`~maxpane_dashboard.data.surf_manager.SurfManager`
is allowed to fetch, *what it may show when a fetch fails*, and *what state
survives a restart*. It holds no clients, does no I/O other than reading and
writing its own JSON file, and imports nothing from the project except the
dependency-free :mod:`maxpane_dashboard.data.series_points` leaf.

Three refresh tiers, sized from PRD §5:

``fast``    every refresh (TTL 0). Three ``eth_getTransactionCount`` reads plus
            one batched ``eth_call`` round. The announce channel emits **no
            logs**, so nonce polling is the only detector that exists for it and
            the whole "how early am I" claim rests on it running every tick.
``medium``  90 s. ``eth_getLogs`` windows, GeckoTerminal/DexScreener, and the
            Blockscout channel bodies — the last only when the nonce moved.
``slow``    420 s. Blockscout counters/holders and the dev tx pages.

A failure never marks a tier fetched; it only spaces the retry
(:data:`TIER_FAILURE_BACKOFF_SECONDS`), so a rate-limited host is not hammered
while the last-good payload covers the gap.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maxpane_dashboard.data.series_points import (
    CLOCK_SKEW_TOLERANCE_SECONDS,
    coerce_points,
)

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = str(Path.home() / ".maxpane" / "surf_cache.json")

_SCHEMA_VERSION = 1
_HISTORY_HOURS = 168          # 7 days of hourly buckets

# ---------------------------------------------------------------------------
# Refresh tiers (PRD §5)
# ---------------------------------------------------------------------------

TIER_FAST = "fast"
TIER_MEDIUM = "medium"
TIER_SLOW = "slow"

TIERS: tuple[str, ...] = (TIER_FAST, TIER_MEDIUM, TIER_SLOW)

TIER_TTL_SECONDS: dict[str, float] = {
    TIER_FAST: 0.0,       # every refresh — see the module docstring
    TIER_MEDIUM: 90.0,    # PRD §5 says 60-120 s
    TIER_SLOW: 420.0,     # PRD §5 says 5-10 min
}

TIER_FAILURE_BACKOFF_SECONDS: dict[str, float] = {
    TIER_FAST: 15.0,
    TIER_MEDIUM: 60.0,
    TIER_SLOW: 120.0,
}


class SurfCache:
    """Tiered TTLs, last-good store, series and baselines for one SURF process.

    Single-threaded asyncio access, no locking, matching the rest of the repo.
    ``clock`` is injectable and every time-taking method also accepts an explicit
    ``now=`` so tests drive expiry without sleeping.
    """

    def __init__(
        self,
        path: str = DEFAULT_CACHE_PATH,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = str(path)
        self._clock = clock
        self._tier_last_fetch: dict[str, float] = {}
        self._tier_next_due: dict[str, float] = {}

    # -- clock ---------------------------------------------------------------

    def _now(self, now: float | None = None) -> float:
        return float(self._clock()) if now is None else float(now)

    # -- tiers ---------------------------------------------------------------

    @staticmethod
    def _check_tier(tier: str) -> str:
        if tier not in TIER_TTL_SECONDS:
            raise ValueError(
                f"unknown SURF refresh tier {tier!r}; expected one of {TIERS}"
            )
        return tier

    def is_fresh(self, tier: str, now: float | None = None) -> bool:
        """``True`` while ``tier``'s TTL has not elapsed (i.e. do not fetch)."""
        self._check_tier(tier)
        due_at = self._tier_next_due.get(tier)
        if due_at is None:
            return False
        return self._now(now) < due_at

    def is_due(self, tier: str, now: float | None = None) -> bool:
        return not self.is_fresh(tier, now)

    def tiers_due(self, now: float | None = None) -> tuple[str, ...]:
        """Every tier whose TTL has elapsed, in :data:`TIERS` order."""
        ts = self._now(now)
        return tuple(t for t in TIERS if not self.is_fresh(t, ts))

    def mark_fetched(self, tier: str, now: float | None = None) -> None:
        """Record a *successful* fetch of ``tier`` and restart its TTL."""
        self._check_tier(tier)
        ts = self._now(now)
        self._tier_last_fetch[tier] = ts
        self._tier_next_due[tier] = ts + TIER_TTL_SECONDS[tier]

    def mark_failed(
        self,
        tier: str,
        now: float | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Record a failed fetch: keep the last-good payload, space the retry."""
        self._check_tier(tier)
        backoff = (
            TIER_FAILURE_BACKOFF_SECONDS[tier]
            if retry_after is None
            else float(retry_after)
        )
        self._tier_next_due[tier] = self._now(now) + max(0.0, backoff)

    def seconds_until_due(self, tier: str, now: float | None = None) -> float:
        self._check_tier(tier)
        due_at = self._tier_next_due.get(tier)
        if due_at is None:
            return 0.0
        return max(0.0, due_at - self._now(now))

    def last_fetch_ts(self, tier: str) -> float | None:
        self._check_tier(tier)
        return self._tier_last_fetch.get(tier)


__all__ = [
    "DEFAULT_CACHE_PATH",
    "SurfCache",
    "TIERS",
    "TIER_FAILURE_BACKOFF_SECONDS",
    "TIER_FAST",
    "TIER_MEDIUM",
    "TIER_SLOW",
    "TIER_TTL_SECONDS",
]
```

- [ ] **Run to green.** `.venv/bin/python -m pytest tests/data/test_surf_cache.py -v`
      → 5 passed.

- [ ] **Commit.**
```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/data/surf_cache.py tests/data/test_surf_cache.py && git commit -m "feat(surf): tiered refresh TTLs on an injected clock"
```

---

### Task WP4.2: Last-good slots with mandatory as-of markers

**Files:**
- Modify: `/Library/Vibes/autopull/maxpane_dashboard/data/surf_cache.py`
- Test: `/Library/Vibes/autopull/tests/data/test_surf_cache.py`

**Interfaces:**
- Produces: `LastGood(payload: Any, ts: float)` frozen dataclass with
  `.age_seconds(now) -> float`, `.as_of_hhmm() -> str`, `.to_dict()`, `.from_dict()`;
  `SLOT_CHAIN/SLOT_CHANNEL/SLOT_MARKET/SLOT_LOGS/SLOT_NFT/SLOT_ACTIVITY: str`,
  `SLOTS: tuple[str, ...]`;
  `SurfCache.store_last_good(slot, payload, *, ts=None) -> LastGood`,
  `.get_last_good(slot) -> LastGood | None`, `.as_of_ts(slot) -> float | None`,
  `.age_of(slot, now=None) -> float | None`, `.newest_as_of() -> float | None`.

- [ ] **Write the failing test.** Append to `tests/data/test_surf_cache.py`:

```python
from maxpane_dashboard.data.surf_cache import (   # noqa: E402  (appended import)
    SLOTS,
    SLOT_CHAIN,
    SLOT_MARKET,
    LastGood,
)


# ---------------------------------------------------------------------------
# Last-good slots
# ---------------------------------------------------------------------------


def test_last_good_survives_a_failed_fetch_and_carries_its_timestamp(tmp_path):
    clock = FakeClock()
    c = _cache(tmp_path, clock)

    c.store_last_good(SLOT_MARKET, {"imd_price_usd": 0.7074})
    clock.advance(300.0)
    c.mark_failed(TIER_MEDIUM)

    entry = c.get_last_good(SLOT_MARKET)
    assert entry.payload == {"imd_price_usd": 0.7074}
    assert entry.age_seconds(clock.t) == 300.0
    assert c.as_of_ts(SLOT_MARKET) == clock.t - 300.0
    assert c.age_of(SLOT_MARKET) == 300.0
    assert len(entry.as_of_hhmm()) == 5 and ":" in entry.as_of_hhmm()


def test_a_last_good_never_exists_without_a_timestamp(tmp_path):
    """A stale value presented as live is worse than an honest gap."""
    c = _cache(tmp_path)
    entry = c.store_last_good(SLOT_CHAIN, {"imd_supply": 2376731.868679})
    assert entry.ts > 0.0
    with pytest.raises(Exception):
        entry.ts = 1.0                       # type: ignore[misc]
    assert entry.age_seconds(entry.ts - 5.0) == 0.0     # never negative


def test_unknown_slot_and_empty_slots_are_honest(tmp_path):
    c = _cache(tmp_path)
    assert c.get_last_good(SLOT_CHAIN) is None
    assert c.as_of_ts(SLOT_CHAIN) is None
    assert c.age_of(SLOT_CHAIN) is None
    assert c.newest_as_of() is None
    with pytest.raises(ValueError):
        c.store_last_good("weather", {})


def test_newest_as_of_is_the_freshest_successful_read(tmp_path):
    clock = FakeClock()
    c = _cache(tmp_path, clock)
    c.store_last_good(SLOT_CHAIN, {})
    clock.advance(120.0)
    c.store_last_good(SLOT_MARKET, {})
    assert c.newest_as_of() == clock.t
    assert len(SLOTS) == 6
```

- [ ] **Run it and watch it fail.** `.venv/bin/python -m pytest tests/data/test_surf_cache.py -v`
      → `ImportError: cannot import name 'SLOTS' from ...surf_cache`.

- [ ] **Minimal implementation.** Insert the slot constants after
      `TIER_FAILURE_BACKOFF_SECONDS`, and the `LastGood` dataclass plus the four
      methods into `SurfCache`:

```python
# ---------------------------------------------------------------------------
# Last-good slots — one per independently failing source group (PRD §5 meta)
# ---------------------------------------------------------------------------

SLOT_CHAIN = "chain"          # state RPC: nonces + the batched eth_call round
SLOT_CHANNEL = "channel"      # Blockscout channel bodies
SLOT_MARKET = "market"        # GeckoTerminal / DexScreener / CoinGecko
SLOT_LOGS = "logs"            # logs RPC pool (mints, identity writes, v4, Seaport)
SLOT_NFT = "nft"              # Blockscout token counters / holders
SLOT_ACTIVITY = "activity"    # Blockscout dev tx pages

SLOTS: tuple[str, ...] = (
    SLOT_CHAIN,
    SLOT_CHANNEL,
    SLOT_MARKET,
    SLOT_LOGS,
    SLOT_NFT,
    SLOT_ACTIVITY,
)


@dataclass(frozen=True)
class LastGood:
    """One source group's last *successful* payload with the time it arrived.

    ``ts`` is mandatory: it is what lets a widget render ``as of HH:MM`` instead
    of implying the value is live. A :class:`LastGood` never exists without it.
    """

    payload: Any
    ts: float

    def age_seconds(self, now: float) -> float:
        return max(0.0, float(now) - float(self.ts))

    def as_of_hhmm(self) -> str:
        return time.strftime("%H:%M", time.localtime(self.ts))

    def to_dict(self) -> dict[str, Any]:
        return {"payload": _jsonable(self.payload), "ts": float(self.ts)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LastGood":
        return cls(payload=data.get("payload"), ts=float(data.get("ts") or 0.0))


def _jsonable(value: Any, _depth: int = 0) -> Any:
    """Best-effort conversion of a cached payload to JSON-safe primitives.

    Non-finite floats become ``None`` and unknown objects are dropped rather
    than coerced — fabricating a value on the way to disk is worse than losing
    it.
    """
    if _depth > 8:
        return None
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset, deque)):
        return [_jsonable(v, _depth + 1) for v in value]
    logger.debug("Dropping non-serialisable %s from the SURF cache", type(value).__name__)
    return None
```

In `SurfCache.__init__` add `self.last_good: dict[str, LastGood] = {}`, and add the
methods:

```python
    # -- last-good snapshots -------------------------------------------------

    @staticmethod
    def _check_slot(slot: str) -> str:
        if slot not in SLOTS:
            raise ValueError(f"unknown SURF slot {slot!r}; expected one of {SLOTS}")
        return slot

    def store_last_good(
        self, slot: str, payload: Any, *, ts: float | None = None
    ) -> LastGood:
        """Replace ``slot``'s last-good payload. Always stamped with a timestamp."""
        self._check_slot(slot)
        entry = LastGood(payload=payload, ts=self._now(ts))
        self.last_good[slot] = entry
        return entry

    def get_last_good(self, slot: str) -> LastGood | None:
        return self.last_good.get(slot)

    def as_of_ts(self, slot: str) -> float | None:
        entry = self.last_good.get(slot)
        return None if entry is None else entry.ts

    def age_of(self, slot: str, now: float | None = None) -> float | None:
        entry = self.last_good.get(slot)
        return None if entry is None else entry.age_seconds(self._now(now))

    def newest_as_of(self) -> float | None:
        """Timestamp of the freshest successful read across every slot."""
        stamps = [e.ts for e in self.last_good.values()]
        return max(stamps) if stamps else None
```

Extend `__all__` with `"LastGood"`, `"SLOTS"`, `"SLOT_ACTIVITY"`, `"SLOT_CHAIN"`,
`"SLOT_CHANNEL"`, `"SLOT_LOGS"`, `"SLOT_MARKET"`, `"SLOT_NFT"`.

- [ ] **Run to green.** `.venv/bin/python -m pytest tests/data/test_surf_cache.py -v`
      → 9 passed.

- [ ] **Commit.**
```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/data/surf_cache.py tests/data/test_surf_cache.py && git commit -m "feat(surf): last-good slots that always carry an as-of timestamp"
```

---

### Task WP4.3: Three hour-bucketed series — and a `None` never punches a zero

**Files:**
- Modify: `/Library/Vibes/autopull/maxpane_dashboard/data/surf_cache.py`
- Test: `/Library/Vibes/autopull/tests/data/test_surf_cache.py`

**Interfaces:**
- Produces: `SERIES_IMD_SUPPLY = "imd_supply"`, `SERIES_IMD_PRICE_USD = "imd_price_usd"`,
  `SERIES_PARITY_PCT = "parity_pct"`, `SERIES_NAMES: tuple[str, ...]`,
  `SERIES_ALLOW_NEGATIVE: dict[str, bool]`;
  `SurfCache.sample_series(now_ts, *, imd_supply=None, imd_price_usd=None, parity_pct=None) -> None`,
  `.get_series(name) -> list[list[float]]`.

> `parity_pct` is a **spread** and is legitimately negative (the live capture is
> −2.75%), so it is the one series loaded with `allow_negative=True`. It has no
> `SURF_KEYS` entry in v1 — it is retained for the v2 parity sparkline and to keep the
> burn/price/parity history one round trip apart. See *Open issues*.

- [ ] **Write the failing test.** Append to `tests/data/test_surf_cache.py`:

```python
from maxpane_dashboard.data.surf_cache import (   # noqa: E402
    SERIES_IMD_PRICE_USD,
    SERIES_IMD_SUPPLY,
    SERIES_NAMES,
    SERIES_PARITY_PCT,
)

# Live values captured 2026-08-08 (tests/fixtures/surf/captures/).
IMD_SUPPLY = 2_376_731.868679          # imd_token.json total_supply / 1e18
IMD_PRICE_USD = 0.7074                 # dexscreener_imd.json priceUsd
FP_PRICE_USD = 0.7274                  # dexscreener_fp.json, deepest pair
PARITY_PCT = -2.7495188342040167       # (imd - fp) / fp * 100


def test_series_bucket_by_hour_and_overwrite_within_the_hour(tmp_path):
    c = _cache(tmp_path)
    base = 1_786_190_400.0               # exactly on an hour boundary

    c.sample_series(base, imd_supply=IMD_SUPPLY, imd_price_usd=IMD_PRICE_USD)
    c.sample_series(base + 1800.0, imd_supply=IMD_SUPPLY - 15_745.0)
    assert c.get_series(SERIES_IMD_SUPPLY) == [[base, IMD_SUPPLY - 15_745.0]]

    c.sample_series(base + 3600.0, imd_supply=IMD_SUPPLY - 15_745.0)
    assert len(c.get_series(SERIES_IMD_SUPPLY)) == 2
    assert c.get_series(SERIES_IMD_PRICE_USD) == [[base, IMD_PRICE_USD]]


def test_none_never_punches_a_zero_into_a_series(tmp_path):
    """A dead RPC must not write a 2.37M -> 0 supply step into the sparkline."""
    c = _cache(tmp_path)
    base = 1_786_190_400.0
    c.sample_series(base, imd_supply=IMD_SUPPLY, imd_price_usd=IMD_PRICE_USD)
    c.sample_series(base + 3600.0, imd_supply=None, imd_price_usd=None, parity_pct=None)

    assert c.get_series(SERIES_IMD_SUPPLY) == [[base, IMD_SUPPLY]]
    assert c.get_series(SERIES_IMD_PRICE_USD) == [[base, IMD_PRICE_USD]]
    assert c.get_series(SERIES_PARITY_PCT) == []


def test_parity_series_accepts_a_negative_spread(tmp_path):
    c = _cache(tmp_path)
    c.sample_series(1_786_190_400.0, parity_pct=PARITY_PCT)
    assert c.get_series(SERIES_PARITY_PCT) == [[1_786_190_400.0, PARITY_PCT]]


def test_non_finite_and_unparsable_samples_are_dropped(tmp_path):
    c = _cache(tmp_path)
    c.sample_series(1_786_190_400.0, imd_supply=float("nan"))
    c.sample_series(1_786_190_400.0, imd_price_usd=float("inf"))
    c.sample_series(1_786_190_400.0, parity_pct="cheap")     # type: ignore[arg-type]
    assert all(c.get_series(name) == [] for name in SERIES_NAMES)


def test_series_are_bounded_at_seven_days(tmp_path):
    c = _cache(tmp_path)
    base = 1_700_000_000.0
    for hour in range(200):
        c.sample_series(base + hour * 3600.0, imd_price_usd=0.7 + hour)
    series = c.get_series(SERIES_IMD_PRICE_USD)
    assert len(series) == 168
    assert series[-1][1] == 0.7 + 199
```

- [ ] **Run it and watch it fail.**
      `.venv/bin/python -m pytest tests/data/test_surf_cache.py -v`
      → `ImportError: cannot import name 'SERIES_IMD_PRICE_USD'`.

- [ ] **Minimal implementation.** Add the series constants after the slot block and the
      two methods to `SurfCache`:

```python
# ---------------------------------------------------------------------------
# Hourly series (7 days deep)
# ---------------------------------------------------------------------------

SERIES_IMD_SUPPLY = "imd_supply"
SERIES_IMD_PRICE_USD = "imd_price_usd"
SERIES_PARITY_PCT = "parity_pct"

SERIES_NAMES: tuple[str, ...] = (
    SERIES_IMD_SUPPLY,
    SERIES_IMD_PRICE_USD,
    SERIES_PARITY_PCT,
)

#: Parity is a *spread* (IMD vs FP) and is legitimately below zero — the live
#: capture is -2.75%. Supply and price cannot be, and a negative one is corruption.
SERIES_ALLOW_NEGATIVE: dict[str, bool] = {
    SERIES_IMD_SUPPLY: False,
    SERIES_IMD_PRICE_USD: False,
    SERIES_PARITY_PCT: True,
}


def _hour_bucket(ts: float) -> float:
    return float(int(ts // 3600) * 3600)
```

In `__init__`:

```python
        self.series: dict[str, deque[tuple[float, float]]] = {
            name: deque(maxlen=_HISTORY_HOURS) for name in SERIES_NAMES
        }
```

Methods:

```python
    # -- series --------------------------------------------------------------

    def _bucket_into(self, name: str, now_ts: float, value: Any) -> None:
        try:
            val = float(value)
        except (TypeError, ValueError):
            return
        if not math.isfinite(val):
            return
        if val < 0 and not SERIES_ALLOW_NEGATIVE.get(name, False):
            return
        deq = self.series.get(name)
        if deq is None:
            return
        bucket = _hour_bucket(float(now_ts))
        if deq and deq[-1][0] == bucket:
            deq[-1] = (bucket, val)
        else:
            deq.append((bucket, val))

    def sample_series(
        self,
        now_ts: float,
        *,
        imd_supply: float | None = None,
        imd_price_usd: float | None = None,
        parity_pct: float | None = None,
    ) -> None:
        """Bucket this cycle's values. ``None`` leaves the series untouched.

        A dead source must never write a sentinel into a history series
        (CLAUDE.md): the zero would be persisted and outlive the outage.
        """
        if imd_supply is not None:
            self._bucket_into(SERIES_IMD_SUPPLY, now_ts, imd_supply)
        if imd_price_usd is not None:
            self._bucket_into(SERIES_IMD_PRICE_USD, now_ts, imd_price_usd)
        if parity_pct is not None:
            self._bucket_into(SERIES_PARITY_PCT, now_ts, parity_pct)

    def get_series(self, name: str) -> list[list[float]]:
        """``[[hour_ts, value], ...]`` oldest first — the sparkline shape."""
        deq = self.series.get(name)
        if not deq:
            return []
        return [[float(ts), float(v)] for (ts, v) in deq]
```

Extend `__all__` with the four series names.

- [ ] **Run to green.** `.venv/bin/python -m pytest tests/data/test_surf_cache.py -v`
      → 14 passed.

- [ ] **Commit.**
```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/data/surf_cache.py tests/data/test_surf_cache.py && git commit -m "feat(surf): hour-bucketed supply/price/parity series, None never zero"
```

---

### Task WP4.4: Signal baselines, including the FIRED timestamps

**Files:**
- Modify: `/Library/Vibes/autopull/maxpane_dashboard/data/surf_cache.py`
- Test: `/Library/Vibes/autopull/tests/data/test_surf_cache.py`

**Interfaces:**
- Produces: `SurfCache.get_baselines() -> dict`, `.set_baselines(baselines: Mapping) -> None`,
  `BASELINE_FIRED_KEY = "fired"`, `BASELINE_LIST_CAP = 64`, `BASELINE_DETAIL_CAP = 200`.

> The cache stores whatever `build_signals` hands back as `advanced_baselines`; it
> deliberately does **not** know the signal schema (that would couple `data/` to
> `analytics/` and break the purity guardrail in Task WP4.6). It only sanitises to
> JSON-safe scalars, one level of nesting, plus the `fired` map of
> `signal name -> {"ts": float, "detail": str}`. It also never imports `FIRED_TTL_S`:
> relaxing a 24 h-old FIRED to `OK` is `build_signals`' decision, and dropping the
> timestamp here would *lose* the `last: …` detail the PRD §3 requires.
>
> **The key and the shape are WP2's, not WP4's, and the earlier draft got both wrong.**
> `build_signals` writes `advanced["fired"] = {name: {"ts": float, "detail": str}}` and
> reads it back through `_fired_store(baselines)` (wp2.md). This task previously froze
> `BASELINE_FIRED_KEY = "fired_at"` holding a bare `{signal: float}`, so
> `set_baselines(advanced)` routed the real store down the *generic scalar* branch,
> `_scalar({...})` returned `_DROP`, and the whole FIRED map was discarded on **every
> cycle** — silently, because nothing in either package compares the two spellings.
> PRD §3's "a restart does not resurrect or lose a FIRED display" simply never worked,
> and WP4.11's restart test was red for a reason that had nothing to do with signals.
> The cache still does not know *which* signals exist (that stays WP2's), only that the
> value under this one key is a two-field mapping per name.

- [ ] **Write the failing test.** Append to `tests/data/test_surf_cache.py`:

```python
from maxpane_dashboard.data.surf_cache import (   # noqa: E402
    BASELINE_DETAIL_CAP,
    BASELINE_FIRED_KEY,
)


def _baselines() -> dict:
    """The shape build_signals returns, using live values from the captures."""
    return {
        "announce_nonce": 14,             # eth_getTransactionCount(ANNOUNCE)
        "dev_nonce": 2350,
        "ops_nonce": 29,
        "lp_liquidity": 1234567890123456789,
        "gate_open": False,               # gate closed since 2026-05-14
        # WP2's spelling (BASELINE_SCALARS), not a paraphrase: the cache is
        # schema-agnostic, so a wrong key here round-trips green and only shows
        # up as a detector that never fires. Task WP4.11 has the same rule.
        "identities_written": 1,          # 1/2000 written
        "imd_supply": IMD_SUPPLY,
        "channel_tx_count": 21,           # posts AND replies, against nonce 14
        "hook_live": False,               # v4 hook not deployed
        "bridge_last_block": 25_707_780,
        # WP2's shape, verbatim: {signal: {"ts": float, "detail": str}}. The
        # details are the real ones build_signals renders — the nonce-13 post
        # and the 2026-07-31 burn.
        BASELINE_FIRED_KEY: {
            "post": {"ts": 1_786_076_831.0, "detail": '#13 "as always 0 promises."'},
            "burn": {"ts": 1_785_903_575.0, "detail": "31,064 IMD → BurnExecutor"},
        },
    }


def test_baselines_round_trip_in_memory(tmp_path):
    c = _cache(tmp_path)
    assert c.get_baselines() == {}
    c.set_baselines(_baselines())
    assert c.get_baselines() == _baselines()


def test_get_baselines_hands_out_a_copy_not_the_live_dict(tmp_path):
    """A caller mutating what it got must not silently advance a baseline.

    The FIRED store is two levels deep, so a one-level ``dict(...)`` is not a
    copy: the per-signal ``{"ts", "detail"}`` dicts would still be shared, and a
    caller editing a detail would rewrite what the next restart renders.
    """
    c = _cache(tmp_path)
    c.set_baselines(_baselines())
    got = c.get_baselines()
    got["announce_nonce"] = 99
    got[BASELINE_FIRED_KEY]["post"]["ts"] = 0.0
    got[BASELINE_FIRED_KEY]["post"]["detail"] = "tampered"
    assert c.get_baselines()["announce_nonce"] == 14
    assert c.get_baselines()[BASELINE_FIRED_KEY]["post"] == {
        "ts": 1_786_076_831.0,
        "detail": '#13 "as always 0 promises."',
    }


def test_unusable_baseline_values_are_dropped_not_coerced(tmp_path):
    c = _cache(tmp_path)
    c.set_baselines(
        {
            "announce_nonce": 14,
            "imd_supply": float("nan"),
            "junk": object(),
            "nested": {"too": {"deep": 1}},
            BASELINE_FIRED_KEY: {
                "post": {"ts": "yesterday", "detail": "x"},   # unparsable stamp
                "lp": {"ts": float("inf"), "detail": "x"},
                "burn": {"ts": -1.0, "detail": "x"},          # non-positive
                "gate": 1_786_076_831.0,                      # the OLD flat shape
            },
        }
    )
    got = c.get_baselines()
    assert got["announce_nonce"] == 14
    assert "imd_supply" not in got          # NaN is not a supply
    assert "junk" not in got
    assert "nested" not in got
    assert got[BASELINE_FIRED_KEY] == {}    # every fired entry was unusable


def test_a_fired_detail_is_coerced_to_text_and_bounded(tmp_path):
    """``detail`` is what a restart re-renders, so it must survive as text.

    It is third-party-influenced (a post body reaches it through WP2), so it is
    stored as a plain string and bounded — but bounded generously: WP2's
    ``DETAIL_LIMIT`` (48) caps the *message body*, and the rendered line adds a
    label and quotes around it. A tight cap here would silently rewrite the
    line the user sees after a restart.
    """
    clock = FakeClock()
    c = _cache(tmp_path, clock)
    c.set_baselines(
        {
            BASELINE_FIRED_KEY: {
                "post": {"ts": clock.t - 60.0, "detail": "x" * (BASELINE_DETAIL_CAP + 50)},
                "lp": {"ts": clock.t - 60.0, "detail": None},
                "gate": {"ts": clock.t - 60.0, "detail": 42},
            }
        }
    )
    fired = c.get_baselines()[BASELINE_FIRED_KEY]
    assert len(fired["post"]["detail"]) == BASELINE_DETAIL_CAP
    assert fired["lp"]["detail"] == ""       # a missing detail is empty, not dropped
    assert fired["gate"]["detail"] == "42"   # coerced, never a stray int on disk


def test_a_future_dated_fired_stamp_is_dropped(tmp_path):
    """Clock-skew corruption must not pin a detector at FIRED forever."""
    clock = FakeClock()
    c = _cache(tmp_path, clock)
    c.set_baselines(
        {
            BASELINE_FIRED_KEY: {
                "post": {"ts": clock.t + 86_400.0, "detail": "from the future"},
                "lp": {"ts": clock.t - 60.0, "detail": "LP +33 ETH"},
            }
        }
    )
    assert c.get_baselines()[BASELINE_FIRED_KEY] == {
        "lp": {"ts": clock.t - 60.0, "detail": "LP +33 ETH"}
    }


def test_set_baselines_replaces_wholesale(tmp_path):
    """build_signals returns the complete advanced set; merging would resurrect."""
    c = _cache(tmp_path)
    c.set_baselines(_baselines())
    c.set_baselines({"announce_nonce": 15})
    assert c.get_baselines() == {"announce_nonce": 15}


def test_non_mapping_baselines_are_ignored(tmp_path):
    c = _cache(tmp_path)
    c.set_baselines(_baselines())
    c.set_baselines(None)                   # type: ignore[arg-type]
    assert c.get_baselines() == {}
```

- [ ] **Run it and watch it fail.**
      `.venv/bin/python -m pytest tests/data/test_surf_cache.py -v`
      → `ImportError: cannot import name 'BASELINE_FIRED_KEY'`.

- [ ] **Minimal implementation.** Add the constants and methods:

```python
# ---------------------------------------------------------------------------
# Signal baselines (PRD §3)
# ---------------------------------------------------------------------------

#: Nested map inside the baselines dict: signal name -> ``{"ts": epoch seconds,
#: "detail": the rendered line}`` of its last FIRED. Persisted so a restart
#: neither resurrects nor loses a FIRED display; whether an entry still
#: *renders* FIRED is ``build_signals``' call, not this module's.
#:
#: The spelling is ``build_signals``' own (``advanced["fired"]``). It is not a
#: free choice: this cache is schema-agnostic, so a key that does not match
#: routes the whole store down the generic scalar branch, where a mapping is
#: dropped — the FIRED map would then be silently discarded every cycle.
BASELINE_FIRED_KEY = "fired"

#: Longest list a baseline value may be (seen tx hashes and the like).
BASELINE_LIST_CAP = 64

#: Longest FIRED ``detail`` string kept. Deliberately far above WP2's
#: ``DETAIL_LIMIT`` (48): that one caps the quoted *message body*, while a
#: rendered detail wraps it in a label, quotes and a ``· last: …`` clause. This
#: bound exists to stop an unbounded third-party string reaching the cache
#: file, not to reformat the line a restart re-renders.
BASELINE_DETAIL_CAP = 200
```

In `__init__`: `self._baselines: dict[str, Any] = {}`.

```python
    # -- signal baselines ----------------------------------------------------

    @staticmethod
    def _scalar(value: Any) -> Any:
        """A JSON-safe scalar, or the sentinel ``_DROP`` when unusable."""
        if value is None or isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else _DROP
        return _DROP

    @staticmethod
    def _sanitise_fired(raw: Any, horizon: float) -> dict[str, dict[str, Any]]:
        """The ``{signal: {"ts", "detail"}}`` store, defensively rebuilt.

        Shape kept deliberately narrow — this is the one nested value the cache
        understands, and it understands it because ``build_signals`` writes it
        and reads it back. Anything that is not a two-field mapping with a
        usable stamp is **dropped**, never repaired: a resurrected FIRED is a
        false alarm and a coerced one is a lie about when it happened. Entries
        in the pre-repair flat shape (``{signal: float}``) land here too and are
        dropped by the same rule, which is the honest outcome — a stamp with no
        detail would restore as a FIRED row quoting nothing.
        """
        fired: dict[str, dict[str, Any]] = {}
        if not isinstance(raw, Mapping):
            return fired
        for sig, entry in raw.items():
            if not isinstance(entry, Mapping):
                logger.debug("Dropping malformed SURF fired entry %r", sig)
                continue
            try:
                stamp = float(entry.get("ts"))      # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            # A future-dated stamp is clock-skew corruption; keeping it would
            # pin the detector at FIRED forever.
            if not math.isfinite(stamp) or not 0.0 < stamp <= horizon:
                continue
            detail = entry.get("detail")
            text = "" if detail is None else str(detail)
            fired[str(sig)] = {"ts": stamp, "detail": text[:BASELINE_DETAIL_CAP]}
        return fired

    def _sanitise_baselines(self, raw: Any, now: float) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            logger.debug("Ignoring non-mapping SURF baselines: %r", type(raw).__name__)
            return {}
        out: dict[str, Any] = {}
        horizon = now + CLOCK_SKEW_TOLERANCE_SECONDS
        for key, value in raw.items():
            name = str(key)
            if name == BASELINE_FIRED_KEY:
                out[name] = self._sanitise_fired(value, horizon)
                continue
            if isinstance(value, (list, tuple)):
                items = [self._scalar(v) for v in list(value)[:BASELINE_LIST_CAP]]
                out[name] = [v for v in items if v is not _DROP]
                continue
            scalar = self._scalar(value)
            if scalar is _DROP:
                logger.debug("Dropping unusable SURF baseline %s=%r", name, value)
                continue
            out[name] = scalar
        return out

    def get_baselines(self) -> dict[str, Any]:
        """A **copy** of the persisted baselines, safe for a caller to mutate.

        The FIRED store is two levels deep, so the inner ``{"ts", "detail"}``
        dicts are copied too — a shallow copy would hand out live references and
        a caller editing a detail would rewrite what the next restart renders.
        """
        out = dict(self._baselines)
        fired = out.get(BASELINE_FIRED_KEY)
        if isinstance(fired, dict):
            out[BASELINE_FIRED_KEY] = {
                name: (dict(entry) if isinstance(entry, dict) else entry)
                for name, entry in fired.items()
            }
        return out

    def set_baselines(self, baselines: Mapping[str, Any], *, now: float | None = None) -> None:
        """Replace the baselines wholesale with ``build_signals``' advanced set.

        Wholesale, never merged: ``build_signals`` returns the *complete* advanced
        set, so merging would let a key it deliberately dropped come back.
        """
        self._baselines = self._sanitise_baselines(baselines, self._now(now))
```

Add the module-level sentinel next to `_jsonable`:

```python
class _Drop:
    """Sentinel: this value is not usable and must be dropped, never coerced."""

    __slots__ = ()

    def __repr__(self) -> str:      # pragma: no cover - debugging aid
        return "<drop>"


_DROP = _Drop()
```

Extend `__all__` with `"BASELINE_DETAIL_CAP"`, `"BASELINE_FIRED_KEY"`, `"BASELINE_LIST_CAP"`.

- [ ] **Prove the key spelling bites.** Set `BASELINE_FIRED_KEY = "fired_at"` (the
      pre-repair value) and re-run
      `.venv/bin/python -m pytest tests/data/test_surf_cache.py -k fired -v` →
      `test_a_future_dated_fired_stamp_is_dropped` and
      `test_a_fired_detail_is_coerced_to_text_and_bounded` fail, because the store now
      goes down the generic scalar branch and `_scalar({...})` drops it. That is exactly
      what `set_baselines(build_signals(...)[1])` did in production while every test
      stayed green. Restore `"fired"`.

- [ ] **Run to green.** `.venv/bin/python -m pytest tests/data/test_surf_cache.py -v`
      → 21 passed.

- [ ] **Commit.**
```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/data/surf_cache.py tests/data/test_surf_cache.py && git commit -m "feat(surf): persistable signal baselines with sanitised FIRED stamps"
```

---

### Task WP4.5: The observed-burn accumulator — successful reads only

**Files:**
- Modify: `/Library/Vibes/autopull/maxpane_dashboard/data/surf_cache.py`
- Test: `/Library/Vibes/autopull/tests/data/test_surf_cache.py`

**Interfaces:**
- Produces: `SurfCache.record_supply(supply: float | None) -> float | None` (returns the
  burn delta observed this call, `0.0` for no change, `None` when nothing could be
  concluded), `.observed_burn_total() -> float | None`, `.last_supply -> float | None`.

> `imd_burned_cum` is **burned since first observation**, not an all-time figure —
> there is no keyless source for the latter (the Base burn receiver was never resolved,
> `surf_game_mechanics.md` §Open questions). It reads `None` until the first successful
> supply read, so a fresh install with a dead RPC never claims "0 burned" as a fact.
>
> **The three states are not interchangeable, and they are a rendering contract, not an
> implementation detail:**
>
> | value | meaning | required rendering |
> |---|---|---|
> | `None` | no successful supply read yet, or the read failed | unavailable (dash) |
> | `0.0` | we have watched; nothing moved *in the observation window* | words, e.g. `no burn observed yet` |
> | `> 0` | the burn this install actually saw | the quantity, labelled `observed` |
>
> `0.0` is the dangerous one. One healthy supply read makes it `0.0` within a single refresh,
> and PRD §1 records ~58,849 IMD burned across three events (05-16, 07-31, 08-05) that predate
> every install — so a widget printing `burned 0 cum` beside a live supply states something
> false about the token. The consuming widget (WP3.2 `SurfHero`) owns that copy and pins it;
> WP4's obligation is to keep the accumulator honest and to never seed it with a documented
> historical number (CLAUDE.md: *read values live; never hardcode a documented one*). If a
> keyless all-time source is ever found, that is a contract change to raise with the plan
> owner — WP4, WP3 and WP0's `SURF_KEYS` comment change together or not at all.

- [ ] **Write the failing test.** Append to `tests/data/test_surf_cache.py`:

```python
def test_observed_burn_total_is_none_before_any_read_then_zero(tmp_path):
    """The three states the widget branches on, pinned at the source.

    ``None`` and ``0.0`` are different claims and the difference is the whole
    point: ``None`` is "we have never successfully read totalSupply", ``0.0``
    is "we have, and nothing has moved *since*".  Neither is "no IMD has ever
    been burned" -- ~58,849 IMD were burned before any install existed (PRD
    §1) and this accumulator structurally cannot see them.  WP3.2's SurfHero
    renders ``0.0`` as words for exactly that reason.
    """
    c = _cache(tmp_path)
    assert c.observed_burn_total() is None
    assert c.record_supply(IMD_SUPPLY) is None          # first read: no conclusion
    assert c.observed_burn_total() == 0.0               # observed nothing, honestly
    # A *delta* still needs a second successful read; one read concludes nothing.
    assert c.record_supply(IMD_SUPPLY) == 0.0
    assert c.observed_burn_total() == 0.0


def test_a_real_burn_is_accumulated(tmp_path):
    """The 2026-08-05 event: 15,745 IMD, announced to the minute."""
    c = _cache(tmp_path)
    c.record_supply(IMD_SUPPLY)
    delta = c.record_supply(IMD_SUPPLY - 15_745.0)
    assert delta == pytest.approx(15_745.0)
    assert c.observed_burn_total() == pytest.approx(15_745.0)

    # A later burn adds; the total is cumulative, never a replacement.
    c.record_supply(IMD_SUPPLY - 15_745.0 - 31_064.0)
    assert c.observed_burn_total() == pytest.approx(46_809.0)


def test_a_failed_supply_read_can_never_produce_a_burn(tmp_path):
    """The regression this whole module exists for: None is not 0 (PRD §6.1)."""
    c = _cache(tmp_path)
    c.record_supply(IMD_SUPPLY)
    assert c.record_supply(None) is None                # outage
    assert c.observed_burn_total() == 0.0               # no 2.37M "burn"
    assert c.last_supply == IMD_SUPPLY                  # baseline untouched

    # Recovery compares against the pre-outage baseline, not against None.
    assert c.record_supply(IMD_SUPPLY) == 0.0
    assert c.observed_burn_total() == 0.0


def test_a_supply_increase_is_a_bridge_in_not_a_negative_burn(tmp_path):
    c = _cache(tmp_path)
    c.record_supply(IMD_SUPPLY)
    assert c.record_supply(IMD_SUPPLY + 1_000.0) == 0.0
    assert c.observed_burn_total() == 0.0
    assert c.last_supply == IMD_SUPPLY + 1_000.0


def test_a_non_finite_supply_is_not_a_reading(tmp_path):
    c = _cache(tmp_path)
    c.record_supply(IMD_SUPPLY)
    assert c.record_supply(float("nan")) is None
    assert c.last_supply == IMD_SUPPLY
```

- [ ] **Run it and watch it fail.**
      `.venv/bin/python -m pytest tests/data/test_surf_cache.py -k burn -v`
      → `AttributeError: 'SurfCache' object has no attribute 'record_supply'`.

- [ ] **Minimal implementation.** In `__init__`: `self.last_supply: float | None = None`
      and `self.burned_cum: float = 0.0`. Then:

```python
    # -- observed burns ------------------------------------------------------

    def record_supply(self, supply: float | None) -> float | None:
        """Fold one ``totalSupply`` reading in. Returns the burn observed, if any.

        ``None`` in -> ``None`` out and **no state change**: a failed read must be
        incapable of producing a BURN (PRD §6.1). The first successful read only
        establishes the baseline, so it also concludes nothing.
        """
        if supply is None or isinstance(supply, bool):
            return None
        try:
            value = float(supply)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or value < 0:
            return None

        previous = self.last_supply
        self.last_supply = value
        if previous is None:
            return None
        if value < previous:
            delta = previous - value
            self.burned_cum += delta
            return delta
        # An increase is an OFT bridge-in, not a negative burn.
        return 0.0

    def observed_burn_total(self) -> float | None:
        """Cumulative burn *since first observation*, or ``None`` if never read.

        Not an all-time total and not obtainable as one: the burns predating
        this cache (~58,849 IMD across 2026-05-16 / 07-31 / 08-05) have no
        keyless source.  ``0.0`` therefore means "nothing observed in the
        window", never "nothing was ever burned" -- consumers must render the
        two differently (see WP3.2 ``SurfHero._update_supply``).
        """
        if self.last_supply is None:
            return None
        return float(self.burned_cum)
```

- [ ] **Prove the test bites.** Change `if supply is None or isinstance(supply, bool):`
      to `supply = supply or 0.0` and re-run
      `.venv/bin/python -m pytest tests/data/test_surf_cache.py -k burn -v` →
      `test_a_failed_supply_read_can_never_produce_a_burn` fails with
      `assert 2376731.868679 == 0.0`. Restore the guard and re-run to green.

- [ ] **Run to green.** `.venv/bin/python -m pytest tests/data/test_surf_cache.py -v`
      → 26 passed.

- [ ] **Commit.**
```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/data/surf_cache.py tests/data/test_surf_cache.py && git commit -m "feat(surf): observed-burn accumulator that a failed read cannot move"
```

---

### Task WP4.6: Persistence — `save()`, `load(now=)`, and a null-poisoned series file

**Files:**
- Modify: `/Library/Vibes/autopull/maxpane_dashboard/data/surf_cache.py`
- Test: `/Library/Vibes/autopull/tests/data/test_surf_cache.py`

**Interfaces:**
- Produces: `SurfCache.save(path: str | None = None) -> None`,
  `SurfCache.load(path: str | None = None, *, now: float | None = None) -> None`.
  Both are fail-soft and never raise. Nothing about the tier marks is persisted —
  every tier is due immediately after a restart.

- [ ] **Write the failing test.** Append to `tests/data/test_surf_cache.py`:

```python
# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

HOSTILE = [
    [1_786_100_000.0, 0.71],       # good
    [1_786_103_600.0, None],       # the reported crash: a null in the file
    "not a point",
    # A **non-numeric** string, matching `tests/data/test_cache_corruption.py`'s
    # own hostile fixture. `"0.72"` would be the wrong choice and it is the one
    # this fixture used to carry: `coerce_point` does `float(pt[1])` inside a
    # `except (TypeError, ValueError)`, so `float("0.72")` *succeeds* and the
    # point survives — three points back, not two, and the assertion below fails
    # for a reason that looks like a validator bug. It is not one. Do **not**
    # "fix" `data/series_points.py` to reject numeric strings: it is a leaf
    # shared by all eight dashboards, no surf work package owns it, and
    # tightening it is a repo-wide change to report to the plan owner.
    [1_786_107_200.0, "banana"],   # a string that is not a number
    [1_786_110_800.0, float("nan")],
    [0, 0.73],                     # non-positive timestamp
    [1_786_114_400.0, 0.74],       # good
]
GOOD = [[1_786_100_000.0, 0.71], [1_786_114_400.0, 0.74]]


def test_round_trip_restores_everything_that_matters(tmp_path):
    clock = FakeClock()
    path = str(tmp_path / "surf_cache.json")
    c = SurfCache(path=path, clock=clock)

    c.store_last_good(SLOT_MARKET, {"imd_price_usd": IMD_PRICE_USD})
    c.sample_series(clock.t, imd_supply=IMD_SUPPLY, imd_price_usd=IMD_PRICE_USD,
                    parity_pct=PARITY_PCT)
    c.set_baselines(_baselines())
    c.record_supply(IMD_SUPPLY)
    c.record_supply(IMD_SUPPLY - 15_745.0)
    c.save()

    restored = SurfCache(path=path, clock=clock)
    restored.load()

    assert restored.get_last_good(SLOT_MARKET).payload == {"imd_price_usd": IMD_PRICE_USD}
    assert restored.get_last_good(SLOT_MARKET).ts == clock.t
    assert restored.get_series(SERIES_IMD_SUPPLY) == c.get_series(SERIES_IMD_SUPPLY)
    assert restored.get_series(SERIES_PARITY_PCT) == [[_bucket(clock.t), PARITY_PCT]]
    assert restored.get_baselines() == _baselines()
    assert restored.observed_burn_total() == pytest.approx(15_745.0)
    assert restored.last_supply == pytest.approx(IMD_SUPPLY - 15_745.0)


def _bucket(ts: float) -> float:
    return float(int(ts // 3600) * 3600)


def test_a_restart_neither_resurrects_nor_loses_a_fired_stamp(tmp_path):
    """PRD §3: the FIRED display must survive a restart with its real age.

    Both halves of the entry have to survive: the ``ts`` is what dates the row
    (``age_s``, and whether ``FIRED_TTL_S`` has passed) and the ``detail`` is
    what the relaxed ``last: …`` clause quotes. Losing either turns a persisted
    FIRED into a blank one.
    """
    clock = FakeClock()
    path = str(tmp_path / "surf_cache.json")
    fired_at = clock.t - 7_200.0             # fired two hours ago

    c = SurfCache(path=path, clock=clock)
    c.set_baselines(
        {
            "announce_nonce": 14,
            BASELINE_FIRED_KEY: {"post": {"ts": fired_at, "detail": '#14 "soon"'}},
        }
    )
    c.save()

    restored = SurfCache(path=path, clock=clock)
    restored.load()
    assert restored.get_baselines()[BASELINE_FIRED_KEY]["post"] == {
        "ts": fired_at,
        "detail": '#14 "soon"',
    }
    # And the *nonce* baseline came back too, so the signal cannot re-fire on
    # the same post.
    assert restored.get_baselines()["announce_nonce"] == 14


def test_every_tier_is_due_again_after_a_restart(tmp_path):
    clock = FakeClock()
    path = str(tmp_path / "surf_cache.json")
    c = SurfCache(path=path, clock=clock)
    for tier in TIERS:
        c.mark_fetched(tier)
    c.save()

    restored = SurfCache(path=path, clock=clock)
    restored.load()
    assert set(restored.tiers_due()) == set(TIERS)


def test_a_null_poisoned_series_costs_only_that_point(tmp_path, caplog):
    """One null used to abort startup for *every* dashboard."""
    path = tmp_path / "surf_cache.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "series": {
                    SERIES_IMD_PRICE_USD: HOSTILE,
                    SERIES_PARITY_PCT: [[1_786_100_000.0, -2.7495188342040167]],
                },
            }
        )
    )
    c = SurfCache(path=str(path), clock=FakeClock())
    with caplog.at_level("WARNING"):
        c.load()                                     # must not raise

    assert c.get_series(SERIES_IMD_PRICE_USD) == GOOD
    assert c.get_series(SERIES_PARITY_PCT) == [[1_786_100_000.0, -2.7495188342040167]]
    assert "Skipped" in caplog.text


def test_a_negative_parity_point_survives_but_a_negative_price_does_not(tmp_path):
    path = tmp_path / "surf_cache.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "series": {
                    SERIES_PARITY_PCT: [[1_786_100_000.0, -2.75]],
                    SERIES_IMD_PRICE_USD: [[1_786_100_000.0, -0.71]],
                },
            }
        )
    )
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c.get_series(SERIES_PARITY_PCT) == [[1_786_100_000.0, -2.75]]
    assert c.get_series(SERIES_IMD_PRICE_USD) == []


def test_corrupt_missing_and_hostile_files_load_empty_not_raise(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json at all")
    SurfCache(path=str(bad), clock=FakeClock()).load()          # no raise

    SurfCache(path=str(tmp_path / "nope.json"), clock=FakeClock()).load()

    listy = tmp_path / "list.json"
    listy.write_text("[1, 2, 3]")
    c = SurfCache(path=str(listy), clock=FakeClock())
    c.load()
    assert c.get_baselines() == {}
    assert c.get_last_good(SLOT_CHAIN) is None


def test_one_bad_section_never_costs_the_others(tmp_path):
    path = tmp_path / "surf_cache.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "last_good": "not a mapping",
                "baselines": {"announce_nonce": 14},
                "series": {SERIES_IMD_SUPPLY: [[1_786_100_000.0, IMD_SUPPLY]]},
                "burned_cum": "lots",
                "last_supply": IMD_SUPPLY,
            }
        )
    )
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    # No `fired` key: `_sanitise_baselines` emits one only when the input had
    # one, and this file's `baselines` section does not. Seeding it
    # unconditionally would be the wrong repair — `test_set_baselines_replaces_wholesale`
    # asserts `{"announce_nonce": 15}` exactly, and a manufactured empty `fired`
    # would also claim a store the file never held.
    assert c.get_baselines() == {"announce_nonce": 14}
    assert c.get_series(SERIES_IMD_SUPPLY) == [[1_786_100_000.0, IMD_SUPPLY]]
    assert c.burned_cum == 0.0
    assert c.last_supply == pytest.approx(IMD_SUPPLY)


def test_save_creates_its_directory_is_atomic_and_never_raises(tmp_path):
    nested = tmp_path / "deep" / "surf_cache.json"
    c = SurfCache(path=str(nested), clock=FakeClock())
    c.set_baselines({"announce_nonce": 14})
    c.save()
    assert nested.exists()
    assert not (tmp_path / "deep" / "surf_cache.json.tmp").exists()
    json.loads(nested.read_text())

    SurfCache(path="/proc/definitely/not/writable.json", clock=FakeClock()).save()


def test_a_non_finite_value_is_nulled_on_the_way_to_disk_never_fabricated(tmp_path):
    path = tmp_path / "surf_cache.json"
    c = SurfCache(path=str(path), clock=FakeClock())
    c.store_last_good(SLOT_CHAIN, {"imd_supply": float("inf"), "block": 25_707_780})
    c.save()
    payload = json.loads(path.read_text())
    assert payload["last_good"][SLOT_CHAIN]["payload"] == {
        "imd_supply": None,
        "block": 25_707_780,
    }


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


def test_the_cache_imports_no_client_no_analytics_no_network():
    from pathlib import Path as _Path

    import maxpane_dashboard.data.surf_cache as mod

    src = _Path(mod.__file__).read_text()
    project_imports = [
        line.strip()
        for line in src.splitlines()
        if line.strip().startswith(("import maxpane", "from maxpane"))
    ]
    assert project_imports == [
        "from maxpane_dashboard.data.series_points import (",
    ]
    for banned in ("requests", "httpx", "aiohttp", "urllib", "socket",
                   "surf_client", "surf_signals", "surf_manager", "textual"):
        assert f"import {banned}" not in src
    # It must not know the FIRED window: relaxing a FIRED is build_signals' call.
    assert "FIRED_TTL_S" not in src
```

- [ ] **Run it and watch it fail.**
      `.venv/bin/python -m pytest tests/data/test_surf_cache.py -v`
      → `AttributeError: 'SurfCache' object has no attribute 'save'`.

- [ ] **Minimal implementation.** Append to `SurfCache`:

```python
    # -- persistence ---------------------------------------------------------

    def save(self, path: str | None = None) -> None:
        """Persist to disk via atomic temp-then-rename. Never raises.

        The tier marks are deliberately **not** persisted: after a restart every
        tier is due, because the chain moved while the process was down and the
        announce nonce is the one number the dashboard exists to be early on.
        """
        target = str(path or self.path)
        payload: dict[str, Any] = {
            "version": _SCHEMA_VERSION,
            "saved_at": self._now(),
            "last_good": {
                slot: entry.to_dict() for slot, entry in self.last_good.items()
            },
            "series": {
                name: [[float(ts), float(v)] for (ts, v) in deq]
                for name, deq in self.series.items()
            },
            "baselines": _jsonable(self._baselines),
            "burned_cum": float(self.burned_cum),
            "last_supply": None if self.last_supply is None else float(self.last_supply),
        }
        tmp = target + ".tmp"
        try:
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(tmp, "w") as handle:
                json.dump(payload, handle)
            os.replace(tmp, target)
            logger.info(
                "SURF cache saved to %s (%d last-good slots, burned %.0f observed)",
                target,
                len(self.last_good),
                self.burned_cum,
            )
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Failed to save the SURF cache: %s", exc)
            try:
                os.remove(tmp)
            except OSError:
                pass

    def load(self, path: str | None = None, *, now: float | None = None) -> None:
        """Restore saved state. Silent no-op on a missing or corrupt file.

        Per-section ``try``/``except``: one bad block never costs the others, and
        nothing here raises into the manager's constructor. Series points are
        validated one at a time, so a single ``null`` costs that sample rather
        than every dashboard's startup.
        """
        target = str(path or self.path)
        try:
            with open(target) as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.info("No SURF cache to load (%s): %s", target, exc)
            return
        if not isinstance(payload, dict):
            logger.warning("SURF cache %s has an unexpected shape, skipping", target)
            return

        reference = self._now(now)

        try:
            for slot, data in (payload.get("last_good") or {}).items():
                if slot not in SLOTS or not isinstance(data, dict):
                    continue
                try:
                    self.last_good[str(slot)] = LastGood.from_dict(data)
                except Exception as exc:            # noqa: BLE001
                    logger.debug("Skipping bad SURF last-good slot %s: %s", slot, exc)
        except Exception as exc:                    # noqa: BLE001
            logger.warning("SURF last_good block bad: %s", exc)

        try:
            skipped = 0
            for name, points in (payload.get("series") or {}).items():
                deq = self.series.get(str(name))
                if deq is None:
                    continue
                good, dropped = coerce_points(
                    points,
                    now=reference,
                    allow_negative=SERIES_ALLOW_NEGATIVE.get(str(name), False),
                )
                skipped += dropped
                deq.clear()
                deq.extend(good)
            if skipped:
                logger.warning(
                    "Skipped %d unusable point(s) while loading the SURF cache %s",
                    skipped,
                    target,
                )
        except Exception as exc:                    # noqa: BLE001
            logger.warning("SURF series block bad: %s", exc)

        try:
            self._baselines = self._sanitise_baselines(
                payload.get("baselines"), reference
            )
        except Exception as exc:                    # noqa: BLE001
            logger.warning("SURF baselines block bad: %s", exc)
            self._baselines = {}

        try:
            burned = float(payload.get("burned_cum") or 0.0)
            self.burned_cum = burned if math.isfinite(burned) and burned >= 0 else 0.0
        except (TypeError, ValueError):
            self.burned_cum = 0.0

        try:
            supply = payload.get("last_supply")
            value = None if supply is None else float(supply)
            self.last_supply = (
                value if value is not None and math.isfinite(value) and value >= 0
                else None
            )
        except (TypeError, ValueError):
            self.last_supply = None

        logger.info(
            "Loaded the SURF cache from %s: %d last-good slots, %d baselines",
            target,
            len(self.last_good),
            len(self._baselines),
        )
```

- [ ] **Prove the test bites.** Replace the `coerce_points(...)` call with
      `[(float(p[0]), float(p[1])) for p in points]` and re-run
      `.venv/bin/python -m pytest tests/data/test_surf_cache.py -k null_poisoned -v` →
      it fails with `TypeError: float() argument must be a string or a real number, not
      'NoneType'` escaping `load()` — the original repro. Restore `coerce_points`.

- [ ] **Run to green.** `.venv/bin/python -m pytest tests/data/test_surf_cache.py -v`
      → 36 passed.

- [ ] **Commit.**
```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/data/surf_cache.py tests/data/test_surf_cache.py && git commit -m "feat(surf): fail-soft cache persistence with per-point series validation"
```

---

### Task WP4.7: Manager scaffolding — one cycle returns exactly `SURF_KEYS`

**Files:**
- Create: `/Library/Vibes/autopull/maxpane_dashboard/data/surf_manager.py`
- Test: `/Library/Vibes/autopull/tests/data/test_surf_manager.py`

**Interfaces:**
- Consumes: `SURF_KEYS`; `SurfCache`; `SurfClient.close()`.
- Produces: `SOURCE_CHAIN/CHANNEL/MARKET/LOGS/NFT/ACTIVITY: str`, `SOURCES: tuple[str, ...]`,
  `FEED_ITEM_LIMIT = 25`, `DEV_ACTIVITY_LIMIT = 25`, `NFT_SALES_LIMIT = 8`;
  `SurfManager(poll_interval: int = 30, *, clock=time.time, cache_path=DEFAULT_CACHE_PATH, client=None, cache=None)`,
  `async SurfManager.fetch_and_compute() -> dict[str, Any]`, `async .close() -> None`,
  `.save_cache() -> None`.

- [ ] **Write the failing test.** Create `tests/data/test_surf_manager.py`:

```python
"""WP4 — orchestration, tiering and degradation tests for :class:`SurfManager`.

Zero network: the client is a double whose transport raises on use, the clock is
a fake, and persistence points at ``tmp_path``. Nothing here sleeps.

The centre of gravity is degradation, because that is the deliverable: the
manager must return exactly ``SURF_KEYS`` under every combination of source
failures, must never let an exception escape, and — the correctness rule the
whole PRD hangs on — must never let a failed read move a baseline.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.data.surf_cache import (
    SERIES_IMD_PRICE_USD,
    SERIES_IMD_SUPPLY,
    SLOT_CHANNEL,
    SurfCache,
)
from maxpane_dashboard.data.surf_manager import (
    SOURCES,
    SOURCE_ACTIVITY,
    SOURCE_CHAIN,
    SOURCE_CHANNEL,
    SOURCE_LOGS,
    SOURCE_MARKET,
    SOURCE_NFT,
    SurfManager,
)
from maxpane_dashboard.data.surf_models import (
    SURF_KEYS,
    ChainState,
    ChannelTx,
    DevTx,
    LogWindow,
    MarketSnapshot,
    NftStats,
    NonceSet,
)
from maxpane_dashboard.data.surf_addresses import (
    ANNOUNCE,
    BURN_EXECUTOR,
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


def _word(value: int) -> str:
    return f"{value & (2**256 - 1):064x}"


def _addr_word(addr: str) -> str:
    return addr[2:].lower().rjust(64, "0")


def _mint_log(to_addr: str, amount_wei: int, *, ts: float, tx: str) -> dict:
    """A raw ``Transfer(0x0 -> dev wallet)`` log, exactly as WP1 passes it through."""
    return {
        "address": "0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7".lower(),
        "topics": [TOPIC_TRANSFER, "0x" + "0" * 64, "0x" + _addr_word(to_addr)],
        "data": "0x" + _word(amount_wei),
        "blockNumber": hex(BLOCK),
        "blockTimestamp": hex(int(ts)),
        "transactionHash": tx,
    }


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
        }
        self._returns.update(overrides)

    async def _answer(self, name: str):
        self.calls.append(name)
        value = self._returns[name]
        if isinstance(value, BaseException):
            raise value
        return value

    async def fetch_nonces(self):        return await self._answer("fetch_nonces")
    async def fetch_chain_state(self):   return await self._answer("fetch_chain_state")
    async def fetch_channel_txs(self):   return await self._answer("fetch_channel_txs")
    async def fetch_dev_activity(self):  return await self._answer("fetch_dev_activity")
    async def fetch_market(self):        return await self._answer("fetch_market")
    async def fetch_recent_logs(self):   return await self._answer("fetch_recent_logs")
    async def fetch_nft_stats(self):     return await self._answer("fetch_nft_stats")

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
        SOURCE_LOGS, SOURCE_NFT, SOURCE_ACTIVITY,
    )


async def test_close_persists_the_cache_and_closes_the_client(tmp_path):
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client)
    await m.fetch_and_compute()
    await m.close()
    assert client.closed is True
    assert (tmp_path / "surf_cache.json").exists()
```

- [ ] **Run it and watch it fail.**
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -v`
      → `ModuleNotFoundError: No module named 'maxpane_dashboard.data.surf_manager'`.

- [ ] **Minimal implementation.** Create `maxpane_dashboard/data/surf_manager.py`:

```python
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

Three rules this module exists to enforce
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

Live values are computed, never quoted: ``parity_pct`` is derived from the two
prices every cycle, and ``imd_burned_cum`` is accumulated from observed supply
decreases. The repo has measured a documented "constant" drift three days
running; the same rule applies here (PRD §6.2).
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
        payload = self._blank_payload()
        payload["degraded"] = self._degraded()
        payload["as_of"] = self.cache.newest_as_of()
        self.save_cache()
        return payload

    # -- degradation ---------------------------------------------------------

    def _note(self, group: str, ok: bool) -> None:
        if ok:
            self._failed_groups.discard(group)
        else:
            self._failed_groups.add(group)
            self._error_count += 1

    def _degraded(self) -> list[str]:
        """Groups the screen must not present as live.

        A group is degraded when its last attempt failed **or** it has never
        produced a payload — the second clause is what keeps a group that failed
        two cycles ago, and is not due again, from reading as healthy.
        """
        out = set(self._failed_groups)
        for group, slot in GROUP_SLOT.items():
            if self.cache.get_last_good(slot) is None:
                out.add(group)
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
```

- [ ] **Run to green.** `.venv/bin/python -m pytest tests/data/test_surf_manager.py -v`
      → 4 passed. Nothing here asserts a *healthy* `degraded == []` yet: with no fetches
      wired, every group legitimately has no last-good payload and is degraded. That
      assertion arrives in Task WP4.10, once all six groups exist.

- [ ] **Commit.**
```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/data/surf_manager.py tests/data/test_surf_manager.py && git commit -m "feat(surf): manager scaffolding that always returns exactly SURF_KEYS"
```

---

### Task WP4.8: Fast tier — nonces, chain state, hero keys, burn accumulation

**Files:**
- Modify: `/Library/Vibes/autopull/maxpane_dashboard/data/surf_manager.py`
- Test: `/Library/Vibes/autopull/tests/data/test_surf_manager.py`

**Interfaces:**
- Consumes: `SurfClient.fetch_nonces()`, `.fetch_chain_state()`; `ChainState`, `NonceSet`;
  `surf_addresses.OPS_WALLET`.
- Produces: `SurfManager._pool_chain(now) -> dict` with keys
  `{"nonces", "state", "ok"}`; payload keys `lp_liquidity`, `lp_imd`, `lp_weth`,
  `lp_owner_ok`, `gate_open`, `imd_supply`, `imd_burned_cum`, `feed_nonce`, `as_of`.
  **Not** `identities_written`: the registry exposes no getter, so that key has no
  fast-tier producer — it comes off `NftStats.written` on the slow tier (Task WP4.10).
  `ok` is `nonces_res is not None **and** state_res is not None` — both halves of the
  one state RPC pool, so half an answer is a degradation of the `chain` group and says
  so. `or` would let a provider that answers `eth_getTransactionCount` but drops the
  batched `eth_call` round publish six `None` hero keys under a `degraded` list that
  omits `chain`.

- [ ] **Write the failing test.** Append to `tests/data/test_surf_manager.py`:

```python
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
```

- [ ] **Run it and watch it fail.**
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -v`
      → `assert None == 1234567890123456789` (`lp_liquidity` is still blank).

- [ ] **Minimal implementation.** Add to `SurfManager`:

```python
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
```

Replace `_cycle` with:

```python
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
        self.cache.record_supply(imd_supply)

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
```

- [ ] **Prove the half-failure flag bites.** In `_pool_chain`, change `ok = ... and ...`
      to `ok = nonces_res is not None or state_res is not None` and re-run
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k "raising_client or chain_outage" -v`
      → `test_a_raising_client_call_is_a_degradation_not_a_crash` fails with `chain`
      **absent** from `data["degraded"]` (the state read raised, the nonce read did
      not, and `or` called that healthy — it also stored a half-empty `SLOT_CHAIN`,
      so `_degraded`'s never-produced-a-payload clause cannot catch it either), while
      `test_a_chain_outage_is_flagged_and_invents_nothing` stays green because it
      kills *both* reads and there the two operators agree. That asymmetry is the
      whole point: only a half-failure can tell `and` from `or`, and exactly one test
      in this file produces one. Restore `and`.

- [ ] **Prove the pool/position doubles bite.** In `_market()`, set
      `"pool_imd": 388_421.0` and `"pool_weth": 142.7067` (the old values) and re-run
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k divided -v`
      → `test_wei_is_divided_exactly_once` fails on
      `assert 388420.99999999994 != 388421.0 ± 3.9e-01` — the two `!=` assertions and
      the two `==` assertions above them become mutually exclusive, so no manager
      implementation can satisfy the test. Restore `POOL_IMD` / `POOL_WETH`.

- [ ] **Run to green.** `.venv/bin/python -m pytest tests/data/test_surf_manager.py -v`
      → 11 passed.

- [ ] **Commit.**
```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/data/surf_manager.py tests/data/test_surf_manager.py && git commit -m "feat(surf): fast-tier chain reads, hero keys and observed-burn wiring"
```

---

### Task WP4.9: Medium tier — market, logs, and channel bodies only on a nonce change

**Files:**
- Modify: `/Library/Vibes/autopull/maxpane_dashboard/data/surf_manager.py`
- Test: `/Library/Vibes/autopull/tests/data/test_surf_manager.py`

**Interfaces:**
- Consumes: `SurfClient.fetch_market()`, `.fetch_recent_logs()`, `.fetch_channel_txs()`;
  `classify_channel_tx(from_addr, to_addr, value_wei, input_hex) -> str`;
  `decode_utf8_calldata(hex_str) -> str | None`;
  `parity_pct(imd_price_usd, fp_price_usd) -> float | None` — **imported from
  `analytics/surf_signals.py`, never re-implemented here.** WP2 builds and table-tests
  it; a second copy in `data/` is exactly the duplication CLAUDE.md's "`analytics/` =
  PURE functions" rule exists to prevent, and it would leave the tested copy with no
  production consumer.
- Produces: payload keys `imd_price_usd`, `imd_change_24h_pct`, `imd_vol_24h_usd`,
  `pool_liquidity_usd`, `fp_price_usd`, `parity_pct`, `eth_usd`, `feed_items`,
  `feed_last_post_age_s`, `hook_status`; helpers `_market_payload`, `_channel_payload`,
  `_bridge_rows`, `_hook_pool_rows`, `_seaport_sale_rows`, `_identity_writes`, and the
  module-level `_hex_int` / `_word_addr` / `_data_words` / `_abi_array` / `_log_ts` log
  decoders.

**Every source group resolves fresh-or-last-good in `_cycle`, and the market group is
not the exception it once was.** A `_pool_*` method returning `None` means one of two
different things — *the tier was fresh so we skipped it* or *the fetch failed* — and only
the second one reaches `_note`. So a group whose consumer reads its values straight off
the returned model publishes `None` on every skipped cycle while `degraded` correctly
reports it healthy: dashes on a chain that is fine, with nothing to flag them. With the
shipped defaults (`--poll-interval` 30 s, `TIER_TTL_SECONDS[TIER_MEDIUM] = 90.0`) the
medium tier is due on **one refresh in three**, so that is two thirds of all refreshes.
This task therefore caches the *whole* market view under `SLOT_MARKET` and resolves
`market_payload` in `_cycle` exactly the way `channel_payload`, `nft_payload` and
`activity_rows` are resolved. `hook_status`/`logs_payload` already read `SLOT_LOGS` back
on every cycle for the same reason.

**All four `LogWindow` groups arrive raw, and this task decodes every one of them.**
That was open, and it is settled WP1's way (open issue 9, now closed): WP1.9 returns
`tuple(seaport or ())` of untouched `eth_getLogs` dicts alongside the other three, its
ratchet test `test_the_client_never_decodes_a_log_itself` bans `_word_addr` / `_log_ts`
from `surf_client.py`, and wp1.md's header states outright that the note about
`seaport_sales` being "decoded by WP1.9b" is wrong. So `seaport_sales` needs the same
treatment as `bridge_mints` and `v4_initializes`, and this task grows a third decoder
rather than a special case. The `FakeSurfClient` double feeds raw rows for all four
groups for the same reason — the previous mixture (raw for two, pre-decoded for
Seaport) is what let a permanently empty `nft_last_sales` ship behind a green suite.

- [ ] **Write the failing test.** Append to `tests/data/test_surf_manager.py`:

```python
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


async def test_hook_status_reads_not_live_until_a_hooked_initialize_appears(tmp_path):
    client = FakeSurfClient()
    m = _manager(tmp_path, client=client)
    assert (await m.fetch_and_compute())["hook_status"] == "NOT LIVE"

    client._returns["fetch_recent_logs"] = LogWindow(
        from_block=BLOCK - 5_000,
        to_block=BLOCK + 10,
        bridge_mints=(),
        identity_updates=(),
        v4_initializes=(
            _v4_init_log("0x" + "ab" * 20, ts=NOW - 120.0, tx="0x" + "a5" * 32),
        ),
        seaport_sales=(),
    )
    m._clock_double.advance(600.0)
    assert (await m.fetch_and_compute())["hook_status"] == "LAUNCHED"


async def test_a_launch_is_never_un_launched_when_the_log_window_moves_past_it(tmp_path):
    """``Initialize`` is irreversible; the ~8 h log window is not.

    ``LOG_WINDOW_BLOCKS`` is 2400 blocks (≈8 h at 12 s), and `_pool_logs`
    replaces `SLOT_LOGS` wholesale on every successful medium-tier read. So a
    `hook_live` derived from the current window alone flips the hero back from
    LAUNCHED to NOT LIVE roughly eight hours after the launch, on a perfectly
    healthy chain, for the one event PRD §1/§7 says this dashboard exists to
    catch. That is a wrong value rather than a stale one — no `as of` marker
    redeems it — so `_pool_logs` latches the flag while leaving `v4_hook_pools`
    as the current window's rows.

    The cycle above (`..._until_a_hooked_initialize_appears`) cannot see this: it
    asserts LAUNCHED on the cycle that reads the log and never runs a later one.
    """
    client = FakeSurfClient(
        fetch_recent_logs=LogWindow(
            from_block=BLOCK - LOG_WINDOW, to_block=BLOCK,
            bridge_mints=(), identity_updates=(), seaport_sales=(),
            v4_initializes=(
                _v4_init_log("0x" + "ab" * 20, ts=NOW - 120.0, tx="0x" + "a5" * 32),
            ),
        )
    )
    m = _manager(tmp_path, client=client)
    assert (await m.fetch_and_compute())["hook_status"] == "LAUNCHED"

    # The pool is still there — the window has simply moved past its Initialize.
    client._returns["fetch_recent_logs"] = LogWindow(
        from_block=BLOCK, to_block=BLOCK + LOG_WINDOW,
        bridge_mints=(), identity_updates=(), v4_initializes=(), seaport_sales=(),
    )
    m._clock_double.advance(600.0)
    later = await m.fetch_and_compute()

    assert later["hook_status"] == "LAUNCHED"
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
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["hook_status"] == "NOT LIVE"


async def test_hook_status_is_none_when_the_logs_pool_never_answered(tmp_path):
    client = FakeSurfClient(fetch_recent_logs=None)
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["hook_status"] is None
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
                _v4_init_log("0x" + "ab" * 20, ts=NOW - 120.0, tx="0x" + "a5" * 32),
            ),
            seaport_sales=(),
        )
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
    assert cached["hook_live"] is True

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
```

(`KNOWN_LABELS` and the address constants are already in the test file's
`surf_addresses` import from Task WP4.7; add `SLOT_LOGS` to the `surf_cache` import.)

- [ ] **Run it and watch it fail.**
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -v`
      → `assert None == 0.7074` (`imd_price_usd` is blank).

- [ ] **Minimal implementation.** Add to `SurfManager`:

```python
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
```

and the module-level log helpers, next to `_tokens`:

```python
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
```

Wire them into `_cycle`, replacing the `chain = await self._pool_chain(now)` line and
extending `data`:

```python
        chain = await self._pool_chain(now)
        state = chain.get("state")
        nonces = chain.get("nonces")
        announce_nonce = _opt_int(_field(nonces, "announce"))

        imd_supply = _tokens(_field(state, "imd_supply_wei"))
        self.cache.record_supply(imd_supply)

        market, logs, channel = await asyncio.gather(
            self._pool_market(tiers, now),
            self._pool_logs(tiers, now),
            self._pool_channel(tiers, now, announce_nonce),
        )
        if market is not None or logs is not None or channel is not None:
            self.cache.mark_fetched(TIER_MEDIUM, now)

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
```

**`fresh_market` is kept separate on purpose — the sparklines must not be fed the
fallback.** A *panel* may serve last-good behind an `as of` marker; a *history series*
may not, because a point is a claim that the value was that at that time. Sampling
`payload["imd_price_usd"]` after this change would re-record the cached price into
every new hour bucket of a multi-hour outage, manufacturing history out of reads that
never happened — the same failure as writing a sentinel, one step subtler, and
`test_an_outage_never_writes_a_sentinel_into_a_series` (Task WP4.12) is the test that
catches it. So replace the sampling call at the end of `_cycle` with:

```python
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
```

and add to the `data` dict:

```python
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
```

plus the two helpers:

```python
    @staticmethod
    def _last_post_age(items: list[dict[str, Any]], now: float) -> float | None:
        """Age of the newest **self**-post. Replies are not the dev posting."""
        stamps = [
            i["ts"] for i in items if i.get("kind") == "self" and i.get("ts") is not None
        ]
        return None if not stamps else max(0.0, float(now) - max(stamps))

    def _hook_status(self) -> str | None:
        """``"LAUNCHED"`` / ``"NOT LIVE"`` / ``None`` when the logs pool never answered.

        Reads the **latched** ``hook_live`` written by ``_pool_logs``, never
        ``v4_hook_pools`` — those rows fall out of the ~8 h log window and a
        launch does not.
        """
        entry = self.cache.get_last_good(SLOT_LOGS)
        if entry is None or not isinstance(entry.payload, dict):
            return None
        return "LAUNCHED" if entry.payload.get("hook_live") else "NOT LIVE"
```

- [ ] **Prove the Seaport walk bites.** In `_seaport_sale_rows`, sum only the *first*
      native consideration leg (`wei = _hex_int("0x" + consideration[0][3]) or 0`) — the
      plausible "the price is what the seller got" reading — and re-run
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k seaport -v` →
      `test_seaport_sales_are_decoded_from_the_raw_order_logs` fails on the
      sum-equals-tx-value assertion (`0.360259911 != 0.3638989`), while both per-row
      prices still look plausible. Restore the loop.

- [ ] **Prove the market fallback bites.** In `_cycle`, drop the last-good arm —
      `market_payload = self._market_payload(market) if market is not None else {}` — and
      re-run
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k "skipped_medium_tier or medium_tier_is_skipped" -v`
      → `test_the_medium_tier_is_skipped_while_fresh` **still passes** (it only counts
      calls) while `test_a_skipped_medium_tier_still_renders_the_whole_market_panel` fails
      on `assert None == 0.7074`. That pair is the point: the call count cannot see a dark
      panel. Restore the arm.

- [ ] **Prove the hook latch bites.** In `_pool_logs`, store `"hook_live": bool(hooked)`
      and re-run
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k hook -v`
      → `test_a_launch_is_never_un_launched_when_the_log_window_moves_past_it` fails on
      `assert 'NOT LIVE' == 'LAUNCHED'`, and the other three hook tests stay green.
      Restore `bool(hooked) or previously_live`.

- [ ] **Run to green.** `.venv/bin/python -m pytest tests/data/test_surf_manager.py -v`
      → 27 passed.

- [ ] **Commit.**
```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/data/surf_manager.py tests/data/test_surf_manager.py && git commit -m "feat(surf): medium tier with live parity, nonce-gated bodies and the four log decoders"
```

---

### Task WP4.10: Slow tier — NFT stats and dev activity

**Files:**
- Modify: `/Library/Vibes/autopull/maxpane_dashboard/data/surf_manager.py`
- Test: `/Library/Vibes/autopull/tests/data/test_surf_manager.py`

**Interfaces:**
- Consumes: `SurfClient.fetch_nft_stats()`, `.fetch_dev_activity()`; `NftStats`, `DevTx`;
  `surf_addresses.KNOWN_LABELS`, `DEV_WALLET`, `OPS_WALLET`, `NFPM`, `POOL_V3`,
  `BURN_EXECUTOR`, `FWA_SPLITTER`, `RELAY_DEPOSITORY`, `SEAPORT`, `UNIVERSAL_ROUTER`.
- Produces: payload keys `identities_written`, `nft_holders`, `nft_transfers_24h`,
  `nft_dev_holdings`, `nft_written`, `nft_last_sales`, `nft_floor`, `dev_activity`;
  `_pool_activity(tiers, now, dev_nonce, ops_nonce)`, `_pool_nft(tiers, now)`,
  `_nft_payload(stats, sales=None)`.

**`identities_written` lands here, not on the fast tier.** It and `nft_written` are one
number with one producer — `NftStats.written`, WP1.8's lifetime distinct-id count over
the registry's Blockscout log view (wp1.md open issue 11). `ChainState` has no such
getter, and the ~8 h `LogWindow.identity_updates` count is a *different* number that
belongs to signal 3's detail line and nowhere else.

**This task carries the address-poisoning *re-check* (PRD §4 / §6.5).** Ownership of the
defence itself is settled in this file's header: WP1.6 filters on the sender and fills
`DevTx.counterparty` / `.counterparty_label` / `.kind` from `KNOWN_LABELS` at
construction, and `_activity_rows` **reads** those three rather than deriving them — two
implementations of one allowlist is how a lookalike eventually inherits its target's
label. What stays here is one assertion about the rule (a row whose `from_addr` is not
the wallet its own `wallet_label` names is dropped *and logged loudly*), the derived
`counterparty_known` boolean, and the wei→ETH division. Four live 1-gwei lookalike sends
are in `tests/fixtures/surf/captures/ops_eth_txs.json` today; the regression test below
feeds them through as though WP1's filter had missed them, which is the only failure mode
this layer can still catch.

**Both dev nonces are read on the fast tier, so a contract creation must not wait for the
slow tier.** PRD §3 #4 says "both dev nonces every refresh; Blockscout tx page **on
change**". `_pool_activity` therefore mirrors `_pool_channel`: a moved dev/ops nonce
forces the tx-page fetch immediately, independent of the 420 s TTL. Left tier-only, a
deploy would surface up to seven minutes late — which defeats the one job NEW DEPLOY has.

- [ ] **Write the failing test.** Append to `tests/data/test_surf_manager.py`:

```python
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
    assert data["degraded"] == []
    assert data["as_of"] == pytest.approx(NOW)
    # This cycle's sample is already in the sparkline, not one refresh behind.
    assert data["supply_series"] == [[1_786_190_400.0, pytest.approx(IMD_SUPPLY)]]
    assert data["price_series"] == [[1_786_190_400.0, pytest.approx(IMD_PRICE_USD)]]


async def test_a_chain_outage_degrades_only_the_chain_group(tmp_path):
    client = FakeSurfClient(fetch_nonces=None, fetch_chain_state=None)
    data = await _manager(tmp_path, client=client).fetch_and_compute()
    assert data["degraded"] == [SOURCE_CHAIN]
    assert data["imd_price_usd"] == pytest.approx(IMD_PRICE_USD)
    assert data["nft_holders"] == NFT_HOLDERS
    assert data["imd_supply"] is None
```

- [ ] **Run it and watch it fail.**
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k nft -v`
      → `assert None == 667`.

- [ ] **Minimal implementation.** Add to `SurfManager`:

```python
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

        What stays here:

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
```

In `_cycle`, extend the `asyncio.gather` to five coroutines and mark the slow tier:

```python
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
        activity_cached = getattr(
            self.cache.get_last_good(SLOT_ACTIVITY), "payload", None
        )
        activity_rows = (
            self._activity_rows(activity) if activity is not None
            else (
                list((activity_cached or {}).get("rows") or [])
                if activity_cached is not None
                else None
            )
        )
```

and add to `data`:

```python
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
```

- [ ] **Prove the unavailability contract bites.** In `_cycle`, change the
      `activity_rows` fallback back to `list((activity_cached or {}).get("rows") or [])`
      — dropping the `activity_cached is not None` arm — and re-run
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k "nft_outage or read_but_empty" -v`
      → `test_an_nft_outage_leaves_the_rest_of_the_screen_alone` fails on
      `assert [] is None`, while `test_a_read_but_empty_page_is_an_empty_list_not_none`
      still passes. That pair is the whole contract: only one of the two shapes may
      claim the pages were read. Restore the arm.

- [ ] **Run to green.** `.venv/bin/python -m pytest tests/data/test_surf_manager.py -v`
      → 38 passed.

- [ ] **Commit.**
```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/data/surf_manager.py tests/data/test_surf_manager.py && git commit -m "feat(surf): slow-tier NFT counters, lifetime written count and dev activity rows"
```

---

### Task WP4.11: Signal integration — real `build_signals`, real baselines, across a restart

**Files:**
- Modify: `/Library/Vibes/autopull/maxpane_dashboard/data/surf_manager.py`
- Test: `/Library/Vibes/autopull/tests/data/test_surf_manager.py`

**Interfaces:**
- Consumes: `build_signals(baselines: dict, readings: dict, now_ts: float) -> tuple[dict, dict]`,
  `READING_KEYS`, `FIRED_TTL_S`; `SurfCache.get_baselines()` / `.set_baselines()`.
- Produces: `SurfManager._readings(data, nonces, channel_payload, activity_rows) -> dict`,
  and the 18 `sig_*` payload keys.

**The readings keys are not restated here — they are imported.** `_readings` builds
`dict.fromkeys(surf_signals.READING_KEYS)` and fills it in place, and a test asserts
`set(readings) == set(READING_KEYS)`. Restating the list in prose is how the two halves
drifted in the first place: an earlier draft of this task emitted `identity_writes`,
`v4_initializes` and `deploys` where WP2 froze `identities_written`, `v4_hook_pools` and
`deploy_events`, and omitted `channel_tx_count`, `announce_last_text`, `announce_last_ts`
and `burn_transfers` entirely. None of that raises: WP2 reads *absent* and *`None`* as the
same thing — a failed read — so four detectors would simply have gone quiet forever (no
decoded NEW POST body, no V4 LAUNCH, no deploy fire, no gate written-count). Extend the
`surf_signals` import with `READING_KEYS`; never retype the names.

Two vocabulary items this task pins down, both consumed by `deploy_events`:

- **`deploy_events` has two sources, because PRD §3 #4 names two shapes.** `kind ==
  "deploy"` rows come from `_activity_rows` (Task WP4.10) — a tx whose `created_contract`
  is set. `kind == "action"` rows come from the **channel feed items**, not from the tx
  pages: the announce EOA is not one of the two wallets `fetch_dev_activity` pages, so an
  outbound contract call from it can only reach the detector through `fetch_channel_txs`,
  where `classify_channel_tx` already labels it `action`. The ERC-8004 registration at
  channel nonce 4 is the PRD's own worked example, and it is the second shape.
  **The merge is gated on both sources having answered** (`if channel and
  activity_read`), because `[]` seeds WP2's `deploy_tx`/`deploy_ts` and one source may
  not make that claim for the other. Merging two cadences into one baseline pair has a
  second, deeper consequence that WP4 cannot fix alone — Open issue 12.
- the `label` WP2 reads off a deploy row is the created contract (a `deploy`) or the
  called method (an `action`) — `ChannelTx.method` when Blockscout decoded one, the
  4-byte selector otherwise, so the ERC-8004 row renders `action register() · announce`
  and an undecoded one renders `action 0xf2c298be · announce`. Both are
  third-party-influenced strings, passed through untouched and escaped at the widget.

- [ ] **Write the failing test.** Append to `tests/data/test_surf_manager.py`:

```python
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
    assert set(readings) == set(surf_signals.READING_KEYS)
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
                to_addr=BURN_EXECUTOR, method="bridgeToBaseBurnReceiver",
                counterparty=BURN_EXECUTOR,
                counterparty_label=KNOWN_LABELS[BURN_EXECUTOR.lower()],
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
```

Add `from maxpane_dashboard.analytics import surf_signals` and `SLOT_CHANNEL` to the
test file's imports (`SLOT_CHANNEL` comes from `surf_cache`, which the file already
imports from).

- [ ] **Run it and watch it fail.**
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k signal -v`
      → `assert None in ('ok', 'watch', 'fired', None)` passes but
      `test_a_new_post_fires_within_one_cycle` fails with `assert None == 'fired'`.

- [ ] **Minimal implementation.** Add to `SurfManager`:

```python
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
```

(`READING_KEYS` and `parity_pct` are already in the `surf_signals` import from Task
WP4.7; no new module constant is needed — the two deploy shapes are selected by their
two source streams, not by a shared kind set.)

In `_cycle`, immediately before `payload = self._finalise(data)` — after `data` is
fully assembled, because the readings now quote it rather than re-deriving it, and
`channel_payload` is the same fresh-or-last-good dict the feed rendered from:

```python
        data.update(
            self._signal_keys(
                self._readings(data, nonces, channel_payload, activity_rows), now
            )
        )
```

- [ ] **Prove the test bites.** In `_signal_keys`, change
      `baselines = self.cache.get_baselines()` to `baselines = {}` and re-run
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k restart -v` →
      `test_a_restart_neither_resurrects_nor_loses_a_fired_signal` fails, because the
      post re-fires with `age_s == 0.0` against an empty baseline. Restore the line.

- [ ] **Prove the contract test bites** — this is the one that guards a *silent*
      failure, so it has to be watched going red. In `_readings`, rename
      `read["identities_written"]` to `read["identity_writes"]` (the spelling this
      task shipped with before the contract was imported instead of retyped) and
      re-run
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k "wp2s_contract or signal" -v`
      → `test_the_readings_dict_is_exactly_wp2s_contract` fails on the set
      comparison, **and every other signal test still passes** — which is exactly
      the point: nothing else can see a detector go quiet. Restore the key.

- [ ] **Prove the write-count wiring bites.** In `_readings`, change
      `read["identities_written"] = logs.get("identity_writes")` to
      `data.get("identities_written")` — the hero's lifetime number, which is the
      wrong-but-adjacent value — and re-run
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k gate_detail -v`
      → `test_the_gate_detail_reads_the_window_and_the_hero_reads_the_lifetime` fails
      on `assert 1 == 2`, and the GATE row's detail reads `closed · 1 written` for a
      window that saw two identities written. Restore.

- [ ] **Run to green.** `.venv/bin/python -m pytest tests/data/test_surf_manager.py -v`
      → 54 passed.

- [ ] **Commit.**
```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/data/surf_manager.py tests/data/test_surf_manager.py && git commit -m "feat(surf): wire the six detectors through the pure signal layer"
```

---

### Task WP4.12: Degradation composition — the whole screen dark, and nothing invented

**Files:**
- Modify: `/Library/Vibes/autopull/maxpane_dashboard/data/surf_manager.py` (only if a
  test finds a gap)
- Test: `/Library/Vibes/autopull/tests/data/test_surf_manager.py`

**Interfaces:** no new public surface — this task is the acceptance criterion for
PRD §11.3 ("all six detectors degrade to explicit states under full network outage; no
signal fires and no baseline moves").

- [ ] **Write the failing test.** Append to `tests/data/test_surf_manager.py`:

```python
# ---------------------------------------------------------------------------
# Full outage — PRD §11.3
# ---------------------------------------------------------------------------


def _dead_client() -> FakeSurfClient:
    """Every source returns ``None``: total, honest outage."""
    return FakeSurfClient(
        fetch_nonces=None, fetch_chain_state=None, fetch_channel_txs=None,
        fetch_dev_activity=None, fetch_market=None, fetch_recent_logs=None,
        fetch_nft_stats=None,
    )


async def test_a_total_outage_returns_the_full_key_set_with_nothing_invented(tmp_path):
    data = await _manager(tmp_path, client=_dead_client()).fetch_and_compute()

    assert set(data) == set(SURF_KEYS)
    assert data["degraded"] == sorted(SOURCES)
    for key in (
        "eth_usd", "imd_price_usd", "imd_change_24h_pct", "imd_vol_24h_usd",
        "pool_liquidity_usd", "fp_price_usd", "parity_pct", "imd_supply",
        "lp_liquidity", "lp_imd", "lp_weth", "lp_owner_ok", "gate_open",
        "identities_written", "imd_burned_cum", "hook_status", "feed_nonce",
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
    clock = FakeClock()
    m = _manager(tmp_path, client=FakeSurfClient(), clock=clock)
    await m.fetch_and_compute()                      # establish real baselines
    before = m.cache.get_baselines()

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
        fetch_nft_stats=RuntimeError("dns"),
    )
    data = await _manager(tmp_path, client=boom).fetch_and_compute()
    assert set(data) == set(SURF_KEYS)
    assert data["degraded"] == sorted(SOURCES)


async def test_the_manager_never_reaches_the_network_in_these_tests(manager):
    """Structural, per CLAUDE.md: the injected transport raises on any use."""
    await manager.fetch_and_compute()
    with pytest.raises(AssertionError):
        await manager.client.http.post("https://ethereum-rpc.publicnode.com")
```

- [ ] **Run it and watch it fail.** `.venv/bin/python -m pytest tests/data/test_surf_manager.py -v`
      → expect `test_an_outage_after_a_good_read_serves_last_good_behind_an_as_of` to
      fail first (`assert 0 == 4`) if `_pool_channel`'s last-good fallback was not
      reached because the cached-nonce short circuit returned before the outage path.

- [ ] **Minimal implementation — verify, do not rewrite.** This property is already
      built into the `_pool_channel` of Task WP4.9; nothing new is added here. **Do not
      paste an older copy of that method back in.** An earlier draft of this task
      restated its body inline and, in doing so, silently reverted two things WP4.9
      had put there: the `_channel_payload` slot (`tx_count`, `last_text`, `last_ts`)
      that `channel_tx_count` and the NEW POST body quote are read from, and the
      nonce-first fetch order. Re-read WP4.9's version and check the two properties
      this task cares about hold in it:

      1. Every early `return None` is a **skip** and sits *above* the `_guard` call,
         so only a real fetch attempt can reach `_note` — a skipped group is not
         degraded and the feed keeps its last-good rows without a staleness marker it
         has not earned.
      2. A failed fetch leaves the slot untouched, so `_cycle`'s `channel_payload`
         falls back to the last good page and `feed_items` still renders 4 rows while
         `SOURCE_CHANNEL` *is* in `degraded`. That is the assertion pair in
         `test_an_outage_after_a_good_read_serves_last_good_behind_an_as_of`.

- [ ] **Prove the test bites.** In `_degraded`, delete the loop

```python
        for group, slot in GROUP_SLOT.items():
            if self.cache.get_last_good(slot) is None:
                out.add(group)
```

      and re-run
      `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k "nft_outage or hook_status_is_none" -v`
      → `test_an_nft_outage_leaves_the_rest_of_the_screen_alone` still passes (the
      attempt failed *this* cycle), but
      `test_hook_status_is_none_when_the_logs_pool_never_answered` shows the shape the
      loop protects: add a `clock.advance(30.0)` second cycle to that test and the logs
      group silently drops out of `degraded` while `hook_status` is still `None` — a
      dark panel with no flag. Restore the loop and re-run to green.

- [ ] **Run the whole suite to green.**
      `.venv/bin/python -m pytest tests/data/test_surf_cache.py tests/data/test_surf_manager.py -v`
      → 36 + 62 passed. Then the full repo:
      `.venv/bin/python -m pytest -q` → all green, no existing dashboard affected.

- [ ] **Commit.**
```bash
cd /Library/Vibes/autopull && git add tests/data/test_surf_manager.py maxpane_dashboard/data/surf_manager.py && git commit -m "test(surf): full-outage composition, false-BURN and last-good regressions"
```

---

## Handoff to the widget and screen packages

After Task WP4.12 the following are true and can be relied on:

- `SurfManager.fetch_and_compute()` returns **exactly** `SURF_KEYS`, every cycle, under
  every failure combination, with no exception escaping.
- Every numeric key is `float | int | None`; `None` means unavailable and must render as
  the widget's explicit unavailable state, never as `0`.
- `degraded` is a sorted `list[str]` drawn from
  `("chain", "channel", "market", "logs", "nft", "activity")`.
- **The three source-backed lists follow WP3's frozen pair of meanings**: `feed_items`,
  `dev_activity` and `nft_last_sales` are `None` when their group has never produced a
  payload, and `[]` only when a read succeeded and genuinely returned nothing. `None`
  must render the widget's unavailable line; `[]` must render "no posts in window" /
  "no recent activity" / "no sales in window" *without* it. `supply_series` and
  `price_series` are the exception and are always lists — they are this cache's own
  history, not a source's answer.
- `nft_floor` is always `None` in v1 — the widget renders `n/a — no keyless source`.
- `identities_written` and `nft_written` are **one number**: `NftStats.written`, WP1.8's
  lifetime distinct-id count over the registry's log view (1 of 2000 today). `None` when
  unread — never `0`, which would state that nobody has written an identity. The
  same-named *reading* handed to `build_signals` is a different number (writes seen in
  the ~8 h log window) and never reaches the flat dict.
- `feed_items` rows are `{ts, kind, from_addr, from_label, text, tx_hash}` newest first,
  `kind ∈ {"self", "reply", "action", "fund"}`, `text` is `None` for non-UTF-8 calldata,
  and **every string is third-party** — `safe_markup` is mandatory in the widget.
- `dev_activity` rows are `{ts, wallet_label, kind, counterparty, counterparty_known,
  value_eth, tx_hash}` newest first; `counterparty_known=False` must never render as
  trusted (address poisoning is live on frenpet.eth today).
- `supply_series` / `price_series` are `[[hour_ts, value], ...]` oldest first — the shape
  `widgets/sparkline_common` expects.
- `imd_burned_cum` is **observation-scoped**, and it is the one key whose `0.0` needs copy
  rather than a number: `None` = no successful supply read yet (unavailable), `0.0` = watched
  and nothing moved *since this install started*, `> 0` = the burn actually seen. It is **not**
  the ~58,849 IMD all-time figure of PRD §1 and can never become it without a new source, so
  consuming widgets must label it `observed` and must not print a bare `burned 0` — that reads
  as "no IMD has ever been burned", which is false on every fresh install. WP3.2's `SurfHero`
  implements this (`burned {n:,.0f} observed` / `no burn observed yet` / dash); screen-level
  fixtures elsewhere must use a plausible observed value such as `15_745.0`, never `58_848.0`.

## Open issues

1. **CLOSED — the model vocabulary is frozen in WP0.4 and imported, not restated.**
   WP0.4 exports `CONSTRUCTOR_KWARGS`; the table at the top of this file is a quotation of
   it, the freeze-check command diffs the two, and every double in this suite constructs by
   keyword so a rename is a `TypeError` at collection. This entry used to say the names
   were "assumed" — and they were: WP0, WP1 and WP4 each carried a different spelling of
   the same seven dataclasses. `ChainState` alone appeared as
   `gate_open`/`imd_supply_wei`/`lp_imd_wei` (WP0), `identity_allowed`/
   `imd_total_supply_wei`/`lp_tokens_owed0` (WP1) and `identity_allowed`/`imd_supply`/
   `lp_imd` (WP4, which was reading *flat-dict* keys off a model). WP1's constructor calls
   would have raised; WP4's `getattr(..., None)` reads would have returned `None` for the
   whole hero with a green suite. Two structural fixes came out of it and neither may be
   reverted: `_field()` raises on an unknown name instead of defaulting, and the flat-key /
   model-field mapping is written down once in the header table.

   Three fields it settled that are worth re-reading before Task WP4.8:
   `lp_imd`/`lp_weth` come off `ChainState.lp_imd_wei`/`lp_weth_wei`, which WP1.4 derives
   from the position's tick bounds — **not** off `MarketSnapshot.pool_imd`/`pool_weth`,
   which is the whole pool across every position;
   `nft_last_sales` comes off `LogWindow.seaport_sales` (raw, decoded in WP4.9) and
   **not** off `NftStats`; and `identities_written` / `nft_written` are one number with
   one producer, `NftStats.written` — WP1.8's `_count_identities_written()`, a lifetime
   distinct-id count over Blockscout's `/addresses/{IDENTITY_REGISTRY}/logs`, filled in
   Task WP4.10. (An earlier revision of this entry said the key had "no producer at all
   in v1 and must stay `None`", which was true when WP1.8 was still a stub and false
   afterwards; the flat key was left hardcoded to `None`, so the hero's "x/2000" and
   WP2's GATE reading were both permanently dark on a healthy chain, behind a green
   suite — the double simply left `written` unset.) `nft_transfers_24h` is a *rate* and
   is `None` until WP1.8's page walk reaches the 24 h edge; it is never back-filled from
   the lifetime `transfers_total` beside it.
2. **CLOSED — the readings-dict keys are imported, not restated.** This entry used to
   list ten key names in prose, four of them misspelled against WP2's frozen
   `READING_KEYS` (`identity_writes`, `v4_initializes`, `deploys`) and four missing
   outright (`channel_tx_count`, `announce_last_text`, `announce_last_ts`,
   `burn_transfers`). Because WP2 encodes *absent* and *`None`* identically as "the read
   failed", that mismatch raised nothing anywhere: it would simply have retired the
   decoded NEW POST body, the V4 LAUNCH fire, every NEW DEPLOY fire and the gate
   written-count, permanently and silently. Task WP4.11 now builds
   `dict.fromkeys(READING_KEYS)` and `test_the_readings_dict_is_exactly_wp2s_contract`
   asserts the set. **Never restate the list in prose again — that is how it drifted.**
3. **`burn_transfers` carries no amount, because no keyless source has one.** WP2's
   `READING_KEYS` types it `{ts, tx_hash, amount}` and PRD §3 #6 names "BurnExecutor tx
   seen" as one of the two ways BURN fires. WP4.11 sources the rows from the dev tx pages
   (`_activity_rows` labels an outbound call to `BURN_EXECUTOR` as `burn`) and sets
   `amount: None`: the IMD quantity is in the token-transfer ledger, not on the tx page,
   and the row's ETH value is the OFT fee — passing *that* as an IMD amount would be a
   fabricated number on a burn row. WP2 already renders `"? IMD → BurnExecutor"` for a
   `None` amount, so the WATCH is honest but imprecise. **To get the real figure, WP0.4's
   `LogWindow` needs a burn group and WP1.9 a fifth filter**
   (`Transfer(IMD, to=BURN_EXECUTOR)`, the exact rows `ops_token_transfers.json` already
   pins at 12,039 + 31,064 + 15,745 IMD); then `_pool_logs` stores decoded rows and
   `_readings` prefers them over the tx-page rows. Report to the plan owner — WP0/WP1
   files, not WP4's.
4. **`channel_tx_count` can be read but cannot move.** `_pool_channel` fetches the page
   only when the announce nonce changes, so the stored count only ever advances alongside
   a self-post — and WP2's NEW POST `watch` branch ("reply on channel · N txs") is
   therefore unreachable in production, though it is unit-tested in WP2. The channel is
   permissionless and two third-party replies already exist. PRD §5 puts *reply
   enumeration* on the slow tier, which is the intended home: letting `_pool_channel` fall
   through when `TIER_SLOW in tiers` costs one page every 7 min and lights the branch.
   `_pool_channel` belongs to Task WP4.9 — agree it with that task's owner rather than
   patching it from WP4.11.

   For contrast, the *other* unreachable-branch case in this plan is now closed:
   `_detect_gate`'s `written > base_written` WATCH branch — "the gate opened and closed
   between two polls" — was dead while `identities_written` was hardcoded `None`, and
   its `· N written` detail suffix never rendered. WP4.9 now counts distinct `topics[1]`
   over `LogWindow.identity_updates` into the log slot and WP4.11 feeds that to WP2, so
   both the suffix and the WATCH branch are live.
5. **`parity_pct` has a cache series but no `SURF_KEYS` entry.** The PRD §5 market group
   lists `supply_series` and `price_series` only. WP4 keeps the parity history so a v2
   sparkline needs no migration; if WP5's `SurfMarket` wants it now, `SURF_KEYS` is
   frozen and the addition is a PRD amendment, not a WP4 decision.
6. **`imd_burned_cum` is "burned since first observation", not all-time.** ~58,849 IMD
   across three verified events predates any install, and the Base burn receiver was
   never resolved from local data, so there is no keyless route to the historical total.
   **Routed to WP3, not WP5** — the earlier version of this note addressed WP5, but the
   hero copy is written in **WP3.2** (`widgets/surf/hero.py::_update_supply`); WP5 only
   splats the manager dict at an already-built widget, so the warning never reached the
   author who could act on it. WP3.2 now renders `burned {n:,.0f} observed`,
   `no burn observed yet` for `0.0`, and a dash for `None`, and carries a cross-WP check
   pointing back here. Two follow-ups still belong to the plan owner:
   - **WP5's screen fixture** uses `imd_burned_cum: 58_848.0` ("12,039 + 31,064 + 15,745"),
     the all-time ledger. It is a plausible-looking value the manager cannot produce;
     it should become an observed value (e.g. `15_745.0`). WP5's file — report, do not fix.
   - **WP0's `SURF_KEYS` comment** reads `# float | None — cumulative, from the burn ledger`,
     which describes an all-time total, and WP0's fixture task says "`imd_burned_cum` must
     be computed from the ledger". That ledger is the *recent* dev-activity window, not an
     exhaustive history, so it cannot back an all-time claim either. WP0's file — report,
     do not fix.
   - **PRD §4** describes the hero slot as "supply + cumulative burned". Substantively true
     (it is cumulative over the observation window) but the wording invites all-time copy;
     worth a one-line PRD amendment to "supply + burn observed since first read".
7. **`nft_transfers_24h` is a rate, and Blockscout serves a lifetime `transfers_count`
   (7,411).** WP1 must derive the 24 h figure (or return `None`); WP4 passes through
   whatever `NftStats.transfers_24h` holds and cannot detect the difference.
8. **`eth_usd` source.** WP4 reads it off `MarketSnapshot`; PRD §5 points at the existing
   `data/price.py` CoinGecko helper. WP1 owns which one fills the field — WP4 only needs
   it to be `float | None`.
9. **CLOSED — `LogWindow` carries raw logs, all four groups, and WP4.9 decodes every
   one.** The two plans said opposite things: WP0.4's `LogWindow` docstring claimed
   *"Groups carry **decoded** event dicts … WP1.9b owns that decode"*, while WP1.9's
   ratchet test `test_the_client_never_decodes_a_log_itself` asserts `_word_addr` and
   `_log_ts` never appear in `surf_client.py`, and wp1.md's *Decode ownership* table
   settles the split from the frozen artifact: WP0.4 froze the four groups as bare
   `tuple[dict, ...]`, so nothing forces a decoded shape and the decoders stay where they
   are already implemented. wp1.md's header names this file's error explicitly — *"the
   note that `seaport_sales` arrives 'decoded by WP1.9b' is wrong — it arrives raw like
   the other three groups and needs the same `_word_addr` treatment"* — and WP1.9 returns
   `seaport_sales=tuple(seaport or ())` of untouched rows.

   WP4 was internally inconsistent about it for one revision, and the inconsistency was
   invisible: `_nft_payload` read `seaport_sales` as pre-decoded `{ts, token_id, eth}`
   while the `FakeSurfClient` double fed exactly that shape for this one group and raw
   dicts for the other three, so every sale would have rendered `{None, None, None}` in
   production with the suite green. Resolved by adding `_seaport_sale_rows` beside
   `_bridge_rows` / `_hook_pool_rows` (offer/consideration walk over 4-word `SpentItem`
   and 5-word `ReceivedItem` groups), making the double hand raw rows for all four, and
   cross-checking against the real fill `0x5b4d1b44…eadad2`, whose two realized totals
   sum to the transaction's own `value` of `363898900000000000` wei. **WP0.4's
   `LogWindow` docstring still carries the old claim — report it to the plan owner; it is
   WP0's file.**
10. **A log with no `blockTimestamp` is dated to first-sight, not to its block.** Some
   keyless logs endpoints return `blockTimestamp` on the log object and some do not;
   resolving a block header per log is a round trip on a pool that already rate-limits, so
   `_log_ts` falls back to the observation clock. This is safe for firing — WP2's
   `_fresh_event` keys on `tx_hash` first, so a re-observed row cannot re-fire — but a
   FIRED age can read "just now" for an event a few minutes old, which is exactly the
   number this dashboard sells. If the working endpoints turn out to omit the field, the
   fix is a batched `eth_getBlockByNumber` in WP1 (one call per distinct block, not per
   log), not a per-log round trip here.
11. **CLOSED — the FIRED store now uses WP2's key and WP2's shape.** Task WP4.4 froze
   `BASELINE_FIRED_KEY = "fired_at"` holding `{signal: float}`, while `build_signals`
   emits and reads `fired` holding `{signal: {"ts": float, "detail": str}}` (wp2.md's
   `_fired_store` and the last two lines of `build_signals`). Because the keys did not
   match, `set_baselines(advanced)` routed the real store down the generic scalar branch,
   `_scalar({...})` returned `_DROP`, and the whole map was discarded **every cycle** —
   PRD §3's "a restart does not resurrect or lose a FIRED display" never worked, and
   WP4.11's restart test was red for a reason unrelated to signals. Fixed inside WP4's
   own files: `BASELINE_FIRED_KEY = "fired"`, a dedicated `_sanitise_fired` that keeps
   `ts` (finite, in `(0, now + CLOCK_SKEW_TOLERANCE_SECONDS]`) and `detail` (coerced with
   `str()`, bounded by `BASELINE_DETAIL_CAP`) and drops anything else whole,
   `get_baselines()` deep-copying the inner dicts, and every WP4.4/WP4.6 literal moved to
   the two-key shape. The cache still does not know which signals exist — only that this
   one key holds a two-field mapping per name.
12. **`deploy_events` merges two differently-tiered streams into one baseline pair, and
   only WP2 can fix it.** PRD §3 #4 names two shapes for NEW DEPLOY: a tx with
   `created_contract` (slow tier, `fetch_dev_activity`) and an announce-EOA outbound
   contract call (medium tier, `fetch_channel_txs`). WP4.11 hands both to WP2 as one
   `deploy_events` list, and WP2's `_fresh_event` reports only the **newest** row and
   refuses anything with `ts <= base["deploy_ts"]` — correct for one chronological
   stream, wrong for two on different cadences. A channel `action` at T+100 advances
   `deploy_ts` to T+100, and the slow-tier `created_contract` deploy at T+0 that arrives
   a refresh later is then dropped forever. It is the exact silent-miss class this key
   exists to prevent.

   Fixed here, because it *is* WP4's: the channel branch is gated on `activity_read`, so
   the merged stream can no longer claim `[]` — "the deploy window was read and held
   nothing", which seeds `deploy_tx`/`deploy_ts` — on the tx pages' behalf while they are
   down. **Not** fixed here, because it is a WP2 contract change: splitting
   `deploy_events` into two `READING_KEYS` entries with their own `BASELINE_EVENT_KEYS`
   pairs (`deploy_events` from the tx pages, `action_events` from the channel), both
   feeding `_detect_deploy`. Raise it with wp2.md's owner.
   `test_an_older_deploy_and_a_newer_action_both_reach_the_detector` pins what WP4 can
   guarantee today — both rows carried, newest first — and goes green on the stronger
   claim the moment WP2 splits the key.
13. **CLOSED — a skip is not an outage, and three places had forgotten it.** All three
   were green-suite defects on a *healthy* chain, and all three are fixed in WP4's own
   files:
   - **The market group had no last-good fallback.** `_pool_market` returns `None` as a
     skip on a fresh medium tier, and `_cycle` read the seven PRD §5 market keys straight
     off it — so with the shipped 30 s poll against a 90 s TTL the whole market panel went
     to dashes on two refreshes in three while `degraded` correctly reported the group
     healthy. Fixed by caching the whole view in `SLOT_MARKET` (`_market_payload`) and
     resolving `market_payload` fresh-or-last-good exactly like `channel_payload` /
     `nft_payload` / `activity_rows`. `test_a_skipped_medium_tier_still_renders_the_whole_
     market_panel` is the regression, and it is the only test in the suite that runs two
     cycles across a skip and then looks at a *value* rather than at a call count.
   - **The sparklines must stay fresh-only.** The fix above makes
     `payload["imd_price_usd"]` last-good-backed, so feeding it to `sample_series` would
     re-record the cached price into every new hour bucket of an outage — inventing
     history, which `test_an_outage_never_writes_a_sentinel_into_a_series` already
     forbids. `_cycle` keeps `fresh_market` separate for exactly that call.
   - **`hook_status` un-launched itself.** `hook_live` was derived from the current ~8 h
     `eth_getLogs` window only, and the slot is replaced wholesale on every successful
     read, so the hero flipped LAUNCHED → NOT LIVE about eight hours after the launch it
     exists to catch. A v4 pool initialization is irreversible, so that is a wrong value,
     not a stale one. `_pool_logs` now latches the flag; `v4_hook_pools` still means
     "seen in this window".
14. **Report-only — `data/series_points.coerce_point` accepts a numeric *string*, and its
   docstring says it does not.** It promises to drop "a value that is not a real number
   (`null`, a string, a bool)", but the implementation is `float(pt[1])` inside
   `except (TypeError, ValueError)`, so `["…", "0.72"]` survives while `["…", "banana"]`
   does not. Task WP4.6's `HOSTILE` fixture was written against the docstring and had to
   be corrected to `"banana"` — the same value `tests/data/test_cache_corruption.py`
   already uses, for the same reason. **Do not "fix" the validator from a surf work
   package.** `maxpane_dashboard/data/series_points.py` is a leaf shared by all eight
   dashboards, no surf WP owns it, and tightening it would change persisted-cache
   behaviour repo-wide. Either the docstring or the coercion should change; that is a
   call for the plan owner.
