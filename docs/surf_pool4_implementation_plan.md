# surf `p` POOL4 view — implementation plan

Master plan for `docs/surf_pool4_PRD.md`. Research of record:
`docs/imd_pool4_mechanics.md` — **every selector, event topic0 and decoded transaction is
tabulated there and is not restated here.** When a work package below says "the selector
table", it means that document's *Recovered interface* and *Events* sections. A number quoted
twice is a number that drifts.

House conventions apply unchanged and are not re-derived: freeze the contract first, one owner
per shared file, report-don't-fix across an ownership boundary, `.venv/bin/python -m pytest`,
prove-it-bites, never `git checkout --` a file. Read `CLAUDE.md` and
`.claude/skills/terminal-layout/SKILL.md` before starting any package.

**What this build is.** A **third body** on `SurfScreen`, on the surf `l` / curator `y`/`f`
precedent. `p` swaps the dashboard body for POOL4's five panels, `escape` backs out one-way,
the hero row stays mounted.

**What this build is NOT.** Not a ninth dashboard. **`app.py`, `__main__.py` and
`screens/game_select.py` are untouched. There is no six-surface renumber. No manager is added
to `MaxPaneApp`, so none of the four `MANAGER_ATTRS` copies changes** — that non-change is
verified, not assumed (WP8). No signing, no calldata for a state change, no keys, no API key,
no hardcoded split, no hardcoded mainnet address.

---

## 0. FROZEN DATA CONTRACT

**This section is the interface.** WP0 lands it as code; every other package builds against it
and against nothing else. Widgets receive only `str` / `int` / `float` / `bool` / `dict` /
`list[dict]`. A failed read is `None`, never `0`. A representable zero is `0`, never `None`.

### 0.1 Where the keys live

`POOL4_KEYS` is a tuple in `data/surf_models.py`, spliced into `SURF_KEYS` as one contiguous
block after the launchpad block. `SurfManager.fetch_and_compute()` returns **exactly**
`SURF_KEYS` under every failure combination, as it does today. Two new row shapes join
`SURF_ROW_KEYS`.

**Every key is spelled with its full `pool4_` prefix in the widget kwargs too.** This is a
deliberate departure from the launchpad panels, which take `as_of_hhmm` short and rely on
`tests/widgets/test_surf_widget_contract._PREFIXED_KWARG_ALIASES`. That alias maps one kwarg
name onto one contract key; a second body whose panels also took `as_of_hhmm` would make one
kwarg name stand for two different keys and the alias would silently stop proving anything.
**No new alias is added, and no pool4 widget goes on `_SHORT_KWARG_WIDGETS`.** WP8 pins that
decision with a test.

### 0.2 Scalar keys (45)

#### Network, discovery and addresses — rendered by `SurfPool4Hatches` (+ titles everywhere)

| key | type | `None` means |
|---|---|---|
| `pool4_network` | `str \| None` | closed vocabulary `"SEPOLIA"` / `"MAINNET"`. `None` = no sweep has ever completed. Every panel title renders `· <word>`, and `· —` on `None` — a panel title never goes networkless |
| `pool4_as_of_hhmm` | `str \| None` | the POOL4 tier's own slower clock. `None` = nothing has ever landed. **Advances only when new data actually lands**, never on a tick that found nothing new |
| `pool4_discovery_state` | `str \| None` | closed vocabulary `"not-discovered"` / `"adopted"` / `"rejected"`. `None` = discovery has not run |
| `pool4_discovery_detail` | `str \| None` | one line of pattern language: which gate a candidate failed, or what was adopted and when. Third-party-derived → escaped at render |
| `pool4_hook_addr` | `str \| None` | the adopted (mainnet) or vendored (Sepolia) hook. `None` = undiscovered |
| `pool4_token_addr` | `str \| None` | IMD on the active network |
| `pool4_vault_addr` | `str \| None` | read **off the hook**, never scraped. `None` = hook did not name one |
| `pool4_dripper_addr` | `str \| None` | `rewardsRecipient()`. `None` = unread |

#### `THE SPLIT` — rendered by `SurfPool4Split`

| key | type | `None` means |
|---|---|---|
| `pool4_measured_inference_pct` | `float \| None` | computed from the live counters, never quoted |
| `pool4_measured_burn_pct` | `float \| None` | ditto |
| `pool4_measured_stakers_pct` | `float \| None` | ditto |
| `pool4_reward_share_bps` | `int \| None` | `rewardShareBps()` — the *claimed* share |
| `pool4_bps_denominator` | `int \| None` | `BPS_DENOMINATOR()` |
| `pool4_split_drift_bps` | `float \| None` | measured stakers share minus claimed, in bps. `None` when either side is unread. **`0.0` is the healthy value and must render as such, not as a dash** |
| `pool4_total_burned` | `float \| None` | whole IMD |
| `pool4_total_rewarded` | `float \| None` | whole IMD |
| `pool4_total_fee_token` | `float \| None` | whole IMD |
| `pool4_retained_eth` | `float \| None` | whole ETH |
| `pool4_last_claim_block` | `int \| None` | |
| `pool4_unsettled_burn` | `float \| None` | accrued-but-unsettled burn leg. `0.0` = settled up to date |
| `pool4_unsettled_stakers` | `float \| None` | ditto, staker leg |

#### `THE RATCHET` — rendered by `SurfPool4Ratchet`

| key | type | `None` means |
|---|---|---|
| `pool4_tokens_in_pool` | `float \| None` | the reserve, whole IMD |
| `pool4_cap_floor` | `float \| None` | **the observed floor, labelled as inferred** (see §5) |
| `pool4_floor_distance` | `float \| None` | reserve − floor, whole IMD. May be negative; a negative is real and renders |
| `pool4_floor_distance_pct` | `float \| None` | distance as % of the floor. `None` when the floor is 0 or unread — never an infinity |
| `pool4_burned_supply_pct` | `float \| None` | `total_burned / total_supply * 100` |
| `pool4_total_supply` | `float \| None` | whole IMD |
| `pool4_reserve_series` | `list[list[float]] \| None` | `[[ts, imd], …]`, oldest first. `[]` = swept and empty. **No sentinel is ever appended**; see §5 for the network-splice hazard |
| `pool4_eth_in_pool` | `float \| None` | whole ETH |
| `pool4_position_liquidity` | `float \| None` | raw uint128 L |
| `pool4_current_tick` | `int \| None` | |
| `pool4_ref_tick` | `int \| None` | |
| `pool4_backstop_centred` | `bool \| None` | tri-state. `None` must never render as "centred" nor as a confident "not centred" |

#### `sIMD VAULT` — rendered by `SurfPool4Vault`

| key | type | `None` means |
|---|---|---|
| `pool4_share_price` | `float \| None` | `convertToAssets(1e18) / 1e18`, whole IMD per share |
| `pool4_share_price_delta_pct` | `float \| None` | change since the session baseline. `None` until a second reading exists — never `0.0` as a stand-in |
| `pool4_vault_assets` | `float \| None` | TVL, whole IMD |
| `pool4_vault_shares` | `float \| None` | whole sIMD |
| `pool4_drip_per_day` | `float \| None` | `dripRatePerSecond() * 86400`, whole IMD |
| `pool4_drippable` | `float \| None` | whole IMD |
| `pool4_can_drip` | `bool \| None` | tri-state |
| `pool4_backlog_imd` | `float \| None` | the dripper's own IMD balance |
| `pool4_backlog_days` | `float \| None` | `backlog / drip_per_day`. **`None` when the rate is 0 or unread — never an infinity** |
| `pool4_implied_apr_pct` | `float \| None` | derived from `drip_per_day` and TVL only, **never from fee flow**. `None` when TVL is 0 or unread — never an infinity |

### 0.3 Row keys (2)

`SURF_ROW_KEYS["pool4_flow"]` — `pool4_flow` is `list[dict] | None`; **`None` = the read
failed, `[]` = swept and genuinely quiet.** Newest first, capped at `POOL4_FLOW_LIMIT = 25` by
the manager.

| field | type | note |
|---|---|---|
| `ts` | `float \| None` | epoch |
| `age_s` | `float \| None` | precomputed by the manager — **the screen and the widget are clock-free** |
| `side` | `str` | closed, producer-owned: `"buy"` / `"sell"` |
| `size_imd` | `float \| None` | IMD in on a sell, IMD out on a buy |
| `burned_imd` | `float` | `ClaimsSettled[0]`. **`0.0` on a buy — a representable zero, never `None`** |
| `stakers_imd` | `float` | `ClaimsSettled[1]`. Same rule |
| `fee_imd` | `float \| None` | `FeeCollected` IMD leg; `None` when the fee was taken in ETH |
| `fee_eth` | `float \| None` | `FeeCollected` ETH leg; `None` when the fee was taken in IMD |
| `settled` | `bool` | `False` = accrued, `ClaimsSettled` has not paid it yet |
| `tx_hash` | `str \| None` | |

`SURF_ROW_KEYS["pool4_hatches"]` — `pool4_hatches` is `list[dict] | None`; `None` = unread,
`[]` is never emitted (the BOND row always exists).

| field | type | note |
|---|---|---|
| `scope` | `str` | closed: `"vault"` / `"dripper"` / `"hook"` / `"bond"` |
| `label` | `str` | closed, producer-owned: `"owner"` / `"paused"` / `"rescue"` / `"market"` / `"rebalance"` / `"burn sink"` / `"rewards"` / `"deployed"` |
| `state` | `str` | closed: `"live"` / `"renounced"` / `"paused"` / `"open"` / `"closed"` / `"absent"` / `"unknown"` |
| `detail` | `str \| None` | free text, third-party-derived → escaped at render |
| `addr` | `str \| None` | rendered through `_fmt.long_addr` |
| `addr_known` | `bool` | `KNOWN_LABELS` allowlist only — never a fallback, never a prefix match |

### 0.4 Widget constructor and update signatures

All five are `textual.containers.Vertical` subclasses with `__init__(self, *args, **kwargs)` —
**no required constructor argument**, so the screen composes them bare and the contract sweep
can instantiate every one of them with no args. Each exposes exactly one public method:

```
SurfPool4Flow.update_data(
    pool4_flow=None, pool4_network=None, pool4_as_of_hhmm=None, **_kwargs) -> None

SurfPool4Split.update_data(
    pool4_network=None,
    pool4_measured_inference_pct=None, pool4_measured_burn_pct=None,
    pool4_measured_stakers_pct=None, pool4_reward_share_bps=None,
    pool4_bps_denominator=None, pool4_split_drift_bps=None,
    pool4_total_burned=None, pool4_total_rewarded=None,
    pool4_total_fee_token=None, pool4_retained_eth=None,
    pool4_last_claim_block=None, pool4_unsettled_burn=None,
    pool4_unsettled_stakers=None, pool4_as_of_hhmm=None, **_kwargs) -> None

SurfPool4Ratchet.update_data(
    pool4_network=None, pool4_tokens_in_pool=None, pool4_cap_floor=None,
    pool4_floor_distance=None, pool4_floor_distance_pct=None,
    pool4_burned_supply_pct=None, pool4_total_supply=None,
    pool4_reserve_series=None, pool4_eth_in_pool=None,
    pool4_position_liquidity=None, pool4_current_tick=None,
    pool4_ref_tick=None, pool4_backstop_centred=None,
    pool4_as_of_hhmm=None, **_kwargs) -> None

SurfPool4Vault.update_data(
    pool4_network=None, pool4_share_price=None,
    pool4_share_price_delta_pct=None, pool4_vault_assets=None,
    pool4_vault_shares=None, pool4_drip_per_day=None, pool4_drippable=None,
    pool4_can_drip=None, pool4_backlog_imd=None, pool4_backlog_days=None,
    pool4_implied_apr_pct=None, pool4_as_of_hhmm=None, **_kwargs) -> None

SurfPool4Hatches.update_data(
    pool4_hatches=None, pool4_network=None, pool4_discovery_state=None,
    pool4_discovery_detail=None, pool4_hook_addr=None, pool4_token_addr=None,
    pool4_vault_addr=None, pool4_dripper_addr=None,
    pool4_as_of_hhmm=None, **_kwargs) -> None
```

**Every one of the 45 scalar keys and both row keys has exactly one renderer above.** Nothing
joins `_KEYS_WITHOUT_A_RENDERER`. `**_kwargs` is mandatory on all five: the screen splats and a
future key must not raise.

### 0.5 Module boundaries frozen with the keys

| module | may import | may **not** import |
|---|---|---|
| `data/surf_pool4.py` | stdlib, `data/keccak.py`, `data/surf_v4.py` | `httpx`, `textual`, anything that reads a clock, `data/surf_client.py` |
| `data/surf_pool4_client.py` | `httpx` (lazily, via `OwnedHttpClient`), `data/surf_pool4.py`, `data/surf_addresses.py` | `textual`, `widgets/` |
| `widgets/surf/pool4_*.py` | `widgets/surf/_fmt.py`, `widgets/surf/_rowfit.py`, `widgets/markup_safety.py`, `widgets/sparkline_common.py` | `data/`, `analytics/` (no pool4 widget needs an analytics module; the allowlist stays at `analytics.surf_feed`) |

---

## 1. Dependency DAG

