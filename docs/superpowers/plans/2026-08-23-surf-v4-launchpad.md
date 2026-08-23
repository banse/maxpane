# Surf v4 Migration And Launchpad View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the five surf panels that report stale or unanswerable state after surfsurf.eth's 2026-08-17 Uniswap v3→v4 migration, and add one `l` LAUNCHPAD body-swap view for the IMD launchpad shipped 2026-08-19.

**Architecture:** The data layer gains a v4 pool read (`extsload`, no `slot0()` in v4) whose pool id is read live from `LaunchpadHook.imdEthPoolId()` rather than hardcoded, plus a fourth cache tier carrying launchpad and decoy-pool state that is spawned-not-awaited so first paint never blocks on it. Widgets stay primitives-only and receive a flat dict. The `l` view is a body swap on curator's `y`/`f` precedent — the hero row stays mounted, `esc` backs out — so `app.py`, `__main__.py` and `GAMES` are untouched.

**Tech Stack:** Python 3.11, Textual, dataclasses, `pytest`. Keyless JSON-RPC (`ethereum-rpc.publicnode.com` for state, `gateway.tenderly.co` / `eth.drpc.org` for logs), Blockscout REST, DexScreener. Vendored keccak (`maxpane_dashboard/data/keccak.py`). No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-08-23-surf-v4-launchpad-design.md`

## Global Constraints

- **Read-only, always.** No signer, no transactor, no calldata for a state change, no keystore. The permissionless burn pipeline is *displayed, never called*.
- **Keyless, always.** No API key of any kind, in code or in tests.
- **No test may touch the network.** Assert it structurally — inject a transport that raises on use. Every external payload is a committed fixture under `tests/fixtures/surf/`.
- **A failed read is `None`, never `0`.** Never write a sentinel into a history series.
- **A revert is not a failed read.** A contract that answered "this does not exist" produces a representable state, not `None`.
- **Escape every third-party string** with `widgets/markup_safety.safe_markup`, after newline flattening *and* after truncation.
- **Inject the clock.** No module a test controls may call `time.time()` internally; loaders take `now=`, signal builders take `now_ts`.
- **Widgets import nothing from `data/` or `analytics/`.** They receive `str`/`int`/`float`/`bool`/`dict`/`list[dict]`.
- **Test command is `.venv/bin/python -m pytest`.** The system `python3` lacks the deps and produces meaningless collection errors.
- **Shorten the label; do not widen the layout.** When a new value would widen a sized cell, shorten the value. `FULL_LAYOUT_COLUMNS` (143, FWA's) is reserved for when no honest short name exists.
- **The app-wide width budget is 143 and surf currently measures 142.** Nothing in this plan may move `__main__.FULL_LAYOUT_COLUMNS`.
- **Commit trailer** on every commit:
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW
  ```
- **Never `git checkout --` a file.** The working tree holds 300 untracked curator fixtures and possibly other uncommitted user work.
- **Report defects in other work packages' files; do not fix them.**

### Verified live values (2026-08-23) — use these as fixture ground truth

| Thing | Value |
|---|---|
| Real v4 pool id | `0xb07d640fd9e2eb9dc81b953c8e4fd006bdfeaf276010fb5418eb763ca15abfb3` |
| Pool composition | native ETH / IMD, `fee = 10000` (1.00%), `tickSpacing 200`, `hooks = 0x0` |
| `extsload` slot0 word | `0x0000000027103e83e8012d82000000000000002f6ca7f98ffeb40bbb997d486e` |
| decoded | `sqrtPriceX96 = 3757351088368496721754945570926`, `tick = 77186`, `lpFee = 10000` |
| `extsload` liquidity word | `0x000000000000000000000000000000000000000000000190c7c60cef771c2ffc` (`7393092836965392068604`) |
| v3 `positions(1167726)` | reverts `execution reverted: Invalid token ID` |
| v3 `ownerOf(1167726)` | reverts `ERC721: owner query for nonexistent token` |
| ETH/IMD v4 pools since block 25,000,000 | 38 (1 real, 37 decoys) |
| Launchpad | `coinCount = 146`, `coinSupply = 1e27`, `initialPriceWad = 6695853418114` |
| Hook | `imdToBurn = 15062422197243027626`, `totalRealImd = 20577661206302839565537`, `burnFeeBps = 50`, `creatorFeeBps = 50`, `MAX_FEE_BPS = 500`, `totalCreatorEthOwed = 74934283907946169` |
| Executor v2 | `tokenBalance = 953674883767`, `minBridgeAmount = 0`, `baseBurnReceiver = 0xf9d7cbf5bEF2f5c9bA93a70F31dDCa6457716793` |
| Ops v4 positions | `PositionManager.balanceOf(OPS_WALLET) = 1` |

---

## File Structure

**Created**

| File | Responsibility |
|---|---|
| `maxpane_dashboard/data/surf_v4.py` | Pure v4 helpers: `pool_state_slots()`, `decode_slot0()`, `decode_liquidity()`. No I/O, no addresses. |
| `maxpane_dashboard/analytics/surf_launchpad.py` | Pure launchpad math: coin ranking, `hot_coin_threshold()`, curve-flow aggregates. No I/O. |
| `maxpane_dashboard/widgets/surf/launchpad.py` | `SurfLaunchpadCoins`, `SurfCurveFlow`, `SurfBurnPipeline`. Primitives only. |
| `tests/data/test_surf_v4.py` | Slot math and decode tests. |
| `tests/analytics/test_surf_launchpad.py` | Ranking and threshold tests. |
| `tests/widgets/test_surf_launchpad_widgets.py` | Composited-output and markup-safety tests. |
| `tests/fixtures/surf/v4_pool_state.json` | extsload words for the real pool. |
| `tests/fixtures/surf/v4_initializes.json` | 38 `Initialize` logs (1 real + 37 decoys). |
| `tests/fixtures/surf/launchpad_reads.json` | Hook/factory/executor getter round. |
| `tests/fixtures/surf/launchpad_logs.json` | `Launched`, `CurveSwap`, `ImdBurned` logs. |

**Modified**

| File | Change | Owner |
|---|---|---|
| `maxpane_dashboard/data/surf_addresses.py` | 5 addresses, 5 topics, 16 selectors, labels | Task 1 only |
| `maxpane_dashboard/data/surf_models.py` | `ChainState` fields, `PoolV4State`, `LaunchpadState`, payload keys, row keys | Task 1 only |
| `maxpane_dashboard/data/surf_cache.py` | `TIER_LAUNCHPAD`, `SLOT_LAUNCHPAD` | Task 2 |
| `maxpane_dashboard/data/surf_client.py` | v4 reads, revert classification, launchpad fetchers | Tasks 3–5 |
| `maxpane_dashboard/data/surf_manager.py` | wiring, detached sweep | Task 6 only |
| `maxpane_dashboard/analytics/surf_signals.py` | 9 detectors | Task 7 only |
| `maxpane_dashboard/widgets/surf/hero.py` | POOL · LP · BURN · SUPPLY | Task 8 |
| `maxpane_dashboard/widgets/surf/signals.py` | labels + quiet-collapse | Task 9 |
| `maxpane_dashboard/widgets/surf/market.py` | v4 repoint | Task 10 |
| `maxpane_dashboard/widgets/surf/activity.py` | launchpad labelling | Task 10 |
| `maxpane_dashboard/screens/surf.py` | `l` mode, body swap, bindings, CSS fallback | Task 12 only |
| `maxpane_dashboard/themes/minimal.tcss` | surf launchpad block | Task 12 only |
| `CLAUDE.md`, `README.md` | keys, conventions, width record | Task 13 only |

**Shared-file ownership.** `surf_manager.py` (Task 6), `analytics/surf_signals.py` (Task 7), `screens/surf.py` + `themes/minimal.tcss` (Task 12), `CLAUDE.md` + `README.md` (Task 13) each belong to exactly one task. No other task edits them.

## Dependency Graph

```
Task 1  (contract freeze)  ── everything below depends on it
   ├── Task 2  (cache tier)          ─┐
   ├── Task 3  (v4 pool reads)       ─┤
   ├── Task 4  (LP revert semantics) ─┼── Task 6 (manager wiring)
   ├── Task 5  (launchpad client)    ─┘        │
   ├── Task 7  (detectors)  ──────────────────┘
   ├── Task 8  (hero widget)      ─┐
   ├── Task 9  (signals widget)   ─┤
   ├── Task 10 (market+activity)  ─┼── Task 12 (screen + CSS) ── Task 13 (docs + width)
   └── Task 11 (launchpad widgets)─┘
```

Tasks 2–5 and 7–11 are parallelisable once Task 1 lands. Task 6 needs 2–5. Task 12 needs 8–11. Task 13 is last because the width sweep needs the real screen.

---

## Task 1: Freeze the data contract

