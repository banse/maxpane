# CURATOR Dashboard ("THE LIST") — Implementation Plan

> **For agentic workers:** this document is the index, the dependency graph and the global
> contract. Each work package is a separate file under `docs/curator_work_packages/`. Steps
> use checkbox (`- [ ]`) syntax; tasks are numbered `WPn.m`. Implement task-by-task, commit
> after each task, and never edit a file another work package owns.

**Goal:** Ship `--game curator`, MaxPane dashboard #11 (8th visible) — **THE LIST**, a keyless
read-only survival watch over `WhitelistCurator`
(`0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91`, Ethereum mainnet): a zero-custody allowlist
game with an hourly doomsday clock, which must be equally good as a live clock and as the
game's archive after the clock wins.

**Architecture:** House data flow — `curator_client` (keyless fetch, injectable transport, two
endpoint pools) → `curator_cache` (tiered TTL, persisted folds/series/evidence record) →
`curator_manager` (`fetch_and_compute()` → one flat dict, exactly `CURATOR_KEYS`) →
`CuratorScreen` (slot grid, width tiers, one `c` swap slot) → `widgets/curator/*` (render
primitives only). All phase, curve, fold and cluster math lives in
`analytics/curator_signals.py` as pure functions with `now_ts` injected.

**Tech stack:** Python 3.11, Textual, httpx (async, injectable transport), pytest. No `web3`,
no `eth_abi` — `eth_call` payloads are hand-encoded with vendored selectors and decoded with
`maxpane_dashboard/data/evm_abi.py` (`strip0x`, `decode_uint`, `decode_address`,
`encode_uint`, `encode_address`), exactly as `surf_client` and `talismans_client` do. Hashes
come from `maxpane_dashboard/data/keccak.py` (`keccak256_hex`). No new third-party dependency.

**Spec:** [`curator_PRD.md`](curator_PRD.md) · **Research:**
[`curator_game_mechanics.md`](curator_game_mechanics.md) · **Captures:**
`tests/fixtures/curator/captures/` (see its `README.md`).

---

## Global constraints

Every task's requirements implicitly include these. They are `CLAUDE.md` house rules plus the
PRD's project-wide requirements; violating one is a defect regardless of what a task says.

- **Read-only, keyless.** No signer, no transaction construction, no key/keystore/API key of
  any kind. `deposit()`, `settle()` and `rescue()` are read *about*, never called.
- **A failed read is `None`, never `0`.** No sentinel ever enters a persisted series. This
  contract has three legitimate zeros — `currentHourTotal()` at an hour boundary,
  `ethNeededThisHour()` during grace, `creditedDelta` above the cap — and each must stay
  distinguishable from a failed read.
- **A dead source degrades to an explicit unavailable state**, last-good behind an
  `as of HH:MM` marker. Never a crash, a blank panel, or a stale number presented as live.
- **Escape every third-party string** with `widgets/markup_safety.safe_markup` before it
  reaches markup or a `DataTable`. v1 renders only self-generated hex and numbers; the rule
  still applies at the boundary.
- **Validate persisted series per point** via `data/series_points.coerce_points`.
- **Inject the clock.** No module a test controls may call `time.time()` internally
  (`now=` / `now_ts` / `clock=` parameters). Every phase value derives from an injected clock.
- **`CuratorScreen` inherits `screens/refresh_guard.RefreshGuard`** — no hand-rolled
  `run_worker(..., exclusive=True)`.
- **Sparklines import `widgets/sparkline_common`** — never copy `build_sparkline`,
  `coerce_points`, `trend_arrow` or `fmt_compact`.
- **Assert against composited output** (`app.screen._compositor.render_strips()`), never a
  widget's content string alone.
- **No test may touch the network** — inject a transport that raises on use; every external
  payload traces to a committed file under `tests/fixtures/curator/`.
- **Read values live; never hardcode a documented one.** The eight immutables
  (`launchTime`, `hourlyThreshold`, `gracePeriod`, `hourDuration`, `minDeposit`,
  `minEscalation`, `creditCap`, `firstJudgedHour`) come off the `once` tier, not from the
  PRD's table. `POINTS_PER_ETH` is a `constant` and is read the same way.
- **Widgets never import from `data/` or `analytics/`** — they receive
  `str`/`int`/`float`/`bool`/`dict`/`list[dict]`.
- **One owner per shared file.** `app.py`, `screens/game_select.py`, `__main__.py`,
  `themes/minimal.tcss`, `CLAUDE.md` and `README.md` belong to **WP7 alone**. Report defects
  in another WP's files; do not fix them. Never `git checkout --` a file to undo your own
  edit — the tree may hold someone else's uncommitted work.
- **Run tests as** `.venv/bin/python -m pytest` — the system `python3` lacks the deps and
  produces alarming collection errors that mean nothing.
- **Commit after each task** with `type(scope): subject`, e.g.
  `feat(curator): freeze CURATOR_KEYS and the six row-key shapes`.

---

## Work packages

