# WP3 report — maxpane adapter, analysis cache tier, detached Tier-B+C sweep

**Status: DONE_WITH_CONCERNS** (all nine tasks complete, suite green and
grown; concerns are a packaging-dependency gap and calibration notes, none
blocking WP6).

Branch `feature/curator-sybil`, base `ed780bd`. Alone on the tree this wave.
Suite at sign-off: see §9 (full number pasted verbatim there).

## Commits, in order

| SHA | Subject |
|---|---|
| `7186578` | feat(curator): sybilkit adapter producing pattern-language analysis rows |
| `c74b611` | feat(curator): analysis cache tier and last-good slot, additively persisted |
| `4c9f476` | feat(curator): detached Tier-B+C analysis sweep on the _spawn_crosscheck pattern |
| `726bcdd` | feat(curator): merge the detached analysis into fetch_and_compute |
| `20050e8` | feat(curator): fold the analysis sweep's health into the logs degradation story |
| `3cd2ebb` | feat(curator): per-wallet linkage and clean rank from the analysis last-good |
| `59afb1d` | test(curator): pin adapter-library agreement on a committed fixture |
| `a2ff0dd` | test(curator): keyless, no-verdict, single-import guardrails for the adapter |
| (sign-off) | test(curator): WP3 sign-off — adapter, tier, detached sweep, degradation |

Every commit is pathspec-limited (`git commit … -- <paths>`, the WP1-concern-1
rule). Files touched, and only these (`git diff ed780bd..HEAD --stat`):

- **created** `maxpane_dashboard/data/curator_clusters.py` (the only maxpane
  import of `sybilkit` — guardrail-tested), `tests/data/test_curator_clusters.py`,
  `tests/fixtures/curator/sybil/adapter_agrees.json`
- `maxpane_dashboard/data/curator_manager.py`, `curator_cache.py`
- additions to `tests/data/test_curator_manager.py`, `test_curator_cache.py`,
  `test_curator_degradation.py`

`curator_client.py`, `curator_signals.py`, `curator_addresses.py`, `sybilkit/`,
every widget/screen: **untouched**. `git diff main --
maxpane_dashboard/analytics/curator_signals.py` is **empty** (byte-identity
stands). The user's untracked `tests/fixtures/curator/captures/live/2026*` are
untouched.

**One environment action beyond the file list:** `sybilkit` was installed
editable into `.venv` (`pip install -e sybilkit/`). Before that, `import
sybilkit` resolved to the repo's `sybilkit/` *directory* as an empty namespace
package — `from sybilkit import detect` failed everywhere. See concern 1.

---

## 1. What was implemented

### `data/curator_clusters.py` — the one seam (WP3.1, WP3.3)

- **`build_analysis(events, first_deposits, *, txs, funding, points_per_eth,
  min_deposit_wei, wallet, config)`** — pure: dataset → `detect` → `segments`
  → `clean_list` → the frozen row shapes. `min_deposit_wei` is not in the
  brief's sketched signature; ruling R13 landed after it was written and the
  preset refuses to exist without the minimum, so the honest signature carries
  it (documented at the parameter). Both live reads are **required** when no
  preset is passed — a missing one raises, and the caller reports "could not
  analyze" instead of analyzing with a remembered 1000.
- **`AnalysisResult`** — the library objects plus the shaped rows plus two
  compact revisable lookups (`groups`, `clean_ranks`) that make any wallet's
  linkage answerable from the persisted payload after a restart.
- **`analysis_keys(result, *, wallet)`** — exactly `CURATOR_ANALYSIS_KEYS`
  (twelve, R14's `points_total` included, filled from the *same*
  `DetectResult.total_points` snapshot as `clean_points`).
  `analysis_as_of_hhmm` stays `None` here on purpose: the pure adapter holds
  no clock; the manager stamps it from the slot.