**Files:**
- Modify: `maxpane_dashboard/data/surf_addresses.py`
- Modify: `maxpane_dashboard/data/surf_models.py`
- Test: `tests/data/test_surf_addresses.py`, `tests/data/test_surf_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `A.LAUNCHPAD_HOOK`, `A.LAUNCHPAD_FACTORY`, `A.BURN_EXECUTOR_V1`, `A.BURN_EXECUTOR_V2`, `A.POSITION_MANAGER_V4`, `A.BASE_BURN_RECEIVER`, `A.POOL_V4_ID_FALLBACK`, `A.V4_POOLS_MAPPING_SLOT`; topics `A.TOPIC_MODIFY_LIQUIDITY`, `A.TOPIC_LAUNCHED`, `A.TOPIC_CURVE_SWAP`, `A.TOPIC_IMD_BURNED`, `A.TOPIC_CREATOR_FEE_ACCRUED`; selectors `A.SEL_EXTSLOAD`, `A.SEL_COIN_COUNT`, `A.SEL_ALL_COINS`, `A.SEL_POOL_ID_OF`, `A.SEL_IMD_ETH_POOL_ID`, `A.SEL_IMD_TO_BURN`, `A.SEL_TOTAL_REAL_IMD`, `A.SEL_BURN_FEE_BPS`, `A.SEL_CREATOR_FEE_BPS`, `A.SEL_TOTAL_CREATOR_ETH_OWED`, `A.SEL_SPOT_PRICE_ETH_PER_COIN`, `A.SEL_GET_CURVE`, `A.SEL_TOKEN_BALANCE`, `A.SEL_MIN_BRIDGE_AMOUNT`, `A.SEL_PREVIEW_BRIDGE`, `A.SEL_BALANCE_OF`; dataclasses `PoolV4State`, `LaunchpadState`, `LaunchpadCoin`; payload keys listed in Step 7; `SURF_ROW_KEYS["launchpad_coins"]`.

- [ ] **Step 1: Write the failing address test**

Append to `tests/data/test_surf_addresses.py`:

```python
def test_launchpad_addresses_are_pinned() -> None:
    """The three contracts shipped 2026-08-19/20, read from chain 2026-08-23."""
    assert A.LAUNCHPAD_HOOK == "0x51768F5dA32BA2008304cC81674da51aCb802888"
    assert A.LAUNCHPAD_FACTORY == "0x73d1ae084F04f793A5bbd6B623d74400C9Fc3f42"
    assert A.BURN_EXECUTOR_V2 == "0xe29386719C155B6847aD5a4E97C6674f10ffc750"
    assert A.POSITION_MANAGER_V4 == "0xbD216513d74C8cf14cf4747E6AaA6420FF64ee9e"
    assert A.BASE_BURN_RECEIVER == "0xf9d7cbf5bEF2f5c9bA93a70F31dDCa6457716793"


def test_burn_executor_v1_is_kept_and_distinct() -> None:
    """V1 holds 0.664 IMD of residue and appears in the historical ledger."""
    assert A.BURN_EXECUTOR_V1 == "0x2EC59BEd2fB9deE447bbEC6e3BCA249782C9B88B"
    assert A.BURN_EXECUTOR_V1 != A.BURN_EXECUTOR_V2


def test_pool_v4_id_is_a_fallback_not_a_source() -> None:
    """Named FALLBACK so no reader mistakes it for the live value.

    The live id comes from LaunchpadHook.imdEthPoolId(); 37 decoy pools make a
    stale constant actively dangerous.
    """
    assert A.POOL_V4_ID_FALLBACK == (
        "0xb07d640fd9e2eb9dc81b953c8e4fd006bdfeaf276010fb5418eb763ca15abfb3"
    )
    assert not hasattr(A, "POOL_V4_ID")


def test_v4_pools_mapping_slot() -> None:
    """PoolManager._pools lives at storage slot 6; verified live via extsload."""
    assert A.V4_POOLS_MAPPING_SLOT == 6
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/data/test_surf_addresses.py -k launchpad_addresses -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'LAUNCHPAD_HOOK'`

- [ ] **Step 3: Add the addresses**

In `maxpane_dashboard/data/surf_addresses.py`, rename `BURN_EXECUTOR` to `BURN_EXECUTOR_V1` (update its docstring comment and its `LABELED_ADDRESSES` / `KNOWN_LABELS` entries), then add:

```python
#: Superseded burn executor.  Kept: it holds 0.664 IMD of residue and appears
#: in the historical burn ledger.  ``rescueToken`` drained it on 2026-08-20.
BURN_EXECUTOR_V1 = "0x2EC59BEd2fB9deE447bbEC6e3BCA249782C9B88B"
#: The live executor.  ``bridgeToBaseBurnReceiver()`` is **permissionless** --
#: the dashboard renders that state and never calls it.
BURN_EXECUTOR_V2 = "0xe29386719C155B6847aD5a4E97C6674f10ffc750"
#: v4 hook behind the IMD launchpad: bonding curves, 0.5% burn + 0.5% creator.
#: It hooks *launchpad coin* pools; the IMD/ETH pool itself is hookless.
LAUNCHPAD_HOOK = "0x51768F5dA32BA2008304cC81674da51aCb802888"
#: ``launch(string,string)`` -- permissionless, unpriced beyond gas.
LAUNCHPAD_FACTORY = "0x73d1ae084F04f793A5bbd6B623d74400C9Fc3f42"
#: Uniswap v4 PositionManager -- holds the ops wallet's single LP position.
POSITION_MANAGER_V4 = "0xbD216513d74C8cf14cf4747E6AaA6420FF64ee9e"
#: Base-side sink the executor bridges to; mainnet supply drops on arrival.
BASE_BURN_RECEIVER = "0xf9d7cbf5bEF2f5c9bA93a70F31dDCa6457716793"

#: **Fallback only.**  The live pool id is read from
#: ``LaunchpadHook.imdEthPoolId()`` every chain round.  38 ETH/IMD v4 pools
#: exist and 37 are decoys, so a stale constant is not merely wrong, it points
#: at somebody else's 98%-fee pool.  Used only when the hook read fails.
POOL_V4_ID_FALLBACK = (
    "0xb07d640fd9e2eb9dc81b953c8e4fd006bdfeaf276010fb5418eb763ca15abfb3"
)
#: Storage slot of ``PoolManager._pools``; v4 has no ``slot0()`` getter.
V4_POOLS_MAPPING_SLOT = 6
```

Add all five to `LABELED_ADDRESSES` and `KNOWN_LABELS`:

```python
    BURN_EXECUTOR_V2.lower(): "BurnExecutor",
    BURN_EXECUTOR_V1.lower(): "BurnExecutor v1",
    LAUNCHPAD_HOOK.lower(): "LaunchpadHook",
    LAUNCHPAD_FACTORY.lower(): "LaunchpadFactory",
    POSITION_MANAGER_V4.lower(): "v4 PositionManager",
    BASE_BURN_RECEIVER.lower(): "Base burn sink",
```

> `test_labels_are_short_enough_for_a_narrow_column` already exists and pins the
> maximum label width. If `v4 PositionManager` (18) trips it, shorten to
> `v4 PosM` — shorten the label, never widen the column.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/data/test_surf_addresses.py -v`
Expected: PASS, including the pre-existing `test_labeled_addresses_is_the_union`, `test_known_labels_covers_every_labeled_address` and `test_every_address_is_checksummed`.

- [ ] **Step 5: Write the failing topic/selector test**

Append to `tests/data/test_surf_addresses.py`:

```python
def test_pinned_v4_and_launchpad_topics() -> None:
    assert A.TOPIC_MODIFY_LIQUIDITY == keccak256_hex(
        b"ModifyLiquidity(bytes32,address,int24,int24,int256,bytes32)"
    )
    assert A.TOPIC_LAUNCHED == keccak256_hex(
        b"Launched(bytes32,address,address,string,string,uint256,uint256)"
    )
    assert A.TOPIC_IMD_BURNED == keccak256_hex(b"ImdBurned(uint256)")


def test_pinned_launchpad_selectors() -> None:
    assert A.SEL_EXTSLOAD == keccak256_hex(b"extsload(bytes32)")[:10]
    assert A.SEL_IMD_ETH_POOL_ID == keccak256_hex(b"imdEthPoolId()")[:10]
    assert A.SEL_COIN_COUNT == keccak256_hex(b"coinCount()")[:10]
```

- [ ] **Step 6: Run, add constants, run again**

Run: `.venv/bin/python -m pytest tests/data/test_surf_addresses.py -k "v4_and_launchpad or launchpad_selectors" -v`
Expected: FAIL, then add each constant **with its preimage entry** in `TOPIC_PREIMAGES` / `SELECTOR_PREIMAGES` (the existing parametrised recompute tests and `test_preimage_maps_cover_exactly_the_constants` enforce the pairing), then PASS.

Topics to add: `TOPIC_MODIFY_LIQUIDITY`, `TOPIC_LAUNCHED`, `TOPIC_CURVE_SWAP` (`CurveSwap(bytes32,address,address,bool,uint256,uint256,uint256,uint256,uint256)`), `TOPIC_IMD_BURNED`, `TOPIC_CREATOR_FEE_ACCRUED` (`CreatorFeeAccrued(address,uint256)`).

Selectors to add: `SEL_EXTSLOAD` `extsload(bytes32)`, `SEL_COIN_COUNT` `coinCount()`, `SEL_ALL_COINS` `allCoins(uint256)`, `SEL_POOL_ID_OF` `poolIdOf(address)`, `SEL_IMD_ETH_POOL_ID` `imdEthPoolId()`, `SEL_IMD_TO_BURN` `imdToBurn()`, `SEL_TOTAL_REAL_IMD` `totalRealImd()`, `SEL_BURN_FEE_BPS` `burnFeeBps()`, `SEL_CREATOR_FEE_BPS` `creatorFeeBps()`, `SEL_TOTAL_CREATOR_ETH_OWED` `totalCreatorEthOwed()`, `SEL_SPOT_PRICE_ETH_PER_COIN` `spotPriceEthPerCoin(bytes32)`, `SEL_GET_CURVE` `getCurve(bytes32)`, `SEL_TOKEN_BALANCE` `tokenBalance()`, `SEL_MIN_BRIDGE_AMOUNT` `minBridgeAmount()`, `SEL_PREVIEW_BRIDGE` `previewBridge()`, `SEL_BALANCE_OF` `balanceOf(address)`.

- [ ] **Step 7: Write the failing model test**

Append to `tests/data/test_surf_models.py`:

```python
from maxpane_dashboard.data.surf_models import (
    LaunchpadCoin,
    LaunchpadState,
    PoolV4State,
    SURF_KEYS,
    SURF_ROW_KEYS,
)


def test_pool_v4_state_fields() -> None:
    s = PoolV4State(
        pool_id="0xb07d",
        sqrt_price_x96=3757351088368496721754945570926,
        tick=77186,
        lp_fee=10000,
        liquidity=7393092836965392068604,
        pool_id_source="hook",
    )
    assert s.lp_fee == 10000
    assert s.pool_id_source == "hook"


def test_pool_id_source_is_recorded_not_inferred() -> None:
    """The panel must be able to say the id came from the fallback."""
    s = PoolV4State(
        pool_id="0xb07d", sqrt_price_x96=None, tick=None, lp_fee=None,
        liquidity=None, pool_id_source="fallback",
    )
    assert s.pool_id_source == "fallback"


def test_new_payload_keys_exist() -> None:
    for key in (
        "pool_venue", "pool_fee_bps", "pool_liquidity_raw", "pool_id_source",
        "decoy_pool_count", "lp_state", "lp_position_count",
        "burn_accrued", "burn_staged", "burn_ready", "burn_min_bridge",
        "launchpad_coin_count", "launchpad_swap_count",
        "launchpad_trader_count", "launchpad_burned_total",
        "launchpad_creator_eth_owed", "launchpad_coins",
        "launchpad_as_of_hhmm",
        "sig_decoy_state", "sig_decoy_detail", "sig_decoy_age_s",
        "sig_burnready_state", "sig_burnready_detail", "sig_burnready_age_s",
        "sig_hot_state", "sig_hot_detail", "sig_hot_age_s",
    ):
        assert key in SURF_KEYS, key


def test_lp_migration_signal_keys_are_renamed_not_dropped() -> None:
    """LP MIGRATION became LP MOVE; the prefix stays `lp` so the widget's
    _ROW_KEYS alignment is unchanged."""
    assert "sig_lp_state" in SURF_KEYS


def test_launchpad_coin_row_keys() -> None:
    assert SURF_ROW_KEYS["launchpad_coins"] == (
        "ticker", "name", "creator", "creator_known",
        "age_s", "price_eth", "change_1h_pct", "swaps_1h", "imd_burned",
    )
```

- [ ] **Step 8: Run to verify it fails, then add the models**

Run: `.venv/bin/python -m pytest tests/data/test_surf_models.py -k "pool_v4 or payload_keys or coin_row" -v`
Expected: FAIL with `ImportError: cannot import name 'PoolV4State'`

Add to `maxpane_dashboard/data/surf_models.py`:

```python
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
```

Add the payload keys from Step 7 to `SURF_KEYS` in their commented groups, and the `launchpad_coins` entry to `SURF_ROW_KEYS`.

- [ ] **Step 9: Run the full data suite**

Run: `.venv/bin/python -m pytest tests/data/ -q`
Expected: PASS. If `test_surf_widget_contract.py` fails on an unknown payload key, that is the contract test doing its job — add the key to its expected set in the same commit, since Task 1 owns the contract.

- [ ] **Step 10: Commit**

```bash
git add maxpane_dashboard/data/surf_addresses.py maxpane_dashboard/data/surf_models.py tests/data/
git commit -m "feat(surf): freeze the v4 and launchpad data contract

Addresses, topics, selectors and payload keys for the post-migration
world. POOL_V4_ID_FALLBACK is named for what it is: the live id comes
from LaunchpadHook.imdEthPoolId(), because 37 decoy ETH/IMD pools make a
stale constant point at somebody else's 98%-fee pool.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Task 2: The launchpad cache tier

**Files:**
- Modify: `maxpane_dashboard/data/surf_cache.py`
- Test: `tests/data/test_surf_cache.py`

**Interfaces:**
- Consumes: nothing from Task 1 (constants only).
- Produces: `TIER_LAUNCHPAD`, `SLOT_LAUNCHPAD`, both exported and in `TIERS` / `SLOTS`.

- [ ] **Step 1: Write the failing test**

```python
def test_launchpad_tier_is_slow_and_backs_off_shorter() -> None:
    """The analysis-tier shape: a long TTL, a shorter failure backoff.

    Deliberately slower than the title bar's clock -- the panel carries its own
    `as of HH:MM` and says so.
    """
    from maxpane_dashboard.data.surf_cache import (
        TIER_FAILURE_BACKOFF_SECONDS,
        TIER_LAUNCHPAD,
        TIER_TTL_SECONDS,
        TIERS,
    )

    assert TIER_LAUNCHPAD in TIERS
    assert TIER_TTL_SECONDS[TIER_LAUNCHPAD] == 600.0
    assert TIER_FAILURE_BACKOFF_SECONDS[TIER_LAUNCHPAD] == 180.0
    assert TIER_FAILURE_BACKOFF_SECONDS[TIER_LAUNCHPAD] < TIER_TTL_SECONDS[TIER_LAUNCHPAD]


def test_launchpad_slot_round_trips_through_the_cache_file(tmp_path) -> None:
    from maxpane_dashboard.data.surf_cache import SLOT_LAUNCHPAD, SLOTS, SurfCache

    assert SLOT_LAUNCHPAD in SLOTS
    cache = SurfCache(path=tmp_path / "surf_cache.json")
    cache.set_last_good(SLOT_LAUNCHPAD, {"coin_count": 146}, now=1000.0)
    cache.save(now=1000.0)

    reloaded = SurfCache(path=tmp_path / "surf_cache.json")
    reloaded.load(now=1001.0)
    assert reloaded.get_last_good(SLOT_LAUNCHPAD)["coin_count"] == 146
```

> Check `SurfCache`'s real constructor and method names before writing this —
> match `tests/data/test_surf_cache.py`'s existing calls exactly rather than the
> shapes sketched here.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/data/test_surf_cache.py -k launchpad -v`
Expected: FAIL with `ImportError: cannot import name 'TIER_LAUNCHPAD'`

- [ ] **Step 3: Add the tier and slot**

```python
#: The launchpad / decoy-pool sweep.  Its own long tier so the analysis panels
#: carry an `as of HH:MM` on a slower clock than the title bar's, deliberately.
TIER_LAUNCHPAD = "launchpad"
```

Add to `TIERS`, `TIER_TTL_SECONDS` (`600.0`), `TIER_FAILURE_BACKOFF_SECONDS` (`180.0`), then:

```python
SLOT_LAUNCHPAD = "launchpad"   # factory/hook/executor getters + log aggregates
```

Add to `SLOTS` and to the module's `__all__`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/data/test_surf_cache.py -q`
Expected: PASS. A cache-version bump may be required if `test_surf_cache.py` pins the schema version; if so bump it and confirm an old file still loads rather than aborting startup.

- [ ] **Step 5: Commit**

```bash
git add maxpane_dashboard/data/surf_cache.py tests/data/test_surf_cache.py
git commit -m "feat(surf): add the launchpad cache tier and slot

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Task 3: v4 pool state, read keylessly

**Files:**
- Create: `maxpane_dashboard/data/surf_v4.py`
- Create: `tests/data/test_surf_v4.py`
- Create: `tests/fixtures/surf/v4_pool_state.json`
- Modify: `maxpane_dashboard/data/surf_client.py`

**Interfaces:**
- Consumes: `A.V4_POOLS_MAPPING_SLOT`, `A.SEL_EXTSLOAD`, `A.SEL_IMD_ETH_POOL_ID`, `A.POOL_V4_ID_FALLBACK`, `PoolV4State`.
- Produces: `surf_v4.pool_state_slots(pool_id) -> tuple[str, str]`, `surf_v4.decode_slot0(word) -> tuple[int, int, int]`, `surf_v4.decode_liquidity(word) -> int`, `surf_v4.price_eth_per_imd(sqrt_price_x96) -> float`; `SurfClient.fetch_pool_v4() -> PoolV4State`.

- [ ] **Step 1: Write the fixture**

`tests/fixtures/surf/v4_pool_state.json` — the exact words read from chain 2026-08-23:

```json
{
  "pool_id": "0xb07d640fd9e2eb9dc81b953c8e4fd006bdfeaf276010fb5418eb763ca15abfb3",
  "slot0_word": "0x0000000027103e83e8012d82000000000000002f6ca7f98ffeb40bbb997d486e",
  "liquidity_word": "0x000000000000000000000000000000000000000000000190c7c60cef771c2ffc",
  "expected": {
    "sqrt_price_x96": 3757351088368496721754945570926,
    "tick": 77186,
    "lp_fee": 10000,
    "liquidity": 7393092836965392068604
  }
}
```

- [ ] **Step 2: Write the failing test**

`tests/data/test_surf_v4.py`:

```python
"""v4 pool state maths.  Pure: no I/O, no network, no addresses."""

import json
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_v4

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures/surf/v4_pool_state.json").read_text()
)


def test_decode_slot0_matches_the_live_word() -> None:
    sqrt, tick, fee = surf_v4.decode_slot0(FIXTURE["slot0_word"])
    assert sqrt == FIXTURE["expected"]["sqrt_price_x96"]
    assert tick == FIXTURE["expected"]["tick"]
    assert fee == FIXTURE["expected"]["lp_fee"]


def test_the_live_pool_is_the_one_percent_tier() -> None:
    """1% is what the dev announced; a decoy at 5-98% must not decode to it."""
    _, _, fee = surf_v4.decode_slot0(FIXTURE["slot0_word"])
    assert fee == 10000


def test_decode_liquidity() -> None:
    assert surf_v4.decode_liquidity(FIXTURE["liquidity_word"]) == (
        FIXTURE["expected"]["liquidity"]
    )


def test_slot_pair_is_base_and_base_plus_three() -> None:
    slot0, liq = surf_v4.pool_state_slots(FIXTURE["pool_id"])
    assert int(liq, 16) - int(slot0, 16) == 3
    assert len(slot0) == 66 and slot0.startswith("0x")


def test_negative_tick_decodes_as_signed() -> None:
    """tick is int24; a pool below 1:1 has a negative tick and must not
    decode as ~16.7 million."""
    word = "0x" + ("000000" + "ffffff" + "0" * 40).rjust(64, "0")
    _, tick, _ = surf_v4.decode_slot0(word)
    assert tick == -1


def test_price_eth_per_imd() -> None:
    """currency0 is native ETH, currency1 is IMD, so sqrtPrice**2 is IMD/ETH."""
    price = surf_v4.price_eth_per_imd(FIXTURE["expected"]["sqrt_price_x96"])
    assert price == pytest.approx(0.00044463, rel=1e-4)


def test_price_of_zero_sqrt_is_none_not_zero() -> None:
    """An unread pool is None; 0.0 would render as a free token."""
    assert surf_v4.price_eth_per_imd(0) is None
```

- [ ] **Step 3: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/data/test_surf_v4.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'maxpane_dashboard.data.surf_v4'`

