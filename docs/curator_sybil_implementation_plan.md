# CURATOR sybil / fan-out detection — implementation plan

Master plan for the approved PRD `docs/curator_sybil_PRD.md` (research:
`docs/curator_sybil_detection.md`; datasets: `docs/curator_sybil_data/`). It turns PRD §9's
WP0–WP6 sketch into an executable, dependency-aware, parallel-agent build, in the house style
of `docs/curator_work_packages/` (the original THE LIST build). Read that set first; every
convention it documents (freeze the contract first, one owner per shared file,
report-don't-fix across a boundary, `.venv/bin/python -m pytest`, prove-it-bites, never
`git checkout --`) applies here unchanged.

**What this build is.** Two deliverables with one dependency edge (PRD §1):

1. `sybilkit/` — a new, standalone, keyless, **maxpane-independent** Python distribution
   (sibling to the `maxpane/` Rust crate) that does EVM sybil-cluster analysis. Pure-Python
   stdlib core + optional `httpx` fetchers + a CLI + a benchmark gate.
2. The **curator dashboard** gains a third view (`MODE_ANALYSIS`, key `f`), a per-wallet
   "linked" line on the `y` view, and a confidence-graded leaderboard flag — all rendered in
   **pattern-language**, powered by `sybilkit` through a single maxpane adapter
   (`data/curator_clusters.py`).

**What this build is NOT** (PRD §2): no Tier-A rewrite (`analytics/curator_signals.py` stays
exactly as shipped), no new on-screen accusatory word, no six-surface renumber (this is an
expansion of an existing dashboard — `__main__.py`, `screens/game_select.py`, `app.py`
`_GAME_CYCLE` are **untouched**), no signing, no allowlist mutation, no persisted verdict, no
API key.

---

## 0. The name decision is a blocker for WP0

`sybilkit` is a **placeholder** (PRD §10). The directory name, every import path, the pyproject
`name`, the CLI entry point and the maxpane adapter's import line all depend on it. **Confirm
or rename before WP0 starts** — a rename after WP1 is a sed across two distributions and their
tests. WP0.1's first task is to lock the name; this plan writes `sybilkit` throughout and every
brief flags the single line to change if it is renamed. Alternates on the table: `fanoutkit`,
`clustre`, `chainsybil`.

---

## 1. The dependency DAG

```
                         ┌───────────────────────────────────────────┐
                         │  WP0  interface freeze (Backend Architect) │
                         │  • sybilkit public API (§3.3)              │
                         │  • new CURATOR_KEYS / ROW_KEYS (§7)        │
                         │  • worst-case analysis fixtures + shapes   │
                         └───────────────┬───────────────────────────┘
                                         │  (freeze sign-off gate)
             ┌───────────────────────────┼───────────────────────────┐
             ▼                            ▼                           ▼
   ┌───────────────────┐        ┌──────────────────┐       ┌────────────────────┐
   │ WP1 sybilkit core │        │ WP5 per-wallet   │       │ (WP4 waits for WP5) │
   │ model+signals+    │        │ surfaces:        │       │                    │
   │ cluster+report+   │        │ y-view linked,   │       │                    │
   │ labels (pure)     │        │ clean-rank,      │       │                    │
   └─────────┬─────────┘        │ graded ⚑ flag    │       │                    │
             │                  │ (widget modules) │       │                    │
             ▼                  └────────┬─────────┘       │                    │
   ┌───────────────────┐                 │ (widget kwargs frozen → hand-off)   │
   │ WP2 sybilkit I/O, │                 ▼                                     │
   │ CLI, curator      │        ┌──────────────────────────────────────────┐  │
   │ preset, bench,    │        │ WP4 third view: MODE_ANALYSIS in          │  │
   │ packaging         │        │ screens/curator.py + 3 analysis widgets + │◄─┘
   └─────────┬─────────┘        │ minimal.tcss mirror + width sweep         │
             │                  └───────────────────┬──────────────────────┘
             ▼                                      │
   ┌───────────────────────────────────────────┐    │
   │ WP3 maxpane adapter & cache:              │    │
   │ data/curator_clusters.py (imports         │    │
   │ sybilkit) + TIER_ANALYSIS/SLOT_CLUSTERS + │    │
   │ detached B+C sweep in curator_manager +   │    │
   │ key-merge + degrade wiring                │    │
   │ (owns curator_manager.py + curator_cache) │    │
   └───────────────────┬───────────────────────┘    │
                       │                             │
                       └──────────────┬──────────────┘
                                      ▼
                    ┌──────────────────────────────────────────┐
                    │ WP6 registration, docs, packaging:        │
                    │ footer/help, README + CLAUDE.md, sybilkit │
                    │ README, second publish-job note, memory,  │
                    │ full-suite + cargo green, live smoke      │
                    └──────────────────────────────────────────┘
```