- **`pattern_language(text, family)`** — the translation boundary: a string
  carrying any of `sybil/cheat/fraud/attack/abuse/wash` is replaced with the
  family's `_REASON_PHRASES` fallback ("matching send amounts", "consecutive
  join indices", "matching send rhythm", "uniform fee fingerprint", "shared
  funder chain"), never shipped. Applied to every reason/label/detail on the
  way out — **including strings read back from the persisted payload**,
  because a hand-edited cache file is third-party input too.
- **`grade_of` / `you_linkage` / `merge_leaderboard_grade`** — answer
  identically off a live `AnalysisResult` and off the slot payload (pinned),
  which is what makes the wallet-switch path work with no new sweep.
- **`candidate_targets`** (R3) — the members of every tier-A component ≥
  `min_size`, in chain order, plus the first `CONTROL_MARGIN` (24)
  non-candidate contributors; tx hashes are the candidates' first-deposit
  transactions (what gas and the freshness discount actually read).
- **`fetch_enrichment` / `EnrichmentSweep`** — one bounded resumable pass:
  known fingerprints/funders never re-read, the funding cursor's pendings go
  first, `"pages"` pendings double the page bound (start = the sources
  default 20, cap `MAX_FUNDING_PAGES` 80), `"unreadable"` retried as-is,
  `fetch_funding` **never called with a zero budget** (skip = don't call),
  every sweep tested `is not None`, never truthiness. **No session, no
  fetch**: with neither `client` nor `transport` the carried state returns
  untouched — proven with a bomb (both source functions monkeypatched to
  raise; nothing raises).

### `curator_cache.py` (WP3.2)

`TIER_ANALYSIS` ("analysis", TTL **1800 s**, backoff **300 s** — shorter than
the TTL so a failed sweep retries sooner than a good one refreshes) and
`SLOT_CLUSTERS` ("clusters"), riding the generic last-good persistence, so
**`_SCHEMA_VERSION` stays 1** (the `ens`/`dropped_events` additive precedent —
an older file simply lacks the slot and restores "the analysis never ran",
which is true; the brief's "gain an `analysis` section" is satisfied by the
slot machinery itself, and adding a second section would have stored the
payload twice). `store_analysis(payload, *, ts)` / `analysis_last_good()` /
`analysis_as_of_hhmm()` added.

**`newest_as_of()` now excludes `SLOT_CLUSTERS`.** Not in the brief, found
while wiring: the sweep re-derives from data already fetched, so a publish
during a total source outage would have marched the title bar's global
`as of HH:MM` forward while nothing had answered — a freshness lie the
settlement-outage tests exist to forbid. The analysis has its own marker.
Pinned by `test_an_analysis_publish_never_moves_the_global_freshness_marker`.

### `curator_manager.py` (WP3.3–WP3.6)

- `_spawn_analysis` / `_analysis_detached` / `_cancel_analysis` /
  `_pool_analysis`, modelled on the crosscheck trio verbatim: gated on
  `TIER_ANALYSIS in tiers`, one-in-flight (the running task is returned, a
  second is never started), spawn-time stamp, cancelled-and-awaited in
  `close()` right after the crosscheck (both hold the client's session), the
  cache still saved.
- **The pure folds run in `asyncio.to_thread`**: `detect` over a real 25k-row
  history is ~0.4 s of CPU, and a detached task still shares the TUI's event
  loop — synchronous, it would hitch every frame twice an hour.
- **Session resolution** (`_analysis_session`): an injected
  `analysis_transport` wins (tests); else the client's own `httpx` session
  (`_client`, the attribute every `OwnedHttpClient` subclass carries —
  production); else nothing, and the sweep publishes tier-A-only having
  opened no socket. `analysis_sleep` is the injected pacing.
- **"Cannot run yet" ≠ "failed"**: no events folded, or no live rate/minimum
  → the tier is spaced (backoff) so the offer is not re-made every cycle, but
  `_analysis_failed` stays False and nothing lights — whichever source is
  actually missing already tells its own story.
- `_pool_config`'s slot payload gains **`min_deposit_wei`** for the preset
  (R13) *without* touching `CONFIG_PAYLOAD_KEYS` or the frozen
  `READING_KEYS` — `_readings` iterates the tuple, so the key never reaches
  `build_signals` (pinned).
- **`_merge_analysis`** (WP3.4) — runs after `build_signals`, **before**
  `_label_with_ens` (the brief sketched after; deviation reasoned below).
  Three states, never collapsed: no last-good keeps every analysis key `None`
  and seeds `row["link_conf"] = None` on every leaderboard row (R9);
  analyzed-none is a representable zero (`operators_count == 0`, real empty
  rows); analyzed merges **copied** rows (mutating the cached slot's rows
  would persist ENS names past their TTLs — pinned by
  `test_the_merge_never_mutates_the_persisted_slot_payload`), real int
  counts, the slot's own `analysis_as_of_hhmm`, the reader's linkage, and the
  share override.
- **ENS**: `clean_list_rows` addresses join `_rendered_addresses` (bounded —
  the adapter caps the rendered slice at `CLEAN_LIST_LIMIT` 20) and the fill
  loop writes `row["name"]`, so the clean list's identity cell is the
  leaderboard's exactly.
- **Degradation** (WP3.5): a failed sweep lights **`logs`** *only while there
  is no analysis last-good to serve*; with one, the keys ride behind their own
  marker and nothing lights; the banner clears when a later sweep publishes.
  No new group name — the frozen vocabulary is untouched.
- **`set_wallet`** (WP3.6) needs no analysis expiry: the sweep is about the
  population, so the next cycle's merge re-answers the four linkage keys from
  the already-held slot (documented in `set_wallet`'s docstring; pinned across
  member → control → stranger, with `manager._analysis_task is None`
  asserted).

## 2. The four payload states — exact key values

| key | not-yet-run | analyzed-none | analyzed-linked | degraded (failed, last-good held) |
|---|---|---|---|---|
| `operator_rows` | `None` | `[]` | rows (share-desc) | the last-good's rows |
| `segment_rows` | `None` | bands (non-empty) | bands | last-good |
| `clean_list_rows` | `None` | top ≤20, everyone | top ≤20 survivors | last-good |
| `operators_count` | `None` | `0` | `int ≥ 1` | last-good int |
| `clean_points` | `None` | `== points_total` | `int < points_total` | last-good |
| `clean_contributors` | `None` | population | survivor count | last-good |
| `points_total` | `None` | int (same snapshot) | int (same snapshot) | last-good |
| `analysis_as_of_hhmm` | `None` | `"HH:MM"` (spawn time) | `"HH:MM"` | the **old** sweep's `"HH:MM"` |
| `you_linked_state` | `None` | `"clean"` (analyzed wallet) | `"linked"` / `"clean"` / `None` (stranger) | from last-good |
| `you_linked_reasons` | `None` | `[]` | pattern phrases / `[]` / `None` | from last-good |
| `you_linked_group_size` | `None` | `None` | group size / `None` | from last-good |
| `you_clean_rank` | `None` | dense int | `None` (linked) / int (clean) | from last-good |
| `leaderboard_rows[].link_conf` | `None` (seeded) | `"clean"`/`None` | `"high"`/`"low"`/`"clean"`/`None` | graded off last-good |
| `degraded` | unchanged | unchanged | unchanged | unchanged **unless no last-good exists** → `⊇ ["logs"]` |

No wallet configured → the four `you_*` keys are `None` in every state and
`wallet` never degrades. A *failed* sweep with **no** last-good renders the
not-yet-run column plus `"logs"` in `degraded`.

## 3. The banding rule as shipped (ruling 5)

`link_conf` / operator `conf` are **structural**, never numeric: noisy-OR
floors every gated cluster at ≥ 0.77, so a numeric boundary bands nothing.

- `"high"` — ≥ 3 distinct evidence families **or** the `funding` family
  present (money provenance is the strongest measured discriminator: 10/10 on
  resolved farm samples vs 0/47 controls).
- `"low"` — exactly two families.
- `"clean"` — analyzed and in no cluster (in `clean_ranks`).
- `None` — not analyzed / sweep not run; renders `?`, never the empty cell
  that means clean.

`flagged` (Tier A's bool) is never touched. The rule is documented in the
adapter's module docstring and pinned by
`test_link_conf_bands_come_from_evidence_structure_not_the_raw_number`.

## 4. `flagged_points_share_pct` — override-with-fallback, as shipped

The analysis last-good's share (`res.flagged_points / res.total_points × 100`,
multiplied once, `None` when `total_points == 0`) **wins when present**; Tier
A's `build_signals` value stands otherwise — pinned by the mandated
`test_the_farm_share_prefers_the_analysis_value_when_it_has_run`, both
directions (override takes effect; a slot with `share: None` leaves Tier A's
value standing). Consequence WP6 should document: an **analyzed-none** sweep
publishes share `0.0`, which overrides a non-zero Tier-A number — that is the
library's honest finding at that snapshot, and FARM and OPERATORS then tell
one story.

## 5. The funding-cursor bounds chosen (R3)

| constant | value | why |
|---|---|---|
| `FUNDING_BUDGET` | 200/sweep | ~70 s at Blockscout's measured ~3 req/s, inside the 1800 s TTL; the WP2 recipe's own example |
| `TX_BUDGET` | 400/sweep | ten 40-call batches (publicnode's measured clean size) |
| `CONTROL_MARGIN` | 24 | small deterministic baseline, chain order |
| page bound | start 20 (sources default), ×2 on `"pages"`, cap `MAX_FUNDING_PAGES` 80 | 80 pages = 4 000 txs, far past any farm wallet; longer histories stay honestly pending |
| `TIER_ANALYSIS` TTL / backoff | 1800 s / 300 s | PRD §4's band low end (coverage grows faster); backoff < TTL or it is decorative |

Coverage arithmetic on the real population: ~6.3k candidate members →
full funding coverage in ~32 sweeps (~16 h of uptime), fingerprints in ~16.
Gas needs ≥ 90 % of a component, so the big components corroborate late —
deliberate: recall grows, precision never dips, and the ≥2-family gate holds
throughout. The cursor (`known` maps, `pending`, `reasons`, `page_bound`)
persists in the slot payload, so coverage survives restarts.

## 6. TDD evidence (RED → GREEN, per task)

| task | RED captured | GREEN |
|---|---|---|
| WP3.1 | collection error (`curator_clusters` absent), 24 tests | 24 passed |
| WP3.2 | `ImportError: SLOT_CLUSTERS` (collection), then the tier/slot pins | cache 73 passed |
| WP3.3 adapter | 8 failed (`candidate_targets`/`fetch_enrichment` absent) | 32 passed |
| WP3.3 manager | `TypeError: unexpected keyword 'analysis_transport'` + 4 named | manager 109 passed |
| WP3.4 | 5 failed (merge absent: dead-vs-empty, keys-filled, farm-share, link_conf, ENS-to-clean-list) | tests/data 2230 passed |
| WP3.5 | 2 failed (banner tests, `_degraded` fold absent) | 236 passed (4 curator files) |
| WP3.6 | green on write (the WP3.4 merge already recomputes per cycle) — proven by mutation instead: dropping the merge's `you_linkage` update reddens both pins + the keys-filled test | restored, green |
| WP3.7 | green on write (agreement over working code) — proven by mutation: a drifted config (minimum knob dropped) reddens the flagged-set equality | restored, green |
| WP3.8 | 1 failed first run (the socket guard caught the word "httpx" in the manager's own docstrings; refined to AST-import + construction-token checks) | 39 passed |
| WP3.9 | first full-suite run: **1 failed** — WP0's `test_the_sybil_fixtures_all_live_in_one_directory` enumerates the sybil fixture directory by hand, and the mandated `adapter_agrees.json` grew it.  The pin's own docstring anticipates "a later WP adds a slice"; the enumeration grew by one commented entry (the CLAUDE.md hardcoded-lists-grow rule, the SLOTS/TIERS precedent) | full suite green (§9) |

One implementation was **wrong on first run and a probe caught it** (the part
of TDD worth reporting): my degradation tests initially inherited a
`logs`-degraded flag from the *cross-check*, because `_analysis_manager`'s
state double claimed `tx_count=222` over a nine-event farm fold — the
cross-check correctly declared the fixture's own fold short at loop teardown.
The double now agrees with its events (`tx_count=9`), which also removed a
real scheduling nondeterminism from every test using it.

## 7. The mandated bites (mutate → red → restore)

| # | mutation | designated red test | result |
|---|---|---|---|
| 1 (mandated) | `pattern_language` passes raw library reasons through | `test_a_raw_library_reason_never_passes_the_boundary` **and** `test_a_hostile_persisted_payload_is_re_guarded_on_the_way_out` | 2 red ✓ |
| 2 | bump `_SCHEMA_VERSION` to 2 | `test_an_older_file_without_the_slot_still_loads_its_other_sections` | red ✓ (+4 schema neighbours) |
| 3 (mandated) | `_cycle` awaits `_pool_analysis` instead of spawning | `test_the_first_payload_is_not_behind_the_analysis_read` — the 5 s timeout fires | red ✓ (5.39 s) |
| 4 (mandated) | merge seeds `[]` on the three row keys when no analysis has run | `test_with_no_analysis_last_good_every_analysis_key_is_none_never_empty` | red ✓ |
| 5 | merge drops the `you_linkage` update | the two WP3.6 pins + `..._every_one_of_the_twelve_keys_is_filled` | 3 red ✓ |
| 6 | `build_analysis` detects with a drifted config (minimum knob `None`) | `test_the_adapter_agrees_with_the_library_on_the_committed_fixture` | red ✓ |
| 7 | `slot_payload` writes `is_sybil: true` into a group | `test_the_analysis_slot_persists_no_boolean_verdict` | red ✓ |

Each restored from the exact original text; suites re-run green after every
restore. (Bite 2's restore initially *looked* red — stale `.pyc`: the two seds
landed in the same second with identical file size, so Python's
mtime+size pyc check kept the mutated bytecode. `__pycache__` cleared,
verified green. Noted so a future agent recognises the shape.)

## 8. The WP6 hand-off

Behaviors the docs must describe:

- **The `f` view fills itself in over time.** First launch: "analysis
  unavailable" (not-yet-run) → within ~a minute the first tier-A publish →
  funding/fingerprint coverage extends every ~30 min (bounded sweeps), so
  operators appear and confidences band upward across the first hours of
  uptime. The `analysis_as_of_hhmm` marker is the sweep's own spawn time and
  moves on its own schedule — deliberately not the title bar's `as of`.
- **`flagged_points_share_pct`** is override-with-fallback (§4 above,
  including the analyzed-none `0.0` consequence). FARM (rail) and OPERATORS
  (panel) therefore agree once the sweep has run.
- **`link_conf` vocabulary** as in §3; the leaderboard's `?` means "not
  analyzed", the empty cell means clean, and `flagged` stays Tier A's.
- **No verdict is persisted**: the slot holds revisable rows, groups carry a
  band *word* and families, and the cache file is scanned for booleans in
  tests. The clean list may re-admit a wallet on a later sweep.
- **Degradation**: analysis failures fold into `logs` only when there is
  nothing to serve; otherwise the stale `analysis_as_of_hhmm` is the signal.
- **`sybilkit` is now a runtime dependency of the dashboard** (see concern 1
  — pyproject is not WP3's file).
- The analysis slot adds ~0.5–1 MB to `~/.maxpane/curator_cache.json` on the
  real population (groups' member lists + the full `clean_ranks` + the
  enrichment cursor). Deliberate: it is what makes any wallet's linkage and
  clean rank answerable across restarts without a re-sweep.
- `segment_rows` arrive ordered operators → cohorts → multiplier bands →
  hour bands (WP4's row cap renders the first 8; concern 5 of its report).
- For the README's data-sources section: the analysis enrichment uses
  publicnode/tenderly (`eth_getTransactionByHash` batches) and Blockscout
  (first-funder pages) through `sybilkit.sources`, keyless, budgeted,
  borrowing the manager's own HTTP session.

## 9. Sign-off — suite state

Full maxpane suite (`.venv/bin/python -m pytest -q`, `testpaths = ["tests"]`):

```
4652 passed, 6 warnings in 384.36s (0:06:24)
```

**0 failed, 0 skipped, 0 xfailed** — nothing was skipped or expected-failed
to get there; the six warnings are the pre-existing Textual deprecation noise
(same count as WP4/WP5's runs, so no new warning — and no "exception was
never retrieved" / teardown traceback anywhere in the run).  4587 at WP4's
fix-round sign-off; the +65 are this WP's new tests net of none removed.
Alongside: `sybilkit` suite **289 passed, 1 xfailed** (untouched, the strict
todo), Rust crate **443 passed** (untouched).

The four curator data suites: **245 passed** (manager 117 · cache 73 ·
clusters 39 · degradation 16); the two curator UI suites re-run green
alongside (**436 passed**, untouched files). `close()` cancels **both**
detached tasks and saves (pinned; no "exception was never retrieved" and no
teardown tracebacks in the run). `git diff main --
maxpane_dashboard/analytics/curator_signals.py` empty at sign-off.

## 10. Self-review

- **Ownership**: `git diff ed780bd..HEAD --stat` lists exactly the eight
  owned/created files; every commit pathspec-limited.
- **No socket in any test**: structural (the WP3.8 guard: no httpx import, no
  client construction in adapter or manager; every test-built `AsyncClient`
  carries a transport) plus behavioral (the no-session bomb; every fetch in
  the suites drives `httpx.MockTransport`).
- **Wei→ETH divided exactly once**: the manager's own count is still pinned
  at zero by the shipped test; the adapter's single `/ _ETH` site is pinned by
  `test_the_adapter_divides_wei_to_eth_exactly_once`.
- **Truthiness discipline**: both sweep results are tested `is not None`;
  the null-result tx pass is pinned healthy.
- **The brief's ordering deviation** (merge before `_label_with_ens`, not
  after) is documented in `_cycle` and in the merge's docstring: the clean
  list's identity cells are the leaderboard's exactly, and a merge that ran
  second would hand the labeller rows it never saw.
- **One edit outside the listed files**: the hand-typed fixture enumeration in
  `tests/data/test_curator_sybil_data.py` grew by the one mandated slice
  (`adapter_agrees.json`).  Growing that pin is the change's necessary
  consequence — the alternative was a red WP0 pin or an uncommitted mandated
  fixture — and the entry carries a comment pointing at the derivation test.
- **Copies stay copies**: `CURATOR_ANALYSIS_KEYS` is imported, never re-typed;
  the farm doubles live once in `test_curator_clusters` and are imported by
  the manager/degradation suites (the house import-not-retype rule).

## 11. Concerns

1. **`sybilkit` is not declared anywhere maxpane's installer can see.**
   `curator_clusters` imports it at module scope, so `pyproject.toml` needs
   `sybilkit` in `dependencies` before any release — but `pyproject.toml` is
   not WP3's file, and `sybilkit` is not on PyPI yet (name verified free in
   WP0). I installed it editable into `.venv` so the app and suite run;
   a `pip install maxpane` from a wheel built today would crash on import.
   **Controller/WP6 must resolve the packaging** (publish sybilkit, vendor a
   path dependency, or gate the import). Highest-priority concern.
2. **The teardown-scheduling fact is now known and worked around, not
   changed**: a detached task spawned in the cycle's last stretch takes its
   first step at loop teardown, so a body with no real awaits (the crosscheck
   against a FakeClient) *completes* there. My fixture fix removed the
   observable consequence; the underlying looseness is shared with the
   shipped crosscheck and is not WP3's to re-architect. Flagged for WP6's
   audit narrative.
3. **The share override on analyzed-none** (§4): a library run that finds
   nothing publishes `0.0` and overrides a non-zero Tier-A FARM number. I
   believe this is the ruling's intent (the analysis value wins when
   present); if review prefers "None share → fallback" for the zero case,
   it is a two-line change in `slot_payload`/`_merge_analysis`.
4. **Production sweep sharing the RPC session**: the enrichment borrows the
   client's `_client` (private-by-convention attribute of the house
   `OwnedHttpClient` mixin, read with `getattr`). It is closed after both
   detached tasks are cancelled, so ordering is safe; a future client
   refactor renaming `_client` degrades the sweep to tier-A-only silently
   (the honest direction, but worth a line in the client's docstring —
   reported here rather than edited, `curator_client.py` is not mine).
5. **Blockscout page-bound telemetry**: WP2's concern 4 stands — 20 pages is
   a guess. The doubling ladder (20→40→80) is self-correcting but the first
   live sweep should be watched for `"pages"` pendings (they log nothing
   today; the reasons are visible in the persisted slot payload).
6. **Not measured here**: a real-population end-to-end sweep timing through
   the manager (the pure folds and the budgets are measured; the paced
   Blockscout pass is arithmetic at ~3 req/s, not a wall-clock measurement
   through `_pool_analysis`). First live run should confirm ~70–90 s.

---

# Fix round 1 (review of `ed780bd..245d967`) — 2026-08-18

Approved, with one plan-mandated Important, the controller's pre-ruled guarded
import, and three ruled-in minors.  All fixed test-first (RED captured where
the behaviour was new; the two agreement-style pins proven by mutation), each
restore verified, pathspec-limited commits, captures untouched.

## I1 — the analyzed-none state, pinned end to end

`test_an_analyzed_none_slot_reaches_the_flat_dict_as_real_zeros`
(`tests/data/test_curator_manager.py`) stores a **real** analyzed-none publish
(the farm with no second family: the amount component exists, no cluster does)
and asserts in the flat dict: `operator_rows == []`, `operators_count == 0`
(an `int`, not `None`), `segment_rows` non-empty with no "largest operators"
band (the none-found semantics: the population bands exist without
operators), `clean_points == points_total > 0`, `clean_contributors == 9`,
`flagged_points_share_pct == 0.0` (the ruled override), `analysis_as_of_hhmm`
a real HH:MM, and for the configured wallet `you_linked_state == "clean"`,
`you_linked_reasons == []`, a dense `you_clean_rank`, every leaderboard row
graded `"clean"`/`None`.

**Mandated bite recorded:** changing the merge's count read to
`_opt_int(slot.get(key)) or None` — the exact collapse class the pin exists
for — reddens it (`1 failed`); restored, `tests/data/` whole: 2249 passed.

## Ruled guarded import — the packaging gap's compatibility story

`curator_clusters.py`'s sybilkit imports now sit in a module-level
`try/except ImportError` setting **`SYBILKIT_AVAILABLE`**; the four analysis
entry points (`build_preset`, `build_analysis`, `candidate_targets`,
`fetch_enrichment`) raise a named `ModuleNotFoundError` through
`_require_sybilkit()` so a direct caller never sees a bare `NameError`.  The
manager checks the flag first in `_pool_analysis`: absence is the existing
cannot-run path — spaced retry, **no banner**, one INFO log line per process
(`_sybilkit_missing_logged`).  The merge, the R9 `link_conf=None` seeding and
a **held last-good** keep working with the library gone (they read persisted
payloads, never the library).  The AST guardrail still lists
`curator_clusters` as the sole importer — no test churn.

Covering tests (RED under the missing flag, GREEN after):
`test_a_missing_sybilkit_is_analysis_unavailable_never_a_crash` (full
contract, twelve keys None, `degraded == []`, link_conf seeded, tier spaced)
and `test_a_held_analysis_still_serves_when_sybilkit_is_gone`.  The **real**
`except ImportError` branch (which the flag monkeypatch cannot execute) was
verified in a subprocess with a meta-path blocker: both modules import
cleanly, `SYBILKIT_AVAILABLE is False`, the entry points raise the named
error, and the payload-side lookups (`grade_of`/`you_linkage`/
`merge_leaderboard_grade`) function fully without the library.

**WP6 hand-off note (ruled):** maxpane's `pyproject` gains `sybilkit` as a
dependency at the first release AFTER sybilkit publishes; until then the
guarded import is the compatibility story.  (This supersedes concern 1's
"highest priority" framing — the gap is now survivable, not crashing.)

## M2 — enrichment outage drives the retry clock

`_pool_analysis` now reads `tx_ok`/`funding_ok`: every attempted source dead
→ the tier-A(+accumulated) result **still publishes** (data-wise honest) but
the tier is marked **failed** (backoff ~300 s, completion-stamped) with a
warning; a partial outage keeps `mark_fetched` and logs which source's
coverage stalls.  "Attempted" is the operative word: a sweep whose only
asked-question source died retries on the backoff too.  Covering:
`test_a_sweep_whose_every_source_died_retries_on_the_backoff` (dead
transport; publish lands, `_analysis_failed` stays False, no banner, due
again after the backoff, not the TTL).

## M3 — an unknown grade band is unknown

`grade_of` on a corrupted/unknown `conf` now answers `None` (renders `?`),
never `"low"` — a confidence word off bad data is a claim.  The membership
fact (`you_linkage`: linked, size, reasons) is untouched.  Covering:
`test_an_unknown_grade_band_is_unknown_never_low`
(`tests/data/test_curator_clusters.py`).

## M4 — failures stamp the retry clock at completion

All three `mark_failed(TIER_ANALYSIS, …)` sites use `float(self._clock())`
(completion) instead of the spawn `now`; freshness stamps
(`store_analysis(ts=now)`) stay spawn-time.  Covering:
`test_a_failed_sweeps_backoff_counts_from_completion_not_spawn` (a sweep that
takes 200 s to die is due at completion+300, not spawn+300 — RED before,
spawn-time stamping made the tier due 200 s early).

## Deferred, as ledgered

The page-bound ratchet gating on attempted passes; `_analysis_failed` not
clearing on cannot-run (now carries the ruled one-line comment naming the
contrived sequence); the `_cancel_analysis` parity note.  Untouched.

## Fix-round test evidence

- RED: `5 failed, 2 passed` on the focused selection (absence ×2, M2, M4, M3
  — I1 green on write, its mandated mutation bite recorded instead).
- GREEN: the four curator data suites **251 passed**; `tests/data/` whole
  **2249 passed** after the bite restore.
- Full maxpane suite after the round (`.venv/bin/python -m pytest -q`,
  `testpaths = ["tests"]`), pasted verbatim — **nothing skipped or xfailed**,
  the six warnings are the pre-existing Textual noise, and the count grew by
  exactly this round's six new tests (4652 → 4658):

```
4658 passed, 6 warnings in 363.23s (0:06:03)
```

## Fix-round commits

| SHA | Subject |
|---|---|
| `96a7ebb` | fix(curator): the fourth payload state, the guarded import and honest retry clocks |
| (report) | docs(curator): WP3 fix round 1 report |
