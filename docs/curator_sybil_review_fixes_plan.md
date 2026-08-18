# sybilkit review fixes — implementation plan

Plan for closing the defects found by the **2026-08-18 max-effort code review of the
`sybilkit/` distribution** (`feature/curator-sybil` @ `33eb8b4`). The review record —
15 confirmed findings ranked most-severe first, a below-the-cap list, a cleanup lane, and the
six findings that need a user ruling — lives in the session memory
`project_sybilkit_review_2026_08`. **This plan does not re-derive the findings; it turns them
into an executable, dependency-aware, parallel-agent build** in the house style of
`docs/curator_sybil_implementation_plan.md` and `docs/curator_sybil_work_packages/`.

**Nothing has been fixed yet.** At the time of writing, the memory file is the only durable
record of the findings; this document is the second. No code was changed to produce it.

**What this build is.** Nine work packages that fix 15 confirmed defects plus a documented
below-the-cap ledger and a no-behaviour-change cleanup lane, across two distributions:
`sybilkit/` (the library, ~290 tests) and `maxpane_dashboard/` (the dashboard, 4 661 tests).
Every fix is TDD-first and mutation-proven, and **every reproduction the review built with a
MockTransport or a hand-built fixture becomes a committed test.**

**What this build is NOT.** No new features. No new dashboard, no six-surface renumber, no
change to `analytics/curator_signals.py` (still byte-identical to what shipped), no new
network path, no key, no signer. No re-tuning of a detector to make a fix pass — if a fix moves
the benchmark gate, that is a finding and it escalates (§9, risk 3). No merge, no tag, no
publish: those stay the user's decision (§4, WP9).

---

## 0. Ground rules — every WP, no exceptions

These come from `CLAUDE.md` and from the base-curator build; they are repeated here because
each one is a bug that already shipped somewhere in this repo.

- **Interpreter.** `/Library/Vibes/autopull/.venv/bin/python -m pytest` for maxpane;
  `cd sybilkit && /Library/Vibes/autopull/.venv/bin/python -m pytest` for the library. The
  system `python3` lacks the deps; worse, in `sybilkit/` it *skips* the fetcher tests instead
  of erroring, so a suite that "passed" never ran its network layer. **A sybilkit run that
  reports any skips is a wrong-interpreter run — treat it as red.**
- **Baselines.** sybilkit: 289 passed + 1 xfail, **0 skipped**. maxpane: 4 661 passed. Both
  must be green at every wave gate, and the counts only ever go **up**.
- **No test touches the network**, in either distribution. Assert it structurally: inject a
  transport that raises on real use. Every external payload is a committed fixture.
  `sybilkit/tests/test_sources.py::test_no_test_file_in_the_suite_builds_a_client_without_a_transport`
  already enforces this across the suite — new test files inherit it, and must stay inside it.
- **A failed read is `None`, never `0` and never `[]`.** Three of the fifteen findings are
  exactly this rule broken on a degraded path.
- **Prove each test bites.** Every fix task below names a mutation: apply it, watch the named
  test go red, restore. Record the observation in the commit body. A fix without a recorded
  bite is not done.
- **Do not weaken a reproduction.** Where the review reproduced a defect, that scenario is the
  new test. If an *existing* test appears to contradict a fix, read it before changing it: in
  at least one case (D1) the existing test does not pin what the finding says it pins.
- **One owner per shared file** (§2). Report defects in another WP's file; never fix across the
  boundary. Never `git checkout --` anything — the working tree holds uncommitted user work.
- **Do not touch `tests/fixtures/curator/captures/live/`.** Those are the user's untracked
  live captures. No WP reads them, writes them, stages them or cleans them.
- **Stage explicit paths.** Never `git add -A`. Commit after each task, with the mutation
  observation in the body.
- **Additive signatures only across the distribution boundary.** `maxpane_dashboard/data/
  curator_clusters.py` imports `sybilkit.signals.first_rows` and
  `sybilkit.signals.tier_a_components`, plus `sybilkit.sources.{blockscout,txs}` and
  `sybilkit.curator.{segments,clean_list,CuratorPreset}`. Any signature change to those is a
  cross-distribution break; new parameters are keyword-only with defaults.

---

## 1. Decisions required before implementation

> ### RULINGS TAKEN — 2026-08-18, by the user: *"take the recommendations"*
>
> | decision | ruling | meaning |
> |---|---|---|
> | **D1** | **B** | drop the fallback — `analyzed = set(res.analyzed)` |
> | **D2** | **C** | walk `/internal-transactions` **only** when the normal walk found no incoming transfer |
> | **D3** | **B** | deterministic `_replay_rank` tie-break, higher `block_number` wins, byte-identical in both modules |
> | **D4** | **A** | **rename** the band to `linked_groups` / "linked groups"; do not filter it |
> | **D5** | **A** | exclude exempt-minimum rows from the near pass entirely |
> | **D6** | **B** | per-address `page_cursors` on `FundingSweep`, defaulted and added last; tolerant read in the adapter |
>
> The two micro-decisions inside WP4 are also ruled **as recommended**: #11(iii) *is*
> implemented (a partial `DepositSweep` where zero-read still returns `None`), and the gas
> reason string of #2 **keeps its current wording and length** — the meaning change is
> documented in the module docstring, not in the rendered string.
>
> **No WP is blocked any more.** Every task in §3 runs.

Six findings need a ruling. **They are collected here, up front, so that the other nine can
start immediately.** Each gives the current behaviour, the options, a recommendation with
rationale, and what moves downstream of each option. Work packages that depend on a decision
are marked **blocked-on-decision** in §2/§4 and carry a fallback so the rest of their tasks
still run.

### D1 — finding #4: `clean_list`'s "analyzed nobody" → "everybody clean" fallback

**Where.** `sybilkit/src/sybilkit/curator.py:637`

```python
analyzed = set(res.analyzed) or set(weights)
```

**What it does now.** With a hand-built or empty `DetectResult`, `res.analyzed` is empty, so
the fallback rewrites *analyzed nobody* into *everybody analyzed and clean*:
`CleanList.standing(addr)` answers `"clean"` for a wallet that `res.wallet(addr)` says was
never analyzed. That is the repo's canonical "confident negative through an outage" hazard, in
the one object whose whole point is telling `clean` / `removed` / `unknown` apart.

**The memory file flags this as pinned by `test_the_clean_list_on_an_empty_result_keeps_everybody`
and therefore a design ruling. Read that test before ruling — it is weaker than it looks.**
`sybilkit/tests/test_curator.py:587` builds its "empty" result with a **real** `detect()` run
(`min_size=10**6`), and `cluster.py:280` sets `result.analyzed = frozenset(contributors)` on
every real run. So `res.analyzed` is *non-empty* in that test and the `or` branch never
fires: the test pins "no **clusters** keeps everybody", not "no **analyzed** keeps everybody".
On this reading the fallback is dead code for every result `detect()` can produce, and
Option B below leaves that test green. **WP5's first task is to verify this by running the
test after the change — if it reddens, the reading was wrong and the ruling escalates.**

| option | behaviour | cost |
|---|---|---|
| **A. keep the fallback** | status quo | `standing()` lies "clean" for an unanalyzed wallet on any hand-built/empty result; the three-word contract in `CleanList.standing`'s own docstring is untrue on that path |
| **B. drop it** — `analyzed = set(res.analyzed)` | a result that analyzed nobody yields no survivors; `standing()` answers `"unknown"`, which is the truth | changes a documented public-API behaviour for hand-built results; `contributors_total` becomes 0 there instead of the population size |
| **C. keep it but mark it** — fall back and set a `partial=True` flag on `CleanList` | preserves both | new public field, new rendering surface in maxpane, and it still ships a confident "clean" by default |

**Recommendation: B (drop the fallback).** It is the only option under which `standing()`'s
own docstring is true, it costs nothing on the path production actually takes (maxpane's
adapter always passes a real `detect()` result), and it is a one-line change with a
one-line docstring note. C buys a flag nobody renders.

**Downstream of B.** sybilkit: `clean_list`'s docstring gains a sentence; three new tests.
maxpane: none expected — `data/curator_clusters.py` builds `CleanList` from a live `detect()`
result, so `clean_contributors` and `clean_list_rows` are unchanged. WP7 confirms by running
`tests/data/test_curator_clusters.py` and `tests/data/test_curator_manager.py`.

---

### D2 — finding #5b: internal-transfer funding blindness

**Where.** `sybilkit/src/sybilkit/sources/blockscout.py:152-179` (`_funder_of`)

**What it does now.** Only `/addresses/{a}/transactions?filter=to` is walked. A wallet funded
by a `disperse`/multisend contract call receives its ETH as an **internal** transfer, which
never appears on that endpoint. The walk therefore completes cleanly with `oldest is None` and
writes a resolved `Funding(funder=None)` row — a *measurement* saying "we walked the whole
history and found no incoming transfer", for exactly the fan-out pattern the funding family
exists to catch. The strongest discriminator in the library (10/10 vs 0/47) is structurally
blind to its own target pattern, and the blindness is recorded as a fact.

| option | behaviour | cost |
|---|---|---|
| **A. document the limitation** | docstring + a coverage note; no new requests | the funding family stays blind to fan-outs; `funder=None` keeps meaning two things |
| **B. always walk `/internal-transactions?filter=to` as a second pass** | full coverage | ~2× Blockscout requests per address on the slow tier (adapter budget 200/sweep at ~3 req/s: ~70 s → ~140 s; still inside the 1 800 s tier, but it doubles the pacing for every wallet) |
| **C. walk internal transactions only when the normal walk finished with no incoming transfer** | full coverage for the fan-out case | near-zero marginal cost: the extra walk happens only for wallets that look self-created or internally funded, which is the minority |

**Recommendation: C.** It buys the target pattern at the cost of the wallets that need it, it
keeps the "a resolved row means the history was walked to the end" contract intact (it now
means *both* histories), and it does not slow the common case. A finished internal-funded
address resolves to `Funding(funder=X, hops=1)` — a direct internal transfer is still one hop.

**Downstream of C.** `FundingSweep`'s shape is unchanged, so the maxpane adapter and its
persisted slot are untouched. But **C changes detection**: more resolved funders means more
`funding` edges, which under the ≥ 2-family gate can promote components to clusters. That
makes `sybilkit/tests/test_bench.py` and maxpane's `tests/fixtures/curator/sybil/adapter_agrees.json`
live risks — WP9 re-checks both, and any movement is reported rather than absorbed. **If the
user wants zero detection movement in this pass, rule A now and file B/C as a follow-up;**
the fix for #5a (the `{'items': null}` frozen-outage row) and the module-docstring rewrite are
*not* blocked either way and land in WP4 regardless.

---

### D3 — finding #7: the conflicting-duplicate dedup rule

**Where.** `sybilkit/src/sybilkit/model.py:252` (`parsed.setdefault(...)`) and the same pattern
at `sybilkit/src/sybilkit/sources/logs.py:259` (`deposits.setdefault(...)`).

**What it does now.** Two rows with the same `(tx_hash, log_index)` but different content —
which is what a reorg replay, or two sweeps merged across a reorg, produces — are deduped
**first-wins on input order**. A shuffled producer and an ordered producer therefore build
different `Dataset`s, which directly contradicts `Dataset.from_events`' own docstring ("so a
shuffled producer and an ordered one build the same dataset"), and an old-then-new ordering
keeps the orphaned row.

| option | behaviour | cost |
|---|---|---|
| **A. keep first-wins** | status quo | order-dependent datasets; the docstring is untrue |
| **B. deterministic content tie-break: keep the higher `block_number`, then a total order on the remaining words** | order-independent; the canonical row (the later inclusion) wins | ~6 lines in each of two modules; identical duplicates are unaffected |
| **C. drop the key entirely when two rows conflict** | order-independent | loses a real row whenever a producer hands over a benign near-duplicate; "dropped, not zeroed" becomes "dropped, and so was its twin" |

**Recommendation: B.** The only real-world producer of a conflicting `(tx_hash, log_index)` is
a replay, and the canonical row is the one at the higher block. Concretely, in both modules:

```python
key = (dep.tx_hash, dep.log_index)
prev = parsed.get(key)
if prev is None or _replay_rank(dep) > _replay_rank(prev):
    parsed[key] = dep
```

with `_replay_rank(d) = (d.block_number, d.new_weight_wei, d.amount_wei, d.credited_delta_wei,
d.weight_added_wei, d.tx_count, d.hour)` — the first term is the rule and the rest exist only
so the answer never depends on input order.

**Downstream of B.** The rule must be **byte-identical in both modules**; the plan freezes it
here so WP2 (`model.py`) and WP4 (`logs.py`) can implement it in parallel without talking, and
WP4 owns the cross-check test that they agree on one scenario. No committed fixture contains a
conflicting duplicate, so nothing else is expected to move.

---

### D4 — finding #12: `largest_operators` — rename the band, or filter it?

**Where.** `sybilkit/src/sybilkit/curator.py:435-446` (the band) vs `curator.py:318-324`
(`Segments.largest_operators`, the property, never called by any consumer).

**What it does now.** The band keyed and labelled `largest_operators` aggregates the members of
**every** linked cluster, however small. The identically-named property applies the preset's
800-ETH combined-credit line. maxpane renders the *band* first in the SEGMENTS panel, so the
on-screen row reading "largest operators" is inflated by every small group, and
`largest_operator_credit_wei` — a knob whose whole purpose is to define "largest" — gates
nothing anybody sees.

| option | band membership | label / key | cost |
|---|---|---|---|
| **A. rename the band** to `linked_groups` / "linked groups"; leave the property as the credit-line slice | unchanged (all linked clusters) | key + label change | key-vocabulary test, one CLI test assertion, one committed fixture, five maxpane test assertions, two READMEs |
| **B. filter the band** to clusters at or above `largest_operator_credit_wei` | shrinks | unchanged | the panel's headline number changes from "6 303 wallets / 43.25 % of points" to the small credit-line slice — which is the *single-send whale list problem* research §5 exists to reject; the fixture numbers and their assertions move |
| **C. do both** — rename the aggregate and add a second `largest_operators` band | two rows | both | more panel surface; the widget renders `MAX_ROWS` only, so ordering has to be re-decided |

**Recommendation: A (rename to `linked_groups` / "linked groups").** The band's *value* — all
linked groups, 43.25 % of points — is the most useful number on the panel and is measured
correctly; the defect is purely that it carries a name that means something else. Renaming
keeps every measured number true, makes the key vocabulary mean exactly one thing, keeps the
credit line meaningful on the property (which a consumer can render if it wants), and speaks
the dashboard's own on-screen word (`linked`). Option B silently deletes the headline and puts
the wrong whale list first. Option C adds surface for a slice already reachable via the
property — defer it.

**Downstream of A** (all of it is WP5 in sybilkit and WP7 in maxpane; §7 lists the exact
tests):

- library: the `_band(...)` call, `Segment.__doc__`'s key vocabulary, `Segments.__doc__`,
  `sybilkit/tests/test_curator.py` (the key-vocabulary regex + the docstring spellings),
  `sybilkit/tests/test_cli.py:210`, `sybilkit/README.md:125`.
- maxpane: **no adapter code change** — the label passes through `pattern_language()` and the
  ordering keys on `b.kind == "operators"`, both unchanged — but five test assertions, one
  committed fixture (`tests/fixtures/curator/sybil/segment_rows_worst.json`), the
  `widgets/curator/segments.py` docstring example and `README.md:76`.