```
 ── wave 0 ─ (all three start immediately, no dependencies) ────────────────
 ┌───────────────────────────┐ ┌──────────────────────────┐ ┌────────────────────────┐
 │ WP0 CONTRACT FREEZE       │ │ WP1 FIXTURE CORPUS       │ │ WP2 ROW-FIT HOIST      │
 │ Backend Architect         │ │ Evidence Collector       │ │ Senior Developer       │
 │ data/surf_models.py       │ │ tests/fixtures/surf/pool4│ │ widgets/surf/_rowfit.py│
 └───────────┬───────────────┘ └───────┬──────────────────┘ └──────────┬─────────────┘
             │                         │                              │
      ┌──────┴──────┬──────────────────┼──────────────┐               │
      ▼             ▼                  │              ▼               ▼
 ── wave 1 ────────────────────────────┼──────────────────────────────────────────────
 ┌─────────────────────┐  ┌────────────┴─────────┐  ┌───────────────────────────────┐
 │ WP3 PURE LAYER      │  │ WP4 RAIL WIDGETS     │  │ WP5 LEFT WIDGETS              │
 │ AI Engineer         │  │ Frontend Developer   │  │ Frontend Developer            │
 │ data/surf_pool4.py  │  │ Ratchet/Vault/Hatches│  │ Flow (RichLog) + Split        │
 └──────────┬──────────┘  └──────────┬───────────┘  └──────────┬────────────────────┘
            │                        │                         │
            ▼                        │                         │
 ── wave 2 ──────────────────────────┼─────────────────────────┼────────────────────
 ┌─────────────────────────────┐     │                         │
 │ WP6 CHAIN CLIENT            │     │                         │
 │ Backend Architect           │     │                         │
 │ data/surf_pool4_client.py   │     │                         │
 └──────────┬──────────────────┘     │                         │
            ▼                        │                         │
 ── wave 3 ──────────────────────────┼─────────────────────────┼────────────────────
 ┌─────────────────────────────┐     │                         │
 │ WP7 MANAGER + CACHE TIER    │     │                         │
 │ Backend Architect           │     │                         │
 │ surf_manager.py, surf_cache │     │                         │
 └──────────┬──────────────────┘     │                         │
            └───────────┬────────────┴─────────────────────────┘
                        ▼
 ── wave 4 ────────────────────────────────────────────────────────────────────────
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ WP8 SCREEN WIRING, LAYOUT SWEEP, SHARED-FILE OWNER  [Senior Developer]   │
 │ screens/surf.py · themes/minimal.tcss · widgets/surf/__init__.py         │
 │ tests/screens/test_surf_screen.py · tests/test_surf_registration.py      │
 │ tests/widgets/test_surf_widget_contract.py · the 4 MANAGER_ATTRS copies  │
 └──────────────────────────────┬───────────────────────────────────────────┘
                                ▼
 ── wave 5 ────────────────────────────────────────────────────────────────────────
 ┌──────────────────┐ ┌───────────────────┐ ┌──────────────────────────────────────┐
 │ WP9 REVIEW       │ │ WP10 DOCS         │ │ WP11 MAINNET SWITCH  [BLOCKED]       │
 │ code-reviewer    │ │ Technical Writer  │ │ Evidence Collector +                 │
 │                  │ │                   │ │ Test Results Analyzer                │
 └──────────────────┘ └───────────────────┘ └──────────────────────────────────────┘
```

**Edges that matter, and why:**

- `WP0 → WP3/WP4/WP5/WP6/WP7` — the keys, row shapes and widget signatures are the whole
  interface. Nothing starts until WP0 signs off.
- `WP1 → WP3/WP6/WP7` — decoders and the client are tested against committed payloads only.
  WP1 is not on the critical path *for WP4/WP5*: the widgets build against synthetic payloads
  shaped by WP0.
- `WP2 → WP5` — `SurfPool4Flow` imports the shared `_budget`/`_row_cols` ladder. WP5 cannot
  start until the hoist exists, and **must not copy it if WP2 is late** (that is exactly the
  three-copy divergence CLAUDE.md names).
- `WP3 → WP6` — the client calls the pure builders/decoders and the fingerprint gate.
- `WP6 → WP7` — the manager wires the client's methods into a detached tier.
- `WP4 + WP5 + WP7 → WP8` — the screen dispatches real keys to real widgets and then, and only
  then, sweeps the layout.

**No edge into `app.py`, `__main__.py`, `screens/game_select.py`, `analytics/`,
`data/surf_client.py`, `data/surf_addresses.py`, or `sybilkit/`.** All out of scope.

---

## 2. Wave schedule

| wave | runs concurrently | waits on | gate to leave the wave |
|---|---|---|---|
| **0** | WP0 ∥ WP1 ∥ WP2 | — | WP0: `POOL4_KEYS` importable, key-count test green, existing full suite unaffected (additive only). WP1: Sepolia launch-3 corpus committed + a `not-yet-discovered` announce-channel corpus. WP2: `_rowfit.py` exists, `test_surf_widgets_b.py` and `test_surf_launchpad_activity.py` green **unchanged** |
| **1** | WP3 ∥ WP4 ∥ WP5 | WP0 (all); WP2 (WP5); WP1 (WP3) | WP3: pure module green incl. the adversarial discovery suite, purity test green. WP4/WP5: five widgets render three payload phases (cold / healthy / degraded) against composited output, width ladders pinned in both directions |
| **2** | WP6 alone | WP3 + WP1 | client green against `httpx.MockTransport` fixtures; structural no-live-socket test green; Sepolia and mainnet pools proven separate |
| **3** | WP7 alone | WP6 | detached-tier tripwire green (fails by timeout), degradation matrix green, last-good/`as of` marker semantics proven, one-in-flight proven |
| **4** | WP8 alone | WP4 + WP5 + WP7 | `p`/`escape` idempotent, `‹ taller` alive on the new body, CSS mirrored, **width and height pins measured and swept in both directions**, `WORST_CASE_TITLE_COLUMNS` re-measured, full suite green |
| **5** | WP9 ∥ WP10; WP11 when mainnet lands | WP8 | review findings filed (never fixed by the reviewer); docs updated; mainnet path verified against real captures |

**Critical path:** `WP0 → WP3 → WP6 → WP7 → WP8` — five stages. WP4/WP5 ride the UI branch and
are validated end-to-end at WP8.

---

## 3. Work packages

### WP0 — contract freeze  ·  Backend Architect

**Owns, exclusively:** `maxpane_dashboard/data/surf_models.py`.

**Does:**
- Adds `POOL4_KEYS` (§0.2, 45 keys) and splices it into `SURF_KEYS` as one commented block.
- Adds `SURF_ROW_KEYS["pool4_flow"]` and `["pool4_hatches"]` (§0.3).
- Adds the wire-level dataclasses the client will return — `Pool4HookState`,
  `Pool4VaultState`, `Pool4DripperState`, `Pool4FlowEvent`, `Pool4Discovery` — **wei-native**,
  matching the module's existing convention (the flat dict is the presentation boundary and
  `_cycle` divides exactly once).
- Adds `POOL4_FLOW_LIMIT = 25` beside the existing `FEED_ITEM_LIMIT` family.
- Writes `docs/surf_pool4_contract.md`: §0 of this plan, verbatim, as the hand-off other
  packages read.

**Does NOT:** touch `surf_manager.py`, `surf_cache.py`, any widget, any screen.

**Tests it writes** (`tests/data/test_surf_pool4_models.py`):
- every `POOL4_KEYS` member appears in `SURF_KEYS` exactly once, and the block is contiguous;
- `POOL4_KEYS` has no duplicates and no key without the `pool4_` prefix;
- both new row-key tuples are non-empty, and every field named in §0.3 is present;
- the dataclasses are wei-native: no field ending `_imd`/`_eth` that is not `_wei`-suffixed
  where it holds a raw chain quantity.

**Acceptance:** `POOL4_KEYS` importable; the existing full suite is unaffected (this package
only adds names — `_finalise` logs keys *outside* `SURF_KEYS`, so an added key is inert until a
producer fills it).

---

### WP1 — fixture corpus  ·  Evidence Collector

**Owns, exclusively:** `tests/fixtures/surf/pool4/**`, `scripts/capture_pool4.py`.

**Starts immediately.** Network-capable, standalone, keyless, no code contract to respect.

**Captures, from the live Sepolia launch-3 deployment** (addresses in the mechanics doc's cast;
hook `0xa1B997…6840`, token `0xB37d54…Cc82`, vault `0x1600E1…17cc`, dripper `0x4dBE17…449B`,
PoolManager `0xE03A10…3543`):

| fixture | what it is |
|---|---|
| `hook_state_healthy.json` | one batched `eth_call` round over the whole recovered getter set |
| `hook_state_partial.json` | the same round with three getters reverting — the "unverified contract answered some of it" case |
| `vault_state.json`, `dripper_state.json` | verified-source contracts, full getter round |
| `flow_logs_mixed.json` | a `getLogs` page containing **at least one BUY, one SELL, one settlement and one accrual-without-settlement**, decoded from the transactions named in the mechanics doc |
| `flow_logs_empty.json` | a swept-and-quiet window — the `[]`-not-`None` case |
| `pool_slot0.json` | `PoolManager.extsload` words for the pool id, for `surf_v4.decode_slot0` |
| `announce_undiscovered.json` | the announce channel **as it is today**: no mainnet pool4 post. This is the day-one path |
| `announce_adversarial_*.json` | six hostile channel corpora — see WP3 |
| `mainnet_absent.json` | mainnet `eth_call` responses proving no hook/vault/dripper exists |

**Rules:** every capture is committed raw JSON with the request that produced it recorded in a
sibling `.request.json`; no capture is hand-edited except the adversarial ones, which are
labelled `synthetic: true` in-file and carry the attack they encode in a `note` field.

**Acceptance:** `.venv/bin/python scripts/capture_pool4.py --dry-run` replays every committed
fixture without a socket; the corpus covers cold, healthy, partial and dead for all four
contracts.

**Blocked half:** the mainnet captures. See §6.

---

### WP2 — row-fit hoist  ·  Senior Developer

**Owns, exclusively:** `maxpane_dashboard/widgets/surf/_rowfit.py` (new),
`maxpane_dashboard/widgets/surf/activity.py`, `maxpane_dashboard/widgets/surf/launchpad_activity.py`.

This package exists because the PRD forbids a fourth copy: `_budget` / `_row_cols` /
`_tier_for` already exist three times in `widgets/surf/`, and the `len()`-vs-`cell_len()` bug
they share therefore has to be fixed three times. **Two steps, two commits, in this order:**

**Step 1 — pure move.** Lift `_GAP`, `_row_cols`, `_budget` and the tier-selection helper into
`widgets/surf/_rowfit.py` with no behaviour change. `activity.py` and `launchpad_activity.py`
import them; their per-panel column constants (`_WALLET_COLS`, `_KIND_COLS`, `ADDR_COLS`,
`FULL_WIDTH`, `WIDEN_HINTS`) **stay in their own modules** — those are per-panel measurements,
not shared machinery. Acceptance: `tests/widgets/test_surf_widgets_b.py` and
`tests/widgets/test_surf_launchpad_activity.py` pass **unmodified**. If a test needs editing,
the move was not pure.

**Step 2 — `cell_len` fit.** `_row_cols` / `_budget` measure with `rich.cells.cell_len`, not
`len()`. Acceptance: a new test in `tests/widgets/test_surf_rowfit.py` renders a row carrying a
CJK counterparty label and an emoji, asserts against composited output that the row does not
exceed the panel width, and is **proven to bite** — it must be red before the fix and green
after, recorded in the WP report.

**Note for the reviewer:** the committed activity/launchpad fixtures are ASCII, so step 2
cannot move `SURF_FULL_LAYOUT_COLUMNS`, `SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS` or
`ACTIVITY_FIRST_FULL_TERMINAL`. WP2 asserts that explicitly rather than assuming it: re-run
the existing width sweeps and record that no pin moved.

**Does NOT:** touch any pool4 file, any screen, any stylesheet.

---

### WP3 — the pure layer  ·  AI Engineer (strict TDD)

**Owns, exclusively:** `maxpane_dashboard/data/surf_pool4.py`,
`tests/data/test_surf_pool4.py`, `tests/data/test_surf_pool4_discovery.py`.

**Depends on:** WP0 (dataclasses), WP1 (fixtures).

**Contains, and nothing else — no I/O, no clock, no Textual:**

1. **Selector and topic constants**, transcribed from the mechanics doc's *Recovered interface*
   and *Events* tables. Each constant carries the doc's own words for what the operands
   provably are; the three unresolved topic0s keep their operand-shaped names and a comment
   saying the pre-image was not found. **Do not invent a signature string for them.**
2. **The permission-flag gate**, expressed as named constants and never as a magic `0x840`:
   ```
   HOOK_FLAG_BEFORE_ADD_LIQUIDITY = 1 << 11
   HOOK_FLAG_AFTER_SWAP           = 1 << 6
   HOOK_FLAG_MASK                 = (1 << 14) - 1
   POOL4_REQUIRED_FLAGS = HOOK_FLAG_BEFORE_ADD_LIQUIDITY | HOOK_FLAG_AFTER_SWAP
   ```
   `has_pool4_flags(addr) -> bool` is `int(addr, 16) & HOOK_FLAG_MASK == POOL4_REQUIRED_FLAGS`
   — **equality, not a subset test.** A subset test admits a hook that also sets
   `AFTER_SWAP_RETURNS_DELTA`, which is a materially different contract.