- [ ] **Step 4: Write the module**

`maxpane_dashboard/data/surf_v4.py`:

```python
"""Uniswap v4 pool-state maths for the surf dashboard.

v4 has no ``slot0()``.  ``PoolManager`` exposes raw storage through
``extsload(bytes32)``, so reading a pool means computing its slot in the
``_pools`` mapping and unpacking the word by hand::

    base   = keccak256(poolId ‖ uint256(6))
    base+0 = sqrtPriceX96 (0-159) | tick (160-183) | protocolFee (184-207) | lpFee (208-231)
    base+3 = liquidity

Pure: no I/O, no addresses, no Textual.  The mapping slot is passed in from
``surf_addresses`` by the caller rather than imported, so this module stays
testable against any pool.
"""

from __future__ import annotations

from maxpane_dashboard.data.keccak import keccak256

_Q96 = 2 ** 96


def pool_state_slots(pool_id: str, mapping_slot: int = 6) -> tuple[str, str]:
    """Return ``(slot0_key, liquidity_key)`` as 0x-prefixed 32-byte hex."""
    raw = bytes.fromhex(pool_id[2:] if pool_id.startswith("0x") else pool_id)
    if len(raw) != 32:
        raise ValueError(f"pool id must be 32 bytes, got {len(raw)}")
    base = int.from_bytes(keccak256(raw + mapping_slot.to_bytes(32, "big")), "big")
    mask = (1 << 256) - 1
    return (
        "0x" + format(base & mask, "064x"),
        "0x" + format((base + 3) & mask, "064x"),
    )


def decode_slot0(word: str) -> tuple[int, int, int]:
    """Unpack ``(sqrtPriceX96, tick, lpFee)``.  ``tick`` is a signed int24."""
    v = int(word, 16)
    sqrt = v & ((1 << 160) - 1)
    tick = (v >> 160) & ((1 << 24) - 1)
    if tick >= 1 << 23:
        tick -= 1 << 24
    lp_fee = (v >> 208) & ((1 << 24) - 1)
    return sqrt, tick, lp_fee


def decode_liquidity(word: str) -> int:
    return int(word, 16)


def price_eth_per_imd(sqrt_price_x96: int | None) -> float | None:
    """ETH per IMD from the pool's sqrt price.

    currency0 is native ETH and currency1 is IMD, so ``(sqrt/2**96)**2`` is
    IMD per ETH and the price we want is its reciprocal.  A zero or missing
    sqrt price is an unread pool: ``None``, never ``0.0``, which would render
    as a free token.
    """
    if not sqrt_price_x96:
        return None
    imd_per_eth = (sqrt_price_x96 / _Q96) ** 2
    if imd_per_eth <= 0:
        return None
    return 1.0 / imd_per_eth
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/data/test_surf_v4.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Prove the tick test bites**

Change `tick -= 1 << 24` to `tick -= 0`, run `test_negative_tick_decodes_as_signed`, confirm it goes RED, restore, confirm GREEN. A silently unsigned tick is a wrong price with no symptom.

- [ ] **Step 7: Write the failing client test**

Append to `tests/data/test_surf_client.py`, following the file's existing raising-transport fixture:

```python
@pytest.mark.asyncio
async def test_fetch_pool_v4_prefers_the_hook_id(monkeypatch) -> None:
    """The live id comes from the hook; the constant is only a fallback."""
    client = _client_with_canned_calls({
        (A.LAUNCHPAD_HOOK, A.SEL_IMD_ETH_POOL_ID): "0x" + "ab" * 32,
        "extsload": (FIXTURE["slot0_word"], FIXTURE["liquidity_word"]),
    })
    state = await client.fetch_pool_v4()
    assert state.pool_id == "0x" + "ab" * 32
    assert state.pool_id_source == "hook"


@pytest.mark.asyncio
async def test_fetch_pool_v4_falls_back_and_says_so() -> None:
    """A failed hook read must not silently pretend the constant is live."""
    client = _client_with_canned_calls({
        (A.LAUNCHPAD_HOOK, A.SEL_IMD_ETH_POOL_ID): None,
        "extsload": (FIXTURE["slot0_word"], FIXTURE["liquidity_word"]),
    })
    state = await client.fetch_pool_v4()
    assert state.pool_id == A.POOL_V4_ID_FALLBACK
    assert state.pool_id_source == "fallback"
```

- [ ] **Step 8: Run, implement `SurfClient.fetch_pool_v4`, run again**

Implement using the client's existing `aggregate3` multicall helper: one round reading `imdEthPoolId()` off the hook, then a second reading both `extsload` slots off `A.POOL_MANAGER_V4`. Every sub-call keeps `allowFailure=True`. Return `PoolV4State` with `None` fields on failure and `pool_id_source` set honestly.

Run: `.venv/bin/python -m pytest tests/data/test_surf_client.py -k pool_v4 -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add maxpane_dashboard/data/surf_v4.py maxpane_dashboard/data/surf_client.py tests/data/test_surf_v4.py tests/data/test_surf_client.py tests/fixtures/surf/v4_pool_state.json
git commit -m "feat(surf): read v4 pool state via extsload

v4 has no slot0(); state comes out of PoolManager._pools by computing the
mapping slot. The pool id is read from LaunchpadHook.imdEthPoolId() and
the vendored constant is a labelled fallback, so a hook outage cannot
silently point the panel at one of the 37 decoy pools.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Task 4: A revert is not a failed read

**Files:**
- Modify: `maxpane_dashboard/data/surf_client.py`
- Test: `tests/data/test_surf_client.py`

**Interfaces:**
- Consumes: `ChainState`.
- Produces: `ChainState.lp_state: str | None` — `"live"`, `"gone"`, or `None`; `ChainState.lp_position_count: int | None`.

- [ ] **Step 1: Write the failing test**

```python
def test_a_revert_is_gone_not_unknown() -> None:
    """positions(1167726) reverts `Invalid token ID`: the contract answered.

    Collapsing that into None renders a completed, announced migration as a
    failed RPC call -- the exact "we looked and there was nothing" versus "we
    could not look" confusion the conventions forbid.
    """
    state = _chain_state_from_multicall_results(
        positions={"success": False, "returnData": _revert("Invalid token ID")},
        owner_of={"success": False, "returnData": _revert("nonexistent token")},
    )
    assert state.lp_state == "gone"
    assert state.lp_liquidity is None


def test_a_transport_failure_is_still_unknown() -> None:
    """No answer at all stays None -- only a revert is evidence."""
    state = _chain_state_from_multicall_results(positions=None, owner_of=None)
    assert state.lp_state is None


def test_a_live_position_is_live() -> None:
    state = _chain_state_from_multicall_results(
        positions={"success": True, "returnData": _positions_words(liquidity=123)},
        owner_of={"success": True, "returnData": _word(A.OPS_WALLET)},
    )
    assert state.lp_state == "live"
    assert state.lp_liquidity == 123
```

Add helpers `_revert(reason)` (ABI-encodes `Error(string)`) and `_positions_words(...)` beside the file's existing decode helpers.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/data/test_surf_client.py -k "revert or transport_failure or position_is_live" -v`
Expected: FAIL — `ChainState` has no attribute `lp_state`

- [ ] **Step 3: Implement**

Add `lp_state: str | None` and `lp_position_count: int | None` to `ChainState` (defaulted so existing constructions keep working), then in the chain fetcher classify:

```python
def _lp_state(positions_result, owner_result) -> str | None:
    """Three outcomes, and the middle one is the point.

    `aggregate3` with allowFailure=True returns success=False for a revert,
    which is an *answer*: the position does not exist. A sub-call that never
    returned at all -- transport error, missing entry -- is unknown.
    """
    if positions_result is None and owner_result is None:
        return None
    reverted = (
        positions_result is not None and not positions_result.get("success")
    )
    if reverted:
        return "gone"
    if positions_result is not None and positions_result.get("success"):
        return "live"
    return None
```

Read `PositionManager.balanceOf(OPS_WALLET)` in the same multicall round for `lp_position_count`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/data/test_surf_client.py -q`
Expected: PASS

- [ ] **Step 5: Prove it bites**

Make `_lp_state` return `None` for the revert case. `test_a_revert_is_gone_not_unknown` must go RED and `test_a_transport_failure_is_still_unknown` must stay GREEN — that pair is what distinguishes the two states. Restore.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/data/surf_client.py tests/data/test_surf_client.py
git commit -m "fix(surf): a revert is a representable state, not a failed read

positions(1167726) reverts 'Invalid token ID' since the 2026-08-17
migration. Mapping that to None made a completed migration render as an
RPC outage.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Task 5: Launchpad and decoy-pool reads

**Files:**
- Modify: `maxpane_dashboard/data/surf_client.py`
- Create: `maxpane_dashboard/analytics/surf_launchpad.py`
- Create: `tests/analytics/test_surf_launchpad.py`
- Create: `tests/fixtures/surf/launchpad_reads.json`, `tests/fixtures/surf/launchpad_logs.json`, `tests/fixtures/surf/v4_initializes.json`
- Test: `tests/data/test_surf_client.py`

**Interfaces:**
- Consumes: Task 1's selectors and topics.
- Produces: `SurfClient.fetch_launchpad() -> LaunchpadState`, `SurfClient.fetch_decoy_pool_count(real_pool_id: str | None) -> tuple[int | None, dict | None]`; `surf_launchpad.rank_coins(launches, swaps, now_ts, limit)`, `surf_launchpad.hot_coin_threshold(swaps_by_coin)`, `surf_launchpad.curve_flow(swaps)`.

- [ ] **Step 1: Capture the fixtures**

Write three fixtures from the values in Global Constraints. `launchpad_logs.json` needs at minimum: 12 `Launched` entries with the real tickers (`ICE`, `GCPU`, `TCC`, `K-256`, `PYCR`, `DAOs`, `ADAM`, `COIN`, `ZALUPA`, …), a spread of `CurveSwap` entries across those coins within a 1 h window, and 3 `ImdBurned` entries. **Include one `Launched` whose ticker is `[/x]`** — that is the markup-injection case, and it must exist in the fixture rather than only in a widget test.

- [ ] **Step 2: Write the failing analytics test**

`tests/analytics/test_surf_launchpad.py`:

```python
"""Launchpad ranking and thresholds.  Pure: no I/O, injected clock."""

