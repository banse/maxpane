# CURATOR sybil / fan-out detection — PRD

Expansion of dashboard #11 (`--game curator`, **THE LIST**) plus a new standalone, keyless,
maxpane-independent detection library. Companion research and measured analysis:
`docs/curator_sybil_detection.md`. Raw datasets: `docs/curator_sybil_data/`. Base dashboard
spec: `docs/curator_PRD.md` (this PRD supersedes its §2 "Out" line that scoped funding-source
tracing out of v1 — the user has now asked for exactly that).

Prompted by surfsurf.eth (Adam) 2026-08-17: *"removes clear sybils … Segment them on the per hour
event and multiplier … an 800 eth deposit for example can do whale lists … and OS the list."*

## 0. The four decisions this PRD is built on (user-confirmed 2026-08-17)

1. **Detection depth: full A+B+C** — logs, gas/nonce fingerprints, and the funding graph. The
   funding signal (funder-is-a-cluster-member: 10/10 on farms vs 0/47 controls) is the strongest
   discriminator and is worth the background Blockscout sweep.
2. **On-screen wording: pattern-language stays.** The dashboard keeps saying "linked wallets /
   fan-out / operators / ⚑" and never "sybil / cheat / fraud / attack". The three forbidden-word
   tests stay green. The **standalone library** is the artifact named "sybil"; it lives outside
   every scanned surface.
3. **A dedicated third view** in THE LIST holds the per-wallet linkage, Adam's list-wide segments,
   and the shareable cleaned-list export.
4. **Standalone form: an in-repo Python distribution** (sibling to the `maxpane/` Rust crate),
   installable and usable without maxpane, with a CLI and JSON output.

## 1. Product summary

Two deliverables, one dependency edge:

- **`sybilkit`** — a general keyless EVM sybil-cluster analysis toolkit. Pure-Python core (bring
  your own event data) + optional keyless fetchers + a CLI. Reusable by anyone; THE LIST is one
  preset. *(Name is a proposal — rename in review if preferred; `fanoutkit`, `clustre`,
  `chainsybil` are alternates. The rest of this PRD uses `sybilkit`.)*
- **The curator dashboard** gains a third view and a per-wallet "linked" line, all rendered in
  pattern-language, powered by `sybilkit` behind a maxpane adapter.

The honest framing, carried from the research: the contract's sqrt curve **pays `sqrt(k)` for
splitting one bankroll across `k` wallets**, and refunds every wei, so the population is farmed by
construction. We do not accuse; we **surface the shape** — "these 1,995 wallets are linked by an
identical 0.45 ETH send, a 2-block cadence, and a shared funder; together they hold 6.8% of all
points, a 44× sqrt subsidy" — and we let the reader see a **de-sybilled** version of the list.

## 2. Scope

**In:**
- A new standalone distribution `sybilkit/` (pyproject, `src/`, tests, CLI, benchmark gate).
- A maxpane adapter (`data/curator_clusters.py`) + a new detached cache tier/slot for the B+C
  background sweep.
- A third curator view (`MODE_ANALYSIS`, key `f`): operators, segments, cleaned-list + export.
- A "linked" line on the existing `y` wallet-standing view; a confidence-graded upgrade to the
  leaderboard `⚑` flag.
- New `CURATOR_KEYS` / `CURATOR_ROW_KEYS`, all rendered pattern-language, all `None`-not-`0`.
- Committed fixtures sliced from the research datasets; a labeled-subset regression gate.

**Out (deliberate):**
- **No new word on screen.** Pattern-language only; the forbidden-word tests are not amended.
- **No change to the surf dashboard** and no cross-dashboard wiring.
- **No Tier-A rewrite in v1.** `analytics/curator_signals.find_clusters` stays exactly as shipped
  (cheap, synchronous, feeds the FARM row and the `c`-view). The library re-implements Tier A for
  its own completeness; converging the two is a tracked follow-up, not v1 scope.
- **No per-second network.** The B+C sweep is background, long-TTL, cached, last-good.
- **No verdicts persisted.** Every stored result is revisable by a later crawl; nothing writes a
  boolean "is a sybil" into a history series.
- **No whole-chain graph mining, no `trace_`/`debug_`, no supervised ML, no keyed source.** Out of
  proportion for a TUI and/or non-keyless.
- **No signing, no allowlist mutation.** MaxPane is read-only; the "cleaned list" is an *export of
  our analysis*, never an onchain write.

## 3. `sybilkit` — the standalone library

### 3.1 Design rules (from the research, non-negotiable)

- **Score clusters, not wallets.** No per-wallet signal separated farms from power users in any
  measured study (ChainCred: 42% vs 32%, precision at base rate). A wallet is flagged only via a
  cluster.