**Edges that matter (why each arrow exists):**

- `WP0 → everything`: the sybilkit public API and the new flat keys/row shapes are the
  interface every other package codes against without talking. Nothing starts until WP0 signs
  off. This is the base-curator WP0 pattern exactly.
- `WP1 → WP2`: the curator preset, the CLI and the bench gate all call the core `detect` /
  `Dataset` / `report`.
- `WP1 + WP2 → WP3`: the maxpane adapter imports `sybilkit` (core **and** `sybilkit.curator`
  preset **and** `sybilkit.sources` for the B+C fetch), so it cannot be tested end-to-end until
  both land.
- `WP5 → WP4`: WP4 owns `screens/curator.py` and must dispatch the wallet widgets' **new**
  kwargs and re-sweep the width with the graded leaderboard flag in place; it consumes WP5's
  hand-off (the exact new kwarg tuples and the leaderboard row sub-key). WP4 does not edit
  WP5's widget modules and WP5 does not edit the screen.
- `WP3, WP4, WP5 → WP6`: registration/docs/packaging and the live smoke need the whole thing.

**No edge into `analytics/curator_signals.py`, `data/curator_client.py`, `app.py`,
`__main__.py`, `screens/game_select.py`, `themes/*` except the curator block.** Those are
out of scope. See §5.

---

## 2. Wave schedule (the parallelization)

| wave | runs concurrently | each waits on | gate |
|---|---|---|---|
| **0** | **WP0** alone | — | freeze sign-off: sybilkit API + new keys/rows importable and pinned; worst-case fixtures committed; full existing suite still green (WP0 adds files only) |
| **1** | **WP1** ∥ **WP5** | WP0 | WP1: core green + mutation-proven, no I/O. WP5: wallet/leaderboard widgets green against synthetic payloads, pattern-language tests green, **widget-kwarg hand-off written** |
| **2** | **WP2** ∥ **WP4** | WP1 (WP2); WP0 + WP5 hand-off (WP4) | WP2: sources/CLI/preset/bench green, `python -m build sybilkit/` produces a wheel. WP4: third view renders three phases of synthetic analysis payloads, width swept and pinned ≤143, three pattern-language render tests green |
| **3** | **WP3** alone | WP1 + WP2 | adapter's flagged set matches the library on a committed fixture; detached sweep proven one-in-flight; degradation matrix green; full suite green |
| **4** | **WP6** alone | WP1–WP5 | full `pytest` + `cargo test` green; `python -m build` (root) and `python -m build sybilkit/` both build; live smoke keyless; docs + memory updated |

**Critical path:** `WP0 → WP1 → WP2 → WP3 → WP6` (five stages). WP4 and WP5 ride the UI branch
(waves 1–2) and are validated end-to-end at WP3's integration test and WP6's live smoke. This
mirrors the base-curator schedule (widgets parallel-early against frozen keys; the shared data
files late and single-owner).

**Why the UI (WP4/WP5) precedes the data (WP3) here, unlike the base build's screen-after-
manager order.** The new keys are frozen in WP0 and the widgets consume the flat dict, never
the library, so they can build against **synthetic analysis payloads sliced from
`docs/curator_sybil_data/`** — the house "synthetic until captured" pattern. WP0 freezes the
**worst-case** operator/segment/clean rows (the 1,995-wallet 0.45 ETH operator, all its
reasons, its `44×` subsidy) so the width sweep measures the state the data is normally in, not a
toy row. WP3's adapter must then produce rows matching those frozen shapes, and WP3.9 asserts it
against the same fixture. If WP0's worst-case row is wrong, WP4 re-pins during WP6 integration —
noted as a risk (§6).

---

## 3. The frozen interfaces (hand-off points)

Two interfaces are frozen in WP0 and are the seams parallel agents code against.

### 3.1 `sybilkit` public API (WP0 freezes; WP1/WP2 implement; WP3 consumes)

