# CURATOR Dashboard ("THE LIST") — PRD

Dashboard #11 (8th visible), `--game curator`, menu position **2** (right after Surfboard,
same surfsurf.eth universe), titled **THE LIST**. Subject: the `WhitelistCurator` contract at
`0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91` on Ethereum mainnet — surfsurf.eth's
zero-custody allowlist game with an hourly doomsday clock. Companion research:
`docs/curator_game_mechanics.md`. Raw captured payloads:
`tests/fixtures/curator/captures/`.

## 1. Product summary

THE LIST is a survival watch. The contract refunds every wei it is ever sent; what persists
is a permissionless whitelist — each wallet's high-water single send, a weight, a sqrt-curve
points score. Two rules make it watchable: **escalation** (only beating your own high-water
mark counts, minimum step 0.1 ETH) and **settlement** (after a 24 h grace period, any
completed clock hour that attracts less than 5 ETH of raw volume freezes the list forever).
The dashboard exists to watch that clock — and to remain the game's archive after the clock
wins.

### Why this subject earns a dashboard

- It is a genuinely novel onchain mechanism (zero custody, gas-priced participation,
  lazy derived settlement) from the dev MaxPane already tracks with the surf dashboard.
- It launched **unannounced** on 2026-08-16 19:58:47 UTC and found 8400 ETH of flow within
  100 minutes purely onchain — the game is live *now* and its first possible death is
  2026-08-17 20:58:47 UTC.
- The endgame is a single, terminal, time-critical event — exactly the shape MaxPane's
  detector-and-degrade architecture is good at (surf's hook launch, FWA's gate).
- The contract's own doc comment delegates sybil analysis to consumers of its event data;
  a read-only dashboard is the intended consumer.

### Live scale (verified 2026-08-16, moving fast)

At 21:13 UTC (75 min old): 145 contributors, 231 deposits, 1630 ETH gross routed.
At 21:33 UTC (95 min old): **252 contributors, 497 deposits, 8401 ETH routed, 7549 ETH in
the then-current hour alone**, early multiplier 1.9342×. Leaderboard at 21:13: #1 credit
461.1 ETH (ladder 1.1 → 461.1), #2 170 ETH, #3 63.5 ETH, ranks 4–12 held by a 9-wallet
farm that sent exactly 60 ETH each inside a 6-minute window — the fan-out pattern the sqrt
curve rewards and the contract's docs predict. Every number here will be stale by build
time; they document scale, not state.

## 2. Scope

**In:** one new dashboard (screen + widget package + 4-module data layer + pure analytics),
registered on all six surfaces at menu position 2; three-phase screen (GRACE / JUDGED /
SETTLED); YOU row when `MAXPANE_WALLET` is set; fan-out cluster flags; captured-payload
fixtures.

**Out (deliberate):**
- **No change to the surf dashboard.** No seventh detector row, no new `KNOWN_LABELS`
  entry, no cross-widget. Surf's layout is settled and its PRD warns against re-cutting it.
- No ENS resolution (keeps every rendered string self-generated hex; still `safe_markup`
  everything at the boundary per convention).