- **Compound conditions.** A cluster forms only when its members are linked by **≥2 independent
  signal families** (amount, sequence, cadence, gas, funding). One family alone never convicts.
- **Minimum cluster size ≥5** (Hop used ≥10, LayerZero ≥20) — keeps one-human-few-wallets out.
- **Reasons, never verdicts.** Output is `reasons: [Reason(family, human_string, strength)]` +
  a `confidence` in [0,1]; multiplicative, graduated, not binary. Freshness *discounts*, never
  convicts.
- **Keyless, endpoint-failover, message-text error classification.** Never a key; never trust a
  provider's error *code* over its message.
- **`None` is a failed read; the three legitimate zeros are answers** (mirrors curator conventions):
  points-share unknown ≠ 0, "no cluster" ≠ "could not analyze".

### 3.2 Module layout

```
sybilkit/
├── pyproject.toml            own distribution; deps: httpx (sources only); core is stdlib
├── src/sybilkit/
│   ├── model.py              Deposit, Tx, Funding, Dataset (wei-native dataclasses, no maxpane)
│   ├── signals/
│   │   ├── amounts.py        identical + near-identical (±tol) amount groups           [tier A]
│   │   ├── sequence.py       consecutive-index runs; ladder-shape similarity           [tier A]
│   │   ├── cadence.py        per-block burst quantization; metronome drip              [tier A]
│   │   ├── split.py          optimal-split ≈ W/k weight signature                       [tier A]
│   │   ├── gas.py            priority-fee / max-fee / gas-limit / type uniformity       [tier B]
│   │   └── funding.py        first-funder graph; peel chains; funder ∈ cluster          [tier C]
│   ├── cluster.py            union-find over edges; ≥2-family gate; min-size; confidence
│   ├── report.py             Cluster{members, reasons[], confidence, points_share, span}
│   ├── labels.py             12 CEX hot wallets (from ChainCred) + infra fan-out exclusion
│   ├── curator.py            THE-LIST preset: sqrt curve, segments, cleaned-list
│   ├── sources/              logs.py · txs.py · blockscout.py (keyless, failover) — optional
│   ├── bench.py              labeled-benchmark regression gate (ChainCred pattern)
│   └── cli.py                sybilkit analyze|segments|export-clean-list
└── tests/                    pure-core TDD; MockTransport for sources; the benchmark gate
```

### 3.3 Public API (frozen in WP0)

```python
from sybilkit import Dataset, detect, DetectConfig

ds = Dataset.from_events(deposits, first_deposits, txs=None, funding=None)  # pure; wei ints
res = detect(ds, DetectConfig(min_size=5, min_families=2, near_amount_tol=0.10))

res.clusters            # list[Cluster] sorted by points_share desc
res.wallet(addr)        # WalletVerdict(in_cluster, cluster_id, reasons, confidence) | None
res.flagged             # set[str] lowercase, confidence ≥ threshold
res.total_points, res.flagged_points, res.clean_points

from sybilkit.curator import segments, clean_list
segments(ds, res)       # whale-operators, per-hour, per-multiplier, index-1000 cohort
clean_list(ds, res)     # ranked survivors + each reader's clean rank
```

Signals are pure `(Dataset, config) -> list[Edge]`; `cluster.py` unions edges and keeps only
components with ≥`min_families` distinct edge-families and ≥`min_size` members. The curve floors
integer-sqrt **exactly** like the contract (`isqrt(weight_wei) * 1000 // 1e9`).

### 3.4 CLI (keyless, JSON out)

```
sybilkit analyze --contract 0x… --from-block N --preset curator --out clusters.json
sybilkit segments --contract 0x… --preset curator
sybilkit export-clean-list --contract 0x… --preset curator --out clean_list.json
```

Sweeps logs, batches `getTransactionByHash`, runs the bounded Blockscout funding pass (resumable,
cached, throttled ~3 req/s), prints/writes `reasons`-shaped JSON. This is Adam's "OS the list" tool.

### 3.5 Packaging & tests

- Built independently: `python -m build sybilkit/`. The root publish workflow only builds maxpane,
  so publishing `sybilkit` is a separate job/tag — **noted for the packaging WP**, not auto-wired.
- `py.typed`; Python 3.11; deps limited to `httpx` (core importable with zero deps).
- **No network in tests** (structural + `MockTransport` doubles, mirroring the curator suite).
- **Benchmark gate**: a committed labeled subset (the 16 audited operators + controls from
  `docs/curator_sybil_data/`) with a precision floor and a median-gap ceiling — the ChainCred
  pattern that stops heuristics being tuned to zero recall. A `todo` marks the cluster-level target
  the wallet-level baseline can't meet, flipped to a real assertion when detection reaches it.

