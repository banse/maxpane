# WP3 — maxpane adapter & cache: `data/curator_clusters.py`, the analysis tier, the detached sweep

**Goal:** Wire `sybilkit` into THE LIST through one adapter, add a long-TTL cache tier/slot for
the background Tier-B+C sweep, run that sweep **detached** exactly like the shipped
`_spawn_crosscheck`, and merge the new analysis keys into the flat `fetch_and_compute()` dict —
without letting an exception escape, without persisting a verdict, and without touching first
paint.

**Dependencies:** WP0 (the new keys/rows), WP1 (`sybilkit` core: `detect`/`Dataset`), WP2
(`sybilkit.curator` preset + `sybilkit.sources`). **Wave 3, alone** — this WP owns the shared
`curator_manager.py`/`curator_cache.py` and is the critical path's narrowest point.

**Owner note — this WP owns and modifies:**

- `maxpane_dashboard/data/curator_manager.py`
- `maxpane_dashboard/data/curator_cache.py`

and **creates:**

- `maxpane_dashboard/data/curator_clusters.py` (the **only** maxpane module that imports
  `sybilkit`)
- `tests/data/test_curator_clusters.py`
- additions to `tests/data/test_curator_cache.py`, `tests/data/test_curator_manager.py`,
  `tests/data/test_curator_degradation.py`
- its own fixtures under `tests/fixtures/curator/sybil/` (adapter slices)

It reads but **must not edit** `curator_client.py`, `curator_signals.py`, `curator_addresses.py`
and the `sybilkit` package — a defect in any is **reported**, not fixed.

### Ground rules

- **`fetch_and_compute()` never raises** and still returns **exactly** `CURATOR_KEYS`
  (now including the new analysis keys) under every failure combination. The new keys default to
  `None`/`[]` in `_blank_payload` (they are already there because `_blank_payload` is
  `dict.fromkeys(CURATOR_KEYS)`) and are filled by the merge below.
- **The new keys are filled in the manager, after `build_signals`** — never by
  `curator_signals.build_signals`. `curator_signals.py` stays exactly as shipped (PRD §2); its
  forbidden-word source scan is untouched. `data/curator_clusters.py` is the only maxpane import
  of `sybilkit`; a guardrail test (WP3.9) asserts `curator_signals.py` never imports it.
- **The detached sweep follows `_spawn_crosscheck` precisely** (`curator_manager.py` ~lines
  958–1008): one-in-flight, publishes into a cache slot the next cycle reads, stamped with the
  **spawn** time, cancelled-and-awaited first in `close()`.
- **No verdict persisted** (PRD §2). The analysis last-good is revisable; nothing writes a
  boolean "is a sybil" into a history series. `store_last_good(SLOT_CLUSTERS, …)` holds the
  revisable result behind an `as of HH:MM`; the schema-version bump rule is the additive-key
  one the cache already uses (`dropped_events`/`ens` precedent — no `_SCHEMA_VERSION` bump).