| WP | Owns | Tasks | Depends on | File |
|---|---|---|---|---|
| WP0 | `data/curator_addresses.py`, `data/curator_models.py`, `abis/curator/`, `tests/curator_fixtures.py`, `tests/data/test_curator_{addresses,models,captures}.py` | 8 | — | [wp0.md](curator_work_packages/wp0.md) |
| WP1 | `scripts/capture_curator_state.py`, `tests/fixtures/curator/captures/live/` | 7 | — (runs on the clock, not on the build) | [wp1.md](curator_work_packages/wp1.md) |
| WP2 | `data/curator_client.py`, `tests/data/test_curator_client.py`, `tests/fixtures/curator/client/` | 11 | WP0 | [wp2.md](curator_work_packages/wp2.md) |
| WP3 | `analytics/curator_signals.py`, `tests/analytics/test_curator_signals.py`, `tests/fixtures/curator/signals/` | 12 | WP0 | [wp3.md](curator_work_packages/wp3.md) |
| WP4 | `widgets/curator/*` (7 modules), `tests/widgets/test_curator_widgets.py` | 9 | WP0 | [wp4.md](curator_work_packages/wp4.md) |
| WP5 | `data/curator_cache.py`, `data/curator_manager.py`, `tests/data/test_curator_{cache,manager,degradation}.py` | 13 | WP0, WP2, WP3 | [wp5.md](curator_work_packages/wp5.md) |
| WP6 | `screens/curator.py`, `tests/screens/test_curator_screen.py` | 8 | WP0, WP4, WP5 | [wp6.md](curator_work_packages/wp6.md) |
| WP7 | every shared file + integration | 13 | all | [wp7.md](curator_work_packages/wp7.md) |

**81 tasks.**

### Recommended agent per work package

The role names are the ones the FWA and surf plans used. This repo's current Claude Code setup
does not register those personas, so each row also names the **concrete subagent type to
launch today**. Launch the concrete one; the role name is what the task brief should say.

| WP | Recommended role | Concrete subagent type | Why this one |
|---|---|---|---|
| WP0 | Backend Architect | `code-architect` | Pure interface design: the frozen vocabulary three other WPs code against in parallel, and the one place a naming mistake costs a whole wave. |
| WP1 | Evidence Collector | `general-purpose` | Network-capable, standalone, no code contract to respect — it fetches, writes JSON and commits. Deliberately not an implementer: it must be runnable at 20:58 UTC by someone who has read nothing else. |
| WP2 | Data Engineer | `general-purpose` | Transport plumbing, ABI decoding, endpoint failover — mechanical, heavily test-driven, no design latitude. |
| WP3 | AI Engineer / numerics | `general-purpose` (strict TDD) | Integer-exact math against committed events; the module is pure and fully specified, so tests come first and `pytest.approx` on a wei value is a review failure. |
| WP4 | Frontend Developer | `general-purpose` | Seven Textual widgets against a frozen kwarg table; the work is width tiers and degradation copy, not logic. |
| WP5 | Backend Architect | `code-architect` | Orchestration, tiering, the settlement latch and the degradation matrix — the WP where a wrong seam is expensive and where two mandated prove-it-bites mutations live. |
| WP6 | UI Designer | `general-purpose` | Slot grid, phase rendering, and the measured width sweep; needs the eye for what a user reads, not more chain knowledge. |
| WP7 | Senior Developer | `general-purpose` | Sole owner of six shared files; the value is care and sequencing, not novelty. |
| audit | Test Results Analyzer | `pr-test-analyzer` | Optional wave-6 pass over the full suite and the three mutation proofs, if the parent wants an independent read. |
| audit | Silent-failure hunter | `silent-failure-hunter` | Optional: this dashboard is a wall of `try/except` degradation paths; a scan for swallowed failures is cheap insurance. |

### Execution waves

```
wave 1:  WP0                        ‖  WP1
         (sequential gate: freezes      (standalone capture rig; its TIMED runs
          the interface everyone          continue through every later wave —
          builds against)                 see "Time-critical captures" below)

wave 2:  WP2  ‖  WP3  ‖  WP4        (three agents in parallel; no shared files)

wave 3:  WP5                        (needs the client + the pure signal layer)

wave 4:  WP6                        (needs the widgets + the manager)

wave 5:  WP7                        (sole owner of every shared file;
                                     full suite + live smoke run)
```