```python
from sybilkit import Dataset, detect, DetectConfig, DetectResult
from sybilkit.model import Deposit, Tx, Funding
from sybilkit.report import Cluster, Reason, WalletVerdict

ds = Dataset.from_events(deposits, first_deposits, txs=None, funding=None)   # pure; wei ints
res: DetectResult = detect(ds, DetectConfig(min_size=5, min_families=2,
                                            near_amount_tol=0.10, confidence_threshold=0.5))

res.clusters            # list[Cluster], sorted by points_share desc
res.wallet(addr)        # WalletVerdict(in_cluster, cluster_id, reasons, confidence) | None
res.flagged             # set[str] lowercase, confidence >= threshold
res.total_points        # int (wei-floored curve points)
res.flagged_points      # int
res.clean_points        # int

from sybilkit.curator import segments, clean_list, curve_points, CuratorPreset
segments(ds, res)       # Segments: whale-operators, per-hour, per-multiplier, index-1000 cohort
clean_list(ds, res)     # CleanList: ranked survivors + clean_rank(addr)
curve_points(weight_wei, points_per_eth)   # isqrt(weight_wei) * points_per_eth // 10**9
```

- **Signals are pure `(Dataset, DetectConfig) -> list[Edge]`**; `cluster.py` unions edges
  (union-find) and keeps components with `≥ min_families` **distinct edge-families** and
  `≥ min_size` members (PRD §3.1). Families: `amount`, `sequence`, `cadence`, `gas`, `funding`.
- **`Reason(family, human_string, strength)`** and a `confidence ∈ [0,1]` per cluster —
  multiplicative, graduated, never binary (PRD §3.1). Freshness discounts, never convicts.
- **`curve_points` floors integer-sqrt exactly like the contract** and exactly like
  `analytics/curator_signals.points_for_weight` (`isqrt(w) * ppe // 10**9`, multiply before
  divide, `10**9` an int not `1e9`).
- **`None` is a failed read; the three legitimate zeros are answers** (mirrors curator
  conventions).

### 3.2 New maxpane flat keys and row shapes (WP0 freezes; WP3 fills; WP4/WP5 render)

