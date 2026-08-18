# WP6 — registration, docs, packaging, audit, live smoke

**Branch** `feature/curator-sybil` · **base** `f0002d0` · **date** 2026-08-18

WP6 wrote no source and modified no shared code file. Its outputs are `README.md`,
`CLAUDE.md`, `sybilkit/README.md`, `docs/curator_sybil_implementation_plan.md` (§6
close-out), `tests/fixtures/curator/sybil/README.md` (ledger close-out), and the audit
/ packaging / smoke records carried in commit bodies.

---

## 0. Commits

| sha | subject |
|---|---|
| `badb3a1` | docs: document the sybil analysis view and the sybilkit tool |
| `9bdb87d` | docs: bring CLAUDE.md up to the sybil-analysis expansion |
| `7712241` | docs(sybilkit): finalise the standalone README |
| `d13c8d7` | test: audit the sybil build's keyless, no-verdict and mutation guarantees |
| `ee9c985` | build: document (and optionally add) the separate sybilkit publish path |
| `a520303` | chore: full suite green across both distributions with the sybil expansion |
| _(see §7)_ | chore: live smoke run — analysis view and sybilkit CLI, keyless |
| _(see §8)_ | docs: close the sybil-analysis ledger and update memory |

---

## 1. WP6.1 — `README.md`

Added, in the Dashboards section, **"THE LIST — the linked-wallet view (`f`)"**: why the
sqrt curve makes wallet-splitting profitable and therefore makes the question interesting;
the three panels (OPERATORS / SEGMENTS / CLEANED LIST) with a real evidence string and the
`⚑`/`◌`/`?` grading; `e` writing `~/.maxpane/curator_clean_list.json` (+ `.csv`) with the
panel naming the path; the `y` view's `linked` line and clean rank; and a paragraph that the
whole thing is **read-only analysis in pattern language and never an accusation** — groups
scored not wallets, two independent evidence families required, no verdict persisted, a later
sweep can re-admit. Plus the fill-in-over-time behaviour and the separate `as of HH:MM` clock.

Other README edits:

- Dashboards table row for THE LIST gains "linked-wallet analysis".
- Keyboard-shortcuts paragraph names `f` and `e`, and quotes the status hints **as the screen
  renders them**: `c panels · y you · f linked`. The WP4 `y wallet` → `y you` rewording is
  carried; `e` is explained as absent from the hints on purpose.
- THE LIST's width paragraph gains the analysis view's **137** and the row minimums (`f` whole
  at 48 rows, `y` at 40, `‹ taller` below each).
- New top-level section **"sybilkit — the analysis library, on its own"**: install matrix, the
  three CLI verbs, maxpane-independence, and the packaging story (a maxpane release does not
  publish it; `pip install maxpane` does not pull it in yet; the guarded import degrades the
  view instead of breaking the install).

**Width table untouched.** `CURATOR_FULL_LAYOUT_COLUMNS` is still 138 and
`FULL_LAYOUT_COLUMNS` still 143, so there was nothing to change — and
`_readme_width_bands()` in `tests/test_surf_registration.py` parses that table's rows and
per-band surf panel names, which is why it was read before touching anything near it. 106
registration/doc tests re-run green after the edit.

No `--game` entry, no menu row, no renumber: this is an expansion of dashboard 2, not a
dashboard 9.

---

## 2. WP6.2 — `CLAUDE.md`

New subsection under the dashboards table: **"THE LIST's linked-wallet analysis — the
`sybilkit` seam (2026-08-18)"**, covering:

- third view, not a ninth dashboard → **no six-surface renumber**;
- `data/curator_clusters.py` as the single importer (named test:
  `test_only_curator_clusters_imports_sybilkit`, which walks every `.py`), and as the
  translation boundary that re-checks *persisted* strings on the way out;
- where the word "sybil" lives (the library; in maxpane only in the adapter's
  `FORBIDDEN_WORDS`, comments and identifiers — never a rendered string, and never at all in
  `analytics/curator_signals.py`, which is byte-identical to what shipped);
- the guarded import **as the packaging story**: maxpane's `pyproject.toml` names `sybilkit`
  only at the first maxpane release *after* sybilkit publishes, and until then absence
  degrades the view rather than breaking `pip install maxpane`;
- the detached Tier-B+C sweep on the `_spawn_crosscheck` precedent, `TIER_ANALYSIS`
  (1800 s TTL, 300 s after failure), `SLOT_CLUSTERS`, the candidate-only funding budget, and
  the fold into the `logs` degraded group only when there is nothing to serve;