import pytest

from maxpane_dashboard.analytics import surf_launchpad as L


def _swaps(**by_coin):
    return dict(by_coin)


def test_hot_threshold_is_three_times_the_median() -> None:
    counts = _swaps(a=1, b=2, c=3, d=4, e=100)
    assert L.hot_coin_threshold(counts) == 9   # median 3 -> 9


def test_hot_threshold_has_a_floor_of_five() -> None:
    """A quiet hour with median 1 must not promote a coin on 3 swaps."""
    counts = _swaps(a=1, b=1, c=1, d=1, e=1)
    assert L.hot_coin_threshold(counts) == 5


def test_no_threshold_below_five_active_coins() -> None:
    """Fewer than 5 coins traded means no meaningful median: OK, not a fire."""
    assert L.hot_coin_threshold(_swaps(a=50, b=1)) is None
    assert L.hot_coin_threshold({}) is None


def test_ranking_is_by_recent_swaps_desc_and_bounded() -> None:
    launches = [
        {"ticker": "A", "name": "Alpha", "creator": "0x1", "ts": 100.0},
        {"ticker": "B", "name": "Beta", "creator": "0x2", "ts": 200.0},
        {"ticker": "C", "name": "Gamma", "creator": "0x3", "ts": 300.0},
    ]
    swaps = [{"coin": "B"}] * 9 + [{"coin": "A"}] * 4 + [{"coin": "C"}]
    rows = L.rank_coins(launches, swaps, now_ts=1000.0, limit=2)
    assert [r["ticker"] for r in rows] == ["B", "A"]
    assert rows[0]["swaps_1h"] == 9
    assert rows[0]["age_s"] == 800.0


def test_a_coin_with_no_swaps_has_none_change_not_zero() -> None:
    """`0%` asserts we measured a flat hour; `None` is 'nothing traded'."""
    launches = [{"ticker": "Q", "name": "Quiet", "creator": "0x9", "ts": 10.0}]
    rows = L.rank_coins(launches, [], now_ts=100.0, limit=5)
    assert rows[0]["swaps_1h"] == 0
    assert rows[0]["change_1h_pct"] is None


def test_ranking_never_reads_the_clock_itself() -> None:
    """now_ts is injected; a module that calls time.time() cannot be tested."""
    import inspect
    assert "time.time()" not in inspect.getsource(L)
```

- [ ] **Step 3: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/analytics/test_surf_launchpad.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 4: Write the analytics module**

`maxpane_dashboard/analytics/surf_launchpad.py`:

```python
"""Launchpad ranking, thresholds and flow aggregates.

Pure functions.  No I/O, no Textual, no ``time.time()`` -- every entry point
takes ``now_ts``.

The HOT COIN threshold is **relative to the hour's own distribution**.  At
~1,170 swaps/day across ~146 coins a fixed "any swap" threshold lights the row
permanently, which is the trap ``signals.py`` documents for ``‹ widen``: a
marker that is always on means nothing.
"""

from __future__ import annotations

import statistics
from typing import Any, Mapping, Sequence

#: A coin is hot at this multiple of the hour's median swap count...
HOT_MULTIPLE = 3
#: ...but never below this floor, so a quiet hour (median 1) cannot promote a
#: coin on 3 swaps.
HOT_FLOOR = 5
#: Below this many active coins there is no meaningful median at all.
HOT_MIN_ACTIVE = 5


def hot_coin_threshold(swaps_by_coin: Mapping[str, int]) -> int | None:
    """Swap count a coin must reach this hour to be HOT, or ``None``.

    ``None`` means "the hour is too thin to judge" and must render OK, not a
    fire: an empty hour is not evidence of a hot coin.
    """
    active = [n for n in swaps_by_coin.values() if n > 0]
    if len(active) < HOT_MIN_ACTIVE:
        return None
    return max(HOT_FLOOR, int(statistics.median(active)) * HOT_MULTIPLE)