- No funding-source sybil tracing (needs per-wallet tx history — heavy; v1 clusters on the
  event data alone, which is what the contract's docs suggest).
- No per-second ticking countdown. Clock values are poll-anchored (fast tier 15 s) like
  every other MaxPane age/countdown; the title bar carries staleness.
- Volume is **never** rendered as TVL, balance, or capital at risk (see §6).

## 3. The flagship: the settlement state machine

One derived value, `phase`, drives the screen. It is computed in `analytics/` from
fast-tier reads plus the injected clock — never from wall time inside a widget.

| phase | when | CLOCK hero | CURVE hero |
|---|---|---|---|
| `grace` | `now < launchTime + 86400` and not settled | `GRACE — judging begins in HH:MM:SS` (absolute end time as subtitle) | live early-bird decay `1.93×`, and "1 ETH buys ≈ N pts now" via the pure curve math |
| `judged` | grace over, `isSettled() == false` | `HOUR N · fed X.XX/5.00 ETH · MM:SS left` from `ethNeededThisHour()` / `timeLeftInHour()` | SURVIVAL: judged hours survived, closest call so far (`min margin @ hour H`) |
| `settled` | `isSettled() == true` | `SETTLED AT HOUR N · lived Dd HHh` | final records: contributors, volume, top score |

**Settlement truth and the latch.** `isSettled()` (eth_call) is the truth; the `Settled`
event is only the obituary — `settle()` is permissionless and may lag death indefinitely.
The moment a fetch observes `isSettled() == true`, the manager persists an **evidence
record** `{value, block_number, observed_at}` to the cache (the re-validated-record pattern
from surf's `hook_status` fix). From then on the dashboard renders SETTLED even through RPC
outages — an outage degrades the *freshness* marker, never the phase. Unlike surf's hook
detector, this latch cannot be griefed: it reads a one-way predicate the contract itself
enforces (deposits revert `AlreadySettled` after any judged hour fails), not
attacker-emittable logs. The `Settled` event, once seen on the logs tier, fills in the
obituary details (final hour, timestamp, totals).

**HOUR AT RISK.** In `judged` phase: `needed > 0` lights the signal yellow ("hour needs
X ETH"); `needed > 0` with fewer than 900 s left lights it red. In `grace` it renders as an
explicit `n/a until hour 24`, never blank. Thresholds are named constants in `analytics/`.

## 4. Widget mapping

Template-derived layout (canonical slot grid per `screens/talismans.py:58-80`, budgets
mirrored not invented). All widgets receive primitives only.

| Slot | Widget | Content |
|---|---|---|
| `#title-bar` | Static | `THE LIST · hour N · GRACE/JUDGED/SETTLED · as-of/⚠ markers` (degraded groups named, surf-style) |
| hero row (3 boxes) | `CuratorHero` | **CLOCK** (phase table above) · **LIST** (`252 wallets · 8401 ETH routed (all refunded) · list OPEN/FROZEN`) · **CURVE/SURVIVAL** (phase table above). Missing value → explicit `unavailable` (MEDI-38) |
| middle left | `CuratorLeaderboard` | top 10 by points: rank, truncated addr, points, credit ETH, ladder tx count, `⚑` cluster flag. The wallet's own row is emphasized if it appears in the top 10 — the YOU signal row (below) is the single dedicated YOU surface |
| middle right (rail top) | `CuratorSparklines` | hourly raw volume + cumulative contributors — **fed exclusively from folded `Deposited` logs**, never from `currentHourTotal()` polling (§6) |
| middle right (rail bottom) | `CuratorSignals` | SETTLED · HOUR AT RISK · HOUR SAVED (last savior + hour) · WHALE (largest single deposit last 60 min when ≥ 25 ETH) · FARM (newest cluster: `9×60Ξ, 6 min`) · FORCED ETH (anomaly, expected `—`) · YOU (rank · pts · `next ≥ X.XX ETH` from `requiredNext`) |
| bottom left | `CuratorActivity` | newest-first deposit feed: `HH:MM 0x1234…abcd 3.60Ξ (+2.80 credit → 7.03 wt) tx#4`, HourSaved rows highlighted, FirstDeposit rows tagged `joined`. De-dupe by (tx, log index); every formatting step degrades (MEDI-37) |
| bottom right (swap slot, key `c`) | `CuratorClosestCalls` ⇄ `CuratorClusters` | closest calls: judged hours by ascending margin, savior wallet; explicit `no judged hours yet — judging begins <UTC>` state. Clusters: size × amount, block window, combined points, share of total points. Default shows CLUSTERS until the first judged hour completes, then CLOSEST CALLS; `c` toggles anytime (FWA's swap pattern, phase-aware default) |
| bottom dock | `StatusBar` | shared widget, unchanged |

**Width:** measured, never reasoned. Target: full layout clears at ≤ 143 columns so the
app-wide `FULL_LAYOUT_COLUMNS` does not move (FWA's 143 stays the binder). Cells sized to
their producers' actual vocabularies (the `dev/ops` lesson): addresses render truncated
`0x1234…abcd` (13 cols), amounts as the market-panel style compact ETH. If the swap-slot
tables cannot clear, they shed columns with `‹ widen`, they do not raise the constant.

## 5. Data layer

### Endpoints (all keyless, all validated in this research)

| purpose | endpoint | validated |
|---|---|---|
| state (batched `eth_call`, `eth_getBalance`) | `ethereum-rpc.publicnode.com` | all 21 parameterless views in one batch round, zero failures. **403s python-urllib's default UA — client sets a real User-Agent** |
| logs primary | `gateway.tenderly.co/public/mainnet` | full-history `eth_getLogs` from deploy block `25769870` in one sweep (377 logs) |
| logs failover | `eth.drpc.org` | failed once with routing message text — classify by message, fail over |
| REST cross-check / gap repair | `eth.blockscout.com/api/v2` | logs pagination (8 pages) reconciled exactly with the RPC sweep |

State and logs pools stay separate (CLAUDE.md rule). No Etherscan (403 to fetchers, keyed
API).

### Addresses (vendored constants module `data/curator_addresses.py`)

Contract, deployer (= surf's dev wallet, but constants are NOT imported across dashboard
data layers — re-vendored with a comment), creation tx/block, all six event topic0 hashes
**with their Solidity preimages** (tests recompute every hash), selector table for the
view batch with preimages. ABI vendored under `abis/` from the verified source.

### Refresh tiers (`data/curator_cache.py`, persisted to `~/.maxpane/curator_cache.json`)

| tier | period | contents |
|---|---|---|
| `fast` | 15 s | one batched eth_call round: `isSettled`, `currentHour`, `currentHourTotal`, `ethNeededThisHour`, `timeLeftInHour`, `lastActiveHour`, `earlyMultiplierBps`, `stats`; `eth_getBalance(contract)` (forced-ETH anomaly); + 6 YOU calls (`pointsOf`, `weightOf`, `contributedBy`, `txCountOf`, `firstHourOf`, `requiredNext`) when `MAXPANE_WALLET` set |
| `medium` | 60 s | incremental `eth_getLogs` from last-seen block + 1; folded into the contributor table, hourly series, clusters; detects `Settled`/`Rescued`/`HourSaved`. Deposit wall-clock stamps come from the log rows themselves — **corrected 2026-08-17: they do carry timestamps.** All 377 RPC rows in `tenderly_logs.json` have `blockTimestamp` and all 376 Blockscout items have `block_timestamp` (pinned by `test_every_captured_log_carries_a_block_timestamp`). The bounded `eth_getBlockByNumber` batch on the **state** pool is therefore a *fallback* for an endpoint that omits the field, not the primary source — a client that discards a stamp it was handed pays a round trip for nothing. A missing stamp renders `--:--`, never `00:00`. Hour buckets need no timestamps — the hour is `Deposited`'s indexed second topic and its wall-clock is `launchTime + hour × hourDuration`, exact |
| `slow` | 420 s | Blockscout cross-check of `stats()` vs folded totals; gap repair if the incremental fold ever skipped blocks across a failover |
| `once` | ∞ | the 8 immutables + `Launched` event + `POINTS_PER_ETH`. ~~Plus a `previewPoints(uint256)` probe~~ — **struck 2026-08-17**: the witness it was meant to provide already exists as a committed capture (`captures/live/20260816T225143Z_curve-probe.json`, 20/20 calls matching `(isqrt(w)*rate)//1e9`), so a runtime probe would be a read every session that nothing renders. See §13 A2 |

First install backfills the full log history from block 25769870 (validated: one sweep).
Failure never marks a tier fetched (`TIER_FAILURE_BACKOFF_SECONDS` per tier, house
pattern). Persisted: folded per-contributor table, hourly volume series, contributors
series, last-seen block, settlement evidence record, cluster state, schema version. Every
persisted series loads through `data/series_points.coerce_points`. All loaders take `now=`.

### Manager data contract (frozen — the parallel-agent interface)

`data/curator_models.py` exports `CURATOR_KEYS` + `CURATOR_ROW_KEYS`; models are wei-native
frozen dataclasses (failable fields `| None`, never 0); the manager divides to ETH exactly
once. Planned flat keys (models module is the source of truth at freeze):

- phase machine: `phase`, `settled`, `settled_hour`, `settled_at_ts`, `lived_desc`
- clock: `current_hour`, `hour_fed_eth`, `hour_needed_eth`, `hour_seconds_left`,
  `grace_seconds_left`, `grace_ends_utc`
- curve: `early_multiplier_x`, `points_per_eth_now`, `survival_streak_hours`,
  `closest_call_margin_eth`, `closest_call_hour`
- list: `contributors_total`, `deposits_total`, `volume_routed_eth`, `top_points`
- signals: `last_saved_hour`, `last_saved_wallet`, `last_saved_age_s`,
  `whale_amount_eth`, `whale_wallet`, `whale_age_s`, `clusters_count`,
  `flagged_points_share_pct`, `forced_eth`, `rescued_total_eth`
- YOU (all `None` when no wallet): `you_rank`, `you_points`, `you_credit_eth`,
  `you_required_next_eth`, `you_marginal_points`
- rows: `leaderboard_rows`, `activity_rows`, `closest_call_rows`, `cluster_rows`,
  `volume_series`, `contributors_series`
- health: `degraded` (group names ⊆ {`state`, `logs`, `wallet`}), `as_of_hhmm`

### Analytics (`analytics/curator_signals.py`, pure, no I/O, `now_ts` injected)

Phase derivation; at-risk logic; streak/closest-call folds; the curve math
(`weight = creditedDelta × earlyBps // 10_000`, integer sqrt with the contract's exact
floor correction — cross-checked in tests against the captured live event where 0.05 ETH at
19 975 bps produced 0.099875 weight to the wei); marginal points for YOU
(`previewPoints`-equivalent applied to `requiredNext`); **cluster heuristic v1**: among
single-deposit wallets, groups of ≥ 3 with byte-identical amounts landing within ≤ 32
blocks. Rendered as `⚑` "fan-out pattern" — pattern language only, never accusation.

## 6. Correctness rules

- **Gas-priced, not capital-priced.** Every wei is refunded in-tx, so volume, hourly totals,
  contributor counts and HourSaved are all fakeable for the price of gas. Copy reads
  "routed (all refunded)"; nothing is ever labeled TVL/locked/at-risk. The one honest
  capital statement (EOA-only gate ⇒ each high-water mark was really held in a real EOA at
  that moment) may appear once, as subtitle text.
- **Poll `isSettled()`; treat `Settled` as the obituary.** Evidence-record latch per §3.
- **The hour-boundary illusion.** `currentHourTotal()` legitimately drops to 0 at every
  boundary while `lastActiveHour()` still shows the previous bucket. History series are fed
  from `Deposited` logs only; the fast tier never writes into a series. A failed read is
  `None`, never 0, and no sentinel ever enters a persisted series.
- **`creditedDelta == 0` is a legitimate event** (deposit above the 1000 ETH cap still
  counts fully toward hourly survival). No division by it; weight ∝ volume is false.
- **Nonzero contract balance is always forced ETH** (anomaly signal), never deposits.
- **Packed-struct off-by-one:** use `firstHourOf()` semantics (raw `contributors()` carries
  a +1 offset); `FirstDeposit.index` is 1-based.
- **Read config live, hardcode nothing documented:** the 8 immutables come from the `once`
  tier, not from this PRD's table.
- Dead source ⇒ explicit unavailable state or last-good behind `as of HH:MM`; degraded
  group names in the title bar; total failure returns the full key contract, all `None`.
- Every rendered string through `widgets/markup_safety.safe_markup` after flattening and
  truncation, even though v1 renders only self-generated hex/numbers.
- `RefreshGuard` for the screen; `sparkline_common` for sparklines; no widget imports from
  `data/` or `analytics/`.

## 7. Time-sensitive context (true on 2026-08-16, will change)

- Grace ends **2026-08-17 19:58:47 UTC**; the first judged hour completes **20:58:47 UTC**
  — the earliest possible settlement. The dashboard may well launch into a settled game;
  SETTLED is a first-class phase, not an error state, and the log history (the whole game)
  stays fetchable keylessly forever.
- The launch remains unannounced everywhere we can read (announce channel, X, Farcaster,
  Dune, Mirror as of 21:13 UTC). What the list gates is unknown. A retro-announcement or a
  consumer contract may appear any day; both are §12 material, not blockers.
- The live-scale numbers in §1 were exploding while measured (5× volume in 20 minutes) —
  every fixture states its capture block, and tests never assert live-looking magnitudes.

## 8. Testing

- **No test touches the network** — transports raise on use; fixtures derive from the real
  captures in `tests/fixtures/curator/captures/` (see its README for provenance), curated
  into small per-test files. The cap-exceeding `creditedDelta == 0` case has no real
  instance yet and ships as a clearly-marked synthetic fixture.
- Phase coverage: GRACE / JUDGED / SETTLED each render from fixtures; the settled screen
  renders with a *final* framing, not staleness warnings.
- **Prove-it-bites mutations** (house rule, mandatory for these) — four, not three
  (amendment A3: the original third item conflated two different pieces of code):
  1. the settlement evidence latch (mutate to re-read-through → red under simulated outage);
  2. the hour-boundary rule (mutate the fold to consume `currentHourTotal` → a boundary
     fixture writes a zero → red);
  3. the **weight** floor, `creditedDelta × earlyBps // 10_000` (mutate `//` to `round` → the
     0.099875 cross-check goes red — that captured event witnesses *this* formula);
  4. the **curve** floor, `points = isqrt(weight) × 1000 // 1e9` (mutate `isqrt` to
     `int(math.sqrt(...))` → the differential against the contract's Newton loop goes red).
- Composited-output assertions (`render_strips`) for every widget; a column-by-column width
  sweep pinning the measured full-layout number and the `‹ widen` markers below it.
- Registration tests derive ids from `GAMES` (never hardcoded), mirroring
  `tests/test_surf_registration.py`; contiguous-keys test covers the position-2 insert.
- Analytics: pure, exhaustive edge tests (hour 0, grace boundary alignment, empty history,
  single contributor, cluster of exactly 3, `requiredNext` for unranked YOU).

## 9. Registration checklist (the six agreeing surfaces)

Insert at menu position 2 — every key below shifts down one; order of work:
**app.py → `__main__.py` → `GAMES`** (registration tests derive from `GAMES`, so it grows
last).

1. `app.py`: `CuratorManager` wiring, screen install, close-on-quit, `_GAME_CYCLE` insert
   `"curator"` after `"surf"` (hand-typed literal, per the redundancy-plus-agreement-test
   pattern — do not derive).
2. `app.py` `MaxPaneApp.__init__` `initial_game="surf"` — **untouched**, but verified: the
   sixth surface, pinned by `test_a_bare_app_prefetches_the_dashboard_the_menu_opens_on`.
3. `__main__.py`: add `curator` to `--game` choices; `default="surf"` untouched.
4. `screens/game_select.py` `GAMES`: row 2 `("2", "curator", "THE LIST", …)`; keys stay
   contiguous 1..8 (existing test asserts).
5. `CLAUDE.md`: dashboard table becomes eight rows ("The eight visible dashboards"), surf
   remains default; adjust every "seven" reference.
6. `README.md`: table + usage examples.

## 10. Theme

No new theme in v1. THE LIST renders correctly under all ten registered themes; the default
`minimal.tcss` gets only the widget-scoped additions the new classes need. (A dedicated
doomsday theme is §12 material.)

## 11. Success criteria

- `pytest` fully green including the new suite; every new detector/decoder test proven to
  bite; `cargo test` untouched and green.
- Full layout measured ≤ 143 columns so `FULL_LAYOUT_COLUMNS` does not move; below it,
  every shed column is advertised (`‹ widen`), nothing clips dark.
- All three phases reachable from fixtures and from live chain; a settled contract renders
  an archive, not an error; an RPC outage after observed settlement still renders SETTLED.
- Keyless end-to-end on a fresh install (backfill included); zero API keys, zero signing
  paths.
- The six registration surfaces agree; `--game curator` launches; menu key `2` opens it;
  `tab` cycles through it.

## 12. Open questions (not blockers)

- **What does the list gate?** Unknown; when a consumer contract appears, a "consumer"
  signal row could join the rail (new measurement of the title-bar worst case — treat as an
  amendment).
- Retro-announcement watch: if the announce channel posts about the curator, does THE LIST
  quote it (would import surf's feed decoding — deliberately out of scope v1)?
- WHALE (25 ETH) and cluster (≥3 × identical × ≤32 blocks) constants are first guesses;
  re-tune against post-grace data and record as amendments.
- If the game survives weeks, the `Deposited` backfill grows unbounded — revisit compaction
  of the folded contributor table (the per-event history can stay unfolded on disk).
- A per-second ticking clock hero (widget-local timer fed by an injected anchor) — only if
  the poll-anchored MM:SS feels dead in real use.

## 13. Amendments

Applied 2026-08-17 after planning against the real captures and the verified source
(`docs/curator_implementation_plan.md` §"Spec amendments proposed"). None changes scope.

| # | change | why |
|---|---|---|
| A1 | none to this document — recorded as a fixture-calibration warning | `earlyMultiplierBps()` in the committed captures is `0x4c23` = **19491 bps = 1.9491×**. §1's 1.9342× (21:33 UTC) and the mechanics doc's 19975 bps first-deposit cross-check are both consistent; a fixture calibrated to a remembered "~1.99×" would silently miscompute every derived weight |
| A2 | §5 `once` tier gains a `previewPoints(uint256)` probe — **half-applied, then half-struck** | the premise was right: the 21-call captured round holds only parameterless views, so the curve had no onchain witness. The *capture* half shipped and settled it — `captures/live/20260816T225143Z_curve-probe.json`, 20 of 20 calls matching `(isqrt(w)*rate)//1e9`. The *runtime* half was never wired (no client method for `SEL_PREVIEW_POINTS`) and is now struck rather than built: it would fetch, every session, a number no widget renders, to re-prove something a committed fixture proves once. The curve is witnessed; the probe is not needed |
| A3 | §8's three mandated mutations become four | the 0.099875 example witnesses the *weight* formula, not `_curve`'s integer sqrt — two different pieces of code, each needs its own proof |
| A4 | ~~§5 `medium` tier gains a bounded `eth_getBlockByNumber` batch as the activity feed's timestamp source~~ — **refuted the next day, and demoted to a fallback** | the premise was wrong. WP0's capture pins prove every one of the 377 RPC log rows carries `blockTimestamp` and every one of the 376 Blockscout items carries `block_timestamp`; only the *hazard doc's* reading of `bs_page_*.json` was mistaken. The feed reads the stamp it is handed and falls back to `eth_getBlockByNumber` only for an endpoint that omits it. Left in the log rather than deleted: the amendment was applied and then disproved by evidence, which is the record worth keeping |

Applied 2026-08-17 by the wave-5 repair pass, after the review of the registered build. Neither
changes scope; both change a §5/§6 detail the earlier text got wrong.

| # | change | why |
|---|---|---|
| A5 | §5's `slow` tier runs **detached**: `fetch_and_compute` starts the Blockscout cross-check and never awaits it | awaiting it put first paint behind a read of the contract's *entire* log history — measured through the real app at **201.2 s** to first payload, of which `fetch_blockscout_logs` was 202.6 of the cycle's 203.8 s, while the next cycle took 0.8 s. The fold every panel renders was ready in under a second and the SIGNALS rail — the doomsday clock — was empty for three and a half minutes, on every launch. The cross-check publishes no key (it agrees with the fold or schedules a repair sweep), and a cycle without it is already the specified `{"ok": None, "checked": False}` state. Its cost still grows with the history while the 420 s period does not; paging only down to a persisted verified-to-block watermark is §12 material |
| A6 | §6's health list `degraded` is **dispatched to `CuratorSignals`**, not screen-only | three rail rows are folded from the logs group and only FARM could say so. `clusters_count == 0` is a representable "read it, found nothing"; `last_saved_hour` and `whale_amount_eth` have no such value, so HOUR SAVED and WHALE rendered a green `none yet` / `none this hour` off a refresh that never read the logs — §6's own "dead source ⇒ explicit unavailable state" rule, broken in the direction that reassures. `degraded` stays a title-bar key as well; it is the one `META_KEYS` entry any widget receives |
| A7 | §2/§4: the YOU row is no longer environment-only — `CuratorScreen` binds **`w`** | added 2026-08-17 on request, after the build. The row is the only actionable number on the screen and it stayed dark until someone edited a shell profile, while the app already owned a validating `WalletInputScreen` that persists to `~/.maxpane/config.toml`. A runtime switch is more than an assignment: `CuratorManager.set_wallet` also clears the within-TTL re-serve (`_fast_wallet`) and drops the `wallet` last-good — both are *about the old address*, and the last-good's payload is literally `{"address": <the old one>}` — then expires the fast tier, because a tier with 12 of its 15 seconds left is "fresh" and the row would stay empty after a keypress that looked like it worked. `NO_WALLET` now names the key before the variable. Four mutations proven to bite |
| A8 | §2/§4: THE LIST gains a **second view** behind `y` — the reader's own standing | added 2026-08-17 on request. §2 scoped the wallet to a single YOU row and that shipped; this is the follow-on, and it is presentation over data already in hand — the six wallet views the fast tier reads and the `Deposited` history the log sweep holds, so the view adds **no request**. Four quadrants: YOUR LADDER (every send, the multiplier it got, and whether it credited or was above the cap), YOUR STANDING (rank, score, banked weight, share of all weight, when it joined), YOUR NEXT MOVE (the requirement alone: `requiredNext` and the high-water mark it must beat) and WHERE IT GETS YOU (the consequence: the points that send buys, whether it is **enough to move up**, and what the rank above would cost). The requirement and its consequence are two different thoughts, and a reader deciding what to type wants the first one alone — which is also what made room for the honest third state: `you_next_send_passes` is `None` when the comparison could not be made, and rendering that as "not enough" would be a claim about a number nobody read. `y` swaps the **body** and leaves the hero in place, so the doomsday clock never leaves the screen — the view exists to decide what to send, and that decision is worthless without the clock it is racing. Nine new keys and one new row shape (`you_ladder_rows`, source-backed: `None` when the logs pool did not read, because an empty ladder rendered as fact tells a depositor they never deposited). Measured: the view clears at the same **138** columns, so nothing moved |

One repo fact that confirms rather than changes §9.4: the contiguous-keys assertion does exist,
but it lives in `tests/test_fwa_theme.py:490`
(`keys == [str(i) for i in range(1, len(GAMES) + 1)]`), not in a registration test file — so the
registration work package must run *that* file and must not duplicate the assertion.