- no verdict persisted, and why the banding is **structural** (noisy-OR floors every gated
  cluster at ≥ 0.77, so a numeric cut would band nothing; the library's own 0.5 flag threshold
  is inert for the same reason, hence `flagged` == clustered).

Also: architecture block gains `sybilkit/` as a second in-repo Python distribution (sibling of
the `maxpane/` Rust crate, built with `python -m build sybilkit/`, never by the root build);
the keys paragraph gains `f`/`e` and the `y wallet` → `y you` rewording with its reason; the
files-on-disk line gains `~/.maxpane/curator_clean_list.json` (+ `.csv`).

**Width section: one sentence, as ruled** — the analysis body measures **137**, binding panel
`CuratorOperators`, one column inside `CURATOR_FULL_LAYOUT_COLUMNS` and six inside FWA's 143,
plus the 48/40-row minimums. The `198 → 172 → 143 → 176 → 152 → 143` record is **not**
appended to: it tracks the app-wide number, which did not move.

One correction of stale pre-existing content, since I own the file: the Tests block said
"~2100 tests". It is 4658. It now also lists the sybilkit suite with the reason its
interpreter matters (without `[sources]`, its fetcher tests *skip* rather than fail).

---

## 3. WP6.3 — `sybilkit/README.md`

The `# TODO(WP6)` marker is resolved, with the two sections it named.

**"The THE LIST preset"** — `sybilkit.curator` is one preset and the worked example for
writing another, not the library's subject; a runnable `CuratorPreset` → `detect` →
`segments`/`clean_list` example; and why the preset's first two fields have no defaults (they
are chain readings; 1000 and 0.05 ETH are measurements of one deployment). Plus the **adapter
boundary** in both directions: nothing here imports maxpane; nothing this library says reaches
a screen unfiltered; and the dashboard's import of it is guarded.

**"Releasing"** — Option A, with the fact it rests on read out of the workflow file rather
than assumed (see §5).

---

## 4. WP6.4 — the audit

### The three mandated greps, pasted

```
$ rg -n "api_key|apikey|x-api-key|Authorization|keystore|private_key|MAXPANE_KEYSTORE" \
       sybilkit/ maxpane_dashboard/data/curator_clusters.py
sybilkit/tests/test_fixtures.py:28:def test_no_fixture_carries_an_api_key() -> None:
sybilkit/tests/test_fixtures.py:34:        for banned in ("api_key=", "apikey=", "x-api-key", "authorization:"):
```

Two hits, **both inside the test that forbids keys**. That is the guardrail, not a key. No
key, secret, keystore or private-key handling exists in either surface.

```
$ rg -n "sybil|cheat|fraud|attack|abuse|farmer" maxpane_dashboard/analytics/curator_signals.py
(exit 1 — nothing)

$ git diff main --stat -- maxpane_dashboard/analytics/curator_signals.py
(empty — byte-identical to what shipped; `find_clusters` still at line 821)

$ rg -ln "import sybilkit|from sybilkit" maxpane_dashboard/
maxpane_dashboard/data/curator_clusters.py
```

Exactly one file, and its ten imports sit inside the `try/except ImportError` that sets
`SYBILKIT_AVAILABLE`.

```
$ git diff main --stat -- maxpane/
(empty — the Rust crate is untouched by this build)
```

### The mutation bites — eight EXECUTED