Added to `data/curator_models.py::CURATOR_KEYS` (the live file is the source of truth — it is
already larger than the wave-2 brief's "49" because of the ENS + `y`-view keys). All new
scalars are `float|int|str|None`; all lists default to `[]`; all rendered pattern-language;
all `None`-not-`0`.

```
# analysis view (MODE_ANALYSIS)
operator_rows           list[dict]  — CURATOR_ROW_KEYS["operator_rows"]
segment_rows            list[dict]  — CURATOR_ROW_KEYS["segment_rows"]
clean_list_rows         list[dict]  — CURATOR_ROW_KEYS["clean_list_rows"]
operators_count         int | None  — 0 is "analyzed, none linked"; None is "could not analyze"
clean_points            int | None
clean_contributors      int | None
analysis_as_of_hhmm     str | None  — the B+C sweep's own freshness marker (long TTL)
# flagged_points_share_pct  — ALREADY EXISTS, reused (see §6 risk 2)
# per-wallet (y view)
you_linked_state        str | None  — "clean" | "linked" | None
you_linked_reasons      list[str]   — pattern-language phrases; [] is "analyzed, not linked"
you_linked_group_size   int | None
you_clean_rank          int | None
```

New `CURATOR_ROW_KEYS` entries (exact tuples frozen in WP0.3; proposal):

```
operator_rows:   ("size", "reasons", "points", "points_share_pct", "sqrt_subsidy_x", "conf")
segment_rows:    ("label", "contributors", "points_share_pct", "detail")
clean_list_rows: ("clean_rank", "address", "points", "credit_eth", "name")
```

New **sub-key on the existing `leaderboard_rows` tuple** (not a new top-level key):

```
leaderboard_rows: (..., "flagged", "name", "link_conf")
                                          # "high" | "low" | "clean" | None  (⚑/◌/empty/?)
```

**`link_conf` is additive; `flagged` (the Tier-A bool) is unchanged**, so
`analytics/curator_signals.py` is not edited and its forbidden-word source scan and existing
`flagged=True` tests stay green (§6 risk 3). The manager merges `link_conf` into the rows the
way `_label_with_ens` merges `name`.

**`clean_list_export_path` is deliberately NOT a manager key** — see §6 risk 1. The export
path is screen-owned.

### 3.3 The routing table (WP0 freezes; removes the WP4↔WP5 coupling)

Which widget renders each new key. WP4 wires the dispatch from this table (from `CURATOR_KEYS`,
not from WP5's source), so WP4 and WP5 never edit the same file:

| new key | rendered by | owned in WP |
|---|---|---|
| `operator_rows`, `operators_count`, `flagged_points_share_pct`, `analysis_as_of_hhmm` | `CuratorOperators` | WP4 |
| `segment_rows`, `analysis_as_of_hhmm` | `CuratorSegments` | WP4 |
| `clean_list_rows`, `clean_points`, `clean_contributors`, `you_clean_rank`, `analysis_as_of_hhmm` | `CuratorCleanList` | WP4 |
| `you_linked_state`, `you_linked_reasons`, `you_linked_group_size`, `you_clean_rank` | `CuratorWalletStanding` (the `linked` + clean-rank lines) | WP5 renders, WP4 wires |
| `leaderboard_rows.link_conf` | `CuratorLeaderboard` (row sub-key, no signature change) | WP5 renders |

Every new top-level key reaches a widget above, so the screen's totality assertion
(`CURATOR_KEYS − dispatched − META_KEYS == ∅`) holds. `analysis_as_of_hhmm` reaches the three
analysis widgets; it is a payload key, not a META key.

---

## 4. Per-WP summary

Full briefs in `docs/curator_sybil_work_packages/wp{0..6}.md`. One-line-per-field summary here.

### WP0 — interface freeze  [Backend Architect]
- **Goal:** lock the `sybilkit` name; freeze the sybilkit public API and the new
  `CURATOR_KEYS`/`CURATOR_ROW_KEYS`; commit worst-case analysis fixtures.
- **Owns/creates:** `sybilkit/src/sybilkit/__init__.py` (API stubs + `py.typed` decision),
  `sybilkit/tests/sybilkit_fixtures.py`, `sybilkit/tests/test_public_api.py`; edits to
  `maxpane_dashboard/data/curator_models.py`; `tests/data/test_curator_models.py` (extend);
  `tests/fixtures/curator/sybil/` (the worst-case slices, shared reader); `sybilkit/README.md`
  stub. Also `docs/curator_sybil_data/` provenance pins.
- **Read-only:** everything else.
- **Proves it:** `test_curator_keys_gained_exactly_the_analysis_surface`; the new keys are in
  `CURATOR_KEYS` and **absent from `SIGNAL_OUTPUT_KEYS`** (guardrail so nobody adds them to
  `curator_signals.py`); the sybilkit API imports and its stubs raise `NotImplementedError`;
  `test_the_curve_preset_signature_floors_like_the_contract` (stub-level).
- **Bite:** rename one new key in `CURATOR_ROW_KEYS`; the row-shape test fails naming it.
- **Done:** both interfaces importable and pinned; existing suite green; hand-off note written.

### WP1 — `sybilkit` core  [Data Engineer / AI Engineer]
- **Goal:** `model` + all Tier-A/B/C signals + `cluster` combiner + `report` + `labels`, pure,
  stdlib-only, TDD, mutation-proven. No I/O.
- **Owns/creates:** `sybilkit/src/sybilkit/{model,cluster,report,labels}.py`,
  `sybilkit/src/sybilkit/signals/{amounts,sequence,cadence,split,gas,funding}.py`,
  `sybilkit/tests/test_{model,signals_*,cluster,report,labels}.py`, its fixtures.
- **Read-only:** WP0's `__init__.py` API surface (implements against it; reports a mismatch).
- **Proves it:** the 16 audited operators from `docs/curator_sybil_data/cluster_economics.json`
  are each found; the 0/47 controls are not flagged; ≥2-family gate; min-size ≥5.
- **Bite:** drop the family-count gate → a single-family control clusters, the FP test reddens;
  drop the funding fold → the 10/10-funder operators lose their strongest edge.
- **Done:** core green, no I/O import anywhere, benchmark-precision-floor placeholder marked.

### WP2 — `sybilkit` I/O, CLI, curator preset, packaging  [Backend Architect]
- **Goal:** keyless `sources/` with failover + message-text error classification; the `curator`
  preset (curve, segments, clean_list); the CLI; the bench gate; own pyproject + `py.typed`.
- **Owns/creates:** `sybilkit/src/sybilkit/sources/{logs,txs,blockscout}.py`,
  `sybilkit/src/sybilkit/{curator,bench,cli}.py`, `sybilkit/pyproject.toml`,
  `sybilkit/src/sybilkit/py.typed`, `sybilkit/tests/test_{sources,curator,cli,bench}.py`,
  `sybilkit/README.md`.
- **Read-only:** WP1's core.
- **Proves it:** no test opens a socket (MockTransport doubles + AST scan, both repos' rule);
  the bench gate has a precision floor + a median-gap ceiling + a `todo` for the cluster-level
  target the wallet-level baseline can't meet; `python -m build sybilkit/` yields a wheel.
- **Bite:** make a source follow a provider's suggested retry range → the livelock test reddens.
- **Done:** library installable and usable without maxpane; CLI runs against a fixture.

### WP3 — maxpane adapter & cache  [Backend Architect]
- **Goal:** `data/curator_clusters.py` (the only maxpane module importing sybilkit);
  `TIER_ANALYSIS` + `SLOT_CLUSTERS` in `curator_cache.py`; the detached B+C sweep in
  `curator_manager.py` (the `_spawn_crosscheck` precedent); merge the new keys into the flat
  dict; degrade wiring.
- **Owns:** `data/curator_manager.py`, `data/curator_cache.py`, and **creates**
  `data/curator_clusters.py`, `tests/data/test_curator_clusters.py`,
  `tests/fixtures/curator/sybil/` (its own slices), plus additions to the manager/cache tests.
- **Read-only:** `curator_client.py`, `curator_signals.py`, `sybilkit/` — report-don't-fix.
- **Proves it:** the adapter's `flagged` set matches `sybilkit` on a committed fixture; the
  sweep runs one-in-flight and publishes into `SLOT_CLUSTERS` the next cycle reads, stamped
  `analysis_as_of_hhmm`; `operators_count == 0` (analyzed, none) vs `None` (could not analyze)
  are distinguished; `close()` cancels **both** detached tasks.
- **Bite:** await the analysis sweep in-cycle → the "first paint not blocked" test reddens;
  make the latch-style analysis result persist a boolean verdict → the "no verdict persisted"
  test reddens.
- **Done:** `fetch_and_compute()` still returns exactly `CURATOR_KEYS`, never raises, with the
  new keys filled from the analysis last-good behind `analysis_as_of_hhmm`.

### WP4 — third view (`MODE_ANALYSIS`)  [Frontend Developer / UI Designer]
- **Goal:** `MODE_ANALYSIS` (key `f`) in `screens/curator.py`; the three panels (OPERATORS,
  SEGMENTS, CLEANED LIST); the `e` export action; the width sweep; the pattern-language render
  tests; the `minimal.tcss` mirror block.
- **Owns:** `screens/curator.py`, `themes/minimal.tcss` (the curator-analysis additions only),
  and **creates** `widgets/curator/{operators,segments,cleaned_list}.py`,
  `tests/screens/test_curator_screen.py` additions, `tests/widgets/test_curator_widgets.py`
  additions.
- **Read-only:** WP5's widget modules (wires their new kwargs from the routing table),
  `curator_manager.py`.
- **Proves it:** each analysis widget gets its **own** copy of the composited pattern-language
  render test (forbidden words `sybil/cheat/fraud/attack/abuse/wash`); the new body's width
  clears ≤143 or advertises `‹ widen`; the hero (doomsday clock) stays in place under `f`;
  `esc` backs out one-way; the export writes `~/.maxpane/curator_clean_list.json` (+ `.csv`)
  and names the path.
- **Bite:** drop a `safe_markup` on an operator reason string → the hostile-symbol test reddens;
  run the analysis body's default without gating → the mode snaps back under the reader.
- **Done:** three modes render, width pinned, `f`/`esc`/`e` behave, nothing clips dark.

### WP5 — per-wallet surfaces  [Frontend Developer]
- **Goal:** the `y`-view `linked` line + clean-rank line; the confidence-graded leaderboard
  flag; the width re-pins for both widgets.
- **Owns:** `widgets/curator/wallet.py`, `widgets/curator/leaderboard.py`, and additions to
  `tests/widgets/test_curator_widgets.py`.
- **Read-only:** `screens/curator.py` (reports the dispatch it needs; does not edit it — WP4
  wires from WP0's routing table), `curator_models.py`.
- **Proves it:** `you_linked_state=None` renders `-- unknown` (never a confident "clean");
  `"linked"` renders pattern-language reasons; the graded flag has four distinct glyphs
  (`⚑`/`◌`/empty/`?`) so colour is never the sole carrier; the flag column never sheds in the
  width tiers.
- **Bite:** render `you_linked_state=None` as "not linked" → the "confident-negative" test
  reddens.
- **Done:** widgets green, **hand-off note** written with the exact new kwarg tuples + the
  `link_conf` sub-key semantics for WP4 to wire.

### WP6 — registration, docs, packaging  [Technical Writer + DevOps]
- **Goal:** footer/help text for `f`; README + CLAUDE.md updates; the `sybilkit` README; the
  **second publish job** note (not auto-wired); memory update; full-suite + `cargo` green; live
  smoke; close the synthetic-fixture ledger.
- **Owns:** `README.md`, `CLAUDE.md`, `sybilkit/README.md` (final), a `.github/workflows/`
  note or a new `publish-sybilkit.yml` **as documentation** (see §6 risk 8), the memory file
  update; **creates** no source.
- **Read-only:** everything else — report-don't-fix.
- **Proves it:** `test_the_readme_documents_the_analysis_view`; `rg` finds no `sybil` in
  `analytics/curator_signals.py`; the keyless proof over both distributions; both builds build.
- **Done:** docs agree, both distributions build, live smoke keyless, ledger closed.

---

## 5. Shared-file discipline (CLAUDE.md "Working with agents")

One owner per shared file, single-owner files late in the sequence:

| file | owner | wave |
|---|---|---|
| `data/curator_models.py` | WP0 | 0 |
| `data/curator_manager.py`, `data/curator_cache.py`, `data/curator_clusters.py` (new) | WP3 | 3 |
| `screens/curator.py`, `themes/minimal.tcss` (curator block) | WP4 | 2 |
| `widgets/curator/wallet.py`, `widgets/curator/leaderboard.py` | WP5 | 1 |
| `widgets/curator/{operators,segments,cleaned_list}.py` (new) | WP4 | 2 |
| `sybilkit/src/sybilkit/{model,cluster,report,labels,signals/*}` | WP1 | 1 |
| `sybilkit/src/sybilkit/{sources/*,curator,bench,cli}`, `sybilkit/pyproject.toml` | WP2 | 2 |
| `README.md`, `CLAUDE.md`, `sybilkit/README.md` | WP6 | 4 |

**Untouched — do not plan changes there (no new dashboard, no renumber):** `app.py`,
`__main__.py`, `screens/game_select.py`, `app.py::_GAME_CYCLE`, the `--game`/`--theme` choices,
`FULL_LAYOUT_COLUMNS`, `data/curator_client.py`, `data/curator_addresses.py`,
`analytics/curator_signals.py`. Report a defect in any of them; never fix across the boundary.
Never `git checkout --` a file (the tree may hold uncommitted user work). Stage explicit paths,
never `git add -A`.

---

## 6. Risks and unknowns (gaps and contradictions found while planning)

Genuine PRD gaps/contradictions, noted here rather than silently resolved (per the brief).

1. **`clean_list_export_path` — manager key or screen-owned?** PRD §7 lists it as a
   `curator_models.py` addition, but PRD §5 makes export an `e`-keypress screen action and PRD
   §2 forbids surprise writes. A manager key would couple the read-only data layer to a file
   write. **Recommendation (needs validation):** drop it from `CURATOR_KEYS`; the CLEANED LIST
   widget receives the path as a **screen-supplied** value (like `you_address`) after `e`. WP0
   omits it from `CURATOR_KEYS`; WP4 owns the export write and the widget's post-export line.
   If the user wants it in the manager contract, WP0 adds it and WP3 emits `None` until an
   export — but the write still happens in the screen.

2. **`flagged_points_share_pct` reuse (PRD §7 "already exists — reused").** It is currently
   computed by **Tier-A** `find_clusters` and drives the FARM rail row. The OPERATORS panel's
   share is the **library's** (stronger, ≥2-family) number. Reusing one key for both means the
   manager must decide which wins. **Recommendation:** the manager overrides
   `flagged_points_share_pct` with the library's value **once the analysis sweep has last-good**,
   falling back to Tier-A's when it hasn't — so FARM and OPERATORS agree and the "confidence-
   graded upgrade to the flag" is consistent. **Alternative:** add a separate
   `linked_points_share_pct` and leave FARM on Tier-A. Flagged because it changes what a shipped
   rail row shows. Confirm in review.

3. **Leaderboard `flagged` cell: change type vs add sub-key.** PRD §6 says the boolean `⚑`
   "upgrades to confidence-graded … a contract change to the `flagged` cell." Changing
   `flagged` from bool would force `analytics/curator_signals.py` (which fills it) to produce
   the graded value — but that module must stay **exactly as shipped** (PRD §2) and its source
   is forbidden-word-scanned. **Recommendation (encoded):** keep `flagged` (bool, Tier-A,
   untouched) and add an **additive** `link_conf` sub-key on `leaderboard_rows`, filled by the
   manager's adapter merge (the ENS-merge precedent). The widget grades the glyph off
   `link_conf` when present, off `flagged` otherwise. This keeps `curator_signals.py` untouched
   and the existing `flagged=True` tests green.

4. **Library name unconfirmed (PRD §10).** Blocks WP0 — see §0. Lock before WP0.

5. **B+C network path.** The detached sweep fetches gas fingerprints (Tier B, batched
   `getTransactionByHash`) and funding (Tier C, Blockscout per-address). The PRD (§4 table)
   routes both "via maxpane adapter". **Recommendation (encoded):** the adapter drives
   `sybilkit.sources` (WP2) with maxpane-appropriate endpoints and an injected `httpx` client,
   **not** new `CuratorClient` methods — this keeps `data/curator_client.py` out of scope
   (one-owner rule) and keeps `sybilkit` self-sufficiently keyless. The no-network test rule is
   satisfied by injecting a `MockTransport` into the sources from the adapter's tests.
   **Alternative:** add `fetch_tx_fingerprints`/`fetch_funding` to `CuratorClient` — rejected
   for v1 because it re-opens a file no WP owns.

6. **UI-before-data synthetic drift.** WP4/WP5 pin widths against synthetic operator/segment
   rows frozen in WP0, before WP3's adapter produces real ones. Mitigation: WP0 freezes the
   **worst-case** rows from the research (§4/§5 numbers — the 1,995-wallet 0.45 ETH operator,
   its reasons string, its `44×` subsidy); WP3.9 asserts the adapter's rows match that fixture's
   shape; WP6 re-pins if the live smoke disagrees. Residual risk: the reason-string worst case
   is a judgement call — WP0 should over-provision it.

7. **Degraded group for the analysis sweep.** PRD §4: fold into `logs` **or** amend
   `CURATOR_DEGRADED_GROUPS` + `SOURCES` + `GROUP_SLOT` + tests together. **Recommendation:**
   fold into `logs` for v1 (fewest surfaces; the title bar's frozen group set is untouched).
   The "analyzed, nothing linked" (representable zero: `operators_count == 0`) vs "could not
   analyze" (`None`) distinction is carried **inside the analysis keys and widgets** (the FARM-
   row precedent), not by a new group name. Confirm in review.

8. **Second publish job is not auto-wired (PRD §3.5).** `.github/workflows/publish.yml` triggers
   on `v*` and runs `python -m build` at the repo root, which builds **only maxpane**
   (`pyproject.toml` packages `maxpane_dashboard`). A `sybilkit` release needs its own build
   (`python -m build sybilkit/`) and upload. **Recommendation:** WP6 documents this as a manual
   step and optionally adds a **separate** `publish-sybilkit.yml` gated on a distinct tag
   pattern (e.g. `sybilkit-v*`) — as a **noted task**, not auto-wired into the maxpane release,
   so a maxpane tag never accidentally publishes an unversioned sybilkit.

9. **Settlement mid-build (PRD §10).** The game may settle during the build. Detection works
   identically on the frozen dataset; the analysis view must archive as well as it live-views
   (the base dashboard's rule). WP4's phase tests cover settled; WP3's sweep runs on the frozen
   log history regardless of phase.

10. **Convergence of Tier A is explicitly deferred (PRD §2/§10).** Do **not** unify
    `analytics/curator_signals.find_clusters` with `sybilkit` in v1. The two Tier-A
    implementations coexist by design (FARM row + `c`-view on the shipped one; OPERATORS panel
    on the library). A guardrail test (WP3/WP6) asserts `curator_signals.py` never imports
    `sybilkit`.

11. **`CURATOR_KEYS` is already larger than "49".** The live `curator_models.py` carries the
    ENS + `y`-view keys. WP0 extends the **live** file, not the wave-2 brief's list, and every
    count-based test in `test_curator_models.py` must be re-derived, not hand-bumped.

### §6 close-out (WP6, 2026-08-18) — how each risk actually landed

Every one of the eleven is resolved and the resolution is on the record below. **All eleven
landed on the recommendation**, so nothing in §6 above is struck or rewritten; this block is the
outcome, appended rather than edited into the risks, so a reader can still see what was open.

| # | landed | evidence |
|---|---|---|
| 1 | **as recommended** — `clean_list_export_path` is NOT in `CURATOR_KEYS` (73 keys, checked). The screen owns the write (`action_export_clean_list`, injectable `export_dir=`) and hands the widget the path through `mark_exported`, never through `update_data`. | `test_the_export_path_renders_only_after_the_screen_reports_a_write` |
| 2 | **as recommended** — `flagged_points_share_pct` is override-with-fallback: the library's number once `SLOT_CLUSTERS` has last-good, Tier-A's until then, so the FARM rail row and the OPERATORS summary agree. No `linked_points_share_pct` was added. | `curator_manager.py` merge; WP3 report §4 |
| 3 | **as recommended** — `flagged` stays the Tier-A bool and `link_conf` is an additive `leaderboard_rows` sub-key filled by the manager's merge. `curator_signals.py` is byte-identical. Glyphs: `⚑` high · `◌` low · empty clean · `?` not analyzed. | `test_link_conf_grades_the_flag`; `git diff main -- .../curator_signals.py` empty |
| 4 | **resolved** — the name is `sybilkit`, locked before WP0 and unchanged since. | `sybilkit/pyproject.toml` |
| 5 | **as recommended** — the adapter drives `sybilkit.sources` with an injected client/transport. `data/curator_client.py` gained no method and is not in this build's diff. | `curator_clusters.fetch_enrichment` |
| 6 | **mitigated, and the residual risk did not fire.** WP0's worst-case rows over-provisioned the reason string to four phrases; WP3.9 pinned the adapter's shape against them; the WP6 live smoke found **no disagreement that needed a re-pin** — the analysis body still clears at 137 against live rows. |
| 7 | **as recommended** — analysis failures fold into the existing `logs` group, and only while there is nothing to serve. `CURATOR_DEGRADED_GROUPS` is untouched. The analyzed-nothing (`0`) vs cannot-analyze (`None`) distinction lives in the keys and widgets. | offline smoke: `degraded == ['logs', 'state']`, all twelve analysis keys `None`, nothing `0` |
| 8 | **Option A, as recommended** — documented manual release in `sybilkit/README.md`. Option B was NOT added: sybilkit has no PyPI project or trusted-publishing config yet, so the job could only fail at upload. Verified that the root workflow builds only maxpane (294-entry wheel, zero `sybilkit` entries, no `sybilkit` in `Requires-Dist`). |
| 9 | **held** — the game had **not** settled by 2026-08-18 (live: hour 31, `JUDGED`, list OPEN). The settled path is covered by WP4's phase tests rather than by a live observation, and the sweep runs off the frozen log history in any phase. |
| 10 | **held** — the two Tier-A implementations coexist. `test_curator_signals_never_imports_sybilkit` and `test_only_curator_clusters_imports_sybilkit` are the guardrails, and both were re-run in the WP6 audit. |
| 11 | **as recommended** — the live file was extended and the counts are derived. `len(CURATOR_KEYS) == 73`. |

---

## 7. Testing & honesty gates (apply to every WP)

- **No network anywhere**, both distributions: structural AST scan + `MockTransport` doubles.
- **Pattern-language:** each new analysis widget gets its own composited forbidden-word test;
  the analytics source-scan is untouched because `sybilkit` is imported only in
  `data/curator_clusters.py`.
- **Wei-exact** curve points, floored like the contract; `pytest.approx` on a wei value is a
  review failure.
- **Benchmark regression gate** in `sybilkit` (precision floor + median-gap ceiling + a `todo`
  for the cluster-level target); plus a maxpane-side assertion that the adapter's flagged set
  matches the library on a committed fixture.
- **Prove each detector bites** (mutate → red → restore), especially the cluster combiner and
  the funding fold.
- **Fixtures** are committed slices of `docs/curator_sybil_data/` under
  `tests/fixtures/curator/sybil/` (maxpane) and `sybilkit/tests/fixtures/` (sybilkit), read-only,
  keyless. Mark synthetics `# SYNTHETIC — re-point at …` so `rg` is the whole checklist.

---

## Recommended approach

Build `sybilkit` as a genuinely standalone keyless distribution first (WP0 freeze → WP1 core →
WP2 io/cli), then wire it into THE LIST through a single adapter (WP3) that follows the
`_spawn_crosscheck` detached-sweep precedent to the letter, while the UI (WP4 third view, WP5
per-wallet) builds in parallel against frozen keys and worst-case synthetic payloads. Keep
`analytics/curator_signals.py` untouched; carry the confidence-graded flag as an additive row
sub-key merged in the manager. Register nothing new (no dashboard, no renumber).

## Why this approach

It maximises parallelism (five-stage critical path, three branches) while respecting every
one-owner-per-shared-file boundary; it keeps the forbidden-word source scan and the shipped
Tier-A heuristic green by never editing `curator_signals.py`; and it isolates all network,
verdicts and file writes at the right layers (sybilkit sources for B+C, the manager for merge,
the screen for export) so the read-only, keyless, `None`-not-`0` invariants hold end-to-end.

## Risks and unknowns

The eleven items in §6 — most importantly the library-name lock (blocks WP0), the
`flagged_points_share_pct` reuse decision, the `clean_list_export_path` ownership, and the
UI-before-data synthetic-drift mitigation. None is a blocker to starting WP0 once the name is
confirmed; each is a decision to record as the corresponding WP lands.

## Implementation steps

Waves 0→4 as scheduled in §2; per-WP task breakdowns in the seven briefs. Gate at each wave
boundary on the criteria in the §2 table.

## Validation plan

Per-WP TDD + prove-it-bites; a WP3 integration test that the adapter agrees with the library on
a committed fixture; a WP6 live smoke run against Ethereum mainnet (keyless, offline-degrades,
`python -m build` for both distributions) plus a `cargo test` that the Rust crate is untouched.