3. **`candidate_addresses(rows) -> list[str]`** — the provenance gate. Takes announce-channel
   rows (the `feed_items` row shape the manager already produces) and returns candidates from
   **self-posts only** (`from_addr == to_addr == ANNOUNCE`, case-insensitive). Replies and
   inbound txs are never scanned. Returns EIP-55-normalised, deduplicated, order-preserving.
4. **`fingerprint_verdict(addr, answers, expected_token) -> (state, detail)`** — the second
   gate, pure over already-fetched `eth_call` answers. Returns `"adopted"` only when *all*
   hold: flags equal; `rewardShareBps()`, `BPS_DENOMINATOR()`, `burnSink()`, `token()`,
   `poolManager()` all answered; `token()` equals the known mainnet IMD
   `0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7`. Anything less returns `"rejected"` with a
   detail naming the *first* failed gate.
5. **Calldata builders and response decoders** for the hook, vault, dripper and the flow logs.
   The v4 pool half **reuses `data/surf_v4.pool_state_slots` / `decode_slot0` and
   `data/keccak.py` and does not re-implement either** — a test asserts `surf_pool4` contains
   no local keccak and no local slot derivation.
6. **The maths**, all total functions that never raise and never return an infinity:
   `measured_split`, `split_drift_bps`, `floor_distance`, `backlog_days`, `implied_apr_pct`,
   `share_price_delta_pct`, `unsettled_legs`.

**Tests it writes:**

*Correctness* — decoders round-trip every WP1 fixture; `measured_split` reproduces the
mechanics doc's 1.00 / 89.10 / 9.90 **from the committed counters**, and a mutated counter set
moves it (the test must not be able to pass by quoting the doc); the four zero-denominator
paths (`floor_distance_pct`, `backlog_days`, `implied_apr_pct`, `split_drift_bps`) all return
`None` and never `inf`/`nan`.

*Adversarial discovery — the security suite, and it is not optional* (see §5):

| case | must produce |
|---|---|
| a reply containing a valid-looking `0x…840` address | no candidate at all (provenance gate) |
| an inbound tx from a stranger to the channel, same content | no candidate |
| a self-post whose address ends `840` but whose `token()` is a stranger's ERC-20 | `"rejected"`, detail names `token` |
| a self-post whose address ends `840` and answers nothing | `"rejected"`, detail names the first dead getter |
| a self-post whose address sets `840` **plus** a RETURNS_DELTA bit | `"rejected"` (equality, not subset) |
| a self-post carrying twenty addresses, one of them valid | the valid one only; the other nineteen never reach a getter call |
| a self-post carrying `0x` + 40 chars of markup (`[/x]`) | no crash, no candidate |
| a **persisted** discovery payload hand-edited to `"adopted"` with a hostile address | re-verified on read, not trusted (mirrors the curator `pattern_language()` precedent: a cache file is third-party input too) |

*Purity* — an AST walk asserting `surf_pool4` imports nothing from `httpx`, `textual`,
`aiohttp`, `time`, `datetime`, or `data.surf_client`.

**Acceptance:** every adversarial case green and each proven to bite (invert the gate, watch
*that* test go red, restore); zero network; zero clock.

---

### WP4 — rail widgets  ·  Frontend Developer

**Owns, exclusively:** `maxpane_dashboard/widgets/surf/pool4_ratchet.py`,
`pool4_vault.py`, `pool4_hatches.py`, `tests/widgets/test_surf_pool4_rail.py`.

**Depends on:** WP0 only. Builds against synthetic payloads shaped by §0.

**Builds** `SurfPool4Ratchet`, `SurfPool4Vault`, `SurfPool4Hatches` — three label/value
panels on `widgets/surf/launchpad.SurfCurveFlow`'s shape (a `Vertical` holding one `Static`,
`text-wrap: nowrap; text-overflow: ellipsis`), **plus the reserve sparkline in RATCHET through
`widgets/sparkline_common`, imported and never copied.**

**Contract details this package owns:**
- Every panel title ends `· <NETWORK WORD>`, and `· —` when `pool4_network is None`. This is a
  rendered interface string: export it as a module constant and assert against composited
  output, not against the content string.
- The floor is labelled **observed**, not guaranteed — `floor (observed) 250.00M` or
  equivalent. A test greps the composited RATCHET body for the word and asserts the words
  `guarantee`/`guaranteed`/`enforced` never appear.
- Every tri-state (`pool4_can_drip`, `pool4_backstop_centred`) renders three distinct words
  and `None` shares no substring with either confident answer — `SurfBurnPipeline._ready_word`'s
  precedent (`ready` / `not yet` / `unknown`, deliberately not `NOT READY`).
- `pool4_backlog_days` renders as *days of runway*, and the panel says the yield is
  rate-limited rather than flow-limited. A raw balance alone is a review failure.