## 4. Detection tiers ↔ cache

| tier | where it runs | network | cadence |
|---|---|---|---|
| A (logs) | existing `find_clusters` (unchanged) **and** `sybilkit` | the sweep already done each refresh | fast (15 s) |
| B (gas/nonce) | `sybilkit` via maxpane adapter | ~1 batched `getTransactionByHash` per new deposit tx | medium, cached |
| C (funding) | `sybilkit` via maxpane adapter, **detached** | ~1–2 keyless Blockscout calls per contributor, resumable | slow tier, long TTL, last-good |

The B+C sweep uses the **detached-task precedent** (`_spawn_crosscheck`, curator_manager.py): a
full Blockscout read measured ~200 s and awaiting it in-cycle blanks the dashboard, so it runs
one-in-flight, publishes into a cache slot the next cycle reads, and stamps `as of HH:MM`.

- New cache tier (`TIER_ANALYSIS`, TTL ~30–60 min, backoff) + slot (`SLOT_CLUSTERS`) in
  `curator_cache.py`.
- **Degradation**: the third view must tell "analyzed, nothing linked" (representable zero) from
  "could not analyze" (`None` + a degraded group) — the FARM-row precedent. Fold the new analysis
  into the existing `logs` degraded group, or amend `CURATOR_DEGRADED_GROUPS` +
  `SOURCES`/`GROUP_SLOT` + tests together (do not add a group name silently — the title bar renders
  it verbatim).

## 5. The third view — `MODE_ANALYSIS`

A full body toggled from the dashboard (key **`f`**, "fan-out / linked"), composed once at mount
and shown by `display` like the `y` view; the hero (doomsday clock) stays in place so the clock
never leaves the screen. `esc` backs out one-way. Footer help gains `f linked`. All text is
pattern-language and every third-party string is `safe_markup`-escaped.

Three panels (each degrades independently, each shows `as of HH:MM`):

1. **OPERATORS** — the linked-wallet groups, widest first. One row per operator:
   `1,995 linked · 0.45Ξ ×N · 2-blk cadence · shared funder   6.8%   44×`
   (size · the reasons in pattern-language · points-share · sqrt-subsidy). `⚑`-consistent with the
   leaderboard flag. Confidence rendered as a filled/hollow marker, never a raw number that reads
   as a verdict.
2. **SEGMENTS** (Adam's ask) — whale **operators** (combined credit, since a single-send 800 ETH+
   list is only 2 wallets / 0.25% of points), per-hour join/points bands, per-multiplier bands, and
   the index-1000 "early" cohort (7.6% of points). Pattern-language labels ("largest operators",
   "early cohort"), never "whale sybil".
3. **CLEANED LIST** — `total points` vs `clean points` (farm groups removed), survivor count, and
   **your clean rank** when a wallet is set; an **EXPORT** action (`e` inside the view) that writes
   `~/.maxpane/curator_clean_list.json` (+ `.csv`) and shows the path. A TUI cannot hand a file to
   the reader, so it writes to disk and names it — Adam's "OS the list."

**Width**: the new body gets its own sweep (the `y`-view precedent), clearing at the pinned width
(`≤143` app-wide; the dashboard body clears at 138) or advertising `‹ widen` per column — markers
are never silenced by raising a constant. The binding panel and its number get pinned like every
other curator layout.

## 6. Per-wallet surfaces (the "improve the wallet view" core)

- **`y` view, YOUR STANDING** gains one line: `linked` → in pattern-language, either
  `not linked to any group` (representable negative), `linked to a 1,995-wallet 0.45Ξ group ·
  same funder` (with reasons), or `-- unknown` when the B+C sweep has not run (`None`, never a
  confident "clean"). New key `you_linked_*` in `CURATOR_KEYS`.
- **`y` view, YOUR RANK / CLEANED** — the reader's rank in the de-sybilled list beside their raw
  rank, so "you're #412 raw, #47 with clear farms removed" is legible. New key
  `you_clean_rank`.
- **Leaderboard `⚑`** upgrades from boolean to **confidence-graded** (`⚑` linked-high, `◌`
  linked-low/one-family, empty clean, `?` fold-not-run) — a contract change to the `flagged` cell,
  re-pinned in the leaderboard width tiers (the flag column never sheds).

## 7. Data contract additions (`data/curator_models.py`)

All new keys are `float|int|None` or `list[dict]`, all rendered pattern-language, all
`None`-not-`0`. Sketch (frozen precisely in WP0):