- width: "linked groups" (13 columns) is **shorter** than "largest operators" (17), and
  `CuratorSegments` is not the analysis body's binding panel (`CuratorOperators` is, at 82
  columns), so the 137-column pin cannot move upward. WP7 re-runs the sweep anyway.

---

### D5 — finding #13: the near-amount rule at the exempt protocol minimum

**Where.** `sybilkit/src/sybilkit/signals/amounts.py:75-91`

**What it does now.** The near pass buckets single-deposit wallets by block, sorts each bucket
by `(amount, address)` and compares **adjacent pairs only**, skipping equal amounts
(`a_amt != b_amt`). At the exempt protocol minimum — where ~1 990 live wallets sit on exactly
the same wei value — a run of byte-equal rows sits between two near neighbours, and **which**
of those byte-equal wallets gets the near edge is decided by lowercase address sort order.
`identical_amount_windows` already rules (R13b) that identicalness at the minimum identifies
nobody; the near pass then quietly re-admits an arbitrary member of that same crowd.

| option | behaviour | cost |
|---|---|---|
| **A. exclude exempt-amount rows from the near pass entirely** (R13b-consistent) | the minimum crowd contributes no amount edges at all, from either rule | a genuine near-neighbour of the minimum loses an edge — but that edge was the arbitrary artifact in the overwhelming majority of cases |
| **B. link equal-amount runs to the neighbour symmetrically** | deterministic | turns a 1 990-member minimum crowd into 1 990 near edges through one neighbour: it *welds* the crowd into a component, which is strictly worse than the arbitrariness it fixes |
| **C. A for exempt amounts, B for non-exempt** | deterministic | for non-exempt amounts the run is already connected by `identical_amount_windows`, so the near edge reaches every member transitively — C collapses to A |

**Recommendation: A.** One line, consistent with the ruling that already exists, and it removes
the order-dependence rather than replacing it with a different arbitrary answer:

```python
    exempt = cfg.protocol_min_amount_wei
    for addr, dep in singles.items():
        if exempt is not None and dep.amount_wei == exempt:
            continue          # R13b: identicalness at the minimum identifies nobody
        by_block[dep.block_number].append((dep.amount_wei, addr))
```

**Downstream of A.** The curator preset passes the live `minDeposit()` as
`protocol_min_amount_wei`, so **this changes detection on the live population**: some
minimum-crowd wallets lose their only `amount` family and, under the ≥ 2-family gate, their
cluster. Like D2/C, this puts `test_bench.py` and `adapter_agrees.json` on the watch list —
WP9 re-checks and reports rather than retunes.

---

### D6 — finding #14: the per-address funding page cursor is a persisted-slot schema change

**Where.** `sybilkit/src/sybilkit/sources/blockscout.py:156-179` and, downstream,
`maxpane_dashboard/data/curator_clusters.py::EnrichmentSweep.state` / `fetch_enrichment`.

**Two defects, only one of them decision-sized.**

- **(a) the filter is dropped from page 2 onward** — `params = nxt` *replaces* `{"filter":
  "to"}` with the server's cursor, so every page after the first asks for the address's whole
  transaction history rather than its incoming half, and a busy wallet hits the page wall
  early. Fix: `params = {**nxt, "filter": "to"}`. **Not decision-blocked — WP4 does it.**
- **(b) there is no per-address page cursor** — an address that lands in `PENDING_PAGES`
  re-walks **from page 1 every sweep, forever**. The adapter measured 80 paced pages ≈ 27 s of
  the 1 800 s cycle spent making zero progress, and pendings head the budget, so they crowd out
  new addresses too.

| option | behaviour | cost |
|---|---|---|
| **A. no cursor** | status quo + the adapter's existing page-bound doubling (20 → 80) | a page-bounded wallet never resolves; the defect stays |
| **B. per-address cursor on `FundingSweep`, persisted in the adapter's slot** | a page-bounded wallet resumes mid-history and finishes over several sweeps | one new defaulted field on a public frozen dataclass; one new key in the adapter's persisted cursor; a compatibility read for payloads written before it |
| **C. B, and delete the adapter's page-bound doubling** | simpler | removes a mechanism with existing tests, in the same pass that adds a new one |

**Recommendation: B.** Concretely:

- `FundingSweep` gains `page_cursors: dict[str, dict] = field(default_factory=dict)` — added
  **last, with a default**, so existing keyword construction and the two positional call sites
  are unaffected. A default is right here (unlike `Dataset`'s deliberate refusal of one)
  because "no cursors" is a real state, not a payload a producer forgot to pass.
- `fetch_funding` gains `cursors: Mapping[str, Mapping] | None = None`, keyword-only.
- `_funder_of` takes the starting `params` and the best-so-far `oldest`, and returns the cursor
  it stopped on. The persisted entry per address is
  `{"params": {...}, "funder": "0x…" | None, "block": int | None}` — Blockscout serves
  newest-first, so a resumed walk only ever needs the best-so-far and the next page params.
- **Compatibility (the load-bearing half):** the maxpane adapter reads the cursor block with
  the same tolerant shape it already uses for `txs`/`funding`/`pending`/`reasons`/`page_bound`
  (`prior.get("cursors")` → `{}` when absent), so **a slot payload written before this change
  still loads and simply resumes from page 1**. WP7 owns an explicit test for that, by name.
- Keep the page-bound doubling for now; §6 records the redundancy for the cleanup lane.

**Downstream of B.** sybilkit: `blockscout.py` + `test_sources.py`. maxpane: `EnrichmentSweep`
gains `funding_cursors`, `state()` gains `"cursors"`, `fetch_enrichment` reads it tolerantly
and passes it back; `slot_payload` carries it inside the existing `enrichment` dict, so
`SLOT_CLUSTERS`'s own shape does not change and nothing in `curator_cache.py` needs a version
bump. WP7's compatibility test is the gate.

---

## 2. Work packages, ownership and the dependency DAG

```
        ┌──────────────────────────────────────────────────────────────┐
        │  Wave 0 — the six rulings (D1..D6).  Not an agent WP.         │
        └───────────────┬──────────────────────────────────────────────┘
                        │
   ┌──────────┬─────────┼──────────┬─────────────┐        wave 1 (5 agents, parallel)
   ▼          ▼         ▼          ▼             ▼
 WP1        WP2       WP3        WP4           WP5
 signals    model    cluster    sources       curator preset
 #1 #2 #13* #7a* #8 #9  #6    #3 #5 #7b* #10 #11 #14*   #4* #12a* #15
   │          │         │          │             │
   └──────────┴────┬────┴──────────┴──────┬──────┘
                   ▼                      ▼               wave 2 (2 agents, parallel)
                 WP6                     WP7
                 CLI + below-cap        maxpane follow-through
                 (cli.py)               (#12b, #14 cursor, sweep-behaviour)
                   └──────────┬───────────┘
                              ▼                            wave 3
                            WP8  cleanup lane (no behaviour change)
                              │
                              ▼                            wave 4
                            WP9  verification + record
```

`*` = blocked on a decision (§1). Every such WP has non-blocked tasks it can run first.

### File ownership — exactly one owner each

| file | owner | wave |
|---|---|---|
| `sybilkit/src/sybilkit/signals/funding.py` | WP1 | 1 |
| `sybilkit/src/sybilkit/signals/gas.py` | WP1 | 1 |
| `sybilkit/src/sybilkit/signals/amounts.py` | WP1 | 1 |
| `sybilkit/tests/test_signals_{funding,gas,amounts}.py` | WP1 | 1 |
| `sybilkit/src/sybilkit/model.py`, `sybilkit/tests/test_model.py` | WP2 | 1 |
| `sybilkit/src/sybilkit/cluster.py`, `sybilkit/tests/test_cluster.py` | WP3 | 1 |
| `sybilkit/src/sybilkit/sources/__init__.py` | WP4 | 1 |
| `sybilkit/src/sybilkit/sources/{logs,txs,blockscout}.py` | WP4 | 1 |
| `sybilkit/tests/test_sources.py` | WP4 | 1 |
| `sybilkit/src/sybilkit/curator.py`, `sybilkit/tests/test_curator.py` | WP5 | 1 |
| `sybilkit/tests/test_cli.py` | **WP5 in wave 1** (one assertion, D4), **WP6 in wave 2** | 1→2 |
| `sybilkit/src/sybilkit/cli.py` | WP6 | 2 |
| `maxpane_dashboard/data/curator_clusters.py` | WP7 | 2 |
| `maxpane_dashboard/widgets/curator/segments.py` (docstring only) | WP7 | 2 |
| `tests/data/test_curator_clusters.py`, `tests/data/test_curator_manager.py`, `tests/data/test_curator_sybil_data.py` | WP7 | 2 |
| `tests/widgets/test_curator_widgets.py`, `tests/screens/test_curator_screen.py` | WP7 | 2 |
| `tests/fixtures/curator/sybil/segment_rows_worst.json` | WP7 | 2 |
| `sybilkit/src/sybilkit/{curve,report,labels,bench}.py`, `sybilkit/src/sybilkit/signals/{__init__,sequence,cadence,split}.py` | WP8 | 3 |
| `sybilkit/tests/{conftest,sybilkit_fixtures,test_bench,test_report,test_purity,test_public_api,test_fixtures,test_curve,test_labels}.py` | WP8 | 3 |
| `README.md` — **the SEGMENTS bullet only (line 76)** | **WP7 in wave 2** | 2 |
| `sybilkit/README.md` — **the `segments(...)` comment only (line 125)** | **WP5 in wave 1** | 1 |
| `README.md` and `sybilkit/README.md` — everything else | WP9 | 4 |
| `CLAUDE.md`, this plan's close-out, the memory record | WP9 | 4 |

**Corrected 2026-08-18 by WP9 (close-out, §10).** As first written this table gave WP9 sole
ownership of both READMEs, while §3/WP5.3 told WP5 to update `sybilkit/README.md:125` and
§3/WP7.1 and §6 told WP7 to update `README.md:76`. Three work packages were named owners of
two files, which is the one thing the ownership table exists to prevent. The rows above are the
resolution the build actually took, and it is the right one: the D4 rename must land in the
same wave as the key it renames, or a README documents a key the library no longer emits across
a wave gate. WP9 confirmed both edits rather than re-making them (§10, "landed in an earlier
wave"), and owns every other line of both files.

**A second correction, 2026-08-18, by the WP9 that finished the close-out.** Two lines this
table assigns to WP7 were still carrying the pre-rename wording when wave 2 closed, and WP9 took
them in the close-out pass on the user's explicit brief rather than reporting them a second time:
`README.md`'s SEGMENTS bullet (line 76) and `maxpane_dashboard/widgets/curator/segments.py`'s
line-3 clause. They were listed as O1 and O2 in the first draft of §10.7 and are closed there
now. The rows above are left as they were written — they record who *should* have taken each
line, and the exception is the interesting part.

**Two more files carry two owners, and neither pair ever runs concurrently.**
`sybilkit/tests/test_cli.py`: WP5 (wave 1) changes exactly one assertion — the
`largest_operators` key spelling at line 210 — because leaving it to WP6 would put the suite red
across a wave gate.
WP6 (wave 2) owns the file from then on. If the user prefers strict one-owner-forever, fold
WP6 into WP5's agent and run it as WP5's last task; the plan is otherwise unchanged.

**Untouched — no WP may edit these:** `maxpane_dashboard/analytics/curator_signals.py`
(byte-identical to what shipped, and a test asserts it never learns sybilkit exists),
`maxpane_dashboard/data/curator_client.py`, `app.py`, `__main__.py`,
`screens/game_select.py`, `themes/minimal.tcss`, `maxpane/` (the Rust crate), and
`tests/fixtures/curator/captures/live/`.

### Wave schedule and gates

| wave | runs concurrently | waits on | gate |
|---|---|---|---|
| **0** | the six rulings | — | D1–D6 answered (or explicitly deferred with the fallback recorded) |
| **1** | WP1 ∥ WP2 ∥ WP3 ∥ WP4 ∥ WP5 | wave 0 | each WP's own tests green **and each mutation observed red**; full sybilkit suite green at ≥ 289 + new, 0 skipped; `test_bench.py` unchanged or **escalated, never retuned** |
| **2** | WP6 ∥ WP7 | wave 1 (WP6 also on WP5's key rename; WP7 on WP5 **and** WP4) | sybilkit suite green; **full maxpane suite green at ≥ 4 661**; the analysis body still measures 137 and `CURATOR_FULL_LAYOUT_COLUMNS`/`FULL_LAYOUT_COLUMNS` are unmoved |
| **3** | WP8 | waves 1–2 | both suites green with **byte-identical detection output** on the committed fixtures — a cleanup that changes a number is a failed cleanup |
| **4** | WP9 | waves 1–3 | both suites green; `cargo test` green; both distributions build; every one of the 15 findings maps to a named committed test; memory + docs updated |

**Critical path:** `wave 0 → WP4 → WP7 → WP8 → WP9`. WP4 is the biggest single WP (five
findings plus three below-cap items in one package) because `sybilkit/tests/test_sources.py` is
one file and splitting it across agents would break the one-owner rule; it is the WP to start
first and to staff best.

---

## 3. Work-package briefs

Each brief lists, per finding: **the failing-first test(s)**, **the minimal code change**, and
**the mutation that proves the test bites**. Test names are proposals in the repo's
sentence-style naming; keep the shape, adjust the wording if the code says otherwise.

---

### WP1 — the evidence-fabrication lane (pure signals)  [Data Engineer / AI Engineer]

**Findings:** #1 (funding self-edge), #2 (gas fingerprints not deduped), #13 (near rule at the
exempt minimum — **blocked on D5**). Plus the unused `Deposit` import in `gas.py` (cleanup
freebie, since WP1 owns the file).

**Owns:** `signals/funding.py`, `signals/gas.py`, `signals/amounts.py`,
`tests/test_signals_funding.py`, `tests/test_signals_gas.py`, `tests/test_signals_amounts.py`.
**Reads, never edits:** `cluster.py`, `signals/__init__.py`, `model.py`.

#### WP1.1 — #1: a self-referential funding row fabricates the funding family

A hand-edited slot payload (third-party input, per the adapter's own translation-boundary rule)
carrying `{'address': A, 'funder': A}` produces `Edge(A, A, "funding", 0.95, …)`. The
union is a no-op, but `best_by_family[root]["funding"]` is set — so the component **gains a
distinct family**, and a one-family component clears the ≥ 2-family gate and convicts at
noisy-OR ≈ 0.995.

- **Failing-first tests** (`test_signals_funding.py`):
  - `test_a_self_funding_row_never_creates_the_funding_family`
  - `test_a_self_funding_row_never_joins_a_shared_funder_hub`
  - `test_a_hand_edited_self_funding_row_cannot_lift_a_one_family_component`
    (drives `detect()` on a one-family fixture + the self row; asserts `res.clusters == []`)
- **Code:** in the peel-chain loop, `if funder is None or funder.lower() == addr.lower() or
  is_infra_funder(funder): continue`; in the `by_funder` fold, the same `entry.funder.lower()
  != addr.lower()` condition. Use `.lower()` on both sides so the guard does not depend on
  WP2's #9 landing (they run in parallel).
- **Mutation:** delete the `funder != addr` clause → all three redden.

#### WP1.2 — #2: N members sharing one transaction present as N agreeing fingerprints

`gas_edges` collects one `Tx` **per member**, so a router/batcher wave whose first deposits all
ride one transaction hands the uniformity test the *same tuple* N times: every axis collapses
by construction and the group scores 0.85 for a fee fingerprint that is one transaction.

- **Failing-first tests** (`test_signals_gas.py`):
  - `test_a_group_whose_first_deposits_share_one_transaction_yields_no_gas_edge`
  - `test_the_uniformity_count_is_distinct_transactions_not_members`
  - `test_a_router_batched_wave_cannot_reach_the_two_axis_strength`
  - `test_a_group_with_enough_distinct_transactions_still_fires` (the guard against
    over-correcting)
- **Code:** build `by_hash: dict[str, Tx]` keyed on `dep.tx_hash` and a separate `covered:
  set[str]` of members that had one; keep the **coverage** gate on `len(covered)` (it is a
  statement about the group) and add a **distinct-transaction** gate
  `len(by_hash) >= cfg.min_size` before any axis is computed. `fingerprints =
  list(by_hash.values())`.
- **Reason string:** leave `f"one fee fingerprint across ×{len(fingerprints)} …"` **unchanged
  in length**. The number now counts distinct transactions; say so in the module docstring
  rather than in the string. Lengthening it risks a cross-distribution re-pin of maxpane's
  82-column OPERATORS evidence cell for no user-visible gain. If the user wants the string to
  say "txs", that is a deliberate width change and WP7 re-runs the sweep.
- **Mutation:** restore the per-member list comprehension → the first two tests redden.
- **Freebie:** drop `Deposit` from `from ..model import Dataset, Deposit, Tx` (unused).

#### WP1.3 — #13: the near rule at the exempt minimum  *(blocked on D5)*

- **Failing-first tests** (`test_signals_amounts.py`):
  - `test_a_near_edge_at_the_exempt_minimum_is_never_emitted`
  - `test_which_of_two_byte_equal_minimum_wallets_links_is_not_decided_by_address_order`
    (two datasets identical but for the addresses' lexical order; assert equal edge sets)
  - `test_a_near_edge_above_the_exempt_minimum_still_fires`
- **Code (D5 option A):** skip `dep.amount_wei == cfg.protocol_min_amount_wei` when building
  `by_block` (§1, D5).
- **Mutation:** remove the exempt filter → the order-independence test reddens.
- **If D5 is deferred:** ship WP1.1 and WP1.2, leave `amounts.py` untouched, and record the
  order-dependence as an open finding in WP9's ledger.

**Done when:** three (or two) fixes green and mutation-proven, no I/O import added, and the
labeled-subset results are either unchanged or the change is **reported**, not absorbed.

---

### WP2 — dataset integrity  [Data Engineer]

**Findings:** #7a (conflicting duplicates in `model.py` — **blocked on D3**), #8 (non-numeric
`ts` drops the whole row), #9 (pre-built-object fast paths skip normalization).

**Owns:** `sybilkit/src/sybilkit/model.py`, `sybilkit/tests/test_model.py`.

#### WP2.1 — #8: a present-but-non-numeric `ts` silently empties the dataset

`ts=None if ts is None else float(ts)` sits inside the row's single `try`, so an ISO-8601
string — exactly what Blockscout and every CSV export hand out — raises `ValueError` and the
blanket `except` drops the **whole deposit**. A fully valid population with ISO timestamps
becomes an empty `Dataset` and every downstream count reads zero.

- **Failing-first tests:**
  - `test_an_iso_string_timestamp_degrades_the_label_and_keeps_the_deposit`
  - `test_a_whole_population_with_iso_timestamps_still_builds_a_dataset` (the review's
    reproduction, committed)
  - `test_a_malformed_amount_still_drops_the_row` (the drop discipline is intact)
- **Code:** parse `ts` in its own `try`, degrading to `None` — `ts` is the one field whose
  absence already degrades a *label* and not a signal (cadence runs off `block_number`), so a
  malformed one must degrade the same way an absent one does. Say that in the docstring.
- **Mutation:** fold `ts` back into the outer `try` → the two ISO tests redden.

#### WP2.2 — #9: the pre-built-object fast paths bypass every coercer

`isinstance(row, Funding)` and `isinstance(row, Tx)` short-circuit straight into the dict.
Consequences, each reproduced: a checksummed `Funding.funder` survives, and since the component
map is lowercase it **kills the 0.95 peel-chain edge** and splits `by_funder` hubs; `Tx` fields
skip `_opt_wei`, so a float fee enters the gas axes; and `_addr` rejects `0X…` while `_wei`
accepts it, so the same spelling is valid in one field and malformed in another.

- **Failing-first tests:**
  - `test_a_checksummed_funder_on_a_prebuilt_row_is_lowercased_like_a_mapping_row`
  - `test_a_prebuilt_tx_with_a_float_fee_is_dropped_not_admitted`
  - `test_an_uppercase_0x_address_is_accepted_exactly_like_a_lowercase_one`
  - `test_the_prebuilt_and_mapping_paths_build_equal_datasets` (same rows through both paths →
    equal `Dataset`)
- **Code:** rebuild both dataclasses through the same coercers inside a `try/except
  (_Malformed, TypeError, ValueError): continue`; and in `_addr`, lowercase (and strip) **before**
  the `0x` prefix check, exactly as `_wei` already does.
- **Mutation:** restore either fast path → the corresponding test reddens.
- **Note for WP1:** this fix can *add* funding edges on hand-built datasets that previously
  lost them to casing. Committed fixtures build through the mapping path, so no movement is
  expected — if the benchmark moves, escalate.

#### WP2.3 — #7a: conflicting duplicates  *(blocked on D3)*

- **Failing-first tests:**
  - `test_a_shuffled_producer_and_an_ordered_one_build_the_same_dataset`
  - `test_a_reorg_replay_keeps_the_row_at_the_higher_block`
  - `test_two_byte_identical_duplicates_still_collapse_to_one_row`
- **Code:** D3 option B's `_replay_rank` fold, byte-identical to WP4's copy in `logs.py`.
- **Mutation:** restore `parsed.setdefault(...)` → the shuffle test reddens.
- **If D3 is deferred:** ship WP2.1/WP2.2 and soften the `from_events` docstring's
  order-independence promise to match the code, with a `# TODO(D3)` naming this plan.

---

### WP3 — order-independent scoring in the combiner  [Data Engineer]

**Finding:** #6.

**Owns:** `sybilkit/src/sybilkit/cluster.py`, `sybilkit/tests/test_cluster.py`.

`detect`'s `last_weight` fold walks `ds.deposits` **in the order the caller supplied**, while
the `Dataset` contract says detectors sort it themselves and both `signals.first_rows` and
`curator.final_weights` do exactly that. A hand-built newest-first dataset therefore makes
`detect().total_points` disagree with `curator.final_weights` on the same input, and the
disagreement is silent.

- **Failing-first tests:**
  - `test_a_newest_first_dataset_scores_the_same_points_as_a_chain_ordered_one`
  - `test_total_points_agrees_with_the_curator_preset_on_a_hand_built_dataset`
  - `test_a_clusters_points_do_not_depend_on_the_deposit_order` (per-cluster, not just the
    total — the share is what reaches the screen)
- **Code:** `for dep in sorted(ds.deposits, key=lambda d: (d.block_number, d.log_index)):` and
  update the comment, which currently asserts an ordering the function does not establish.
- **Mutation:** remove the `sorted(...)` → the first test reddens.
- **Do not** hoist this into a shared helper here; that is WP8's lane and it must not ride
  along with a behaviour fix.

---

### WP4 — the sources lane  [Backend Architect] — *start this first*

**Findings:** #3, #5a + #5c (docstring), #5b (**blocked on D2**), #7b (`logs.py` half —
**blocked on D3**), #10 (both halves), #11, #14a + #14b (**#14b blocked on D6**). Plus
below-cap items B3(half), B6, B7 (§5).

**Owns:** `sources/__init__.py`, `sources/logs.py`, `sources/txs.py`, `sources/blockscout.py`,
`sybilkit/tests/test_sources.py`.

This is one WP because `test_sources.py` is one file and the findings interact (a change to
error classification changes what the batch path raises, which changes what `txs.py` catches).
Run its tasks in the order below; commit each.

#### WP4.1 — #3: `rpc_call` treats any 200 body it cannot read as success

`resp.json()` failing sets `body = None`, and the final line returns `body.get("result") if
isinstance(body, dict) else body`. So a **200 text/html** answer returns `None` with **no pool
rotation** — a healthy second endpoint is never tried — and a **200 `[]`** body is returned
verbatim, which `_page` accepts as a page of zero logs, so `fetch_deposits` completes an
**empty sweep**: "this contract has no history", during an outage. `rpc_batch` already rotates
on the same input, and that asymmetry is the proof the intent was rotation.

- **Failing-first tests:**
  - `test_a_two_hundred_html_body_rotates_to_the_next_endpoint` (assert the transport recorded
    a request to the second URL)
  - `test_a_two_hundred_bare_array_body_is_not_a_completed_sweep`
  - `test_an_unreadable_body_from_every_endpoint_degrades_to_none_not_an_empty_history`
- **Code:** after the DEAD-status check, parse; if the body is unparseable or **not a `dict`**
  (a single JSON-RPC answer is an object by spec, even when its `result` is a list), set `last`
  and `break` to the next URL — the same shape `rpc_batch` uses for `not isinstance(body, list)`.
- **Mutation:** restore the `else body` tail → all three redden.

#### WP4.2 — #11: range-classified errors shrink but never rotate

Three sub-defects on one path (`logs.py::_page`): (i) a throttle message containing `"limited
to"` is classified `RangeTooWide`, so the walk shrink-loops 800 → 50 **against the same
endpoint** and fails the sweep with the second endpoint receiving zero requests; (ii) the span
shrink is permanent for the whole walk, so one dense region costs 16× the requests for every
later chunk; (iii) one more `RangeTooWide` after `max_shrinks` returns `None` and **discards
every chunk already fetched**, with no resume cursor.

- **Failing-first tests:**
  - `test_a_throttle_message_that_looks_like_a_range_cap_still_rotates_the_pool`
  - `test_the_second_endpoint_receives_a_request_before_the_sweep_fails`
  - `test_a_narrowed_span_recovers_after_a_run_of_clean_chunks`
  - `test_a_sweep_that_read_some_chunks_returns_how_far_it_got_not_none`
  - `test_a_sweep_that_read_nothing_is_still_none` (the existing contract, kept)
- **Code:**
  - (i) `_page` keeps its own `pool = list(cfg.log_rpcs)`; on shrink exhaustion (or
    `span <= cfg.min_log_window`) it drops the head of the pool, resets `span` and `shrinks`,
    and continues from the **same cursor**. `None` only when the pool is empty.
  - (ii) after `SPAN_RECOVER_AFTER = 4` consecutive clean chunks, double `span` back toward
    `cfg.log_chunk_blocks`.
  - (iii) `_page` returns `(rows, covered_to_block)`; `fetch_deposits` builds
    `DepositSweep(from_block, covered_to, …)` when at least one chunk was read, and `None` when
    zero were. `DepositSweep.to_block` is already the field that tells the truth about coverage
    and is already the resume cursor, so a partial sweep is honest rather than a lie of
    omission. **Micro-decision, recommended not blocking:** this relaxes a documented
    "None, never a partial" contract. It is safe here because maxpane never calls
    `fetch_deposits` (the adapter imports only `sources.blockscout`, `sources.txs` and
    `DEFAULT_CONFIG`), and the CLI records `block_range` from the sweep, so the partial states
    its own extent. If the user prefers the strict contract, implement (i) and (ii) only and
    record (iii) as deferred.
- **Mutation:** remove the rotation → `test_the_second_endpoint_receives_a_request_before_the_sweep_fails`
  reddens.

#### WP4.3 — #10: a malformed later batch discards everything already read; and the code tiebreak

`txs.py:146` returns `None` on `MalformedRequest`, but `None`'s documented meaning is "**no**
batch was read". One bad hash string in a hand-edited cursor (a `-32602`) therefore throws away
every fingerprint the earlier batches did read. Separately, `sources/__init__.py:244` ends
`is_endpoint_limitation` with `err.get("code") not in MALFORMED_REQUEST_CODES` — classification
**by code**, which `CLAUDE.md` forbids for exactly the reason the module's own docstring gives.

- **Failing-first tests:**
  - `test_a_malformed_hash_in_a_later_batch_keeps_the_fingerprints_already_read`
  - `test_a_malformed_hash_in_the_first_batch_is_still_none`
  - `test_the_pending_cursor_after_a_malformed_batch_names_every_unread_hash`
  - `test_a_genuine_invalid_params_message_short_circuits_without_rotating`
  - `test_an_error_object_with_no_message_falls_back_to_the_code_and_says_so`
- **Code:**
  - `txs.py`: enumerate `batches`; on `MalformedRequest`, extend `pending` with **every hash
    from this batch onward** and `break`. The existing `if read == 0: return None` then keeps
    the "no batch was read" meaning exact.
  - `sources/__init__.py`: add `MALFORMED_REQUEST_PATTERNS` (`"invalid params"`, `"invalid
    request"`, `"method not found"`, `"parse error"`, `"unknown block"`, …) and require
    **message agreement** before short-circuiting. Fall back to the code **only** when the
    error object carries no message at all — the one case with no text to classify — and say
    so in the docstring, since it is now the module's single documented use of a code.
- **Mutation:** restore `return None` → the first test reddens; drop the message vocabulary →
  the drpc routing-refusal rotation test reddens.
- **Guard rail:** `test_a_malformed_request_short_circuits_instead_of_rotating` (line 331) and
  `test_a_malformed_batch_short_circuits_instead_of_rotating` (line 618) exist and must stay
  green **without being weakened** — the new vocabulary has to cover the real-world spellings
  they use. If it cannot, that is a finding, not a licence to edit the assertion.

#### WP4.4 — #5a and #5c: the frozen-outage row and the lying module docstring

`{"items": null}` from a 200 passes the `"items" in body` guard, so the walk is treated as
**complete** and a resolved `Funding(funder=None)` row is written — the exact "corruption
outlives the outage" hazard the `FundingSweep` docstring spends a paragraph forbidding, and in
the adapter's persisted slot it outlives the process too. Separately, the **module** docstring
(lines 15-21) still teaches the pre-`b0ebcbd` behaviour ("emitted with a `None` funder **and**
stays pending"), which the class docstring and the code explicitly reversed.

- **Failing-first tests:**
  - `test_a_page_whose_items_are_null_is_unreadable_not_a_finished_walk`
  - `test_a_null_items_page_never_freezes_a_none_funder_into_a_resolved_row`
  - `test_the_funding_docstrings_agree_that_a_pending_address_gets_no_row` (scan
    `blockscout.__doc__` for the contradictory phrase — the repo already does doc-agreement
    tests, cf. `test_the_segment_key_vocabulary_is_exactly_what_the_docstring_names`)
- **Code:** `items = body.get("items")`; require `isinstance(items, list)` or return
  `PENDING_UNREADABLE`. Rewrite the module docstring paragraph to match the class docstring.
- **Mutation:** restore the `"items" not in body` guard → the first two redden.

#### WP4.5 — #14a: the incoming filter is dropped from page 2

- **Failing-first test:** `test_every_funding_page_after_the_first_still_carries_the_incoming_filter`
  (assert the recorded page-2 request's params, which the review proved carry no filter).
- **Code:** `params = {**nxt, "filter": "to"}`.
- **Mutation:** restore `params = nxt` → the test reddens.
- Check `test_funding_paginates_by_keyset_and_takes_the_oldest_incoming_transfer` (line 757):
  if it asserts page-2 params equal the cursor verbatim, that assertion **pins the defect** and
  is updated; nothing else in it moves.

#### WP4.6 — #14b: the per-address page cursor  *(blocked on D6)*

- **Failing-first tests:**
  - `test_a_page_bounded_address_resumes_from_its_own_cursor_next_pass`
  - `test_a_resumed_walk_keeps_the_oldest_funder_found_before_the_bound`
  - `test_a_sweep_without_cursors_still_walks_from_page_one`
  - and the existing `test_a_page_bounded_address_is_actually_re_read_on_the_next_pass`
    (line 881) must stay green — it is the weaker statement the new tests strengthen.
- **Code:** D6 option B (§1) — `FundingSweep.page_cursors` (defaulted, added last),
  `fetch_funding(..., cursors=None)`, `_funder_of` taking a starting `params` + best-so-far and
  returning the cursor it stopped on.
- **Mutation:** ignore the incoming `cursors` argument → the resume test reddens.

#### WP4.7 — #5b: internal-transfer funding  *(blocked on D2)*

- **Failing-first tests** (D2 option C):
  - `test_a_wallet_funded_by_an_internal_transfer_resolves_its_funder`
  - `test_the_internal_walk_only_runs_when_the_normal_walk_found_nothing`
    (assert the request count for a normally-funded wallet is unchanged)
  - `test_a_disperse_style_fan_out_produces_one_shared_funder_across_the_batch`
- **Code:** after a `_COMPLETE` walk with `oldest is None`, walk
  `/addresses/{a}/internal-transactions` with `filter=to` under the same page bound, cursor and
  pacing; a hit resolves `Funding(funder=X, hops=1)`.
- **Mutation:** skip the internal walk → the fan-out test reddens.
- **If D2 rules A:** write only the documentation change plus
  `test_the_funding_docstring_states_that_internal_transfers_are_not_walked`, and record the
  limitation in the WP9 ledger and in `sybilkit/README.md`.

#### WP4.8 — #7b, and the below-cap items that live in `sources/`

- **#7b:** the `_replay_rank` dedupe in `logs.py:259`, byte-identical to WP2's copy, plus
  `test_a_replayed_log_row_is_deduped_to_the_higher_block` and the cross-module agreement test
  `test_the_log_sweep_and_from_events_agree_on_a_conflicting_duplicate`.
- **B3 (half): a negative `--funding-budget` inverts the cap** — `wanted[:budget]` with a
  negative slices from the end, so `budget=-5` looks up *all but the last five*. Clamp inside
  `fetch_funding`: `budget = None if budget is None else max(0, budget)`, and `0` means
  everything deferred, `truncated=True`, **zero requests**.
  Test: `test_a_negative_funding_budget_is_a_zero_budget_not_an_inverted_one`.
- **B6: a 429 rotates with no backoff** — `429 ∈ DEAD_STATUS_CODES` breaks straight to the next
  URL. Pace `backoff_seconds[attempt]` before rotating on 429 specifically (it is the one dead
  status that means "later", not "never").
  Test: `test_a_429_backs_off_before_rotating`.
- **B7: string-echoed batch ids are dropped on re-alignment** — `by_id.get(entry.get("id"))`
  misses a provider that echoes `"1"` for `1`, so those slots stay `None`, decode to nothing,
  and land in `pending` — a silent partial that looks like a reorg.
  Test: `test_a_provider_that_echoes_string_ids_still_realigns_the_batch`.
  Code: normalize the echoed id through a small `_slot_of(raw)` that tries `int(raw)` for `str`.

**Done when:** all of the above green and mutation-proven; the existing 44 tests in
`test_sources.py` are green **without a weakened assertion**, except the two that pin a defect
(#14a's page-2 params and, if applicable, the partial-sweep contract), each of which is
changed with a comment naming this plan.

---

### WP5 — the curator preset  [Backend Architect / Data Engineer]

**Findings:** #4 (**blocked on D1**), #12 library half (**blocked on D4**), #15.

**Owns:** `sybilkit/src/sybilkit/curator.py`, `sybilkit/tests/test_curator.py`, and — for wave
1 only — the single `largest_operators` assertion in `sybilkit/tests/test_cli.py:210`.

#### WP5.1 — #15: band details that fabricate facts

Two strings, both reproduced. A late-cohort window on a young dataset computes
`range(last_hour - late_cohort_hours + 1, last_hour + 1)` and can print **"joined in hours
-1–0"** — an hour that does not exist. And the early-cohort detail says "the first N addresses
on the list", where N is merely how many of the first-1 000 join indices are **in this
dataset** — on a partial sweep it names a fact about the list that is really a fact about the
sample.

- **Failing-first tests:**
  - `test_the_late_cohort_window_never_names_an_hour_before_zero`
  - `test_the_early_cohort_detail_counts_indices_present_not_addresses_on_the_list`
- **Code:** `start = max(0, last_hour - preset.late_cohort_hours + 1)`; and reword to
  `f"{len(early):,} of the first {cutoff:,} join indices present"`.
- **Mutation:** remove the clamp → the first test reddens on a dataset whose max hour is 1 with
  `late_cohort_hours = 3`.

#### WP5.2 — #4: the clean-list fallback  *(blocked on D1)*

- **First task: run `test_the_clean_list_on_an_empty_result_keeps_everybody` after the change.**
  §1/D1 argues it stays green because the test's "empty" result comes from a real `detect()`
  run and therefore has a populated `analyzed`. If it reddens, stop and escalate — the reading
  was wrong and the ruling changes shape.
- **Failing-first tests:**
  - `test_a_result_that_analyzed_nobody_produces_no_survivors`
  - `test_standing_of_an_unanalyzed_address_is_unknown_not_clean`
  - `test_a_hand_built_result_never_makes_the_clean_list_speak_for_the_unanalyzed`
- **Code:** `analyzed = set(res.analyzed)`, plus a docstring sentence naming the hazard.
- **Mutation:** restore `or set(weights)` → all three redden.

#### WP5.3 — #12 library half: rename the band  *(blocked on D4)*

- **Failing-first tests:**
  - `test_the_linked_groups_band_is_not_named_after_the_credit_line`
  - `test_the_largest_operators_property_is_the_only_thing_the_credit_line_gates`
  - the existing `test_the_segment_key_vocabulary_is_exactly_what_the_docstring_names` moves
    with the code (regex + docstring spellings) — it is the agreement test, not a defect pin.
- **Code:** `_band("linked_groups", "operators", "linked groups", …)`; update `Segment.__doc__`'s
  key vocabulary and `Segments.__doc__`'s prose; update `test_cli.py:210` to
  `"linked_groups"`; update `sybilkit/README.md:125`.
- **Mutation:** rename it back → the vocabulary test reddens naming the old key.
- **Hand-off to WP7** (write it down, do not assume): the new key, the new label string, the
  confirmation that `kind` stays `"operators"` (so the adapter's ordering is untouched), and
  the note that the label got *shorter*, so no maxpane width can grow.

---

### WP6 — the CLI and the below-cap lane  [Backend Architect]  *(wave 2)*

**Owns:** `sybilkit/src/sybilkit/cli.py`, `sybilkit/tests/test_cli.py` (from wave 2 on).
**Depends on:** WP5 (the renamed key) and WP4 (the sources signatures).

Five below-cap items (§5, B1/B2/B3-half/B4/B5), each small, each real:

| item | code | test |
|---|---|---|
| **B1** uncaught `ValueError`/`KeyError` tracebacks, including a live chain answering **zero** | name the specific cause — a `POINTS_PER_ETH()` or `minDeposit()` that reads as `0` is a legitimate reading and an unusable rate, so raise a `CliError` that says so; then widen `main`'s handler to `(ValueError, KeyError, ArithmeticError)` → message + exit 3, leaving genuine bugs to propagate | `test_a_chain_that_answers_zero_points_per_eth_is_a_named_error_not_a_traceback`; `test_an_unexpected_value_error_exits_non_zero_with_a_message` |
| **B2** `_iso()` appends `Z` to a non-UTC offset → `…+02:00Z` | detect a trailing `[+-]HH:MM`, convert through `datetime.fromisoformat(...).astimezone(utc)`; only a naive stamp gets a bare `Z` | `test_a_non_utc_offset_is_converted_rather_than_suffixed_with_z` |
| **B3** (CLI half) negative `--funding-budget` | `type=` a non-negative-int helper in `build_parser` | `test_a_negative_funding_budget_is_rejected_at_the_command_line` |
| **B4** `--max-txs 0` still fetches the whole first block (`if out and …` lets the first group through) | `if cap <= 0: return [], (min(by_block) if by_block else None)` | `test_a_zero_tx_cap_fetches_nothing_and_says_where_it_stopped` |
| **B5** inverted `block_range` provenance when `--from-block` is past head | a from-block past the head is a user error worth naming: `CliError` quoting both numbers, rather than a provenance header whose `to < from` | `test_a_from_block_past_the_head_is_a_named_error_not_an_inverted_range` |

**Mutation for each:** revert the single guard and watch the named test redden.
**Also:** if WP4 implemented #11(iii), the CLI's `coverage` block should record a partial log
sweep (`"covered_to"`), so an artifact never claims a range it did not read.

---

### WP7 — the maxpane follow-through  [Backend Architect + Frontend Developer]  *(wave 2)*

**Owns:** `maxpane_dashboard/data/curator_clusters.py`,
`maxpane_dashboard/widgets/curator/segments.py` (docstring only),
`tests/data/test_curator_clusters.py`, `tests/data/test_curator_manager.py`,
`tests/data/test_curator_sybil_data.py`, `tests/widgets/test_curator_widgets.py`,
`tests/screens/test_curator_screen.py`, `tests/fixtures/curator/sybil/segment_rows_worst.json`.
**Depends on:** WP5 (D4 rename) and WP4 (D6 cursor, #3/#10/#11 sweep behaviour).
**Reads, never edits:** `sybilkit/`, `data/curator_manager.py`'s siblings outside the adapter,
`analytics/curator_signals.py`.

#### WP7.1 — #12 consumer half: the SEGMENTS rename

No adapter **code** change is expected (`pattern_language()` passes the label through and the
ordering keys on `kind == "operators"`), which WP7 verifies rather than assumes. What moves:

| file | change |
|---|---|
| `tests/data/test_curator_clusters.py:389` | `assert labels[0] == "linked groups"` |
| `tests/data/test_curator_manager.py:2520` | `row["label"] != "linked groups"` |
| `tests/data/test_curator_sybil_data.py:683-684` | key becomes `"linked groups"`; **the numbers 6 303 and 43.25 stay** — that is the point of choosing rename over filter |
| `tests/widgets/test_curator_widgets.py:3379, 3455` | the composited assertions |
| `tests/screens/test_curator_screen.py:2484` | the composited assertion |
| `tests/fixtures/curator/sybil/segment_rows_worst.json` | the label string |
| `maxpane_dashboard/widgets/curator/segments.py:6, 8` | the docstring example |
| `README.md:76` | the SEGMENTS bullet |

- **New test:** `test_the_segments_panel_never_calls_a_small_group_a_largest_operator`
  (composited, off a fixture with one tiny cluster) — the finding's on-screen consequence, now
  pinned.
- **Width:** re-run the analysis-body sweep in `tests/screens/test_curator_screen.py`. Expect
  **137 unchanged** (`CuratorOperators` binds at 82 columns; the new label is four columns
  shorter than the old one). `CURATOR_FULL_LAYOUT_COLUMNS` (138) and `FULL_LAYOUT_COLUMNS`
  (143) must not move; if either does, stop and report.

#### WP7.2 — #14 cursor plumbing and persisted-payload compatibility

- **Code:** `EnrichmentSweep` gains `funding_cursors: dict[str, dict]`; `state()` gains a
  `"cursors"` key; `fetch_enrichment` reads `prior.get("cursors")` with the same tolerant shape
  as `txs`/`funding`/`pending`/`reasons`/`page_bound` and passes it to `fetch_funding(...,
  cursors=…)`. The cursor rides **inside** the existing `enrichment` dict of `slot_payload`, so
  `SLOT_CLUSTERS`'s own shape is unchanged and `curator_cache.py` needs no version bump.
- **Failing-first tests:**
  - `test_a_slot_payload_written_before_the_cursor_still_loads` (the compat gate — load a
    committed pre-change payload, assert it resumes from page 1 and nothing raises)
  - `test_the_funding_cursor_survives_a_round_trip_through_the_slot_payload`
  - `test_a_page_bounded_address_makes_progress_across_two_sweeps`
  - `test_no_verdict_enters_the_cursor` (the existing no-boolean-verdict scan still passes over
    the enlarged payload)
- **Mutation:** drop `"cursors"` from `state()` → the round-trip test reddens; make the read
  non-tolerant (`prior["cursors"]`) → the compat test reddens.

#### WP7.3 — the sweep-behaviour changes the detached sweep consumes (#3, #10, #11)

The adapter treats `sweep is None` as an outage and anything else as a healthy pass. After
WP4, `fetch_tx_fingerprints` can return a **partial** `TxSweep` where it used to return `None`,
and `fetch_deposits` (which the adapter does not call, but the CLI does) can return a partial
`DepositSweep`. Pin the adapter's reading of the new states:

- `test_a_partial_tx_sweep_is_a_healthy_pass_that_leaves_the_rest_wanted`
- `test_an_outage_still_keeps_the_last_good_rather_than_publishing_an_empty_analysis`
- `test_a_null_items_funding_page_leaves_the_address_pending_not_resolved` (the #5a
  consequence, asserted at the adapter)

#### WP7.4 — the regression watch

Re-run, and report rather than absorb, any movement in:
`tests/fixtures/curator/sybil/adapter_agrees.json`'s agreement test (D2/C and D5/A can both
change which wallets cluster), the twelve analysis keys' degraded matrix, and the
`FORBIDDEN_WORDS` composited tests on all three analysis panels (unchanged strings, but the
scan is cheap insurance after a label rename).

**Done when:** the full maxpane suite is green at ≥ 4 661, the analysis body still measures
137, and no `~/.maxpane/*.json` was written by the run (no new manager, so no `MANAGER_ATTRS`
copy needs growing — confirm with `rg -n MANAGER_ATTRS tests/` that none is stale).

---

### WP8 — the cleanup lane (no behaviour change)  [Data Engineer]  *(wave 3)*

Serialized after waves 1–2 because every file it touches belongs to an earlier WP. **Its gate
is byte-identical detection output on the committed fixtures** — a cleanup that changes a
number is a failed cleanup, and the way to prove it is to snapshot `detect()`'s result on the
labeled subset before and after.

| item | change | test |
|---|---|---|
| `detect()` recomputes `first_rows` ~6× | compute once in `detect`; pass it to the signals through a **new keyword-only `firsts=None`** parameter (additive — maxpane imports `first_rows` and `tier_a_components` directly, so their signatures may only grow) | `test_the_signals_accept_a_precomputed_first_row_map_and_agree_with_deriving_it` |
| `split` re-runs `identical_amount_windows` | pass the windows in, same additive shape | `test_split_and_amounts_walk_one_windowing_pass` |
| `clean_list` re-derives `segments`' folds | share `final_weights`/`credited_totals` via optional parameters | `test_clean_list_and_segments_agree_when_handed_the_same_folds` |
| `Edge.strength` duplicates `Reason.strength` | **defer the refactor**; add the invariant test instead — dropping the field means editing every `Edge(...)` construction in five signal modules for no behaviour change, which is exactly the risk this lane exists to avoid | `test_every_edges_strength_equals_its_reasons_strength` |
| `curator.first_deposits` duplicates `signals.first_rows` | delegate | `test_the_preset_and_the_signals_agree_on_first_deposits` |
| `_Session._last_at` is dead state | remove the slot and its assignment | covered by the existing pacing tests |
| unused `Deposit` import in `gas.py` | done in WP1.2 | — |
| the page-bound doubling is redundant once D6/B lands | **record only**; do not remove in the same pass that adds the cursor | — |

---

### WP9 — verification, ledger and record  [Technical Writer + DevOps]  *(wave 4)*

**Owns:** `README.md`, `sybilkit/README.md`, `CLAUDE.md` (only if a documented behaviour
changed), this plan's close-out section, and the memory update. **Creates no source.**

1. **`cd /Library/Vibes/autopull/sybilkit && /Library/Vibes/autopull/.venv/bin/python -m pytest -q`**
   — green, ≥ 289 passed + 1 xfail + every new test, **0 skipped**. A skip means the wrong
   interpreter and the run does not count.
2. **`/Library/Vibes/autopull/.venv/bin/python -m pytest -q`** at the repo root — green,
   ≥ 4 661.
3. **`cd maxpane && cargo test`** — 443, untouched (sanity: no WP should have gone near it).
4. **Re-run the review's reproductions as committed tests.** Produce the finding → test table
   (§8) and assert it is complete: every one of the 15 findings names at least one test that
   exists, and every mutation was observed red. A finding with no test is not closed.
5. **Both distributions build.** `python -m build sybilkit/` and, at the root, `python -m build`
   — and re-verify the root wheel carries **zero** `sybilkit` entries and no `sybilkit` in
   `Requires-Dist` (the packaging story in `CLAUDE.md` depends on it).
6. **Structural gates re-run:** the no-network AST scans in both suites;
   `rg -n "import sybilkit|from sybilkit" maxpane_dashboard/` returns exactly
   `data/curator_clusters.py`; `git diff main -- maxpane_dashboard/analytics/curator_signals.py`
   is empty; the stdlib-only core proof (`python -I -S` gate).
7. **Width pins:** `FULL_LAYOUT_COLUMNS` 143, `CURATOR_FULL_LAYOUT_COLUMNS` 138, analysis body
   137 — all unmoved, or the movement is explained in the close-out.
8. **Docs:** update `sybilkit/README.md` for any behaviour that changed (the `linked_groups`
   key, the funding coverage note under D2, the partial-sweep contract under #11(iii)), and
   `README.md:76` for the SEGMENTS label. Touch `CLAUDE.md` only if a *documented* behaviour
   moved.
9. **Record:** update the memory file so its headline stops saying "NOTHING FIXED YET", with a
   per-finding landed/deferred table and the rulings actually taken.
10. **Do not touch `tests/fixtures/curator/captures/live/`.**

**Merging, tagging and publishing remain the user's decision.** WP9 ends with a green tree and
a recommendation, not with a merge, a push or a `v*` tag. Note for the recommendation: the
review's own judgement is that these should land **before the first manual PyPI publish of
sybilkit**, because four of them can fabricate or erase an evidence family and the library's
output judges real people's wallets.

---

## 4. Below-the-cap ledger — where each item landed

Nothing is silently dropped. Seven items, all confirmed, all smaller.

| # | item | WP | priority |
|---|---|---|---|
| B1 | CLI uncaught `ValueError`/`KeyError` tracebacks, incl. a live chain answering zero | WP6 | wave 2 |
| B2 | `_iso()` appends `Z` to a non-UTC offset → `…+02:00Z` in provenance | WP6 | wave 2 |
| B3 | negative `--funding-budget` inverts the cap via slicing | WP4 (clamp) + WP6 (argparse) | waves 1–2 |
| B4 | `--max-txs 0` still fetches the whole first block | WP6 | wave 2 |
| B5 | inverted `block_range` provenance when `--from-block` is past head | WP6 | wave 2 |
| B6 | 429 rotates with no backoff | WP4 | wave 1 |
| B7 | string-echoed batch ids are dropped on re-alignment | WP4 | wave 1 |

**Nothing here is deferred.** They are lower priority only in the sense that they ride in waves
1–2 behind the ranked findings inside the same work packages.

## 5. Cleanup-lane ledger

All seven items are in WP8 (§3), one of them (`Edge.strength`) **deliberately deferred to an
invariant test** rather than refactored, with the reason recorded. The page-bound doubling's
redundancy after D6/B is recorded, not acted on.

---

## 6. Cross-distribution impact — planned, not discovered

| trigger | sybilkit side | maxpane side | maxpane tests that move |
|---|---|---|---|
| **#12 / D4** rename `largest_operators` → `linked_groups` | `curator.py` band + two docstrings; `test_curator.py` vocabulary regex; `test_cli.py:210`; `sybilkit/README.md:125` | **no adapter code change expected** (label passes through `pattern_language`, ordering keys on `kind`) — verify, don't assume | `tests/data/test_curator_clusters.py:389`; `tests/data/test_curator_manager.py:2520`; `tests/data/test_curator_sybil_data.py:683-684`; `tests/widgets/test_curator_widgets.py:3379,3455`; `tests/screens/test_curator_screen.py:2484`; fixture `tests/fixtures/curator/sybil/segment_rows_worst.json`; `README.md:76` |
| **#14 / D6** per-address funding cursor | `FundingSweep.page_cursors` (defaulted, last), `fetch_funding(cursors=…)` | `EnrichmentSweep.funding_cursors`, `state()["cursors"]`, tolerant read in `fetch_enrichment`; cursor rides inside the existing `enrichment` dict so `SLOT_CLUSTERS`'s shape is unchanged | new: `test_a_slot_payload_written_before_the_cursor_still_loads`, `test_the_funding_cursor_survives_a_round_trip_through_the_slot_payload`, `test_a_page_bounded_address_makes_progress_across_two_sweeps` (all in `tests/data/test_curator_clusters.py`) |
| **#3 / #10 / #11** sources recovery | partial sweeps where `None` used to be returned; rotation on unreadable bodies | the detached sweep's `is None` reading stays correct; partial passes now merge | new: `test_a_partial_tx_sweep_is_a_healthy_pass_that_leaves_the_rest_wanted`, `test_an_outage_still_keeps_the_last_good_rather_than_publishing_an_empty_analysis` |
| **#5a** `{'items': null}` | pending instead of a resolved `None`-funder row | more pendings, fewer frozen rows | new: `test_a_null_items_funding_page_leaves_the_address_pending_not_resolved` |
| **#5b / D2-C** and **#13 / D5-A** | **detection changes** | the flagged set on a fixture can move | watch: `tests/fixtures/curator/sybil/adapter_agrees.json`'s agreement test and `sybilkit/tests/test_bench.py` — **report movement, never retune** |
| **WP8** shared-helper hoists | additive keyword-only parameters only | maxpane imports `sybilkit.signals.first_rows` and `tier_a_components` **directly** — their signatures may only grow | none expected; WP8's gate is byte-identical detection output |

---

## 7. Finding → work package → test map (WP9 asserts this table is complete)

| # | finding | WP | decision | primary new test(s) |
|---|---|---|---|---|
| 1 | funding self-edge fabricates a family | WP1.1 | — | `test_a_self_funding_row_never_creates_the_funding_family` |
| 2 | gas fingerprints not deduped by tx | WP1.2 | — | `test_a_group_whose_first_deposits_share_one_transaction_yields_no_gas_edge` |
| 3 | `rpc_call` accepts any unreadable 200 | WP4.1 | — | `test_a_two_hundred_html_body_rotates_to_the_next_endpoint` |
| 4 | clean-list "everybody clean" fallback | WP5.2 | **D1** | `test_a_result_that_analyzed_nobody_produces_no_survivors` |
| 5a | `{'items': null}` freezes a resolved row | WP4.4 | — | `test_a_page_whose_items_are_null_is_unreadable_not_a_finished_walk` |
| 5b | internal-transfer funding blindness | WP4.7 | **D2** | `test_a_wallet_funded_by_an_internal_transfer_resolves_its_funder` |
| 5c | module docstring teaches the old behaviour | WP4.4 | — | `test_the_funding_docstrings_agree_that_a_pending_address_gets_no_row` |
| 6 | `last_weight` trusts deposit order | WP3 | — | `test_a_newest_first_dataset_scores_the_same_points_as_a_chain_ordered_one` |
| 7 | conflicting duplicates deduped first-wins | WP2.3 + WP4.8 | **D3** | `test_a_shuffled_producer_and_an_ordered_one_build_the_same_dataset` |
| 8 | non-numeric `ts` drops the whole row | WP2.1 | — | `test_a_whole_population_with_iso_timestamps_still_builds_a_dataset` |
| 9 | pre-built fast paths skip normalization | WP2.2 | — | `test_the_prebuilt_and_mapping_paths_build_equal_datasets` |
| 10 | malformed later batch discards reads; code tiebreak | WP4.3 | — | `test_a_malformed_hash_in_a_later_batch_keeps_the_fingerprints_already_read` |
| 11 | range errors shrink but never rotate | WP4.2 | — | `test_the_second_endpoint_receives_a_request_before_the_sweep_fails` |
| 12 | `largest_operators` band vs property | WP5.3 + WP7.1 | **D4** | `test_the_segments_panel_never_calls_a_small_group_a_largest_operator` |
| 13 | near rule at the exempt minimum | WP1.3 | **D5** | `test_which_of_two_byte_equal_minimum_wallets_links_is_not_decided_by_address_order` |
| 14a | funding filter dropped from page 2 | WP4.5 | — | `test_every_funding_page_after_the_first_still_carries_the_incoming_filter` |
| 14b | no per-address page cursor | WP4.6 + WP7.2 | **D6** | `test_a_page_bounded_address_resumes_from_its_own_cursor_next_pass` |
| 15 | band details fabricate facts at the edges | WP5.1 | — | `test_the_late_cohort_window_never_names_an_hour_before_zero` |

---

## 8. Risks and unknowns

1. **A fix moves the benchmark.** D2/C and D5/A both change *detection*, and #9 can add funding
   edges that casing used to kill. `sybilkit/tests/test_bench.py` carries a precision floor, a
   median-gap ceiling and a strict xfail, and maxpane's `adapter_agrees.json` pins the two
   distributions' agreement. **Rule: a WP that moves either reports it and stops. Retuning a
   gate so a fix passes is the one thing this plan forbids outright.** If the movement is an
   improvement, WP9 re-baselines it deliberately and records the before/after.
2. **The review's central claim — that all 15 live on paths the committed fixtures never walk —
   predicts that fixing them moves no existing test** except the ones that pin a defect (#14a's
   page-2 params, possibly the #11(iii) contract) and the ones that move with a rename (#12).
   If a wave-1 WP reddens something else, that is new information: report it before fixing.
3. **D1's pinned test may not be pinned.** §1/D1 argues from the code that
   `test_the_clean_list_on_an_empty_result_keeps_everybody` stays green under the recommended
   fix. That is a reading of two files, not a measurement. WP5.2's first action is to measure
   it.
4. **WP4 is large.** Five findings, three below-cap items and one test file. It is the critical
   path and the likeliest place for a schedule slip. Mitigation: it is task-ordered so each
   task commits independently, and WP4.1/WP4.2 (the two that can turn an outage into a false
   "no history") are first.
5. **`test_cli.py`'s two owners.** Mitigated by wave separation and by naming the single line
   WP5 may touch. If that feels too fine, fold WP6 into WP5's agent.
6. **#11(iii) relaxes a documented contract** ("`None`, never a partial"). It is safe today
   because maxpane never calls `fetch_deposits`, but it is a public API of a distribution about
   to be published. Recommended, flagged, and reversible — implement (i)+(ii) alone if the user
   prefers.
7. **The gas reason string.** Its number changes meaning under #2. Keeping the string's length
   avoids a cross-distribution width re-pin; if the user wants the wording to change, WP7
   re-sweeps the OPERATORS panel.
8. **Uncommitted user work in the tree.** The status at planning time shows untracked live
   captures under `tests/fixtures/curator/captures/live/`. No WP touches them, and no WP may
   `git checkout --` or `git add -A`.
9. **Version metadata.** Nothing here bumps a version. If the user later bumps
   `pyproject.toml`, re-run `pip install -e .` before trusting `--version` or the status bar —
   an editable install writes that metadata once, at install time.

---

## Recommended approach

Answer the six rulings first (§1) — they are cheap to answer and they unblock four of the nine
work packages. Then run five agents in parallel across the five natural file boundaries of the
library (signals, model, cluster, sources, curator preset), each fixing its findings TDD-first
with a recorded mutation. Follow with two parallel agents for the two consumers (the CLI, and
maxpane's adapter plus its SEGMENTS surface), then serialize the no-behaviour-change cleanup,
then verify both distributions and hand the merge decision back to the user.

## Why this approach

It maximises parallelism without ever putting two agents in one file — the sources findings are
deliberately kept in one work package precisely *because* `test_sources.py` is one file, and the
one file with two owners has them separated by a wave and limited to a single named line. It
puts every decision in front of the work instead of inside it, so an agent never silently
chooses a design. It keeps the review's reproductions as the tests, so the fixes cannot be
weaker than the findings. And it treats detection movement as a finding rather than as
something to tune away, which is the only way the benchmark gate keeps meaning anything.

## Risks and unknowns

The nine items in §8 — most importantly that D2/C and D5/A change detection and therefore put
the benchmark gate and the two distributions' agreement fixture in play, and that D1's
"pinned" test may not actually pin what the review record says it does. Neither blocks
starting: WP1.1/WP1.2, all of WP2 except #7, WP3, WP4.1–WP4.5 and WP5.1 need no ruling at all.

## Implementation steps

Waves 0 → 4 as scheduled in §2, with the per-WP task lists in §3. Gate at each wave boundary on
the criteria in the §2 table: both suites green, every mutation observed red, the benchmark
either unmoved or escalated.

## Validation plan

Per-WP TDD plus a recorded prove-it-bites for every fix; a finding → test completeness table
(§7) asserted by WP9; the full sybilkit suite (≥ 289 + 1 xfail, **0 skipped**) and the full
maxpane suite (≥ 4 661) green; `cargo test` green; both distributions building with the root
wheel still carrying no `sybilkit`; the structural keyless/no-network/one-importer gates
re-run; and the three width pins (143 / 138 / 137) unmoved. Merging, tagging and publishing
are explicitly out of scope and remain the user's call.

---

# 10. Close-out — WP9, 2026-08-18

**Status: every one of the 15 confirmed findings and all seven below-cap items landed.**
Nothing on the ranked list is deferred. Four items were *deliberately* not acted on and each
one is named in §10.5 with the reason and, where one exists, the pin that replaces it.

This section is the durable record. It was written after the runs below, not before them, and
every number in it is a measurement rather than an expectation.

**Written twice.** The first WP9 agent died on a server error part-way through, leaving an
uncommitted `sybilkit/README.md` and this section in draft. The second WP9 re-ran every gate
from scratch rather than inheriting a number, and **re-derived §10.2 by mutation** instead of
by reading the earlier table: for each finding the defect was reintroduced in the source, the
whole suite was run, and the tests that actually reddened were recorded. Several claims in the
draft did not survive that, and each is corrected in place rather than quietly dropped: the
R3.6 pin column named two tests that stay green under the defect (§10.3, §10.4); the flat "no
`sybilkit` in METADATA" was imprecise (§10.1); and four statements in the uncommitted
`sybilkit/README.md` draft were wrong or incomplete against the source (§10.6). The two
documentation items the draft left **open** — O1 and O2 — are closed by this pass rather than
handed on.

## 10.1 Measured state

**59** commits of code and tests after the review baseline `33eb8b4`, across two distributions —
counted with `git rev-list --count 33eb8b4..fa29dfa`, `fa29dfa` being the last of them — plus
this close-out's own documentation commits on top of that. The branch total is deliberately
*not* quoted here: every attempt at it so far has been one out, because the commit stating the
number is itself one of the commits being counted. Run `git rev-list --count 33eb8b4..HEAD`.

| gate | baseline | measured 2026-08-18 | verdict |
|---|---|---|---|
| `cd sybilkit && .venv/bin/python -m pytest -q` | 289 passed + 1 xfail, 0 skipped | **422 passed, 1 xfailed, 0 skipped** in 13.71 s / 14.65 s (run twice, before and after the doc commits) | green, +133 |
| `.venv/bin/python -m pytest -q` (root) | 4 661 passed | **4 671 passed**, 6 warnings, in 359.01 s | green, +10 |
| `cd maxpane && cargo test` | 443 | **443** = 210 + 216 + 17 across three binaries, plus 0 doc-tests; 0 failed | green, untouched |
| `python -m build sybilkit/` | — | `sybilkit-0.0.1.tar.gz` + `.whl`, **isolated** env (network was available; no `--no-isolation` needed) | built |
| `python -m build` (root) | — | `maxpane-0.7.1.tar.gz` + `.whl`, isolated env | built |
| root wheel `sybilkit` entries | 0 | **0** of 294 entries — and 0 of 294 in the sdist too | clean |
| root wheel `Requires-Dist` | `httpx`, `pydantic`, `textual` | **unchanged**; no `sybilkit` | clean |
| root wheel `METADATA` mentions `sybilkit` | — | **yes, and correctly**: nine lines, all inside the long-description body that is `README.md`'s own "sybilkit — the analysis library, on its own" section. Prose, not a dependency and not a packaged file. The earlier draft's flat "no `sybilkit` in METADATA" was imprecise | honest |
| `sybilkit/tests/test_bench.py` | — | `git diff 33eb8b4` **empty**; 9 passed, 1 xfailed | unmoved |
| `tests/fixtures/curator/sybil/adapter_agrees.json` | — | `git diff 33eb8b4` **empty** | unmoved |
| `FULL_LAYOUT_COLUMNS` | 143 | **143** | unmoved |
| `CURATOR_FULL_LAYOUT_COLUMNS` | 138 | **138** | unmoved |
| analysis body | 137 | **137** | unmoved |

**Zero skips on the library run**, which is the interpreter proof: a `sybilkit` suite that skips
has silently dropped its fetcher tests, and this build's biggest lane is the fetchers.

**The two detection-changing rulings moved nothing measurable.** D2-C (internal-transfer
funding) and D5-A (the exempt-minimum near pass) were both flagged in §8 risk 1 as live threats
to the benchmark gate and to the two distributions' agreement fixture. Both files are
byte-identical to the baseline and both gating tests are green, so there is nothing to
re-baseline and nothing to report as movement. The review's central claim in §8 risk 2 — that
all 15 defects live on paths the committed fixtures never walk — held.

### Width pins, swept rather than read

Constants are not evidence; the sweeps are. Every pin below is a **render of the real screen at
a width, in both directions** — clean at N, `‹ widen` at N−1 — and not a constant read back. 18
tests, run by name, all green in 44.87 s:

- **143, the app-wide number.** `tests/screens/test_surf_screen.py::test_the_measured_full_layout_width_is_exactly_the_tight_one`
  measures the binding dashboard's own requirement tight both ways;
  `…::test_surf_fits_inside_the_documented_app_width` and
  `…::test_the_documented_width_still_covers_the_measured_one` tie it to
  `__main__.FULL_LAYOUT_COLUMNS` and to the README's `≥ 143`.
- **138, curator's own.** `test_the_measured_width_clears_every_marker` (0 markers at 138),
  `…_is_tight_not_padded` (> 0 at 137), `…_holds_at_a_short_terminal_too` (both assertions at
  every swept height), `test_the_width_requirement_does_not_move_with_the_terminal_height`,
  `test_the_widest_phase_is_the_one_measured` (138 == the max over the swept phases),
  `test_the_binding_panel_is_the_signal_rail` — still bound by `CuratorSignals`.
- **137, the `f` body.** `test_the_analysis_view_clears_the_measured_width`,
  `test_the_analysis_body_clears_one_column_inside_the_screens_pin` (tight in **both**
  directions: clear at 137, `‹ widen` at 136, at both heights),
  `test_the_analysis_binding_panel_is_the_operators_table` (the marked-panel set is exactly
  `{CuratorOperators}`), `test_the_analysis_body_fits_whole_at_its_measured_height`.
- `test_the_wallet_view_clears_at_the_pinned_full_layout_width` — the `y` body.
- `tests/test_curator_registration.py` width family — `CURATOR_FULL_LAYOUT_COLUMNS ≤
  FULL_LAYOUT_COLUMNS`, CLAUDE.md still states curator's measured 138, and the README still
  documents the dashboard.

Re-run after this close-out's own edits, since one of them changes a rendered module's docstring
and one changes a README two of those tests read.

The D4 rename could only ever shrink a column ("linked groups" is 13 to "largest operators"'
17) and `CuratorSegments` is not the binder, so the direction was known; it was swept anyway.

### Structural gates

| gate | result |
|---|---|
| `rg -n "import sybilkit\|from sybilkit" maxpane_dashboard/` | exactly one file, `data/curator_clusters.py` (10 import lines) |
| `git diff main -- maxpane_dashboard/analytics/curator_signals.py` | **0 bytes** |
| `tests/data/test_curator_clusters.py::test_only_curator_clusters_imports_sybilkit` | passed |
| `tests/data/test_curator_clusters.py::test_curator_signals_never_imports_sybilkit` | passed |
| `sybilkit/tests/test_purity.py` (stdlib-only core) | 2 passed |
| `sybilkit/tests/test_sources.py::test_no_test_file_in_the_suite_builds_a_client_without_a_transport` | passed |
| `tests/test_curator_registration.py::test_no_curator_test_can_touch_the_network` | passed |
| `tests/test_fwa_guardrails.py::test_no_network_in_any_fwa_test` | passed |
| `tests/test_capture_curator_state.py::test_nothing_here_reaches_the_network` | passed |
| the two `_replay_rank` copies | `inspect.getsource` identical, 1 607 chars each; pinned by `test_the_two_copies_of_the_replay_rule_are_character_identical`, and that pin was **watched go red** (mutating `model.py`'s rank alone reddens it) |
| additive-only cross-distribution signatures | verified by introspection — every new parameter is keyword-only with a default (`cursors=`, `firsts=`, `windows=`, `singles=`, `weights=`, `credits=`, `groups=`); `signals.first_rows(ds)` unchanged |
| `git diff 33eb8b4 -- sybilkit/tests/test_bench.py tests/fixtures/curator/sybil/adapter_agrees.json` | **empty** — the benchmark gate and the two distributions' agreement fixture are byte-unchanged from the review baseline |
| `tests/fixtures/curator/captures/live/` | untouched, still untracked |

## 10.2 Finding → work package → committed test

Every row names a test that **exists and was run by name**: 91 collected library ids (84 node
ids, 7 of them parametrised) in 2.81 s and 7 maxpane ids in 0.50 s, all passing. A finding whose
test could not be run by name would be recorded here as **not closed**; there are none.

**And every row names the test that actually bites.** The second WP9 pass did not inherit the
first one's table — it reintroduced each defect in the source, ran the whole suite, and recorded
which tests reddened. **58 distinct mutations across 71 suite runs** — 13 scenarios were measured
twice, because the harness's first version overwrote its own backup when one scenario edited a
file twice and left three lines of it behind. That leftover was caught by `diff -r` against a
pristine copy of `sybilkit/src`, not by a green suite (it made two unrelated tests fail in every
later run, which is what gave it away), the harness was fixed, and every affected scenario was
re-measured. `diff -r` after the last mutation is identical and `git status` shows no source file
touched. Where the plan's §7 headline is **not** the test carrying the signal, the row says so
rather than reading tidily. An honest table that admits a weak row is worth more than one that
hides it.

| # | finding | WP · ruling | the mutation, and what it reddened | commit |
|---|---|---|---|---|
| 1 | funding self-edge fabricates a family | WP1.1 | **drop the peel-chain self-funder guard** → RED `test_a_self_funding_row_never_creates_the_funding_family` (the §7 headline), `test_a_hand_edited_self_funding_row_cannot_lift_a_one_family_component`, `test_a_self_funding_row_never_joins_a_shared_funder_hub`. **Drop the hub-fold guard instead** → RED `…_never_joins_a_shared_funder_hub` and `test_the_self_funder_guard_does_not_depend_on_the_funders_casing`. Both halves are pinned, by different tests; the headline bites on the peel half only | `f4171b7`, `5d04a89` |
| 2 | gas fingerprints not deduped by tx | WP1.2 | **key the fingerprint map per member instead of per tx hash** → RED `test_a_group_whose_first_deposits_share_one_transaction_yields_no_gas_edge` (headline), `test_the_uniformity_count_is_distinct_transactions_not_members`, `test_a_router_batched_wave_cannot_reach_the_two_axis_strength`. A second mutation (gate on `len(covered)` rather than `len(by_hash)`) reddens the headline and the router one again. `test_a_group_with_enough_distinct_transactions_still_fires` is the *positive* control — it stays green here by design and reddens when a fix over-tightens (measured: it goes red under the WP8 fold-divergence mutation) | `92bcdb3` |
| 3 | `rpc_call` accepts any unreadable 200 | WP4.1 | **return the unreadable body instead of rotating** → RED `test_a_two_hundred_html_body_rotates_to_the_next_endpoint` (headline), `test_a_two_hundred_bare_array_body_is_not_a_completed_sweep`, `test_an_unreadable_body_from_every_endpoint_degrades_to_none_not_an_empty_history` | `e961af3` |
| 4 | clean-list "everybody clean" fallback | WP5.2 · **D1-B** | **restore `or set(weights)`** → RED `test_a_result_that_analyzed_nobody_produces_no_survivors` (headline), `test_standing_of_an_unanalyzed_address_is_unknown_not_clean`, `test_a_hand_built_result_never_makes_the_clean_list_speak_for_the_unanalyzed`. `test_the_clean_list_on_an_empty_result_keeps_everybody` stayed green through the real fix, exactly as §1/D1 predicted from the code | `4f4e163`, `26fcbed` |
| 5a | `{'items': null}` freezes a resolved row | WP4.4 | **`items = body.get("items") or []` behind an `"items" in body` guard** (the pre-fix shape) → RED `test_a_page_whose_items_are_null_is_unreadable_not_a_finished_walk` (headline), `test_a_null_items_page_never_freezes_a_none_funder_into_a_resolved_row` | `4819bc3` |
| 5b | internal-transfer funding blindness | WP4.7 · **D2-C** | **return `_COMPLETE` after the external walk instead of walking internals** → RED `test_a_wallet_funded_by_an_internal_transfer_resolves_its_funder` (headline), `test_the_internal_walk_only_runs_when_the_normal_walk_found_nothing`, `test_a_disperse_style_fan_out_produces_one_shared_funder_across_the_batch`, `test_a_walk_bounded_inside_the_internal_history_resumes_there` | `469b4d0`, `2d319ea` |
| 5c | module docstring teaches the old behaviour | WP4.4 | **rewrite the module docstring's "no row at all"** → RED `test_the_funding_docstrings_agree_that_a_pending_address_gets_no_row`; **rewrite `FundingSweep`'s "a pending address has no row"** → RED the same test. *Weakness, stated:* the test reads only those two docstrings, so `fetch_funding`'s own docstring is unpinned — mutating it reddens nothing | `4819bc3` |
| 6 | `last_weight` trusts deposit order | WP3 | **fold the deposits unsorted** → RED `test_a_newest_first_dataset_scores_the_same_points_as_a_chain_ordered_one` (headline), `test_a_clusters_points_do_not_depend_on_the_deposit_order`, `test_total_points_agrees_with_the_curator_preset_on_a_hand_built_dataset`, `test_a_same_block_ladder_cluster_scores_the_same_points_in_any_order`, `test_the_final_weight_fold_breaks_a_same_block_tie_by_log_index` | `c3a2854`, `c1aed77` |
| 7a | conflicting duplicates, `model.py` | WP2.3 · **D3-B** | **`parsed.setdefault(key, dep)`** → RED 9, including `test_a_shuffled_producer_and_an_ordered_one_build_the_same_dataset` (headline), `test_a_reorg_replay_keeps_the_row_at_the_higher_block`, `test_the_higher_block_wins_even_when_the_other_row_scores_higher`, and all three arrival-order tests. `test_two_byte_identical_duplicates_still_collapse_to_one_row` is the control and stays green | `4f5539c`, `97f5fc7` |
| 7b | conflicting duplicates, `sources/logs.py` | WP4.8 · **D3-B** | **`deposits.setdefault(key, dep)`** → RED `test_a_replayed_log_row_is_deduped_to_the_higher_block`, `test_the_log_sweep_and_from_events_agree_on_a_conflicting_duplicate`. *Weakness, stated:* `test_the_two_copies_of_the_replay_rule_are_character_identical` does **not** bite on this — it compares the two functions' source text, so it pins "one rule, two copies" and nothing about dedup behaviour. Its own bite was measured separately: truncating `model.py`'s rank reddens it | `1a4c426`, `53bbe8b` |
| 8 | non-numeric `ts` drops the whole row | WP2.1 | **raise `_Malformed` from the `ts` coercer** → RED `test_a_whole_population_with_iso_timestamps_still_builds_a_dataset` (headline), `test_an_iso_string_timestamp_degrades_the_label_and_keeps_the_deposit`, `test_an_unrepresentable_timestamp_degrades_the_label_too`, `test_a_log_row_whose_timestamp_cannot_be_a_float_degrades_the_label_not_the_row`. `test_a_malformed_amount_still_drops_the_row` is the control — a *signal* word still drops its row — and stays green | `0e31753`, `1aa6561` |
| 9 | pre-built fast paths skip normalization | WP2.2 | **re-add both fast paths** (`isinstance(row, Tx)` / `isinstance(row, Funding)` → store verbatim) → RED `test_the_prebuilt_and_mapping_paths_build_equal_datasets` (headline), `test_a_checksummed_funder_on_a_prebuilt_row_is_lowercased_like_a_mapping_row`, `test_a_prebuilt_tx_with_a_float_fee_is_dropped_not_admitted` | `5b0ff55` |
| 10 | malformed later batch discards reads; code tiebreak | WP4.3 | **`return None` on a malformed batch** → RED `test_a_malformed_hash_in_a_later_batch_keeps_the_fingerprints_already_read` (headline), `test_the_pending_cursor_after_a_malformed_batch_names_every_unread_hash`. The three adjacent pins were bitten separately: dropping the `read == 0` guard → RED `test_a_malformed_hash_in_the_first_batch_is_still_none` (+3); dropping `"invalid params"` from the malformed vocabulary → RED `test_a_genuine_invalid_params_message_short_circuits_without_rotating`; removing the no-message code fallback **or** re-classifying by code → RED `test_an_error_object_with_no_message_falls_back_to_the_code_and_says_so` | `65cb602`, `e0090f6` |
| 11 | range errors shrink but never rotate | WP4.2 | **(i) never rotate** (`return rows, covered` in place of `pool.pop(0)`) → RED `test_the_second_endpoint_receives_a_request_before_the_sweep_fails` (headline), `test_a_throttle_message_that_looks_like_a_range_cap_still_rotates_the_pool`, `test_an_endpoint_that_refuses_every_wide_span_is_dropped_rather_than_retried`. **(ii) no span recovery** → RED `test_a_narrowed_span_recovers_after_a_run_of_clean_chunks` (+2). **(iii) discard the partial** (`covered < head` → `None`) → RED `test_a_sweep_that_read_some_chunks_returns_how_far_it_got_not_none`, `test_a_partial_log_sweep_states_the_extent_it_covered_not_the_one_it_asked_for`. `test_a_sweep_that_read_nothing_is_still_none` is the control for (iii) | `98bba1c`, `1daaef9`, `38efaf8` |
| 12 | `largest_operators` band vs property | WP5.3 + WP7.1 · **D4-A** | **rename the band back to `largest_operators` / "largest operators"** → RED, in the library, `test_the_linked_groups_band_is_not_named_after_the_credit_line`, `test_the_segment_key_vocabulary_is_exactly_what_the_docstring_names`, `test_segments_prints_the_operators_and_the_bands`; and, **through the distribution boundary with no maxpane change at all**, `tests/widgets/test_curator_widgets.py::test_the_segments_panel_never_calls_a_small_group_a_largest_operator` (the §7 headline) and `…::test_the_segment_rows_lead_with_the_operators_and_end_with_the_hours` | `caf7b76`, `ceffe02`, `d695e4a` |
| 13 | near rule at the exempt minimum | WP1.3 · **D5-A** | **stop excluding exempt rows from the near pass** → RED `test_a_near_edge_at_the_exempt_minimum_is_never_emitted` **and** `test_which_of_two_byte_equal_minimum_wallets_links_is_not_decided_by_address_order` (the §7 headline — it does carry signal). `test_a_near_edge_above_the_exempt_minimum_still_fires` and `test_which_member_of_a_byte_equal_run_carries_the_near_edge_changes_nothing` are the controls for the *scope* of D5-A and stay green | `134873b`, `b4ae077` |
| 14a | funding filter dropped from page 2 | WP4.5 | **`query = dict(nxt)`** (the cursor without our filter) → RED `test_every_funding_page_after_the_first_still_carries_the_incoming_filter` (headline), `test_a_sweep_without_cursors_still_walks_from_page_one` | `9af7cb1`, `32871ba` |
| 14b | no per-address page cursor | WP4.6 + WP7.2 · **D6-B** | **ignore the persisted cursor** (`_resume_from(None)`) → RED, in the library, `test_a_page_bounded_address_resumes_from_its_own_cursor_next_pass` (headline), `test_a_resumed_walk_keeps_the_oldest_funder_found_before_the_bound`, `test_a_walk_bounded_inside_the_internal_history_resumes_there`, `test_a_hand_edited_cursor_is_re_stamped_with_the_incoming_filter`; and in maxpane `test_a_page_bounded_address_makes_progress_across_two_sweeps`, `test_the_funding_cursor_survives_a_round_trip_through_the_slot_payload`. **Drop the cursor from the persisted slot instead** → RED those two plus `test_an_outage_still_keeps_the_last_good_rather_than_publishing_an_empty_analysis`. **Read the slot key intolerantly** (`prior["cursors"]`) → RED `test_a_slot_payload_written_before_the_cursor_still_loads` (+9) | `2da4bae`, `11359d0`, `aa217a3` |
| 15 | band details fabricate facts at the edges | WP5.1 | **drop the `max(0, …)` floor** → RED `test_the_late_cohort_window_never_names_an_hour_before_zero` (headline), `test_a_dataset_whose_only_hour_is_zero_reads_as_one_hour_not_a_range`. **Reword the early-cohort detail to "addresses on the list"** → RED `test_the_early_cohort_detail_counts_indices_present_not_addresses_on_the_list` | `ca3499c`, `4652cf4` |

**Nothing on the ranked list is unclosed**, and no row rests on a test that carries no signal.
Three carry a stated qualification (5c's unpinned third docstring, 7b's character-identity test,
and #1's split across two guards) and they are written into the rows above rather than into a
footnote.

### The five rulings taken during the build, bitten too

| ruling | mutation | what reddened |
|---|---|---|
| **R3.7** — the amended *total* replay rank | truncate the rank back to the seven numeric words | `test_two_rows_differing_only_in_contributor_are_not_settled_by_arrival`, `…_only_in_ts_…`, `test_two_rows_differing_only_in_a_nan_ts_are_not_settled_by_arrival`, `test_a_readable_ts_outranks_an_unreadable_one_at_the_epoch`, `test_a_sweep_carrying_an_unreadable_timestamp_builds_the_same_dataset_either_way`, `test_the_log_sweep_and_from_events_agree_on_a_conflicting_duplicate`, **and** `test_the_two_copies_of_the_replay_rule_are_character_identical` — which is where that test earns its place |
| **R3.7b** — NaN/inf handled in the coercer, not the rank | let a non-finite `ts` through the coercer | `test_a_nan_timestamp_degrades_the_label_and_keeps_the_deposit`, `test_two_rows_differing_only_in_a_nan_ts_are_not_settled_by_arrival`, `test_an_unrepresentable_timestamp_degrades_the_label_too`, `test_a_sweep_carrying_an_unreadable_timestamp_builds_the_same_dataset_either_way` |
| **R3.6** — the conservative shrinks reset stays inside the full-span guard | hoist `shrinks = 0` out of `if span == full_span:` | **exactly one test**: `test_an_endpoint_that_refuses_every_wide_span_is_dropped_rather_than_retried`. `test_a_second_dense_region_costs_a_shrink_and_not_the_endpoint` stays **green** — see §10.4; the first draft of §10.3 named it as the placement pin and it is not one |
| **R3.8** — an empty-string funder is unresolved, not a measurement | accept any completed walk's `funder` verbatim | `test_a_funder_that_is_not_an_address_leaves_the_address_unresolved` (all three ids: `empty`, `short`, `word`). Adopting an unreadable best-so-far in `_resume_from` instead → `test_a_hand_edited_cursor_never_carries_an_unreadable_best_so_far` |
| **R3.9** — a container guard on every persisted read | remove `_persisted_map`'s `isinstance` → `test_every_persisted_enrichment_map_survives_a_hand_edited_cache_file`; remove `_persisted_addresses`' → `test_a_hand_edited_pending_list_is_dropped_not_iterated`; drop the per-entry `isinstance(value, Mapping)` → `test_a_cursor_entry_that_is_not_a_mapping_is_dropped_not_cast` | one guard, one test, each measured separately |

### Below-the-cap ledger — all seven landed

Each row's test was run by name **and** watched go red under the defect's own reintroduction.

| # | item | WP | the mutation → the test that reddened | commit |
|---|---|---|---|---|
| B1 | CLI uncaught `ValueError`/`KeyError`, incl. a chain answering zero | WP6 | drop the `rate == 0` check → `test_cli.py::test_a_chain_that_answers_zero_points_per_eth_is_a_named_error_not_a_traceback`; narrow `main`'s catch-all → `…::test_an_unexpected_value_error_exits_non_zero_with_a_message` and `…::test_a_malformed_labeled_bundle_is_a_message_not_a_key_error_traceback` | `8d5b66b`, `8015c17` |
| B2 | `_iso()` appends `Z` to a non-UTC offset | WP6 | skip the offset branch → `test_cli.py::test_a_non_utc_offset_is_converted_rather_than_suffixed_with_z` | `6ee1b8f` |
| B3 | negative `--funding-budget` inverts the cap | WP4 + WP6 | drop the library clamp → `test_sources.py::test_a_negative_funding_budget_is_a_zero_budget_not_an_inverted_one[-2]`; take `type=int` at the parser → `test_cli.py::test_a_negative_funding_budget_is_rejected_at_the_command_line` | `1a4c426`, `ce6b18f` |
| B4 | `--max-txs 0` still fetches the first block | WP6 | `cap <= 0` → `cap < 0` → `test_cli.py::test_a_zero_tx_cap_fetches_nothing_and_says_where_it_stopped` | `e707d06` |
| B5 | inverted `block_range` when `--from-block` is past head | WP6 | drop the head check → `test_cli.py::test_a_from_block_past_the_head_is_a_named_error_not_an_inverted_range` | `34e21bb`, `5530aca` |
| B6 | 429 rotates with no backoff | WP4 | zero the dead-status pause → `test_sources.py::test_a_429_backs_off_before_rotating` | `1a4c426` |
| B7 | string-echoed batch ids dropped on re-alignment | WP4 | drop the `int(raw)` retry in `_slot_of` → `test_sources.py::test_a_provider_that_echoes_string_ids_still_realigns_the_batch` | `1a4c426`, `99b3333` |

### Cleanup lane (WP8) — byte-identical detection output

These six are **agreement invariants, and they bite on divergence rather than on the hoist's
absence** — which is the honest thing to say about them: reverting a hoist leaves them green,
because deriving a fold twice gives the same answer twice. What they forbid is the *day the two
answers differ*, and each was watched go red on exactly that.

| item | the test, and the mutation it reddens under | commit |
|---|---|---|
| `detect()` recomputed `first_rows` ~7× | `test_public_api.py::test_the_signals_accept_a_precomputed_first_row_map_and_agree_with_deriving_it` — RED when a handed-in first-row map stops being the derived one (+4 signal tests with it) | `e77559e` |
| `split` re-ran `identical_amount_windows` | `test_public_api.py::test_split_and_amounts_walk_one_windowing_pass` — same shape, on the shared windowing pass | `d4753ff` |
| `clean_list` re-derived `segments`' folds | `test_public_api.py::test_clean_list_and_segments_agree_when_handed_the_same_folds` — RED when `clean_list` treats a handed-in `weights` differently from a derived one | `ccb393d` |
| `Edge.strength` duplicates `Reason.strength` | **refactor deliberately not taken**; `test_public_api.py::test_every_edges_strength_equals_its_reasons_strength` — RED when one `Edge(...)` is constructed with a strength its reason does not carry | `dafdacf` |
| `curator.first_deposits` duplicated `signals.first_rows` | `test_public_api.py::test_the_preset_and_the_signals_agree_on_first_deposits` — both compared to a third, hand-written derivation, so the comparison cannot become vacuous once one delegates | `c155a7f` |
| `_Session._last_at` dead state | `test_public_api.py::test_no_hand_written_slot_is_written_and_never_read` — a **structural scan**, not a note about one name: adding any never-loaded slot to any `__slots__` in the distribution reddens it (measured) | `5dabb17` |
| unused `Deposit` import in `gas.py` | folded into WP1.2 | `92bcdb3` |
| page-bound doubling redundant after D6-B | **recorded, not removed** — see §10.5 | — |

## 10.3 The rulings actually taken

The six from §1, all as recommended, all implemented:

| decision | ruling | what shipped |
|---|---|---|
| **D1** | **B** | `analyzed = set(res.analyzed)` — the fallback is gone. §1/D1's *reading* was also correct: `test_the_clean_list_on_an_empty_result_keeps_everybody` stayed green, so risk 3 in §8 did not materialise. |
| **D2** | **C** | `/internal-transactions?filter=to` is walked **only** when the external walk finished with no incoming transfer. Detection did not move on any committed fixture. |
| **D3** | **B** | deterministic `_replay_rank`, higher `block_number` wins, character-identical in `model.py` and `sources/logs.py`, and now *checked* rather than claimed. |
| **D4** | **A** | the band is `linked_groups` / "linked groups"; the credit line gates only `Segments.largest_operators`, which stays a property and is never a band. Membership and every measured number are unchanged. |
| **D5** | **A** | exempt-minimum rows are excluded from the near pass entirely. |
| **D6** | **B** | `FundingSweep.page_cursors` (defaulted, added last), `fetch_funding(..., cursors=…)` keyword-only; the maxpane slot carries it inside the existing `enrichment` dict, read tolerantly, so a pre-change payload still loads. |

Plus the two §1 micro-decisions: **#11(iii) was implemented** (a partial `DepositSweep` where a
zero-read still returns `None`; the CLI header now states the range actually covered,
`76fc08b`), and the **#2 gas reason string kept its wording and length**, with the meaning
change documented in the module docstring rather than in the rendered string — so no
cross-distribution re-pin of maxpane's 82-column OPERATORS evidence cell was needed.

### Five rulings taken *after* this plan was written

These were made during the remediation round, on defects the round's own audits found in the
round's own fixes. They are recorded here because they are design choices, not repairs. Their
pins were re-verified by mutation in the close-out (§10.2), and one of the pin columns below was
wrong — it is corrected in place.

| ruling | question | decision | why | pin |
|---|---|---|---|---|
| **R3.7 — the amended total replay rank** | D3-B froze a `_replay_rank` of seven *numeric* words, so two rows sharing a `(tx_hash, log_index)` and differing only in `contributor` and/or `ts` still ranked **equal** — and equal means first-wins, the exact order-dependence D3 existed to remove. | extend the rank to **every** field of the row: `contributor` after the numeric words, then `ts` as a present-flag followed by a value (because `None` does not order). | D3-B's own stated intent was a *total* order; the frozen text was an incomplete expression of it. Amending the rule is faithful to the ruling; leaving it would have shipped D3's promise unkept in the two fields most likely to differ between two decoders of one log. | `test_model.py::test_two_rows_differing_only_in_contributor_are_not_settled_by_arrival`, `…::test_two_rows_differing_only_in_ts_are_not_settled_by_arrival`, `…::test_a_readable_ts_outranks_an_unreadable_one_at_the_epoch`, `test_sources.py::test_the_two_copies_of_the_replay_rule_are_character_identical` |
| **R3.6 — the conservative shrinks reset** | #11(ii) gave the *span* a recovery but not the *shrink budget*, so a walk that spent its four shrinks on one dense region carried `shrinks == 4` forever and answered the next dense region by dropping a healthy endpoint. Where should the budget reset? | reset `shrinks` to 0 **only when the span has recovered all the way to `cfg.log_chunk_blocks`** — never on a partial recovery. | full width is reachable only by *reading real chunks*, so a conservative reset can never feed the livelock the shrink cap exists to prevent. The naive "recovery is recovery" hoist reintroduces it, and left 102 tests green while doing so — which is why the *placement* is pinned and not merely the fix. | **Corrected 2026-08-18 by measurement.** The placement pin is `test_sources.py::test_an_endpoint_that_refuses_every_wide_span_is_dropped_rather_than_retried` — the only test that reddens when `shrinks = 0` is hoisted out of the guard. `…::test_a_second_dense_region_costs_a_shrink_and_not_the_endpoint` stays **green** under that hoist (it pins the *fix*, and it reddens when the recovery is removed altogether), and `…::test_a_providers_suggested_retry_range_is_never_adopted` reddened under no mutation this pass applied — its bite is **not demonstrated here**. The first draft of this row named the two that do not carry the signal |
| **R3.8 — an empty-string funder is unresolved, not a measurement** | `fetch_funding` wrote `Funding(funder=funder, …)` for any completed walk, so a `from` that came back `""` produced a row byte-identical to the honest negative "both histories walked, nobody funded this wallet" — and the documented resume recipe would have frozen that failed read forever. | anything that is not an address leaves the address **`PENDING_UNREADABLE`**. Skipping only the *entry* was rejected: the next transfer up would then be resolved as the "first" one, inventing a funder rather than admitting a hole. | the repo's own rule — a failed read is `None`, never a value — applied to the one field whose whole meaning is "we finished looking". The same value arrives through a second door (`page_cursors` round-trips through a consumer's cache file), so `_resume_from` drops an unreadable best-so-far too: tolerant means dropping what we cannot read, not believing it. | `test_sources.py::test_a_funder_that_is_not_an_address_leaves_the_address_unresolved` (3 ids), `…::test_a_hand_edited_cursor_never_carries_an_unreadable_best_so_far` |
| **R3.9 — a container guard on every persisted read** | D6-B added `cursors` to the adapter's persisted slot. All *six* sub-payloads `fetch_enrichment` reads back were read with a type assumption (`(prior.get(k) or {}).items()`, `(prior.get("pending") or ())`) about bytes the module's own docstring calls third-party input. | guard the container type on all six; an unreadable map reads `{}` and an unreadable sequence reads `()`. | the failure is not a crash the user sees — the manager contains it — but a *permanent* one: a backoff does not repair a file, so every later sweep fails identically and the analysis panels stay dark until the cache is deleted by hand. `"pending": "0xab…"` was worse than a crash: iterating a string yields one single-character "address" per character, and pendings **head** the funding budget, so 42 characters would crowd 42 real wallets out of every sweep silently. `{}`/`()` is the honest reading because an unreadable map and an empty one mean the same thing to this caller — nothing to carry — and the next sweep re-derives it. | `tests/data/test_curator_clusters.py::test_every_persisted_enrichment_map_survives_a_hand_edited_cache_file`, `…::test_a_cursor_entry_that_is_not_a_mapping_is_dropped_not_cast`, `…::test_a_hand_edited_pending_list_is_dropped_not_iterated` |

## 10.4 Assertions that could not fail — and one record that could not be true

The round's audit found two committed tests that were green for a reason unrelated to what they
claimed to pin. Both are now anchored on the thing they name. Recording them here because
"a green test that cannot fail" is the exact defect class this build exists to remove, and it
turned up *inside the build itself*.

- **`d695e4a` — the SEGMENTS band assertions read the panel, not the band cell.** The band row's
  own **detail** cell reads `16 linked groups · 0.45Ξ–171.99Ξ send shapes`, so
  `"linked groups" in <the SEGMENTS panel>` was satisfied by the detail whatever the *label*
  said. Two of the four assertions the D4 rename reported as reddening could not see the label
  at all; the two that did bite bit only because the narrow tier sheds the detail column. At
  full width — where those two run — the panel-level read proved nothing. All four are now
  anchored on the band **cell**, via a `_row_cells(text, anchor)` helper that splits the one
  composited row on the table's own inter-column padding.
- **`38efaf8` — R3.6's fix was pinned, its *placement* was not.** Hoisting `shrinks = 0` out of
  `if span == full_span:` — the "recovery is recovery" simplification the comment beside it
  explicitly warns against — left all 102 other tests in `test_sources.py` green, including
  `test_a_second_dense_region_costs_a_shrink_and_not_the_endpoint`, while reintroducing exactly
  the livelock the shrink cap exists to prevent. The shape that shows it is an endpoint whose
  cap sits **at** `min_log_window`.

**And the third, found by the close-out's own re-audit.** The first draft of §10.3's R3.6 row
named `test_a_second_dense_region_costs_a_shrink_and_not_the_endpoint` and
`test_a_providers_suggested_retry_range_is_never_adopted` as the *placement* pins — the two
tests §10.4's second bullet had just finished saying stay green under the hoist. The row
contradicted the paragraph two screens below it. Nothing in the code was wrong; the **record**
was, and a record that names the wrong pin is how the right one gets deleted in a later cleanup.
It is corrected in §10.3, and the rule this close-out took from it is the one §10.2 now follows
throughout: name the test that was *watched go red*, never the test whose name reads best.

## 10.5 Deliberately not done — with the reason

Four. None of them is an oversight, and none is a finding left open by accident.

1. **The peel-chain casing guard carries no test, on purpose (`5d04a89`).** `funding.py` holds
   the self-funder guard twice — on the peel chain and in the `by_funder` hub fold — and only
   the hub half is pinned. Mutating the peel-chain line from `funder.lower() == addr.lower()`
   to `funder == addr` leaves the **whole suite green**. Measured, not assumed: the peel chain
   reaches its edge only through `component_of`, which is keyed on the dataset's own contributor
   spellings, so a funder spelled differently from every contributor misses that lookup and
   yields no edge whatever the guard decides. The only dataset in which both spellings resolve
   is one carrying the same wallet twice as two contributors — and that dataset already breaks
   the lowercase-address invariant `Edge` and `_UnionFind` document, and **no producer in either
   distribution can build it** (`Dataset.from_events`, `sources/logs.py`, `sources/blockscout.py`
   and maxpane's adapter all lowercase). There is therefore no honest fixture, and a green test
   that cannot fail is the thing this round removes rather than adds. The line carries a comment
   naming the `component_of` argument and the module docstring says which half is pinned.
   **Re-measured in the close-out**: with `funder.lower() == addr.lower()` mutated to
   `funder == addr`, the library suite is 422 passed + 1 xfailed — unchanged. Removing the guard
   *entirely* is a different mutation and does redden three tests (§10.2, row 1), so the guard is
   load-bearing and only its **casing** is unpinnable.
2. **D5-A leaves a lexical winner among *non-exempt* byte-equal runs (`b4ae077`).** The ruling
   scoped the fix to the protocol minimum, so the near pass still picks the run's
   lowest-/highest-addressed member as the one carrying the near edge, decided by lowercase
   address order. It is **harmless and now written down**: a byte-equal run of two or more
   non-exempt single-deposit rows in one block is *already one component* before the near pass
   runs (`identical_amount_windows` welds it), so the near edge merges the same two components
   whichever member carries it. Membership is order-independent, and membership is what every
   count, share and reason a caller sees comes from. Pinned rather than asserted in prose by
   `test_which_member_of_a_byte_equal_run_carries_the_near_edge_changes_nothing`, which runs one
   run under two address permutations and asserts *both* halves: the carrier moves, the induced
   partition does not.
3. **`Edge.strength` is not refactored away (WP8, `dafdacf`).** Dropping the duplicated field
   means editing every `Edge(...)` construction in five signal modules for no behaviour change —
   exactly the risk the cleanup lane exists to avoid. The lane leaves the **invariant** instead,
   because the duplication is harmless only while the two agree and its two readers disagree the
   moment they do not (`detect`'s per-family "best" pick reads `edge.reason.strength`; `Edge`'s
   own docstring says `strength` is what confidence is built from).
4. **The adapter's page-bound doubling stays (D6-B, §1).** It is redundant now that a
   page-bounded address resumes from its own cursor, but removing a mechanism with existing
   tests in the same pass that adds a new one is how both end up untested. Recorded for a later
   cleanup; it is still live at `data/curator_clusters.py:773`.

## 10.6 Documentation

- **`sybilkit/README.md`** — updated by WP9 for every behaviour that moved: a "What a sweep
  returns, and what it means" table (`None` = nothing read, stated per fetcher; `DepositSweep.to_block`
  as coverage *and* resume cursor under #11(iii)); the funding walk's two-history coverage under
  D2-C and the rule that `funder=None` in `funding` is a measurement while anything unreadable
  is `pending`; the per-address `page_cursors` and its tolerant read; a "What the dataset
  guarantees" section for the total replay tie-break (D3-B as amended by R3.7) and the `ts`
  degrade under #8; the `linked_groups` key vocabulary and why the rename was the fix under
  D4-A; `clean_list`'s `analyzed`-only survivors under D1-B; and the additive keyword-only
  folds. Line 125's `segments(...)` comment landed in wave 1 with the rename (it is why the
  working-tree diff was purely additive: the stale band name was already gone) and was confirmed,
  not re-made.
  **Four corrections the second WP9 made to that draft before committing it**, each checked
  against the source rather than against the draft:
  1. *"an ISO-8601 timestamp is a readable dataset with unlabelled hours"* was wrong — hour
     bands come from the event's own `hour` word and are unaffected. The only casualty of an
     unreadable `ts` is the CLI's `generated_at` provenance stamp, and the paragraph now says
     that, plus the R3.7b rule that a `NaN`/`inf` degrades **in the coercer** rather than in the
     tie-break.
  2. `fetch_deposits`' `None` is "the head could not be read, **or** not one chunk could", not
     "zero chunks were read".
  3. `fetch_funding`'s `None` is "not one attempted address answered" — and the README now
     carries the reason a deferral does not soften it.
  4. the shared-fold list gained `groups=`, which `gas_edges` takes and the draft omitted.
  Two behaviours the draft did not mention at all were added: **every CLI refusal is a named
  message and a non-zero exit** (B1–B5), and the failover's two new rules — an unreadable 200
  rotates (#3) and a 429 backs off before rotating (B6).
- **`README.md`** — the SEGMENTS bullet landed in wave 2 with the rename (`ceffe02`), and this
  close-out **fixed one clause on it**: that commit had introduced "the single-send whales" as a
  band, and there is no such band. `Segments.bands` emits exactly `linked_groups`,
  `early_cohort`, `late_cohort`, `hour_<h>`, `multiplier_<edge_bps>` and `multiplier_unknown`
  (read off `curator.py`, not off a docstring); the credit-line slice is the `largest_operators`
  *property*, which is what finding #12 was about, and the adapter renders `seg.bands` only. The
  `single-send whales ≥ 800Ξ` row exists solely in
  `tests/fixtures/curator/sybil/segment_rows_worst.json`, which carries the literal `SYNTHETIC —`
  marker and is a width-calibration payload, not library output. The bullet now names the bands
  the library actually emits. This was O1.
- **`maxpane_dashboard/widgets/curator/segments.py`** — one clause on line 3, and nothing else in
  the file. It still opened "One row per derived band: whale **operators** by combined credit"
  while its own example three lines below already read `linked groups`: the exact
  mis-description finding #12 closed everywhere else, surviving where no test looks. It now reads
  "**every linked group**, aggregated". This was O2.
- **`CLAUDE.md` — deliberately untouched, and that is a conclusion rather than an omission.**
  Checked claim by claim against this build: the three width numbers (143 / 138 / 137) were
  re-swept and did not move; the six-surface rules were not exercised (this was an expansion, not
  a ninth dashboard, and `app.py`, `__main__.py` and `GAMES` are untouched); "only
  `data/curator_clusters.py` imports sybilkit" and "`analytics/curator_signals.py` is
  byte-identical to what shipped" were both re-verified mechanically; "resumable through a cursor
  in the slot" is still true and is now *more* true (the cursor is per-address); the structural
  `high`/`low` banding, the `⚑`/`◌`/`?` vocabulary and the forbidden-word boundary are unchanged;
  the status hints `c panels · y you · f linked` are unchanged; and the guarded-import packaging
  story is re-verified by the root wheel carrying zero `sybilkit` entries and no `sybilkit` in
  `Requires-Dist`. **No behaviour CLAUDE.md documents moved, so no line of it was edited.**
- **This plan** — the §2 ownership table's README self-contradiction is corrected in place, a
  second note records the two lines WP9 took from WP7's column in this pass, and this close-out
  section is appended and then re-derived by measurement. The file was **untracked** until this
  commit; it is committed now so the record stops living in a chat session.

## 10.7 Open items

Nothing on the ranked list is open, and the two documentation items the first draft left open
(O1, O2) are closed above. What follows is everything a next pass would want to know.

| # | item | why it is open |
|---|---|---|
| O1 | *(closed)* `README.md`'s SEGMENTS bullet named a band that does not exist. | Fixed in this close-out — see §10.6. |
| O2 | *(closed)* `widgets/curator/segments.py:3` described the panel's first row as the credit-line slice. | Fixed in this close-out — see §10.6. |
| O3 | The adapter's page-bound doubling is now redundant (§10.5 item 4). | Deliberately deferred to a later cleanup, not this pass: removing a mechanism that has tests, in the same pass that adds its replacement, is how both end up untested. Still live at `data/curator_clusters.py:773`. |
| O4 | `Edge.strength` / `Reason.strength` remain two fields holding one number (§10.5 item 3). | Deliberately deferred; the invariant is pinned instead, and the pin was watched go red. |
| O5 | The peel-chain **casing** guard has no test and cannot be given an honest one (§10.5 item 1). | Structurally unreachable through any producer in either distribution — re-measured: the casing mutation leaves 422 passed + 1 xfailed. The guard itself *is* pinned; only its `.lower()` is not. Revisit only if a producer stops lowercasing. |
| O6 | D5-A leaves a lexical carrier among non-exempt byte-equal runs (§10.5 item 2). | Ruled deliberately: D5-A scoped the fix to the protocol minimum. Proven not to change membership and pinned by `test_which_member_of_a_byte_equal_run_carries_the_near_edge_changes_nothing`. Revisit only if `identical_amount_windows` stops welding those runs. |
| O7 | `fetch_funding`'s own docstring is not covered by the doc-agreement test (§10.2, row 5c). | The test reads the module docstring and `FundingSweep`'s; a third statement of the same contract sits in the function docstring and is unpinned. Cheap to add; not added in a pass whose brief was verification. |
| O8 | `test_a_providers_suggested_retry_range_is_never_adopted` reddened under no mutation this pass applied. | Not evidence that it cannot bite — the pass did not construct a mutation that adopts a provider's suggested range, because the code never parses one. Recorded so the next reader does not take it for a demonstrated pin. |
| O9 | `sybilkit` is still absent from maxpane's `pyproject.toml`, so `pip install maxpane` degrades the analysis panels to "analysis unavailable". | By design until sybilkit publishes; adding it early makes `pip install maxpane` fail to resolve. Nothing in this build changed it, and the root wheel was re-verified clean. |
| O10 | The memory record `project_sybilkit_review_2026_08` still headlines "15 CONFIRMED defects OPEN (unfixed)". | Outside this WP9's file ownership as briefed — the brief names `sybilkit/README.md`, `README.md`, `CLAUDE.md`, this plan and one widget docstring. This section is the durable record instead; the memory line is a one-line correction whenever the user wants it. |

## 10.8 Recommendation

**Land it. Do not publish `sybilkit` before it.**

Both suites are green with zero skips and both counts only went up (+133 library, +10 maxpane);
`cargo test` is 443 and untouched; both distributions build in isolated environments; the root
wheel carries zero `sybilkit` entries and no `sybilkit` in `Requires-Dist`; the benchmark gate
and the two distributions' agreement fixture are byte-unchanged from the review baseline; all
three width pins were re-swept rather than read off a constant; and **every one of the 15
findings, all seven below-cap items and all five build-time rulings was watched go red under its
own defect** rather than certified by a passing test's name.

The review's own judgement stands and this round's measurements support it: four of the fifteen
could **fabricate or erase an evidence family**, and three more could turn an outage into a
confident "we looked and there was nothing" — in a library whose output judges real people's
wallets, and which is about to be published by hand for the first time. Landing them before the
first upload is the difference between a first release and a first erratum.

**Merging, tagging and publishing remain the user's decision.** WP9 ends here, with a green tree
and this record — not with a merge, a push or a `v*` tag. Suggested order when the user is
ready: merge `feature/curator-sybil` to `main`; re-run `pip install -e .` if any version is
bumped (an editable install writes its metadata once, at install time, and this venv once
reported a three-month-old version for exactly that reason); then cut the sybilkit release by
hand from `sybilkit/pyproject.toml` per `sybilkit/README.md`'s Releasing section. The two
one-clause documentation fixes the first draft listed as prerequisites (O1, O2) are **done** —
they were the last two places in the tree that still described the band by the name finding #12
removed. Outside this document, `rg -n "largest operators"` now returns four lines and every one
of them is a **test or comment asserting the old name is gone** — `test_curator.py:606`,
`tests/data/test_curator_clusters.py:389`, `tests/data/test_curator_sybil_data.py:688`
(`assert "largest operators" not in by_label`) and `tests/data/test_curator_manager.py:2521`.
Nothing renders it.