Peak concurrency: 4 (wave 1 WP1 + wave 2's three). Critical path:
**WP0 → WP2/WP3 → WP5 → WP6 → WP7**, five waves.

WP4 has one task (its `CURATOR_KEYS` contract test) that imports `data/curator_models.py`; if
WP0 has not landed, **park that task rather than stubbing the module** — one owner per file.

WP1 shares no file with any other work package: it owns `scripts/capture_curator_state.py` and
the **subdirectory** `tests/fixtures/curator/captures/live/`. WP0 owns the sixteen files
already in `tests/fixtures/curator/captures/` and their `README.md`. WP0's capture guard is
therefore written against a **named required set**, never a file count, so a WP1 capture
landing mid-build cannot turn WP0's suite red.

---

## The frozen interface

WP0 freezes the module surface in wave 1 and nothing after it may rename a field. Four seams
are pinned by tests **on both sides**, because "three vocabularies for one dataclass" is the
defect class that cost the surf plan two review rounds.

1. **Dataclass fields.** `CuratorState`, `WalletState`, `ContributorRow`, `DepositEvent`,
   `HourBucket`, `SettlementRecord` and `LogSweep` are defined once in WP0.5.
   `CONSTRUCTOR_KWARGS` pins the field tuples so a mismatch fails at **import**, not at
   render. WP2 constructs them; WP5 reads them; both import `CONSTRUCTOR_KWARGS` and assert
   the kwargs their own code passes.
2. **`READING_KEYS`.** WP5's `_readings()` emits exactly the keys WP3's `build_signals()`
   consumes, with the outage encoding held constant: `None` means "the read failed",
   `[]`/`()` means "the read succeeded and found nothing". HOUR AT RISK and SETTLED both
   depend on that distinction — a `None` needed-ETH must never light the yellow state.
3. **`CURATOR_KEYS`.** The flat manager dict, PRD §5 made exact by WP0.6. WP4's
   widget-contract test asserts containment, so a widget can never read a key the manager
   does not emit; WP6's dispatch test asserts totality, so no key reaches no widget.
4. **`PHASES = ("grace", "judged", "settled")`.** One tuple, imported by the analytics layer
   (which produces it), the manager (which passes it through), the widgets (which branch on
   it) and the screen (which picks the swap-slot default from it). A fourth spelling
   anywhere is a silent fallback arm.

**Unit discipline:** models are **wei-native** (`*_wei: int`), the flat dict is the
presentation boundary (ETH floats). The manager divides exactly once. `test_no_wei_key_leaks_into_the_flat_dict` pins it.

**Naming discipline:** model fields mirror the chain, flat keys mirror the PRD. The getter is
`isSettled()` so the model field is `settled`; `ethNeededThisHour()` → `hour_needed_wei` on
the model and `hour_needed_eth` in the dict. The mapping table lives in WP5, and WP0.5's
`test_no_flat_dict_key_masquerades_as_a_model_field` forbids the confusion.

---

## Where the raw material lives

`tests/fixtures/curator/captures/` holds eighteen committed files: seventeen from the
2026-08-16 research session, all fetched between 21:04 and 21:14 UTC when the contract was
~75 minutes old, plus one hour-boundary series taken at 21:56–22:01 UTC the same evening.
Their provenance is in that directory's `README.md`. Everything the build tests against
traces to one of them.

| capture | what it pins | who slices it |
|---|---|---|
| `source.sol` | the verified source, solc 0.8.28 — the *only* authority for event/function signatures and for `_curve`/`_sqrt`/`_isShort`/`_credit` | WP0 (preimages), WP3 (math transcription) |
| `contract.json`, `wc_abi.json` | two saves of the same Blockscout smart-contracts response, incl. the ABI | WP0 (vendors `abis/curator/whitelist_curator.json`) |
| `creation_tx.json` | creation tx `0x240bf1a8…`, block **25769870**, 2026-08-16 19:58:47 UTC, `launchTime == 1786910327` | WP0 (creation block/ts pins) |
| `batch.json` / `results.json` | the **21-call batched `eth_call` round and its raw returns** — the selector table's cross-check and the state decoder's fixture | WP0 (selectors), WP2 (`fetch_state`) |
| `tenderly_logs.json` | one full-history `eth_getLogs` sweep from the deploy block, 377 logs = 1 `Launched` + **231** `Deposited` + 145 `FirstDeposit` (recounted from the committed bytes; every earlier doc said 226, and a fold calibrated to 226 silently drops five real deposits). The file is the **whole JSON-RPC envelope** — rows live under `result` | WP2 (log sweep), WP3 (folds) |
| `bs_page_0..7.json` | the same history via Blockscout pagination, 376 logs, reconciled | WP2 (REST cross-check / gap repair) |
| `ann_page_0.json` | the announce channel's tx page: it never *posted* about the curator, but it did make deposit #1 (one `deposit` item) | WP0 (a fact pin only; **surf is out of scope**) |
| `hour_boundary_h1_h2.json` | the same 21-call batch re-sent every ~20 s across the hour 1 → 2 crossing (16 samples, 21:56:15 → 22:01:21 UTC), with a `views` table mapping request id → selector → Solidity signature | WP2 (state decoder over a moving series), WP5 (the boundary fold rule) |

Two decoded facts worth stating up front, because they were read out of `results.json` during
planning and contradict things people remember:

- `earlyMultiplierBps()` at capture is `0x4c23` = **19491 bps = 1.9491×**, not ~1.99×.
- `currentHourTotal()` and `lastActiveHour()` agree in the 21:04–21:14 round (`hour 1`,
  `0x27d2c90dce228ae5b0` wei) — the state that makes the hour-boundary hazard *invisible* in
  the original set. `hour_boundary_h1_h2.json` fixes half of that: it shows
  `currentHourTotal()` falling **9987.26 → 51.48 ETH** across 21:58:47 UTC while `stats()`
  keeps climbing (516 → 524 contributors), which is the drop a naive state-poll sparkline
  renders as a 99.5% crash. It does **not** show the stale pair: a deposit landed within 11 s,
  so `lastActiveHour()` had already rolled to hour 2 in the first post-boundary sample. That
  variant — an hour crossing with no deposit yet, which post-grace is also the at-risk state —
  is still capture **A** below.

Slice ownership follows the surf rule: **WP0 owns the captures and pins their facts; each
consuming work package owns its own slices** under
`tests/fixtures/curator/<its-own-dir>/`. The root of `tests/fixtures/curator/` holds
directories only — WP0.7 asserts it, and that is what stops one WP's fixture landing in
another WP's glob.

---

## Time-critical captures — the part the PRD does not cover

**Every committed capture is from grace hour 1.** Nothing has been judged, nothing has
settled, `earlyBps` is mid-decay, and the hour bucket happens to be the current one. Three
states are irreplaceable once missed, and two of the three windows are **today**.

| # | state | how to recognise it | window | if missed |
|---|---|---|---|---|
| **A** | hour boundary, **no deposit yet** | `currentHourTotal() == 0` **while** `lastActiveHour()` still names the previous hour, `timeLeftInHour()` ≈ 3600 | any `HH:58:47` → next-hour crossing, until settlement; cheapest of the three, retryable hourly. **The crossing itself is already captured** (`hour_boundary_h1_h2.json`, 2026-08-16 21:58:47 UTC) — what is missing is a *quiet* crossing, i.e. one where no deposit lands in the first seconds. **Missed at three consecutive boundaries** (21:58:47, 22:58:47, 23:58:47) — during grace a deposit lands within seconds of every crossing, so the quiet state simply does not exist yet; it becomes the *normal* case after grace | the stale-`lastActiveHour` decode path has no real fixture; the volume-drop half of the hazard is covered |
| **B** | post-grace, judged hour in progress | `earlyMultiplierBps() == 10000` exactly, `currentHour() >= 24`, `ethNeededThisHour()` can be > 0 | opens **2026-08-17 19:58:47 UTC**; the flat-multiplier state persists, but a *judged hour with a live deficit* may be brief | JUDGED phase, HOUR AT RISK yellow/red and the flat-multiplier branch are all fixture-less |
| **C** | settlement transition | `isSettled() == true`; a `Settled` log if anyone calls `settle()`; a `HourSaved` log if one ever fires | earliest **2026-08-17 20:58:47 UTC**; the *transition* is one-shot and unrepeatable forever | SETTLED is the terminal product state and would ship tested only against synthetics; `HourSaved` may never fire at all |

**WP1 exists for exactly this**, and is scheduled in wave 1 so the rig is proven long before
it is needed: `scripts/capture_curator_state.py` is a one-shot, keyless, dependency-light
script (real `User-Agent`, no key, no signing) that writes a timestamped bundle plus a
manifest line into `tests/fixtures/curator/captures/live/`. It can be run by anyone, at any
moment, with no knowledge of build progress and no risk to another agent's files. **Run it at
every opportunity; a redundant bundle costs a few kilobytes and a missed one costs a
fixture that cannot be recreated.**

### Synthetic until captured

State this plainly to whoever picks up the work, and keep the table current:

| fixture | status | re-point when |
|---|---|---|
| hour-boundary volume drop (`currentHourTotal` collapses, cumulative `stats()` keeps rising) | **real** — `hour_boundary_h1_h2.json`, 16 samples across 2026-08-16 21:58:47 UTC | done |
| hour-boundary state with a **stale** `lastActiveHour` (`currentHourTotal == 0`, previous hour still named) | **synthetic** — hand-built from `results.json` with two words changed | capture **A** lands (WP1.3): a *quiet* crossing |
| post-grace state (`earlyBps == 10000`) | **synthetic** — `results.json` with `0x4c23` → `0x2710` | capture **B** lands (WP1.4) |
| judged hour with a deficit (`ethNeededThisHour > 0`) | **synthetic** | capture **B** lands |
| settled state (`isSettled == true`) + the `Settled` log | **synthetic** — the log row is hand-built from the ABI, its *shape* is real | capture **C** lands (WP1.5) |
| `HourSaved` log row | **synthetic** — never fired on chain as of the captures | capture **C**, only if one ever fires. It may not; say so rather than waiting. |
| `creditedDelta == 0` deposit (above the 1000 ETH cap) | **synthetic, permanently plausible** — the largest real send is 461.1 ETH | a >1000 ETH deposit lands. Do not wait for it. |
| `Rescued` log row | **synthetic** — forced ETH is an anomaly that may never occur | never, realistically |
| `previewPoints(weight)` / `pointsOf(addr)` returns | **REAL, captured 2026-08-16 22:51:43Z** — `captures/live/20260816T225143Z_curve-probe.json`, 20 of 20 calls answered and every one equal to `(isqrt(w) * rate) // 1e9` computed locally | done (WP1.6). The curve is validated **against chain**, not by transcription |

**Tests that must be re-pointed when a real payload lands** are marked in their owning WP with
the literal comment `# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>`
so `rg "SYNTHETIC — re-point"` is the whole checklist.

**WP7.13 closed it out on 2026-08-17, and closed it *open*.** The grep returns **33** matches
and **none of them was re-pointed**, because no bundle for capture A, B or C exists: the newest
live bundle is `20260817T000322Z`, both of the 2026-08-17 windows (19:58:47 and 20:58:47 UTC)
were still ahead, and the quiet crossing has now been missed at three consecutive boundaries —
21:58:47, 22:58:47 and 23:58:47 — each time because a deposit landed within seconds of the
boundary, which is the *normal* state during grace. Nothing is wrong with the rig. The per-marker
inventory, classified as waiting-on-A (3), waiting-on-B (15), waiting-on-C (6),
permanent-synthetic (3) and prose (6), lives in
`tests/fixtures/curator/captures/live/README.md` under "The marker inventory". Every marker
stays; deleting one to tidy the grep is how a fixture stops being tracked.

---

## Hazard → owning task → test

PRD §6 and the mechanics doc's hazard list, each with exactly one owner and one enforcement.
A hazard with no test is not handled.

| # | Hazard | Owner | Enforcement |
|---|---|---|---|
| H1 | **Poll `isSettled()`; the `Settled` event is the obituary.** `settle()` is permissionless and may lag death indefinitely. | WP5.4 | The fast tier reads the view. The manager persists an evidence record `{value, block_number, observed_at}` on first observation of `true` and never re-reads through it. **Mandated mutation:** make the latch re-read through → the simulated-outage test goes red. |
| H2 | **`currentHourTotal()` zeroes at every hour boundary** while `lastActiveHour()` still shows the previous bucket. | WP5.3 | Series are fed **only** from folded `Deposited` logs; the hour comes off the event's *indexed* second topic, so no timestamp is needed and no state read participates. A structural test asserts the fast tier's payload keys are disjoint from the series writer's inputs. **Mandated mutation:** make the fold consume `currentHourTotal` → the boundary fixture writes a zero → red. |
| H3 | **`creditedDelta == 0` is legitimate** (deposit above `creditCap` still counts fully toward hourly survival). | WP3.5 | `credited_delta()` and `weight_added()` are total functions; no division by `creditedDelta` anywhere (a static scan in WP7.12); a synthetic >1000 ETH event asserts full hourly credit with zero weight. |
| H4 | **Volume is gas-priced, not capital-priced.** Every wei is refunded in-tx. | WP4.2, WP7.12 | Copy reads `routed (all refunded)`. A guardrail scan over `widgets/curator/`, `screens/curator.py` and `data/curator_manager.py` forbids the strings `TVL`, `locked`, `at risk`, `capital` adjacent to a volume field. The one honest capital sentence (EOA gate) appears once, as subtitle text. |
| H5 | **Nonzero contract balance is always forced ETH**, never deposits. | WP5.8 | `eth_getBalance(contract)` feeds `forced_eth` only; expected rendering is `—`. A test asserts a nonzero balance never reaches a volume, TVL or hero total. |
| H6 | **`contributors()` carries a `firstHour + 1` offset**; `firstHourOf()` un-shifts it; `FirstDeposit.index` is 1-based. | WP2.5, WP3.6 | The client reads `firstHourOf()` (2 words: `hour`, `hasJoined`) and never the raw struct field. A decode test asserts `(0, false)` for a never-joined address is **not** rendered as "joined in hour 0". The fold asserts `FirstDeposit.index` maxes at exactly `totalContributors` (145 in the captures). |
| H7 | **Integer sqrt must floor exactly like the contract.** `points = (isqrt(weight) * 1000) // 1e9`, multiplication before division. | WP3.3 | `math.isqrt` in production; the test transcribes the contract's seeded-Newton loop with its `result <= a/result ? result : result - 1` correction and asserts equality over an edge + randomized corpus. **Mandated mutation:** `//` → `round` (and `isqrt` → `int(math.sqrt(...))`) → red. |
| H8 | **`weightAdded = creditedDelta * earlyBps // 10_000`**, floor. | WP3.4 | Wei-exact `==` (never `pytest.approx`) against the captured event where 0.05 ETH at 19975 bps produced 0.099875 ETH of weight, plus a differential over **all 231** captured `Deposited` rows. |
| H9 | **publicnode 403s python-urllib's default UA.** | WP2.1 | The client sets an explicit real `User-Agent` header. A test asserts the header is present, non-empty, and not a `python-`/`urllib`/`httpx` default, on every request the transport sees. |
| H10 | **drpc fails with a routing message**; providers reuse `-32602`/`-32005` for unrelated meanings. | WP2.3 | Classification is on **message text**, not code (`_looks_like_endpoint_limitation` / `_is_range_limitation` pattern tables, mirrored from `surf_client`). A test drives a `-32602`-coded routing message and asserts failover, and a `-32602`-coded malformed-request body and asserts short-circuit. A provider's "suggested range" is **never followed** — the window halves. |
| H11 | **State and logs need different endpoint pools.** publicnode refuses archive `eth_getLogs`. | WP2.1 | Two pool lists, structurally separate, with a banned-host frozenset (`eth.llamarpc.com`, `rpc.ankr.com`, `cloudflare-eth.com`, `api.reservoir.tools`, `*.alchemy.com`, `infura.io`, any `etherscan.io`). Constructor raises on a banned host; a test asserts publicnode is absent from the logs pool. |
| H12 | **`timeLeftInHour()` returns `hourDuration`, never 0, at an exact boundary.** | WP3.2 | A "0 seconds left" render is unreachable; the countdown formatter is tested at 3600 and 1. |
| H13 | **The in-progress hour is never judged.** `_isShort` returns false while `lastActive == hour`. | WP3.8 | The judged-hour fold excludes the current hour; a test at the exact boundary asserts the hour that just completed becomes judgeable and the new one does not. |
| H14 | **~~Tenderly's `eth_getLogs` returns no `blockTimestamp`~~ — REFUTED 2026-08-17.** Every one of the 377 RPC rows carries `blockTimestamp` and every one of the 376 Blockscout items carries `block_timestamp` (`test_every_captured_log_carries_a_block_timestamp`). The real hazard is the inverse: *discarding* a stamp you were handed, then paying a round trip to re-fetch it. | WP2.8 | Deposit wall-clock stamps are read off the log row; the bounded `eth_getBlockByNumber` batch (state pool, distinct blocks of the newest N rows) is the **fallback** for an endpoint that omits the field. Hour buckets need **no** timestamps at all: the hour is an indexed topic and its wall-clock is `launchTime + hour * hourDuration`, exact by construction. A missing stamp renders `--:--`, never `00:00`. |
| H15 | **Deposits after death revert; the backfill grows unbounded** if the game survives weeks. | WP5.5 | The folded contributor table and the hourly series are persisted; the raw per-event history stays on disk unfolded and is capped by a documented row limit with the drop counted and logged. Compaction is PRD §12 material, not v1. |

---

## Known gaps carried into implementation

Not blockers. Each is a decision the implementer confirms against the live chain rather than
an assumption the plan hides.

- **~~The sqrt curve has no committed onchain cross-check~~ — CLOSED 2026-08-16 22:51:43Z.**
  The premise was right when it was written: the 21-call round holds only parameterless views.
  WP1.6 then ran, and `captures/live/20260816T225143Z_curve-probe.json` holds
  `previewPoints(uint256)` for twelve weights and `pointsOf`/`weightOf` for four real wallets —
  20 of 20 calls answered, every return equal to `(isqrt(weight) * rate) // 1e9` computed
  locally, with `0`, `1`, `1e9-1` and `1e9` all flooring to **0 points** (the floor is real, not
  a rounding artefact). It is now correct to say **"validated against chain"**, and
  `test_the_curve_matches_previewpoints_on_chain` is the assertion. WP3.3's transcription of the
  contract's own Newton loop stays as the second, independent witness. The *runtime* half of
  amendment A2 was struck rather than built (PRD §13): a client method for `SEL_PREVIEW_POINTS`
  would fetch, every session, a number no widget renders.
- **`HourSaved` may never fire.** It requires a judged hour to cross the threshold from below.
  If the game dies at hour 24 the event never exists, and the signal row must render its
  explicit never-fired state rather than waiting for a payload. Do not block on capture C's
  third component.
- **The WHALE (≥ 25 ETH) and cluster (≥ 3 wallets × identical amount × ≤ 32 blocks)
  constants are first guesses** (PRD §12). They are named constants in `analytics/`,
  constructor-injectable where it costs nothing, and re-tuned against post-grace data as a
  recorded amendment — not silently.
- **What the list gates is unknown.** No consumer contract exists. If one appears, a
  "consumer" signal row is an amendment with its own title-bar width measurement, not a v1
  edit.
- **The dashboard may launch into a settled game.** SETTLED is a first-class phase, built and
  tested as a normal state, never an error. The whole log history stays keylessly fetchable
  forever, so the archive is complete regardless of when the build finishes.
- **~~Blockscout log items carry no per-log block timestamp~~ — wrong, and corrected by the
  WP0 capture pins.** Blockscout items carry `block_timestamp` and the RPC rows carry
  `blockTimestamp`; the planning read confused those with `FirstDeposit`'s own *data* field,
  which is also present. The block-timestamp batch survives as a fallback only (H14).

---

## Spec amendments proposed

The PRD is authoritative and was not redesigned. Four things found while planning against the
real captures and the real source should be corrected or made explicit; none changes scope.

1. **`earlyBps` at capture is 1.9491×, not ~1.99×.** `results.json` id 6 is `0x4c23` = 19491.
   Anything quoting ~1.99 for the committed captures is wrong; the 1.9342× in the mechanics
   doc (21:33 UTC) and the 19975 bps of the first-deposit cross-check are both consistent.
   *Affects:* nothing structural — but a fixture calibrated to 1.99 would silently miscompute
   every weight in a test.
2. **PRD §5's fast tier should name `previewPoints(uint256)` as a `once`-tier probe.** The
   YOU row's `you_marginal_points` is specified as "`previewPoints`-equivalent applied to
   `requiredNext`", i.e. recomputed locally. That is correct and cheap — but with no captured
   `previewPoints` return, the recomputation has no onchain witness. Adding one argument-taking
   call to the capture set (WP1.6) makes the curve claim verifiable instead of merely
   transcribed. *Proposed:* add it to the `once` tier and to the capture script.
3. **PRD §8's third mandated mutation is mis-aimed.** "The curve floor (mutate `//` to
   `round` → the 0.099875 cross-check goes red)" — the 0.099875 example exercises
   `weightAdded = creditedDelta × earlyBps / 10_000`, which is the *weight* formula, not
   `_curve`'s integer sqrt. Both deserve a mutation and they are different code. *Proposed:*
   split into H8 (weight floor, witnessed by 0.099875) and H7 (sqrt floor, witnessed by the
   Newton transcription and, once captured, by `previewPoints`). Both are in this plan.