- `pool4_implied_apr_pct is None` renders the suppressed state, never `∞`, never `0%`.
- All third-party strings (`detail`, `addr`) go through
  `widgets/markup_safety.safe_markup`; the `Static` receives a **pre-built
  `rich.text.Text`**, never a markup string (CLAUDE.md's `SurfFeed._row_text` rule).

**Tests it writes:** cold (all-`None`) / healthy / partial payloads rendered and asserted
against `_compositor.render_strips()`, **joining segments per row first, then rows by
newline**; a width ladder per panel with each threshold asserted in **both** directions; the
forbidden-word scan; a `[/x]`-bearing `detail` and a `[$warning]`-bearing `addr` that must not
raise `MarkupError`; a no-args `update_data()` sweep.

**Does NOT:** touch `widgets/surf/__init__.py` (WP8 owns it), `screens/surf.py`,
`themes/minimal.tcss`, or any other WP's widget module. Defects found in WP5's modules are
**reported, not fixed**.

---

### WP5 — left-column widgets  ·  Frontend Developer

**Owns, exclusively:** `maxpane_dashboard/widgets/surf/pool4_flow.py`,
`pool4_split.py`, `tests/widgets/test_surf_pool4_left.py`.

**Depends on:** WP0 and **WP2** (`_rowfit`).

**Builds** `SurfPool4Flow` — a `RichLog(wrap=False)` panel on `widgets/surf/activity.py`'s
shape, importing `_budget` / `_row_cols` from `widgets/surf/_rowfit.py`. **Copying that ladder
is a review failure**; if `_rowfit` is missing, this package is blocked, not licensed to
duplicate.

Column ladder, widest tier first, each tier naming what it shed on the panel's own title
(`WIDEN_HINTS` idiom, with the `SHORT_HINT` fallback for widths too narrow to say it in words):

| col | source | note |
|---|---|---|
| age | `age_s` → `_fmt.fmt_age` | precomputed; the widget is clock-free |
| side | `side` | `BUY` / `SELL`, closed vocabulary, cell sized to the widest member exactly |
| size | `size_imd` → `_fmt.fmt_imd` | |
| burned | `burned_imd` | **`0.00` on a buy, never a dash** |
| stakers | `stakers_imd` | same |
| inference | `fee_imd` or `fee_eth` | in the currency it was taken in; the cell carries the unit |

**The load-bearing rule for this panel:** a buy has no burn and no staker leg, and that is a
*representable zero*. `None` is reserved for `pool4_flow is None` — the whole-panel unavailable
state, rendered as its own explicit line. The test that pins this asserts that a buy row and a
degraded panel produce **different composited text**. This is the FARM/HOUR-SAVED defect
CLAUDE.md records, and it is the single most likely way this panel ships wrong.

**Builds** `SurfPool4Split` — a label/value `Static` panel showing the measured percentages,
the four counters, `lastClaimBlock`, and the unsettled legs. **The measured split is rendered
from the payload's measured keys only**; a test asserts the literals `89.1`, `9.9` and `1.0`
appear nowhere in the module source. When `pool4_split_drift_bps` is non-zero the panel says
so in its own words and the drift line is the most prominent thing on it.

**Tests it writes:** as WP4, plus the buy-zero-vs-degraded test above; a
`pool4_flow=[]`-vs-`None` test (quiet ≠ unavailable); a `RichLog` fitting test proving no row
is ever narrowed at write time (build a row wider than the log, assert it was withheld or
fitted, never silently shrunk); the row-shape test asserting every fixture row matches
`SURF_ROW_KEYS["pool4_flow"]` exactly.

**Does NOT:** touch `widgets/surf/__init__.py`, `activity.py`, `launchpad_activity.py`,
`_rowfit.py`, the screen or the stylesheet.

---

### WP6 — the chain client  ·  Backend Architect

**Owns, exclusively:** `maxpane_dashboard/data/surf_pool4_client.py`,
`tests/data/test_surf_pool4_client.py`.

**Depends on:** WP3 (builders/decoders/gates), WP1 (fixtures).

**A new client module, deliberately not an extension of `surf_client.py`.** `surf_client.py`
is a 3,200-line shared file with its own owner and its own mainnet endpoint pools; co-owning it
across this build is how a merge conflict becomes a silent endpoint change.

**Builds `Pool4Client(OwnedHttpClient)` with four endpoint pools, not two:**

```
SEPOLIA_STATE_RPCS   — batched eth_call
SEPOLIA_LOG_RPCS     — archive eth_getLogs; publicnode is BANNED here
MAINNET_STATE_RPCS   — reuse surf_client.STATE_RPC_PRIMARY / _FALLBACKS values
MAINNET_LOG_RPCS     — reuse surf_client.LOG_RPCS values
```

Values are re-declared in this module rather than imported, matching the repo's
redundancy-plus-an-agreement-test pattern; a test asserts the mainnet lists agree with
`surf_client`'s, and that `_BANNED_RPC_HOSTS` is honoured on both networks. **State and logs
need different pools** — `ethereum-rpc.publicnode.com` refuses archive `eth_getLogs`, and the
Sepolia equivalent is assumed to do the same until measured.

**Methods:** `verify_hook(addr, *, network)`, `fetch_hook_state`, `fetch_vault_state`,
`fetch_dripper_state`, `fetch_flow_logs(from_block, to_block)`, `fetch_pool_slot0(pool_id)`.
Each returns its WP0 dataclass or `None`; **`None` means "we could not read", never "zero"**,
and a partial answer degrades field-by-field (the `NftStats.transfers_24h`-beside-a-healthy-
`holders` granularity this repo already uses).

**RPC error classification is on message text, not code** — providers reuse `-32602`/`-32005`
for unrelated meanings, and one provider's suggested-retry range decrements one block per round
trip and livelocks anything following it verbatim. Reuse `surf_client`'s pattern tuples by
transcription, with an agreement test.

**Tests it writes:** every method against `httpx.MockTransport` over WP1 fixtures; a
**structural** no-network test — any `httpx.AsyncClient` constructed in a test without an
explicit `transport=` is a live socket (`tests/test_fwa_guardrails.py`'s precedent, adapted);
a transport that raises on use, injected, proving the failure path returns `None` and does not
raise; the four-pool separation test (a Sepolia call must never reach a mainnet URL and vice
versa — assert on the URLs the mock transport was actually handed); the banned-host test; the
livelock test (a provider that decrements one block per round trip must be abandoned, not
followed).

---

### WP7 — manager and cache tier  ·  Backend Architect

**Owns, exclusively:** `maxpane_dashboard/data/surf_manager.py`,
`maxpane_dashboard/data/surf_cache.py`, `tests/data/test_surf_manager_pool4.py`,
`tests/data/test_surf_cache_pool4.py`.

**Depends on:** WP6.

**Cache additions:** `TIER_POOL4`, `SLOT_POOL4`, and the reserve series. TTL on the curator
`TIER_ANALYSIS` / surf `TIER_LAUNCHPAD` precedent: a long tier with a shorter failure backoff,
its own last-good, its own `as of`.

**The series is namespaced by network.** `SERIES_POOL4_RESERVE_SEPOLIA` and
`SERIES_POOL4_RESERVE_MAINNET` are two series, and `pool4_reserve_series` publishes the one
matching `pool4_network`. A single series would splice a testnet history onto a mainnet one at
the switchover and draw a sparkline of two different chains. A test asserts the two never
interleave across a simulated switch.

**Manager additions**, mirroring `_spawn_launchpad` / `_launchpad_detached` /
`_pool_launchpad` / `_launchpad_payload` exactly:
- `SOURCE_POOL4 = "p4"` — **two characters, deliberately**, for `SOURCE_LAUNCHPAD = "pad"`'s
  reason: the title bar renders every degraded member verbatim on a `height: 1` `Static` with
  no ellipsis. See §5.
- `_spawn_pool4` — **spawned, never awaited**; one sweep in flight at a time; the tier stays
  due while a sweep runs so a slow read cannot stack behind a fast poll.
- Discovery runs first, off the channel rows `_pool_channel` already produced — **no new
  request for the announce channel** — through `surf_pool4.candidate_addresses` and then
  `Pool4Client.verify_hook`. Only a `"rejected"`-free verdict switches `pool4_network` to
  `"MAINNET"`. A persisted adopted address is **re-verified on read**, never trusted.
- Last-good semantics: nothing is stored on a blank read, so the slot keeps its previous
  payload *and its previous timestamp* — the marker goes stale, which is the true statement,
  rather than a fresh marker over dashes.
- Degradation: `p4` reaches `_degraded()` **only when there is nothing to serve at all**;
  otherwise a stale `pool4_as_of_hhmm` is the signal. Same rule as `pad`.
- `pool4_share_price_delta_pct` baseline is held in the manager, seeded on the first successful
  read of a session, and **reset when `pool4_network` changes** — a Sepolia baseline under a
  mainnet share price is a fabricated number.
- The clock is injected everywhere (`now=` / `now_ts`); nothing in this module calls
  `time.time()` internally on the pool4 path.

**Tests it writes:**
- `test_the_first_payload_is_not_behind_the_pool4_read` — the tripwire, **which fails by
  timing out**, on `test_the_first_payload_is_not_behind_the_analysis_read`'s exact shape.
- one-sweep-in-flight (a second cycle during a slow sweep must not start a second task);
- the degradation matrix: each of {discovery dead, hook dead, vault dead, dripper dead, logs
  dead, all dead} × {last-good present, absent} → the exact `degraded` list and the exact
  `pool4_as_of_hhmm` (advanced or not);
- **the marker never advances on a tick that found nothing new** — mutate the payload to be
  identical, assert the `hhmm` string is unchanged;
- no sentinel reaches the reserve series: a failed read must leave the series untouched, and
  a `0` must never be appended (mutate the guard, watch *that* test redden);
- the full `SURF_KEYS` contract still holds under every failure combination;
- the network-switch test: a simulated Sepolia→mainnet adoption swaps the series, resets the
  share-price baseline, and changes every panel's network word in one payload.

---

### WP8 — screen wiring, layout sweep, shared-file owner  ·  Senior Developer

**Sole owner of every shared file in this build:**

| file | why it is here |
|---|---|
| `maxpane_dashboard/screens/surf.py` | the third body, `p`/`escape`, `_show_mode`, `_SCROLL_COLUMNS`, `KEY_HINTS`, the two new pins |
| `maxpane_dashboard/themes/minimal.tcss` | every screen rule must be mirrored property-for-property |
| `maxpane_dashboard/widgets/surf/__init__.py` | the five new exports + the package docstring table |
| `tests/screens/test_surf_screen.py` | `SURF_WIDGET_SIGNATURES`, the width/height sweeps, the CSS-agreement test, `WORST_CASE_TITLE_COLUMNS` |
| `tests/test_surf_registration.py` | the composite "every panel reaches the compositor" assertions |
| `tests/widgets/test_surf_widget_contract.py` | the derived sweep + the "no new kwarg alias" pin |
| `tests/test_app_startup.py`, `tests/test_game_select_quit.py`, `tests/test_curator_registration.py` | **the other three `MANAGER_ATTRS` copies — owned but expected unchanged** |

**Depends on:** WP4, WP5, WP7.

**Does:**

1. `MODE_POOL4 = "pool4"` beside `MODE_DASHBOARD` / `MODE_LAUNCHPAD`. `_show_mode` becomes a
   three-way and `_SCROLL_COLUMNS` **gains a `MODE_POOL4` entry**. Omitting that entry is the
   exact 2026-08-25 defect: `_rail_is_cut` would answer for a hidden container and `‹ taller`
   would be dark across the whole new body at every height. A test asserts the marker lights on
   the pool4 body.
2. `POOL4_BODY_ID`, `POOL4_LEFT_ID`, `POOL4_RAIL_ID` exported constants; the body composed
   **once and hidden by `display`**, so the first `p` paints a complete frame.
3. `Binding("p", "toggle_pool4", …)`; `action_toggle_pool4` idempotent (a second `p` returns to
   the dashboard, curator's `action_toggle_analysis` precedent); `escape` returns to the
   dashboard from **either** alternate body.
4. Dispatch: all 45 scalar keys + 2 row keys to the five panels, **each in its own `try`**, on
   every refresh whether or not `p` is showing — a body that starts rendering only when it
   becomes visible is blank for a beat after the keypress.
5. `KEY_HINTS = "[dim]l launchpad · p pool4[/]"` — **one markup run**, not a letter-only `[dim]`
   split, or the two halves land in separate `Segment`s that never share a composited line and
   the app-level acceptance grep for the contiguous phrase fails.
6. **The two new pins, measured in situ and swept:**
   - `SURF_POOL4_FULL_LAYOUT_COLUMNS` and `SURF_POOL4_FULL_LAYOUT_ROWS`, their own constants
     with their own `#:` reasoning blocks. Not derived from the launchpad's 138/31 and not
     assumed equal to them.
   - The sweep runs **118..152** — comfortably below and above, and never starting at 138 or at
     whatever the pin lands on, so it cannot agree with a neighbouring pin by construction.
   - The pin must land at or under `__main__.FULL_LAYOUT_COLUMNS` (143). If it does not,
     **shorten a value, do not raise the pin** — the standing rule.
   - The binding panel is named by a test (`test_the_pool4_binding_panel_is_…`), not by a
     sentence. A seam whose binding panel clips in silence is **disqualified**: RATCHET, VAULT
     and HATCHES are plain label/value `Static`s that ellipsise quietly, so if the rail binds,
     the seam is wrong. Prefer a seam where the marked FLOW panel binds.
   - `scrollbar-gutter: stable` on **both** columns, `overflow-y: auto` on both, a `min-height`
     on every `1fr` child, and exactly one `1fr` child per column (FLOW on the left, HATCHES in
     the rail).
7. **Re-measure `WORST_CASE_TITLE_COLUMNS`.** `SOURCE_POOL4` is a seventh degraded group, and
   the title bar's worst case is currently 139 against a 143 pin — `, p4` costs four columns and
   lands it *exactly* on the pin. Measure it; do not compute it. If it exceeds
   `SURF_FULL_LAYOUT_COLUMNS`, shorten the copy.
8. Measure the status-bar hint against `StatusBar`'s own left-label budget at the full layout
   width. `l launchpad · p pool4` is longer than what shipped; it is not assumed to fit.
9. Mirror every new screen rule into `themes/minimal.tcss` and re-run the property-by-property
   agreement test.
10. Confirm the **non-changes**: `app.py`, `__main__.py`, `screens/game_select.py` untouched;
    all four `MANAGER_ATTRS` copies unchanged and
    `test_every_copy_of_manager_attrs_names_every_manager_the_app_builds` green.

**Tests it writes/extends:** the width sweep in both directions (set the pin one too low and
one too high, confirm each reddens — a one-directional width test would have missed the defect
that shipped here before); the height sweep against a **full-length** flow payload, since the
committed capture is the small case on both axes; the mode-toggle idempotence tests; the
`‹ taller` test on the new body; the dispatch test comparing recorded kwargs against
`SURF_WIDGET_SIGNATURES`; the CSS agreement test; the no-new-alias test; a test that the first
`p` keypress composites a full frame (nothing blank).

---

### WP9 — review  ·  `feature-dev:code-reviewer`

Scoped pass over WP0–WP8. **A review never fixes what it finds** — findings go on a named
follow-up list with their evidence, including findings in the reviewer's own earlier work.
Verification *is* allowed and expected: flip a constant, monkeypatch a cell, render at a width,
then restore and confirm the tree is clean.

**Mandated checks:** the eight adversarial discovery cases each bite; the width test reddens in
both directions; the "marker does not advance on an unchanged tick" test reddens when the guard
is removed; the buy-zero-vs-degraded distinction survives a mutation; `rg -n "89\.1|9\.9|1\.0%"
maxpane_dashboard/widgets/surf/pool4_*.py` returns nothing; `rg -n "0x840"
maxpane_dashboard/data/surf_pool4.py` returns nothing (named constants only); every fixture is
committed and no test opens a socket.

---

### WP10 — documentation  ·  Technical Writer

**Owns:** `README.md`, `CLAUDE.md` (the surf row, the keys paragraph, the body-swap paragraph),
`.claude/skills/terminal-layout/SKILL.md` (the pin table gains two rows),
`docs/surf_pool4_implementation_evidence.md`.

**Depends on:** WP8 for the measured numbers. **Quotes no number this plan or the PRD guessed**
— every pin, every threshold and every worst-case column count comes from WP8's recorded sweep.

Must state, in CLAUDE.md's own voice: `p` is a third body on `SurfScreen`, not a ninth
dashboard; the network word is on every panel title and why; `capFloor` is inferred; the
discovery fingerprint is a security boundary.

---

### WP11 — mainnet switch verification  ·  Evidence Collector + Test Results Analyzer

**BLOCKED on the mainnet deployment landing.** See §6.

Captures the real announce post that names the mainnet hook, the real mainnet hook/vault/
dripper state, and the real flow logs; commits them as fixtures; replays the whole discovery
path against them; and confirms the network word flips, the series switches, the share-price
baseline resets, and no Sepolia number survives the switch anywhere on screen.

---

## 4. Test plan

**These constraints are not per-package advice. They are the acceptance bar for every package
in this build.**

1. **No test may touch the network, and it is asserted structurally.** Inject an `httpx`
   transport that raises on use; assert the failure path returns `None` rather than raising.
   `tests/test_fwa_guardrails.py`'s "an `AsyncClient` constructed without an explicit
   `transport=` is a live socket" check is transcribed for `Pool4Client`.
2. **Every external payload is a committed fixture** under `tests/fixtures/surf/pool4/`.
   Nothing is generated at test time from a live read, and the adversarial fixtures are
   labelled synthetic in-file with the attack they encode.
3. **Layout assertions go against composited output** via `app.screen._compositor.render_strips()`,
   **joining segments per ROW first and then rows by newline.** Joining every segment with a
   newline splits one painted row into several apparent lines the moment a row carries two
   styles, and a test written that way passes while the user sees something else.
4. **A width test must fail in both directions.** Set the pin too low and too high; confirm
   each reddens; record both in the WP report. Sweep the boundary, never a comfortable width.
   Prefer asserting a property (*whenever a row would clip, the marker is lit*) over a literal
   (*the marker lights below 35*) — the literal goes stale silently.
5. **The clock is injected.** `now=` on cache loaders, `now_ts` on anything deriving an age.
   No module a test needs to control calls `time.time()` internally. Every age reaching a
   widget is precomputed by the manager, so any captured instant replays forever.
6. **Prove a test bites.** Mutate the code, watch the test go red, **check which test reddened**
   — a mutation that reddens a neighbouring test proves nothing about the one under
   examination — restore, and record it. Mandatory for: the `cell_len` fix (WP2), every
   adversarial discovery case (WP3), the detached-read tripwire and the no-sentinel guard
   (WP7), the width pin in both directions (WP8).
7. **Parallel agents run only their own test files, never the suite.** The full suite (~11 min,
   5,630 tests) runs at the WP8 gate and again at the WP9 gate, and nowhere else.
8. **`.venv/bin/python -m pytest`**, never the system `python3`.

**New test files, by owner:**

| file | owner |
|---|---|
| `tests/data/test_surf_pool4_models.py` | WP0 |
| `tests/widgets/test_surf_rowfit.py` | WP2 |
| `tests/data/test_surf_pool4.py`, `tests/data/test_surf_pool4_discovery.py` | WP3 |
| `tests/widgets/test_surf_pool4_rail.py` | WP4 |
| `tests/widgets/test_surf_pool4_left.py` | WP5 |
| `tests/data/test_surf_pool4_client.py` | WP6 |
| `tests/data/test_surf_manager_pool4.py`, `tests/data/test_surf_cache_pool4.py` | WP7 |
| extensions to `tests/screens/test_surf_screen.py`, `tests/test_surf_registration.py`, `tests/widgets/test_surf_widget_contract.py` | WP8 |

---

## 5. Risks

### R1 — The hook is UNVERIFIED source. Its interface is *recovered*, not read.

Every getter name, every argument order and three of the eight event signatures come from
`PUSH4` selector recovery, Openchain lookups and log-set decoding — **not from source**. Three
topic0s have no known pre-image at all and are named for what their operands provably are.

*What can go wrong:* a getter that answers on Sepolia reverts on mainnet because the mainnet
hook is a different build; an operand order that is right for the Sepolia bytecode and wrong
for mainnet's; a "counter" that is something else.

*Controls:* (a) **field-by-field degradation** — a reverting getter is one `None` field inside
an otherwise-healthy payload, never a dead panel; (b) the mechanics doc's table is the single
source and is referenced, never copied, so a correction lands once; (c) **cross-checks that the
chain can settle**: Σ`FeeCollected` IMD legs must equal `totalFeeToken()`, Σ`ClaimsSettled[0]`
must equal `totalBurned()`, Σ`ClaimsSettled[1]` must equal `totalRewarded()`. WP7 computes all
three and **publishes the disagreement rather than the assumption** — a mismatch means the
recovered interface is wrong on this deployment, and the SPLIT panel is where it shows.
*Severity: high. Likelihood: medium. Detectable on day one via (c).*

### R2 — `capFloor`'s meaning is INFERRED, not proven.

It is deduced from launch 1 coming to rest at 48,849,555 against a 50,000,000 floor. Nothing in
source says a floor stops the burn.

*Control:* the number is labelled **observed floor** on screen, never *guaranteed*, and WP4
carries a forbidden-word test for `guarantee`/`guaranteed`/`enforced` in the RATCHET body. The
distance-to-floor line is presented as a distance, not as a promise. **Do not add a "safe until"
or "burns stop at" phrasing** — that is the claim the chain has not made.
*Severity: medium (a reputational/analytical error, not a crash). Likelihood: it is already
true. Fully mitigated by copy.*

### R3 — The announce channel is attacker-writable. The discovery gate is a security boundary.

Anyone can send the channel a UTF-8 calldata tx and six community replies are already in it. A
`0x…` scraped from the feed is **untrusted input**, and the failure mode is rendering an
attacker's contract as the protocol's — with the reader's own money decision behind it.

*Controls, and both are required:* provenance (`from == to == channel`, self-posts only) and
fingerprint (flag equality, five getters answering, `token()` == the known mainnet IMD). Then:
`rewardsRecipient()` and the vault/dripper are read **off the adopted hook**, never scraped, so
a single adoption is the only trust decision in the chain. A persisted adoption is
**re-verified on read** — a hand-edited cache file is third-party input, on the curator
`pattern_language()` precedent.

*Its own adversarial suite is mandatory* — the eight cases in WP3 — and each must be proven to
bite. A green discovery suite that cannot fail is worse than no suite: it is the exact
"verification claim" failure recorded in this project's memory.
*Severity: critical. Likelihood: low but adversarial, i.e. it happens when someone chooses.
This is the package to review hardest.*

### R4 — The not-yet-discovered path is what actually runs on day one.

**There is no pool4 hook, vault or dripper on mainnet.** So on the day this ships, the code
that executes is: discovery finds nothing → `pool4_network == "SEPOLIA"` → every panel title
says SEPOLIA → the numbers on screen are testnet numbers.

*This is the primary path, not the edge case,* and it must be the **best-tested** path, not an
afterthought. Concretely:
- WP1's `announce_undiscovered.json` is captured **first**, before any healthy-mainnet fixture;
- WP3's very first test is "an announce corpus with no pool4 post yields no candidate and
  `not-discovered`";
- WP8's first screen test renders the whole body in the undiscovered state and asserts the word
  SEPOLIA on **all five** panel titles;
- WP9 reviews the undiscovered path before the adopted one.

The related hazard: a testnet number on an unmarked panel is not merely stale, it is
**fictional presented as live**. The network word is therefore in the panel title — not a
footnote, not a status-bar mention — and its absence is a hard test failure, not a cosmetic one.
*Severity: high. Likelihood: certain.*

### R5 — The seventh degraded group lands the title bar exactly on its pin.

`_title_line` renders every `degraded` member verbatim on a `height: 1` wrapping `Static` —
past the first line, text reaches no pixel at all: no `…`, no scrollbar, no trace.
`WORST_CASE_TITLE_COLUMNS` is 139 today against `SURF_FULL_LAYOUT_COLUMNS = 143`, and `, p4`
costs four columns. **That is 143 exactly — zero margin.** WP8 measures it rather than
computing it, and if it goes over, the copy shortens. This is also why `SOURCE_POOL4` is
spelled `"p4"` and not `"pool4"`.
*Severity: medium (silently truncates the one row that exists to say something is down).
Likelihood: high without the explicit measurement step.*

### R6 — The reserve series can splice two chains into one sparkline.

A single `pool4_reserve` series would carry Sepolia points until the switchover and mainnet
points after it, and the RATCHET sparkline would draw a continuous line across two different
tokens on two different chains. Mitigated by two network-namespaced series (WP7) and a test
that they never interleave. The same hazard applies to `pool4_share_price_delta_pct`'s session
baseline, which resets on a network change.
*Severity: medium. Likelihood: certain at the switchover if not designed for.*

### R7 — Three copies of the row-fit ladder become four.

If WP2 slips, WP5 is tempted to copy `_budget`/`_row_cols` into `pool4_flow.py`. That is a
fourth copy of a helper whose known `len()`-vs-`cell_len()` bug already has to be fixed three
times. **WP5 is blocked, not licensed to duplicate.** Sequencing WP2 into wave 0, with no
dependencies of its own, is the mitigation.

### R8 — Sepolia endpoint availability is unmeasured.

The mainnet pools are known-good and their dead endpoints are recorded. The Sepolia
equivalents are not. WP6 must **measure** which Sepolia endpoints batch `eth_call` and which
serve archive `eth_getLogs`, record the result beside the constants, and add anything dead to
the banned list with its symptom. Do not assume the mainnet split transfers.

### R9 — Verified-source contracts are the easy half, and that is a trap.

`StakedIMD` and `RewardDripper` are verified and their semantics are certain; the hook is not.
The temptation is to build the vault and dripper panels well and the ratchet/split panels
optimistically. The reverse is correct: **the two panels reading the unverified contract need
the most degradation testing**, because they are the ones whose reads can be wrong rather than
merely absent.

---

## 6. What can start now, and what is blocked

**Expected within ~24h:** the mainnet pool4 deployment. That expectation changes almost
nothing about the schedule, because the view is specified to *discover* rather than to be
configured.

**Start immediately — no dependency on the deployment (WP0 through WP10, i.e. every package
that builds the feature):**

- WP0, WP1 (Sepolia half), WP2 — wave 0, today.
- WP3, WP4, WP5 — as soon as WP0/WP2 sign off.
- WP6, WP7, WP8, WP9, WP10 — the whole critical path. **None of them needs the mainnet
  contracts to exist.** Every one of them is tested against committed fixtures, and the
  undiscovered path (R4) is the day-one behaviour they must get right.

**Blocked on the deployment landing:**

- **WP1's mainnet half** — the real announce post, the real mainnet hook/vault/dripper state
  and the real flow logs. Until then WP1 commits `announce_undiscovered.json` (the true current
  state) and `mainnet_absent.json` (proof nothing is there), which are the fixtures the primary
  path is tested against anyway.
- **WP11 entirely** — the switch verification.
- **The `adopted` fixtures in WP3's suite** are *synthetic until then*, clearly labelled, and
  re-run against the real capture at WP11. A synthetic adoption fixture is fine for proving the
  gate logic; it is not evidence about the real hook, and WP11 is where that evidence arrives.

**What must NOT happen while waiting:** hardcoding a mainnet address "temporarily", relaxing
either discovery gate to make a synthetic fixture pass, or shipping a panel that renders a
Sepolia number without its network word. All three are the failure this view exists to prevent.

**One thing to watch during the wait:** the dev was still doing `setPeer` /
`setEnforcedOptions` / `send` on mainnet IMD at 2026-09-01 06:37 UTC, and the announced intent
is to move LP "over the coming weeks" rather than in one step. A mainnet pool4 hook may
therefore appear *before* it holds meaningful liquidity. The view handles that correctly by
construction — it reads live values and never a documented one — but WP11 should capture that
intermediate state too, because "adopted, and the reserve is near zero" is a real state a
reader will see and it must not read as an outage.

---

# AMENDMENTS

Binding changes to the plan above, made after a package reported back. Later text wins.

## A1 — `tests/data/test_surf_models.py` is owned by WP0 (was owned by nobody)

WP0's acceptance criterion *"the existing full suite is unaffected — this package only adds
names"* was **wrong**. It reasoned about `_finalise`, which does ignore keys it was not given,
but not about the tests that **derive** from `SURF_KEYS`. Splicing `POOL4_KEYS` in reddens
`test_surf_keys_is_exactly_the_prd_contract` immediately (reproduced: 1 failed, 63 passed).

The file had no owner, so wave 0 could not have closed. It is now **WP0's**, along with the
second defect WP0 found in it (below).

The other `SURF_KEYS`-derived sites already have owners and go red only when their producers
land. They are listed here so nobody rediscovers them at the WP8 gate:

| site | owner |
|---|---|
| `tests/data/test_surf_manager.py` — `set(data) == set(SURF_KEYS)`, 4 places | WP7 |
| `tests/screens/test_surf_screen.py` — dispatch coverage, and `SURF_ROW_KEYS` ⊆ fixture list-keys | WP8 |
| `tests/test_surf_registration.py` — the triage sweep | WP8 |

`tests/widgets/test_surf_widget_contract.py` is unaffected: it checks kwargs ⊆ `SURF_KEYS`.

## A2 — a test in `test_surf_models.py` cannot fail, and guards twelve models

`test_no_model_field_defaults_to_zero` asserts `field.default in (None, False, ())`. `in`
compares with `==` and **`0 == False`**, so a field defaulting to `0` passes the test named for
catching exactly that. Proven: an `int = 0` default left the suite fully green.

This is the repo's known "tests that cannot fail" family and it is being fixed with an identity
check, then **proven to bite on the original file** — not merely on a transcribed copy.

## A3 — the hook has no `vault()` getter (binding on WP6 and WP3)

§0.2 says `pool4_vault_addr` is *"read off the hook, never scraped"*. The intent stands and is
binding; the **hop count was wrong**. The recovered interface has no vault getter. The real path
is two hops:

```
hook.rewardsRecipient()  →  RewardDripper  →  dripper.vault()  →  StakedIMD
```

corroborated by `RewardDripper.renounceOwnership()` reverting when `vault == 0`.

`Pool4HookState` therefore has **no** `vault` field, and a test pins that absence deliberately:
a field with no getter behind it invites a producer to fill it by scraping the announce channel,
which is the one way this address must never be obtained. **WP6 must not look for `vault()` on
the hook.**

## A4 — `POOL4_FLOW_LIMIT` lives in `surf_models.py`

It could not go "beside the `FEED_ITEM_LIMIT` family" — that family is in `surf_manager.py`,
which WP0 may not touch and WP7 owns. **WP7 imports it; it does not redeclare it.**

## A5 — the closed vocabularies are exported constants

`POOL4_NETWORKS`, `POOL4_DISCOVERY_STATES`, `POOL4_FLOW_SIDES`, `POOL4_HATCH_SCOPES`,
`POOL4_HATCH_LABELS`, `POOL4_HATCH_STATES`. §0 named their members in prose only, which would
have had five packages hand-typing `"not-discovered"`. Import them; never retype a member.

## A6 — "45 scalar keys" is 43 + 2

Pinned as **two** numbers (43 scalars, 2 row keys) so a later edit cannot reach 45 by adding a
scalar and dropping a row.

## A7 — `capFloor` is better evidenced than §5 assumed

`docs/imd_pool4_mechanics.md` has been corrected since this plan was written. The floor is no
longer merely inferred: on Sepolia launch 1 a buy took the reserve from `152,030,338.5414` to
**exactly `50,000,000.000000000000000000`**, the wei-exact `capFloor()`. It binds **the swap
path**.

Two consequences for THE RATCHET (WP4) — "distance to floor" is a real binding number and should
read as one; **and a reserve *below* the floor is a legitimate state**, not a bug and not a
degraded read. Launch 1 sits below its own floor today because a backstop rebalance can move the
reserve where a swap cannot. The panel must not clamp it to zero distance or flag an error.

## A8 — the permission-flag constant was WRONG everywhere. It is `0x2840`, not `0x840`

**This is the security gate, and the plan, the PRD and the mechanics doc all had it wrong.**

The hook address ends `6840`. The visible `840` is a **mined vanity tail**; the flag field is the
low 14 bits, `0x6840 & 0x3FFF` = **`0x2840`**. Reading the tail as the field silently drops a bit.

Corroborated by asking the contract instead of doing arithmetic on the address —
`getHookPermissions()` (`0xc4e833ce`) on all three Sepolia launch hooks returns exactly
`beforeInitialize`, `beforeAddLiquidity`, `afterSwap`, and each decoded mask equals that
address's own low 14 bits:

```
launch 1  0x1230007b…6840   low14 = 0x2840   getHookPermissions = 0x2840   agree
launch 2  0xCA0612FF…E840   low14 = 0x2840   getHookPermissions = 0x2840   agree
launch 3  0xa1B997A9…6840   low14 = 0x2840   getHookPermissions = 0x2840   agree
```

**Both failure modes are live:**

* `low14 == 0x840` (the plan's mandated equality test) **rejects the real hook** — pool4 would
  never be discovered, on any chain, ever.
* `low14 & 0x840` **accepts a hook that does not gate pool initialisation** — the permission that
  makes pool4 a single pool nobody else can open with this hook.

**Binding on WP3:** `HOOK_FLAG_BEFORE_INITIALIZE = 1 << 13` is required, the gate is an equality
test against all three bits, and `getHookPermissions()` is read as a second, independent source
that must agree with the address. `announce_adversarial_flag_mismatch.json` encodes the
previously-documented `0x0840` address **as the attack**, so a gate built from the old docs goes
red rather than silently passing.

`docs/imd_pool4_mechanics.md` and `docs/surf_pool4_PRD.md` are corrected.

## A9 — no symmetric ETH cross-check: `totalFeeToken` is cumulative, `retainedEth` is a balance

Four of the five counter reconciliations hold to the wei (Σ`FeeCollected`[imd] = `totalFeeToken`,
Σ`ClaimsSettled`[0] = `totalBurned` = `balanceOf(0xdEaD)`, Σ`ClaimsSettled`[1] = `totalRewarded`).

The fifth — Σ`FeeCollected`[eth] vs `retainedEth()` — reads 0.0057 vs 0 and **that is correct
behaviour, not a defect**: the token counter is *cumulative* while the ETH one is a *current
balance*, and the owner has withdrawn everything ever collected. What actually holds is:

```
Σ FeeCollected[eth] == Σ FeesWithdrawn[eth] + retainedEth()
```

**Binding on WP7:** do not publish a symmetric ETH mismatch as "the recovered interface is
wrong". The SPLIT panel would cry wolf on every owner withdrawal.

## A10 — `eth_call` to an address with no code returns `"0x"` and no error

**Binding on WP3 and WP6.** A fingerprint gate that treats *"did not error"* as *"the getter
answered"* adopts an empty address. An empty return is a **failed** fingerprint, not a passed one.
Captured in `rpc_error_states.json`.

Also captured there: `-32602` means *"eth_getLogs is limited to 0 - 50 blocks"* on one provider
and *"Invalid params"* on another — CLAUDE.md's classify-on-message-text rule, now with evidence
behind it rather than folklore.

## A11 — R8 is measured. Sepolia does NOT split the way mainnet does

Sepolia `ethereum-sepolia-rpc.publicnode.com` **batches `eth_call` *and* serves archive
`eth_getLogs`** — unlike its mainnet sibling, which refuses archive `eth_getLogs`.

**Two evidence errors in this amendment's first draft, corrected by WP6, which re-measured
instead of transcribing** (R8 said measure, and the point of measuring is that it can disagree):

* Tenderly Sepolia's 429 is **not reproducible at 3 calls** — a 3-call batch returns 200. It is
  the **30-call round this client actually issues** that gets `-32005 rate limit exceeded`, cold,
  on the first attempt. The conclusion holds; the stated evidence did not, and a future reader
  re-probing with a toy batch would have "corrected" the pool the wrong way.
* `sepolia.drpc.org` does **not** "400 on `eth_blockNumber`". It answers *every* method with
  `code 35 "chain is not available on free plan, please upgrade to paid plan"` — a **keyed
  endpoint wearing a keyless URL**. That is a ban, not a method to avoid. Ban it by hostname
  `sepolia.drpc.org`, never by `drpc.org`: `eth.drpc.org` is a working mainnet log endpoint, and
  a test pins that the broader spelling would have broken it.

`rpc.sepolia.org` 404s (Apache); `omniatech` 521s; `1rpc.io` serves one 30-call batch then 429s
and caps logs at 50 blocks (`-32602`), so it is a **state fallback only**.

**WP6 must not assume the mainnet state/logs split transfers to Sepolia.** R8 is closed.

**§3's WP6 body is superseded and wrong where it disagrees.** It says "publicnode is BANNED" from
`SEPOLIA_LOG_RPCS`; on Sepolia publicnode is the endpoint that *works* for both. A reader who
stops at §3 builds the wrong pool. The measured pools are:

```
SEPOLIA_STATE_RPCS = publicnode (primary), 1rpc.io (fallback)
SEPOLIA_LOG_RPCS   = publicnode (primary), tenderly sepolia (fallback)
banned on Sepolia  = sepolia.drpc.org, rpc.sepolia.org, omniatech
```

Also measured, and load-bearing: `blockTimestamp` is present on `eth_getLogs` from both Sepolia
log endpoints and all three mainnet ones. `decode_flow_events` reads it, so an endpoint omitting
it would silently cost every flow row its age.

## A12 — four more event topic0s recovered

`OwnershipTransferred(address,address)`, `PoolInitialized(uint160,int24)`,
`MarketOpened(uint128,uint256,uint256)`, `RewardsRecipientUpdated(address,address)` — all
confirmed against their emitting transactions.

The three genuinely unresolved topics survived a further 143,640-candidate keccak sweep and keep
their operand-shaped names. The mechanics doc's `0xbdf538ed…` "retired backstop" topic never
appears in launch 3, so no guessed 32-byte tail was recorded for it.

## A13 — one network-word policy, hoisted: the ALLOWLIST wins

WP4 and WP5 independently wrote the same title helper with **different semantics on unknown
input**. WP5 allowlists against `POOL4_NETWORKS` (`"BASE"` → `—`); WP4 passes through (`"BASE"` →
`BASE`). Both are defensible in isolation. Together they are a defect: one pool4 body could paint
`THE SPLIT · —` beside `THE RATCHET · BASE` — five panels disagreeing about which chain the
numbers above them came from, which is R4 exactly.

**Decision: the allowlist, and one implementation.**

Reasoning, so it is not relitigated:

* The network word is each panel's **claim about the provenance of its own numbers**. This view
  exists to render testnet data before mainnet exists; a panel confidently naming a chain it does
  not recognise is the precise failure the network marker was introduced to prevent. `—` says
  "cannot stand behind this label", which is honest. `BASE` from an unrecognised string is a
  confident claim about provenance nothing supports.
* `POOL4_NETWORKS` is a **closed vocabulary** (A5). A value outside it is a producer bug, not a
  new network — and it should surface as an unknown marker, not be laundered into a title.
* WP4's objection — that a third network would blank the title the day it is added — is real but
  is already answered by the repo's own pattern: adding a network means adding it to
  `POOL4_NETWORKS`, and the agreement test reddens until it is. That is redundancy plus an
  agreement test, the same shape CLAUDE.md mandates for `_GAME_CYCLE` and the `--game` choices.
  A pass-through has no such tripwire: it would render a typo'd network word forever, silently.

**The hoist**, sequenced so no two packages edit one file:

1. **WP4** creates `maxpane_dashboard/widgets/surf/_pool4.py` holding exactly one `network_word`,
   one `panel_title` and one separator constant, on the allowlist policy, and switches its three
   rail modules to import them. WP4 owns `_pool4.py`.
2. **WP5** then switches `pool4_flow.py` / `pool4_split.py` to import from `_pool4.py` and deletes
   its local copy.
3. A test asserts **no pool4 widget module defines a local `network_word` / `panel_title`** — the
   same "imported and not copied" shape WP5 already wrote for the `_rowfit` ladder, which is why
   this defect was caught at all.

Until step 2 lands, `pool4_flow.py` remains the de-facto source; nothing ships in that state.

## A14 — the vault's `decimals()` is **24**, and the contract's share formulas are wrong by 10⁶

**Binding on WP7. Verified live.** Solady's ERC4626 reports `asset decimals + _decimalsOffset`,
and `StakedIMD._decimalsOffset()` is 6, so `decimals()` returns **24**. One whole `sIMD` is `1e24`
units. Contract §0.2's formulas divide by `1e18` and are wrong in both directions:

```
convertToAssets(1e18)/1e18 = 0.000001302985528554   ← wrong: reads as a dead vault
convertToAssets(1e24)/1e18 = 1.302985528554         ← pool4_share_price
totalSupply/1e18 = 21,010,977,789.12 sIMD           ← wrong: reads as an emissions farm
totalSupply/1e24 =         21,010.98 sIMD           ← pool4_vault_shares
cross-check: totalAssets 27,377.00 / 21,010.98 = 1.302986   ✓
```

Both numbers reach the screen through WP7, and both failure modes are *plausible-looking*, which
is what makes this dangerous: neither renders as an obvious error. `share_price_delta_pct` is
scale-invariant, so WP3 is unaffected.

## A15 — `backstop()` returns three words, not four

The getter returns 96 bytes: `(int24 lower, int24 upper, uint128 liquidity)`. **There is no ETH
word.** The `0.4253 ETH` in the mechanics doc's earlier draft came from the *event* `0xe3966151…`,
which has four operands. A decoder expecting four reads past the answer. Mechanics doc corrected.

WP0 should decide whether `Pool4HookState.backstop`, currently typed `str | None` and carrying a
`"lower,upper,liquidity"` string, ought to be three fields.

## A16 — settlement is decided by LOG ORDER, not by transaction

`MANIFEST.json` states that an accrual with no `ClaimsSettled` in the same transaction is the
accrued-but-unsettled case. **The corpus disproves it.** The accrual in `0x028d1448a9` is matched
to the wei by `ClaimsSettled` in a *different* transaction, `0x832f0efbe3`; and inside
`0x48090d111b` the `ClaimsSettled` sits at logIndex `0x7b`, *before* that transaction's own
accrual at `0x82`, paying the **previous** transaction's amounts.

Settlement rides the next swap. A same-transaction rule marks settled rows unsettled and vice
versa. WP3 implemented log ordering and `Σaccrual − ΣClaimsSettled` agrees with it to the wei
(267,300 / 29,700 outstanding). **The fixture note is what needs correcting, not the code.**

## A17 — `data/surf_pool4.py`'s import allowlist is wider than §0.5 says

§0.5 allows stdlib + `keccak` + `surf_v4`. But A5 *requires* importing the vocabularies from
`surf_models`, and WP3 also imports `data/evm_abi.strip0x` — the repo's existing stdlib-only ABI
codec — rather than growing a fourth copy of it, which is CLAUDE.md's "reuse before you build".

Both are legitimate and both are proved pure **transitively** by WP3's own test. WP8's purity gate
must enforce the *property* (nothing reaches `httpx`, `textual`, `aiohttp`, a clock, or
`surf_client`), not the literal three-module table — the surf widget-contract test is the
precedent, and its recursion is the part that bites.

## A18 — three wire-model shape changes (payload keys UNCHANGED)

Consequences of A14/A15. `POOL4_KEYS` stays 45 and `SURF_KEYS` stays 127 — **no payload key
changed, so WP8's dispatch is unaffected.** The wire models did:

| model | was | now |
|---|---|---|
| `Pool4HookState` | `backstop: str \| None` | `backstop_tick_lower`, `backstop_tick_upper`, `backstop_liquidity`, all `int \| None` |
| `Pool4VaultState` | — | **`decimals: int \| None` added, read from chain** |
| `Pool4VaultState` | `total_shares_wei` | `total_shares_raw` |

**WP6 must add `decimals()` to its vault call round.** **WP7 divides shares by `10 ** decimals`,
never `1e18`**, and derives `pool4_backstop_centred` from the two bounds against `current_tick`.

`decimals` is **read, never assumed**. A14's 24 is a *Sepolia* measurement; the mainnet vault does
not exist and nothing binds its `_decimalsOffset()` to Sepolia's, so a hardcoded 24 would
reproduce the 10⁶ defect at the switchover — silently, because both wrong forms render as
plausible numbers. A test refuses a `POOL4_VAULT_DECIMALS`-style constant so the hardcode cannot
return wearing a name.

`CONSTRUCTOR_KWARGS` in `tests/data/test_surf_pool4_models.py` is the machine-readable copy of the
shapes. Import it rather than hand-typing field lists: a rename then surfaces as a collection
error instead of a `None` panel.

## A19 — the backstop bounds stay model-internal. No new payload key

`pool4_backstop_centred` remains the only rendered output of the backstop. WP4's RATCHET panel
already renders it as the `centred` / `drifted` / `unknown` tri-state, and that is the
decision-relevant fact; raw tick bounds on a rail panel are noise, and adding them would be a
`POOL4_KEYS` change this late for no reader benefit. Declined deliberately — recorded so it is not
reopened.

**Correction to this amendment's own prose (WP7's D2).** A19 first said the value is derived "from
the two bounds against `current_tick`". That is wrong and the code is right:
`surf_pool4.backstop_centred(backstop_tick_lower, ref_tick, tick_spacing)` compares the **lower
bound against `refTick()`, within one `tickSpacing`** — because `rebalance()` re-centres against
the reference and can only land on a spacing multiple. On the committed capture that is
`|204180 - 204150| = 30` against a spacing of `60`. Corrected here so a later reader does not
"fix" the function to match a wrong amendment.

## A20 — the outstanding-legs figure is not round, and one assertion compares floats

The outstanding remainder is `267299999999999999994537` / `29699999999999999999393` wei — 5,463
and 607 wei **below** the round 267,300 / 29,700.

This breaks nothing: `267299999999999999994537 / 1e18` is exactly `267300.0` in float64, so the
existing assertion passes. But an assertion against the round literal cannot see a wei-level
discrepancy, and a docstring promising agreement *"to the wei"* beside a float comparison
overstates what that line checks. The wei-exact part is the integer pairing above it. Assert the
legs in integer wei where the claim is made, or soften the claim.

Generalises: **this corpus has values that are round to two decimals and not round to the wei.**
Any future check on them belongs in integer wei-space, not in floats.

## A21 — PROCESS: every package namespaces its scratch files

**A real collision happened.** WP3's `scratchpad/mutate2.py` was overwritten by WP4's
rail-widget mutation script between two of WP3's runs. It noticed only because the output printed
WP4's test names and pass count instead of its own. Confirmed: the shared scratchpad held generic
`mutate.py`, `mutate2.py`, `measure.py`, `measure2.py` from several packages at once.

Nothing in the repo was harmed — each script restored its own targets — but the failure mode this
opens is the worst one available to this branch: **a mutation harness that silently becomes
another package's is a way to report a green security suite that was never run.** The whole
credibility of the discovery gate rests on "each mutation was proven to bite", and that evidence
is worthless if the harness under it belonged to someone else.

**Binding on every package, current and future:** scratch files go under `scratchpad/<wp>/` with
package-prefixed names. Never `mutate.py`. WP3 and WP4 have moved; WP1 has been told.

**For WP9:** treat a mutation-evidence table as unverified if its harness cannot be shown to have
been namespaced at the time it ran. Re-running a sample is cheap; trusting a possibly-swapped
harness is not.

## A22 — `vault_state.json` captured `convertToAssets` at the wrong argument

The fixture asked `convertToAssets(1e18)`. On a 24-decimal vault that is a **millionth of a
share**, so the captured `1_302_985_528_554` renders as `0.0000013 IMD/share` — a dead-looking
vault — against a true share price of `1.302986`.

WP3 **removed** the `convertToAssets_1e18` alias rather than mapping it onto `share_price_wei`,
because accepting it would launder a wrong-argument answer into a right-looking field. That is the
correct call and it stands: `decode_vault_state(vault_state.json).share_price_wei` is `None` today
and a test says why. **The fix belongs in the capture.**

WP1 re-captures with `decimals()` read first and `convertToAssets(10 ** decimals)` keyed
`convertToAssets` (WP3 reads `SHARE_PRICE_CALL = "convertToAssets"`). **WP6 must call it the same
way.** The self-validating cross-check to record with it: `totalAssets 27,377.00 / shares
21,010.98 = 1.302986`.

## A23 — mutation harnesses: namespaced, owner-scoped, and verified after

A23 supersedes the looser wording in A21. The scratchpad collision was **bidirectional**: WP3's
harness was replaced by WP4's, *and* WP4's run executed WP3's mutations against
`data/surf_pool4.py` — a file WP4 does not own. WP3's script self-restored and the tree verified
clean, but WP4 also reports one of its own runs left a mutation in `pool4_vault.py` that it caught
only because a test reddened.

CLAUDE.md **requires** proving a test bites, so a source-rewriting harness is not bannable. Three
rules make it safe in a shared tree instead:

1. **Namespaced.** `scratchpad/<wp>/<wp>_*.py`. Never a bare `mutate.py`.
2. **Owner-scoped.** A harness may mutate only files its own package owns. WP3 mutating
   `surf_pool4.py` was always fine; WP4 running WP3's script was not.
3. **Verified after, not assumed.** Every run ends with a byte-identity check (sha256 or `cmp`)
   **and** a `git status` glance before any result is reported. "The script restores its targets"
   is a claim about a script that may not be the one you think you ran.

Independently verified after the hoist: 510 tests green across all ten pool4/surf files, and
`git status` shows only the expected set. No stray mutation survived.

## A24 — `NETWORK_WORDS` stays restated in the widget, with the agreement test in the test file

WP4 flagged this rather than assuming it, correctly. `_pool4.py` restates the tuple and the
**test** imports `POOL4_NETWORKS` from `surf_models` to assert set-and-length equality.

Confirmed as the right shape, for two independent reasons: contract §0.5 forbids a pool4 widget
importing `data/`, and CLAUDE.md mandates redundancy plus an agreement test generally — deriving
the widget's copy from the contract's would make the test compare a constant against itself and it
could never fail again. This is `_GAME_CYCLE`'s pattern exactly. **No §0.5 amendment needed.**

The test bites in both directions: dropping a member reddens (a network added to the contract but
not the widget would show every reader an em dash), and adding one reddens (a word invented in the
widget with no contract behind it).

## A25 — a restore that does not survive a kill is not a restore

A21/A23 said verify after the run. That is not enough, and WP5 found the gap the hard way.

Its mutation harness was **killed mid-run by the two-minute Bash timeout**, leaving `if False:`
inside `_render_view` in `pool4_flow.py`. The scoped suite it then checked was **green**, because
that mutation's own test was not in the run it happened to look at. It was caught only by grepping
the source for injected markers.

This is the most dangerous shape yet seen on this branch: a live source mutation, surviving in a
tree that reports green, on a package whose evidence is a table of mutations. **An end-of-run
restore is not a restore when the run can be killed.**

A mutation harness in this repo must:

1. **Write the pristine copy to disk before touching anything** — not hold it in memory, which dies
   with the process.
2. **Restore in `finally`**, and install `SIGTERM`/`SIGINT` handlers that restore before exiting.
3. **Delete its `.bak` only on a clean finish**, so a surviving `.bak` is itself the alarm.
4. **Scope each pytest run to the tests that mutation is expected to redden**, so a killed run is
   short and a green result cannot come from a suite that never covered the mutation.
5. **Grep the sources for injected markers on the way out** — as part of the harness's exit path,
   not as a habit the operator might skip. Both incidents on this branch were caught by a marker
   grep or by an unrelated test reddening, never by the harness noticing its own damage.
6. Then the A23 checks: byte-identity, and a `git status` glance, before reporting anything.

Rule 4 is the one that makes rule 5 rarely necessary, and it is easy to get subtly wrong: **the
scoped suite a harness checks must contain the mutation's own test.** WP5's killed run read green
because the mutation's test was not in the scoped run it looked at; WP4 found a leftover `0.00%` in
`pool4_vault.py` only because an *unrelated* test reddened. A scope that excludes the mutation's own
test converts a kill into a silent green.

Note the interaction with the 120 s Bash default: a harness that runs a whole widget file per
mutation *will* be killed. WP5's rebuilt battery runs ~35 s by scoping each run.

Independently verified at this point in the build: no mutation markers anywhere in the pool4 or
surf sources, no stray `.bak`/`.orig`/`.PRE` files, 393 passed with the single expected
`_PENDING_MIGRATION` handshake failure.


## A26 — WP7's two out-of-scope test edits are APPROVED, and they are the A1 shape again

WP7 edited `tests/data/test_surf_cache.py` and added a `DeadPool4Client` double to
`tests/data/test_surf_manager.py`, both wider than its brief, and flagged it rather than doing it
quietly. Approved, on its reasoning:

* `test_surf_cache.py` **has no owner in the plan** — the same gap A1 found in
  `test_surf_models.py`. `TIER_POOL4`/`SLOT_POOL4` necessarily redden its TTL and slot-count
  assertions, nobody else could fix them, and leaving them red would break WP8's gate. The edits
  stay hand-typed rather than derived, per the redundancy-plus-agreement-test rule.
* `DeadPool4Client` is **structural, not cosmetic**: without an injected double, every manager
  built in that suite would construct a real `Pool4Client` and the detached sweep would open a
  socket. That is a network-touching test suite, which CLAUDE.md forbids and requires be asserted
  structurally.

**For WP8:** two test files in this build were unowned and both were found only when a package
tripped over them. Check for a third before the gate rather than after.

## A27 — the persisted-adoption defence is RETIRED. Every sentence promising it is now false

Supersedes §3 WP3/WP7's "a persisted adopted address is re-verified on read, never trusted"
wherever it appears in this document (including §3 WP7's bullet and the WP3 adversarial table's
eighth row).

**Why it went.** The fingerprint is forgeable by construction, and two packages measured it
independently: the security pass mined a `0x2840`-shaped address in ~16,000 tries, WP3 reproduced
it in **20,141 tries in under a second**. Feed `fingerprint_verdict` that address plus a contract
answering real mainnet IMD to `token()` and zero words to the rest, and it returns
`("adopted", "flags, token and four getters agree")`. Four of the five getters are pure liveness
checks any contract passes; `token()` is a value the candidate's own contract chooses.

So **provenance — a transaction signed by the announce wallet — is the only unforgeable gate**, and
the persisted path was the one path that skipped it. WP7 removed the persisted address from the
candidate set entirely; WP3 then deleted `reverify_persisted`, which the manager structurally could
no longer call.

The old docstring's promise ("a payload hand-edited to `adopted` for an address that passes no gate
comes back `rejected`") was true **only of the committed fixture**, whose flag word is `0x0000`.
Against anyone actually trying it returned *adopted*. That is why the function was deleted rather
than documented: a reassuring sentence attached to a defence a live demo defeats in twenty seconds
is worse than no sentence, because someone greps for the cache-file protection and finds it.

**Still-false sentences, each in a file its own package owns** (reported by WP3, not edited by it):
`data/surf_models.py:889` and `:548` (WP0), `tests/data/test_surf_pool4_client.py:1380`'s test name
and docstring (WP6), `tests/fixtures/surf/pool4/MANIFEST.json:229` (WP1). All dispatched.

**The one future pressure, named so it can be refused on its merits.** The self-post naming the
hook can age out of the channel window, and discovery then loses a genuinely adopted hook — see
S15, measured at ~64 days. Someone will reach for the cache as the fix. **The fix is to read enough
of the channel, or to persist the self-post's transaction hash and re-establish provenance from the
chain (F5) — never to re-nominate from storage**, which would trade a paging bug for the provenance
bypass this retirement closed.


## A28 — two harness rules learned in flight (WP5)

**1. The pristine copy goes OUTSIDE the repo tree.** WP7's harness wrote
`maxpane_dashboard/data/surf_manager.py.wp7.bak` beside the file it was mutating. Its cleanup
worked — the backups were gone by the time I checked, exactly as A25's "delete only on a clean
finish" requires — but WP5 saw them mid-run, and that is the window: a concurrent `git add -A`, or
a process death before cleanup, commits a stale copy of a live module. A stale `surf_manager.py.bak`
sitting beside the real one is precisely the thing that gets imported by accident a month later.
Write pristine copies under `scratchpad/<wp>/`, never beside the target.

**2. The `git status` check must be scoped to the files you own.** WP5's harness reported
`git status unchanged: False` and it was a false alarm — WP7 and WP8 had landed `surf_manager.py`,
`screens/surf.py`, `widgets/surf/__init__.py` and CLAUDE.md between its two snapshots. Nothing of
WP5's had moved.

A whole-tree comparison is the wrong instrument in a live multi-agent tree: **it reports neighbours
as if they were you, which trains the operator to ignore the check** — and the check is the last
line of defence against a killed harness. Compare only status lines naming your own files. This
strengthens A23's third rule rather than replacing it: still check, but check something that can
only mean what you think it means.

## A29 — two more ways verification machinery lies, both found in shipped work (WP6)

Both were live in tests reported as passing in an earlier wave, and neither was visible without
mutating.

**1. Subset membership cannot prove which list was walked.** WP6's four-pool separation tests
asserted that the URLs touched were a *subset of the expected hosts*. But
`gateway.tenderly.co` is in **both** the mainnet state pool and the mainnet log pool (verified), so
a state call that walked the **log** list still touched a host that is a member of both — and the
test stayed green. Routing `fetch_transaction` through the wrong pool was undetectable.

Fixed by asserting the pool's own **prefix, in order**, which pins the list rather than the hosts.
Generalises: when two collections overlap, membership tests cannot distinguish them — assert the
sequence, or assert against the *other* collection's exclusive members.

**2. A mutation harness that cannot match a parametrized test downgrades every parametrized guard.**
pytest names a parametrized case `name[param]`; WP6's matcher compared against the bare function
name, so a correct bite was reported as "wrong test reddened" — indistinguishable from a real
failure, and in the other direction it would have masked one.

This is A25 rule 4's failure mode reached from inside the tooling, and the second harness defect on
this branch after WP3's stale anchors. **The harness is code, and it is the code the evidence rests
on.** Any package whose batteries match test names must handle parametrized cases; several
batteries here are matching parametrized tests.

## A30 — a live mutation of the SECURITY GATE sat in the tree, and the residue check could not see it

The most serious process failure on this branch. Recorded in full because the lesson is general.

**What happened.** WP3's battery 1 crashed mid-mutation and left
`POOL4_REQUIRED_FLAGS = 0x840` in the working tree — *the exact catastrophic value its own M1 exists
to catch*, on the constant that is the security boundary of the view. The harness predated A25: no
`try/finally`, no on-disk pristine, restore inline only. A `NameError` introduced during editing
fired **after** `MOD.write_text(src)`.

**Why the safety net missed it.** The residue check grepped for a **hand-written list of expected
marker strings**. Two mutations were sitting in the file while that grep reported clean. It was
found only because the test suite failed.

**A marker list is a test that cannot fail.** It can only find residue someone remembered to
enumerate, and the residue you fail to predict is exactly the residue a crash leaves. This is the
seventh instance of the cannot-fail family on this branch and the **third inside the verification
machinery itself** (after WP3's stale anchors and WP6's parametrized-name matcher).

**The rules, tightened:**

1. **sha256 against an on-disk pristine is the only sound residue check.** Not a marker grep, not a
   git-status glance, not "the script restores at the end". Identity or nothing.
2. **Retrofit harnesses written before the rule existed.** A25 was written mid-branch and battery 1
   was not brought forward — being early is not an exemption, and the oldest harness guards the
   oldest and most load-bearing code.
3. **Scan for every B-side literal across every battery**, evaluated against the module source, not
   a remembered subset.

**Verified clean at the time of writing** (orchestrator, independently): the gate is `0x2840` with
an equality test, the real hook passes, the `0x840` address is rejected, the only surviving mentions
of `0x840` are docstrings explaining the hazard, and all 49 mutations across six batteries bite from
a clean base with zero stale anchors.

**A sobering corollary.** Any green suite run during the window when that mutation was live would
have been green *with a broken security gate* — the gate's own tests would have failed, which is how
it surfaced, but a targeted run that excluded them would not have. This is the concrete case for
A25 rule 4: the scoped run must contain the mutation's own test.

## A31 — CPython's `.pyc` cache can make a mutation report BITES having never run

**The most consequential defect found in the verification machinery on this branch, and it is
branch-wide.** Found by WP7; reproduced independently by the orchestrator.

CPython invalidates a cached `.pyc` on **(source mtime truncated to seconds, source size)**. A
mutation battery that rewrites a module in place will, whenever two mutations produce the **same
file size within the same second**, run the *previous* mutation's bytecode. WP7 hit exactly that:
`if tx is None:` and `if not proved:` both became `if False:  # WP7MUT`, both left
`surf_manager.py` at exactly 234,512 bytes, both written in the same second.

The mutation was **correct on disk**. The marker check passed. The sha256-vs-pristine check passed
— the file really had changed. And the test reported **green having never executed the change.**

Reproduced from scratch:

```
warm cache, f() = AAA
rewrite source to BBB, same byte length, same mtime second
fresh interpreter:     f() = AAA      <- stale bytecode
PYTHONPYCACHEPREFIX=…: f() = BBB      <- correct
```

**Why every earlier safeguard misses it.** A30's sha256 gate compares the *source* against a
pristine — and the source is genuinely mutated, so it passes. A marker grep passes for the same
reason. The on-disk content is right; it is the *interpreter* that is wrong. No file-level check can
see this.

**The fix, and this wording matters (WP0's correction):** the cache directory must be **UNIQUE PER
MUTATION**, not merely relocated. Setting one `PYTHONPYCACHEPREFIX` for the whole battery
**reproduces the bug exactly as the default `__pycache__` does** — a prefix relocates the cache, it
does not invalidate it. WP0 demonstrated both halves on its own colliding mutations, no sleeps,
both writes inside one second:

```
one shared prefix:      R1.6 -> not_discovered | self-post
                        R6.2 -> not_discovered | self-post     <- STALE, same as default
unique per mutation:    R1.6 -> not_discovered | self-post
                        R6.2 -> not-discovered | docs          <- correct
```

Touching mtime forward, or padding sizes, are weaker workarounds that fail on the next coincidence.

**WP0 also checked that the hazard was reachable in its own battery rather than assuming a clean
re-run meant immunity**: three of its mutations produce byte-identical file sizes, so the
precondition was live and only the *incidental* >1s gap between consecutive pytest invocations had
been saving it. That is luck, not design — and it is the reason a clean re-run is not by itself
evidence that a battery was never affected.

**Every battery on this branch that rewrites a module in place is exposed** — WP0, WP3, WP4, WP5,
WP6 and WP8 all have that shape. WP7 re-ran its **entire** battery under the fix rather than only
the new mutations, on the grounds that every prior BITES was suspect; all 58 still bite. **The same
re-run is required of every other package before its evidence can be trusted.**

This is the fourth defect found inside the verification machinery (after WP3's stale anchors, WP6's
parametrized-name matcher, and A30's marker-list residue check) and the only one that no file-level
check could ever have caught. *The harness is code, and it is the code the evidence rests on.*

## A32 — A31's sibling: a battery re-run while a neighbour is writing measures noise

**Found by WP3 while re-running under the A31 fix.** Its battery gave 6/6 then 4/6 on consecutive
runs, and the cause was not the harness: **five runs of the UNMUTATED suite** gave
`182 passed / 2 errors / 2 errors / 2 errors / 4 failed` while `surf_models.py` was rewritten twice
in fifteen seconds by the package that owns it.

A31 is *the interpreter ran something other than the source*. This is *the world changed underneath
the source*. **Neither is visible to a file-level check on the file under test**, which is what makes
them a pair.

**The fix WP3 built, and it should be standard:** a **dependency stability gate** — a sha256
fingerprint of everything outside the mutated file that can change what a run means (the contract
module, shared helpers, the test files), checked at the end, **exiting non-zero with
`DEPENDENCY MOVED MID-RUN`** rather than reporting numbers it cannot stand behind.

WP6 independently hit the same thing from a different angle: three of its mutations reported
"WRONG TEST reddened" when pytest had emitted a *collection error* — because a neighbour's module
was mid-write and would not import. It now retries bounded and raises rather than scoring.

**Operationally: do not re-run a mutation battery while another package is live in the tree.** If
you must, gate on dependency stability and report `deps-moved`. Every "N/N bite" figure taken during
a concurrent wave should be read as provisional until it has been repeated on a settled tree — WP3
took its definitive runs only after three consecutive clean full passes confirmed the tree had
stopped moving.


## A33 — A28 was violated in practice, and the violation outlived the run that made it

A stale pristine copy — `wp3_b7.pristine`, 107,182 bytes — was found **at the repository root**,
untracked, superseded, and exactly what `git add -A` would have committed. A28 already required
pristine copies to live under `scratchpad/<wp>/` and never beside the target; this is the rule being
broken rather than a new rule.

What makes it worth its own amendment is the **diagnostic cost**. The file differed from the live
`surf_pool4.py`, which is the alarming case — and distinguishing "a stale snapshot from an earlier
battery" from "the live file is mutated and this is the clean copy" took a direct check of the
security gate:

```
live POOL4_REQUIRED_FLAGS = 0x2840     mainnet hook passes: True    0x840 rejected: True
pristine: 2,505 lines   live: 2,562 lines  (the sentinel work landed after the snapshot)
```

The live file was correct and strictly newer. But **a stray pristine is indistinguishable from
evidence of a live mutation until someone checks**, and on this branch a live mutation of that exact
constant has already happened once (A30). A surviving backup is supposed to be an *alarm*; one left
outside its own harness's lifetime is a **false** alarm, and false alarms are how a real one gets
skimmed past.

Moved to `scratchpad/wp3/`, not deleted — a copy whose provenance is unclear is not something to
destroy while working out what it was.

## A34 — a stale reading is indistinguishable from a live defect, and I forwarded one

**The orchestrator's own error, recorded because the pattern is general.**

WP10 reported that `POOL4_LEFT_ID` / `POOL4_RAIL_ID` described an arrangement that "has never
shipped". I forwarded it to WP8b as a recurrence of W3 without checking the live file. WP8b had
**already corrected both blocks** as part of its rebalance; WP10 had read a pre-edit copy. Verified:
the blocks read *"THE SPLIT over THE RATCHET over POOL4 FLOW"* and *"HATCHES over sIMD VAULT"*, and
`compose()` builds exactly that.

**Why I believed it without checking:** it matched a defect that had genuinely occurred **twice** in
those same two constants. A finding that fits a known pattern is the one most likely to be waved
through — and I had verified WP10's *other* findings, including the one against my own research doc,
so the omission was selective rather than systematic. That is worse, not better.

This is A33's lesson from the other side. There, a stale *pristine file* was indistinguishable from
evidence of a live mutation until the security gate was checked directly. Here, a stale *reading* was
indistinguishable from a live defect until the file was read. **In a tree this many packages are
writing, the age of an observation is part of the observation** — and one query is cheaper than a
round trip.

**WP8b's response is the durable half**, and better than a third manual correction: twice stale plus
one false alarm is a pattern, and every instance was a human noticing. It wrote
`test_the_pool4_column_blocks_name_the_panels_compose_builds`, which parses each block's leading bold
sentence and compares it against what `compose` actually builds — pinning the convention that a block
**leads with a bold run naming its panels top to bottom, joined by "over"**. Five docstring-only
mutations, each reddening its own parametrised case. The defect was never a code defect, which is
why nothing else could see it.

It also **declined to guard the blocks' `1fr` claims**, and said why: every phrasing that survived a
paragraph reflow also passed for a sentence naming the *wrong* panel. Better to guard the falsifiable
half and state the scope than to ship a green test that proves nothing. The `1fr` claim is guarded a
layer down against `minimal.tcss`, the copy that renders.

Full suite after the addition: **7,009 passed, 0 failed** — 7,007 plus exactly the two new
parametrised cases.

## A35 — a DELETED test does not fail, and only a which-test-reddened battery notices

**The most dangerous verification shape found on this branch, because it produces a green suite
with less coverage and no signal at all.** Found by WP4, in its own edit.

A span replacement ran from the test it meant to change to the next banner and **swallowed five
tests in between** — four reward-path tests and the twelve-lever guard. The suite stayed **green**,
because deleted tests do not fail. No count was being watched, so nothing said otherwise.

**What caught it:** three mutations reported `MISS` with `actual=[]` — *the signature of an expected
test that no longer exists*, as distinct from one that failed to bite. WP4's own summary is the rule
worth keeping:

> A battery that only counted failures would have reported those three as **passing mutations**.

This is the cannot-fail family one level out. Every earlier instance was a test that *existed and
asserted nothing useful*; this is a test that **stopped existing** while its guard-shaped absence
looked identical to success.

**Two rules follow:**

1. **A mutation harness must assert its expected test exists before mutating.** `actual == []` and
   "the guard did not fire" are different outcomes and must be reported differently. Only a battery
   that names the expected test can tell them apart.
2. **The collected test count is a gate, not trivia.** `pytest --collect-only -q` is a one-second
   check that a refactor did not eat coverage. Verified at this point: **7,010 collected** against
   the 7,009 green at commit `4563fda`, so no net deletion survives.

WP4 also found a second, smaller instance the same round: a test passed on words *borrowed from
neighbouring lines* — `delivery` and `drip rate` appear in two adjacent constants, so restoring the
retired claim it was written to forbid left it green. It now scans the whole panel for the forbidden
claim. Same lesson as A29's "pin the claim, never a token that appears in it", reached from a third
direction.

## A36 — pytest exits 4 for a NONEXISTENT test, and a harness reading "non-zero = failed" scores it as BITES

A35's mechanism, found in the wild by WP7 the moment it added A35's guard. Verified independently:

```
pytest …::test_this_does_not_exist   ->  exit 4   (usage error)
pytest …::a_real_passing_test        ->  exit 0
```

A battery that treats any non-zero exit as "the guard fired" therefore reports **proven coverage
for a test that does not exist**. WP7's guard caught two on its first run — `F5/M27` and `S15/M29`,
both pointing at tests renamed or superseded **rounds earlier**.

**This retroactively corrects reported evidence.** WP7's `65/65`, `60/60` and `56/56` each included
two mutations that executed nothing. WP7 raised this itself rather than quietly re-running, which is
the only reason it is knowable.

Its own framing is the durable lesson, and it now has three instances behind it:

> All three of my battery failures have been *the harness lying about coverage it never had* — a
> reused `.pyc` (A31), an unapplied mutation (A29), and now a nonexistent test — and **none of them
> was a failing test**. A battery's own instrumentation needs more distrust than the code it
> measures.

**Required of every harness:** collect the test files up front, **refuse to run a mutation whose
expected node is not in the collected set**, and never infer a bite from an exit code alone. WP7
also now compares the collected count across the whole run (204 before, 204 after) — A35's gate
applied per-battery rather than only at the suite level.

## A37 — reading a harness's output through `grep` is a kill, and kills it past its own cleanup

Found by WP5. A25 established that *the restore must survive a kill*; this is a kill nobody
classified as one.

Piping a mutation harness into `grep` **SIGPIPEs the harness** the moment `grep` has seen enough —
after its own last write but **before its cleanup**. Two `.bak` files survived a run that way. WP5
verified the tree by sha256 against those pristine copies before touching anything (both identical,
no residue), then added a `SIGPIPE` handler and confirmed cleanup.

The operational form: **`harness.py | grep BITES` is not a read-only operation.** It is the same
class as A25's 120-second timeout, reached through a shell idiom that looks inert. Handle `SIGPIPE`
alongside `SIGTERM`/`SIGINT`, or write to a file and grep the file.

Worth noting where this sits: this is the **fourth** distinct way a harness on this branch has
produced a result about something it did not validly run — after a reused `.pyc` (A31), an
unapplied mutation (A29), and a nonexistent test (A36). Every one was invisible to the file-level
checks, and every one was found by a package auditing its own instrumentation.

## A38 — a probe loop that asserts inside itself hides every failure after the first

Found by WP5, sweeping past a red test rather than accepting it as the whole story.

`test_every_pool4_zero_needle_really_renders_when_its_key_is_zero` asserts **inside** its loop, so
it stops at the first bad needle. One failure was visible. Sweeping all 39 by hand:

```
6 of 39 zero needles do NOT render
```

So "the only two red in a 7,021-pass suite" was **an artefact of loop ordering**, not a measurement.
Five of the six were stale needle *text* — D19's liveness word changed the leg heads
(`nodes -- · earned 0.00` became `nodes -- reserve · earned 0.00`) — and the rendering itself is
correct: zeros stay distinguishable from missing reads in every combination.

**The compounding part:** the five were reachable only *after* the sixth was fixed. A loop that stops
first hides the rest, so each fix reveals one more and the suite looks nearly-green throughout. This
file's own docstring is a history of vacuous needles — the guard exists precisely because these go
stale — and its shape was concealing exactly what it was written to expose.

**Fix:** `pytest.mark.parametrize` over the probe table so each key fails independently. A probe
table is a collection of independent claims and must fail as one.

## A39 — I misattributed a defect twice in one round, both times by forwarding

Recorded because it is now a pattern rather than a slip, and A34 already named it once.

1. I forwarded WP10's report that two docstrings were stale. They had **already been fixed**; WP10
   had read a pre-edit copy.
2. I forwarded WP8b's description of the vault change as *"WP5's in-flight edit"* and dispatched the
   fix to WP5. `pool4_vault.py` is **WP4's** file — verified: `DELIVERY_NOT_APR_NOTE` has **0**
   occurrences at commit `4563fda`, the file carries an uncommitted 69-insertion diff, and
   `pool4_implied_apr_pct` is in `SurfPool4Vault`'s signature and not `SurfPool4Split`'s. **I had
   dispatched that very change to WP4 myself**, one round earlier.

Both times the finding was real and only the owner was wrong. Both times I verified the *substance*
and took the *attribution* on trust — and an attribution is a claim about the repository exactly as
much as a line number is.

**The rule:** when a report names another package's file, confirm ownership from `git` before
routing. `git show <commit>:<path>` and `git diff --stat <path>` answer it in one call. Forwarding
an attribution unverified costs a round trip and asks the wrong package to change a file it does not
own — which the standing one-owner-per-file rule exists to prevent.