def curve_flow(swaps: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate swap rows into the CURVE FLOW panel's numbers."""
    buys = sum(1 for s in swaps if s.get("is_buy"))
    total = len(swaps)
    traders = {s.get("trader") for s in swaps if s.get("trader")}
    return {
        "swap_count": total,
        "trader_count": len(traders),
        "buy_pct": (100.0 * buys / total) if total else None,
        "sell_pct": (100.0 * (total - buys) / total) if total else None,
    }


def rank_coins(
    launches: Sequence[Mapping[str, Any]],
    swaps: Sequence[Mapping[str, Any]],
    now_ts: float,
    limit: int,
) -> list[dict[str, Any]]:
    """Rank launched coins by recent swap count, most active first.

    Ranking happens **from logs alone** -- no per-coin RPC call.  One
    ``getLogs`` over ``CurveSwap`` yields counts for every coin, so cost is
    flat whether the launchpad holds 146 coins or 1,460.  Curve state is read
    only for the rows this function returns.

    ``ticker`` and ``name`` are carried through raw: they are attacker-chosen
    and are escaped at render, not here.
    """
    counts: dict[str, int] = {}
    for swap in swaps:
        coin = swap.get("coin")
        if coin:
            counts[coin] = counts.get(coin, 0) + 1

    rows: list[dict[str, Any]] = []
    for launch in launches:
        ticker = launch.get("ticker")
        ts = launch.get("ts")
        rows.append(
            {
                "ticker": ticker,
                "name": launch.get("name"),
                "creator": launch.get("creator"),
                "creator_known": bool(launch.get("creator_known")),
                "age_s": (now_ts - ts) if isinstance(ts, (int, float)) else None,
                "price_eth": launch.get("price_eth"),
                # No swaps this hour is not a flat hour: None, never 0.0.
                "change_1h_pct": launch.get("change_1h_pct"),
                "swaps_1h": counts.get(ticker, 0),
                "imd_burned": launch.get("imd_burned"),
            }
        )
    rows.sort(key=lambda r: (-r["swaps_1h"], -(r["age_s"] or 0.0)))
    return rows[:limit]
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/analytics/test_surf_launchpad.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Add the client fetchers with a raising transport test**

```python
@pytest.mark.asyncio
async def test_launchpad_fetch_never_touches_the_network_in_tests() -> None:
    client = SurfClient(transport=_RaisesOnUse())
    with pytest.raises(_NetworkTouched):
        await client.fetch_launchpad()


@pytest.mark.asyncio
async def test_decoy_count_excludes_the_real_pool() -> None:
    """38 Initialize logs, one of which is the live pool: 37 decoys."""
    client = _client_with_canned_logs(_load("v4_initializes.json"))
    count, newest = await client.fetch_decoy_pool_count(
        real_pool_id=A.POOL_V4_ID_FALLBACK
    )
    assert count == 37
    assert newest["fee"] == 80000


@pytest.mark.asyncio
async def test_zero_accrued_imd_is_zero_not_none() -> None:
    """A representable zero: 'we looked, nothing accrued'."""
    client = _client_with_canned_calls({(A.LAUNCHPAD_HOOK, A.SEL_IMD_TO_BURN): _word(0)})
    state = await client.fetch_launchpad()
    assert state.imd_to_burn_wei == 0
```

Implement `fetch_launchpad()` (one `aggregate3` over hook + factory + executor getters, one `getLogs` per topic against the **logs** pool, then `rank_coins`) and `fetch_decoy_pool_count()` (one `getLogs` on `TOPIC_V4_INITIALIZE` filtered to `currency1 == IMD`, minus the real pool id). State calls go to publicnode; `eth_getLogs` goes to tenderly/drpc — the standing split.

- [ ] **Step 7: Run and commit**

Run: `.venv/bin/python -m pytest tests/data/test_surf_client.py tests/analytics/test_surf_launchpad.py -q`
Expected: PASS

```bash
git add maxpane_dashboard/analytics/surf_launchpad.py maxpane_dashboard/data/surf_client.py tests/analytics/test_surf_launchpad.py tests/data/test_surf_client.py tests/fixtures/surf/
git commit -m "feat(surf): read the launchpad and count decoy pools

Coins are ranked from CurveSwap logs alone, so cost is flat in the number
of coins; curve state is read only for rendered rows. HOT COIN's threshold
is relative to the hour's own median, with a floor, because a fixed
threshold lights the row permanently at ~1,170 swaps/day.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Task 6: Manager wiring and the detached sweep

**Files:**
- Modify: `maxpane_dashboard/data/surf_manager.py` *(sole owner)*
- Test: `tests/data/test_surf_manager.py`

**Interfaces:**
- Consumes: Tasks 2–5.
- Produces: every payload key from Task 1 Step 7, populated.

- [ ] **Step 1: Write the tripwire test**

```python
@pytest.mark.asyncio
async def test_the_first_payload_is_not_behind_the_launchpad_read() -> None:
    """The sweep is spawned, never awaited.  This fails by timing out.

    Modelled on curator's `_spawn_crosscheck` tripwire: a launchpad read that
    blocks fetch_and_compute would push first paint behind a 146-coin sweep.
    """
    never = asyncio.Event()

    async def _hangs(*_a, **_kw):
        await never.wait()

    manager = _manager_with(fetch_launchpad=_hangs)
    payload = await asyncio.wait_for(manager.fetch_and_compute(), timeout=2.0)
    assert payload["imd_supply"] is not None
    assert payload["launchpad_coin_count"] is None


@pytest.mark.asyncio
async def test_a_failed_sweep_serves_last_good_behind_as_of() -> None:
    """Stale is a marker, not a degraded group -- degradation is for nothing
    to serve at all."""
    manager = _manager_with_last_good(SLOT_LAUNCHPAD, {"coin_count": 146}, at=1000.0)
    payload = await manager.fetch_and_compute()
    assert payload["launchpad_coin_count"] == 146
    assert payload["launchpad_as_of_hhmm"] is not None
    assert "launchpad" not in payload["degraded"]


@pytest.mark.asyncio
async def test_a_failed_sweep_with_nothing_to_serve_degrades() -> None:
    manager = _manager_with_last_good(SLOT_LAUNCHPAD, None)
    payload = await manager.fetch_and_compute()
    assert "launchpad" in payload["degraded"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/data/test_surf_manager.py -k launchpad -v`
Expected: FAIL — `KeyError: 'launchpad_coin_count'`

- [ ] **Step 3: Implement**

Add `_pool_launchpad(tiers, now)` following the shape of `_pool_nft`, gated on `TIER_LAUNCHPAD in tiers`. Spawn it from `_cycle` **without awaiting** — mirror `_spawn_crosscheck`'s task handling, including holding a reference so the task is not garbage-collected and swallowing its exception into the log. Publish every Task 1 key, mapping `PoolV4State` and `LaunchpadState` into the flat dict, and compute:

```python
read["burn_ready"] = (
    accrued is not None
    and min_bridge is not None
    and accrued >= max(min_bridge, 1)
)
```

`burn_ready` is `None` when either input is `None` — "we cannot tell" is not "not ready".

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/data/test_surf_manager.py -q`
Expected: PASS

- [ ] **Step 5: Prove the tripwire bites**

Change the spawn to `await self._pool_launchpad(...)`. `test_the_first_payload_is_not_behind_the_launchpad_read` must fail by **timeout**, not assertion. Restore.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/data/surf_manager.py tests/data/test_surf_manager.py
git commit -m "feat(surf): wire the launchpad tier as a detached sweep

Spawned, never awaited, on the _spawn_crosscheck precedent: first paint
must not sit behind a 146-coin sweep. A failed sweep with last-good to
serve is a stale as-of marker, not a degraded group.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Task 7: Nine detectors

**Files:**
- Modify: `maxpane_dashboard/analytics/surf_signals.py` *(sole owner)*
- Test: `tests/analytics/test_surf_signals.py`

**Interfaces:**
- Consumes: Task 1's keys, `surf_launchpad.hot_coin_threshold`.
- Produces: `sig_decoy_*`, `sig_burnready_*`, `sig_hot_*`; `sig_lp_*` re-aimed at the v4 position.

- [ ] **Step 1: Write the failing tests**

`build_signals(baselines, readings, now_ts)` is **positional** and returns
`(signals, advanced_baselines)` — use the file's existing `_row(name, ...)`
helper style, which already unpacks the tuple:

```python
def _state(name, baselines, readings, now=NOW):
    out, _ = sig.build_signals(baselines, readings, now)
    return out[f"sig_{name}_state"], out[f"sig_{name}_detail"]


def test_lp_move_watches_the_v4_position_not_the_migration() -> None:
    """LP MIGRATION is spent -- it fired, and the migration is finished."""
    state, detail = _state("lp", {"lp_liquidity": 100}, {"lp_liquidity": 90})
    assert state == "fired"
    assert "v4" in detail or "position" in detail


def test_decoy_pool_fires_on_a_new_spoof_pool() -> None:
    state, _ = _state(
        "decoy",
        {"decoy_pool_count": 36},
        {"decoy_pool_count": 37, "decoy_newest_fee_bps": 8000},
    )
    assert state == "fired"


def test_decoy_pool_is_unknown_when_the_scan_failed() -> None:
    """Not OK. An unreadable detector is unknown -- never a clean bill."""
    state, _ = _state("decoy", {}, {"decoy_pool_count": None})
    assert state is None


def test_burn_ready_fires_only_when_both_inputs_read() -> None:
    ready, _ = _state("burnready", {}, {"burn_ready": True, "burn_accrued": 15.06})
    assert ready == "fired"

    unknown, _ = _state("burnready", {}, {"burn_ready": None})
    assert unknown is None

    idle, _ = _state("burnready", {}, {"burn_ready": False, "burn_accrued": 0.0})
    assert idle == "ok"


def test_hot_coin_is_ok_not_fired_on_a_thin_hour() -> None:
    """Fewer than 5 active coins: no meaningful median, so no fire."""
    state, _ = _state("hot", {}, {"launchpad_swaps_by_coin": {"a": 50, "b": 1}})
    assert state == "ok"


def test_hot_coin_detail_is_escaped() -> None:
    """The ticker is attacker-chosen: launch() is permissionless."""
    counts = {f"c{i}": 1 for i in range(5)}
    counts["[/x]"] = 99
    _, detail = _state("hot", {}, {"launchpad_swaps_by_coin": counts})
    assert "[/x]" not in detail


def test_signal_output_keys_grew_to_twenty_seven() -> None:
    """SIGNAL_OUTPUT_KEYS is DERIVED from _DETECTORS, so registering the three
    new detectors is what publishes their keys -- there is no second list to
    keep in step inside this module."""
    assert len(sig.SIGNAL_NAMES) == 9
    assert len(sig.SIGNAL_OUTPUT_KEYS) == 27
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -k "decoy or burn_ready or hot_coin or lp_move" -v`
Expected: FAIL — `KeyError: 'sig_decoy_state'`

- [ ] **Step 3: Implement the three detectors and re-aim LP**

Add `_detect_decoy`, `_detect_burn_ready`, `_detect_hot_coin` beside the existing `_detect_*` functions, each returning the module's `_Det` via `_fired` / `_watch` / `_ok` / `_dead`. Re-aim `_detect_lp` at v4 position liquidity.

**Register them in `_DETECTORS`** — that tuple is the single source, and both `SIGNAL_NAMES` and `SIGNAL_OUTPUT_KEYS` derive from it, so the module can never advertise a key it does not emit:

```python
_DETECTORS: tuple[tuple[str, Any], ...] = (
    ("post", _detect_post),
    ("lp", _detect_lp),
    ("gate", _detect_gate),
    ("deploy", _detect_deploy),
    ("bridge", _detect_bridge),
    ("burn", _detect_burn),
    ("decoy", _detect_decoy),
    ("burnready", _detect_burn_ready),
    ("hot", _detect_hot_coin),
)
```

Order matters: it is render order, and Task 9's `DETECTOR_LABELS` must align 1:1 with it.

Every detail string passes through the module's existing `safe_markup`-and-truncate path — `_detect_hot_coin` is the first detector whose detail contains a *token symbol*, which is the most attacker-controlled string on the dashboard.

> `tests/data/test_surf_models.py::test_signal_output_keys_are_a_subset_of_surf_keys` is the cross-surface guard here: it asserts every derived signal key exists in `SURF_KEYS`. Task 1 adds those nine keys, so it stays green while Task 1 is landed and Task 7 is not — extra keys in `SURF_KEYS` are allowed, missing ones are not. If you are running Task 7 before Task 1, that test is your failure and the fix is Task 1, not a new key here.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add maxpane_dashboard/analytics/surf_signals.py tests/analytics/test_surf_signals.py
git commit -m "feat(surf): add DECOY POOL, BURN READY and HOT COIN; re-aim LP

LP MIGRATION fired and the migration is finished; it becomes LP MOVE
against the v4 position. An unreadable detector is unknown, never OK.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Task 8: Hero row — POOL · LP · BURN · SUPPLY

**Files:**
- Modify: `maxpane_dashboard/widgets/surf/hero.py`
- Test: `tests/test_surf_widgets_a.py`

**Interfaces:**
- Consumes: `pool_venue`, `pool_fee_bps`, `pool_liquidity_usd`, `pool_id_source`, `decoy_pool_count`, `lp_state`, `lp_imd`, `lp_weth`, `lp_owner_ok`, `burn_accrued`, `burn_staged`, `burn_ready`, `imd_burned_cum`, `imd_supply`.
- Produces: nothing consumed downstream except by the screen's queries.

- [ ] **Step 1: Write the failing tests**

```python
def test_lp_card_says_migrated_not_unknown() -> None:
    lines = _lp_lines(lp_state="gone", lp_imd=None, lp_weth=None, lp_owner_ok=None, tier="full")
    text = " ".join(lines)
    assert "migrated" in text
    assert "unknown" not in text and "--" not in text


def test_lp_card_still_says_unknown_on_a_failed_read() -> None:
    lines = _lp_lines(lp_state=None, lp_imd=None, lp_weth=None, lp_owner_ok=None, tier="full")
    assert "migrated" not in " ".join(lines)


def test_pool_card_names_the_venue_and_the_decoys() -> None:
    lines = _pool_lines(pool_venue="v4", pool_fee_bps=10000, pool_liquidity_usd=805927.0,
                        decoy_pool_count=37, pool_id_source="hook", tier="full")
    text = " ".join(lines)
    assert "v4" in text and "1%" in text and "38" in text


def test_pool_card_flags_a_fallback_id() -> None:
    """If the hook read failed the panel must not imply it knows the pool."""
    lines = _pool_lines(pool_venue="v4", pool_fee_bps=None, pool_liquidity_usd=None,
                        decoy_pool_count=None, pool_id_source="fallback", tier="full")
    assert "?" in " ".join(lines) or "unverified" in " ".join(lines)


def test_burn_card_distinguishes_zero_from_unread() -> None:
    zero = _burn_lines(burn_accrued=0.0, burn_staged=0.0, burn_ready=False,
                       imd_burned_cum=3299.0, tier="full")
    unread = _burn_lines(burn_accrued=None, burn_staged=None, burn_ready=None,
                         imd_burned_cum=None, tier="full")
    assert " ".join(zero) != " ".join(unread)
    assert "0" in " ".join(zero)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_surf_widgets_a.py -k "lp_card or pool_card or burn_card" -v`
Expected: FAIL — `_pool_lines` is not defined

- [ ] **Step 3: Implement**

Rename `_hook_lines` to `_pool_lines` and rewrite it; add `_burn_lines`; extend `_lp_lines` with the `lp_state` parameter. Update `SurfHero`'s `update_data` signature, its `data` dict and its four `render_lines_at_tier` lambdas. Keep every existing width tier — the boxes are still quarters of a full-width row and their content budgets have not changed.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_surf_widgets_a.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add maxpane_dashboard/widgets/surf/hero.py tests/test_surf_widgets_a.py
git commit -m "feat(surf): hero becomes POOL / LP / BURN / SUPPLY

HOOK hunted a hooked IMD pool that will never exist -- the dev retracted
the framing on 2026-08-16 and the live pool is hookless. GATE moves to a
detector row; BURN takes its slot.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Task 9: Signals widget — nine rows with quiet-collapse

**Files:**
- Modify: `maxpane_dashboard/widgets/surf/signals.py`
- Test: `tests/test_surf_widgets_a.py`

**Interfaces:**
- Consumes: nine `sig_*` triples.
- Produces: `DETECTOR_LABELS` (9-tuple) — imported by the screen tests and the app-level acceptance tests; never retyped.

- [ ] **Step 1: Write the failing tests**

```python
def test_detector_labels_are_the_nine() -> None:
    assert DETECTOR_LABELS == (
        "NEW POST", "LP MOVE", "GATE OPEN", "NEW DEPLOY", "BRIDGE STAGE",
        "BURN", "DECOY POOL", "BURN READY", "HOT COIN",
    )


def test_no_label_is_longer_than_the_old_widest() -> None:
    """The head is unshrinkable, so a longer label costs panel width.
    `BRIDGE STAGE` (12) was the widest before and must stay the widest."""
    assert max(len(x) for x in DETECTOR_LABELS) == len("BRIDGE STAGE")


def test_ok_rows_fold_into_one_quiet_line() -> None:
    rows = _visible_rows({
        "post": "fired", "lp": "ok", "gate": "ok", "deploy": "ok",
        "bridge": "ok", "burn": "ok", "decoy": "fired", "burnready": "watch",
        "hot": "ok",
    })
    assert "NEW POST" in rows and "DECOY POOL" in rows and "BURN READY" in rows
    assert "6 quiet" in rows


def test_an_unknown_row_never_folds() -> None:
    """The rule curator's rail shipped wrong: a dead detector folded in with
    the OK ones reads confident and green through an outage."""
    rows = _visible_rows({
        "post": "ok", "lp": "ok", "gate": None, "deploy": "ok",
        "bridge": "ok", "burn": "ok", "decoy": "ok", "burnready": "ok",
        "hot": "ok",
    })
    assert "GATE OPEN" in rows
    assert "8 quiet" in rows


def test_all_quiet_still_renders_the_panel() -> None:
    rows = _visible_rows({k: "ok" for k in
                          ("post", "lp", "gate", "deploy", "bridge", "burn",
                           "decoy", "burnready", "hot")})
    assert "9 quiet" in rows
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_surf_widgets_a.py -k "detector_labels or quiet or unknown_row" -v`
Expected: FAIL — `DETECTOR_LABELS` still has 6 entries

- [ ] **Step 3: Implement**

Extend `DETECTOR_LABELS` and `_ROW_KEYS` to nine aligned pairs (`("decoy", "#surf-sig-decoy")`, `("burnready", "#surf-sig-burnready")`, `("hot", "#surf-sig-hot")`), rename the `lp` label to `LP MOVE`, and add the fold. The fold counts **only** rows whose state is exactly `"ok"`; `None` and unknown states always render their own row. Update the module docstring's row budget from 8 lines to "title + spacer + up to 9 rows".

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_surf_widgets_a.py -q`
Expected: PASS

- [ ] **Step 5: Prove the fold bites**

Change the fold predicate from `state == "ok"` to `state in ("ok", None)`. `test_an_unknown_row_never_folds` must go RED. Restore. This is the exact regression the test exists for.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/widgets/surf/signals.py tests/test_surf_widgets_a.py
git commit -m "feat(surf): nine detectors with quiet-collapse

FIRED and WATCH always render; OK rows fold into one dim line. Unknown
rows never fold -- that is the rule curator's rail shipped wrong, where a
dead group rendered as 'none yet' and read green through an outage.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Task 10: Market repoint and launchpad labelling

**Files:**
- Modify: `maxpane_dashboard/widgets/surf/market.py`, `maxpane_dashboard/widgets/surf/activity.py`
- Test: `tests/test_surf_widgets_b.py`

**Interfaces:**
- Consumes: `pool_venue`, `pool_liquidity_usd`, `legacy_pool_liquidity_usd`, `imd_price_usd`, `price_source_disagreement_pct`; `dev_activity` rows.
- Produces: nothing downstream.

- [ ] **Step 1: Write the failing tests**

```python
def test_market_shows_the_v4_pool_and_keeps_v3_as_legacy() -> None:
    lines = _market_lines(pool_venue="v4", pool_liquidity_usd=805927.0,
                          legacy_pool_liquidity_usd=2195.0, tier="full")
    text = " ".join(lines)
    assert "805" in text.replace(",", "") or "806" in text.replace(",", "")
    assert "legacy" in text


def test_market_marks_a_price_source_disagreement() -> None:
    """Two independent keyless sources agree to 0.2% today; 2% is ~10x that."""
    lines = _market_lines(pool_venue="v4", imd_price_usd=1.08,
                          price_source_disagreement_pct=7.4, tier="full")
    assert "?" in " ".join(lines) or "check" in " ".join(lines)


def test_launchpad_hook_renders_as_a_known_label() -> None:
    """It was the dev's most frequent counterparty and rendered as anonymous
    truncated hex through the address-poisoning fallback."""
    row = {
        "ts": 1000.0, "wallet_label": "dev", "kind": "burn",
        "counterparty": "LaunchpadHook", "counterparty_known": True,
        "value_eth": 0.0, "tx_hash": "0x" + "aa" * 32,
    }
    assert "LaunchpadHook" in " ".join(_activity_lines([row], now_ts=2000.0, width=80))


def test_the_kind_vocabulary_did_not_grow() -> None:
    """burnAccruedImd maps onto the existing `burn` kind, so the kind cell's
    width is unchanged and surf's 142 columns are safe.  Shorten the label;
    do not widen the layout."""
    from maxpane_dashboard.data.surf_client import DEV_TX_KINDS
    assert DEV_TX_KINDS == frozenset(
        {"deploy", "lp", "burn", "bridge", "fwa claim", "transfer", "other"}
    )
    assert max(len(k) for k in DEV_TX_KINDS) == len("fwa claim")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_surf_widgets_b.py -k "market_shows or disagreement or launchpad_hook or vocabulary" -v`
Expected: FAIL on the market tests; `test_the_kind_vocabulary_did_not_grow` should PASS immediately — it is a **guard**, and it passing now is the point.

- [ ] **Step 3: Implement**

Repoint `market.py` at the v4 keys, add the dim `legacy pool` line and the disagreement marker. In `activity.py` no width constant changes: `burnAccruedImd` classifies as the existing `burn` kind. Confirm `_KIND_COLS` stays `9`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_surf_widgets_b.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add maxpane_dashboard/widgets/surf/market.py maxpane_dashboard/widgets/surf/activity.py tests/test_surf_widgets_b.py
git commit -m "fix(surf): quote the v4 pool, label the launchpad contracts

The market panel was quoting a drained v3 pool: \$2,195 liquidity against
the live pool's \$805,927. The kind vocabulary is unchanged -- burnAccruedImd
maps onto the existing 'burn' kind, so the kind cell does not widen.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Task 11: Launchpad widgets

**Files:**
- Create: `maxpane_dashboard/widgets/surf/launchpad.py`
- Create: `tests/widgets/test_surf_launchpad_widgets.py`
- Modify: `maxpane_dashboard/widgets/surf/__init__.py`

**Interfaces:**
- Consumes: `launchpad_coins` rows, `launchpad_*` scalars, `burn_*` scalars.
- Produces: `SurfLaunchpadCoins`, `SurfCurveFlow`, `SurfBurnPipeline`, each with `update_data(**kwargs)`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from textual.app import App

from maxpane_dashboard.widgets.surf.launchpad import (
    SurfBurnPipeline, SurfCurveFlow, SurfLaunchpadCoins,
)

HOSTILE = {
    "ticker": "[/x]", "name": "[bold red]pwn[/]", "creator": "0xdead",
    "creator_known": False, "age_s": 60.0, "price_eth": 0.0071,
    "change_1h_pct": 34.0, "swaps_1h": 88, "imd_burned": 142.1,
}


@pytest.mark.asyncio
async def test_hostile_ticker_and_name_never_reach_markup() -> None:
    """launch(string,string) is permissionless: anyone can name a coin `[/x]`.

    Asserted against composited output -- a string that never reaches a pixel
    passes a naive content-string test while being invisible to the user.
    """
    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    async with _A().run_test() as pilot:
        widget = pilot.app.query_one(SurfLaunchpadCoins)
        widget.update_data(coins=[HOSTILE], coin_count=146, as_of_hhmm="01:14")
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join(seg.text for strip in strips for seg in strip)
        assert "pwn" in text          # the value is shown...
        assert "[bold red]" not in text   # ...but never as markup
        assert "[/x]" not in text


@pytest.mark.asyncio
async def test_a_quiet_coin_renders_a_dash_not_zero_percent() -> None:
    quiet = HOSTILE | {"ticker": "Q", "name": "Quiet", "change_1h_pct": None,
                       "swaps_1h": 0}

    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    async with _A().run_test() as pilot:
        widget = pilot.app.query_one(SurfLaunchpadCoins)
        widget.update_data(coins=[quiet], coin_count=1, as_of_hhmm="01:14")
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join(seg.text for strip in strips for seg in strip)
        assert "0%" not in text


@pytest.mark.asyncio
async def test_burn_pipeline_shows_ready_only_when_ready() -> None:
    class _A(App):
        def compose(self):
            yield SurfBurnPipeline()

    async with _A().run_test() as pilot:
        widget = pilot.app.query_one(SurfBurnPipeline)
        widget.update_data(burn_accrued=15.06, burn_staged=0.0, burn_ready=True,
                           burned_total=3299.0, burn_events=66)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        assert "ready" in "\n".join(seg.text for s in strips for seg in s)


@pytest.mark.asyncio
async def test_burn_pipeline_unknown_is_not_ready() -> None:
    class _A(App):
        def compose(self):
            yield SurfBurnPipeline()

    async with _A().run_test() as pilot:
        widget = pilot.app.query_one(SurfBurnPipeline)
        widget.update_data(burn_accrued=None, burn_staged=None, burn_ready=None,
                           burned_total=None, burn_events=None)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        assert "ready" not in "\n".join(seg.text for s in strips for seg in s)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/widgets/test_surf_launchpad_widgets.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement the three widgets**

`maxpane_dashboard/widgets/surf/launchpad.py`. Primitives only — no import from `data/` or `analytics/`. Use `widgets/markup_safety.safe_markup` on `ticker`, `name` and any rendered `creator`, after newline flattening and after truncation. Sparklines, if any, import `widgets/sparkline_common`; do not copy the helpers. Export all three from `widgets/surf/__init__.py`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/widgets/test_surf_launchpad_widgets.py -v`
Expected: PASS

- [ ] **Step 5: Prove the escaping bites**

Remove the `safe_markup` call on `name`. `test_hostile_ticker_and_name_never_reach_markup` must go RED — and note whether it fails as an assertion or as a *crash*, because Textual defers `Text.from_markup` into the message pump and a malformed name raises outside the screen's `try/except`. Restore.

- [ ] **Step 6: Check the template**

`templates/` is the copy-source for new dashboards. Check whether an equivalent table widget there has the same escaping, and whether it has drifted *ahead*. Report what you find; **do not fix another package's file.**

- [ ] **Step 7: Commit**

```bash
git add maxpane_dashboard/widgets/surf/launchpad.py maxpane_dashboard/widgets/surf/__init__.py tests/widgets/test_surf_launchpad_widgets.py
git commit -m "feat(surf): launchpad coins, curve flow and burn pipeline widgets

Ticker and name are attacker-chosen -- launch(string,string) costs only
gas -- so both are escaped and the test asserts against composited output.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Task 12: The `l` view — screen, bindings, CSS

**Files:**
- Modify: `maxpane_dashboard/screens/surf.py` *(sole owner)*
- Modify: `maxpane_dashboard/themes/minimal.tcss` *(sole owner)*
- Test: `tests/screens/test_surf_screen.py`

**Interfaces:**
- Consumes: Tasks 8–11's widgets.
- Produces: `MODE_DASHBOARD`, `MODE_LAUNCHPAD`, `LAUNCHPAD_BODY_ID`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_l_swaps_the_body_and_keeps_the_hero() -> None:
    """Body swap on curator's y/f precedent: the hero never leaves."""
    async with _surf_app().run_test() as pilot:
        await pilot.press("l")
        assert pilot.app.screen.query_one(f"#{LAUNCHPAD_BODY_ID}").display is True
        assert pilot.app.screen.query_one(SurfHero).display is True
        assert pilot.app.screen.query_one("#middle-row").display is False


@pytest.mark.asyncio
async def test_escape_backs_out_one_way() -> None:
    async with _surf_app().run_test() as pilot:
        await pilot.press("l")
        await pilot.press("escape")
        assert pilot.app.screen.query_one("#middle-row").display is True


@pytest.mark.asyncio
async def test_l_is_idempotent_and_toggles_back() -> None:
    async with _surf_app().run_test() as pilot:
        await pilot.press("l")
        await pilot.press("l")
        assert pilot.app.screen.query_one("#middle-row").display is True


@pytest.mark.asyncio
async def test_the_status_hint_names_the_new_view() -> None:
    async with _surf_app().run_test() as pilot:
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join(seg.text for s in strips for seg in s)
        assert "l launchpad" in text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/screens/test_surf_screen.py -k "swaps_the_body or backs_out or idempotent or status_hint" -v`
Expected: FAIL — no `l` binding

- [ ] **Step 3: Implement**

Add `Binding("l", "toggle_launchpad", "Launchpad", show=False)` and `Binding("escape", "show_dashboard", show=False)` to `SurfScreen.BINDINGS`. Add `MODE_DASHBOARD` / `MODE_LAUNCHPAD`, a `_mode` attribute, `_show_mode()` on curator's shape, and compose the launchpad body **hidden** inside a `Vertical(id=LAUNCHPAD_BODY_ID)`. Replace the module docstring's "No `c`" note, which no longer describes the screen.

Add the CSS to **both** `SurfScreen.DEFAULT_CSS` and `themes/minimal.tcss` — the two copies must stay in agreement, edit both or neither. Add an agreement test in the shape of curator's `test_selected_nft_geometry_matches_widget_and_screen_fallback_css`; that exact class of drift shipped as recently as v0.8.2.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/screens/test_surf_screen.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add maxpane_dashboard/screens/surf.py maxpane_dashboard/themes/minimal.tcss tests/screens/test_surf_screen.py
git commit -m "feat(surf): add the l LAUNCHPAD view

Body swap with the hero left in place, esc backs out. `l` matches
curator's meaning -- a full-width table view -- and is free app-wide.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Task 13: Width sweep and documentation

**Files:**
- Modify: `CLAUDE.md`, `README.md` *(sole owner)*
- Test: `tests/screens/test_surf_screen.py`

**Interfaces:**
- Consumes: the assembled screen.
- Produces: the pinned width constants and the binding-panel test.

- [ ] **Step 1: Write the failing sweep**

```python
@pytest.mark.parametrize("width", range(120, 175))
@pytest.mark.asyncio
async def test_the_launchpad_body_is_whole_from_its_pinned_width(width) -> None:
    """Start the sweep away from the pin: a sweep that began at the constant
    would agree with it by construction."""
    async with _surf_app(width=width).run_test() as pilot:
        await pilot.press("l")
        await pilot.pause()
        title = _title_text(pilot)
        if width >= SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS:
            assert "‹ widen" not in title
        else:
            assert "‹ widen" in title


@pytest.mark.asyncio
async def test_the_launchpad_binding_panel_is_the_coins_table() -> None:
    """Pinned by a test, not by a sentence in CLAUDE.md."""
    widths = await _measure_panels(mode="launchpad")
    assert max(widths, key=widths.get) == "SurfLaunchpadCoins"


@pytest.mark.asyncio
async def test_the_default_view_still_clears_at_the_app_wide_width() -> None:
    """Nothing in this change may move FULL_LAYOUT_COLUMNS."""
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS
    assert FULL_LAYOUT_COLUMNS == 143
    async with _surf_app(width=FULL_LAYOUT_COLUMNS).run_test() as pilot:
        await pilot.pause()
        assert "‹ widen" not in _title_text(pilot)
```

- [ ] **Step 2: Run the sweep and read the real number**

Run: `.venv/bin/python -m pytest tests/screens/test_surf_screen.py -k pinned_width -v`

The sweep **tells you** the number; it is not chosen. Set `SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS` to the lowest width at which the marker clears, then re-run to green.

> If the default view now exceeds 143, **do not raise `FULL_LAYOUT_COLUMNS`.**
> Find the widened cell and shorten its content. The likely candidates are the
> hero's new BURN copy and the market's `legacy pool` line, in that order.

- [ ] **Step 3: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: 4,988 + the new tests, all green. Investigate any failure in `tests/test_app_startup.py` or `tests/test_cli_game_choices.py` immediately — surf is `GAMES[0]` and the `--game` default, so it is the dashboard prefetched at launch.

- [ ] **Step 4: Update the docs**

In `CLAUDE.md`:
- the surf keys line gains `l launchpad`;
- the surf width paragraph records the `l` body's measured number and states explicitly whether the app-wide 143 moved (**if it did not, do not append to the 198 → 172 → 143 → 176 → 152 → 143 record** — that record tracks the app-wide number only);
- the Conventions section gains the shortening rule: *when a new value would widen a sized cell, shorten the value; moving `FULL_LAYOUT_COLUMNS` is reserved for when no honest short name exists*;
- the dashboard-two description notes the v4 migration and the launchpad view.

In `README.md`: the surf keys and the view list.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md tests/screens/test_surf_screen.py
git commit -m "docs(surf): pin the launchpad width and record the shortening rule

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AkbWnHkoXYpuQ6W7Jw4kyW"
```

---

## Self-Review Notes

**Spec coverage.** §2 → Tasks 3–5 (evidence becomes fixtures). §3 → Task 1. §4 → Task 3. §5 → Tasks 2, 6. §6.1 → Task 8. §6.2 → Tasks 4, 8. §6.3 → Task 10. §6.4 → Task 10. §7 → Tasks 6, 8, 11. §8 → Tasks 5, 11, 12. §9 → Tasks 7, 9. §10 → Task 13. §11 → distributed. §12 → nothing, correctly.

**Type consistency.** Four API errors were caught reading the real modules and are
fixed above; they would each have failed on first run:

| Error | Corrected to |
|---|---|
| `SURF_PAYLOAD_KEYS` | `SURF_KEYS` (`surf_models.py:261`) |
| `tests/test_surf_signals.py` | `tests/analytics/test_surf_signals.py` |
| `build_signals(base=, read=, now_ts=)` returning a dict | positional `(baselines, readings, now_ts)` returning `(signals, advanced_baselines)` |
| detectors added ad hoc | registered in `_DETECTORS`, which derives `SIGNAL_NAMES` and `SIGNAL_OUTPUT_KEYS` |

Cross-task names verified consistent: `PoolV4State` fields (Task 1) against Task 3's
tests; `ChainState.lp_state` (Task 4) against Task 8's `_lp_lines`; `rank_coins`'
row keys (Task 5) against `SURF_ROW_KEYS["launchpad_coins"]` (Task 1) and Task 11's
`HOSTILE` fixture; `_DETECTORS` order (Task 7) against `DETECTOR_LABELS` order
(Task 9); `LAUNCHPAD_BODY_ID` (Task 12) against its own test.

**One spec assumption was refuted during planning and the plan reflects it.** §6.4 warned that new activity kinds could widen the kind cell past surf's 142 columns. `DEV_TX_KINDS` already contains `"burn"`, so `burnAccruedImd` needs **no new kind** and the cell cannot widen. Task 10 Step 1 turns that into a standing guard (`test_the_kind_vocabulary_did_not_grow`) rather than a measurement risk. The width sequencing worry that shaped the task order is therefore smaller than stated — but Task 13's sweep still runs, because the `l` body is new and the hero copy did change.