4. **PRD §5's log tier needs a block-timestamp source.** Tenderly's `eth_getLogs` returns no
   `blockTimestamp`, and Blockscout's log items do not carry one either, so
   `CuratorActivity`'s `HH:MM` column has no specified provenance. *Proposed:* a bounded
   `eth_getBlockByNumber` batch on the **state** pool over the distinct blocks of the rendered
   window (H14), with `--:--` as the explicit unavailable stamp. This is additive and costs
   one batched round per medium tick at most.

One thing the repo **contradicts** in the PRD, and it is in the PRD's favour:

- PRD §9.4 says "keys stay contiguous 1..8 (existing test asserts)". The test exists but is in
  `tests/test_fwa_theme.py:490` (`keys == [str(i) for i in range(1, len(GAMES) + 1)]`), not in
  a registration test file. WP7.4 must run **that** file, and WP7.6's new
  `tests/test_curator_registration.py` should not duplicate the assertion.

---

## Definition of done

PRD §11's success criteria, verified by WP7's integration tasks:

1. `.venv/bin/python -m pytest` is fully green; `cargo test` (from `maxpane/`) is untouched
   and green. No existing dashboard's tests change except the registration tests that derive
   from `GAMES`.
2. GRACE, JUDGED and SETTLED each render from fixtures through the real screen, asserted on
   composited output; the settled screen renders a **final** framing, not a staleness warning.