Method for each: byte-copy the file to the scratchpad, mutate, run the designated test,
restore from the copy, clear `__pycache__` (WP3's stale-pyc lesson), confirm
`git diff --quiet <path>`. Never `git checkout --`.

| # | file:line | mutation | designated test | result |
|---|---|---|---|---|
| 1 | `sybilkit/src/sybilkit/curve.py:44` | `//` → `round(…/…)` | `test_the_curve_floors_never_rounds` | **red** (6 failed) |
| 2 | `curve.py:44` | `isqrt` → `int(math.sqrt(…))` | `test_float_sqrt_is_off_by_one_on_a_large_weight` | **red** (2 failed) |
| 3 | `curve.py:44` | divide before multiply | `test_a_sub_eth_weight_keeps_its_points` | **red** (6 failed) |
| 4 | `sybilkit/src/sybilkit/signals/funding.py:60` | peel chain fires on **any** contributor funder | `test_a_main_wallet_funder_outside_the_component_is_not_evidence` | **red** |
| 5 | `sybilkit/src/sybilkit/cluster.py:226` | family gate `config.min_families` → `1` | `test_one_family_never_convicts` **and** `test_no_control_is_flagged` | **both red** (9 failed) |
| 6 | `sybilkit/src/sybilkit/sources/logs.py:196` | parse and adopt the provider's suggested range | `test_a_providers_suggested_retry_range_is_never_adopted` | **red** — spans `[800, 798, 797, 796]`, the one-block-per-round-trip livelock reproduced |
| 7 | `maxpane_dashboard/data/curator_manager.py:1576` | `_spawn_analysis(…)` → `await self._pool_analysis(…)` | `test_the_first_payload_is_not_behind_the_analysis_read` | **red** by `TimeoutError` in 5.39 s |
| 8 | `maxpane_dashboard/widgets/curator/operators.py:234` | drop `safe_markup` on the reasons cell | `test_a_hostile_operator_reason_renders_literally` | **red** — the deferred `MarkupError` kills the harness app |

That covers every bite the brief named (the family gate, the funding fold, the three
curve-floor variants, the first-paint spawn) plus WP2's mandated livelock and WP4's mandated
markup bite.

**Worth recording for the next auditor.** The obvious spelling of bite 4 — `if funder in
ds.first_index` — does **not** redden the designated test, because that fixture builds its
`Dataset` with an empty `first_deposits` list, so `first_index` is empty and the mutated
branch never executes. Deriving the contributor set from `ds.deposits` reddens it as designed.
A bite that fails to bite is not always a weak test; check the mutation reached the code first.

### Inspected, not executed

Verified to **exist** and to name their own mutation in their docstring:
`test_curator_keys_covers_the_local_signature_map` (WP4 bite 2);
`test_a_raw_library_reason_never_passes_the_boundary` +
`test_a_hostile_persisted_payload_is_re_guarded_on_the_way_out` (WP3 bite 1);
`test_with_no_analysis_last_good_every_analysis_key_is_none_never_empty` (WP3 bite 4);
`test_the_analysis_slot_persists_no_boolean_verdict` (WP3 bite 7);
`test_passes_is_the_two_bars_together` + `test_a_heuristic_tuned_to_zero_recall_fails_the_gate`
(WP2 bite 4); `test_operators_none_is_unavailable_and_zero_is_a_real_negative` (WP4 bite 3);
`test_link_conf_grades_the_flag` (WP5 bite 5);
`test_a_failed_export_never_leaves_a_stale_receipt` (WP4 fix round).

After every restore the affected suites were re-run green and `git status --porcelain` showed
no tracked modification.

---

## 5. WP6.5 — the second publish path

**Choice: Option A** — a documented manual release step in `sybilkit/README.md`.

Option B (`.github/workflows/publish-sybilkit.yml` on a `sybilkit-v*` tag) was **deliberately
not added**. The controller allowed it conditionally; I declined because sybilkit has no PyPI
project and no trusted-publishing configuration yet, so such a job could only ever fail at the
upload step, and a red release workflow teaches a reader less than a documented command that
works. It can be added the day the PyPI project exists. *(Flagged as a judgment call — see
§10.)*

The fact, read out of the file rather than inferred: `.github/workflows/publish.yml` triggers
on `v*`, checks out, and runs `python -m build` with no `working-directory` and no `cd`. The
root `pyproject.toml` packages `maxpane_dashboard` alone.

Both builds verified, into the scratchpad so the repo's `dist/` is untouched:

```
$ python -m build --outdir <scratch> .
Successfully built maxpane-0.7.1.tar.gz and maxpane-0.7.1-py3-none-any.whl
  wheel: 294 entries · top-level {maxpane_dashboard, maxpane-0.7.1.dist-info}
  sybilkit entries: []
  Requires-Dist: httpx>=0.27 / pydantic>=2.0 / textual>=0.80   ← no `sybilkit`

$ python -m build --outdir <scratch> sybilkit/
Successfully built sybilkit-0.0.1.tar.gz and sybilkit-0.0.1-py3-none-any.whl
  wheel: 25 entries · top-level {sybilkit, sybilkit-0.0.1.dist-info}
  py.typed shipped · Requires-Dist: httpx>=0.27; extra == 'sources'
```

Core wheel in a scratch venv holding only pip/setuptools:

```
import sybilkit              OK
from sybilkit import detect  OK
import sybilkit.sources      OK   (httpx not in sys.modules, and not installed)
sybilkit --help              OK   (analyze / segments / export-clean-list)
```

---

## 6. WP6.6 — the three suites

```
maxpane   .venv/bin/python -m pytest -q
          4658 passed, 6 warnings in 366.81s      (nothing skipped, nothing xfailed)

sybilkit  cd sybilkit && ../.venv/bin/python -m pytest -q
          289 passed, 1 xfailed in 9.65s          (httpx present — see the caveat)

rust      cd maxpane && cargo test
          210 + 216 + 17 = 443 passed, 0 failed;  git diff main -- maxpane/ is EMPTY
```

The maxpane suite was run twice: once at the start of WP6 and once after all doc commits and
after every audit mutation was restored. Both 4658.

`git diff main --stat`, pre-existing files only: `CLAUDE.md`, `README.md` (WP6);
`data/curator_models.py` (WP0); `data/curator_manager.py`, `data/curator_cache.py` (WP3);
`screens/curator.py`, `themes/minimal.tcss` (WP4); `widgets/curator/leaderboard.py`,
`widgets/curator/wallet.py` (WP5); `widgets/curator/__init__.py` (WP4, +33, exports only —
not named in the brief's list but structurally required); tests. New: `sybilkit/`,
`data/curator_clusters.py`, the three new widgets, the sybil fixtures, `docs/`. **No stray
edit by any WP.** The user's untracked live captures under
`tests/fixtures/curator/captures/live/` are untouched and still show as `??`.

---

## 7. WP6.7 — the live smoke

Ethereum mainnet, 2026-08-18 ~05:16–05:35 UTC. THE LIST was live at **hour 31, phase JUDGED,
list OPEN, 15,888 wallets, 115.3K ETH routed**. Read-only throughout: no transaction, no
signer, no key requested. `pip install -e .` was run first, so `--version` prints
`maxpane 0.7.1 / Python 3.11.15 (/Library/Vibes/autopull/.venv/bin/python)`.

### 7.1 The real TUI — it DID run

The dispatch allowed a substitute if the TUI would not run headless. It ran. I drove the real
`python -m maxpane_dashboard --game curator --font-size 0` inside a **160×50 pty** (a small
driver sizes the pty via `TIOCSWINSZ` and renders the app's own escape stream through `pyte`,
so what follows is literally what a user sees). `pyte` was installed into a scratch venv used
only by the driver; the app itself ran on the repo's `.venv`.

**Note for the next agent:** `--game curator` still opens the splash and the CHOOSE PANE menu.
The sequence is any-key, then `2`.

- **First paint at t+2 s**: clock, THE LIST, SURVIVAL, TOP OF THE LIST, TRENDS, the seven-row
  SIGNALS rail (`◐ FARM 440 fan-out groups · 47.9% of points`, `● YOU rank 8829 …`), ACTIVITY
  and CLOSEST CALLS, all populated from the live chain.
- Status hints render exactly `c panels · y you · f linked`.
- `f` → the three panels with the doomsday clock still on screen. The sweep had not landed at
  that point, so all three read their **explicit unavailable states** —
  `⚠ analysis unavailable` / `⚠ segments unavailable` / `⚠ clean list unavailable` — with `--`
  in every cell. Not blank, not zero.
- `e` on a not-yet-analyzed list wrote **nothing** and printed **no receipt**. That is the
  designed behaviour, and it is the right one: an empty allowlist file fabricated from a read
  that never happened outlives the outage.
- `esc` back; `y` → the wallet view with `clean -- unknown` and `linked -- unknown` pre-sweep;
  `c` swaps CLOSEST CALLS ↔ FAN-OUT PATTERNS (`view: closest` → `view: clusters` in the status
  bar); `q` exits cleanly, **exit code 0**.

### 7.2 The detached sweep, timed live

A direct keyless `CuratorManager.fetch_and_compute()` loop against the real cache:

```
cycle 1   1.96 s   73/73 contract keys · degraded=[] · ALL TWELVE analysis keys None
                   ← the first-paint guarantee, measured: the minutes-long sweep
                     is not inside this call
cycles 2–8  0.73–1.11 s each, analysis still 0/12
cycle 9   1.46 s   analysis landed — 11/12 filled
```

The twelfth, `you_linked_group_size`, is correctly `None`: this wallet is not in a group.

```
operator_rows list[158] · segment_rows list[39] · clean_list_rows list[20]
operators_count 158 · points_total 26,916,312 · clean_points 12,250,905
clean_contributors 6,443 · you_linked_state 'clean' · you_clean_rank 3,072
analysis_as_of_hhmm '05:20'   while the title bar read 'as of 05:24'
leaderboard link_conf: {None: 10} before → {'clean': 10} after
```

Two things worth naming:

- The **separate slower clock** is real and visible: `05:20` (the sweep's spawn time) against
  the title bar's `05:24`.
- `flagged_points_share_pct` moved **47.92 → 54.49** between cycle 1 and cycle 9. That is
  plan §6 risk 2's override-with-fallback **observed live**: Tier-A's number until the sweep
  has last-good, the library's afterwards, so the FARM rail row and the OPERATORS summary
  agree on one screen.

### 7.3 The analysis view over live rows

The real `CuratorScreen` composited at 138×48 over that live payload:

```
OPERATORS
158 linked groups · 54.5% of all points · as of 05:20
SIZE           EVIDENCE                                             POINTS     SHARE  SQRT   CONF
1,104 linked   ≈ W/k equal split: 14042.0Ξ across ×1003 of 14.0Ξ …  5,247,839  19.5%  33.2×  ◌
770 linked     consecutive join indices 3,723–3,752 · 0-block span… 3,250,132  12.1%  27.7×  ⚑
1,996 linked   consecutive join indices 1,051–1,090 · 1-block span… 1,812,237   6.7%  44.7×  ⚑
327 linked     identical odd 2.067Ξ send ×324 · metronomic drip …     528,966   2.0%  18.1×  ◌
300 linked     first funder is a member of the same cluster (peel…)   454,865   1.7%  17.3×  ⚑
896 linked     identical odd 0.098Ξ send ×4 …                         317,159   1.2%  29.8×  ⚑

SEGMENTS      39 bands: largest operators · early cohort · late cohort ·
              four multiplier bands · per-hour bands
CLEANED LIST  6,443 wallets · 12,250,905 of 26,916,312 pts ·
              linked groups removed · you #3,072 · as of 05:20
```

**`‹ widen` count at 138 columns: 0.** The hero region is pixel-identical before and after
`f` — the clock never leaves. No forbidden word appears anywhere on screen (the driver checks
`sybil/cheat/fraud/attack/abuse/wash/farmer` against the composited text).

`e` with `export_dir` redirected to a scratch directory (never `~/.maxpane`) wrote
`curator_clean_list.json` (2,885 B) and `.csv` (1,274 B), and the panel printed
`saved → …/export/curator_clean_list.json` — the path kept by its **tail** behind a leading
ellipsis, as designed. JSON is the `clean_list_rows` payload verbatim; the CSV header is
`clean_rank,address,points,credit_eth,name`.

`y` over the same payload: `clean  #3,072 with farms removed` and
`linked  not linked to any group`. Raw rank 8,829 → clean rank 3,072.

### 7.4 No verdict on disk

The real `~/.maxpane/curator_cache.json` grew a genuine `clusters` last-good slot (158
groups). Walked it recursively: **zero boolean values anywhere in the payload**. A group
carries `size` / `conf` / `families` / `reasons` / `members`, and `conf` is a band **word**
(`'low'`), not a number and not a bool.

### 7.5 Fresh-install backfill

Scratch cache path, nothing pre-existing: cold `fetch_and_compute()` in **5.78 s**, 73/73
keys, `degraded=[]`, 15,889 contributors backfilled from the live logs, a 15 MB cache written
on close. A DEBUG-level capture of the entire log stream contains **none** of `api_key`,
`apikey`, `x-api-key`, `authorization`, `keystore`, `private key`, `password`, `secret`.

### 7.6 Offline

Networking removed **process-locally** — every httpx proxy pointed at a closed port, so
nothing on the machine was reconfigured and no other process was affected — with a scratch
cache path:

```
73/73 keys, exact contract match
degraded == ['logs', 'state']
keys that are literally 0: []          ← nothing fabricated a zero
all twelve analysis keys: None
the process did not exit
```

Composited, the analysis body reads the three unavailable states with `--` cells and the title
bar carries `⚠ logs, state`.

### 7.7 sybilkit standalone, live and keyless

From the built wheel into a scratch venv (`pip install "sybilkit[sources]"`):

```
$ sybilkit analyze --contract 0xcB0b…FDA91 --from-block 25770000 \
                   --preset curator --tiers a --out cli_live.json
wrote 157 rows                                                    (7.9 s wall)
```

Reasons-shaped and verdict-free: cluster keys are
`cluster_id/size/members/reasons/confidence/points/points_share/span_blocks`, and **no boolean
field exists**. Totals: 26,913,344 total points, 12,338,648 clean, 15,885 contributors, 157
clusters. `generated_at` is `2026-08-18T03:25:47Z` — taken **from the data**, not the wall
clock.

`sybilkit segments` returns operators plus bands with the same provenance header;
`sybilkit export-clean-list` returned 6,452 entries with wei as decimal **strings**
(`"786000000000000000000"`).

The library's 157 clusters / 26,913,344 points against the dashboard's 158 / 26,916,312 is the
two reads being a few blocks apart, not a disagreement.

The **core-only** install (no httpx anywhere) runs `from sybilkit import detect` and
`sybilkit --help` — see §5.

### 7.8 What I could not exercise

- **`m` / `tab` / `r` / `t`** were not driven in the pty run (the sequence was already long and
  each adds a network cycle). They are unchanged by this build and covered by the existing
  registration and app-startup suites. `tab`-visits-curator-once-per-lap is asserted by
  `tests/test_app_startup.py`, not by me.
- **`w`** (the wallet prompt) was not driven live: it opens a modal that would have needed a
  typed address, and `set_wallet`'s tier/last-good invalidation is pinned by manager tests.
- **The settled phase** could not be observed — the game had not settled (see §8, risk 9).
- The **`e` receipt over a real analyzed list** was exercised through the screen harness with
  the live payload rather than inside the pty, because the pty run's sweep had not landed
  before the scripted key sequence reached `e`, and I would not redirect a pty run's export
  into the user's real `~/.maxpane`.

---

## 8. WP6.8 — the SYNTHETIC reconciliation and the plan close-out

### `rg "SYNTHETIC —" tests/ sybilkit/tests/`

42 hits, three marker generations. **`sybilkit/tests/` carries none of any generation.**

| generation | hits | disposition |
|---|---:|---|
| `SYNTHETIC — calibrated …` (this build's) | 6 | **permanent-synthetic**, reason recorded |
| `SYNTHETIC — re-point …` (the base curator build's) | 33 | not this build's ledger; untouched |
| `SYNTHETIC — permanent …` (base build's) | 3 | already closed there |

The six "calibrated" hits are the three `*_worst.json` slices under
`tests/fixtures/curator/sybil/`, the shared reader's `SYNTHETIC_MARKER` constant, and that
directory's README.

**Why they stay synthetic**, now written into
`tests/fixtures/curator/sybil/README.md` (whose old promise — "when WP3 exists, re-point them
at a real bundle and drop the marker" — is retired in place):

1. They are **worst-case envelopes**, not snapshots, and WP4/WP5 pin column widths against
   them. A live bundle is one sample of a population that moves every hour, so re-pointing
   width pins at one repeats exactly the surf IMD/FP-peg mistake CLAUDE.md records. The
   56-column `degraded_row` detail and the 12-character name probe exist *because* no single
   live bundle is guaranteed to contain them.
2. The numbers already **are** live reads — `docs/curator_sybil_data/` is the 2026-08-17 sweep
   of the real population, and `tests/data/test_curator_sybil_data.py` re-derives every value
   from it. "SYNTHETIC" here means *shaped into the panel schema by hand*, not *invented*,
   which is precisely why `labeled_subset.json` (same archive, unreshaped) carries no marker.

The marker **literal** is deliberately unchanged rather than reworded to
`SYNTHETIC — permanent`: `tests/curator_sybil_fixtures.SYNTHETIC_MARKER` and
`test_the_synthetic_slices_are_marked_and_the_measured_one_is_not` pin the exact string, and a
doc close-out is not a reason to move a pinned literal in three files. `rg "SYNTHETIC —"` still
finds all three, which is the property the ledger was built for.
`tests/data/test_curator_sybil_data.py` re-run after the README edit: **33 passed**.

### Plan §6 true-up

A close-out table was **appended** to §6 rather than edited into the risks, so a reader can
still see what was open. **All eleven landed on the recommendation**, so nothing is struck.
The two I verified against code rather than reports: `clean_list_export_path` is not in
`CURATOR_KEYS` (73 keys, checked in the interpreter), and `flagged_points_share_pct`'s
override-with-fallback was watched flipping live (§7.2). Risk 6's residual — "WP6 re-pins if
the live smoke disagrees" — **did not fire**: the analysis body still clears at 137 against
live rows.

---

## 9. MEMORY (for controller)

The dispatch reserves the memory write to the controller. Nothing was written to the memory
directory from here. Proposed content:

### 9a. New entry — `project_curator_sybil_analysis.md`

> **Curator Sybil / fan-out analysis** — THE LIST's third view, shipped on
> `feature/curator-sybil` 2026-08-18.
>
> **What it is.** `f` on `--game curator` swaps the dashboard body for MODE_ANALYSIS —
> OPERATORS / SEGMENTS / CLEANED LIST — with the doomsday clock left in place (`esc` backs
> out). `e` inside that view exports the cleaned list to `~/.maxpane/curator_clean_list.json`
> (+ `.csv`). The `y` view grew a `linked` line and a clean rank; the leaderboard's flag is
> confidence-graded (`⚑` high / `◌` low / empty clean / `?` not analyzed). Status hints read
> `c panels · y you · f linked` — `y wallet` was reworded to `y you` for one column.
>
> **`sybilkit` is a SECOND in-repo Python distribution** (sibling of the `maxpane/` Rust
> crate): its own `pyproject.toml`, tests, version and PyPI name. Keyless, maxpane-independent,
> stdlib-only core with an optional `[sources]` httpx extra, CLI
> `sybilkit analyze|segments|export-clean-list`. Built with `python -m build sybilkit/` and
> **published by hand** (`twine upload sybilkit/dist/*`) — the root `v*` workflow builds only
> maxpane and must never publish it.
>
> **The packaging ordering rule.** maxpane's `pyproject.toml` gains `sybilkit` as a dependency
> only at the first maxpane release *after* sybilkit is on PyPI. Until then
> `data/curator_clusters.py` — the **only** maxpane module importing it — guards the import
> behind `SYBILKIT_AVAILABLE`, and absence degrades the `f` view to `analysis unavailable`
> instead of breaking `pip install maxpane`.
>
> **Detection design.** Clusters are scored, never wallets: ≥ 2 independent signal families
> (amount / sequence / cadence / gas / funding) and ≥ 5 members, noisy-OR confidence. Because
> noisy-OR floors every gated cluster at ≥ 0.77, the on-screen banding is **structural** (high
> = ≥ 3 families or funding present; low = exactly two) and the library's own 0.5 flag
> threshold is inert, so `flagged` == clustered. Tier-B+C enrichment runs as a **detached**
> sweep on the `_spawn_crosscheck` precedent (long `TIER_ANALYSIS`, 1800 s / 300 s after a
> failure; `SLOT_CLUSTERS` last-good), candidate-members only and never the full population, so
> first paint stays ~2 s. Failures fold into the `logs` degraded group only when there is
> nothing to serve. **No verdict is ever persisted.**
>
> **The language split.** The dashboard says fan-out / linked / `⚑` and never "sybil" — that
> word lives only in the standalone library, and `analytics/curator_signals.py` is
> byte-identical to what shipped.
>
> **Measured live (2026-08-18, hour 31, JUDGED):** first analysis publish ~4 minutes after
> launch (8 poll cycles), 158 linked groups holding 54.5% of 26,916,312 points, 6,443 clean
> wallets. Analysis body clears at **137** columns (binding panel `CuratorOperators`); the `f`
> body is whole from 48 rows, the `y` body from 40. `CURATOR_FULL_LAYOUT_COLUMNS` (138) and
> `FULL_LAYOUT_COLUMNS` (143) both unmoved.

### 9b. Milestones bump — `project_milestones.md`

> **2026-08-18 — `feature/curator-sybil`.** THE LIST gains a **third view** (`f` linked-wallet
> analysis, `e` export), and the repo gains its **second in-repo Python distribution**,
> `sybilkit` (keyless EVM sybil/fan-out cluster toolkit, CLI, its own pyproject; not yet on
> PyPI — maxpane's guarded import is the bridge). Still 8 visible dashboards; no renumber.
> Suites: **maxpane 4658** (was 4442), **sybilkit 289 + 1 xfail**, **Rust 443**. The app-wide
> `FULL_LAYOUT_COLUMNS` is still 143.

---

## 10. Audit findings (reported, NOT fixed)

Nothing rising to a defect in another WP's code was found. Four observations, all minor, none
fixed:

1. **`widgets/curator/__init__.py` is not in the WP6 brief's expected-diff list** (§6). It is a
   +33-line export-only change, structurally required to expose the three new panels, and
   obviously WP4's. Reported only because the brief said to report anything outside the list.
2. **`~/.maxpane/maxpane.log` contains NUL bytes** from an earlier session, so `rg` treats it
   as binary and silently reports "binary file matches". Pre-existing, unrelated to this build.
   Pipe it through `tr -d '\0'` before grepping. Worth a line in a future CLAUDE.md hazards
   pass if it recurs.
3. **`--game curator` still shows the splash and the game-select menu** rather than going
   straight to the dashboard. CLAUDE.md's Build & run block says `--game fwa  # straight to one
   dashboard`. Either the comment is loose (the flag selects *which* dashboard, not whether the
   splash shows) or the intro is doing what `[intro] mode = "always"` in the user's
   `~/.maxpane/config.toml` asks. **Not touched** — it is pre-existing behaviour, unrelated to
   this build, and the config file makes the "always" reading likely.
4. **`sybilkit/pyproject.toml`'s `Homepage` points at `https://github.com/banse/maxpane`.** WP2
   ledgered this as a WP6 check. It is self-consistent (the README's own clone URL) and honest
   — sybilkit really does live in that repository — but a distribution published to PyPI under
   its own name pointing at another project's repo will read oddly to an installer. Flagged for
   the controller as a pre-publish decision, not changed: `pyproject.toml` is WP2's file.

Additionally, one *auditing* pitfall worth carrying forward rather than a defect: bite 4's
obvious mutation (`funder in ds.first_index`) does not bite, because that fixture's `Dataset`
is built with an empty `first_deposits` list. See §4.

## 11. Self-review

- **Did I only write what I verified?** Every factual claim in README/CLAUDE was checked
  against code or a run before it was written: the 137/138/143 numbers and the 48/40 heights
  against `ANALYSIS_MIN_HEIGHT`/`WALLET_MIN_HEIGHT` and the screen's own docstring; the
  single-import and byte-identical claims against `rg` and `git diff`; the status-hint string
  against `KEY_HINTS` *and* against the live pty screen; the export filenames against
  `CLEAN_LIST_BASENAME` and against files on disk.
- **One claim I wrote and then corrected.** My first CLAUDE.md draft said the word "sybil"
  appears nowhere in `maxpane_dashboard/` outside the adapter's forbidden-word list. That is
  false — it appears in `curator_models.py` comments (including "the de-sybilled list") and in
  `curator_manager._sybilkit_missing_logged`. I narrowed the sentence to the true and testable
  claim before committing: never in a rendered string, and never at all in
  `curator_signals.py`. Recorded here because the over-strong version is exactly the kind of
  sentence that survives into three documents.
- **Bites: eight executed, ten inspected.** The dispatch allowed inspection-only; I executed
  everything the brief named plus WP2's and WP4's mandated ones, because a bite table copied
  forward from a report is not an audit.
- **I did not fix anything I found.** §10 is a report, not a changelog.

## 12. Concerns

1. **The analysis takes ~4 minutes to first publish**, not the "~a minute" WP3's hand-off
   estimated. Nothing is wrong — the sweep is bounded and paced — and the docs I wrote say
   "the first minutes of uptime", which is accurate. But a reader who presses `f` at t+30 s
   sees three unavailable panels and may conclude the feature is broken. If anything is worth
   a follow-up, it is a *not-yet* state distinct from *unavailable* on the first run. Deliberately
   not built here: it would be new source, which WP6 may not write.
2. **Option B (the `sybilkit-v*` workflow) was declined**, and that is a judgment call the
   controller may want to reverse. My reasoning is in §5: no PyPI project, no trusted-publishing
   config, so the job could only fail. If the controller prefers it landed now, it is a
   ten-line file and the trigger must be `sybilkit-v*` **only**.
3. **`sybilkit` 0.0.1 is not on PyPI**, so today the guarded import is the *only* thing
   standing between an end user's `pip install maxpane` and a dashboard whose `f` view never
   works. That is by design and documented in three places, but it means the feature is
   effectively dev-only until someone runs the manual publish.
4. **The width pins now have a live counter-example available and did not use it.** §8 argues
   (correctly, I believe) that worst-case envelopes beat a live sample for *width*. But the
   live payload I captured — 158 operators, real reason strings — is exactly the kind of
   evidence a future re-pin should be checked against, and it exists now only in this session's
   scratchpad. If the controller wants it kept, it should be committed as a fixture by a WP
   that owns fixtures.
5. **`~/.maxpane/curator_cache.json` was written by the smoke** (it now carries a real
   `clusters` slot and grew 14.8 → 17.2 MB). That is normal app behaviour and is an
   improvement, not damage; a byte-copy of the whole `~/.maxpane` directory was taken before
   any of this and is in the session scratchpad if anything needs reverting.