- **Keyless, no-network tests** — the adapter drives `sybilkit.sources` with an **injected
  transport** (WP2's `transport=` kwarg); a test that opens a real socket is a failure.
- **A failed read is `None`; the two representable states are answers.** `operators_count == 0`
  means "analyzed, nothing linked" (representable zero); `None` means "could not analyze"
  (`None` + the `logs` degraded group — plan §6 risk 7, fold into `logs`).
- Commit after each task.

---

### Task WP3.1: `data/curator_clusters.py` — the pure adapter core

**Interfaces:** produces `build_analysis(events, first_deposits, *, txs=None, funding=None,
points_per_eth=None, wallet=None, config=None) -> AnalysisResult` — a **pure** function that
turns the cache's decoded `DepositEvent` history (plus optional tx/funding enrichment) into the
new flat keys via `sybilkit`. Also `analysis_keys(result) -> dict` returning exactly the new
`CURATOR_KEYS` subset, and `merge_leaderboard_grade(leaderboard_rows, result) -> None` (in-place,
the ENS-merge shape) filling `link_conf`.

`AnalysisResult` is a small value object holding the `sybilkit.DetectResult`, the segments, the
clean list, and the reader's linkage — everything the manager needs to fill the flat dict.

**Steps:**

- [ ] Failing tests (`test_curator_clusters.py`): with only events (tier A), `build_analysis`
      produces `operator_rows` matching `CURATOR_ROW_KEYS["operator_rows"]`, `operators_count`,
      `segment_rows`, `clean_list_rows`, `clean_points`, `clean_contributors`, and — when a
      `wallet` is set — `you_linked_state`/`you_linked_reasons`/`you_linked_group_size`/
      `you_clean_rank`; the flagged set **matches `sybilkit.detect(...).flagged`** on a committed
      fixture (`tests/fixtures/curator/sybil/`); every operator row's `reasons` is a list of
      pattern-language strings (no `sybil/cheat/fraud/attack/abuse/wash`, asserted here too —
      the adapter is the translation boundary from library vocabulary to on-screen pattern
      language); `link_conf` is `"high"|"low"|"clean"|None` per the cluster confidence.
- [ ] `build_analysis` divides wei→ETH **once** for the `_eth`-denominated row fields, matching
      `build_signals`' boundary (no double division). `points`/`points_share_pct`/`sqrt_subsidy_x`
      come from the preset.
- [ ] **The pattern-language translation lives here**: `sybilkit` reasons carry the library's
      vocabulary; the adapter maps each `Reason.family`+`human_string` to the on-screen phrase
      ("identical 0.45 ETH send", "2-block cadence", "shared funder"). A `_REASON_PHRASES` table
      + a test that the output never contains a forbidden word.
- [ ] **Bite:** drop the forbidden-word filter/mapping and pass a raw library reason through →
      the adapter's pattern-language test reddens. Restore.
- [ ] Commit: `feat(curator): sybilkit adapter producing pattern-language analysis rows`

---

### Task WP3.2: `curator_cache.py` — `TIER_ANALYSIS` and `SLOT_CLUSTERS`

**Interfaces:** add `TIER_ANALYSIS = "analysis"` to `TIERS`, `TIER_TTL_SECONDS`
(≈ 1800–3600 s — PRD §4 "~30–60 min"), `TIER_FAILURE_BACKOFF_SECONDS`; add `SLOT_CLUSTERS =
"clusters"` to `SLOTS`; add `store_analysis(payload, *, ts)` / `analysis_last_good()` /
`analysis_as_of_hhmm()` methods reading `SLOT_CLUSTERS`.

**Steps:**

- [ ] Failing tests (`test_curator_cache.py` additions):
  - `TIER_ANALYSIS` is in `TIERS` and its TTL is in the 1800–3600 s band; its failure backoff
    is shorter than its TTL; the `once`/`fast`/`medium`/`slow` tiers are unchanged.
  - `SLOT_CLUSTERS` is in `SLOTS`; `store_last_good(SLOT_CLUSTERS, None)` is refused (the
    existing rule); the analysis last-good survives a save/load round trip; **the schema
    version does not move** (an older file simply lacks the slot — the `ens`/`dropped_events`
    precedent).
  - `analysis_as_of_hhmm()` renders the slot's own stamp, distinct from the fast tier's
    `newest_as_of()` — the analysis is a long-TTL slot and its freshness marker moves on its own
    schedule.
  - **No verdict persisted:** the persisted analysis payload holds revisable rows, and a test
    asserts no boolean `is_sybil`/`flagged` value enters a **series** (the series writers are
    untouched; this pins that the analysis slot is a last-good, not a history).
- [ ] Implement. Extend `SLOTS`/`TIERS` tuples and the `__all__` export; the `_payload()`/
      `load()` gain an `analysis` section behind a per-section `try/except` (the house pattern).
- [ ] **Bite:** bump `_SCHEMA_VERSION` unnecessarily → the "older file loads its other sections"
      test reddens (an old file would now load nothing). Restore, keeping the additive approach.
- [ ] Commit: `feat(curator): analysis cache tier and last-good slot, additively persisted`

---

### Task WP3.3: The detached Tier-B+C sweep in `curator_manager.py`

**Interfaces:** `_spawn_analysis(tiers, now, config)` and `_analysis_detached(...)` and
`_pool_analysis(...)`, modelled **exactly** on `_spawn_crosscheck` / `_crosscheck_detached` /
`_pool_crosscheck` (curator_manager.py ~958–1139). A new `self._analysis_task` field alongside
`self._crosscheck_task`.

**The rule (PRD §4):** a full Tier-B+C read (batched `getTransactionByHash` for gas + Blockscout
per-address for funding) is minutes long and awaiting it in-cycle blanks the dashboard — so it
runs detached, one-in-flight, publishes into `SLOT_CLUSTERS` the next cycle reads, stamps
`as of HH:MM` at **spawn** time.

**Steps:**

- [ ] Failing tests (`test_curator_manager.py` additions):
  - `_spawn_analysis` starts a task and returns immediately; a second call while one is in
    flight returns the running task and does **not** start another (one-in-flight, the
    `_spawn_crosscheck` guard);
  - the sweep publishes into `SLOT_CLUSTERS` and the **next** cycle reads it (the payload built
    before the sweep lands is the already-supported "analysis not yet run" state — `None` +
    `analysis_as_of_hhmm=None`);
  - the sweep drives `sybilkit.sources` with an **injected transport** (no real socket);
  - `TIER_ANALYSIS not in tiers` → the sweep is skipped (gated like the slow tier);
  - `close()` cancels **both** `_crosscheck_task` and `_analysis_task` (extend
    `_cancel_crosscheck`/`close`), and saves the cache after.
- [ ] Implement. The sweep: read the cache's `events()` + `first_deposits()`, fetch tx
      fingerprints (Tier B) and funding (Tier C) via `sybilkit.sources` (bounded, throttled,
      resumable), call `curator_clusters.build_analysis`, and `cache.store_analysis(payload,
      ts=spawn_now)`. It publishes no key directly — the **next** `_cycle` reads the slot and
      merges (WP3.4).
- [ ] **Bite (mandated — first paint not blocked):** `await` the analysis sweep inside `_cycle`
      instead of spawning it → a "first payload is not behind the analysis read" test reddens
      (measure the payload is produced before the sweep completes, the `_spawn_crosscheck`
      precedent). Restore. Record for WP6's audit.
- [ ] Commit: `feat(curator): detached Tier-B+C analysis sweep on the _spawn_crosscheck pattern`

---

### Task WP3.4: Merge the analysis into the flat dict (`_cycle`)

**Interfaces:** in `_cycle`, after `build_signals` and the existing `_label_with_ens`, read
`cache.analysis_last_good()` and merge the new keys into `payload` (the ENS-merge shape), then
fill `analysis_as_of_hhmm`, then `_finalise`.

**Steps:**

- [ ] Failing tests:
  - `fetch_and_compute()` returns **exactly** `CURATOR_KEYS` (the new keys included) under every
    failure combination and **never raises** (extend the existing
    `test_it_returns_exactly_curator_keys_always` — this is the one test WP0 turned red; it goes
    green here);
  - with no analysis last-good, every new key is `None`/`[]` and `analysis_as_of_hhmm` is `None`
    (the "not yet analyzed" state — never a confident empty);
  - with an analysis last-good, `operator_rows`/`segment_rows`/`clean_list_rows` are populated,
    `operators_count` is a real count (`0` when analyzed-and-none), and `you_linked_*`/
    `you_clean_rank` reflect the configured wallet;
  - `merge_leaderboard_grade` fills `link_conf` on the leaderboard rows in place, leaving
    `flagged` (the Tier-A bool) untouched;
  - **the `flagged_points_share_pct` reuse decision (plan §6 risk 2):** implement the
    recommended **override-with-fallback** — the analysis last-good's share wins when present,
    the Tier-A value stands otherwise — and pin it with
    `test_the_farm_share_prefers_the_analysis_value_when_it_has_run`. If review rejects the
    override, the fallback (a separate key) is a one-line change; note it in the commit body.
- [ ] Implement the merge next to `_label_with_ens`, guarded by `_safe_call`.
- [ ] **Bite:** seed the new row keys to `[]` in the merge when the analysis did not run → the
      "dead-vs-empty" test reddens (a not-yet-run analysis must be `None`, not an empty table
      asserting nobody is linked). Restore.
- [ ] Commit: `feat(curator): merge the detached analysis into fetch_and_compute`

---

### Task WP3.5: Degradation wiring (fold into `logs`)

**Interfaces:** the analysis's failure degrades the **`logs`** group (plan §6 risk 7); no new
`CURATOR_DEGRADED_GROUPS` name (the title bar renders those verbatim and they are frozen).

**Steps:**

- [ ] Failing tests (`test_curator_degradation.py` additions): a failed analysis sweep marks
      `TIER_ANALYSIS` failed (backoff), does **not** blank the fold or the clock, and surfaces
      as `degraded == ["logs"]` **only if** the log-derived story is also degraded — i.e. an
      analysis-only failure while the log fold is fresh keeps the analysis keys on last-good
      behind `analysis_as_of_hhmm` and does **not** falsely light `logs`. Decide and pin the
      exact rule: the analysis is enrichment over logs, so its **absence** degrades the analysis
      keys to last-good/`None`, and the group banner fires only when the analysis has **never**
      produced a payload (the "unavailable state" the FARM row already uses for
      `clusters_count is None`).
- [ ] Implement, reusing `_note`/`_degraded`/`GROUP_SLOT`. If the exact semantics need a new
      group after all, that is a **scope change** — stop and escalate per plan §6 risk 7 rather
      than silently adding a group name.
- [ ] Commit: `feat(curator): fold the analysis sweep's health into the logs degradation story`

---

### Task WP3.6: The reader's linkage and clean rank

**Interfaces:** `you_linked_state` / `you_linked_reasons` / `you_linked_group_size` /
`you_clean_rank`, filled from `AnalysisResult` for the configured wallet.

**Steps:**

- [ ] Failing tests: a wallet in a cluster → `you_linked_state == "linked"`, reasons are
      pattern-language, `you_linked_group_size` is the cluster size, `you_clean_rank` is `None`
      (removed from the clean list); a wallet analyzed and not linked → `you_linked_state ==
      "clean"`, `you_linked_reasons == []`, `you_clean_rank` a dense rank; the analysis not yet
      run → `you_linked_state is None` (never a confident "clean"); no wallet configured → all
      four `None` and **no** `wallet` degradation (the existing rule).
- [ ] `set_wallet` already exists and expires the fast tier + drops the wallet last-good — extend
      it (or the next cycle's merge) so the reader's linkage recomputes for the new address from
      the **already-held** analysis last-good, without forcing a fresh B+C sweep (the sweep is
      about-the-population, not about-one-wallet).
- [ ] Commit: `feat(curator): per-wallet linkage and clean rank from the analysis last-good`

---

### Task WP3.7: The integration fixture — adapter agrees with the library

**Steps:**

- [ ] A committed fixture (`tests/fixtures/curator/sybil/adapter_agrees.json`) and a test:
      `build_analysis` over the fixture's events produces a `flagged` set **identical** to
      `sybilkit.detect(Dataset.from_events(...)).flagged`, and the `operator_rows` shapes match
      `CURATOR_ROW_KEYS["operator_rows"]`. This is the seam the PRD §8 mandates ("a maxpane-side
      assertion that the adapter's flagged set matches the library on a committed fixture").
- [ ] Assert the `operator_rows` produced match the **worst-case fixture shape** WP0 froze
      (`operator_row_worst.json`), so WP4's width sweep was measured against a real shape.
- [ ] Commit: `test(curator): pin adapter-library agreement on a committed fixture`

---

### Task WP3.8: No-network + no-verdict-persisted guardrails

**Steps:**

- [ ] `test_no_curator_module_opens_a_socket_for_analysis`: the adapter's sweep tests all inject
      a transport; a structural scan confirms no bare client in the test paths.
- [ ] `test_the_analysis_slot_persists_no_boolean_verdict`: save a cache with an analysis
      last-good, read the file, assert no `is_sybil`/`sybil`/`verdict` boolean key is written to
      disk (revisable rows only — PRD §2).
- [ ] `test_curator_signals_never_imports_sybilkit`: AST-scan `analytics/curator_signals.py` —
      it must not import the library (the Tier-A-stays-shipped + forbidden-word-source rules).
- [ ] `test_only_curator_clusters_imports_sybilkit`: the **only** maxpane module importing
      `sybilkit` is `data/curator_clusters.py` (a repo-wide scan).
- [ ] Commit: `test(curator): keyless, no-verdict, single-import guardrails for the adapter`

---

### Task WP3.9: Full-WP + suite green and sign-off

**Steps:**

- [ ] Run the whole WP surface, then the full maxpane suite. The manager totality test WP0
      reddened is now green; nothing else moved except the tests this WP added.
- [ ] Confirm `close()` cancels both detached tasks and saves (no "task was never retrieved"
      warning; no traceback on quit while a sweep is in flight — the `_cancel_crosscheck`
      precedent).
- [ ] Write the WP4/WP6 hand-off note: the exact new-key values the payload carries in each
      state (not-yet-run / analyzed-none / analyzed-linked / degraded), the `analysis_as_of_hhmm`
      semantics, and the `flagged_points_share_pct` override decision (so WP4's OPERATORS panel
      and the FARM row agree, and WP6's docs describe the right behaviour).
- [ ] Commit: `test(curator): WP3 sign-off — adapter, tier, detached sweep, degradation`

**Done when:** the flat contract holds under every failure combination with the new keys filled
from a detached, one-in-flight, last-good analysis sweep; first paint is never behind it; no
verdict is persisted; `curator_signals.py` is untouched; and the adapter agrees with `sybilkit`
on a committed fixture.