3. Under a full outage after settlement was observed, the dashboard still renders SETTLED —
   the outage degrades the freshness marker, never the phase.
4. The **four** mandated prove-it-bites mutations — settlement latch, hour-boundary fold,
   curve floor and weight floor, the fourth split out by amendment 3 above — were each
   performed, watched go red, and restored, with the evidence recorded in WP7.12. **Done
   2026-08-17**, eight mutations in total (the latch and the fold each needed two halves to
   reach their tests, and the curve floor has three variants); every one reddened a *named*
   test and `git status --short` was empty after each restore.
5. The full layout is **measured** at ≤ 143 columns, so `__main__.FULL_LAYOUT_COLUMNS` does
   not move; below it every shed column is advertised with `‹ widen` and nothing clips dark.
6. The six registration surfaces agree: `--game curator` launches, menu key `2` opens it,
   `tab` cycles through it, `q` closes `CuratorManager`, `initial_game="surf"` and
   `default="surf"` are unchanged and verified.
7. Keyless end-to-end on a fresh install, backfill included: zero API keys, zero signing
   paths, zero network access in the test suite.

---

## Status at the close of WP7 — 2026-08-17

All eight work packages landed. This section is the plan's own reconciliation: what is true
now, and what in the document above was already struck rather than deleted.