- Operators/segments: `operator_rows`, `segment_rows`, `operators_count`,
  `flagged_points_share_pct` (already exists — reused), `clean_points`, `clean_contributors`.
- Cleaned list / export: `clean_list_rows`, `clean_list_export_path`.
- Per-wallet: `you_linked_state` (`"clean"|"linked"|None`), `you_linked_reasons` (list[str]),
  `you_linked_group_size`, `you_clean_rank`.
- Row-key tuples for `operator_rows` / `segment_rows` / `clean_list_rows` in `CURATOR_ROW_KEYS`.
- New activity/degraded vocabulary only if a group is added (see §4) — otherwise fold into `logs`.

Every new key must reach a widget or be in `META_KEYS` (`test_no_contract_key_reaches_no_widget`),
and the manager's `_finalise` drops any key not in `CURATOR_KEYS` — so the models change lands
first, in WP0, exactly as the base curator build did.

## 8. Testing & honesty gates

- **No network anywhere** (structural AST scan + transport doubles), both repos.
- **Pattern-language**: the third view's widgets get their own copy of
  `test_..._uses_pattern_language` (forbidden words on composited render). The analytics
  source-scan is untouched because `sybilkit` is imported only in `data/curator_clusters.py`, never
  in `curator_signals.py`.
- **Wei-exact** points; recompute-and-compare floors identically to the contract.
- **Benchmark regression gate** in `sybilkit` (§3.5), plus a maxpane-side assertion that the
  adapter's flagged set matches the library on a committed fixture.
- **Prove each detector bites** (mutate → red → restore), per CLAUDE.md, for the cluster combiner
  and the funding fold especially.
- **Fixtures** are committed slices of `docs/curator_sybil_data/` under
  `tests/fixtures/curator/sybil/` (both repos), read-only, keyless.

## 9. Work packages (for the project-planner agent)

Parallelizable after WP0+WP1. Best-matching agents in brackets.

- **WP0 — contracts** [Backend Architect]: freeze the `sybilkit` public API (§3.3) and the new
  `CURATOR_KEYS`/`ROW_KEYS` (§7). One owner; everything else builds against these.
- **WP1 — `sybilkit` core** [Data Engineer / AI Engineer]: `model` + all Tier-A/B/C signals +
  `cluster` combiner + `report` + `labels`, pure, TDD, mutation-proven. No I/O.
- **WP2 — `sybilkit` I/O & CLI** [Backend Architect]: keyless `sources/` with failover, `curator`
  preset (curve + segments + clean_list), `cli`, `bench` gate, packaging (own pyproject, `py.typed`).
- **WP3 — maxpane adapter & cache** [Backend Architect]: `data/curator_clusters.py` (imports
  sybilkit), new `TIER_ANALYSIS`/`SLOT_CLUSTERS`, detached sweep in `curator_manager`, degrade
  wiring. Owns `curator_manager.py` + `curator_cache.py`.
- **WP4 — third view** [Frontend Developer / UI Designer]: `MODE_ANALYSIS` screen plumbing (owns
  `screens/curator.py`), the three panels, width sweep, pattern-language test, `themes/minimal.tcss`
  mirror.
- **WP5 — per-wallet surfaces** [Frontend Developer]: `y`-view "linked" + clean-rank lines,
  confidence-graded leaderboard flag, their width re-pins.
- **WP6 — registration, docs, packaging** [Technical Writer + DevOps]: keybinding/footer/help,
  README + CLAUDE.md updates, `sybilkit` README, the second publish job note, memory update.

Shared-file discipline (CLAUDE.md): `screens/curator.py` → WP4 only; `curator_manager.py` /
`curator_cache.py` → WP3 only; `__main__`/`game_select` untouched (no new dashboard, no renumber).
`curator_models.py` → WP0 only. Report defects in others' files; never fix across a boundary.

## 10. Open questions (not blockers)

- **Library name** — `sybilkit` is a placeholder; confirm or rename in review.
- **Convergence of Tier A** — v1 keeps the shipped `find_clusters` and lets the library
  re-implement Tier A. A later WP can refactor `find_clusters` to a thin logs-only view over
  library primitives *without* importing the "sybil"-named package into `curator_signals.py`
  (e.g. by the library exposing a neutrally-named Tier-A entry point, or a vendored pure copy).
- **Settlement** — the game may settle mid-build (hour 24+ judged). Detection works identically on
  the frozen dataset; the third view must be as good an archive as a live view (same rule the base
  dashboard follows).
- **Export cadence** — write the cleaned list every sweep, or only on the `e` keypress? Proposed:
  on keypress (explicit user action), matching the read-only, no-surprise-writes ethic.