**Shipped.** `--game curator` is registered on all six agreeing surfaces (`app.py` wiring +
`_GAME_CYCLE`, `MaxPaneApp.__init__`'s `initial_game` verified untouched, `__main__.py`'s
`--game` choices, `GAMES` at menu key **2** with 3..8 renumbered, CLAUDE.md's eight-row table,
README's table and usage block), plus the curator block appended at the end of
`themes/minimal.tcss`. Suite: **4287 passed, 0 failed**; `cargo test` 17 passed, untouched.

**Definition of done, item by item.**

1. Green, and `cargo test` untouched — yes. The only pre-existing tests that changed are the
   registration ones: `tests/test_app_startup.py` (`ALL_GAMES`, `MANAGER_ATTRS`),
   `tests/test_surf_registration.py` (`MANAGER_ATTRS`) and `tests/test_fwa_theme.py`'s
   append-only stylesheet guard, which every previous dashboard also moved.
2. GRACE, JUDGED and SETTLED each render through the real screen on composited output — yes,
   and the settled framing is an archive, not a staleness warning.
3. SETTLED survives a total outage — yes, and the mutation that breaks it is recorded.
4. Four mutations, eight applications, each reddening a named test — yes.
5. Measured **138** columns, so `FULL_LAYOUT_COLUMNS` did not move from FWA's 143 — yes.
6. The six surfaces agree; `surf` is still `GAMES[0]`, still the `--game` default and still the
   bare-app prefetch — yes, pinned in two files.
7. Keyless end-to-end — yes. `rg -i "api_key|apikey|x-api-key|Authorization|keystore|
   private_key"` over the whole package returns **zero** hits, and the guardrail scans in
   `tests/test_curator_registration.py` keep it that way.

**Verified against the live chain on 2026-08-17** (grace hour 11-12), not just against
fixtures: the top three folded leaderboard rows equal `pointsOf(address)` read straight off
publicnode — 36,924 / 33,547 / 30,853, wei-exact — which validates the sqrt curve, the weight
fold and the leaderboard end to end. `contributors_total` / `deposits_total` track `stats()`
live rather than the fold. `FORCED ETH` renders `—`. The countdown to 19:58:47 UTC is exact.

**Two findings from the smoke run, reported and not fixed** (they belong to WP2/WP4/WP5):

- **First paint costs about three minutes.** `fetch_blockscout_logs` takes ~196 s of a ~190 s
  first cycle, paginating 10,000+ logs; the cache does not help, because the cost is the REST
  cross-check and not the backfill. It is TTL'd, so the second cycle is 0.8 s — but the manager
  publishes one flat dict per cycle, so the screen shows "Loading..." until the slow tier
  returns. H15 anticipated unbounded growth; the scale arrived faster than the plan assumed
  (145 contributors and 231 deposits at capture, 8,000+ and 10,000+ thirteen hours later).
- **The YOU row cannot tell "no wallet configured" from "the wallet read failed."** Both
  produce five `None` `you_*` keys, so under an outage the row reads `set MAXPANE_WALLET` at a
  user who has set it. The title bar does say `⚠ … wallet`, so the degradation is advertised —
  the row's own copy is what is wrong. A `you_configured` flag in the flat dict would close it.

### Wave-5 repair pass (2026-08-17, after review)

Five findings against the registered build, each verified before it was touched. The first of
the two smoke-run findings above (the three-minute first paint) is **closed** by item 3; the
second (the YOU row's `set MAXPANE_WALLET` under a wallet outage) is **not**, and is still the
one open defect from that pair. `degraded` now reaching a widget makes it cheap: the same key
that fixed item 5 tells that row whether the wallet group answered.

1. **`tests/test_game_select_quit.py` kept a real `CuratorManager`.** `MANAGER_ATTRS` lives in
   *four* test modules and wave 5 grew three; the fourth left the real manager on the app, so
   the `q` those headless tests press awaited its real `close()` and rewrote the developer's own
   7.5 MB `~/.maxpane/curator_cache.json` with an empty one. Reproduced against a redirected
   `HOME`. The list stays hardcoded in all four; the agreement test now walks `tests/` for every
   copy and compares each against the managers `MaxPaneApp.__init__` builds, so a fifth is
   covered the day it is written. CLAUDE.md named two files and now names four.
2. **The cluster table cut its own headline number.** `_POINTS_COLS` was a hand-typed 8 and the
   live top row is 2,663,784 points, so it rendered `2,663,78` at 138, 143, 200 and 250 columns
   with no `‹ widen` — a cell width is fixed while a panel's is not. Now derived from the same
   two bounds `_PATTERN_COLS` uses (a row's `points` is the *sum* over its members, so the
   per-wallet ceiling does not bound it); tier costs 45 → 47 and 33 → 35. Every clusters fixture
   had happened to pick a value that fits 8, which is why the suite was green over it.
3. **First paint no longer waits on the cross-check** (PRD A5). Detached, one at a time,
   cancelled by `close()`.
4. **`dropped_events` is persisted.** The in-process fix for the history cap died at the file:
   a relaunched cache reported 0 dropped, so once the cap trips every launch declares the fold
   short against the contract's counter and re-sweeps from the creation block. ~890 deposits/h
   puts 25,000 about fifteen hours after launch — shortly after the first judged hour.
5. **HOUR SAVED and WHALE go `-- unknown` when the logs pool is dead** (PRD A6).

Curator's measured width is unchanged at **138**, and `FULL_LAYOUT_COLUMNS` stays FWA's 143.

**Still open, and deliberately.** The synthetic-fixture ledger closed *open*: 33 markers, none
re-pointed, because captures A, B and C had not happened yet — see "Synthetic until captured"
above and the marker inventory in `tests/fixtures/curator/captures/live/README.md`. The WHALE
and cluster constants are still first guesses (PRD §12). What the list gates is still unknown.
